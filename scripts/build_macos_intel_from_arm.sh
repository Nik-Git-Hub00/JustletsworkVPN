#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "This script is only for building Intel macOS app from Apple Silicon via Rosetta." >&2
  echo "On an Intel Mac use ./scripts/build_macos.sh" >&2
  exit 64
fi

base_python="${PYTHON:-python3}"
venv_dir="venv-intel"
python_bin="${venv_dir}/bin/python"

if [[ ! -x "$python_bin" ]]; then
  arch -x86_64 "$base_python" - <<'PYVER'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required")
PYVER
  arch -x86_64 "$base_python" -m venv "$venv_dir"
fi

arch -x86_64 "$python_bin" -m pip install --upgrade pip
arch -x86_64 "$python_bin" -m pip install -r requirements.txt

if [[ ! -x runtime/macos-x64/sing-box ]]; then
  ./scripts/fetch_runtime_macos.sh amd64
fi

arch -x86_64 "$python_bin" -m PyInstaller --clean -y specs/macos_intel.spec

mkdir -p release
rm -f release/WorkVPN-macos-x64.zip
ditto -c -k --keepParent "dist/WorkVPN.app" "release/WorkVPN-macos-x64.zip"
echo "Release: release/WorkVPN-macos-x64.zip"
./scripts/package_macos_dmg.sh macos-x64
