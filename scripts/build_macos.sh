#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

case "$(uname -m)" in
  arm64)
    runtime_path="runtime/macos-arm64/sing-box"
    fetch_arch="arm64"
    spec_path="specs/macos_arm.spec"
    release_arch="macos-arm64"
    ;;
  x86_64)
    runtime_path="runtime/macos-x64/sing-box"
    fetch_arch="amd64"
    spec_path="specs/macos_intel.spec"
    release_arch="macos-x64"
    ;;
  *)
    echo "Unsupported macOS architecture: $(uname -m)" >&2
    exit 64
    ;;
esac

base_python="${PYTHON:-python3}"
venv_dir="venv"
python_bin="${venv_dir}/bin/python"

if [[ ! -x "$python_bin" ]]; then
  "$base_python" - <<'PYVER'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required")
PYVER
  "$base_python" -m venv "$venv_dir"
fi

"$python_bin" -m pip install --upgrade pip
"$python_bin" -m pip install -r requirements.txt

if [[ ! -x "$runtime_path" ]]; then
  ./scripts/fetch_runtime_macos.sh "$fetch_arch"
fi

"$python_bin" -m PyInstaller --clean -y "$spec_path"

mkdir -p release
rm -f "release/WorkVPN-${release_arch}.zip"
ditto -c -k --keepParent "dist/WorkVPN.app" "release/WorkVPN-${release_arch}.zip"
echo "Release: release/WorkVPN-${release_arch}.zip"
./scripts/package_macos_dmg.sh "$release_arch"
