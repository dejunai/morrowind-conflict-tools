# Split of mwdialog_check.py, speed-ups and fixes (2026-11-13, 2026-11-14)

- `mwdialog_check.py` keeps the run as a whole (the `World` scan, fixing, merging, sorting, `--full`, the command
  line). Code that stands on its own moved to 15 `mwdialog_*` modules; `mwdialog_check` imports every name back.
  Command-line options, `--help`, plan files, records and JSON are unchanged. Details: `MWDIALOG_REFACTOR.md`.
- Seven speed-ups with the same results (default check on 981 plugins: 98 s to 47 s). `mwstranded_data.json` is
  now written with its cells sorted.
- `--undo` (`vortex_tidy.py`, `mwdialog_luafix.py`) skips a journal line cut short by an interrupted `--apply`.
- mwguard and mwsoundguard restart their report timers after a save loads; mwhangwatch finds MWSE's handler
  tables through mwguard's wrapper.
- Fixed after review: the asset check crashed on every model (wrong module handed to `mwdialog_assets`), and the
  Vortex staging/downloads folders were lost from `record_bases`, so `--restore-textures` could not find
  `staging:` originals. New `tests/test_split_modules.py`; the tests also run from the game folder.

# Human-readable output wrapping (2026-11-11)

- Console output, report text, dated `mwdialog_fixes.log` lines, and `argparse --help` wrap at 115 characters (`mwdialog_text.py`).
- Continuation lines indent two spaces beyond the source line's leading indent, or align under a `- ` bullet or under the message after a log timestamp. A single overlong token (a long path) is not split.
- Clear lists (left-alone notes, missing masters, plugins taken out of the load order, patch load-order hints, and similar) are printed as bulleted `- ` items.
- Plan files are still written unwrapped: `--apply` compares action lines (including patch hashes) exactly. The on-screen plan preview is wrapped. Rules, records, JSON, CSV/TSV, and Lua patches are unchanged.
- The fix-log parser rejoins wrapped continuation lines so existing and newly wrapped logs both work.

# Relative paths, Vortex settings, and bundled LuaJIT (2026-11-11)

- No hardcoded absolute paths in the tools. The game root is the folder the scripts live in.
- Vortex's Morrowind staging and download folders are read from Vortex's own settings
  (`%APPDATA%\Vortex\state.v2`, `state`, or a settings backup). `--staging`, `--vortex-dir`,
  `--vortex-downloads` / `--downloads` override. If Vortex's data cannot be read and no flag is
  given, the tool exits with a message naming the folders it tried and the flag to pass.
- Recorded paths (`mwdialog_added_masters.json`, `mwdialog_reduced_textures.txt`, and the promoted
  block in `mwdialog_check.rules.txt`) are stored as `staging:` / `downloads:` / `game:` plus a
  path relative to that base. Older absolute entries are still read and are converted on the next write.
- LuaJIT is looked up at `<game>\tools\luajit\luajit.exe`, then on PATH. It is not committed
  (see `tools/README.md`).
- 7-Zip is looked up on PATH (`7z`), then at `<game>\tools\7z`. No registry and no Program Files
  paths. A missing 7-Zip is a clear error when a `.7z`/`.rar` archive needs to be opened.

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

## Asset pass speed-ups and the asset cache (`--asset-check` and `--full`)

The baseline is commit `dee9957`. The `*.perf.diff` files hold only this round's changes; the `*.diff` files still show everything since the originals. CLIs are unchanged. The only on-disk change is the cache file, which is converted automatically.

