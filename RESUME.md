# Resume: Morrowind tools, MWManager and the mw* Lua suite (2026-11-22)

## Suite MCM and MCA follow-up

- Deployed `mwmanagermenu` in Steam and updated MWManager's copy to put suite settings under **MW Conflict Tools**.
  Existing per-mod pages remain nested below the suite tabs. The menu exposes collected templates to MWSE's
  keybind menu, and Effect Inspector, Mouse Guard, Teleport Guard, and Plugin Patches use template registration.
- Absorbed the remaining Plain Paper Fix preference into `mwcriminal` with one-time config migration; archived
  the old standalone source outside `MWSE\mods`. Removed the owned No Accidental Theft book patch and its MCM
  controls; the third-party theft mod remains installed. MWManager archives old Plain Paper Fix installs.
- Audited suite MCM controls for descriptions. MCA 8.2's actual `MCA_setup` script specifies hostile party
  sizes 2-5, 2-10, and 2-20, represented by 0, 1, and 2. Replaced the misleading slider with these options,
  migrated the former invalid value 3, and repaired that value in already initialized saves when MCA AutoStartup
  is enabled. MCA options only apply when MCA initializes; the MCM now states this.
- Changes are synced to the clone and MWManager, including the previous blacklist-window fix.
  Vortex's generated deployment metadata still mentions the removed book-patch file
  until Vortex refreshes it; the deployed and staged patch sources were both removed. No in-game testing.
- The suite and its menu now live under `MWSE\mods\mwsuite`. A highest-priority bootstrap adds that directory
  to Lua's search path, preserving existing imports; metadata keys, mwguard attribution/exemptions, and tidy's
  own-mod handling recognize the nested layout. Other locally maintained mods remain standalone. MWManager archives old flat copies,
  journals the migration, and refuses an upgrade while Vortex still stages old flat suite paths.
- `mwpluginpatches` was moved in both Vortex staging and the live install, preserving hardlinks. The generated
  Vortex deployment manifest still records the old paths until the next deployment; do not edit it manually.
  Redeploy in Vortex and verify the suite and keybinds in game. Originals are in
  `Data Files\MWSE\backups\suite-relocation-20261121`.

Read this first, then `.claude\CLAUDE.md` and the memory index. The user stopped this session near the usage
limit. The own-mod logging continuation below is committed locally and not pushed: clone `565eaa9`, MWManager
`b76b856`. The subsequent Attend Me, KB5, and mod-refactor changes are committed and pushed to both repositories.

## 2026-11-22 continuation: absorb Companion Sneak and extract Personal Effects

- Extracted the Personal Effects runtime from `mwpluginpatches` to standalone `mwpersonaleffects`; its opt-in
  state migrates only when the old patch was enabled. Removed its loader/config/MCM entries and Vortex-staged
  patch source; required ESP records remain.
- Fully absorbed Companion Sneak's detector, inspector UI, settings, hotkey, blacklist, and Attend Me/
  Stealth Overhaul interoperability into `mwcriminal`. Legacy settings and blacklist migrate once; the old
  disabled setting does not enable the new mod. The retired source and metadata are removed; the old config
  stays for migration and compatibility aliases remain.
- Added replacement metadata for `mwcriminal` and `mwpersonaleffects`; removed the retired metadata from both
  manifests and added the new metadata entries to MWManager's reference/source manifests. Updated the suite
  inventory and design/bug docs.
- Focused migration tests passed. Full tests passed in isolation: Steam, clone, and MWManager each
  **495 passed, 25 skipped**. Bundled LuaJIT syntax checks passed for 34 changed Lua files.
- The generated `Data Files\vortex.deployment.json` still records the removed `personalEffectsFix.lua` until
  Vortex refreshes deployment metadata; do not edit that generated file manually. The game was not run.
- Synced, committed, and pushed to `G:\projects\morrowind-conflict-tools` and `G:\projects\MWManager` on
  2026-11-22.

## 2026-11-22 follow-up: visible exit for mwcriminal inspector

- The custom blacklist window put its only Close button in the footer after a proportional-height scroll pane.
  Moved Close into the fixed header in both the blacklist and detector inspector, before scrollable content.
- Added a LuaJIT UI regression test that checks the button is created before the list and that clicking it leaves
  menu mode and destroys the window. The focused `test_mwcriminal.py` passed in Steam, clone, and MWManager
  (**10 passed** each); the edited Lua file passes LuaJIT syntax validation.
- The change is synced to both repositories. It has not yet been tested in-game.

## 2026-11-21 continuation: Attend Me interoperability and MUSE KB5

- `mwcompanions` now recognizes Attend Me forced recruits, respects Attend Me's Wait/Move/Wander state, delegates
  warping when Attend Me's active auto-teleport feature is enabled, and avoids automatic assist overriding its
  commands. Standalone behavior remains covered by regression tests.
