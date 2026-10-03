# The First Descendant on Armada ARM64, Oct 1, 2026

## Result

The First Descendant launches under Proton Experimental ARM64 on the AYN Thor and reaches
the real game binary, `M1-Win64-Shipping.exe`. Stock Turnip first stops at the game's own
hardware check, before any anti-cheat runs:

```text
This game cannot be run due to insufficient hardware support.
If you see this message even though your system meets the requirements,
it might be caused by an outdated Windows version, outdated graphics drivers, or an issue with third-party OSDs(On-screen Display).
```

This is not an anti-cheat kick. During that hardware-dialog stop, Easy Anti-Cheat never ran and BlackCipher was never spawned. The game process stayed alive for about 6.5 minutes behind the modal `Message` dialog, using little CPU, until it was stopped. No crash dump was written, and `M1/Saved/Logs` stayed empty.

The isolated CTS-tested Turnip sparse-image patch removes that hardware dialog and reaches
a 1920x1080 D3D12 swapchain. Startup then fails because the caller passes breadcrumb slot
offsets `0x600` and `0x604`, rather than full GPU virtual addresses, to
`ID3D12GraphicsCommandList2::WriteBufferImmediate`. vkd3d correctly invalidates the
command list, and `Close` returns `E_INVALIDARG`.

Warn-only vkd3d instrumentation proves that no sub-64-KiB VA was returned by
`GetGPUVirtualAddress`. A separate x64 test passes valid 64-bit addresses through the same
FEX to ARM64X boundary. Caller-stack attribution then places the call inside
`M1-Win64-Shipping.exe` at RVA `0x55ab13f`, a marker wrapper for
`ID3D12GraphicsCommandList2::WriteBufferImmediate`. The shipping binary pairs that path
with Unreal's `r.GPUCrashDebugging` switch and the literal token `nogpucrashdebugging`.

One launch with the engine switch `-nogpucrashdebugging` produced no `0x600` or `0x604`
writes. The 1920x1080 swapchain stayed up and presented. The next graphics boundary is a
compute pipeline that asks for wave size 32 while Turnip supports 64 through 128. Before
that process was stopped, `NGService64.exe` and `BlackCipher64.aes` had started. No
Easy Anti-Cheat process appeared.

No hosts, network, anti-cheat binaries, validation, architecture identity, or server
communication were changed. Instrumented DLLs, the patched driver, and copied compatdata
were isolated per process. Proton, game files, anti-cheat files, and system packages were
not replaced. The exact Armada launch option was restored.

## Launch chain

Stock launch via `steam://rungameid/2074920` at 12:58:51:

| Time | Stage |
| --- | --- |
| 12:58:52 | Steam install script: `NGService64_Install.bat`, plus the bundled `EasyAntiCheat_EOS_Setup.exe uninstall 954200fbf510465d963850369d5cc878` |
| 13:00:28 | `Game process added`, task `Completed` |
| about 13:00:30 | `TheFirstDescendant.exe -steam` (Proton `steam.exe` wrapper) |
| about 13:00:36 | `M1-Win64-Shipping.exe M1 -steam` starts, peaks near 963 MB RSS |
| shortly after | `Message` window, class `steam_app_2074920`, owned by the shipping process, shows the hardware-support error |
| 13:07:00 | Stopped by the tester, `Game process removed` |

Anti-cheat status:

- Easy Anti-Cheat: not used at launch. The install script uninstalls the EAC product, and no EAC process or `AppData/Roaming/EasyAntiCheat` log appeared.
- BlackCipher / Nexon Game Security: the install script copied `NGService64.exe` into `C:\ProgramData\Nexon\NGS` and wrote an encrypted `NGService.log`. `BlackCipher64`, `BlackCall64`, and a running NGService process never appeared. The game fails its hardware check before starting game security.
- Game process: reached and stayed resident, blocked on the error dialog.

At the error, the shipping process had 32 threads, all sleeping in `ntsync_schedule`, `futex_do_wait`, or `poll`. CPU time grew only about 0.2 s per 10 s.

## Diagnostic launch

A second stock launch at 13:16 used temporary launch options, then restored the original string:

```text
PROTON_LOG=1 VKD3D_DEBUG=warn VKD3D_SHADER_DEBUG=warn /usr/libexec/armada/armada-game-launch %command%
```

Steam recorded that command on `Game process added`. The same hardware dialog appeared. The process was stopped once the dialog was up. `M1/Saved/Logs` is still empty, so the game did not write its own reason.

vkd3d-proton 3.1.0 (build `7f0c30ad3c8f28d`) and DXVK 3.1.1 (aarch64) did create a D3D12 device:

```text
info:  Found device: Turnip Adreno (TM) 740 (turnip Mesa driver 26.2.3)
info:    Skipping: Software driver
info:vkd3d-proton:vkd3d_memory_info_decide_hvv_usage: Topology: UMA-like topology.
info:vkd3d-proton:d3d12_device_caps_init_shader_model: Enabling support for SM 6.6.
```

llvmpipe was enumerated and skipped. There were zero `vkd3d: err` lines and no feature-level rejection. Shader model 6.6 was enabled. `VK_EXT_descriptor_buffer` and `VK_EXT_mutable_descriptor_type` were detected. `VK_EXT_device_generated_commands` was skipped because not every pipeline stage supports it. That skip is not a device-creation failure.

The prefix advertises Windows 10 build `19045` (`CurrentBuild` / `CurrentBuildNumber`), with `DisplayVersion` labeled `21H1`. The published minimum is Windows 10 x64 20H2 (build 19042) and DirectX 12. The advertised build is newer than that minimum, so this is not an outdated-OS rejection.

The only adapter query that failed, immediately before device init, was:

```text
warn:  DxgiAdapter::QueryInterface: Unknown interface query
warn:  f0db4c7f-fe5a-42a2-bd62-f2a6cf6fc83e
```

That IID is `IDXCoreAdapter`. DXVK does not implement it, so the game cannot read DXCore adapter properties (driver version, hardware ID, dedicated memory) through that interface. The dialog text points at outdated drivers when the requirements are otherwise met. This is the best log-backed candidate. Confidence is medium: the query fails, and the dialog still appears, but the game never prints which predicate fired.

Not the trigger, from this log:

- D3D12 device creation on Turnip succeeded.
- Shader model 6.6 was enabled. This is not a shader-model cap failure.
- No vkd3d feature-level failure was logged.
- The advertised Windows build meets 20H2.

Turnip gaps that vkd3d did not cite while starting this process: `shaderFloat64` is false, `VK_EXT_mesh_shader` is absent, `uniformAndStorageBuffer16BitAccess` is false, and `VK_KHR_ray_tracing_pipeline` is absent (`VK_KHR_ray_query` is present). Nexon's site also says integrated GPUs are not suitable and asks for 4 GB of video memory. vkd3d logged a UMA-like topology but did not log the dedicated-memory value returned to the game, so a VRAM or integrated-GPU rejection is possible and unproven.

## Unreal log launch

A third launch at 13:23:40 used this temporary option, then restored the original wrapper:

```text
WINEDEBUG=-all PROTON_LOG=1 /usr/libexec/armada/armada-game-launch %command% -log
```

Steam's `Game process added` line at 13:23:46 contains `WINEDEBUG=-all`, the armada wrapper, and `-log`. Proton recorded the game command as `TheFirstDescendant.exe -steam -log`, with effective `WINEDEBUG=-all`. No `VKD3D_FEATURE_LEVEL` and no vendor override were set. `ShowEula` did not return. `ShowInterstitials` continued on its own. The install script still ran (3 steps).

| Time | Stage |
| --- | --- |
| 13:23:40 | `steam://rungameid/2074920` |
| 13:23:41 | Install script evaluator, 3 steps |
| 13:23:46 | `Game process added`, task `Completed` |
| 13:23:51 | `Game process updated` |
| 13:24:00 | `Game process updated`; `CrashReportClient.ini` rewritten |
| about 13:24:12 | Same `Message` window, class `steam_app_2074920` |
| 13:28:21 | `steam://forceexitapp/2074920` |
| 13:28:24 | `Game process removed` after `wineserver -k` on prefix 2074920 |

The dialog was identified by window title `Message` and class `steam_app_2074920`. A new pixel capture was not taken. The string in the shipping binary that matches the earlier capture is the generic hardware dialog, not the separate SM6 dialog that also exists in that binary:

```text
DirectX 12 with Feature Level SM6 is not supported on your system. Try running without the -sm6 command line argument.
```

`M1/Saved/Logs` stayed empty for the whole time the dialog was up (polled through 13:28). The install tree gained no new log. The launcher is Unreal's `BootstrapPackagedGame` and names `M1\Binaries\Win64\M1-Win64-Shipping.exe`. `-log` reached that launcher. The shipping process still did not create a log file, so this build did not record the predicate. The Proton log is 12220 bytes and is saved as `~/tfd-proton-2026-10-01-1323.log`. It repeats the 13:16 graphics result and adds nothing from the game itself: Turnip device created, llvmpipe skipped, SM 6.6 enabled, UMA-like upload topology, zero `vkd3d` errors, and the same unknown `IDXCoreAdapter` query (`f0db4c7f-fe5a-42a2-bd62-f2a6cf6fc83e`). DXVK's `Game:` lines are `xalia.exe` and `M1-Win64-Shipping.exe` only. No EasyAntiCheat or NGService process appears there.

## What the check is not

The exact comparison is still not printed. These three candidates are ruled out by this launch plus read-only DXGI/DXCore and Vulkan inspection:

- Shader model / feature level. vkd3d enabled SM 6.6, logged no feature-level error, and the dialog that appeared is not the SM6 string above.
- Dedicated VRAM below the published 4 GB floor, if the game reads `DXGI_ADAPTER_DESC.DedicatedVideoMemory`. Turnip exposes one heap, `MEMORY_HEAP_DEVICE_LOCAL_BIT`, size 12177113088 bytes (11.34 GiB), budget 9.52 GiB. DXVK 3.1.1 commit `25ca63f17f34bdc` sets dedicated memory from the largest device-local heap and, when there is no separate system heap, copies that size into shared memory. The 512 MiB integrated carve-out runs only when that adapter is linked to a discrete GPU. This machine has one GPU, so the reported dedicated size stays about 11.34 GiB, above 4 GB. System RAM is 15856460 kB.
- A missing Vulkan device. The D3D12 device is created on Turnip. Mesh shader, `shaderFloat64`, 16-bit storage, and the ray-tracing pipeline remain absent, and vkd3d still does not cite them at startup.

## What can still fail the check

Two reported properties match the dialog and are not disproven:

- DXCore driver properties. `IDXCoreAdapter` is still the only failed adapter query. DXVK returns `E_NOINTERFACE` for that IID, so driver version, hardware ID, and DXCore dedicated-memory properties are not available. The dialog text names outdated graphics drivers. Vendor reported through DXGI is the real Vulkan identity: vendor `0x5143`, device `0x43050a01`, name `Turnip Adreno (TM) 740`, type `PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU`. DXGI flags stay `DXGI_ADAPTER_FLAG3_NONE`. A vendor or driver-version allow-list would fail closed when DXCore is missing. The game never prints that comparison.
- D3D12 UMA. vkd3d-proton `7f0c30ad` (2026-09-17) is later than the 2026-02-13 fix that ignores `LAZILY_ALLOCATED` memory types in `d3d12_device_is_uma`. The other three Turnip types are host-visible. One of them is host-visible and not host-coherent (`0x000b`). That function therefore reports `UMA = true` and `CacheCoherentUMA = false`. Nexon says integrated GPUs are not suitable. The upload-path log line `Topology: UMA-like topology` is the same device, and it is not itself the D3D12 architecture bit. The game did not log a UMA rejection.

Confidence at that point: the predicate string was not in a log. The failed check was not SM 6.6 as a vkd3d cap, and not a sub-4 GB DXGI dedicated-memory report. Static inspection below names the branch.

## Startup branch

Read-only PE inspection of the installed `M1-Win64-Shipping.exe` (image base `0x140000000`). Nothing was patched, hooked, or launched for this pass.

The generic dialog is one wide string, VA `0x14a3bb950`, next to the key `RequiredDX12.Detailed`. Its only code reference is `0x14639de15`, inside the pdata function `0x14639ddb0`. That function is Unreal's Windows Dynamic RHI failure reporter. The RHI names it selects are `D3D11RHI`, `D3D12RHI`, `VulkanRHI`, and `OpenGLDrv`. The D3D12 arm is the generic dialog. The D3D11, Vulkan, and OpenGL arms use the stock engine sentences. A separate function, `0x14639dbd0`, shows the stock SM6 sentence only when a forced-feature-level optional is set, the RHI value is 1 (`D3D12RHI`), and the feature-level dword is 4. The caller at `0x14639ee04` reaches the generic dialog only when that SM6 function returns false. The launch did not pass `-sm6`, and the window text was the generic dialog, so the SM6-only arm did not run.

The generic arm runs when the D3D12 supported-feature-level list is empty (array count at the object is 0). That is `IsSupported` failing for the targeted D3D12 feature level, with D3D12 forced, so the engine does not fall through to D3D11. `bUseD3D12InGame` and `PCD3D_SM6` are live strings in this binary. `PCD3D_SM5` is also present, but this boot did not take a D3D11 fallback.

vkd3d-proton's feature-level ladder, in `d3d12_device_caps_init_feature_level`, stops at 11_1 unless tiled resources are at least tier 2. Tier 2 requires `sparseResidencyImage2D`. On this Turnip device that feature is false. The other inputs for tier 2 are already true: `sparseBinding`, `sparseResidencyBuffer`, `sparseResidencyAliased`, `residencyStandard2DBlockShape`, `residencyNonResidentStrict`, `shaderResourceResidency`, `shaderResourceMinLod`, `filterMinmaxSingleComponentFormats`, and a queue with `QUEUE_SPARSE_BINDING_BIT`. `residencyAlignedMipSize` is false, so it would not cap the tier at 1. `sparseResidencyImage3D` is also false, which caps the tier at 2, and tier 2 is enough for feature level 12_0.

Feature level 12_1, which this engine generation treats as SM6, additionally needs rasterizer-ordered views and conservative rasterization tier 1. Both are already available here: `VK_EXT_fragment_shader_interlock` reports pixel and sample interlock, and conservative rasterization evaluates to tier 2 (`degenerateTrianglesRasterized` is true, `fullyCoveredFragmentShaderInputVariable` is false). The boot log never printed `DX Ultimate supported!`, which vkd3d prints only for feature level 12_2. 12_2 stays blocked by mesh shaders and raytracing tier, and SM6 does not require 12_2.

So the failed public property is D3D12 feature level 12_1 / SM6, because tiled resources stay at tier 0 while `sparseResidencyImage2D` is false. The device is still created, and shader model 6.6 is still enabled. Those are necessary and not sufficient.

The `IDXCoreAdapter` query is not this branch. The IID is absent from the shipping exe. It is present in the game's Agility `D3D12/x64/D3D12Core.dll`, and vkd3d's `d3d12_get_adapter` probes that IID and then uses `IDXGIAdapter` when the probe fails. The probe is logged and the device is created afterward. UMA is reported by `d3d12_device_is_uma`, and `MinIntegratedMemorySizeBucket` is a config key in a different function. Neither comparison is the dialog arm that ran.

## Mesa sparse residency investigation

The installed package is `mesa-vulkan-drivers-26.2.3-1.fc44.armada.aarch64`, built from `mesa-26.2.3-1.fc44.armada.src.rpm`. The exact Mesa 26.2.3 source and upstream main at commit `31e9a6b2e95e30d84bf3177d1f497d063e59b6b2` use this gate in `src/freedreno/vulkan/tu_device.cc`:

```cpp
features->sparseResidencyImage2D = pdevice->has_sparse_prr &&
   pdevice->info->props.ubwc_all_formats_compatible;
```

Adreno 740 uses the `a7xx_gen2` device template. Adreno 750 uses `a7xx_gen3`, which is the first template to set `ubwc_all_formats_compatible = true`. The dev-info comment says A750+ added a hardware flag for interpreting UBWC and fast-clear data across mutable format casts. Current upstream still excludes A740.

The sparse image implementation itself is substantial. Commit `918e25e158cda49b9e258e1c4a84d761711f1c20`, Mesa MR `!32671`, emulates Vulkan's standard 64 KiB sparse tiles with native 4 KiB macrotiles, including bank swizzling, mip tails, aliasing, sparse shader residency checks, and VM_BIND ordering. Its commit message explicitly names D3D tiled resources tier 2 and D3D feature level 12_0. Related commits include `ae532344` for sparse FDL layouts, `70cf4008` for sparse shader checks, `655934ee` for `shaderResourceResidency`, and `de60f2ff` for `shaderResourceMinLod`.

No upstream A740 sparse-image issue, merge request, or A740 CI suite was found. No public A740 programming document establishes that its mutable tiled-format behavior matches A750. Mesa's per-generation property and the CTS result below are therefore the strongest available hardware boundary.

