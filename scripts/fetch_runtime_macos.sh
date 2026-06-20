#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
VERSION="${SING_BOX_VERSION:-1.13.13}"
ARCH="${1:-all}"
BASE_URL="https://github.com/SagerNet/sing-box/releases/download/v${VERSION}"
TMP_DIR="${TMPDIR:-/tmp}/workvpn-sing-box-${VERSION}"

fetch_one() {
  local arch="$1"
  local target_dir="$2"
  local archive_name="sing-box-${VERSION}-darwin-${arch}.tar.gz"
  local url="${BASE_URL}/${archive_name}"
  local work="${TMP_DIR}/darwin-${arch}"

  mkdir -p "$work" "$target_dir"
  echo "Downloading ${url}"
  curl -L -o "${work}/${archive_name}" "$url"
  rm -rf "${work}/extract"
  mkdir -p "${work}/extract"
  tar -xzf "${work}/${archive_name}" -C "${work}/extract"
  local src_dir="${work}/extract/sing-box-${VERSION}-darwin-${arch}"
  if [[ ! -d "$src_dir" ]]; then
    src_dir="$(find "${work}/extract" -maxdepth 1 -type d -name 'sing-box-*' | head -n 1)"
  fi
  cp "${src_dir}/sing-box" "${target_dir}/sing-box"
  chmod +x "${target_dir}/sing-box"
  [[ -f "${src_dir}/LICENSE" ]] && cp "${src_dir}/LICENSE" "${target_dir}/LICENSE"
}

case "$ARCH" in
  native)
    case "$(uname -m)" in
      arm64) fetch_one arm64 runtime/macos-arm64 ;;
      x86_64) fetch_one amd64 runtime/macos-x64 ;;
      *) echo "Unsupported macOS architecture: $(uname -m)" >&2; exit 64 ;;
    esac
    ;;
  arm64) fetch_one arm64 runtime/macos-arm64 ;;
  amd64|x64|x86_64) fetch_one amd64 runtime/macos-x64 ;;
  all) fetch_one arm64 runtime/macos-arm64; fetch_one amd64 runtime/macos-x64 ;;
  *) echo "Usage: $0 [native|arm64|amd64|all]" >&2; exit 64 ;;
esac
