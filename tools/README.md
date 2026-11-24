# Bundled tools

The scripts look for these programs in this folder first, then beside the scripts, then the game folder, then on
PATH. Nothing here is hardcoded to a drive letter. Everything in this folder is redistributable and committed, each
with its license; the only exception is `Translation.txt` (below).

| Tool | Files | License | Source |
| --- | --- | --- | --- |
| texconv (DirectXTex) | `texconv.exe` | MIT (`TEXCONV_LICENSE.txt`) | https://github.com/microsoft/DirectXTex |
| FFmpeg 9.0.2, LGPL shared build | `ffmpeg.exe`, `ffprobe.exe`, `av*.dll`, `sw*.dll` | LGPL v3 (`FFMPEG_LICENSE.txt` + `GPLv3.txt`) | https://ffmpeg.org/, https://github.com/BtbN/FFmpeg-Builds |
| 7-Zip 26.02 | `7z/7z.exe`, `7z/7z.dll` | GNU LGPL + unRAR restriction (`7z/License.txt`) | https://www.7-zip.org/ |
| LuaJIT 2.1 | `luajit/` | MIT (`luajit/COPYRIGHT`) | https://luajit.org/ |

Keep each license file beside its binaries when redistributing.

Exact sources for the bundled builds:

- FFmpeg: source for this build is FFmpeg commit `7adfbe40dc` (n9.0.2-39-g7adfbe40dc, release/9.0 branch,
  https://git.ffmpeg.org/ffmpeg.git), built by BtbN release `autobuild-2026-10-31-12-59`:
  https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-10-31-12-59
  (asset `ffmpeg-n9.0.2-39-g7adfbe40dc-win64-lgpl-shared-9.0.zip`; build scripts at https://github.com/BtbN/FFmpeg-Builds).
- 7-Zip 26.02 source: https://www.7-zip.org/ (download page, 7-Zip 26.02 source code).

## texconv

DDS conversion, mipmaps and compression in the asset fixer.

## FFmpeg

`mwdialog_check.py --fix` repairs broken sounds with `ffmpeg`; the sound-length cache reads MP3 durations with
`ffprobe`. This is the shared (DLL) LGPL build, so both programs use the same DLLs and every file stays under
GitHub's 100 MB limit (`winget install BtbN.FFmpeg.LGPL.Shared.9.0`; copy `bin\` without `ffplay.exe`, plus
`LICENSE.txt` as `FFMPEG_LICENSE.txt`). LGPLv3 is a set of additional permissions on top of the GPLv3, so
`GPLv3.txt` ships beside it.

## 7-Zip (`7z/`)

Reads `.7z` and `.rar` Vortex download archives for the master-mismatch check. `7z.dll` is needed for `.rar` (the
standalone `7za.exe` cannot read RAR). The unRAR restriction means the RAR code may not be used to create RAR
archives.

## LuaJIT (`luajit/`)

`mwdialog_luafix.py` and `vortex_tidy.py` syntax-check Lua patches with LuaJIT before writing them, and the tests run
the Lua suite with it. If LuaJIT is missing the tools say so and do not patch (`--luajit PATH` to point at a
binary, or `--no-syntax-check` to rely on the parser alone).

## Tamriel Data's rename map (`Translation.txt`, not included)

`mwdialog_check.py --fix` uses it to give objects in older plugins their current Tamriel Data IDs instead of removing
them. It ships with Tamriel Data in its `Docs` folder: copy it here as `Translation.txt`, and again when Tamriel Data
updates. This is the only place `--fix` looks; without it `--fix` carries on as usual. The file is Tamriel Data's:
it is gitignored until redistribution is permitted.
