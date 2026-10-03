# Thor Godot 4.5 baseline, Oct 2 2026

Device was free after VRChat. No sudo. `msm_perfcntr_sample.py` was copied to the device and not executed. Gamescope focus stayed on app 769, not 2074920. First Descendant settings were not opened. Cyberpunk was not launched.

Godot `4.5.stable.official.876b29033` on Vulkan 1.4.354, device `Qualcomm - Turnip Adreno (TM) 740`. Demo commit `90f2e38d7b5cf9e6fd0b788d0da1df4b84d49269`. Seed `20261002`. Measure window 20 s after 8 s warmup. Vsync off, frame cap off. 3D render size 1280x720. Gamescope still presents the X window at 1920x1080, so the JSON `window_*` fields are the panel size and `width`/`height` are the viewport.

Raw JSON is on the Thor at `~/godot-arm64-benchmark/results/Linux-aarch64/` and copied to `godot/results/Linux-aarch64/`.

## Baseline

`DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 sh ~/godot-arm64-benchmark/scripts/run-benchmark.sh`

Both runs exited 0, reported 1280x720, and stayed on GPU clock 680 MHz. Process CPU time was about 4 to 6 seconds across a 21 second wall, so the CPU is not the limiter. MemAvailable stayed above 8 GB.

| Run | Frames | p50 | p95 | GPU busy | CPU s | RSS |
| --- | --- | --- | --- | --- | --- | --- |
| Forward+, voxel GI, shadows on | 453 | 43.85 ms | 54.75 ms | 0.940 | 4.36 | 491 MB |
| Mobile, voxel GI, shadows on | 830 | 23.96 ms | 33.62 ms | 0.939 | 5.63 | 322 MB |

Mobile is the faster renderer at the same scene, about 1.8 times the frame count, and both are GPU-bound. A native 1920x1080 Mobile repeat (no viewport scale) was 594 frames, p50 33.20 ms, GPU busy 0.932. Dropping the 3D size to 1280x720 is a real gain, and the GPU stays full.

## Config tests

Same camera and seed. Flags are user args after `--benchmark`. Locking vsync every measured frame was tried once and idled the GPU. Those files are in `contaminated-per-frame-lock/` and are not used below. The measured window only locks the viewport before timing starts.

| Run | Frames | p50 | GPU busy | CPU s |
| --- | --- | --- | --- | --- |
| Forward+, 3D scale 0.5 (640x360) | 508 | 38.59 ms | 0.934 | 4.49 |
| Mobile, lightmap GI | 1251 | 15.39 ms | 0.935 | 7.75 |
| Mobile, shadows off | 1159 | 16.94 ms | 0.979 | 5.74 |
| Mobile, lightmap GI, shadows off | 1996 | 9.38 ms | 0.931 | 7.72 |

Forward+ barely moved when the 3D buffer shrank by 4 times, and GPU busy stayed 93 percent. That renderer is not fill-rate bound in this scene. Mobile lightmap and Mobile shadows-off each help, and they stack. The stacked run is still 93 percent GPU busy at 680 MHz, with CPU time at 7.7 seconds. The bottleneck does not move to the CPU.

Best measured configuration: Mobile renderer, the demo's lightmap GI, shadows off, 1280x720, vsync off. p50 9.38 ms, 1996 frames in the 20 second window.

```sh
python3 ~/godot-arm64-benchmark/scripts/sample_host.py \
  --godot ~/godot-arm64-benchmark/cache/linux-arm64/Godot_v4.5-stable_linux.arm64 \
  --project ~/godot-arm64-benchmark/src/tps-demo \
  --renderer mobile --driver vulkan --audio-driver Dummy \
  --out ~/godot-arm64-benchmark/results/Linux-aarch64/mobile-lightmap-noshadow.json \
  --user-arg=--bench-gi --user-arg=lightmap \
  --user-arg=--bench-shadows --user-arg=off
```

## Frame profile

The winning Mobile configuration was captured with Godot's own Vulkan timestamps. The help text says `--gpu-profile`, but this 4.5 binary only enables the printer for `--profile-gpu`. No RenderDoc, no Adreno counters, and no First Descendant settings were touched. Focus stayed on app 769.

