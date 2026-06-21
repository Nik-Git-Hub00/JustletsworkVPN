#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
VERSION="${SING_BOX_VERSION:-1.13.13}"
ARCH="${1:-native}"
BASE_URL="https://github.com/SagerNet/sing-box/releases/download/v${VERSION}"
TMP_DIR="${TMPDIR:-/tmp}/workvpn-sing-box-${VERSION}"

fetch_one() {
  local arch="$1"
  local target_dir="$2"
  local archive_name="sing-box-${VERSION}-linux-${arch}.tar.gz"
  local url="${BASE_URL}/${archive_name}"
  local work="${TMP_DIR}/linux-${arch}"

  mkdir -p "$work" "$target_dir"
  echo "Downloading ${url}"
  curl -L -o "${work}/${archive_name}" "$url"
  rm -rf "${work}/extract"
  mkdir -p "${work}/extract"
  tar -xzf "${work}/${archive_name}" -C "${work}/extract"
  local src_dir="${work}/extract/sing-box-${VERSION}-linux-${arch}"
  if [[ ! -d "$src_dir" ]]; then
    src_dir="$(find "${work}/extract" -maxdepth 1 -type d -name 'sing-box-*' | head -n 1)"
  fi
  cp "${src_dir}/sing-box" "${target_dir}/sing-box"
  chmod +x "${target_dir}/sing-box"
  [[ -f "${src_dir}/libcronet.so" ]] && cp "${src_dir}/libcronet.so" "${target_dir}/libcronet.so"
  [[ -f "${src_dir}/LICENSE" ]] && cp "${src_dir}/LICENSE" "${target_dir}/LICENSE"
}

case "$ARCH" in
  native)
    case "$(uname -m)" in
      x86_64|amd64) fetch_one amd64 runtime/linux-amd64 ;;
      aarch64|arm64) fetch_one arm64 runtime/linux-arm64 ;;
      *) echo "Unsupported Linux architecture: $(uname -m)" >&2; exit 64 ;;
    esac
    ;;
  amd64|x64|x86_64) fetch_one amd64 runtime/linux-amd64 ;;
  arm64|aarch64) fetch_one arm64 runtime/linux-arm64 ;;
  all) fetch_one amd64 runtime/linux-amd64; fetch_one arm64 runtime/linux-arm64 ;;
  *) echo "Usage: $0 [native|amd64|arm64|all]" >&2; exit 64 ;;
esac
