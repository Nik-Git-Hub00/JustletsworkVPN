# WorkVPN

Clean workspace for the WorkVPN desktop client.

## Layout

- `apps/gui_vpn_mac.py` - macOS entrypoint.
- `apps/gui_vpn_win.py` - Windows entrypoint.
- `apps/cli_vpn_linux.py` - Linux CLI entrypoint.
- `src/workvpn/platform/mac_app.py` - macOS GUI/helper implementation.
- `src/workvpn/platform/win_app.py` - Windows GUI/process implementation.
- `src/workvpn/platform/linux_cli.py` - Linux CLI/systemd implementation.
- `assets/` - shared UI assets and icons.
- `runtime/` - architecture folders for sing-box runtime files. Binaries are not committed.
- `installer/` - Inno Setup script for Windows setup installers.
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
runtime/linux-amd64/sing-box
runtime/linux-amd64/libcronet.so
runtime/linux-amd64/LICENSE
runtime/linux-arm64/sing-box
runtime/linux-arm64/libcronet.so
runtime/linux-arm64/LICENSE
```

Manual fetch commands:

```bash
./scripts/fetch_runtime_macos.sh native   # current Mac architecture
./scripts/fetch_runtime_macos.sh all      # both ARM and Intel
```

```powershell
./scripts/fetch_runtime_windows.ps1 -Arch all
```

```bash
./scripts/fetch_runtime_linux.sh native  # current Linux architecture
./scripts/fetch_runtime_linux.sh all     # both amd64 and arm64
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

Linux native architecture:

```bash
./scripts/build_linux.sh
./scripts/package_linux.sh
```

For manual Windows setup installer builds, install Inno Setup 6 first. Without it, the scripts still build the portable zip/onefile exe and skip the setup `.exe`.

On Windows you can also choose a specific Python:

```powershell
$env:PYTHON = "C:\Path\To\python.exe"
./scripts/build_windows.ps1
```

Build outputs are copied to `release/` as artifacts:

```text
release/WorkVPN-macos-arm64.zip
release/WorkVPN-macos-arm64.dmg
release/WorkVPN-macos-x64.zip
release/WorkVPN-macos-x64.dmg
release/WorkVPN-windows-amd64.zip
release/WorkVPN-Setup-<version>-windows-amd64.exe
release/WorkVPN-windows-arm64.zip
release/WorkVPN-Setup-<version>-windows-arm64.exe
release/WorkVPN-linux-amd64.tar.gz
release/WorkVPN-<version>-linux-amd64.deb
release/WorkVPN-<version>-linux-amd64.rpm
release/WorkVPN-linux-arm64.tar.gz
release/WorkVPN-<version>-linux-arm64.deb
release/WorkVPN-<version>-linux-arm64.rpm
```

macOS builds create both zip and DMG artifacts. The zip contains `WorkVPN.app`; the DMG contains `WorkVPN.app`, an Applications shortcut, and the install background. `sing-box` is bundled inside the app. Windows zips contain only `WorkVPN.exe`; `sing-box.exe` and `libcronet.dll` are bundled into the onefile executable by PyInstaller. Linux builds create a portable tar.gz plus deb/rpm packages for amd64 and arm64.

## Linux CLI

The Linux client is CLI-only and uses systemd to run `sing-box`. It is intended for systemd distributions. Arch works through the tar.gz artifact. Gentoo works if installed with systemd; OpenRC needs a separate service backend that is not included yet.

Portable tar.gz flow:

```bash
tar -xzf WorkVPN-linux-amd64.tar.gz
cd WorkVPN-linux-amd64
./workvpn setup --uuid YOUR-UUID --url https://example.com/path
workvpn start
workvpn status
workvpn logs -n 100
workvpn stop
```

Package flow:

```bash
sudo apt install ./WorkVPN-<version>-linux-amd64.deb
# or
sudo rpm -i ./WorkVPN-<version>-linux-amd64.rpm

workvpn setup --uuid YOUR-UUID --url https://example.com/path
workvpn start
```

Linux install layout:

```text
/usr/bin/workvpn                 # deb/rpm
/usr/local/bin/workvpn           # tar.gz self-install
/usr/lib/workvpn/sing-box
/usr/lib/workvpn/libcronet.so
/etc/workvpn/settings.json
/etc/workvpn/config.json
/etc/systemd/system/workvpn.service
```

Useful commands:

```bash
workvpn -h
workvpn setup -h
workvpn refresh
workvpn start
workvpn stop
workvpn restart
workvpn status
workvpn logs -f
workvpn ip
workvpn uninstall --purge
```

`setup` installs the runtime/service if needed, saves UUID and URL, downloads `config_universal.json`, inserts the UUID, and writes `/etc/workvpn/config.json`. It does not start VPN automatically.

## Windows installer

The Windows setup installers are built with Inno Setup 6 from `installer/WorkVPN.iss`. The installer supports English and Russian, uses the Windows UI language as the default, and still shows a language selector before installation.

Installer behavior:

- installs to `C:\Program Files\WorkVPN`;
- creates a Desktop shortcut by default;
- does not request a Windows reboot after installation;
- shows an optional `Launch WorkVPN` checkbox after installation;
- launches WorkVPN from the installer with the current elevated user context;
- removes `%LOCALAPPDATA%\WorkVPN` during uninstall.

If Inno Setup 6 is not installed during a manual Windows build, the build script skips the setup `.exe` and still creates the portable zip/onefile exe artifact.

## GitHub release workflow

Release builds are handled by `.github/workflows/release.yml`.

Manual release from GitHub Actions:

- `bump=patch`: `1.0.0` -> `1.0.1`
- `bump=minor`: `1.0.0` -> `1.1.0`
- `bump=major`: `1.0.0` -> `2.0.0`
- `bump=manual`: use the explicit `version` input

If there are no existing `v*.*.*` tags, the first automatic release is `v1.0.0`.

The workflow uploads macOS zip/DMG artifacts, Windows zip/setup artifacts, and Linux tar.gz/deb/rpm artifacts to the GitHub Release.

