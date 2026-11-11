# mwdialog_check / mwdialog_assets / vortex_tidy: fixes from the code review

Drop-in replacements for the three scripts. The command-line options, file names and on-disk formats are unchanged:

- rules.txt, the asset cache, `vortex_tidy_journal.jsonl` and `mwdialog_unused_assets.txt`
- the `.bak` and `.bakN` backups under `mwdialog_backup\`
- `*.mwdialog-YYYYMMDD-HHMMSS.bak`, `*.mwdialog-play.bak`, and the `Off\<feature>\<plugin>\` layout

The `--help` output of both CLIs is byte-identical to the originals.

Per-file diffs are in `mwdialog_check.diff`, `mwdialog_assets.diff` and `vortex_tidy.diff` (against the originals you sent). The tests are in `tests/` (`pytest tests`; `MW_SRC=<folder> pytest tests` runs them against another copy, such as the originals).

## Shared helpers (new, in mwdialog_check.py)

- **`safe_write_bytes(path, data, validate=None, keep_times=None)`** writes in this order:
  1. It writes `<path>.mwdtmp`, fsyncs it, reads it back and compares, then runs the optional validator. If any of that fails, the original is untouched.
  2. It copies the bytes over the existing file in place (`r+b`, write, truncate, fsync). This means **Vortex hard links stay links**. A brand-new file is `os.replace`d into place instead.
  3. If step 2 fails, the checked copy is left behind as `.mwdtmp`.
  4. It restores the dates when asked to, because load order is date-based.
- **`write_plugin_bytes`** = `safe_write_bytes` + `validate_plugin_bytes`. It refuses to write anything that isn't a whole TES3 file: a TES3 header first, and every record and subrecord in bounds.
- **`"mw_bytes"` codec error handler (`MW_ERRORS`)** makes cp1252, cp1251 and cp1250 text lossless.
  - Decoding: a byte the code page leaves undefined (0x81, 0x8D, 0x8F, 0x90, 0x9D in cp1252) becomes `chr(byte)`.
  - Encoding: it turns back into the same byte. A `surrogateescape` surrogate is accepted too.
  - It doesn't use lone surrogates, so printing and utf-8 logs can't crash.
- **`set_hedr_count`**, **`is_our_patch`**, **`read_plugin_bytes`/`forget_cached`** (read cache), **`set_link`** (PNAM/NNAM), **`keep_new_original`** (asset originals).

## Findings

| # | Status | What changed |
|---|---|---|
| **C1** clean removes deliberate reverts | **fixed** | `run_clean` orders masters by load order (FRMR numbering still uses MAST order). A record, a placed reference, AMBI, WHGT and the junk-cell test are now compared only with the version this plugin overrides: the **last** master that has it. Before, it matched against *any* master. A copy of an earlier master's value now stays. |
| **I1** non-atomic in-place writes | **fixed** (plugins, ini, rules-update, assets) | Every plugin write goes through `write_plugin_bytes`: `apply_plan`, `apply_item_fixes`, `write_patch`, `write_inplace`, the performers and cell-winner patches, `--restore`, `--restore-all`, `rename_ascii`, and the `--update-rules` file. The same goes for the Morrowind.ini rewrite and `replace_asset_in_place` (`safe_write_bytes`). Restores read back and compare the result, and keep the `.bak` on a mismatch. **Partial:** the rules-file writers that use `open(..., "w")` text mode (`--sort` and other rules edits) are unchanged. They already make a dated backup, and converting them needed more text-mode/newline care than this pass allowed. |
| **I2** lossy/crashing text encoding; one bad plugin stops the run | **fixed** | All 41 `.encode/.decode(ENC, "replace"/strict)` sites in record handling now use `MW_ERRORS`, as do the ini decode/encode and the long-id search. `run_fix`'s two per-plugin loops and `run_clean`'s write loop catch `Exception` per plugin, report "NOT changed (Type: msg)", and go on. The ini/text *file readers* that use `errors="replace"` are unchanged (read-only). |
| **I3** leveled-list merge ignores masters | **fixed** | `merge_levlist(tag, defs, known=None, masters_of=None)`. Each definition is diffed against the latest earlier definition by one of its masters (full master closure), else the first. This means a patch can now remove what its master added. Flags/chance come from the last plugin that changed them. `run_multipatch` passes the closure. Without `masters_of` it is still exactly tes3cmd's merge. |
| **I4** --restore-unused misplaces orphaned files | **fixed** | It recognises `\Off\unused\`, `\Off\orphaned\` and `\Off\broken\` (any case, either slash). Such a file goes back into the mod folder and is hard-linked (or copied) into Data Files. Errors are caught per line. The record is renamed `.restored` only when every line succeeded, so you can retry; it returns 1 otherwise. |
| **I5** only the first-ever asset backup is kept | **fixed** | `backup_asset_original` and `_backup_in_mod` still never replace an existing backup. When the current file is neither that backup nor a repair these tools wrote, it is kept as `<backup>.YYYYMMDD-HHMMSS<ext>` beside it. This is the mod-update case. Repairs are recorded as sha256 lines in `<backup>.repaired.sha256` by `replace_asset_in_place`. `--sort`'s "added masters" archive keeps the old first-only behaviour (`track_new=False`). |
| **I6** rename_ascii rewrites bytes anywhere; ignores NIFs | **fixed** | The new `plugin_path_rename` parses records and changes only:<br>• the **whole value** of path subrecords: MODL, ITEX, ALCH TEXT, SOUN FNAM, LTEX DATA, BSGN TNAM, INFO SNAM, MGEF PTEX. It matches the path without its top folder, or with it.<br>• the full path (with folders) inside SCPT SCTX/SCDT and INFO BNAM.<br>Book and dialogue text, and same-named files in other folders, are untouched. Writes are validated and keep the date. `check_folder` reports instead of renaming when a .nif/.kf in the mod names the file (`_models_naming`). |
| **I7** normal-map moves (revised to the intended design) | **fixed** | Vanilla Morrowind and MGE XE don't use normal maps; only OpenMW does. So tidy moves **every** `*_n/_nm/_normal/_nrm` `.dds/.tga/.bmp` under `textures\` to `Off\normal maps\<mod>\`, as the original did. There is no asset-cache requirement and there are no model-named, plugin-named or diffuse-sibling exceptions (`model_named_textures` and `_plugin_text` are removed; nothing else used them). If a model names a moved normal map, `mwdialog_check.py --fix` puts a flat stand-in there. When no diffuse texture with the same stem minus the suffix (`.dds/.tga/.bmp`, same folder) sits beside it, the file is still moved, with a warning: *"no matching diffuse texture beside it, check it's really a normal map; --undo puts it back"*. The warning goes in the move's reason and in a plan-level NOTE naming the file, and `--apply` prints `WARNING: moved … ` for each such file. **Supporting fix in mwdialog_check.py:** `VortexRepo.find` never returns a normal map that sits under an `Off\` folder of a mod, so `--fix` no longer copies the real map back out of `Off\normal maps\`. It uses the flat stand-in instead. Other files in `Off\` are found as before. `placeholder_dds` now also treats `_nrm` as a normal map: it gets flat (128,128,255), where before it got grey. |
| **I8** damaged BSA → struct.error crash | **fixed** | The new `_bsa_directory` checks the header: `12*count <= hash_off`, `12+hash_off <= file size`, and that the directory isn't short. Name offsets are bounds-checked too. Problems raise `FormatError`. All callers catch it and print a note: `files_present`, the asset index, `fix_long_names` and vortex_tidy's `run_assets`. |
| **I9** --play ini sync after a failed run; one ini backup | **fixed** | `main()` updates `[Game Files]` only when `_main` returned normally. Otherwise it prints that the ini was NOT updated. `write_ini_game_files` keeps three backups:<br>• `.mwdialog-original.bak`, written once<br>• `.mwdialog-play.bak`, replaced each time as before<br>• a dated `.mwdialog-YYYYMMDD-HHMMSS.bak`, never replaced and **not pruned**, so it can't delete anything that already exists<br>The ini itself is written with `safe_write_bytes`. |
| **M1** backups capped at .bak99 | **fixed** | `backup_candidates` lists the folder with a case-insensitive regex, with no upper limit. Oldest first: legacy next-to-file copies, then the backup folder, numerically sorted. `backup_path` = highest + 1. |
| **M2** second module copy when run as a script | **fixed** | On import, the module registers itself as `sys.modules["mwdialog_check"]`. That makes `mwdialog_assets` and `vortex_tidy` see the same settings (`--encoding`) and caches. |
| **M3** fix_long_names collisions / missed references | **fixed** | Skipped with a message: an id whose 31-character prefix another long id shares, or that equals an existing id. Renames now also cover placed references (CELL NAME after FRMR) and the whole value of ENAM, SCRI, NPCS, BNAM, CNAM, RNAM, ANAM, KNAM, TNAM and XSOL outside INFO/SCPT/DIAL. With `--openmw-cfg` it only reports. |
| **M4** build_merge loses DIAL/CELL details, master sizes 0 | **fixed** | The later DIAL record wins unless it is deleted. A type change is still warned about, and the first one is kept. CELL record flags (persistent etc.) come from the last input. The master size falls back to `master_paths`. If it is still unknown, a warning is logged and 0 is written as before. |
| **M5** remove_master ignores moved refs | **fixed** | MVRF counts like FRMR. |
| **M6** HEDR count written at a fixed offset | **fixed** | `set_hedr_count` writes only when HEDR is the first subrecord and is at least 300 bytes. |
| **M7** case-sensitive "our patch" checks | **fixed** | All 20 `x in/not in OUR_PATCHES` checks now use `is_our_patch()`. |
| **M8** multipatch cells reduced to NAME/DATA/AMBI | **fixed** | The world keeps each cell's latest header (`cell_heads`). Multipatch CELL records are that header with only NAME (renamed cells), or DATA fog and AMBI (fog cells), changed. Region, water height, map colour and so on are kept. |
| **M9** merged_objects raw scan, NPCO collapse | **fixed** | It uses `iter_records` on each file and leaves out a damaged plugin with a message. `merge_fields` keys inventory/spell entries by (id, occurrence), so two stacks of one item stay two. |
| **M10** performance | **partial (safe wins only)** | • Tag decoding is cached (`_tag`).<br>• `read_plugin_bytes` caches file bytes for `load_plugin`, `_check_refs`, `index_masters` and `merged_objects`. The key is size + mtime_ns, and every write drops its entry. The cache is capped at 256 MB.<br>• `_cell_exists` builds its name union once.<br>Measured on a 37 MB synthetic plugin: `iter_records` 0.18 → 0.08 s, records+subrecords 1.21 → 0.57 s, `World.load_plugin` 7.3 → 5.7 s. Nothing riskier was attempted. |
| **M11** lint | **fixed (real issues)** | Removed 9 unused variables and the duplicate `"TES3"` in `CONTENT_SKIP_TAGS`, and fixed 10 placeholder-less f-strings. `ruff --select F,E9,PLE` is clean. The remaining `B023` (18, closures called immediately inside the loop) and `B007` (101 unused loop variables) are style-only and left alone to keep the diff reviewable. |
| **M12** vortex_tidy details | **fixed** | • Deleted mods go to `deleted_dir(--staging)` (same folder as before for the default staging).<br>• A plan-only run doesn't create `vortex_tidy_blacklist.txt`.<br>• `--undo` reports what it couldn't put back, keeps those entries in the journal (rewritten atomically), returns 1, and never overwrites something already at the source.<br>• `_tool_modules` reuses already-loaded modules.<br>• `run_assets` warns if Data Files is missing and catches a damaged BSA. |
| **M13** DX10 textures always become DXT5 | **fixed (partial by design)** | `dx10_has_alpha` reads the DXGI format at offset 128 and the alpha mode at offset 144. Opaque formats → BC1/DXT1: BC1, BC4, BC5, BC6H, B5G6R5, B8G8R8X8, or alpha mode "opaque". BC2, BC3, BC7, RGBA and unknown formats → BC3 as before. It doesn't inspect BC7 pixel data, so an opaque BC7 without the opaque flag still becomes DXT5. |
| **M14** set_prev/relink no-op when PNAM is missing | **fixed** | `set_link` inserts PNAM after INAM (NNAM after INAM/PNAM) when it is absent. |

## Behaviour changes you will notice

1. **`--clean` removes fewer records.** It keeps records, references and cell settings that copy an *earlier* master but differ from the *last* one, because that is a deliberate revert. This is the C1 fix.
2. **Multipatch leveled lists can differ.** A patch can now remove entries its master added, and flags/chance follow the last plugin that changed them (I3).
3. **Multipatch cells are bigger.** They now carry the full winning header, not just NAME/DATA/AMBI (M8).
4. **`--fix` long-id renaming does a bit more and a bit less.** It now also renames placed references and owner/script/enchantment fields, but skips ids whose 31-character name would collide. With `--openmw-cfg` it only reports.
5. **Asset repairs may create extra dated originals** (`name.YYYYMMDD-HHMMSS.dds`) and `*.repaired.sha256` sidecars in `Off\...`.
   - This happens when a file differs from the kept original and isn't a known repair, for example after a mod update.
   - Originals kept by the *old* version have no sidecar. So the first new run on a file that the old version already repaired will keep one extra copy, of the repaired file. That copy is harmless and can be deleted.
6. **Non-ASCII renames are more conservative.** They are report-only when a model in the mod names the file. Only path fields and full paths in scripts are rewritten, never book or dialogue text.
7. **vortex_tidy moves every normal map** to `Off\normal maps\<mod>\`, with or without the asset cache. When a model names one, `mwdialog_check.py --fix` creates a flat stand-in normal map in Data Files, and it is never a copy pulled back from `Off\`. A normal map with no diffuse texture beside it is still moved, but the plan and `--apply` output warn about it by name. `--undo` puts it back.
8. **Morrowind.ini gets more backups:** a one-time `-original.bak` and a dated one per change, in addition to `-play.bak`. Messages now name the dated backup. The ini isn't synced after a run that stopped early.
9. **`--restore-unused` returns 1 and keeps its record** if any file couldn't be put back. **`vortex_tidy --undo`** behaves the same way with its journal.
10. **Messages:** a temporary `<file>.mwdtmp` can appear next to a plugin or asset if a write fails halfway. That file is the checked new version and can be deleted. Per-plugin errors are now printed as `NOT changed (Type: message)` and the run continues.
11. **Memory:** up to about 256 MB of plugin bytes are cached during a run.

## Deliberately not changed

- The **package restructure** and **splitting `World`** were not done in this pass (too risky). This is the main follow-up.
- **Follow-up:** `--clean` still identifies INFO records by INAM alone, not (topic, INAM), when comparing duplicates. This was not changed because it affects which records `--clean` deletes, and it needs its own tests on real dialogue.
- **Follow-up:** the rules-file writers that use text mode `open(..., "w")` still overwrite in place, after their existing dated backup (I1 partial).
- The `B023` and `B007` lint items, and the `_func` pyflakes note (an intentional `_` name).
- `merge_levlist` without `masters_of` (direct callers, tests) still behaves exactly like tes3cmd.
- The out-of-scope scripts `chargen_ship_patch.py` and `stranded_doors_patch.py` were not reviewed or changed.
