import json
import math
import os
import platform
import queue
import re
import signal
import subprocess
import ctypes
import sys
import tempfile
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
VPN_VERIFY_ERROR = "VPN запустился, но внешний IP не изменился. Проверьте UUID или доступность сервера."
VPN_START_ERROR = "Windows не смог создать VPN-интерфейс. Попробуйте подключить ещё раз."
APP_TITLE = "WorkVPN"
TRAY_ICON_SIZE = 256

DOWNLOAD_RETRIES = 3
RETRY_DELAY = 2
PUBLIC_IP_URL = "https://ident.me"
VPN_VERIFY_TIMEOUT = 30
VPN_VERIFY_INTERVAL = 1
VPN_VERIFY_HTTP_TIMEOUT = 4
SINGBOX_START_RETRIES = 2
SINGBOX_START_RETRY_DELAY = 5
SINGBOX_ALIVE_CHECK_DELAY = 1.2

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

FONT = "Segoe UI"


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
APP_SUPPORT = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or APP_DIR) / "WorkVPN"
APP_SUPPORT.mkdir(parents=True, exist_ok=True)
CONFIG = APP_SUPPORT / "config.json"
TOKEN_FILE = APP_SUPPORT / "token.txt"
CONFIG_URL_FILE = APP_SUPPORT / "config_url.txt"


