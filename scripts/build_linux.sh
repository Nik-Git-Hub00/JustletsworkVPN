#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

case "$(uname -m)" in
  x86_64|amd64)
    runtime_path="runtime/linux-amd64/sing-box"
    fetch_arch="amd64"
    release_arch="linux-amd64"
    ;;
  aarch64|arm64)
    runtime_path="runtime/linux-arm64/sing-box"
    fetch_arch="arm64"
    release_arch="linux-arm64"
    ;;
  *)
    echo "Unsupported Linux architecture: $(uname -m)" >&2
    exit 64
    ;;
esac

base_python="${PYTHON:-python3}"
venv_dir=".venv/${release_arch}"
python_bin="${venv_dir}/bin/python"

"$base_python" - <<'PYVER'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required")
PYVER

create_venv() {
  local log_file="/tmp/workvpn-venv-error.log"
  if "$base_python" -m venv "$venv_dir" 2>"$log_file"; then
    return 0
  fi

  if grep -qi "ensurepip" "$log_file" && command -v apt-get >/dev/null 2>&1; then
    echo "python3-venv is missing. Installing it with apt-get..."
    if [[ "$(id -u)" -eq 0 ]]; then
      apt-get update
      apt-get install -y python3-venv
    else
      sudo apt-get update
      sudo apt-get install -y python3-venv
    fi
    "$base_python" -m venv "$venv_dir"
    return 0
  fi

  cat "$log_file" >&2
  echo >&2
  echo "Could not create Python virtualenv." >&2
  echo "Install the venv package for your distro first." >&2
  echo "Debian/Ubuntu: sudo apt-get install python3-venv" >&2
  exit 1
}

if [[ ! -x "$python_bin" ]]; then
  rm -rf "$venv_dir"
  create_venv
fi

"$python_bin" - <<'PYVER'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required in the virtual environment")
PYVER

venv_arch="$("$python_bin" -c 'import platform; print(platform.machine().lower())')"
case "${release_arch}:${venv_arch}" in
  linux-amd64:x86_64|linux-amd64:amd64|linux-arm64:aarch64|linux-arm64:arm64) ;;
  *)
    echo "Virtual environment architecture mismatch: expected ${release_arch#linux-}, found $venv_arch" >&2
    echo "Remove $venv_dir and run the build again." >&2
    exit 64
    ;;
esac

"$python_bin" -m pip install --upgrade pip
"$python_bin" -m pip install -r requirements.txt

runtime_dir="runtime/${release_arch}"
if [[ ! -x "$runtime_path" || ! -f "${runtime_dir}/libcronet.so" ]]; then
  ./scripts/fetch_runtime_linux.sh "$fetch_arch"
fi

"$python_bin" -m PyInstaller --clean -y "specs/linux.spec"

package_dir="release/WorkVPN-${release_arch}"
rm -rf "$package_dir"
mkdir -p "$package_dir"
cp "dist/workvpn" "$package_dir/workvpn"
cp "$runtime_path" "$package_dir/sing-box"
chmod +x "$package_dir/workvpn" "$package_dir/sing-box"
if [[ -f "runtime/${release_arch}/libcronet.so" ]]; then
  cp "runtime/${release_arch}/libcronet.so" "$package_dir/libcronet.so"
fi
if [[ -f "runtime/${release_arch}/LICENSE" ]]; then
  cp "runtime/${release_arch}/LICENSE" "$package_dir/LICENSE.sing-box"
fi
mkdir -p release
rm -f "release/WorkVPN-${release_arch}.tar.gz"
tar -C release -czf "release/WorkVPN-${release_arch}.tar.gz" "WorkVPN-${release_arch}"
echo "Release: release/WorkVPN-${release_arch}.tar.gz"
