# Bundled tools

The scripts look for these programs in this folder first, then beside the scripts, then the game folder, then on
PATH. Nothing here is hardcoded to a drive letter. Everything in this folder is redistributable and committed, each
with its license; the only exception is `Translation.txt` (below).

| Tool | Files | License | Source |
| --- | --- | --- | --- |
| texconv (DirectXTex) | `texconv.exe` | MIT (`TEXCONV_LICENSE.txt`) | https://github.com/microsoft/DirectXTex |
| FFmpeg 9.0.2 with LAME 3.100, our audio-only build | `ffmpeg.exe`, `ffprobe.exe` | LGPL v2.1 or later (`LGPL-2.1.txt`; LAME: `source/LAME_LICENSE.txt`) | `source/` (complete, see below) |
| 7-Zip 26.02 | `7z/7z.exe`, `7z/7z.dll` | GNU LGPL v2.1 + unRAR restriction (`7z/License.txt`, `7z/LGPL-2.1.txt`) | `7z/7z2602-src.7z` |
| LuaJIT 2.1 | `luajit/` | MIT (`luajit/COPYRIGHT`) | https://luajit.org/ |

Keep each license file beside its binaries when redistributing.

Exact sources for the bundled builds (shipped here, so this folder is complete on its own):

- FFmpeg: `source/` holds the complete corresponding source of `ffmpeg.exe` and `ffprobe.exe`: the FFmpeg 9.0.2
  release (`ffmpeg-9.0.2.tar.xz`, sha256 `8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e`, from
  https://ffmpeg.org/releases/, signature `.asc` beside it), LAME 3.100 (`lame-3.100.tar.gz`, sha256
  `ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e`, from https://lame.sourceforge.io/), and
  `build-ffmpeg.sh`, the script that built them (MSYS2 MINGW64, gcc). No other library is linked in: the programs
  use only Windows system DLLs.
- 7-Zip 26.02: `7z/7z2602-src.7z` is the upstream source archive (sha256
  `c7502dd4557481f52ccf1b3e680329f1fdd207e79a25544afeb3106325474944`, from
  https://github.com/ip7z/7zip/releases/tag/26.02).

## texconv

DDS conversion, mipmaps and compression in the asset fixer.

## FFmpeg

`mwdialog_check.py --fix` repairs broken sounds with `ffmpeg`; the sound-length cache reads MP3 durations with
`ffprobe`. This is our own static, audio-only build (WAV/MP3/Ogg/FLAC/AIFF in; PCM WAV or LAME MP3 out;
resampling), with no external libraries besides LAME, so its whole source fits in `source/`. To rebuild it, run
`source/build-ffmpeg.sh` in an MSYS2 MINGW64 shell and copy `build/ffmpeg.exe` and `build/ffprobe.exe` here.

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
