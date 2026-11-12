# Tools next to the scripts

These utilities look for optional binaries under this folder, then on PATH. Nothing here is hardcoded to a drive letter.

## LuaJIT (`tools/luajit/`)

`mwdialog_luafix.py` and `vortex_tidy.py` syntax-check Lua patches with LuaJIT before writing them.

Copy a LuaJIT 2.1 Windows build into `tools/luajit/` (this folder). You need at least:

- `luajit.exe`
- `lua51.dll`
- the `jit/` folder (the `.lua` modules that ship with LuaJIT)
- `COPYRIGHT` (LuaJIT's MIT license; keep it next to the binary)

A ready-made copy can be taken from an existing MWSE or MWManager `tools/luajit` folder (copy, don't move). Official sources: https://luajit.org/

If LuaJIT is not found, the tools say so clearly and do not patch (`--luajit PATH` to point at a binary, or `--no-syntax-check` to rely on the parser alone). This directory is gitignored; do not commit the binaries.

## 7-Zip (`tools/7z/`)

Used to read `.7z` and `.rar` Vortex download archives for the master-mismatch check. Looked up in this order:

1. `7z` on PATH
2. `tools/7z/7z.exe` (or `tools/7z.exe`)

If a `.7z`/`.rar` archive needs to be opened and 7-Zip is not found, the tool exits with a message telling you to install 7-Zip and add it to PATH, or to place `7z.exe` here.
