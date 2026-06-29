import os
import re
import sys
from pathlib import Path


VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def _version_candidates():
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        yield Path(getattr(sys, "_MEIPASS", executable.parent)) / "VERSION"
        yield executable.parent / "VERSION"
        yield executable.parent.parent / "Resources" / "VERSION"

    module = Path(__file__).resolve()
    for parent in module.parents:
        yield parent / "VERSION"


def get_app_version() -> str:
    runtime_version = os.environ.get("WORKVPN_APP_VERSION", "").strip()
    if VERSION_PATTERN.fullmatch(runtime_version):
        return runtime_version

    for path in _version_candidates():
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if VERSION_PATTERN.fullmatch(value):
            return value
    return "0.0.0"
