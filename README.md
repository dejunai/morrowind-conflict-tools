# Morrowind Conflict Tools

A comprehensive, automated maintenance and conflict resolution suite for **The Elder Scrolls III: Morrowind**. Built entirely in Python (standard library only), this toolset handles deep plugin conflict resolution, dirty record cleaning, cell and dialogue repair, load-order sorting, asset validation and optimization, and AST-level MWSE Lua hardening.

The suite is engineered for massive, complex mod lists (hundreds of plugins, tens of thousands of assets) and provides two primary automated workflows:
1. **`vortex_tidy.py`** - Staging-level mod directory sanitizer, file structure organizer, asset validator, and Lua patcher.
2. **`mwdialog_check.py`** - Game-level plugin validator, dialogue fixer, cell conflict resolver, automated patch builder (AutoMerge, Multipatch, SoundFix), and mlox-compatible load-order sorter.

> [!IMPORTANT]
> **Detailed Function Architecture & Empirical Fix Catalog**:
> For the architecture of the Python modules in the package, command-line switches, and empirical fix examples from the historical fix archives, consult **[MORE_INFO.md](docs/MORE_INFO.md)**.

## Install (beta)

New to all this? The **[Quick Start guide](docs/QUICK_START.md)** walks through it in plain words.

1. Install [Python](https://www.python.org/downloads/windows/) 3.9 or newer (tick "Add python.exe to PATH").
2. Download the `conflict-tools-<version>.zip` asset from the GitHub Releases page (not "Source code", and not "Code > Download ZIP", which holds the developer files too).
3. Unzip it into your Morrowind folder, so you get `Morrowind\conflict-tools\` beside `Morrowind.exe`.
4. Double-click `conflict-tools\mwdialog_check.bat`. It only reads: it writes a report and opens it in Notepad. Nothing in your game changes until you run a fix switch.
5. To play, double-click `conflict-tools\Play Morrowind.bat` (or copy it into the Morrowind folder).

Vortex is optional: without it the tools scan `Data Files` only. Mod Organizer 2 is not supported (its mods are not in `Data Files`).

---

## Table of Contents

- [Install (beta)](#install-beta)

- [Core Tools Overview](#core-tools-overview)
  - [vortex_tidy.py - Mod Staging Sanitizer & Pipeline](#vortex_tidypy---mod-staging-sanitizer--pipeline)
  - [mwdialog_check.py - Plugin Analysis & Conflict Engine](#mwdialog_checkpy---plugin-analysis--conflict-engine)
- [Command-Line Switch Reference](#command-line-switch-reference)
  - [vortex_tidy Switches](#vortex_tidy-switches)
  - [mwdialog_check Switches](#mwdialog_check-switches)
  - [mwdialog_luafix Switches](#mwdialog_luafix-switches)
  - [Exit Codes & Environment Variables](#exit-codes--environment-variables)
- [The Plan-Then-Apply Workflow](#the-plan-then-apply-workflow)
- [Load Order & Starting the Game](#load-order--starting-the-game)
- [Key Architectural Features](#key-architectural-features)
  - [Dialogue & INFO Chain Healing](#dialogue--info-chain-healing)
  - [Cell Conflicts & Footing Rescue](#cell-conflicts--footing-rescue)
  - [AutoMerge & Multipatch](#automerge--multipatch)
  - [Audio Script Recompilation (--soundfix)](#audio-script-recompilation---soundfix)
  - [MWSE Lua AST Analysis & KnownBugs](#mwse-lua-ast-analysis--knownbugs)
- [MWSE Suite (CR-18)](#mwse-suite-cr-18)
- [OpenMW Converter (experimental)](#openmw-converter-experimental)
- [Installation & Directory Layout](#installation--directory-layout)
- [Requirements & Bundled Binaries](#requirements--bundled-binaries)
- [Developer Tools (repository only)](#developer-tools-repository-only)
  - [deploy.py](#deploypy)
  - [doc_scan.py](#doc_scanpy)
  - [sync.py](#syncpy)
  - [release.py](#releasepy)
  - [tes3diff.py](#tes3diffpy)
- [License](#license)

---

## Core Tools Overview

### vortex_tidy.py - Mod Staging Sanitizer & Pipeline

`vortex_tidy.py` inspects and cleans each individual mod folder inside Vortex's Morrowind staging directory (read directly from Vortex's configuration state, or specified via `--staging`). It ensures that mods deployed to `Data Files` are properly structured, free of stray junk files, and statically verified:

1. **Folder & Hierarchy Normalization**:
   - Leaves alone any mod that installs into the game folder instead of `Data Files` (an `.exe`, `.dll` or `.asi`, or a `Data Files` folder, at its root, like MGE XE), and every mod on the blacklist: `Morrowind Code Patch*`, `MCP beta*` and `NIFZER0EDIT*` are built in. If `vortex_tidy_blacklist.txt` is missing it is created with those patterns plus `*Breezify*`; an existing file is never overwritten or added to. Add further folder-name patterns one per line (wildcards allowed).
   - Keeps game folders (`Meshes`, `Textures`, `Icons`, `Sound`, `Music`, `BookArt`, `Splash`, `Fonts`, `Video`, `DistantLand`), support folders (`MWSE`, `MGE3`, `Shaders`, `Grass`, `MCPatch`), plugins (`.esp`, `.esm`, `.omwaddon`), `.bsa` archives, MWSE `*-metadata.toml` files and `<plugin>.bugreport.txt` where they are. `Extras\` and `bugreports\` are never moved or looked inside. Each mod's `Off\` folder follows one layout, `Off\<plugin>\<reason>\<path>` (see `docs/dev/OFF-LAYOUT.md`): tidy moves older layouts in it into that one (journaled, `--undo` reverses it) and never moves a file whose path is over MAX_PATH; those are listed in `Off\<plugin>\max_path_too_long.txt`.
   - Moves documentation files (`.txt`, `.md`, `.pdf`, `.html`, `.htm`, `.doc`, `.docx`, `.odt`, `.rtf`, `.nfo`) at the mod root into `Docs\`, renamed `<mod name> - <file>` so one mod's `readme.txt` cannot overwrite another's when deployed. Documents already in `Docs\` that do not already name the mod get the same prefix.
   - Moves root image previews (`.jpg`, `.png`, `.gif`, `.bmp`, `.webp`) into `Screenshots\`, renamed the same way.
   - A root folder holding a mod's readme (named after the mod or one of its plugins, or holding nothing but documents) becomes part of `Docs\`; anything in it that is not a document goes to `Extras\`. Everything else at the root that is not game data (FOMOD option folders, `meta.ini`, `.bak` files...) goes to `Extras\<mod name>\`, where `<mod name>` is the folder name without Vortex's Nexus id, version and download stamp.
   - Moves MGE XE grass plugins (only statics, activators and cells, mostly grass) into `Grass\`, where MGE XE's distant land generator reads them; the game never loads them.
   - Moves the OpenMW-specific files of a mod that also has MWSE Lua (`*.omwscripts` and the `scripts`, `l10n`, `animations` and `playlists` folders, plus an `OpenMW\` folder an earlier run made) to `Off\<plugin>\OpenMW\`: the MWSE side is the one that is used. An `.omwaddon` with no `.esp`/`.esm` beside it is renamed `.esp` when the mod has no OpenMW scripts; with scripts, the plan flags it, and `--apply` stops at it, offers to open its folder, and offers to delete the mod (moved to `<staging> - deleted by vortex_tidy` beside the staging folder, so `--undo` can bring it back).
   - **OpenMW-only mods** (OpenMW scripts and no MWSE Lua of their own): an optional, and very experimental, OpenMW-to-MWSE converter is being developed separately. It is not released, not included and not needed. Tidy is prepared for it: if/when it is found (on PATH, or beside these tools), `--apply` converts such a mod in its staged folder only (never in Data Files), the plan shows a preview first, and `--undo` reverses the conversion. `--convert-omwscripts=hardcode` picks the converter's other mode (hard-coded values become MCM settings) and `--no-convert-omwscripts` turns conversion off. A conversion that is blocked or fails writes nothing: one WARNING line, and the mod is set aside as below. A mod whose original author has asked to be excluded from conversion is set aside too, and the WARNING tells you to contact the original mod author. Tidy never renames, moves or enables a converted mod's plugins. See [OpenMW Converter](#openmw-converter-experimental).
   - **OpenMW-only mods that are not converted** (no converter found, a failed or blocked conversion, or `--no-convert-omwscripts`) move as one whole package to `Off\<plugin name>\OpenMW\` (the stem of the mod's first `.omwscripts`; for example `Off\wildlife_attacks_npc\OpenMW\`): plugins, scripts, data folders (`textures\`, `meshes\`, `sound\`...) and tidy's `Docs\` and `Screenshots\`. The mod folder keeps only `Off\` (and Vortex's marker file), so a mod still enabled in Vortex deploys nothing else. Without the converter the plan has one NOTE line. Nothing is lost: every tidy run looks at set-aside packages again, so the first run after the converter is found offers to convert them. A converter that needs a newer Python than the one that would run it counts as not found (one WARNING). A package an older tidy run set aside at `Off\OpenMW\<mod name>\` is moved to the new place (merged with what is there) on the next run.
   - A mod's `bugreports\` folder is made when a bug report is written, and can be left empty when a report is deleted again. At the end of every run (`--apply`, a dry run or `--undo`), tidy removes a `bugreports\` folder that is empty and that it made or emptied during the run; one that was already empty when the run began, or that has anything in it, stays.
   - Moves OpenMW-only normal maps (`*_n` / `*_nm` / `*_normal` / `*_nrm`) whose diffuse texture exists to `Off\<plugin>\normal maps\`, so they are not deployed to vanilla Morrowind with MGE XE.
2. **Asset Sanitization & Optimization**:
   - Inspects DDS textures for corrupt headers, missing mipmaps, unsupported formats, and uncompressed RGBA.
   - Automatically generates missing mipmaps using bundled `texconv`.
   - Broken files it can't repair (empty, not the format their name says, truncated, a model the game crashes on, an MP3 with no audio) go to `<mod>\Off\broken\<plugin>\<path>` and a small valid dummy of the same type takes their place (made in code for textures, icons and sounds; a model gets the game's Dwemer coin from `Morrowind.bsa` so the gap is easy to spot, or with `--no-coins` an empty, invisible model made in code, which is also used, and the plan says so, when the coin isn't found (that fallback also prints a one-time warning that the core game files have been altered, at the end of the output and of the plan; it never blocks, and tells you to restore the shipped files); other types copied from a core game file), marked by `<original>.tidy-dummy` so later runs leave it alone. A crashing model another copy exists for is only moved out, so the good copy wins. `--undo` puts the original back.
   - Downsamples textures and splash screens exceeding 2048x2048 down to 2048 (preserving full size if `--no-reduce-textures` or `--no-reduce-splash` is passed). Splash screens are still made 24-bit RLE TGA.
3. **MWSE Lua AST Static Analysis & In-Place Hardening**:
   - Runs `mwdialog_luafix.py` against the MWSE Lua files of every staged mod (and the core files a KnownBugs rule names when a staged mod ships MWSE itself). Tidy works only on staged files: `--staging` (and every staging folder an `--undo` journal names) is refused, with exit code `2` and nothing written, when it is Data Files, the game folder, or inside either, comparing real paths (symlinks and junctions followed, case ignored); the converter handoff refuses the same targets. Only MWManager's initial tidy (its init mode: the core install, which is never staged) may act on Data Files. Nothing in Data Files is read or written before deploy, except reading the base game's archives and masters and `MWSE\config\mwguard.json`. A write over a staged file replaces it, so a Vortex hard link is broken, never written through: Data Files keeps the old file until Vortex deploys again. The MWSE core files in Data Files (`Data Files\MWSE\core\...`, which MWSE's updater writes there) are left to the deploy step, `mwdialog_luafix.py --core-only`.
   - Parses code into a full Abstract Syntax Tree (AST) using a pure-Python Lua 5.1/LuaJIT parser.
   - Injects nil-guards, compresses absurd event priorities, adds a log shim that sends a spamming mod's lines past its allowance to its own `MWSE\logs\<mod>.log`, and applies targeted patches for KnownBugs where no general rule applies (KB1-KB50 and KB52 minus the retired and removed ones; there is no KB18).
4. **Strict Safety**:
   - Implements a strict two-stage **Plan-then-Apply** execution model (`plans\vortex_tidy_plan.txt`): `--apply` works the plan out again and refuses, changing nothing, when its actions differ from the plan you reviewed.
   - A Lua file whose content hash changed since it was checked is not patched, and a patched file is only written when LuaJIT (or luac) compiles it.
   - Moves, Lua patches and asset repairs are journaled (`generated\vortex_tidy_journal.jsonl`). Before a mod's files are repaired, every file the repairs can change (the file, same-named files beside it, the mod's plugins and bug reports) is copied to `backups\tidy\<run>\assets\<mod>\` and journaled with its SHA-256; a mod whose originals can't be kept is not repaired. `--undo` reverts the whole last `--apply`: each asset original goes back to its own path (written in place, so Vortex hard links and plugin dates survive) and the files the repairs made are deleted (repaired copies under new names, the mod's `Off\` copies, a new bug report); then the Lua patches, then the moves. It does not reverse a repair; it brings back the file as it was. Run it again to revert the `--apply` before that. A missing or altered original, or a file changed since the `--apply`, stops `--undo` before anything changes; `--force` overwrites changed files, but only with an original whose hash matches. The `vortex_tidy` sections `lua_apply` writes into bug reports are not undone.
   - Deploy in Vortex after `--apply` or `--undo`, so the game folder matches (Vortex removes the files that moved on that Deploy). Purging before `--apply` is good practice, but not needed.

### mwdialog_check.py - Plugin Analysis & Conflict Engine

`mwdialog_check.py` is the primary conflict resolution, cleaning, and patching powerhouse. Operating on the active load order and `Data Files`, it can run individual targeted repairs or an all-in-one automated pipeline (`--full`):

1. **Plugin Cleaning & Sanitization (`--clean`, `--fix`)**:
   - Cleans dirty records, evil GMSTs (e.g. `sTeleportDisabled`), duplicate object instances, and identical-to-master (ITM) junk cells (such as empty `ToddTest` cells).
   - Resolves references pointing to deleted records, fixes misplaced exterior cell copies, and repairs out-of-order `XSCL` subrecords.
   - `.esm` master files are never rewritten. Master issues are written into `mwdialog_check - ESM fixes.esp`. `--patch-esm` is an older alias of `--fix` (kept for older batch notes).
2. **Dialogue & INFO Chain Repair (`--fix`)**:
   - Scans all `DIAL` topics and `INFO` responses across the active plugin graph.
   - Detects and repairs broken `PNAM` (previous response) chains, infinite circular dialogue loops, and orphaned responses that freeze the game.
   - Replaces missing sound files referenced in dialogue with valid silent placeholders or removes broken speech pointers.
3. **Cell Conflicts & Land Movement (`--cell-conflicts`)**:
   - Identifies overlapping edits across exterior and interior cells.
   - Resolves conflicting exterior cell names.
   - Detects moved land and incompatible landscape overhauls (e.g. Anthology Solstheim vs. Tomb of the Snow Prince), giving the user clear interactive choices to disable incompatible plugin trees.
   - For an ordinary conflict between two plugins, besides keeping one winner or turning one off, you can choose `[7]` or `[8]`: `<plugin> always loses`. That plugin goes onto `generated\mwdialog_check.conflict.blacklist.txt` at once (the file is made by the first such pick; no plugin is on the list until you choose one): later `--cell-conflicts` runs leave it out and `--sort` loads it early, so every other mod wins. Pairs flagged INCOMPATIBLE don't get these two choices (one side has to be turned off). The list is tool-managed; to take a plugin off it, delete its line by hand.
   - When you turn off one side of an INCOMPATIBLE pair, the loss is recorded in `generated\mwdialog_incompatible_losers.txt` (loser, what it lost to, when). While the winner is still active, the loser stays off in every other incompatibility it is in, without asking again; when the winner is gone, the record lapses and the plugin is judged afresh. Delete a line to take it back.
4. **NIF Raycasting & Footing Rescue (`mwdialog_footing.py`)**:
   - Solves the classic 'drowned NPC' problem: when a later mod alters coastline terrain or removes a dock, NPCs left standing over open water are detected via 3D raycasting against NIF collision meshes (`RootCollisionNode`) and LAND heights.
   - Moves stranded actors to the nearest stable, dry footing or relocates them to matching moved land. This runs as part of `--fix` (`fix_cell_winners`).
5. **Automated Patch Generation**:
   - **AutoMerge (`--auto-merge`)**: Finds active `.esp` plugins with no cell, land, or pathgrid edits that can move together without changing what wins against any other plugin, merges them into `mwdialog_check AutoMerge.esp` (or `--merge-name`), and deactivates the inputs.
   - **Multipatch (`--multipatch`)**: Builds `mwdialog_check Multipatch.esp` like tes3cmd multipatch: merged leveled lists, fog-bugged cells (illegal fog density 0 is set to 0.01), and reverted cell names, plus objects several mods change, merged field by field, unless `--no-merge-objects` is passed. Beast-race NPCs (the winning race record's beast flag) with no model or a humanoid skeleton (`base_anim.nif`, `base_anim_female.nif`) get the beast skeleton `base_animkna.nif`, and those with a mod's pose model that lacks the beast bones (toes, tail) get a copy of the pose with them grafted, unless `--no-beast-skeleton`. Load it last.
   - **Doubled performers**: no plugin is built for them. The `mwperformers` MWSE module lets one performer per inn perform, in the game, and removes no one; it works only in the interiors `mwperformers_data.json` lists (each interior with performers placed in it, written with the other suite data). A `mwdialog_check Performers Patch.esp` left by an earlier version is set aside (kept as a backup) and taken out of the load order by `--fix`.
   - **SoundFix**: Recompiles problematic audio scripts using `MWRecompile` into `mwdialog_check - MWSoundFix.esp`, replacing broken `GetSoundPlaying` polling loops with state variables. `--fix` rebuilds this patch unless `--no-soundfix` is passed. `--soundfix` runs that step on its own.
6. **Load-Order Sorter (`--sort`)**:
   - Built-in mlox-compatible topological sorter (implemented in `mwdialog_check.py`; `mwdialog_loadorder.py` parses rules and stores the order).
   - Evaluates custom rules from `generated\mwdialog_check.rules.txt` (`[Order]`, `[NearStart]`, `[NearEnd]`, `[Exact]`; `--sort` keeps a `[Context]` section there itself), then mlox's `mlox\mlox_user.txt` and `mlox\mlox_base.txt` in the game folder. A rule that contradicts an earlier one is skipped.
   - Automatically adds patch-after-mod rules and dialogue cell-filter rules (`mwdialog_cellorder.py`) unless `--no-content-order` is passed.
   - The intended order is written to `generated\mwdialog_load_order.txt` and plugin dates are set one day apart from 2000-01-01. Any run that changed that list writes it into `Morrowind.ini`'s `[Game Files]` when it ends normally, and `--play` writes it again before starting the game (Vortex's rewrite of that section can be cut at Windows' 32,767-character limit). See [Load Order & Starting the Game](#load-order--starting-the-game).
7. **Asset Integrity Check (`--asset-check`)**:
   - Verifies all model, texture, and sound references in active plugins against loose files and loaded BSA archives (`mwdialog_bsa.py`).
   - Generates stand-in dummy assets for missing meshes or textures to prevent game crashes.

---

## Command-Line Switch Reference

### vortex_tidy Switches

| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--version` | *(flag)* | Print the package version and exit. |
| *(default)* | *(none)* | Generates a preview plan in `plans\vortex_tidy_plan.txt` without modifying files. |
| `--staging` | `<PATH>` | Explicit path to Vortex's Morrowind staging folder. Overrides automatic Vortex detection. |
| `--only` | `<PATTERN ...>` | Restricts tidying only to specified mod staging folder names (wildcards allowed). |
| `--skip` | `<PATTERN ...>` | Skips specified mod staging folder names this run. To always skip one, add it to `vortex_tidy_blacklist.txt` (created with the built-in patterns and `*Breezify*` if missing; an existing file is never overwritten). |
| `--apply` | *(flag)* | Enacts the reviewed plan in `plans\vortex_tidy_plan.txt`. Refuses if the plan was modified or is out of date. |
| `--yes` | *(flag)* | With `--apply`: don't ask first. |
| `--undo` | *(flag)* | Reverts the whole last `--apply` from the journal: original asset files back at their own paths (files the repairs made deleted), Lua patches, then moves. Again: the `--apply` before that. Stops, changing nothing, when an original is missing or altered or a file changed since. It also reverses conversions made by the optional OpenMW converter: the files it wrote are deleted (one you edited since stays, with a warning), the original package goes back to its own paths, and the converter's shared runtime goes only when no converted mod is left. |
| `--force` | *(flag)* | With `--undo`: overwrite files changed since the `--apply` (only with an original whose hash matches). |
| `--no-assets` | *(flag)* | Skips the asset check of each mod's files. |
| `--no-lua` | *(flag)* | Skips the Lua check (`mwdialog_luafix`). |
| `--lua-only` | *(flag)* | Only the Lua check: no moves, no asset check. |
| `--lua-level` | `high` / `medium` | Which Lua findings `--apply` patches (default `high`). |
| `--luajit` | `<PATH>` | Path to the LuaJIT or luac binary the Lua check compiles with. |
| `--lua-log` | `flagged` / `all` / `off` | Which mods the Lua check gives the log shim: `flagged` (default), `all`, or `off`. |
| `--no-reduce-textures` | *(flag)* | Prevents downscaling of textures larger than 2048x2048. |
| `--no-reduce-splash` | *(flag)* | Prevents downscaling of splash screens wider than 2048 (they are still made 24-bit RLE TGA). |
| `--no-coins` | *(flag)* | A broken or missing model gets an empty, invisible model (made in code) instead of the default Dwemer coin from `Morrowind.bsa`. Use the same setting for the plan and `--apply`: the plan line names the kind. Dummies already in place are left alone either way. |
| `--convert-omwscripts` | `normal` / `hardcode` | OpenMW-only mods (OpenMW scripts, no MWSE Lua) are converted for MWSE if/when the optional, very experimental OpenMW converter (in development, not included) is found on PATH or beside these tools. Default and bare flag: `normal`; `--convert-omwscripts=hardcode` picks its other mode (hard-coded values become MCM settings). Converter not found: one note, and the mod is set aside whole in `Off\<plugin name>\OpenMW\`, where later runs look at it again. |
| `--no-convert-omwscripts` | *(flag)* | Don't convert: OpenMW-only mods get their whole package moved to `Off\<plugin name>\OpenMW\`. |
| `--pack-report` | *(flag)* | For a bug report: copies `MWSE.log`, `Data Files\MWSE\logs\` and `conflict-tools\generated\` (only those; a missing one is noted in the summary), replaces your folders with `<MORROWIND>`, `<STAGING>`, `<DOWNLOADS>` and `<USERPROFILE>` (longest match first, either slash style, doubled backslashes, any case) and your Windows user name with `<USERNAME>` in the copies, and packs them with `scrub-summary.txt` (replacements per file, and what was skipped or excluded, no contents) into `conflict-tools\reports\conflict-tools-report-YYYYMMDD-HHMMSS.zip`. Prints that path as one line; no 7-Zip: an error and a non-zero exit. Read-only on the game: files are copied, never changed, moved or deleted, and nothing is written to Data Files. Binary files (an SQLite cache, anything with a NUL byte or a binary extension, UTF-16 text) are left out and listed, not scrubbed. Stands alone: not with `--apply`, `--undo` or `--lua-only`. |
| `--after-mwse-update` | `<EXIT_CODE>` | For a caller that just ran `MWSE-Update.exe` (MWManager; these tools never start it): the updater's exit code. On a successful update (exit code `0` and `<game>\mwse-version.txt` present and different from `--mwse-version-before`), only the MWSE core Known Bugs patches are re-applied (`mwdialog_luafix.py --core-only`: a dry run first, then apply, with luafix's usual backup and journal). No staged tidy run and no other tidy function. `Morrowind.exe` must be closed (nothing is killed); if it is running, the hook refuses with a non-zero exit and writes nothing. A failed updater or no update skips the hook and exits `0`. In Python: `vortex_tidy.tidy_after_mwse_update(returncode, version_before)`. |
| `--mwse-version-before` | `<TEXT>` | With `--after-mwse-update`: `mwse-version.txt` as it was before the updater ran (empty for a fresh install). |

---

### mwdialog_check Switches

#### Pipeline & High-Level Execution
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--version` | *(flag)* | Print the package version and exit. |
| *(default)* | `[DATA_DIR]` | Runs non-destructive validation on active plugins and outputs conflict reports. |
| `--full` | *(flag)* | Starts from scratch. Aborts (exit 2) if a plugin's master is missing from Data Files. Replays the answers remembered in `mwdialog_conflict_answers.json` unless `--fresh-answers`. Then: undo the auto-merge (when there is one); turn back on what earlier runs turned off (and drop their conflict rules, rebuilt-interior choices and asset stand-ins); `--add-all-esp` if given; turn off redundant plugins (asking in a console; `--no-redundant` skips it); a cell-conflicts report (asking only hard incompatibilities); sort; set the old Multipatch aside; clean and fix with the asset check, no Multipatch yet (footing and SoundFix run as part of `--fix`); sort again; stop and open `mwdialog_report.txt` if any ERROR remains; otherwise AutoMerge, sort, `--all`, sort again; stop again on ERROR; then offer interactive `--cell-conflicts`. `--yes`: no questions; `--add-all-esp`: add every plugin first; `--play`: start the game at the end. With `--preserve-saves=strict` there is no reset, unmerge or redundant step, and the steps it runs hold back what `strict` holds back (the auto-merge is kept as it is); `--preserve-saves` / `basic` is passed on to every step. Prints a per-step summary; exit 2 when a step fails or an ERROR stops it. A bare `--full` (not `--dry-run`, no `--preserve-saves`) that finds `.ess` saves in the game's `Saves` folder asks `[y/N]` first (it rewrites plugins and the load order; mid-playthrough use `--preserve-saves=strict`). `--yes` skips the question; with no console and no `--yes` it refuses and changes nothing. |
| `--all` | *(flag)* | `--clean`, then `--fix`, then `--multipatch`. |
| `--fix` | *(flag)* | After the report, show a fix plan and apply it after you confirm. `.esp` files are fixed in place (backed up first); masters (`.esm`) through `mwdialog_check - ESM fixes.esp`. Also rebuilds Cell Fixes (`mwdialog_check Cell Fixes.esp`: doubled objects, footing moves, exterior float drops, pathgrids), SoundFix unless `--no-soundfix`, the MWSE suite data, and `MWSE\config\mwsoundguard_data.json`. `.esm` files are never rewritten. |
| `--dry-run` | *(flag)* | With `--fix` (or other writing steps): show the plan but change nothing. |
| `--yes` | *(flag)* | With `--fix`: apply without asking. |
| `--play` | *(flag)* | Start `Morrowind.exe` directly, skipping the Morrowind Launcher (after any other steps given, e.g. `--sort --play`; not after a failed step, and skipped with `--dry-run`). Refuses (exit 3) when a plugin's master is missing, off, or loads after it, and (exit 4) when a core file or one of our patches no longer matches its recorded hash (see `--play-force`). Writes `generated\mwdialog_load_order.txt` into `Morrowind.ini`'s `[Game Files]`, brings `Data Files` up to date with `lua tools\` (removing, with a backup, what it deployed earlier for a mod or file `lua tools\` no longer has), and sets `SteamAppId` so Steam doesn't redirect to the Launcher. On its own, just does that and starts the game. |
| `--play-anyway` | *(flag)* | With `--play`: start even if a plugin's master is missing or loads after it, or your mods changed since our patches were built (a seriously bad idea: run `--fix` instead). |
| `--play-force` | *(flag)* | With `--play`: start even when the hash check fails (a core `.esm`/`.bsa` or one of our patches changed, or a recorded patch is missing). The warning is still printed. |
| `--rebaseline-hashes` | *(flag)* | Accept the core files and our patches as they are now: record their current hashes as the baseline `--play` checks, then stop (or start the game with `--play`). With `--dry-run`, only show what would change. |
| `--exe` | `<NAME>` | With `--play`: the game executable (default `Morrowind.exe`). |
| `--steam-appid` | `<ID>` | With `--play`: Steam app id (default 22320). |

#### Plugin Selection, Config, & Environment
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--plugins` | `<PLUGINS ...>` | Explicit load order (file names in Data Files), instead of the active load order. |
| `--only` | `<PLUGINS ...>` | Report (and fix) only issues coming from these plugins. Not an alias of `--plugins`. |
| `--ini` | `<PATH>` | Path to `Morrowind.ini` (default: the one in the game folder; its `[Archives]` are read). The plugin list is `generated\mwdialog_load_order.txt`, made from this ini the first time, and written back into it whenever a run changes it, and by `--play`. |
| `--openmw-cfg` | `<PATH>` | Reads `content=` and `data=` from `openmw.cfg`. With it (or `--plugins`), `Morrowind.ini` is never written; with it, `--fix` also skips SoundFix, the MWSE suite data and the sound cache. |
| `--vortex-dir`, `--staging` | `<PATH>` | Vortex's mod staging folder, searched for files that exist there but were never deployed (default: Vortex's own setting). |
| `--no-vortex` | *(flag)* | Disables Vortex staging integration. Automatic when Vortex is not installed (no `%APPDATA%\Vortex`). Mod Organizer 2 is not supported: its mods are not in Data Files. |
| `--vortex-downloads`, `--downloads` | `<PATH>` | Vortex download folder, to read a plugin's original header from its download archive when `--fix` has rewritten it (default: Vortex's own setting). |
| `--no-archive-lookup` | *(flag)* | Don't open download archives for the master check. |
| `--encoding` | `<NAME>` | Text encoding of plugin strings (default `cp1252`; `cp1251` Russian, `cp1250` Polish). |
| `--csv` | `<PATH>` | Also write the report to a CSV file. |
| `--no-interactive` | *(flag)* | With `--cell-conflicts` (and `--redundant`): only report, don't ask. Also the case when the output goes to a file. |

