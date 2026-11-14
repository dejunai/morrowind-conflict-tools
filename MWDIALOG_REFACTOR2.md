# mwdialog review follow-up, 2026-11-14

What changed after the review of the conflict tools and the `mw*` MWSE mods. The earlier split, the seven
speed-ups, and the 2026-11-14 asset-check fixes are in `MWDIALOG_REFACTOR.md`. This file is only this pass.

## Summary

| Change | Where |
| --- | --- |
| pytest 9.2.0 installed for the interpreter that runs the tools | user site-packages (the scripts still use only the standard library) |
| `chargen_ship_patch.py` and `stranded_doors_patch.py` retired | `_backup\retired-one-off-20261114\` |
| Leveled-list merge drops one `(id, level)`, and leaves other levels of that id | `mwdialog_records.py` `merge_levlist` |
| Each merged object record is parsed once | `mwdialog_records.py` `merge_object` |
| Master check uses the shared TES3 reader, and a matching file size no longer clears reference misses | `mwdialog_mastercheck.py` |
| An archive copy with no real overlap is ignored | `mwdialog_mastercheck.py` `original_from_archive` |
| Staging folders are indexed once per run | `mwdialog_mastercheck.py` `staging_folder_of` |
| Cell-conflict object tags come from the shared read cache, keyed by size and `mtime_ns` | `mwdialog_cellmods.py` `object_info` |
| Hidden performers are stored on the player | `Data Files\MWSE\mods\mwperformers\main.lua` |
| Stranded scenery is shown again from `startingPosition` | `Data Files\MWSE\mods\mwstranded\main.lua` |
| mwguard stays loaded when profiling is off, and the sample rate is read live | `Data Files\MWSE\mods\mwguard\main.lua` |

`python -m pytest tests -q` after these edits: 336 passed, 21 skipped.

## 1. pytest

pytest 9.2.0 was installed with `python -m pip install pytest` into the user site-packages of the Python 3.15
that runs the tools (`py.test` landed in the user Scripts folder, which is not on `PATH`; `python -m pytest`
works). Nothing in the tool scripts imports pytest.

## 2. Retired one-off patch builders

`chargen_ship_patch.py` and `stranded_doors_patch.py` were one-off ESP builders. They imported all of
`mwdialog_check.py` to reuse the record helpers. They are not part of `--fix`, `--cell-conflicts`, or the
MWSE mods.

Both files were moved, unchanged, to `_backup\retired-one-off-20261114\`.

- `README.md` lists them under that folder.
- `tests\test_paths.py` no longer treats those two names as shipped root scripts. `MWDIALOG_REFACTOR2.md`
  still matches the `mwdialog_` lint pattern.

`chargen_ship_patch.py` wrote every cell reference in the persistent group (no `NAM0`). Exterior references
are temporary, so those edits would not apply. That was left as it is, because the script is retired.
`stranded_doors_patch.py` already split persistent and temporary references; it was retired with it.

## 3. Leveled lists and object merges

File: `mwdialog_records.py`

`merge_levlist` still measures each definition against the latest earlier definition written by one of its
masters. Removing an entry removes that `(id, level)` pair only. A level of the same item added by another
mod stays. The old second pass deleted every level of an id the moment the measured list omitted the id.

`tests\test_check.py` `test_I3_dropping_one_level_keeps_another_mods_other_level` covers it: Morrowind has
`sword` at level 1, mod A adds `sword` at level 10, mod B (mastered to Morrowind) drops `sword` and adds
`axe`. The merge keeps `sword` at 10.

`merge_object` used to call `merge_fields` twice for every version. It now parses each body once and builds
the field map and the field order from that parse. The merged bytes are the same.

## 4. Master check

File: `mwdialog_mastercheck.py`

### Shared reader

`header_masters`, `plugin_facts`, `master_profile`, and the per-plugin read inside `check` use
`mwdialog_tes3` (`iter_records`, `iter_subs`, `cstr`, `read_plugin_bytes`). The private walker is gone.

`cstr` keeps bytes the code page does not define, and it keeps spaces in an id. The old `_cstr` used
`cp1252` with replacement and `strip()`, so those ids could not match the rest of the tools.

A record whose subrecords run past its end stops that record (`FormatError`). The old walker treated the
overrun as data and kept going.

`master_profile` remembers a file by path, size, and `mtime_ns`. The old key used the timestamp truncated
to a whole second, so two writes in the same second with the same size shared one profile. A rewrite that
restores the previous timestamp and keeps the same size still hits the cache; the read cache in
`mwdialog_tes3` has the same limit.

### Same file size

`assess` still records whether the master is the same size as the copy the plugin was saved against, and a
different size still adds 0.1 to the confidence. A matching size used to force the confidence down to 0.05
and the kind to `matches` or `other version`, so unresolved references could not reach "different mod".
That override is gone. `tests\test_mastercheck.py` `test_assess_scores` expects "different mod" for four
unresolved `zz_` ids even when both sizes are 5.

### Download archives

`original_from_archive` scores each copy as shared record ids minus ids that appear in only one of the two
files. A negative score is skipped. A same-named plugin from another archive, which the stem prefix match
can still open, is no longer treated as the downloaded original and its reference names are not added to
the verdict. `test_unrelated_archive_copy_is_not_used` puts a plugin of unrelated ids in a zip named like
the mod folder and expects no original.

`staging_folder_of` still prefers a hard link under the staging root. The fallback used to list every mod
folder on every plugin. It now builds one map of top-level filename to mod folder per staging root for the
process. Nested plugin paths are still not in that map; a hard link is what finds those.

## 5. Object tags for mwcollide and mwstranded

File: `mwdialog_cellmods.py` `object_info`

The tag, model, and script lookup that `--cell-conflicts` uses before writing `mwcollide_data.json` and
`mwstranded_data.json` read every plugin with `open().read()` and cached the result by plugin name only.
It now uses `read_plugin_bytes` (the same size and `mtime_ns` cache as the rest of the run) and its own
memo key is `(name, size, mtime_ns)` for each file in the load order. A plugin rewritten earlier in the
same process, with a new size or timestamp, is read again.

## 6. MWSE mods

### mwperformers

File: `Data Files\MWSE\mods\mwperformers\main.lua`

Hiding a performer used to set `ref.data.mwperformersHidden` on the NPC, and the one-time log line set
`ref.data.mwperformersLogged`. Touching `ref.data` stores a lua table on that reference in the save, for
every performer the player walks up to.

Hidden performers are now a map on `tes3.player.data.mwperformers`, keyed by cell, object id, and the
plugin placement (`startingPosition`), rounded with `floor(x + 0.5)`. The "left this NPC alone" log is a
session table (`sessionLogged`), cleared on `loaded`. Showing them again clears the player-data key and
enables the reference. The hide rule is unchanged: only a performer placed by the same mod that makes them
perform is disabled, and the mod that loads last keeps its band.

### mwstranded

File: `Data Files\MWSE\mods\mwstranded\main.lua`

The list match already used `startingPosition` for objects. The "shown again" path rebuilt the key from
the live position, so a nudge across a half-unit boundary (mwfloatfix lowering an item, for example) left
the reference disabled after it left the list. Objects now use `startingPosition` there too. Actors still
use where they stand. Rounding is still Python's half-to-even `round`, via `pyRound`.

### mwguard

File: `Data Files\MWSE\mods\mwguard\main.lua`

`enabled = false` in `mwguard.json` used to `return` before the Mod Config menu was registered, so the
menu could not turn profiling back on. The script now always registers the menu and always installs the
`event.register` wrapper. While `config.enabled` is false the wrapper calls the original handler and does
not time it, `checkPriority` does not log, and the periodic report returns immediately. `sampleEvery` is
read on each call, so the sample-rate slider applies to handlers already wrapped. Turning profiling on
from a session that loaded with it off takes effect for handlers registered after mwguard, without a
restart. Handlers registered before mwguard's `main.lua` runs are still not wrapped; MWSE has already
called `event.register` for those mods.

## 7. How it was checked

- `python -m pytest tests -q`: 336 passed, 21 skipped (skips are the existing LuaJIT, MWSE-source, and git
  cases).
- New or updated tests: leveled-list levels (`test_I3_dropping_one_level_keeps_another_mods_other_level`),
  same-size master verdict (`test_assess_scores`), unrelated archive copy
  (`test_unrelated_archive_copy_is_not_used`).
- The three Lua files were not loaded inside the game.

## 8. Left as they were

- `diag\impact.py` and `diag\keys.py` still import `mwdialog_check_new.py`, which is not in this folder.
  `diag\lantern_diag.py` imports `mwdialog_check` and is unchanged.
- One cell-reference error still counts as three misses in `assess`. Cell references are still not part of
  `plugin_facts`; `mwdialog_check.py` passes that flag in from its own reference walk.
- `mwinfoloop`'s startup cache is still keyed by plugin size and modification time. A dialogue rewrite that
  keeps the same size and restores the old timestamp still looks like the same install.
- The staging filename index is still one level deep.
- `--fix`, `--full`, and an in-game pass of the three Lua mods were not run for this pass. The test suite
  covers the Python behaviour these edits changed.

## 9. Follow-up fixes after review (2026-11-14)

- **Same-size master (middle option).** `assess` again treats a plugin saved against a master of exactly the
  installed size as built for it, but no longer clears every miss: the verdict is at most "other version"
  (confidence capped at 0.74) unless the misses are overwhelming - at least `SAME_SIZE_OVERWHELMING` (90%) of
  the references into the master don't resolve, and at least `SAME_SIZE_MIN_MISSES` (8) of them (a
  cell-reference error counts as 3). A different size keeps the plain verdict.
- **Downloaded original for large plugins.** The archive cache kept only 5,000 defined IDs per copy, and the new
  "skip a copy that shares fewer IDs than it differs by" rule then rejected the exact original of any plugin
  with more than about 10,000 IDs (Tamriel Rebuilt scale). Every ID (and every reference and link) is now kept.
  The cache has `"archives_version": 2`; entries from an older or unversioned cache are dropped and read again
  from the archive, never mixed. The key is `<archive>|<size>|<st_mtime_ns>|<plugin>`, and paths stay tagged
  (`downloads:` / `staging:` / `game:`).
- **Refreshable memos.** `_staging_index(root, refresh=True)`, `master_profile(path, refresh=True)` and
  `clear_caches()` (staging index and master profiles; the JSON cache is not touched). MWManager's GUI calls
  `clear_caches()` where it re-reads Vortex.
- **Reader.** `_subs` keeps the subrecords read before a bad size (what its docstring says); `plugin_facts`
  handles each record on its own, so one unreadable record no longer hides the rest of the plugin.
- **Minor.** Unused `import shutil` removed; the `merge_levlist` docstring rewrapped; mwguard's "active as
  passive profiler" line is written only when profiling is on (no other mwguard change).
- **Patch for Purists sort rule.** A rule in the rules text, not in the code: `mwdialog_check.rules.txt` has
  `[NearStart]` / `Patch for Purists.esm` near its top, so `--sort` loads it right after Bloodmoon.esm and before
  Tamriel_Data, OAAB_Data and the other masters (its own masters are the three Bethesda files). The scripts
  have no list of major masters.
- Tests: `test_assess_scores` (same size: few misses -> other version; overwhelming -> different mod),
  `test_large_plugin_matches_its_downloaded_original` (12,000 and 100,000 IDs),
  `test_unversioned_archive_cache_is_dropped_and_rebuilt`, `test_archive_cache_round_trips_tagged_and_versioned`,
  `test_bad_record_does_not_hide_the_rest_of_the_plugin`, `test_staging_index_and_profiles_can_be_refreshed`,
  `tests/test_rules_pfp.py` (the rules file orders Patch for Purists).
