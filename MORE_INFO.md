# Morrowind Conflict Tools: Comprehensive Architecture & Function Reference (MORE_INFO.md)

This document provides a low-level architectural analysis of the **Morrowind Conflict Tools** suite. It covers all 36 Python modules, describes how the major subsystems operate, lists the command-line switches that trigger them, and documents concrete empirical fix examples drawn from the historical fix archive (`fixes.archive.txt`), the active fix log (`mwdialog_fixes.log`), and third-party MWSE Lua repair records (`LUA_MOD_BUGS.md`). Function names in the tables are the real entry points in the current code. Helper functions and internal scanners are omitted.

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
|  Pure-Python Lexer &  |              |  AST Static Checker |              |  KB1-KB17, KB19      |
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

- `mwdialog_bugreports.py` — author-facing findings for one plugin and its declared master chain, never unrelated mod interactions (`--bug-reports`, also run by `--fix` and `--asset-check`).
- `mwdialog_datatree.py` — the Data Files tree and its BSAs: which models and assets exist on disk.
- `mwdialog_generated.py` — stand-ins and other files `--fix` puts in Data Files or changes there.
- `mwdialog_media.py` — DDS, NIF, and sound file formats: reading, reducing, placeholders, and silent stand-ins.
- `mwdialog_ownership.py` — ownership checks shared by the scanner and the Cell Fixes patch builder.
- `mwdialog_pathgrid.py` — for `--fix` (Cell Fixes): pathgrids that walk people into what a later mod built.
- `mwdialog_paths.py` — shared path helpers (no hardcoded absolute paths) and the run lock (`mwdialog.lock`).
- `mwdialog_state.py` — the small record files the tools keep beside themselves (merged plugins, disabled plugins, cell winners, and so on).
- `mwdialog_mgeghosts.py` — MGE XE distant-land overrides for the objects `mwcollide` hides as exterior cells load.
- `mwdialog_console.py` — questions with a default, the window title, and rotation of `mwdialog_fixes.log`.

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
| `cell_filter_rules` | `--sort` | `mwdialog_cellorder.py` | Generates load-order rules ensuring plugins whose dialogue filters on a cell name load after the plugin that defines that cell. | Ordered a councilors patch after `TR_Mainland.esm` because of a cell filter on `Port Telvannis` |
| `write_collide_data` | `--cell-conflicts`, `--fix` | `mwdialog_cellmods.py` | Writes overlapping placements for `mwcollide` (`mwcollide_data.json`). `--collide-radius` defaults to 32 units (`COLLIDE_ANY_RADIUS`). | Overlapping statics in a Balmora city overhaul written for `mwcollide` to hide as the cell loads |
| `write_float_data` | `--cell-conflicts`, `--fix` | `mwdialog_cellmods.py` | Writes `MWSE\config\mwfloatfix_data.json`: the loose items that could float, so in-game `mwfloatfix` checks only those. Stamped with size and an FNV-1a hash of Cell Fixes (`patch_sources` / `fnv1a_file`), not the plugin's file time. | Mapped loose bowls, cups, and gold coins in tavern overhauls |
| `write_rescue_data` | `--fix` | `mwdialog_footing.py` | Writes `mwfloatfix_rescue.json` for people who may be under water in saves made before the footing pass. | Listed actors for `mwfloatfix` to put back once per save |

---

## 5. AutoMerge & Conflict Multipatch Engine

### Architectural Narrative
Morrowind's 32-bit engine imposes a hard limit on the number of active plugins (approx. 254). Furthermore, when multiple plugins modify the same record type, the last-loaded plugin completely overwrites earlier changes, destroying balance patches, stat tweaks, and creature edits.

The patching engine provides two complementary solutions:
1. **AutoMerge (`mwdialog_check AutoMerge.esp`)**: Finds active `.esp` plugins with no cell, land, or pathgrid edits that can move together without changing what wins against any other plugin, merges them into one patch, and deactivates the inputs. Plugins listed in `mwdialog_auto-merge.blacklist.txt` are never merged.
2. **Multipatch (`mwdialog_check Multipatch.esp`)**: Like tes3cmd multipatch: merged leveled lists, fog-bugged interiors (fog density 0 is set to 0.01), and reverted exterior cell names. By default it also merges objects several mods change, field by field (like TES3Merge), unless `--no-merge-objects` is passed. Load it last.

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `run_multipatch` | `--multipatch`, `--all`, `--full` | `mwdialog_multipatch.py` | Builds the Multipatch: leveled lists, fog density 0 → 0.01, reverted cell names, and optional object merges. | `mwdialog_check Multipatch.esp: cell 'Abernanit': fog density 0 (from Cutting Room Floor) set to 0.01` |
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

