#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

version="${APP_VERSION:-$(cat VERSION 2>/dev/null || echo 1.0.0)}"
case "$(uname -m)" in
  x86_64|amd64)
    release_arch="linux-amd64"
    deb_arch="amd64"
    rpm_arch="x86_64"
    ;;
  aarch64|arm64)
    release_arch="linux-arm64"
    deb_arch="arm64"
    rpm_arch="aarch64"
    ;;
  *)
    echo "Unsupported Linux architecture: $(uname -m)" >&2
    exit 64
    ;;
esac

package_dir="release/WorkVPN-${release_arch}"
if [[ ! -x "${package_dir}/workvpn" || ! -x "${package_dir}/sing-box" ]]; then
  echo "Missing ${package_dir}. Run ./scripts/build_linux.sh first." >&2
  exit 1
fi
if [[ ! -f "${package_dir}/libcronet.so" ]]; then
  echo "Missing ${package_dir}/libcronet.so. Re-run ./scripts/build_linux.sh to refresh runtime." >&2
  exit 1
fi

unit_file="build/linux-package/workvpn.service"
mkdir -p "$(dirname "$unit_file")"
cat > "$unit_file" <<'UNIT'
[Unit]
Description=WorkVPN sing-box service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/usr/lib/workvpn
Environment=LD_LIBRARY_PATH=/usr/lib/workvpn
ExecStart=/usr/lib/workvpn/sing-box run -c /etc/workvpn/config.json
Restart=on-failure
RestartSec=2
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
UNIT

build_deb() {
  local root_dir="build/deb-${release_arch}"
  rm -rf "$root_dir"
  mkdir -p "$root_dir/DEBIAN" "$root_dir/usr/bin" "$root_dir/usr/lib/workvpn" "$root_dir/etc/systemd/system"
  install -m 0755 "${package_dir}/workvpn" "$root_dir/usr/bin/workvpn"
  install -m 0755 "${package_dir}/sing-box" "$root_dir/usr/lib/workvpn/sing-box"
  install -m 0644 "${package_dir}/libcronet.so" "$root_dir/usr/lib/workvpn/libcronet.so"
  install -m 0644 "$unit_file" "$root_dir/etc/systemd/system/workvpn.service"
  [[ -f "${package_dir}/LICENSE.sing-box" ]] && install -m 0644 "${package_dir}/LICENSE.sing-box" "$root_dir/usr/lib/workvpn/LICENSE.sing-box"

  cat > "$root_dir/DEBIAN/control" <<CONTROL
Package: workvpn
Version: ${version}
Section: net
Priority: optional
Architecture: ${deb_arch}
Maintainer: WorkVPN
Depends: systemd
Description: WorkVPN CLI client
 WorkVPN command line client for managing a sing-box VPN service.
CONTROL

  cat > "$root_dir/DEBIAN/postinst" <<'POSTINST'
#!/usr/bin/env sh
set -e
systemctl daemon-reload >/dev/null 2>&1 || true
exit 0
POSTINST
  cat > "$root_dir/DEBIAN/prerm" <<'PRERM'
#!/usr/bin/env sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "deconfigure" ]; then
  systemctl stop workvpn.service >/dev/null 2>&1 || true
fi
exit 0
PRERM
  cat > "$root_dir/DEBIAN/postrm" <<'POSTRM'
#!/usr/bin/env sh
set -e
systemctl daemon-reload >/dev/null 2>&1 || true
if [ "$1" = "purge" ]; then
  rm -rf /etc/workvpn
fi
exit 0
POSTRM
  chmod 0755 "$root_dir/DEBIAN/postinst" "$root_dir/DEBIAN/prerm" "$root_dir/DEBIAN/postrm"

  local out="release/WorkVPN-${version}-${release_arch}.deb"
  rm -f "$out"
  dpkg-deb --build --root-owner-group "$root_dir" "$out"
  echo "Release: $out"
}

build_rpm() {
  if ! command -v rpmbuild >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
      echo "rpmbuild is missing. Installing rpm with apt-get..."
      if [[ "$(id -u)" -eq 0 ]]; then
        apt-get update
        apt-get install -y rpm
      else
        sudo apt-get update
        sudo apt-get install -y rpm
      fi
    else
      echo "rpmbuild is missing. Install rpm/rpm-build first." >&2
      return 1
    fi
  fi

  local top="$(pwd)/build/rpmbuild-${release_arch}"
  local spec="build/workvpn-${release_arch}.spec"
  local license_install=""
  local license_file=""
  if [[ -f "${package_dir}/LICENSE.sing-box" ]]; then
    license_install="install -m 0644 %{_package_dir}/LICENSE.sing-box %{buildroot}/usr/lib/workvpn/LICENSE.sing-box"
    license_file="/usr/lib/workvpn/LICENSE.sing-box"
  fi
  rm -rf "$top"
  mkdir -p "$top/BUILD" "$top/BUILDROOT" "$top/RPMS" "$top/SOURCES" "$top/SPECS" "$top/SRPMS"

  cat > "$spec" <<SPEC
Name: workvpn
Version: ${version}
Release: 1%{?dist}
Summary: WorkVPN CLI client
License: Proprietary
URL: https://example.invalid/workvpn
AutoReqProv: no

%description
WorkVPN command line client for managing a sing-box VPN service.

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/usr/bin %{buildroot}/usr/lib/workvpn %{buildroot}/etc/systemd/system
install -m 0755 %{_package_dir}/workvpn %{buildroot}/usr/bin/workvpn
install -m 0755 %{_package_dir}/sing-box %{buildroot}/usr/lib/workvpn/sing-box
install -m 0644 %{_package_dir}/libcronet.so %{buildroot}/usr/lib/workvpn/libcronet.so
install -m 0644 %{_unit_file} %{buildroot}/etc/systemd/system/workvpn.service
${license_install}

%post
systemctl daemon-reload >/dev/null 2>&1 || true

%preun
if [ \$1 -eq 0 ]; then
  systemctl stop workvpn.service >/dev/null 2>&1 || true
fi

%postun
systemctl daemon-reload >/dev/null 2>&1 || true

%files
/usr/bin/workvpn
/usr/lib/workvpn/sing-box
/usr/lib/workvpn/libcronet.so
%config(noreplace) /etc/systemd/system/workvpn.service
%dir /usr/lib/workvpn
${license_file}
SPEC

  rpmbuild \
    --define "_topdir ${top}" \
    --define "_package_dir $(pwd)/${package_dir}" \
    --define "_unit_file $(pwd)/${unit_file}" \
    --target "${rpm_arch}" \
    -bb "$spec"

  local built
  built="$(find "$top/RPMS" -type f -name 'workvpn-*.rpm' | head -n 1)"
  local out="release/WorkVPN-${version}-${release_arch}.rpm"
  rm -f "$out"
  cp "$built" "$out"
  echo "Release: $out"
}

mkdir -p release build
build_deb
build_rpm
