#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

usage() {
  cat >&2 <<'EOF'
Usage: ./scripts/build_macos.sh [native|arm64|x64]

  native  Build for the current Mac architecture (default).
  arm64   Build for Apple Silicon.
  x64     Build for Intel. On Apple Silicon this uses Rosetta.
EOF
}

requested_arch="${1:-native}"
host_arch="$(uname -m)"

if (( $# > 1 )); then
  usage
  exit 64
fi

case "$requested_arch" in
  native)
    case "$host_arch" in
      arm64) target_arch="arm64" ;;
      x86_64) target_arch="x64" ;;
      *) echo "Unsupported macOS architecture: $host_arch" >&2; exit 64 ;;
    esac
    ;;
  arm64|aarch64) target_arch="arm64" ;;
  x64|amd64|x86_64|intel) target_arch="x64" ;;
  -h|--help) usage; exit 0 ;;
  *) usage; exit 64 ;;
esac

use_rosetta=false
case "${host_arch}:${target_arch}" in
  arm64:arm64|x86_64:x64) ;;
  arm64:x64) use_rosetta=true ;;
  x86_64:arm64)
    echo "An Intel Mac cannot build the Apple Silicon app with PyInstaller." >&2
    exit 64
    ;;
  *)
    echo "Unsupported host/target combination: ${host_arch} -> ${target_arch}" >&2
    exit 64
    ;;
esac

if [[ "$target_arch" == "arm64" ]]; then
  runtime_path="runtime/macos-arm64/sing-box"
  fetch_arch="arm64"
  spec_path="specs/macos_arm.spec"
  release_arch="macos-arm64"
else
  runtime_path="runtime/macos-x64/sing-box"
  fetch_arch="amd64"
  spec_path="specs/macos_intel.spec"
  release_arch="macos-x64"
fi

run_target() {
  if [[ "$use_rosetta" == true ]]; then
    arch -x86_64 "$@"
  else
    "$@"
  fi
}

if [[ "$use_rosetta" == true ]] && ! arch -x86_64 /usr/bin/true 2>/dev/null; then
  echo "Rosetta is required for an Intel build on Apple Silicon." >&2
  echo "Install it with: softwareupdate --install-rosetta --agree-to-license" >&2
  exit 69
fi

app_version="${APP_VERSION:-$(head -n 1 VERSION | tr -d '[:space:]')}"
if [[ ! "$app_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid application version: $app_version" >&2
  exit 64
fi
export APP_VERSION="$app_version"
export APP_UPDATE_REPO="${APP_UPDATE_REPO:-${GITHUB_REPOSITORY:-}}"

echo "Building WorkVPN v$APP_VERSION for $release_arch"
[[ -n "$APP_UPDATE_REPO" ]] && echo "Update repository: $APP_UPDATE_REPO"

base_python="${PYTHON:-python3}"
venv_dir=".venv/macos-${target_arch}"
python_bin="${venv_dir}/bin/python"

run_target "$base_python" - <<'PYVER'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required")
PYVER

python_arch="$(run_target "$base_python" -c 'import platform; print(platform.machine().lower())')"
case "${target_arch}:${python_arch}" in
  arm64:arm64|x64:x86_64|x64:amd64) ;;
  *)
    echo "Selected target $target_arch requires matching Python, found: $python_arch" >&2
    exit 64
    ;;
esac

if [[ ! -x "$python_bin" ]]; then
  mkdir -p "$(dirname "$venv_dir")"
  run_target "$base_python" -m venv "$venv_dir"
fi

venv_arch="$(run_target "$python_bin" -c 'import platform; print(platform.machine().lower())')"
if [[ "$venv_arch" != "$python_arch" ]]; then
  echo "Virtual environment architecture mismatch: expected $python_arch, found $venv_arch" >&2
  echo "Remove $venv_dir and run the build again." >&2
  exit 64
fi

run_target "$python_bin" -m pip install --upgrade pip
run_target "$python_bin" -m pip install -r requirements.txt

if [[ ! -x "$runtime_path" ]]; then
  ./scripts/fetch_runtime_macos.sh "$fetch_arch"
fi

run_target "$python_bin" -m PyInstaller --clean -y "$spec_path"

mkdir -p release
rm -f "release/WorkVPN-${release_arch}.zip"
ditto -c -k --keepParent "dist/WorkVPN.app" "release/WorkVPN-${release_arch}.zip"
echo "Release: release/WorkVPN-${release_arch}.zip"
./scripts/package_macos_dmg.sh "$release_arch"