#### Cleaning & ESM Repairs
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--clean` | *(flag)* | Cleans `.esp` plugins like `tes3cmd clean`: duplicate object instances, redundant `AMBI`/`WHGT`, records duplicated from masters, Evil GMSTs, junk cells. `.esm` files are not rewritten. |
| `--patch-esm` | *(flag)* | Same as `--fix` (kept for older batch notes). `--fix` already writes master fixes into `mwdialog_check - ESM fixes.esp`. |
| `--no-placeholders` | *(flag)* | With `--fix`: don't add stand-in gold coins for objects that scripts name but no mod defines. |
| `--restore-dates` | *(flag)* | Undo the last `--sort` (put the old dates back). |
| `--header` | `<FILE ...>` | Show a plugin's Author and Description, or set them with `--set-author` / `--set-description`. |
| `--set-author` | `<TEXT>` | With `--header`: new Author (`+text` appends). |
| `--set-description` | `<TEXT>` | With `--header`: new Description (`+text` appends; `\n` starts a new line). |

#### Dialogue & Quest Checks
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--no-sounds` | *(flag)* | Skip checking that voice/sound files exist. |
| `--min-severity` | `ERROR`/`WARN`/`INFO` | Lowest severity to report (default `WARN`; use `INFO` to also see harmless notes). |

