#!/bin/sh
# Install Zig 0.17.1 into $1 for CUI_PY_PTY builds (used by cibuildwheel).
set -eu
dest=$1
ver=0.17.1
case "$(uname -m)-$(uname -s)" in
    x86_64-Linux) t=x86_64-linux sha=3581863e3cbcfd0fce0efc682ce7e9e93da96668a977791d356a26d2a7e9b17a ;;
    aarch64-Linux) t=aarch64-linux sha=a1546d5646eb184437918d6635ca6b762a0e889eac09cef720ee7a1ed3fe7795 ;;
    arm64-Darwin) t=aarch64-macos sha=75f1bc7a1e9852f17ec9a0c1895f767c4ec56d46bc8a834920eece1d0359dd8d ;;
    x86_64-Darwin) t=x86_64-macos sha=9af07b20319fbd0c92ee46ad23e81d6a782b1aaea2cfb8dcbff35f1d2c7ddbb7 ;;
    *) echo "install-zig: unsupported host $(uname -m)-$(uname -s)" >&2; exit 1 ;;
esac
tmp=$(mktemp -d)
curl -fsSL -o "$tmp/zig.tar.xz" "https://ziglang.org/download/$ver/zig-$t-$ver.tar.xz"
if command -v sha256sum >/dev/null; then
    echo "$sha  $tmp/zig.tar.xz" | sha256sum -c -
else
    echo "$sha  $tmp/zig.tar.xz" | shasum -a 256 -c -
fi
mkdir -p "$dest"
tar -xJf "$tmp/zig.tar.xz" -C "$dest" --strip-components=1
rm -rf "$tmp"
"$dest/zig" version