| # | Change | Where |
|---|---|---|
| 1 | **The "unused" scan no longer reads the tool's own files.** In the Morrowind folder itself it reads only `Morrowind.ini`, plus the `mge3` and `MWSE` folders. Files under Data Files are still read, except `*.bugreport.txt`. Before, the scan read the cache, `mwdialog_report.txt`, `mwdialog_unused_assets.txt` and the other lists. Every texture name in those files then counted as "used", so from the second run on, "unused" shrank to almost nothing (284 → 0 on the benchmark; now 284 on both runs). The cache's own entry, a word list of the whole cache, is gone too. | `mwdialog_assets.check`, text-file walk |
| 2 | **Model texture lists are read once and cached.** `ModelAssets.missing_textures` used to read every model (loose and in BSAs) with `NIF_TEXTURE_RE` on every run. It now uses the `"tn"` list in the cached model facts (`nif:<path>`), or vortex_tidy's record of the same file. A BSA's models are read once into `bsa2:<name>`, kept while the BSA's size and date are unchanged. A cache miss uses `nif_texture_names`, which gives exactly the old regex's results but about 15× faster (it finds the extension first). Tests cover spaces, odd characters, cp1252 bytes, double extensions and random bytes. | `nif_texture_names`, `nif_texture_refs`, `ModelAssets.texture_names`/`bsa_facts`, `model_facts`, `model_facts_cached` |
| 3 | **The cache is written as the run goes, and safely.** Entries are committed in batches of 500 and again right after the asset pass, not only at exit. Each batch is one SQLite transaction, so it is written whole or not at all. A killed run keeps every committed batch; the test kills a process with `os._exit`. Write errors of any kind are reported once and never stop the run. A damaged cache file is renamed `.bad` and a new one is started. There is no `.add` side file any more. | `AssetCache.flush`/`close`, `shared_cache` |
| 4 | **The cache is smaller and faster.** <br>• **Format:** `mwdialog_asset_cache.sqlite` replaces the JSON. It is read once at start-up, with each entry decoded only when used. <br>• **Texture headers:** stored as a few decoded fields (`tex2:`) instead of 296 hex characters (`texh:`). Old `texh:` entries are converted the first time they are used. <br>• **Pruning:** after each asset pass, entries for files that no longer exist are removed. vortex_tidy removes the records of files and mods that are gone. The file is compacted (VACUUM) when pruning frees a quarter of it or more. <br>• **Migration:** the old `mwdialog_asset_cache.json` and its `.add` file are converted once, then renamed `.json.migrated` / `.json.add.migrated`, not deleted. Converted: model facts (to `nif:`), `texh:`, `snd:`, `refs:`/`names:` and `fixed:`. Dropped: the per-path `clean2:`/`seen2:` entries (now kept per mod), the old `bsa:` lists, and the word lists of the tool's own files. <br>• **Other readers:** vortex_tidy had no direct reader of the JSON left; it already used `shared_cache` (the normal-map redesign removed its direct read). | `AssetCache`, `migrate_key`, `texture_facts` |
| 5 | **One walk of Data Files per asset pass.** `DataTree` walks Data Files once with `os.scandir`. ModelAssets, the asset checks, the sound list and the Lua/config scan all use it. Before, the same tree was walked four times and up to four `stat` calls were made per file; now it is one `os.stat` per file. The sizes and dates in Windows' directory listing are deliberately **not** used. For a Vortex hard link that vortex_tidy repaired through its other name, those can be stale, and the cache would then trust a changed file. BSA name lists and indexes (`bsa_file_names`, `bsa_index`) are remembered for the run by size + `mtime_ns`. That removes the repeated BSA reads in the 6–7 scans of a `--full`. | `DataTree`, `collect_sound_files(tree=)`, `_bsa_memo` |
| 6 | **vortex_tidy keeps one record per mod file and the full check trusts it.** The record is keyed `tidy3:<mod folder>\|<path>`, with size + date. It holds a clean flag and, for models, the full model facts including the texture list. A Data Files file counts as the same file when its size and date match a tidy record for that path. With a Vortex hard link they always do; a different file at that path doesn't. Such a file gets the light check only (name, empty file) and its model facts come from tidy, so it isn't read. **Stand-ins** listed in `mwdialog_generated_files.txt` are always checked in full, bypassing both the cache and tidy's records. So a proper file put in place of one is noticed, even when it has the same size and date. | `check_folder`, `run_assets`, `prune_tidy`, `AssetCache.tidy_lookup`, `generated_rels` |

