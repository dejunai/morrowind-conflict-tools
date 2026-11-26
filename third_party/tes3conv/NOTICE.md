# tes3conv (vendored program)

`tes3conv.exe` here is the unmodified official Windows build of **tes3conv v0.4.1** by Greatness7. It converts a
Morrowind plugin (.esp/.esm) to JSON and back. The conflict tools do not need it to run: it is used by the developer
tool `tes3diff.py` (repository only) and the golden tests, and is carried with the tools for future use.

| | |
|---|---|
| Program | tes3conv v0.4.1 (Windows x64), `tes3conv.exe`, 2,876,928 bytes |
| Source | https://github.com/Greatness7/tes3conv |
| Release | https://github.com/Greatness7/tes3conv/releases/tag/v0.4.1 (asset `windows-latest.zip`) |
| Tag / commit | `v0.4.1` = `6dc51f7950d3581f62cf568ccb714801c24a10f0` |
| SHA-256 of `tes3conv.exe` | `3c259868c9deca42a658ff6c69cbc8578f8eeee99ebab5342bdb73beef650b40` |
| SHA-256 of `windows-latest.zip` | `2783e835efdd4e28e9d31d63674c9c036f1332ef948707d581af33e7618a87a9` (GitHub's digest for the asset) |
| Built from | the `tes3` library, https://github.com/Greatness7/tes3 at `51fae82b79838d76a39d0d1d0d472d7f48e8577f` (the `rev` in tes3conv's `Cargo.toml`) |

The file is checked against that SHA-256 by `tests/test_tes3conv_vendored.py` and by `tes3diff.py --check`. Do not
replace it with another build without changing the pin, this note and the test together.

## Licenses (they travel with the program)

| File | What | Where it comes from |
|---|---|---|
| `LICENSE` | tes3conv: MIT, Copyright (c) 2025 Greatness7 | `LICENSE` of the tes3conv repository at commit `0d66873219607726c3bc79516a96d170ec7705d2`. The `v0.4.1` tag itself has no license file; this commit, made nine minutes after the release, only adds it (its parent is the tag). |
| `LICENSE-tes3` | tes3 library: MIT, Copyright (c) 2022 Greatness7 | `LICENSE` of the tes3 repository at `51fae82b79838d76a39d0d1d0d472d7f48e8577f`. The crate declares `license = "MIT OR Apache-2.0"` in its `Cargo.toml`, but the repository holds only this MIT text (no Apache-2.0 file at that commit or on `main`), so the MIT option is the one shipped. |
| `LICENSE-mimalloc_rust` | mimalloc_rust (the allocator tes3conv links in): MIT, Copyright 2019 Octavian Oncescu | `LICENSE.txt` of https://github.com/purpleprotocol/mimalloc_rust at `eff21096d5ee5337ec89e2b7174f1bbb11026c70` (the `rev` in tes3conv's `Cargo.toml`). |

tes3conv is also built with other Rust crates (`serde_json`, `clap` and their dependencies, listed in the
`Cargo.lock` of the tag), which are under MIT and/or Apache-2.0 terms; their texts are not repeated here.

tes3conv may lag the tes3 library: newer record types or fields may not round-trip.