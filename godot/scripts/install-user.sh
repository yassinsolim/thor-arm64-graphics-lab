#!/bin/sh
# unpack the official linux arm64 editor into this tree. no root, no system path.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
# status stays on stderr. stdout is only the binary path, for command substitution.
sh "$ROOT/scripts/fetch.sh" >&2
DEST="$ROOT/cache/linux-arm64"
mkdir -p "$DEST"
if [ ! -x "$DEST/Godot_v4.5-stable_linux.arm64" ]; then
    unzip -o "$ROOT/cache/Godot_v4.5-stable_linux.arm64.zip" -d "$DEST" >&2
    chmod +x "$DEST/Godot_v4.5-stable_linux.arm64"
fi
BIN="$DEST/Godot_v4.5-stable_linux.arm64"
# linux file(1) says "ARM aarch64"; some builds only say "aarch64".
# require both ELF and aarch64 so a text file cannot pass.
desc=$(file "$BIN")
if ! printf '%s\n' "$desc" | grep -q "ELF" || ! printf '%s\n' "$desc" | grep -q "aarch64"; then
    echo "unpacked binary is not an aarch64 ELF" >&2
    printf '%s\n' "$desc" >&2
    exit 1
fi
if ldd "$BIN" 2>/dev/null | grep -q "not found"; then
    echo "official editor is missing libraries:" >&2
    ldd "$BIN" | grep "not found" >&2
    echo "see README build recipe. do not copy this binary onto the system loader path." >&2
    exit 1
fi
echo "$BIN"
