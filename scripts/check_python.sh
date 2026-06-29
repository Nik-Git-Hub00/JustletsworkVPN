#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
${PYTHON:-python3} -m py_compile \
  apps/gui_vpn_mac.py \
  apps/gui_vpn_win.py \
  src/workvpn/version.py src/workvpn/update_check.py \
  src/workvpn/platform/mac_backend.py \
  src/workvpn/platform/mac_app.py \
  src/workvpn/platform/win_backend.py \
  src/workvpn/platform/win_app.py