The kernel path is already present. The Thor uses MSM VM_BIND and PRR, and stock Turnip reports `sparseResidencyBuffer = true`. A kernel or FEX change is not the missing first step.

Sparse images disable UBWC in `tu_image.cc`, but the A750 property is not merely an unrelated proxy. It also controls mutable-format handling and whether Turnip can keep an image tiled when views reinterpret the format. That became visible in the conformance experiment below.

### Isolated A740 experiment

A separate Mesa 26.2.3 build introduced a dedicated `supports_sparse_image_2d` property rather than falsely setting `ubwc_all_formats_compatible`. It enabled that property only for the A740 entry. Multisample sparse residency remained disabled on A740, while A750 retained its existing behavior.

The build succeeded without replacing any system library. Loading only the isolated ICD produced:

```text
sparseResidencyImage2D       = true
sparseResidency2Samples      = false
sparseResidency4Samples      = false
sparseResidency8Samples      = false
sparseResidencyAliased       = true
residencyStandard2DBlockShape = true
residencyAlignedMipSize      = false
residencyNonResidentStrict   = true
```

VK-GL-CTS 1.4.6.1 was built separately. Three representative `rgba8` sparse-residency cases passed. A broader 8,139-case sparse 2D list then produced 768 passes and 744 legitimate `NotSupported` results before aborting on:

```text
dEQP-VK.sparse_resources.image_sparse_residency.mutable.2d.r32_sint_r32_uint_r16g16_sint
```

Turnip hit its own assertion in `tu_image.cc`:

```text
Assertion `!(image->vk.create_flags & VK_IMAGE_CREATE_SPARSE_RESIDENCY_BIT) ||
           tile_mode == TILE6_3' failed.
