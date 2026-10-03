#!/bin/sh
# forward+ then mobile. no sudo. prints the optional counter command.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
DEMO=$(sh "$ROOT/scripts/prepare-demo.sh")
HOST=$(uname -s)
ARCH=$(uname -m)
RESULTS="$ROOT/results/${HOST}-${ARCH}"
mkdir -p "$RESULTS"

case "$HOST-$ARCH" in
    Linux-aarch64|Linux-arm64)
        GODOT=$(sh "$ROOT/scripts/install-user.sh")
        DRIVER=vulkan
        AUDIO=Dummy
        ;;
    Darwin-arm64)
        ZIP="$ROOT/cache/Godot_v4.5-stable_macos.universal.zip"
        APP="$ROOT/cache/macos/Godot.app/Contents/MacOS/Godot"
        if [ ! -x "$APP" ]; then
            if [ ! -f "$ZIP" ]; then
                echo "macOS editor zip is not in cache/. this path is only for a local boot check." >&2
                exit 1
            fi
            unzip -o "$ZIP" -d "$ROOT/cache/macos"
        fi
        GODOT=$APP
        DRIVER=metal
        AUDIO=Dummy
        echo "darwin boot check only. this is not a Thor result."
        ;;
    *)
        echo "no editor selected for $HOST $ARCH" >&2
        exit 1
        ;;
esac

if [ -f "$ROOT/msm_perfcntr_sample.py" ]; then
    SAMPLER="$ROOT/msm_perfcntr_sample.py"
else
    SAMPLER="$ROOT/../msm_perfcntr_sample.py"
fi

echo "importing demo resources"
# editor-only. finishes the .godot import cache, then quits.
# the play launch below does not import on its own.
# macOS 4.5 aborts in --headless --import. the windowed editor import works.
if [ "$HOST" = "Darwin" ]; then
    "$GODOT" --import --path "$DEMO" > "$RESULTS/import.log" 2>&1
else
    "$GODOT" --headless --import --path "$DEMO" > "$RESULTS/import.log" 2>&1
fi

fail=0
for renderer in forward_plus mobile; do
    out="$RESULTS/${renderer}.json"
    echo "=== $renderer ($DRIVER) ==="
    if ! python3 "$ROOT/scripts/sample_host.py" \
        --godot "$GODOT" \
        --project "$DEMO" \
        --renderer "$renderer" \
        --driver "$DRIVER" \
        --audio-driver "$AUDIO" \
        --out "$out"
    then
        fail=1
    fi
done

cat > "$RESULTS/counters-optional.txt" << EOF
Optional. Do not run this during the first benchmark, and do not run it
unless you are at the keyboard. It needs sudo / CAP_PERFMON and samples the
whole GPU, so the Godot window has to be the thing on screen.

Start a second forward_plus run, wait for BENCHMARK_MEASURE_START and the
BENCHMARK_PID line, then:

sudo python3 $SAMPLER \\
  --seconds 20 \\
  --pid PID \\
  --display \${DISPLAY:-:0} \\
  --no-focus-check \\
  --out $RESULTS/perfcntr-forward_plus.json

Use --focus-app N instead of --no-focus-check when xprop shows a numeric
GAMESCOPE_FOCUSED_APP for this window. The default focus id is 2074920 and
will refuse a Godot window.
EOF

echo "optional counter command: $RESULTS/counters-optional.txt"
echo "results: $RESULTS"
exit "$fail"
