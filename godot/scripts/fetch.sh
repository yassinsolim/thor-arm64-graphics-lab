#!/bin/sh
# download the pinned godot 4.5 artifacts into cache/ and check hashes.
# user-space only. does not install anything on the system.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
CACHE="$ROOT/cache"
mkdir -p "$CACHE"
cd "$CACHE"

base="https://github.com/godotengine/godot/releases/download/4.5-stable"
fetch() {
    name=$1
    if [ ! -f "$name" ]; then
        curl -fL --retry 3 -o "$name" "$base/$name"
    fi
}

fetch SHA512-SUMS.txt
fetch godot-4.5-stable.tar.xz.sha256
fetch godot-4.5-stable.tar.xz
fetch Godot_v4.5-stable_linux.arm64.zip

# macOS has shasum. Armada SteamOS has coreutils and no shasum.
sha256_file() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        sha256sum "$1" | awk '{print $1}'
    fi
}

expected_src="2cdb383d68bfe646c832064b9063310745e8db03a2e4b59f5946ee934b95c67d"
expected_arm="f9f167c0a19cc84385b508c12bd0e7a290dd21a639bce2ed6dcf4647af796589"
got_src=$(sha256_file godot-4.5-stable.tar.xz)
got_arm=$(sha256_file Godot_v4.5-stable_linux.arm64.zip)
sidecar=$(awk '{print $1}' godot-4.5-stable.tar.xz.sha256)
if [ "$got_src" != "$expected_src" ] || [ "$got_src" != "$sidecar" ]; then
    echo "source tarball hash mismatch" >&2
    exit 1
fi
if [ "$got_arm" != "$expected_arm" ]; then
    echo "arm64 zip hash mismatch" >&2
    exit 1
fi
if command -v shasum >/dev/null 2>&1; then
    shasum -a 512 -c SHA512-SUMS.txt --ignore-missing
else
    sha512sum -c SHA512-SUMS.txt --ignore-missing
fi
echo "fetch ok"
