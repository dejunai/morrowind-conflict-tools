# One Off layout for every tool: Off\<plugin>\<reason>\<path>, tidy migrates the older ones, MAX_PATH files are listed, never moved (2026-11-26)

- Decided by dej (dejunai): everything the tools set aside in a staged mod goes to `Off\<plugin>\<reason>\<path relative to the
  mod>`. `docs/OFF-LAYOUT.md` is the spec: `<plugin>` (the mod's first plugin, else its first `.omwscripts` stem as omw2mwse
  names it, else the mod's name; sanitised the converter's way), the fixed list of reasons with a one-line meaning each,
  no nested reasons, collisions (" (2)", folders merge), journal and undo. New shared module `mwdialog_offlayout.py`.
- Reasons renamed to say what they hold: `names` -> `ascii`, `longpaths` -> `shortened paths`, `sound` -> `converted sounds`,
  `textures` -> `converted textures`, `text keys` -> `fixed text keys`, `texture paths` -> `fixed texture paths`,
  `added masters` -> `plugin repairs`, `unused` -> `unused assets`, `orphaned` -> `orphaned animations`,
  `converted` -> `repaired originals`, `Damaged assets` -> `broken`... The migration maps every older spelling (MWManager's too).
- `mwdialog_generated.off_dest`, `backup_asset_original`, the asset check, the sound/text-key/long-path/plugin repairs and tidy
  (broken dummies, normal maps, the hybrid OpenMW move, whole-package moves) all write the new layout; what finds an
  original, a broken file or an unused-assets record also finds the older layouts.
- vortex_tidy plans (one plan, one journal, `--undo` reverses it byte for byte) the migration of loose files in `Off\`,
  `Off\<reason>\<plugin>\`, `Off\OpenMW\<mod>\`, `Off\<path>` and `Off\<name>\...`. Idempotent. Never touches what an
  omw2mwse manifest lists, never touches a folder already in the layout, leaves the unrecognised alone with one NOTE.
- MAX_PATH: a file whose path is over 259 characters, or would be after the move, is never moved (moving it would make it
  worse). `Off\<plugin>\max_path_too_long.txt` lists them, one path per line relative to the mod's folder, deduped,
  refreshed, removed when empty; journaled (`write` ops), `--undo` restores the previous text or removes the file.
- Merging an `Off\OpenMW\<mod>\` package into an existing one merges folders instead of numbering them.
- The OpenMW converter needs Python 3.11+ (omw2mwse 0.2.3 imports `tomllib` in sidecar.py and build.py; no pyproject, no
  machine-readable minimum yet), these tools stay 3.9+: `setup_converter` probes the interpreter that would run it
  (`interpreter_version`: this Python, or a python executable asked for its version; an .exe/.cmd launcher is not judged)
  against `CONVERTER_MIN_PYTHON = (3, 11)`; older = the converter is treated as missing, one WARNING (`needs Python 3.11+,
  but it would run on Python 3.x`), the mod's whole package goes to `Off\\<plugin>\\OpenMW\\`. A `requires-python` in the
  converter's pyproject.toml or a `requiresPython` in its `--json` replaces the constant. Tests: gate, probe, declared minimum,
  JSON field, one warning for several mods, apply + undo.
- Tests: `tests/test_off_layout.py` (reasons, owner rule, every legacy layout, idempotence, undo, collisions, manifest
  protection, the MAX_PATH list, Python 3.9 syntax); expected paths in six older tests updated.

# vortex_tidy: a mod its author excluded from conversion is set aside with a plain WARNING; the tracked blacklist file is removed (2026-11-26)

- A mod whose original author asked to be excluded from mwsuite's conversion utility (omw2mwse 8367f55: it writes
  nothing, not even a manifest, answers verdict `blocked` and exits 0) is treated like any blocked mod: its whole package
  goes to `Off\<plugin name>\OpenMW\` untouched. The one WARNING says, with the mod name, that the original mod author
  has asked that the mod be excluded from mwsuite's conversion utility and to contact them for details. Tidy never shows
  or logs the converter's code, file, line or message for it (not in the plan, the output or the journal).
- Fixed: a `blocked` verdict with nothing written was skipped at `--apply` (it counted as converted and stayed put). Any
  `blocked` entry now moves its package, with or without output to undo. A `reason` of any shape (a dict with missing or
  odd keys, a string, a list, null) and alerts that aren't dicts no longer stop tidy; a missing manifest is fine.
- The tracked `mwdialog_check.conflict.blacklist.txt` at the repo root (Dej's old hand-made list; no tool read it) is
  removed. Nobody gets another person's always-loses picks; the list is the generated one in `generated\`.

# mwdialog_check: no plugin is built into the always-loses list; its header names the file it is in (2026-11-26)

- `OAAB_Saplings.esm` is no longer built in (`CONFLICT_BLACKLIST_BUILTIN` is removed). Nothing is pre-decided for
  anyone: with no `mwdialog_check.conflict.blacklist.txt`, or an empty one, no plugin always loses, and the first
  `[7]` / `[8]` pick writes only the header and that pick. A list you already have is read as it is, `OAAB_Saplings.esm`
  included if it is one of your entries.
- The generated header names the file it is actually written to (`conflict_blacklist_header(path)`), not always
  `mwdialog_check.conflict.blacklist.txt`: MWManager keeps the list in `mwmanager_conflict_blacklist.txt`, and a hand-written
  list converted under any file name gets that name in its header. `CONFLICT_BLACKLIST_HEADER` is gone (use the function).
- Tests: no built-in entry; the header follows the file name (default, MWManager's name, an absolute path).

# docs: README and MORE_INFO cover the last day of work (2026-11-26)

- vortex_tidy: the OpenMW converter (omw2mwse) is described: when it runs (OpenMW-only mods, `hardcode` by default,
  `--convert-omwscripts` / `--no-convert-omwscripts`), the verdict (`blocked` undone at once, `partial` converted with
  a NOTE), the 0.2.3 plugin `placement` / `status` contract (only root plugins on by default, one NOTE for the rest),
  `--undo` of a conversion, the whole-package move to `Off\<plugin name>\OpenMW\` (the entries below dated
  2026-11-25 still name `Off\OpenMW\<mod>\` for it; 193acde moved it), and the cleanup of empty `bugreports\` folders.
  A new README section and a MORE_INFO subsection point to the OpenMW Converter project
  (https://github.com/dejunai/openmw-mwse) as experimental, in early development and private for now, and keep it
  apart from tidy's own `.omwaddon` / `Off\OpenMW\` handling.
- `--cell-conflicts`: the `[7]` / `[8]` "<plugin> always loses" choices, the tool-managed
  `mwdialog_check.conflict.blacklist.txt` (made by the first pick; reading never
  makes it; remove a plugin by hand), and `mwdialog_incompatible_losers.txt` (holds
  while the winner is active, lapses when it is gone).
- `--play`: the lua tools deploy is described by SHA-256 lineage (`generated\mwdialog_lua_manifest.json`, up to 16
  earlier hashes per file), with file times only for content no record knows. It said older / newer by time before.
- luafix: README lists the generic tuning rules (G2, G2S, G8, U1, M1) and the `skipRules` key; MORE_INFO's M1 row
  notes that M1 and G2 share a handler's first line.
- Corrections: mwhangwatch has no Mod Config tab of its own (its settings are on mwguard's Guard & Hang Watch page,
  saved in `mwhangwatch.json`); mwguard's `EnableLogTimestamps` is off by default and has a `logTimestampMode`
  (`wallclock` or `elapsed`); the suite is tested on Python 3.9 and 3.15 (the luafix `lupa` tests on 3.14), not only
  3.15; the empty-`bugreports\` rule (removed when empty and made or emptied during the run; one already empty at the
  start stays).

# luafix's lock check uses its own module copy; two suite tests made deterministic (2026-11-26)

- `mwdialog_luafix.main()` and `find_checker()` each re-imported `mwdialog_paths` inside the function. That resolves
  through `sys.modules` at call time, so when something replaces the module set between import and call (MWManager's
  combined run `pytest tests tools/steam-upstream/tests` swaps and recomposes copies per test folder) luafix got a
  fresh copy of `mwdialog_paths` while the lock was stubbed on, or held by, the copy it was loaded with. The lock
  check itself was already the first thing `main()` does (before `--undo`, before any write), but it asked the wrong
  copy, so a held game lock was not refused and `--undo` printed "Nothing to undo (no journal)." Both local imports
  are gone: luafix uses its module-level `MP`. New test `test_luafix_lock_check_uses_the_module_it_was_loaded_with`
  removes `mwdialog_paths` from `sys.modules` and still expects the refusal.
- `test_fix_refreshes_the_suite_data_from_the_load_order_file_last` read `inspect.getsource(m._main)` and searched the
  text; that goes through `linecache` and the code object's line number, so it returned other text when the file or
  the module set changed after the import (once in about six runs in MWManager). It now parses the module's own file
  with `ast` and checks the order of the calls (multipatch and sound patch before the aux-only cell-conflicts run, on
  `resolve()`'s order) - same assertions, no source-text search.

# vortex_tidy sets an unconverted OpenMW-only mod aside as Off\<plugin name>\OpenMW (2026-11-26)

- The whole-package move (blocked by omw2mwse, conversion failed, converter missing, `--no-convert-omwscripts`)
  now goes to `Off\<plugin name>\OpenMW\`, omw2mwse's own place and name, not `Off\OpenMW\<mod name>\`. The name is
  copied from the converter (`mod_name_for` in 3d372b3): the stem of the first `*.omwscripts` in the package folder
  (pathlib order), everything but letters, digits, `_` and `-` removed, `OpenMWMod` if nothing is left, the folder's
  own name when it has no `.omwscripts`. Example: `Wild Attacks-54448-1-9` holding `wildlife_attacks_npc.omwscripts`
  -> `Off\wildlife_attacks_npc\OpenMW\` (before: `Off\OpenMW\Wild Attacks\`). The root package takes the name of the
  `.omwscripts` at the mod root, else the one in an `OpenMW\` folder, else the package already under
  `Off\<name>\OpenMW\`, so leftovers (`Docs\`, `Screenshots\`, ...) join it. `Docs\` and `Screenshots\` go inside the
  package, so a later omw2mwse run finds it at its canonical place and moves nothing (it used to leave `Docs\` behind).
- Migration: an `Off\OpenMW\<x>\` folder from an earlier tidy run is moved to `Off\<its plugin name>\OpenMW\` in the same
  pass, the emptied folders are removed, and a second run finds nothing to do. Moves and removed folders are
  journaled like any move, so `--undo` restores everything byte for byte, and journals written before the change
  (they only hold source and destination) still undo.
- Hybrids (real MWSE Lua) are unchanged: their OpenMW-specific files still go to `Off\OpenMW\<mod name>\`.
  Tidy's own `Extras\<mod name>\` for other mods is unchanged. A converter-placed `Extras\<plugin>\` is ignored by tidy
  (`Extras` is one of its own folders), listed in the manifest and removed by `--undo`; it cannot collide with
  another mod's `Extras\<mod name>\`, and inside one mod a same-named folder would only share a folder.

# vortex_tidy follows omw2mwse 0.2.3's plugin placement (2026-11-26)

- omw2mwse 3d372b3 replaced the `optional` boolean with `placement` (`root`, `extras`, `off`), `status` (`required`,
  `undetermined`, `obsolete`), `path` and `sourceRel` on each entry of `mods[].plugins[]` (`--json`) and `plugins`
  in `omw2mwse-manifest.json`. Tidy reads them, the JSON first, then the manifest on disk. Only placement `root` is
  enabled by default; `extras` (`Extras\<Mod>\`) and `off` (`Off\<Mod>\OpenMW\`) are never auto-enabled.
- At `--apply`, one NOTE per non-root plugin: where the converter put it and its reason. Dry runs stay quiet.
  Tidy never moves, renames or enables a plugin, and never reads readmes or FOMOD text for this.
- Fallbacks: the 0.2.2 boolean `optional: true` counts as not-root (the earlier NOTE); a manifest with no `plugins`
  key falls back to the scan for root plugins with no `.omwaddon`/`.omwgame` source.
- Converter-placed files in `Extras\<Mod>\` and `Off\<Mod>\OpenMW\` are listed in the manifest, so `--undo`
  removes the copies (each only while its hash matches) and puts the obsolete root plugin back from `Off\`.
  A blocked mod's conversion is undone first, then its whole package goes to tidy's `Off\OpenMW\<mod>\`.
- Folder names differ by design: tidy sets a package aside at `Off\OpenMW\<mod name from the Vortex folder>\` and
  keeps its own files in `Extras\<mod name>\`; omw2mwse uses `Off\<plugin name from the .omwscripts>\OpenMW\` and
  `Extras\<plugin name>\`. The converter accepts tidy's layout and moves the package (the mod's `Docs\` stays
  behind in tidy's folder); `--undo` reverses both steps exactly.

# --cell-conflicts remembers who lost an INCOMPATIBLE choice (2026-11-25)

- The plugin you turn off in an INCOMPATIBLE pair is recorded with the plugin it lost to, in the new
  generated file `mwdialog_incompatible_losers.txt` (`loser<TAB>lost to<TAB>when`; edit by hand to take a line back).
  While the plugin it lost to is still active, the loser is resolved: any other incompatibility it is in
  (Himmelryn against Anthology Solstheim after it lost to The Snow Prince) turns it off again without a question, even
  when a saved answer for that pair picks the other side. When the winner is gone the line lapses and the loser is
  asked about afresh (the existing re-enable of a plugin whose winner is gone is unchanged). It is a record of its
  own, not the always-loses list: that list also makes `--sort` load a plugin early and drops its conflicts, which
  is wrong for a plugin that is turned off. Names compare without regard to case (`.ESP` / `.esp`).

# vortex_tidy reads omw2mwse's optional-plugin flag (2026-11-25)

- omw2mwse 166252b lists every root plugin it emits or leaves in `mods[].plugins[]` (`--json`) and under `plugins` in
  `omw2mwse-manifest.json`: `{name, source, kind, optional, reason}`. Tidy reads the flag (JSON first, then the
  manifest on disk) and prints one NOTE per optional plugin with the converter's reason; a required plugin gets no
  note. Tidy still never enables or renames a converted mod's plugins. Checked against the real converter:
  `wildlife_getfight.esp` is optional and `No Fires in Bad Weather.esp` is not.
- The earlier guess (a root `.esp`/`.esm` with no `.omwaddon` source) is kept only as a fallback for a manifest
  with no `plugins` key. `plugin-rename-clash` handling is unchanged.

# omw2mwse verdicts, Vortex title and author, optional plugins, empty bugreports (2026-11-25)

Follows f31470a (already pushed, so a second commit).

- An OpenMW-only mod that is not converted now has its ENTIRE package moved to `Off\OpenMW\<mod>\` (same relative
  paths): plugins, scripts, `textures\`, `meshes\`, `sound\`, `icons\`, `fonts\`, tidy's own `Docs\` and
  `Screenshots\`, everything. The staging root keeps only `Off\` (and Vortex's `__folder_managed_by_vortex`), so a mod
  that stays enabled in Vortex deploys nothing but `Off\`. This covers: omw2mwse not found, a conversion that fails
  (conflict, refusal, error), a conversion omw2mwse judges `blocked`, and `--no-convert-omwscripts`. An `OpenMW\`
  folder an earlier run made is unpacked there, not nested; omw2mwse's generated output is never moved (it is
  removed). `--undo` puts every file back to its original place from the journal. Hybrids (real MWSE Lua) are
  unchanged: MWSE-first, only their OpenMW-specific files go to `Off\OpenMW\<mod>\`.
- The converter's verdict (`mods[].verdict` in its `--json`) is honoured. `blocked`: it exits 0 and still writes an
  active loader, so tidy does not ship it. The plan lists it up front; at `--apply` the converter output is undone
  straight away from its manifest (nothing is journaled), the whole package is set aside as above, and there is one
  WARNING line (verdict, blocker count, first message). `partial` is converted, with one NOTE.
- `--title` and `--author` are passed to omw2mwse from Vortex's mod info (`modName`, else the logical or custom
  file name; `author`) when Vortex has them (`mwdialog_paths.vortex_mod_info`); no flags otherwise.
- omw2mwse renames `.omwaddon` to `.esp` and `.omwgame` to `.esm` itself and keeps the originals under `Off\`;
  tidy never renames a converted mod's plugins. A plugin the converter flags (`plugin-rename-clash`) or that the
  manifest shows at the mod root with no `Off\...` source is reported in a NOTE and never enabled. This goes by
  the converter's own report and manifest, never by name. The converter has no explicit "optional plugin" flag
  yet: one is needed for plugins such as `wildlife_getfight.esp`.
- `--undo` takes the omw2mwse conversions of a run out first (they were the last thing `--apply` did), then the
  asset repairs, the Lua patches and the moves. Before, a bug report the asset pass had written in a converted
  mod could come back from `Off\` after its repair was undone.
- A `bugreports\` folder is removed at the end of a run (`--apply`, dry run, `--undo`) when it is empty and was
  not there when the run began, so tidy only removes one it made. A folder that was already there stays, empty or
  not. (The converter also sweeps a tidy bug report in a mod root into `Off\<Mod>\OpenMW\bugreports\`, which
  leaves the folder empty.)

# vortex_tidy --undo reverses an omw2mwse conversion (2026-11-25)

- `--apply` journals each conversion with the converter's own report: where the original package was
  (`relocatedFrom`, or `source` when it was not moved), where omw2mwse keeps it (`Off\<Mod>\OpenMW\`), the folder
  and manifest it wrote and the manifest's file list with hashes. The record shares the `--apply` id, so one
  `--undo` undoes the moves, the Lua patches, the asset repairs and the conversions of that run.
- `--undo` puts the original package back from `Off\<Mod>\OpenMW\` at its original paths (a file already there
  with the same content just lets the Off copy go; a different one is kept, with one WARNING line), then deletes
  what omw2mwse wrote, from its manifest (the manifest on disk, else the journaled copy, else whatever carries its
  markers plus `MWSE\config\omwcompat_<Mod>.json`). A generated file whose hash is no longer the manifest's was
  edited: it stays, with one WARNING line, and so does the manifest. Never deleted: a path of the original
  package, anything under the Off package, anything a manifest path points outside the mod folder at, or a
  file the manifest does not list (your own MWSE mods, the game's config). Emptied folders go.
- The shared `MWSE\lib\omwcompat` runtime goes, in every mod it was deferred in, only once no converted mod is
  left in any mod folder of staging or in Data Files (a deployed copy of a mod just undone does not count).
- A second `--undo` finds nothing to do. Checked end to end against the real omw2mwse (a package at the mod root, one
  set aside under `Off\OpenMW\<Mod>\`, both modes, two mods sharing the runtime): the mod folders come back
  byte for byte, folder for folder.

# OpenMW converter output is recognised by its markers; tidy converts OpenMW-only mods (2026-11-25)

- `mwdialog_paths.omw_generated` / `omw_generated_dir`: a folder is omw2mwse output when it holds
  `omw2mwse-manifest.json`, or its `main.lua` has the generated-loader header ("generated by omw2mwse",
  "Generated file: re-run omw2mwse") or requires / registers `omwcompat`; every file in it is too, and so is the
  runtime, `MWSE\lib\omwcompat.lua` and `MWSE\lib\omwcompat\`. Markers, not folder names.
- `--play`: never lists a converted mod under "aren't in lua tools ... Delete them if unwanted", and its prune
  keeps (and reports) a recorded file that is converter output now.
- luafix: never checks or patches converter output or the runtime, also with `--include-own` or when pointed
  straight at the folder or a file in it (not even Known Bugs repairs); the converter fixes them at the source.
- vortex_tidy: `.omwgame` stays at the mod root. OpenMW scripts set aside under `Off\<mod>\OpenMW\` (omw2mwse)
  or `Off\OpenMW\<mod>\` (earlier tidy runs) count, so such an `.omwaddon` is flagged OpenMW-only, not renamed
  `.esp`. In a mod omw2mwse converted, its `.omwaddon` (the converter's copy) is left as it is, with a plan NOTE.
  `Off\` and `MWSE\` were already never moved.
- The unused-asset name scan and the Lua orphan scan also read `.omw` (`main.lua.omw`) and `.omwscripts` files.
- vortex_tidy hands OpenMW-only mods to the converter: a mod with OpenMW scripts (an `*.omwscripts` at its root,
  in `OpenMW\` or set aside under `Off\`) and no real MWSE Lua is converted on `--apply` by
  `omw2mwse --convert-omwscripts=<mode> <mod> --json`, `hardcode` by default (with
  `--accept-hardcode-conversions`), `--convert-omwscripts=normal` for the converter's other mode,
  `--no-convert-omwscripts` for the old move. The converter lays the mod out itself, so nothing else in it moves
  that run; the plan lists `convert with omw2mwse (<mode>)` as an action and a dry-run preview. A conflict
  (exit 4), refusal (3) or error is one WARNING line, the run goes on and the mod stays in the plan. The
  converter is found on PATH or beside these tools (this folder, its `tools\` or the folder above: an
  `omw2mwse(.exe/.cmd/.bat/.py)`, a checkout's `bin\omw2mwse`, or the `omw2mwse` package); not found: one
  WARNING line and the usual `Off\OpenMW\` move.
- Hybrid mods (real MWSE Lua: a `.lua` under `MWSE\` that omw2mwse did not generate) are never converted:
  their OpenMW files go to `Off\OpenMW\<mod>\` as before.

# luafix: generic tuning rules for throttles (2026-11-25)

- `G2S`: a per-frame handler `G2` used to leave at medium (unseen calls or state writes) is gated at high when
  its call closure scans the world every frame (`tes3.rayTest`, `:iterateReferences()`, `tes3.getReference` of
  anything but the player, `tes3.findActorsInProximity`, `tes3.iterateObjects`) and nothing in it is
  frame-critical. Same gate and interval as `G2`, its own id.
- `G8`: a literal `tes3.messageBox` in a handler of an event that fires per hit or per NPC decision is shown at
  most once per `messageInterval` (new key, 10 s). User-action events are left alone; in a per-frame handler it
  is a report.
- `U1`: a per-frame handler that sets the `.text` of a `createLabel` / `createBlock` element to a plain value
  writes it only when it differs.
- `skipRules` (new key): generic rule ids to report but never apply, like `skipKnown` for KB/KP/KR.
- `M1` and `G2` both open a handler with an early return; at `--level medium` the second pass no longer sees the
  gate as missing when the menu-mode return comes first (both are read from the handler's leading guards), so
  such files are no longer rejected. `M1` skips a handler that already returns in menu mode.
- `KP3` wording: Keg Drip refreshes once a second as shipped.

# --play never deploys an older lua tools file over a newer one (2026-11-25)

- A deployed Lua file is only replaced when that isn't a downgrade. Hash lineage decides: the deploy record
  (`generated\mwdialog_lua_manifest.json`) now keeps, per file, the SHA-256s --play deployed before
  (`history`, newest first, up to 16), so a lua tools copy that is a version Data Files already had and moved
  past is left alone. A deployed file whose content no record knows (edited by hand) is dated by modification
  time, as before. Identical files are a no-op; a file never deployed, with nothing newer, deploys as usual.
- Each file left alone gets one warning line naming it and what to do (copy it into lua tools, or delete it so
  --play deploys lua tools' copy), instead of a header and a list.
- `mwdialog_paths`: `downgrade_reason`, `git_blob_ids`, `git_path_history` (the same rule for sync.py's hops,
  against each destination repo's git log).
# Vortex folders found again after Vortex compacts its settings (2026-11-25)

- Vortex's settings (`%APPDATA%\Vortex\state.v2`) are read as the LevelDB they are: sorted tables (`.ldb`, keys
  prefix-compressed, blocks Snappy-compressed) and the write-ahead log, newest entry winning. The old byte search
  only found a key while it happened to be stored whole (in the log, or on a table restart point), so after
  Vortex re-compacted its tables on start-up the runs failed with "Could not determine Vortex's Morrowind
  staging folder". Read-only; a file Vortex holds open is skipped.
- When the settings still can't be read, a folder Vortex's own marker (`__vortex_staging_folder`,
  `__vortex_downloads_folder`) vouches for is used: the one remembered from the last run that resolved
  (`generated\vortex_paths.json`), then Vortex's default location.
- `mwdialog_check` accepts `--staging DIR` (what its error message suggests) as well as `--vortex-dir DIR`.

# luafix: frame-drain and safe-handle patches, fewer false hits (2026-11-25)

- New targeted patches, applied like KB patches by `tidy --lua-only --apply`: `KP1` Attend Me wheel rays once per
  frame, `KP2` Attend Me recruit mode one frame in three, `KP3` Keg Drip mesh names cached, `KP4` G7 Containers
  keeps its linked container as a safe handle; `KR1`-`KR3` safe handles in AURA's fader and Attend Me's timers.
  Report labels `(Known Perf)` / `(Ref Safety)`; `"skipKnown"` lists ids to report but not apply.
- `G6` skips `getReference("player")`; `H2` treats custom events fired only from `loaded` as `loaded`;
  `MWSE\backups\` and switched-off folders are skipped; files nothing names are listed as unreferenced (still
  patched; report-only findings set aside). `RULES_REV` 3.

# MWSE optimizations; Performers Patch removed, mwperformers one performer per inn (2026-11-25)

- `mwperformers` lets one performer per interior perform, whichever mod added it or made it perform (base-game
  bards and converted NPCs included). The pick is random and kept per place on the player; the others' song
  scripts are held through `scriptExecute` (filtered by script), their song is stopped and a performing animation
  goes back to the plain one. Nobody is disabled. Bards an older version hid are shown again on the next visit.
- The Performers Patch is gone: `fix_performers`, `find_double_performers`, `--performers-patch` and
  `--no-performers` (and its `--full` forwarding). `--fix` sets aside a patch an earlier version built
  (`retire_performers_patch`, a backup beside it) and takes it out of the load order.
- luafix: `V1` needs vector evidence and covers `+` / `-`; `H2` exempts timers started in `loaded`; `D1` also
  flags costly work before `e.passes`; new report-only `G6`, `G7`, `R1`, `T1`, `P1`. Rule changes re-analyse cached
  files (`RULES_REV` in the cache key; the patch header version is unchanged).
- Suite: jiubDelay counts only until the delay is reached and caches its global and the Friends & Frens check;
  pandsfixes / Tales handwriting fix return first when `e.passes` is false; mwfloatfix casts at
  `worldObjectRoot` first (whole world only when that can't settle it), reuses one ray parameter table, writes its
  config at a save only when the whitelist grew, and uses `:isValid()`; mwcriminal keeps the keyring container as a
  safe handle; mwhangwatch really unregisters and unwraps when turned off; mwsoundguard caches call sites and
  skips the lookup while off; mwexitguard's keyDown is filtered to F4.

# Lua deployment follows lua tools; MWSE core fixed by KB patch only (2026-11-24)

- `--play` replaces a deployed suite file that is older than, and different from, its `lua tools` copy (the old one
  goes to `backups\lua deploy\<date>\`). A deployed copy newer than `lua tools`' is left alone and listed, since
  edits belong in `lua tools`; files left in `MWSE\mods\mwsuite` that `lua tools` no longer has are listed.
  `MWSE\config\` still only gets missing files.
- `lua tools\MWSE\core\` is gone: MWSE's `ExclusionsPage.lua` is no longer deployed. KB4 is rewritten against
  MWSE's own file (its old fingerprints matched an earlier local edit, not MWSE), applies whole or not at all, and
  together with KB3 turns the stock file into the paged one exactly. `vortex_tidy.py` now also checks the KB-named
  core files in `Data Files\MWSE\core` and patches them in place.

# Install subfolders and Lua deployment (2026-11-23)

- Inside the install: `tools\` holds `texconv.exe` (still also found in the game folder or on PATH), `plans\`
  holds the Tidy and luafix plans, `dummy assets\` the stand-in models and animation, and `lua tools\` the MWSE
  Lua suite (formerly the repo's `Data Files\`). `--play` copies any `lua tools` file missing from `Data Files`
  before starting the game; files already there are left alone.
- Bundled programs (`texconv`, `ffmpeg`, `ffprobe`) are looked up in `tools\` first, then beside the scripts, the
  game folder, and PATH. `--fix` sound repair now finds `tools\ffmpeg.exe`.
- 7-Zip is looked up in `tools\7z\` before PATH.
- `tools\` now ships in the repo with its licenses: texconv (MIT), FFmpeg 9.0.2 + LAME 3.100 (LGPL), 7-Zip (LGPL +
  unRAR), LuaJIT (MIT). Only Tamriel Data's `Translation.txt` stays gitignored.
- Project code is MIT (`LICENSE`).
- `ffmpeg.exe` / `ffprobe.exe` are now our own static audio-only build (about 5 MB each, no DLLs) instead of
  BtbN's 60-library shared build. Its complete source (FFmpeg 9.0.2, LAME 3.100, `build-ffmpeg.sh`) ships in
  `tools\source\`; 7-Zip's 26.02 source archive and the LGPL 2.1 text ship in `tools\7z\`.
- `--no-reduce-textures` / `--no-reduce-splash` (`vortex_tidy.py`, `mwdialog_check.py --asset-check`): keep
  textures and splash screens over 2048 full size; other texture and splash repairs still apply.

# Install folder and backups (2026-11-23)

- The tools install to a subfolder of the game folder (`Morrowind\conflict-tools\`). Without a `Data Files`
  argument, `mwdialog_check.py` (and the `.bat` files, Tidy and luafix) find the game by `Morrowind.ini` in the
  working folder, the folder above it, or above the scripts. Records, plans and journals stay in the game folder;
  bundled programs (`texconv.exe`, `tools\`) are found beside the scripts too.
- Backups go to `conflict-tools\backups\` when the tools are installed in the game folder, else
  `<game folder>\mwdialog_backup\`. The top keeps one backup per file (the newest); making a new one moves the
  older ones to `backups\legacy\`. Morrowind.ini's original and dated copies go to legacy; backups where older
  versions put them are still found by `--restore`, `--restore-all` and `--clean-up`.

# Incompatible plugins and safer rebuilds (2026-11-23)

- Moved-land terrain, winning pathgrids and matching literal script coordinates can require choosing one
  incompatible plugin family; object-only findings remain warnings. Automatic large-scale relocation and
  script recompilation are not performed.
- Conflict choices set aside detected master and exclusive object/script dependents, invalidate affected
  generated patches, and are rechecked if the group changes. Active merges must be undone first.
- `--full` unmerges before restoring disabled plugins and stops before building if an incompatibility remains.
  Fixes, Multipatch builds and merges recheck for incompatibilities, including those exposed by later sorts.
  Unreadable plugins stop the check, existing conflict rules survive mandatory-only reviews, and a failed
  build does not launch a requested `--play`.
- `--unmerge --dry-run` no longer changes plugins, records or the load order and does not run a mutating follow-up.
- Blanked exterior cell names are restored in the responsible .esp; competing nonblank names remain a
  cell-conflict choice. AutoMerge checks cell filters and rejects inputs with mismatched masters.
- Scripts whose last placed target was deleted by Cell Fixes receive a hidden placeholder; merged-input
  diagnostics identify the original plugin.

# Moved land, drowned people, cell filters (2026-11-22; relocation superseded)

- The experimental `--fix` relocation of objects and door arrivals for moved land was later disabled; see the entry above.
- `--fix`: people left over water follow an island a later mod moved, and the footing search reaches further before giving up (`mwdialog_footing.py`).
- `--fix`: a plugin whose dialogue filters on a cell another plugin names loads after it (`mwdialog_cellorder.py`).
- Master check: changes already in the updated master and dead references `--fix` drops are INFO.

# Audit fixes (2026-11-22)

- `--restore-all` backs up what it replaces and removes no backup.
- `--clean-up` keeps the oldest and the newest backup, and all backups of a plugin that isn't installed.
- Repairs and renames keep a copy of an updated original; a failed backup stops the write.
- `--restore-unused` never overwrites a newer file; `--restore-textures` keeps the lines it couldn't restore.
- `--fix` and `--clean` don't write over a plugin that changed since it was read.
- The tools lock the game they work on, with the same lock as MWManager's jobs.
- `--merge` and `--auto-merge` leave no temp file when their check fails; two typos in one response are both fixed.
- luafix offers MWSE Core known-bug fixes on cached runs too.
- mwsaveguard writes every deferred save, leaves look-alike NPCs alone and accepts NUL padding at a save's end.
- mwteleportguard ignores comments and quoted words.
- mwpersonaleffects fills the chest once and empties a stray chest once.

# Tamriel Data renames (2026-11-22)

- `--fix` reads Tamriel Data's rename map from `tools\Translation.txt` only. It is optional.
- `--fix` renames placed objects Tamriel Data renamed, instead of removing them.
- The 64-unit match, the renamed-interior match and the master guard accept an object's current name.
- Rename chains are followed to the first name that exists.

# AFFresh typo, withdrawn cloak patch (2026-11-22)

- `--fix`: AFFresh.esm's "his fried," and "He is true friend of" read "his friend," and "He is a true friend of" through the ESM fixes patch (`TEXT_TYPOS`, exact phrases only).
- mwpluginpatches: the stealth companion cloak patch is withdrawn, as `tes3script:recompile` crashed the game at start.

# Logs and Known Bug 8 (2026-11-22)

- luafix v5: the log shim lets start-up lines through during and after `initialized`, and prints no notice of its own.
- luafix v5: patched mods no longer carry the tool's name; older patches are upgraded on the next run.
- luafix KB8: Tamriel Data waits for a save to finish loading before reading actors' spell lists.
- mwcriminal: detection suppressions are logged to `MWSE\logs\mwcriminal.log`.
- mwexitguard: the settings page is registered, so it appears under MW Conflict Tools.

# Locks, companions, topic (2026-11-22)

- mwcriminal: a picked door stays unlocked, and relocking keeps the door's own level.
- mwcompanions: companions can put their weapon away after a fight.
- mwpluginpatches: Friends & Frens stealth companions don't cloak for a drawn weapon or readied spell.
- `--fix` flips an .esm's reference to the temporary group only if nothing can need it persistent; the Clean_Piran exception list is gone.
- mwpluginpatches: UI Expansion's topic colours wait for the topic list, so travel NPCs' topics don't stay amber.
- mwpluginpatches: vanilla NPCs that Friends & Frens converts keep their generic dialogue.
- mwpluginpatches: `illegible handwriting` is learned again, and goes away when the quest is finished.
- mwpluginpatches: Voices of Vvardenfell's routine console lines can be hidden; that mod's file is not edited.
- mwpluginpatches: vanilla `Sound_Boat_Hull` and `Sound_Water_Spout` scripts start one loop per source with Expanded Sounds active, instead of restarting when the engine reports a non-actor loop as not playing.
- mwpluginpatches: Graphic Herbalism harvested flora now use a suite-owned 1–90 day respawn slider (default 3). The original K archive and live Graphic Herbalism Lua contained no 3-day/30-day direct respawn hardcode, so no third-party Lua restore was required.

# Bards (2026-11-22)

- mwperformers: a bard's script is paused for the length of a dialogue, so no new song starts.
- mwperformers: lute shields are excluded from Weapon Sheathing, so the lute stays in the bard's hands.

# Arrille trapdoor (2026-11-22)

- Removed mwpluginpatches' hardcoded Arrille trapdoor fix: on every cell change it switched back on the
  duplicate that mwfloatfix's blacklist had hidden.
- mwfloatfix's hide key replaces an entry that is already listed instead of refusing it.

# Door-lock compatibility retirement (2026-11-21)

- Removed the mwpluginpatches door-lock workaround and its MCM controls; configure locks and standing key access
  in mwcriminal instead.
- Kept the unrelated Arrille's Tradehouse duplicate-rental-door repair as its own patch, migrating the old
  compatibility switch to its new switch without overriding an existing setting.

# Lua guard memory use (2026-11-21)

- `mwguard` reads only the handler's source lines for profiling hints instead of retaining whole source files.
- `mwinfoloop` releases INFO tracking after each startup topic and between dialogue walks, without changing its
  cycle detection or cache.
- `mwhangwatch` continues tallying all sounds but builds detailed sound log lines only within its configured limit.
  These diagnostics remain optional; actual memory savings depend on the load order and settings.

# [NearStart] / [NearEnd] are [Order] rules too (2026-11-14)

- In your rules file (`mwdialog_check.rules.txt`), a `[NearStart]` or `[NearEnd]` block now also orders its own
  plugins, the way it places them: `[NearStart]` as listed, `[NearEnd]` reversed (its first plugin loads last,
  mlox's convention). A plugin listed there needs no second `[Order]` entry. A block of one plugin orders
  nothing. Wildcards expand as in `[Order]`.
- A step that contradicts a master, an `[Exact]` group or an earlier rule is skipped and reported like any
  `[Order]` step (the plugin still goes to the start / end); an .esm still loads before every .esp. The same
  pair in an `[Order]` block adds nothing (no duplicate). `--update-rules` lists such steps but never cuts a
  `[Near*]` block.
- mlox's own files (`mlox_user.txt`, `mlox_base.txt`) keep mlox's meaning: their `[Near*]` lists are priorities,
  not an order (read as an order they would move `mwse_Containers.esp` after `XE Sky Variations.esp`).
- The [Order]-rule checks of `--cell-conflicts` and `--sort`'s added masters read `[Near*]` blocks the same way.
- New `tests/test_near_order.py`.

# Master check cache: tagged relative paths (2026-11-14)

- `mwdialog_mastercheck_cache.json` stores the fix logs and download archives it names (its `logs` and
  `archives` keys, each copy's `archive`, a verdict's `from_archive`) as `game:` / `staging:` / `downloads:` plus
  a path relative to that folder, like the other records.
- Older absolute entries are still read, so nothing is parsed or unpacked again, and are stored tagged on the
  next check. A path under none of those folders (a `--fix-log` elsewhere) is kept as it is and named once on
  the console. A tag whose folder isn't known on a run (`--no-archive-lookup` without `--vortex-downloads`) is
  left as it is.
- New `tests/test_mastercheck_cache.py`.

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
