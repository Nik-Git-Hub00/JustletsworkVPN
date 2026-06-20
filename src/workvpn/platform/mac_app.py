import atexit
import json
import math
import os
import platform
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.request
from urllib.parse import urlparse
import uuid
from pathlib import Path
from tkinter import messagebox, scrolledtext

try:
    import pystray
except Exception:
    pystray = None

from PIL import Image, ImageDraw, ImageFilter, ImageTk

try:
    import ssl
    import certifi
except Exception:
    ssl = None
    certifi = None


CUSTOM_USER_AGENT = "SingBoxVPN-Client/1.0-private"
UUID_PLACEHOLDER = "__TYPE_UUID__"
SERVER_CONFIG_FILENAME = "config_universal.json"
CONFIG_DOWNLOAD_ERROR = "Не удалось скачать конфиг. Проверьте правильность URL и учётных данных."
VPN_VERIFY_ERROR = "Не удалось подтвердить VPN-подключение. Проверьте UUID."
APP_TITLE = "WorkVPN"
TRAY_ICON_SIZE = 256

DOWNLOAD_RETRIES = 3
RETRY_DELAY = 2
PUBLIC_IP_URL = "https://ident.me"
VPN_VERIFY_TIMEOUT = 10
VPN_VERIFY_INTERVAL = 1
VPN_VERIFY_HTTP_TIMEOUT = 3
VPN_VERIFY_SAME_IP_LIMIT = 3

ANSI_ESCAPE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

BG = "#061221"
CARD = "#101c2f"
CARD_SOFT = "#14233a"
TITLE = "#eef6ff"
MUTED = "#8ea5c2"

GREEN = "#14b8a6"
RED = "#fb7185"
BLUE = "#3b82f6"
BLUE_HOVER = "#2563eb"
GRAY = "#22324a"
GRAY_HOVER = "#2f4566"
ORANGE = "#f59e0b"
RED_HOVER = "#e11d48"

FONT = "Helvetica"

LAUNCHD_LABEL = "WorkVPN"

SYSTEM_SUPPORT = Path("/Library/Application Support/WorkVPN")
SYSTEM_SING_BOX = SYSTEM_SUPPORT / "sing-box"
SYSTEM_CONFIG = SYSTEM_SUPPORT / "config.json"
SYSTEM_LOG = SYSTEM_SUPPORT / "singbox.log"
LAUNCHD_PLIST = Path("/Library/LaunchDaemons/WorkVPN.plist")
HELPER_PATH = Path("/usr/local/bin/workvpnctl")
SUDOERS_PATH = Path("/etc/sudoers.d/workvpn")
HELPER_VERSION = "2026-06-20-workvpn-helper-v1"


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = app_dir()


def repo_root() -> Path:
    for parent in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
        if (parent / "assets").exists() and (parent / "runtime").exists():
            return parent
    return Path.cwd()


REPO_ROOT = repo_root()
APP_SUPPORT = Path.home() / "Library" / "Application Support" / "WorkVPN"
APP_SUPPORT.mkdir(parents=True, exist_ok=True)
CONFIG = APP_SUPPORT / "config.json"
TOKEN_FILE = APP_SUPPORT / "token.txt"
CONFIG_URL_FILE = APP_SUPPORT / "config_url.txt"


