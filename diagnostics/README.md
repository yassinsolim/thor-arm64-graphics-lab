# Diagnostics

These patches only add logs or a test. They are not proposed changes to vkd3d-proton or Mesa.

The alignment test is the one that failed its own premise: on this Turnip build the committed and placed buffer addresses were already 64 KiB aligned. See `docs/vkd3d-turnip-alignment.md`.
