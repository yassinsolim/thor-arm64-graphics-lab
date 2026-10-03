# vkd3d-proton ARM64X instrumentation build, Oct 1, 2026

## Inputs and verification

- vkd3d-proton commit: `7f0c30ad3c8f28dfe47c34bb897b972e2d1ca724`
- Git tree: `ea2eed9d8503e1d32b3ed1bba257168fd5351a8d`
- GitHub reports the commit as unsigned.
- Source archive SHA-256: `063803dd8c0771c2fec27d0fc358743c38570dd2babc9168a54d9fb1b673ef74`
- Instrumentation patch: `diagnostics/vkd3d-proton-7f0c30ad-wbi-va-log.patch`
- Patch SHA-256: `a65f7459cb4f2bdeecd10a2cadff1c9fcf114054c57026df9314ff63f6e440ea`
- SPIRV-Headers submodule: `f88a2d766840fc825af1fc065977953ba1fa4a91`
- Vulkan-Headers submodule: `ee2ec5fd83dafce291024683b50dc89219333076`
- dxil-spirv submodule: `c5e5522a121c5908a1c4fd472d68fa70c8fde9f4`

The compiler was the official LLVM-MinGW 20260922 UCRT Ubuntu 22.04 AArch64 release from
`mstorsjo/llvm-mingw`:

```text
llvm-mingw-20260922-ucrt-ubuntu-22.04-aarch64.tar.xz
SHA-256 07d21263c56bfe9a713db6fdb3f7434bf4c121a005e40397d3b4c0170fb06769
clang 23.1.2, LLVM commit 85ac560262434c9ccfc0c183ec22d4138ed647fb
```

The hash matched the digest published for the GitHub release asset. The build ran without
root in an ARM64 Ubuntu 22.04 container pinned to:

```text
ubuntu@sha256:b8b6ee6aa931ecd9d0d952abc34dc0e5f7c6a30c6bb71b079fe399fde0329c02
local image sha256:1c9b39579fce9453b14e55a8988352991c4502d0402dd2565c49dc8c0b5714a8
```

The image contained Meson 1.9.0, Ninja, build-essential, and glslang-tools. No host or Thor
package was installed or replaced.

## Build

A plain AArch64 build completed but was not usable for the x64 game. Proton Experimental
uses an ARM64EC/ARM64X D3D12 path under FEX. Loading the plain AArch64 DLL produced
`c000007b`.

The accepted build used the repository's `build-arm64x.txt` cross file, including:

```text
arm64ec-w64-mingw32-gcc
arm64ec-w64-mingw32-g++
-march=armv8.2-a -mtune=cortex-x3 -marm64x
```

Equivalent build commands inside the pinned container were:

```sh
meson setup build-arm64x \
  --cross-file build-arm64x.txt \
  --native-file build-native-container.txt \
  --buildtype release \
  -Denable_tests=true -Denable_extras=false -Denable_trace=false
ninja -C build-arm64x
```

`llvm-objdump` identifies the resulting core as `coff-arm64x`.

An x64 test executable was also built from the same source with
`x86_64-w64-mingw32-clang` and the same test options. It was used to exercise the
x64/FEX to ARM64X ABI boundary against the instrumented ARM64X DLLs.

## Artifact hashes

```text
67ffc528ab187354478d1a6a59d491ec0cee3c43964d78b6ade2ac80e3c6db00  d3d12.dll
d391c37dab09cc55754729025ea3caa4b85b7bb530c3b3a8b732b18bad73b5f0  d3d12core.dll
684a921eb3f5ae0f33aac5b437ea081c22b145765c6406d48965d7f9e85cc94a  d3d12-arm64x.exe
0709a790b1fdbd958e056982cf90db115a4017afaea258cd0e941e8a6f3f3e68  d3d12-x64.exe
```

Thor copies and logs are under:

```text
~/tfd-turnip-a740-sparse-2026-10-01/vkd3d-instrumented/
```

## Isolation

`WINEDLLPATH` alone did not override Proton's own DLL search path. Direct bind mounts made
normal Proton prefix setup try to replace the mounted files and fail with `EBUSY`.

The successful game run used:

1. A symlinked copy of Proton Experimental in `proton-isolated-tree`, with only
   `d3d12.dll` and `d3d12core.dll` replaced by the instrumented ARM64X files.
2. A full copied game prefix in `game-compatdata`.
3. `game-isolated-proton.sh`, SHA-256
   `8e87b40c593d270b225ac12287da42f30ba69cdb17a7a2f419a4b65668f8bb8a`,
   which substituted the isolated Proton executable while retaining
   `/usr/libexec/armada/armada-game-launch`.
4. Per-process `VK_ICD_FILENAMES` and `VK_DRIVER_FILES` pointing to the CTS-tested Turnip
   build.

The original Proton tree, original game prefix, game files, and anti-cheat files were not
modified.

## Focused tests

ARM64X tests against the isolated prefix:

```text
test_write_buffer_immediate:       59 executed, 0 failures
test_gpu_virtual_address:          22 executed, 0 failures
test_create_committed_resource:    79 executed, 0 failures, 1 todo
```

The intentionally invalid-address test produced the expected diagnostic for `0x600`
without changing its expected result.

The x64 executable then ran through FEX against the same ARM64X DLLs:

```text
test_write_buffer_immediate:       59 executed, 0 failures
test_gpu_virtual_address:          22 executed, 0 failures
test_check_feature_support:       376 executed, 0 failures
```

`test_check_feature_support` returned `MaxSupportedFeatureLevel = 0xc000`, which is
`D3D_FEATURE_LEVEL_12_0`. Shader model 6.6 is a separate capability and was enabled in
the game log.

The x64 `WriteBufferImmediate` test proves that valid 64-bit GPU virtual addresses survive
the normal x64/FEX to ARM64X call boundary in this exact isolated runtime. It does not
exclude a title-specific interop layer, but it rules out a general ARM64EC thunk
truncation.

## Caller-stack extension

`diagnostics/vkd3d-proton-7f0c30ad-wbi-caller.patch` applies after the warn-only
patch. SHA-256
`dbdf766ddeaa0e3d4f348c01b51541c7276cc712e45663e02ee2525b6750800a`.

The rebuilt core is SHA-256
`4f9e036100a8820c5f2a3980d7a81407c8b3f092e942ab1f1d78049b6b54c9b0`
and is `coff-arm64x`. The x64 `test_write_buffer_immediate` result remained 59 executed
and 0 failures. A small x64 smoke call to destination `0x600` still made `Close` return
`0x80070057`, and `RtlCaptureStackBackTrace` resolved a frame in the x64 smoke executable.
The native return address was only the ARM64EC thunk inside `d3d12core.dll`. The FEX
CPU-area PC was zero for that smoke call, so the unwind stack is the caller record used
for the game.