```

For this mutable image, the A740 path in `tu_image_init` sees an incompatible format reinterpretation and sets `force_linear_tile`. Sparse residency requires `TILE6_3`, so image creation reaches the assertion. A750 takes the `ubwc_all_formats_compatible` mutable path instead.

This is bounded evidence that A740 support is partial, not merely disabled. Basic single-sample sparse 2D images, arrays, mappings, and residency work, but at least one required mutable-format path was not rejected correctly. Advertising the feature with only a device gate would be non-conformant.

### Turnip implementation attempt

The follow-up patch implements the smallest truthful behavior:

1. Add `supports_sparse_image_2d` separately from `ubwc_all_formats_compatible`, enable it for A750+ and the A740 device entry, and retain the existing PRR requirement.
2. Keep `sparseResidency2Samples`, `sparseResidency4Samples`, and `sparseResidency8Samples` false on A740.
3. Move the existing mutable-format linear-layout checks into a shared helper.
4. In `tu_GetPhysicalDeviceImageFormatProperties2`, reject a sparse mutable image when the same format-list path would force `tu_image_init` to use linear tiling. This returns `VK_ERROR_FORMAT_NOT_SUPPORTED` before image creation instead of creating an invalid sparse linear image or suppressing the assertion.

The patch does not alter the assertion, claim A750's UBWC format-casting capability, skip tests, or advertise multisample sparse residency. It is preserved at:

```text
mesa/mesa-26.2.3-turnip-a740-sparse-image-rfc.patch
SHA-256 8d23938829c8e5a34c18bf5242a33de0fb147fe2e5037baea1382d7bef908059
```

An isolated Mesa 26.2.3 build succeeded. The exact prior assertion case now returns `NotSupported` at the Vulkan format query, as required for a combination the driver cannot keep tiled:

```text
dEQP-VK.sparse_resources.image_sparse_residency.mutable.2d.r32_sint_r32_uint_r16g16_sint
NotSupported (The image format does not support sparse+mutable operations)
```

VK-GL-CTS 1.4.6.1 commit `5c8aae22885448d70a2873e94a93b24b49505c32` then produced:

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

The `NotSupported` results are format, queue, or mutable-format combinations that the format-property query rejects. No test was waived or skipped, and no assertion recurred. This focused result is sufficient for an RFC and isolated runtime testing, but not yet for a system-wide install or a Vulkan conformance claim. Full Vulkan CTS, vkd3d-proton tiled-resource tests, review of the rejected typeless format families, and an A740 CI job remain required upstream.

### Isolated game test

The validated driver was copied to a non-system directory and referenced only through temporary per-process `VK_ICD_FILENAMES` and `VK_DRIVER_FILES` values. The launch option retained `/usr/libexec/armada/armada-game-launch %command%`. No system library was replaced.

Two launch attempts did not reach Proton's game command. In both, Steam completed the three-step install-script evaluator and then stopped at:

```text
GameAction [AppID 2074920, ActionID 1] : LaunchApp changed task to ShowInterstitials with ""
GameAction [AppID 2074920, ActionID 1] : LaunchApp waiting for user response to ShowInterstitials ""
```

The first wait lasted about 2 minutes 43 seconds and the second about 5 minutes 5 seconds. No `M1-Win64-Shipping.exe`, game-security process, new Proton game log, or game window appeared. Because the Steam interstitial requires a user response of unknown meaning, it was not clicked. Those two attempts did not reach the game. Later Big Picture launches did. See "Patched driver runtime" below.

Durable artifacts on the Thor are under:

```text
~/tfd-turnip-a740-sparse-2026-10-01/
```

That directory contains the patch, isolated driver, SHA-256 hashes, CTS case lists, QPA logs, complete focused CTS text log, `vulkaninfo` summary, Steam console excerpt, and `RESULTS.txt`. Temporary build trees and container images were removed.

### ShowInterstitials inspection

A later isolated-driver launch used the same per-process ICD variables plus `PROTON_LOG=1`, `PROTON_LOG_DIR` pointed at the evidence directory, and `VKD3D_DEBUG=info`. The Armada wrapper stayed in the launch option. The system Turnip library was not replaced. Its SHA-256 is still `b1542c07fd448a41bad6220cc6a3f26b48fc1458ab289fc4ff02e93e60f65d09`. The isolated library is still `dac166671e9e1b8948eb098099f65a4d45a2837cd1c9a13ca46d9477b85bca97`.

The only Steam text that could be read before the wait is an ordinary client-update banner:

```text
Your Steam Client has been updated
Thanks for participating in the beta. This beta has ended. Restart Steam to return to the current release.
Restart Steam
Dismiss
Your Steam Client is already up to date - View patch notes
Close
```

`Dismiss` and `Close` were clicked. The banner text stayed. `Restart Steam` was not clicked, because that would leave the `steamdeck_publicbeta` client. This banner is not the launch blocker.

Every isolated launch still ends at:

```text
GameAction [AppID 2074920, ActionID 1] : LaunchApp changed task to ShowInterstitials with ""
GameAction [AppID 2074920, ActionID 1] : LaunchApp waiting for user response to ShowInterstitials ""
```

While the install script is running, DevTools lists a separate page titled `Launching...`. The main Steam document does not gain the interstitial text. When the wait line is logged, that page stops answering DevTools, so its body text was never captured. KWin's window list for this session contains only `plasmashell` (1422x800 and 1422x62). Steam does not create a toplevel, with `-silent` or during the first seconds without it, so the prompt is not on a readable screen surface.

That inspection was from the desktop and silent Steam sessions. It did not reach `M1-Win64-Shipping.exe`. The later gamescope Big Picture session is a different result, below.

## Patched driver runtime

With Steam in gamescope Big Picture, `ShowInterstitials` continued on its own in about one second. Nothing was clicked. The isolated ICD stayed in the launch option in front of `/usr/libexec/armada/armada-game-launch %command%`. The system Turnip library was not replaced.

Two launches reached the game. Both used the isolated driver `dac166671e9e1b8948eb098099f65a4d45a2837cd1c9a13ca46d9477b85bca97`. Proton is Experimental ARM64, vkd3d-proton 3.1.0, build `7f0c30ad3c8f28d`.

The first used `VKD3D_DEBUG=info`. The loader opened the isolated `libvulkan_freedreno.so`. vkd3d detected Unreal Engine 5.2.2, enabled SM 6.6, and created a 1920x1080 swapchain with 3 buffers. The hardware dialog did not appear. About 0.27 seconds after the swapchain, Unreal hit `LowLevelFatalError` in `D3D12Util.cpp:1096` for `D3D12CommandList.cpp:267` with `E_INVALIDARG`. `VKD3D_DEBUG=info` hides `warn`, so that log does not name the command. It is preserved as `steam-2074920-vkd3d-info.log`.

The second launch was the controlled capture: `VKD3D_DEBUG=warn`, `PROTON_LOG=1`, `PROTON_LOG_DIR` on the evidence directory, and `VK_LOADER_DEBUG=driver`. Same isolated ICD and the same Armada wrapper. Preserved as `steam-2074920-vkd3d-warn.log`.

That first warn capture did not print vkd3d's maximum feature level. The later isolated
feature-query test below verifies it as `D3D_FEATURE_LEVEL_12_0` (`0xc000`). SM 6.6 is a
separate capability and was also enabled. Feature level 12_1 and DirectX Ultimate were
not reported.

The warn log names the failure. Command list `000000005ef5aaa0` was marked invalid ten times, five for each destination:

```text
Invalid target address 0000000000000600.
Invalid target address 0000000000000604.
```

That string is `d3d12_command_list_WriteBufferImmediate` in vkd3d-proton `libs/vkd3d/command.c` at this build. `vkd3d_va_map_deref` finds no buffer covering `parameters[i].Dest`, then `d3d12_command_list_mark_as_invalid` stores the reason. The D3D12 method is `ID3D12GraphicsCommandList2::WriteBufferImmediate`. The destinations are `D3D12_GPU_VIRTUAL_ADDRESS` values `0x600` and `0x604`, four bytes apart, so two 32-bit immediate writes. `ID3D12GraphicsCommandList::Close` then logs `Error occurred during command list recording.` and returns `E_INVALIDARG` because `list->is_valid` is false. Unreal treats that `Close` result as fatal at `D3D12CommandList.cpp:267`.

`0x600` and `0x604` are not sparse-image tile addresses. Vulkan sparse tiles are 64 KiB, and the log has no sparse-format fallback and no failed sparse VA assignment. The RFC patch's single-sample `sparseResidencyImage2D` bit is what let the device, SM 6.6, and the swapchain exist. It is not the call that returned `E_INVALIDARG`.

The same warn log has one vkd3d heap warning: requested alignment `0x10000`, got GPU VA `0x11aecc000`, which is not 64 KiB aligned. In vkd3d-proton `7f0c30ad`, `d3d12_device_aligns_bda_64k` is false only for `VK_DRIVER_ID_MESA_TURNIP`. The 64 KiB padding path runs only when `VKD3D_ALLOCATION_FLAG_REQUIRE_ALIGNED_GPU_ADDRESS` is set. That flag is set in `d3d12_heap_init` for heaps that allow buffers. `CreateCommittedResource` for a buffer calls `vkd3d_allocate_heap_memory` with `extra_allocation_flags` left at 0, so committed buffers skip the padding. The logged address is `va + realignment_offset`. It is still `0x11aecc000`, so this allocation was not shifted. That matches an allocation that never took the padding path.

Turnip in Mesa 26.2.3 does not advertise `VK_VALVE_buffer_device_address_allocation_alignment`. `tu_GetDeviceBufferMemoryRequirements` asks for 64-byte alignment for a normal buffer and for the CPU page size for a sparse buffer. On this device that page size is 4096. `tu_BindBufferMemory2` sets the device address to the buffer object's IOVA plus the bind offset. `0x11aecc000` is 4 KiB aligned and not 64 KiB aligned, which matches that allocator. Isolated `vulkaninfo` on the patched driver reports `bufferDeviceAddress=true` and no VALVE alignment feature.

`0x600` and `0x604` are not a mask or truncation of `0x11aecc000`. A failed lookup of that heap, or of that heap plus offset `0x600`, would have logged `0x11aecc000` or `0x11aed2600`. The VA map rejected the addresses because nothing registered covers them. That is what an application-supplied offset from a zero base looks like, or a VA vkd3d never published. It is not what a broken lookup of the unaligned heap looks like. Those two faults are both real and they are not yet the same fault.

The DLL in that first warn capture was Proton's stock aarch64 `d3d12core.dll`, SHA-256
`20984091fd07cbf39941f3e15f4ef400c21fdb302901c195677f1954ba6dcb60`,
loaded from the prefix `system32`. That build has no `Max feature level` string and no
`GetGPUVirtualAddress` trace string. `VKD3D_DEBUG=trace` could not print the missing
addresses. No behavior change was made. `0x600` was not remapped.

Easy Anti-Cheat and BlackCipher do not appear in the warn log, and no game, CrashReport, Wine, or security process for 2074920 was still running after the capture.

## After the run

Launch options inside the 2074920 block are again exactly:

```text
/usr/libexec/armada/armada-game-launch %command%
```

The temporary `VK_ICD_FILENAMES`, `VK_DRIVER_FILES`, `VK_LOADER_DEBUG`, `PROTON_LOG`, `PROTON_LOG_DIR`, and `VKD3D_DEBUG=warn` prefix was removed through Steam while the client stayed up. Steam is running under gamescope Big Picture (`steam -gamepadui -steamos3 -steampal -steamdeck`). CDP on `127.0.0.1:8080` still answers. No game or Wine test process was left.

System Turnip SHA-256 is still `b1542c07fd448a41bad6220cc6a3f26b48fc1458ab289fc4ff02e93e60f65d09`. The isolated driver is still `dac166671e9e1b8948eb098099f65a4d45a2837cd1c9a13ca46d9477b85bca97`. Both Proton logs remain under `~/tfd-turnip-a740-sparse-2026-10-01/`. Steam rewrote playtime on its own (`Playtime2wks` 690). That value was left as Steam wrote it.

The next step was measurement, not a padding change and not a capability spoof.
`diagnostics/vkd3d-proton-7f0c30ad-wbi-va-log.patch` (SHA-256
`a65f7459cb4f2bdeecd10a2cadff1c9fcf114054c57026df9314ff63f6e440ea`)
adds WARN lines only. `GetGPUVirtualAddress` logs any returned VA below 64 KiB with
dimension, width, size, and flags. The alignment failure logs allocation details.
`WriteBufferImmediate` logs the immediate value, mode, count, and index next to the
rejected address. It does not insert an address into the VA map or make `Close` succeed.

### Instrumented ARM64X capture

The patch was built without root using the official LLVM-MinGW 20260922 user-space
toolchain in a pinned Ubuntu 22.04 ARM64 container. The source commit, submodule commits,
download hashes, commands, binary hashes, and isolation recipe are recorded in
`diagnostics/vkd3d_arm64x_instrumentation_build_2026-10-01.md`.

A plain AArch64 DLL was not suitable for the x64/FEX game path and failed to load with
`c000007b`. The final build used vkd3d-proton's ARM64X cross file and produced:

```text
67ffc528ab187354478d1a6a59d491ec0cee3c43964d78b6ade2ac80e3c6db00  d3d12.dll
d391c37dab09cc55754729025ea3caa4b85b7bb530c3b3a8b732b18bad73b5f0  d3d12core.dll
```

The ARM64X focused tests all passed:

```text
test_write_buffer_immediate:       59 executed, 0 failures
test_gpu_virtual_address:          22 executed, 0 failures
test_create_committed_resource:    79 executed, 0 failures, 1 todo
```

The one instrumented game run used a symlinked isolated Proton tree and a copied game
compatdata directory. Only those copies contained the ARM64X DLLs. The original Proton,
game prefix, game files, and anti-cheat files were untouched. The launch still passed
through the Armada wrapper and used the CTS-tested sparse-image Turnip per process.

The final log is:

```text
~/tfd-turnip-a740-sparse-2026-10-01/steam-2074920-vkd3d-instrumented-isolated.log
```

It loaded vkd3d build `7f0c30ad3c8f28d+`, enabled SM 6.6, and created the same
1920x1080 three-buffer swapchain. It emitted zero `GetGPUVirtualAddress low va` lines.
Therefore, vkd3d did not return `0`, `0x600`, `0x604`, or any other sub-64-KiB GPU VA to
the caller.

The exact failing `ID3D12GraphicsCommandList2::WriteBufferImmediate` sequence on command
list `000000005ebefe40` was:

```text
Dest 0x600  Value 0x80000001  Mode MARKER_IN
Dest 0x600  Value 0x80000003  Mode MARKER_IN
Dest 0x604  Value 0x80000003  Mode MARKER_OUT
Dest 0x600  Value 0x80000004  Mode MARKER_IN
Dest 0x604  Value 0x80000004  Mode MARKER_OUT
Dest 0x600  Value 0x80000005  Mode MARKER_IN
Dest 0x604  Value 0x80000005  Mode MARKER_OUT
Dest 0x600  Value 0x80000002  Mode MARKER_IN
Dest 0x604  Value 0x80000002  Mode MARKER_OUT
Dest 0x604  Value 0x80000001  Mode MARKER_OUT
```

Each call had `count 1, index 0`. Modes 1 and 2 are
`D3D12_WRITEBUFFERIMMEDIATE_MODE_MARKER_IN` and
`D3D12_WRITEBUFFERIMMEDIATE_MODE_MARKER_OUT`. The paired slots and marker values identify
a GPU progress or breadcrumb sequence, not resource payload writes. D3D12 requires each
destination to be a valid 4-byte-aligned GPU virtual address in a destination resource.
The values are aligned but no resource in vkd3d's VA map covers them, so vkd3d correctly
invalidates the command list. `Close` then returns `E_INVALIDARG`.

Turnip still returned 4-KiB-aligned buffer device addresses where vkd3d requested 64-KiB
alignment. The captured raw VAs included `0x11aecc000`, `0x11cecc000`,
`0x11f2cc000`, `0x1267ec000`, `0x126bec000`, and `0x128218000`, with `padded=0`.
The `realign` field in this instrumentation was printed with a 64-bit format although the
field is 32-bit, so its nonzero upper-bit values are not evidence and must be ignored.
The raw VAs and `padded=0` remain valid. None can numerically become `0x600` or `0x604`.

An x64 test executable built from the same source then ran through FEX against the same
instrumented ARM64X DLLs:

```text
test_write_buffer_immediate:       59 executed, 0 failures
test_gpu_virtual_address:          22 executed, 0 failures
test_check_feature_support:       376 executed, 0 failures
MaxSupportedFeatureLevel:          0xc000, D3D_FEATURE_LEVEL_12_0
```

The x64 `WriteBufferImmediate` test passed valid 64-bit GPU addresses through the same
x64/FEX to ARM64X boundary. This rules out a general ARM64EC thunk truncation.

The immediate root cause is therefore a zero or missing breadcrumb buffer base on the
caller side. The title supplies raw slot offsets `0x600` and `0x604` to a method that
requires full GPU virtual addresses. The evidence does not identify whether the zero base
originates in Unreal 5.2.2, title-specific breadcrumb code, or another title-specific
interop component. It does identify the boundary: vkd3d receives those exact values and
does not manufacture them, and Turnip's independent 64-KiB BDA alignment limitation does
not produce them.

No vkd3d behavioral patch is justified. Blindly remapping low addresses would hide an
invalid API call and could write to the wrong resource. The caller attribution and the
`-nogpucrashdebugging` test are below.

### Caller attribution

`diagnostics/vkd3d-proton-7f0c30ad-wbi-caller.patch` (SHA-256
`dbdf766ddeaa0e3d4f348c01b51541c7276cc712e45663e02ee2525b6750800a`)
applies on top of the warn-only patch. On an invalid destination of `0x600` or `0x604`
it logs the native return address, up to eight `RtlCaptureStackBackTrace` frames, and
each frame's module and RVA. On ARM64EC it also reads the FEX/Windows CPU area at x64
TEB `+0x1788` and logs that context's PC and stack slot when the memory is readable. It
does not change recording or the `Close` result.

The rebuilt ARM64X `d3d12core.dll` is SHA-256
`4f9e036100a8820c5f2a3980d7a81407c8b3f092e942ab1f1d78049b6b54c9b0`.
`llvm-objdump -f` still reports `coff-arm64x`. The x64
`test_write_buffer_immediate` run stayed at 59 tests and 0 failures, with no caller log,
so valid calls are unchanged.

An x64 smoke call with destination `0x600` returned `Close` `0x80070057`. Its native
return address was the ARM64EC thunk inside `d3d12core.dll`. The unwind stack still
contained `wbi-caller-smoke-x64.exe` at RVA `0x154a`. In that direct smoke call the CPU-area
PC was zero, so the unwind stack is the reliable caller record under FEX. The native
ARM64X smoke binary's return address was the smoke executable itself.

The game log is:

```text
~/tfd-turnip-a740-sparse-2026-10-01/steam-2074920-vkd3d-caller.log
```

Every `0x600` and `0x604` call on command list `000000005ecf3b00` has the same first
shipping-exe frame:

```text
ret     d3d12core.dll rva 0x7b5064
stack   d3d12core.dll rva 0x40067c
stack   d3d12core.dll rva 0x7b5064
stack   M1-Win64-Shipping.exe rva 0x55ab13f
```

Later frames stay in that executable, including `0x55ab2d7` or `0x55ab5b4`, then
`0x638ab1f` and `0x638bf11`. The CPU-area PC stayed at RVA `0x4fcf03b` for every call
while the real call site changed, and the x64 stack slot was not a code address. The
unwind frame at `0x55ab13f` is the caller.

Read-only pdata lookup puts `0x55ab13f` in the function `0x55ab0b0` through `0x55ab155`.
That function builds one `D3D12_WRITEBUFFERIMMEDIATE_PARAMETER`, turns a zero flag into
mode 1 and a nonzero flag into mode 2, and calls vtable slot `+0x210`. In vkd3d-proton
`7f0c30ad` that slot is `ID3D12GraphicsCommandList2::WriteBufferImmediate`, the 66th
entry. The two nearby call sites are the marker-in and marker-out wrappers.

The same executable contains these UTF-16 strings, with code references in the D3D12 RHI
region around `0x6387ee3` and `0xeee31b`:

```text
r.GPUCrashDebugging
r.GPUCrashDebugging.Breadcrumbs
nogpucrashdebugging
gpucrashdebugging
GPUCrashDebugging.Breadcrumbs.PrintMinimal
Use -gpucrashdebugging to track current GPU state.
GPU Crash Debugging disabled
GPU Crash Debugging enabled
```

This is Unreal's optional GPU-crash breadcrumb writer linked into the shipping image. It
is not a FEX translation thunk, not a separate graphics DLL, and not vkd3d calling itself.
The two `d3d12core.dll` frames are the ARM64EC entry thunk and the native implementation.

### Official switch test

The binary's own switch token is `nogpucrashdebugging`, next to `r.GPUCrashDebugging` and
`gpucrashdebugging`. One isolated launch appended that engine argument and nothing else:

```text
TheFirstDescendant.exe -steam -nogpucrashdebugging
M1-Win64-Shipping.exe M1 -steam -nogpucrashdebugging
```

The log is `steam-2074920-vkd3d-nogpu.log`. It contains the argument, SM 6.6, a
1920x1080 three-buffer swapchain, later swapchain recreates, and zero
`Invalid target address` or `WBI caller` lines. `Close` did not fail for the breadcrumb
slots. The CTS-tested Turnip ICD and the instrumented ARM64X core stayed per process.

The next graphics boundary appeared while the process was still presenting:

```text
d3d12_device_validate_shader_meta: Required WaveSize range [32, 32], but supported range is [64, 128].
d3d12_pipeline_state_init_compute: Failed to create Vulkan compute pipeline, hr 0x80070057.
```

That happened twice. The process did not exit on it. Before the launch was stopped,
these security processes were present:

```text
NGService64.exe -service
BlackCipher64.aes
```

No Easy Anti-Cheat process appeared. The game, Wine server, NGService, and BlackCipher
processes were then stopped. Launch options were restored to the Armada wrapper. System
Turnip remained `b1542c07fd448a41bad6220cc6a3f26b48fc1458ab289fc4ff02e93e60f65d09`. The
isolated Turnip remained `dac166671e9e1b8948eb098099f65a4d45a2837cd1c9a13ca46d9477b85bca97`.
No game, anti-cheat, or system package was modified.

## Wave32 compute boundary

### Exact shaders

A behavior-neutral extension to the isolated vkd3d core added the shader hash, metadata
flags, workgroup dimensions, and preferred wave size to the existing validation error:

```text
Shader fb2dc4ecd1a2ce1b requires WaveSize range [32, 32], but supported range is [64, 128]; flags 0x2, workgroup [32, 1, 1], preferred 0.
Shader 16ba142daca3904b requires WaveSize range [32, 32], but supported range is [64, 128]; flags 0x6, workgroup [32, 1, 1], preferred 0.
```

The patch is
`diagnostics/vkd3d-proton-7f0c30ad-wave-meta-log.patch`. The ARM64X core SHA-256
is `c2c9cbc6d826b4dcd356d4c307f6b5b070843b636e474dda2a2faf6da71709f8`.
The focused x64 `test_write_buffer_immediate` run still executed 59 tests with zero
failures.

`VKD3D_SHADER_DUMP_PATH` captured both original DXIL containers and vkd3d's translated
SPIR-V. Both SPIR-V modules validate for Vulkan 1.1. Their preserved hashes are:

```text
a7b9cf6bd61c0eca7ae12c9ed2f12ec02ce6b9936c9ff8fb59848014dbaf8f49  fb2dc4ecd1a2ce1b.dxil
e848f413d0e0838c114090aa1438c41a4269f7560ef34691b29e05f42d8da32d  fb2dc4ecd1a2ce1b.spv
d7ba9884eba745103b6e03595ebade5f3464a303e88dffa8fa8a33fd4ec45d50  16ba142daca3904b.dxil
39c1a7d796f6f1a2b235b4ce3d39f3b6b3caab7a036ed1baadf42d255cac9fd8  16ba142daca3904b.spv
```

Flag `0x2` is `USES_SUBGROUP_OPERATIONS`. Flag `0x6` adds
`USES_NATIVE_16BIT_OPERATIONS`. The second module is the native FP16 permutation of the
same algorithm.

These are not shaders that merely carry a redundant WaveSize attribute. Both have local
size `[32, 1, 1]`, read `SubgroupLocalInvocationId`, mask lane indices to 0 through 31,
and execute many `OpGroupNonUniformShuffle` operations. The shuffle source lanes include
the current lane plus 1 and plus 4, wrapped within 32 lanes. The surrounding operations
perform repeated three-component min and max filtering. This matches Unreal's
`TSRRejectShadingCS`: Epic's public diagnostics describe that pass as WaveSize 32 and
using wave intrinsics for 3x3 min, max, and sum convolutions. The two failing PSOs are
therefore the FP32 and FP16 TSR RejectShading wave-op permutations.

### A740 and Turnip capability

This is not an unexposed A740 wave32 mode. Mesa main at
`ab10c10849604a8b2a225635c06ebfc7355ff0d6` still defines A7xx
`threadsize_base = 64`; A740 inherits it. The public A6xx/A7xx register description has
only `THREAD64` and `THREAD128` encodings. Turnip consequently reports:

```text
minSubgroupSize = 64
maxSubgroupSize = 128
requiredSubgroupSizeStages includes compute
subgroupSizeControl = true
computeFullSubgroups = true
```

IR3 already has complete single/double wave-size plumbing. `IR3_SINGLE_ONLY` means the
64-lane base mode and `IR3_DOUBLE_ONLY` means 128 lanes. The original upstream
`VK_EXT_subgroup_size_control` implementation explicitly advertised 64 through 128.
Qualcomm's public OpenCL guide says wave size is GPU and compiler dependent and must be
queried. It does not establish a 32-lane mode for A740.

Exposing 32 would therefore be a capability lie, not a missing one-line Turnip feature.
A conformant software implementation would have to create logical 32-lane subgroups on
64-lane hardware and correctly lower every subgroup builtin and operation, including
ballot, vote, shuffle, arithmetic, masks, barriers, reconvergence, helper lanes, and full
subgroups. It would then need the complete Vulkan subgroup and subgroup-size-control CTS
coverage before Turnip could lower `minSubgroupSize`. No existing incomplete IR3 path
does that, so no Mesa patch was created or game-tested.

### Unreal fallback test

Unreal documents `r.TSR.WaveOps` as controlling wave operations in TSR shading-rejection
heuristics. The isolated title settings were already at their lowest and were not
selecting TSR:

```text
AntiAliasing=0
SelectUpscaler=EM1Upscaler::None
sg.AntiAliasingQuality=0
```

One isolated test added this normal rendering CVar to the isolated `Engine.ini`:

```ini
[SystemSettings]
r.TSR.WaveOps=0
```

It did not remove the two PSO creations. The same two WaveSize errors occurred, while
the breadcrumb errors remained absent. This indicates the shipping title eagerly loads
or warms the cooked wave-op PSOs even when TSR is not selected and the runtime CVar asks
for the non-wave path. The title process and `BlackCipher64.aes` remained running until
the controlled stop. The CVar does not provide a usable end-user workaround for this
build.

The correct fix belongs in the title's Unreal shader cook or PSO selection. It should
query `WaveLaneCountMin`, cook and select the non-wave `TSRRejectShadingCS` permutation
when 32 is unsupported, and omit unsupported wave32 PSOs from startup prewarming.
`r.TSR.WaveOps=0` shows that Unreal already has the intended non-wave algorithm. Forcing
wave64, ignoring the DXIL WaveSize requirement, or advertising wave32 in Turnip would
not be correct.

Capture log:

```text
~/tfd-turnip-a740-sparse-2026-10-01/steam-2074920-wave32-shader-dump.log
~/tfd-turnip-a740-sparse-2026-10-01/steam-2074920-tsr-waveops0.log
~/tfd-turnip-a740-sparse-2026-10-01/wave32-shaders/
```

After the tests, the exact original `Engine.ini` hash
`537b69bc4f0da6faf66b538899052a5b5ad229b622d73a79a02304e07071d5ea`
was restored. No game, Wine, NGService, BlackCipher, or EAC process remained. Steam
stayed running. The exact launch option was restored to
`/usr/libexec/armada/armada-game-launch %command%`. System and isolated Turnip hashes
were unchanged.

### Wave32 emulation decision: no-go

No compiler or runtime lowering was implemented, and the game was not launched again.
The captured shaders do not establish a semantics-preserving wave32 emulation on the
native 64-lane wave.

Both translated shaders are straight-line compute shaders. Each has one function, two
labels, and one unconditional branch. Their only subgroup operations are 66
`OpGroupNonUniformShuffle` instructions. There is no ballot, vote, reduction, scan,
quad operation, `OpControlBarrier`, `OpMemoryBarrier`, workgroup memory, or constant 32.
`SubgroupSize` is not read. vkd3d's metadata already supplies the DXIL requirement:
exact wave size 32, workgroup `[32, 1, 1]`, and no preferred size. LLVM 19 cannot
disassemble the DXIL bitcode because DXIL does not use standard ABI alignment, so the
operation inventory comes from the SPIR-V that vkd3d produced from those exact
containers.

Every shuffle index has one of these forms, in both the FP32 and FP16 shaders:

```text
((lane + 1) & 31) | (lane & ~31)    18 uses
((lane + 4) & 31) | (lane & ~31)    42 uses
((lane + 5) & 31) | (lane & ~31)     6 uses
```

`lane` is `SubgroupLocalInvocationId`. The mask keeps the target inside the aligned
32-lane cluster containing the current lane. The offsets are a 4-wide neighborhood:
one column right, one row down, and the diagonal. The values being shuffled are
computed from `LocalInvocationIndex`, while the destination lane comes from the
subgroup ID.

Vulkan's compute scope makes the workgroup a superset of the subgroup, so invocations
from two workgroups are never in one subgroup. Turnip documents the same hardware
constraint: a wave cannot contain multiple workgroups because those workgroups can take
different barriers. A 32-thread workgroup therefore occupies one 64-lane A740 wave and
leaves 32 lanes inactive. `wave_granularity = 2` is only the occupancy accounting for
wave pairs. It does not merge workgroups into one subgroup. The multiple-workgroup
packing boundary is not present.

The actual boundary is lane identity. The Vulkan specification, quoted by Turnip in
`ir3_nir_lower_subgroup_id_cs`, says there is no direct relationship between
`SubgroupLocalInvocationId` and `LocalInvocationIndex`. A 64-lane subgroup may number
its 32 active invocations as 0 through 31, but it is not required to do so and it is
not required to make subgroup lane `i` the same thread as local invocation `i`.
`OpGroupNonUniformShuffle` selects by subgroup lane, not by local invocation. The
neighborhood above is spatially meaningful only for one particular permutation. D3D
also leaves the thread-to-lane permutation implementation-defined, and these shaders
do not request `DerivativeGroupLinear`, which is the execution mode dxil-spirv says
would be required before that mapping may be assumed.

Current Turnip privately lowers the subgroup invocation to
`local_invocation_index & (subgroup_size - 1)` and selects a 64-lane wave when the
workgroup fits in `threadsize_base`. For these two shaders that happens to mean lanes
0 through 31. That is a driver-internal choice, not a result the compiler can rely on
without advertising subgroup size 32. Removing `RequiredSubgroupSize` would preserve
the current output only while that choice remains. It is not a proven emulation.

A shared-memory exchange could impose an identity permutation explicitly, but that
would define a permutation the captured DXIL does not prove to be the D3D permutation.
No focused equivalence test can supply the missing reference mapping. vkd3d's existing
`ALLOW_WAVE32` path only bypasses validation for quirked shaders. It does not rewrite
shuffles, and neither captured shader has that flag. NIR subgroup lowering can lower
supported operations to the hardware subgroup size, but it cannot turn an arbitrary
application shuffle into a virtual 32-lane wave without the same unproven lane map.

This is the hard stop. A correct implementation requires either honest 32-lane subgroup
support, which A740 does not expose, or a title permutation that does not use wave32.

### Wave32 prewarm observation: not fatal to the process

One controlled launch was left running for 10 minutes after the shipping process
appeared. The launch used the CTS-clean isolated Turnip sparse-image driver, the
behavior-neutral instrumented `d3d12core`, the already documented title settings
(`AntiAliasing=0`, `SelectUpscaler=EM1Upscaler::None`, `sg.AntiAliasingQuality=0`),
and `-nogpucrashdebugging`. No shader was edited, subgroup size was not forced, and
`VKD3D_SHADER_DUMP_PATH` was not set. No purchase, EULA, privacy, or account prompt
was used.

The shipping process stayed up for the full window and was still alive when it was
stopped later. The monitor recorded `alive=1`, `removed=0`, and `fatal=0` from game
start through 631 seconds. The Proton log grew to 124045 bytes and then stayed at
that size. It contains no `Device removed`, `Fatal error`, or device-lost line, and
no new Unreal crash directory appeared. `Saved/Logs` still had only `cef3.log`.

Four compute PSOs failed validation. All request exact WaveSize 32 against the
device range 64 to 128, with workgroup `[32, 1, 1]`:

```text
fb2dc4ecd1a2ce1b  flags 0x2  first prewarm, monitor about 43 s
16ba142daca3904b  flags 0x6  first prewarm, monitor about 43 s
111c17cfaab28e46  flags 0x2  later, monitor about 109 s
b3a71aa39a7b59a8  flags 0x2  later, monitor about 109 s
```

After those errors the title kept creating other pipelines. The vkd3d disk-cache
thread flushed 314, 12, 1338, and 358 new PSOs and then went idle. Gamescope WSI
created a 3-image swapchain for X window `0x220004f`. The wave32 failures did not
kill the device or the process.

Security processes were mixed. At monitor 78 seconds, `NGService64.exe -service`
(PID 131809) and `BlackCipher64.aes` (PID 131815) were both present. `NGService64.exe`
was gone by the next 10 second sample. `BlackCipher64.aes` was still running at the
10 minute mark and at the later stop. No Easy Anti-Cheat process appeared. Nexon
`NXPEpicWebHelper.exe` GPU, storage, and network helpers stayed up with the game.
That is a live Nexon web view process, not a confirmed login or server connection.

A visible menu was not confirmed. The title window on Xwayland display `:2` was
`0x2400001`, titled `The First Descendant`, owned by `M1-Win64-Shipping.exe` PID
131423, state Normal, size 1920 by 1080. Its input hint was false. The child window
`0x220004f` had `_WINE_ALLOW_FLIP` set, and an X11 grab of display `:2` was a solid
black 1920 by 1080 frame, which matches a direct flip rather than a readable X
buffer. `gamescopectl` shots of `gamescope-0` stayed on Steam Big Picture content
from other titles, and repeated shots were pixel-identical. `gamescope-1` was the
KDE bottom screen. Raising the title window did not change the `gamescope-0` shot.
No menu, login, or error dialog was captured.

This run does not support a fatal-crash report to Nexon. The two original prewarm
PSOs, and the two later wave32 PSOs, failed while the process, BlackCipher, and the
Nexon web helper kept running and other PSOs continued to compile. The title-side
cook and prewarm fix already stated above is still the right fix for the missing
shaders. It is not a demonstrated startup crash.

Stop and restore: `steam://forceexitapp/2074920` did not exit the title within about
20 seconds. The isolated prefix wineserver was then stopped with `wineserver -k`.
No `M1`, BlackCipher, NGService, Nexon web helper, or wineserver process remained.
Steam stayed running. Launch options were set back through Steam and checked in
`localconfig.vdf` as exactly `/usr/libexec/armada/armada-game-launch %command%`.
System Turnip SHA-256 remained
`b1542c07fd448a41bad6220cc6a3f26b48fc1458ab289fc4ff02e93e60f65d09`. Isolated Turnip
SHA-256 remained
`dac166671e9e1b8948eb098099f65a4d45a2837cd1c9a13ca46d9477b85bca97`. `Engine.ini`
remained `537b69bc4f0da6faf66b538899052a5b5ad229b622d73a79a02304e07071d5ea`. The
title rewrote `GameUserSettings.ini` during startup. The documented anti-aliasing
and upscaler keys were still `AntiAliasing=0`, `SelectUpscaler=EM1Upscaler::None`,
`sg.AntiAliasingQuality=0`, and `TSR=EM1TSRQuality::Quality`.