**Removed:** the re-read of every "no polygons" model on each run. That fix-up for older cache entries is now done once, when an old entry is used.

### Benchmark (synthetic install on the box: 22,000 DDS, 8,000 loose NIFs, an 8,000-model BSA, 2,000 WAVs, 800 Lua files, 6 plugins)

| run | before | after |
|---|---|---|
| `--asset-check` run 1 / run 2 | 12.1 s / 9.5 s | 7.7 s / **3.1 s** |
| `--full --yes` run 1 / run 2 | 25.4 s / 12.8 s | 21.5 s / **6.7 s** |
| `--full` asset step, run 1 / run 2 | 22 s / 10 s | 18 s / **4 s** |
| cache after run 2 | 23.1 MB JSON (grows every run) | 12.6 MB SQLite (stable) |
| `--asset-check` after vortex_tidy checked the mods (hard links) | n/a | 5.0 s first run, no model read |
| first run after converting a 22 MB JSON cache | n/a | conversion 1 s, run 8.5 s, next 3.2 s |

The reports from before and after are identical apart from the order of lines. The one exception is the corrected "unused" count on run 2.

### Behaviour changes you will notice

1. **New cache file.** The cache is now `mwdialog_asset_cache.sqlite`, next to Morrowind.ini, and while a run is going it may have `-wal` and `-shm` files beside it. The first run converts the old JSON and prints `Asset cache: converting mwdialog_asset_cache.json (N MB) ... once`, then the new name of the old file. Delete `mwdialog_asset_cache.json.migrated` when you like.
2. **The first run after updating does some reading again:**
   - every model's texture list (to fill `"tn"`);
   - every BSA's models, once each;
   - in vortex_tidy, every mod file once, because the old per-path clean entries can't be tied to a mod.

   After that, runs read only new or changed files.