```sh
python3 ~/godot-arm64-benchmark/scripts/sample_host.py \
  --godot ~/godot-arm64-benchmark/cache/linux-arm64/Godot_v4.5-stable_linux.arm64 \
  --project ~/godot-arm64-benchmark/src/tps-demo \
  --renderer mobile --driver vulkan --audio-driver Dummy \
  --out ~/godot-arm64-benchmark/results/Linux-aarch64/mobile-lightmap-noshadow-profile.json \
  --godot-arg=--profile-gpu \
  --user-arg=--bench-gi --user-arg=lightmap \
  --user-arg=--bench-shadows --user-arg=off
```

The run repeated the earlier result: 1994 frames, p50 9.367 ms, GPU busy 0.932, CPU 7.79 s. The last measured frame reported `gpu_ms=7.110`, `cpu_ms=0.765`, 241 visible draws, 503,847 primitives, and 0 shadow draws.

`--profile-gpu` prints each `RENDER_TIMESTAMP` region as a one-second average. The "total" on that line is only the last frame in the second, so it can sit below the region averages. The region lines are the measurement. Across the 20 samples after `BENCHMARK_MEASURE_START`:

| Region | Median GPU time |
| --- | --- |
| Render Opaque + Transparent | 9.25 ms |
| Tonemap | 0.59 ms |
| Glow | 0.20 ms |
| Cull 3D Scene / Setup 3D Scene | under 0.14 ms |

No shadow region appeared. Mobile still logs that FSR2, SSAO, and volumetric fog are Forward+ only, so those passes are not in this frame. Tonemap plus glow is about 0.8 ms. The merged color pass is the frame. Godot does not give reflection probes their own timestamp. The three probes in `level.tscn` are shown by the lightmap path and are update-once, so a per-frame probe render would have to be inside that same color pass.

## One A/B: probes hidden

Same run, plus `--user-arg=--bench-probes --user-arg=off`, which hides `ReflectionProbes` after the lightmap is applied. Result file: `mobile-lightmap-noshadow-noprobes.json`.

| Config | Frames | p50 | Opaque+transparent median | GPU busy |
| --- | --- | --- | --- | --- |
| Probes shown | 1994 | 9.367 ms | 9.25 ms | 0.932 |
| Probes hidden | 2339 | 8.108 ms | 7.64 ms | 0.934 |

Draws and primitives stayed 241 and 503,847. Tonemap and glow stayed 0.59 ms and 0.20 ms. Hiding the probes saves about 1.3 ms and does not move the bottleneck off the GPU.

## Color-pass isolation

The no-probe baseline above is the control for everything in this section: Mobile, lightmap GI, shadows off, probes hidden, 1280x720, same camera and seed. p50 8.108 ms, color-pass median 7.64 ms, 241 draws, 503,847 primitives, GPU busy 0.934 at 680 MHz.

Each run below changes one factor. `--profile-gpu` stays on. Focus stayed on app 769. No Adreno counters. JSON and logs: `results/Linux-aarch64/mobile-iso-*.json`.

```sh
export DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000
python3 ~/godot-arm64-benchmark/scripts/sample_host.py \
  --godot ~/godot-arm64-benchmark/cache/linux-arm64/Godot_v4.5-stable_linux.arm64 \
  --project ~/godot-arm64-benchmark/src/tps-demo \
  --renderer mobile --driver vulkan --audio-driver Dummy \
  --godot-arg=--profile-gpu \
  --out ~/godot-arm64-benchmark/results/Linux-aarch64/mobile-iso-opaque.json \
  --user-arg=--bench-gi --user-arg=lightmap \
  --user-arg=--bench-shadows --user-arg=off \
  --user-arg=--bench-probes --user-arg=off \
  --user-arg=--bench-pass --user-arg=opaque
```

The other captures use the same command with a different `--out` and one extra factor: `--bench-shade unshaded`, `--bench-shade wireframe`, `--bench-shade flat`, `--bench-shade flat-structure`, or `--bench-geo structure|props|core`. The flat-plus-hide runs pass both `--bench-shade flat` and one `--bench-geo`.