```text
~/tfd-turnip-a740-sparse-2026-10-01/steam-2074920-wave32-outcome.log
  SHA-256 c5c292c4ff0cf2da9727ff1883db24e7c9709e9095530a374b2474ec7573f219
~/tfd-turnip-a740-sparse-2026-10-01/wave32-outcome/timeline.txt
~/tfd-turnip-a740-sparse-2026-10-01/wave32-outcome/shots/
```

### Presentation and focus: title visible at Select Language

Relaunched at 18:47:57 with the same isolated Turnip launch option and
`-nogpucrashdebugging`, started through `steam://rungameid/2074920`. Nothing in
rendering, security, shaders, or title files was changed.

Root cause of the hidden title: Steam Gaming Mode kept itself in front. Gamescope picks
the focused app from `GAMESCOPECTRL_BASELAYER_APPID` on the Steam Xwayland (`:1`) root,
in order. Steam wrote `413091, 769, 2074920` (`413091` is Steam's system-UI sentinel,
`769` is Steam itself), so Steam stayed focused even though gamescope already listed the
title as focusable (`GAMESCOPE_FOCUSABLE_APPS = 769, 2074920`, window `0x2400001`,
`STEAM_GAME = 2074920`, on Xwayland `:2`). Steam's own state agreed the title was
running: `MainRunningAppID = 2074920`. Its composition store had
`eCompositionMode = 3` (Opaque) with queue `[769, 2074920]`. In the Steam UI code,
Opaque puts 769 at the head of the queue. The UI was on `/library/app/2074920`, and
that route stays Opaque unless the game-list selection matches the running app. A
URL launch does not set that selection. Normally the Resume button on that page moves
to the running-app route and Steam hides itself. In the earlier run Steam then idled into
its screenshot screensaver, which is why the captures showed other games.

The Resume path was not usable this time. The Steam webhelper GPU process exited with
`GPU state invalid after WaitForGetOffsetInRange` at 18:50:35. Steam then idle-suspended
the device at 18:50:39 and resumed at 18:50:45. The title and BlackCipher survived the
suspend. After that, the Steam UI stopped painting (its clock stayed at 6:50) and the
DevTools JS contexts stopped answering. The kernel log had no GPU hang or recovery
message.

Correction used: the standard gamescope base-layer control atom, written the same way
Steam writes it for a running game, with the title ahead of Steam:

```sh
DISPLAY=:1 xprop -root -f GAMESCOPECTRL_BASELAYER_APPID 32c \
  -set GAMESCOPECTRL_BASELAYER_APPID "413091,2074920,769"
```

Gamescope immediately reported `GAMESCOPE_FOCUSED_APP = 2074920`,
`GAMESCOPE_FOCUSED_APP_GFX = 2074920`, and focused window `0x2400001`. No input was
sent to the game.

Visible state at 18:58 and 19:01 on the top display: the title's first-run
**Select Language** screen. Text Language shows English, Voice Language shows English,
and a Next prompt is at the bottom right. The animated background changes between
captures, so the title is presenting live frames. This screen needs the user, so the
game was left running. The process timeline is `M1-Win64-Shipping.exe` (PID 134773) and
`BlackCipher64.aes` (PID 135033), both alive about 16 minutes after launch, with no
Easy Anti-Cheat process. The Proton log has the same 4 WaveSize 32 validation errors
and no device-removed or fatal line.

Steam side effect, not fixed: about 30 seconds after the title took focus, Steam's
Xwayland `:1` (PID 111444) went into uninterruptible sleep in `dma_fence_default_wait`
and stayed there. `xprop` on `:1` times out. The webhelper GPU process exited again at
18:58:13, and the webhelper processes are now zombies. Xwayland `:2` and gamescope still
respond, and the title keeps presenting. The Steam overlay and Steam button will not work
until that fence wait clears or the session is restarted. This was not root-caused. No
kernel GPU fault was logged.

Launch options: Steam's UI IPC was down, so the temporary option could not be restored
yet. A watcher, `presentation-2026-10-01/restore-launch-options.py` (log `restore.log`),
waits until `M1-Win64-Shipping.exe` exits and Steam's SharedJSContext answers. It then
renames `steam-2074920.log` to `steam-2074920-presentation.log`, sets
`/usr/libexec/armada/armada-game-launch %command%` through
`SteamClient.Apps.SetAppLaunchOptions`, and checks `localconfig.vdf`. It stops after
24 hours. Until it reports `verified launch option restored`, a relaunch from Steam will
still use the isolated test option. System Turnip is unchanged.

```text
~/tfd-turnip-a740-sparse-2026-10-01/presentation-2026-10-01/steam-screensaver-1847.png
~/tfd-turnip-a740-sparse-2026-10-01/presentation-2026-10-01/steam-opaque-frozen-1854.png
~/tfd-turnip-a740-sparse-2026-10-01/presentation-2026-10-01/tfd-visible-1858.png
~/tfd-turnip-a740-sparse-2026-10-01/presentation-2026-10-01/tfd-visible-1901.png
~/tfd-turnip-a740-sparse-2026-10-01/presentation-2026-10-01/restore.log
```

### Black screen at 19:07: Steam took focus back

At 19:08 the top panel was on (backlight 3067 of 4096, `bl_power` 0, DSI-2
connected and enabled) and gamescope was alive, but its scanout was a fully black
1920 by 1080 frame. The bottom screen was still the desktop. This was not DPMS and
not a panel power loss.

The title had not crashed. `M1-Win64-Shipping.exe` PID 134773 was runnable and
still accumulating CPU. `BlackCipher64.aes` was still running. No Easy Anti-Cheat
process. The Proton log was unchanged since 18:50:38 (132010 bytes), still the same
4 WaveSize errors, with no `Device removed`, `VK_ERROR_DEVICE_LOST`, or fatal line.
No new crash directory. `dmesg` and the kernel journal since 19:00 have no msm,
Adreno, DRM fault, hang, or GPU recovery message.

The title had moved past Select Language. `GameUserSettings.ini` was rewritten at
19:06:44. After focus was restored the top screen showed **Screen Calibration**:
HDR Display Off, Screen Brightness 5, Screen Contrast 6, with Next and Back. So
Next on the language screen had been accepted, and the game was drawing that next
page the whole time it looked black.

While the picture was black, Steam's Xwayland `:1` was answering too slowly to read
the focus atoms (it had been in uninterruptible `dma_fence_default_wait`). When it
answered at 19:10, Steam had rewritten the base layer to `413091, 769` and dropped
2074920. Focused app was 769, Steam's own window. Steam's UI was not painting, so
that layer was the black frame. The title stayed in `GAMESCOPE_FOCUSABLE_APPS`.
Gamescope's present counter did not advance while that black frame was up.
`vkd3d-swapchain` was inside an infinite `DRM_IOCTL` syncobj wait
(timeout `0x7fffffffffffffff`), which is the present thread waiting for a buffer
Gamescope was not scanning out. It was not a logged GPU reset.

Same correction as before, once `:1` answered:

```sh
DISPLAY=:1 xprop -root -f GAMESCOPECTRL_BASELAYER_APPID 32c \
  -set GAMESCOPECTRL_BASELAYER_APPID "413091,2074920,769"
```

Gamescope focused 2074920 again. The calibration screen was on the top display at
19:10, and the base layer was still `413091, 2074920, 769` six seconds later. No
input was sent. The game and BlackCipher were left running. The restore watcher is
still only `armed`. It has not changed the launch option.

```text
~/tfd-turnip-a740-sparse-2026-10-01/presentation-2026-10-01/tfd-black-1908.png
~/tfd-turnip-a740-sparse-2026-10-01/presentation-2026-10-01/tfd-calibration-1910.png
```

### HDR toggle at 19:11: Steam session restart, not a reboot

The kernel did not reboot. Uptime was still 9 hours 18 minutes at 19:12, and
`journalctl --list-boots` kept this boot as index 0 (boot id
`1a0d3e4f7ce84bbdb7c9cf08bdcf88d1`). The previous boot had already ended at 09:53.
What restarted was the user gamescope session. `gamescope-session-plus@steam.service`
stopped at 19:11:32 and a new one started at 19:11:34. New gamescope and Steam
processes came up. The game, Wine, and BlackCipher did not.

The only coredump from the teardown is `mangoapp` PID 111473, SIGABRT at 19:11:32.
Its journal line is `terminate called without an active exception` after
`X connection to :1 broken`. The backtrace is two unresolved frames. That is
mangoapp dying because the X server went away, not the trigger. There is no
gamescope coredump and no kernel msm, Adreno, DRM fault, hang, or GPU recovery
line.

The trigger is Steam's CEF GPU process. `cef_log.txt` at 19:11:23:

```text
GPU state invalid after WaitForGetOffsetInRange
GPU process exited unexpectedly: exit_code=512
The GPU process has crashed 3 time(s)
```

At 19:11:24 PluginLoader logged `CEF has requested that we detach` and
`CEF has disconnected`. At 19:11:26 steamwebhelper wrote
`assert_20261001191126_5.dmp` with
`Assert( CefCrashReportingEnabled() ):/data/src/webhelper/html_chrome.cpp:622`.
Steam discarded that upload. At 19:11:30 the old gamescope logged
`lease-connector: companion app disconnected`, then DRM `drmModeAtomicCommit`
and `drmModeRmFB` failures, and the session script tore down. The same
`WaitForGetOffsetInRange` GPU-process failure had already happened at 18:50
(during the idle suspend) and 18:58 (after the title took focus). Those two did
not end the session. The third one did.

The HDR toggle did land in the title. `GameUserSettings.ini` was rewritten at
19:11:25 with `bUseHDRDisplayOutput=False`, `bDesiredUsingHDRDisplayOutput=False`,
and `HDRDisplayOutputNits=1000`. The Proton log grew only to 132074 bytes at that
same second and its new tail is `pid 134667 != 134666, skipping destruction
(fork without exec?)`. It has no swapchain recreation and no colorspace change.
Gamescope logged no HDR modeset before the teardown. `VK_EXT_swapchain_colorspace`
was reported off (`extSwapchainColorSpace : 0`) at device init. So the toggle is
the action that lines up with the third GPU-process crash, and the setting was
saved, but there is no log of gamescope recreating the display for it.

The restore watcher saw the game exit, renamed the Proton log to
`steam-2074920-presentation.log`, and at 19:12:01 verified the launch option
back to `/usr/libexec/armada/armada-game-launch %command%`. System Turnip is still
`b1542c07fd448a41bad6220cc6a3f26b48fc1458ab289fc4ff02e93e60f65d09`. Steam is up
again under gamescope. No game or Wine process was left. The game was not relaunched.

### Where the title got to

The CTS-clean sparse-image Turnip patch got past the hardware dialog to a
1920x1080 D3D12 swapchain. `-nogpucrashdebugging` removed the invalid breadcrumb
writes. The four exact WaveSize 32 compute PSOs failed validation and were not
fatal: the process, BlackCipher, and the Nexon web helper kept running, and other
PSOs compiled. No Easy Anti-Cheat process appeared. Once Gamescope was told to put
app 2074920 ahead of Steam, the title reached Select Language and then Screen
Calibration. Toggling HDR off on that page coincided with Steam's CEF GPU process
dying for the third time and the gamescope session restarting. Leave HDR off. The
next legitimate issue to report is that Steam CEF GPU-process loss
(`WaitForGetOffsetInRange`, exit 512) tears down the whole gamescope session on
this Turnip stack, not a title crash and not a kernel GPU reset.

### Durable patched launch option

After the session restart the user pressed Play from the Steam UI. That process
is the unpatched system Turnip, so the hardware dialog came back. It is still
running as `M1-Win64-Shipping.exe` PID 140729 with `-steam` only and
pressure-vessel's system ICD list. It was not stopped.

The isolated driver is unchanged and was not rebuilt or installed system-wide.
ICD `freedreno_icd.game.json` still points at
`~/tfd-turnip-a740-sparse-2026-10-01/driver/lib64/libvulkan_freedreno.so`,
SHA-256 `dac166671e9e1b8948eb098099f65a4d45a2837cd1c9a13ca46d9477b85bca97`.
System Turnip is still
`b1542c07fd448a41bad6220cc6a3f26b48fc1458ab289fc4ff02e93e60f65d09`.

Steam's `SetAppLaunchOptions` stored this for app 2074920, and `localconfig.vdf`
has the same string:

```text
VK_ICD_FILENAMES=$HOME/tfd-turnip-a740-sparse-2026-10-01/driver/freedreno_icd.game.json VK_DRIVER_FILES=$HOME/tfd-turnip-a740-sparse-2026-10-01/driver/freedreno_icd.game.json /usr/libexec/armada/armada-game-launch %command% -nogpucrashdebugging
```

