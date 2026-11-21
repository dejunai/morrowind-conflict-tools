# Resume: Morrowind tools, MWManager and the mw* Lua suite (2026-11-21)

Read this first, then `.claude\CLAUDE.md` and the memory index. The user hit their usage limit mid-session;
everything below is committed but **not pushed** (push only when the user asks).

## Where things live
- **Steam root** (`G:\Program Files\Steam\steamapps\common\Morrowind`): the source of the Python tools
  (`mwdialog_*.py`, `vortex_tidy.py`) and the MWSE Lua mods (`Data Files\MWSE\mods\mw*`, lower-case = ours). Not a
  git repo. The mw* Lua files are **Vortex hardlinks** to `G:\Vortex Mods\morrowind\<mod>`: edit in place; a new
  file must be hardlinked into its staging folder (`os.link`).
- **Repo clone** `G:\projects\morrowind-conflict-tools` (branch master, github.com/dejunai/morrowind-conflict-tools).
- **MWManager** `G:\projects\MWManager` (branch main): vendors the Steam files unchanged in its root,
  `tools\steam-upstream\` (COPY_MANIFEST.json) and `reference\mwse-lua-guards\` (SOURCE_MANIFEST.json, LF).
  Never edit vendored files in MWManager directly.
- **Sync** a Steam-root change everywhere: `python -X utf8 mwdialog_backup\sync\sync_upstream.py "<note>" <relative
  paths>` (updates both manifests). Use Write for .py scripts (heredocs mangle backslashes).
- **Tests**: `python -X utf8 -m pytest tests -q -p no:cacheprovider` in each of the three places (Steam ~12 s,
  clone ~9 s, MWManager ~2.5 min). Lua syntax: `tools\luajit\luajit.exe` with `loadfile`. The game can't be run
  from a session: always say what wasn't tested in game.

## Unpushed commits (push both when the user says so)
- MWManager: e8efdf4 (mwcompanions) and the "Commit everything" commit after it. 4a596b1 and earlier are pushed.
- Clone: 8a6a22a (mwcompanions) and the commit after it. be51fec and earlier are pushed.
- Push: `git push -q origin main` (MWManager) / `git push -q origin master` (clone).

## Workstreams and their state
1. **Memory-exhaustion crashes (Steam game).** Suspected: our guards. Every mw* mod now defaults to
   `enabled = false` (`tests\test_guards_default_off.py` enforces it and that each has an Enabled MCM switch).
   The Steam install's saved configs were turned off too; originals in `mwdialog_backup\sync\guard-configs-before\`.
   Next: the user turns them on one at a time in their MCMs to find the culprit. Nothing tested in game yet.
2. **mwcriminal** (one lock/sneak/theft mod replacing Modern Lockpicking, No Accidental Theft, Stealth Overhaul
   tweaks and our glue patches). Built: `Data Files\MWSE\mods\mwcriminal\` (config, core, main, mcm),
   `tests\test_mwcriminal.py`, design and open decisions in `MWCRIMINAL_DESIGN.md` (includes the Shift+activate
   blacklist). Check that file for decisions the user hasn't answered. Not tested in game; the originals stay
   installed until ours matches them.
3. **mwcompanions** (replaces Easy Escort, Attend Me, abot's Smart Companions, with our adjustments). Core
   committed; design in `MWCOMPANIONS_DESIGN.md`. Open question to the user: include Attend Me's command menu
   and recruiting? Not tested in game.
4. **mwcollide offline.** `--fix` deletes the earlier mod's doubled objects in `Cell Fixes.esp`
   (`mwdialog_doubled_deleted.txt`); runs without --fix rebuild the patch when a listed mod leaves. mwcollide's
   runtime hiding is now only a fallback. Not tested in game.
5. **mwfloatfix targeted.** `--cell-conflicts` writes `MWSE\config\mwfloatfix_data.json` (items near a support a
   later mod moved/deleted, on changed LAND, over a replaced mesh); mwfloatfix checks only those. Possible
   follow-up (not started): settle items fully offline (NIF triangle parsing) and drop mwfloatfix.
6. **MWManager per-game state.** `mwmanager_gamestate.py`: answers, rules, cell winners, load orders, FOMOD answers
   belong to one game folder (`mwmanager_state_owner.json`); pointed at another real install (has Morrowind.exe,
   not under %TEMP%) they move to `game_states\<game>\`. Currently owned by `G:\GOG Galaxy\Games\Morrowind`.
   Steam's old conflict blacklist sits in `game_states\imported-from-steam\`. `mwmanager_rules.txt` and the
   conflict blacklist are untracked now (recreated with defaults). Not covered: journal, staging, deployments.
7. **FOMOD option "Requires: <plugin>, Nexus <id>" line** with a Change… picker (`needed_mods.requirement_sources`,
   shipped table `mwmanager_option_requires.json` built by `tools\build_option_requires.py`, cache in
   `outputs\`). Not yet seen on screen. Tamriel_Data.esm resolves to HD (59927); SD users use Change….
8. **Threaded batch** (user's work, reviewed): fixed the tidy-thread hang on a blocked rescan and the companion
   heartbeat line. The rest looked sound.

## Standing rules (from the user)
- Concise, no unrequested extras, no over-engineering; a test per fix that fails without it.
- No fixed Morrowind.exe addresses in Lua; `tes3reference.disabled` is read-only (use :disable()/:enable()).
- `dejespreplacements` is personal: never publish. `mwmanager_non_master_plugin_blacklist.json` local edits are the
  user's; GUI-generated files stay untracked.
- Long pauses: a counter every 20 s when countable, else one "please be patient" line, never a heartbeat timer.
- Splash screens: TGA only, top of `Splash\`; never convert or move them.
- --fix never edits an .esm (changes go into a patch).

## Linked sessions from this conversation (all idle)
- local_e0e2d1e1-22bd-431d-8e0e-89d3ddc5c473: mwcollide offline (done)
- local_920205b9-9167-41ee-9b68-2a8d9e0cb4ed: mwcriminal
- local_3ff89705-46a6-45b9-8d18-8fa2339f4b10: mwfloatfix targeting (done)
- local_719d3b57-4d84-4200-92d6-554fb444f2d6: mwcompanions (waiting on the command-menu question)