3. **"Unused" textures and sounds stay reported on later runs.** Before, they disappeared from the second run on. Expect more `--fix` moves to `Off\unused\` than you've seen lately; they are the real unused files.
4. A BSA's texture names now come from all its models, including ones a later BSA overrides. That is slightly more conservative: a texture only an overridden model uses is never called unused.

## AutoMerge object-merge fix (2026-11-11)
Bug: `--auto-merge` keeps only the last input's whole record when two inputs change the same object, and the
merged plugin lists every input's masters. The Multipatch's object merge then measured each AutoMerge record
against that union of masters, so an input made against Morrowind.esm alone looked like it deliberately undid
another master's change. Prison-ship lantern: Glowing Flames TLAD Tweaks (masters: vanilla; radius 375, script
Float, no sound) beat the Expanded Sounds TLAD patch inside the merge; with Expanded Sounds among the merge's
masters, the Multipatch read "Float, no sound" as an intended revert and kept it.
Fix:
* `expand_merged` / `object_merges`: the Multipatch looks at a merged plugin as the plugins it was built from
  (`mwdialog_merged.txt`), each measured against its own masters; results the merged plugin already has are
  skipped. Falls back to the merged plugin if any input file is gone.
* `run_auto_merge`: objects (MERGE_TAGS) that 2+ inputs change are merged field by field before
  `build_merge` writes them (`object_merges=`), so the AutoMerge itself is right. Off with --no-merge-objects.
* Tests: tests/test_automerge_objects.py (8).

## Mipmaps only where a world model draws the texture (2026-11-11, branch `mipmaps`)
Before: vortex_tidy (`check_folder` -> `_examine_dds`) reported "no mipmaps" for EVERY DDS of 64 px+ with one
level in a mod (except the few `ui_texture` paths) and `--apply` regenerated the chain with texconv (`-m 0`,
original kept in `Off\textures\`). mwdialog_check's asset pass did the same for every loose DDS in Data Files
that tidy hadn't already recorded (WARN + a `tex` fix for `--fix`). MCM logos, effect sprites, blood/glow
sheets, texture packs... all got mipmaps.
Now:
* **vortex_tidy**: a texture is reported without mipmaps only when one of the mod's OWN world models names it
  (`.nif` texture lists from the cached model facts; effect / UI models don't count) and it isn't exempt.
  Skipped ones are counted ("N texture(s) without mipmaps left alone") and their tidy record keeps
  `"m": true` + the texture facts (`"t"`), so a later model that starts using one is noticed without
  re-reading clean files. No cache-key bump (the change only narrows findings).
* **mwdialog_check --asset-check / --full**: the per-file texture pass no longer judges mipmaps. A new per-pair
  pass (`mip_pairs`) takes every WINNING model (loose or BSA) that isn't an effect/UI model, resolves each texture
  it names to the WINNING file (the `.dds` of a `.tga/.bmp` name first) and reports those without mipmaps:
  loose ones as WARN + a `tex {"mips": true}` fix (merged with any other conversion of the same file; `--fix`,
  `--dry-run` and the `Off\` backups as before); ones inside a BSA as one INFO line (a BSA can't be changed).
  This covers texture packs for existing models, including tidy-trusted hard links.
  Override rules (`WinningFiles`): vanilla Morrowind takes the newest by date - the latest-dated BSA (same
  date: registered later), then the loose file unless that BSA is newer; Morrowind.ini `TryArchiveFirst=1`
  prefers the BSA, `-1` loose only.
  Cache: loose textures `tex2:` (size+date; tidy's `"t"` is used first), textures in BSAs `tex2b:<bsa>|<rel>`
  (BSA size+date), model texture lists as before (`nif:`, `bsa2:`, tidy `"f"`). Repeat runs read no DDS/NIF.
* **Exemptions** (`MIP_EXEMPT_DEFAULTS` in mwdialog_assets.py, globs on lowercase backslash paths; user file
  `mwdialog_mip_exempt.txt` next to Morrowind.ini: `texture:`, `texture-name:`, `mesh:`, `mesh-name:` lines,
  `!` in front drops a default):
  - texture paths: `icons\*`, `bookart\*`, `splash\*`, `mwse\*`, `*\mwse\*`, `*\mcm\*`, `textures\{menu,menus,ui,gui,hud,
    levelup,splash,bookart,birthsign(s),vfx,fx,effects}\*`, `textures\cursor*\*`, `textures\*\vfx\*`, plus the old
    `ui_texture` set (menu_, tx_menu, tx_cursor, compass, target, scroll... at the top of Textures);
  - texture names: `menu_*`, `tx_menu*`, `*logo*`, `*splash*`, `cursor*`, `tx_cursor*`, `compass*`, `tx_compass*`,
    `levelup*`, `vfx_*`, `*_vfx*`, `tx_*fx*`, `fx_*`, `tx_blood*`, `blood_*`, `tx_glow*`, `*_glowsheet*`, `*spritesheet*`;
  - effect / UI models (their textures don't count): `meshes\e\*`, `meshes\{vfx,fx,mwse,menu,ui}\*`,
    `meshes\*\vfx\*`, `meshes\*\mwse\*`, names `vfx_*`, `*_vfx*`, `fx_*`. Magic-effect particle textures (MGEF
    PTEX) are named by no model, so they are never flagged.
* `ModelAssets.bsa_paths` (one line in mwdialog_check.py) keeps the registered BSA list for the pass.
* Tests: tests/test_mipmaps.py (8): MCM logo / icon / book art / VFX not flagged, own-model texture flagged,
  texture pack flagged only by the top-level check, BSA override order + TryArchiveFirst, vanilla BSA model vs
  loose pack, cached skip re-judged when a model appears, exemption file, cache reuse (no DDS/NIF/BSA reads).
Not changed: `ModelAssets.mesh_bsa` still keeps the FIRST BSA that has a model (used by the missing-model /
missing-texture checks); the game uses the newest. DX10 textures are still converted with a full chain.

## Paths too long for Windows / the game's fields (2026-11-11, branch `longpaths`)
New module `mwdialog_longpaths.py` (loaded by mwdialog_check like mwdialog_assets).
Limits used (from MWSE's engine headers): full path <= 259 characters (MAX_PATH; Morrowind.exe isn't
long-path aware; TES3DataHandler keeps Data Files in a MAX_PATH buffer); SOUN FNAM <= 31 (TES3Sound
filename[32]); MGEF ITEX/PTEX <= 31 (TES3MagicEffect icon[32]/particleTexture[32]; reported, MGEF isn't
retargeted); MODL/ITEX/BODY/BSGN are heap strings (no record limit); LTEX texturePath[MAX_PATH]. Files in
a BSA are found by hash: never moved. The CS's 32-character mesh limit is an editor limit only.
* mwdialog_check --asset-check (also --full): files under Meshes/Textures/Icons/Sound/Splash whose full path
  in Data Files is over 259 characters (or a sound whose record name is over 31) are planned to move to
  `<Top>\lp\<name, 16 chars>_<sha1 of old path, 6 hex>.<ext>` (longer hash, then a number, on a clash; the same
  file always gets the same name; a model's x*.nif/x*.kf twins move with it). Records naming the old path:
  every .esp record is corrected in place (the existing item-fix path, .bak first); for masters the last
  master record of each object gets a corrected copy in `mwdialog_check - ESM fixes.esp` (the .esm is never
  written). Loose models naming a moved texture get the new length-prefixed name (original kept via
  backup_asset_original, feature "longpaths"). A texture a BSA model names is left alone (WARN). Music,
  video and book art (named in scripts / book text) are reported only. Near-limit files (>240): one INFO.
  --fix moves the Data Files file and, for a Vortex hard link, the mod folder's copy; a failed move drops
  its record fixes. --dry-run shows the plan. Report first by default.
* `mwdialog_longpaths.json` (next to Morrowind.ini) lists every move (old/new path, files, edited .esp and
  models, masters corrected through the patch). Files already moved are never shortened again; records
  still naming an old path (another mod, a master) are pointed at the new one on later runs, and the old
  name counts as present for the missing-file checks. `--longpaths-undo` moves everything back and
  restores the paths in plugins and models (the next --fix rebuilds the patch without the copies).
* vortex_tidy: per mod, files whose path will be too long once deployed are moved inside the mod folder
  (--apply), the mod's .esp files edited (originals in Off\longpaths\), its models' texture names rewritten,
  its .esm listed for mwdialog_check's ESM patch; staging paths over 259 that deploy fine: INFO.
* Tests: tests/test_longpaths.py (8): naming/uniqueness/collisions, .esp edited + .esm via patch, loose model
  texture + icon (.tga name, .dds file), BSA-named texture left alone, undo + rerun idempotency with x*.kf
  twins, dry run, tidy per-mod flow then the ESM patch, sound name over the 32-byte field.

## Master mismatch guard (mwdialog_mastercheck.py)

A patch made for a different mod with the same file name, or for another version of its master, is now
recognised and reported with a confidence score, instead of being "repaired" into place.

- **Primary signal: reference resolution.** For each .esp and each master it lists *or names in its file name*
  (`X - Y Compatibility Patch.esp` -> `X.esp`, `Y.esp`; tes3cmd-made patches often list no masters), the IDs it
  overrides or names (inventory, scripts, spells, factions, races/classes/body parts, leveled-list entries,
  journal/topic/object names in its scripts and result scripts, INFO PNAM/NNAM links, cell references into the
  master) are checked against the installed master. An ID that isn't defined anywhere but carries one of the
  master's ID prefixes (e.g. `CS_`) counts as a reference into that master that no longer resolves.
- **Evidence that survives cleaning.** References an earlier --fix removed (`'X' doesn't exist -> ...`) and master
  cell references dropped (`in master 'M', which no longer exists there`) are read back from
  `mwdialog_fixes.log` and `mwdialog_backup\fixes.archive.txt` (stream-parsed: only lines with the key phrases are
  decoded; the append-only archive is continued from the cached offset, a rotated log is re-read), and misses are
  kept per (plugin, master) in `mwdialog_mastercheck_cache.json`.