The next Play from the game's page uses the patched driver per process, keeps
the Armada wrapper, and passes `-nogpucrashdebugging`. The copy already open
does not. HDR stays saved off. The game was not launched again.

### Home screen, about 14 FPS

The user closed the unpatched dialog and pressed Play. At 19:30 the shipping
process was `M1-Win64-Shipping.exe` PID 141377 with `-nogpucrashdebugging`, and
its maps show the isolated library
`~/tfd-turnip-a740-sparse-2026-10-01/driver/lib64/libvulkan_freedreno.so`.
Gamescope focus was app 2074920, base layer `413091, 2074920, 769`. BlackCipher
was running. The game was left running and the launch option was not changed.

This launch has no Proton log. The saved config in the normal prefix, written
19:25, is native 1920x1080, `SelectUpscaler=EM1Upscaler::None`,
`sg.ResolutionQuality=100`, every `sg.*Quality` at 0, ray tracing off, HDR off,
`bUseVSync=False`, `bUseDynamicResolution=False`, `FrameRateLimit=60`.
`FSR_FG=false` and `DLSS_FG` off. The config keys exist for FSR, FSR4, XeSS,
DLSS upscaling, and both frame-generation toggles. The active choice is no
upscaler.

Gamescope's completed-present counter, sampled every 15 seconds from 19:30:20
to 19:31:35, moved 24912, 25122, 25328, 25530, 25737, 25859. The steady
intervals are about 14 frames per second. One interval dropped to about 8.
Gamescope's FPS limit is 60 and the title cap is 60, so 14 is not a cap.
The GPU sat at 615 MHz and then 680 MHz. 680 MHz is the devfreq maximum, and
the transition stats show almost all residency at that top bin. GPU temperature
was about 83 C. The game process held about 270% CPU. The prime core's
hardware max is 2957 MHz and its current scaling max was 2093 MHz, with the
core pinned there. The hottest CPU sensor was about 94 C. Later inspection
showed that 2093 MHz was the Balanced profile's configured cap, not a thermal
cooling-state reduction. RAM available stayed near 2.9 GB, with about
3.7 GB of zram used. The shader cache was still being written around 19:25 and
was quiet by 19:31, so the 14 FPS after that is the steady menu rate, not a
compile hitch.

This is a native 1080p Unreal frame on an Adreno 740, through FEX, with the GPU
at the top of its clocks and the CPU capped by the Balanced power profile. It is not a software
fallback to the system Turnip, and it is not Gamescope stuck on Steam. Sitting
in this menu is safe at these temperatures. A gameplay load can still hitch
while pipelines compile, and memory is already tight enough that a zone load
can push swap harder. It is not, by itself, evidence the device will crash.

DLSS and DLSS frame generation need an NVIDIA GPU. FSR 4's ML upscaler is an
AMD RDNA 4 path and is not a Turnip feature. The portable control is FSR
upscaling, which this config already has, currently set to None. FSR frame
generation is a saved toggle and is off. AMD documents FSR frame generation as
usable on non-AMD GPUs when a game ships it, and this title's players report
that toggle, including bugs and a warning that it wants a high base rate. At
14 FPS it should stay off. Snapdragon Game Super Resolution is a Qualcomm
library a game integrates. It is not wired into this Proton or vkd3d path, so
there is no SGSR switch to flip.

The first manual change is one step: set the in-game resolution to 1280x720
and the frame cap to 30. Leave the upscaler off for that test, leave the low
quality values as they are, leave ray tracing, HDR, VSync, dynamic resolution,
and frame generation off. If that is still under 30, set the upscaler to FSR
Performance rather than stacking another resolution drop. FSR Quality is the
step back up only if Performance is comfortably above 30.

### 720p baseline, about 21.5 FPS

The user set 1280x720 and a 30 FPS cap. The same process, PID 141377, was still
running at 19:40 with `-nogpucrashdebugging` and the isolated Turnip library
mapped. The launch option was not changed. `GameUserSettings.ini` was rewritten
at 19:35:45 and now has `ResolutionSizeX=1280`, `ResolutionSizeY=720`,
`FrameRateLimit=30`, `SelectUpscaler=EM1Upscaler::None`, `sg.ResolutionQuality=100`,
`bUseDynamicResolution=False`, `bUseVSync=False`, ray tracing off, HDR off,
`FSR_FG=false`, and `DLSS_FG` off. The inactive quality keys remain
`FSR=EM1FSRQuality::Quality`, `XeSS=EXeSSQualityMode::Quality`, and
`TSR=EM1TSRQuality::Quality`.

Gamescope completed presents from 19:40:35 to 19:41:50 were 35693, 36020, 36347,
36673, 36996, 37322. Each 15 second interval was 21.6, 21.6, 21.6, 21.4, and
21.6 FPS. The 30 FPS cap was not reached. One DRM client in the game was busy
about 97% of each interval. GPU frequency moved between 550, 615, and 680 MHz.
GPU temperature stayed about 83 C. The process used about 335 to 339% CPU. The
prime core stayed pinned at its 2093 MHz scaling cap, under a 2957 MHz hardware
max, at about 95 C. Available RAM stayed near 3.0 GB and zram use stayed near
3.88 GB.

The 720p menu is GPU-bound. The CPU is already at its Balanced profile ceiling, so it
can become the limit once the GPU has less pixel work. The session is safe to
leave on this menu. The game was not stopped.

The shipping executable names the upscaler choices `None`, `DLSS`, `FSR`,
`FSR4`, `XESS`, and `TSR`. It does not contain the text "FSR 3". The FSR
quality values it does contain are `NativeAA`, `Quality`, `Balanced`,
`Performance`, and `UltraPerformance`, plus a separate FSR frame-generation
option. `UltraPerformance` is the least expensive of those modes. XeSS is a
menu choice with its own quality enum. The binary also has a check that the
current RHI may not support XeSS, and this Turnip session has not shown XeSS
running, so XeSS hardware support is not established. TSR is the wrong next
test: the two WaveSize 32 PSOs that fail on A740 are the FP32 and FP16
`TSRRejectShadingCS` permutations.

The next single change is the FSR upscaler at Ultra Performance. Leave the
output at 1280x720, the cap at 30, and frame generation off. Leave FSR4, XeSS,
TSR, DLSS, ray tracing, HDR, VSync, and dynamic resolution untouched.

### FSR Ultra Performance holds the 30 cap

The user switched the upscaler to FSR Ultra Performance. PID 141377 was still
the same process, still mapped to the isolated Turnip library, and the launch
option was not changed. `GameUserSettings.ini` at 19:44:00 has
`SelectUpscaler=EM1Upscaler::FSR`, `FSR=EM1FSRQuality::UltraPerformance`,
`ResolutionSizeX=1280`, `ResolutionSizeY=720`, `FrameRateLimit=30`,
`FSR_FG=false`, `DLSS_FG` off, dynamic resolution off, VSync off, ray tracing
off, and HDR off. This launch still has no Proton log. The kernel journal from
19:43 has no GPU hang, and the only title log is the old `cef3.log` from 19:23.
The shader cache was rewritten at 19:43:54 and 19:44:01, then the present rate
settled.

From 19:44:57 to 19:45:58, each 5 second window completed 153 or 154 presents:
29.9 to 30.1 FPS, twelve intervals, no dip. That is the 30 FPS cap, and the
pacing is even. The GPU stayed at 680 MHz and about 80% busy, down from about
97% busy at the 21.5 FPS no-upscaler baseline. GPU temperature was 78 to 81 C.
The process used about 403 to 415% CPU. The prime core stayed at its 2093 MHz
Balanced profile cap, hardware max 2957 MHz, at about 94 to 95 C. Available RAM drifted
from about 3.00 GB to 2.94 GB. Zram use stayed about 3.89 GB.

Against the earlier menu measurements, native 1080p was about 14 FPS and 720p
with no upscaler was 21.5 FPS. Ultra Performance is the first of the three to
sit on the cap. The GPU idle time says there is headroom, so the uncapped rate
is higher than 30 and this sample cannot show it. Frame generation stays off.
The next single test is FSR Performance at the same 1280x720 output and 30 cap.

### Uncapped FSR Ultra Performance is about 36 FPS

The user left FSR Ultra Performance at 1280x720 and raised `FrameRateLimit`
from 30 to 60. The ini timestamp is 19:48:37. `FSR_FG` and `DLSS_FG` stayed
off, dynamic resolution, VSync, ray tracing, and HDR stayed off. PID 141377
was still running with the isolated Turnip library mapped. Gamescope's own
FPS limit was still 60, and focus was still app 2074920. The launch option
was not changed. The kernel journal from 19:48 has no GPU hang, and the shader
cache had no new files.

From 19:49:18 to 19:50:20 the present rate was 35.7, 35.6, 35.0, 35.6, 35.9,
34.9, 35.8, 35.6, 35.7, 35.9, 35.7, and 35.9 FPS. That is about 36 FPS, inside
30 to 40, and it is not the 60 cap. The GPU stayed at 680 MHz and 94 to 96%
busy, at 81 to 83 C. The process used about 451 to 472% CPU. The prime core
stayed at its 2093 MHz Balanced profile cap, hardware max 2957 MHz, at 93 to 95 C.
Available RAM settled near 2.97 GB. Zram use stayed about 3.96 GB.

The real menu base is about 36 FPS. Native 1080p was 14, 720p with no upscaler
was 21.5, and the same FSR mode under a 30 cap sat at 30 with the GPU only 80%
busy. With the cap at 60 the GPU is full again, so the earlier spare time was
only about 6 FPS. Frame generation is not a sensible way to reach 60. The GPU
has no room for that pass, and 36 is a low base to interpolate. Keep Ultra
Performance. A 30 cap is the even choice. Leave frame generation off, and do
not step up to FSR Performance if the goal is to stay at 30.

### Menu benchmark, frame generation on

The user turned FSR frame generation on and allowed graphics-menu input on the
same home screen. PID 141377 stayed up the whole time, still on
`-nogpucrashdebugging` and the isolated Turnip library. The launch option was
not changed. Resolution stayed 1280x720, the cap stayed 60, ray tracing, HDR,
VSync, and dynamic resolution stayed off, and the low quality values stayed.
Gamescope's present counter is the displayed rate, including any generated
frames. This launch still has no Proton log and the game shows no split
counter, so the real render rate was not measured separately. The kernel
journal from 19:52 through the tests has no GPU hang.

| scene | displayed FPS | GPU | CPU | notes |
| --- | --- | --- | --- | --- |
| 1080p, no upscaler | 14 | 680 MHz, near full | ~270% | earlier |
| 720p, no upscaler | 21.5 | 97% busy | ~338% | earlier |
| 720p, FSR Ultra Performance, FG off | 36 | 94 to 96% busy, 81 to 83 C | ~460%, 93 to 95 C | real base, cap 60 |
| 720p, FSR Ultra Performance, FG on | 47 | 82% busy, 80 to 84 C, 680 MHz | ~520%, 94 to 95 C | best displayed |
| 720p, FSR Performance, FG on | 41 | 81 to 84% busy, 81 to 84 C | ~500%, 94 to 95 C | stable, slower |
| 720p, XeSS Quality, FG off | 7 | 99% busy, 76 to 77 C | ~210% | regression, removed |

Ultra Performance with frame generation, from 19:54:04 to 19:55:10, read 46.4
to 47.5 FPS across twelve windows, with one window at 49.8. That pacing is
even. It does not double the 36 FPS base, and the GPU was less busy than the
no-frame-generation run, so the extra presents are not 47 fully rendered
frames. Available RAM stayed near 2.9 GB. Zram use rose to about 4.10 GB and
later about 4.26 GB, and held flat inside each sample.

FSR Performance with frame generation was measured from 20:01:49 to 20:02:51
after a 20 second warm-up. It held 39.9 to 42.1 FPS. XeSS is in the Additional
Options list, next to Off, AMD FSR3, and Epic Games TSR. XeSS Quality applied,
frame generation was turned off first, and the home screen then held 6.8 to
7.2 FPS for a full minute. That branch stopped there. A mis-click selected TSR
for a few seconds. It was switched back before any TSR sample. TSR was not
benchmarked.

The restored choice is 1280x720, FSR Ultra Performance, FSR frame generation
on, cap 60. A check from 20:08:58 to 20:09:23 read 44.3 to 47.5 FPS, with one
dip while the GPU clock briefly left 680 MHz. The process was alive and
Gamescope focus was still 2074920. The menu is stable at GPU about 82 C and
CPU about 95 C. A mission was not entered.

### Further optimization study

The live stack is kernel 7.2.6, FEX
`2609^20260908git395b132`, Gamescope 3.16.29-ogc2, vkd3d-proton 3.1 in Proton
Experimental ARM64, and the isolated Mesa 26.2.3 Turnip. Turnip's
`VK_EXT_descriptor_buffer` path is active. The older vkd3d info capture calls
the memory topology UMA-like and confirms mutable descriptors and descriptor
buffers. `VK_EXT_descriptor_heap` is not exposed by this driver.

The hot-thread sample on the final menu had one game thread at 97% of a core,
RHI thread at 37%, another game thread at 36%, two foreground workers and the
render thread near 27% each, four background workers near 13% each, and RHI
submission near 11%. Total process CPU over that sample was about 361%.
vkd3d queue and fence threads were small. This is real FEX cost spread across
several threads, but it is not one render thread completely serializing the
frame.

The active game FEX config already has multiblock, x87 reduced precision, full
TSO with half-barrier optimization, and `FEX_DISKCACHE=1`. Its disk cache has
reached 1 GiB. FEX 2609 calls that cache experimental and says it reduces JIT
work and stutter on later launches, not steady GPU time. It has no eviction or
size limit yet. Enabling the FEX L2 lookup can reduce lookup stutter at the
cost of memory, but this process already leaves only about 3 GiB available and
uses 4 to 5 GiB of zram. It was not tested. Armada's Fast FEX profile disables
TSO; that changes x86 memory semantics and was rejected.

The game DRM client reports about 3.27 GiB resident in unified memory. There
is no separate VRAM. CPU pressure was material, but memory PSI was near zero
during the menu. The Mesa and Steam pipeline caches were warm. The
`vkd3d-proton.cache` file is 1.62 MiB. No new shader-cache writes occurred in
the later steady samples. Memory pressure is a zone-load risk, not the cause
of the steady menu limit.

Turnip exposes only aggregate DRM busy, cycles, and resident-memory counters
here. No bandwidth, GMEM, or per-renderpass counters are available without an
instrumented driver. Mesa's current Turnip autotuner already chooses between
GMEM and sysmem, and Mesa 26.1 added a DXVK/vkd3d preference for sysmem plus
mobile renderpass autotuning. No `TU_DEBUG` mode is active. Forcing either
GMEM or sysmem would override that logic and was rejected. Mesa 26.2.4 has no
A740 performance fix relevant to this title. Moving to Mesa main or a
community `-O3` build would combine many unvalidated changes with the sparse
patch and needs a separate CTS and A/B effort.

vkd3d-proton 3.1 already contains the mobile tiler work for deferred clears,
renderpass suspend and resume, and fewer query and resolve renderpass breaks.
`single_queue` disables asynchronous compute and transfer queues. Upstream
documents async compute as a performance path, and this process's extra queue
threads are not a major CPU consumer, so `single_queue` was not tested.
`no_upload_hvv` explicitly costs GPU performance. `force_static_cbv` is an
unsafe NVIDIA-only speed hack. `force_host_cached` is for captures.
`descriptor_heap` cannot work without the Vulkan extension. None was added to
the launch option.

Gamescope reports explicit sync, no Vulkan swapchain, no present backlog, and
zero presents in flight when queried. The physical composition path already
has a hardware plane and does not explain the 36 FPS real base. Its external
FSR, NIS, and SGSR filters see only the completed 1280x720 color image. They
cannot replace the in-game FSR3 pass, which has Unreal's depth, motion,
exposure, jitter, and reactive information. A spatial Gamescope filter could
only sharpen the final 720p-to-panel scale and would add work rather than
raise game FPS.

#### Armada Performance profile A/B

Balanced sets the A510 cluster to 1555 MHz, the middle cluster to 2054 MHz,
and the X3 to 2093 MHz with the conservative governor. These are profile caps,
not thermal cooling states. The thermal cpufreq cooling devices stayed at
state zero. Performance is the documented user profile. It sets 2016, 2803,
and 2957 MHz, the performance governor, a fixed 680 MHz GPU, and the
aggressive fan curve. It does not raise thermal limits or overclock.

The Balanced comparison, excluding the first transition interval and one
counter anomaly above the 60 FPS limit, stayed about 44 to 45 FPS. Performance
was warmed for 20 seconds, then measured for 60 seconds. It stayed 41.3 to
45.6 FPS, average 44.2, with GPU busy about 79%, GPU 81 to 84 C, CPU 94 to
96 C, and process CPU about 484%. There was no gain despite the X3 running at
2957 MHz and the fan reaching 7792 RPM. The profile was restored to Balanced.
The result indicates that the final displayed rate is dominated by GPU and
frame-generation scheduling, not the Balanced CPU ceiling.

