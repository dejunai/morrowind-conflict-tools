# Morrowind Conflict Tools

A comprehensive, automated maintenance and conflict resolution suite for **The Elder Scrolls III: Morrowind**. Built entirely in Python (standard library only), this toolset handles deep plugin conflict resolution, dirty record cleaning, cell and dialogue repair, load-order sorting, asset validation and optimization, and AST-level MWSE Lua hardening.

The suite is engineered for massive, complex mod lists (hundreds of plugins, tens of thousands of assets) and provides two primary automated workflows:
1. **`vortex_tidy.py`** — Staging-level mod directory sanitizer, file structure organizer, asset validator, and Lua patcher.
2. **`mwdialog_check.py`** — Game-level plugin validator, dialogue fixer, cell conflict resolver, automated patch builder (AutoMerge, Multipatch, SoundFix), and mlox-compatible load-order sorter.

> [!IMPORTANT]
> **Detailed Function Architecture & Empirical Fix Catalog**:
> For the architecture of all 36 modules, command-line switches, and empirical fix examples from the historical fix archives, consult **[MORE_INFO.md](MORE_INFO.md)**.

---

## Table of Contents

- [Core Tools Overview](#core-tools-overview)
  - [vortex_tidy.py — Mod Staging Sanitizer & Pipeline](#vortex_tidypy--mod-staging-sanitizer--pipeline)
  - [mwdialog_check.py — Plugin Analysis & Conflict Engine](#mwdialog_checkpy--plugin-analysis--conflict-engine)
- [Command-Line Switch Reference](#command-line-switch-reference)
  - [vortex_tidy Switches](#vortex_tidy-switches)
  - [mwdialog_check Switches](#mwdialog_check-switches)
  - [mwdialog_luafix Switches](#mwdialog_luafix-switches)
- [The Plan-Then-Apply Workflow](#the-plan-then-apply-workflow)
- [Key Architectural Features](#key-architectural-features)
  - [Dialogue & INFO Chain Healing](#dialogue--info-chain-healing)
  - [Cell Conflicts & Footing Rescue](#cell-conflicts--footing-rescue)
  - [AutoMerge & Multipatch](#automerge--multipatch)
  - [Audio Script Recompilation (--soundfix)](#audio-script-recompilation---soundfix)
  - [MWSE Lua AST Analysis & KnownBugs](#mwse-lua-ast-analysis--knownbugs)
- [MWSE Suite (CR-18)](#mwse-suite-cr-18)
- [Installation & Directory Layout](#installation--directory-layout)
- [Requirements & Bundled Binaries](#requirements--bundled-binaries)
- [License](#license)

---

## Core Tools Overview

### vortex_tidy.py — Mod Staging Sanitizer & Pipeline

`vortex_tidy.py` inspects and cleans each individual mod folder inside Vortex's Morrowind staging directory (read directly from Vortex's configuration state, or specified via `--staging`). It ensures that mods deployed to `Data Files` are properly structured, free of stray junk files, and statically verified:

1. **Folder & Hierarchy Normalization**:
   - Detects nested `Data Files` directories, misplaced asset folders, and root-level clutter.
   - Moves documentation files (`.txt`, `.md`, `.pdf`, `.html`, `.htm`, `.doc`, `.docx`, `.odt`, `.rtf`, `.nfo`) at the mod root into `Docs\`, renamed `<mod name> - <file>` so one mod's `readme.txt` cannot overwrite another's when deployed. Documents already in `Docs\` that do not already name the mod get the same prefix.
   - Moves root image previews (`.jpg`, `.png`, `.gif`, `.bmp`, `.webp`) into `Screenshots\`, renamed the same way.
   - Relocates misplaced textures (`.dds`, `.tga`), meshes (`.nif`), icons, book art, and audio files into their canonical `Textures`, `Meshes`, and other game folders at the mod root.
   - Identifies MGE XE distant-land grass plugins and leaves them out of standard active plugin lists.
   - Moves OpenMW-only normal maps (`*_n` / `*_nm` / `*_normal` / `*_nrm`) whose diffuse texture exists to `Off\normal maps\<mod name>\`, so they are not deployed to vanilla Morrowind with MGE XE.
2. **Asset Sanitization & Optimization**:
   - Inspects DDS textures for corrupt headers, missing mipmaps, unsupported formats, and uncompressed RGBA.
   - Automatically generates missing mipmaps using bundled `texconv`.
   - Downsamples textures and splash screens exceeding 2048x2048 down to 2048 (preserving full size if `--no-reduce-textures` or `--no-reduce-splash` is passed). Splash screens are still made 24-bit RLE TGA.
3. **MWSE Lua AST Static Analysis & In-Place Hardening**:
   - Runs `mwdialog_luafix.py` against all Lua scripts across staged mods.
   - Parses code into a full Abstract Syntax Tree (AST) using a pure-Python Lua 5.1/LuaJIT parser.
   - Injects nil-guards, compresses absurd event priorities, adds a rate-limiting log shim for unthrottled `print` / `mwse.log` calls, and applies targeted patches for KnownBugs (KB1–KB17 and KB19; there is no KB18).
4. **Strict Safety**:
   - Implements a strict two-stage **Plan-then-Apply** execution model (`plans\vortex_tidy_plan.txt`).
   - Every file modification, move, or patch is cryptographically hashed and verified before execution.
   - Complete reversibility via `--undo` using an atomic action journal.

### mwdialog_check.py — Plugin Analysis & Conflict Engine

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
4. **NIF Raycasting & Footing Rescue (`mwdialog_footing.py`)**:
   - Solves the classic 'drowned NPC' problem: when a later mod alters coastline terrain or removes a dock, NPCs left standing over open water are detected via 3D raycasting against NIF collision meshes (`RootCollisionNode`) and LAND heights.
   - Moves stranded actors to the nearest stable, dry footing or relocates them to matching moved land. This runs as part of `--fix` (`fix_cell_winners`).
5. **Automated Patch Generation**:
   - **AutoMerge (`--auto-merge`)**: Finds active `.esp` plugins with no cell, land, or pathgrid edits that can move together without changing what wins against any other plugin, merges them into `mwdialog_check AutoMerge.esp` (or `--merge-name`), and deactivates the inputs.
   - **Multipatch (`--multipatch`)**: Builds `mwdialog_check Multipatch.esp` like tes3cmd multipatch: merged leveled lists, fog-bugged cells (illegal fog density 0 is set to 0.01), and reverted cell names, plus objects several mods change, merged field by field, unless `--no-merge-objects` is passed. Load it last.
   - **Doubled performers**: no plugin is built for them. The `mwperformers` MWSE module lets one performer per inn perform, in the game, and removes no one. A `mwdialog_check Performers Patch.esp` left by an earlier version is set aside (kept as a backup) and taken out of the load order by `--fix`.
   - **SoundFix**: Recompiles problematic audio scripts using `MWRecompile` into `mwdialog_check - MWSoundFix.esp`, replacing broken `GetSoundPlaying` polling loops with state variables. `--fix` rebuilds this patch unless `--no-soundfix` is passed. `--soundfix` runs that step on its own.
6. **Load-Order Sorter (`--sort`)**:
   - Built-in mlox-compatible topological sorter (implemented in `mwdialog_check.py`; `mwdialog_loadorder.py` parses rules and stores the order).
   - Evaluates custom rules from `mwdialog_check.rules.txt` (`[Order]`, `[NearStart]`, `[NearEnd]`, `[Context]`), then mlox's `mlox_user.txt` and `mlox_base.txt`.
   - Automatically adds patch-after-mod rules and dialogue cell-filter rules (`mwdialog_cellorder.py`) unless `--no-content-order` is passed.
   - The intended order is written to `generated\mwdialog_load_order.txt` and plugin dates are set one day apart. `--play` writes that list back into `Morrowind.ini` (whose `[Game Files]` section can be truncated by Windows' 32,767-character limit).
7. **Asset Integrity Check (`--asset-check`)**:
   - Verifies all model, texture, and sound references in active plugins against loose files and loaded BSA archives (`mwdialog_bsa.py`).
   - Generates stand-in dummy assets for missing meshes or textures to prevent game crashes.

---

## Command-Line Switch Reference

### vortex_tidy Switches

| Switch | Argument | Description |
| :--- | :--- | :--- |
| *(default)* | *(none)* | Generates a preview plan in `plans\vortex_tidy_plan.txt` without modifying files. |
| `--staging` | `<PATH>` | Explicit path to Vortex's Morrowind staging folder. Overrides automatic Vortex detection. |
| `--only` | `<PATTERN ...>` | Restricts tidying only to specified mod staging folder names (wildcards allowed). |
| `--skip` | `<PATTERN ...>` | Skips specified mod staging folder names this run. To always skip one, add it to `vortex_tidy_blacklist.txt`. |
| `--apply` | *(flag)* | Enacts the reviewed plan in `plans\vortex_tidy_plan.txt`. Refuses if the plan was modified or is out of date. |
| `--yes` | *(flag)* | With `--apply`: don't ask first. |
| `--undo` | *(flag)* | Reverses the last applied tidy actions using the execution journal. |
| `--no-assets` | *(flag)* | Skips the asset check of each mod's files. |
| `--no-lua` | *(flag)* | Skips the Lua check (`mwdialog_luafix`). |
| `--lua-only` | *(flag)* | Only the Lua check: no moves, no asset check. |
| `--lua-level` | `high` / `medium` | Which Lua findings `--apply` patches (default `high`). |
| `--luajit` | `<PATH>` | Path to the LuaJIT or luac binary the Lua check compiles with. |
| `--lua-log` | `flagged` / `all` / `off` | Which mods the Lua check gives the log shim: `flagged` (default), `all`, or `off`. |
| `--no-reduce-textures` | *(flag)* | Prevents downscaling of textures larger than 2048x2048. |
| `--no-reduce-splash` | *(flag)* | Prevents downscaling of splash screens wider than 2048 (they are still made 24-bit RLE TGA). |

---

### mwdialog_check Switches

#### Pipeline & High-Level Execution
| Switch | Argument | Description |
| :--- | :--- | :--- |
| *(default)* | `[DATA_DIR]` | Runs non-destructive validation on active plugins and outputs conflict reports. |
| `--full` | *(flag)* | Starts from scratch. Aborts if a plugin's master is missing from Data Files. Then: unmerge; turn back on what earlier runs turned off (and drop their conflict rules and asset stand-ins); the redundant-plugin step; a cell-conflicts report (asking only hard incompatibilities); sort; set the old Multipatch aside; `--clean --fix --asset-check` (footing and SoundFix run as part of `--fix`); sort; stop and open `mwdialog_report.txt` if any ERROR remains; otherwise AutoMerge, sort, `--all`, sort again; stop again on ERROR; then offer interactive `--cell-conflicts`. `--yes`: no questions; `--add-all-esp`: add every plugin first; `--play`: start the game at the end. |
| `--all` | *(flag)* | `--clean`, then `--fix`, then `--multipatch`. |
| `--fix` | *(flag)* | After the report, show a fix plan and apply it after you confirm. `.esp` files are fixed in place; masters (`.esm`) through `mwdialog_check - ESM fixes.esp`. Also rebuilds SoundFix unless `--no-soundfix`, refreshes the MWSE suite data, and runs footing / exterior float drops in `fix_cell_winners`. `.esm` files are never rewritten. |
| `--dry-run` | *(flag)* | With `--fix` (or other writing steps): show the plan but change nothing. |
| `--yes` | *(flag)* | With `--fix`: apply without asking. |
| `--play` | *(flag)* | Start `Morrowind.exe` directly, skipping the Morrowind Launcher (after any other steps given, e.g. `--sort --play`). Deploys `lua tools` to `Data Files` as part of launch. On its own, just starts the game. |
| `--play-anyway` | *(flag)* | With `--play`: start even if a plugin's master is missing or loads after it. |
| `--exe` | `<NAME>` | With `--play`: the game executable (default `Morrowind.exe`). |
| `--steam-appid` | `<ID>` | With `--play`: Steam app id (default 22320). |

#### Plugin Selection, Config, & Environment
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--plugins` | `<PLUGINS ...>` | Explicit load order (file names in Data Files), instead of the active load order. |
| `--only` | `<PLUGINS ...>` | Report (and fix) only issues coming from these plugins. Not an alias of `--plugins`. |
| `--ini` | `<PATH>` | Path to `Morrowind.ini` (its `[Archives]`). The plugin list is `generated\mwdialog_load_order.txt`, made from this ini the first time, and written back into it whenever a run changes it, and by `--play`. |
| `--openmw-cfg` | `<PATH>` | Reads `content=` and `data=` from `openmw.cfg`. |
| `--vortex-dir`, `--staging` | `<PATH>` | Staging folder override for Vortex integration. |
| `--no-vortex` | *(flag)* | Disables Vortex staging integration. |
| `--vortex-downloads`, `--downloads` | `<PATH>` | Vortex download folder, to read a plugin's original header from its download archive when `--fix` has rewritten it (default: Vortex's own setting). |
| `--no-archive-lookup` | *(flag)* | Don't open download archives for the master check. |
| `--encoding` | `<NAME>` | Text encoding of plugin strings (default `cp1252`; `cp1251` Russian, `cp1250` Polish). |
| `--csv` | `<PATH>` | Also write the report to a CSV file. |
| `--no-interactive` | *(flag)* | Don't ask questions; use saved answers or report-only where a prompt would appear. |

#### Cleaning & ESM Repairs
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--clean` | *(flag)* | Cleans dirty records, evil GMSTs, ITM junk cells, and misplaced exterior copies. `.esm` files are not rewritten. |
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
| `--cell-conflicts` | *(flag)* | Analyzes exterior and interior cell conflicts, moved land, and prompts for conflict choices. Also writes the MWSE suite data (`mwfloatfix_data.json`, `mwcollide_data.json`, `mwstranded_data.json`). |
| `--only-incompatible` | *(flag)* | Limits cell conflict analysis to hard incompatibilities (e.g. moved land). |
| `--only-new` | *(flag)* | Only prompts for cell conflicts that have not been answered in `mwdialog_conflict_answers.json`. |
| `--fresh-answers` | *(flag)* | Discards saved conflict answers and prompts interactively. |
| `--use-answers` | *(flag)* | Uses existing saved conflict answers without prompting. |
| `--conflict-min` | `<N>` | Minimum overlapping references required to flag a cell conflict. |
| `--conflict-top` | `<N>` | Caps the number of displayed cell conflicts to top N. |
| `--conflict-all` | *(flag)* | Reports all cell conflicts regardless of threshold. |
| `--conflict-all-places` | *(flag)* | Evaluates conflicts across all worldspace locations. |
| `--collide-radius` | `<FLOAT>` | Proximity radius in game units for detecting overlapping placed objects (default 32). |
| `--no-doubled` | *(flag)* | Skips checking for doubled object placements. |

#### Load Order & Sorter
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--sort` | *(flag)* | Sort the active plugins: masters before the plugins using them, then the rules in `mwdialog_check.rules.txt` and mlox's `mlox_user.txt` / `mlox_base.txt`. Dates are set one day apart. The intended order is `generated\mwdialog_load_order.txt`. |
| `--no-mlox-rules` | *(flag)* | With `--sort`: use only `mwdialog_check.rules.txt`. |
| `--update-rules` | *(flag)* | Removes the steps of mlox's `mlox_user.txt` and `mlox_base.txt` that `--sort` already skips because a master, your `mwdialog_check.rules.txt`, a context rule, or an earlier mlox rule says otherwise, or because they would put an `.esp` before an `.esm`. Only the contradicted step of an `[Order]` rule is commented out or split; the rest of the rule stays. Your own rules file is only reported, never edited. `--dry-run` shows the plan and the reason for each. Does not download anything. |
| `--no-content-order` | *(flag)* | With `--sort`: don't add the automatic patch-after-mod rules or the dialogue cell-filter rules from `mwdialog_cellorder.py`. |
| `--no-add-masters` | *(flag)* | With `--sort`: don't add a mod as a master to the patch that changes its records (keep only the `[Context]` order rule). |
| `--add-all-esp` | *(flag)* | Activate every `.esm`/`.esp` in Data Files in `generated\mwdialog_load_order.txt` (masters first, then by date; MGE XE grass plugins left out; the old ini is backed up). Use `--dry-run` to preview. |

#### Merging & Patch Creation
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--auto-merge` | *(flag)* | Generates `mwdialog_check AutoMerge.esp` (or `--merge-name`) from eligible plugins with no cell, land, or pathgrid edits, and deactivates them. Plugins listed in `mwdialog_auto-merge.blacklist.txt` are never merged. Use `--dry-run` first. |
| `--merge` | `<OUT.esp> <INPUT ...>` | Merge the inputs into the named output plugin. The first argument is the output name. |
| `--merge-name` | `<NAME.esp>` | With `--auto-merge`: the merged plugin's name. |
| `--merge-plan` | *(flag)* | Recommend merges `--auto-merge` doesn't make (plugins with cells, land, or pathgrids). Read-only: writes `mwdialog_merge_plan.txt` and `.json`. |
| `--plan-size` | `<N>` | With `--merge-plan`: at most N plugins per merge (small patches aren't capped; default 8). |
| `--unmerge` | `[NAME.esp ...]` | Undo an `--auto-merge`: reactivate the plugins it replaced and remove the merged plugin (all recorded merges if no name is given). |
| `--merge-all` | *(flag)* | With `--merge`: include every input anyway. |
| `--merge-with` | `<PLUGINS ...>` | With `--merge`: plugins (not merged) that count as installed when checking the inputs. |
| `--no-follow-up`, `--no-follow-fix` | *(flag)* | Don't run the usual follow-ups (`--fix --multipatch` after `--auto-merge` or a `--sort` that changed the order, and so on). |
| `--multipatch` | *(flag)* | Generates `mwdialog_check Multipatch.esp` (merged leveled lists, fog, cell names, and merged objects unless `--no-merge-objects`). |
| `--no-merge-objects` | *(flag)* | With `--multipatch`: don't merge objects several mods change. |

#### Sound Repair & SoundFix
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--soundfix` | *(flag)* | Recompiles problematic audio scripts into `mwdialog_check - MWSoundFix.esp`. Already runs as part of `--fix` unless `--no-soundfix`. |
| `--soundfix-report` | *(flag)* | Reports scripts eligible for soundfix without compiling. |
| `--soundfix-undo` | *(flag)* | Removes the SoundFix patch and its data file. |
| `--soundfix-loop-mode` | `flag`/`restart` | Loop state tracking method (`flag` for MWSE, `restart` for vanilla engine). |
| `--no-soundfix` | *(flag)* | Skip audio script recompilation during `--fix`. |
| `--repair-sounds` | *(flag)* | Re-saves sound files the active plugins play that the game can hang or crash on (24/32-bit or odd-codec WAVs, MP3s with damaged or huge tags), under the same names. Needs ffmpeg. Originals go to `<mod folder>\Off\<plugin>\<path>`. No plugin is changed. Missing files are not synthesized here; `--fix` / `--asset-check` create silent stand-ins for those. |
| `--mwrecompile` | `<PATH>` | Path to `MWRecompile` for `--soundfix`. |

#### Asset Management & Health
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--asset-check` | *(flag)* | Validates models, textures, and sound files referenced across active plugins. |
| `--no-reduce-textures` | *(flag)* | Keeps textures > 2048 full size during asset repairs. |
| `--no-reduce-splash` | *(flag)* | Keeps splash screens > 2048 full size during asset repairs. |
| `--restore-textures` | *(flag)* | Restores original textures from backup copies. |
| `--restore-unused` | *(flag)* | Puts back the unused textures/sounds `--asset-check --fix` moved to `Off\unused\`. |
| `--remove-generated` | *(flag)* | Removes generated placeholder assets and stand-in files. |
| `--longpaths-undo` | *(flag)* | Puts back every file `--fix` or `vortex_tidy` moved to a short path, and the paths in plugins and models. |

#### Redundancy, Masters, & Safety
| Switch | Argument | Description |
| :--- | :--- | :--- |
| `--redundant` | *(flag)* | Detects redundant plugins whose records are completely superseded by later mods. |
| `--redundant-auto` | *(flag)* | Automatically deactivates identified redundant plugins. |
| `--no-redundant` | *(flag)* | Skips redundancy analysis (including during `--full`). |
| `--redundant-undo` | `[PLUGINS ...]` | Re-enables plugins previously disabled as redundant. |
| `--reenable` | `[PLUGINS ...]` | Safely re-enables disabled plugins after verifying master availability. |
| `--disable-mismatched` | *(flag)* | Deactivates compatibility patches built for a different master than the one installed. |
| `--mismatch-threshold` | `<FLOAT>` | Confidence from which a master counts as a different mod (default 0.75). |
| `--no-master-guard` | *(flag)* | Skip the master mismatch check. |
| `--bug-reports` | *(flag)* | Write `<plugin>.bugreport.txt` for plugins with problems of their own (also done by `--fix` and `--asset-check`). |
| `--no-bug-reports` | *(flag)* | Don't write `<plugin>.bugreport.txt` files. |
| `--preserve-saves` | `[strict]` | Restricts patch generation and cleaning to prevent breaking in-progress saves. |
| `--restore` | `<PLUGINS ...>` | Restores specified plugins from their newest backup. |
| `--restore-all` | *(flag)* | Reverts all plugins to their oldest original backups (what is replaced is backed up first). |
| `--clean-up` | *(flag)* | Deletes the backups between each plugin's oldest original and its newest backup. |
| `--trace` | `<RECORDS ...>` | Traces the history and overrides of specific record IDs across the load order. |
| `--fix-log` | `<PATH>` | Where to append a record of fixes (default `mwdialog_fixes.log`). |

---

### mwdialog_luafix Switches

| Switch | Argument | Description |
| :--- | :--- | :--- |
| *(default)* | `[PATHS ...]` | Analyzes the given Lua files or directories (default: `Data Files\MWSE\mods` of the Morrowind folder) and writes `plans\mwdialog_luafix_plan.txt`. |
| `--apply` | *(flag)* | Enacts reviewed AST patches from `plans\mwdialog_luafix_plan.txt`. |
| `--yes` | *(flag)* | With `--apply`: don't ask first. |
| `--undo` | *(flag)* | Puts back the files the last `--apply` patched. |
| `--force` | *(flag)* | With `--undo`: also put back files changed since they were patched. |
| `--level` | `high`/`medium` | What gets patched: `high` (default) or also the medium-confidence findings. |
| `--include-own` | *(flag)* | Also check your own mods (`mwguard`, `mwcollide`, and the rest of the suite). |
| `--luajit` | `<PATH>` | Path to LuaJIT or luac to check syntax with. |
| `--no-syntax-check` | *(flag)* | Patch even with no LuaJIT/luac (parser only). |
| `--log-shim-always` | *(flag)* | Add the log shim even where `mwguard` covers it. |
| `--lua-log` | `flagged`/`all`/`off` | Which mods get the log shim: `flagged` (default), `all`, or `off`. |
| `--no-cache` | *(flag)* | Read every file again. |
| `--all` | *(flag)* | Also list what was left alone on purpose. |
| `--json` | `<PATH>` | Also write the findings as JSON to this file. |
| `--diff` | *(flag)* | Show each patch as a diff. |

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
2. **User Review**: The plan clearly lists every file move, texture compression, and Lua patch (including cryptographic hashes of the original file and the intended patch).
3. **Strict Application**: Running with `--apply` validates the plan. If any target file was touched or modified after the plan was generated, `--apply` **refuses to run** (exit code 2), safeguards the old plan as `.prev.txt`, and generates a fresh plan for review.
4. **Post-Apply Blanking**: After a successful apply, the plan file is automatically blanked so actions cannot be accidentally applied twice.
5. **Full Rollback**: Every applied change is recorded in an atomic journal, allowing complete restoration via `--undo`.

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
- **Footing Rescue (`mwdialog_footing.py`)**: When one mod moves or deletes a dock, pier, or coastline and another mod places an NPC there, the actor is left floating or drowning in deep water. Using 3D raycasting against NIF collision meshes (`RootCollisionNode`) and exterior `LAND` heightmaps, `find_footing` first searches 128 units around in 8-unit rings, then up to 4096 units, for dry, level footing (at most 64 units above or below the old height). This runs during `--fix` inside `fix_cell_winners`. The same step also runs `find_float_drops`, which lowers loose exterior items onto what is under them now (the offline z pass into Cell Fixes). Interiors are still left to the in-game `mwfloatfix` module.

### AutoMerge & Multipatch
- **AutoMerge (`mwdialog_check AutoMerge.esp`)**: Frees plugin slots by merging active `.esp` files that have no cell, land, or pathgrid edits and can move together without changing what wins against any other plugin. The inputs are deactivated and recorded so `--unmerge` can put them back.
- **Multipatch (`mwdialog_check Multipatch.esp`)**: Like tes3cmd multipatch: merged leveled lists, illegal fog density `0.0` set to `0.01`, and reverted exterior cell names. By default it also merges objects several mods change, field by field (like TES3Merge), unless `--no-merge-objects` is passed.

### Audio Script Recompilation (--soundfix)
A notorious Morrowind engine quirk causes `GetSoundPlaying` to return `0` for certain object sounds. Scripts written as `if ( GetSoundPlaying == 0 ) PlayLoopSound3D ...` execute every single frame, choking the audio channel and causing severe stutter.
- `--soundfix` (and `--fix`, unless `--no-soundfix`) locates these polling loops across all active plugin scripts.
- Rewrites the script logic to manage loop state using an internal tracking flag (`mwdialog_soundfix.rewrite`).
- Invokes `tools\MWRecompile\MWRecompile.exe` to compile the rewritten source into `mwdialog_check - MWSoundFix.esp`.

### MWSE Lua AST Analysis & KnownBugs
Unlike crude regex-based matchers, `mwdialog_luafix.py` uses a pure-Python lexical scanner and parser (`mwdialog_lua.py`) to build an AST for Lua 5.1/LuaJIT code:
- **Nil Guards**: Automatically inserts defensive guards before unchecked property accesses (e.g. `e.reference.object`).
- **Priority Compression**: Event handler priorities whose absolute value is 10,000 or more are compressed into 1000–1999, keeping their relative order (`compress_priority`).
- **Log Shimming**: Rate-limits unthrottled `print` and `mwse.log` calls (not `tes3.log`) inside per-frame simulation events (`simulate`, `render`). The current shim is version 6.
- **Targeted KnownBugs (KB1–KB17 and KB19)**: Hardens high-profile third-party mods against known engine crashes, memory leaks, sound-loop stacking, and unbounded UI element growth (such as MWSE Core's `ExclusionsPage` unbounded item pagination). There is no KB18: the WBSR save-block conflict is handled at runtime by `mwsaveguard.wbsr_bard`, not by a luafix patch of WBSR. See [MORE_INFO.md](MORE_INFO.md) for the catalog.
- **MWSE performance checks (report only)**: `G6` `tes3.getReference` in a frequent handler or a fast repeating timer; `G7` `tes3.rayTest` every frame or in a frequent handler with no `maxDistance`, no `root`, or `accurateSkinned`; `R1` a timer callback that uses a reference from its event with no safe handle or `:isValid()` check; `T1` `timer.start{ callback = "name" }` with no `timer.register("name", ...)` anywhere in the mod; `P1` `ref.data` written on a non-actor reference without `ref.modified = true`. `V1` (number before a vector in `*`, `+`, `-`) now flags only operands with vector evidence (MWSE's documented vector fields and functions, `tes3vector3.new`, a reference's `.position`, or a local set from one); `H2` no longer flags a timer started in `loaded` (MWSE clears every timer just before it); `D1` also flags costly work in an `infoFilter` handler that runs before it checks `e.passes`. `G6` ignores `getReference("player")`; `H2` treats a custom event fired only from `loaded` like `loaded`; `MWSE\backups\` and switched-off folders are skipped; files nothing loads are listed as unreferenced, their report-only findings set aside.
- **Frame-drain and reference-safety patches (KP1–KP4, KR1–KR3)**: Attend Me's per-frame rays (one cast per frame for the wheel, recruit mode at 20 Hz), Keg Drip's mesh-name work, G7 Containers' `getReference` per tile update, and safe handles in AURA's fader and Attend Me's timers. On by default; `"skipKnown": ["KP2"]` leaves one out. See [MORE_INFO.md](MORE_INFO.md).

---

## MWSE Suite (CR-18)

The first-party MWSE modules live in `lua tools\MWSE\mods\mwsuite\` and are deployed to `Data Files` by `--play` (and by MWManager). Recent suite logging and memory-safety work includes:

- **Log shim v6** (`mwdialog_luafix.py`): tighter lifecycle allowlist so lines like "Dialogue started with…" are not treated as init lines and forwarded to MWSE.log. The shim still intercepts `print` and `mwse.log`.
- **mwsaveguard**: if a requested save never reaches saveguard because another handler returned false, it logs that the save was swallowed and lists the registered save handlers. `wbsr_bard` (loaded from mwsaveguard) releases only WBSR's save block for bard / performer songs; real dialogue still blocks saving. The toggle is on by default when WBSR is installed and loaded, and off (and registers nothing) when it is not.
- **mwhangwatch**: the 95%+ address-space warning is a non-modal toast, and it is opt-in (`memWarn` defaults to false). The hang watch itself (`enabled`) stays off until you turn it on.
- **mwfloatfix / `mwdialog_check --fix`**: `write_float_data` stamps `mwfloatfix_data.json` with size and an FNV-1a content hash of Cell Fixes, not the plugin's file time (those dates are rewritten for load order). `--fix` also runs an exterior z pass (`find_float_drops`) into Cell Fixes; interiors are still checked in-game.
- **mwsoundguard**: when a repeating sound comes from an object whose id is just a number, the log also records the mesh, name, source mod, and Lua caller when there is one.
- **mwguard**: `EnableLogTimestamps` (on by default) prefixes every MWSE.log line written through `print` / `mwse.log` with a clock time (`[HH:MM:SS]`).

Other suite modules include `mwcollide`, `mwstranded`, `mwperformers`, `mwinfoloop`, `mwcriminal`, `mwcompanions`, and the rest of the folders under `mwsuite`.

---

## Installation & Directory Layout

Install the tools directly into a subfolder of your Morrowind directory, e.g.:
```text
<Morrowind>\conflict-tools\
```

Run from this folder (or from the game root), the tools automatically locate `Morrowind.ini` and `Data Files`.

```text
Morrowind\
 ├── Morrowind.exe
 ├── Morrowind.ini
 ├── Data Files\
 └── conflict-tools\             [Repository root]
     ├── mwdialog_check.py        [Main plugin analysis & patcher]
     ├── mwdialog_check.bat       [Windows batch runner]
     ├── vortex_tidy.py           [Vortex staging organizer & sanitizer]
     ├── vortex_tidy.bat          [Windows batch runner]
     ├── mwdialog_luafix.py       [MWSE Lua AST hardening tool]
     ├── README.md                [This documentation]
     ├── MORE_INFO.md             [Architecture & function guide]
     ├── plans\                   [Plan-then-apply files (.txt)]
     ├── generated\               [Logs, conflict answers, caches, mwdialog_load_order.txt]
     ├── backups\                 [Automatic backups (legacy\ for older)]
     ├── tools\                   [Bundled utilities (see below)]
     └── lua tools\               [MWSE suite modules deployed to Data Files]
```

---

## Requirements & Bundled Binaries

- **Python 3.8+** (standard library only; no external pip dependencies required to run the tools). Developed and tested on Python 3.15. The luafix tests that use `lupa` need a side-by-side Python 3.14.
- **Windows OS** (Win32 process management, `MAX_PATH` handling, Vortex integration).
- **Bundled Binaries** (under `tools\`; see [tools/README.md](tools/README.md) for licenses and exact layouts):
  - `tools\texconv.exe`: DirectX texture processing, DDS mipmap generation, compression (MIT).
  - `tools\ffmpeg.exe` & `tools\ffprobe.exe`: Audio inspection, format conversion, silent stand-in synthesis (LGPL static build).
  - `tools\7z\7z.exe`: Archive inspection for download master verification (LGPL / unRAR).
  - `tools\luajit\luajit.exe`: Bytecode syntax verification of patched Lua mods (MIT).
  - `tools\MWRecompile\MWRecompile.exe`: Recompiles rewritten sound scripts for `--soundfix`.

---

## Detailed Technical Architecture & Function Reference

For the architecture of all 36 modules, the switches that trigger each subsystem, and empirical fix examples from the historical fix archives, please read:

📖 **[MORE_INFO.md](MORE_INFO.md)**

---

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details. Bundled tools in `tools/` maintain their respective open-source licenses (see [tools/README.md](tools/README.md)).