- **Header size only when it is the original value:** the size recorded the first time a mismatch is seen
  (`mwdialog_master_sizes.json`, written before --fix syncs it), the oldest `synced the size recorded for 'M'
  (a -> b)` line in the logs, or - when the header was rewritten (a sync or "added master" in the logs) - the
  plugin as downloaded: the Vortex download archive named like the mod's staging folder (`--vortex-downloads`,
  default: Vortex's own setting (no hardcoded fallback); .zip natively, .7z/.rar via 7-Zip (PATH, then <game>\tools\7z);
  `--no-archive-lookup` to skip). The downloaded copy's references are checked too. Archive reads are cached
  by archive size/date.
- **Verdicts:** `matches`, `other version` (WARN: a few references gone, the rest lines up; stays enabled, --fix
  cleans as before) and `different mod` (confidence >= 0.75, `--mismatch-threshold`): WARN, and --fix/--clean
  do **not** sync the header size or strip the dead references/cell references of that plugin (they are the
  evidence). `--disable-mismatched` takes such plugins out of `mwdialog_load_order.txt` (logged; add the line back
  to undo). `--no-master-guard` turns the check off.
- Camonna Tong case (real data): `OAAB Brother Junipers Twin Lamps - Camonna Tong Compatibility Patch.esp` is
  for Caeris' Camonna Tong, an older version: its embedded CS_GalynScript is identical to the installed one and
  CS_CT12 resolves, but its Galyn Arvel carries `CS_FairKey`, which Camonna Tong 2.16 no longer has (an earlier
  --fix removed it). Verdict: other version, 25% confidence of a different mod; keep it.

