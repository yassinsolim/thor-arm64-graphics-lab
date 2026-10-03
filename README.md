# ARM64 graphics lab

Notes, measurements, and patches from getting Windows and native games onto an AYN Thor running Armada Linux. The GPU is an Adreno 740. The native driver is Turnip. Windows titles run through FEX and Proton.

The useful public result is a Turnip change that exposes single-sample sparse 2D images on A740. That is what let The First Descendant create a D3D12 device and reach gameplay. The rest of this repo is the measurement around that change: what was GPU-bound, what was a translation or runtime problem, and which ideas did not survive a test.

## What is here

| Path | What it is |
| --- | --- |
| [docs/first-descendant.md](docs/first-descendant.md) | Launch chain, the sparse-image gate, settings, and frame-time results |
| [docs/mesa-a740-sparse-images.md](docs/mesa-a740-sparse-images.md) | RFC notes and the VK-GL-CTS result |
| [mesa/](mesa/) | The patch, against Mesa 26.2.3 and against main |
| [docs/godot-arm64-baseline.md](docs/godot-arm64-baseline.md) | Native Godot 4.5 Forward+ vs Mobile on the same GPU |
| [godot/](godot/) | Deterministic benchmark harness and raw JSON |
| [tools/msm_perfcntr_sample.py](tools/msm_perfcntr_sample.py) | Root-gated Adreno counter sampler |
| [analysis/fsr3_1_4_pacer_sim.py](analysis/fsr3_1_4_pacer_sim.py) | Model of the public FSR 3.1.4 frame-generation pacer |
| [docs/vkd3d-turnip-alignment.md](docs/vkd3d-turnip-alignment.md) | A 64 KiB buffer-address hypothesis that the device run disproved |
| [diagnostics/](diagnostics/) | Warn-only vkd3d logs used to test those hypotheses. Not an upstream proposal |

## Device

- AYN Thor, Snapdragon 8 Gen 2, Adreno 740
- Armada Linux, aarch64
- Turnip from Mesa 26.2.3, plus an isolated build of current main for the RFC
- FEX and Proton for x86_64 Windows titles

## First Descendant

Stock Turnip reports sparse 2D residency as unsupported. The game treats that as missing D3D12 feature level 12_1 and stops. An isolated driver with single-sample `sparseResidencyImage2D` enabled gets past that check. Multisample sparse residency stays off, because A740 does not have the A750 UBWC mutable-format bit.

A focused VK-GL-CTS 1.4.6.1 run of the sparse 2D caselist was 3073 passed, 0 failed, 5066 not supported, on both Mesa 26.2.3 and the main port. That is not full CTS and not a conformance claim. Adreno X1-85 is not enabled.

Playable settings on this device, after that driver, were 1280x720, Low, FSR Ultra Performance, FSR frame generation on, and a 60 FPS cap. Lobby frame times sat around 44 to 47 displayed FPS. Albion sat around 21 to 30. The GPU was the limiter. Frame generation did not remove that cost.

## Godot control

Godot 4.5 runs natively, so it separates driver and scene cost from FEX and vkd3d. At 1280x720 the Mobile renderer was much faster than Forward+. With lightmap GI and shadows off, median frame time was 9.38 ms and the GPU stayed about 93 percent busy at 680 MHz. The remaining cost was material shading and fill on the Structure meshes, not a Turnip pass bug.

## Not proposed upstream

- The vkd3d 64 KiB committed-buffer alignment idea. On this Turnip build both the committed address and the placed address were already 64 KiB aligned.
- A vkd3d or Mesa change for the FSR 3 present bubble. The pacer model matches the public FSR 3.1.4 source, and there was no correct general patch.
- Any change to the game, its anti-cheat, or its shaders.

## Mesa merge request

The RFC text is in [mesa/MERGE_REQUEST.md](mesa/MERGE_REQUEST.md). Opening it still needs a Freedesktop GitLab fork of [mesa/mesa](https://gitlab.freedesktop.org/mesa/mesa). This repository is the public record until that request exists.

## License

Original notes and tools in this repository are MIT. See [LICENSE](LICENSE). The Mesa patches are against Mesa's own license. The Godot harness patch is against the MIT third-person demo.
