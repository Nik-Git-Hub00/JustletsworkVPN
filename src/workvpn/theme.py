import json
from pathlib import Path


DARK = "dark"
LIGHT = "light"
SETTINGS_FILENAME = "theme_settings.json"

LIGHT_STATUS_COLORS = {
    "#14b8a6": "#087f73",
    "#fb7185": "#c93452",
    "#f59e0b": "#9a5b00",
}


def load_theme(app_support: Path) -> str:
    try:
        data = json.loads((app_support / SETTINGS_FILENAME).read_text(encoding="utf-8"))
        if data.get("theme") == LIGHT:
            return LIGHT
    except (OSError, ValueError, TypeError):
        pass
    return DARK


def save_theme(app_support: Path, theme: str) -> None:
    app_support.mkdir(parents=True, exist_ok=True)
    path = app_support / SETTINGS_FILENAME
    path.write_text(
        json.dumps({"theme": LIGHT if theme == LIGHT else DARK}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def status_color(theme: str, color: str) -> str:
    if theme == LIGHT:
        return LIGHT_STATUS_COLORS.get(color.lower(), color)
    return color


def style_sheet(theme: str) -> str:
    return LIGHT_STYLE if theme == LIGHT else DARK_STYLE


DARK_STYLE = """
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
QPushButton#themeToggle {
    background: #10213a; border: 1px solid #284867; border-radius: 8px; padding: 5px;
}
QPushButton#themeToggle:hover { background: #183252; border-color: #3b6389; }
QPushButton#themeToggle:pressed { background: #0c1a2d; }
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


LIGHT_STYLE = """
QWidget#central, QDialog#credentialsDialog { background: #dfe7ef; color: #172033; }
QLabel#appTitle { color: #10233b; font-weight: 700; }
QLabel#subtitle, QLabel#dialogSubtitle { color: #5f7692; }
QLabel#timeCaption { color: #526b88; font-weight: 700; }
QLabel#timer { color: #10233b; font-weight: 400; }
QLabel#status { font-weight: 700; }
QFrame#updateBanner { background: #d3e4f1; border: 1px solid #79a9cf; border-radius: 8px; }
QLabel#updateText { color: #173a58; font-weight: 700; }
QPushButton#updateOpen, QPushButton#updateDisable {
    color: #17324d; background: #e8eef4; border: 1px solid #8eb2d0;
    border-radius: 6px; font-weight: 700; padding: 0 10px;
}
QPushButton#updateOpen:hover, QPushButton#updateDisable:hover { background: #d2e0eb; }
QPushButton#themeToggle {
    background: #e8eef4; border: 1px solid #a7bdd2; border-radius: 8px; padding: 5px;
}
QPushButton#themeToggle:hover { background: #d8e6f2; border-color: #7f9fbc; }
QPushButton#themeToggle:pressed { background: #cbddea; }
QPushButton#powerButton { border: none; background: transparent; padding: 0; }
QPushButton#powerButton:disabled { background: transparent; }
QPushButton#actionButton, QPushButton#dangerButton, QPushButton#saveButton {
    color: #172033; background: #e8eef4; border: 1px solid #a7bdd2;
    border-radius: 7px; font-weight: 700; padding: 8px 18px;
}
QPushButton#actionButton:hover { background: #d8e6f2; border-color: #7f9fbc; }
QPushButton#actionButton:pressed { background: #cbddea; }
QPushButton#dangerButton { color: #172033; background: #e3a5b4; border-color: #c93f62; }
QPushButton#dangerButton:hover { background: #d991a3; border-color: #b92f53; }
QPushButton#saveButton { color: #ffffff; background: #1266d6; border-color: #2f7bed; }
QPushButton#saveButton:hover { background: #1d7cff; }
QFrame#logPanel { background: #e6edf4; border: 1px solid #9bb4cb; border-radius: 8px; }
QFrame#logHeader { background: #d5e0ea; border: none; }
QLabel#logTitle { color: #172033; font-weight: 700; border: none; }
QPushButton#hideLog { color: #526b88; background: transparent; border: none; font-weight: 700; }
QPushButton#hideLog:hover { color: #10233b; }
QPlainTextEdit#logText {
    color: #172033; background: #edf2f6; border: none;
    padding: 8px; font-family: Menlo, Monaco, monospace;
}
QLabel#dialogTitle { color: #10233b; font-size: 20px; font-weight: 700; }
QLabel#fieldLabel { color: #172033; font-weight: 700; }
QLabel#fieldError { color: #c93452; min-height: 20px; }
QLineEdit#credentialField {
    color: #172033; background: #edf2f6; border: 1px solid #a7bdd2;
    border-radius: 7px; padding: 11px 12px; selection-background-color: #3b82f6;
}
QLineEdit#credentialField:focus { border-color: #2879d0; }
"""
