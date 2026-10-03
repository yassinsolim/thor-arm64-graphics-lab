# Godot 4.5 arm64 benchmark

Native ARM64 control for the Adreno 740 / Turnip path. Godot 4.5 runs without FEX, Proton, or vkd3d, so a slow result here would implicate the driver or the scene rather than translation. The Thor measurements are in `docs/godot-arm64-baseline.md`. No system install and no sudo.

## What is pinned

See `PINNED.md`. Short version:

- Godot `4.5-stable`, source `876b290332ec6f2e6d173d08162a02aa7e6ca46d`, MIT.
- Official Linux editor `Godot_v4.5-stable_linux.arm64` inside the arm64 zip. It is an AArch64 ELF. Armada is aarch64 glibc, so this is the binary to try. Mono is not used.
- Demo tag `4.5-90f2e38`, commit `90f2e38d7b5cf9e6fd0b788d0da1df4b84d49269`. Code is MIT. Assets and music are CC-BY 3.0.

`scripts/fetch.sh` re-downloads the Godot artifacts and refuses a hash mismatch. `scripts/install-user.sh` unzips the editor under `cache/linux-arm64/` and stops if `ldd` reports a missing library. Nothing is copied into `/usr`.

## Benchmark patch

`patches/tps-demo-benchmark.patch` is meant for the demo repo, not for Godot itself. `git apply --check` succeeds on a clean checkout of `90f2e38d7b5cf9e6fd0b788d0da1df4b84d49269`. The scripts are preloaded, so the first launch does not depend on Godot's global class cache.

Pass `--benchmark` after `--`, or the engine's own `--benchmark` flag (a different switch) is what runs. The run script does this.

When that user arg is set:

- Skip the menu. No clicks.
- Seed `20261002` before the level enters the tree. Forklift model pick uses that seed instead of `randomize()`.
- Player spawns on the first spawn marker. Input, crosshair, and mouse capture stay off.
- A camera walks the existing spawn walkway at 4 m/s, looping the same five points.
- 8 s warmup, then 20 s measured, then quit. Timeout 180 s from the first camera frame.
- Window 1280x720, vsync off, frame cap off. Those are measurement controls.
- Graphics keys are reset to the demo's own defaults in memory. `user://settings.ini` is not written.

It prints `BENCHMARK_READY`, `BENCHMARK_MEASURE_START`, then one `BENCHMARK_DONE` JSON line with frame count, p50, p95, min, max, renderer, driver, seed, and size.

## First run, no root

```sh
sh godot/scripts/run-benchmark.sh
```

On the Thor, after the transfer below, the same script unpacks the arm64 editor if needed, applies the patch if the demo clone does not already have it, imports resources, then runs Forward+ then Mobile on Vulkan. Linux uses `--headless --import`. The macOS 4.5 editor aborts in that mode (`Pure virtual function called`), so the Mac boot check uses `--import` without `--headless`. That Mac result is Metal and is not a Thor result. The import cache stays on the machine that created it. Do not copy `src/tps-demo/.godot` between macOS and Linux.

Host sampling in `scripts/sample_host.py` does not use sudo:

- Godot's own frame-time summary
- `/proc/<pid>/fdinfo` `drm-engine-gpu` busy, when `/proc` exists
- GPU `cur_freq` under the Adreno devfreq path, and any `thermal_zone` whose type mentions gpu, gpuss, or adreno
- RSS, MemAvailable, zram from `/proc`
- `GAMESCOPE_FOCUSED_APP` via `xprop` on `$DISPLAY` or `:0`

There is no completed-present X atom in current Gamescope. The frame series is the engine's 20 s window. Focus is still recorded so a later counter capture can name the right app id.

The script writes `results/<host>-<arch>/counters-optional.txt` and does not run it.

## Optional counters

`tools/msm_perfcntr_sample.py` still defaults to Gamescope focus `2074920` and the First Descendant settings file. New flags, off unless you pass them:

