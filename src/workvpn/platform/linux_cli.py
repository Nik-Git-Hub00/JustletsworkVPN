import argparse
import ipaddress
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import ssl
    import certifi
except Exception:
    ssl = None
    certifi = None

APP_NAME = "WorkVPN"
SERVICE_NAME = "workvpn.service"
CUSTOM_USER_AGENT = "SingBoxVPN-Client/1.0-private"
CONFIG_NAME = "config_universal.json"
UUID_PLACEHOLDER = "__TYPE_UUID__"

ETC_DIR = Path("/etc/workvpn")
LIB_DIR = Path("/usr/lib/workvpn")
SETTINGS_PATH = ETC_DIR / "settings.json"
CONFIG_PATH = ETC_DIR / "config.json"
SING_BOX_PATH = LIB_DIR / "sing-box"
PACKAGE_CLI_PATH = Path("/usr/bin/workvpn")
SELF_INSTALL_CLI_PATH = Path("/usr/local/bin/workvpn")
SYSTEMD_UNIT_PATH = Path("/etc/systemd/system") / SERVICE_NAME


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def require_linux() -> None:
    if sys.platform != "linux":
        raise SystemExit("This CLI is intended for Linux.")


def run(cmd, *, check=True, capture=False):
    kwargs = {"text": True}
    if capture:
        kwargs.update({"stdout": subprocess.PIPE, "stderr": subprocess.PIPE})
    try:
        result = subprocess.run(cmd, **kwargs)
    except KeyboardInterrupt:
        raise SystemExit(130)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def sudo_cmd(cmd):
    if is_root():
        return cmd
    return ["sudo", *cmd]


def run_sudo(cmd, *, check=True, capture=False):
    return run(sudo_cmd(cmd), check=check, capture=capture)


def arch_name() -> str:
    machine = os.uname().machine.lower()
    if machine in {"x86_64", "amd64"}:
        return "linux-amd64"
    if machine in {"aarch64", "arm64"}:
        return "linux-arm64"
    raise SystemExit(f"Unsupported Linux architecture: {machine}")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def bundled_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return repo_root() / "runtime" / arch_name()


def find_runtime_sing_box() -> Path:
    candidates = [
        Path.cwd() / "sing-box",
        bundled_dir() / "sing-box",
        repo_root() / "runtime" / arch_name() / "sing-box",
        SING_BOX_PATH,
    ]
    for path in candidates:
        if path.exists():
            return path
    searched = "\n".join(f"  - {path}" for path in candidates)
    raise SystemExit(f"sing-box runtime was not found. Searched:\n{searched}\nRun scripts/fetch_runtime_linux.sh first.")


def normalize_server_url(value: str) -> str:
    value = (value or "").strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SystemExit("Invalid URL. Use https://")
    if value.endswith("/"):
        return urljoin(value, CONFIG_NAME)
    if parsed.path.endswith(CONFIG_NAME):
        return value
    return value + "/" + CONFIG_NAME


def url_origin(value: str) -> str:
    parsed = urlparse(value)
    return f"{parsed.scheme}://{parsed.netloc}" + parsed.path.rsplit("/", 1)[0].rstrip("/")


def ssl_context():
    if ssl is None:
        return None
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def http_get(url: str, timeout: float = 12.0) -> str:
    if urlparse(url).scheme != "https":
        raise SystemExit("Refusing to fetch over a non-HTTPS URL.")
    request = urllib.request.Request(url, headers={"User-Agent": CUSTOM_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=ssl_context()) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset)


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    return json.loads(SETTINGS_PATH.read_text())


def write_root_file(path: Path, content: str, mode: str = "0644") -> None:
    tmp = Path(f"/tmp/workvpn-{path.name}-{os.getpid()}")
    tmp.write_text(content)
    run_sudo(["install", "-D", "-m", mode, str(tmp), str(path)])
    tmp.unlink(missing_ok=True)


def ensure_dirs() -> None:
    run_sudo(["install", "-d", "-m", "0755", str(ETC_DIR), str(LIB_DIR)])


def systemd_unit() -> str:
    return f"""[Unit]
Description=WorkVPN sing-box service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={LIB_DIR}
Environment=LD_LIBRARY_PATH={LIB_DIR}
ExecStart={SING_BOX_PATH} run -c {CONFIG_PATH}
Restart=on-failure
RestartSec=2
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"""


def current_cli_path() -> Path:
    return Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).resolve()


def cli_self_install_target() -> Path | None:
    current = current_cli_path()
    if current in {PACKAGE_CLI_PATH, SELF_INSTALL_CLI_PATH}:
        return None
    return SELF_INSTALL_CLI_PATH