#### Cell Conflicts, Land Moves, & Footing
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--cell-conflicts` | *(flag)* | Analyzes exterior and interior cell conflicts, moved land, and prompts for conflict choices. Also writes the MWSE suite data (`mwfloatfix_data.json`, `mwcollide_data.json`, `mwstranded_data.json`, `mwperformers_data.json`). |
| `--only-incompatible` | *(flag)* | Limits cell conflict analysis to hard incompatibilities (e.g. moved land). |
| `--only-new` | *(flag)* | Replay every answer remembered in `mwdialog_conflict_answers.json` and ask only about the conflicts that have none yet. |
| `--fresh-answers` | *(flag)* | With `--full`: don't replay the remembered answers (by default `--full` replays them and asks only about new conflicts). Incompatible plugins are still asked about. |
| `--use-answers` | *(flag)* | With `--cell-conflicts`: take every remembered answer (a pair with none is asked in a console), then run what it needs (`--sort`, and `--fix --multipatch` if a plugin was turned off or a winner chosen). With `--full`: keep `mwdialog_cell_winners.txt` and replay the answers. |
| `--conflict-min` | `<N>` | A plugin must add at least N new objects to a cell to count (default 5). |
| `--conflict-top` | `<N>` | Print the N most serious pairs in the summary (default 40); the questions still go through every pair. |
| `--conflict-all` | *(flag)* | Show every pair in the summary. |
| `--conflict-all-places` | *(flag)* | Also list the pairs that only put a few objects near each other (left to `mwcollide`, not asked about). |
| `--collide-radius` | `<UNITS>` | For `mwcollide`: hide anything of the earlier of two unrelated mods within this many units of something of the later one's (default 32; 0: only the same object or model, within 64). |
| `--no-doubled` | *(flag)* | With `--fix`: don't look for (or turn off) plugins that place the same objects twice (recorded in `mwdialog_disabled.txt`). |

#### Load Order & Sorter
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--sort` | *(flag)* | Sort the active plugins: masters before the plugins using them, then the rules in `mwdialog_check.rules.txt` and mlox's `mlox_user.txt` / `mlox_base.txt`. Dates are set one day apart. The intended order is `generated\mwdialog_load_order.txt`. |
| `--no-mlox-rules` | *(flag)* | With `--sort`: use only `mwdialog_check.rules.txt`. |
| `--update-rules` | *(flag)* | Removes the steps of mlox's `mlox_user.txt` and `mlox_base.txt` that `--sort` already skips because a master, your `mwdialog_check.rules.txt`, a context rule, or an earlier mlox rule says otherwise, or because they would put an `.esp` before an `.esm`. Only the contradicted step of an `[Order]` rule is commented out or split; the rest of the rule stays. Your own rules file is only reported, never edited. `--dry-run` shows the plan and the reason for each. Does not download anything. |
| `--no-content-order` | *(flag)* | With `--sort`: don't add the automatic patch-after-mod rules or the dialogue cell-filter rules from `mwdialog_cellorder.py` (and so add no masters either). |
| `--no-add-masters` | *(flag)* | With `--sort`: don't add a mod as a master to the patch that changes its records (keep only the `[Context]` order rule). |
| `--add-all-esp` | *(flag)* | Activate every `.esm`/`.esp` in Data Files in `generated\mwdialog_load_order.txt` (masters first, then by date). Left out: MGE XE grass plugins (`grass_plugins` in `mgeXE.toml`), plugins an auto-merge replaces, and plugins `--fix` or `--redundant` turned off. The old list is backed up. Use `--dry-run` to preview. |