- Added Known Bug KB5 for MUSE 2.02's two split `category:createOnOffButton` calls. Fixed luafix's cache key to
  include the Known Bugs fingerprints, so tidy rechecks unchanged files when a repair is added. Tidy applied the
  verified fix to the hard-linked staged/deployed `MWSE\mods\music\MUSE.lua`; both paths now compile with the
  bundled LuaJIT, and a fresh tidy run proposes no patch.
- Synced the companion and KB5 code, tests, and docs to `G:\projects\morrowind-conflict-tools` and
  `G:\projects\MWManager`. Nothing is committed or pushed yet.
- Verification: Steam **491 passed, 25 skipped**; clone **451 passed, 64 skipped, 1 deselected** (the known
  absolute-path policy check); MWManager **583 passed, 4 skipped**. The game was not run.

## 2026-11-21 continuation: own mods use native logging

The user clarified that our mods must be rewritten to work without injected log shims. All 22 names in
`mwdialog_luafix.py:OWN_MODS` are now exempt by default; the Steam `mwguard.json` nested luafix policy lists the
same set. Removed embedded shims from 26 own-mod Lua files and added regression tests that reject both reinjection
and any remaining shim source. Kept native low-frequency and user-triggered messages; aggregated companion/crime
overlap warnings, removed per-popup diagnostics, and reduced Personal Effects clone/unlock logs.

Synced the 26 Lua files and luafix/test changes to the clone and MWManager. Verification: Steam 487 passed / 25
skipped; clone 449 passed / 62 skipped / one known absolute-path test deselected; MWManager 583 passed / 4 skipped.
Luafix's bundled LuaJIT syntax check passed for all 26 edited Lua files. The game was not run.

The continuation is committed locally as clone `565eaa9` and MWManager `b76b856`; neither was pushed. Keep
luafix backups/journals and existing Vortex backup files.

## 2026-11-21 evening handoff (Perplexity): audit fixes, Steam only (historical checkpoint)

State first: the 9fd81f6 / 444c7b9 commits described below as uncommitted were committed **and pushed** at 16:37.
Then `PERPLEXITY_AUDIT.MD` (Steam root) was written and these fixes were made **in the Steam root only**: not yet
synced to the clone or MWManager, not committed. G:\projects was not writable from that session.

- H1 mwguard: no hooks at all when off at start-up (switching on needs a restart); unregistered per-frame
  handlers are released (the wrapper table was never collected under LuaJIT). `tests\test_mwguard.py`.
- H2 + M1 log shim (`SHIM_V = 4`): the flush timer restarts on `loaded`; the lifecycle keep words
  (`LIFECYCLE_PATTERNS`) count only before initialized, near the line start, at most `lifecycleMax` (20) per mod;
  patterns validated once, plain ones matched plain. Two tests in `test_logshim.py`. Installed third-party copies
  still carry v3 until luafix is run again.
- M3 mwcompanions: `downed` keyed by reference id -> safe handle. Test in `test_mwcompanions.py`.
- M4 luafix: backup and journal line fsynced before the in-place write. Test in `test_luafix.py`.
- L1/L2 mwhangwatch (one params table in the now-playing scan; memory level 80 everywhere), `tests\test_mwhangwatch.py`.
  L4 duplicate `import struct` removed from vortex_tidy. L6 `fix_long_names` encodes ids once.
- Correction: mwguard, mwcompanions and mwhangwatch are **not** Vortex hard links (no staging folder); some mw*
  mods are (mwpluginpatches is).
- Verified: Linux full suite has no new failures (the 6 left fail the same on 9fd81f6); on Windows, LuaJIT compiles
  the three changed mods and test_mwguard / test_mwcompanions / test_mwhangwatch pass. pytest isn't reachable
  from the Perplexity sandbox (per-user site-packages), so the full Windows suite hasn't run. Nothing tested in game.

Checkpoint next steps (superseded by the continuation above): run the Steam suite; sync the 11 files
(`sync_upstream.py`); commit both repos locally; decide M2 (shim baked into 10 own mods), L7/L9 (stray
_lumo_*.py, 17 .vortex_backup files); rerun luafix to put shim v4 into third-party mods.

## 2026-11-21 handoff: aggressive Lua logs and Known Bugs (historical checkpoint)

### Completed and synced
- `mwdialog_luafix.py` v4 now applies the log shim to all third-party loggers by default: ordinary/debug spam is
  redirected to `Data Files\MWSE\logs\<plugin>.log`; errors, warnings, tracebacks, and lifecycle lines containing
  register/initialized/started/loaded/ready/version/active still reach `MWSE.log`. Error lines also reach the
  private mod log. Limits: zero initial/ordinary MWSE budget, 25 private lines/s, repeated errors not suppressed.
