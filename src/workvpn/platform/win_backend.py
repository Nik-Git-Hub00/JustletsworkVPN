import json
import locale
import os
import platform
import re
import subprocess
import ctypes
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlparse
from pathlib import Path

try:
    import pystray
except Exception:
    pystray = None

from PIL import Image, ImageDraw, ImageFilter

try:
    import ssl
    import certifi
except Exception:
    ssl = None
    certifi = None


CUSTOM_USER_AGENT = "SingBoxVPN-Client/1.0-private"


def detect_language() -> str:
    try:
        candidates = []
        for getter in (locale.getlocale, locale.getdefaultlocale):
            try:
                value = getter()[0]
            except Exception:
                value = None
            if value:
                candidates.append(value)
        for env_name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
            value = os.environ.get(env_name)
            if value:
                candidates.append(value)
        return "ru" if any(str(value).lower().startswith("ru") for value in candidates) else "en"
    except Exception:
        return "en"


LANG = detect_language()

I18N = {
    "ru": {
        "config_download_error": "Не удалось скачать конфиг. Проверьте правильность URL и учётных данных.",
        "vpn_verify_error": "Не удалось подтвердить VPN-подключение. Проверьте UUID.",
        "vpn_verify_error_win": "VPN запустился, но внешний IP не изменился. Проверьте UUID или доступность сервера.",
        "vpn_start_error_win": "Windows не смог создать VPN-интерфейс. Попробуйте подключить ещё раз.",
        "singbox_check": "Проверка sing-box check...\n",
        "singbox_check_ok": "Проверка sing-box config: OK\n",
        "singbox_check_error": "Проверка sing-box config: ошибка\n",
        "config_check_exception": "Ошибка проверки config.json: {error}\n",
        "download_config": "Скачивание config.json: {url}\n",
        "download_config_attempt": "Скачивание config.json, попытка {attempt}/{total}...\n",
        "config_ready": "config.json скачан, UUID вставлен и применён.\n",
        "config_prepare_error": "Ошибка подготовки config.json: {error}\n",
        "soft_stop": "Отправляю sing-box мягкую остановку...\n",
        "ctrl_break_fallback": "sing-box не завершился после Ctrl+Break, пробую обычную остановку...\n",
        "ctrl_break_unavailable": "Ctrl+Break недоступен, пробую обычную остановку...\n",
        "disconnected": "Отключено",
        "connected": "Подключено",
        "busy_action": "выполняется действие",
        "tray_open": "Открыть",
        "connect": "Подключить",
        "disconnect": "Отключить",
        "exit": "Выход",
        "secure_connection": "Защищенное подключение",
        "connection_time": "Время подключения",
        "change_token_url": "Изменить токен или URL",
        "log": "Лог",
        "singbox_log": "Лог sing-box",
        "hide": "Скрыть",
        "vpn_data": "Данные VPN",
        "connection_data": "Данные подключения",
        "enter_uuid_url": "Введите UUID и URL сервера.",
        "uuid_token": "UUID токен",
        "server_url": "URL сервера",
        "invalid_uuid": "Введите корректный UUID.",
        "invalid_url": "Введите корректный URL сервера: https://",
        "save": "Сохранить",
        "cancel": "Отмена",
        "token_saved_log": "Токен и URL сервера сохранены.\n",
        "save_data_error": "Не удалось сохранить данные подключения: {error}\n",
        "new_data_next_connect": "Новые данные будут применены при следующем подключении.\n",
        "new_data_connect": "Новые данные будут использованы при подключении.\n",
        "token_required": "Требуется токен или URL",
        "checking_config": "Проверка конфига...",
        "initial_setup": "Первичная настройка...",
        "checking_vpn": "Проверка VPN...",
        "connected_ip": "Подключено · IP {ip}",
        "saved_token_loaded": "Сохранённый токен загружен.\n",
        "helper_installed": "Helper установлен.\n",
        "helper_missing": "Helper не установлен. При первом подключении будет один запрос пароля.\n",
        "vpn_ip": "IP VPN: {ip}",
        "vpn_ip_checking": "IP VPN: проверяется",
        "pystray_missing_mac": "pystray не установлен: значок в верхней панели недоступен.\n",
        "pystray_missing_win": "pystray не установлен: значок в трее недоступен.\n",
        "tray_icon_error": "Ошибка запуска значка в трее: {error}\n",
        "error": "Ошибка",
        "vpn_check_title": "Проверка VPN",
        "helper_install_required": "Требуется первичная установка helper. Сейчас macOS попросит пароль администратора один раз.\n",
        "helper_install_error": "Ошибка установки helper.\n",
        "helper_sudo_failed": "Helper установлен, но sudo -n проверка не прошла.\n",
        "helper_install_success": "Helper успешно установлен. Дальше пароль спрашиваться не должен.\n",
        "singbox_not_found": "Ошибка: не найден sing-box:\n{path}\n",
        "file_not_found": "Не найден файл:\n{path}",
        "config_ok_starting": "Проверка config.json успешна, запускаю VPN клиент...\n",
        "helper_install_failed_box": "Не удалось установить helper",
        "before_ip": "IP до подключения",
        "current_ip": "Текущий IP",
        "ip_unknown": "{label}: не удалось определить\n",
        "ip_unknown_error": "{label}: не удалось определить ({error})\n",
        "checking_active_vpn_ip": "Проверяю IP активного VPN через ident.me...\n",
        "checking_ident": "Проверка VPN через ident.me...\n",
        "checking_ident_timeout": "Проверяю внешний IP через ident.me до {timeout} секунд...\n",
        "service_stopped": "сервис sing-box остановлен",
        "process_stopped": "процесс sing-box остановлен",
        "ident_same_retry_mac": "ident.me вернул прежний IP: {ip}. Проверка {count}/{limit}...\n",
        "ident_same_retry_win": "Текущий IP пока прежний: {ip}. Проверяю ещё до {left} сек.\n",
        "external_ip_same": "внешний IP не изменился",
        "external_ip_same_after_start": "внешний IP не изменился после запуска sing-box",
        "vpn_ip_confirmed": "VPN IP подтверждён: {ip}\n",
        "ident_empty": "ident.me вернул пустой ответ",
        "ident_unavailable": "ident.me пока недоступен: {error}\n",
        "external_ip_failed": "не удалось получить внешний IP",
        "stop_after_failed_verify": "Останавливаю sing-box после неудачной проверки VPN...\n",
        "helper_stop_code": "helper stop завершился с кодом {code}\n",
        "stop_after_verify_error": "Не удалось остановить sing-box после проверки: {error}\n",
        "start_helper": "Запуск sing-box через helper...\n",
        "helper_start_error": "Ошибка запуска helper.\n",
        "singbox_started": "sing-box запущен.\n",
        "vpn_not_confirmed": "VPN не подтверждён: {reason}\n",
        "last_ident_ip": "Последний IP от ident.me: {ip}\n",
        "service_not_confirmed": "Сервис создан, но статус running не подтверждён.\n",
        "disconnecting": "Отключение...",
        "stop_helper": "\nОстановка sing-box через helper...\n",
        "stop_singbox": "\nОстановка sing-box...\n",
        "service_still_active": "Предупреждение: сервис всё ещё активен.\n",
        "singbox_stopped": "sing-box остановлен.\n",
        "exiting": "Выход...",
        "mac_only": "Этот клиент предназначен для macOS.",
        "retry_wait": "Жду паузу перед повторным запуском...\n",
        "start_attempt": "Запуск sing-box, попытка {attempt}/{total}...\n",
        "start_error": "Ошибка запуска sing-box: {error}\n",
        "started_check_ip": "sing-box запущен, проверяю внешний IP...\n",
        "started_exit_code": "sing-box завершился при старте с кодом {code}",
        "unknown_error": "неизвестная ошибка",
        "start_failed": "Не удалось запустить sing-box: {error}\n",
        "read_log_error": "\nОшибка чтения лога: {error}\n",
        "singbox_exit_code": "\nsing-box завершился с кодом {code}\n",
        "stop_error": "Ошибка остановки sing-box: {error}\n",
        "updates_disabled_log": "Проверка обновлений отключена.\n",
        "update_check_error": "Проверка обновлений недоступна: {error}\n",
        "update_disable": "Не показывать",
        "update_open": "Открыть",
        "update_available": "Доступна новая версия {version}.",
    },
    "en": {
        "config_download_error": "Could not download the config. Check the URL and credentials.",
        "vpn_verify_error": "Could not verify the VPN connection. Check the UUID.",
        "vpn_verify_error_win": "VPN started, but the external IP did not change. Check the UUID or server availability.",
        "vpn_start_error_win": "Windows could not create the VPN interface. Try connecting again.",
        "singbox_check": "Checking sing-box config...\n",
        "singbox_check_ok": "sing-box config check: OK\n",
        "singbox_check_error": "sing-box config check: error\n",
        "config_check_exception": "config.json check error: {error}\n",
        "download_config": "Downloading config.json: {url}\n",
        "download_config_attempt": "Downloading config.json, attempt {attempt}/{total}...\n",
        "config_ready": "config.json downloaded, UUID inserted and applied.\n",
        "config_prepare_error": "config.json preparation error: {error}\n",
        "soft_stop": "Sending graceful stop to sing-box...\n",
        "ctrl_break_fallback": "sing-box did not stop after Ctrl+Break, trying regular stop...\n",
        "ctrl_break_unavailable": "Ctrl+Break is unavailable, trying regular stop...\n",
        "disconnected": "Disconnected",
        "connected": "Connected",
        "busy_action": "busy",
        "tray_open": "Open",
        "connect": "Connect",
        "disconnect": "Disconnect",
        "exit": "Exit",
        "secure_connection": "Secure connection",
        "connection_time": "Connection time",
        "change_token_url": "Change token or URL",
        "log": "Log",
        "singbox_log": "sing-box log",
        "hide": "Hide",
        "vpn_data": "VPN data",
        "connection_data": "Connection data",
        "enter_uuid_url": "Enter UUID and server URL.",
        "uuid_token": "UUID token",
        "server_url": "Server URL",
        "invalid_uuid": "Enter a valid UUID.",
        "invalid_url": "Enter a valid server URL: https://",
        "save": "Save",
        "cancel": "Cancel",
        "token_saved_log": "Token and server URL saved.\n",
        "save_data_error": "Could not save connection data: {error}\n",
        "new_data_next_connect": "New data will be applied on the next connection.\n",
        "new_data_connect": "New data will be used when connecting.\n",
        "token_required": "Token or URL required",
        "checking_config": "Checking config...",
        "initial_setup": "Initial setup...",
        "checking_vpn": "Checking VPN...",
        "connected_ip": "Connected · IP {ip}",
        "saved_token_loaded": "Saved token loaded.\n",
        "helper_installed": "Helper installed.\n",
        "helper_missing": "Helper is not installed. macOS will ask for the administrator password once on the first connection.\n",
        "vpn_ip": "VPN IP: {ip}",
        "vpn_ip_checking": "VPN IP: checking",
        "pystray_missing_mac": "pystray is not installed: menu bar icon is unavailable.\n",
        "pystray_missing_win": "pystray is not installed: tray icon is unavailable.\n",
        "tray_icon_error": "Tray icon startup error: {error}\n",
        "error": "Error",
        "vpn_check_title": "VPN check",
        "helper_install_required": "Initial helper installation required. macOS will ask for the administrator password once.\n",
        "helper_install_error": "Helper installation error.\n",
        "helper_sudo_failed": "Helper installed, but sudo -n check failed.\n",
        "helper_install_success": "Helper installed successfully. Password should not be requested again.\n",
        "singbox_not_found": "Error: sing-box not found:\n{path}\n",
        "file_not_found": "File not found:\n{path}",
        "config_ok_starting": "config.json check passed, starting VPN client...\n",
        "helper_install_failed_box": "Could not install helper",
        "before_ip": "IP before connection",
        "current_ip": "Current IP",
        "ip_unknown": "{label}: could not determine\n",
        "ip_unknown_error": "{label}: could not determine ({error})\n",
        "checking_active_vpn_ip": "Checking active VPN IP through ident.me...\n",
        "checking_ident": "Checking VPN through ident.me...\n",
        "checking_ident_timeout": "Checking external IP through ident.me for up to {timeout} seconds...\n",
        "service_stopped": "sing-box service stopped",
        "process_stopped": "sing-box process stopped",
        "ident_same_retry_mac": "ident.me returned the previous IP: {ip}. Check {count}/{limit}...\n",
        "ident_same_retry_win": "Current IP is still unchanged: {ip}. Checking for {left} more sec.\n",
        "external_ip_same": "external IP did not change",
        "external_ip_same_after_start": "external IP did not change after sing-box startup",
        "vpn_ip_confirmed": "VPN IP confirmed: {ip}\n",
        "ident_empty": "ident.me returned an empty response",
        "ident_unavailable": "ident.me is currently unavailable: {error}\n",
        "external_ip_failed": "could not get external IP",
        "stop_after_failed_verify": "Stopping sing-box after failed VPN verification...\n",
        "helper_stop_code": "helper stop exited with code {code}\n",
        "stop_after_verify_error": "Could not stop sing-box after verification: {error}\n",
        "start_helper": "Starting sing-box through helper...\n",
        "helper_start_error": "Helper startup error.\n",
        "singbox_started": "sing-box started.\n",
        "vpn_not_confirmed": "VPN was not confirmed: {reason}\n",
        "last_ident_ip": "Last IP from ident.me: {ip}\n",
        "service_not_confirmed": "Service was created, but running status was not confirmed.\n",
        "disconnecting": "Disconnecting...",
        "stop_helper": "\nStopping sing-box through helper...\n",
        "stop_singbox": "\nStopping sing-box...\n",
        "service_still_active": "Warning: service is still active.\n",
        "singbox_stopped": "sing-box stopped.\n",
        "exiting": "Exiting...",
        "mac_only": "This client is intended for macOS.",
        "retry_wait": "Waiting before retry...\n",
        "start_attempt": "Starting sing-box, attempt {attempt}/{total}...\n",
        "start_error": "sing-box startup error: {error}\n",
        "started_check_ip": "sing-box started, checking external IP...\n",
        "started_exit_code": "sing-box exited during startup with code {code}",
        "unknown_error": "unknown error",
        "start_failed": "Could not start sing-box: {error}\n",
        "read_log_error": "\nLog read error: {error}\n",
        "singbox_exit_code": "\nsing-box exited with code {code}\n",
        "stop_error": "sing-box stop error: {error}\n",
        "updates_disabled_log": "Update checks disabled.\n",
        "update_check_error": "Update check is unavailable: {error}\n",
        "update_disable": "Hide",
        "update_open": "Open",
        "update_available": "New version {version} is available.",
    },
}


