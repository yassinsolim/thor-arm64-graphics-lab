#!/bin/sh
# clone the pinned demo and apply the benchmark patch if this tree does not
# already contain it. safe to re-run.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
DEMO="$ROOT/src/tps-demo"
PATCH="$ROOT/patches/tps-demo-benchmark.patch"
PIN="90f2e38d7b5cf9e6fd0b788d0da1df4b84d49269"
mkdir -p "$ROOT/src"
if [ ! -d "$DEMO/.git" ]; then
    git clone --depth 1 --branch 4.5-90f2e38 https://github.com/godotengine/tps-demo.git "$DEMO"
fi
got=$(git -C "$DEMO" rev-parse HEAD)
if [ "$got" != "$PIN" ]; then
    echo "demo HEAD is $got, want $PIN" >&2
    exit 1
fi
if [ ! -f "$DEMO/benchmark/benchmark_config.gd" ]; then
    git -C "$DEMO" apply "$PATCH"
fi
echo "$DEMO"
