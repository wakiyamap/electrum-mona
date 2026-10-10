#!/bin/bash
#
# This script cross-compiles the "lyra2re2_hash" python C extension (Lyra2REv2,
# the proof-of-work of Monacoin) to Windows, and installs it into the python inside wine.
#
# There is no C compiler inside wine, so pip (inside wine) cannot build the sdist,
# and there are no binary wheels on PyPI. So instead we compile the extension using the
# mingw-w64 toolchain of the host, linking against the python DLL that is inside wine.
# As it then looks installed to pip, the "lyra2re2-hash" line
# of contrib/deterministic-build/requirements.txt gets skipped when that file is installed.
#
# env vars (set by make_win.sh):
# - CONTRIB, CACHEDIR, WINEPREFIX, WINE_PYTHON, GCC_TRIPLET_HOST

LYRA2RE2_HASH_VERSION="1.2.0"
LYRA2RE2_HASH_SHA256="5cc17e562a37859cbe3f7ec2825a3a84616c2e482a6fa129dd2f1f731671ab52"
# ^ sdist on PyPI.
# note: this version is duplicated in contrib/deterministic-build/requirements.txt
#       and in contrib/android/p4a_recipes/lyra2re2_hash/__init__.py
LYRA2RE2_HASH_FILENAME="lyra2re2_hash-$LYRA2RE2_HASH_VERSION.tar.gz"
LYRA2RE2_HASH_URL="https://files.pythonhosted.org/packages/source/l/lyra2re2_hash/$LYRA2RE2_HASH_FILENAME"

set -e

. "$CONTRIB"/build_tools_util.sh

pkgname="lyra2re2_hash"
info "Building $pkgname..."

PYHOME="$WINEPREFIX/drive_c/python3"
SITE_PACKAGES="$PYHOME/Lib/site-packages"
BUILDDIR="$CACHEDIR/$pkgname"

# the file we build here must be the one that is pinned for the other platforms
grep -q "sha256:$LYRA2RE2_HASH_SHA256" "$CONTRIB/deterministic-build/requirements.txt" \
    || fail "$pkgname $LYRA2RE2_HASH_VERSION is not what is pinned in deterministic-build/requirements.txt"

download_if_not_exist "$CACHEDIR/$LYRA2RE2_HASH_FILENAME" "$LYRA2RE2_HASH_URL"
verify_hash "$CACHEDIR/$LYRA2RE2_HASH_FILENAME" "$LYRA2RE2_HASH_SHA256"
rm -rf "$BUILDDIR"
mkdir -p "$BUILDDIR"
tar xf "$CACHEDIR/$LYRA2RE2_HASH_FILENAME" -C "$BUILDDIR" --strip-components=1

(
    cd "$BUILDDIR"
    # e.g. python312.dll (but not python3.dll)
    PYTHON_DLL=$(ls "$PYHOME"/python3[0-9]*.dll) || fail "Could not find the python DLL inside wine"
    # note: list of source files is from the setup.py of the sdist. We only need the lyra2re2 module.
    # note: see build_tools_util.sh for why LYRA2RE2_HASH_CFLAGS is needed
    gcc_host gcc -shared -O2 -g0 $LYRA2RE2_HASH_CFLAGS \
        -static-libgcc -Wl,--no-insert-timestamp \
        -I"$PYHOME/include" -I. -I./sha3 \
        -o "$pkgname.pyd" \
        Lyra2RE.c Sponge.c Lyra2.c \
        sha3/blake.c sha3/groestl.c sha3/keccak.c sha3/cubehash.c sha3/bmw.c sha3/skein.c \
        lyra2re2module.c \
        "$PYTHON_DLL" || fail "Could not build $pkgname"
    host_strip "$pkgname.pyd"
)

info "Installing $pkgname into wine python."
cp -fpv "$BUILDDIR/$pkgname.pyd" "$SITE_PACKAGES/" || fail "Could not copy $pkgname to its destination"
# minimal metadata, so that pip considers the package as installed
DIST_INFO="$SITE_PACKAGES/$pkgname-$LYRA2RE2_HASH_VERSION.dist-info"
rm -rf "$SITE_PACKAGES/$pkgname"-*.dist-info
mkdir -p "$DIST_INFO"
cat > "$DIST_INFO/METADATA" <<EOF
Metadata-Version: 2.1
Name: $pkgname
Version: $LYRA2RE2_HASH_VERSION
EOF
echo "build-lyra2rev2.sh" > "$DIST_INFO/INSTALLER"

info "Testing $pkgname inside wine."
# test vector: PoW hash of the Monacoin mainnet header at height 2618875 (same as in blockchain.py)
$WINE_PYTHON -c "
import lyra2re2_hash
raw_header = bytes.fromhex(
    '000000207ef097f85c42eae5e53551c95a30c336a86b3958e9b2c99a44a16b4a4e5efb90c31ab1ae'
    '02f56e9391b2427f02f418410d864df97ff869d0ab6f03f0971960528a8f41620c6d041a88c2bf8b')
expected = '000000000000006985a7b5e5f5984542519975f07d9160457c3667eb44e44d74'
assert lyra2re2_hash.getPoWHash(raw_header)[::-1].hex() == expected, 'wrong hash'
" || fail "$pkgname does not work inside wine"

info "$pkgname has been built and installed."