def resource_path(name: str) -> Path:
    possible_paths = [
        APP_DIR / name,
        Path(getattr(sys, "_MEIPASS", APP_DIR)) / name,
        REPO_ROOT / name,
        Path.cwd() / name,
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return APP_DIR / name


def find_icon_file() -> Path:
    possible_paths = [
        APP_DIR / "vpn_icon.ico",
        Path(getattr(sys, "_MEIPASS", APP_DIR)) / "vpn_icon.ico",
        REPO_ROOT / "assets" / "vpn_icon.ico",
        Path.cwd() / "vpn_icon.ico",
        APP_DIR / "vpn_icon.icns",
        Path(getattr(sys, "_MEIPASS", APP_DIR)) / "vpn_icon.icns",
        REPO_ROOT / "assets" / "vpn_icon.icns",
        Path.cwd() / "vpn_icon.icns",
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return APP_DIR / "vpn_icon.ico"


ICON_FILE = find_icon_file()
WINDOW_ICON_CACHE = None


def load_icon_source_image():
    candidates = (
        resource_path("assets/workvpn_icon_imagegen_source.png"),
        resource_path("assets/workvpn_icon_tile_source.png"),
        ICON_FILE,
    )
    for source in candidates:
        try:
            icon = Image.open(source)
            if hasattr(icon, "ico"):
                largest_size = max(icon.ico.sizes(), key=lambda item: item[0] * item[1])
                icon = icon.ico.getimage(largest_size)
            return icon.convert("RGBA")
        except Exception:
            continue
    return None


def render_system_icon_layer(source, size: int):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    icon = source.copy()
    icon.thumbnail((size, size), Image.LANCZOS)
    image.alpha_composite(icon, ((size - icon.width) // 2, (size - icon.height) // 2))
    if size <= 64:
        image = image.filter(ImageFilter.UnsharpMask(radius=0.45, percent=185, threshold=1))
    if size <= 24:
        image = image.filter(ImageFilter.UnsharpMask(radius=0.30, percent=120, threshold=0))
    return image


def get_windows_system_icon_file():
    global WINDOW_ICON_CACHE
    if WINDOW_ICON_CACHE and WINDOW_ICON_CACHE.exists():
        return WINDOW_ICON_CACHE

    source = load_icon_source_image()
    if source is None:
        return ICON_FILE

    try:
        cache_dir = Path(tempfile.gettempdir()) / "WorkVPN"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / "workvpn_system_icon.ico"
        sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
        layers = [render_system_icon_layer(source, size) for size in sizes]
        layers[-1].save(cache_path, format="ICO", sizes=[(size, size) for size in sizes], append_images=layers[:-1])
        WINDOW_ICON_CACHE = cache_path
        return cache_path
    except Exception:
        return ICON_FILE


def load_window_icon(size: int):
    source = load_icon_source_image()
    if source is None:
        return None
    return ImageTk.PhotoImage(render_system_icon_layer(source, size))


def apply_window_icon(root):
    icons = []
    for size in (256, 64, 48, 32, 24, 20, 16):
        icon = load_window_icon(size)
        if icon:
            icons.append(icon)
    if icons:
        root._workvpn_window_icons = icons
        try:
            root.iconphoto(True, *icons)
        except Exception:
            pass
    try:
        if os.name != "nt" and ICON_FILE.exists() and ICON_FILE.suffix.lower() == ".ico":
            root.iconbitmap(str(ICON_FILE))
    except Exception:
        pass

    if os.name != "nt":
        return
    try:
        hwnd = root.winfo_id()
        user32 = ctypes.windll.user32
        image_icon = 1
        lr_load_from_file = 0x0010
        wm_seticon = 0x0080
        icon_small = 0
        icon_big = 1
        sm_cxicon = 11
        sm_cyicon = 12
        sm_cxsmicon = 49
        sm_cysmicon = 50
        big_w = max(64, user32.GetSystemMetrics(sm_cxicon))
        big_h = max(64, user32.GetSystemMetrics(sm_cyicon))
        small_w = max(16, user32.GetSystemMetrics(sm_cxsmicon))
        small_h = max(16, user32.GetSystemMetrics(sm_cysmicon))
        system_icon_file = get_windows_system_icon_file()
        big_icon = user32.LoadImageW(None, str(system_icon_file), image_icon, big_w, big_h, lr_load_from_file)
        small_icon = user32.LoadImageW(None, str(system_icon_file), image_icon, small_w, small_h, lr_load_from_file)
        if big_icon:
            user32.SendMessageW(hwnd, wm_seticon, icon_big, big_icon)
        if small_icon:
            user32.SendMessageW(hwnd, wm_seticon, icon_small, small_icon)
        root._workvpn_hicons = [h for h in (big_icon, small_icon) if h]
    except Exception:
        pass


def windows_runtime_dir() -> str:
    machine = (platform.machine() or "").lower()
    return "windows-arm64" if machine in ("arm64", "aarch64") else "windows-amd64"


def find_bundled_sing_box() -> Path:
    runtime_dir = windows_runtime_dir()
    possible_paths = [
        APP_DIR / "sing-box.exe",
        Path(getattr(sys, "_MEIPASS", APP_DIR)) / "sing-box.exe",
        REPO_ROOT / "runtime" / runtime_dir / "sing-box.exe",
        REPO_ROOT / "runtime" / "windows" / "sing-box.exe",
        Path.cwd() / "sing-box.exe",
        APP_DIR / "sing-box",
        Path(getattr(sys, "_MEIPASS", APP_DIR)) / "sing-box",
        Path.cwd() / "sing-box",
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return APP_DIR / "sing-box.exe"


SING_BOX = find_bundled_sing_box()


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


def collect_values_by_key(value, target_key: str):
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == target_key and isinstance(item, str) and item.strip():
                found.append(item.strip())
            found.extend(collect_values_by_key(item, target_key))
    elif isinstance(value, list):
        for item in value:
            found.extend(collect_values_by_key(item, target_key))
    return found



def singbox_creationflags():
    if os.name != "nt":
        return 0
    return subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE


def singbox_startupinfo():
    if os.name != "nt":
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return startupinfo


def send_windows_ctrl_break(process):
    if os.name != "nt" or not process or process.poll() is not None:
        return False
    kernel32 = ctypes.windll.kernel32
    ctrl_break_event = 1
    kernel32.FreeConsole()
    attached = kernel32.AttachConsole(process.pid)
    if not attached:
        return False
    try:
        kernel32.SetConsoleCtrlHandler(None, True)
        ok = kernel32.GenerateConsoleCtrlEvent(ctrl_break_event, process.pid)
        time.sleep(0.3)
        return bool(ok)
    finally:
        kernel32.FreeConsole()
        kernel32.SetConsoleCtrlHandler(None, False)


def stop_singbox_process(process, log_func=None, timeout=8):
    if not process or process.poll() is not None:
        return

    def log(message):
        if log_func:
            log_func(message)

    if os.name == "nt":
        log("Отправляю sing-box мягкую остановку...\n")
        if send_windows_ctrl_break(process):
            try:
                process.wait(timeout=timeout)
                return
            except subprocess.TimeoutExpired:
                log("sing-box не завершился после Ctrl+Break, пробую обычную остановку...\n")
        else:
            log("Ctrl+Break недоступен, пробую обычную остановку...\n")

    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def validate_singbox_config(config_path: Path, log_func) -> bool:
    try:
        log_func("Проверка sing-box check...\n")
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            [str(SING_BOX), "check", "-c", str(config_path)],
            cwd=str(APP_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            **kwargs,
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
        try:
            icon = Image.open(ICON_FILE)
            if hasattr(icon, "ico"):
                largest_size = max(icon.ico.sizes(), key=lambda item: item[0] * item[1])
                icon = icon.ico.getimage(largest_size)
            return icon.convert("RGBA").resize((TRAY_ICON_SIZE, TRAY_ICON_SIZE), Image.LANCZOS)
        except Exception:
            image = Image.new("RGBA", (TRAY_ICON_SIZE, TRAY_ICON_SIZE), (15, 23, 42, 255))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((45, 45, 211, 211), radius=44, fill=(30, 41, 59, 255))
            return image


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    if getattr(sys, "frozen", False):
        params = " ".join(f'"{arg}"' for arg in sys.argv[1:])
    else:
        params = " ".join(f'"{arg}"' for arg in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, str(APP_DIR), 1)
    sys.exit(0)


def set_windows_app_id():
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WorkVPN")
    except Exception:
        pass


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
        self.icon_size = max(21, int(height * 0.58))
        self.icon_gap = max(10, int(height * 0.30))
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
        apply_window_icon(self.root)
        self.ui_scale = self.calculate_ui_scale()
        self.window_width, self.window_height = self.calculate_window_size()
        self.root.geometry(f"{self.window_width}x{self.window_height}")
        self.root.minsize(430, 650)
        self.root.resizable(False, False)
        self.status_var = tk.StringVar(value="Отключено")
        self.timer_var = tk.StringVar(value="00:00:00")
        self.connection_state = "disconnected"
        self.client_uuid = self.load_saved_token()
        self.config_url = self.load_saved_config_url()
        self.process = None
        self.tray_actions = queue.Queue()
        self.tray_icon = None
        self.logo_image = None
        self.power_button = None
        self.log_panel = None
        self.log_panel_visible = False
        self.log_panel_height = 0
        self.log_panel_target = self.scale_px(220)
        self.connected_since = None
        self.vpn_ip = None
        self.is_stopping = False
        self.is_exiting = False
        self.logo_size = self.clamp_px(90, 78, 104)
        self.title_size = self.fit_font_size(APP_TITLE, 30, self.window_width - self.scale_px(110), 22, 30, "bold")
        self.subtitle_size = self.clamp_px(11, 10, 13)
        self.timer_size = self.clamp_px(24, 22, 28)
        self.power_size = self.clamp_px(108, 96, 120)
        self.center_window()
        self.build_ui()
        self.register_windows_window_handlers()
        self.root.after(250, lambda: apply_window_icon(self.root))
        self.root.after(100, self.process_tray_actions)
        self.create_tray()
        self.root.after(250, self.request_token_on_start)
        self.log_safe(f"Bundled sing-box: {SING_BOX}\n")
        if self.client_uuid:
            self.log_safe("Сохранённый токен загружен.\n")

    def register_windows_window_handlers(self):
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.root.bind("<Unmap>", self.on_minimize)

    def on_minimize(self, event):
        if self.root.state() == "iconic" and not self.is_exiting:
            self.root.after(100, self.hide_to_tray)

    def hide_to_tray(self):
        try:
            self.root.withdraw()
        except Exception:
            pass

    def show_window(self, icon=None, item=None):
        try:
            self.root.deiconify()
            self.root.state("normal")
            self.center_window()
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
            self.log_safe("pystray не установлен: значок в трее недоступен.\n")
            return
        menu = pystray.Menu(
            pystray.MenuItem("Открыть", lambda icon, item: self.enqueue_tray_action("show"), default=True),
            pystray.MenuItem(self.tray_vpn_ip_text, None, enabled=False, visible=self.tray_has_vpn_ip),
            pystray.MenuItem("Подключить", lambda icon, item: self.enqueue_tray_action("start"), enabled=self.tray_can_start),
            pystray.MenuItem("Отключить", lambda icon, item: self.enqueue_tray_action("stop"), enabled=self.tray_can_stop),
            pystray.MenuItem("Выход", lambda icon, item: self.enqueue_tray_action("exit")),
        )
        self.tray_icon = pystray.Icon(APP_TITLE, create_tray_image("red"), f"{APP_TITLE} - отключено", menu)
        threading.Thread(target=self.run_tray_icon, daemon=True).start()

    def run_tray_icon(self):
        try:
            self.tray_icon.run()
        except Exception as e:
            self.log_safe(f"Ошибка запуска значка в трее: {e}\n")

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

    def scale_px(self, value):
        return max(1, int(round(value * self.ui_scale)))

    def clamp_px(self, value, min_value, max_value):
        return max(min_value, min(self.scale_px(value), max_value))

    def fit_font_size(self, text, base_size, max_width, min_size, max_size, weight="normal"):
        size = max(min_size, min(self.scale_px(base_size), max_size))
        while size > min_size:
            if tkfont.Font(family=FONT, size=size, weight=weight).measure(text) <= max_width:
                return size
            size -= 1
        return min_size

    def calculate_ui_scale(self):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        short_side = min(screen_width, screen_height)
        long_side = max(screen_width, screen_height)

        if short_side <= 800:
            return 0.88
        if short_side <= 900:
            return 0.94
        if long_side >= 3600 or short_side >= 2000:
            return 1.18
        if long_side >= 2500 or short_side >= 1350:
            return 1.08
        return 1.0

    def calculate_window_size(self):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(max(self.scale_px(560), 500), screen_width - 80)
        height = min(max(self.scale_px(780), 700), screen_height - 70)
        return width, height

    def build_ui(self):
        self.root.configure(bg=BG)
        wrapper = tk.Frame(self.root, bg=BG)
        wrapper.pack(fill="both", expand=True, padx=self.scale_px(32), pady=(self.scale_px(20), self.scale_px(30)))

        buttons = tk.Frame(wrapper, bg=BG)
        buttons.pack(side="bottom", fill="x")

        button_height = self.scale_px(44)
        button_font = self.clamp_px(10, 9, 12)
        self.token_btn = ModernButton(buttons, "Изменить токен или URL", None, self.change_token, width=310, height=button_height, font_size=button_font, icon_file="ui_token.png")
        self.token_btn.pack(anchor="center", fill="x", pady=(0, self.scale_px(8)))
        self.log_btn = ModernButton(buttons, "Лог", None, self.toggle_log_panel, width=310, height=button_height, font_size=button_font, icon_file="ui_log.png")
        self.log_btn.pack(anchor="center", fill="x", pady=(0, self.scale_px(8)))
        self.exit_btn = ModernButton(
            buttons,
            "Выход",
            None,
            self.exit_app,
            width=310,
            height=button_height,
            font_size=button_font,
            normal_bg="#4a1624",
            hover_bg="#6d1d32",
            border="#9f2947",
            fg="#ffe4ea",
            icon_file="ui_exit.png",
        )
        self.exit_btn.pack(anchor="center", fill="x")

        top = tk.Frame(wrapper, bg=BG)
        top.pack(side="top", fill="both", expand=True)

        tk.Label(top, text=APP_TITLE, bg=BG, fg=TITLE, font=(FONT, self.title_size, "bold")).pack(anchor="center")
        tk.Label(top, text="Защищенное подключение", bg=BG, fg=MUTED, font=(FONT, self.subtitle_size)).pack(anchor="center", pady=(self.scale_px(2), self.scale_px(8)))

        self.logo_image = load_logo(self.logo_size)
        if self.logo_image:
            logo = tk.Label(top, image=self.logo_image, bg=BG)
        else:
            logo = tk.Label(top, text="VPN", bg=BG, fg=GREEN, font=(FONT, self.scale_px(42), "bold"))
        logo.pack(anchor="center")

        tk.Label(top, text="Время подключения", bg=BG, fg=MUTED, font=(FONT, self.clamp_px(10, 9, 12), "bold")).pack(anchor="center", pady=(self.scale_px(14), self.scale_px(2)))
        self.timer_label = tk.Label(top, textvariable=self.timer_var, bg=BG, fg=TITLE, font=(FONT, self.timer_size))
        self.timer_label.pack(anchor="center")

        self.power_button = PowerButton(top, self.toggle_vpn, self.power_size)
        self.power_button.pack(anchor="center", pady=(self.scale_px(10), self.scale_px(6)))

        self.status_label = tk.Label(top, textvariable=self.status_var, bg=BG, fg=RED, font=(FONT, self.clamp_px(10, 9, 11), "bold"))
        self.status_label.pack(anchor="center", pady=(0, self.scale_px(20)))

        self.log_panel = tk.Frame(self.root, bg="#07111f", highlightthickness=1, highlightbackground="#24415f")
        self.log_panel.place(x=self.scale_px(28), y=self.window_height, width=self.window_width - self.scale_px(56), height=0)
        log_header = tk.Frame(self.log_panel, bg="#0d1c31")
        log_header.pack(fill="x")
        tk.Label(log_header, text="Лог sing-box", bg="#0d1c31", fg=TITLE, font=(FONT, self.clamp_px(11, 10, 13), "bold")).pack(side="left", padx=14, pady=9)
        close_log = tk.Label(log_header, text="Скрыть", bg="#0d1c31", fg=MUTED, font=(FONT, self.clamp_px(10, 9, 12), "bold"), cursor="hand2")
        close_log.pack(side="right", padx=14)
        close_log.bind("<Button-1>", lambda event: self.toggle_log_panel(False))
        self.log = scrolledtext.ScrolledText(
            self.log_panel,
            width=72,
            height=10,
            font=("Cascadia Mono", 9),
            bg="#030a14",
            fg="#d7e3f4",
            insertbackground="white",
            relief="flat",
            bd=0,
            highlightthickness=0,
        )
        self.log.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.set_disconnected()

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

    def start_vpn(self):
        if self.connection_state != "disconnected" or self.is_exiting:
            return
        if not SING_BOX.exists():
            messagebox.showerror("Ошибка", f"Не найден файл:\n{SING_BOX}")
            return
        if not self.prompt_for_token():
            self.set_status("disconnected", "Требуется токен или URL", ORANGE, "orange", True, False, True)
            return
        self.set_checking()
        threading.Thread(target=self.prepare_and_start_vpn, daemon=True).start()

    def prepare_and_start_vpn(self):
        before_ip = self.get_public_ip_for_log("IP до подключения")
        ok = update_config_from_template(self.log_safe, self.client_uuid, self.config_url)
        if not ok:
            self.root.after(0, self.set_disconnected)
            self.root.after(0, messagebox.showerror, "Ошибка", CONFIG_DOWNLOAD_ERROR)
            return
        self.log_safe("Проверка config.json успешна, запускаю VPN клиент...\n")
        self.root.after(0, self.launch_singbox, before_ip)

    def launch_singbox(self, before_ip=None):
        if not CONFIG.exists():
            messagebox.showerror("Ошибка", f"Не найден файл:\n{CONFIG}")
            self.set_disconnected()
            return
        self.set_verifying()
        threading.Thread(target=self.launch_singbox_worker, args=(before_ip,), daemon=True).start()

    def launch_singbox_worker(self, before_ip=None):
        last_error = None
        for attempt in range(1, SINGBOX_START_RETRIES + 1):
            if self.is_exiting or self.is_stopping:
                return
            if attempt > 1:
                self.log_safe("Жду паузу перед повторным запуском...\n")
                time.sleep(SINGBOX_START_RETRY_DELAY)

            self.log_safe(f"Запуск sing-box, попытка {attempt}/{SINGBOX_START_RETRIES}...\n")
            try:
                kwargs = {}
                if os.name == "nt":
                    kwargs["creationflags"] = singbox_creationflags()
                    kwargs["startupinfo"] = singbox_startupinfo()
                process = subprocess.Popen(
                    [str(SING_BOX), "run", "-c", str(CONFIG)],
                    cwd=str(APP_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    **kwargs,
                )
            except Exception as e:
                last_error = str(e)
                self.log_safe(f"Ошибка запуска sing-box: {e}\n")
                break

            self.process = process
            threading.Thread(target=self.read_logs, args=(process,), daemon=True).start()
            threading.Thread(target=self.watch_process, args=(process,), daemon=True).start()

            time.sleep(SINGBOX_ALIVE_CHECK_DELAY)
            if process.poll() is None:
                self.log_safe("sing-box запущен, проверяю внешний IP...\n")
                threading.Thread(target=self.verify_after_start, args=(before_ip, process), daemon=True).start()
                return

            last_error = f"sing-box завершился при старте с кодом {process.returncode}"
            self.log_safe(last_error + "\n")
            if self.process is process:
                self.process = None

        self.log_safe(f"Не удалось запустить sing-box: {last_error or 'неизвестная ошибка'}\n")
        self.root.after(0, self.set_disconnected)
        self.root.after(0, messagebox.showerror, "Ошибка", VPN_START_ERROR)

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

    def verify_vpn_connection(self, before_ip, process=None):
        self.log_safe(f"Проверяю внешний IP через ident.me до {VPN_VERIFY_TIMEOUT} секунд...\n")
        deadline = time.time() + VPN_VERIFY_TIMEOUT
        last_ip = None
        last_error = None
        unchanged_logged_at = 0

        while time.time() < deadline:
            active_process = process or self.process
            if not active_process or active_process.poll() is not None:
                return False, None, "процесс sing-box остановлен"
            try:
                ip = fetch_public_ip(timeout=VPN_VERIFY_HTTP_TIMEOUT)
                if ip:
                    last_ip = ip
                    if before_ip and ip == before_ip:
                        now = time.time()
                        if now - unchanged_logged_at >= 5:
                            left = max(0, int(deadline - now))
                            self.log_safe(f"Текущий IP пока прежний: {ip}. Проверяю ещё до {left} сек.\n")
                            unchanged_logged_at = now
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
            return False, last_ip, "внешний IP не изменился после запуска sing-box"
        return False, last_ip, last_error or "не удалось получить внешний IP"

    def verify_after_start(self, before_ip, process=None):
        ok, vpn_ip, reason = self.verify_vpn_connection(before_ip, process)
        if ok:
            self.root.after(0, self.set_connected, vpn_ip)
            return
        self.log_safe(f"VPN не подтверждён: {reason}\n")
        if vpn_ip:
            self.log_safe(f"Последний IP от ident.me: {vpn_ip}\n")
        if reason == "процесс sing-box остановлен":
            self.root.after(0, self.set_disconnected)
            self.root.after(0, messagebox.showerror, "Ошибка", VPN_START_ERROR)
            return
        self.stop_process_after_failed_verify(process)
        self.root.after(0, self.set_disconnected)
        self.root.after(0, messagebox.showerror, "Проверка VPN", VPN_VERIFY_ERROR)


    def stop_process_after_failed_verify(self, process=None):
        self.log_safe("Останавливаю sing-box после неудачной проверки VPN...\n")
        active_process = process or self.process
        stop_singbox_process(active_process, self.log_safe)
        if self.process is active_process:
            self.process = None


    def read_logs(self, process=None):
        try:
            active_process = process or self.process
            if not active_process or not active_process.stdout:
                return
            for line in active_process.stdout:
                self.root.after(0, self.write_log, clean_log(line))
        except Exception as e:
            self.root.after(0, self.write_log, f"\nОшибка чтения лога: {e}\n")

    def watch_process(self, process=None):
        active_process = process or self.process
        if not active_process:
            return
        code = active_process.wait()
        self.root.after(0, self.write_log, f"\nsing-box завершился с кодом {code}\n")
        if self.process is active_process:
            self.process = None
        if self.process is None and not self.is_exiting and not self.is_stopping:
            self.root.after(0, self.set_disconnected)

    def stop_vpn(self):
        if self.is_stopping or self.connection_state != "connected" or self.is_exiting:
            return
        self.is_stopping = True
        self.set_status("busy", "Отключение...", ORANGE, "orange", False, False, True)
        threading.Thread(target=self.stop_vpn_worker, daemon=True).start()

    def stop_vpn_worker(self):
        self.log_safe("\nОстановка sing-box...\n")
        active_process = self.process
        try:
            stop_singbox_process(active_process, self.log_safe)
        except Exception as e:
            self.log_safe(f"Ошибка остановки sing-box: {e}\n")
        if self.process is active_process:
            self.process = None
        self.log_safe("sing-box остановлен.\n")
        if not self.is_exiting:
            self.root.after(0, self.set_disconnected)


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
                stop_singbox_process(self.process, self.log_safe)
            finally:
                if self.tray_icon:
                    self.tray_icon.stop()
                self.root.after(0, self.root.destroy)

        threading.Thread(target=worker, daemon=True).start()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    if os.name == "nt" and not is_admin():
        relaunch_as_admin()

    set_windows_app_id()
    root = tk.Tk()
    app = SingBoxGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
