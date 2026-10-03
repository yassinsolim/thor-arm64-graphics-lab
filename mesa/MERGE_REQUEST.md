# RFC: single-sample sparseResidencyImage2D on Adreno 740

Patch: `mesa-main-9046ec144-turnip-a740-sparse-image-rfc.patch`

Apply it on Mesa main `ea47b35cf639176f5e76253363eff70f8ff6e40d` or later. It was written against `9046ec144bbb18a2cfbb7719adf19303b710a2c3` and applied cleanly there. The 26.2.3 patch is the earlier CTS run, not the branch to open.

Suggested commit message:

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

Suggested merge request:

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
