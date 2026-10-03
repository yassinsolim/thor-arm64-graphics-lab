# vkd3d-proton command-list timestamps

Patch: `diagnostics/vkd3d-proton-7f0c30ad-pass-timestamps.patch`
Source pin: vkd3d-proton `7f0c30ad3c8f28dfe47c34bb897b972e2d1ca724`
Thor tree: `~/tfd-perf-2026-10-01/vkd3d-proton-7f0c30ad`
Summary log: `~/tfd-perf-2026-10-01/pass-ts-summary.txt`
Raw capture: `~/tfd-perf-2026-10-01/pass-ts.csv` (strip NUL padding before parsing)
Stale boot capture, before the host query reset: `~/tfd-perf-2026-10-01/pass-ts-stale-boot.csv`

The log is inactive unless `VKD3D_PASS_TIMESTAMPS` is set to a path. Scope stays `list` unless `VKD3D_PASS_TS_SCOPE=pass`. The worker reads timestamp queries with availability bits and does not call `vkQueueWaitIdle` or wait on a fence in the submit path. After a successful read it host-resets that query range so the next user cannot observe the previous result.

Clock check on this Adreno 740 Turnip: `timestampPeriod` 52.083332 ns (19.2 MHz), 48 valid bits, `VK_EXT_calibrated_timestamps` not exposed. Standalone test: `~/tfd-perf-2026-10-01/a740-timestamp-test`.

ARM64X rebuild uses the existing `localhost/vkd3d-build` container, meson native file `~/tfd-perf-2026-10-01/build-native.txt`, and llvm-mingw mounted at `/work/toolchain`. `enable_profiling` stays off. The game loads the prefix copies at `compatdata/2074920/pfx/drive_c/windows/system32/d3d12core.dll`, not the stock Proton file, so a capture has to replace that prefix file and the stock file has to be copied back afterward.

Two recording bugs dropped every list on the first run. `Reset` begins the Vulkan command buffer and then clears the timestamp state. Tiler suspend ends that command buffer and may not submit the fixup, so the end timestamp has to be written on the original buffer first. Both are in the patch.
