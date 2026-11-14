# mwdialog refactor, 2026-11-13

What changed in the Morrowind conflict tools and the `mw*` MWSE mods on 2026-11-13: three bug fixes, a split of
`mwdialog_check.py` into smaller modules, and seven speed-ups.

## Summary

| | Before | After |
| --- | --- | --- |
| `mwdialog_check.py` | 13,229 lines | 8,972 lines |
| Modules it loads | paths, text (+ assets, longpaths, mastercheck on demand) | the same, plus 15 new ones |
| Default check, 981 plugins | 98 s | 47 s |
| `--cell-conflicts`, 981 plugins | 31 s | 25 s |

Behaviour is meant to be unchanged apart from the bug fixes and one ordering change
(`mwstranded_data.json` is now written with its cells sorted).

## Rolling back

The scripts as they were before the split are in `_backup_pre_refactor\` (the ten `.py` files and the `.bat`
wrappers). To undo the split and the speed-ups, copy them back over the game folder and delete the 15 new
modules listed below.

That backup was taken after the undo-journal fix (section 1.3), so it already contains it. The Lua fixes
(sections 1.1 and 1.2) have no backup copy; undo them by hand from the descriptions below.

## 1. Bug fixes

### 1.1 Report timers stopped after the first save load

Files: `Data Files\MWSE\mods\mwguard\main.lua`, `Data Files\MWSE\mods\mwsoundguard\main.lua`

MWSE cancels every timer right before the `loaded` event. Both mods started their repeating timer once, at
`initialized`, so it only ran at the main menu. In play, mwguard never wrote a `PERF` report and mwsoundguard
never wrote its per-minute summary.

Both now start the timer from `initialized` and again from `loaded`.

### 1.2 mwhangwatch could not name sound-blocking mods while mwguard was on

File: `Data Files\MWSE\mods\mwhangwatch\main.lua`

mwhangwatch finds MWSE's handler tables by reading the upvalues of `event.register`. mwguard loads first
(load-priority 10000) and replaces `event.register` with its own function, so the lookup found nothing and the
"BLOCKED by" feature turned itself off.

mwhangwatch now follows mwguard's saved `origRegister` upvalue back to MWSE's own function before looking.

### 1.3 `--undo` could crash on its own journal

Files: `vortex_tidy.py`, `mwdialog_luafix.py`

- Both journal readers parsed every line with `json.loads` and no guard. A line cut short by an interrupted
  `--apply` made `--undo` stop with a traceback. They now skip blank or unreadable lines and say so.
- `vortex_tidy.py --apply` now flushes the run header and each `rmdir` line as it writes them.

Known gap, left as it is: `vortex_tidy.py` journals a move just after the rename. A crash in that instant
leaves one move unrecorded. Journaling first would leave a phantom entry whenever a rename fails.

## 2. The split

`mwdialog_check.py` kept everything that depends on the run as a whole (the `World` scan, fixing, merging,
sorting, `--full`, the command line). Code that stands on its own moved to 15 modules.

Rules the split follows:

- **Layers.** A module only imports modules above it in the table. There are no import cycles.
- **Nothing was renamed or rewritten.** Functions moved as they were, except for the two changes listed under
  "Changes made while moving".
- **`mwdialog_check` still exposes every name.** It imports each moved name back, so its own code,
  `mwdialog_assets.py`, `mwdialog_longpaths.py`, `mwdialog_mastercheck.py` and `vortex_tidy.py` work unchanged
  through `mwdialog_check.X`.

| Module | Lines | Builds on | What it holds |
| --- | --- | --- | --- |
| `mwdialog_tes3.py` | 349 | | The plugin file format: records and subrecords, the lossless text codec, cached reads, safe in-place writes |
| `mwdialog_bsa.py` | 96 | tes3 | BSA archives: directory, file names, a once-per-run memo |
| `mwdialog_media.py` | 341 | | Asset formats: DDS (read, reduce, placeholders), NIF (texture names, text keys, empty models), sound files |
| `mwdialog_backup.py` | 96 | | Where backups go and finding them again; `index_dir` |
| `mwdialog_loadorder.py` | 300 | backup, tes3 | `Morrowind.ini` [Game Files], `mwdialog_load_order.txt`, parsing of the mlox-style rule files |
| `mwdialog_records.py` | 551 | tes3 | Single records: splitting and cleaning cells, renumbering references, leveled-list and object merging, what a plugin defines and names |
| `mwdialog_state.py` | 427 | backup, paths, tes3 | The small record files beside the scripts: merged, disabled, conflict answers, cell winners, redundant, generated files, added masters |
| `mwdialog_cellmods.py` | 351 | tes3 | What `--cell-conflicts` writes for the MWSE mods: `mwcollide_data.json`, `mwstranded_data.json` |
| `mwdialog_datatree.py` | 604 | bsa, media, state, tes3 | What is on disk: `DataTree`, `ModelAssets`, `VortexRepo`; loaders for the on-demand modules |
| `mwdialog_console.py` | 109 | backup | Questions at the keyboard, the window title, the fix log |
| `mwdialog_masters.py` | 169 | backup, loadorder, tes3 | Adding and removing a master, whether an added one is still used |
| `mwdialog_patchfile.py` | 213 | backup, records, tes3 | Building the generated fix patch: placeholder records and cells, item fixes |
| `mwdialog_redundant.py` | 481 | console, datatree, patchfile, state, tes3 | Who uses whose objects, what each plugin is, which plugins make another redundant |
| `mwdialog_generated.py` | 364 | backup, console, datatree, media, paths, state, tes3 | Stand-in files, reduced textures, kept originals, removing them again |
| `mwdialog_restore.py` | 212 | backup, console, patchfile, redundant, tes3 | Restoring backups and sort dates, clearing unneeded backups |

Every module that prints also uses `mwdialog_text` for wrapping, as `mwdialog_check.py` does.

### The `--encoding` setting

`dec`, `enc` and `cstr` now live in `mwdialog_tes3.py` and read `mwdialog_tes3.ENC`. `mwdialog_check._main` sets
both its own `ENC` and `mwdialog_tes3.ENC` from `--encoding`. Moved code outside `mwdialog_tes3.py` that used
`ENC` directly now reads `mwdialog_tes3.ENC`, so it follows the setting too.

`mwdialog_check.ENC` still exists and is still what `mwdialog_longpaths.py` reads.

### Changes made while moving

- The three on-demand loaders (`mastercheck_module`, `longpaths_module`, `asset_health_module`) were three
  copies of the same import code. They now share one helper, `_sibling`, in `mwdialog_datatree.py`.
- `mwdialog_check.py` no longer imports `codecs` or `glob`; nothing left in it uses them.

## 3. Speed-ups

A profile of the default check on 981 plugins picked these. Each gives the same result as the code it replaced.

| Change | File | Before | After |
| --- | --- | --- | --- |
| Master-name pattern | `mwdialog_mastercheck.py`, `candidate_masters` | Built and compiled a regex for every plugin pair, about 700,000 times; a third of the run | One compiled pattern per plugin name, kept in `_STEM_RE` |
| Loop search in response chains | `mwdialog_check.py`, `World._check_chain` | Walked the chain again from every response | Skips responses an earlier walk already covered |
| "Some cell name starts with X" | `mwdialog_check.py`, `World._check_script_cells`, `World._cell_exists` | Scanned every cell name for each dialogue filter | Binary search in a sorted list, remembered per filter |
| Reading a cell | `mwdialog_check.py`, `World._load_cell` | Two passes over the cell's subrecords | One pass |
| Subrecord iteration | `mwdialog_tes3.py`, `iter_subs` | A function call and two unpacks per subrecord | One unpack and a dictionary lookup |
| "Does a patch cover both?" | `mwdialog_cellmods.py`, `write_collide_data` | Scanned every plugin for every pair in every cell; rebuilt the same grid per pair | A per-cell index of plugins, and one grid per plugin per cell |
| Vortex settings | `mwdialog_paths.py`, `read_vortex_settings` | Vortex's database files scanned once for staging and again for downloads | Read once per run |

One output change: `write_stranded_data` now writes the cells of `mwstranded_data.json` in sorted order. The
order used to vary from run to run. The mwstranded mod reads the cells into a table, so the order does not
matter to it.

## 4. How it was checked

- **Same output.** The original and the changed scripts were run on a copy of the 981 plugins and state files,
  in two modes: the default check, and `--cell-conflicts`. Console output and error output were byte-identical
  in both. `mwcollide_data.json` and `mwstranded_data.json` held the same data.
- **Same names.** Every name the original `mwdialog_check` module exposed still exists on the new one, apart
  from the two dropped standard-library imports.
- **Static checks.** All scripts compile with warnings as errors. A check of undefined names, call arguments
  and cross-module references found nothing.
- **Bug fixes.** The edited Lua files pass a LuaJIT syntax check. The upvalue lookup was tested against a mock
  of the wrapped `event.register`. `--undo` was tested with a journal whose last line was cut short.

Those runs used `--no-vortex --no-archive-lookup --no-sounds --no-interactive`, and the copy had plugins only,
no assets or BSAs.

## 5. Not checked

- `--fix`, `--sort`, `--full`, `--clean`, `--merge`, `--auto-merge`, `--multipatch`, `--asset-check` and
  `--play` were not run after the change. They passed the static checks and an import test only. Run
  `--fix --dry-run` before trusting `--fix` or `--full`.
- The Lua fixes were not run inside the game.
- There was no `tests\` folder in this install, so the README's `pytest` step could not be run. It was run
  afterwards; see section 7.

## 6. Left to do

- A second profile, to see what dominates the remaining 47 s.
- A review of `mwdialog_assets.py`, `mwdialog_longpaths.py`, `mwdialog_text.py` and the analysis rules in
  `mwdialog_luafix.py`. These were only checked statically.
- `README.md` still describes `mwdialog_check.py` as one file and does not list the new modules.
- The rest of `mwdialog_check.py` (sorting, fixing, merging, the command line) is tightly interlinked. Splitting
  it further means restructuring, not moving code.
- About 20 functions are not referenced by any script, for example `warn_overflow` and `find_vortex_root`.
  Some may belong to the missing tests.
- Smaller Lua issues found in review and not changed: mwfloatfix lowers wall-mounted torches; mwcollide matches
  on current position where the other mods use `startingPosition`; mwguard's wrapper cache never frees;
  mwperformers stores a log-once flag in the save; mwhangwatch's "now playing" scan is heavy;
  `mwguard\interop.lua` and `mwdialog_luafix.py` still describe a log-spam guard that no longer exists.

## 7. Fixes after review, 2026-11-14

Running the test suite against the split found two faults that the plugins-only comparison could not show.

- **The asset checks crashed on every model.** `ModelAssets.texture_names` in `mwdialog_datatree.py` passed its
  own module to `mwdialog_assets.model_facts_cached`, which expects `mwdialog_check` (`TEXT_KEY_TAG` and the
  other names). It now passes `mwdialog_check`, through `_check_module()`.
- **Vortex folders were lost from the record files.** `record_bases` in `mwdialog_state.py` looked for
  `TOP_ARGS` in its own globals, so the staging and downloads folders were never bases. `--restore-textures`
  could not find any `staging:` original, and new records would have held absolute paths. It now reads
  `TOP_ARGS` from `mwdialog_check`.
- `_sibling` loads the file that sits next to `mwdialog_datatree.py`, as the three loaders did before the split,
  not the first module of that name on `sys.path`.
- `read_vortex_settings` keeps only an answer that names a folder, takes `refresh=True`, and returns its own
  copy each time. `clear_vortex_settings_cache()` forgets it.

The tests now sit in `tests\` next to the scripts. Two were updated for the new layout
(`test_redundant_ask.py` patches `mwdialog_console`; `test_cache.py` patches every module that reads
models, through `conftest.patch_everywhere`). `tests\test_split_modules.py` is new: tagged `staging:` and
`downloads:` paths through `record_bases` and `--restore-textures`, the module handed to `mwdialog_assets`,
the sibling loader, the settings memo, and a check that no moved module reads run state from its own globals.
The backup of the files these fixes changed is in `_backup\pre-refactor-fixes-20261114-063112\`, with
`ROLLBACK.ps1`.