- `--focus-app N` to require a different Gamescope id
- `--no-focus-check` to log focus and skip that settings file
- `--display` (default `:0`, unchanged for the old capture)

Run that only by hand, during a second launch, after `BENCHMARK_MEASURE_START`. The printed command is in the results directory. It needs sudo because the kernel stream is `CAP_PERFMON`. Closing it releases the one global counter stream.

## Success

A local macOS boot check on Oct 2 finished both renderers and exited 0. It used Metal on an Apple M5. `gpu_busy` is null because macOS has no `/proc` fdinfo. These numbers are not Thor results.

| Renderer | Frames | p50 | Size | Seed |
| --- | --- | --- | --- | --- |
| Forward+ | 1425 | 13.948 ms | 1280x720 | 20261002 |
| Mobile | 2362 | 8.336 ms | 1280x720 | 20261002 |

Mobile printed that MetalFX Temporal, SSAO, and volumetric fog are Forward+ only. That is the demo applying its own defaults. The window still measured and quit 0. On Linux the scale mode is the demo's FSR2 default instead of MetalFX. SSAO and volumetric fog can still warn under Mobile. That warning is not a stop.

Thor numbers from the same day are in `THOR-2026-10-02.md`. That run used Turnip on the Adreno 740. The Mac table above is only a boot check.

A renderer succeeds when the process exits 0, `BENCHMARK_DONE` has at least 30 frames, and the reported size is 1280x720.

The pair succeeds when both `forward_plus` and `mobile` do that, and each JSON has a wall time near 20 s. On Linux, `gpu_busy` is filled from fdinfo. On macOS it stays null. That null is expected here.

## Stop

- No `BENCHMARK_MEASURE_START` within 600 s.
- `BENCHMARK_FAIL`, or exit code other than 0.
- Fewer than 30 measured frames, or a size other than 1280x720.
- Linux only: MemAvailable under 1.5 GiB and zram used over 6 GiB. The host sends SIGTERM.
- The editor's `ldd` reports a missing library. Use the build recipe. Do not copy a random Turnip into the system path for this run.
- Any urge to edit a proprietary game, disable anti-cheat, or treat the macOS Metal numbers as Thor numbers.

## Upstream artifacts

1. The demo patch, as a Godot TPS-demo PR: deterministic camera path, fixed seed, 1280x720, no quality change. Link the MIT/CC-BY license. Do not attach Thor counter dumps to that PR.
2. If Forward+ fails device creation on Turnip, a Godot issue with the renderer name, the driver string, and the Vulkan error, plus a Mesa issue whose repro is a CTS or a tiny RenderingDevice sample. The demo assets are not the repro.
3. If both renderers finish and fdinfo shows the GPU saturated with the same texture-stall shape as the earlier lobby capture, the Mesa writeup stays a hardware and counter note. It does not need the demo's screenshots.

## Source build, only if the official binary will not load

From `godot-4.5-stable.tar.xz`, user-space prefix, no install step:

```sh
tar -xf godot-4.5-stable.tar.xz
cd godot-4.5-stable
scons platform=linuxbsd arch=arm64 target=editor production=yes
```

Needs a C++ toolchain, Python, and SCons. Point `run-benchmark.sh` at that `bin/godot.linuxbsd.editor.arm64` by replacing the unpacked official binary in `cache/linux-arm64/` only after `ldd` on the official file has already failed. Do not start this build during the first 2 hour window unless the official ELF refuses to start.

## After VRChat

From the resumes repo, once the Thor is free. This does not start counters and does not touch Steam.

```sh
rsync -a --exclude src/tps-demo/.git --exclude src/tps-demo/.godot --exclude cache/macos --exclude results \
  godot/ thor:~/godot-arm64-benchmark/ && \
rsync -a tools/msm_perfcntr_sample.py thor:~/godot-arm64-benchmark/msm_perfcntr_sample.py && \
ssh thor 'sh ~/godot-arm64-benchmark/scripts/run-benchmark.sh'
```
