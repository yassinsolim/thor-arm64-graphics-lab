# Turnip A740 sparse image RFC, Oct 2, 2026

Branch prepared, merge request not opened. No Freedesktop GitLab credential is stored on this machine. Safe to open as an RFC once that login exists. Not safe to ask for a merge.

Branch: `turnip-rfc-a740-sparse-image` at `7c48e0a52517fed7ca11dd4293e29e7c3b625733`, parent `ea47b35cf639176f5e76253363eff70f8ff6e40d`, in `$HOME/src/mesa-main-rfc` on the device. The commit is only those six freedreno files. Build products and CTS logs are untracked.

Patch: `mesa/mesa-main-9046ec144-turnip-a740-sparse-image-rfc.patch`
Written against Mesa main `9046ec144bbb18a2cfbb7719adf19303b710a2c3`. It applied cleanly onto the main fetched for the build, `ea47b35cf639176f5e76253363eff70f8ff6e40d` (`radv: move game performance tuning to a separate drirc file`).
Earlier patch, the one first CTS tested: `mesa/mesa-26.2.3-turnip-a740-sparse-image-rfc.patch` on Mesa 26.2.3 `31e9a6b2e`.

## Decision: X1-85 stays gated

Adreno X1-85 (`0xffff43050c01`) is in its own `add_gpus` block with the same A740 gen2 programming and without `supports_sparse_image_2d`. Sparse 2D residency was only run on FD740. The flag stays on the tested ids: deprecated `GPUId(740)`, `0x43050a01`, and `0xffff43050a01`. `a7xx_gen3` still sets the flag, so A750 and later keep the sparse behavior they already had.

## What the port keeps

- `sparseResidencyImage2D` requires `has_sparse_prr` and `supports_sparse_image_2d`.
- `sparseResidency2Samples`, `sparseResidency4Samples`, and `sparseResidency8Samples` also require `ubwc_all_formats_compatible`, so they stay off on A740.
- Mutable format lists that would force a linear tile are rejected from sparse image creation when `ubwc_all_formats_compatible` is false. The image-init path uses the same helper, so the old `TILE6_3` assertion is not the rejection path.
- `VkPhysicalDeviceImageFormatInfo2` has no sample-count field. An earlier draft checked `info->samples` and did not compile. Multisample sparse residency stays gated by the feature bits only. That matches the 26.2.3 patch.

## Build

Isolated tree on the device, not a system install. Ubuntu container, GCC 15.2.0, Meson 1.12.1, Ninja. Options: Vulkan freedreno only, gallium empty, platforms empty, `freedreno-kmds=msm`, llvm disabled. Prefix `install-turnip-rfc`. The host ICD json points at that `libvulkan_freedreno.so`. System Mesa was not replaced.

`ninja` completed. Host-side checks from that tree: `fd6_layout` exited 0, `ir3_delay_test` reported 12 passes.

## Evidence

VK-GL-CTS 1.4.6.1 `5c8aae22885448d70a2873e94a93b24b49505c32`, Adreno 740 (`vendorID 0x5143`, `deviceID 0x43050a01`, Turnip).

Mesa 26.2.3, preserved as the old run:

```text
Focused image_sparse_residency 2D:
  Passed: 186
  Failed: 0
  Not supported: 2592

Broad focused sparse 2D, arrays, mutable images, aliasing, mip tails,
shader intrinsics, rebind, block shapes, and queues:
  Passed: 3073
  Failed: 0
  Not supported: 5066
```

Same two caselists, rerun on the main port (`ea47b35` plus this patch), isolated ICD:

```text
Focused image_sparse_residency 2D:
  Passed: 186
  Failed: 0
  Not supported: 2592

Broad focused list (8139 cases):
  Passed: 3073
  Failed: 0
  Not supported: 5066
```

Case-by-case comparison of the broad list against the 26.2.3 qpa: 0 missing cases, 0 status changes. `dEQP-VK.sparse_resources.image_sparse_residency.mutable.2d.r32_sint_r32_uint_r16g16_sint` is NotSupported on both. No test was waived. This is not full CTS and not a conformance claim.

Logs on the device, left in place: `~/src/mesa-main-rfc/cts-sparse-residency-2d-ea47b35.qpa` and `~/src/mesa-main-rfc/cts-sparse-2d-focused-ea47b35.qpa`. The 26.2.3 logs were not overwritten.

## Commit message

```text
turnip: RFC single-sample sparse images on a740

A740 has PRR and single-sample sparse 2D residency, but it does not have
A750's ubwc_all_formats_compatible bit. Gate sparseResidencyImage2D on a
separate flag, leave multisample sparse residency on the A750 bit, and
reject mutable format lists that would force a linear sparse image.

A focused VK-GL-CTS 1.4.6.1 run of this approach on Mesa 26.2.3 and
Adreno 740 reported 3073 passes, 0 failures, and 5066 NotSupported.
The same caselist on this main port matched that result case by case.
That run is not full CTS. Adreno X1-85 stays gated.
```

## MR description

```text
RFC: single-sample sparseResidencyImage2D on Adreno 740

A740 can do single-sample sparse 2D images. It cannot claim A750's mutable UBWC behavior. This does not enable sparseResidency2Samples, sparseResidency4Samples, or sparseResidency8Samples on A740.

`supports_sparse_image_2d` is set for a7xx_gen3, which already exposed sparse images through `ubwc_all_formats_compatible`, and for the tested FD740 ids (`GPUId(740)`, `0x43050a01`, `0xffff43050a01`). Adreno X1-85 (`0xffff43050c01`) is a separate info block and does not set the flag. It has not been CTS tested.

Mutable format combinations that `tu_image_init` would force to linear tiling are rejected up front with `VK_ERROR_FORMAT_NOT_SUPPORTED`. The old failure was an assertion that sparse residency required `TILE6_3`.

Main rejected every sparse-residency format query unless `ubwc_all_formats_compatible` was set. This RFC replaces that check with `supports_sparse_image_2d`. Multisample sparse residency stays on the A750 flag. The format-query struct has no sample count, so there is no separate query-time sample check.

Built with GCC 15.2.0. Tested on Adreno 740, VK-GL-CTS 1.4.6.1 (`5c8aae22885448d70a2873e94a93b24b49505c32`):

The Mesa 26.2.3 run of the broad focused list (sparse 2D, arrays, mutable images, aliasing, mip tails, shader intrinsics, rebind, block shapes, and queues) was 3073 passed, 0 failed, 5066 NotSupported. The same caselist on this main port matched those statuses case by case, including NotSupported for `dEQP-VK.sparse_resources.image_sparse_residency.mutable.2d.r32_sint_r32_uint_r16g16_sint`. No tests were skipped or waived.

Not done: full Vulkan CTS, vkd3d-proton tiled-resource tests, review of the rejected typeless format families, an A740 CI job, and any run on X1-85. Please do not merge this as a conformance change.
```

## Still true before a merge

1. Full Vulkan CTS, tiled-resource tests, typeless-format review, and an A740 CI job.
2. X1-85 stays off until that chip has its own run.
3. Rebase onto whatever main is on the day it is opened. It applied to `ea47b35` on Oct 2, 2026.