def tr(key: str, **kwargs) -> str:
    text = I18N.get(LANG, I18N["en"]).get(key, I18N["en"].get(key, key))
    return text.format(**kwargs) if kwargs else text

UUID_PLACEHOLDER = "__TYPE_UUID__"
SERVER_CONFIG_FILENAME = "config_universal.json"
CONFIG_DOWNLOAD_ERROR = tr("config_download_error")
VPN_VERIFY_ERROR = tr("vpn_verify_error_win")
VPN_START_ERROR = tr("vpn_start_error_win")
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
    if urlparse(url).scheme != "https":
        raise ValueError("Refusing to download config over a non-HTTPS URL.")
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
        log(tr("soft_stop"))
        if send_windows_ctrl_break(process):
            try:
                process.wait(timeout=timeout)
                return
            except subprocess.TimeoutExpired:
                log(tr("ctrl_break_fallback"))
        else:
            log(tr("ctrl_break_unavailable"))

    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def validate_singbox_config(config_path: Path, log_func) -> bool:
    try:
        log_func(tr("singbox_check"))
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
            log_func(tr("singbox_check_ok"))
            return True
        log_func(tr("singbox_check_error"))
        log_func(result.stdout + "\n")
        return False
    except Exception as e:
        log_func(tr("config_check_exception", error=e))
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
    log_func(tr("download_config", url=final_url))
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        tmp_path = None
        try:
            log_func(tr("download_config_attempt", attempt=attempt, total=DOWNLOAD_RETRIES))
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
            log_func(tr("config_ready"))
            return True
        except Exception as e:
            log_func(tr("config_prepare_error", error=e))
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            if attempt < DOWNLOAD_RETRIES:
                time.sleep(RETRY_DELAY)
    log_func(CONFIG_DOWNLOAD_ERROR + "\n")
    return False


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