def same_file(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def ensure_runtime_and_service(sing_box: str | None = None, *, force: bool = False) -> bool:
    require_linux()
    src = Path(sing_box).expanduser().resolve() if sing_box else find_runtime_sing_box()
    if not src.exists():
        raise SystemExit(f"sing-box was not found: {src}")

    cli_src = current_cli_path()
    cli_target = cli_self_install_target()
    src_dir = src.parent
    bundled_libcronet = src_dir / "libcronet.so"
    target_libcronet = LIB_DIR / "libcronet.so"
    runtime_missing = (
        force
        or (cli_target is not None and not cli_target.exists())
        or not SING_BOX_PATH.exists()
        or not SYSTEMD_UNIT_PATH.exists()
        or (bundled_libcronet.exists() and not target_libcronet.exists())
    )
    if not runtime_missing:
        return False

    ensure_dirs()
    if cli_target is not None:
        run_sudo(["install", "-m", "0755", str(cli_src), str(cli_target)])
        print(f"Installed {cli_target}")
    if not same_file(src, SING_BOX_PATH):
        run_sudo(["install", "-m", "0755", str(src), str(SING_BOX_PATH)])
        print(f"Installed {SING_BOX_PATH}")
    if bundled_libcronet.exists() and not same_file(bundled_libcronet, target_libcronet):
        run_sudo(["install", "-m", "0644", str(bundled_libcronet), str(target_libcronet)])
        print(f"Installed {target_libcronet}")
    write_root_file(SYSTEMD_UNIT_PATH, systemd_unit(), "0644")
    run_sudo(["systemctl", "daemon-reload"])
    print(f"Installed {SYSTEMD_UNIT_PATH}")
    return True


def install_runtime_and_service(args) -> int:
    installed = ensure_runtime_and_service(args.sing_box, force=True)
    if not installed:
        print("Runtime and service are already installed.")
    print("Service was not started. Run: workvpn setup --uuid ... --url ... && workvpn start")
    return 0


def prepare_config(vpn_uuid: str, server_url: str) -> str:
    try:
        uuid.UUID(vpn_uuid)
    except ValueError:
        raise SystemExit("Invalid UUID.")
    config_url = normalize_server_url(server_url)
    print(f"Downloading config: {config_url}")
    text = http_get(config_url)
    if UUID_PLACEHOLDER not in text:
        raise SystemExit(f"Downloaded config does not contain {UUID_PLACEHOLDER} placeholder.")
    prepared = text.replace(UUID_PLACEHOLDER, vpn_uuid)
    json.loads(prepared)
    return prepared


def setup(args) -> int:
    require_linux()
    ensure_runtime_and_service()
    config_url = normalize_server_url(args.url)
    prepared = prepare_config(args.uuid, args.url)
    ensure_dirs()
    settings = {
        "uuid": args.uuid,
        "url": url_origin(config_url),
        "config_url": config_url,
        "updated_at": int(time.time()),
    }
    write_root_file(SETTINGS_PATH, json.dumps(settings, indent=2) + "\n", "0600")
    write_root_file(CONFIG_PATH, prepared, "0600")
    print(f"Saved settings: {SETTINGS_PATH}")
    print(f"Saved config: {CONFIG_PATH}")
    print("VPN was not started. Run: workvpn start")
    return 0


def refresh_config(args) -> int:
    settings = load_settings()
    if not settings.get("uuid") or not settings.get("config_url"):
        raise SystemExit("No saved settings. Run setup first.")
    prepared = prepare_config(settings["uuid"], settings["config_url"])
    write_root_file(CONFIG_PATH, prepared, "0600")
    print(f"Refreshed config: {CONFIG_PATH}")
    return 0


def systemctl(action: str, *, check=True, capture=False):
    return run_sudo(["systemctl", action, SERVICE_NAME], check=check, capture=capture)


def start(args) -> int:
    if not CONFIG_PATH.exists():
        print("Config is missing. Run setup first.", file=sys.stderr)
        return 2
    print("Starting WorkVPN...")
    systemctl("start")
    time.sleep(1)
    if not is_active_quiet():
        print("Service did not become active. Check: workvpn logs", file=sys.stderr)
        return 1
    ip = external_ip(tries=args.ip_tries, delay=args.ip_delay)
    if ip:
        print(f"Connected · IP {ip}")
    else:
        print("Service is running, but external IP check failed.")
    return 0


def stop(args) -> int:
    print("Stopping WorkVPN...")
    systemctl("stop", check=False)
    print("Stopped")
    return 0


def restart(args) -> int:
    print("Restarting WorkVPN...")
    systemctl("restart")
    ip = external_ip(tries=args.ip_tries, delay=args.ip_delay)
    if ip:
        print(f"Connected · IP {ip}")
    return 0


def is_active_quiet() -> bool:
    result = run_sudo(["systemctl", "is-active", "--quiet", SERVICE_NAME], check=False)
    return result.returncode == 0


def status(args) -> int:
    active = is_active_quiet()
    print(f"Service: {'running' if active else 'stopped'}")
    if SETTINGS_PATH.exists():
        settings = load_settings()
        if settings.get("config_url"):
            print(f"Config URL: {settings['config_url']}")
    if active:
        ip = external_ip(tries=1, delay=0)
        print(f"VPN IP: {ip or 'unknown'}")
    return 0 if active else 3


def logs(args) -> int:
    cmd = ["journalctl", "-u", SERVICE_NAME, "--no-pager"]
    if args.follow:
        cmd.append("-f")
    elif args.lines:
        cmd.extend(["-n", str(args.lines)])
    try:
        return run_sudo(cmd, check=False).returncode
    except KeyboardInterrupt:
        return 130


def external_ip(tries: int = 3, delay: float = 1.0) -> str | None:
    for attempt in range(max(1, tries)):
        try:
            value = http_get("https://ident.me", timeout=5).strip()
            ipaddress.ip_address(value)
            return value
        except Exception as exc:
            if attempt == max(1, tries) - 1:
                print(f"IP check failed: {exc}", file=sys.stderr)
            elif delay > 0:
                time.sleep(delay)
    return None


def ip(args) -> int:
    value = external_ip(tries=args.ip_tries, delay=args.ip_delay)
    if value:
        print(value)
        return 0
    return 1


def uninstall(args) -> int:
    systemctl("stop", check=False)
    run_sudo(["systemctl", "disable", SERVICE_NAME], check=False)
    if SYSTEMD_UNIT_PATH.exists():
        run_sudo(["rm", "-f", str(SYSTEMD_UNIT_PATH)], check=False)
    run_sudo(["systemctl", "daemon-reload"], check=False)
    run_sudo(["rm", "-f", str(SELF_INSTALL_CLI_PATH)], check=False)
    if args.purge:
        run_sudo(["rm", "-rf", str(ETC_DIR), str(LIB_DIR)], check=False)
    print("Uninstalled service" + (" and data" if args.purge else ""))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workvpn",
        description="WorkVPN Linux CLI. Configure and control the VPN service.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  workvpn setup --uuid 00000000-0000-0000-0000-000000000000 --url https://example.com/path
  workvpn start
  workvpn status
  workvpn logs -n 100
  workvpn logs -f
  workvpn stop
  workvpn uninstall --purge

Notes:
  setup installs the bundled runtime/service when missing, saves UUID/URL, and prepares config.
  setup does not start VPN. start/stop/restart/uninstall use sudo when root permissions are needed.
""",
    )
    sub = parser.add_subparsers(dest="command", metavar="command", required=True)

    p = sub.add_parser(
        "setup",
        help="install runtime if needed, save UUID/URL, and prepare config",
        description="Install bundled sing-box/service if needed, download config_universal.json, insert UUID, and save /etc/workvpn/config.json. VPN is not started.",
    )
    p.add_argument("--uuid", required=True, help="VPN UUID token")
    p.add_argument("--url", required=True, help="server base URL or full config_universal.json URL")
    p.set_defaults(func=setup)

    p = sub.add_parser(
        "refresh",
        help="download config again using saved settings",
        description="Refresh /etc/workvpn/config.json using the UUID and URL saved by setup.",
    )
    p.set_defaults(func=refresh_config)

    p = sub.add_parser(
        "start",
        help="start VPN service",
        description="Start workvpn.service and print the external VPN IP if ident.me is available.",
    )
    p.add_argument("--ip-tries", type=int, default=5, help="external IP check attempts, default: 5")
    p.add_argument("--ip-delay", type=float, default=1.0, help="delay between IP checks in seconds, default: 1.0")
    p.set_defaults(func=start)

    p = sub.add_parser("stop", help="stop VPN service", description="Stop workvpn.service.")
    p.set_defaults(func=stop)

    p = sub.add_parser(
        "restart",
        help="restart VPN service",
        description="Restart workvpn.service and print the external VPN IP if ident.me is available.",
    )
    p.add_argument("--ip-tries", type=int, default=5, help="external IP check attempts, default: 5")
    p.add_argument("--ip-delay", type=float, default=1.0, help="delay between IP checks in seconds, default: 1.0")
    p.set_defaults(func=restart)

    p = sub.add_parser(
        "status",
        help="show service and VPN IP status",
        description="Show whether workvpn.service is running and print the current external IP when active.",
    )
    p.set_defaults(func=status)

    p = sub.add_parser(
        "logs",
        help="show service logs",
        description="Show journalctl logs for workvpn.service.",
    )
    p.add_argument("-n", "--lines", type=int, default=80, help="number of log lines, default: 80")
    p.add_argument("-f", "--follow", action="store_true", help="follow logs live")
    p.set_defaults(func=logs)

    p = sub.add_parser(
        "ip",
        help="show current external IP",
        description="Print the current external IP using ident.me.",
    )
    p.add_argument("--ip-tries", type=int, default=3, help="external IP check attempts, default: 3")
    p.add_argument("--ip-delay", type=float, default=1.0, help="delay between IP checks in seconds, default: 1.0")
    p.set_defaults(func=ip)

    p = sub.add_parser(
        "uninstall",
        help="remove service; use --purge to remove data/runtime",
        description="Stop and remove workvpn.service. With --purge, also remove /etc/workvpn and /usr/lib/workvpn.",
    )
    p.add_argument("--purge", action="store_true", help="remove config and runtime files too")
    p.set_defaults(func=uninstall)

    return parser


def main(argv=None) -> int:
    try:
        require_linux()
        parser = build_parser()
        args = parser.parse_args(argv)
        return args.func(args)
    except KeyboardInterrupt:
        return 130
