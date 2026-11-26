# Morrowind Conflict Tools: Comprehensive Architecture & Function Reference (MORE_INFO.md)

This document provides a low-level architectural analysis of the **Morrowind Conflict Tools** suite. It covers all 36 Python modules, describes how the major subsystems operate, lists the command-line switches that trigger them, and documents concrete empirical fix examples drawn from the historical fix archive (`fixes.archive.txt`), the active fix log (`mwdialog_fixes.log`), and third-party MWSE Lua repair records (`LUA_MOD_BUGS.md`). Function names in the tables are the real entry points in the current code. Helper functions and internal scanners are omitted. The tools are by dej (dejunai).

---

## Table of Contents

1. [Architectural Overview & Subsystem Map](#1-architectural-overview--subsystem-map)
2. [Plugin Integrity, Cleaning, and Binary Record Repairs](#2-plugin-integrity-cleaning-and-binary-record-repairs)
3. [Dialogue Logic, INFO Linked Lists & Topic Graph Healing](#3-dialogue-logic-info-linked-lists--topic-graph-healing)
4. [Cell Conflicts, Landscape Shifts, and 3D NIF Collision Footing Rescue](#4-cell-conflicts-landscape-shifts-and-3d-nif-collision-footing-rescue)
5. [AutoMerge & Conflict Multipatch Engine](#5-automerge--conflict-multipatch-engine)
6. [Performer & Bard Deduplication](#6-performer--bard-deduplication)
7. [Audio Script Recompilation & Sound Asset Repair](#7-audio-script-recompilation--sound-asset-repair)
8. [Asset Validation, DDS Textures, Mipmaps & Stand-ins](#8-asset-validation-dds-textures-mipmaps--stand-ins)
9. [Vortex Staging Normalization & File Organization](#9-vortex-staging-normalization--file-organization)
10. [MWSE Lua AST Static Analysis, Hardening & Targeted KnownBugs](#10-mwse-lua-ast-static-analysis-hardening--targeted-knownbugs)
11. [Load Order Sorting, Rule Management & Master Integrity](#11-load-order-sorting-rule-management--master-integrity)
12. [State Management, Safety Guards, Backups & Rollback](#12-state-management-safety-guards-backups--rollback)
13. [MWSE Suite Notes (CR-18)](#13-mwse-suite-notes-cr-18)
14. [Files, Exit Codes & Environment](#14-files-exit-codes--environment)
15. [Keeping a Game in Progress (`--preserve-saves`)](#15-keeping-a-game-in-progress---preserve-saves)

---

## 1. Architectural Overview & Subsystem Map

The Morrowind Conflict Tools suite operates across two distinct scopes:
- **Staging Scope (`vortex_tidy.py`)**: Interacts directly with the mod manager staging directory (Vortex), restructuring mod archives before deployment, standardizing asset trees, generating missing texture mipmaps, downscaling oversized assets, and performing static AST analysis on MWSE Lua scripts.
- **Runtime Scope (`mwdialog_check.py`)**: Interacts with the active Morrowind installation (`Data Files`, `Morrowind.ini`, and the intended load order in `generated\mwdialog_load_order.txt`). It parses binary ESM/ESP records, evaluates cell references, resolves dirty edits, links dialogue graphs, computes topological load orders, and builds dynamic conflict-resolution plugins.

```text
                              +---------------------------------------+
                              |         vortex_tidy.py                |
                              |  - Mod Staging Directory Sanitizer    |
                              |  - Documentation & Asset Relocation   |
                              |  - DDS Header & Mipmap Optimization   |
                              +---------------------------------------+
                                                  |
                                                  v
+-----------------------+              +---------------------+              +----------------------+
|    mwdialog_lua.py    | <----------> |  mwdialog_luafix.py | <----------> |  Targeted KnownBugs  |
|  Pure-Python Lexer &  |              |  AST Static Checker |              |  KB1-KB17, KB19-51   |
|  Parser for LuaJIT    |              |  & In-Place Patcher |              |  & Nil Guards        |
+-----------------------+              +---------------------+              +----------------------+
                                                  |
                                                  v
+--------------------------------------------------------------------------------------------------+
|                                    mwdialog_check.py                                             |
|                             Main Conflict & Patching Engine                                      |
+--------------------------------------------------------------------------------------------------+
          |                                       |                                      |
          v                                       v                                      v
+-------------------+                   +-------------------+                  +-------------------+
| Plugin Integrity  |                   | Cell & Landscape  |                  | Patch Generation  |
| - mwdialog_records|                   | - mwdialog_cellmods|                 | - mwdialog_multipatch |
| - mwdialog_tes3   |                   | - mwdialog_footing|                  | - mwdialog_mergeplan |
| - mwdialog_patchfile |                | - mwdialog_anthology_override |      | - mwdialog_soundfix |
+-------------------+                   +-------------------+                  +-------------------+
```

The remaining modules, not drawn above, are:

- `mwdialog_bugreports.py` - author-facing findings for one plugin and its declared master chain, never unrelated mod interactions (`--bug-reports`, also run by `--fix` and `--asset-check`).
- `mwdialog_datatree.py` - the Data Files tree and its BSAs: which models and assets exist on disk.
- `mwdialog_generated.py` - stand-ins and other files `--fix` puts in Data Files or changes there.
- `mwdialog_media.py` - DDS, NIF, and sound file formats: reading, reducing, placeholders, and silent stand-ins.
- `mwdialog_ownership.py` - ownership checks shared by the scanner and the Cell Fixes patch builder.
- `mwdialog_pathgrid.py` - for `--fix` (Cell Fixes): pathgrids that walk people into what a later mod built.
- `mwdialog_paths.py` - shared path helpers (no hardcoded absolute paths) and the run lock (`mwdialog.lock`).
- `mwdialog_state.py` - the small record files the tools keep beside themselves (merged plugins, disabled plugins, cell winners, and so on).
- `mwdialog_mgeghosts.py` - MGE XE distant-land overrides for the objects `mwcollide` hides as exterior cells load: `mge3\Conflict Tools Ghost Statics.toml` (by object ID) when `mgeXE.toml` is in the game folder (the G7 fork), else `mge3\Conflict Tools Ghost Statics.ovr` (by mesh); removed when nothing needs excluding. An object is excluded only when every exterior copy of it is hidden.
- `mwdialog_masters.py` - a plugin's master list: adding and removing a master (the masters `--sort` adds to patches, recorded in `mwdialog_added_masters.json`), whether an added one is still used, which plugins a set of patches covers, and `check_masters_for_play` (the master check `--play` runs first).
- `mwdialog_console.py` - questions with a default, the window title, and rotation of `mwdialog_fixes.log`.

Outside the 36 modules: `vortex_tidy.bat` and `mwdialog_check.bat` (Windows runners; `mwdialog_check.bat` with no arguments writes `generated\mwdialog_report.txt` and opens it), `Play Morrowind.bat` (runs `mwdialog_check.bat --play`; see section 11), `tests\` (pytest; `MW_SRC` points the tests at another copy of the scripts; run them as `pytest tests`, since a plain `pytest` also collects old copies under `_backup\...\tests` and fails on duplicate test names; e.g. `tests\test_dialogue.py` covers the dialogue checks and the plugin limit, `tests\test_tidy_undo_assets.py` the tidy `--undo` of asset repairs, `tests\test_tidy_dummies.py` tidy's broken-asset dummies, `tests\test_audit_fixes.py` `--clean-up` and `--clean-up-undo`, among others), and `diag\` (developer one-off scripts for a single record or merge question, run by hand; not part of any workflow. They load the `mwdialog_check.py` in the folder above them, `lantern_diag.py` another folder's if given one, and read the load order from `generated\`, falling back to the game folder).

Python: the tools need Python 3.9 or newer (standard library only) and are developed on 3.15. The whole test suite runs on Python 3.9 and on 3.15 (latest full run: 1272 passed, 5 machine-specific skips); the luafix tests that use `lupa` run on 3.14.

---

## 2. Plugin Integrity, Cleaning, and Binary Record Repairs

### Architectural Narrative
Morrowind plugins (`.esp`, `.esm`) use a hierarchical binary chunk format consisting of 4-character record headers (e.g. `CELL`, `INFO`, `ACTI`), record lengths, flags, and sequences of subrecords. Due to bugs in the original Bethesda Construction Set, plugins frequently ship with 'dirty edits': accidental GMST overrides (evil GMSTs that break game settings), identical-to-master (ITM) records that revert earlier fixes, duplicate object placements, junk test cells (such as empty `ToddTest` cells), and out-of-order subrecords.

The cleaning subsystem (`mwdialog_records.py`, `mwdialog_tes3.py`, `mwdialog_patchfile.py`, and `mwdialog_check.py`) parses binary plugin streams losslessly. It decodes strings using a custom CP1252 codec handler (`_mw_bytes_errors`) that ensures arbitrary byte sequences can round-trip without corruption. When `--clean` or `--fix` is triggered, the engine evaluates records against their master definitions. Duplicate object references in identical coordinates are dropped, evil GMSTs are removed, and out-of-order `XSCL` (scale) subrecords placed after `DATA/DELE` tags are restored to their legal positions. `.esm` files are never rewritten; master issues go into `mwdialog_check - ESM fixes.esp`.

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `run_clean` | `--clean`, `--all`, `--full` | `mwdialog_check.py` | Cleans dirty records in place on `.esp` files: evil GMSTs, ITM junk cells, duplicate references. Masters are not rewritten. | `Blood and Gore.esp: cleaned Evil GMST steleportdisabled` |
| `clean_cell` | `--clean`, `--fix` | `mwdialog_records.py` | Scans one `CELL` record against masters; strips ITM content and empty junk cells such as `ToddTest`. | `The Doors of Oblivion 1.4.esp: cleaned [cell ToddTest] junk cell (nothing new compared to its master)` |
| `rewrite_cell_refs` | `--clean`, `--fix` | `mwdialog_records.py` | Rebuilds a `CELL` record body; strips reference blocks whose `FRMR` IDs are flagged for removal or deduplication. | `Ald-Ruhn X.esp: cleaned [cell Ald-ruhn (-1, 6)] duplicate object instance ex_velothi_temple_01 (#4495 from morrowind.esm)` |
| `drop_cell_refs` | `--clean`, `--fix` | `mwdialog_records.py` | Drops placed reference copies duplicated across multiple exterior cells. | `Odai River Upper Overhaul.esp: [cell (0, 0)] flora_tree_ai_02: dropped reference #481796 duplicate` |
| `misplaced_duplicates` | `--clean` | `mwdialog_records.py` | Identifies identical reference instances placed in two different exterior cells where one belongs to an adjacent cell. | (same class of clean as the dropped-reference example above) |
| `late_scales` | `--fix`, `--clean` | `mwdialog_records.py` | Relocates out-of-order `XSCL` (scale) subrecords that appear after `DATA/DELE` blocks back to the reference header. | `Cleaned out-of-order XSCL scale subrecord in Great House Fliggerty Armor.esp` |
| `write_patch` | `--fix`, `--patch-esm` | `mwdialog_patchfile.py` | Writes `mwdialog_check - ESM fixes.esp` containing non-destructive overrides for master bugs. `--patch-esm` is an older alias of `--fix`. | `mwdialog_check - ESM fixes.esp: 'bs_rockbridge_mw' is placed by Daedric Shrine Overhaul FULL.esp before The Doors of Oblivion` |
| `apply_item_fixes` | `--fix` | `mwdialog_patchfile.py` | Rewrites broken item definitions in-place, repairing dangling script IDs or broken model links. | `Privileges&Services 1.1.esp: BODY 'IndorilPaulUa1': model 'AnPr\Arm\IndorilPaulUA1.nif' doesn't exist -> use 'bam\a_indoril_pauldron_ua.nif'` |
| `read_td_renames` | `--fix` | `mwdialog_patchfile.py` | Ingests Tamriel Data `Translation.txt` ID mappings and remaps legacy object references to current IDs. | `Remapped legacy TR item 'T_IngMine_Emerald_01' to 'T_IngMine_Emerald'` |
| `read_plugin_bytes` | *(internal)* | `mwdialog_tes3.py` | Fast cached binary reader with file modification and size validation. | Verified integrity of `Morrowind.esm` (79,836,375 bytes) |
| `iter_records` | *(internal)* | `mwdialog_tes3.py` | Binary generator yielding 4-character record tags, body bytes, flags, and offsets. | Streamed 45,000 records from `TR_Mainland.esm` |
| `pack_sub` / `set_link` | `--fix` | `mwdialog_tes3.py` | Rebuilds or replaces a 4-byte subrecord tag while the writer recalculates parent record header lengths. | `MCA - Khajiit Diversity Revamped Addon.esp: cleaned [cell Sadrith Mora, Dirty Muriel's Cornerclub] redundant WHGT` |

---

## 3. Dialogue Logic, INFO Linked Lists & Topic Graph Healing

### Architectural Narrative
Dialogue in Morrowind is organized into dialogue topics (`DIAL` records) representing conversations, rumors, greetings, and journal entries. Responses under each topic are stored in `INFO` records. Unlike modern engines that query dialogue dynamically, Morrowind links `INFO` records as an explicit singly linked list using the `PNAM` (Previous Record Name) subrecord: each response explicitly stores the ID of the response that must precede it in the evaluation order.

When multiple mods edit the same dialogue topic, this linked list frequently corrupts:
1. **Broken `PNAM` Chains**: Mod B points to an `INFO` deleted or overridden by Mod C, leaving the list severed.
2. **Infinite Loops**: Circular references where response A points to B, B points to C, and C points back to A, causing the engine to freeze in an infinite traversal loop.
3. **Orphaned `INFO` Records**: Responses saved without a parent `DIAL` record header, causing memory leaks or unpredictable dialogue injection.
4. **Invalid Script Triggers & Missing Audio**: Responses that trigger non-existent topics (`AddTopic`) or reference missing voice files (`Sound\Vo\...`).

`mwdialog_check.py` models dialogue as a directed graph inside `scan`. `plan_fixes` groups the proposed repairs; `apply_plan` / `run_fix` enact them: they reconstruct every chain, walk cycles to break them safely, reconnect dangling `PNAM` pointers to valid ancestors, remove orphaned responses, and comment out invalid `AddTopic` script commands.

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `scan` | `--fix`, *(default)* | `mwdialog_check.py` | Builds the dialogue graph across all active plugins; flags loops, broken pointers, missing voice lines, and speaker/script issues. | `MaiqMainland.esp: [Greeting 1] 29926225161036723252: result script adds topic 'Bleakrock', which does not exist -> commented out result-script line` |
| `plan_fixes` | `--fix` | `mwdialog_check.py` | Groups proposed repairs by plugin into in-place `.esp` plans and ESM-patch plans (masters are never rewritten). | `Djangos Dialogue - Patch for Purists.esp: [latest rumors] 1469412633283572447: previous-entry (PNAM) chain loops back on itself through 2 response(s) -> broke loop` |
| `apply_plan` | `--fix` | `mwdialog_check.py` | Rewrites one plugin (or collects changed INFO records for the ESM patch) according to its plan: relink `PNAM`, delete orphans, drop missing sound references. | `Tribunal.esm: [Asciene Rane] 23404284612240822214: previous (PNAM) link points to '1392327964637821771', which has been deleted -> relinked` (written into the ESM fixes patch) |
| `run_fix` | `--fix`, `--patch-esm` | `mwdialog_check.py` | Applies the plan, rebuilds `mwdialog_check - ESM fixes.esp`, and continues with SoundFix and the MWSE suite data unless those steps are skipped. | `AATL Mini Integration - Static Encounters.ESP: INFO record at offset 130191 is not preceded by a DIAL topic (orphaned response) -> deleted orphaned response` |
| `run_fix` (sounds / speakers) | `--fix` | `mwdialog_check.py` | The same pass validates voice paths against Data Files and BSAs, and drops local-variable conditions on placeholder speakers with no script. | `TheGardenOfDreams.esp: [Hello] 1784624959263039984: sound file 'Sound\Vo\x32\deg\deg_proper.mp3' not found in Data Files or BSA -> deleted sound reference` |

---

## 4. Cell Conflicts, Landscape Shifts, and 3D NIF Collision Footing Rescue

### Architectural Narrative
Worldspace conflicts in Morrowind fall into three primary categories:
1. **Conflicting Cell Attributes**: Disagreeing exterior cell names, regional associations, and ambient lighting parameters.
2. **Moved Land & Macro Landscape Shifts**: Massive overhauls (e.g. Anthology Solstheim, Tomb of the Snow Prince, Tamriel Rebuilt) shift entire island or coastline coordinates. Scripts, pathgrids, and objects targeting original coordinates become invalid.
3. **Footing Loss (Drowned / Hovering NPCs)**: When mod A places an NPC on a dock, pier, or natural cliff, and mod B later modifies the coastline or removes the dock, the NPC is left floating in mid-air or submerged underwater.

The conflict engine employs a sophisticated solution:
- `mwdialog_anthology_override.py` scans literal coordinates in compiled scripts (`SetPos`, `PositionCell`) and pathgrids to detect hard landscape moves and prompts the user for mutually exclusive resolution choices.
- `mwdialog_footing.py` implements a 3D raycasting engine. It parses the actual collision geometry (`RootCollisionNode`, `AvoidNode`, `NiTriShape`) directly from binary NIF files (`nif_triangles`) and landscape heightmaps (`land_heights`). When an actor is found suspended over water (`SUNK = -64.0`), `find_footing` first searches 128 units around in 8-unit rings, then up to 4096 units across cell borders, for dry, level footing at most 64 units above or below the old height (`SAME_LEVEL`), with probes at most 24 units uneven (`LEVEL`). This runs during `--fix` inside `fix_cell_winners`, not as a standalone `--cell-conflicts` writer. The same step also lowers loose exterior items onto what is under them now (`find_float_drops`).
- For an ordinary (not INCOMPATIBLE) conflict, `--cell-conflicts` also offers `[7] <A> always loses` and `[8] <B> always loses`. They are numbers because `a` already means "use last time's answers". The choice applies at once for the rest of the run (the plugin's other conflicts are dropped) and is saved as one line, with the date, in `generated\mwdialog_check.conflict.blacklist.txt`. That file is tool-managed and is made by the first `[7]` / `[8]` pick, not before (reading a missing file makes nothing): a `GENERATED` header (naming the file's own name), then the pick. Nothing is pre-decided: with no file, or an empty one, no plugin always loses, and no plugin is built into the code. A hand-written file is only read until a pick is added to it; that pick converts it once (entries and notes kept, the old file backed up). A dry run or replayed answers neither ask nor save. A listed plugin is left out of `--cell-conflicts` (no report, no question), `--sort` loads it as early as its masters allow (an `.esm` among the masters, an `.esp` right after the `.esm` files), and `mwcollide` hides its objects where two sit on top of each other. Editing the list is done by hand only: delete a line to take a plugin back. Don't list a compatibility patch, which must load after the mods it patches.
- A plugin turned off to settle an INCOMPATIBLE pair is recorded, with the plugin it lost to, in `generated\mwdialog_incompatible_losers.txt` (`loser<TAB>lost to<TAB>when`; names compare without regard to case). While the plugin it lost to is still active (installed, not turned off, not merged away), `--cell-conflicts` turns the loser off again without asking in every other incompatibility it is in, even when a saved answer for that pair picks the other side. When the winner is gone the line lapses and the loser is judged afresh; the existing re-enable of a plugin whose winner is gone is unchanged. This record is separate from the always-loses list, which also changes the load order and drops the plugin's conflicts, and that is wrong for a plugin that is turned off. Delete a line to take one back.

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `fix_cell_winners` | `--fix` | `mwdialog_check.py` | Rebuilds `mwdialog_check Cell Fixes.esp`: doubled objects, footing moves, exterior float drops, and pathgrid repairs. | Rescued fishermen and harbor guards left over water after a Seyda Neen dock overhaul |
| `find_footing` | `--fix` | `mwdialog_footing.py` | Raycasts 3D collision geometry to locate stable dry ground for NPCs left over water; returns updated positions. | `Footing: N people whose footing was taken away moved to footing beside it` |
| `find_float_drops` | `--fix` | `mwdialog_footing.py` | Exterior-only z pass: loose items hanging over what a later mod took away are put down on what is under them now, into Cell Fixes. Interiors stay with in-game `mwfloatfix`. | A bucket on the Seyda Neen dock dropped from z 107.9 to 84.0 |
| `nif_triangles` | `--fix` | `mwdialog_footing.py` | Extracts triangle vertex collision coordinates from NIF `RootCollisionNode` blocks. | Parsed collision triangles from `docks\dock_wood_01.nif` |
| `to_world` | `--fix` | `mwdialog_footing.py` | Transforms model local-space collision triangles into worldspace coordinates using reference translation and rotation. | Transformed pier collision bounds into the exterior cell |
| `incompatible_land_plugins` | `--cell-conflicts`, `--full` | `mwdialog_anthology_override.py` | Detects incompatible landscape shifts between conflicting land overhauls; prompts the user for load-order branch isolation. | Detected incompatible Solstheim land coordinates between `Anthology Solstheim.esp` and `TOTSP.esp` |
| `absolute_script_positions` | `--cell-conflicts` | `mwdialog_anthology_override.py` | Extracts literal `SetPos` / `PositionCell` coordinates from compiled scripts to detect hardcoded travel destinations. | Identified a hardcoded travel target in a ferry travel script |
| `add_conflict_blacklist` / `read_conflict_blacklist` / `migrate_conflict_blacklist` | `--cell-conflicts`, `--sort` | `mwdialog_state.py` | Choices `[7]` / `[8]` append the plugin as one dated line to the tool-managed `mwdialog_check.conflict.blacklist.txt`; the first pick makes it (header, the pick) or converts a hand-written one once, backed up first; reading never makes or changes it, and with no file the list is empty. Listed plugins are left out of `--cell-conflicts` and loaded early by `--sort`. | Chose `[7]` for one side of a pair: the plugin left its other conflicts for the rest of the run |
| `add_incompatible_loser` / `read_incompatible_losers` | `--cell-conflicts`, `--full` | `mwdialog_state.py` / `mwdialog_check.py` | Records the plugin turned off in an INCOMPATIBLE pair with the plugin it lost to; while that winner is active the loser is turned off again, unasked, wherever else it is incompatible. | `Himmelryn.esp`, turned off in favour of The Snow Prince, was not asked about again against Anthology Solstheim |
| `cell_filter_rules` | `--sort` | `mwdialog_cellorder.py` | Generates load-order rules ensuring plugins whose dialogue filters on a cell name load after the plugin that defines that cell. | Ordered a councilors patch after `TR_Mainland.esm` because of a cell filter on `Port Telvannis` |
| `write_collide_data` | `--cell-conflicts`, `--fix` | `mwdialog_cellmods.py` | Writes overlapping placements for `mwcollide` (`mwcollide_data.json`). `--collide-radius` defaults to 32 units (`COLLIDE_ANY_RADIUS`). | Overlapping statics in a Balmora city overhaul written for `mwcollide` to hide as the cell loads |
| `write_float_data` | `--cell-conflicts`, `--fix` | `mwdialog_cellmods.py` | Writes `MWSE\config\mwfloatfix_data.json`: the loose items that could float, so in-game `mwfloatfix` checks only those. Stamped with size and an FNV-1a hash of Cell Fixes (`patch_sources` / `fnv1a_file`), not the plugin's file time. | Mapped loose bowls, cups, and gold coins in tavern overhauls |
| `write_rescue_data` | `--fix` | `mwdialog_footing.py` | Writes `mwfloatfix_rescue.json` for people who may be under water in saves made before the footing pass. | Listed actors for `mwfloatfix` to put back once per save |

---

## 5. AutoMerge & Conflict Multipatch Engine

### Architectural Narrative
Morrowind's original engine loads at most 255 plugins, and MWSE / MGE XE at most 1024. `--add-all-esp` and `--sort` note a list over 255 (MWSE is needed to load them all); over 1024, they and `--play` warn that the last plugins won't load, and a scan reports a WARN on plugin #1025 (not with `--openmw-cfg`: OpenMW has no such limit). Turn some off or merge them (`--auto-merge`). Furthermore, when multiple plugins modify the same record type, the last-loaded plugin completely overwrites earlier changes, destroying balance patches, stat tweaks, and creature edits.

The patching engine provides two complementary solutions:
1. **AutoMerge (`mwdialog_check AutoMerge.esp`)**: Finds active `.esp` plugins with no cell, land, or pathgrid edits that can move together without changing what wins against any other plugin, merges them into one patch, and deactivates the inputs. Plugins listed in `mwdialog_auto-merge.blacklist.txt` are never merged.
2. **Multipatch (`mwdialog_check Multipatch.esp`)**: Like tes3cmd multipatch: merged leveled lists, fog-bugged interiors (fog density 0 is set to 0.01), and reverted exterior cell names. By default it also merges objects several mods change, field by field (like TES3Merge), unless `--no-merge-objects` is passed. Load it last.

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `run_multipatch` | `--multipatch`, `--all`, `--full` | `mwdialog_multipatch.py` | Builds the Multipatch: leveled lists, fog density 0 -> 0.01, reverted cell names, and optional object merges. | `mwdialog_check Multipatch.esp: cell 'Abernanit': fog density 0 (from Cutting Room Floor) set to 0.01` |
| `object_merges` | `--multipatch` | `mwdialog_multipatch.py` | Combines what each plugin changed in an NPC, creature, item, or spell, unless `--no-merge-objects`. | Field-by-field merge of an NPC edited by two balance mods |
| `run_auto_merge` | `--auto-merge`, `--full` | `mwdialog_check.py` | Merges eligible plugins into `mwdialog_check AutoMerge.esp` (or `--merge-name`) and deactivates them. | `mwdialog_check AutoMerge.esp: merged and deactivated Bow to the Daedra OAAB Add-on.ESP, KingsOathFix.ESP...` |
| `write_plan` | `--merge-plan` | `mwdialog_mergeplan.py` | Recommends merges `--auto-merge` doesn't make (plugins with cells, land, or pathgrids). Writes `mwdialog_merge_plan.txt` and `mwdialog_merge_plan.json`. | Calculated merge groups of weapon/armor balance plugins |
| `run_unmerge` | `--unmerge` | `mwdialog_check.py` | Reactivates the plugins an AutoMerge replaced and removes the merged plugin. | Restored the individual armor balance patches to the active load order |

---

## 6. Performer & Bard Deduplication

### Architectural Narrative
Tavern and city overhauls (such as *Animated Morrowind*, *Bards of Bardenfell*, and various tavern expansions) frequently place animated musician and bard NPCs in the exact same taverns (e.g. *The Rat In The Pot* in Ald-ruhn, *Lucky Lockup* in Balmora). When these mods are combined, taverns become overcrowded with multiple performers playing conflicting audio tracks simultaneously.

This is decided in the game only, by the `mwperformers` MWSE module; `mwdialog_check` builds no plugin for it (the Performers Patch and its `--performers-patch` / `--no-performers` switches are gone). On each visit to an interior, `mwperformers` finds every performer there (a bard, lute or drummer animation, or a script named for it), whichever mod added it or made it perform: an inn's own NPC that a mod turned into a bard counts the same as a new one, and Morrowind.esm's bards no longer always lose. One is picked at random to keep performing, and the pick is kept for that place on the player, so it is the same on every visit in that game. The others stop performing: their song script is held through MWSE's `scriptExecute` event (registered with that script as its filter), their song stops, and a performing animation goes back to the plain one. Nobody is disabled, hidden or deleted, and they can still be talked to. Bards that an older `mwperformers` hid (disabled) are shown again when their place is next visited. Its Mod Config menu can pick again for the current place.

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `retire_performers_patch` | `--fix` | `mwdialog_check.py` | Sets aside a `mwdialog_check Performers Patch.esp` an earlier version built (renamed to a backup, never deleted) and takes it out of the load order; nothing happens when there is none. Skipped with `--preserve-saves`. | `mwdialog_check Performers Patch.esp (made by an earlier version) set aside and taken out of the load order` |
| `settleCell` | in game | `mwperformers` (MWSE) | One performer per interior, picked at random and kept on the player; the rest stop through `scriptExecute`, the plain animation and a stopped song. | The Eight Plates: one of three bards plays; the others stand by and can be talked to |

---

## 7. Audio Script Recompilation & Sound Asset Repair

### Architectural Narrative
A notorious Morrowind engine quirk causes `GetSoundPlaying` to return `0` for certain object sounds even while they are still playing. Scripts written as:

```mwscript
if ( GetSoundPlaying "my_sound" == 0 )
    PlayLoopSound3D "my_sound"
endif
```

execute `PlayLoopSound3D` every single frame, flooding Morrowind's DirectSound buffer, exhausting audio channels, and causing stutter.

`--soundfix` (and `--fix`, unless `--no-soundfix`) locates these polling loops. `mwdialog_soundfix.rewrite` rewrites the script to track playback state with an explicit variable, then `run_mwrecompile` compiles the rewritten source with `tools\MWRecompile\MWRecompile.exe` into `mwdialog_check - MWSoundFix.esp`. A script is only rewritten when its source first recompiles to its shipped bytecode (so the source can be trusted); `generated\mwdialog_soundfix_report.txt` lists the scripts left alone and why. The new bytecode is that of the rewritten script, not a byte-for-byte match of the original. `--soundfix-loop-mode flag` (default) starts a loop once and re-arms it on a game load and through the `mwsoundfix` MWSE helper when its object comes back; `restart` also restarts it on every cell change, for an install without MWSE. `--soundfix-report` (or `--soundfix --dry-run`) writes the report only; `--soundfix-undo` takes the patch out (backed up first) with its helper data. `--preserve-saves` skips the step, since it adds script variables a saved game holds values for.

`--repair-sounds` is a different step: it re-saves damaged sound *files* the active plugins play (24/32-bit or odd-codec WAVs, MP3s with damaged or huge tags) under the same names, using bundled ffmpeg. Originals go to `<mod folder>\Off\<plugin>\<path>`. No plugin is changed. Silent stand-ins for *missing* files are created by `--fix` / `--asset-check`, not by `--repair-sounds`.

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `run_soundfix` | `--soundfix`, `--fix` | `mwdialog_soundfix.py` | Identifies `GetSoundPlaying` polling loops, rewrites scripts with state variables, and recompiles via `MWRecompile`. | Recompiled ambient water and machinery scripts into `mwdialog_check - MWSoundFix.esp` |
| `guard_kind` | `--soundfix` | `mwdialog_soundfix.py` | Analyzes conditional blocks to detect unchecked `GetSoundPlaying` loop guards. | Identified an unthrottled loop guard in a waterfall script |
| `structure` | `--soundfix` | `mwdialog_soundfix.py` | Builds a block-level indentation and control-flow map of Morrowind script source lines. | Parsed a nested conditional script in a Dwemer machinery mod |
| `rewrite` | `--soundfix` | `mwdialog_soundfix.py` | Rewrites the script source to keep loop state in a short variable. | Replaced a per-frame `PlayLoopSound3D` poll with a state flag |
| `run_mwrecompile` | `--soundfix` | `mwdialog_soundfix.py` | Invokes `tools\MWRecompile\MWRecompile.exe` on the rewritten source. | Compiled the rewritten scripts into the SoundFix patch |
| `run_repair_sounds` | `--repair-sounds` | `mwdialog_check.py` | Re-saves hang- or crash-prone sound files under the same names; originals go to `Off\`. | `repaired Sound\Fx\example.wav: it is a 24-bit WAV; original kept as ...\Off\...` |
| `repair_sound_ffmpeg` | `--repair-sounds` | `mwdialog_check.py` | Locates the bundled or PATH `ffmpeg` used by `run_repair_sounds`. | Used `tools\ffmpeg.exe` to re-save a damaged MP3 tag |
| `write_sound_cache` | `--fix` | `mwdialog_soundcache.py` | At the end of a `--fix` that changed something, writes `Data Files\MWSE\config\mwsoundguard_data.json` (sound durations for `mwsoundguard`, from the winning `SOUN` records; WAVs read directly, other formats through `ffprobe`). Not written, exit 2, when the final load order is missing plugins. | Cached sound durations across vanilla and Tamriel Data archives |

---

## 8. Asset Validation, DDS Textures, Mipmaps & Stand-ins

### Architectural Narrative
Asset failures in Morrowind are a primary cause of visual glitches and hard desktop crashes:
1. **Missing Mipmaps**: Textures without pre-calculated mipmaps shimmer violently in the distance and cause severe GPU texture-sampling pipeline stalls.
2. **Uncompressed Textures & Oversized Dimensions**: Huge uncompressed 32-bit RGBA textures or textures larger than 2048x2048 exceed Morrowind's legacy DirectX 8/9 texture memory allocations, leading to out-of-memory CTDs.
3. **Corrupt NIF Models & Broken Block Links**: Models with invalid child pointers (`nif_links_past_end`) or missing vertex shapes (`nif_without_shapes`) crash the engine upon entering a cell.
4. **Missing Meshes & Textures**: A missing model throws the infamous yellow exclamation mark, while a missing texture renders pure white.

`mwdialog_assets.py` operates as an asset validation pipeline. It verifies file references across loose directories and BSA archives (`mwdialog_bsa.py`). Missing mipmaps are automatically generated using bundled `texconv`, oversized textures are downscaled to 2048x2048, and corrupt or missing meshes receive valid stand-in dummy assets to keep the engine stable.

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `check` | `--asset-check`, `--full` | `mwdialog_assets.py` | Validates all model, texture, and audio references across plugins against loose files and BSAs. | `Data Files: 'textures\1em_B_N_DElf_Head07a.dds' (tex) -> repaired (original: Wyrmhaven-42933)` |
| `apply` | `--asset-check`, `--fix` | `mwdialog_assets.py` | Enacts the asset repairs: mipmaps, downscales, and stand-ins. | Generated mipmap levels for a loose armor texture |
| `needs_mips` | `--asset-check` | `mwdialog_assets.py` | Decides whether a DDS texture lacks a full mipmap chain and should be sent to `texconv`. | Flagged a texture with no mipmaps |
| `splash_too_wide` | `--asset-check` | `mwdialog_assets.py` | Detects splash screens wider than 2048 (still converted to 24-bit RLE TGA even if `--no-reduce-splash`). | Rescaled an oversized splash screen |
| `nif_without_shapes` | `--asset-check` | `mwdialog_assets.py` | Inspects binary NIF block headers to detect corrupt models devoid of drawable geometry. | Flagged an empty model and assigned a stand-in |
| `nif_links_past_end` | `--asset-check` | `mwdialog_assets.py` | Detects fatal NIF corruption where child node pointers reference block indices beyond the file header count. | Intercepted a crash-inducing cave rock model before game launch |
| `bsa_index` | *(internal)* | `mwdialog_bsa.py` | Parses TES3 BSA archive directory headers, building an index of archived assets. | Indexed assets inside `Morrowind.bsa`, `Tribunal.bsa`, and `Bloodmoon.bsa` |
| `check` / `apply` / `undo` | `--asset-check`, `--longpaths-undo` | `mwdialog_longpaths.py` | Shortens asset paths that exceed Windows or Morrowind limits, and can put them back. | Moved a long texture path and retargeted the plugin that named it |
| `restore_unused` | `--restore-unused` | `mwdialog_assets.py` | Puts back unused textures/sounds that `--asset-check --fix` moved to `Off\<plugin>\unused assets\`. | Restored a texture that a later plugin started using |

---

## 9. Vortex Staging Normalization & File Organization

### Architectural Narrative
When installing mods through mod managers like Vortex, mod archives frequently contain readmes, text walkthroughs, image previews, changelogs, FOMOD leftovers and OpenMW-only files strewn across the root mod folder. If deployed directly to the game, these files clutter the installation and cause file-override collisions.

`vortex_tidy.py` automates the cleanup of Vortex's staging directory. It inspects each mod folder, moves documents (`.txt`, `.md`, `.pdf`, `.html`, `.htm`, `.doc`, `.docx`, `.odt`, `.rtf`, `.nfo`) into `Docs\` renamed `<mod name> - <file>`, moves root images into `Screenshots\` with the same prefix, turns a root readme folder into part of `Docs\`, moves everything else that is not game data to `Extras\<mod name>\`, moves MGE XE grass plugins to `Grass\`, moves a hybrid mod's OpenMW files to `Off\OpenMW\<mod name>\`, converts OpenMW-only mods with the OpenMW converter or sets them aside whole in `Off\<plugin name>\OpenMW\` (see below), moves OpenMW-only normal maps to `Off\normal maps\<mod name>\`, renames a script-free `.omwaddon` with no `.esp`/`.esm` beside it to `.esp`, runs the asset check on each mod's files, and interfaces with `mwdialog_luafix.py` to harden MWSE scripts in place. Game folders, support folders (`MWSE`, `MGE3`, `Shaders`, `Grass`, `MCPatch`), plugins, `.bsa` archives and `*-metadata.toml` stay where they are. A mod that installs into the game folder (an `.exe`, `.dll`, `.asi` or a `Data Files` folder at its root) is left alone, as is every mod matching the blacklist (`Morrowind Code Patch*`, `MCP beta*`, `NIFZER0EDIT*`, plus `vortex_tidy_blacklist.txt`; `--skip` adds patterns for one run). All operations are strictly planned before execution via `plans\vortex_tidy_plan.txt` (sections: the moves, `LUA CHECK`, `ASSET CHECK`); `--lua-only` plans and applies only the Lua section, `--no-lua` / `--no-assets` leave a section out.

**Broken assets and dummies.** A file the asset check finds broken and can't repair (empty, not the format its name says, truncated, a model the game crashes on, an MP3 with no audio) goes to `<mod>\Off\<plugin>\broken\<path>`, and a small valid dummy of the same type takes its place, so the plugins and models naming it still find a file. The plan line is `repair dummy <path>`. Made in code: a 4x4 texture for DDS, TGA, BMP and PNG (flat normal-map colour for `*_n` / `*_nm`..., black for glow/specular maps, grey otherwise), an 8x8 JPEG, a 32x32 icon for a DDS under `icons\`, silent WAV and MP3. A model (NIF) gets the game's Dwemer coin by default, read out of the core `Morrowind.bsa` (`meshes\m\misc_dwrv_coin00.nif`, the stand-in `--fix` uses; nothing is written outside the mod), so the missing mesh is easy to spot without the game's giant error marker; with `--no-coins`, an empty invisible NIF made in code (one empty `NiNode`). When the coin isn't in `Morrowind.bsa`, the empty NIF is used and the plan says so; a warning that the core game files have been altered is also shown once per run, at the end of the output and of the plan (comment lines, not actions). It never blocks, but it is strongly worded and tells you to restore the shipped files (Steam or GOG "verify integrity" / "verify / repair", or reinstall the original `Morrowind.bsa`). The same warning fires when a known core file tidy looks up by name is missing or unreadable: `Morrowind.bsa` itself, the coin in it, or `meshes\i\xin_dagoth_bridge00.kf` (the `.kf` stand-in). `Tribunal.bsa` and `Bloodmoon.bsa` are optional sources and are not warned about; nor is a run with no `Data Files` folder at all (tidy is simply not in a game folder). The plan line names the kind (`{"dummy": "coin"}` or `"empty"`), so `--apply` refuses a plan made with the other setting. Any other type (`.kf`, `.bik`, `.fnt`, `.tex`...) gets a copy of a core game file of that type, from `Morrowind.bsa` / `Tribunal.bsa` / `Bloodmoon.bsa` or the game's own loose `Video` and `Fonts` files (a file Vortex deployed never counts), in this order: the core file at the same path; else the smallest core file whose name appears in no active plugin, no staged mod's plugin and not in `Morrowind.ini`; for a `.kf` only, then `meshes\i\xin_dagoth_bridge00.kf`; else the smallest core file of the type. The pick is cached in `generated\vortex_tidy_dummy_sources.json` (renewed when those plugins, `Morrowind.ini` or the core BSAs change; delete it to force a new pick). Nothing is shipped: a type with no dummy either way is left as it is, and the plan says so. `<original>.tidy-dummy` beside the kept original records the dummy's path and SHA-256, so a later run neither reports nor replaces it while it is unchanged, whichever `--no-coins` setting made it or is used now. A model the game crashes on that another copy exists for (another staged mod, loose in Data Files, or a BSA there) is only moved out (`repair brokenout`), so that copy wins after Deploy; a stand-in already in place of a broken model stays. `--undo` puts the original back and removes the dummy's `Off\` copy and mark.

**OpenMW-only mods and the OpenMW converter.** A mod is OpenMW-only when it has OpenMW scripts (an `*.omwscripts` at its root, in `OpenMW\`, or set aside under `Off\`) and no MWSE Lua of its own (no `.lua` under `MWSE\` that omw2mwse did not generate). A mod with real MWSE Lua is MWSE-first: its OpenMW files go to `Off\OpenMW\<mod name>\` and it is never converted. `--apply` hands an OpenMW-only mod to the converter, `omw2mwse --convert-omwscripts=<mode> <mod> --json`, found on PATH or beside these tools (this folder, its `tools\` or the folder above; no fixed paths). The mode is `normal` by default; `--convert-omwscripts=hardcode` picks the other mode (with `--accept-hardcode-conversions`) and `--no-convert-omwscripts` turns conversion off. Vortex's mod name and author are passed as `--title` and `--author` when Vortex has them. The converter lays the mod out itself, so nothing else in it moves that run; the plan lists `convert with omw2mwse (<mode>)` and a dry-run preview. A conflict (exit 4), a refusal or an error is one WARNING line, and the mod is treated as not converted (below). The converter is experimental: see the last section of this chapter.

**What tidy reads back from the converter.** The verdict (`mods[].verdict`) is honoured: `blocked` (the converter exits 0 yet writes an active loader) is not shipped, so its output is undone at once, the plan says so up front, and the mod is treated as not converted. A mod whose original author has asked that it be excluded from conversion comes back `blocked` too, with nothing written (not even a manifest): tidy moves its whole package to `Off\<plugin>\OpenMW\` untouched, with one plain WARNING saying the original mod author asked for the exclusion and to contact them for details, and it never shows or logs where the converter found the request. `partial` counts as converted, with a NOTE. The converter also reports each plugin it emits (`mods[].plugins[]` of its JSON, else `plugins` in `omw2mwse-manifest.json`) with `placement` (`root`, `extras` or `off`), `status` (`required`, `undetermined` or `obsolete`), `path`, `sourceRel` and `reason` (omw2mwse 0.2.3). Only `root` plugins are on by default. Tidy prints one NOTE at `--apply` for each plugin the converter put in `Extras\<Mod>\` or `Off\<Mod>\OpenMW\`, with the converter's reason (for example `wildlife_getfight.esp`, obsolete). It never renames, moves or enables a converted mod's plugins (the converter renames `.omwaddon` / `.omwgame` to `.esp` / `.esm` itself and keeps the originals under `Off\`), and it never reads readmes or FOMOD text to decide. For an older converter, `optional: true` counts as not-root, and a manifest with no `plugins` key falls back to a scan for root plugins with no `.omwaddon` / `.omwgame` source.

**An OpenMW-only mod that is not converted** (no converter found, a failed or blocked conversion, or `--no-convert-omwscripts`) moves as one whole package to `Off\<plugin name>\OpenMW\`, with the same relative paths: plugins, scripts, data folders (`textures\`, `meshes\`, `sound\`, `icons\`, `fonts\`...) and tidy's own `Docs\` and `Screenshots\`. The mod folder keeps only `Off\` (and Vortex's marker file), so a mod that stays enabled in Vortex deploys nothing else. `<plugin name>` is the converter's own name for the package (`package_name` here, `mod_name_for` there): the stem of the first `*.omwscripts` in the folder, with everything but letters, digits, `_` and `-` removed (`OpenMWMod` if nothing is left; the folder's own name when it has no `.omwscripts`). Example: `Wild Attacks-54448-1-9`, holding `wildlife_attacks_npc.omwscripts`, goes to `Off\wildlife_attacks_npc\OpenMW\`. A package an older tidy run set aside at `Off\OpenMW\<mod name>\` moves to the new place on the next run (journaled like any move). A converter's own output is never moved.

**Undo of a conversion.** `--apply` journals each conversion with the converter's own report (where the original package was, where the converter keeps it, the folder and manifest it wrote, and the manifest's file list with hashes). `--undo` takes the conversions of a run out first, then the asset repairs, the Lua patches and the moves. It puts the original package back from `Off\<plugin name>\OpenMW\` at its original paths, then deletes what omw2mwse wrote, from its manifest, each file only while its hash still matches (an edited one stays, with a WARNING line, and so does the manifest). Files in `Extras\<Mod>\` and `Off\<Mod>\OpenMW\` that the converter placed are handled the same way. The shared `MWSE\lib\omwcompat` runtime goes only when no converted mod is left in staging or in `Data Files`. A second `--undo` finds nothing to do.

**Empty `bugreports\` folders.** A mod's `bugreports\` folder is made when a bug report is written, and a report left with no sections is deleted without its folder. At the end of every run (`--apply`, a dry run or `--undo`), tidy removes a `bugreports\` folder that is empty and that it made or emptied during the run (absent, or holding files, when the run began). One that was already empty when the run began is not tidy's and stays, and so does one that has anything in it.

**Undo.** Asset repairs still keep their usual copies in the mod's `Off\` folder, and `--apply` also keeps every file they can change in `backups\tidy\<run>\assets\<mod>\`, journaled with its SHA-256 (a mod whose originals can't be kept is not repaired). `--undo` does not reverse a repair: it puts each original back at its own path and deletes the files the repairs made, including the mod's `Off\` copies. One `--undo` reverts the whole last `--apply` (conversions, assets, then Lua including MWSE core, then moves); run it again for the `--apply` before that (older journals: one entry at a time). A missing or altered original, or a file changed since the `--apply`, stops it before anything changes; `--force` overwrites changed files, but only when the original's hash matches. Files are written back in place, so Vortex hard links and plugin dates survive; still Purge before `--apply` and Deploy after `--undo`. The `vortex_tidy` sections `lua_apply` writes into bug reports are not undone.

MWSE's own core files that a KnownBugs rule names (KB3, KB4: `MWSE\core\mcm\components\pages\exclusionspage.lua`) are put into `Data Files` by MWSE's updater, not by Vortex, so the Lua check reads them in `Data Files\MWSE\core\` and patches them in place there, unless a staged mod ships MWSE itself (then that mod's copy is the one checked).

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `run_plan` | *(default)* | `vortex_tidy.py` | Scans the Vortex staging folder; compiles proposed moves, asset fixes, and Lua patches into `plans\vortex_tidy_plan.txt`. | Generated a staging plan proposing document relocations across staged mods |
| `apply` / `apply_main` | `--apply` | `vortex_tidy.py` | Works the plan out again and enacts it only when it lists the same actions as the plan file (else exit 2, the new plan written, the old kept as `vortex_tidy_plan.prev.txt`); asks first unless `--yes`; blanks the plan file (or cuts it down to what was not applied) and copies it to `backups\tidy\<run>\`. | Applied moves and DDS mipmap repairs across staged mod directories |
| `undo` | `--undo`, `--force` | `vortex_tidy.py` | Reads `generated\vortex_tidy_journal.jsonl` and reverts the whole last `--apply` (every journal head with its `apply` id; an older journal without the id: one entry at a time): the omw2mwse conversions first (`undo_conversion`: the files the converter wrote go, each only while its hash matches, and the original package comes back from `Off\<plugin name>\OpenMW\`), then the asset originals (`_asset_preflight` checks every original is there with its journaled SHA-256 and every file is as the `--apply` left it, else nothing is changed and exit 1; `_asset_undo` deletes the files the repairs made, then writes each original back in place with its old file time), then the Lua patches (mods' and MWSE core files, also preflighted), then the moves. `--force` overwrites files changed since, never without a matching original. Short-path records tidy made are dropped from `mwdialog_longpaths.json`, so `mwdialog_check --longpaths-undo` skips what is already back. What can't be put back stays in the journal for another try. | Put back a mod's original `.tga` and plugin and deleted the repaired `.dds` and its `Off\` copy |
| `apply_dummy_rule` | *(plan)* | `vortex_tidy.py` | Turns the asset check's `broken` / `brokenout` findings into `dummy` fixes; keeps `brokenout` (moved out only) when another copy of a model can win (`_copy_elsewhere`); leaves a type with no dummy as it is; skips tidy's own unchanged dummies (`tidy_dummies`). | `repair dummy meshes\x\bad_tree.nif` |
| `dummy_bytes` / `nif_dummy` / `generate_dummy` / `core_dummy` | `--no-coins` | `vortex_tidy.py` | The dummy for a path: a model gets the Dwemer coin from `Morrowind.bsa` (`coin_nif`), or the empty NIF with `--no-coins` or without the coin; a missing known core file (`Morrowind.bsa`, the coin, the `.kf` stand-in) also raises the one-time core-files warning (`core_warning`). Another type is made in code when it can be, else a core game file picked as described above (cached in `vortex_tidy_dummy_sources.json`). | A `.kf` dummy copied from an unused core animation |
| `make_dummies` | `--apply` | `vortex_tidy.py` | Copies each broken original to `Off\<plugin>\broken\<path>` (a dated name when a different file is there), reads it back, writes the dummy in place (a Vortex hard link stays one) and writes the `.tidy-dummy` mark. | Truncated `textures\x.dds` replaced by a 4x4 placeholder |
| `AssetJournal` | `--apply` | `vortex_tidy.py` | Before a mod's repairs: copies every file they can change (`_repair_candidates`: the file and same-named files beside it, an ASCII rename's new path, the mod's plugins, bug reports, `.repaired.sha256` notes, and for short paths the moved files and the models naming them) to `backups\tidy\<run>\assets\<mod>\`, reads each copy back, and journals it with its SHA-256 and file time. A copy that fails means the mod is not repaired. After: journals each file's new hash and the files and folders the repairs made; originals of files left unchanged are deleted again. | Kept a texture and the mod's `.esp` before a DDS conversion |
| `plan_mod` | *(internal)* | `vortex_tidy.py` | Plans one mod folder's moves (Docs, Screenshots, Extras, Grass, a hybrid mod's `Off\<plugin>\OpenMW\`, normal maps, the Off layout migration and the MAX_PATH list (`OL.plan_migration`, `OL.guard_moves`), `.omwaddon` renames, an OpenMW-only mod's whole-package move), or says why the mod is left alone (a `Data Files` folder or an `.exe`/`.dll`/`.asi` at its root). | `ModName\readme.txt` -> `ModName\Docs\ModName - readme.txt` |
| `find_converter` / `converter_python_problem` / `interpreter_version` / `run_converter` / `convert_apply` | `--apply`, `--convert-omwscripts`, `--no-convert-omwscripts` | `vortex_tidy.py` | Finds `omw2mwse` (PATH, then beside these tools), runs it with `--json` in `normal` (default) or `hardcode` mode (`--title` / `--author` from Vortex), reads each mod's verdict and plugin placement, undoes a `blocked` result at once, journals each conversion for `--undo`, and prints one NOTE per plugin the converter put in `Extras\` or `Off\`. | An OpenMW-only mod converted; `wildlife_getfight.esp`, which the converter judged obsolete and put in `Off\`, got a NOTE with its reason |
| `whole_package_moves` / `package_name` | `--apply` | `vortex_tidy.py` | Moves an OpenMW-only mod that is not converted to `Off\<plugin name>\OpenMW\` as one package, named the way the converter names it; an older `Off\OpenMW\<mod name>\` moves there too. | `Wild Attacks-54448-1-9` -> `Off\wildlife_attacks_npc\OpenMW\` |
| `undo_conversion` | `--undo` | `vortex_tidy.py` | Reverses one journaled conversion: puts the original package back, deletes the converter's files while their hashes match, removes the shared `omwcompat` runtime only when no converted mod is left. | The original `.esp` and scripts back at their own paths, the converter's loader gone |
| `remove_empty_bugreports` | `--apply`, `--undo`, dry run | `vortex_tidy.py` | Removes a `bugreports\` folder that is empty at the end of the run and that tidy made or emptied during it. | A `bugreports\` folder left empty after a report was deleted was removed |
| `blacklist` | *(internal)* | `vortex_tidy.py` | The built-in patterns plus `vortex_tidy_blacklist.txt` (one per line, wildcards allowed, matched against the mod's folder name, case ignored); made the first time `--apply` runs. | Left the Morrowind Code Patch's folder untouched |
| `is_doc` | *(internal)* | `vortex_tidy.py` | Detects document extensions that belong in `Docs\`. | Planned `Readme - Version 2.1.txt` -> `Docs\<mod name> - Readme - Version 2.1.txt` |
| `is_grass_plugin` | *(internal)* | `vortex_tidy.py` | Identifies MGE XE grass plugins (only `STAT`/`ACTI`/`CELL` records, at least 60% of the objects grass by model path or id); `plan_mod` moves them to `Grass\`, and `mwdialog_check` never loads one it finds in the load order. | Moved `Rem_AL_Grass.esp` to the mod's `Grass\` folder |

### The OpenMW Converter (experimental)

A separate project, the **OpenMW Converter** ([dejunai/openmw-mwse](https://github.com/dejunai/openmw-mwse)), is aimed at turning OpenMW-oriented content (OpenMW Lua scripts) toward MWSE. It is experimental and in early development, and its repository is private for now; see that project's own README for current status. These tools do not need it and do not include it.

It is not the same as tidy's own OpenMW handling in a staging folder: the `.omwaddon` rename, a hybrid mod's OpenMW files in `Off\<plugin>\OpenMW\`, and OpenMW-only normal maps in `Off\<plugin>\normal maps\`. The only link is the one described above: when `omw2mwse` is found, `vortex_tidy --apply` runs it on OpenMW-only mods in `normal` mode (`--convert-omwscripts=hardcode` picks the other mode); when it is not, those mods are set aside whole in `Off\<plugin name>\OpenMW\`. The converter's output is recognised by its markers (`omw2mwse-manifest.json`, the "generated by omw2mwse" loader header, a `require` or registration of `omwcompat`, `MWSE\lib\omwcompat*`), not by folder names. `--play`, luafix, the scans and tidy all leave it alone: `--play` does not list a converted mod as unknown and its prune keeps converter files, and luafix never checks or patches them, with or without `--include-own`.

---

## 10. MWSE Lua AST Static Analysis, Hardening & Targeted KnownBugs

### Architectural Narrative
Morrowind Script Extender (MWSE) allows modders to execute Lua code directly inside the game engine. However, third-party Lua mods frequently suffer from unhandled exceptions, nil dereferences during game loads, uncontrolled event recursion, and memory leaks. Crude regex search-and-replace tools cannot safely patch Lua because code structure, comments, and nested closures alter execution flow.

`mwdialog_luafix.py` incorporates a complete, pure-Python lexical scanner and recursive-descent parser (`mwdialog_lua.py`) specifically supporting Lua 5.1 and LuaJIT syntax. It parses Lua files into an Abstract Syntax Tree (AST), performs static semantic analysis, and applies defensive code hardening:
1. **Nil Guards**: Injects defensive checks before accessing chained properties (e.g. ensuring `e.reference` is non-nil before dereferencing `e.reference.object`).
2. **Priority Compression** (`G1`): Event handler priorities whose absolute value is `priorityLimit` (10,000) or more are made ordinary, keeping their relative order (`compress_priority` in `mwdialog_luafix.py`): `base + 100 * log10(|p| / limit)`. With the default `priorityMode` `keepOrder` that is 9000-9999 (10000 -> 9000, 1e6 -> 9200, 1e9 -> 9500, `math.huge` -> 9999; a negative priority the same, negated), so the mod still runs before every ordinary priority. `priorityMode` `clamp` uses `priorityClampTo` (1000) to 1999 instead, like the old mwguard's runtime clamp.
3. **Log Shimming** (`F1`): For a mod with log-spam signs (logging every frame, in loops, in frequent events, debug flags on; `--lua-log all` takes every mod that logs, `off` none), injects a shim around `print` and `mwse.log` (not `tes3.log`): the mod's lines past its allowance go to `Data Files\MWSE\logs\<mod>.log` (by default at most 25 lines a second, rotated at 2 MB keeping one `<mod>.old.log`), while errors and lifecycle lines still reach MWSE.log. Mods `mwguard` covers are left out unless `--log-shim-always` (or `logShimWhenMwguard`). The current shim is version 6 (`SHIM_V = 6`). Its lifecycle allowlist uses tight patterns such as `"] started"` and `"has started"`, not the bare substring `"start"`, so lines like "Dialogue started with..." are not forwarded to MWSE.log.
4. **Targeted KnownBugs (KB1-KB17 and KB19-KB51), plus KP1-KP4 and KR1-KR3**: Hardens high-profile third-party mods against severe documented defects. There is no KB18: the conflict between abot's WBSR and tavern bard songs is handled at runtime by `mwsaveguard.wbsr_bard`, not by patching WBSR's Lua. KB20-KB50 reproduce local hand repairs of released third-party Lua (asset paths, syntax, nil guards, handlers that register again on every load), kept as exact text in `mwdialog_luafix_kb.py`. KB51 is an upstream MUSE 2.02 syntax bug (a newline between `MUSE.DebugLog` and `(`).
5. **MWSE performance and persistence checks** (report only, from the MWSE docs' tips): `G6` `tes3.getReference` (it scans every cell's references) in a frequent handler or a fast repeating timer; `G7` `tes3.rayTest` every frame or in a frequent handler with no `maxDistance`, no `root` (`worldObjectRoot`, `worldPickRoot`, `worldLandscapeRoot`), or with `accurateSkinned`; `R1` a `timer.start` callback that uses a reference captured from its event with no `tes3.makeSafeObjectHandle` or `:isValid()` check; `T1` a named timer callback (`callback = "mod:name"`) that no file of the mod registers with `timer.register`; `P1` `ref.data` written on a reference the code shows is not an actor, with no `ref.modified = true` (the data is not saved). `V1` now needs vector evidence for the right-hand operand (the 92 vector fields and functions in MWSE's docs, `tes3vector3.new`, `.position` of a reference, `:normalized()`/`:copy()`/`:lerp()`, or a local assigned once from one of those) and also covers `n + v` and `n - v` (rewritten `v + n` and `-v + n`): plain number math such as `2 * math.pi` or `0.9 * vol` is no longer flagged. `H2` no longer flags timers started in `loaded`, of any type: MWSE clears real, simulate and game timers just before that event. `D1` also flags an `infoFilter` handler that does costly work (string calls, `tes3.*` lookups) before it checks `e.passes`; it is fixed (an early return) only when the handler has no other effects, else reported. Noise filters: `G6` leaves `tes3.getReference("player")` alone (MWSE answers it without a scan); a custom event fired only from a `loaded` handler counts as `loaded` for `H2`; Lua under `MWSE\\backups\\` and in folders switched off by name (`.disabled`, `.mohidden`, `-off`, `_off`, ` off`) is skipped. With Data Files known, a file nothing names (no `require`/`include`/`dofile`, module name, path or bare name in any MWSE Lua, and no dynamic prefix that could reach it) is listed as unreferenced: it is still checked and patched, but its report-only findings are set aside under that line, not counted.

### Targeted KnownBugs Catalog (KB1-KB17 and KB19-KB51)

- **KB1 (`AttendMeMWSE/followers.lua`)**: `refresh()` reads `.mobile` on references kept from the last pass; a deleted one raises `sol: received nil for self`. The patch wraps that access in `pcall`.
- **KB2 (`UI Expansion/menudialog.lua`)**: The topic updater queries an empty property key, so actor-unique topics never reuse their cached info. The patch uses `"MenuDialog_UIEXP_info"`.
- **KB3 (`MWSE Core`: `core\mcm\components\pages\exclusionspage.lua`)**: ExclusionsPage destroys `outerContainer` and then dereferences that destroyed element's parent. The patch keeps the parent first.
- **KB4 (`MWSE Core`: `core\mcm\components\pages\exclusionspage.lua`)**: ExclusionsPage builds one UI element per item, unbounded (thousands with Tamriel Data). KB4 rewrites the generator to pages of 100 per column. All of KB4 applies, or none of it. This is separate from KB3.
- **KB5 (`MUSE 2.02/music/muse.lua`)**: Two MCM calls split a parenthesized argument after the method name; LuaJIT rejects the file.
- **KB6 (`OpenUI - MWSE/mod.lua`)**: The enchanted weapon HUD dereferences `weapon.itemData.condition` before checking that `itemData` exists.
- **KB7 (`Friends & Frens/main.lua`)**: `%Sign` is not a dialogue variable; the patch substitutes the companion's script-local birthsign on `infoGetText`.
- **KB8 (`Tamriel Data/magic.lua`)**: Invisibility detection read actors' spell lists while a save was loading (raw ids such as `0x736f6867`). It now waits for `loaded`.
- **KB9 (`Directional Sunrays/main.lua`)**: The interior sunray pass called the engine's `updateSun` through FFI with no current weather; it now checks first.
- **KB10 (`Robe'n'Hood/main.lua`)**: `isBadWeather` / hat helpers dereference `weather.index` / `weather.name` when `tes3.getCurrentWeather()` is still nil after a new game started from inside a session.
- **KB11 (`Nocturnal Moths/util/init.lua`, `effectmanager.lua`, `main.lua`)**: `util.isNiceWeather` indexes `currentWeather.index` without a nil check, and `EffectManager` caches `activeEffects` across saves; the patch also resets that cache on load.
- **KB12 (`Tamriel Data/weather.lua`)**: `if weather and weather.index == ... or weather.index == ...` leaves the `or` branch unguarded when `weather` is nil; `silenceCreatures` also indexed a nil weather.
- **KB13 (`UI Expansion/common.lua`)**: `createElements` registers destroy cleanup for icon and button filter blocks but not for `searchBlock`, so `menuEnter` calls `clearFilter()` on destroyed UI after a new game or load.
- **KB14 (`Nocturnal Moths/util/init.lua`, `effectmanager.lua`)**: `util.playSound` starts a looped `R0_moths_fluttering` without `tes3.getSoundPlaying`, and the KB11 reset dropped `activeEffects` without `tes3.removeSound`, stacking copies after a load.
- **KB15 (`AURA/common.lua`)**: `common.getTrackPlaying` trusts `tes3.getSoundPlaying`, which the engine often answers as false for a still-playing 3D loop, so AURA's door/window timers start the sound again.
- **KB16 (`Flies/main.lua`)**: On `cellChanged`, Flies plays a looped `'Flies'` sound on every qualifying corpse without `tes3.getSoundPlaying` or a stop on deactivate/load, stacking copies. mwsoundguard cannot see this: it skips NPCs and creatures.
- **KB17 (`Tel Raloran/levpad.lua`)**: `addLevitation` plays a looped 2D `'forcefield'` without `tes3.getSoundPlaying`, and there is no `loaded` handler to clear it.
- **KB19 (`Keg Drip/main.lua`)**: `refreshCell` used a 0.01-unit position test, deleted and recreated the drip activator on a miss, and restarted `dripKeg`. The patch loosens `samePlacement`.
- **No KB18**: WBSR's save handler blocks any `Vo\` lip-sync, including bard songs. That is handled by `mwsaveguard.wbsr_bard`, not a luafix patch of WBSR.

- **KB20** (Magicka Expanded `lib\operatorjack\magickaexpanded\effects\{alteration,conjuration,destruction,illusion,mysticism,restoration}.lua` and `mods\operatorjack\magickaexpanded-lorefriendlypack\effects\banishdaedraeffect.lua`): default effect icons and particle textures named `.tga` files that ship as `.dds`.
- **KB21** (DRIP `mods\mer\drip\customeffects\effects\selfrepair.lua`, `thorns.lua`): `vfx_alt_glow.tga` ships as `.dds`.
- **KB22** (OAAB Grazelands `mods\oaab\grazelands\effects\flawedsummondaedrotheffect.lua`): `vfx_conj_flare02.tga` ships as `.dds`.
- **KB23** (OAAB Grazelands `mods\oaab\grazelands\achievements.lua`): `tes3.getGlobal()` can be nil when the achievement globals are not loaded; missing values fall back to player data.
- **KB24** (The Garden of Dreams `mods\x32\summons\interop.lua`): `vfx_conj_flare02.tga` ships as `.dds`.
- **KB25** (SSQN Patches `mods\cz\ssqnpatches\main.lua`): four quest icons name `BA_Vamp.dds`; the shipped icon is `BA_Vampire.dds`.
- **KB26** (SSQN LE `mods\ssqn\iconlist.lua`): `icons.MT_S` names `\Icons\SSQN\MT\MT24MT_S.dds`; the icon ships as `\Icons\SSQN\MT24MT_S.dds`.
- **KB27** (Map Icons `mods\spammer\map icons\skyicons.lua`, `vanillaicons.lua`): the chapel icon names `temple.dds.dds`.
- **KB28** (Creatures and Critters `mods\danae\cc\main.lua`): the `_plume` ids list is missing three commas, so the file does not compile.
- **KB29** (Dynamic Object Replacer `lib\dor\gpobjectreplacer.lua`): swapping a reference copies item data and cell state without nil checks.
- **KB30** (Secrets of the Crystal City `mods\aa22\music\main.lua`): `musicSelectTrack` reads `tes3.player.cell` before a game is loaded.
- **KB31** (Buying Game `mods\buyinggame\common.lua`, `main.lua`): export/import, restock and barter handlers index the player cell, region, service actor and reference data without nil checks.
- **KB32** (Companion Leveler `mods\companionleveler\functions\common.lua`): `validCompanionCheck` reads `mobileActor.object.name` before checking the actor exists.
- **KB33** (Imperial Stables `mods\danae\stables\main.lua`): resident and activate handlers index `.data`, `.object` and `.cell` without nil checks, and write Lua data on references that do not support it.
- **KB34** (Elemental Effects `mods\elemental effects\main.lua`): body-part and restore-health handlers index `bodyPartManager`, `data` and `sceneNode` without nil checks.
- **KB35** (Essential Indicators `mods\essential indicators\main.lua`): `essentialSwitch` iterates `tes3.getPlayerCell()` without checking for a cell.
- **KB36** (Improved Global Map Markers `mods\improved global map markers\main.lua`): handlers read `tes3.getPlayerRef().data` and cleared-cell lists without nil checks, and use the undefined global `typeCell`.
- **KB37** (Lucid Disturbing Dreams `mods\kdd\lucid-disturbing-dreams\main.lua`): each load registers journal and `spellTick` handlers again, so they stack; `tes3.getJournalIndex` can return nil.
- **KB38** (Morrowind Achievement Collection `mods\mac\playerdata.lua`): the book handler concatenates a boolean into a log line, and counters index player data without nil checks.
- **KB39** (Bardic Inspiration `mods\mer\bardicinspiration\controllers\lutecontroller.lua`): copying lute item data assigns to `itemData.data` when that table does not exist.
- **KB40** (Hidden Robe Armor `mods\mer\hiddenrobearmor\main.lua`): the `loaded` handler compares `e.reference` (which loaded events do not have) with the player, so the equipment refresh never runs.
- **KB41** (Just Drop It `mods\mer\justdropit\main.lua`): death/activate handlers index reference data without checking the reference supports Lua data.
- **KB42** (MUSE 2.02 `mods\music\depthsnair.lua`, `main.lua`, `muse.lua`): jump/cell checks and music selection read `tes3.player.mobile` and the cell without nil checks; MUSE switched to a folder before checking it has music.
- **KB43** (Memento Mori `mods\ossuaries of the ghostfence\calm ghosties.lua`, `lights out.lua`): each load starts another endless calm timer and registers `simulate` again; lights out reads the player cell and a trigger reference without nil checks.
- **KB44** (The Achievement Framework `mods\sb_achievements\main.lua`): progress text and the hidden-achievement group call `progress()`/`progressMax()` and index `menuAchievements[category][256]` without nil checks.
- **KB45** (Onion `mods\sb_onion\main.lua`): equip/unequip handlers index the reference's race and Lua data without nil checks.
- **KB46** (Small QoL Improvements `mods\spammer\qol improvements\main.lua`): the scroll equip handlers also run for NPC equips and call `tes3.mobilePlayer:equipMagic` with the NPC's item.
- **KB47** (MWSE Set Bonus `mods\static\setbonus\conditions.lua`, `main.lua`, `setbonusflags\main.lua`): condition watchers keep deleted references; `enchantedBaseId` reads `itemData.data` on item data that is not initialised during equip.
- **KB48** (MWSE Lanterns `mods\syanide\magiclanternlights\main.lua`): the lantern equip check indexes `npcRef.object` without checking it is an NPC.
- **KB49** (Animated Dialogue `mods\tauer\animated-dialogue\services\actors\actorposeblender.lua`): the pose blender blends the root bones, which flips the actor 180 degrees against the engine's facing when dialogue ends.
- **KB50** (Watch the Skies, 15 files under `mods\tew\watch the skies\`: `main.lua`, `util.lua`, `mcm.lua`, `components\common.lua`, `components\events.lua`, and `services\{cloudspeed,dynamicweatherchanges,interiortransitions,particleamount,particlemesh,seasonaldaytime,seasonalweather,skytexture,variablefog,variablerain}.lua`): services capture `tes3.worldController.weatherController` when the file loads and index weathers, regions and timers without nil checks; service timers are started again on every init without cancelling the last one.
- **KB51** (MUSE 2.02 `mods\music\cell.lua`, `combat.lua`, `interior.lua`, `region.lua`): a newline between `MUSE.DebugLog` and `(` is ambiguous syntax in LuaJIT, so those four files never load. The rule joins the call onto one line. Upstream in MUSE 2.02 and the official Patch for MUSE 2 v2.02.

### Rule catalog

Every finding has a rule id and a confidence: `high` findings are patched by `--apply`, `medium` ones only with `--level medium` (`--lua-level medium` in `vortex_tidy`), the rest are only reported. Rules marked *fix* can be patched when the case is certain; otherwise the finding stays a report, with the reason. A patch is a few token-span edits: encoding, line endings and every line number stay the same (helpers go at the start of line 1), and the file is rewritten through the same handle so Vortex's hard links keep sharing it.

| Rule | What it finds | Fix / report |
| :--- | :--- | :--- |
| `G1` | Absurd event priority (`\|p\| >= priorityLimit`) | fix: compressed, order kept |
| `G2` | A per-frame handler (`simulate`, `simulated`, `enterFrame`) that only polls state | fix: runs every `minInterval` (0.35 s) |
| `G2S` | A per-frame handler `G2` would leave at medium (it calls code luafix can't see, or writes game state) that scans the world every frame (`tes3.rayTest`, `:iterateReferences()`, `tes3.getReference` other than the player, `tes3.findActorsInProximity`, `tes3.iterateObjects`) and shows nothing frame-critical | fix: runs every `minInterval` (0.35 s) |
| `G3` | A repeating timer faster than 0.35 s whose callback only polls | fix: 0.35 s |
| `G4` | A one-shot handler (done flag) that never unregisters | fix: unregisters once the flag is set |
| `G5` | Per-frame costs: uncached lookups, config/file I/O, allocations, message boxes every frame | report |
| `G8` | The same literal `tes3.messageBox` in a handler of an event that fires per hit or per NPC decision (`damage`, `attack`, `spellTick`, `calcHitChance`, `determineAction`, `combatStarted`...); user-action events (`itemTileUpdated`, `uiObjectTooltip`, `activationTargetChanged`) are left alone | fix: shown at most once per `messageInterval` (10 s); in a per-frame handler: report |
| `G6` | `tes3.getReference` in a frequent handler or a fast repeating timer | report |
| `G7` | `tes3.rayTest` every frame or in a frequent handler with no `maxDistance`, no `root`, or `accurateSkinned` | report |
| `A1` | `ref.data.x` used without a guard | fix: nil guard |
| `A2` | A keybind's `.keyCode` (`.mouseButton`...) read with no check | fix: nil guard |
| `A3` | A tes3 lookup that can return nil (`getObject`, `getReference`, `getPlayerTarget`, `findMenu`...) used without a check | fix: nil guard |
| `A4` | An event field that can be nil (damage `e.attacker`, attack `e.targetMobile`, cellChanged `e.previousCell`...) used without a check | fix: nil guard |
| `A5` | An NPC's `.head` / `.hair` used without a check | fix: nil guard |
| `B1` | A UI element used after `:destroy()` | report |
| `C1` | An engine console command sent through `tes3.runLegacyScript` | report |
| `D1` | An `infoFilter` handler doing costly work before it checks `e.passes` | fix: early return (only when the handler has no other effects) |
| `F1` | Log spam | fix: log shim |
| `F2` | A logger created at DEBUG/TRACE level | fix: INFO |
| `H1` | `event.register` inside a load/cellChanged/... handler | fix for a named handler (`isRegistered` guard); report for an anonymous one |
| `H2` | A repeating timer started in a handler that runs again, never cancelled (not `loaded`) | report |
| `H3` | Global variables a mod creates by accident | report |
| `H4` | Game data used at file load, before `initialized` | report |
| `H5` | `require` cycles inside a mod | report |
| `H6` | `tes3.messageBox` inside a loop | report |
| `H7` | `X.f()` through `local X = require(...)` of the same mod, whose table never gets `f` | report |
| `I1` | A `.tga`/`.bmp` it names is gone and a `.dds` of that name is there | fix: names the `.dds` |
| `I2` | A repeating real-time timer that redraws UI keeps running through a save | fix: skips while saving |
| `I3` | A config written inside a save handler | fix: written the frame after |
| `L1` | A `while` loop that walks links (`x = x.next`) or counts down by a computed step | fix: capped at 10000 turns |
| `M1` | An `enterFrame` handler (it also fires in menus) with no UI work | fix: returns in menu mode (not added when the handler already returns in menu mode; `M1` and `G2` both read the handler's leading guards, so the second pass never adds the gate twice) |
| `U1` | A per-frame handler setting `.text` of an element it made with `:createLabel` / `:createBlock` to a plain value (a name, a field, a literal) every frame | fix: `if x.text ~= v then x.text = v end` |
| `P1` | `ref.data` written on a non-actor reference with no `ref.modified = true` | report |
| `R1` | A timer callback holding a reference from its event with no safe handle / `:isValid()` check | report |
| `S1` | `tes3.getSoundPlaying{ reference = <not the player> }` used to decide a restart | report (`mwsoundguard` caps it) |
| `T1` | `timer.start{ callback = "name" }` with no `timer.register("name", ...)` in the mod | report |
| `V1` | `number * vector`, `number + vector`, `number - vector` (with vector evidence) | fix: `v * n`, `v + n`, `-v + n` |
| `KB<n>`, `KP<n>`, `KR<n>` | A documented bug in a named mod or MWSE core file | fix: its exact replacement (below) |

Never touched: MWSE's own code (except the exact KnownBugs fingerprints in named core and lib files) and the suite's own mods. The first-party list is `Data Files\MWSE\mods\mwsuite\ownmods.json` (ships with mwsuite as `lua tools\MWSE\mods\mwsuite\ownmods.json`; schema `{"version": 1, "ownMods": [...]}`). If that file is missing from a deployed mwsuite folder, unreadable, or not version 1, luafix uses a built-in fallback list (including `mwconsole`, not `mweffectinspector`) and prints a warning. `ownMods` is who we are; `exemptMods` (in the settings / `mwguard.json`) is a user list of third-party folders to leave alone. Both are skipped unless `--include-own`; even then only A1-A5 and F1 (`OWN_FIX_RULES`) are applied to them (both are exempt from the log shim, so for them F1 only takes an old shim back out). An original that does not compile is left alone unless an exact KnownBugs repair makes it compile (also when this tool's own parser rejects it). Results are cached by content (`--no-cache` reads every file again); the KnownBugs fingerprints and the settings are part of the cache key.

### Settings

luafix reads, in order (later wins): its built-in defaults, `Data Files\MWSE\config\mwguard.json` (only the keys it shares with `mwguard`), that file's `"luafix"` section, then `generated\mwdialog_luafix.json`. Keys: `priorityLimit` (10000), `priorityMode` (`keepOrder` / `clamp`), `priorityClampTo` (1000), `minInterval` (0.35), `exemptMods`, `log` (the shim: `scope`, `perSecond` 25, `maxMB` 2, `keepOld` 1, `flushSeconds` 2, `lifecycleMax` 5, `keepPatterns`, `exemptMods`...), `logSpamGuard`, `enabled`, `logShimWhenMwguard`, `skipKnown` (KB/KP/KR ids to report but never apply), `skipRules` (generic rule ids such as `G2S`, `G8`, `U1` to report but never apply) and `messageInterval` (10, seconds between two of `G8`'s message boxes). The plan header names the files it read.

The syntax checker is found in this order: `--luajit`, `tools\luajit\luajit.exe` (game folder, then the scripts' folder), `luajit` / `luac5.1` / `luac` on PATH, then the `lupa` Python package. With none, nothing is patched (`--apply` exits 2) unless `--no-syntax-check`. Each run also writes `generated\mwdialog_luafix_known_bugs.txt` (every KnownBugs fingerprint found: DETECTED / patched / NOT PATCHED); `--json` writes the findings as JSON, `--diff` prints each patch, `--all` also lists what was left alone on purpose.

### Core-only entry point (`--core-only`)

For a caller that only wants MWSE's own core files repaired (MWManager runs it after `MWSE-Update.exe`, and before `--play`), `apply_core_known_bugs(data_dir, dry_run=False, *, game_dir=None, cfg=None, checker=<auto>, no_syntax_check=False, journal=None, backup_root=None)` returns a list of `CoreResult`, one per core file a KnownBugs rule names (`known_core_files()`: KB3/KB4 on `core\mcm\components\pages\exclusionspage.lua` today). It reads and patches nothing else and writes no plan file. `core_data_dir(path)` finds `Data Files` from the Morrowind folder or from `Data Files` itself. Importing the module has no side effects, and every path is an argument.

A write goes through `apply_report`, so it is the same as `--apply`: the original is copied to `backups\luafix\<run>\` first, the journal line carries the before/after SHA-1, a file that changed since it was checked is refused, the patched text must pass the syntax checker (no checker: refused, unless `--no-syntax-check`), and `--undo` puts the run back. The journal's run line also carries `"core_only": true` and `"entry"` (the run's folder name), which is the `journal_entry` of each written file.

| `status` | Meaning |
| :--- | :--- |
| `applied` | Patched (with `dry_run`: would be; `written` says which). |
| `already-patched` | Our header (`--[[localpatch N: KB3 KB4]]`) is at the top and no fingerprint is left. |
| `no-match` | No fingerprint and no header: MWSE fixed or changed the file. |
| `partial` | A rule that applies whole or not at all (KB4) matches only some of its parts. Nothing is written, not even the rules that do match. `parts_matched` / `parts_total` count the parts of every rule on the file. |
| `refused` | Nothing written; `reason` says why (file not found, no syntax checker, the checker rejects the patch, the file changed after it was checked, an I/O error). |

`--core-only [FOLDER] [--dry-run] [--json FILE|-] [--luajit EXE] [--no-syntax-check]` prints a summary and exits `0` (every file applied, already patched or no match), `1` (lock held), `2` (any file refused; wins over partial), `3` (partial, none refused) or `4` (no such folder); a bad option combination exits `2` like any argparse error. `--json -` prints only the JSON on stdout (the summary goes to stderr):

```json
{"tool": "mwdialog_luafix", "mode": "core-only", "version": 5, "dry_run": false, "data_dir": "<Data Files>", "journal": "<journal path>", "exit_code": 0,
 "counts": {"applied": 1, "already-patched": 0, "no-match": 0, "partial": 0, "refused": 0},
 "files": [{"path": "<Data Files>\\MWSE\\core\\mcm\\components\\pages\\exclusionspage.lua", "rel": "core/mcm/components/pages/exclusionspage.lua",
   "kb_ids": ["KB3", "KB4"], "status": "applied", "parts_matched": 4, "parts_total": 4, "reason": "patched KB3, KB4",
   "journal_entry": "20261125-190000", "dry_run": false, "written": true, "backup": "<backup folder>\\...\\exclusionspage.lua",
   "sha1_before": "e059dc3c...", "sha1_after": "eda5739b...",
   "kbs": [{"kb": "KB3", "state": "matches", "parts_matched": 1, "parts_total": 1}, {"kb": "KB4", "state": "matches", "parts_matched": 3, "parts_total": 3}]}]}
```

A rule's `state` is `matches`, `partial`, `already-patched`, `no-match` or `skipped` (listed in `skipKnown`). A write takes the same two locks as `--apply`; a dry run takes none.

### Targeted frame-drain (KP) and reference-safety (KR) patches

Applied like the KB patches (exact text, whole or not at all, same header and checks), labelled `(Known Perf)` and `(Ref Safety)` in the report. They are on by default; to leave one out, list its id in `"skipKnown"` (in `mwguard.json`'s `"luafix"` section or `mwdialog_luafix.json`), for example `"skipKnown": ["KP2"]`: it is then reported as not applied.

- **KP1 (`AttendMeMWSE/actions.lua`)**: while the command wheel is open, `onSimulate` and `resolveMoveContext` cast the same crosshair ray in one frame. `rayWorld` keeps the hit's reference for the rest of that frame (the simulate handler is registered through `localpatch_frameRays`, which clears the memo after it returns or errors), so a second cast with the same `ignore` reuses it. Only the reference is kept: MWSE reuses the result object at the next `rayTest`. About 4 casts become 2 on frames where both run.
- **KP2 (`AttendMeMWSE/recruit.lua`)**: in recruit mode `onSimulate` cast a ray and rebuilt the ring layout every frame; it now runs one frame in three (about 20 Hz at 60 fps).
- **KP3 (`Keg Drip/main.lua`)**: `normalizeMesh` (three string calls) ran for every reference at each refresh (once a second as shipped); its result is now kept per mesh name.
- **KP4 (`G7 Containers/main.lua`)**: `checkData` called `tes3.getReference` (a scan of every cell's references) for the linked container on every tile update, tooltip and equip; it now keeps a safe handle and looks again only when the handle is invalid or the reference is deleted.
- **KR1 (`AURA/fader.lua`)**: the fade timer's callback used the reference it captured; it now stops when that reference's safe handle is no longer valid.
- **KR2 (`AttendMeMWSE/actions.lua`)**: same for the follow tick (`forceFollow`) and `travelThen`'s timer.
- **KR3 (`AttendMeMWSE/recruit.lua`)**: same for the recall visual's timer.
- **Looked at and left alone**: Seph's Enemy Bars `rayTest` (already a 0.06 s timer chain), AURA `floraSounds` (0.2 s, only while moving, short ray; a narrower root could miss what it looks for), Realistic Repair `stations.lua` (4 Hz short ray; dropping `accurateSkinned` changes which actors it hits), Crafting Framework `Positioner` (a per-frame ray is how placement works).

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `check_paths` | *(default)* | `mwdialog_luafix.py` | Scans Lua scripts, parses ASTs, checks rules and KnownBugs, and feeds the plan written as `plans\mwdialog_luafix_plan.txt`. | Generated a Lua plan flagging nil guards and KnownBug patches |
| `apply_report` | `--apply` | `mwdialog_luafix.py` | Enacts planned Lua patches; refuses a file whose content hash changed since it was checked; the original goes to `backups\luafix\<run>\` and every write is journaled (`generated\mwdialog_luafix_journal.jsonl`, with before/after hashes). | Patched `MWSE\core\mcm\components\pages\exclusionspage.lua` with KB4 |
| `apply_core_known_bugs` | `--core-only` | `mwdialog_luafix.py` | Checks and patches only the MWSE core files a KnownBugs rule names (KB3/KB4), with no plan file, through the same backup, journal, hash check and `--undo` as `apply_report`; returns one `CoreResult` (status `applied` / `already-patched` / `no-match` / `partial` / `refused`) per file. `--dry-run` writes nothing. | MWManager re-applied KB3/KB4 after `MWSE-Update.exe` |
| `undo` | `--undo` | `mwdialog_luafix.py` | Restores the files the last `--apply` patched, from the journal (the plan file plays no part). A file changed since it was patched is left unless `--force`. | Reverted an experimental Lua patch |
| `tokenize` | *(internal)* | `mwdialog_lua.py` | Lexical scanner producing Lua 5.1/LuaJIT tokens, comments, and literals. | Tokenized a large UI Expansion module |
| `parse` | *(internal)* | `mwdialog_lua.py` | Recursive-descent parser generating the Abstract Syntax Tree. | Constructed the AST for a patched script |
| `compress_priority` | `--apply` | `mwdialog_luafix.py` | Compresses `event.register` priorities with `\|p\| >= 10000` into 9000-9999 (`keepOrder`, the default) or 1000-1999 (`clamp`), keeping order. | Compressed priority `1000000` to `9200` |
| `log_shim` | `--lua-log`, `--log-shim-always` | `mwdialog_luafix.py` | Injects the version-6 shim around `print` / `mwse.log` that sends a mod's lines past its allowance to its own log. | Redirected a per-frame combat logger into `Data Files\MWSE\logs\<mod>.log` |
| `verify_patch` | *(internal)* | `mwdialog_luafix.py` | Compiles the patched file with LuaJIT (or luac / lupa) before it is kept. | Verified syntax of patched Lua files |

---

## 11. Load Order Sorting, Rule Management & Master Integrity

### Architectural Narrative
Plugin load order determines which mod wins conflicting record edits. The sorting engine lives in `mwdialog_check.py` (`run_sort`, `compute_order`). `mwdialog_loadorder.py` parses mlox-style rule files and stores the intended order in `generated\mwdialog_load_order.txt` (and writes `[Game Files]` when asked). It integrates mlox-style rules from `Morrowind\mlox\mlox_user.txt` and `mlox_base.txt`, plus user overrides in `generated\mwdialog_check.rules.txt` (made with an explanatory header the first time `--sort` runs). Files are read in that order (your rules file first, then the automatic content rules, then mlox's), and a rule that contradicts an earlier one is skipped, so yours win. A plugin always loads after its masters, and every `.esm` before every `.esp`. Dates are set one day apart from 2000-01-01; `--restore-dates` puts the previous dates back (`mwdialog_loadorder_undo.txt`).

Key sorter features:
- **Rule blocks** (one plugin per line, `;` comments, case ignored, wildcards `*` and `?` and mlox's `<VER>`): `[Order]` (each loads before the next), `[NearStart]` (as early as masters allow, in this order), `[NearEnd]` (as late as possible; the FIRST one listed loads LAST, mlox's convention), and `[Exact]` (these load one right after the other, in exactly this order, with nothing in between; exact names, no wildcards; not applied, with a note, if masters make it impossible). An entry that isn't an `.esp`/`.esm` name (or a wildcard that can match one) is an ERROR in your rules file (the sort stops, exit 2) and a WARN in mlox's. `--sort` keeps two sections in your file itself: `[Context]` at the top (the patch-after-mod rules it worked out; every line a comment, rewritten on every sort) and the rules `--cell-conflicts` adds.
- **Built-in placement**: `mwdialog_check - ESM fixes.esp` loads as early as its masters allow; `XE Sky Variations.esp` (when installed), the auto-merge, the old performers patch, `mwdialog_check PlaceholderCell ESP Patch.esp` and `mwdialog_check Multipatch.esp` load at the very end, in that order. Leave them out of your rules file.
- **`[Exact]` repair**: before any other command, a run checks whether an `[Exact]` group came apart (a plugin in it was saved or replaced since the last sort and got a new date) and runs `--sort --yes` first (`--dry-run`: report only).
- **Automatic content rules**: Unless `--no-content-order` is passed, `--sort` adds patch-after-mod `content_rules` (a small `.esp` most of whose records are another `.esp`'s loads after it) and dialogue cell-filter rules from `mwdialog_cellorder.py`. Unless `--no-add-masters`, a patch `.esp` that changes another mod's records without naming it as a master gets it added as a real master (recorded in `mwdialog_added_masters.json`; taken out again if your own rule later puts the patch first, or the master is gone).
- **`--update-rules`**: Does not download or fetch anything. `run_update_rules` reads the local rule sources (`mwdialog_check.rules.txt`, then `Morrowind\mlox\mlox_user.txt` and `mlox_base.txt`), asks `compute_order` which mlox `[Order]` steps were already skipped because a master, your rules file, a context rule, or an earlier mlox rule said otherwise, or because a step would put an `.esp` before an `.esm`, and then edits only the mlox files: the contradicted step is commented out or the rule is split, a `;; mwdialog_check --update-rules <stamp>:` note is inserted, and the old file is saved with `stamped_backup`. Your `mwdialog_check.rules.txt` is only printed for you to fix by hand. `--dry-run` shows the plan and writes nothing.
- **Master Compatibility Guard (`mwdialog_mastercheck.py`)**: Analyzes compatibility patches to determine if they were built for the currently installed version of their master. If a patch was built for a different master, `--disable-mismatched` takes it out of the load order.
- **The intended order** is `generated\mwdialog_load_order.txt`, with plugin dates set one day apart. It is made from `Morrowind.ini`'s `[Game Files]` the first time (not saved on a `--dry-run`); an empty or damaged one is replaced by its backup. `--plugins` and `--openmw-cfg` (its `content=` and `data=` lines) replace it for one run. MGE XE grass plugins found in the list (only `STAT`/`ACTI`/`CELL` records, mostly grass) are left out of every run.
- **Writing `Morrowind.ini`**: `apply_load_order_to_ini` writes the list into `[Game Files]` when a run that changed it ends normally (not after a crash or Ctrl+C, not with `--dry-run`, `--plugins` or `--openmw-cfg`), and `--play` writes it again. Plugins not in Data Files are left out. Backups: `backups\legacy\Morrowind.ini.mwdialog-original.bak` (the ini before the tools first changed it), `backups\Morrowind.ini.mwdialog-play.bak` (the latest previous version), and a dated `backups\legacy\Morrowind.ini.mwdialog-<date>.bak` for each write. Vortex rewrites the ini through Windows' 32,767-character section limit and can cut a long list: when `mwdialog_load_order.txt` does not exist yet and the ini's list looks cut (`truncated_game_files`), the run does `--add-all-esp --sort --yes` first.
- **`--add-all-esp`** puts every `.esm`/`.esp` in Data Files into the list, masters first, then by date, except the plugins `mgeXE.toml`'s `grass_plugins` names, plugins an auto-merge replaces (`mwdialog_merged.txt`), and plugins `--fix` (`mwdialog_disabled.txt`) or `--redundant` (`mwdialog_redundant.txt`) turned off.

### Starting the game (`--play`)

`launch_game` (in `mwdialog_check.py`) runs after every other step given (only when they ended with exit 0 or 1; skipped with `--dry-run`), or on its own:
1. Plugins listed in `mwdialog_load_order.txt` but not in Data Files are left out.
2. `check_masters_for_play`: every active plugin's masters must be active, present and loading before it. If not, the game is not started (exit 3), with the fix for each case (`--add-all-esp`, `--sort`, or turn the plugin off). `--play-anyway` starts it regardless.
3. `Morrowind.ini`'s `[Game Files]` is set from the list (backed up as above), with a note when the list is longer than Vortex can keep.
4. `deploy_lua_tools` (in `mwdialog_paths.py`) brings `Data Files` up to date with `lua tools\` (laid out like Data Files): a missing file is copied in; a deployed file that differs is replaced only when it is the older version (as a new file, so a Vortex hard link is not written through; the old one goes to `backups\lua deploy\<date>\`); a deployed copy that is the newer version is left alone, with one warning line naming it and what to do (edits belong in `lua tools\`), and the rest carries on. Which is newer is decided by SHA-256 lineage (`downgrade_reason`), not file times: for each file the record below keeps the hash of what `--play` deployed and up to 16 earlier hashes (`history`, newest first), so if the `lua tools\` copy is a version the deployed file already held and has moved past, deploying it would be a downgrade whatever the timestamps say. Modification times decide only when the deployed file's content is in no record (a hand edit), and then a deployed copy at least as new is kept. Identical files are left as they are; files under `MWSE\config\` (your settings) are only copied when missing; outside the suite's own files (another mod's folder, `MWSE\mods\<mod>\`), a file `--play` didn't put there is never replaced. What it deployed is recorded per mod, with SHA-256 and the earlier hashes, in `generated\mwdialog_lua_manifest.json` (versioned JSON, never in Data Files). A file that record lists and `lua tools\` no longer has is removed; when a whole mod is gone, so are its `*-metadata.toml` and its configs. A suite module owns the configs its Lua writes, whatever their names (`mwse.saveConfig`, also through `pcall`, an MCM template's `saveOnClose`, `json.savefile("config\\...")`, `io.open` of `MWSE\config\<name>.json` for writing, with a literal or a string assigned in the same file; a `MWSE\config\<name>` folder it creates with `lfs.mkdir` counts as `<name>/`), not the ones it only reads; `lua tools\MWSE\mods\mwsuite\ownmods.json` may declare them instead with an optional `"configs": {"<module>": ["name", "folder/"]}`, which replaces detection for that module. The record keeps each module's configs, so they can be removed after its Lua is gone; a config a module still in `lua tools\` writes, reads or ships is kept and listed. Each file is copied to `backups\lua prune\<date>\Data Files\` (hash-checked) and journaled in `journal.jsonl` there before it is deleted, and emptied folders are removed. A suite file edited since `--play` deployed it is still removed and reported loudly; a changed file in another mod's folder is kept. `python mwdialog_paths.py --undo-lua-prune [RUN] [--data-dir PATH]` puts the newest prune (or folder `RUN`) back, and the next `--play` leaves those files alone. Suite modules removed before the record existed are named in `RETIRED_SUITE_MODS` (today `mweffectinspector` and `mwpersonaleffects`) and removed once: their `Data Files\MWSE\mods\mwsuite\<name>\`, `<name>-metadata.toml` and `MWSE\config\<name>.json`. Other files in `Data Files\MWSE\mods\mwsuite\` that `lua tools\` doesn't have and no record lists are listed, not deleted.
5. `--exe` (default `Morrowind.exe`) is started detached in the game folder with `SteamAppId` and `SteamGameId` set to `--steam-appid` (default 22320), so the Steam copy doesn't hand itself back to Steam and open the Launcher. On Windows it warns when `steam.exe` is not running.

`Play Morrowind.bat` is the end-user shortcut for this: it calls `mwdialog_check.bat --play` (the `mwdialog_check.bat` next to it, or else the one in `conflict-tools\` next to it, so it works from either folder; relative paths only) and pauses only when the run ends with an error code, such as exit 3 from the master check. Steps added before `--play` in it (e.g. `--sort --yes --play`) run every time.

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `run_sort` | `--sort`, `--full` | `mwdialog_check.py` | Evaluates rules, resolves the dependency graph, sets plugin dates, and writes `generated\mwdialog_load_order.txt`. | Sorted the active plugins into topological load order |
| `compute_order` | *(internal)* | `mwdialog_check.py` | Builds and resolves the order graph, recording which rule steps were skipped and why. | Reported a skipped mlox step that contradicted a user rule |
| `parse_rules` | `--sort` | `mwdialog_loadorder.py` | Parses mlox-style `[Order]`, `[NearStart]`, `[NearEnd]` and `[Exact]` blocks; counts the other mlox tags (`[Note]`, `[Conflict]`, `[Requires]`, `[Patch]`, `[Version]`) as ignored. The `[Context]` section `--sort` writes is all comments, for reading only. | Loaded rules from `mwdialog_check.rules.txt` and `mlox_base.txt` |
| `content_rules` / `cell_filter_rules` | `--sort` | `mwdialog_check.py` / `mwdialog_cellorder.py` | Automatic patch-after-mod and dialogue cell-filter rules, unless `--no-content-order`. | A small patch loaded after the `.esp` whose records it changes |
| `run_update_rules` | `--update-rules` | `mwdialog_check.py` | Comments out or splits contradicted mlox `[Order]` steps; never edits your rules file; never downloads. | `mlox_base.txt: N contradicting step(s) removed (old file saved as ...)` |
| `check` / `disable` | `--disable-mismatched` | `mwdialog_mastercheck.py` | Compares a patch against the installed master and can take a mismatch out of the load order. | Flagged a preview patch built for an older `TR_Mainland.esm` |
| `find_redundant` | `--redundant` | `mwdialog_redundant.py` | Finds plugins doing the same job as another: nothing of theirs would be missed, or two versions of one mod. | Identified obsolete balance patches superseded by a later overhaul |
| `launch_game` / `check_masters_for_play` | `--play` | `mwdialog_check.py` / `mwdialog_masters.py` | Checks masters, writes the ini, deploys `lua tools\`, starts the game without the Launcher. | `--play: NOT starting the game ... Missing masters / plugins` |
| `apply_load_order_to_ini` | *(end of any run)* | `mwdialog_check.py` | Writes the changed load order into `Morrowind.ini`'s `[Game Files]`. | `Morrowind.ini's [Game Files] updated from mwdialog_load_order.txt` |
| `build_compatibility_guard` | `--fix`, `--multipatch`, `--auto-merge`, `--merge` | `mwdialog_check.py` | Before anything is written, runs the incompatible-only cell-conflict check (asking in a console) and stops the run if it fails. | Asked about two land overhauls before the patches were built |
| `disable_dependents` | `--cell-conflicts`, `--redundant-auto` | `mwdialog_redundant.py` | When a parent mod is disabled, also disables the plugins that depend on it. | Automatically disabled sub-patches when the parent mod was isolated |

---

## 12. State Management, Safety Guards, Backups & Rollback

### Architectural Narrative
Modifying massive mod installations carries inherent risk. The suite employs defensive engineering across all modules:
1. **Run Lock (`mwdialog_paths.acquire_run_lock`)**: Holds `mwdialog.lock` beside the tools until the process ends, so two runs of `mwdialog_check.py`, `vortex_tidy.py` or `mwdialog_luafix.py` cannot overlap. A second lock per game folder (`acquire_game_lock`, in `%TEMP%\mwmanager-locks\`) shuts out MWManager jobs on the same game; MWManager can hand its lock to a tool it starts through `MWMANAGER_DELEGATED_LOCKS`. A busy lock ends the run with exit 1 and "Another Morrowind tool or MWManager is still working on this game".
2. **Two-Tier Backup Rotation (`mwdialog_backup.py`)**: Backups go to `conflict-tools\backups\` (or `<game>\mwdialog_backup\` when the tools are not installed in the game folder), at the file's path under the game folder (`Data Files\X.esp` -> `backups\Data Files\X.esp.bak`). The top level preserves the single newest backup per file (`stamped_backup` / `backup_path`), while older backups rotate into `backups\legacy\`. The tools' own files in `generated\` and `plans\` keep their one backup as `<file>.bak` next to the file. `backups\Off\cleanup\` holds backups `--clean-up` couldn't safely delete. Run folders: `backups\luafix\<run>\`, `backups\tidy\<run>\` (with `assets\<mod>\`: the originals tidy `--undo` puts back), `backups\lua deploy\<date>\`; `backups\fixes.archive.txt` holds older fix-log runs.
3. **Atomic Plan Execution (`mwdialog_planfile.py`)**: Operations are written to temporary files and enacted via atomic OS renames, eliminating incomplete writes if interrupted.
4. **`--restore` / `--restore-all` / `--clean-up` / `--restore-dates`**: Newest-backup restore, oldest-original restore (what is replaced is backed up first), prune backups (`--clean-up`, below; `--clean-up-undo` puts back what it moved), and undo the last `--sort`'s dates, respectively.
5. **Start-of-run clean-ups**: each run first drops masters it added that are gone, turns back on a plugin turned off in favour of another (doubled, conflicting, or redundant) when that other one is gone, rebuilds Cell Fixes when a mod one of its doubled-object deletions favoured is gone (not with `--fix`, which rebuilds it anyway), and notes an auto-merge that still holds a plugin `--redundant` turned off.
6. **Other undo switches**: `--unmerge`, `--reenable`, `--redundant-undo`, `--remove-generated`, `--restore-textures`, `--restore-unused`, `--longpaths-undo`, `--soundfix-undo` (see the README's switch tables).

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `write_atomic` | *(internal)* | `mwdialog_planfile.py` | Writes a file via a unique temporary file and an atomic rename. | Safely wrote `plans\vortex_tidy_plan.txt` |
| `stamped_backup` | *(internal)* | `mwdialog_backup.py` | Saves a timestamped copy before a rule file or plugin is edited. | Saved `mlox_base.txt` before `--update-rules` edited it |
| `restore_backups` | `--restore` | `mwdialog_restore.py` | Restores specified plugins from their newest backup copies. | Restored `Clean_Mines and Caverns.esp` from its newest backup |
| `restore_all` | `--restore-all` | `mwdialog_restore.py` | Reverts all modified plugins back to their oldest original backups (the current files are backed up first). | Reverted the load order back to the original backups |
| `run_clean_up` | `--clean-up` | `mwdialog_restore.py` | Finds every plugin `.bak` in Data Files and the backups folder (with `legacy\`, not its `Off\`). A plugin that is installed or parked (a plugin file directly in Data Files; any plugin under a `Grass`, `Off`, `Extras`, `Docs`, `OpenMW`, `bugreports` or `MCPatch` folder at the top of Data Files or the game folder; anywhere in this game's Vortex staging folder; named in the tools' records: the auto-merge and what it merged, `mwdialog_merge_rebuild.txt`, `mwdialog_disabled.txt`, `mwdialog_redundant.txt`; MGE XE's `grass_plugins` in `mgeXE.toml`; or one of the tools' own generated patches and the AutoMerge) keeps its oldest (the original) and newest backup. A plugin confirmed gone has every backup deleted. When the inventory is incomplete (a folder or record that can't be read, Vortex staging that can't be read, a `--vortex-dir` that isn't a folder, or `--no-vortex`), a plugin not found is not treated as gone: its backups are moved to `<backups>\Off\cleanup\<path relative to the backups or game folder>` and journaled with their SHA-256 in `generated\mwdialog_cleanup_journal.jsonl`. `--dry-run` lists the in-between, orphan and uncertain groups; asks unless `--yes`; logged to the fix log. | Freed disk space by pruning intermediate backup files |
| `run_clean_up_undo` | `--clean-up-undo` | `mwdialog_restore.py` | Puts back the backups the last `--clean-up` moved to `Off\cleanup\`: each must still have its journaled SHA-256, and a different file at the old path is never overwritten. What can't be put back stays in the journal (exit 1). | Brought back the backups of a plugin parked in a folder the scan couldn't read |
| `restore_dates` | `--restore-dates` | `mwdialog_restore.py` | Undoes the last `--sort` by putting the old plugin dates back. | Restored dates after an experimental sort |
| `cap_fix_log` | *(internal)* | `mwdialog_console.py` | Caps `mwdialog_fixes.log` at 20 MB by appending older sessions to `backups\fixes.archive.txt`. | Rotated the oldest session log into the archive |
| `wrap` | *(internal)* | `mwdialog_text.py` | Formats and wraps report and log lines at 115 characters with hanging indents. | Formatted a long conflict report for the console |

---

## 13. MWSE Suite Notes (CR-18)

The first-party MWSE modules live in `lua tools\MWSE\mods\mwsuite\` and are deployed to `Data Files` by `mwdialog_check.py --play` (and by MWManager). They are not patched by luafix unless `--include-own` is passed (then only rules A1-A5 and F1). The first-party names themselves are listed in `lua tools\MWSE\mods\mwsuite\ownmods.json`, which deploys with the suite so luafix can read it at `Data Files\MWSE\mods\mwsuite\ownmods.json`. `lua tools\` also holds each module's `*-metadata.toml` (`mwsuite` itself is the module search path, load priority 1000001) and `MWSE\config\mwguard.json`. `mwmanagermenu` gathers every suite module's settings page into one Mod Config Menu entry (MW Conflict Tools).

| Module | What it does (from its header) | Data from `mwdialog_check` |
| :--- | :--- | :--- |
| `mwcollide` | Hides doubled objects as cells load (two unrelated plugins placing things in the same spot) | `mwcollide_data.json` (`--cell-conflicts`, `--fix`) |
| `mwcompanions` | Following, warping and follower combat in one place | |
| `mwconsole` | Console commands (More Console Commands compatible), Tab completion, selection details (panel next to the console; Alt+I window with a Show Effects button) and the effect inspector; off by default | |
| `mwcriminal` | Sneaking, theft and door locks in one place | |
| `mwcustomclasspersistence` | Saves custom classes from the Create Class menu for later games | |
| `mwexitguard` | Clean fast exit: avoids the on-exit freeze and the renderer unloading crash | |
| `mwfloatfix` | Settles floating loose items as cells load; puts back people a save left under water | `mwfloatfix_data.json`, `mwfloatfix_rescue.json` (`--fix`) |
| `mwguard` | Passive profiler and issue logger for MWSE Lua mods (priorities, per-frame costs, log spam); owns the **Guard & Hang Watch** Mod Config menu shared with `mwhangwatch` (pages *Memory & Hang Log* and *Lua Profiler*); `EnableLogTimestamps` and `logTimestampMode` | |
| `mwhangwatch` | Finds what a hang is doing (`MWSE\logs\mwhangwatch.log`); off by default. No Mod Config tab of its own: its settings are on mwguard's **Guard & Hang Watch** page and are saved in its own `mwhangwatch.json` | |
| `mwinfoloop` | Finds dialogue response lists that go round in a circle and keeps them from freezing the game | |
| `mwmanagermenu` | One Mod Config Menu entry for the suite | |
| `mwmouseguard` | Multi-monitor cursor containment and scroll-bleed protection | |
| `mwperformers` | One performer per inn (see section 6) | |
| `mwpluginpatches` | Targeted runtime patches for specific plugins, on only when the target plugin is active: `aiVoicesConsole`, `autoStartup`, `bardicInstruments`, `coastGuardContraband`, `friendsAndFrensLore`, `graphicHerbalismRespawn`, `jiubDelay`, `lostHeirDelay`, `mabrDist`, `pandsfixes`, `personalEffects`, `talesHandwritingFix`, `trainerLogUnlock`, `uiExpansionTopics`, `ysmirShield` (all 15 are described in `lua tools\mwpluginpatches-metadata.toml`) | |
| `mwquicktoggle` | A quick key on an equipped item unequips it and restores what it displaced | |
| `mwsaveguard` | Guards against save corruption and save crashes; `wbsr_bard` | |
| `mwsoundfix` | The MWSE side of `--soundfix` (re-arms rewritten sound loops) | `mwdialog_check - MWSoundFix.esp` helper data |
| `mwsoundguard` | Stops one object from stacking the same sound over and over | `mwsoundguard_data.json` (`--fix`) |
| `mwstranded` | Objects left in the void when another mod rebuilt an interior | `mwstranded_data.json` (`--cell-conflicts`, `--fix`) |
| `mwteleportguard` | Defers scripted dialogue teleports until the conversation closes | |
| `mwwarnsuppression` | Suppresses benign engine warning spam in MWSE.log and Warnings.txt | |

The `*_data.json` files go to `Data Files\MWSE\config\`. `--fix` refreshes the suite's data last, from the final load order (with Cell Fixes, the auto-merge, the sound patch and the Multipatch included).


- **Log shim v6** (`mwdialog_luafix.py`, `SHIM_V = 6`): the lifecycle allowlist no longer uses the bare substring `"start"`. Real init lines still pass; "Dialogue started with..." is sent only to the mod's own log under `Data Files\MWSE\logs\`.
- **mwsaveguard swallowed-save logging**: if a save handler earlier in the chain returns false, MWSE never calls saveguard's own handler. A low-priority follow-up now logs that the save was swallowed and lists the registered save handlers (this is how WBSR's block was identified).
- **mwsaveguard `wbsr_bard`**: when WBSR is installed and loaded, this module is on by default (and off, registering nothing, when WBSR is absent). For a bard or performer song only, it unregisters the one save block WBSR just added; real dialogue and shrine speeches still block saving. WBSR, Bards of Bardenfell, and mwperformers are not edited.
- **mwhangwatch**: no Mod Config tab of its own; its settings are on the **Guard & Hang Watch** page that mwguard registers (page *Memory & Hang Log*), and closing that menu saves `mwhangwatch.json` (its own settings file) as well as `mwguard.json`. The in-game MW Conflict Tools list (`mwmanagermenu`) has no separate mwhangwatch tab either. `enabled` (the hang watch) defaults to false. The address-space warning is a separate opt-in (`memWarn` defaults to false; it comes up at `memLimit`, 80% of the 4 GB by default, and works with the hang watch off) and is a non-modal toast, so clicking it cannot leave the cursor stuck in menu mode after alt-tab.
- **mwfloatfix data stamp and exterior z pass**: `write_float_data` records size and an FNV-1a hash of `mwdialog_check Cell Fixes.esp` in `mwfloatfix_data.json`, because `--fix` stamps plugin dates for load order and a file time cannot identify the build. `find_float_drops` during `--fix` writes exterior z corrections into Cell Fixes; interiors remain the in-game module's job. Until `mwdialog_check --fix` is run on current plugins, an older JSON may still look out of date.
- **mwsoundguard attribution**: for an object whose id is just a number, the log also records mesh, name, source mod, and the Lua caller when `tes3.playSound` was wrapped.
- **mwguard `EnableLogTimestamps`**: off by default (a saved `mwguard.json` that already has it on stays on). When on, global `print` and `mwse.log` are wrapped once, as mwguard loads, and every MWSE.log line written through them gets a time prefix. `logTimestampMode` picks the style: `wallclock` (the default, `[HH:MM:SS]`) or `elapsed` (whole seconds since launch, six digits, `[000042]`; the width grows only past 999999 s). Both are on the Lua Profiler page (*Enable timestamps*): the switch needs a restart, a style change applies to the next line. MWSE has no timestamp setting of its own for this.

Other suite modules include `mwcollide`, `mwstranded`, `mwperformers`, `mwinfoloop`, `mwcriminal`, `mwcompanions`, `mwexitguard`, `mwpluginpatches`, and the remaining folders under `mwsuite`.

---

## 14. Files, Exit Codes & Environment

### Files the tools keep

When the tools are installed in `<game>\conflict-tools\`, the records, caches, journals and reports below are in `conflict-tools\generated\` (a copy left in the game folder by an older version is moved there the first time). Run from anywhere else, they are kept in the game folder.

| File | Written by | What it holds |
| :--- | :--- | :--- |
| `mwdialog_load_order.txt` | `--sort`, `--add-all-esp`, merges, plugins turned off | The active plugins, in load order |
| `mwdialog_check.rules.txt` | you; `--sort` (`[Context]`), `--cell-conflicts` | Your load order rules |
| `mwdialog_loadorder_undo.txt` | `--sort` | The previous dates, for `--restore-dates` |
| `mwdialog_added_masters.json` | `--sort` | Masters added to patches |
| `mwdialog_merged.txt`, `mwdialog_merge_rebuild.txt` | `--auto-merge`, `--redundant` | What each merged plugin replaces; merges still holding a plugin `--redundant` turned off |
| `mwdialog_merge_plan.txt`, `.json` | `--merge-plan` | Recommended merges |
| `mwdialog_disabled.txt` | `--fix`, `--cell-conflicts` | Plugins turned off (for `--reenable`) |
| `mwdialog_cleanup_journal.jsonl` | `--clean-up` | Backups moved to `<backups>\Off\cleanup\` (for `--clean-up-undo`) |
| `mwdialog_redundant.txt` | `--redundant` | Plugins turned off as redundant, and keep-both choices |
| `mwdialog_conflict_answers.json`, `mwdialog_new_conflicts.txt` | `--cell-conflicts` | Remembered answers; pairs the last `--use-answers` run had none for |
| `mwdialog_check.conflict.blacklist.txt` | generated (the tool makes it at the first `[7]` / `[8]` "<plugin> always loses" pick in `--cell-conflicts`, and adds a plugin per pick; remove a plugin by editing it by hand) | Plugins that always lose cell conflicts: left out of `--cell-conflicts`, loaded early by `--sort`. A hand-written one is converted once (entries kept, old file backed up) |
| `mwdialog_incompatible_losers.txt` | generated (`--cell-conflicts` adds a line when you turn off one side of an INCOMPATIBLE pair) | `loser<TAB>lost to<TAB>when`. While the winner is still active the loser is turned off again, unasked, in any incompatibility it is in; when the winner is gone the line lapses. Delete a line to take it back |
| `mwdialog_auto-merge.blacklist.txt` | you | Plugins `--auto-merge` never merges |
| `mwdialog_cell_winners.txt` | `--cell-conflicts` | Whose version of a rebuilt interior wins (built by `--fix` into `mwdialog_check Cell Fixes.esp`) |
| `mwdialog_doubled_deleted.txt` | `--fix` | Doubled objects deleted in Cell Fixes |
| `mwdialog_cell_fixes.txt` | `--fix` | Objects Cell Fixes moves along with the piece they were placed by, which another mod moved |
| `mwdialog_door_owners.txt` | `--fix` | Owners changed in Cell Fixes, and questionable ones left as they are |
| `mwdialog_pathgrid_fixes.txt`, `mwdialog_pathgrid_cache.json` | `--fix` | Pathgrid repairs and their cache |
| `mwdialog_patch_inputs.json` | `note_patch_inputs`, after `fix_cell_winners` writes `mwdialog_check Cell Fixes.esp` | Patch file name -> the active plugins it was last built with; read by `keeps_deletions` under `--preserve-saves`. Written only after a successful write of Cell Fixes: in `--fix` / `--all` / `--full` (not with `--preserve-saves strict`), and when a run without `--fix` rebuilds it because a mod in `mwdialog_doubled_deleted.txt` left the load order (`release_lost_doubles`). Never on `--dry-run`, or when `keeps_deletions` keeps the current build |
| `mwdialog_generated_files.txt` | `--fix`, `--asset-check --fix` | Stand-ins put in Data Files (for `--remove-generated`) |
| `mwdialog_reduced_textures.txt` | `--asset-check --fix` | Textures reduced to 2048 (for `--restore-textures`) |
| `mwdialog_unused_assets.txt` | `--asset-check --fix` | Unused files moved to `Off\<plugin>\unused assets\` (for `--restore-unused`; older paths are followed to where tidy migrated them) |
| `mwdialog_longpaths.json` | `--fix`, `vortex_tidy` | Files moved to a short path (for `--longpaths-undo`) |
| `mwdialog_short_meshes.txt` | `--fix` | Body part / armor / clothing models given a path of at most 31 characters |
| `mwdialog_ignored_normal_maps.txt` | asset check | Normal maps models name that don't exist (`--fix` puts a flat stand-in in their place) |
| `mwdialog_mip_exempt.txt` | you | Extra (or, with `!`, dropped) patterns for textures that need no mipmaps (`texture:`, `texture-name:`, `mesh:`, `mesh-name:`) |
| `mwdialog_master_sizes.json`, `mwdialog_mastercheck_cache.json`, `mwdialog_mastercheck_facts.json` | master check | Original header sizes and cached master analysis |
| `mwdialog_object_cache.json`, asset cache | scans | Per-plugin and per-file caches, keyed by content |
| `mwdialog_soundfix_report.txt` | `--soundfix`, `--fix` | Sound scripts rewritten or left alone, and why |
| `mwdialog_report.txt` | `mwdialog_check.bat` (no arguments) | The last scan's report |
| `mwdialog_fixes.log` (`--fix-log`) | `--fix` and other writing steps | Dated record of every fix; trimmed to 20 MB, older runs moved to `backups\fixes.archive.txt` |
| `mwdialog_luafix.json` | you | luafix settings (see section 10) |
| `mwdialog_luafix_known_bugs.txt`, `mwdialog_luafix_journal.jsonl` | `mwdialog_luafix` | KnownBugs fingerprints found; patch journal |
| `vortex_tidy_dummy_sources.json` | `vortex_tidy` | The core game file picked as the dummy for each file type that can't be made in code; renewed when the plugins, `Morrowind.ini` or the core BSAs change; delete it to force a new pick |
| `vortex_tidy_journal.jsonl`, `vortex_tidy_blacklist.txt` | `vortex_tidy` | Move journal; mods never touched |
| `vortex_paths.json` | any tool | The last Vortex staging/download folders that resolved (only ones Vortex's marker file vouches for) |
| `plans\vortex_tidy_plan.txt`, `plans\mwdialog_luafix_plan.txt` | plan mode | The plans `--apply` enacts (`.prev.txt` after a refusal) |

In the game: `Data Files\MWSE\config\` gets the suite's data files (section 13); `<plugin>.bugreport.txt` goes to `<mod folder>\bugreports\` (the plugin's Vortex mod folder), else `<game>\bugreports\`, from `--bug-reports`, `--fix` and `--asset-check`; asset originals go to `<mod folder>\Off\<plugin>\<path>`; `mge3\Conflict Tools Ghost Statics.toml` / `.ovr` for MGE XE.

### Vortex folders

`mwdialog_paths.py` reads Vortex's staging folder (`settings###mods###installPath`) and download folder from Vortex's `state.v2` LevelDB database under `%APPDATA%\Vortex` (read directly, no Vortex needed), or from its settings backups. When those can't be read, it falls back to a folder that carries Vortex's marker file (`__vortex_staging_folder` / `__vortex_downloads_folder`): the one remembered in `generated\vortex_paths.json`, then Vortex's default location. `--staging` / `--vortex-dir` and `--downloads` / `--vortex-downloads` override all of it; `--no-vortex` (mwdialog_check) skips the staging search. When a folder that is needed can't be found, the error lists every place looked at, and the run ends with exit 2.

### Exit codes

| Tool | Code | Meaning |
| :--- | :--- | :--- |
| `mwdialog_check` | 0 | Done, no ERROR left |
| `mwdialog_check` | 1 | Done, ERRORs reported; also a busy lock, and some steps with nothing to do |
| `mwdialog_check` | 2 | Failed or refused (Vortex folder not found, bad rules entry, `--full` stopped, sound cache not written, `--play`'s game file missing...) |
| `mwdialog_check` | 3 | `--play` refused because of masters |
| `vortex_tidy` | 0 / 1 / 2 | Done / busy lock, nothing to undo, `--undo` refused (an original missing or altered, a file changed since) or items left in the journal, or actions left unapplied / no plan, plan mismatch, staging folder not found |
| `mwdialog_luafix` | 0 / 1 / 2 | Done / busy lock or nothing to undo / no plan, plan mismatch, or no syntax checker for `--apply` |
| `mwdialog_luafix --core-only` | 0 / 1 / 2 / 3 / 4 | Done (applied, already patched or no match) / busy lock / a file refused / partial match, nothing written / no such Morrowind folder |
| `mwdialog_check.bat` | 9009 | Python 3 was not found |

Inside `--full`, a step that ends with anything but 0 or 1 stops the run; `--play` after other steps starts the game only when they ended with 0 or 1.

### Environment variables

| Variable | Used by | Meaning |
| :--- | :--- | :--- |
| `MWRECOMPILE` | `--soundfix`, `--fix` | Path to `MWRecompile.exe` (after `--mwrecompile`) |
| `APPDATA` | all | Where Vortex's settings are read from |
| `MWDIALOG_PAUSE` | `mwdialog_check.py` | Set by `mwdialog_check.bat` when started from Explorer: wait for Enter at the end (only when the output is on screen, and not after starting the game) |
| `MWMANAGER_DELEGATED_LOCKS` | all | MWManager's hand-off of its game lock to a tool it starts |
| `SteamAppId`, `SteamGameId` | `--play` | Set (not read) for the started game |
| `MW_SRC` | `tests\` | The folder of scripts the tests load (default: the repository) |

---

## 15. Keeping a Game in Progress (`--preserve-saves`)

A saved game holds copies of some records and references, and values for script variables. Some fixes change exactly those, which can break a game in progress (an object that comes back beside the copy the save holds, a script variable the save has a value for, a reference moved between groups). `--preserve-saves` holds those fixes back and says what it held back.

**Syntax.** `--preserve-saves` takes an optional value (`choices=("basic", "strict")`): the bare flag means `basic`; `--preserve-saves strict` or `--preserve-saves=strict` for the stricter level; not given, it is off. A bare `--preserve-saves` followed by anything other than `basic` or `strict` (including a Data Files path, or nothing) is rewritten to `--preserve-saves=basic` before argparse runs, so the path is parsed as the folder. The same applies to a unique abbreviation such as `--preserve` when abbreviations are allowed. `preserve_saves()` reads this run's arguments, or the outermost run's, so it also holds inside every `--full` step (`run_full` passes it on to each step).

### `basic` (the bare flag)

- **Topic renames** (`apply_plan`): nameless topics keep no name; a rename would move their responses to another topic.
- **SoundFix** (`--soundfix`, and inside `--fix`): not built, since it adds script variables a saved game holds values for. `--soundfix` on its own exits 1; `--fix` prints "Sound-script patch: not rebuilt". `--soundfix-undo` and `--soundfix-report` still work.
- **Cell Fixes** (`keeps_deletions`): a rebuild of `mwdialog_check Cell Fixes.esp`, or its removal when no rebuilt interior is chosen any more, is skipped when the new build would no longer delete an object the current build deletes while every plugin it was built on is still active (the object would come back beside the copy the save has). "Built on" is the active plugins recorded in `mwdialog_patch_inputs.json` (else the patch's masters). When one of them is gone, the rebuild goes ahead (keeping the old build would leave a missing master, or delete an object whose other copy went with that plugin). This also covers the start-of-run rebuild by `release_lost_doubles`.
- **Old Performers patch**: an earlier version's `mwdialog_check Performers Patch.esp` is not set aside.

### `strict` (everything in `basic`, and)

- **Active plugins stay as they are:** `--unmerge` and `--reenable` are refused (exit 2); `--auto-merge` keeps the merge as it is (exit 0); `--fix`'s doubled-plugin step and `--redundant` / `--redundant-auto` report only; in `--cell-conflicts`, an incompatible pair, or a remembered answer that turns a plugin off, is left as it is and reported, turn-off choices are not offered, and incompatible plugins left active are not an ERROR; incompatible moved-land plugins (`run_cell_conflicts`) are only a warning.
- **Start-of-run clean-ups:** `release_lost_winners` (turning back on a plugin turned off in favour of one that is gone) and `release_lost_doubles` (rebuilding Cell Fixes when a doubled object's rival is gone) don't run.
- **Cell Fixes is not rebuilt at all** (`fix_cell_winners` is skipped in `--fix`), so `mwdialog_patch_inputs.json` is not written either.
- **Reference clean-ups:** `--clean` leaves CELL records alone (no duplicate object instances or junk cells removed; the rest of `--clean` still runs), and `fix_cell_layouts` deletes no misplaced duplicate reference (late scales are still moved).
- **Persistence flips:** `fix_ref_groups` doesn't move references between a master's persistent and temporary groups.
- **`--full`:** no "undo the auto-merge", no "turn back on what earlier runs turned off" and no redundant step; the other steps run with `strict`, so the auto-merge step keeps the merge.

Not affected at either level: the report itself, the ESM patch and in-place `.esp` fixes, the Multipatch, `--sort`, the asset check, and the other start-of-run checks (added masters that are gone, `release_redundant`).
