#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

release_arch="${1:-}"
if [[ -z "$release_arch" ]]; then
  echo "Usage: $0 macos-arm64|macos-x64" >&2
  exit 64
fi

app_path="dist/WorkVPN.app"
background_path="build_tools/dmg/background_dmg_panels.png"
release_dir="release"
dmg_name="WorkVPN-${release_arch}.dmg"
stage_dir="build/dmg-${release_arch}"
rw_dmg="build/WorkVPN-${release_arch}.rw.dmg"
final_dmg="${release_dir}/${dmg_name}"
volume_name="WorkVPN"

if [[ ! -d "$app_path" ]]; then
  echo "App not found: $app_path" >&2
  exit 66
fi
if [[ ! -f "$background_path" ]]; then
  echo "DMG background not found: $background_path" >&2
  exit 66
fi

mkdir -p "$release_dir" build
rm -rf "$stage_dir" "$rw_dmg" "$final_dmg"
mkdir -p "$stage_dir/.background"

cp -R "$app_path" "$stage_dir/WorkVPN.app"
cp "$background_path" "$stage_dir/.background/background.png"
ln -s /Applications "$stage_dir/Applications"

hdiutil create \
  -volname "$volume_name" \
  -srcfolder "$stage_dir" \
  -fs HFS+ \
  -fsargs "-c c=64,a=16,e=16" \
  -format UDRW \
  -ov \
  "$rw_dmg" >/dev/null

mount_output="$(hdiutil attach -readwrite -noverify -noautoopen "$rw_dmg")"
device="$(printf '%s\n' "$mount_output" | awk '/\/Volumes\// {print $1; exit}')"
mount_point="/Volumes/${volume_name}"

cleanup() {
  if [[ -n "${device:-}" ]]; then
    hdiutil detach "$device" >/dev/null 2>&1 || true
  elif [[ -d "$mount_point" ]]; then
    hdiutil detach "$mount_point" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

osascript <<OSA >/dev/null
 tell application "Finder"
   tell disk "${volume_name}"
     open
     set current view of container window to icon view
     set toolbar visible of container window to false
     set statusbar visible of container window to false
     set the bounds of container window to {100, 100, 720, 520}
     set viewOptions to the icon view options of container window
     set arrangement of viewOptions to not arranged
     set icon size of viewOptions to 104
     set background picture of viewOptions to file ".background:background.png"
     set position of item "WorkVPN.app" of container window to {139, 215}
     set position of item "Applications" of container window to {471, 215}
     close
     open
     update without registering applications
     delay 1
   end tell
 end tell
OSA

sync
cleanup
trap - EXIT

hdiutil convert "$rw_dmg" -format UDZO -imagekey zlib-level=9 -o "$final_dmg" >/dev/null
rm -rf "$stage_dir" "$rw_dmg"

echo "Release: $final_dmg"