#### Custom upscaler feasibility

In-game FSR3 is the only useful temporal path available without modifying the
title. Qualcomm SGSR1 is a one-pass spatial color filter. Gamescope 3.16.29
already lists `sgsr` as a scaling filter, so an external SGSR1 implementation
is already present. It may improve scaling quality, but it cannot improve
render FPS over FSR Ultra Performance.

SGSR2 is temporal. Qualcomm documents low-resolution color, depth, and motion
vectors as required inputs, with a convert pass and an upscale pass. The
open-source Unreal plugin must be integrated into the game or engine so those
resources and camera state are correct. Gamescope cannot recover them from
the final swapchain image.

A vkd3d temporal-upscaler layer would have to identify the title's color,
depth, motion-vector, exposure, and reactive resources, replace swapchain
sizing and presentation, track barriers and queue ownership, inject several
compute passes, and repeat that work for every title update. A generic Vulkan
hook does not reliably intercept vkd3d's internal dispatch path. A D3D12 proxy
or injected DLL would also be inappropriate for this BlackCipher-protected
title. It was not attempted.

The active result remains:

```text
1280x720
low preset
AMD FSR3 Ultra Performance
FSR frame generation on
60 FPS cap
ray tracing, HDR, VSync, dynamic resolution off
Armada Balanced power profile
```

The exact active launch option remains:

```text
VK_ICD_FILENAMES=$HOME/tfd-turnip-a740-sparse-2026-10-01/driver/freedreno_icd.game.json VK_DRIVER_FILES=$HOME/tfd-turnip-a740-sparse-2026-10-01/driver/freedreno_icd.game.json /usr/libexec/armada/armada-game-launch %command% -nogpucrashdebugging
```

PID 141377 stayed alive and focused. BlackCipher was not modified, the game
was not restarted, and no gameplay or account state was entered.

### Frame-generation bubble

The harness is `~/tfd-perf-2026-10-01/menu_bench.py` on Thor. Each run records
the Gamescope completed-present counter, single-present intervals, the game
process `drm-engine-gpu` busy time, GPU and X3 clocks, both thermal zones,
available RAM, zram, PSI, the saved graphics keys, and the focused app id.
Raw JSON is in that directory. The game stayed on the same lobby. Settings
stayed 1280x720, low, FSR Ultra Performance, 60 cap, ray tracing, HDR, VSync,
and dynamic resolution off. Armada stayed on Balanced. The durable patched
Turnip launch option was not changed. BlackCipher PID 141608 stayed up.

Two early runs, `fg-on-a` at 61.2 FPS and `fg-on-b` at 62.4 FPS, are discarded.
`GAMESCOPE_FOCUSED_APP` was 769, so those presents were Steam's, held at the
Gamescope 60 cap. Focus was put back on the title with the same base-layer
atom as before, on `DISPLAY=:0`:

```text
413091,2074920,769
```

After that, `GAMESCOPE_FOCUSED_APP` and `GAMESCOPE_FOCUSED_APP_GFX` were
2074920 for every timed run below. Frame generation was toggled from the
graphics menu and checked in `GameUserSettings.ini` before the timer started.
Esc returned to the lobby. No gameplay, matchmaking, purchase, or account
screen was opened.

| Run | Frame generation | Presents | FPS | GPU busy | p50 | p95 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| fg-on-focused | on | 1524 / 40.0 s | 38.1 | 71.9% | 23.6 ms | 47.9 ms |
| fg-on-focused-b | on | 1496 / 40.0 s | 37.4 | 69.8% | 25.3 ms | 49.7 ms |
| fg-off-a | off | 1327 / 40.0 s | 33.2 | 96.1% | 29.8 ms | 39.9 ms |
| fg-on-restore | on | 1689 / 40.0 s | 42.2 | 76.1% | 21.4 ms | 42.6 ms |

GPU clocks were 615 to 680 MHz on the clean runs. The restore run also
touched 475 MHz and 220 MHz, which is the simple_ondemand response to the
idle gaps, and it has 15 intervals over 80 ms. Temperatures stayed about
81 to 83 C on the GPU and 94 to 95 C on the X3. The two clean frame-generation
runs agree within 0.7 FPS. The off run is 4 to 5 FPS below them. The restore
average is higher, and part of that spread is the clock dip, so the stable
displayed gain is the 37 to 38 FPS pair against 33 FPS, not the 42 FPS sample.

The interval histogram is the bubble. With frame generation off, 758 of 1327
intervals sit in 25 to 33 ms and only 12 intervals are under 16 ms. The GPU
is full. With frame generation on, `fg-on-focused-b` splits: 544 intervals
in 33 to 50 ms and 258 in 12 to 16 ms, with another 295 under 12 ms. The
short intervals are the generated presents. The long intervals are longer
than the real frame was with frame generation off, and the GPU is only about
70% busy while they happen. Frame generation adds a short present, then the
following real present waits, and the Adreno is idle inside that wait.

A thread sample on the game process shows where the CPU time goes. One
`GameThread` (tid 141786) used 98% of a core and stayed on cpu7, the X3,
which Balanced holds at 2093 MHz. `AMD FSR Present` (tid 145207) used 87%
and moved across the A715 cores. It was usually running in userspace, and
when it slept the kernel stack was `ntsync_schedule` inside ioctl. `AMD FSR
Interpo` used 14% and spent the samples asleep on the same ntsync wait.
The render thread was about 27%. The earlier Performance-profile run already
raised the X3 to 2957 MHz and pinned the GPU at 680 MHz without lifting the
displayed rate, so this gap is not the Balanced clock cap.

vkd3d-proton 7f0c30ad does contain the staggered-submit scheduler, and its
comment names FSR3 frame generation on a single graphics queue. It does not
run on this device. `d3d12_command_queue_needs_staggered_submissions` returns
immediately when `tiler_suspend_resume` is set, and `d3d12_device_init_workarounds`
sets that flag for `VK_DRIVER_ID_MESA_TURNIP`. The same commit's Unreal
catch-all also sets `NO_STAGGERED_SUBMIT` for any `Win64-Shipping.exe` that
has no specific config override. `M1-Win64-Shipping.exe` is not in that
override table. Its only title entry is a shader quirk for one reflection
mip hash. Vulkaninfo on the isolated Turnip ICD reports one queue that is
graphics, compute, transfer, and sparse, with `queueCount` 1, plus a second
family that is sparse-binding only. There is no second 3D queue to overlap
the interpolation submit with the next real frame.

Re-enabling staggered submit would cross both of those choices. The tiler
path exists because splitting suspend/resume command buffers does not keep
a tiled GPU busy, and the Unreal flag exists because staggered submit caused
trouble on other shipping builds. Neither change is a semantics-preserving
patch for this title. No vkd3d or Mesa patch was built. The sparse-image
Turnip library and the durable launch option are unchanged. Frame generation
was left on because the repeated lobby runs still display more frames that
way, at 37 to 38 FPS versus 33 FPS, with the game focused and BlackCipher
still running.

### Why selective stagger and a second queue both stop

Two ways to overlap the interpolation compute with the next real frame were
checked against vkd3d-proton `7f0c30ad` and Mesa 26.2.3 Turnip. Neither is a
correct patch. No driver was rebuilt, and the running game was left on the
focused lobby with frame generation on.

Selective stagger cannot see a safe split for this title. The scheduler's
only interleave is a CPU `vkWaitSemaphores` between chunks of the lower
priority queue so another D3D12 queue can take the single `VkQueue`. At
execute time vkd3d already knows which command buffers keep a dynamic
render pass open: a fused pair is the case where `suspend.vk_fixup_cmd_buffer`
is set and `d3d12_command_list_render_pass_suspend_resume_avoids_fixup`
says the next list resumes it, so the suspend store is not emitted. Those
two Vulkan command buffers must stay in one submit. Any other boundary is
ambiguous once fixup, query-reset, and cleanup command buffers are mixed
into the same array. The conservative rule is therefore the one already
shipping: if the device uses suspend/resume, stagger nothing. On Turnip
that flag is always set. Unreal command lists that still have a render pass
at `Close()` take the suspending bit, so the graphics execute that would
have to yield is exactly the execute the gate must not split.

The public FSR 3.1.4 DX12 swapchain
(`FrameInterpolationSwapchainDX12.cpp` in the FidelityFX SDK) shows the
submits would not qualify even if the gate were looser. It creates
`AMD FSR PresentQueue` as a high-priority DIRECT queue and
`AMD FSR AsyncComputeQueue` as a high-priority COMPUTE queue, then leaves
interpolation on the game queue unless `allowAsyncWorkloads` is set.
`presentInterpolated` signals `gameFence` and the interpolation queue waits
on that fence before any interpolation command list. `Present` then waits
on `compositionFenceCPU` and inserts `gameQueue->Wait(presentFence)` so the
next real-frame submit cannot start until the presenter has signaled after
`Present`. The presenter thread (`AMD FSR Presenter Thread`) waits on
`interpolationFence`, spins in `waitForFenceValue` until
`compositionFenceGPU` completes, then `waitForPerformanceCount` until the
paced QPC target, then presents and signals `presentFence`. Those waits are
the 33 to 50 ms gaps. Staggering a compute-only chunk cannot start the next
real frame early, because the game queue has already been told to wait.
Ignoring that wait would be a broken fence.

A second Vulkan queue is not available as real concurrency. Mesa 26.2.3
hardcodes `queueCount = 1` on the graphics family. The comment above
`tu_gfx_queue_family_properties` says another queue in the family requires
a narrower scope in `nir_opt_acquire_release_barriers` (Mesa merge request
33504). `tu_emulate_second_queue` reports `queueCount = 2` only for the
Android HWUI engine, and `tu_queue_init` aliases that second `VkQueue` onto
the first kernel submitqueue. msm can create priority submitqueues and
Turnip probes `MSM_SUBMITQUEUE_ALLOW_PREEMPT`, but those queues are not
exposed as a second Vulkan queue, and a second queue would still have to
honor `ID3D12CommandQueue::Wait`. Raising `queueCount` was not attempted.
No CTS run was started, because there is no queue-count change to validate.

The sparse-image Turnip library and the durable launch option are unchanged.
Frame generation stays on.

### Present-gap split

`~/tfd-perf-2026-10-01/timeline.py` reads the Gamescope present counter and
the game's `drm-engine-gpu` counter at each completed present, and samples
whether `AMD FSR Present` and `AMD FSR Interpo` are running or sleeping.
The GPU file descriptor is resolved once, so the poll stays near 10 ms. The
focused lobby capture `211310-fg-on-timeline-b-timeline.json` is 25.01 s,
861 single-present intervals, poll 10.46 ms, focus 2074920, FSR Ultra
Performance, frame generation on, 1280x720, cap 60.

| Interval | n | Wall p50 / p95 | GPU p50 / p95 | Idle p50 / p95 | Presenter running | Interpolation asleep |
| --- | ---: | --- | --- | --- | ---: | ---: |
| under 20 ms | 340 | 12.6 / 18.9 ms | 7.2 / 16.8 ms | 7.6 / 16.0 ms | 1.00 | 1.00 |
| 33 to 50 ms | 261 | 40.2 / 48.0 ms | 33.7 / 42.3 ms | 8.8 / 18.1 ms | 1.00 | 0.75 |

The long gap is the real frame. Its extra length versus the short gap is GPU
time, 33.7 ms against 7.2 ms. The idle piece is about 8 ms on both. During
that idle the presenter thread stays runnable, so it is not blocked in
ntsync or in a kernel `Present`. The interpolation thread is asleep on its
event, which matches `WaitForSingleObject(presentEvent)` after the command
list has already been submitted. The earlier focused frame-generation-off
run was 33.2 FPS at 96.1% GPU, p50 29.8 ms, about 1 ms idle. A second
frame-generation-off timeline was not taken: the Off click did not change
`FSR_FG`, and Steam rewrote the Gamescope base layer back to itself between
attempts. Frame generation is still on. The graphics menu was left open.

Proton Experimental ARM64's `aarch64-unix/ntdll.so` implements
`NtQueryPerformanceCounter` with `clock_gettime`. A native
`CLOCK_MONOTONIC` spin on Thor has 1 ns resolution, zero backward jumps in
100000 reads, and an 8 ms spin finishes 0.37 us late at the median and 0.68
us late at p95 (max 40 us). That clock is not inserting the 8 ms. FEX does
not replace this counter; the x86 call reaches the same unix ntdll. The 8 ms
is the presenter's own `waitForPerformanceCount` target in the public FSR
3.1.4 source (`FrameInterpolationSwapchainDX12.cpp`): after `waitForFenceValue` on
`compositionFenceGPU`, it spins or sleeps until `previousPresentQpc +
presentQpcDelta`. `deltaToUse` is half the interpolation-thread frame
average, minus variance and `safetyMarginInSec`, and it is applied to both
the interpolated and the real present. With vsync off, `Present` uses sync
interval 0. The pace still runs.

No vkd3d, DXVK, Mesa, or FEX patch was built. Dropping `gameQueue->Wait` or
the fence spin would skip a wait the swapchain asked for. The sparse-image
driver and the durable launch option are unchanged.

The boundary is that 8 ms presenter pace, added on every present, on top of
a real frame that already takes about 34 ms of GPU. Public-source simulation
below shows that skipping it after every late real frame is not a useful fix.

### Public FSR pacer proof

The title's frame-generation DLL is:

```text
M1/Binaries/Win64/amd_fidelityfx_framegeneration_dx12.dll
size 1090832
SHA-256 1429c91128d59a20120dd09b189a7e7ddfecf7e7b700d825bce4c4c6e9c0d451
FileVersion 3.1.5.44888
ProductVersion 3.1.5.0
```

This corrects the working assumption that the bundled component was 3.1.4.
Its UTF-16 strings include `AMD FSR Presenter Thread`, `AMD FSR
Interpolation Thread`, and `AMD FSR PresentQueue`. Its PDB path names
`Kits/FidelityFX/framegeneration/dx12`, and its exports are the newer
provider API (`ffxCreateContext`, `ffxConfigure`, `ffxQuery`, and
`ffxDispatch`). The public FSR 3.1.4 source still matches the observed
pacer, and the same target calculation and wait are equivalent in
FidelityFX SDK tags 1.1.4, 2.0.0, 2.1.1, 2.2.0, and 2.3.0. There is no
newer public deadline fix to backport.

The full DX12 sample was not built. It depends on the FidelityFX Cauldron
sample stack and a Windows presentation environment, and the prior
LLVM-MinGW container and compiler archive are no longer present on Thor.
The relevant algorithm is platform-independent, so
`analysis/fsr3_1_4_pacer_sim.py` models the exact upstream state transition:

```text
target = previousPresentQpc + presentQpcDelta
present = max(compositionFenceCompletion, target)
previousPresentQpc = actual present QPC
```

Upstream already implements the proposed missed-deadline check.
`waitForPerformanceCount` reads QPC and returns immediately when current QPC
is at or past the target. The observed 8 ms therefore means the composition
fence completed before the target. It is intentional minimum spacing, not a
missed-deadline bug.

The standalone suite has 11 passing tests: on-time and late fences, late
generated and real frames, generated-before-real ordering, 60/90/120 Hz,
VSync on/off equivalence in the pacer, frame-cap input periods, completion
after target, QPC precision and signed-wrap guard, and stock versus absolute
catch-up spacing. The script and output are also archived on Thor:

```text
~/tfd-perf-2026-10-01/fsr3_1_4_pacer_sim.py
~/tfd-perf-2026-10-01/fsr-pacer-sim.json
```

With 33.7 ms real GPU work, 7.2 ms interpolation, a 12.6 ms observed present
delta, 120 Hz panel, and VSync off, 300 synthetic pairs produce:

| Policy | Displayed FPS | p50 | p95 | Sub-1-ms intervals | Mean pacer wait |
| --- | ---: | ---: | ---: | ---: | ---: |
| FSR 3 stock | 37.42 | 12.6 ms | 40.9 ms | 0 | 6.3 ms/present |
| absolute catch-up candidate | 48.98 | 0.0 ms | 40.9 ms | 300 | 0 |

The stock model reproduces the measured 37.4 FPS and the short/long split.
The candidate only raises throughput by presenting generated and real images
back-to-back after every late frame. Half of all intervals collapse to zero.
That destroys pacing and makes the generated image pointless. It is not an
upstreamable fix.

No patch is saved under `mesa/` because no correct source change
was found. Nexon does not need to update its FSR integration for a missing
deadline check. A useful integration change would need a different policy,
such as dropping an already-late generated frame or decoupling next-frame
rendering from real-present completion. That changes quality and latency
semantics and needs AMD and Nexon to design it, not a local backport.

The game and BlackCipher stayed alive, focus was restored to 2074920,
`FSR_FG=True`, and the durable patched-Turnip launch option was unchanged.
The graphics menu remains open because repeated Esc and Back input did not
close it reliably; no gameplay or account action was entered.

### Real frame: GPU-bound, no generic patch

