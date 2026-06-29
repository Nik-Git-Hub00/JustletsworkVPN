import json
import os
import platform
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

try:
    import ssl
    import certifi
except Exception:
    ssl = None
    certifi = None

from workvpn.version import get_app_version


SEMVER = re.compile(r"^(?:v)?(\d+)\.(\d+)\.(\d+)$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SETTINGS_FILE = "update_settings.json"


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    release_url: str
    download_url: str | None = None


def _ssl_context():
    if ssl is None:
        return None
    try:
        return ssl.create_default_context(cafile=certifi.where()) if certifi else ssl.create_default_context()
    except Exception:
        return None


def _metadata_candidates(filename: str):
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        bundle_root = executable.parent
        yield Path(getattr(sys, "_MEIPASS", bundle_root)) / filename
        yield bundle_root / filename
        yield bundle_root.parent / "Resources" / filename
        yield bundle_root.parent / "Frameworks" / filename

    module = Path(__file__).resolve()
    for parent in module.parents:
        yield parent / filename


def _normalize_repo(value: str) -> str | None:
    value = (value or "").strip().strip("/")
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            return None
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) >= 2:
            value = f"{parts[0]}/{parts[1]}"
    return value if REPO_RE.fullmatch(value) else None


def get_update_repo() -> str | None:
    env_repo = _normalize_repo(os.environ.get("WORKVPN_UPDATE_REPO", ""))
    if env_repo:
        return env_repo
    for path in _metadata_candidates("UPDATE_REPO"):
        try:
            repo = _normalize_repo(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if repo:
            return repo
    return None


def _version_tuple(version: str) -> tuple[int, int, int] | None:
    match = SEMVER.fullmatch((version or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def is_newer_version(candidate: str, current: str | None = None) -> bool:
    current_tuple = _version_tuple(current or get_app_version())
    candidate_tuple = _version_tuple(candidate)
    return bool(current_tuple and candidate_tuple and candidate_tuple > current_tuple)


def _settings_path(app_support: Path) -> Path:
    return app_support / SETTINGS_FILE


def update_checks_disabled(app_support: Path) -> bool:
    try:
        data = json.loads(_settings_path(app_support).read_text(encoding="utf-8"))
        return bool(data.get("disabled"))
    except Exception:
        return False


def disable_update_checks(app_support: Path) -> None:
    app_support.mkdir(parents=True, exist_ok=True)
    _settings_path(app_support).write_text(json.dumps({"disabled": True}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _preferred_asset_keywords() -> tuple[str, ...]:
    system = sys.platform
    machine = platform.machine().lower()
    if system == "darwin":
        return ("macos-arm64.dmg", "macos-arm64.zip") if machine == "arm64" else ("macos-x64.dmg", "macos-x64.zip")
    if system == "win32":
        return ("windows-arm64.exe", "windows-arm64.zip") if "arm" in machine else ("windows-amd64.exe", "windows-amd64.zip")
    return ()


def _pick_asset(assets: list[dict]) -> str | None:
    keywords = _preferred_asset_keywords()
    for keyword in keywords:
        for asset in assets:
            name = str(asset.get("name", "")).lower()
            url = asset.get("browser_download_url")
            if keyword in name and url:
                return str(url)
    return None


def check_latest_release(timeout: float = 4.0) -> UpdateInfo | None:
    repo = get_update_repo()
    if not repo:
        return None
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"WorkVPN/{get_app_version()}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
        data = json.loads(response.read().decode("utf-8"))
    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    version_tuple = _version_tuple(tag)
    if not version_tuple or not is_newer_version(tag):
        return None
    version = ".".join(str(part) for part in version_tuple)
    release_url = str(data.get("html_url") or f"https://github.com/{repo}/releases/latest")
    download_url = _pick_asset(data.get("assets") or [])
    return UpdateInfo(version=version, release_url=release_url, download_url=download_url)