## vortex_tidy: orphan normal maps stay in place

- A normal map (`*_n`, `*_nm`, `*_normal`, `*_nrm`) moves to `Off\normal maps\<mod>\` only when its diffuse
  texture exists: beside it, at the same path under `textures\` (or by name) in any mod in staging, loose in
  Data Files, or in a BSA there. One with no diffuse anywhere is left where it is - not moved, no stand-in -
  and listed in the plan ("left in place"); if nothing uses it, mwdialog_check --full's unused-asset purge
  removes it.
- Exception: a file whose path (mod folder included) says "normal map(s)" - any case and separator,
  `(?<![a-z])normal[\s_\-.]*maps?(?![a-z])`: Normal Maps, normal_map, Normal-Map, NormalMap, normal.maps - an add-on normal-map pack, which is
  for OpenMW only - moves either way, and the plan notes the pack as not applicable to classic Morrowind.

## mwdialog_luafix.py + mwdialog_lua.py (new): static checker / in-place patcher for MWSE Lua mods

- `mwdialog_lua.py`: pure-Python Lua 5.1/LuaJIT tokenizer (long brackets of any level, nested-level comments,
  every escape incl. `\z`/`\x`/`\ddd`, LuaJIT number suffixes, BOM, shebang) and a full recursive-descent parser
  (every statement/expression, goto/labels) with byte spans; text is handled as latin-1 so edits never touch bytes
  they don't replace. Scope resolution binds each name to its local/param/global.
- Rules G1-G5, A1, A2, B1, C1, D1, F1, F2, H1-H6 (see the module docstring); only `high` findings are patched by
  default (`--level medium` adds the rest that have a mechanical fix). Helpers are put at the start of line 1, so
  no line number moves. A patch is written only when LuaJIT compiles it (the original must compile too), the
  parser re-reads it, and a second pass would change nothing more.
- Thresholds shared with mwguard: `MWSE\config\mwguard.json` (its `priorityLimit`, `logBudgetInit`, `logBudget`,
  `logKeepPatterns`, `logExemptMods`, `enabled`, `logSpamGuard`, v1's `throttleSeconds`; a `"luafix"` section for
  the rest), then `mwdialog_luafix.json`.
- Safety: only files under `...\MWSE\mods\` (never core/lib/config/initialize.lua), your own mods skipped unless
  `--include-own`, plan by default, in-place `r+b` writes (hard links kept) after a backup copy to
  `mwdialog_backup\luafix\<run>\`, journal + `--undo` (refuses files changed since), per-file results cached in the
  asset cache (`luafix1:` keys).
- vortex_tidy: the Lua check runs per staging mod after the moves (plan lists it, `--apply` patches, `--undo`
  reverts; `--no-lua`, `--lua-only`, `--lua-level`, `--luajit`).

## mwdialog_luafix 2: the log shim replaces the old mwguard's log-spam guard

mwguard is now a passive profiler, so F1 is the only thing keeping log spam out of MWSE.log.

- **One shim per mod, inline on line 1 of each of its files that logs.** Line numbers don't move. The shim makes `print`, `mwse` and `mwluafix_log` locals of that file only. The global `print` and other mods are never touched. The shared state lives in `package.loaded["mwluafix_logshim:<mod>"]`, built by whichever of the mod's files loads first.
- **Routing, like the old guard:**
  - The mod's first `budgetInit` lines (40) reach MWSE.log, plus `budget` (10) after `initialized`.
  - Errors and warnings always reach MWSE.log: anything matching `keepPatterns` (error / traceback / fail / warn / attempt to / `file.lua:N:` ...). The mod's own log gets them too.
  - Everything else goes to `Data Files\MWSE\logs\<mod>.log`, with one notice in MWSE.log.
- **The mod's own log:**
  - Identical lines collapse into "previous line repeated N more time(s)".
  - At most `perSecond` (50) lines a second; the rest are counted as "dropped".
  - Rotated at `maxMB` (2), keeping one `<mod>.old.log`. The previous session's log is rotated the same way at the first write.
  - If something else (the mod's own `outputFile` logger) already wrote `<mod>.log` this session, the shim writes `<mod>.luafix.log` instead.
- **Flushing:** opened lazily and buffered. Flushed on every line before `initialized`, on errors, every `flushSeconds` (2), and on save/loaded/menuEnter and Lua shutdown.
- **Failures:** every io call is pcall'd or returns nil. A log that can't be opened leaves the mod in MWSE.log. Ten internal errors and the shim passes everything through.
- **Loggers:** `mwse.Logger.new(...)`, `require("logging.logger").new(...)` and `.getLogger(...)` in a shimmed mod become `mwluafix_log.wrap(...)`. On that instance only, trace/debug/info go through the same route, and the logger's own level and format still decide. warn/error are untouched. With MWSE's logger, the record is made from the wrapper, so `EnableLogLineNumbers` still shows the mod's line.
- **Scope:** `--lua-log flagged` (default: mods with log-spam signs), `all` (every mod that logs) or `off`, in both `mwdialog_luafix` and `vortex_tidy`, or `log.scope`. `exemptMods` (and the old `logExemptMods`) never get it.
- **Upgrading:** version-1 shims already in files are replaced in place by the new one, even with the scope off.
- **Settings:** `mwguard.json` → `"luafix": { "log": { scope, budgetInit, budget, keepPatterns, perSecond, maxMB, keepOld, flushSeconds, errorRepeat, exemptMods } }`. The old top-level `logBudgetInit` / `logBudget` / `logKeepPatterns` / `logExemptMods` are still read.
