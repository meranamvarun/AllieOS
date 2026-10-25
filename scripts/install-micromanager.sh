#!/usr/bin/env bash
set -euo pipefail

# Micro-Manager does not publish Linux binaries, so AllieOS builds a reviewed,
# pinned source revision. See docs/third-party/micro-manager.md.
MM_VERSION="2.0.3"
MM_COMMIT="bba80619603cf8974a0666c06c60ec68111d14b2"
MM_3RDPARTY_REVISION="227"
SWIG_VERSION="3.0.12"
SWIG_SHA256="5d9f84a99bd4593be487c94301c44c5070a5bc66fa448f965d31103d6f5b5294"
INSTALL_DIR="/opt/micro-manager/${MM_VERSION}-${MM_COMMIT:0:12}"

install_desktop_entry() {
  install -d -m 0755 /usr/local/share/applications
  cat > /usr/local/share/applications/org.micro-manager.MicroManager.desktop <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Micro-Manager
Comment=Microscope control and image acquisition
Exec=/usr/local/bin/micromanager
TryExec=/usr/local/bin/micromanager
Icon=applications-science
Terminal=false
Categories=Science;Education;
StartupNotify=true
DESKTOP
  chmod 0644 /usr/local/share/applications/org.micro-manager.MicroManager.desktop
}

if [[ "$(uname -s)" != "Linux" ]] || \
   ! grep -Eq '^ID=(allieos|ubuntu)$' /etc/os-release; then
  echo "Micro-Manager installation requires AllieOS or a compatible base system." >&2
  exit 2
fi
if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root through alliectl or sudo." >&2
  exit 2
fi
if [[ -x "${INSTALL_DIR}/bin/micromanager" ]]; then
  ln -sfn "${INSTALL_DIR}/bin/micromanager" /usr/local/bin/micromanager
  install_desktop_entry
  echo "Micro-Manager ${MM_VERSION} is already installed."
  exit 0
fi
if [[ -e /usr/local/bin/micromanager && ! -L /usr/local/bin/micromanager ]]; then
  echo "/usr/local/bin/micromanager exists and is not an AllieOS-managed symlink." >&2
  exit 2
fi

apt-get install --yes \
  ant autoconf autoconf-archive automake build-essential ca-certificates curl git \
  libboost-all-dev libpcre3-dev libtool openjdk-11-jdk pkg-config subversion

BUILD_DIR="$(mktemp -d -t allieos-micromanager.XXXXXXXX)"
trap 'rm -rf -- "${BUILD_DIR}"' EXIT

curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 \
  "https://downloads.sourceforge.net/project/swig/swig/swig-${SWIG_VERSION}/swig-${SWIG_VERSION}.tar.gz" \
  --output "${BUILD_DIR}/swig.tar.gz"
printf '%s  %s\n' "${SWIG_SHA256}" "${BUILD_DIR}/swig.tar.gz" | sha256sum --check --status
tar -xzf "${BUILD_DIR}/swig.tar.gz" -C "${BUILD_DIR}"
pushd "${BUILD_DIR}/swig-${SWIG_VERSION}" >/dev/null
./configure --prefix="${BUILD_DIR}/swig-prefix"
make -j"$(nproc)"
make install
popd >/dev/null

mkdir "${BUILD_DIR}/3rdpartypublic"
svn checkout --quiet --revision "${MM_3RDPARTY_REVISION}" \
  https://svn.micro-manager.org/3rdpartypublic/classext \
  "${BUILD_DIR}/3rdpartypublic/classext"
[[ "$(svn info --show-item revision "${BUILD_DIR}/3rdpartypublic/classext")" == "${MM_3RDPARTY_REVISION}" ]]
git clone --quiet --no-checkout https://github.com/micro-manager/micro-manager.git \
  "${BUILD_DIR}/micro-manager"
git -C "${BUILD_DIR}/micro-manager" checkout --quiet --detach "${MM_COMMIT}"
git -C "${BUILD_DIR}/micro-manager" submodule update --init --recursive --quiet
[[ "$(git -C "${BUILD_DIR}/micro-manager" rev-parse HEAD)" == "${MM_COMMIT}" ]]
[[ "$(cat "${BUILD_DIR}/micro-manager/3rdpartypublic-revision")" == "${MM_3RDPARTY_REVISION}" ]]

export SWIG="${BUILD_DIR}/swig-prefix/bin/swig"
pushd "${BUILD_DIR}/micro-manager" >/dev/null
./autogen.sh
./configure --prefix="${INSTALL_DIR}"
make fetchdeps
make -j"$(nproc)"
make install
popd >/dev/null

ln -sfn "${INSTALL_DIR}/bin/micromanager" /usr/local/bin/micromanager
install_desktop_entry
echo "Installed Micro-Manager ${MM_VERSION} at ${INSTALL_DIR}."