- Our native-log apps are exempt from the generic shim and use `Data Files\MWSE\logs`; `mwhangwatch` was moved
  there. No own literal logger writes a `.log` in the Morrowind root. `mwguard.json` has the matching local policy.
- Nil repairs A1-A5 are more aggressive (and/or guards, local/table values, generic-for statement guards), while
  ambiguous direct lookup expressions remain reports. `--include-own` remains restricted to A1-A5/F1.
- Exact non-hookable repairs are now `(Known Bugs) KB<n>: <owner>: <description>`:
  - KB1 AttendMeMWSE stale deleted-reference `.mobile` access.
  - KB2 UI Expansion's empty cached-info property key.
  - KB3 MWSE Core ExclusionsPage dereference after destroying `outerContainer`.
  - KB4 MWSE Core ExclusionsPage unbounded native object UI.
- Core remains excluded from general scanning. Only exact named `KNOWN_BUGS` file/text fingerprints can authorize
  a core edit. Default luafix runs explicitly include those core paths.
- KB4 is installed in `Data Files\MWSE\core\mcm\components\pages\ExclusionsPage.lua`: strict 100-item pages per
  column, Previous/Next buttons, page/total/item count, page clamping, and page reset on search/filter changes.
  Bulk toggles still operate on the complete logical list. `LUA_MOD_BUGS.md` section 39 documents it and explains
  why the core mod list/dropdown were audited but not changed without a reproduced failure.
- Luafix produces `mwdialog_luafix_known_bugs.txt` on direct runs and `vortex_tidy` writes author-facing per-mod
  `bugreports\*.bugreport.txt` sections for KB findings, with DETECTED/PATCHED/NOT PATCHED status.
- The Lua guidance now uses the correct `MWSE\logs\mwhangwatch.log` path and portable Vortex staging examples.
- Installed third-party copies were already repaired. AttendMe's old marker was normalized from `K1` to `KB1` in
  Steam/Vortex. A clean targeted core scan reported no vulnerable KB fingerprint.

### Verification checkpoint
- Steam full suite after KB4/reporting: **478 passed, 23 skipped**.
- Standalone clone: **443 passed, 57 skipped; one failure** in `test_no_absolute_paths_in_repo_code`. Two new
  absolute Vortex examples in the guidance were fixed and re-synced after that run; `RESUME.md` still contains
  intentional machine paths and was the pre-existing reason to exclude this one policy test.
- MWManager final suite was manually stopped at 49% with no failure printed because the user requested a handoff.
  The immediately preceding pre-KB4 MWManager run was **583 passed, 4 skipped**. Rerun it.
- LuaJIT `loadfile` accepts the paged ExclusionsPage. KB4's test reconstructs the vulnerable source from its exact
  fingerprints, repairs it, and confirms paging is restored.
- Nothing was tested in game.

### Exact next steps at that checkpoint (superseded by the continuation above)
1. Inspect `git status` in `G:\projects\morrowind-conflict-tools` and `G:\projects\MWManager`; all current changes
   are intentional synced work, including newly tracked Lua guidance and MWSE core ExclusionsPage. Do not discard
   the earlier mw* logging/nil changes. `mwdialog_luafix_known_bugs.txt` is generated output in the clone; decide
   whether to ignore it rather than commit it.
2. Rerun clone tests excluding only the known RESUME absolute-path policy case, and rerun the complete MWManager
   suite. Steam is already clean.
3. Run default `python -X utf8 mwdialog_luafix.py --no-cache --lua-log all` once if a fresh full plan is wanted;
   the present Steam plan file was last generated for the single core file and has zero actions.
4. Commit both repositories locally with no push. The previous logging work and KB4/reporting belong in the same
   checkpoint unless a small split is obviously cleaner.

## Where things live
- **Steam root** (`G:\Program Files\Steam\steamapps\common\Morrowind`): the source of the Python tools
  (`mwdialog_*.py`, `vortex_tidy.py`) and the MWSE Lua mods (`Data Files\MWSE\mods\mw*`, lower-case = ours). Not a
  git repo. Some mw* Lua files are Vortex hardlinks to `G:\Vortex Mods\morrowind\<mod>`; others are independent
  copies. Verify before relying on propagation. `mwcompanions` and `mwguard` are not hardlinks; hardlink a new
  staged file only when its mod uses hardlinks.
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
- MWManager: `b76b856` (native own-mod logging), plus `e8efdf4` and earlier local checkpoint commits.
- Clone: `565eaa9` (native own-mod logging), plus `8a6a22a` and earlier local checkpoint commits.
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
3. **mwcompanions** (replaces Easy Escort, Attend Me, abot's Smart Companions, with our adjustments). Optional
   Attend Me follower recognition, command-respecting behavior, and warp delegation are implemented; see
   `MWCOMPANIONS_DESIGN.md`. Not tested in game.
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
