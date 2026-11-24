# Morrowind Conflict Tools

Python utilities for Morrowind plugin conflict resolution, load-order sorting, asset health, and MWSE Lua hardening. Install them in a subfolder of the Morrowind game folder, e.g. `Morrowind\conflict-tools\`. Run from there (or from the game folder) they find the game by its `Morrowind.ini` in the working folder or the one above, so `Data Files` need not be given; from anywhere else pass the `Data Files` folder. Rules, records, caches, journals, logs and reports are kept in `conflict-tools\generated\` (a copy left in the game folder by an older version is moved there the first time it is used), plans in `conflict-tools\plans\`; backups go to `conflict-tools\backups\`, which holds one backup per file (the newest), with every older one in `backups\legacy\`. Scripts run from outside the game folder keep backups in `<game folder>\mwdialog_backup\` the same way.

This repository also includes the rule files and run records from one real install, used as a messy testbed load order.

## Requirements

- **Python 3** (the tools use the standard library only)
- **Windows** is the intended environment (Vortex staging paths, `MAX_PATH` checks, Win32 process checks)
- Optional: **LuaJIT** (or `luac`) so Lua patches can be syntax-checked before they are written. Bundled in `tools/luajit/` (see `tools/README.md`); otherwise `luajit` on `PATH`, then the `lupa` package, is used.
- Optional: **7-Zip** (bundled in `tools/7z/`, else `7z` on PATH) to read `.7z`/`.rar` download archives in the master check
- Optional: **texconv** for DDS conversion, mipmaps, and compression in the asset fixer (bundled `tools\texconv.exe`, else the game folder or PATH)
- Optional: **ffmpeg** / **ffprobe** (bundled LGPL build in `tools\`, else PATH) for sound repair and MP3 lengths

On Windows you can also use the included `mwdialog_check.bat` and `vortex_tidy.bat` wrappers.

## Tools

| Script | What it does |
| --- | --- |
| `mwdialog_check.py` | Main plugin checker and fixer. Dialogue/INFO problems, missing masters, cell conflicts, cleaning, AutoMerge, Multipatch, load-order sort (mlox-style rules), and an `--asset-check`. `--full` runs the whole pipeline. |
| `mwdialog_assets.py` | Asset health used by `--asset-check` / `--fix`: unreadable or truncated DDS, missing mipmaps, uncompressed textures, unused loose files, files in the wrong folder. |
| `mwdialog_mastercheck.py` | Whether a compatibility patch was built for the master that is actually installed (reference resolution, size/date signals). |
| `mwdialog_longpaths.py` | Asset paths that are too long for Windows `MAX_PATH` or for Morrowind's fixed-length fields. Used by both the checker and tidy. |
| `mwdialog_footing.py` | `--fix` Cell Fixes: people whose footing a later mod took away (sunk land, deleted docks, a moved island) are moved to the nearest dry footing. |
| `mwdialog_anthology_override.py` | Detects incompatible old-site terrain, pathgrids and script coordinates when a mod moves land (including Anthology Solstheim and Tomb of the Snow Prince). Automatic large-scale relocation is disabled. |
| `mwdialog_cellorder.py` | Load-order rule: a plugin whose dialogue filters on a cell another plugin names loads after it. |
| `vortex_tidy.py` | Tidies each mod folder in Vortex's Morrowind staging directory (from Vortex's settings, or `--staging`): loose docs/images, wrong-folder assets, then the asset check and the Lua check. Plan first, then `--apply`. |
| `mwdialog_luafix.py` | Static checker and in-place patcher for MWSE Lua (parser-based, not regex). Nil guards, absurd event priorities, log-spam shim, one-shot handlers, and related rules. Plan first, then `--apply`. |
| `mwdialog_lua.py` | Pure-Python Lua 5.1 / LuaJIT tokenizer and parser, used by `mwdialog_luafix.py`. |
| `mwdialog_planfile.py` | Shared plan-file helpers: atomic writes, blanking after a successful `--apply`, audit copies, strict comparison of the reviewed plan. |
| `mwdialog_tes3.py`, `mwdialog_bsa.py`, `mwdialog_media.py`, `mwdialog_backup.py`, `mwdialog_loadorder.py`, `mwdialog_records.py`, `mwdialog_state.py`, `mwdialog_cellmods.py`, `mwdialog_datatree.py`, `mwdialog_console.py`, `mwdialog_masters.py`, `mwdialog_patchfile.py`, `mwdialog_redundant.py`, `mwdialog_generated.py`, `mwdialog_restore.py` | Parts of `mwdialog_check.py` split out into their own modules (plugin format, BSAs, asset formats, backups, load order, records, state files, what `--cell-conflicts` writes, the Data Files tree, console, masters, the fix patch, redundant plugins, generated files, restoring). `mwdialog_check.py` imports every name back. See `MWDIALOG_REFACTOR.md`. |
| `mwdialog_text.py` | Shared helper that wraps human-readable console, report, `--help`, and fix-log text at 115 characters, with a hanging indent and bullets for lists. |
| `_backup\retired-one-off-20261114\chargen_ship_patch.py` | Retired. Built `Chargen Ship - Original Model.esp`. Not part of the checker. |
| `_backup\retired-one-off-20261114\stranded_doors_patch.py` | Retired. Built `Stranded Doors - DRPV Patch.esp`. Not part of the checker. |

`diag/` holds small diagnostic scripts used while developing the tools. They hard-code a local game path.

## Plan mode and `--apply`

`vortex_tidy.py` and `mwdialog_luafix.py` share a strict plan-then-apply flow.

1. **Write a plan** (default; do not pass `--apply`):

   ```text
   python vortex_tidy.py
   python vortex_tidy.py --lua-only
   python mwdialog_luafix.py
   ```

   The plan is written to `plans\vortex_tidy_plan.txt` or `plans\mwdialog_luafix_plan.txt` beside the scripts.

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

Textures larger than 2048 and splash screens wider than 2048 are reduced to 2048 by default. `--no-reduce-textures` and `--no-reduce-splash` (on `vortex_tidy.py`, and with `mwdialog_check.py --asset-check`) keep them full size; give the same flags for the plan and `--apply`, or `--apply` refuses because the plan changed.

`mwdialog_check.py` uses a different confirmation style (`--fix` / `--dry-run` / `--yes`), not this plan-file flow.

## Incompatible plugins

`--full` and `--cell-conflicts` identify evidenced moved-land incompatibilities and require a choice before building.
Run `python mwdialog_check.py "Data Files" --cell-conflicts` in a console, then choose which side to turn off.
The choice also sets aside active plugins with declared master dependencies or detected exclusive object/script
uses; shared objects do not force removal. Review the displayed group and any warnings about MWSE Lua references.
Generated patches are set aside for rebuilding; active merges must be undone first (`--full` does this).
Remembered choices are checked again if the dependent group changes. `--reenable` restores plugins only when
their required masters and selected group root are available.

The detector is not exhaustive: old-site objects without terrain, pathgrid or matching literal script evidence
are warnings for review, not mandatory choices, and variable-driven script or Lua dependencies may be missed.
`--fix`, `--multipatch` and merge commands also refuse detected incompatibilities; builds recheck after sorting.
Unreadable plugins stop the compatibility check, and a failed build does not launch a requested `--play`.
An unattended run stops instead of guessing. Large-scale relocation and script recompilation are not performed.

## Config files in this repository

These live in the game folder, except as noted.

**Rules and lists you edit:**

- `mwdialog_check.rules.txt` — your mlox-style load-order rules for `--sort` (these win over mlox's own files). None ship with the tools: `--sort` makes the file with only its instruction header when it is missing, then keeps its `[Context]` section and the rules `--cell-conflicts` adds there. The ESM fixes patch's place (early) and the end of the order (XE Sky Variations when installed, then the auto-merge and our patches) are built into the sorter; a `[NearStart]` / `[NearEnd]` block there also orders its own plugins (`[NearEnd]`: first listed loads last), so they need no extra `[Order]` entry
- mlox rules are not included; the tool reads `mlox\mlox_user.txt` and `mlox_base.txt` from your own mlox install if they exist, and `mwdialog_check.rules.txt` is the place for your own rules
- `mwdialog_check.conflict.blacklist.txt` — plugins left out of `--cell-conflicts` and loaded early so others win
- `vortex_tidy_blacklist.txt` — Vortex staging folders tidy should never touch
- `lua tools/MWSE/config/mwguard.json` — thresholds shared with `mwdialog_luafix.py` (deployed to `Data Files\MWSE\config\` like the rest of `lua tools`)

**Records the tools read and update** (this install's current state; file paths in them are stored as `staging:` / `downloads:` / `game:` plus a relative path):

- `mwdialog_load_order.txt` — plugin load order
- `mwdialog_conflict_answers.json` — answers given to conflict questions
- `mwdialog_added_masters.json` — masters the checker added
- `mwdialog_cell_winners.txt`, `mwdialog_cell_fixes.txt` — cell-conflict winners and fixes
- `mwdialog_disabled.txt`, `mwdialog_redundant.txt` — plugins turned off, or marked redundant / keep-both
- `mwdialog_merged.txt` — AutoMerge inputs
- `mwdialog_generated_files.txt`, `mwdialog_ignored_normal_maps.txt`, `mwdialog_reduced_textures.txt`, `mwdialog_short_meshes.txt`, `mwdialog_master_sizes.json`

`dummy assets\` holds the stand-in model and animation (`mwdialog_dummy*.nif`, `.kf`) used for missing or broken ones.

A default `mwdialog_mip_exempt.txt` can be added beside the scripts if you want to override the built-in mipmap exemptions; this install did not have one.

## Vortex paths

Staging and download folders are read from Vortex's own settings (`%APPDATA%\Vortex\state.v2`, `state`, or a settings backup). `{game}` and `{USERDATA}` placeholders are expanded. `--staging` / `--vortex-dir` and `--vortex-downloads` / `--downloads` override those settings.

If Vortex's data cannot be read and no override is given, the tool exits with a message that names every folder it tried and the flag to pass. There is no hardcoded fallback path. `--no-vortex` skips the staging folder; `--no-archive-lookup` (or `--no-master-guard`) skips the download folder.

The "deleted by vortex_tidy" folder is derived from the resolved staging folder (`<staging name> - deleted by vortex_tidy`, beside it).

## MWSE mods

`lua tools/MWSE/mods/` holds the mw* Lua suite these tools work with (`mwsuite`); `--play` brings `Data Files` up to date from it: a missing file is copied in, and a deployed file older than its `lua tools` copy is replaced (the old one is kept under `backups\lua deploy\`). A deployed file newer than `lua tools`' copy is left alone and listed, since edits belong in `lua tools`; `MWSE\config\` (the player's settings) only ever gets missing files. MWSE's own core files are not shipped: the fixes to them are Known Bugs patches (`KB3`, `KB4`) that `vortex_tidy.py` and `mwdialog_luafix.py` write into the player's copy, marked `localpatch`. Among them are `mwguard` (a passive profiler: it times per-frame handlers and logs extreme priorities to `MWSE\logs\mwguard.log`, without throttling or changing other mods), `mwsoundguard` and `mwhangwatch`.

## Sound scripts (`--soundfix`)

Many scripts start a sound only while `GetSoundPlaying` says it isn't playing. Where the engine answers 0 for object sounds, they restart it every frame. `--soundfix` (also run by `--fix`; `--no-soundfix` skips it) rewrites them to keep their own state, a flag for a loop and a one-frame-early timer for a one-shot, and recompiles them with `tools\MWRecompile\` into `mwdialog_check - MWSoundFix.esp`, which the sorter loads just before the Multipatch. A script is changed only when its unchanged source recompiles to exactly the bytecode it ships with; `generated\mwdialog_soundfix_report.txt` lists every script and why any was left alone (those stay under `mwsoundguard`). The `mwsoundfix` MWSE mod re-arms the patched scripts on every load and when their objects come back. `--dry-run` or `--soundfix-report` only report; `--soundfix-undo` takes the patch out; `--soundfix-loop-mode restart` is for an install without MWSE. New games are assumed: old saves aren't migrated.

## Keeping a game in progress (`--preserve-saves`)

Missing masters are an expected Morrowind warning, so by default the tools may still turn plugins off or rebuild the auto-merge. `--preserve-saves` holds back what damages a game in progress instead: `--soundfix` (it adds script variables), naming nameless topics, and any rebuild of Cell Fixes or the Performers patch that would bring back an object they delete while the plugins they were built on are all still active (recorded in `mwdialog_patch_inputs.json`). `--preserve-saves=strict` also keeps the active plugins (doubled, redundant and conflict turn-offs are reported only; `--reenable` and `--unmerge` refuse), the auto-merge and those two patches exactly as they are, skips the duplicate-object and misplaced-copy clean-ups and the persistence flips, and reports incompatible plugins instead of stopping; `--full` then has no reset, unmerge or redundant step. Everything held back is reported.

## Output wrapping

Human-readable feedback (console, `mwdialog_report.txt` when stdout is redirected, dated lines in `mwdialog_fixes.log`, and `argparse --help`) is wrapped at 115 characters. A continuation line is indented two spaces beyond the line's own indent, or aligns under a `- ` bullet or under the message after a log timestamp. A path or other single token longer than 115 characters is left on its own line.

Plan files (`vortex_tidy_plan.txt`, `mwdialog_luafix_plan.txt`) are written unwrapped: `--apply` compares action lines (moves, patch hashes, repairs) exactly, so those must stay one line. The console preview of a plan is wrapped. Rules, records, JSON, CSV/TSV, and Lua patch content are also left as-is.

## Usage notes

- Put the scripts in `Morrowind\conflict-tools\` (any subfolder of the game folder works), or pass paths (`Data Files` for the checker, `--staging` for tidy, folder arguments for luafix).
- For tidy, Purge in Vortex first, `--apply`, then Deploy.
- Do not run `--full`, `--fix`, or `--apply` against live mods until you have reviewed the plan.
- Tests live in `tests/`. From a clone, or from the install folder with `tests\` copied beside the scripts: `pytest`. They only use temp folders.

## License

MIT; see [LICENSE](LICENSE). The bundled programs in `tools/` keep their own licenses; see [tools/README.md](tools/README.md).
