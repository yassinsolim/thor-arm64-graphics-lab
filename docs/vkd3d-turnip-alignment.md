# vkd3d-proton Turnip 64 KiB committed-buffer VA, Oct 2, 2026

Draft only. Do not submit. The test ran on the device. It does not prove the bug, and the non-Turnip control fails the test as written.

Test patch: `diagnostics/vkd3d-proton-e9dfbdc-turnip-bda-alignment-test.patch` on vkd3d-proton `e9dfbdc`. It adds `test_committed_vs_heap_buffer_va_alignment`. The test creates one committed default-heap buffer and one placed buffer on a buffer-only heap, then compares `GetGPUVirtualAddress` alignment at 64 KiB. It requires the placed VA to be aligned on every driver. The lavapipe run below shows that requirement does not hold. The committed-buffer check is `bug_if` only when the device extension reports `VK_DRIVER_ID_MESA_TURNIP`. The default Windows test build stubs `get_driver_properties()`, so the test asks `ID3D12DeviceExt` itself.

Built on the device in the isolated container with MinGW GCC 13, `build-win64.txt`, `enable_tests=true`. `tests/d3d12_resource.c` compiled with no warning, and `tests/d3d12.exe` linked. The binary is an x64 PE. It was run under the stock x86_64 Wine inside FEX, prefix `$HOME/src/vkd3d-bda-prefix`, which is not a game prefix. `WINEDLLOVERRIDES=d3d12,d3d12core=n`. Implicit Vulkan layers were disabled.

This is only the alignment question. It is not `WriteBufferImmediate`, not a small invalid address, and not a title-specific command list.

## What the public source shows

vkd3d-proton `libs/vkd3d/memory.c`, `d3d12_device_aligns_bda_64k`: the function returns false only for `VK_DRIVER_ID_MESA_TURNIP`. The comment says Turnip is the driver that does not naturally give 64 KiB buffer device addresses, and that an extension should express it.

The 64 KiB pad in `vkd3d_memory_allocation_init` runs only when all of these are true:

- `VK_VALVE_buffer_device_address_allocation_alignment` feature is off
- `VKD3D_ALLOCATION_FLAG_REQUIRE_ALIGNED_GPU_ADDRESS` is set
- `d3d12_device_aligns_bda_64k` is false
- the allocation is not host-imported and has no `pNext`
- `memory_requirements.alignment` is at least `D3D12_DEFAULT_RESOURCE_PLACEMENT_ALIGNMENT` (64 KiB)

`libs/vkd3d/heap.c` sets `REQUIRE_ALIGNED_GPU_ADDRESS` for a heap that does not deny buffers.

`d3d12_resource_create_committed` for a buffer calls `vkd3d_allocate_heap_memory` with a zeroed `vkd3d_allocate_heap_memory_info`. `extra_allocation_flags` stays 0. `vkd3d_allocate_heap_memory` adds `VKD3D_ALLOCATION_FLAG_GLOBAL_BUFFER` when buffers are allowed. It does not add `REQUIRE_ALIGNED_GPU_ADDRESS`.

So a committed buffer skips the pad. A buffer-capable `CreateHeap` does not.

Mesa main `tu_GetDeviceBufferMemoryRequirements` still asks for 64-byte alignment on a normal buffer and the CPU page size on a sparse-binding buffer. `VK_VALVE_buffer_device_address_allocation_alignment` is exposed only when `has_iova_align` is true. On the MSM DRM path, `has_iova_align` is `has_set_iova`. If that is false, vkd3d takes the pad path above, and committed buffers miss it. If the feature is true, vkd3d instead passes `VkBufferDeviceAddressAlignmentAllocateInfoVALVE` with 64 KiB and does not use the pad.

## Device result, Oct 2, 2026

The x86_64 PE cannot dlopen the aarch64 CTS ICD. The run used an x86_64 rebuild of the same Mesa tree (`ea47b35` plus the local sparse-image commit), configured with `-Dplatforms=x11` so Wine can see a native surface and advertise `VK_KHR_win32_surface`. That binary is not the CTS driver. `VK_ICD_FILENAMES` pointed at `freedreno_icd.x64.json` only.

`vulkaninfo` on that ICD:

- device: Turnip Adreno (TM) 740
- `driverID`: `DRIVER_ID_MESA_TURNIP`
- `driverInfo`: Mesa 26.3.0-devel
- `apiVersion`: 1.4.363
- `VK_VALVE_buffer_device_address_allocation_alignment`, revision 1, is exposed

That extension is enabled only when `has_iova_align` is true. On the MSM path `has_iova_align` is `has_set_iova`. So `has_iova_align` is true on this A740. vkd3d then sends `VkBufferDeviceAddressAlignmentAllocateInfoVALVE` at 64 KiB and does not take the pad path. This device cannot show the missing `REQUIRE_ALIGNED_GPU_ADDRESS` bug.

`VKD3D_TEST_FILTER=test_committed_vs_heap_buffer_va_alignment`. Log: `$HOME/src/vkd3d-bda-run/turnip-x64-alignment2.log`.

```text
committed VA 0x1000e0000, placed VA 0x1000f0000, turnip 1
Fixed bug: Committed buffer GPU VA 0x1000e0000 is not 64 KiB aligned.
7 tests executed (0 failures, 0 successful todo, 0 skipped, 0 todo, 1 bugs).
exit 0
```

`0x1000e0000` and `0x1000f0000` both have low 16 bits 0, so both are 64 KiB aligned. `turnip 1` means the test saw `VK_DRIVER_ID_MESA_TURNIP`. "Fixed bug" means the `bug_if(turnip)` check passed. The process did not fail.

## Lavapipe control

Same exe, guest ICD `/usr/share/vulkan/icd.d/lvp_icd.x86_64.json` (`/usr/lib/libvulkan_lvp.so`). Log: `$HOME/src/vkd3d-bda-run/lvp-alignment.log`.

`vulkaninfo`: llvmpipe (LLVM 22.1.8, 256 bits), `DRIVER_ID_MESA_LLVMPIPE`, Mesa 26.2.0. The VALVE alignment extension is not in the extension list.

```text
committed VA 0x7fffb37ff000, placed VA 0x7fffb380f000, turnip 0
Test failed: Placed buffer GPU VA 0x7fffb380f000 is not 64 KiB aligned.
Test failed: Committed buffer GPU VA 0x7fffb37ff000 is not 64 KiB aligned.
8 tests executed (2 failures, 0 successful todo, 0 skipped, 0 todo, 0 bugs).
exit 1
```

Both addresses end in `0xf000`. They are 4 KiB aligned and 64 KiB apart, and neither is 64 KiB aligned. `d3d12_device_aligns_bda_64k` returns true for every driver that is not Turnip, so vkd3d does not pad lavapipe. This llvmpipe does not align on its own. The test's unconditional placed-VA check fails on the control. That is a test bug, not evidence for the Turnip committed-buffer path.

## Why this is not ready to send

The source still shows that a committed buffer does not set `REQUIRE_ALIGNED_GPU_ADDRESS`. On this A740 the VALVE feature is on, and both measured VAs are 64 KiB aligned, so the missing flag is not visible. The lavapipe run does not pass. Do not open the issue or the PR. Do not paste the old "not executed" wording.

A later draft would need a Turnip device where `has_iova_align` is false, and a control where the placed VA is actually 64 KiB aligned. This run is not that.
