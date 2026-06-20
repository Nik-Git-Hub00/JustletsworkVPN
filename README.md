# WorkVPN

Clean workspace for the WorkVPN desktop client.

## Layout

- `apps/gui_vpn_mac.py` - macOS entrypoint.
- `apps/gui_vpn_win.py` - Windows entrypoint.
- `src/workvpn/platform/mac_app.py` - macOS GUI/helper implementation.
- `src/workvpn/platform/win_app.py` - Windows GUI/process implementation.
- `assets/` - shared UI assets and icons.
- `runtime/` - architecture folders for sing-box runtime files. Binaries are not committed.
- `specs/` - PyInstaller specs for workers.
- `scripts/` - setup/build/fetch helpers.

## Runtime binaries

`sing-box` binaries are intentionally not stored in GitHub. The build scripts download them when missing.

Runtime layout after fetch:

```text
runtime/macos-arm64/sing-box
runtime/macos-arm64/LICENSE
runtime/macos-x64/sing-box
runtime/macos-x64/LICENSE
runtime/windows-amd64/sing-box.exe
runtime/windows-amd64/libcronet.dll
runtime/windows-amd64/LICENSE
runtime/windows-arm64/sing-box.exe
runtime/windows-arm64/libcronet.dll
runtime/windows-arm64/LICENSE
```

Manual fetch commands:

```bash
./scripts/fetch_runtime_macos.sh native   # current Mac architecture
./scripts/fetch_runtime_macos.sh all      # both ARM and Intel
```

```powershell
./scripts/fetch_runtime_windows.ps1 -Arch all
```

## Python

Use Python 3.11 or newer. The current local builds were tested with Python 3.14, but the scripts do not require exactly 3.14.

The build scripts create `venv` automatically and install `requirements.txt` on each run. If you need a specific Python binary, pass it through `PYTHON`:

```bash
PYTHON=/path/to/python3 ./scripts/build_macos.sh
```

For Intel macOS builds from Apple Silicon, the script creates `venv-intel` through Rosetta/`arch -x86_64` and downloads the Intel `sing-box` automatically.

## Build commands

macOS:

```bash
./scripts/build_macos.sh                 # native build: ARM on Apple Silicon, Intel on Intel Mac
./scripts/build_macos_intel_from_arm.sh  # Intel build from Apple Silicon via Rosetta
```

Windows x64:

```powershell
./scripts/build_windows.ps1
```

Windows ARM64:

```powershell
./scripts/build_windows_arm64.ps1
```

On Windows you can also choose a specific Python:

```powershell
$env:PYTHON = "C:\Path\To\python.exe"
./scripts/build_windows.ps1
```

Build outputs are copied to `release/` as zip archives:

```text
release/WorkVPN-macos-arm64.zip
release/WorkVPN-macos-x64.zip
release/WorkVPN-windows-amd64.zip
release/WorkVPN-windows-arm64.zip
```

macOS zips contain `WorkVPN.app`; `sing-box` is already bundled inside it. Windows zips contain only `WorkVPN.exe`; `sing-box.exe` and `libcronet.dll` are bundled into the onefile executable by PyInstaller.