`--soundfix` (and `--fix`, unless `--no-soundfix`) locates these polling loops. `mwdialog_soundfix.rewrite` rewrites the script to track playback state with an explicit variable, then `run_mwrecompile` compiles the rewritten source with `tools\MWRecompile\MWRecompile.exe` into `mwdialog_check - MWSoundFix.esp`. The new bytecode is that of the rewritten script, not a byte-for-byte match of the original.

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
| `write_sound_cache` | `--fix`, `--soundfix` | `mwdialog_soundcache.py` | Computes audio file durations using `ffprobe` and caches results. | Cached sound durations across vanilla and Tamriel Data archives |

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
| `restore_unused` | `--restore-unused` | `mwdialog_assets.py` | Puts back unused textures/sounds that `--asset-check --fix` moved to `Off\unused\`. | Restored a texture that a later plugin started using |

---

## 9. Vortex Staging Normalization & File Organization

### Architectural Narrative
When installing mods through mod managers like Vortex, mod archives frequently contain non-standard directory layouts: nested `Data Files\Data Files` structures, readmes, text walkthroughs, image previews, and changelogs strewn across the root mod folder. If deployed directly to the game, these files clutter the installation and cause file-override collisions.

`vortex_tidy.py` automates the cleanup of Vortex's staging directory. It inspects each mod folder, moves documents (`.txt`, `.md`, `.pdf`, `.html`, `.htm`, `.doc`, `.docx`, `.odt`, `.rtf`, `.nfo`) into `Docs\` renamed `<mod name> - <file>`, moves root images into `Screenshots\` with the same prefix, relocates misplaced textures and meshes to canonical game folders at the mod root, leaves distant-land grass plugins out of the active list, moves OpenMW-only normal maps to `Off\normal maps\<mod name>\`, and interfaces with `mwdialog_luafix.py` to harden MWSE scripts in-place. All operations are strictly planned before execution via `plans\vortex_tidy_plan.txt`.

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `run_plan` | *(default)* | `vortex_tidy.py` | Scans the Vortex staging folder; compiles proposed moves, asset fixes, and Lua patches into `plans\vortex_tidy_plan.txt`. | Generated a staging plan proposing document relocations across staged mods |
| `apply` / `apply_main` | `--apply` | `vortex_tidy.py` | Validates file hashes and enacts the reviewed plan; blanks the plan file upon completion. | Applied moves and DDS mipmap repairs across staged mod directories |
| `undo` | `--undo` | `vortex_tidy.py` | Reads the execution journal and reverts all moved, renamed, or patched files. | Fully reverted the last tidy apply |
| `plan_mod` | *(internal)* | `vortex_tidy.py` | Normalizes one mod folder: flattens nested `Data Files`, plans Docs/Screenshots moves, and flags OpenMW-only addons. | Flattened `ModName\Data Files\Meshes` to `ModName\Meshes` |
| `is_doc` | *(internal)* | `vortex_tidy.py` | Detects document extensions that belong in `Docs\`. | Planned `Readme - Version 2.1.txt` → `Docs\<mod name> - Readme - Version 2.1.txt` |
| `is_grass_plugin` | *(internal)* | `vortex_tidy.py` | Identifies MGE XE distant-land grass plugins and keeps them out of the standard active list. | Identified and isolated `Rem_AL_Grass.esp` from the active load order |

---

## 10. MWSE Lua AST Static Analysis, Hardening & Targeted KnownBugs

### Architectural Narrative
Morrowind Script Extender (MWSE) allows modders to execute Lua code directly inside the game engine. However, third-party Lua mods frequently suffer from unhandled exceptions, nil dereferences during game loads, uncontrolled event recursion, and memory leaks. Crude regex search-and-replace tools cannot safely patch Lua because code structure, comments, and nested closures alter execution flow.

`mwdialog_luafix.py` incorporates a complete, pure-Python lexical scanner and recursive-descent parser (`mwdialog_lua.py`) specifically supporting Lua 5.1 and LuaJIT syntax. It parses Lua files into an Abstract Syntax Tree (AST), performs static semantic analysis, and applies defensive code hardening:
1. **Nil Guards**: Injects defensive checks before accessing chained properties (e.g. ensuring `e.reference` is non-nil before dereferencing `e.reference.object`).
2. **Priority Compression**: Event handler priorities whose absolute value is 10,000 or more are compressed into 1000–1999, keeping their relative order (`compress_priority` in `mwdialog_luafix.py`).
3. **Log Shimming**: Injects a rate-limiting shim around unthrottled `print` and `mwse.log` calls (not `tes3.log`) inside per-frame handlers. The current shim is version 6 (`SHIM_V = 6`). Its lifecycle allowlist uses tight patterns such as `"] started"` and `"has started"`, not the bare substring `"start"`, so lines like "Dialogue started with…" are not forwarded to MWSE.log.
4. **Targeted KnownBugs (KB1–KB17 and KB19)**: Hardens high-profile third-party mods against severe documented defects. There is no KB18: the conflict between abot's WBSR and tavern bard songs is handled at runtime by `mwsaveguard.wbsr_bard`, not by patching WBSR's Lua.
5. **MWSE performance and persistence checks** (report only, from the MWSE docs' tips): `G6` `tes3.getReference` (it scans every cell's references) in a frequent handler or a fast repeating timer; `G7` `tes3.rayTest` every frame or in a frequent handler with no `maxDistance`, no `root` (`worldObjectRoot`, `worldPickRoot`, `worldLandscapeRoot`), or with `accurateSkinned`; `R1` a `timer.start` callback that uses a reference captured from its event with no `tes3.makeSafeObjectHandle` or `:isValid()` check; `T1` a named timer callback (`callback = "mod:name"`) that no file of the mod registers with `timer.register`; `P1` `ref.data` written on a reference the code shows is not an actor, with no `ref.modified = true` (the data is not saved). `V1` now needs vector evidence for the right-hand operand (the 92 vector fields and functions in MWSE's docs, `tes3vector3.new`, `.position` of a reference, `:normalized()`/`:copy()`/`:lerp()`, or a local assigned once from one of those) and also covers `n + v` and `n - v` (rewritten `v + n` and `-v + n`): plain number math such as `2 * math.pi` or `0.9 * vol` is no longer flagged. `H2` no longer flags timers started in `loaded`, of any type: MWSE clears real, simulate and game timers just before that event. `D1` also flags an `infoFilter` handler that does costly work (string calls, `tes3.*` lookups) before it checks `e.passes`; it is fixed (an early return) only when the handler has no other effects, else reported.

### Targeted KnownBugs Catalog (KB1–KB17 and KB19)

- **KB1 (`AttendMeMWSE/followers.lua`)**: `refresh()` reads `.mobile` on references kept from the last pass; a deleted one raises `sol: received nil for self`. The patch wraps that access in `pcall`.
- **KB2 (`UI Expansion/menudialog.lua`)**: The topic updater queries an empty property key, so actor-unique topics never reuse their cached info. The patch uses `"MenuDialog_UIEXP_info"`.
- **KB3 (`MWSE Core/exclusionspage.lua`)**: ExclusionsPage destroys `outerContainer` and then dereferences that destroyed element's parent. The patch keeps the parent first.
- **KB4 (`MWSE Core/exclusionspage.lua`)**: ExclusionsPage builds one UI element per item, unbounded (thousands with Tamriel Data). KB4 rewrites the generator to pages of 100 per column. All of KB4 applies, or none of it. This is separate from KB3.
- **KB5 (`MUSE 2.02/music/muse.lua`)**: Two MCM calls split a parenthesized argument after the method name; LuaJIT rejects the file.
- **KB6 (`OpenUI - MWSE/mod.lua`)**: The enchanted weapon HUD dereferences `weapon.itemData.condition` before checking that `itemData` exists.
- **KB7 (`Friends & Frens/main.lua`)**: `%Sign` is not a dialogue variable; the patch substitutes the companion's script-local birthsign on `infoGetText`.
- **KB8 (`Tamriel Data/magic.lua`)**: Invisibility detection read actors' spell lists while a save was loading (raw ids such as `0x736f6867`). It now waits for `loaded`.
- **KB9 (`Directional Sunrays/main.lua`)**: The interior sunray pass called the engine's `updateSun` through FFI with no current weather; it now checks first.
- **KB10 (`Robe'n'Hood/main.lua`)**: `isBadWeather` / hat helpers dereference `weather.index` / `weather.name` when `tes3.getCurrentWeather()` is still nil after a new game started from inside a session.
- **KB11 (`Nocturnal Moths/util/init.lua`)**: `util.isNiceWeather` indexes `currentWeather.index` without a nil check, and `EffectManager` caches `activeEffects` across saves; the patch also resets that cache on load.
- **KB12 (`Tamriel Data/weather.lua`)**: `if weather and weather.index == ... or weather.index == ...` leaves the `or` branch unguarded when `weather` is nil; `silenceCreatures` also indexed a nil weather.
- **KB13 (`UI Expansion/common.lua`)**: `createElements` registers destroy cleanup for icon and button filter blocks but not for `searchBlock`, so `menuEnter` calls `clearFilter()` on destroyed UI after a new game or load.
- **KB14 (`Nocturnal Moths/util/init.lua`)**: `util.playSound` starts a looped `R0_moths_fluttering` without `tes3.getSoundPlaying`, and the KB11 reset dropped `activeEffects` without `tes3.removeSound`, stacking copies after a load.
- **KB15 (`AURA/common.lua`)**: `common.getTrackPlaying` trusts `tes3.getSoundPlaying`, which the engine often answers as false for a still-playing 3D loop, so AURA's door/window timers start the sound again.
- **KB16 (`Flies/main.lua`)**: On `cellChanged`, Flies plays a looped `'Flies'` sound on every qualifying corpse without `tes3.getSoundPlaying` or a stop on deactivate/load, stacking copies. mwsoundguard cannot see this: it skips NPCs and creatures.
- **KB17 (`Tel Raloran/levpad.lua`)**: `addLevitation` plays a looped 2D `'forcefield'` without `tes3.getSoundPlaying`, and there is no `loaded` handler to clear it.
- **KB19 (`Keg Drip/main.lua`)**: `refreshCell` used a 0.01-unit position test, deleted and recreated the drip activator on a miss, and restarted `dripKeg`. The patch loosens `samePlacement`.
- **No KB18**: WBSR's save handler blocks any `Vo\` lip-sync, including bard songs. That is handled by `mwsaveguard.wbsr_bard`, not a luafix patch of WBSR.

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `check_paths` | *(default)* | `mwdialog_luafix.py` | Scans Lua scripts, parses ASTs, checks rules and KnownBugs, and feeds the plan written as `plans\mwdialog_luafix_plan.txt`. | Generated a Lua plan flagging nil guards and KnownBug patches |
| `apply_report` | `--apply` | `mwdialog_luafix.py` | Enacts planned Lua patches after hash validation; verifies syntax with LuaJIT. | Patched `MWSE\core\mcm\components\pages\exclusionspage.lua` with KB4 |
| `undo` | `--undo` | `mwdialog_luafix.py` | Restores the files the last `--apply` patched. `--force` also puts back files changed since. | Reverted an experimental Lua patch |
| `tokenize` | *(internal)* | `mwdialog_lua.py` | Lexical scanner producing Lua 5.1/LuaJIT tokens, comments, and literals. | Tokenized a large UI Expansion module |
| `parse` | *(internal)* | `mwdialog_lua.py` | Recursive-descent parser generating the Abstract Syntax Tree. | Constructed the AST for a patched script |
| `compress_priority` | `--apply` | `mwdialog_luafix.py` | Compresses `event.register` priorities with `\|p\| >= 10000` into 1000–1999, keeping order. | Compressed priority `1000000` into the 1000–1999 band |
| `log_shim` | `--lua-log`, `--log-shim-always` | `mwdialog_luafix.py` | Injects the version-6 rate-limiting shim around `print` / `mwse.log`. | Redirected a per-frame combat logger into `Data Files\MWSE\logs\<mod>.log` |
| `verify_patch` | *(internal)* | `mwdialog_luafix.py` | Compiles the patched file with LuaJIT (or luac / lupa) before it is kept. | Verified syntax of patched Lua files |

---

## 11. Load Order Sorting, Rule Management & Master Integrity

### Architectural Narrative
Plugin load order determines which mod wins conflicting record edits. The sorting engine lives in `mwdialog_check.py` (`run_sort`, `compute_order`). `mwdialog_loadorder.py` parses mlox-style rule files and stores the intended order in `generated\mwdialog_load_order.txt` (and writes `[Game Files]` when asked). It integrates mlox-style rules from `Morrowind\mlox\mlox_base.txt` and `mlox_user.txt`, plus user overrides in `mwdialog_check.rules.txt`. Your rules file wins over mlox's.

Key sorter features:
- **`[NearStart]` & `[NearEnd]` Blocks**: Enforces positional constraints (e.g. loading master bug fixes early, and loading auto-merges, multipatches, and sky variations at the very end).
- **Automatic content rules**: Unless `--no-content-order` is passed, `--sort` adds patch-after-mod `content_rules` and dialogue cell-filter rules from `mwdialog_cellorder.py`.
- **`--update-rules`**: Does not download or fetch anything. `run_update_rules` reads the local rule sources (`mwdialog_check.rules.txt`, then `Morrowind\mlox\mlox_user.txt` and `mlox_base.txt`), asks `compute_order` which mlox `[Order]` steps were already skipped because a master, your rules file, a context rule, or an earlier mlox rule said otherwise, or because a step would put an `.esp` before an `.esm`, and then edits only the mlox files: the contradicted step is commented out or the rule is split, a `;; mwdialog_check --update-rules <stamp>:` note is inserted, and the old file is saved with `stamped_backup`. Your `mwdialog_check.rules.txt` is only printed for you to fix by hand. `--dry-run` shows the plan and writes nothing.
- **Master Compatibility Guard (`mwdialog_mastercheck.py`)**: Analyzes compatibility patches to determine if they were built for the currently installed version of their master. If a patch was built for a different master, `--disable-mismatched` takes it out of the load order.
- **The intended order** is `generated\mwdialog_load_order.txt`, with plugin dates set one day apart. `Morrowind.ini`'s `[Game Files]` can be truncated by Windows' 32,767-character limit; `--play` writes the intended list back into the ini.

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `run_sort` | `--sort`, `--full` | `mwdialog_check.py` | Evaluates rules, resolves the dependency graph, sets plugin dates, and writes `generated\mwdialog_load_order.txt`. | Sorted the active plugins into topological load order |
| `compute_order` | *(internal)* | `mwdialog_check.py` | Builds and resolves the order graph, recording which rule steps were skipped and why. | Reported a skipped mlox step that contradicted a user rule |
| `parse_rules` | `--sort` | `mwdialog_loadorder.py` | Parses mlox-style `[Order]`, `[NearStart]`, `[NearEnd]`, and `[Context]` blocks. | Loaded rules from `mwdialog_check.rules.txt` and `mlox_base.txt` |
| `content_rules` / `cell_filter_rules` | `--sort` | `mwdialog_check.py` / `mwdialog_cellorder.py` | Automatic patch-after-mod and dialogue cell-filter rules, unless `--no-content-order`. | A small patch loaded after the `.esp` whose records it changes |
| `run_update_rules` | `--update-rules` | `mwdialog_check.py` | Comments out or splits contradicted mlox `[Order]` steps; never edits your rules file; never downloads. | `mlox_base.txt: N contradicting step(s) removed (old file saved as ...)` |
| `check` / `disable` | `--disable-mismatched` | `mwdialog_mastercheck.py` | Compares a patch against the installed master and can take a mismatch out of the load order. | Flagged a preview patch built for an older `TR_Mainland.esm` |
| `find_redundant` | `--redundant` | `mwdialog_redundant.py` | Finds plugins whose records are completely superseded by later-loading mods. | Identified obsolete balance patches superseded by a later overhaul |
| `disable_dependents` | `--cell-conflicts`, `--redundant-auto` | `mwdialog_redundant.py` | When a parent mod is disabled, also disables the plugins that depend on it. | Automatically disabled sub-patches when the parent mod was isolated |

---

## 12. State Management, Safety Guards, Backups & Rollback

### Architectural Narrative
Modifying massive mod installations carries inherent risk. The suite employs defensive engineering across all modules:
1. **Run Lock (`mwdialog_paths.acquire_run_lock`)**: Holds `mwdialog.lock` beside the tools until the process ends, so two runs of `mwdialog_check.py` or `vortex_tidy.py` cannot overlap.
2. **Two-Tier Backup Rotation (`mwdialog_backup.py`)**: Backups go to `conflict-tools\backups\`. The top level preserves the single newest backup per file (`stamped_backup` / `backup_path`), while older backups rotate into `backups\legacy\`.
3. **Atomic Plan Execution (`mwdialog_planfile.py`)**: Operations are written to temporary files and enacted via atomic OS renames, eliminating incomplete writes if interrupted.
4. **`--restore` / `--restore-all` / `--clean-up` / `--restore-dates`**: Newest-backup restore, oldest-original restore (what is replaced is backed up first), prune intermediates, and undo the last `--sort`'s dates, respectively.

### Function & Switch Reference Table

| Function | Primary Switch | Subsystem / Module | Description & Mechanics | Real-World Empirical Fix Example |
| :--- | :--- | :--- | :--- | :--- |
| `write_atomic` | *(internal)* | `mwdialog_planfile.py` | Writes a file via a unique temporary file and an atomic rename. | Safely wrote `plans\vortex_tidy_plan.txt` |
| `stamped_backup` | *(internal)* | `mwdialog_backup.py` | Saves a timestamped copy before a rule file or plugin is edited. | Saved `mlox_base.txt` before `--update-rules` edited it |
| `restore_backups` | `--restore` | `mwdialog_restore.py` | Restores specified plugins from their newest backup copies. | Restored `Clean_Mines and Caverns.esp` from its newest backup |
| `restore_all` | `--restore-all` | `mwdialog_restore.py` | Reverts all modified plugins back to their oldest original backups (the current files are backed up first). | Reverted the load order back to the original backups |
| `run_clean_up` | `--clean-up` | `mwdialog_restore.py` | Deletes the backups between each plugin's oldest original and its newest. | Freed disk space by pruning intermediate backup files |
| `restore_dates` | `--restore-dates` | `mwdialog_restore.py` | Undoes the last `--sort` by putting the old plugin dates back. | Restored dates after an experimental sort |
| `cap_fix_log` | *(internal)* | `mwdialog_console.py` | Caps `mwdialog_fixes.log` at 20 MB by appending older sessions to `backups\fixes.archive.txt`. | Rotated the oldest session log into the archive |
| `wrap` | *(internal)* | `mwdialog_text.py` | Formats and wraps report and log lines at 115 characters with hanging indents. | Formatted a long conflict report for the console |

---

## 13. MWSE Suite Notes (CR-18)

The first-party MWSE modules live in `lua tools\MWSE\mods\mwsuite\` and are deployed to `Data Files` by `mwdialog_check.py --play` (and by MWManager). They are not patched by luafix unless `--include-own` is passed.

- **Log shim v6** (`mwdialog_luafix.py`, `SHIM_V = 6`): the lifecycle allowlist no longer uses the bare substring `"start"`. Real init lines still pass; "Dialogue started with…" is sent only to the mod's own log under `Data Files\MWSE\logs\`.
- **mwsaveguard swallowed-save logging**: if a save handler earlier in the chain returns false, MWSE never calls saveguard's own handler. A low-priority follow-up now logs that the save was swallowed and lists the registered save handlers (this is how WBSR's block was identified).
- **mwsaveguard `wbsr_bard`**: when WBSR is installed and loaded, this module is on by default (and off, registering nothing, when WBSR is absent). For a bard or performer song only, it unregisters the one save block WBSR just added; real dialogue and shrine speeches still block saving. WBSR, Bards of Bardenfell, and mwperformers are not edited.
- **mwhangwatch**: `enabled` (the hang watch) defaults to false. The address-space warning is a separate opt-in (`memWarn` defaults to false) and is a non-modal toast, so clicking it cannot leave the cursor stuck in menu mode after alt-tab.
- **mwfloatfix data stamp and exterior z pass**: `write_float_data` records size and an FNV-1a hash of `mwdialog_check Cell Fixes.esp` in `mwfloatfix_data.json`, because `--fix` stamps plugin dates for load order and a file time cannot identify the build. `find_float_drops` during `--fix` writes exterior z corrections into Cell Fixes; interiors remain the in-game module's job. Until `mwdialog_check --fix` is run on current plugins, an older JSON may still look out of date.
- **mwsoundguard attribution**: for an object whose id is just a number, the log also records mesh, name, source mod, and the Lua caller when `tes3.playSound` was wrapped.
- **mwguard `EnableLogTimestamps`**: on by default. Prefixes every MWSE.log line written through `print` / `mwse.log` with a clock time (`[HH:MM:SS]`). There is no separate MWSE core setting for this.

Other suite modules include `mwcollide`, `mwstranded`, `mwperformers`, `mwinfoloop`, `mwcriminal`, `mwcompanions`, `mwexitguard`, `mwpluginpatches`, and the remaining folders under `mwsuite`.