| Run | Frames | p50 | Color median | Draws | Primitives | GPU busy |
| --- | --- | --- | --- | --- | --- | --- |
| No-probe baseline | 2339 | 8.108 ms | 7.64 ms | 241 | 503,847 | 0.934 |
| Hide fully blended meshes | 2364 | 8.000 ms | 7.56 ms | 208 | 502,469 | 0.930 |
| Debug unshaded | 3129 | 6.023 ms | 6.30 ms | 241 | 503,847 | 0.927 |
| Debug wireframe | 536 | 33.683 ms | 39.97 ms | 241 | 503,847 | 0.936 |
| Hide Structure | 4783 | 3.830 ms | 3.28 ms | 158 | 248,890 | 0.927 |
| Hide Props | 2883 | 6.993 ms | 6.40 ms | 128 | 281,152 | 0.924 |
| Hide Core | 2356 | 8.128 ms | 7.63 ms | 236 | 486,539 | 0.933 |
| Flat unshaded, every mesh | 3945 | 4.849 ms | 4.00 ms | 241 | 503,847 | 0.927 |
| Flat, Structure hidden | 6986 | 2.734 ms | 1.77 ms | 158 | 248,890 | 0.925 |
| Flat, Props hidden | 5256 | 3.647 ms | 2.66 ms | 128 | 281,152 | 0.931 |
| Flat unshaded, Structure only | 3296 | 5.804 ms | 5.14 ms | 241 | 503,847 | 0.930 |

Every row exited 0 at 1280x720. GPU clock stayed 680 MHz. Tonemap stayed 0.59 ms and glow 0.21 ms on the shaded runs and on both flat overrides. Debug unshaded and wireframe dropped tonemap to about 0.15 ms and printed no glow region, so those two are weaker probes of the color pass alone.

Hiding blended meshes is not the lever. The run hid 139 mesh instances whose every surface is alpha blended, including the light-shaft shader and the glass materials, and left 73 mixed meshes alone so a glass surface would not delete a building. That removed 33 draws and 1,378 primitives. p50 moved from 8.108 ms to 8.000 ms.

Primitive count is not the lever either. Structure is 254,957 of the primitives and hiding it removes 4.36 ms of the color pass. Props are 222,695 primitives and 113 draws, and hiding them removes 1.24 ms. Core is about 17,000 primitives and does not move the frame. Similar triangle counts, different time.

The same draws and the same 503,847 primitives get much cheaper when the materials do. One shared textureless unshaded material on all 1,215 meshes cuts the color pass from 7.64 ms to 4.00 ms and p50 from 8.108 ms to 4.849 ms. Godot's debug unshaded view still shows albedo and only reaches 6.30 ms in that region. Most of the material gap is the real material shader and its textures, not the lighting term by itself.

That material gap is concentrated on Structure. Flattening only those 340 meshes, still 241 draws and 503,847 primitives, cuts the color pass to 5.14 ms and p50 to 5.804 ms. The other meshes account for the rest of the drop from 5.14 ms to 4.00 ms.

About 4.0 ms remains after the trivial shader. It still tracks which meshes are on screen: hiding Structure under the flat shader takes the color pass from 4.00 ms to 1.77 ms, and hiding Props takes it to 2.66 ms. Per primitive those two groups are much closer once the materials are gone than they were with the real shaders. A fixed framebuffer cost at 720p would not fall when Structure is hidden. Hiding a group also uncovers whatever was behind it, so those deltas are the cost of drawing that group instead of the pixels behind it, not a pure layer time.

Wireframe is not a fill-rate result. It kept 241 draws and 503,847 primitives and made the color pass about 40 ms, with the GPU still full. Debug line drawing is a slower path here, so it does not measure bandwidth.

## What to change

The practical benchmark change is `--bench-shade flat-structure`, already in the demo patch and off unless that flag is passed. Against the 8.108 ms baseline it measures p50 5.804 ms and color-pass median 5.14 ms, at the same camera, resolution, draws, and primitives. The quality tradeoff is the building: those 340 meshes become one gray unshaded material, so Structure loses albedo, lighting, and alpha. Props, characters, and the rest of the shading stay. Flattening every mesh reaches p50 4.849 ms and also throws away those materials. Hiding Structure reaches p50 3.83 ms and removes the building.

This is scene-level tuning of the Structure materials. It does not point at a Turnip patch or a Godot pass change. The GPU stayed at 680 MHz and about 93 percent busy while a material override on the same draws made the frame faster, which is shader and texture work, not a driver stall that ignores the scene. The transparent draws inside `Render Opaque + Transparent` are cheap, so splitting that timestamp is not the next win. A Godot change would matter only if the mobile shader sampled textures the Structure materials do not ask for, and these runs do not show that. No issue was filed.
