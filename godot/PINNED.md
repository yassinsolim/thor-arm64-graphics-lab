# Pinned artifacts, verified Oct 2, 2026

Hashes below were computed on this machine and matched the upstream checksum files. Nothing here was copied onto the Thor.

## Godot 4.5 stable

Tag `4.5-stable` on `godotengine/godot` and `godotengine/godot-builds`, published 2025-09-15.

Source commit `876b290332ec6f2e6d173d08162a02aa7e6ca46d`. The macOS editor prints `4.5.stable.official.876b29033`, the same commit.

License: MIT. `LICENSE.txt` inside the source tarball (`godot-4.5-stable/LICENSE.txt`) SHA-256 `b0435e3b3e4e55238f05f4b306f30524a1b2e20147810d436eaa554fa6855c80`. Copyright 2014-present Godot Engine contributors, and 2007-2014 Juan Linietsky, Ariel Manzur.

| File | SHA-256 | SHA-512 |
| --- | --- | --- |
| `godot-4.5-stable.tar.xz` | `2cdb383d68bfe646c832064b9063310745e8db03a2e4b59f5946ee934b95c67d` | `046428d8c336747d1853e4a2cdab82e3d6605d25c64dc85efdaa600cbca7436e59e32b401e89b92bcef42059afb2b9156bbce85c34a658cf76957830bd829d50` |
| `Godot_v4.5-stable_linux.arm64.zip` | `f9f167c0a19cc84385b508c12bd0e7a290dd21a639bce2ed6dcf4647af796589` | `36a9f21358f3521832d83e692f0f5364e0486f7ddeb1008a99973774a3fc26953ebf80965e9140ae6a2595b6a568b8e0d5f8efb7cb37609b01ea8f8e16b8b3c4` |
| `Godot_v4.5-stable_macos.universal.zip` | `abb7cabe99fead0bd63ce03bd8c611734b2941f9b90051e8e3b5c6691527954d` | `59d195d1876210fa0f8c36bc10b147339fc8e076c684b74111533992f1a1dcdc0f760461f4cadad627e5b11e74468b54b9355fc6ea0c507c52533dfa7aa0c617` |

The source SHA-256 matches `godot-4.5-stable.tar.xz.sha256` from the same release. The three SHA-512 lines match `SHA512-SUMS.txt` from that release (`shasum -a 512 -c`).

The arm64 zip contains one file, `Godot_v4.5-stable_linux.arm64`. `file` reports `ELF 64-bit LSB executable, ARM aarch64`, dynamically linked, interpreter `/lib/ld-linux-aarch64.so.1`, for GNU/Linux 5.15.0. That is the editor to run on Armada. There is an official binary. A from-source build is only the fallback in the README if `ldd` reports missing libraries.

Do not use the .NET/mono editor. This demo is GDScript.

## Third-person demo

Repository `godotengine/tps-demo`, tag `4.5-90f2e38`.

Annotated as a lightweight tag pointing at commit `90f2e38d7b5cf9e6fd0b788d0da1df4b84d49269` (2025-10-11, "Use static typing in all scripts (#208)"). A local clone's `git rev-parse HEAD` returned that full hash.

`LICENSE.md` SHA-256 `f7bf763d4c378425b99a5abfe42f49bb03fc530e9721cc5943072becf348caff`.

- Code: MIT, copyright 2018-2021 Juan Linietsky and Godot Engine contributors.
- Scene assets: CC-BY 3.0, copyright 2018 Juan Linietsky and Fernando Miguel Calabró.
- Music: CC-BY 3.0, copyright 2018 Christian Fernando Perucchi.
- Some Substance Painter source materials were provided by GameTextures.com. The license file does not grant a separate license for those beyond the CC-BY scene. Do not republish the assets. The benchmark patch is code only.

The patch is `patches/tps-demo-benchmark.patch`. It does not change graphics quality. It forces the demo's own defaults, then windowed 1280x720, vsync off, and an uncapped frame rate, only when `--benchmark` is passed after `--`.