The real frame is the focused lobby capture
`~/tfd-perf-2026-10-01/204625-fg-off-a.json`, not the later frame-generation
runs. Settings were 1280x720, FSR Ultra Performance, frame generation off,
Low, 60 cap, ray tracing, HDR, VSync, and dynamic resolution off. Over
40.002 s it completed 1327 presents, 33.17 FPS. Frame time was p50 29.82 ms,
p95 39.93 ms, p99 44.53 ms. 758 of 1327 intervals were 25 to 33 ms, 12 were
under 16 ms, and one was at least 50 ms. GPU busy was 96.1 percent at the
top bin, 680 MHz, with three samples at 615 MHz. The prime core stayed at
the Balanced cap, 2092.8 MHz. Memory pressure was not the limiter (PSI
memory avg10 0.10). Idle inside the frame is about 1.2 ms, so this is not
the 60 cap and it is not the FSR presenter wait.

That classifies the real frame as GPU-bound. It does not yet say whether
the GPU time is ALU, texture, bandwidth, or a driver synchronization tax.
The live msm fdinfo on this process exposes `drm-engine-gpu`,
`drm-cycles-gpu`, `drm-maxfreq-gpu` (680 MHz), and resident memory. It does
not expose shader-core, texture, cache, GMEM, or bus counters. debugfs and
tracefs are mode 0700, so `/sys/kernel/debug/dri` is unreadable and fdperf
or perfetto cannot attach. Those tools are not installed. The isolated
Turnip ICD does not advertise a Vulkan performance-counter query.
`TU_DEBUG=perfc` would need that same kernel interface and a relaunch.
`TU_DEBUG=sysmem`, `gmem`, `flushall`, and `syncdraw` change rendering
behavior, so they were not used. Turnip's vkd3d drirc entry already sets
`tu_autotune_algorithm=prefer_sysmem`.

A new FG-off lobby window was not captured in this pass. The graphics menu
was still open. Gamescope focus was 2074920 and X11 focus was window
0x2400001, with the pointer on the Off pill, but button clicks, Right, and
a uinput Escape did not rewrite `GameUserSettings.ini` and did not close
the menu. `FSR_FG` stayed True. The ini was not edited behind the game and
the process was not relaunched. The survey is
`~/tfd-perf-2026-10-01/real-frame-counter-survey.txt`.

Mesa main after 26.2.3 has no generic Adreno 740 performance commit that
matches this frame. The Turnip and IR3 commits since 16 September 2026 are
error handling, LRZ stencil tagging for a narrow case, multiview, quad
control, disk-cache serialization, and IR3 source-mod and quirk fixes.
None of those is evidence of a spill, flush, or autotune bug in this
workload, so none was backported. vkd3d-proton after 7f0c30ad adds
`adreno_7xx_extra_compat` (959639435c). Its own comment says it enables
slower paths, strict byte-address wrap, min16 denorms, and a wave128
workaround for debugging. It is not a performance fix and it was not
enabled.

No patch was written. Changing title shader code, stripping precision, or
guessing an ALU rewrite without a counter split would not be an upstream
change. The counter path that can split this frame is prepared below. It
needs one privileged process. It was not run from here.

The game (PID 141377) and BlackCipher (PID 141608) stayed alive. Focus was
2074920. Frame generation is still on, which is the configuration to keep.
The durable patched-Turnip launch option is unchanged. The graphics menu
is still open. Escape on that menu returns to the lobby. Escape on the
lobby is Exit Game, so it should not be pressed once the lobby is back.

### Rootless counters: the sampling ioctl needs CAP_PERFMON

Kernel `7.2.6` has `CONFIG_DRM_MSM=y` and `CONFIG_DEBUG_FS_ALLOW_ALL=y`.
The debugfs mount is still mode 0700, so the directory cannot be listed
as the user. The msm debugfs files on this kernel are `gpu`, `kms`,
devfreq tunables, and `shrink`. There is no perfcntr file. `setfacl` on
debugfs would not expose SP, TP, UCHE, or VBIF, and it would expose the
GPU state and shrink files. That was not done.

fdinfo on the live client still has only `drm-engine-gpu`,
`drm-cycles-gpu`, `drm-maxfreq-gpu`, and resident memory. fdperf,
perfetto, and perf are not installed. Building them in a home directory
would not add a permission the kernel does not grant.

The real interface is `DRM_IOCTL_MSM_PERFCNTR_CONFIG` (command `0x0E` in
Linux 7.2 `include/uapi/drm/msm_drm.h`). Two uses:

- `MSM_PERFCNTR_STREAM` asks the kernel to program the group's select
  registers and read the counter registers on a timer. `msm_ioctl_perfcntr_config`
  returns EPERM unless `perfmon_capable()` (CAP_PERFMON or CAP_SYS_ADMIN).
  A call from uid 1000 on `/dev/dri/renderD128` returned EPERM. This is
  the whole-GPU sampler. It does not use debugfs.
- Without that flag the same ioctl only reserves counter slots for the
  calling DRM file. That call returned success and produced no samples.
  Mesa main uses this reservation so Turnip can emit CP snapshots inside
  `VK_KHR_performance_query` begin and end (`tu_query_pool.cc` on main,
  plus `src/freedreno/perfcntrs/freedreno_perfcntr.c`). The isolated
  Mesa 26.2.3 driver does not advertise that extension. The game never
  records those queries. Backporting the query implementation would not
  observe this already-running process unless the driver also injected
  queries into the title's command stream and the game was relaunched.
  That is not a small patch, and it was not written.

No driver patch is under `mesa/`. The sampler is
`tools/msm_perfcntr_sample.py`, copied to
`~/tfd-perf-2026-10-01/msm_perfcntr_sample.py`. Running it as the user
prints EPERM and writes nothing.

Before the command: leave the graphics menu (Escape there returns to the
lobby), set FSR frame generation off, keep 1280x720, FSR Ultra
Performance, Low, cap 60, and RT, HDR, VSync, and dynamic resolution off.
Gamescope focus must be 2074920. The script refuses any other focus or
`FSR_FG` value. After it finishes, turn frame generation back on.

```text
sudo --preserve-env=DISPLAY,XAUTHORITY,XDG_RUNTIME_DIR \
  python3 $HOME/tfd-perf-2026-10-01/msm_perfcntr_sample.py \
  --seconds 20 \
  --pid 141377 \
  --out $HOME/tfd-perf-2026-10-01/perfcntr-fg-off.json
```

What that one process unlocks, at 5 ms for the whole GPU: SP busy, ALU,
EFU, TP/UCHE/RB stalls, wave context and idle, fragment ALU and texture
instruction counts, instruction-cache miss rate, TP L1 miss rate, UCHE
stalls, UCHE VBIF read and write beats (the a7xx stand-in for VBIF;
GBIF is not a selectable group), CCU GMEM read and write, and CP sync
stalls and cache flushes. It also records fdinfo busy and the GPU clock
across the same window. It is not per-renderpass. Register spills are
not a hardware counter in this set. Wave contexts per cycle is the
occupancy signal it can report.

Security: sudo gives this process CAP_PERFMON. It opens the render node,
programs the upstream perfcntr select registers from the fixed a7xx
countable list, and reads those counters. It does not run the game as
root, does not read the game's memory, and does not change debugfs. It
holds the one global stream until it exits, so a second sampler gets
EBUSY. Select-register programming is the kernel's own profiling path
and does use the hardware counter slots while it runs.

Rollback is process exit. Ctrl-C or a normal finish closes the anon fd
and the kernel drops the stream. Confirm with:

```text
sudo python3 $HOME/tfd-perf-2026-10-01/msm_perfcntr_sample.py --status
```

That opens the stream and releases it immediately. Do not `chmod` or
`setfacl` debugfs.

### Capture prep at 22:16: the game stopped presenting

The capture was not prepared. Game PID 141377 and BlackCipher PID 141608
are alive and Gamescope focus is 2074920 on window 0x2400001, but the
game no longer presents frames. Gamescope's completed-present counter did
not move during 10 s and 3 s windows with the game focused (361024 before
and after). It moved only while Steam was briefly shown. Screenshots from
22:06 to 22:16 are byte-identical: the graphics menu with FSR frame
generation On. GPU busy is still about 95 percent at 615 MHz. The `AMD FSR
Presenter` and `AMD FSR Interpolation` threads no longer exist in the
process.

The game ignores input from every route tried. XTest clicks, keys, and
motion on `:1`, a WM_TAKE_FOCUS message, and uinput keyboard and mouse
devices that Gamescope opened (confirmed in its fd table) did not move the
game cursor or change `GameUserSettings.ini`. Its mtime has not changed
and `FSR_FG=True`. The game's X socket has no unread backlog, and
Gamescope reports keyboard and input focus on the game window. The most
likely cause is that the first Off click started a frame-generation
teardown that did not finish: the FSR threads exited, the toggle was not
saved, and no frame reaches Gamescope. That is inferred, not proven.
Proton logging is off in this launch, and the kernel log has no msm fault
lines.

The game was not killed or relaunched, and the ini was not edited. The
sampler would refuse to run, correctly, because `FSR_FG` is True. The fix
is a normal user restart of the game: exit it from Steam (or force-stop
it), then launch with the unchanged per-game option. On the lobby, use the
touchscreen or controller to set FSR frame generation off. Leave the menu
with Back, check that `FSR_FG=False` is saved, then run the sudo command
above with the new game PID.

### False focus refusal after the restart

After the restart the lobby was valid: game PID 201208, BlackCipher PID
201446, `FSR_FG=False`, 1280x720, FSR Ultra Performance, Low, cap 60, RT,
HDR, VSync, and dynamic resolution off. A later sampler run reported focus
None. The Gamescope atom was 2074920 the whole time, including six reads
over about 9 s at 33.4 FPS and 95.8 percent GPU busy. Display `:0` has
access control limited to `SI:localuser:armada`, so `xprop` inside the
sudo process is rejected and the script treated the empty reply as no
focus. The script now runs that one `xprop` through `runuser` as the
invoking user. The X host list was not changed, and no input was sent.

A rerun then reported focus 769. The game (PID 201208) and BlackCipher
were still alive, `FSR_FG` was still False, and frames were presenting.
Steam had the Gamescope focus list at that moment. By the next check the
base layer was already `413091, 2074920, 769` and focus stayed 2074920
for 24 s, so Steam was not continuously reclaiming it. Xwayland `:0` is
started without `-auth` and `/run/user/1000/xauth_*` does not exist, so
no X authority file is required for this user. The sampler now waits up
to 30 s for focus 2074920, records focus during the capture, and marks
the file invalid if focus leaves the game. The launch command is
`ssh -t thor ~/tfd-perf-2026-10-01/run_counters.sh`.

### FG-off counter capture

The sampler completed: `~/tfd-perf-2026-10-01/perfcntr-fg-off.json`, 4027
samples, 0 gaps, valid, focus 2074920 for all 20 focus reads, PID 201208,
20.142 s. Settings were the FG-off lobby: 1280x720, FSR Ultra Performance,
Low, cap 60, RT, HDR, VSync, and dynamic resolution off. fdinfo GPU busy
was 19.339 s, 96.0 percent. The sample timestamp advances at 19.190 MHz
(median step 96002 ticks, 5.000 ms). That is the always-on clock, not the
GPU core clock. `CP_BUSY_CYCLES` is 672 MHz over the GPU-busy time, which
matches the 550 to 680 MHz devfreq bins, so CP counts core clocks. SP
counters run 8.90 times the CP count, so they are summed across shader
instances. Ratios inside one group cancel that factor.

Every counter was monotonic. The sum of 5 ms steps equals the last-minus-first
span, so nothing wrapped and the sampler ratios are not a math error.
`drm-cycles-gpu` fell by 5.43e7 between the two fdinfo snapshots while
engine time rose. Those two cycle reads are not used. UCHE GMEM beat
counters stayed at 0 for every sample, so they do not count this workload.
CCU GMEM counters do.

Normalized over 20.142 s:

| Signal | Value |
| --- | ---: |
| SP ALU working / SP busy | 0.433 |
| SP EFU / SP busy | 0.089 |
| SP stalled on TP / SP busy | 0.176 |
| SP stalled on UCHE / SP busy | 0.136 |
| SP stalled on RB / SP busy | 0.006 |
| SP wave idle / SP busy | 0.014 |
| SP wave wait / SP busy | 0.140 |
| Wave contexts / context-cycle | 7.61 |
| FS full-ALU / FS texture, raw | 23.66 |
| FS half-ALU / FS full-ALU | 0.016 |
| SP instruction-cache miss | 0.0007 |
| TP L1 miss / L1 request | 0.588 |
| TP stalled on UCHE / TP busy | 0.494 |
| TP starved by SP / TP busy | 0.659 |
| UCHE arbiter stall / UCHE busy | 0.140 |
| UCHE VBIF latency | 197 cycles, 293 ns at 672 MHz |
| DRAM read | 5.49 GiB/s (32 bytes per beat, Mesa fd7) |
| DRAM write | 1.39 GiB/s |
| Texture share of read beats | 0.658 |
| CP SQE sync stall / CP busy | 0.407 |
| CP cache flushes | 5523/s |

The 5 ms bins split the story. The busiest SP quartile has 4.73 times the
TP stall and 2.22 times the UCHE stall of the quietest quartile, but only
0.76 times the ALU cycles, 0.47 times the texture read beats, and 1.01
times the CP sync stall. Cache flushes are lower in the busy bins, not
higher. So the intervals that stretch are texture-latency stalls: the
shader core waits, fewer requests complete, and the bus is quieter. They
are not extra ALU, not a flush storm, and not a bandwidth spike. L1 misses
correlate with TP-UCHE stalls at 0.69. CP sync stall does not correlate
with SP busy (0.03), so that steady 41 percent is the command processor
waiting on a busy GPU, not the variable cost.

This is not a proven driver bug. The fragment shaders issue about 24
full-precision ALU counter ticks per texture tick, and half-precision ALU
is 1.6 percent of full. Forcing lower precision would change results.
External bandwidth is a small fraction of the 8 Gen 2 bus, so UBWC would
be saving bytes that are not the limit. CCU GMEM traffic is higher in the
fast bins, which is the opposite of a sysmem-fallback stall. Instruction
cache misses are 0.07 percent. Occupancy is 7.6 contexts with 1.4 percent
wave idle, which is not an empty machine and is not evidence of spills.

No patch. The next experiment is per-render-pass GPU time on this same
FG-off lobby, enough to see whether one pass owns the TP stall, before any
tiling, UBWC, or sysmem change. That needs a timestamp query in the
isolated driver and a relaunch. The raw capture is unchanged.

After the capture, `FSR_FG` was already True. Focus had drifted to Steam
and was put back on 2074920. The game and BlackCipher were still the same
PIDs. The launch option was unchanged. No graphics click was sent.

## Install

- App 2074920, build `25625698`, depot 2074921 manifest `4051971590687371757`
- StateFlags 4, UpdateResult 0
- Downloaded 79449709520 of 79449709520 bytes, SizeOnDisk 80564894200
- Content log at 12:14:17: scheduler finished, result No Error

## Test system

- AYN Thor Max, Armada `20260926.c2fd048`, kernel 7.2.6, 4096-byte pages
- FEX `2609^20260908git395b132`
- GPU: Turnip Adreno (TM) 740, Mesa 26.2.3
- Steam client build 1790721607 (`steamdeck_publicbeta`)
- Proton Experimental ARM64, Steam app 4427310, build 25551720, version `experimental-11.0-20260924-cache-arm64`
- Compat mapping: `proton-experimental-arm64` (unchanged)
- Launch option: `/usr/libexec/armada/armada-game-launch %command%` (unchanged)

## EULA

The first two launch attempts (12:18 and 12:36) stopped at `LaunchApp waiting for user response to ShowEula`. Steam was restarted once with `2074920_eula_0` set to `1` in `localconfig.vdf` (the same key Goose Goose Duck has). The 12:58 launch went straight to the install script without showing the agreement, so no Agree click was needed.

## Integrity check after the run

SHA-256 prefixes matched the pre-launch values:

```text
f6a52adbb75c0155  EasyAntiCheat/EasyAntiCheat_EOS_Setup.exe
e8049d2cf8b0397c  M1/Binaries/Win64/BlackCipher/NGService64.exe
e023c8b7a299ae77  M1/Binaries/Win64/BlackCipher/BlackCipher64.aes
8c88205c5bee15d8  M1/Binaries/Win64/BlackCipher/BlackCall64.aes
21a659279db75362  M1/Binaries/Win64/BlackCipher/config.bc
```

Those prefixes are from the stock launches earlier in the day. They were not hashed again after the patched-driver crashes. After the warn capture, no game, Wine, or security process for app 2074920 was left, and Steam stayed up in gamescope Big Picture.

## Logs on the Thor

