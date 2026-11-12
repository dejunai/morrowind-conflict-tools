# Morrowind Conflict Tools

Python utilities for Morrowind plugin conflict resolution, load-order sorting, asset health, and MWSE Lua hardening. They are meant to live in the Morrowind game folder (the Steam install root), next to `Morrowind.ini` and `Data Files`.

This repository also includes the rule files and run records from one real install, used as a messy testbed load order.

## Requirements

- **Python 3** (the tools use the standard library only)
- **Windows** is the intended environment (Vortex staging paths, `MAX_PATH` checks, Win32 process checks)
- Optional: **LuaJIT** (or `luac`) so Lua patches can be syntax-checked before they are written. The `lupa` package is a fallback if neither is on `PATH`.
- Optional: **texconv** for DDS conversion, mipmaps, and compression in the asset fixer

On Windows you can also use the included `mwdialog_check.bat` and `vortex_tidy.bat` wrappers.

## Tools

| Script | What it does |
| --- | --- |
| `mwdialog_check.py` | Main plugin checker and fixer. Dialogue/INFO problems, missing masters, cell conflicts, cleaning, AutoMerge, Multipatch, load-order sort (mlox-style rules), and an `--asset-check`. `--full` runs the whole pipeline. |
| `mwdialog_assets.py` | Asset health used by `--asset-check` / `--fix`: unreadable or truncated DDS, missing mipmaps, uncompressed textures, unused loose files, files in the wrong folder. |
| `mwdialog_mastercheck.py` | Whether a compatibility patch was built for the master that is actually installed (reference resolution, size/date signals). |
| `mwdialog_longpaths.py` | Asset paths that are too long for Windows `MAX_PATH` or for Morrowind's fixed-length fields. Used by both the checker and tidy. |
| `vortex_tidy.py` | Tidies each mod folder in Vortex's Morrowind staging directory: loose docs/images, wrong-folder assets, then the asset check and the Lua check. Plan first, then `--apply`. |
| `mwdialog_luafix.py` | Static checker and in-place patcher for MWSE Lua (parser-based, not regex). Nil guards, absurd event priorities, log-spam shim, one-shot handlers, and related rules. Plan first, then `--apply`. |
| `mwdialog_lua.py` | Pure-Python Lua 5.1 / LuaJIT tokenizer and parser, used by `mwdialog_luafix.py`. |
| `mwdialog_planfile.py` | Shared plan-file helpers: atomic writes, blanking after a successful `--apply`, audit copies, strict comparison of the reviewed plan. |
| `chargen_ship_patch.py` | Builds `Chargen Ship - Original Model.esp` so the chargen ship keeps the original hull shape when a ship replacer is installed. |
| `stranded_doors_patch.py` | Builds `Stranded Doors - DRPV Patch.esp` to put two load doors left in the void back into Dwemer Ruins Plus. |

`diag/` holds small diagnostic scripts used while developing the tools. They hard-code a local game path.

## Plan mode and `--apply`

`vortex_tidy.py` and `mwdialog_luafix.py` share a strict plan-then-apply flow.

1. **Write a plan** (default; do not pass `--apply`):

   ```text
   python vortex_tidy.py
   python vortex_tidy.py --lua-only
   python mwdialog_luafix.py
   ```

   The plan is written to `vortex_tidy_plan.txt` or `mwdialog_luafix_plan.txt`.

2. **Review** the plan.

3. **Apply** only that reviewed plan:

   ```text
   python vortex_tidy.py --apply
   python mwdialog_luafix.py --apply
   ```

   `--apply` enacts the actions in the plan you reviewed (normalised: moves, Lua patches with a patch hash, asset repairs listed in the plan). It does **not** silently recompute a new plan and enact that instead.

4. **If the current check differs** from the reviewed plan, `--apply` **refuses**: nothing is changed, the new plan is written, the old plan is kept as `<plan>.prev.txt`, and the process **exits with code 2**. Run plan mode, review again, then `--apply`.

5. **A missing or blank plan** also refuses (exit code 2): run plan mode first.

6. **After a successful `--apply`**, the plan file is blanked (only a header comment is left) so it cannot be enacted a second time. If some actions were not applied (an error, a refused patch, Ctrl+C), the plan is rewritten with only what is still pending. `--undo` uses the journal, not the plan.

`--lua-only` on `vortex_tidy.py` replaces only the Lua section of its plan.

`mwdialog_check.py` uses a different confirmation style (`--fix` / `--dry-run` / `--yes`), not this plan-file flow.

## Config files in this repository

These live next to the scripts in the game folder, except as noted.

**Rules and lists you edit:**

- `mwdialog_check.rules.txt` — mlox-style load-order rules for `--sort` (these win over mlox's own files)
- mlox rules are not included; the tool reads `mlox\mlox_user.txt` and `mlox_base.txt` from your own mlox install if they exist, and `mwdialog_check.rules.txt` is the place for your own rules
- `mwdialog_check.conflict.blacklist.txt` — plugins left out of `--cell-conflicts` and loaded early so others win
- `vortex_tidy_blacklist.txt` — Vortex staging folders tidy should never touch
- `Data Files/MWSE/config/mwguard.json` — thresholds shared with `mwdialog_luafix.py` (copy this to `Data Files\MWSE\config\` in the game folder)

**Records the tools read and update** (this install's current state):

- `mwdialog_load_order.txt` — plugin load order
- `mwdialog_conflict_answers.json` — answers given to conflict questions
- `mwdialog_added_masters.json` — masters the checker added
- `mwdialog_cell_winners.txt`, `mwdialog_cell_fixes.txt` — cell-conflict winners and fixes
- `mwdialog_disabled.txt`, `mwdialog_redundant.txt` — plugins turned off, or marked redundant / keep-both
- `mwdialog_merged.txt` — AutoMerge inputs
- `mwdialog_generated_files.txt`, `mwdialog_ignored_normal_maps.txt`, `mwdialog_reduced_textures.txt`, `mwdialog_short_meshes.txt`, `mwdialog_master_sizes.json`

A default `mwdialog_mip_exempt.txt` can be added beside the scripts if you want to override the built-in mipmap exemptions; this install did not have one.

## Usage notes

- Put the scripts in the Morrowind game folder, or pass paths (`--staging` for tidy, folder arguments for luafix). `vortex_tidy.py` defaults to `G:\Vortex Mods\morrowind`.
- For tidy, Purge in Vortex first, `--apply`, then Deploy.
- Do not run `--full`, `--fix`, or `--apply` against live mods until you have reviewed the plan.
- Tests live in `tests/`. From a clone: `pytest`.

## Personal paths

Several configs and the `diag/` scripts contain absolute paths from the original install, including `G:\Program Files\Steam\steamapps\common\Morrowind` and `G:\Vortex Mods\morrowind`. They are install-specific, not secrets.

## License

No license is attached. Ask the author before reusing or redistributing this work.
