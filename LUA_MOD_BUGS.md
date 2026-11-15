# Third-Party Lua Mod Bug Fixes (LUA_MOD_BUGS.md)

This log records genuine bugs in third-party MWSE Lua mods that have been repaired directly in their respective files.

> **Policy**:
> - Only edit third-party mods when resolving actual bugs, crashes, unhandled exceptions, or severe defects in their own code.
> - Workarounds for external mod conflicts, engine edge-cases, and patterns that can recur across multiple mods belong in dedicated suite tools (`mw*` suite / `mwpluginpatches`), not in third-party source files.

---

## 1. Animated Dialogue

* **Author**: Tauer
* **Files**:
  * [nodeResolver.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/tauer/animated-dialogue/services/nodes/nodeResolver.lua#L11-L22)
  * [actorPoseBlender.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/tauer/animated-dialogue/services/actors/actorPoseBlender.lua#L58-L72)
* **Bugs**:
  1. **Cyclic Controller Infinite Loop**: When traversing scene nodes in `nodeResolver.lua`, cyclic controller parent/child links caused `while controller do` to enter an infinite loop and freeze the process.
  2. **180° Actor Facing Flip on Dialogue Close**: During dialogue exit transition, `actorPoseBlender:capture()` traversed all bones starting with `Bip` and slerped their rotations back to vanilla idle poses. Blending root transform bones (`Bip01`, `Bip01 NonAccum`, `Bip01 Footsteps`, `Root Bone`) caused quaternion antipodal flips and desynchronized the actor's orientation from Morrowind's native facing, making NPCs (such as Sellus Gravius) abruptly snap 180° away.
* **Fixes**:
  1. In `nodeResolver.lua`, added a `seen = {}` lookup table inside the traversal loop to break out immediately if a controller is visited more than once.
  2. In `actorPoseBlender.lua`, added an explicit guard in `this:capture()` skipping root transform bones (`name ~= "Bip01" and name ~= "Bip01 NonAccum" and name ~= "Bip01 Footsteps" and name ~= "Root Bone"`).

---

## 2. Keg Drip

* **Author**: Merlord
* **File**: [main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/KegDrip/main.lua#L130-L240)
* **Bugs**:
  1. Raycast direction vector syntax used `-1 * up` instead of `up * -1`, which can throw metatable operation errors in certain vector math versions.
  2. Raycasting and puddle calculations polled unthrottled during `menuMode`, consuming CPU while the game was paused.
  3. Hardcoded 1-second interval checks across all active cells without MCM configurability.
* **Fixes**:
  1. Corrected direction vector multiplication to `up * -1`.
  2. Guarded `simulate` event with `if tes3.menuMode() or not config.formPuddles then return end`.
  3. Added configurable `checkInterval` (default 3 seconds) with an MCM slider.

---

## 3. Small QoL Improvements

* **Author**: Spammer
* **File**: [main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/Spammer/QoL%20Improvements/main.lua#L63-L110)
* **Bugs**:
  1. `equip` and `equipped` event handlers executed without verifying if the equipping actor was `tes3.player`, attempting to run player-only UI notifications and magic equipping logic on NPCs.
  2. If a scroll or on-use enchanted item was consumed or moved before the one-frame delayed timer fired, `tes3.mobilePlayer:equipMagic()` was called with an invalid/nil item, triggering an unhandled Lua exception.
* **Fixes**:
  1. Added early guard `if e.reference ~= tes3.player then return end`.
  2. Added player inventory verification (`inv:contains(item)`) and protected calls (`pcall`) around `equipMagic`.

---

## 4. Essential Indicators

* **Author**: Petethegoat
* **File**: [main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/Essential%20Indicators/main.lua#L72-L195)
* **Bugs**:
  1. `tes3.getPlayerCell()` returns `nil` during certain cell transitions and load screens; iterating its references threw `attempt to index a nil value`.
  2. `onDamage` hook displayed the prophecy severance messagebox for any damage event—including non-lethal hits, NPC infighting, or environmental damage—and spammed messages repeatedly.
  3. `MenuMulti:findChild("MenuMulti_sneak_icon")` could return nil if HUD mods altered or removed the sneak icon, crashing `simulate`.
  4. Extreme event priority (`-10000`) caused registration collisions.
* **Fixes**:
  1. Added nil guard on `playerCell` in `essentialSwitch()`.
  2. Filtered `onDamage` warnings to lethal hits directly originating from the player or player summons, with a 15-second cooldown.
  3. Safely checked `child` validity before setting `maxWidth`/`maxHeight`.
  4. Standardized event priority from `-10000` to `-9000`.

---

## 5. Companion Leveler

* **Author**: Remiros & Team
* **File**: [mcm.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/companionLeveler/mcm.lua#L436-L530)
* **Bug**: EasyMCM sliders under the "Attribute Modifiers" category failed to render track elements properly and collapsed to zero width on certain screen resolutions and UI scalings.
* **Fix**: Added a `postCreate = fixSlider` callback for each attribute modifier slider, enforcing `minWidth = 180`, ensuring child element visibility, and synchronizing widget values during layout.

---

## 6. Character Sound Overhaul

* **Author**: R-Zero
* **File**: [interop.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/Character%20Sound%20Overhaul/interop.lua#L80-L98)
* **Bug**: `this.addSoundData` logged every individual sound registration via `mwse.log()`, dumping over 20,000 lines into `MWSE.log` during game launch and pushing other mod logs out of buffer.
* **Fix**: Redirected sound registrations into a separate dedicated log file ([Data Files/MWSE/logs/CSO_soundData.log](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/logs/CSO_soundData.log)).

---

## 7. Elemental Effects

* **Author**: Greatness7
* **File**: [main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/Elemental%20Effects/main.lua#L210-L250)
* **Bug**: When spell projectiles expired or hit non-actor objects, accessing `e.target.data.ee` without verifying target existence produced nil-indexing errors.
* **Fix**: Added guard conditions verifying `e.target` and `e.target.data` prior to updating visual shader properties.

---

## 8. Syanide's Magic Lantern Lights

* **Author**: Syanide
* **File**: [main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/Syanide/MagicLanternLights/main.lua#L399-L426)
* **Bug**: OAAB glowbug variants (`mwse_oaab_glwbug_*`) and buglamps were referenced in lantern tables but lacked fallback mesh path resolution in `updateLanternNode()`, passing nil meshes to the node attacher.
* **Fix**: Explicitly mapped mesh file paths for OAAB glowbug jars and vanilla buglamp variants.

---

## 9. Let There Be Darkness

* **Author**: RFD
* **File**: [main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/RFD/LetThereBeDarkness/main.lua#L143-L150)
* **Bug**: Attempted to evaluate cell light levels and display configuration menus before `tes3.player` or active cells were fully instantiated during game initialization.
* **Fix**: Added `if tes3.player == nil then return end` guard on startup hooks.

---

## 10. Sophisticated Save System

* **Author**: NullCascade
* **File**: [main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/Sophisticated%20Save%20System/main.lua#L203-L210)
* **Bug**: In `onSimulate()`, when autosaves were queued via `needToSave = true`, SSS dispatched `tes3.saveGame({ file = "autosave" })` without clearing `needToSave` upfront, relying on its downstream `onSave` handler (priority 0) to reset it. If any higher-priority save event handler or validator (such as `mwsaveguard`, priority 10000) deferred, blocked, or claimed the save, `onSave` never ran. As a consequence, `needToSave` remained `true` indefinitely, causing SSS to repeatedly invoke `tes3.saveGame()` on every single frame, locking game progress bars at 50% and causing engine access violations.
* **Fix**: In `onSimulate()`, explicitly set `needToSave = false` immediately before calling `tes3.saveGame({ file = "autosave" })`.

---

## 11. Companion Sneak (Inspector UI)

* **Author**: Companion Sneak Team
* **File**: [inspectorui.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwcompanionsneak/inspectorui.lua#L292-L340)
* **Bug**: Invoked `inputBorder.marginRight = 8` and `clearBtn.marginRight = 8` during search-bar UI construction. `tes3uiElement` does not define `marginRight` (only `borderRight`), throwing `sol: cannot set (new_index) into this object: no defined new_index operation on usertype`, which corrupted the UI element tree and caused engine hangs on game exit.
* **Fix**: Replaced invalid `marginRight` calls with `borderRight = 8`.

---

## 12. The Doors of Oblivion

* **Author**: Doors of Oblivion Team
* **File**: [Tx_metal_strip_02.tga](file:///g:/Vortex%20Mods/morrowind/The%20Doors%20of%20Oblivion%201.4-44398-1-4/textures/Tx_metal_strip_02.tga)
* **Bug**: Shipped an obsolete 12KB `Tx_metal_strip_02.tga` filled with near-zero black pixels (RGB 21, 25, 26). Because the Morrowind engine prioritizes loose `.tga` matches over `.dds` textures, this file crushed textures on every model referencing `Tx_metal_strip_02` (such as the standard common chest `contain_com_chest_02.nif`), overriding installed 2K MET / Articus / Vurt `.dds` replacements and rendering chests completely black in-game.
* **Fix**: Moved `Tx_metal_strip_02.tga` to `Off/textures/` and pruned the deployed file from `Data Files/Textures/`, allowing the high-definition `tx_metal_strip_02.dds` texture to load as intended.

---

## 13. Graphic Herbalism & Harvest Lights Integration

* **Author**: Greatness7 / RogiVagel / Harvest Lights Team
* **Files**:
  * [main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/graphicHerbalism/main.lua)
  * [main.lua (Patch Staging)](file:///G:/Vortex%20Mods/morrowind/Graphic%20Herbalism%20-%20Ultimate%20Override%20Patch/MWSE/mods/graphicHerbalism/main.lua)
* **Bugs**:
  1. Flora without dedicated `HerbalismSwitch` NIFs (unpatched plants, custom landmass flora from Tamriel Rebuilt, Project Cyrodiil, SHOTN, or mods lacking switch models) failed to visually change when picked because `updateHerbalismSwitch()` returned early on missing `switchNode`, leaving picked flora models unaltered.
  2. In `updateHerbalismSwitch()`, changes to `switchNode.switchIndex` were made without invoking `sceneNode:update()`, preventing immediate NetImmerse bounding box and visible subtree recalculations.
  3. In `onActivate()`, Graphic Herbalism intercepted the activation and returned `false` without firing `event.trigger("containerClosed", { reference = ref })`. Because `HarvestLights` depends on `containerClosed` to shut off lights associated with glowing mushrooms and flora (`bc mushroom 256`, glowing lichen, etc.), glowing lights remained burning after flora was harvested.
  4. Mushroom replacements in prior patch staging were misplaced under `Meshes/fg/` (Flora Glow paths) instead of standard game paths (`Meshes/f/flora_bc_mushroom_*.nif`), causing conflicting replacers without switch nodes to win file precedence and leaving Seyda Neen courtyard mushrooms un-harvestable visually.
* **Fix**:
  1. Added universal vaporization fallback: when `switchNode` is missing or invalid on harvest, `sceneNode.appCulled = true` is applied and tracked in `ref.data.GH`. When cell resets/respawns (`index == 0`), `sceneNode.appCulled = false` restores the flora.
  2. Enhanced switch indexing: resolves target children by name (`HARVESTED`/`PICKED`/`NORMAL`/`SPOILED`) with index clamping, unsets `appCulled`, and executes `sceneNode:update()`.
  3. Added `event.trigger("containerClosed", { reference = ref })` inside `onActivate()` so `HarvestLights` immediately disables associated light sources when glowing flora is picked.
  4. Guarded `onActivate` and `onTooltipDrawn` against harvested flora using both `ref.data.GH` and `ref.sceneNode.appCulled`.
  5. Assembled all 816 validated modifying NIFs (base game, DLCs, glowing mushrooms, smoothed marshmerrow, and landmass flora) and 36 associated high-quality textures into a unified Vortex staging override package at [Graphic Herbalism - Ultimate Override Patch](file:///G:/Vortex%20Mods/morrowind/Graphic%20Herbalism%20-%20Ultimate%20Override%20Patch).

---

## 14. Census & Excise Door Guard Facing Lock

* **Author**: Bethesda Softworks / MWSE Patch
* **File**: [personalEffectsFix.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/patches/personalEffectsFix.lua)
* **Bug**: In `Seyda Neen, Census and Excise Office`, the doorway guard (`chargen door guard`, Ganciele Douar, Ref 172857) has an `AI_Wander(0)` package. When the player walks past him towards the hallway door (`CharGen Door Hall` at (258, 255)), or triggers his voice greeting (`CharGenDoorGuardTalker`), the engine AI turns his body North towards the wall and doorway. Because distance is 0, the actor has no wander waypoints to return to, permanently freezing his orientation facing into the wooden pillar/wall across game sessions and save reloads.
* **Fix**: Added `restoreDoorGuardFacing()` in `personalEffectsFix.lua` that restores his orientation to `facing = math.pi` (180 degrees, pointing South directly into the room towards Socucius Ergalla's desk and the dock entrance). Automatically enforced on cell load/transition, periodic cell heartbeat, and upon exiting dialogue with the guard.

---

## 15. 50% Save Hang and CTD upon Leaving Census & Excise Office

* **Author**: `abot` / MWSE Guard Mods / Engine Bug
* **Files**:
  - [mwsaveguard/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwsaveguard/main.lua)
  - [personalEffectsFix.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/patches/personalEffectsFix.lua)
  - [Plain Paper Fix/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/abot/Plain%20Paper%20Fix/main.lua)
* **Bug**:
  1. In Morrowind, save game progress 0–50% serializes player stats and global data; at 50%, the engine enters `RecordsHandler::saveGame2` -> `Cell_static::saveReference` to serialize cell entities and placed references.
  2. Calling `mwscript.setDelete({ reference = ref })` or `ref:delete()` on placed interior cell references (such as `sc_paper plain` Ref 0x0104EA44 in `Seyda Neen, Census and Excise Office` by `Plain Paper Fix`, or duplicate actors by `mwsaveguard`) deallocates reference memory and attachments while the reference remains in the cell's active reference list. Subsequent engine allocations (such as `DialogueInfo` instances during conversations with Sellus Gravius or Census guards) reuse that freed heap address. During save serialization at 50%, `Cell_static::saveReference+0x288` attempts to serialize ExtraData type 6 (`ExtraScriptVariables`), dereferencing the reused pointer as a script object and crashing with `EXCEPTION_ACCESS_VIOLATION (C0000005)`.
  3. Furthermore, `mwsaveguard` and `personalEffectsFix` contained a geographic doorway heuristic (`math.abs(pos.x - 1173) < 250 and math.abs(pos.y - (-391)) < 250`) that falsely targeted legitimate NPCs near the exit door and invoked `ref.delete()` / `setDelete`, causing instant save corruption upon exiting the office.
* **Fix**:
  1. Completely removed all calls to `ref:delete()` and `mwscript.setDelete` across `Plain Paper Fix`, `mwsaveguard`, and `personalEffectsFix`. Placed references are now safely retired using `ref:disable()`, `ref.modified = true`, and moving position far out of bounds (`z = -10000`), preserving memory structure integrity and allowing the engine to serialize the disabled state without dangling pointers.
  2. Removed the overly aggressive geographic doorway rule from both `mwsaveguard` and `personalEffectsFix`, strictly limiting clone identification to explicit duplicate references (`playersavegame` or matching player base object and appearance).
  3. Added `sanitizeCellReferences()` to `mwsaveguard` executing immediately prior to save operations, verifying active cell references and cleaning any invalid script variable attachments on unscripted world references.

---

## 16. Custom Class Persistence Across New Game Playthroughs

* **Author**: `mwcustomclasspersistence`
* **Files**:
  - [mwcustomclasspersistence/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwcustomclasspersistence/main.lua)
  - [savedCustomClasses.json](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/config/savedCustomClasses.json)
* **Bug**:
  1. Custom classes created in character generation (`MenuCreateClass`) were not persisting to `savedCustomClasses.json` because the mod attempted to read `tes3.player.object.class` with a 1-frame delay upon clicking OK in `MenuCreateClass`. In Morrowind, clicking OK in `MenuCreateClass` transitions to `MenuStatReview`, and the class is not finalized on `tes3.player.object.class` until `MenuStatReview` is accepted or chargen concludes. The single-frame check failed, leaving `savedCustomClasses.json` uncreated and empty.
  2. When opening `MenuChooseClass` ("Pick from a list"), `mwcustomclasspersistence` did not reload saved classes from disk, failed to show any previously created custom classes, and lacked hooks to update `MenuStatReview` or recalculate starting attributes, skills, and derived stats (Health, Magicka, Fatigue) when selecting a custom class.
* **Fix**:
  1. Extracted the user's custom class **"Outlander"** (Combat specialization, Strength/Agility attributes, Major skills: Alchemy, Athletics, Restoration, Marksman, Mercantile; Minor skills: Armorer, Medium Armor, Sneak, Long Blade, Security) directly from recent save data and created [savedCustomClasses.json](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/config/savedCustomClasses.json).
  2. Overhauled `mwcustomclasspersistence/main.lua`:
     - Dynamically reloads `savedCustomClasses.json` every time `MenuChooseClass` opens.
     - Injects custom classes under a styled "--- Custom Classes ---" header in `MenuChooseClass_ClassScroll`.
     - Displays full specialization, favorite attributes, major/minor skills, and class description in the preview pane upon selection.
     - Recalculates all starting player attributes (+10 favorite bonuses), 27 skill ratings (race bonuses, +5 specialization bonus, +25 major bonus, +10 minor bonus), and derived Health, Magicka, and Fatigue.
     - Hooked `MenuStatReview` so the chosen custom class name is prominently reflected in the review window.
     - Auto-saves custom classes on `MenuStatReview` acceptance, `MenuCreateClass` submission, and savegame `loaded` events.

---

## 17. Plain Paper Fix Modernization (`mwplainpaperfix`)

* **Author**: Original Plain Paper Fix Creator / MWSE Modernization
* **Files**:
  - [mwplainpaperfix/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwplainpaperfix/main.lua)
  - [mwplainpaperfix/mcm.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwplainpaperfix/mcm.lua)
  - [mwplainpaperfix.json](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/config/mwplainpaperfix.json)
* **Features & Architecture**:
  1. Complete modern reimplementation of the historic "Plain Paper Fix" mod honoring the original creator.
  2. Full interactive MCM menu under **Plain Paper Fix**:
     - **Enable/Disable** toggle.
     - **Tweak Plain Paper Stats** with configurable Weight (0.05), Value (3), and Enchant Capacity (100).
     - **Interactive Whitelist & Blacklist Exclusions Page**: Two-column interactive interface where every paper, scroll, and document without text (734 unique items scanned from base game, DLCs, Tamriel Data, OAAB Data, TR_Mainland, and other landmass mods) is automatically whitelisted for direct inventory pickup, and every paper with written text (3,707 items) is blacklisted to open the reading window normally. Clicking any item interactively transfers it between the Whitelist and Blacklist.
     - **Re-scan All Plugins** button to instantly re-analyze all loaded plugins and auto-classify any newly added paper objects.
  3. Safe reference handling: completely avoids engine use-after-free and 50% save crashes by retiring picked-up papers via `ref:disable()`, `ref.modified = true`, and moving out of bounds (`z = -10000`), completely avoiding `setDelete` or `ref:delete()`.

---

## 18. No Accidental Theft - Owned Book Reading & Stealing Protection

* **Author**: `mer` / Unified Patch in `mwpluginpatches`
* **Files**:
  - [noAccidentalTheftBookFix.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/patches/noAccidentalTheftBookFix.lua)
  - [mwpluginpatches/config.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/config.lua)
  - [mwpluginpatches/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/main.lua)
  - [mwpluginpatches/mcm.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/mcm.lua)
  - [noAccidentalTheft.json](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/config/noAccidentalTheft.json)
* **Bug / Limitation**:
  `accidentalTheftProtection` blocks activating ANY owned world object unless the player is actively sneaking. This prevented players from opening and reading owned books, letters, notes, and documents in the world without sneaking first, even if they had no intention of stealing them.
* **Fix & Architecture**:
  1. Synchronized all 8,474 book IDs across loaded plugins into `noAccidentalTheft.json`'s `blacklist` table so `accidentalTheftProtection` permits activating them to read without sneaking.
  2. Created [noAccidentalTheftBookFix.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/patches/noAccidentalTheftBookFix.lua) in `mwpluginpatches`:
     - Tracks when an owned book or scroll is activated while standing (not sneaking).
     - When `MenuBook` or `MenuScroll` opens for an owned document while standing, the **Take** button (`MenuBook_button_take` / `MenuBook_PickupButton`) is automatically disabled, greyed out (`alpha = 0.35`), given a red tint (`negative_color`), and blocked from mouse clicks or hotkeys with an informational alert and hover tooltip ("Owned: Must sneak to take").
     - If the player is actively sneaking when activating the owned book, the Take button remains fully enabled to allow intentional theft with standard crime checks.
     - Includes configurable MCM option in `mwpluginpatches` to toggle the Take button appearance between **Disabled & Red Tint** and **Hidden / Missing**.

---

## 19. New Game Crash at Prison Ship Initialization (`sg_setLocalRotationMatrix`)

* **Author**: `personalEffectsFix.lua` / Engine Crash
* **Files**:
  - [personalEffectsFix.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/patches/personalEffectsFix.lua)
  - [noAccidentalTheftBookFix.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/patches/noAccidentalTheftBookFix.lua)
* **Bug**:
  1. In `personalEffectsFix.lua`, `restoreSellusFacing()` and `restoreDoorGuardFacing()` were registered to run on `loaded` via `schedulePurge()`. When starting a New Game, the player spawns in the `Imperial Prison Ship` tutorial cell, while `chargen captain` (Sellus Gravius) resides in `Seyda Neen, Census and Excise Office`. Calling `captain:updateSceneGraph()` while the actor's cell is unloaded and its `sceneNode` is `nil` dereferenced a null scene node pointer inside Morrowind's native `sg_setLocalRotationMatrix+0x19`, causing an instant crash to desktop (`EXCEPTION_ACCESS_VIOLATION 0xC0000005`) right after the intro BIK finishes.
  2. Additionally, in `noAccidentalTheftBookFix.lua`, `syncBlacklistWithBooks()` was invoked synchronously inside `initialized`, when `tes3.dataHandler.nonDynamicData.books` had not yet been loaded by the engine.
* **Fix**:
  1. In `personalEffectsFix.lua`, strictly guarded `restoreSellusFacing()`, `restoreDoorGuardFacing()`, and `schedulePurge()`:
     - They now verify that `tes3.player.cell` is `Seyda Neen, Census and Excise Office` before executing.
     - They check `captain.cell == pCell and captain.sceneNode ~= nil` and `guard.cell == pCell and guard.sceneNode ~= nil` before setting orientation and wrap `updateSceneGraph` in `pcall`.
  2. In `noAccidentalTheftBookFix.lua`, moved `syncBlacklistWithBooks()` to run on the `loaded` event and added `if not ndd or not ndd.books then return end` guards.

---

## 20. MWSE ExtraDataList Node Corruption CTD on Bread Pickup (`ScriptRecord::execute+0x24`)

* **Author**: `mwsaveguard`
* **File**: [mwsaveguard/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwsaveguard/main.lua)
* **Bug**:
  In `mwsaveguard/main.lua`, `sanitizeCellReferences()` called `ref.attachments.variables = nil` on cell references lacking scripts. In MWSE / Morrowind's C++ data structures, assigning `nil` to `ref.attachments.variables` does not cleanly unlink the `ExtraScriptVariables` node in the engine's `ExtraDataList`. Instead, it leaves an unlinked dangling pointer (`0x00000074`). When the player subsequently picked up an item (such as `ingred_bread_01`), the engine invoked `DataHandler::executeReferenceScripts` to traverse cell references and execute scripts, encountering `0x74` as a script pointer and immediately crashing with `EXCEPTION_ACCESS_VIOLATION` in `ScriptRecord::execute+0x24`.
* **Fix**:
  Removed `sanitizeCellReferences()` and all calls to `ref.attachments.variables = nil` from `mwsaveguard/main.lua`.

---

## 21. Custom Class Persistence UI IDs & `getStatistic` Nil Exception

* **Author**: `mwcustomclasspersistence`
* **File**: [mwcustomclasspersistence/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwcustomclasspersistence/main.lua)
* **Bug**:
  1. `applyCustomClassToPlayer()` called `tes3.getStatistic({ reference = tes3.player, ... })`. `tes3.getStatistic` does not exist in MWSE (statistics are read directly from `tes3.mobilePlayer.attributes[id+1].base` and `tes3.mobilePlayer.skills[id+1].base`), throwing `attempt to call field 'getStatistic' (a nil value)` at line 137 and aborting stat calculations.
  2. In `displayCustomClassInChooseMenu()`, element lookups passed raw string identifiers (e.g. `menu:findChild("MenuChooseClass_SelectedText")`) instead of registered integer IDs via `tes3ui.registerID()`. As a result, all lookups returned `nil`, leaving the right-hand details pane in the Choose Class menu blank or showing previous class details instead of the selected custom class ("Outlander").
  3. `formatSkillList` and attribute lookups referenced non-existent helpers (`tes3.getSkillName`, `tes3.getAttributeName`).
* **Fix**:
  1. Replaced `getStatistic` calls with direct `tes3.mobilePlayer.attributes[...]` reads.
  2. Wrapped all UI lookup strings in `tes3ui.registerID(...)`.
  3. Replaced skill and attribute helpers with standard `tes3.getSkill(id).name` and static `ATTRIBUTE_NAMES` mapping.

---

## 22. No Accidental Theft - Book Take Icon & Kezyma UI Reddening

* **Author**: Unified Patch in `mwpluginpatches`
* **File**: [noAccidentalTheftBookFix.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/patches/noAccidentalTheftBookFix.lua)
* **Bug**:
  In `handleBookUI()`, `menu:findChild("MenuBook_button_take")` passed raw string literals to `findChild`, which expects an integer ID. Consequently, `takeBtn` returned `nil`, and the Take button (including Kezyma UI's replacement hand icon) was not disabled or tinted red when reading owned books while standing.
* **Fix**:
  1. Registered and cached all numeric IDs: `MenuBook_button_take`, `MenuBook_PickupButton`, `MenuBook_button_take_idle`, `_over`, `_pressed`.
  2. Added recursive search and child element tinting: both the button container and all its child texture states (`_idle`, `_over`, `_pressed`) are colored with `negative_color` (red), dimmed (`alpha = 0.55`), disabled, blocked from click events with an alert, and updated with a theft warning tooltip.

---

## 24. Save Hang / Crash at 50% on Reference SCRI Pointer Dereference (`Cell_static::saveReference+0x607`)

* **Author**: `mwsaveguard` / `mwplainpaperfix` / Engine Bug
* **Files**:
  - [mwsaveguard/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwsaveguard/main.lua)
  - [mwplainpaperfix/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwplainpaperfix/main.lua)
  - [mwplainpaperfix/mcm.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwplainpaperfix/mcm.lua)
* **Bug**:
  1. In `mwplainpaperfix/main.lua`, `onLoaded()` modified base object stats for `sc_paper plain` (`value`, `weight`, `enchantCapacity = 100`). Modifying a base object record at runtime dirty-marked active cell references (including `sc_paper plain` FRMR 17099332 from Patch for Purists in the Census Office), forcing Morrowind to serialize them during cell saving. Furthermore, setting `enchantCapacity` on an unenchanted book record violates engine assumptions.
  2. Inside Morrowind's native reference serialization routine `Cell_static::saveReference`:
     ```x86asm
     0x004E19F8: 8B 43 14        mov eax, [ebx + 0x14]  ; script pointer from ExtraScriptVariables
     0x004E19FB: 85 C0           test eax, eax
     0x004E19FD: 74 41           jz 0x004E1A40
     0x004E19FF: 8B C8           mov ecx, eax
     0x004E1A01: 8B 11           mov edx, [ecx]
     0x004E1A07: FF 52 20        call [edx + 0x20]      ; CRASH / HANG AT 50%
     ```
     Vanilla code only checked `jz 0x004E1A40` (`eax == 0`). When a reference's ExtraData structure contained an invalid, negative, or flag value (e.g. `eax = 0x80000000`), the engine attempted to call `[edx + 0x20]`, resulting in a null/invalid pointer dereference (`EXCEPTION_ACCESS_VIOLATION`) that froze the game window at 50% save progress.
* **Fix**:
  1. In `mwsaveguard/main.lua`, installed an in-memory binary patch at `0x004E19FD` replacing `0x74` (`JZ`) with `0x7E` (`JLE`). If `eax <= 0` (including `0x80000000`, `0xFFFFFFFF`, or null), the engine jumps safely to `0x004E1A40`, bypassing the invalid script name call and cleanly serializing the reference.
  2. In `mwplainpaperfix/main.lua` and `mwplainpaperfix/mcm.lua`, removed all runtime base object mutations (`tweakPaperStats`, `paperWeight`, `paperValue`, `paperEnchantCapacity`) and removed forced `ref.modified = true` / position displacements, keeping the mod strictly focused on direct inventory pickup and sneak requirements.