#### Merging & Patch Creation
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--auto-merge` | *(flag)* | Generates `mwdialog_check AutoMerge.esp` (or `--merge-name`) from eligible plugins with no cell, land, or pathgrid edits, and deactivates them. Plugins listed in `mwdialog_auto-merge.blacklist.txt` are never merged. If that file is missing it is created with `XE Sky Variations.esp`; an existing file is never overwritten or added to. Use `--dry-run` first. Kept as it is with `--preserve-saves=strict`. |
| `--merge` | `<OUT.esp> <INPUT ...>` | Merge the inputs (files or folders) into the named output plugin, written beside the inputs' originals (their Vortex mod folder for deployed files) unless the name includes a path. Inputs whose masters aren't active, or whose dialogue names things no installed mod defines, are left out. Later inputs win. |
| `--merge-name` | `<NAME.esp>` | With `--auto-merge`: the merged plugin's name. |
| `--merge-plan` | *(flag)* | Recommend merges `--auto-merge` doesn't make (plugins with cells, land, or pathgrids). Read-only: writes `mwdialog_merge_plan.txt` and `.json`. |
| `--plan-size` | `<N>` | With `--merge-plan`: at most N plugins per merge (small patches aren't capped; default 8). |
| `--unmerge` | `[NAME.esp ...]` | Undo an `--auto-merge`: reactivate the plugins it replaced and remove the merged plugin (all recorded merges if no name is given). Refused (exit 2) with `--preserve-saves=strict`. |
| `--merge-all` | *(flag)* | With `--merge`: include every input anyway. |
| `--merge-with` | `<PLUGINS ...>` | With `--merge`: plugins (not merged) that count as installed when checking the inputs. |
| `--no-follow-up`, `--no-follow-fix` | *(flag)* | Don't run the usual follow-ups (`--fix --multipatch` after `--auto-merge` or a `--sort` that changed the order, and so on). |
| `--multipatch` | *(flag)* | Generates `mwdialog_check Multipatch.esp` (merged leveled lists, fog, cell names, and merged objects unless `--no-merge-objects`). |
| `--no-merge-objects` | *(flag)* | With `--multipatch`: don't merge objects several mods change. |
| `--no-beast-skeleton` | *(flag)* | With `--multipatch`: don't give beast-race NPCs with no model or a humanoid skeleton the beast skeleton, nor graft the beast bones into a copy of a pose model that lacks them. |

#### Sound Repair & SoundFix
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--soundfix` | *(flag)* | Recompiles problematic audio scripts into `mwdialog_check - MWSoundFix.esp`. Only scripts whose source recompiles to their shipped bytecode are changed; `generated\mwdialog_soundfix_report.txt` lists the rest. Already runs as part of `--fix` unless `--no-soundfix`. With `--dry-run`: report only. Not built with `--preserve-saves` (exit 1 on its own; skipped inside `--fix`). |
| `--soundfix-report` | *(flag)* | Reports scripts eligible for soundfix without compiling. |
| `--soundfix-undo` | *(flag)* | Takes the SoundFix patch out (backed up first), with its helper data. |
| `--soundfix-loop-mode` | `flag`/`restart` | `flag` (default): a loop starts once, re-armed on a game load and by the `mwsoundfix` MWSE helper when its object comes back; `restart`: also restarted on every cell change (for an install without MWSE). |
| `--no-soundfix` | *(flag)* | Skip audio script recompilation during `--fix`. |
| `--repair-sounds` | *(flag)* | Re-saves sound files the active plugins play that the game can hang or crash on (24/32-bit or odd-codec WAVs, MP3s with damaged or huge tags), under the same names. Needs ffmpeg. Originals go to `<mod folder>\Off\<plugin>\<path>`. No plugin is changed. Missing files are not synthesized here; `--fix` / `--asset-check` create silent stand-ins for those. |
| `--mwrecompile` | `<PATH>` | `MWRecompile.exe` for `--soundfix` (default: the `MWRECOMPILE` environment variable, then `tools\MWRecompile\`, then PATH). |

#### Asset Management & Health
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--asset-check` | *(flag)* | Also check the files records, scripts and `Morrowind.ini` name (models and their textures, icons, sounds, music, videos, fonts), searching Vortex mod folders and `.Orphaned` for missing ones; with `--fix`, put them back or use stand-ins (adds a few minutes). |
| `--no-reduce-textures` | *(flag)* | Keeps textures > 2048 full size during asset repairs. |
| `--no-reduce-splash` | *(flag)* | Keeps splash screens > 2048 full size during asset repairs. |
| `--restore-textures` | *(flag)* | Puts back the full-size textures `--asset-check --fix` reduced to 2048 (listed in `mwdialog_reduced_textures.txt`). |
| `--restore-unused` | *(flag)* | Puts back the unused textures/sounds `--asset-check --fix` moved to `Off\unused\`. |
| `--remove-generated` | *(flag)* | Deletes the stand-in files `--fix` put in Data Files (listed in `mwdialog_generated_files.txt`); a file whose size changed since (the real file is there now) is left alone. |
| `--longpaths-undo` | *(flag)* | Puts back every file `--fix` or `vortex_tidy` moved to a short path, and the paths in plugins and models (moves a `vortex_tidy --undo` already put back are no longer listed). |

#### Redundancy, Masters, & Safety
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--redundant` | *(flag)* | Finds plugins doing the same job as another (nothing of theirs would be missed, or two versions of one mod), describes how they overlap, and asks which to keep (report only outside a console or with `--no-interactive`; remembered in `mwdialog_redundant.txt`). Report only with `--preserve-saves=strict`. |
| `--redundant-auto` | *(flag)* | `--redundant`, turning off the high-confidence ones (an `.esp` that changes nothing in the game and that nothing needs) without asking; two versions of one mod are still only asked about. |
| `--no-redundant` | *(flag)* | Skips redundancy analysis (including during `--full`). |
| `--redundant-undo` | `[PLUGINS ...]` | Turns back on plugins `--redundant` turned off (all of them, and forgets the keep-both choices, with no name). |
| `--reenable` | `[PLUGINS ...]` | Turns back on plugins `--fix` turned off as doubled (all of them with no name; see `mwdialog_disabled.txt`), after checking their masters are available. Refused (exit 2) with `--preserve-saves=strict`. |
| `--disable-mismatched` | *(flag)* | Deactivates compatibility patches built for a different master than the one installed. |
| `--mismatch-threshold` | `<FLOAT>` | Confidence from which a master counts as a different mod (default 0.75). |
| `--no-master-guard` | *(flag)* | Skip the master mismatch check. |
| `--bug-reports` | *(flag)* | Write `<plugin>.bugreport.txt` for plugins with problems of their own (also done by `--fix` and `--asset-check`). |
| `--no-bug-reports` | *(flag)* | Don't write `<plugin>.bugreport.txt` files. |
| `--preserve-saves` | `[basic\|strict]` | Keep a game in progress working. The bare flag means `basic` (a following Data Files path is still the folder, not the value); `--preserve-saves=strict` (or `--preserve-saves strict`) for more. `basic` skips `--soundfix` (it adds script variables), the topic renames, any rebuild or removal of Cell Fixes that would bring back an object it deletes, and setting aside an old Performers patch. `strict` does all that and also keeps the active plugins, the auto-merge and Cell Fixes exactly as they are (`--unmerge` / `--reenable` refused, `--auto-merge` kept, doubled/redundant/conflict turn-offs reported only), and skips the reference clean-ups and persistence flips. What it holds back is reported. Details: [MORE_INFO.md](docs/MORE_INFO.md#15-keeping-a-game-in-progress---preserve-saves). |
| `--restore` | `<PLUGINS ...>` | Puts each plugin's newest backup back (keeping the file date) and exits. |
| `--restore-all` | *(flag)* | Reverts all plugins to their oldest original backups (what is replaced is backed up first). With `--dry-run` it only lists them. |
| `--undo-all` | *(flag)* | Undoes the plugin fixes in one go: `--restore-all`, then `--redundant-undo`, then `--reenable`, each run in turn with `--yes`, `--dry-run` and `--ini` passed on. Every step runs; one with nothing to do is fine. Exit `2` when a step failed. |
| `--clean-up` | *(flag)* | Prunes plugin `.bak` backups (in Data Files and the backups folder): an installed or parked plugin keeps its oldest (the original) and newest; a plugin confirmed gone loses all of them; when it can't tell (a folder or record unreadable, Vortex staging unreadable, `--no-vortex`), that plugin's backups are moved to `<backups>\Off\cleanup\<path>` and journaled in `generated\mwdialog_cleanup_journal.jsonl`. `--dry-run` lists all three groups; asks first unless `--yes`. |
| `--clean-up-undo` | *(flag)* | Puts back the backups the last `--clean-up` moved to `Off\cleanup\` (checked against their SHA-256; never over a different file). |
| `--trace` | `<ID ...>` | Follows object IDs through the load order: who defines, places, deletes or scripts them. |
| `--fix-log` | `<PATH>` | Where to append a record of fixes (default `mwdialog_fixes.log`). |

---

### mwdialog_luafix Switches

| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--version` | *(flag)* | Print the package version and exit. |
| *(default)* | `[PATHS ...]` | Analyzes the given staged mod folders or Lua files (default: every staged mod with an `MWSE` folder; a path in Data Files is refused, since nothing there is checked or patched before deploy: use `--core-only` at deploy for the core files) and writes `plans\mwdialog_luafix_plan.txt` and `generated\mwdialog_luafix_known_bugs.txt`. |
| `--staging` | `<DIR>` | Vortex's Morrowind staging folder (default: Vortex's own setting). |
| `--apply` | *(flag)* | Enacts reviewed AST patches from `plans\mwdialog_luafix_plan.txt`. |
| `--yes` | *(flag)* | With `--apply`: don't ask first. |
| `--undo` | *(flag)* | Puts back the files the last `--apply` patched. |
| `--force` | *(flag)* | With `--undo`: also put back files changed since they were patched. |
| `--level` | `high`/`medium` | What gets patched: `high` (default) or also the medium-confidence findings. |
| `--include-own` | *(flag)* | Also check the suite's own mods (the names in `Data Files\MWSE\mods\mwsuite\ownmods.json`, or a built-in fallback if that file is missing: `mwcollide`, `mwconsole`, `mwcompanions`, `mwcriminal`...) and any `exemptMods` in the settings, which are skipped by default. Only A1-A5 (nil guards) and F1 (log shim) are applied to them. `ownMods` is the first-party list (who we are); `exemptMods` is a user list. |
| `--luajit` | `<PATH>` | Path to LuaJIT or luac to check syntax with (default: `tools\luajit\luajit.exe`, then `luajit` / `luac5.1` / `luac` on PATH, then the `lupa` Python package if installed). |
| `--no-syntax-check` | *(flag)* | Patch even with no LuaJIT/luac (parser only). Without it, `--apply` with no checker refuses (exit 2). |
| `--log-shim-always` | *(flag)* | Add the log shim even where `mwguard` covers it. |
| `--lua-log` | `flagged`/`all`/`off` | Which mods get the log shim: `flagged` (default), `all`, or `off`. |
| `--no-cache` | *(flag)* | Read every file again. |
| `--all` | *(flag)* | Also list what was left alone on purpose. |
| `--json` | `<PATH>` | Also write the findings as JSON to this file. With `--core-only`, the result as JSON; `-` prints it to stdout (and the summary goes to stderr). |
| `--diff` | *(flag)* | Show each patch as a diff. |
| `--core-only` | `[FOLDER]` | Checks and patches only the MWSE core files a KnownBugs rule names (KB3/KB4 on `core\mcm\components\pages\exclusionspage.lua` today), straight away and with no plan file, for a caller such as MWManager after `MWSE-Update.exe`. `FOLDER` is the Morrowind folder or its `Data Files` folder (default: `Data Files` of the Morrowind folder). Nothing else is scanned. Each file gets one status: `applied`, `already-patched` (our header is there, no fingerprint left), `no-match` (upstream fixed or changed it), `partial` (a rule whose parts must all match matches only some: nothing written) or `refused` (a reason is given: file missing, no syntax checker, patch rejected, changed since it was checked). Writes use the same backup, journal, hash check and `--undo` as `--apply`. Exit codes: `0` done (applied, already patched or no match), `1` another tool or MWManager holds the lock, `2` a file was refused, `3` partial (and none refused), `4` no such Morrowind folder. |
| `--dry-run` | *(flag)* | With `--core-only`: only check; write nothing, take no lock. |

---

### Exit Codes & Environment Variables

| Tool | Code | Meaning |
| :--- | :--- | :--- |
| `mwdialog_check` | `0` | Done, no ERROR left. |
| `mwdialog_check` | `1` | Done, ERRORs reported (also: another tool or MWManager holds the lock, or a step had nothing to do, e.g. `--reenable` with no match). |
| `mwdialog_check` | `2` | Failed or refused: Vortex folders not found, a bad entry in your rules file, `--full` stopped, the sound cache not written, and so on. |
| `mwdialog_check` | `3` | `--play` refused: a plugin's master is missing, off, or loads after it. |
| `mwdialog_check` | `4` | `--play` refused: the hash check failed (`--play-force` starts anyway; `--rebaseline-hashes` accepts the files). |
| `mwdialog_check` | `5` | `--play` refused: mods were added, removed or updated since our patches were built (`--fix` rebuilds them; `--play-anyway` starts anyway, a seriously bad idea). |
| `vortex_tidy`, `mwdialog_luafix` | `0` / `1` / `2` | Done / lock held, nothing to undo, an `--undo` that refused or left items in the journal, or some actions left unapplied / no plan, plan mismatch, Vortex folder not found, or (luafix) no syntax checker for `--apply`. |
| `mwdialog_check.bat` | `9009` | Python 3 was not found. |

Exit codes and files in detail: [MORE_INFO.md](docs/MORE_INFO.md#14-files-exit-codes--environment).

Environment variables: `MWRECOMPILE` (path to `MWRecompile.exe`), `APPDATA` (where Vortex's settings are read from), `MWDIALOG_PAUSE` (set by `mwdialog_check.bat` when started from Explorer: wait for Enter at the end), `MWMANAGER_DELEGATED_LOCKS` (set by MWManager for the tools it starts), and `MW_SRC` (tests only: the folder of scripts to test).

---

## The Plan-Then-Apply Workflow

To guarantee safety and prevent unintended modifications across huge mod installations, `vortex_tidy.py` and `mwdialog_luafix.py` enforce a strict **Plan-Then-Apply** paradigm:

```text
+-----------------------+      Generates      +-----------------------------+
|  python vortex_tidy   | ------------------> | plans/vortex_tidy_plan.txt  |
+-----------------------+                     +-----------------------------+
                                                             |
                                                             | Review Plan
                                                             v
+-------------------------------+   Executes Only   +-----------------------------+
| python vortex_tidy --apply    | <---------------- | Verified, Hashed Action Plan|
+-------------------------------+                   +-----------------------------+
```

1. **Plan Generation**: Running `python vortex_tidy.py` (or `python mwdialog_luafix.py`) scans the environment, computes required moves, DDS conversions, and AST patches, and writes an explicit plain-text plan to `plans/`.
2. **User Review**: The plan lists every file move, asset repair, and Lua patch (with the rule and line of each finding).
3. **Strict Application**: `--apply` works the plan out again and compares it with the plan file, action by action. If they differ (a file changed, a mod was added, the plan was edited), `--apply` **refuses to run** (exit code 2), keeps the old plan as `<plan>.prev.txt`, and writes the fresh plan for review. No plan file, or a blank one, also refuses: run plan mode first. A Lua file whose content hash changed since the check is refused on its own.
4. **Post-Apply Blanking**: After an apply, the plan file is blanked (a second `--apply` does nothing until plan mode runs again), or cut down to what was not applied. Copies of the plan as reviewed and as enacted go to `backups\tidy\<run>\` (`backups\luafix\<run>\` for luafix).
5. **Rollback**: Every move, Lua patch and (tidy) asset repair is recorded in a journal (`generated\vortex_tidy_journal.jsonl`, `generated\mwdialog_luafix_journal.jsonl`), and `--undo` puts back the last `--apply`. Patched Lua originals are also copied to `backups\luafix\<run>\`; tidy's asset originals to `backups\tidy\<run>\assets\<mod>\`, with their SHA-256 in the journal. tidy `--undo` stops before changing anything when an original is missing or altered, or a file changed since (`--force` overwrites changed files when the original's hash matches). luafix `--undo` leaves a file changed since it was patched unless `--force`.

---

## Load Order & Starting the Game

- **The load order is `generated\mwdialog_load_order.txt`**, one plugin per line. It is made from `Morrowind.ini`'s `[Game Files]` the first time; from then on it is the list the tools read, and an empty or damaged one is replaced by its backup. Plugin dates (set by `--sort`) decide the order the game loads them in.
- **`Morrowind.ini` is written** when a run that changed the list (`--sort`, `--add-all-esp`, a merge, a plugin turned off...) ends normally, so MGE XE's distant land generator sees the same order, and again by `--play`. Plugins not in Data Files are left out. Not with `--dry-run`, `--plugins` or `--openmw-cfg`. The ini as it was before the tools first changed it is kept as `backups\legacy\Morrowind.ini.mwdialog-original.bak`, the latest previous one as `backups\Morrowind.ini.mwdialog-play.bak`, and every version as a dated copy in `backups\legacy\`.
- **Automatic repairs before a run**: if `Morrowind.ini`'s list was cut at the 32,767-character section limit (and there is no `mwdialog_load_order.txt` yet), the run does `--add-all-esp --sort --yes` first. If an `[Exact]` group came apart (a plugin in it was saved since the last sort), it does `--sort --yes` first. `--dry-run` only reports these.
- **Follow-ups**: `--sort` that changed the order, and `--auto-merge`, then run `--fix --multipatch`; `--unmerge` then runs `--add-all-esp --sort`. `--no-follow-up` skips them.
- **Compatibility guard**: before `--fix`, `--multipatch`, `--auto-merge` or `--merge` write anything, the run checks for plugins that are incompatible with each other (moved land and the like; asked about in a console) and stops if that check fails.
- **`--play`** (or double-click `Play Morrowind.bat`) checks every active plugin's masters (refusing with exit 3; `--play-anyway` starts regardless), checks that no mod was added, removed or updated since our patches were built (refusing with exit 5: run `--fix`; in a console it asks whether to start anyway, `[y/N]`, and `--play-anyway` starts regardless; either is a seriously bad idea), checks the hashes of the core files and our patches (refusing with exit 4; `--play-force` starts regardless; see [the hash check](docs/MORE_INFO.md#the-hash-check-before-starting)), writes the ini, deploys `lua tools\` into `Data Files` (missing files copied, a deployed file replaced, with a backup in `backups\lua deploy\<date>\`, only when it is the older version (an older version is never put over a newer one: one warning names the file; your `MWSE\config\` settings are always left alone); which is older is decided by SHA-256 lineage, not file times: what it deployed is recorded in `generated\mwdialog_lua_manifest.json` with the earlier hashes each file had (up to 16), and file times are used only when a deployed file's content is in no record; and files an earlier `--play` deployed for a mod no longer in `lua tools\`, with its `*-metadata.toml` and `MWSE\config\` settings, are removed, backed up to `backups\lua prune\<date>\` and listed; `python mwdialog_paths.py --undo-lua-prune` puts them back), then starts the game detached with `SteamAppId` set (`--steam-appid`, default 22320). Details: [MORE_INFO.md](docs/MORE_INFO.md#starting-the-game---play).

---

## Key Architectural Features

### Dialogue & INFO Chain Healing
Morrowind's dialogue engine links topic responses (`INFO` records) in a singly linked list via the `PNAM` (Previous Record Name) subrecord. When multiple mods add or modify responses under the same topic, broken links, circular references, or orphaned records frequently cause the engine to freeze or endlessly loop:
- `mwdialog_check.py` analyzes the complete directed graph of `INFO` chains for every `DIAL` record (`scan`, then `plan_fixes` / `run_fix`).
- Identifies circular references (where response A points to B, and B points back to A) and breaks the loop safely.
- Resolves dangling `PNAM` pointers that reference non-existent or deleted `INFO` records, relinking the list to the next valid response.
- Cleans orphaned `INFO` records that exist without a parent `DIAL` record.

### Cell Conflicts & Footing Rescue
When multiple mods edit the same worldspace, landscape vertices and exterior objects frequently conflict.
- **Land Moves**: Major overhauls (such as Anthology Solstheim or Tomb of the Snow Prince) move entire landmasses. `mwdialog_anthology_override.py` detects script coordinates, pathgrids, and landscape height shifts, prompting the user to isolate incompatible mod branches.
- **Plugins that always lose, and INCOMPATIBLE losers**: choices `[7]` / `[8]` (`<plugin> always loses`) add a plugin to the generated `mwdialog_check.conflict.blacklist.txt`, which `--cell-conflicts` and `--sort` read. A plugin turned off in an INCOMPATIBLE pair is recorded in `mwdialog_incompatible_losers.txt` and is not asked about again while the plugin it lost to is still active. Both files live in `generated\`; remove a line by hand to undo one. Details: [MORE_INFO.md](docs/MORE_INFO.md#4-cell-conflicts-landscape-shifts-and-3d-nif-collision-footing-rescue).
- **Footing Rescue (`mwdialog_footing.py`)**: When one mod moves or deletes a dock, pier, or coastline and another mod places an NPC there, the actor is left floating or drowning in deep water. Using 3D raycasting against NIF collision meshes (`RootCollisionNode`) and exterior `LAND` heightmaps, `find_footing` first searches 128 units around in 8-unit rings, then up to 4096 units, for dry, level footing (at most 64 units above or below the old height). This runs during `--fix` inside `fix_cell_winners`. The same step also runs `find_float_drops`, which lowers loose exterior items onto what is under them now (the offline z pass into Cell Fixes). Interiors are still left to the in-game `mwfloatfix` module.

### AutoMerge & Multipatch
- **AutoMerge (`mwdialog_check AutoMerge.esp`)**: Frees plugin slots by merging active `.esp` files that have no cell, land, or pathgrid edits and can move together without changing what wins against any other plugin. The inputs are deactivated and recorded so `--unmerge` can put them back.
- **Multipatch (`mwdialog_check Multipatch.esp`)**: Like tes3cmd multipatch: merged leveled lists, illegal fog density `0.0` set to `0.01`, and reverted exterior cell names. By default it also merges objects several mods change, field by field (like TES3Merge), unless `--no-merge-objects` is passed. Beast-race NPCs (the winning race record's beast flag) with no model or a humanoid skeleton (`base_anim.nif`, `base_anim_female.nif`) get the beast skeleton `base_animkna.nif`; beast-race NPCs whose pose model lacks the beast bones get a copy with them grafted (`Meshes\mwdialog_beastpose\`), unless `--no-beast-skeleton`.

### Audio Script Recompilation (--soundfix)
A notorious Morrowind engine quirk causes `GetSoundPlaying` to return `0` for certain object sounds. Scripts written as `if ( GetSoundPlaying == 0 ) PlayLoopSound3D ...` execute every single frame, choking the audio channel and causing severe stutter.
- `--soundfix` (and `--fix`, unless `--no-soundfix`) locates these polling loops across all active plugin scripts.
- Rewrites the script logic to manage loop state using an internal tracking flag (`mwdialog_soundfix.rewrite`).
- Invokes `tools\MWRecompile\MWRecompile.exe` to compile the rewritten source into `mwdialog_check - MWSoundFix.esp`.

### MWSE Lua AST Analysis & KnownBugs
Unlike crude regex-based matchers, `mwdialog_luafix.py` uses a pure-Python lexical scanner and parser (`mwdialog_lua.py`) to build an AST for Lua 5.1/LuaJIT code:
- **Nil Guards**: Automatically inserts defensive guards before unchecked property accesses (e.g. `e.reference.object`).
- **Priority Compression**: Event handler priorities whose absolute value is 10,000 or more (`priorityLimit`) are made ordinary, keeping their relative order (`compress_priority`). By default (`priorityMode` `keepOrder`) they go to 9000-9999 (10000 -> 9000, 1e6 -> 9200, `math.huge` -> 9999; negative ones the same, negated), so they still run before every ordinary priority. `priorityMode` `clamp` uses 1000-1999 instead.
- **Log Shimming** (rule `F1`): for a mod with log-spam signs (logging every frame, in loops, in frequent events, debug flags on), its `print` / `mwse.log` lines past its allowance go to `Data Files\MWSE\logs\<mod>.log` (rotated at 2 MB, at most 25 lines a second); errors and lifecycle lines still reach `MWSE.log`. `--lua-log all` gives every mod that logs the shim, `off` none. The current shim is version 7. In the report, `F1 high` means the plan adds or upgrades the shim; a file that already has the current shim shows `shimmed`. Every log it handles is new in each game session, like `MWSE.log`: the previous session's log is kept as `<mod>.old.log` (replacing the older one), and a log from an earlier session that nothing wrote to is set aside when the game has initialized. A mod that keeps its own log in `Data Files\MWSE\logs\` by opening it in append mode (`io.open(path, "a")`) gets the same treatment: the first such open in a session starts the file new, later opens append.
- **General rules first, then Known Bugs**: the general rules (including `Y1` for syntax LuaJIT always rejects, `F3` for true/false in log text and `R1` safe handles) run before the Known Bugs table, and a Known Bugs part applies only where no rule matched. `KB5`, `KB28` and `KB51` were retired because a rule makes the same repair; a new entry must say why no rule can express it. Icons and textures stay as the mod ships them: luafix has no rule or Known Bugs entry that rewrites an image path or extension (`I1` and `KB20`, `KB25`, `KB26` were removed 2026-11-26).
- **Targeted KnownBugs (KB1-KB4, KB6-KB17, KB19, KB23, KB29-KB50, KB52)**: Hardens high-profile third-party mods against known engine crashes, memory leaks, sound-loop stacking, unbounded UI element growth (such as MWSE Core's `ExclusionsPage` unbounded item pagination), missing-comma syntax, nil crashes, and handlers that register again on every load. There is no KB18: the WBSR save-block conflict is handled at runtime by `mwsaveguard.wbsr_bard`, not by a luafix patch of WBSR. KB52 is the first entry added under the policy above: Tamriel Data's Detect Invisibility opacity pass, which failed every frame on a stale reference (its tables are local to `magic.lua`, so no rule reaches them). See [MORE_INFO.md](docs/MORE_INFO.md) for the catalog.
- **MWSE performance checks (report only)**: `G6` `tes3.getReference` in a frequent handler or a fast repeating timer; `G7` `tes3.rayTest` every frame or in a frequent handler with no `maxDistance`, no `root`, or `accurateSkinned`; `T1` `timer.start{ callback = "name" }` with no `timer.register("name", ...)` anywhere in the mod; `P1` `ref.data` written on a non-actor reference without `ref.modified = true`. `V1` (number before a vector in `*`, `+`, `-`) now flags only operands with vector evidence (MWSE's documented vector fields and functions, `tes3vector3.new`, a reference's `.position`, or a local set from one); `H2` no longer flags a timer started in `loaded` (MWSE clears every timer just before it); `D1` also flags costly work in an `infoFilter` handler that runs before it checks `e.passes`. `G6` ignores `getReference("player")`; `H2` treats a custom event fired only from `loaded` like `loaded`; `MWSE\backups\` and switched-off folders are skipped; files nothing loads are listed as unreferenced, their report-only findings set aside.
- **Generic tuning rules**: `G2` (a per-frame handler that only polls state runs every `minInterval`) and `G2S` (the same for a handler `G2` would leave at medium that scans the world every frame, for example with `tes3.rayTest`, `:iterateReferences()` or `tes3.findActorsInProximity`, and shows nothing frame-critical); `G8` (the same literal `tes3.messageBox` in a handler of a per-hit or per-decision combat event is shown at most once per `messageInterval`, 10 s by default); `U1` (a per-frame handler writes the `.text` of a label it made only when the value changed); `M1` (an `enterFrame` handler with no UI work returns in menu mode). `M1` and `G2` both read a handler's leading guards, so they share its first line instead of adding it twice. The config key `skipRules` (generic rule ids such as `"G2S"`, `"G8"`, `"U1"`) reports a rule but never applies it, like `skipKnown` does for Known Bugs. See [MORE_INFO.md](docs/MORE_INFO.md) for the rule table and config keys.
- **Reference-safety patches (KR1-KR3)**: safe handles in AURA's fader and Attend Me's timers. On by default; `"skipKnown": ["KR2"]` leaves one out. The frame-drain patches KP1-KP4 were removed (they fixed no bug; mwsuite intercept candidates); a file they already patched keeps it until `--undo` or a reinstall. See [MORE_INFO.md](docs/MORE_INFO.md).

---

## MWSE Suite (CR-18)

For the in-game menus and what their settings do, see the [Lua suite guide](docs/mwsuite-README.MD).

The first-party MWSE modules live in `lua tools\MWSE\mods\mwsuite\` (with their `*-metadata.toml` files, `ownmods.json`, and `MWSE\config\mwguard.json`) and are deployed to `Data Files` by `--play` (and by MWManager). luafix reads the first-party list from `Data Files\MWSE\mods\mwsuite\ownmods.json` (schema `{"version": 1, "ownMods": [...]}`) and falls back to a built-in copy, with a warning, if that file is missing from a deployed mwsuite folder. It leaves those mods (and any `exemptMods`) alone unless `--include-own` (then only A1-A5 and F1). See [MORE_INFO.md](docs/MORE_INFO.md#13-mwse-suite-notes-cr-18) for the module list. Recent suite logging and memory-safety work includes:

- **Log shim v6** (`mwdialog_luafix.py`): tighter lifecycle allowlist so lines like "Dialogue started with..." are not treated as init lines and forwarded to MWSE.log. The shim still intercepts `print` and `mwse.log`.
- **Log shim v7** (`mwdialog_luafix.py`): fresh logs each session (see Log Shimming), including a mod's own append-mode log under `Data Files\MWSE\logs\`.
- **mwsaveguard**: if a requested save never reaches saveguard because another handler returned false, it logs that the save was swallowed, lists the registered save handlers (found even behind other mods' wrapped `event.register`), says whether the save-renaming mod was reached, and asks again every second for up to 20 seconds (a Mod Config toggle; one message, no spam) until the save goes through or it gives up. The log also shows the name the save finally goes ahead with. `wbsr_bard` (loaded from mwsaveguard) releases only WBSR's save block for bard / performer songs; real dialogue still blocks saving. The toggle is on by default when WBSR is installed and loaded, and off (and registers nothing) when it is not.
- **mwhangwatch**: has no Mod Config tab of its own. Its settings are on the **Guard & Hang Watch** page that mwguard registers (page *Memory & Hang Log*), and closing that menu saves them to mwhangwatch's own settings file, `mwhangwatch.json`, next to `mwguard.json`. The low-memory warning (address space at `memLimit`, 80% by default, 70-99 in the MCM) is a non-modal toast, and it is opt-in (`memWarn` defaults to false). The hang watch itself (`enabled`) stays off until you turn it on.
- **mwfloatfix / `mwdialog_check --fix`**: `write_float_data` stamps `mwfloatfix_data.json` with size and an FNV-1a content hash of Cell Fixes, not the plugin's file time (those dates are rewritten for load order). `--fix` also runs an exterior z pass (`find_float_drops`) into Cell Fixes; interiors are still checked in-game.
- **mwsoundguard**: when a repeating sound comes from an object whose id is just a number, the log also records the mesh, name, source mod, and Lua caller when there is one.
- **mwguard**: its Mod Config menu is **Guard & Hang Watch** (pages *Memory & Hang Log* and *Lua Profiler*). `EnableLogTimestamps` (off by default; turning it on or off needs a restart) prefixes every MWSE.log line written through `print` / `mwse.log` with a time: `logTimestampMode` is `wallclock` (the default, `[HH:MM:SS]`) or `elapsed` (whole seconds since launch, `[000042]`).

Other suite modules include `mwcollide`, `mwstranded`, `mwperformers`, `mwinfoloop`, `mwcriminal`, `mwcompanions`, `mwexitguard`, `mwpluginpatches`, and the rest of the folders under `mwsuite`.

---

## OpenMW Converter (experimental)

An optional, very experimental OpenMW-to-MWSE converter is being developed separately. It is not released, not included, and not needed. If it is later found on PATH or beside these tools, tidy can use it; until then, OpenMW-only mods are set aside in `Off\<plugin name>\OpenMW\`. See `--convert-omwscripts` in the tidy switch table above.

---

## Installation & Directory Layout

Install the tools directly into a subfolder of your Morrowind directory, e.g.:
```text
<Morrowind>\conflict-tools\
```

Run from this folder (or from the game root), the tools automatically locate `Morrowind.ini` and `Data Files`: without a `Data Files` argument they use the first folder holding `Morrowind.ini` among the working folder, its parent, the parent of the scripts' folder, and the scripts' folder. Vortex's staging and download folders come from Vortex's own settings (its `state.v2` database or settings backups under `%APPDATA%\Vortex`), else from Vortex's marker file in the folder remembered in `generated\vortex_paths.json` or in Vortex's default location; `--staging` / `--downloads` override them.

The `.bat` files are the usual way in: `mwdialog_check.bat` with no arguments scans and opens `generated\mwdialog_report.txt` in Notepad; with arguments it passes them through (its header lists common commands). `vortex_tidy.bat` passes its arguments to `vortex_tidy.py`. `Play Morrowind.bat` is the one-click way to play: it runs `mwdialog_check.bat --play` (master check, load order into `Morrowind.ini`, lua tools brought up to date, then `Morrowind.exe` without the Launcher) and keeps its window open only if that ends with an error code. It works from `conflict-tools\` or copied up into the Morrowind folder; add steps before `--play` in it (e.g. `--sort --yes --play`) to run them every time.

```text
Morrowind\
 +-- Morrowind.exe
 +-- Morrowind.ini
 +-- mgeXE.toml                 [MGE XE (G7): its grass_plugins list is read]
 +-- mlox\                      [mlox_user.txt / mlox_base.txt, read by --sort]
 +-- Data Files\
 +-- conflict-tools\             [Repository root]
     +-- mwdialog_check.py        [Main plugin analysis & patcher]
     +-- mwdialog_check.bat       [Windows batch runner]
     +-- Play Morrowind.bat       [One click: mwdialog_check --play]
     +-- vortex_tidy.py           [Vortex staging organizer & sanitizer]
     +-- vortex_tidy.bat          [Windows batch runner]
     +-- mwdialog_luafix.py       [MWSE Lua AST hardening tool]
     +-- README.md                [This documentation]
     +-- LICENSE
     +-- docs\                    [MORE_INFO.md, QUICK_START.md, mwsuite-README.MD; docs\dev\:
                                   LUA-DEBUGGING.md, OFF-LAYOUT.md, LUA_MOD_BUGS.md]
     +-- plans\                   [Plan-then-apply files (.txt)]
     +-- generated\               [Load order, rules, records, caches, journals, reports (see MORE_INFO)]
     +-- backups\                 [Automatic backups (legacy\ for older; luafix\, tidy\, lua deploy\)]
     +-- tools\                   [Bundled utilities (see below)]
     +-- lua tools\               [MWSE suite modules deployed to Data Files]
     +-- tests\                   [pytest suite (repository only)]
     +-- diag\                    [local, not in the package: one-off diagnostics; listed in .gitignore]
```

When the tools are not installed inside the game folder, their records go straight into the game folder and backups into `<game>\mwdialog_backup\`.

---

## Requirements & Bundled Binaries

- **Python 3.9 or newer** (standard library only; no pip packages are needed to run the tools). Python 3.9 minimum; tested on 3.9 and the latest 3.x.
  - The luafix tests that use `lupa` run on 3.14.
  - `lupa` is optional: luafix uses it as a last-resort syntax checker when no LuaJIT/luac is found. The luafix tests that use `lupa` need a side-by-side Python 3.14 (they are skipped when it isn't installed). Run the tests with `python -m pytest tests` (or `pytest tests`): always name the `tests` folder, because a plain `pytest` also collects old copies under `_backup\...\tests` and fails on duplicate test names.
- **Windows OS** (Win32 process management, `MAX_PATH` handling, Vortex integration).
- **Bundled Binaries** (under `tools\`; see [tools/README.md](tools/README.md) for licenses and exact layouts):
  - `tools\texconv.exe`: DirectX texture processing, DDS mipmap generation, compression (MIT).
  The packaged zip is about 24 MB, mostly bundled ffmpeg, 7-Zip and texconv. The source archives for ffmpeg, LAME and 7-Zip are included to meet their LGPL licences.

- `tools\ffmpeg.exe` & `tools\ffprobe.exe`: Audio inspection, format conversion, silent stand-in synthesis, and sound durations for `mwsoundguard_data.json` (LGPL static build).
  - `tools\7z\7z.exe`: Archive inspection for download master verification (LGPL / unRAR). Optional: `--no-archive-lookup` skips it.
  - `tools\luajit\luajit.exe`: Bytecode syntax verification of patched Lua mods (MIT).
  - `tools\MWRecompile\MWRecompile.exe`: Recompiles rewritten sound scripts for `--soundfix`.

---

## Developer Tools (repository only)

These scripts are for working on the tools. They are in the repository and are never deployed into an install.

### deploy.py

Copies the runtime files and docs (git-tracked, chosen by `deploy_manifest.txt`, repository only) from the repository to an install, usually `<Morrowind>\conflict-tools\`.

```text
python deploy.py [TARGET] [--backups DIR] [--dry-run]
python deploy.py -h | --help
```

| Switch | Argument | Description |
| :--- | :--- | :--- |
| `TARGET` | `<PATH>` | The folder to deploy into. Saved in `deploy.ini` beside `deploy.py` (machine-specific, never committed); with no `TARGET` the saved one is used. |
| `--backups` | `<DIR>` | Where the backup of every file a deploy overwrites goes, also as `--backups=DIR` (saved in `deploy.ini` too). Default: a `_deploy_backups` folder beside the repository. Never inside `TARGET` or inside a game install. Each deploy gets `conflict-tools-deploy-<stamp>\` with `SHA256SUMS.txt`, `NEW_FILES.txt` and a relative `ROLLBACK.ps1`. |
| `--dry-run` | *(flag)* | Report what a real run would copy, skip and back up, and write nothing (not even `deploy.ini`). |
| `-h`, `--help` | *(flag)* | Print the full help and exit. |

A real run into a Morrowind install (`TARGET` is, or is inside, a folder holding `Morrowind.exe` or `Data Files`) refuses while Morrowind or MWManager is running; it never stops them. Any other target is not checked for running programs. Exit codes: `0` done, `1` refused or a copy failed its hash check, `2` an unknown switch or no target.

### doc_scan.py

Checks that the docs and the code agree on command-line switches. It never edits anything.

```text
python doc_scan.py [DIR]
python doc_scan.py -h | --help
```

It reads `README.md` and `docs\*.md` (not `docs\dev\`, and not a local `docs\CHANGES.md` if one is present), and the switches the tools define (argparse calls and hand-written parsers). It prints one line per documented switch the code doesn't have (file, line, and the tool it was checked against) and one per switch the code has that no doc mentions, then a summary. A switch hidden with `help=argparse.SUPPRESS` (retired or internal) is not listed as undocumented. Switches of other programs (`luajit`, `git`...) written after that program's name are left out. `DIR` checks another copy of the project. Exit codes: `0` clean, `1` something to fix, `2` an unknown switch.

### sync.py

`sync.py` is a local developer script on this machine, not part of the package: it is listed in `.gitignore`, is not committed, and is never deployed (`deploy.py` refuses it). A fresh clone does not include it. On a machine that has the script, it carries the tools from the checkout into MWManager, one way, and never writes to a Morrowind install (`deploy.py` is the only tool that does). The MWManager path is saved in `sync.ini` beside it (also ignored).

### release.py

`python release.py [VERSION]` builds `dist\conflict-tools-<VERSION>.zip` for a GitHub release: a `conflict-tools\` folder holding exactly what `deploy.py` ships, taken from the last commit (`git archive`, so `.bat` files are CRLF and everything else LF). VERSION defaults to `git describe --tags --always`. It warns when shipped files have uncommitted changes. It is never deployed.

### tes3diff.py

A record-level diff of two plugins, for reading what `vortex_tidy` or `mwdialog_check` wrote, and the helper behind the golden tests in `tests\test_tes3conv_golden.py`. It reads both plugins and writes nothing. It uses the optional converter **tes3conv** by Greatness7 (https://github.com/Greatness7/tes3conv, MIT License), which turns a plugin into JSON and back. tes3conv is bundled at `tools\tes3conv\` and deployed with the tools. `tes3diff.py` itself is a developer script and is not deployed; the tests that use tes3conv skip when it is not found.

```text
python tes3diff.py OLD NEW [--tes3conv PATH] [--limit N]
python tes3diff.py --check [--tes3conv PATH]
python tes3diff.py -h | --help
```

| Switch | Argument | Description |
| :--- | :--- | :--- |
| `OLD` `NEW` | `<PLUGIN>` | The two plugins (`.esp` / `.esm`) to compare. |
| `--check` | *(flag)* | Find tes3conv, verify it against the pinned release and report; compares nothing. |
| `--tes3conv` | `<PATH>` | The tes3conv program, or a folder holding it. |
| `--limit` | `<N>` | At most `N` changed fields per record (default 20; `0` for all). |
| `-h`, `--help` | *(flag)* | Print the full help and exit. |

It prints one line per record added (`+`), removed (`-`) or changed (`~`), each changed field as `path: old -> new`, and a summary. Records are matched by type and id (a cell by name and grid), so a record that only moved is not a difference. Exit codes: `0` no differences, `1` differences, `2` an unknown switch, `3` tes3conv not found or failed.

Finding tes3conv: `--tes3conv`, then the copy that ships with the tools (`tools\tes3conv\tes3conv.exe`, see below), then the `TES3CONV` environment variable (`TES3CONV=off` switches the rest of the lookup off, to see the tests skip), then `PATH`, then an untracked dev tools folder relative to the repository: `.devtools\tes3conv\` in it (in `.gitignore`) or `_devtools\tes3conv\` beside it. Nothing is ever put in a game install or in the user profile. With the vendored copy there is nothing to set up; to try another location, download the official **v0.4.1** Windows asset `windows-latest.zip` from https://github.com/Greatness7/tes3conv/releases/tag/v0.4.1, check its SHA-256 (`2783e835efdd4e28e9d31d63674c9c036f1332ef948707d581af33e7618a87a9`, GitHub's digest for that asset) and unpack `tes3conv.exe` into one of those folders.

**The vendored copy.** `tools\tes3conv\` holds the unmodified official v0.4.1 Windows `tes3conv.exe` with its license files (`LICENSE`, `LICENSE-tes3`, `LICENSE-mimalloc_rust`) and a `NOTICE.md` naming the source, tag and checksums. It is carried by `deploy_manifest.txt` into an install and, on a machine that has the local `sync.py` script, into MWManager, always together with the licenses; `tests\test_tes3conv_vendored.py` fails if the program is there without them or its hash is not the pin. Nothing the tools do needs it yet; `tes3diff.py` itself stays repository-only.

The version is pinned to v0.4.1. tes3conv has no way to print its version, so the check is the SHA-256 of `tes3conv.exe` (`3c259868c9deca42a658ff6c69cbc8578f8eeee99ebab5342bdb73beef650b40`, from that asset); another program, or a platform with no pinned hash, gets a warning and the run goes on. **The binary may lag the tes3 library it is built on: newer record types or fields may not round-trip.** A diff shows what the converter understands, not proof of byte-for-byte equality.

---

## Detailed Technical Architecture & Function Reference

For the architecture of the Python modules in the package, the switches that trigger each subsystem, and empirical fix examples from the historical fix archives, please read:

**[MORE_INFO.md](docs/MORE_INFO.md)**

---

## License

Created by dej (dejunai).

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details. Bundled tools in `tools/` maintain their respective open-source licenses (see [tools/README.md](tools/README.md)). The optional developer helper `tes3diff.py` and its golden tests use [tes3conv](https://github.com/Greatness7/tes3conv) by Greatness7 (MIT License, pinned to v0.4.1). The unmodified v0.4.1 Windows `tes3conv.exe` is vendored in `tools/tes3conv/` with its license files and a [NOTICE.md](tools/tes3conv/NOTICE.md): tes3conv (MIT, Copyright (c) 2025 Greatness7), the tes3 library it is built on (MIT, Copyright (c) 2022 Greatness7; its crate says "MIT OR Apache-2.0", the repository carries the MIT text only) and mimalloc_rust (MIT). The licenses travel wherever the program goes.