def resource_path(name: str) -> Path:
    possible_paths = [
        APP_DIR / name,
        APP_DIR.parent / "Resources" / name,
        APP_DIR.parent / "Frameworks" / name,
        REPO_ROOT / name,
        Path.cwd() / name,
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return APP_DIR / name


def find_icon_file() -> Path:
    possible_paths = [
        APP_DIR / "vpn_icon.icns",
        APP_DIR.parent / "Resources" / "vpn_icon.icns",
        APP_DIR.parent / "Frameworks" / "vpn_icon.icns",
        REPO_ROOT / "assets" / "vpn_icon.icns",
        Path.cwd() / "vpn_icon.icns",
        APP_DIR / "vpn_icon.ico",
        APP_DIR.parent / "Resources" / "vpn_icon.ico",
        APP_DIR.parent / "Frameworks" / "vpn_icon.ico",
        REPO_ROOT / "assets" / "vpn_icon.ico",
        Path.cwd() / "vpn_icon.ico",
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return APP_DIR / "vpn_icon.icns"


ICON_FILE = find_icon_file()


def patch_pystray_retina_icon():
    if sys.platform != "darwin" or pystray is None:
        return
    try:
        import pystray._darwin as darwin

        if getattr(darwin.Icon, "_workvpn_retina_patch", False):
            return

        def assert_retina_image(self):
            thickness = float(self._status_bar.thickness())
            point_size = (int(thickness), int(thickness))
            if self._icon_image and self._icon_image.size() == point_size:
                return

            scale = 2
            try:
                screen = darwin.AppKit.NSScreen.mainScreen()
                if screen:
                    scale = max(scale, int(round(float(screen.backingScaleFactor()))))
            except Exception:
                pass

            pixel_size = max(64, int(round(thickness * scale)))
            source = darwin.PIL.Image.new("RGBA", (pixel_size, pixel_size))
            source.paste(self._icon.resize((pixel_size, pixel_size), darwin.PIL.Image.LANCZOS))

            b = darwin.io.BytesIO()
            source.save(b, "png")
            data = darwin.Foundation.NSData.dataWithBytes_length_(b.getvalue(), len(b.getvalue()))
            self._icon_image = darwin.AppKit.NSImage.alloc().initWithData_(data)
            self._icon_image.setSize_(darwin.AppKit.NSMakeSize(thickness, thickness))
            self._status_item.button().setImage_(self._icon_image)

        darwin.Icon._assert_image = assert_retina_image
        darwin.Icon._workvpn_retina_patch = True
    except Exception:
        pass


patch_pystray_retina_icon()


def find_bundled_sing_box() -> Path:
    runtime_dir = "macos-arm64" if platform.machine() == "arm64" else "macos-x64"
    possible_paths = [
        APP_DIR / "sing-box",
        APP_DIR.parent / "Frameworks" / "sing-box",
        APP_DIR.parent / "Resources" / "sing-box",
        REPO_ROOT / "runtime" / runtime_dir / "sing-box",
        Path.cwd() / "sing-box",
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return APP_DIR / "sing-box"


BUNDLED_SING_BOX = find_bundled_sing_box()


def ssl_context():
    if ssl and certifi:
        return ssl.create_default_context(cafile=certifi.where())
    if ssl:
        return ssl.create_default_context()
    return None


def clean_log(line: str) -> str:
    line = ANSI_ESCAPE.sub("", line)
    line = re.sub(r"\[\d+\]\s*", "", line)
    m = re.search(r"(\d{2}:\d{2}:\d{2}).*(INFO|DEBUG|ERROR|WARN|FATAL)(.*)", line)
    if m:
        return f"{m.group(1)} {m.group(2)}{m.group(3)}\n"
    return line.strip() + "\n"


def make_request(url: str):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", CUSTOM_USER_AGENT)
    return req


def download_file(url: str, target_path: Path) -> Path:
    ctx = ssl_context()
    if ctx:
        with urllib.request.urlopen(make_request(url), timeout=20, context=ctx) as response:
            data = response.read()
    else:
        with urllib.request.urlopen(make_request(url), timeout=20) as response:
            data = response.read()
    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    with open(tmp_path, "wb") as f:
        f.write(data)
    return tmp_path


def fetch_public_ip(timeout=4) -> str | None:
    ctx = ssl_context()
    req = make_request(PUBLIC_IP_URL)
    if ctx:
        response = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    else:
        response = urllib.request.urlopen(req, timeout=timeout)
    with response:
        value = response.read(128).decode("utf-8", errors="replace").strip()
    if re.fullmatch(r"[0-9a-fA-F:.]+", value):
        return value
    return None


def build_config_url(config_url: str) -> str:
    url = config_url.strip()
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path.endswith("/" + SERVER_CONFIG_FILENAME) or path == "/" + SERVER_CONFIG_FILENAME:
        return url.rstrip("/")
    return url.rstrip("/") + "/" + SERVER_CONFIG_FILENAME


def validate_singbox_config(config_path: Path, log_func) -> bool:
    singbox = SYSTEM_SING_BOX if SYSTEM_SING_BOX.exists() else BUNDLED_SING_BOX
    try:
        log_func("Проверка sing-box check...\n")
        result = subprocess.run(
            [str(singbox), "check", "-c", str(config_path)],
            cwd=str(APP_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        if result.returncode == 0:
            log_func("Проверка sing-box config: OK\n")
            return True
        log_func("Проверка sing-box config: ошибка\n")
        log_func(result.stdout + "\n")
        return False
    except Exception as e:
        log_func(f"Ошибка проверки config.json: {e}\n")
        return False


def replace_uuid_placeholder(value, client_uuid: str) -> tuple[object, int]:
    if isinstance(value, dict):
        total = 0
        result = {}
        for key, item in value.items():
            replaced_item, count = replace_uuid_placeholder(item, client_uuid)
            result[key] = replaced_item
            total += count
        return result, total
    if isinstance(value, list):
        total = 0
        result = []
        for item in value:
            replaced_item, count = replace_uuid_placeholder(item, client_uuid)
            result.append(replaced_item)
            total += count
        return result, total
    if value == UUID_PLACEHOLDER:
        return client_uuid, 1
    return value, 0


def update_config_from_template(log_func, client_uuid: str, config_url: str) -> bool:
    final_url = build_config_url(config_url)
    log_func(f"Скачивание config.json: {final_url}\n")
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        tmp_path = None
        try:
            log_func(f"Скачивание config.json, попытка {attempt}/{DOWNLOAD_RETRIES}...\n")
            tmp_path = download_file(final_url, CONFIG)

            with open(tmp_path, "r", encoding="utf-8") as f:
                template = json.load(f)

            config, replacements = replace_uuid_placeholder(template, client_uuid)
            if replacements == 0:
                tmp_path.unlink(missing_ok=True)
                tmp_path = None
                raise RuntimeError(f"placeholder {UUID_PLACEHOLDER} not found")

            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
                f.write("\n")

            if not validate_singbox_config(tmp_path, log_func):
                tmp_path.unlink(missing_ok=True)
                tmp_path = None
                raise RuntimeError("sing-box check failed")
            os.replace(tmp_path, CONFIG)
            log_func("config.json скачан, UUID вставлен и применён.\n")
            return True
        except Exception as e:
            log_func(f"Ошибка подготовки config.json: {e}\n")
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            if attempt < DOWNLOAD_RETRIES:
                time.sleep(RETRY_DELAY)
    log_func(CONFIG_DOWNLOAD_ERROR + "\n")
    return False


def load_logo(size: int):
    try:
        img = Image.open(resource_path("assets/vpn_shield.png")).convert("RGBA")
        img.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(img, ((size - img.width) // 2, (size - img.height) // 2))
        return ImageTk.PhotoImage(canvas)
    except Exception:
        return None


def load_png_icon(filename: str, size=24, tint=None):
    try:
        img = Image.open(resource_path(f"assets/{filename}")).convert("RGBA")
        img = img.resize((size, size), Image.LANCZOS)
        if tint:
            alpha = img.getchannel("A")
            img = Image.new("RGBA", img.size, tint)
            img.putalpha(alpha)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


def create_status_dot(status="red", size=34):
    scale = 4
    canvas = size * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    if status == "green":
        base, light, glow_color = (20, 184, 166, 255), (94, 234, 212, 255), (20, 184, 166, 100)
    elif status == "orange":
        base, light, glow_color = (217, 119, 6, 255), (252, 211, 77, 255), (245, 158, 11, 95)
    else:
        base, light, glow_color = (225, 29, 72, 255), (251, 113, 133, 255), (244, 63, 94, 95)

    glow = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    pad = int(canvas * 0.19)
    glow_draw.ellipse((pad, pad, canvas - pad, canvas - pad), fill=glow_color)
    glow = glow.filter(ImageFilter.GaussianBlur(max(8, int(canvas * 0.08))))
    image.alpha_composite(glow)

    draw = ImageDraw.Draw(image)
    center = canvas // 2
    shadow_radius = int(canvas * 0.29)
    draw.ellipse(
        (center - shadow_radius, center - shadow_radius, center + shadow_radius, center + shadow_radius),
        fill=(8, 17, 31, 255),
    )

    max_radius = int(canvas * 0.21)
    for i in range(max_radius, 0, -1):
        t = i / max_radius
        r = int(base[0] * (1 - t) + light[0] * t)
        g = int(base[1] * (1 - t) + light[1] * t)
        b = int(base[2] * (1 - t) + light[2] * t)
        draw.ellipse((center - i, center - i, center + i, center + i), fill=(r, g, b, 255))

    ring_radius = int(canvas * 0.25)
    ring_width = max(2, int(canvas * 0.025))
    draw.ellipse(
        (center - ring_radius, center - ring_radius, center + ring_radius, center + ring_radius),
        outline=(238, 246, 255, 45),
        width=ring_width,
    )

    image = image.resize((size, size), Image.LANCZOS)
    return ImageTk.PhotoImage(image)


def create_background(width: int, height: int):
    scale = 2
    w, h = width * scale, height * scale
    image = Image.new("RGB", (w, h), (5, 13, 25))
    pixels = image.load()
    for y in range(h):
        for x in range(w):
            nx = (x / w) - 0.5
            ny = (y / h) - 0.42
            radial = max(0.0, 1.0 - ((nx * nx * 2.2 + ny * ny * 1.6) ** 0.5))
            vertical = y / h
            r = int(4 + radial * 16 + vertical * 2)
            g = int(13 + radial * 32 + vertical * 5)
            b = int(28 + radial * 58 + vertical * 12)
            pixels[x, y] = (r, g, b)

    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    draw.ellipse((int(w * 0.18), int(h * 0.56), int(w * 0.82), int(h * 1.14)), fill=(20, 184, 166, 42))
    glow = glow.filter(ImageFilter.GaussianBlur(int(70 * scale)))
    image = Image.alpha_composite(image.convert("RGBA"), glow)
    image = image.resize((width, height), Image.LANCZOS)
    return ImageTk.PhotoImage(image)


def create_power_button_image(state="disconnected", size=172, disabled=False):
    try:
        image = Image.open(resource_path(f"assets/power_button_{state}.png")).convert("RGBA")
        image.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(image, ((size - image.width) // 2, (size - image.height) // 2))
        if disabled and state not in ("busy", "disconnected"):
            alpha = canvas.getchannel("A").point(lambda a: int(a * 0.65))
            canvas.putalpha(alpha)
        return ImageTk.PhotoImage(canvas)
    except Exception:
        pass

    scale = 4
    canvas = size * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if state == "connected":
        base = (18, 122, 44)
        light = (96, 231, 78)
        glow_color = (72, 255, 112, 120)
    elif state == "busy":
        base = (167, 96, 10)
        light = (255, 195, 61)
        glow_color = (245, 158, 11, 115)
    else:
        base = (159, 29, 54)
        light = (255, 88, 116)
        glow_color = (255, 70, 100, 100)

    if disabled and state not in ("busy", "disconnected"):
        base = tuple(int(v * 0.62) for v in base)
        light = tuple(int(v * 0.7) for v in light)

    center = canvas // 2
    radius = int(canvas * 0.35)

    glow = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_pad = int(canvas * 0.21)
    glow_draw.ellipse((glow_pad, glow_pad, canvas - glow_pad, canvas - glow_pad), fill=glow_color)
    glow = glow.filter(ImageFilter.GaussianBlur(int(canvas * 0.045)))
    image.alpha_composite(glow)

    shadow = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.ellipse(
        (center - radius, center - radius + int(canvas * 0.025), center + radius, center + radius + int(canvas * 0.035)),
        fill=(0, 0, 0, 95),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(int(canvas * 0.026)))
    image.alpha_composite(shadow)

    fill_layer = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    fill_px = fill_layer.load()
    for y in range(center - radius, center + radius + 1):
        for x in range(center - radius, center + radius + 1):
            dx = (x - center) / radius
            dy = (y - center) / radius
            d = (dx * dx + dy * dy) ** 0.5
            if d <= 1.0:
                vertical = max(0.0, min(1.0, 1.0 - ((y - (center - radius)) / (radius * 2))))
                radial = max(0.0, 1.0 - d)
                t = 0.28 + vertical * 0.42 + radial * 0.3
                r = int(base[0] * (1 - t) + light[0] * t)
                g = int(base[1] * (1 - t) + light[1] * t)
                b = int(base[2] * (1 - t) + light[2] * t)
                fill_px[x, y] = (r, g, b, 255)
    image.alpha_composite(fill_layer)

    ring = max(5, int(canvas * 0.022))
    draw.ellipse(
        (center - radius, center - radius, center + radius, center + radius),
        outline=(232, 255, 242, 215),
        width=ring,
    )
    highlight = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    highlight_draw = ImageDraw.Draw(highlight)
    highlight_draw.ellipse(
        (
            center - int(radius * 0.58),
            center - int(radius * 0.68),
            center + int(radius * 0.45),
            center - int(radius * 0.15),
        ),
        fill=(255, 255, 255, 26),
    )
    highlight = highlight.filter(ImageFilter.GaussianBlur(int(canvas * 0.018)))
    image.alpha_composite(highlight)

    try:
        icon = Image.open(resource_path("assets/ui_power.png")).convert("RGBA")
        icon = icon.resize((int(canvas * 0.25), int(canvas * 0.25)), Image.LANCZOS)
        image.alpha_composite(icon, (center - icon.width // 2, center - icon.height // 2))
    except Exception:
        icon_radius = int(canvas * 0.15)
        icon_width = max(8, int(canvas * 0.031))
        points = []
        for angle in range(42, 319, 4):
            radians = math.radians(angle)
            points.append((center + int(icon_radius * math.sin(radians)), center - int(icon_radius * math.cos(radians))))
        draw.line(points, fill=(250, 252, 255, 242), width=icon_width, joint="curve")
        draw.line((center, center - int(canvas * 0.18), center, center + int(canvas * 0.02)), fill=(250, 252, 255, 242), width=icon_width)

    image = image.resize((size, size), Image.LANCZOS)
    alpha = image.getchannel("A")
    alpha = alpha.point(lambda a: 0 if a < 8 else a)
    image.putalpha(alpha)
    return ImageTk.PhotoImage(image)


def create_button_icon(kind: str, color=(218, 230, 247, 255), size=30):
    scale = 4
    canvas = size * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    c = color
    width = max(8, int(canvas * 0.085))

    if kind == "token":
        box = (int(canvas * 0.18), int(canvas * 0.18), int(canvas * 0.82), int(canvas * 0.82))
        draw.arc(box, 38, 325, fill=c, width=width)
        draw.polygon(
            [
                (int(canvas * 0.26), int(canvas * 0.25)),
                (int(canvas * 0.18), int(canvas * 0.52)),
                (int(canvas * 0.44), int(canvas * 0.45)),
            ],
            fill=c,
        )
    elif kind == "log":
        draw.rounded_rectangle((int(canvas * 0.24), int(canvas * 0.12), int(canvas * 0.76), int(canvas * 0.88)), radius=int(canvas * 0.045), outline=c, width=width)
        draw.line((int(canvas * 0.61), int(canvas * 0.12), int(canvas * 0.76), int(canvas * 0.28)), fill=c, width=width)
        draw.line((int(canvas * 0.36), int(canvas * 0.42), int(canvas * 0.64), int(canvas * 0.42)), fill=c, width=width)
        draw.line((int(canvas * 0.36), int(canvas * 0.56), int(canvas * 0.64), int(canvas * 0.56)), fill=c, width=width)
        draw.line((int(canvas * 0.36), int(canvas * 0.70), int(canvas * 0.58), int(canvas * 0.70)), fill=c, width=width)
    elif kind == "exit":
        draw.line((int(canvas * 0.28), int(canvas * 0.28), int(canvas * 0.72), int(canvas * 0.72)), fill=c, width=width)
        draw.line((int(canvas * 0.72), int(canvas * 0.28), int(canvas * 0.28), int(canvas * 0.72)), fill=c, width=width)
    elif kind == "save":
        draw.line((int(canvas * 0.22), int(canvas * 0.52), int(canvas * 0.43), int(canvas * 0.72)), fill=c, width=width)
        draw.line((int(canvas * 0.43), int(canvas * 0.72), int(canvas * 0.78), int(canvas * 0.28)), fill=c, width=width)
    elif kind == "cancel":
        draw.line((int(canvas * 0.3), int(canvas * 0.3), int(canvas * 0.7), int(canvas * 0.7)), fill=c, width=width)
        draw.line((int(canvas * 0.7), int(canvas * 0.3), int(canvas * 0.3), int(canvas * 0.7)), fill=c, width=width)

    image = image.resize((size, size), Image.LANCZOS)
    return ImageTk.PhotoImage(image)


def create_tray_image(status_color="red"):
    filename = f"tray_icon_{status_color}.png"
    try:
        image = Image.open(resource_path(f"assets/{filename}")).convert("RGBA")
        image.thumbnail((TRAY_ICON_SIZE, TRAY_ICON_SIZE), Image.LANCZOS)
        canvas = Image.new("RGBA", (TRAY_ICON_SIZE, TRAY_ICON_SIZE), (0, 0, 0, 0))
        canvas.alpha_composite(image, ((TRAY_ICON_SIZE - image.width) // 2, (TRAY_ICON_SIZE - image.height) // 2))
        return canvas
    except Exception:
        image = Image.new("RGBA", (TRAY_ICON_SIZE, TRAY_ICON_SIZE), (15, 23, 42, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((45, 45, 211, 211), radius=44, fill=(30, 41, 59, 255))
        return image


def applescript_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def run_admin_shell(command: str) -> subprocess.CompletedProcess:
    script = f"do shell script {applescript_quote(command)} with administrator privileges"
    return subprocess.run(["osascript", "-e", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def run_helper(action: str) -> subprocess.CompletedProcess:
    return subprocess.run(["sudo", "-n", str(HELPER_PATH), action], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def helper_output(result: subprocess.CompletedProcess) -> str:
    parts = []
    if result.stdout:
        parts.append(result.stdout.strip())
    if result.stderr:
        parts.append(result.stderr.strip())
    return "\n".join(part for part in parts if part)


def helper_ready() -> bool:
    if not HELPER_PATH.exists():
        return False
    try:
        version = subprocess.run(["sudo", "-n", str(HELPER_PATH), "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if version.returncode != 0 or version.stdout.strip() != HELPER_VERSION:
            return False
    except Exception:
        return False
    result = subprocess.run(["sudo", "-n", str(HELPER_PATH), "status"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.returncode in (0, 3)


def launchd_is_running() -> bool:
    try:
        result = subprocess.run(["sudo", "-n", str(HELPER_PATH), "status"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if result.returncode != 0:
            return False
        text = result.stdout
        return "state = running" in text or re.search(r"\bpid\s*=\s*\d+", text) is not None
    except Exception:
        return False


def install_helper_command() -> str:
    bundled = shlex.quote(str(BUNDLED_SING_BOX))
    system_support = shlex.quote(str(SYSTEM_SUPPORT))
    system_singbox = shlex.quote(str(SYSTEM_SING_BOX))
    launchd_plist = shlex.quote(str(LAUNCHD_PLIST))
    helper_path = shlex.quote(str(HELPER_PATH))
    sudoers_path = shlex.quote(str(SUDOERS_PATH))

    helper_lines = [
        "#!/bin/sh",
        "set -e",
        f'LABEL="{LAUNCHD_LABEL}"',
        'SYSTEM_CONFIG="/Library/Application Support/WorkVPN/config.json"',
        'USER_CONFIG="$HOME/Library/Application Support/WorkVPN/config.json"',
        f'PLIST="{LAUNCHD_PLIST}"',
        f'# WorkVPN helper version: {HELPER_VERSION}',
        'case "$1" in',
        '  version)',
        f'    echo "{HELPER_VERSION}"',
        '    ;;',
        '  start)',
        '    if [ ! -f "$USER_CONFIG" ]; then',
        '      echo "User config not found: $USER_CONFIG" >&2',
        '      exit 2',
        '    fi',
        '    cp "$USER_CONFIG" "$SYSTEM_CONFIG"',
        '    chown root:wheel "$SYSTEM_CONFIG"',
        '    chmod 644 "$SYSTEM_CONFIG"',
        '    /bin/launchctl bootstrap system "$PLIST" >/dev/null 2>&1 || true',
        '    /bin/launchctl kickstart -k system/$LABEL',
        '    ;;',
        '  stop)',
        '    /bin/launchctl stop system/$LABEL >/dev/null 2>&1 || true',
        '    for i in 1 2 3; do',
        '      if ! /bin/launchctl print system/$LABEL >/dev/null 2>&1; then exit 0; fi',
        '      if ! /bin/launchctl print system/$LABEL 2>/dev/null | /usr/bin/grep -Eq "state = running|pid = [0-9]+"; then exit 0; fi',
        '      sleep 1',
        '    done',
        '    /bin/launchctl kill SIGTERM system/$LABEL >/dev/null 2>&1 || true',
        '    sleep 2',
        '    if /bin/launchctl print system/$LABEL 2>/dev/null | /usr/bin/grep -Eq "state = running|pid = [0-9]+"; then',
        '      /bin/launchctl kill SIGKILL system/$LABEL >/dev/null 2>&1 || true',
        '    fi',
        '    ;;',
        '  status)',
        '    /bin/launchctl print system/$LABEL',
        '    ;;',
        '  *)',
        '    echo "Usage: workvpnctl start|stop|status|version" >&2',
        '    exit 64',
        '    ;;',
        'esac',
        '',
    ]
    helper_script = "\n".join(helper_lines)

    plist_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"',
        ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        '<plist version="1.0">',
        '<dict>',
        '    <key>Label</key>',
        f'    <string>{LAUNCHD_LABEL}</string>',
        '    <key>ProgramArguments</key>',
        '    <array>',
        f'        <string>{SYSTEM_SING_BOX}</string>',
        '        <string>run</string>',
        '        <string>-c</string>',
        f'        <string>{SYSTEM_CONFIG}</string>',
        '    </array>',
        '    <key>WorkingDirectory</key>',
        f'    <string>{SYSTEM_SUPPORT}</string>',
        '    <key>RunAtLoad</key>',
        '    <false/>',
        '    <key>KeepAlive</key>',
        '    <false/>',
        '    <key>StandardOutPath</key>',
        f'    <string>{SYSTEM_LOG}</string>',
        '    <key>StandardErrorPath</key>',
        f'    <string>{SYSTEM_LOG}</string>',
        '</dict>',
        '</plist>',
        '',
    ]
    plist = "\n".join(plist_lines)

    sudoers = f"""%admin ALL=(root) NOPASSWD: {HELPER_PATH} start
%admin ALL=(root) NOPASSWD: {HELPER_PATH} stop
%admin ALL=(root) NOPASSWD: {HELPER_PATH} status
%admin ALL=(root) NOPASSWD: {HELPER_PATH} version
"""

    cmd = f"""
set -e
mkdir -p {system_support}
mkdir -p /usr/local/bin
mkdir -p /etc/sudoers.d

# Remove old helper/service leftovers before installing WorkVPN helper.
for old_plist in /Library/LaunchDaemons/com.*.singboxvpn.plist; do
  [ -e "$old_plist" ] || continue
  old_label="$(basename "$old_plist" .plist)"
  launchctl stop "system/$old_label" >/dev/null 2>&1 || true
  launchctl bootout system "$old_plist" >/dev/null 2>&1 || true
  launchctl kill SIGTERM "system/$old_label" >/dev/null 2>&1 || true
  rm -f "$old_plist"
done
rm -f /usr/local/bin/singboxvpnctl
rm -f /etc/sudoers.d/singboxvpn
rm -rf "/Library/Application Support/SingBoxVPN"

if [ ! -f {bundled} ]; then
  echo "Bundled sing-box not found: {bundled}" >&2
  exit 10
fi

cp {bundled} {system_singbox}
# Remove Gatekeeper quarantine from installed runtime files.
xattr -rd com.apple.quarantine {system_support} >/dev/null 2>&1 || true
xattr -rd com.apple.quarantine {system_singbox} >/dev/null 2>&1 || true
chown root:wheel {system_singbox}
chmod 755 {system_singbox}

cat > {helper_path} <<'HELPER_EOF'
{helper_script}
HELPER_EOF
chown root:wheel {helper_path}
chmod 755 {helper_path}

cat > {launchd_plist} <<'PLIST_EOF'
{plist}
PLIST_EOF
chown root:wheel {launchd_plist}
chmod 644 {launchd_plist}

cat > {sudoers_path} <<'SUDOERS_EOF'
{sudoers}
SUDOERS_EOF
chown root:wheel {sudoers_path}
chmod 440 {sudoers_path}
/usr/sbin/visudo -cf {sudoers_path}

# Remove quarantine from helper, plist and system support.
xattr -rd com.apple.quarantine {system_support} >/dev/null 2>&1 || true
xattr -rd com.apple.quarantine {helper_path} >/dev/null 2>&1 || true
xattr -rd com.apple.quarantine {launchd_plist} >/dev/null 2>&1 || true
xattr -rd com.apple.quarantine {sudoers_path} >/dev/null 2>&1 || true

launchctl bootout system/{LAUNCHD_LABEL} >/dev/null 2>&1 || true
launchctl bootstrap system {launchd_plist} >/dev/null 2>&1 || true

exit 0
"""
    return cmd


class PrettyButton(tk.Frame):
    def __init__(self, parent, text, command, bg_color, hover_color, width_chars=20):
        super().__init__(parent, bg=bg_color, cursor="hand2", highlightthickness=1, highlightbackground="#22324a", bd=0)
        self.command = command
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.disabled = False
        self.label = tk.Label(self, text=text, bg=bg_color, fg="white", font=(FONT, 10, "bold"), width=width_chars, padx=12, pady=9, cursor="hand2")
        self.label.pack(fill="both", expand=True)
        self.bind("<Button-1>", self._click)
        self.label.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.label.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.label.bind("<Leave>", self._leave)

    def _click(self, _):
        if not self.disabled and self.command:
            self.command()

    def _enter(self, _):
        if not self.disabled:
            self.configure(bg=self.hover_color)
            self.label.configure(bg=self.hover_color)

    def _leave(self, _):
        if not self.disabled:
            self.configure(bg=self.bg_color)
            self.label.configure(bg=self.bg_color)

    def set_enabled(self, enabled: bool):
        self.disabled = not enabled
        if enabled:
            self.configure(bg=self.bg_color, cursor="hand2")
            self.label.configure(bg=self.bg_color, fg="white", cursor="hand2")
        else:
            disabled_bg = "#1f2d42"
            self.configure(bg=disabled_bg, cursor="arrow")
            self.label.configure(bg=disabled_bg, fg="#7f94af", cursor="arrow")


class ModernButton(tk.Frame):
    def __init__(
        self,
        parent,
        text,
        icon,
        command,
        width=300,
        normal_bg="#10213a",
        hover_bg="#162b49",
        border="#25425f",
        fg="#e6edf7",
        icon_file=None,
        icon_kind=None,
        icon_color=None,
        font_size=12,
        pady=8,
        height=48,
    ):
        super().__init__(parent, bg=normal_bg, cursor="hand2", highlightthickness=1, highlightbackground=border, bd=0)
        self.command = command
        self.disabled = False
        self.normal_bg = normal_bg
        self.hover_bg = hover_bg
        self.current_bg = normal_bg
        self.fg = fg
        self.disabled_bg = "#172337"
        self.button_width = width
        self.button_height = height
        self.text = text
        self.font_tuple = (FONT, font_size, "bold")
        self.icon_kind = icon_kind or self.icon_kind_from_file(icon_file)
        self.icon_color = icon_color or (230, 239, 252, 255)
        self.icon_file = icon_file
        self.configure(width=width, height=height)
        self.pack_propagate(False)
        self.icon_size = 27 if height >= 48 else 21
        self.icon_gap = 14 if height >= 48 else 10
        if self.icon_file:
            self.icon_image = load_png_icon(self.icon_file, self.icon_size, icon_color if icon_color else None)
        else:
            self.icon_image = create_button_icon(self.icon_kind, self.icon_color, self.icon_size) if self.icon_kind else None
        self.canvas = tk.Canvas(
            self,
            width=width,
            height=height,
            bg=self.normal_bg,
            bd=0,
            highlightthickness=0,
            relief="flat",
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)
        self.text_id = None
        self.icon_id = None
        self.draw_content()
        self.bind("<Button-1>", self._click)
        self.canvas.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.canvas.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.canvas.bind("<Leave>", self._leave)
        self.canvas.bind("<Configure>", self._resize)

    @staticmethod
    def icon_kind_from_file(icon_file):
        if not icon_file:
            return None
        name = icon_file.replace(".png", "").replace("ui_", "")
        return {
            "token": "token",
            "log": "log",
            "exit": "exit",
            "save": "save",
            "cancel": "cancel",
        }.get(name)

    def _resize(self, event):
        self.button_width = max(1, event.width)
        self.button_height = max(1, event.height)
        self.draw_content()

    def draw_content(self):
        self.canvas.delete("all")
        self.canvas.configure(bg=self.current_bg)
        width = max(1, self.canvas.winfo_width() or self.button_width)
        height = max(1, self.canvas.winfo_height() or self.button_height)
        text_width = tkfont.Font(font=self.font_tuple).measure(self.text)
        center_y = height / 2
        color = "#70839d" if self.disabled else self.fg
        if self.icon_image:
            icon_gap = self.icon_gap
            group_width = self.icon_size + icon_gap + text_width
            if group_width > width - 18:
                icon_gap = max(6, int(icon_gap * 0.65))
                group_width = self.icon_size + icon_gap + text_width
            start_x = max(8, (width - group_width) / 2)
            icon_x = start_x + self.icon_size / 2
            text_x = start_x + self.icon_size + icon_gap + text_width / 2
            self.icon_id = self.canvas.create_image(icon_x, center_y, image=self.icon_image, anchor="center")
        else:
            text_x = width / 2
        self.text_id = self.canvas.create_text(
            text_x,
            center_y,
            text=self.text,
            fill=color,
            font=self.font_tuple,
            anchor="center",
        )

    def _set_bg(self, color):
        self.current_bg = color
        self.configure(bg=color)
        self.canvas.configure(bg=color)

    def _set_cursor(self, cursor):
        self.configure(cursor=cursor)
        self.canvas.configure(cursor=cursor)

    def _click(self, _):
        if not self.disabled and self.command:
            self.command()

    def _enter(self, _):
        if not self.disabled:
            self._set_bg(self.hover_bg)
            self.draw_content()

    def _leave(self, _):
        if not self.disabled:
            self._set_bg(self.normal_bg)
            self.draw_content()

    def set_enabled(self, enabled: bool):
        self.disabled = not enabled
        if enabled:
            self._set_bg(self.normal_bg)
            self._set_cursor("hand2")
        else:
            self._set_bg(self.disabled_bg)
            self._set_cursor("arrow")
        self.draw_content()


class PowerButton(tk.Label):
    def __init__(self, parent, command, size=172):
        self.command = command
        self.size = size
        self.disabled = False
        self.state_name = "disconnected"
        self.image_ref = create_power_button_image(self.state_name, self.size)
        super().__init__(parent, image=self.image_ref, bg=BG, cursor="hand2", bd=0)
        self.bind("<Button-1>", self._click)

    def _click(self, _):
        if not self.disabled and self.command:
            self.command()

    def set_state(self, state_name: str, enabled: bool):
        self.state_name = state_name
        self.disabled = not enabled
        self.image_ref = create_power_button_image(state_name, self.size, self.disabled)
        self.configure(image=self.image_ref, cursor="hand2" if enabled else "arrow")


class SingBoxGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.configure(bg=BG)
        self.window_width, self.window_height = self.calculate_window_size()
        self.root.geometry(f"{self.window_width}x{self.window_height}")
        self.root.minsize(430, 650)
        self.root.resizable(False, False)
        self.status_var = tk.StringVar(value="Отключено")
        self.timer_var = tk.StringVar(value="00:00:00")
        self.connection_state = "disconnected"
        self.client_uuid = self.load_saved_token()
        self.config_url = self.load_saved_config_url()
        self.tray_actions = queue.Queue()
        self.tray_icon = None
        self.status_dot_image = None
        self.logo_image = None
        self.background_image = None
        self.power_button = None
        self.log_panel = None
        self.log_panel_visible = False
        self.log_panel_height = 0
        self.log_panel_target = 220
        self.connected_since = None
        self.vpn_ip = None
        self.log_tail_running = False
        self.log_position = 0
        self.is_stopping = False
        self.is_exiting = False
        self.first_log_sync_done = False
        self.logo_size = self.clamp_px(int(self.window_height * 0.145), 96, 118)
        self.title_size = self.fit_font_size(APP_TITLE, 30, self.window_width - 110, 24, 30, "bold")
        self.subtitle_size = self.clamp_px(14, 12, 14)
        self.timer_size = self.clamp_px(28, 24, 28)
        self.power_size = self.clamp_px(int(self.window_height * 0.16), 120, 140)
        self.center_window()
        self.build_ui()
        self.register_macos_window_handlers()
        self.root.after(100, self.process_tray_actions)
        self.create_tray()
        self.root.after(250, self.request_token_on_start)
        self.root.bind("<FocusIn>", lambda event: self.show_window() if self.root.state() == "withdrawn" else None)
        self.log_safe(f"Bundled sing-box: {BUNDLED_SING_BOX}\n")
        self.log_safe(f"Helper: {HELPER_PATH}\n")
        if self.client_uuid:
            self.log_safe("Сохранённый токен загружен.\n")
        if helper_ready():
            self.log_safe("Helper установлен.\n")
            if launchd_is_running():
                self.set_connected()
                self.start_log_tail()
                threading.Thread(target=self.refresh_connected_ip, daemon=True).start()
        else:
            self.log_safe("Helper не установлен. При первом подключении будет один запрос пароля.\n")

    def register_macos_window_handlers(self):
        """macOS-style window behavior.

        - Red close button: hide only the window, keep app/VPN running.
        - Dock click after close: show the window again.
        - Cmd+Q / Dock -> Quit: stop sing-box and quit app.
        """
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)

        self.root.bind_all("<Command-m>", lambda event: self.minimize_to_dock())
        self.root.bind_all("<Command-M>", lambda event: self.minimize_to_dock())

        try:
            self.root.createcommand("tk::mac::Quit", self.exit_app)
        except Exception:
            pass

        try:
            self.root.createcommand("tk::mac::ReopenApplication", self.show_window)
        except Exception:
            pass

    def minimize_to_dock(self):
        # Normal yellow-button style minimize. Do not use withdraw here.
        try:
            self.root.iconify()
        except Exception:
            pass

    def close_window(self):
        # Red close button: hide only the window. VPN keeps running.
        try:
            self.root.withdraw()
        except Exception:
            pass

    def show_window(self, icon=None, item=None):
        # Dock click / app activation should bring the hidden window back.
        try:
            self.root.deiconify()
            self.root.state("normal")
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def enqueue_tray_action(self, action):
        self.tray_actions.put(action)

    def process_tray_actions(self):
        try:
            while True:
                action = self.tray_actions.get_nowait()
                if action == "show":
                    self.show_window()
                elif action == "start":
                    self.start_vpn()
                elif action == "stop":
                    self.stop_vpn()
                elif action == "exit":
                    self.exit_app()
        except queue.Empty:
            pass

        if not self.is_exiting:
            self.root.after(100, self.process_tray_actions)

    def tray_can_start(self, item=None):
        return self.connection_state == "disconnected" and not self.is_exiting

    def tray_can_stop(self, item=None):
        return self.connection_state == "connected" and not self.is_exiting

    def tray_has_vpn_ip(self, item=None):
        return self.connection_state == "connected" and bool(self.vpn_ip) and not self.is_exiting

    def tray_vpn_ip_text(self, item=None):
        return f"IP VPN: {self.vpn_ip}" if self.vpn_ip else "IP VPN: проверяется"

    def create_tray(self):
        if pystray is None:
            self.log_safe("pystray не установлен: значок в верхней панели недоступен.\n")
            return

        menu = pystray.Menu(
            pystray.MenuItem("Открыть", lambda icon, item: self.enqueue_tray_action("show"), default=True),
            pystray.MenuItem(
                self.tray_vpn_ip_text,
                None,
                enabled=False,
                visible=self.tray_has_vpn_ip,
            ),
            pystray.MenuItem(
                "Подключить",
                lambda icon, item: self.enqueue_tray_action("start"),
                enabled=self.tray_can_start,
            ),
            pystray.MenuItem(
                "Отключить",
                lambda icon, item: self.enqueue_tray_action("stop"),
                enabled=self.tray_can_stop,
            ),
            pystray.MenuItem("Выход", lambda icon, item: self.enqueue_tray_action("exit")),
        )
        self.tray_icon = pystray.Icon(APP_TITLE, create_tray_image("red"), f"{APP_TITLE} - отключено", menu)
        try:
            self.tray_icon.run_detached()
        except Exception:
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def update_tray_icon(self, color):
        if not self.tray_icon:
            return

        self.tray_icon.icon = create_tray_image(color)
        titles = {
            "green": f"{APP_TITLE} - подключено",
            "orange": f"{APP_TITLE} - выполняется действие",
            "red": f"{APP_TITLE} - отключено",
        }
        self.tray_icon.title = titles.get(color, APP_TITLE)
        try:
            self.tray_icon.update_menu()
        except Exception:
            pass

    def calculate_window_size(self):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(max(int(screen_width * 0.3), 460), 540, screen_width - 120)
        height = min(max(int(screen_height * 0.74), 700), 800, screen_height - 120)
        return width, height

    @staticmethod
    def clamp_px(value, min_value, max_value):
        return max(min_value, min(int(value), max_value))

    def fit_font_size(self, text, base_size, max_width, min_size, max_size, weight="normal"):
        size = max(min_size, min(int(base_size), max_size))
        while size > min_size:
            if tkfont.Font(family=FONT, size=size, weight=weight).measure(text) <= max_width:
                return size
            size -= 1
        return min_size

    def build_ui(self):
        self.root.configure(bg=BG)
        wrapper = tk.Frame(self.root, bg=BG)
        wrapper.pack(fill="both", expand=True, padx=32, pady=(24, 34))

        top = tk.Frame(wrapper, bg=BG)
        top.pack(side="top", fill="both", expand=True)

        tk.Label(top, text=APP_TITLE, bg=BG, fg=TITLE, font=(FONT, self.title_size, "bold")).pack(anchor="center")
        tk.Label(top, text="Защищенное подключение", bg=BG, fg=MUTED, font=(FONT, self.subtitle_size)).pack(anchor="center", pady=(4, 14))

        self.logo_image = load_logo(self.logo_size)
        if self.logo_image:
            logo = tk.Label(top, image=self.logo_image, bg=BG)
        else:
            logo = tk.Label(top, text="VPN", bg=BG, fg=GREEN, font=(FONT, 42, "bold"))
        logo.pack(anchor="center")

        tk.Label(top, text="Время подключения", bg=BG, fg=MUTED, font=(FONT, 11, "bold")).pack(anchor="center", pady=(16, 4))
        self.timer_label = tk.Label(top, textvariable=self.timer_var, bg=BG, fg=TITLE, font=(FONT, self.timer_size))
        self.timer_label.pack(anchor="center")

        self.power_button = PowerButton(top, self.toggle_vpn, self.power_size)
        self.power_button.pack(anchor="center", pady=(14, 12))

        self.status_label = tk.Label(top, textvariable=self.status_var, bg=BG, fg=RED, font=(FONT, 11, "bold"))
        self.status_label.pack(anchor="center", pady=(0, 20))

        buttons = tk.Frame(wrapper, bg=BG)
        buttons.pack(side="bottom", fill="x")

        self.token_btn = ModernButton(buttons, "Изменить токен или URL", None, self.change_token, width=310, icon_file="ui_token.png")
        self.token_btn.pack(anchor="center", fill="x", pady=(0, 8))
        self.log_btn = ModernButton(buttons, "Лог", None, self.toggle_log_panel, width=310, icon_file="ui_log.png")
        self.log_btn.pack(anchor="center", fill="x", pady=(0, 8))
        self.exit_btn = ModernButton(
            buttons,
            "Выход",
            None,
            self.exit_app,
            width=310,
            normal_bg="#4a1624",
            hover_bg="#6d1d32",
            border="#9f2947",
            fg="#ffe4ea",
            icon_file="ui_exit.png",
        )
        self.exit_btn.pack(anchor="center", fill="x")

        self.log_panel = tk.Frame(self.root, bg="#07111f", highlightthickness=1, highlightbackground="#24415f")
        self.log_panel.place(x=28, y=self.window_height, width=self.window_width - 56, height=0)
        log_header = tk.Frame(self.log_panel, bg="#0d1c31")
        log_header.pack(fill="x")
        tk.Label(log_header, text="Лог sing-box", bg="#0d1c31", fg=TITLE, font=(FONT, 12, "bold")).pack(side="left", padx=14, pady=9)
        close_log = tk.Label(log_header, text="Скрыть", bg="#0d1c31", fg=MUTED, font=(FONT, 11, "bold"), cursor="hand2")
        close_log.pack(side="right", padx=14)
        close_log.bind("<Button-1>", lambda event: self.toggle_log_panel(False))
        self.log = scrolledtext.ScrolledText(
            self.log_panel,
            width=72,
            height=10,
            font=("Menlo", 9),
            bg="#030a14",
            fg="#d7e3f4",
            insertbackground="white",
            relief="flat",
            bd=0,
            highlightthickness=0,
        )
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.bind_text_shortcuts(self.log)
        self.set_disconnected()

    def bind_text_shortcuts(self, widget):
        def copy_selection(event=None):
            try:
                selected = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
            except tk.TclError:
                return "break"
            widget.clipboard_clear()
            widget.clipboard_append(selected)
            return "break"

        def select_all(event=None):
            widget.tag_add(tk.SEL, "1.0", tk.END)
            widget.mark_set(tk.INSERT, "1.0")
            widget.see(tk.INSERT)
            return "break"

        widget.bind("<Command-c>", copy_selection)
        widget.bind("<Command-C>", copy_selection)
        widget.bind("<Control-c>", copy_selection)
        widget.bind("<Command-a>", select_all)
        widget.bind("<Command-A>", select_all)
        widget.bind("<Control-a>", select_all)

    def log_safe(self, text):
        self.root.after(0, self.write_log, text)

    def center_window(self):
        self.root.update_idletasks()
        x = int((self.root.winfo_screenwidth() / 2) - (self.window_width / 2))
        y = int((self.root.winfo_screenheight() / 2) - (self.window_height / 2))
        self.root.geometry(f"{self.window_width}x{self.window_height}+{x}+{y}")

    def write_log(self, text):
        self.log.insert(tk.END, text)
        self.log.see(tk.END)

    def toggle_vpn(self):
        if self.connection_state == "connected":
            self.stop_vpn()
        elif self.connection_state == "disconnected":
            self.start_vpn()

    def toggle_log_panel(self, force=None):
        if force is None:
            self.log_panel_visible = not self.log_panel_visible
        else:
            self.log_panel_visible = bool(force)
        target = self.log_panel_target if self.log_panel_visible else 0
        self.animate_log_panel(target)

    def animate_log_panel(self, target):
        step = 22 if target > self.log_panel_height else -22
        next_height = self.log_panel_height + step
        if (step > 0 and next_height >= target) or (step < 0 and next_height <= target):
            next_height = target
        self.log_panel_height = next_height
        self.log_panel.place_configure(y=self.window_height - self.log_panel_height, height=self.log_panel_height)
        if self.log_panel_height != target:
            self.root.after(12, lambda: self.animate_log_panel(target))

    def update_timer(self):
        if self.connection_state == "connected" and self.connected_since:
            elapsed = max(0, int(time.time() - self.connected_since))
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            seconds = elapsed % 60
            self.timer_var.set(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            self.root.after(1000, self.update_timer)

    def load_saved_token(self):
        try:
            token = TOKEN_FILE.read_text(encoding="utf-8").strip()
            return str(uuid.UUID(token)) if token else None
        except Exception:
            return None

    def save_token(self, token: str):
        TOKEN_FILE.write_text(token + "\n", encoding="utf-8")

    def load_saved_config_url(self):
        try:
            url = CONFIG_URL_FILE.read_text(encoding="utf-8").strip()
            return url if self.is_valid_config_url(url) else None
        except Exception:
            return None

    def save_config_url(self, config_url: str):
        CONFIG_URL_FILE.write_text(config_url + "\n", encoding="utf-8")

    @staticmethod
    def is_valid_config_url(config_url: str) -> bool:
        parsed = urlparse(config_url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc) and not parsed.query and not parsed.fragment

    def ask_token_dialog(self, initial_token="", initial_url=""):
        dialog = tk.Toplevel(self.root)
        dialog.title("Данные VPN")
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        result = {"token": None, "config_url": None}
        frame = tk.Frame(dialog, bg=BG, padx=20, pady=18)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Данные подключения", bg=BG, fg=TITLE, font=(FONT, 14, "bold")).pack(anchor="w")
        tk.Label(frame, text="Введите UUID и URL сервера.", bg=BG, fg=MUTED, font=(FONT, 10)).pack(anchor="w", pady=(5, 12))

        tk.Label(frame, text="UUID токен", bg=BG, fg=TITLE, font=(FONT, 10, "bold")).pack(anchor="w")
        token_var = tk.StringVar(value=initial_token)
        token_entry = tk.Entry(frame, textvariable=token_var, width=54, font=(FONT, 12), bg="#0b1a2d", fg="#e5e7eb", insertbackground="white", relief="flat", highlightthickness=1, highlightbackground="#25425f", highlightcolor=BLUE)
        token_entry.pack(fill="x", ipady=8, pady=(5, 12))

        tk.Label(frame, text="URL сервера", bg=BG, fg=TITLE, font=(FONT, 10, "bold")).pack(anchor="w")
        url_var = tk.StringVar(value=initial_url)
        url_entry = tk.Entry(frame, textvariable=url_var, width=54, font=(FONT, 12), bg="#0b1a2d", fg="#e5e7eb", insertbackground="white", relief="flat", highlightthickness=1, highlightbackground="#25425f", highlightcolor=BLUE)
        url_entry.pack(fill="x", ipady=8, pady=(5, 0))

        error_label = tk.Label(frame, text="", bg=BG, fg=RED, font=(FONT, 9))
        error_label.pack(anchor="w", pady=(6, 0))

        button_row = tk.Frame(frame, bg=BG)
        button_row.pack(fill="x", pady=(12, 0))

        def save():
            token = token_var.get().strip()
            config_url = url_var.get().strip()
            try:
                result["token"] = str(uuid.UUID(token))
            except ValueError:
                error_label.config(text="Введите корректный UUID.")
                return
            if not self.is_valid_config_url(config_url):
                error_label.config(text="Введите корректный URL сервера: http:// или https://")
                return
            result["config_url"] = config_url
            dialog.destroy()

        def cancel():
            dialog.destroy()

        button_box = tk.Frame(button_row, bg=BG)
        button_box.pack(anchor="center")
        save_btn = ModernButton(
            button_box,
            "Сохранить",
            None,
            save,
            width=210,
            normal_bg="#1266d6",
            hover_bg="#1d7cff",
            border="#3b82f6",
            icon_file="ui_save.png",
            font_size=10,
            pady=7,
            height=44,
        )
        save_btn.pack(side="left", padx=(0, 10))
        cancel_btn = ModernButton(
            button_box,
            "Отмена",
            None,
            cancel,
            width=180,
            normal_bg="#10213a",
            hover_bg="#162b49",
            border="#25425f",
            icon_file="ui_cancel.png",
            font_size=10,
            pady=7,
            height=44,
        )
        cancel_btn.pack(side="left")

        dialog.protocol("WM_DELETE_WINDOW", cancel)
        dialog.bind("<Return>", lambda event: save())
        dialog.bind("<Escape>", lambda event: cancel())
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.root.winfo_rooty() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        token_entry.focus_set()
        token_entry.selection_range(0, tk.END)
        self.root.wait_window(dialog)
        return result["token"], result["config_url"]

    def prompt_for_token(self, force=False) -> bool:
        if self.client_uuid and self.config_url and not force:
            return True

        token, config_url = self.ask_token_dialog(self.client_uuid or "", self.config_url or "")
        if not token or not config_url:
            return False

        self.client_uuid = token
        self.config_url = config_url
        try:
            self.save_token(token)
            self.save_config_url(config_url)
            self.write_log("Токен и URL сервера сохранены.\n")
        except Exception as e:
            self.write_log(f"Не удалось сохранить данные подключения: {e}\n")
        return True

    def change_token(self):
        if self.is_exiting:
            return
        if self.prompt_for_token(force=True):
            if self.connection_state == "connected":
                self.write_log("Новые данные будут применены при следующем подключении.\n")
            else:
                self.write_log("Новые данные будут использованы при подключении.\n")

    def request_token_on_start(self):
        if self.client_uuid and self.config_url:
            return
        if not self.prompt_for_token():
            self.set_status("disconnected", "Требуется токен или URL", ORANGE, "orange", True, False, True)

    def set_status(self, state, text, color, dot_color, start_enabled, stop_enabled, exit_enabled):
        self.connection_state = state
        self.status_var.set(text)
        self.status_label.config(fg=color)
        if state == "connected":
            self.power_button.set_state("connected", True)
        elif state == "busy":
            self.power_button.set_state("busy", False)
        else:
            self.power_button.set_state("disconnected", start_enabled)
        if hasattr(self, "token_btn"):
            self.token_btn.set_enabled(not self.is_exiting)
        if hasattr(self, "log_btn"):
            self.log_btn.set_enabled(not self.is_exiting)
        if hasattr(self, "exit_btn"):
            self.exit_btn.set_enabled(exit_enabled)
        self.update_tray_icon(dot_color)

    def set_checking(self):
        self.set_status("busy", "Проверка конфига...", ORANGE, "orange", False, False, True)

    def set_installing(self):
        self.set_status("busy", "Первичная настройка...", ORANGE, "orange", False, False, False)

    def set_verifying(self):
        self.set_status("busy", "Проверка VPN...", ORANGE, "orange", False, False, True)

    def set_connected(self, vpn_ip=None):
        self.is_stopping = False
        self.vpn_ip = vpn_ip or self.vpn_ip
        status_text = f"Подключено · IP {self.vpn_ip}" if self.vpn_ip else "Подключено"
        self.set_status("connected", status_text, GREEN, "green", False, True, True)
        if not self.connected_since:
            self.connected_since = time.time()
            self.update_timer()

    def set_disconnected(self):
        self.is_stopping = False
        self.connected_since = None
        self.vpn_ip = None
        self.timer_var.set("00:00:00")
        self.set_status("disconnected", "Отключено", RED, "red", True, False, True)

    def install_helper_if_needed(self) -> bool:
        if helper_ready():
            return True
        self.log_safe("Требуется первичная установка helper. Сейчас macOS попросит пароль администратора один раз.\n")
        result = run_admin_shell(install_helper_command())
        if result.returncode != 0:
            self.log_safe("Ошибка установки helper.\n")
            if result.stderr:
                self.log_safe(result.stderr + "\n")
            if result.stdout:
                self.log_safe(result.stdout + "\n")
            return False
        time.sleep(0.5)
        if not helper_ready():
            self.log_safe("Helper установлен, но sudo -n проверка не прошла.\n")
            return False
        self.log_safe("Helper успешно установлен. Дальше пароль спрашиваться не должен.\n")
        return True

    def start_vpn(self):
        if self.connection_state != "disconnected" or self.is_exiting:
            return
        if not self.prompt_for_token():
            self.set_status("disconnected", "Требуется токен или URL", ORANGE, "orange", True, False, True)
            return
        self.set_checking()
        threading.Thread(target=self.prepare_and_start_vpn, daemon=True).start()

    def prepare_and_start_vpn(self):
        if not BUNDLED_SING_BOX.exists() and not SYSTEM_SING_BOX.exists():
            self.log_safe(f"Ошибка: не найден sing-box:\n{BUNDLED_SING_BOX}\n")
            self.root.after(0, self.set_disconnected)
            return
        before_ip = self.get_public_ip_for_log("IP до подключения")
        ok = update_config_from_template(self.log_safe, self.client_uuid, self.config_url)
        if not ok:
            self.root.after(0, self.set_disconnected)
            self.root.after(0, messagebox.showerror, "Ошибка", CONFIG_DOWNLOAD_ERROR)
            return
        self.log_safe("Проверка config.json успешна, запускаю VPN клиент...\n")
        if not helper_ready():
            self.root.after(0, self.set_installing)
            if not self.install_helper_if_needed():
                self.root.after(0, self.set_disconnected)
                self.root.after(0, messagebox.showerror, "Ошибка", "Не удалось установить helper")
                return
        self.launch_singbox_helper(before_ip)

    def get_public_ip_for_log(self, label):
        try:
            ip = fetch_public_ip()
            if ip:
                self.log_safe(f"{label}: {ip}\n")
                return ip
            self.log_safe(f"{label}: не удалось определить\n")
        except Exception as e:
            self.log_safe(f"{label}: не удалось определить ({e})\n")
        return None

    def refresh_connected_ip(self):
        self.log_safe("Проверяю IP активного VPN через ident.me...\n")
        ip = self.get_public_ip_for_log("Текущий IP")
        if ip and self.connection_state == "connected":
            self.root.after(0, self.set_connected, ip)

    def verify_vpn_connection(self, before_ip):
        self.root.after(0, self.set_verifying)
        self.log_safe("Проверка VPN через ident.me...\n")
        deadline = time.time() + VPN_VERIFY_TIMEOUT
        last_ip = None
        last_error = None
        same_ip_count = 0

        while time.time() < deadline:
            if not launchd_is_running():
                return False, None, "сервис sing-box остановлен"
            try:
                ip = fetch_public_ip(timeout=VPN_VERIFY_HTTP_TIMEOUT)
                if ip:
                    last_ip = ip
                    if before_ip and ip == before_ip:
                        same_ip_count += 1
                        self.log_safe(
                            f"ident.me вернул прежний IP: {ip}. Проверка {same_ip_count}/{VPN_VERIFY_SAME_IP_LIMIT}...\n"
                        )
                        if same_ip_count >= VPN_VERIFY_SAME_IP_LIMIT:
                            return False, ip, "внешний IP не изменился"
                    else:
                        self.log_safe(f"VPN IP подтверждён: {ip}\n")
                        return True, ip, None
                else:
                    last_error = "ident.me вернул пустой ответ"
            except Exception as e:
                last_error = str(e)
                self.log_safe(f"ident.me пока недоступен: {e}\n")
            time.sleep(VPN_VERIFY_INTERVAL)

        if last_ip and before_ip and last_ip == before_ip:
            return False, last_ip, "внешний IP не изменился"
        return False, last_ip, last_error or "не удалось получить внешний IP"

    def stop_helper_after_failed_verify(self):
        self.log_safe("Останавливаю sing-box после неудачной проверки VPN...\n")
        try:
            if helper_ready():
                result = run_helper("stop")
            else:
                result = run_admin_shell(
                    f"launchctl stop system/{LAUNCHD_LABEL} >/dev/null 2>&1 || true; "
                    "sleep 3; "
                    f"launchctl kill SIGTERM system/{LAUNCHD_LABEL} >/dev/null 2>&1 || true"
                )
            debug_output = helper_output(result)
            if debug_output:
                self.log_safe(debug_output + "\n")
            if result.returncode != 0:
                self.log_safe(f"helper stop завершился с кодом {result.returncode}\n")
        except Exception as e:
            self.log_safe(f"Не удалось остановить sing-box после проверки: {e}\n")

    def launch_singbox_helper(self, before_ip=None):
        self.log_safe("Запуск sing-box через helper...\n")
        self.log_position = 0
        self.first_log_sync_done = False
        self.start_log_tail()
        result = run_helper("start")
        if result.returncode != 0:
            self.log_safe("Ошибка запуска helper.\n")
            if result.stderr:
                self.log_safe(result.stderr + "\n")
            if result.stdout:
                self.log_safe(result.stdout + "\n")
            self.root.after(0, self.set_disconnected)
            return
        for _ in range(12):
            time.sleep(0.5)
            if launchd_is_running():
                self.log_safe("sing-box запущен.\n")
                ok, vpn_ip, reason = self.verify_vpn_connection(before_ip)
                if ok:
                    self.root.after(0, self.set_connected, vpn_ip)
                    return
                self.log_safe(f"VPN не подтверждён: {reason}\n")
                if vpn_ip:
                    self.log_safe(f"Последний IP от ident.me: {vpn_ip}\n")
                self.stop_helper_after_failed_verify()
                self.root.after(0, self.set_disconnected)
                self.root.after(0, messagebox.showerror, "Ошибка", VPN_VERIFY_ERROR)
                return
        self.log_safe("Сервис создан, но статус running не подтверждён.\n")
        self.root.after(0, self.set_disconnected)
        self.root.after(0, messagebox.showerror, "Ошибка", VPN_VERIFY_ERROR)

    def start_log_tail(self):
        if self.log_tail_running:
            return
        self.log_tail_running = True
        threading.Thread(target=self.tail_log_loop, daemon=True).start()

    def tail_log_loop(self):
        while self.log_tail_running:
            try:
                if SYSTEM_LOG.exists():
                    with open(SYSTEM_LOG, "r", encoding="utf-8", errors="replace") as f:
                        if not self.first_log_sync_done:
                            f.seek(0, os.SEEK_END)
                            self.log_position = f.tell()
                            self.first_log_sync_done = True
                        f.seek(self.log_position)
                        lines = f.readlines()
                        self.log_position = f.tell()
                    for line in lines:
                        self.root.after(0, self.write_log, clean_log(line))
            except Exception:
                pass
            time.sleep(0.5)

    def stop_vpn(self):
        if self.is_stopping or self.connection_state != "connected" or self.is_exiting:
            return
        self.is_stopping = True
        self.set_status("busy", "Отключение...", ORANGE, "orange", False, False, True)
        threading.Thread(target=self.stop_vpn_worker, daemon=True).start()

    def stop_vpn_worker(self):
        self.log_safe("\nОстановка sing-box через helper...\n")
        if helper_ready():
            result = run_helper("stop")
        else:
            result = run_admin_shell(
                f"launchctl stop system/{LAUNCHD_LABEL} >/dev/null 2>&1 || true; "
                "sleep 3; "
                f"launchctl kill SIGTERM system/{LAUNCHD_LABEL} >/dev/null 2>&1 || true"
            )
        debug_output = helper_output(result)
        if debug_output:
            self.log_safe(debug_output + "\n")
        if result.returncode != 0:
            self.log_safe(f"helper stop завершился с кодом {result.returncode}\n")
        time.sleep(1.0)
        if launchd_is_running():
            self.log_safe("Предупреждение: сервис всё ещё активен.\n")
            self.root.after(0, self.set_connected)
            return
        self.log_safe("sing-box остановлен.\n")
        self.root.after(0, self.set_disconnected)

    def cleanup_on_exit(self):
        """Best-effort cleanup for Cmd+Q / Dock Quit / app shutdown."""
        try:
            if helper_ready():
                run_helper("stop")
        except Exception:
            pass

    def exit_app(self, icon=None, item=None):
        if self.is_exiting:
            return

        self.is_exiting = True
        self.connection_state = "busy"
        self.power_button.set_state("busy", False)
        self.token_btn.set_enabled(False)
        self.log_btn.set_enabled(False)
        self.exit_btn.set_enabled(False)
        self.status_var.set("Выход...")
        self.status_label.config(fg=ORANGE)
        self.update_tray_icon("orange")

        def worker():
            try:
                if self.connection_state == "connected" or launchd_is_running():
                    self.stop_vpn_worker()
            finally:
                self.log_tail_running = False
                if self.tray_icon:
                    self.tray_icon.stop()
                self.root.after(0, self.root.destroy)

        threading.Thread(target=worker, daemon=True).start()


def main():
    if platform.system() != "Darwin":
        messagebox.showerror("Ошибка", "Этот клиент предназначен для macOS.")
        sys.exit(1)
    root = tk.Tk()
    app = SingBoxGUI(root)
    atexit.register(app.cleanup_on_exit)
    root.mainloop()


if __name__ == "__main__":
    main()
