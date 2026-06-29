import atexit
import platform
import sys
import threading
import time
import uuid
from urllib.parse import urlparse

from PySide6.QtCore import (
    QAbstractAnimation,
    QEvent,
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QColor, QFont, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .mac_backend import (
    APP_SUPPORT,
    APP_TITLE,
    BUNDLED_SING_BOX,
    CONFIG_DOWNLOAD_ERROR,
    CONFIG_URL_FILE,
    GREEN,
    HELPER_PATH,
    ORANGE,
    RED,
    SYSTEM_LOG,
    SYSTEM_SING_BOX,
    TOKEN_FILE,
    VPN_VERIFY_ERROR,
    VPN_VERIFY_HTTP_TIMEOUT,
    VPN_VERIFY_INTERVAL,
    VPN_VERIFY_SAME_IP_LIMIT,
    VPN_VERIFY_TIMEOUT,
    clean_log,
    create_tray_image,
    fetch_public_ip,
    helper_output,
    helper_ready,
    install_helper_command,
    launchd_is_running,
    pystray,
    resource_path,
    run_admin_shell,
    run_helper,
    tr,
    update_config_from_template,
)
from workvpn.update_check import check_latest_release, disable_update_checks, update_checks_disabled
from workvpn.version import get_app_version


APP_VERSION = get_app_version()
WINDOW_TITLE = f"{APP_TITLE} v{APP_VERSION}"


class UiBridge(QObject):
    append_log = Signal(str)
    status = Signal(str, str, str, bool, bool)
    timer_text = Signal(str)
    error = Signal(str, str)
    tray_action = Signal(str)
    finished_exit = Signal()
    update_available = Signal(object)


def pixmap_asset(filename: str) -> QPixmap:
    return QPixmap(str(resource_path(f"assets/{filename}")))


def icon_asset(filename: str) -> QIcon:
    return QIcon(str(resource_path(f"assets/{filename}")))


class ActionButton(QPushButton):
    def __init__(self, text, icon_file, danger=False, parent=None):
        super().__init__(text, parent)
        self.setObjectName("dangerButton" if danger else "actionButton")
        self.setIcon(icon_asset(icon_file))
        self.setIconSize(QSize(25, 25))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(50)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class PowerButton(QPushButton):
    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self.clicked.connect(callback)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setObjectName("powerButton")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.state = "disconnected"
        self.set_state("disconnected", True)

    def set_state(self, state: str, enabled: bool):
        self.state = state
        self.setEnabled(enabled)
        self.setIcon(icon_asset(f"power_button_{state}.png"))

    def set_diameter(self, diameter: int):
        self.setFixedSize(diameter, diameter)
        self.setIconSize(QSize(diameter, diameter))


class CredentialsDialog(QDialog):
    def __init__(self, token="", config_url="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("vpn_data"))
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setMinimumWidth(500)
        self.setMaximumWidth(640)
        self.setObjectName("credentialsDialog")
        self.result_token = None
        self.result_url = None

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(9)

        title = QLabel(tr("connection_data"))
        title.setObjectName("dialogTitle")
        root.addWidget(title)

        subtitle = QLabel(tr("enter_uuid_url"))
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)
        root.addSpacing(8)

        root.addWidget(self._field_label(tr("uuid_token")))
        self.token_edit = QLineEdit(token)
        self.token_edit.setObjectName("credentialField")
        self.token_edit.setClearButtonEnabled(True)
        root.addWidget(self.token_edit)

        root.addSpacing(5)
        root.addWidget(self._field_label(tr("server_url")))
        self.url_edit = QLineEdit(config_url)
        self.url_edit.setObjectName("credentialField")
        self.url_edit.setClearButtonEnabled(True)
        root.addWidget(self.url_edit)

        self.error_label = QLabel("")
        self.error_label.setObjectName("fieldError")
        self.error_label.setWordWrap(True)
        root.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        save = ActionButton(tr("save"), "ui_save.png")
        save.setObjectName("saveButton")
        cancel = ActionButton(tr("cancel"), "ui_cancel.png")
        save.clicked.connect(self.validate_and_accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        root.addLayout(buttons)

        self.token_edit.selectAll()
        self.token_edit.setFocus()
        self.adjustSize()
        self.setFixedSize(self.size())

    @staticmethod
    def _field_label(text):
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def changeEvent(self, event):
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.windowState()
            & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen)
        ):
            QTimer.singleShot(0, self.showNormal)

    def validate_and_accept(self):
        token = self.token_edit.text().strip()
        config_url = self.url_edit.text().strip()
        try:
            token = str(uuid.UUID(token))
        except ValueError:
            self.error_label.setText(tr("invalid_uuid"))
            return
        parsed = urlparse(config_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            self.error_label.setText(tr("invalid_url"))
            return
        self.result_token = token
        self.result_url = config_url
        self.accept()


class WorkVpnWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(QIcon(str(resource_path("assets/vpn_icon.icns"))))
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setFixedSize(self.initial_window_size())

        self.connection_state = "disconnected"
        self.client_uuid = self.load_saved_token()
        self.config_url = self.load_saved_config_url()
        self.tray_icon = None
        self.connected_since = None
        self.vpn_ip = None
        self.log_tail_running = False
        self.log_position = 0
        self.first_log_sync_done = False
        self.is_stopping = False
        self.is_exiting = False
        self.allow_close = False

        self.bridge = UiBridge()
        self.bridge.append_log.connect(self.write_log)
        self.bridge.status.connect(self.apply_status)
        self.bridge.error.connect(self.show_error)
        self.bridge.tray_action.connect(self.handle_tray_action)
        self.bridge.finished_exit.connect(QApplication.instance().quit)
        self.bridge.update_available.connect(self.show_update_banner)

        self.build_ui()
        self.bridge.timer_text.connect(self.timer_label.setText)
        self.apply_styles()
        self.install_shortcuts()
        self.create_tray()
        self.set_disconnected()

        self.timer_tick = QTimer(self)
        self.timer_tick.timeout.connect(self.update_timer)
        self.timer_tick.start(1000)

        QTimer.singleShot(250, self.request_token_on_start)
        QTimer.singleShot(1200, self.check_for_updates)
        self.log_safe(f"Bundled sing-box: {BUNDLED_SING_BOX}\n")
        self.log_safe(f"Helper: {HELPER_PATH}\n")
        if self.client_uuid:
            self.log_safe(tr("saved_token_loaded"))
        if helper_ready():
            self.log_safe(tr("helper_installed"))
            if launchd_is_running():
                self.set_connected()
                self.start_log_tail()
                threading.Thread(target=self.refresh_connected_ip, daemon=True).start()
        else:
            self.log_safe(tr("helper_missing"))

    def initial_window_size(self):
        screen = QApplication.primaryScreen().availableGeometry()
        width = min(max(440, round(screen.width() * 0.32)), 560, max(420, screen.width() - 48))
        height = min(max(680, round(screen.height() * 0.82)), 840, max(640, screen.height() - 48))
        return QSize(width, height)

    def build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(34, 24, 34, 30)
        outer.setSpacing(0)

        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.title_label = QLabel(APP_TITLE)
        self.title_label.setObjectName("appTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(tr("secure_connection"))
        self.subtitle_label.setObjectName("subtitle")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.subtitle_label)
        content_layout.addSpacing(10)

        self.update_banner = QFrame()
        self.update_banner.setObjectName("updateBanner")
        self.update_banner.hide()
        update_layout = QHBoxLayout(self.update_banner)
        update_layout.setContentsMargins(12, 8, 10, 8)
        update_layout.setSpacing(10)
        update_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.update_text = QLabel("")
        self.update_text.setObjectName("updateText")
        self.update_text.setWordWrap(True)
        self.update_open_btn = QPushButton(tr("update_open"))
        self.update_open_btn.setObjectName("updateOpen")
        self.update_disable_btn = QPushButton(tr("update_disable"))
        self.update_disable_btn.setObjectName("updateDisable")
        self.update_open_btn.clicked.connect(self.open_update_url)
        self.update_disable_btn.clicked.connect(self.disable_updates)
        update_layout.addWidget(self.update_text, 1, Qt.AlignmentFlag.AlignVCenter)
        update_layout.addWidget(self.update_open_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        update_layout.addWidget(self.update_disable_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        content_layout.addWidget(self.update_banner)
        content_layout.addSpacing(12)

        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_source = pixmap_asset("vpn_shield.png")
        content_layout.addWidget(self.logo_label, 0, Qt.AlignmentFlag.AlignCenter)
        content_layout.addStretch(2)

        self.time_caption = QLabel(tr("connection_time"))
        self.time_caption.setObjectName("timeCaption")
        self.time_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.time_caption)
        content_layout.addSpacing(4)

        self.timer_label = QLabel("00:00:00")
        self.timer_label.setObjectName("timer")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.timer_label)
        content_layout.addStretch(1)

        self.power_button = PowerButton(self.toggle_vpn)
        content_layout.addWidget(self.power_button, 0, Qt.AlignmentFlag.AlignCenter)
        content_layout.addSpacing(10)

        self.status_label = QLabel(tr("disconnected"))
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        content_layout.addWidget(self.status_label)
        content_layout.addStretch(1)
        outer.addWidget(self.content, 1)

        self.buttons = QWidget()
        buttons_layout = QVBoxLayout(self.buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(9)
        self.token_btn = ActionButton(tr("change_token_url"), "ui_token.png")
        self.log_btn = ActionButton(tr("log"), "ui_log.png")
        self.exit_btn = ActionButton(tr("exit"), "ui_exit.png", danger=True)
        self.token_btn.clicked.connect(self.change_token)
        self.log_btn.clicked.connect(lambda _checked=False: self.toggle_log_panel())
        self.exit_btn.clicked.connect(self.exit_app)
        buttons_layout.addWidget(self.token_btn)
        buttons_layout.addWidget(self.log_btn)
        buttons_layout.addWidget(self.exit_btn)
        outer.addWidget(self.buttons)

        self.log_panel = QFrame(central)
        self.log_panel.setObjectName("logPanel")
        self.log_panel.hide()
        log_shadow = QGraphicsDropShadowEffect(self.log_panel)
        log_shadow.setBlurRadius(28)
        log_shadow.setOffset(0, 6)
        log_shadow.setColor(QColor(0, 0, 0, 150))
        self.log_panel.setGraphicsEffect(log_shadow)
        log_layout = QVBoxLayout(self.log_panel)
        log_layout.setContentsMargins(0, 0, 0, 10)
        log_layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("logHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 8, 14, 8)
        header_title = QLabel(tr("singbox_log"))
        header_title.setObjectName("logTitle")
        hide = QPushButton(tr("hide"))
        hide.setObjectName("hideLog")
        hide.clicked.connect(lambda: self.toggle_log_panel(False))
        header_layout.addWidget(header_title)
        header_layout.addStretch()
        header_layout.addWidget(hide)
        log_layout.addWidget(header)
        self.log = QPlainTextEdit()
        self.log.setObjectName("logText")
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        log_layout.addWidget(self.log)

        self.log_animation = QPropertyAnimation(self.log_panel, b"geometry", self)
        self.log_animation.setDuration(220)
        self.log_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.log_animation.finished.connect(self.finish_log_animation)
        self.log_panel_visible = False
        self.update_responsive_sizes()
        self.position_log_panel()

    def apply_styles(self):
        self.setStyleSheet(
            """
            QWidget#central, QDialog#credentialsDialog { background: #061221; color: #eef6ff; }
            QLabel#appTitle { color: #eef6ff; font-weight: 700; }
            QLabel#subtitle, QLabel#dialogSubtitle { color: #8ea5c2; }
            QLabel#timeCaption { color: #8ea5c2; font-weight: 700; }
            QLabel#timer { color: #eef6ff; font-weight: 400; }
            QLabel#status { font-weight: 700; }
            QFrame#updateBanner { background: #0d2b45; border: 1px solid #2b75a8; border-radius: 8px; }
            QLabel#updateText { color: #d8efff; font-weight: 700; }
            QPushButton#updateOpen, QPushButton#updateDisable {
                color: #eef6ff; background: #15395a; border: 1px solid #3a7dad;
                border-radius: 6px; font-weight: 700; padding: 0 10px;
            }
            QPushButton#updateOpen:hover, QPushButton#updateDisable:hover { background: #1d4c76; }
            QPushButton#powerButton { border: none; background: transparent; padding: 0; }
            QPushButton#powerButton:disabled { background: transparent; }
            QPushButton#actionButton, QPushButton#dangerButton, QPushButton#saveButton {
                color: #eef6ff; background: #10213a; border: 1px solid #284867;
                border-radius: 7px; font-weight: 700; padding: 8px 18px;
            }
            QPushButton#actionButton:hover { background: #183252; border-color: #3b6389; }
            QPushButton#actionButton:pressed { background: #0c1a2d; }
            QPushButton#dangerButton { color: #ffe4ea; background: #4a1624; border-color: #9f2947; }
            QPushButton#dangerButton:hover { background: #6d1d32; border-color: #d3365c; }
            QPushButton#saveButton { background: #1266d6; border-color: #3b82f6; }
            QPushButton#saveButton:hover { background: #1d7cff; }
            QFrame#logPanel { background: #07111f; border: 1px solid #284867; border-radius: 8px; }
            QFrame#logHeader { background: #0d1c31; border: none; }
            QLabel#logTitle { color: #eef6ff; font-weight: 700; border: none; }
            QPushButton#hideLog { color: #8ea5c2; background: transparent; border: none; font-weight: 700; }
            QPushButton#hideLog:hover { color: #eef6ff; }
            QPlainTextEdit#logText {
                color: #d7e3f4; background: #030a14; border: none;
                padding: 8px; font-family: Menlo, Monaco, monospace;
            }
            QLabel#dialogTitle { color: #eef6ff; font-size: 20px; font-weight: 700; }
            QLabel#fieldLabel { color: #eef6ff; font-weight: 700; }
            QLabel#fieldError { color: #fb7185; min-height: 20px; }
            QLineEdit#credentialField {
                color: #eef6ff; background: #0b1a2d; border: 1px solid #284867;
                border-radius: 7px; padding: 11px 12px; selection-background-color: #2563eb;
            }
            QLineEdit#credentialField:focus { border-color: #3b82f6; }
            """
        )

    def install_shortcuts(self):
        self.minimize_shortcut = QShortcut(QKeySequence("Meta+M"), self)
        self.minimize_shortcut.activated.connect(self.showMinimized)
        self.quit_shortcut = QShortcut(QKeySequence("Meta+Q"), self)
        self.quit_shortcut.activated.connect(self.exit_app)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_responsive_sizes()
        self.position_log_panel()

    def update_responsive_sizes(self):
        h = max(self.height(), 680)
        w = max(self.width(), 440)
        title_size = max(32, min(48, round(w * 0.09)))
        subtitle_size = max(15, min(19, round(w * 0.034)))
        timer_size = max(34, min(46, round(w * 0.082)))
        logo_size = max(104, min(142, round(h * 0.16)))
        power_size = max(118, min(154, round(h * 0.18)))
        self.title_label.setFont(QFont("Helvetica", title_size, QFont.Weight.Bold))
        self.subtitle_label.setFont(QFont("Helvetica", subtitle_size))
        self.time_caption.setFont(QFont("Helvetica", max(14, min(17, round(w * 0.03))), QFont.Weight.Bold))
        self.timer_label.setFont(QFont("Helvetica", timer_size))
        self.status_label.setFont(QFont("Helvetica", max(14, min(17, round(w * 0.03))), QFont.Weight.Bold))
        self.logo_label.setPixmap(
            self.logo_source.scaled(
                logo_size, logo_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        self.logo_label.setFixedSize(logo_size, logo_size)
        self.power_button.set_diameter(power_size)
        button_height = max(48, min(58, round(h * 0.066)))
        icon_size = max(23, min(29, round(button_height * 0.48)))
        for button in (self.token_btn, self.log_btn, self.exit_btn):
            button.setMinimumHeight(button_height)
            button.setMaximumHeight(button_height)
            button.setIconSize(QSize(icon_size, icon_size))
            button.setFont(QFont("Helvetica", max(14, min(17, round(w * 0.03))), QFont.Weight.Bold))
        if hasattr(self, "update_text"):
            update_font = QFont("Helvetica", max(11, min(13, round(w * 0.024))), QFont.Weight.Bold)
            self.update_text.setFont(update_font)
            for button in (self.update_open_btn, self.update_disable_btn):
                button.setFixedHeight(max(30, min(34, round(w * 0.06))))
                button.setFont(QFont("Helvetica", max(10, min(12, round(w * 0.022))), QFont.Weight.Bold))

    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
        else:
            event.ignore()
            self.hide()

    def changeEvent(self, event):
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.windowState()
            & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen)
        ):
            QTimer.singleShot(0, self.showNormal)
        elif event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.raise_()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def handle_tray_action(self, action):
        if action == "show":
            self.show_window()
        elif action == "start":
            self.start_vpn()
        elif action == "stop":
            self.stop_vpn()
        elif action == "exit":
            self.exit_app()

    def create_tray(self):
        if pystray is None:
            self.log_safe(tr("pystray_missing_mac"))
            return
        menu = pystray.Menu(
            pystray.MenuItem(tr("tray_open"), lambda *_: self.bridge.tray_action.emit("show"), default=True),
            pystray.MenuItem(self.tray_vpn_ip_text, None, enabled=False, visible=self.tray_has_vpn_ip),
            pystray.MenuItem(tr("connect"), lambda *_: self.bridge.tray_action.emit("start"), enabled=self.tray_can_start),
            pystray.MenuItem(tr("disconnect"), lambda *_: self.bridge.tray_action.emit("stop"), enabled=self.tray_can_stop),
            pystray.MenuItem(tr("exit"), lambda *_: self.bridge.tray_action.emit("exit")),
        )
        self.tray_icon = pystray.Icon(
            APP_TITLE, create_tray_image("red"), f"{APP_TITLE} - {tr('disconnected').lower()}", menu
        )
        try:
            self.tray_icon.run_detached()
        except Exception:
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def tray_can_start(self, _=None):
        return self.connection_state == "disconnected" and not self.is_exiting

    def tray_can_stop(self, _=None):
        return self.connection_state == "connected" and not self.is_exiting

    def tray_has_vpn_ip(self, _=None):
        return self.connection_state == "connected" and bool(self.vpn_ip) and not self.is_exiting

    def tray_vpn_ip_text(self, _=None):
        return tr("vpn_ip", ip=self.vpn_ip) if self.vpn_ip else tr("vpn_ip_checking")

    def update_tray_icon(self, color):
        if not self.tray_icon:
            return
        self.tray_icon.icon = create_tray_image(color)
        titles = {
            "green": f"{APP_TITLE} - {tr('connected').lower()}",
            "orange": f"{APP_TITLE} - {tr('busy_action')}",
            "red": f"{APP_TITLE} - {tr('disconnected').lower()}",
        }
        self.tray_icon.title = titles.get(color, APP_TITLE)
        try:
            self.tray_icon.update_menu()
        except Exception:
            pass

    def log_safe(self, text):
        self.bridge.append_log.emit(text)

    def write_log(self, text):
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)

    def toggle_log_panel(self, force=None):
        self.log_panel_visible = not self.log_panel_visible if force is None else bool(force)
        closed, opened = self.log_panel_geometries()
        self.log_animation.stop()
        if self.log_panel_visible:
            self.log_panel.setGeometry(closed)
            self.log_panel.show()
            self.log_panel.raise_()
            self.log_animation.setStartValue(closed)
            self.log_animation.setEndValue(opened)
        else:
            self.log_animation.setStartValue(self.log_panel.geometry())
            self.log_animation.setEndValue(closed)
        self.log_animation.start()

    def log_panel_geometries(self):
        margin_x = 34
        margin_bottom = 26
        desired_height = min(280, max(220, round(self.height() * 0.30)))
        status_bottom = self.status_label.mapTo(
            self.centralWidget(), QPoint(0, self.status_label.height())
        ).y()
        opened_top = max(
            self.height() - margin_bottom - desired_height,
            status_bottom + 16,
        )
        panel_height = max(1, self.height() - margin_bottom - opened_top)
        panel_width = max(320, self.width() - margin_x * 2)
        closed = QRect(margin_x, self.height() - margin_bottom, panel_width, 0)
        opened = QRect(
            margin_x,
            opened_top,
            panel_width,
            panel_height,
        )
        return closed, opened

    def position_log_panel(self):
        if not hasattr(self, "log_panel") or self.log_animation.state() == QAbstractAnimation.State.Running:
            return
        closed, opened = self.log_panel_geometries()
        self.log_panel.setGeometry(opened if self.log_panel_visible else closed)

    def finish_log_animation(self):
        if not self.log_panel_visible:
            self.log_panel.hide()


    def check_for_updates(self):
        if self.is_exiting or update_checks_disabled(APP_SUPPORT):
            return

        def worker():
            try:
                update = check_latest_release()
            except Exception as error:
                self.log_safe(tr("update_check_error", error=error))
                return
            if update and not self.is_exiting:
                self.bridge.update_available.emit(update)

        threading.Thread(target=worker, daemon=True).start()

    def show_update_banner(self, update):
        self.available_update = update
        self.update_text.setText(tr("update_available", version=update.version))
        self.update_banner.show()
        self.update_responsive_sizes()
        self.position_log_panel()

    def open_update_url(self):
        update = getattr(self, "available_update", None)
        if not update:
            return
        QDesktopServices.openUrl(QUrl(update.download_url or update.release_url))

    def disable_updates(self):
        disable_update_checks(APP_SUPPORT)
        self.update_banner.hide()
        self.write_log(tr("updates_disabled_log"))
        self.update_responsive_sizes()
        self.position_log_panel()

    def load_saved_token(self):
        try:
            token = TOKEN_FILE.read_text(encoding="utf-8").strip()
            return str(uuid.UUID(token)) if token else None
        except Exception:
            return None

    def load_saved_config_url(self):
        try:
            url = CONFIG_URL_FILE.read_text(encoding="utf-8").strip()
            parsed = urlparse(url)
            return url if parsed.scheme == "https" and parsed.netloc and not parsed.query and not parsed.fragment else None
        except Exception:
            return None

    def prompt_for_token(self, force=False):
        if self.client_uuid and self.config_url and not force:
            return True
        dialog = CredentialsDialog(self.client_uuid or "", self.config_url or "", self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        self.client_uuid = dialog.result_token
        self.config_url = dialog.result_url
        try:
            TOKEN_FILE.write_text(self.client_uuid + "\n", encoding="utf-8")
            CONFIG_URL_FILE.write_text(self.config_url + "\n", encoding="utf-8")
            self.write_log(tr("token_saved_log"))
        except Exception as error:
            self.write_log(tr("save_data_error", error=error))
        return True

    def request_token_on_start(self):
        if not self.client_uuid or not self.config_url:
            if not self.prompt_for_token():
                self.set_status("disconnected", tr("token_required"), ORANGE, "orange", True, True)

    def change_token(self):
        if self.is_exiting:
            return
        if self.prompt_for_token(force=True):
            self.write_log(tr("new_data_next_connect") if self.connection_state == "connected" else tr("new_data_connect"))

    def toggle_vpn(self):
        if self.connection_state == "connected":
            self.stop_vpn()
        elif self.connection_state == "disconnected":
            self.start_vpn()

    def set_status(self, state, text, color, tray_color, power_enabled, exit_enabled):
        self.bridge.status.emit(state, text, color, power_enabled, exit_enabled)
        self.update_tray_icon(tray_color)

    def apply_status(self, state, text, color, power_enabled, exit_enabled):
        self.connection_state = state
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")
        power_state = "connected" if state == "connected" else "busy" if state == "busy" else "disconnected"
        self.power_button.set_state(power_state, power_enabled)
        self.token_btn.setEnabled(not self.is_exiting)
        self.log_btn.setEnabled(not self.is_exiting)
        self.exit_btn.setEnabled(exit_enabled)

    def set_disconnected(self):
        self.is_stopping = False
        self.connected_since = None
        self.vpn_ip = None
        self.bridge.timer_text.emit("00:00:00")
        self.set_status("disconnected", tr("disconnected"), RED, "red", True, True)

    def set_connected(self, vpn_ip=None):
        self.is_stopping = False
        self.vpn_ip = vpn_ip or self.vpn_ip
        text = tr("connected_ip", ip=self.vpn_ip) if self.vpn_ip else tr("connected")
        self.set_status("connected", text, GREEN, "green", True, True)
        if not self.connected_since:
            self.connected_since = time.time()

    def update_timer(self):
        if self.connection_state != "connected" or not self.connected_since:
            return
        elapsed = max(0, int(time.time() - self.connected_since))
        self.timer_label.setText(f"{elapsed // 3600:02d}:{(elapsed % 3600) // 60:02d}:{elapsed % 60:02d}")

    def start_vpn(self):
        if self.connection_state != "disconnected" or self.is_exiting:
            return
        if not self.prompt_for_token():
            self.set_status("disconnected", tr("token_required"), ORANGE, "orange", True, True)
            return
        self.set_status("busy", tr("checking_config"), ORANGE, "orange", False, True)
        threading.Thread(target=self.prepare_and_start_vpn, daemon=True).start()

    def prepare_and_start_vpn(self):
        if not BUNDLED_SING_BOX.exists() and not SYSTEM_SING_BOX.exists():
            self.log_safe(tr("singbox_not_found", path=BUNDLED_SING_BOX))
            self.set_disconnected()
            return
        before_ip = self.get_public_ip_for_log(tr("before_ip"))
        if not update_config_from_template(self.log_safe, self.client_uuid, self.config_url):
            self.set_disconnected()
            self.bridge.error.emit(tr("error"), CONFIG_DOWNLOAD_ERROR)
            return
        self.log_safe(tr("config_ok_starting"))
        if not helper_ready():
            self.set_status("busy", tr("initial_setup"), ORANGE, "orange", False, False)
            if not self.install_helper_if_needed():
                self.set_disconnected()
                self.bridge.error.emit(tr("error"), tr("helper_install_failed_box"))
                return
        self.launch_singbox_helper(before_ip)

    def install_helper_if_needed(self):
        if helper_ready():
            return True
        self.log_safe(tr("helper_install_required"))
        result = run_admin_shell(install_helper_command())
        if result.returncode != 0:
            self.log_safe(tr("helper_install_error"))
            self.log_safe((result.stderr or "") + (result.stdout or ""))
            return False
        time.sleep(0.5)
        if not helper_ready():
            self.log_safe(tr("helper_sudo_failed"))
            return False
        self.log_safe(tr("helper_install_success"))
        return True

    def get_public_ip_for_log(self, label):
        try:
            ip = fetch_public_ip()
            if ip:
                self.log_safe(f"{label}: {ip}\n")
                return ip
            self.log_safe(tr("ip_unknown", label=label))
        except Exception as error:
            self.log_safe(tr("ip_unknown_error", label=label, error=error))
        return None

    def refresh_connected_ip(self):
        self.log_safe(tr("checking_active_vpn_ip"))
        ip = self.get_public_ip_for_log(tr("current_ip"))
        if ip and self.connection_state == "connected":
            self.set_connected(ip)

    def verify_vpn_connection(self, before_ip):
        self.set_status("busy", tr("checking_vpn"), ORANGE, "orange", False, True)
        self.log_safe(tr("checking_ident"))
        deadline = time.time() + VPN_VERIFY_TIMEOUT
        last_ip = None
        last_error = None
        same_ip_count = 0
        while time.time() < deadline:
            if not launchd_is_running():
                return False, None, tr("service_stopped")
            try:
                ip = fetch_public_ip(timeout=VPN_VERIFY_HTTP_TIMEOUT)
                if ip:
                    last_ip = ip
                    if before_ip and ip == before_ip:
                        same_ip_count += 1
                        self.log_safe(tr("ident_same_retry_mac", ip=ip, count=same_ip_count, limit=VPN_VERIFY_SAME_IP_LIMIT))
                        if same_ip_count >= VPN_VERIFY_SAME_IP_LIMIT:
                            return False, ip, tr("external_ip_same")
                    else:
                        self.log_safe(tr("vpn_ip_confirmed", ip=ip))
                        return True, ip, None
                else:
                    last_error = tr("ident_empty")
            except Exception as error:
                last_error = str(error)
                self.log_safe(tr("ident_unavailable", error=error))
            time.sleep(VPN_VERIFY_INTERVAL)
        return False, last_ip, last_error or tr("external_ip_failed")

    def launch_singbox_helper(self, before_ip=None):
        self.log_safe(tr("start_helper"))
        self.log_position = 0
        self.first_log_sync_done = False
        self.start_log_tail()
        result = run_helper("start")
        if result.returncode != 0:
            self.log_safe(tr("helper_start_error"))
            self.log_safe((result.stderr or "") + (result.stdout or ""))
            self.set_disconnected()
            return
        for _ in range(12):
            time.sleep(0.5)
            if launchd_is_running():
                self.log_safe(tr("singbox_started"))
                ok, vpn_ip, reason = self.verify_vpn_connection(before_ip)
                if ok:
                    self.set_connected(vpn_ip)
                    return
                self.log_safe(tr("vpn_not_confirmed", reason=reason))
                self.stop_helper_after_failed_verify()
                self.set_disconnected()
                self.bridge.error.emit(tr("error"), VPN_VERIFY_ERROR)
                return
        self.log_safe(tr("service_not_confirmed"))
        self.set_disconnected()
        self.bridge.error.emit(tr("error"), VPN_VERIFY_ERROR)

    def stop_helper_after_failed_verify(self):
        self.log_safe(tr("stop_after_failed_verify"))
        try:
            result = run_helper("stop") if helper_ready() else run_admin_shell("launchctl stop system/WorkVPN || true")
            output = helper_output(result)
            if output:
                self.log_safe(output + "\n")
        except Exception as error:
            self.log_safe(tr("stop_after_verify_error", error=error))

    def start_log_tail(self):
        if self.log_tail_running:
            return
        self.log_tail_running = True
        threading.Thread(target=self.tail_log_loop, daemon=True).start()

    def tail_log_loop(self):
        while self.log_tail_running:
            try:
                if SYSTEM_LOG.exists():
                    with SYSTEM_LOG.open("r", encoding="utf-8", errors="replace") as stream:
                        if not self.first_log_sync_done:
                            stream.seek(0, 2)
                            self.log_position = stream.tell()
                            self.first_log_sync_done = True
                        stream.seek(self.log_position)
                        lines = stream.readlines()
                        self.log_position = stream.tell()
                    for line in lines:
                        self.log_safe(clean_log(line))
            except Exception:
                pass
            time.sleep(0.5)

    def stop_vpn(self):
        if self.is_stopping or self.connection_state != "connected" or self.is_exiting:
            return
        self.is_stopping = True
        self.set_status("busy", tr("disconnecting"), ORANGE, "orange", False, True)
        threading.Thread(target=self.stop_vpn_worker, daemon=True).start()

    def stop_vpn_worker(self):
        self.log_safe(tr("stop_helper"))
        result = run_helper("stop") if helper_ready() else run_admin_shell("launchctl stop system/WorkVPN || true")
        output = helper_output(result)
        if output:
            self.log_safe(output + "\n")
        time.sleep(1)
        if launchd_is_running():
            self.log_safe(tr("service_still_active"))
            self.set_connected()
            return
        self.log_safe(tr("singbox_stopped"))
        self.set_disconnected()

    def show_error(self, title, message):
        QMessageBox.critical(self, title, message)

    def cleanup_on_exit(self):
        try:
            if helper_ready():
                run_helper("stop")
        except Exception:
            pass

    def exit_app(self):
        if self.is_exiting:
            return
        self.is_exiting = True
        self.set_status("busy", tr("exiting"), ORANGE, "orange", False, False)

        def worker():
            try:
                if launchd_is_running():
                    result = run_helper("stop") if helper_ready() else run_admin_shell("launchctl stop system/WorkVPN || true")
                    output = helper_output(result)
                    if output:
                        self.log_safe(output + "\n")
            finally:
                self.log_tail_running = False
                if self.tray_icon:
                    self.tray_icon.stop()
                self.allow_close = True
                self.bridge.finished_exit.emit()

        threading.Thread(target=worker, daemon=True).start()


def main():
    if platform.system() != "Darwin":
        raise SystemExit(tr("mac_only"))
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationDisplayName(APP_TITLE)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(resource_path("assets/vpn_icon.icns"))))
    window = WorkVpnWindow()
    app.applicationStateChanged.connect(
        lambda state: window.show_window()
        if state == Qt.ApplicationState.ApplicationActive and not window.isVisible() and not window.is_exiting
        else None
    )
    atexit.register(window.cleanup_on_exit)
    window.show()
    sys.exit(app.exec())