```text
~/.local/share/Steam/logs/console_log.txt          launch chain, 12:58:51 to 13:07:00, and the logged launch at 13:16
~/.local/share/Steam/logs/content_log.txt          install completion, 12:14:17
~/tfd-proton-2026-10-01-1323.log                  Proton log from the 13:23 -log launch, 12220 bytes
~/steam-2074920.log                                same 13:23 log; the 13:16 7.8 MB log was replaced when this launch started
~/tfd-hardware-message-2026-10-01.png              capture of the error dialog
~/tfd-launch-monitor-2026-10-01.log                process monitor output
~/tfd-turnip-a740-sparse-2026-10-01/              patch, isolated driver, CTS and launch evidence
~/tfd-turnip-a740-sparse-2026-10-01/steam-2074920-vkd3d-instrumented-isolated.log
~/tfd-turnip-a740-sparse-2026-10-01/steam-2074920-vkd3d-caller.log
~/tfd-turnip-a740-sparse-2026-10-01/steam-2074920-vkd3d-nogpu.log
~/tfd-turnip-a740-sparse-2026-10-01/steam-2074920-wave32-shader-dump.log
~/tfd-turnip-a740-sparse-2026-10-01/steam-2074920-tsr-waveops0.log
~/tfd-turnip-a740-sparse-2026-10-01/steam-2074920-wave32-outcome.log
~/tfd-turnip-a740-sparse-2026-10-01/wave32-outcome/
~/tfd-turnip-a740-sparse-2026-10-01/presentation-2026-10-01/
~/tfd-turnip-a740-sparse-2026-10-01/steam-2074920.log            presentation run, renamed to steam-2074920-presentation.log after exit
~/tfd-turnip-a740-sparse-2026-10-01/wave32-shaders/
~/tfd-turnip-a740-sparse-2026-10-01/vkd3d-instrumented/logs/
~/.local/share/Steam/steamapps/common/The First Descendant/M1/Binaries/Win64/BlackCipher/NGService.log
~/.local/share/Steam/steamapps/compatdata/2074920/pfx/drive_c/users/steamuser/AppData/Local/M1/Saved/
```

### Command-list GPU timestamps

The pass owner is still not known for the FG-off lobby. The instrumentation is in vkd3d-proton `7f0c30ad`, patch `diagnostics/vkd3d-proton-7f0c30ad-pass-timestamps.patch`, recipe `diagnostics/vkd3d-pass-timestamps-recipe.md`. It records one Vulkan timestamp pair per D3D12 command list, reads them on a worker with availability bits, and does not wait on the queue in the submit path. No shader binary or source is written. The Adreno 740 clock check stands: period 52.083332 ns, 48 valid bits, no calibrated timestamps.

The first live capture only wrote the CSV header. `Reset` opens the command buffer and then cleared the timestamp state, and the tiler suspend path ends that buffer before `Close`. Both are fixed in the patch. A later capture also repeated old query results; the worker now host-resets a slot after it has read it. The raw file is `~/tfd-perf-2026-10-01/pass-ts.csv`. It contains NUL padding, so strip NULs before parsing. A short ranking is `~/tfd-perf-2026-10-01/pass-ts-summary.txt`.

FG was not turned off. Steam kept input focus on app 769 while the game window stayed the graphics focus. The existing click script aborts unless focus is 2074920, and the earlier automated Off click wedged presents, so it was not run again. `FSR_FG` stayed True. Resolution, FSR Ultra Performance, Low, cap 60, and the RT, HDR, VSync, and dynamic-resolution keys stayed as before.

During that FG-on scene, frame ids tracked Gamescope presents: 66 frame ids and 67 presents in 3 seconds, about 22 per second. That is not the 33.17 FPS FG-off lobby, so overhead against that baseline was not measured. The per-frame sum of list deltas is about 105 ms, longer than the roughly 45 ms present interval, so the lists overlap and the sum is not a split of one frame. Percentages below are median list time divided by 30 ms.

Steady single-pass lists, median and p95, graphics unless noted:

- 9.22 ms (p95 9.41), 30.7% of 30 ms, once a frame. PSO `0415327867ef7bbd`, fragment `1e9734cc38264910`, 89 draws, 1280x720, 1 sample.
- 7.38 ms (p95 7.50), 24.6%, once a frame. PSO `caa4de38b5064bd4`, fragment `7f9596c416d763b9`, 1 draw, 512x512.
- 6.75 ms (p95 8.59), 22.5%, twice a frame. PSO `08a9cff9cfad8bd6`, fragment `772ca6a9b2be01a2`, 89 draws, 1280x720.
- 4.13 ms (p95 4.32), 13.8%, once a frame. PSO `6384cfe7850f30e6`, fragment `93d87fbeb5b08f9e`, 89 draws, 1280x720.
- 3.13 ms (p95 3.21), 10.4%, compute. PSO `644f0bf17a7830a6`, shader `070d87bc28351078`, 24 dispatches, 320x180.

These are fragment draws plus one smaller compute list. No copy or sync list is in that set. That lines up with the earlier SP/TP/UCHE picture, fragment ALU plus texture miss, not DRAM, spill, or occupancy. vkd3d meta flags on these hashes were 0, so it did not mark native 16-bit or FP64. SPIR-V size was recorded as 0. No IR3 text was dumped. Nothing there is a proven compiler or driver bug, so no Mesa change was made. The sparse-image patch is unchanged.

Next capture: FG off on the lobby, with the game's input focus actually on 2074920, same list scope. If `0415327867ef7bbd` and `08a9cff9cfad8bd6` still lead, read Turnip IR3 stats for those hashes only (half versus full, texture count, spills) without printing shader text. Pass scope is not the next step for these single-pass lists.

After the capture the prefix `d3d12.dll` and `d3d12core.dll` were copied back from stock Proton Experimental ARM64 (d3d12core 9306112 bytes). The durable launch option is the patched Turnip ICD plus `armada-game-launch` and `-nogpucrashdebugging`, with no `VKD3D_PASS_TIMESTAMPS` and no isolated Proton wrapper. The restored process is PID 230714, BlackCipher PID 231044, stock d3d12core mapped, Turnip sparse build mapped, `FSR_FG=True`.

### FG-off lobby timestamps

The user turned FSR frame generation off in the graphics menu and returned to the lobby. Saved settings at 04:39 were `FSR_FG=False`, 1280x720, FSR Ultra Performance, Low (`sg.ViewDistanceQuality=0`, `sg.ShadingQuality=0`, `sg.ResolutionQuality=100`), cap 60, ray tracing, HDR, VSync, and dynamic resolution off. Stock process 233780, BlackCipher 234023, focus 2074920, patched Turnip mapped, stock `d3d12core.dll` (9306112 bytes), no timestamp env.

A 15.1 s stock window with focus on 2074920 the whole time presented at 36.42 FPS, GPU busy 95.8%. That is the same-session FG-off lobby baseline. The older 33.17 FPS capture is the historical baseline.

The instrumented relaunch used the same ARM64X build as the previous run (`d3d12core.dll` SHA-256 prefix `60c3177e`, the Reset, tiler-suspend, and host-reset fixes). Focus stayed 2074920 for every one of the 20 one-second samples. BlackCipher was 236650. No graphics click was sent. The full 20 s averaged 19.17 FPS. The last 7 s, after warm-up, were 26.4 FPS (frame time 37.8 ms), GPU busy 97.2% over the whole window. Against 36.42 FPS that steady rate is 27% slower. Against 33.17 FPS it is 20% slower. The under-2% target was missed. List intervals still overlap (sum about 107 ms), so the milliseconds below are not a partition of the frame, and the missed overhead budget means they include timestamp cost on top of the draws.

Steady single-pass lists, 169 focused frames, median and p95. Share is of the 37.8 ms instrumented frame:

- 9.19 ms (p95 9.38), 24% of the frame, once a frame. PSO `0415327867ef7bbd`, fragment `1e9734cc38264910`, 89 draws, 1280x720, 1 sample.
- 7.41 ms (p95 7.59), 20%, once a frame. PSO `caa4de38b5064bd4`, fragment `7f9596c416d763b9`, 1 draw, 512x512, 1 sample.
- 6.76 ms (p95 8.57), 18% each and twice a frame. PSO `08a9cff9cfad8bd6`, fragment `772ca6a9b2be01a2`, 89 draws, 1280x720.
- 4.11 ms (p95 4.30), 11%, once a frame. PSO `6384cfe7850f30e6`, fragment `93d87fbeb5b08f9e`, 89 draws, 1280x720.
- 3.23 ms (p95 4.42), 9%, compute. PSO `644f0bf17a7830a6`, shader `070d87bc28351078`, 24 dispatches, 320x180.

Those five still lead, in the same order, and the medians match the earlier FG-on instrumented run within a few hundredths of a millisecond. Turning frame generation off did not change which lists own the time. vkd3d meta flags on these hashes were 0: no native 16-bit bit and no FP64 bit. SPIR-V size was 0.

The 512x512 list is one graphics draw and one render pass. Its p95 is 7.59 ms against a 7.41 ms median, so the cost is steady rather than a variable queue stall. It shades about 3.5 times fewer pixels than the 9.19 ms 1280x720 pass and still takes 80% as long, about 28 ns per pixel against about 10 ns per pixel for that 720p pass. That is a fat fragment shader, not a copy or a clear. This Turnip build only prints half versus full ALU, cat5 texture count, and register pressure as comments on the IR3 disassembly path. There is no stats-only switch. Disassembly was not enabled, and no shader text was saved. Nothing in the flags or the timing proves an IR3 lowering bug, a spill, or a redundant texture fetch, so no compiler patch was made.

After the capture the prefix DLLs were copied back from stock Proton (d3d12core 9306112 bytes) and the durable launch option was restored: patched Turnip ICD, `armada-game-launch`, `-nogpucrashdebugging`, no timestamp env, no isolated Proton wrapper. The running process is PID 238774, BlackCipher PID 239044, stock d3d12core, Turnip sparse build, `FSR_FG=False`. A 10 s sample about two minutes after that launch was 19.4 FPS at 98% GPU, and Gamescope was not publishing `GAMESCOPE_FOCUSED_APP`, so that sample is not a second lobby baseline. Frame generation was left off.

### IR3 numeric stats

Stock vkd3d already names a shader module with the 16-hex `meta.hash` when `VKD3D_CONFIG=debug_utils` is set. It does not put the PSO hash on the module. The stats hook reads that name and writes one numeric line per compiled variant. The line is the shader hash plus stage, binning, full and half ALU, full and half SFU, cat5 texture count, sampler and image counts, full and half registers, max waves, subgroup size, spill bytes, stp/ldp, branch and predicate counts, branch stack, nops, sync stalls, input and output counts, and the category counts the compiler already stores. It does not print instructions, constants, or source. `TU_IR3_STATS` must be a path or the hook does nothing. The patch is `mesa/mesa-26.2.3-turnip-a740-ir3-stats.patch`, applied on top of the sparse-image patch. The rebuilt library is `~/tfd-turnip-a740-sparse-2026-10-01/driver-stats/lib64/libvulkan_freedreno.so`, SHA-256 `8e3babd08393e734389c3528db2bb10b68564c24ee59a09de77cc4e1a69b0c5c`. It was not installed over the system driver. The CTS-tested library `dac166671e9e1b8948eb098099f65a4d45a2837cd1c9a13ca46d9477b85bca97` was left in place.

`vulkaninfo` with that ICD enumerated Turnip Adreno 740, Mesa 26.2.3, API 1.4.354. Two game launches with `TU_IR3_STATS`, `VKD3D_CONFIG=debug_utils`, stock vkd3d, and `-nogpucrashdebugging` never got there. Each stayed at 29 threads and about 924 MB, never opened a DRM device, never started BlackCipher, and never created the stats file. The same session on the normal patched driver then started BlackCipher, grew to about 3.9 GB and 134 threads, and ran a render thread plus `PSOPrecompilePool`. No stats rows exist for the five hashes. The 512x512 explanation is still the timing one: one draw, 262144 pixels, median 7.41 ms and p95 7.59 ms, about 28 ns per pixel against about 10 ns per pixel for the 9.19 ms 1280x720 pass. That is steady fragment work, not a copy or a clear. Without the IR3 counts it does not show a spill, an avoidable FP32 lowering, a redundant fetch, or a scheduler bug.

No compiler fix. Frame generation was left off. The durable launch option is the normal patched Turnip ICD again, with no `TU_IR3_STATS` and no `debug_utils`. Prefix `d3d12core.dll` is stock, 9306112 bytes. The running process after that restore is PID 263699, BlackCipher PID 264037, `FSR_FG=False`.

### Unresponsive session at 05:55

PID 263699 was alive when checked, not the old graphics-menu freeze. Elapsed about 23 minutes, about 225% CPU, RSS about 3.9 GB, 134 threads, DRM `renderD128` open, mapped library `~/tfd-turnip-a740-sparse-2026-10-01/driver/lib64/libvulkan_freedreno.so`. BlackCipher PID 264037 was alive. Steam PID 262373 and gamescope PID 262295 were alive. One `steamwebhelper` was a zombie. The process env had no `TU_IR3_STATS`, no `VKD3D_CONFIG`, and no `VKD3D_PASS_TIMESTAMPS`. Prefix `d3d12.dll` was 229376 bytes and `d3d12core.dll` was 9306112. `FSR_FG=False`, ini mtime 05:36:12, 1280x720, FSR Ultra Performance, cap 60. No AMD FSR Presenter or Interpolation threads. GPU time was about 100% busy at 680 MHz, then about 58% at 615 MHz. The user-readable kernel log had no msm hang or fault. `GAMESCOPE_FOCUSED_APP` was missing. The base layer was still `413091, 2074920, 769`. The focused X window `0x400000` was the KDE Wayland host, not the game.

A Gamescope screenshot at 05:57:33, `~/tfd-perf-2026-10-01/recover-0555.png`, is the system-requirements Notice ("Gameplay may be unstable. Please check the minimum system requirements." with Confirm). It is not the graphics menu. That rules out the known FG teardown: frame generation was already off, the FSR threads were already gone, and Gamescope could capture a new frame.

At 05:58:32 Steam wrote `/tmp/dumps/assert_20261002055832_61.dmp` and started an out-of-process upload. Gamescope then logged "DRM lease broker disconnected", the Wayland connection broke, mangoapp PID 262356 dumped core, and `armada-bottom-screen.service` failed. The session came back at 05:58:43, which took the game with it. The dump file does not contain the text of the assertion. A separate, earlier console line at 05:06:25 is `CSteamEngine::BMainLoop appears to have stalled > 15 seconds without event signalled`. Xwayland `:1` did not answer `xprop` during the inspection. The durable launch option was already the normal sparse Turnip ICD plus `armada-game-launch %command% -nogpucrashdebugging`, so Steam was not shut down to edit it.

One relaunch at 06:01:13 used that option. PID 270342, BlackCipher 270783, normal sparse Turnip mapped, pressure-vessel ICD override, no stats or timestamp env. The game rewrote `GameUserSettings.ini` at 06:02:17. Size stayed 35439 and `FSR_FG` stayed False. The frame went from the Nexon and Magnum splash (`recover-0602.png`) to the same Notice (`recover-0604.png`). Focus was set back to app 2074920, base layer `413091, 2074920, 769`, with no game input, so Confirm was not pressed and the lobby was not entered. A 6 second window on that notice completed presents 12838 to 12954, 19.33 FPS, none in flight. Focus stayed 2074920. BlackCipher stayed up. Frame generation was left off.

Verification from 06:06 to 06:09: the game is healthy, so it was not restarted again. It is still PID 270342 (`M1-Win64-Shipping.exe M1 -steam -nogpucrashdebugging`), with BlackCipher 270783. The user pressed Confirm, turned frame generation on (the ini was saved at 06:05:32 with `FSR_FG=True`, 1280x720, FSR Ultra Performance, cap 60), and loaded into Albion. A 12 s window at 06:07 completed only 3 presents at about 1% GPU. That was the Albion loading screen (`verify-0608.png`), not a hang: the game used about 340% CPU and the kernel reported memory pressure, with 1.5 GB available and 7.8 GB of zram in use. Over the next 50 s, the rate per 10 s window was 11.3, 13.2, 17.2, 24.3, then 21.2 FPS, with the GPU at 50 to 86 percent. At 06:09 it was 29.7 and then 25.1 FPS. The `AMD FSR Presenter` and `AMD FSR Interpolation` threads were present, and focus was 2074920 in every sample. `verify-0609.png` is live Albion gameplay with the HUD up. Mapped driver `~/tfd-turnip-a740-sparse-2026-10-01/driver/lib64/libvulkan_freedreno.so`, SHA-256 `dac166671e9e1b8948eb098099f65a4d45a2837cd1c9a13ca46d9477b85bca97`. Prefix `d3d12.dll` `6b4af87a…` (229376 bytes) and `d3d12core.dll` `20984091…` (9306112 bytes) are byte-identical to stock Proton Experimental ARM64. The process env has no `TU_IR3_STATS`, `VKD3D_CONFIG`, or `VKD3D_PASS_TIMESTAMPS`. `TU_DEBUG_FILE=/tmp/tu_debug_file.txt` is set, but that file is empty and dates from Oct 1 10:06, before this work.
