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

* **Author**: Melchior Dahrk and Greatness7 (MWSE Lua by Greatness7). [Keg Drip](https://www.nexusmods.com/morrowind/mods/47903)
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

* **Author**: Anumaril21. [Essential Indicators](https://www.nexusmods.com/morrowind/mods/48267)
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

* **Author**: Kleidium. [Companion Leveler](https://www.nexusmods.com/morrowind/mods/51760)
* **File**: [mcm.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/companionLeveler/mcm.lua#L436-L530)
* **Bug**: EasyMCM sliders under the "Attribute Modifiers" category failed to render track elements properly and collapsed to zero width on certain screen resolutions and UI scalings.
* **Fix**: Added a `postCreate = fixSlider` callback for each attribute modifier slider, enforcing `minWidth = 180`, ensuring child element visibility, and synchronizing widget values during layout.

---

## 6. Character Sound Overhaul

* **Author**: Anumaril21. [Character Sound Overhaul](https://www.nexusmods.com/morrowind/mods/49654)
* **File**: [interop.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/Character%20Sound%20Overhaul/interop.lua#L80-L98)
* **Bug**: `this.addSoundData` logged every individual sound registration via `mwse.log()`, dumping over 20,000 lines into `MWSE.log` during game launch and pushing other mod logs out of buffer.
* **Fix**: Redirected sound registrations into a separate dedicated log file ([Data Files/MWSE/logs/CSO_soundData.log](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/logs/CSO_soundData.log)).

---

## 7. Elemental Effects

* **Author**: Anumaril21. [Elemental Effects](https://www.nexusmods.com/morrowind/mods/49799)
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

* **Author**: TES3 Community. [Let There Be Darkness](https://www.nexusmods.com/morrowind/mods/47912)
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

* **Author**: Morrowind Conflict Tools (`mwcriminal` inspector UI).
* **File**: [inspectorUI.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwsuite/mwcriminal/inspectorUI.lua#L292-L340)
* **Bug**: Invoked `inputBorder.marginRight = 8` and `clearBtn.marginRight = 8` during search-bar UI construction. `tes3uiElement` does not define `marginRight` (only `borderRight`), throwing `sol: cannot set (new_index) into this object: no defined new_index operation on usertype`, which corrupted the UI element tree and caused engine hangs on game exit.
* **Fix**: Replaced invalid `marginRight` calls with `borderRight = 8`.

---

## 12. The Doors of Oblivion

* **Author**: Ashstaar, as credited on [The Doors of Oblivion release page](https://www.nexusmods.com/morrowind/mods/44398).
* **File**: [Tx_metal_strip_02.tga](file:///g:/Vortex%20Mods/morrowind/The%20Doors%20of%20Oblivion%201.4-44398-1-4/textures/Tx_metal_strip_02.tga)
* **Bug**: Shipped an obsolete 12KB `Tx_metal_strip_02.tga` filled with near-zero black pixels (RGB 21, 25, 26). Because the Morrowind engine prioritizes loose `.tga` matches over `.dds` textures, this file crushed textures on every model referencing `Tx_metal_strip_02` (such as the standard common chest `contain_com_chest_02.nif`), overriding installed 2K MET / Articus / Vurt `.dds` replacements and rendering chests completely black in-game.
* **Fix**: Moved `Tx_metal_strip_02.tga` to `Off/textures/` and pruned the deployed file from `Data Files/Textures/`, allowing the high-definition `tx_metal_strip_02.dds` texture to load as intended.

---

## 13. Graphic Herbalism & Harvest Lights Integration

* **Authors**: Stuporstar and Greatness7 ([Graphic Herbalism MWSE/OpenMW](https://www.nexusmods.com/morrowind/mods/46599)), RogiVagel ([Graphic Herbalism ReVisited](https://www.nexusmods.com/morrowind/mods/52666)), and Kynesifnar ([Harvest Lights MWSE Edition](https://www.nexusmods.com/morrowind/mods/57276)).
* **Files**:
  * [main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/graphicHerbalism/main.lua)
  * [main.lua (Patch Staging)](file:///G:/Vortex%20Mods/morrowind/Graphic%20Herbalism%20-%20Ultimate%20Override%20Patch/MWSE/mods/graphicHerbalism/main.lua)
* **Bugs**:
  1. Flora without dedicated `HerbalismSwitch` NIFs (unpatched plants, custom landmass flora from Tamriel Rebuilt, Project Cyrodiil, SHOTN, or mods lacking switch models) failed to visually change when picked because `updateHerbalismSwitch()` returned early on missing `switchNode`, leaving picked flora models unaltered.
  2. In `updateHerbalismSwitch()`, changes to `switchNode.switchIndex` were made without invoking `sceneNode:update()`, preventing immediate NetImmerse bounding box and visible subtree recalculations.
  3. In `onActivate()`, Graphic Herbalism intercepted the activation and returned `false` without firing `event.trigger("containerClosed", { reference = ref })`. Because `HarvestLights` depends on `containerClosed` to shut off lights associated with glowing mushrooms and flora (`bc mushroom 256`, glowing lichen, etc.), glowing lights remained burning after flora was harvested.
  4. Mushroom replacements in prior patch staging were misplaced under `Meshes/fg/` (Flora Glow paths) instead of standard game paths (`Meshes/f/flora_bc_mushroom_*.nif`), causing conflicting replacers without switch nodes to win file precedence and leaving Seyda Neen courtyard mushrooms un-harvestable visually.
  5. **Pre-harvest Flora Reversion on Save Load**: Harvested flora state (`ref.data.GH = 1`) persisted in save files, but upon reloading a game, flora reverted visually to unharvested models and became non-interactive. This was caused by two compounding engine/lifecycle bugs:
     * `onCellChanged` guarded updates behind `if today > (day or 0)`. On Day 0 (start of a new game), `DaysPassed` is 0, so `0 > 0` evaluated to `false`, bypassing cell updates entirely.
     * When the `loaded` event fires, reference scene nodes (`ref.sceneNode`) are not yet constructed. Graphic Herbalism lacked a `referenceActivated` event listener, so when Morrowind subsequently constructed the 3D meshes, they loaded with default unharvested NIF states (`switchIndex = 0`, `appCulled = false`) and were never switched.
* **Fix**:
  1. Added universal vaporization fallback: when `switchNode` is missing or invalid on harvest, `sceneNode.appCulled = true` is applied and tracked in `ref.data.GH`. When cell resets/respawns (`index == 0`), `sceneNode.appCulled = false` restores the flora.
  2. Enhanced switch indexing: resolves target children by name (`HARVESTED`/`PICKED`/`NORMAL`/`SPOILED`) with index clamping, unsets `appCulled`, and executes `sceneNode:update()`.
  3. Added `event.trigger("containerClosed", { reference = ref })` inside `onActivate()` so `HarvestLights` immediately disables associated light sources when glowing flora is picked.
  4. Guarded `onActivate` and `onTooltipDrawn` against harvested flora using both `ref.data.GH` and `ref.sceneNode.appCulled`.
  5. Assembled all 816 validated modifying NIFs (base game, DLCs, glowing mushrooms, smoothed marshmerrow, and landmass flora) and 36 associated high-quality textures into a unified Vortex staging override package at [Graphic Herbalism - Ultimate Override Patch](file:///G:/Vortex%20Mods/morrowind/Graphic%20Herbalism%20-%20Ultimate%20Override%20Patch).
  6. Added a `referenceActivated` event listener to apply `updateHerbalismSwitch(ref, ref.data.GH)` the moment any flora's 3D scene node is attached. Refactored `onCellChanged` to check `if day == nil or today > day` with string cell keys, ensuring Day 0 initialization and cell transitions always execute.

---

## 14. Census & Excise Door Guard Facing Lock

* **Credits**: Bethesda Softworks (base game) and Morrowind Conflict Tools (`personalEffectsFix.lua`).
* **File**: [personalEffectsFix.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/patches/personalEffectsFix.lua)
* **Bug**: In `Seyda Neen, Census and Excise Office`, the doorway guard (`chargen door guard`, Ganciele Douar, Ref 172857) has an `AI_Wander(0)` package. When the player walks past him towards the hallway door (`CharGen Door Hall` at (258, 255)), or triggers his voice greeting (`CharGenDoorGuardTalker`), the engine AI turns his body North towards the wall and doorway. Because distance is 0, the actor has no wander waypoints to return to, permanently freezing his orientation facing into the wooden pillar/wall across game sessions and save reloads.
* **Fix**: Added `restoreDoorGuardFacing()` in `personalEffectsFix.lua` that restores his orientation to `facing = math.pi` (180 degrees, pointing South directly into the room towards Socucius Ergalla's desk and the dock entrance). Automatically enforced on cell load/transition, periodic cell heartbeat, and upon exiting dialogue with the guard.

---

## 15. 50% Save Hang and CTD upon Leaving Census & Excise Office

* **Credits**: abot (MWSE Plain Paper Fix) and Morrowind Conflict Tools (`mwsaveguard` and `personalEffectsFix.lua`).
* **Files**:
  - [mwsaveguard/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwsuite/mwsaveguard/main.lua)
  - [personalEffectsFix.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/patches/personalEffectsFix.lua)
  - [Plain Paper Fix/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/abot/Plain%20Paper%20Fix/main.lua)
* **Bug**:
  1. In Morrowind, save game progress 0–50% serializes player stats and global data; at 50%, the engine enters `RecordsHandler::saveGame2` -> `Cell_static::saveReference` to serialize cell entities and placed references.
  2. Calling `mwscript.setDelete({ reference = ref })` or `ref:delete()` on placed interior cell references (such as `sc_paper plain` Ref 0x0104EA44 in `Seyda Neen, Census and Excise Office` by `Plain Paper Fix`, or duplicate actors by `mwsaveguard`) deallocates reference memory and attachments while the reference remains in the cell's active reference list. Subsequent engine allocations (such as `DialogueInfo` instances during conversations with Sellus Gravius or Census guards) reuse that freed heap address. During save serialization at 50%, `Cell_static::saveReference+0x288` attempts to serialize ExtraData type 6 (`ExtraScriptVariables`), dereferencing the reused pointer as a script object and crashing with `EXCEPTION_ACCESS_VIOLATION (C0000005)`.
  3. Furthermore, `mwsaveguard` and `personalEffectsFix` contained a geographic doorway heuristic (`math.abs(pos.x - 1173) < 250 and math.abs(pos.y - (-391)) < 250`) that falsely targeted legitimate NPCs near the exit door and invoked `ref.delete()` / `setDelete`, causing instant save corruption upon exiting the office.
* **Fix**:
  1. Completely removed all calls to `ref:delete()` and `mwscript.setDelete` across `Plain Paper Fix`, `mwsaveguard`, and `personalEffectsFix`. Placed references are now safely retired using `ref:disable()`, `ref.modified = true`, and moving position far out of bounds (`z = -10000`), preserving memory structure integrity and allowing the engine to serialize the disabled state without dangling pointers.
  2. Removed the overly aggressive geographic doorway rule from both `mwsaveguard` and `personalEffectsFix`, strictly limiting clone identification to explicit duplicate references (`playersavegame` or the player's own base object; appearance alone is not a clone).
  3. Added `sanitizeCellReferences()` to `mwsaveguard` executing immediately prior to save operations, verifying active cell references and cleaning any invalid script variable attachments on unscripted world references.

---

## 16. Custom Class Persistence Across New Game Playthroughs

* **Author**: Morrowind Conflict Tools (`mwcustomclasspersistence`).
* **Files**:
  - [mwcustomclasspersistence/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwsuite/mwcustomclasspersistence/main.lua)
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

* **Credits**: XmirroR ([original Plain Paper Fix](https://www.nexusmods.com/morrowind/mods/52309?tab=files)), abot (the separate [MWSE Plain Paper Fix](https://www.nexusmods.com/morrowind/mods/47735)), and Morrowind Conflict Tools (the `mwplainpaperfix` reimplementation documented here).
* **Files**:
  - [mwplainpaperfix/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwplainpaperfix/main.lua)
  - [mwplainpaperfix/mcm.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwplainpaperfix/mcm.lua)
  - [mwplainpaperfix.json](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/config/mwplainpaperfix.json)
* **Features & Architecture**:
  1. Modern reimplementation of XmirroR's original Plain Paper Fix.
  2. Full interactive MCM menu under **Plain Paper Fix**:
     - **Enable/Disable** toggle.
     - **Tweak Plain Paper Stats** with configurable Weight (0.05), Value (3), and Enchant Capacity (100).
     - **Interactive Whitelist & Blacklist Exclusions Page**: Two-column interactive interface where every paper, scroll, and document without text (734 unique items scanned from base game, DLCs, Tamriel Data, OAAB Data, TR_Mainland, and other landmass mods) is automatically whitelisted for direct inventory pickup, and every paper with written text (3,707 items) is blacklisted to open the reading window normally. Clicking any item interactively transfers it between the Whitelist and Blacklist.
     - **Re-scan All Plugins** button to instantly re-analyze all loaded plugins and auto-classify any newly added paper objects.
  3. Safe reference handling: completely avoids engine use-after-free and 50% save crashes by retiring picked-up papers via `ref:disable()`, `ref.modified = true`, and moving out of bounds (`z = -10000`), completely avoiding `setDelete` or `ref:delete()`.

---

## 18. Accidental Theft Protection - Owned Book Reading & Stealing Protection

* **Credits**: Merlord ([Accidental Theft Protection](https://www.nexusmods.com/morrowind/mods/48264)) and Morrowind Conflict Tools (the `mwpluginpatches` compatibility patch).
* **Files**:
  - [noAccidentalTheftBookFix.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/patches/noAccidentalTheftBookFix.lua)
  - [mwpluginpatches/config.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwsuite/mwpluginpatches/config.lua)
  - [mwpluginpatches/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwsuite/mwpluginpatches/main.lua)
  - [mwpluginpatches/mcm.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwsuite/mwpluginpatches/mcm.lua)
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

* **Author**: Morrowind Conflict Tools (`personalEffectsFix.lua` and `noAccidentalTheftBookFix.lua`).
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

* **Author**: Morrowind Conflict Tools (`mwsaveguard`).
* **File**: [mwsaveguard/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwsuite/mwsaveguard/main.lua)
* **Bug**:
  In `mwsaveguard/main.lua`, `sanitizeCellReferences()` called `ref.attachments.variables = nil` on cell references lacking scripts. In MWSE / Morrowind's C++ data structures, assigning `nil` to `ref.attachments.variables` does not cleanly unlink the `ExtraScriptVariables` node in the engine's `ExtraDataList`. Instead, it leaves an unlinked dangling pointer (`0x00000074`). When the player subsequently picked up an item (such as `ingred_bread_01`), the engine invoked `DataHandler::executeReferenceScripts` to traverse cell references and execute scripts, encountering `0x74` as a script pointer and immediately crashing with `EXCEPTION_ACCESS_VIOLATION` in `ScriptRecord::execute+0x24`.
* **Fix**:
  Removed `sanitizeCellReferences()` and all calls to `ref.attachments.variables = nil` from `mwsaveguard/main.lua`.

---

## 21. Custom Class Persistence UI IDs & `getStatistic` Nil Exception

* **Author**: Morrowind Conflict Tools (`mwcustomclasspersistence`).
* **File**: [mwcustomclasspersistence/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwsuite/mwcustomclasspersistence/main.lua)
* **Bug**:
  1. `applyCustomClassToPlayer()` called `tes3.getStatistic({ reference = tes3.player, ... })`. `tes3.getStatistic` does not exist in MWSE (statistics are read directly from `tes3.mobilePlayer.attributes[id+1].base` and `tes3.mobilePlayer.skills[id+1].base`), throwing `attempt to call field 'getStatistic' (a nil value)` at line 137 and aborting stat calculations.
  2. In `displayCustomClassInChooseMenu()`, element lookups passed raw string identifiers (e.g. `menu:findChild("MenuChooseClass_SelectedText")`) instead of registered integer IDs via `tes3ui.registerID()`. As a result, all lookups returned `nil`, leaving the right-hand details pane in the Choose Class menu blank or showing previous class details instead of the selected custom class ("Outlander").
  3. `formatSkillList` and attribute lookups referenced non-existent helpers (`tes3.getSkillName`, `tes3.getAttributeName`).
* **Fix**:
  1. Replaced `getStatistic` calls with direct `tes3.mobilePlayer.attributes[...]` reads.
  2. Wrapped all UI lookup strings in `tes3ui.registerID(...)`.
  3. Replaced skill and attribute helpers with standard `tes3.getSkill(id).name` and static `ATTRIBUTE_NAMES` mapping.

---

## 22. Accidental Theft Protection - Book Take Icon & Kezyma UI Reddening

* **Credits**: Morrowind Conflict Tools (the `mwpluginpatches` compatibility patch for Merlord's [Accidental Theft Protection](https://www.nexusmods.com/morrowind/mods/48264)).
* **File**: [noAccidentalTheftBookFix.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/patches/noAccidentalTheftBookFix.lua)
* **Bug**:
  In `handleBookUI()`, `menu:findChild("MenuBook_button_take")` passed raw string literals to `findChild`, which expects an integer ID. Consequently, `takeBtn` returned `nil`, and the Take button (including Kezyma UI's replacement hand icon) was not disabled or tinted red when reading owned books while standing.
* **Fix**:
  1. Registered and cached all numeric IDs: `MenuBook_button_take`, `MenuBook_PickupButton`, `MenuBook_button_take_idle`, `_over`, `_pressed`.
  2. Added recursive search and child element tinting: both the button container and all its child texture states (`_idle`, `_over`, `_pressed`) are colored with `negative_color` (red), dimmed (`alpha = 0.55`), disabled, blocked from click events with an alert, and updated with a theft warning tooltip.

---

## 25. MWSE Core MCM ExclusionsPage Destroyed Element Access (`toggleFiltered` & `resetToDefault`)

* **Authors**: [MWSE contributors](https://github.com/MWSE/MWSE).
* **File**: [exclusionspage.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/core/mcm/components/pages/exclusionspage.lua#L82-L91)
* **Bug**:
  In `exclusionspage.lua`, both `resetToDefault()` (line 88) and `toggleFiltered()` (line 226) attempted to destroy and recreate the exclusions page layout with:
  ```lua
  self.elements.outerContainer.parent:destroyChildren()
  self:create(self.elements.outerContainer.parent)
  ```
  `self.elements.outerContainer` is a child of `outerContainer.parent`. Calling `parent:destroyChildren()` immediately deletes `outerContainer`. The very next line then attempts to index `.parent` on the destroyed element (`self.elements.outerContainer.parent`), causing Sol to throw an unhandled Lua exception during the UI click/key event:
  `sol: 'self' argument is lua_nil (bad '.' access?)`
* **Fix**:
  1. Cached `local parent = self.elements.outerContainer.parent` before invoking `parent:destroyChildren()`, and passed `parent` directly into `self:create(parent)`.
  2. In `toggle()` (line 135) and `updateSearch()` (line 157), guarded `self.elements.outerContainer:getTopLevelMenu():updateLayout()` with `local topMenu = self.elements.outerContainer and self.elements.outerContainer:getTopLevelMenu()` before calling `:updateLayout()` to prevent `sol: 'self' argument is lua_nil` crashes during search bar reset / filter switching when the top-level menu is not yet resolved.

---

## 26. More Console Commands (MCC) Duplicate Command Registration in `mweffectinspector`

* **Credits**: JosephMcKean ([More Console Commands](https://www.nexusmods.com/morrowind/mods/52500)) and Morrowind Conflict Tools (`mweffectinspector`, where the duplicate registration occurred).
* **File**: [mweffectinspector/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwsuite/mweffectinspector/main.lua#L49-L78)
* **Bug**:
  `tryRegisterWithMCC()` was invoked both during `onInitialized` and registered as a listener on the `command:register` event. Because `mweffectinspector` initializes before MCC (priority 0 vs priority -999), the first call registered `showeffects` and `cleareffects`. When MCC subsequently initialized and triggered `command:register`, `tryRegisterWithMCC()` executed a second time, triggering MCC's error log in `data.lua`:
  `[More Console Commands | data.lua:908 | ERROR] Attempt to create existing command ... Use modify() instead.`
* **Fix**:
  Added an idempotent guard (`local mccRegistered = false`) and an existence check against `interop.data.commands[cmd.name:lower()]` before registering commands, preventing duplicate registrations.
* **Status (2026-11-25)**:
  `mweffectinspector` has been removed from the suite. `showeffects` and `cleareffects` now belong to `mwconsole`, which registers them once. This entry is kept as history.

---

## 27. Unthrottled Per-Frame Achievement Evaluation in `sb_achievements`

* **Author**: Safebox - Pirate, as credited on the [achievement framework release page](https://www.nexusmods.com/morrowind/mods/51081).
* **File**: [sb_achievements/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/sb_achievements/main.lua#L35-L42)
* **Bug**:
  `enterFrameCallback` ran unthrottled on every single render frame (60–80x/sec). On every frame, it looped over all registered achievements and executed their Lua condition and progress functions, consuming ~1 ms/frame average CPU and producing micro-stutter spikes up to 50 ms.
* **Fix**:
  Throttled `enterFrameCallback` using `os.clock()` so achievement progress and unlock conditions are evaluated at most once every 2.0 seconds.

---

## 28. Unthrottled Per-Frame Flora Raycasting in `tew/AURA` (`florasounds.lua`)

* **Authors**: tewlwolow and stanliqubit. [AURA](https://www.nexusmods.com/morrowind/mods/48255)
* **File**: [tew/aura/misc/florasounds.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/tew/aura/misc/florasounds.lua#L93-L115)
* **Bug**:
  `playFlora` ran on `simulate` (every frame), executing a downwards `tes3.rayTest` with `useModelCoordinates = true` even when the player was completely stationary or walking over non-vegetation surfaces. This raycast consumed ~1 ms of frame time (~1,250 ms CPU time per 30 seconds).
* **Fix**:
  1. Throttled the simulation check to at most once every 0.20 seconds (5 checks/sec, matching natural footstep cadence).
  2. Added a stationary distance check (`playerPos:distance(lastCheckPos) < 25`) so raycasting is skipped completely when the player is not moving.
  3. Eliminated redundant vector cloning allocations.

---

## 29. False-Positive Recovery Fade in `mwpluginpatches` (`psguardfix.lua`)

* **Credits**: Arci (Arcimaestro Antares, [Privileges and Services](https://www.nexusmods.com/morrowind/mods/50403)) and Morrowind Conflict Tools (`psguardfix.lua`, where the false positive occurred).
* **File**: [mwpluginpatches/patches/psguardfix.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwpluginpatches/patches/psguardfix.lua#L119-L162)
* **Bug**:
  `psguardfix` monitored P&S scripts (`ABM_ll_DetectPCCrimeScript`, `ABM_PutItBackScript`) which are triggered by ambient NPC voice/trespass evaluations. When an evaluation passed with no crime detected, the script stopped naturally without ever invoking `FadeOut`. However, `psguardfix` assumed that *any* script termination with no guard present meant the screen was stuck black, erroneously triggering `fadeBackIn()` and logging misleading recovery messages.
* **Fix**:
  Updated `fadeBackIn()` to check `tes3.worldController.transitionFader.value > 0.05` before executing a fade or logging, ensuring recovery only runs when the screen was actually left faded to black.

---

## 30. Guards Treated as Companions During Sneaking in Companion Mods and Stealth Detection

* **Credits**: Kleidium ([Companion Leveler](https://www.nexusmods.com/morrowind/mods/51760)), Pirate ([HUD Companion Health Bar](https://www.nexusmods.com/morrowind/mods/60242)), drekar51 ([Attend Me Expanded MWSE](https://www.nexusmods.com/morrowind/mods/60810)), and Morrowind Conflict Tools (the former `mwcompanionsneak`, now part of `mwcriminal`).
* **Files**:
  - [companionLeveler/functions/common.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/companionLeveler/functions/common.lua#L522-L548)
  - [Pirate/HUD Companion Health Bar/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/Pirate/HUD%20Companion%20Health%20Bar/main.lua#L85-L108)
  - [AttendMeMWSE/followers.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/AttendMeMWSE/followers.lua#L17-L38)
  - [mwcriminal/core.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwsuite/mwcriminal/core.lua#L203-L206)
* **Bug**:
  When sneaking near a guard, `MoreAttentiveGuards` (`celediel/MoreAttentiveGuards/sneak.lua`) assigns the guard a temporary `tes3.aiPackage.follow` targeting the player while inspecting them. Because `companionLeveler`, `HUD Companion Health Bar`, and `AttendMeMWSE` only checked for a follow package targeting the player without verifying `obj.isGuard` or guard class/script:
  1. `companionLeveler` added the guard to `npcTable()`, initialized blank companion mod data on the guard reference, and logged `Companion Mod Data not found, setting to base Mod Data values` / `NPC Mod Data not found, setting to base Mod Data values`.
  2. `HUD Companion Health Bar` and `AttendMeMWSE` immediately instantiated health/magicka/fatigue UI elements for the guard, forcing the player to manually blacklist them.
* **Fix**:
  The retired `mwcompanionsneak` detector is now part of `mwcriminal`; it excludes explicit `isGuard` records and no longer uses broad class-name matching, which could reject legitimate companions. The separate third-party companion fixes still need their own upstream review.

---

## 31. Multi-Monitor Secondary Screen Scroll Bleed in `mwmouseguard` (`main.lua`)

* **Author**: Morrowind Conflict Tools (`mwmouseguard`).
* **File**: [mwmouseguard/main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mwsuite/mwmouseguard/main.lua#L37-L145)
* **Bug**:
  `mwmouseguard` set the Win32 `ClipCursor` rectangle to `[0, 0, width, height]`. Because Win32 `ClipCursor` bounds are inclusive (`left <= x <= right`), the cursor was allowed to sit at `x = width`. In dual-monitor setups, `x = width` is the very first pixel column of the adjacent monitor, causing Windows 10/11 "Scroll inactive windows when hovering" to route `WM_MOUSEWHEEL` to the second screen. Furthermore, Windows automatically clears `ClipCursor` on window activation shifts, notifications, or modal dialogs; `mwmouseguard` used a one-shot latch (`if not isClipped or fg ~= cachedHwnd`) and never reclipped once Windows reset the clip.
* **Fix**:
  1. Inset the clipping rectangle by 2px on all edges (`left + 2, top + 2, right - 2, bottom - 2`), strictly confining the cursor inside Morrowind's monitor and preventing border drift.
  2. Added Win32 `GetClipCursor` verification to continuously detect if Windows dropped the clip, immediately restoring it.
  3. Added `tes3.event.mouseWheel` verification and reduced check interval to 0.15s with proper timer reference handling.

---

## 33. BSAPack Exclusion List, Unprocessable Asset Guard, & Progress Prompts

* **Files**:
  - [bsapack.cpp](file:///k:/Downloads/Browser/bsapack%20source/bsapack.cpp)
  - [bsapack.h](file:///k:/Downloads/Browser/bsapack%20source/bsapack.h)
  - [bsapack.dej.exe (build directory)](file:///k:/Downloads/Browser/bsapack%20source/bsapack.dej.exe)
  - [bsapack.dej.exe (conflict-tools tools)](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/conflict-tools/tools/bsapack.dej.exe)
* **Feature & Fix**:
  1. **Exclusion List Support (`-exclude <file>`)**:
     - Added `-exclude <file>` / `--exclude <file>` / `-exclude=<file>` flag (with `-except` maintained as an alias):
       `bsapack pack <folder|archive> [split_size_mb] -exclude <exclusions.txt>`
     - Reads one exclusion entry per line, supporting relative paths (`Textures\my_image.png`, `Data Files\Sound\foo.wav`), directory prefixes (`sound\`, `music\`), and extension patterns (`*.png`, `.png`).
     - Normalizes paths (strips `data files\`, `.\`, quotes, trims whitespace, standardizes slashes to `\`, case-folds).
     - Applied binary search `bsearch` on sorted exact keys for $O(\log N)$ performance over tens of thousands of files.
  2. **Preserved Loose Files / Error Exemption**:
     - Exclusion list filtering executes *before* Morrowind BSA asset type compatibility validation.
     - Files matched by the exclusion list remain loose on disk and are completely exempt from unprocessable asset checks (e.g. `.png`, `.wav`), producing zero errors or false-positive aborts.
  3. **Unprocessable Asset Guard**:
     - Morrowind's native engine only resolves Meshes, Textures, Icons, BookArt, and Splash from BSA archives. Audio (`Sound`, `Music`), fonts (`Fonts`), video cutscenes (`Video`), scripts, and text files must remain loose.
     - Any non-excluded unprocessable assets trigger an explicit error listing each offending file and reason, aborting the pack to avoid game corruptions.
  4. **Status Prompts**:
     - Configured `#define STATUS_INTERVAL 2000` so progress outputs claim how many files have been processed every 2,000 files and when segments change.

---

## 34. `altvadder\splash` CTD on `MenuLoading` `updateLayout` (`EXCEPTION_ACCESS_VIOLATION 0xC0000005`)

* **Author**: Altvadder. [Regional Splashscreens (MWSE)](https://www.nexusmods.com/morrowind/mods/58512)
* **File**: [altvadder\splash\main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/altvadder/splash/main.lua#L110-L360)
* **Bug**:
  1. `altvadder\splash` intercepts `MenuLoading` via `uiActivated`. Inside `uiActivated`, it called `menu:createImage({ path = chosen })` for uncompressed high-resolution splash `.tga` files (e.g. `Morrowind.tga`, 2048x1024, ~8.4 MB uncompressed D3D surface) followed immediately by a synchronous `menu:updateLayout()`.
  2. In 32-bit Morrowind (4.00 GiB virtual address space limit), when virtual memory usage reaches 95-98% (here 3.94 GiB / 98.62%), contiguous memory is completely fragmented. D3D/NetImmerse's texture allocation fails and returns NULL. NetImmerse dereferences the pointer during `updateLayout`, triggering a fatal `EXCEPTION_ACCESS_VIOLATION (0xC0000005)`. Because hardware access violations are OS-level structured exceptions, Lua's `pcall` cannot catch or prevent the process from crashing.
  3. Calling `menu:updateLayout()` synchronously from inside `uiActivated` is re-entrant: the engine is in the middle of constructing the menu widget tree when `uiActivated` fires.
  4. Additionally, `enforceTimer` was hammering `m:updateLayout()` 10 times a second (`0.1s` interval), and `slideshowTimer` loaded additional uncompressed multi-megabyte textures into NetImmerse's `NiSourceTexture` cache during cell loading without checking available memory.
* **Fix**:
  1. Added `isMemorySafe()` guard: queries `mwse.getVirtualMemoryUsage()`. If 32-bit virtual memory exceeds 3400 MB (~83%), custom splash injection and slideshow cycling are automatically bypassed, letting the lightweight vanilla loading screen render safely without crashing.
  2. Removed the synchronous re-entrant `menu:updateLayout()` from line 259. Morrowind's native UI loop automatically performs initial layout and drawing when `uiActivated` returns.
  3. Guarded full-screen menu styling and background rect creation: they are only applied after verifying that the image element was successfully created.
  4. Relaxed `enforceTimer` to 0.25s, added menu visibility and `isMemorySafe()` guards, and wrapped layout calls in protected executions.

---

## 35. MCM Accidental Theft Protection "Books" Crash (`ERROR_NOT_ENOUGH_MEMORY 0x80070008` / `0xC0000005`)

* **Credits**: [MWSE contributors](https://github.com/MWSE/MWSE) (`ExclusionsPage.lua`) and Merlord ([Accidental Theft Protection](https://www.nexusmods.com/morrowind/mods/48264)).
* **Files**:
  - [ExclusionsPage.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/core/mcm/components/pages/ExclusionsPage.lua#L20-L245)
  - [accidentalTheftProtection\main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mer/accidentalTheftProtection/main.lua#L1-L70)
  - [noAccidentalTheft.json](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/config/noAccidentalTheft.json)
* **Bug**:
  1. In MWSE's `ExclusionsPage.lua`, selecting any category with thousands of items (such as "Books" with 8,474+ objects across base game, Tamriel Rebuilt, OAAB, etc.) looped across all items and called `list:createTextSelect` for every single item without any limit or virtualization.
  2. Creating 8,474+ native C++ UI elements simultaneously in a single scrollable container exhausted the 32-bit heap (virtual memory reached 3.98 GiB / 99.41%), failing with Windows error `0x80070008` ("Not enough memory resources are available to process this command") and an immediate `EXCEPTION_ACCESS_VIOLATION (0xC0000005)` crash to desktop.
  3. Furthermore, `noAccidentalTheft.json` was previously bloated with 10,437 individual book IDs (including invalid non-UTF8 ANSI characters) in an attempt to whitelist all books for reading without sneaking.
* **Fix**:
  1. In `ExclusionsPage.lua`, introduced `MAX_DISPLAY_ITEMS = 200` and updated `distributeLeft` / `distributeRight` / `updateSearch` / `toggleFiltered`:
     - Renders at most 200 items into each column, appending a notice: `"... and X more items (type in Search to filter)"`.
     - The search box now dynamically filters the full in-memory list and renders matching items up to 200 items in under 1ms with negligible memory overhead.
  2. In `accidentalTheftProtection\main.lua`, added native `allowReadingBooks = true` support:
     - Directly checks `obj.objectType == tes3.objectType.book` in `onActivate(e)`, allowing any book or scroll in any mod to be opened and read without sneaking (while `noAccidentalTheftBookFix` protects the Take button).
     - Added an MCM toggle for "Allow reading owned books without sneaking".
  3. Cleaned `noAccidentalTheft.json` to `{ "enabled": true, "allowReadingBooks": true, "blacklist": {} }`, dropping its file size from 363 KB of bloated book IDs down to clean JSON.

---

## 36. MWSE Core File Reading, JSON/Config Loading, & MCM Resilience Audit

* **Authors**: [MWSE contributors](https://github.com/MWSE/MWSE).
* **Files**:
  - [initialize.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/core/initialize.lua#L235-L830)
  - [mcm\main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/core/mcm/main.lua#L45-L215)
  - [Template.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/core/mcm/components/templates/Template.lua#L150-L345)
  - [ConfigVariable.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/core/mcm/variables/ConfigVariable.lua#L10-L40)
  - [TableVariable.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/core/mcm/variables/TableVariable.lua#L10-L27)
  - [Dropdown.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/core/mcm/components/settings/Dropdown.lua#L15-L85)
  - [CycleButton.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/core/mcm/components/settings/CycleButton.lua#L15-L25)
* **Bug**:
  1. `json.loadfile` opened files in Windows text mode (`"r"`), risking premature truncation on Ctrl-Z (`0x1A`), did not strip UTF-8 BOM (`\xEF\xBB\xBF`), and did not wrap `json.decode` in `pcall`. Any invalid byte (such as Windows-1252 high bytes `0x91-0x94` from Morrowind record text) or trailing comma caused unhandled parse aborts.
  2. `json.savefile` and `toml.saveFile` used raw `assert(io.open(...))`. If parent directories did not exist or permissions failed, Lua threw an unhandled crash. Furthermore, `json.savefile` appended `.json` unconditionally, creating `.json.json` when callers included an extension.
  3. `mwse.loadConfig` and `fixLoadedResult` assumed the loaded config was a table; if corrupted to a boolean or primitive, indexing keys crashed. Subtables in `fixLoadedResult` also failed if a primitive was loaded where defaults expected a table.
  4. `mwse.loadTranslations` and `loadLocaleFile` called unhandled `error` and hard `assert` when translation files were missing or invalid tables, crashing mod initialization instead of falling back to default keys.
  5. In MCM components (`main.lua`, `Template.lua`, `Dropdown.lua`, `ConfigVariable.lua`, `TableVariable.lua`), unguarded `#config.favorites`, missing `findMenu` checks, unverified `headerImagePath` elements, missing tab lookups, and uninitialized `options` or `self.table` references caused nil-indexing crashes.
* **Fix**:
  1. Updated `json.loadfile` to open in binary mode (`"rb"`), strip UTF-8 BOM, protect decode with `pcall`, and apply automatic multi-stage fallbacks: trailing comma trimming before `}`/`]` and sanitizing Windows-1252 curly quotes/dashes into standard ASCII.
  2. Updated `json.savefile` and `toml.saveFile`: added `.json` normalization, automatic recursive parent directory creation, safe `io.open` error logging (no assert crash), and protected encoding preventing open handle leaks.
  3. Hardened `mwse.loadConfig` with `type(result) ~= "table"` reset and updated `fixLoadedResult` to replace primitive values with deep copies of default subtables when schema expects tables.
  4. Added binary reading, BOM stripping, and empty-file guards to `toml.loadFile` and `yaml.loadFile`.
  5. Converted `mwse.loadTranslations` and `loadLocaleFile` to non-fatal warning logging with automatic string passthrough fallback if translation tables are missing.
  6. Added nil-safe guards in MCM components for menus, header images, tab lists, favorites length checks, config variables, and options tables.

---

## 37. Accidental Theft Protection Door Interaction & Erroneous Seyda Neen Tavern Ownership

* **Credits**: Merlord ([Accidental Theft Protection](https://www.nexusmods.com/morrowind/mods/48264)) and the OAAB team (tavern door record).
* **Files**:
  - [main.lua](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/MWSE/mods/mer/accidentalTheftProtection/main.lua)
  - [main.lua (Vortex Staging)](file:///G:/Vortex%20Mods/morrowind/Accidental%20Theft%20Protection-48264-1-0-1-1590981508/MWSE/mods/mer/accidentalTheftProtection/main.lua)
  - [Seyda Neen - Damp Little Squat - unshabby.ESP](file:///g:/Program%20Files/Steam/steamapps/common/Morrowind/Data%20Files/Seyda%20Neen%20-%20Damp%20Little%20Squat%20-%20unshabby.ESP)
* **Bug**:
  1. `accidentalTheftProtection` intercepted the `activate` event for all references lacking player ownership (`not tes3.hasOwnershipAccess{target = e.target}`). Because it did not filter by object type, any owned door reference (such as the interior exit door in Seyda Neen Lighthouse owned by Thavere Vedrano) unconditionally returned `false` unless the player was sneaking, trapping the player inside interiors and requiring sneaking to leave buildings.
  2. In `Seyda Neen - Damp Little Squat - unshabby.ESP`, the exterior doors leading to public establishments—The Dirty Anchor (FRMR 20) and The Glass Parrot (FRMR 21, 22)—erroneously retained `ANAM: indrele rathryon` from copied shack references. Although the doors were unlocked (`INTV: 0`), UI Expansion flagged them as "Owner: Indrele Rathryon" with red activation crosshairs, and `accidentalTheftProtection` dropped activation clicks without sneaking, giving the appearance of being locked in broad daylight.
* **Fix**:
  1. Updated `accidentalTheftProtection\main.lua` with door bypass logic: door references are never blocked without sneaking if the player is in an interior cell (`tes3.player.cell.isInterior`), if the door leads to an exterior (`ref.destination.cell and not ref.destination.cell.isInterior`), or if the door is unlocked (`not (ref.lockNode and ref.lockNode.locked)`). Interior door navigation and exits now always work freely.
  2. Removed spurious `ANAM: indrele rathryon` ownership subrecords from FRMR 20, 21, and 22 in `Seyda Neen - Damp Little Squat - unshabby.ESP` (and synchronized with Vortex staging), restoring the tavern and glass shop doors to standard public unowned access.

---

## 38. UI Expansion Dialogue Topic Cached Info Lookup Bug

* **Author**: NullCascade
* **Files**:
  - `Data Files\MWSE\mods\UI Expansion\MenuDialog.lua` (lines 111-135)
  - the same file in its Vortex staging folder (`UI Expansion v1.7.3-46071-1-7-3-1729551917`)
* **Bug**:
  1. In `MenuDialog.lua` line 113, inside `updateTopicsList`, the cached dialogue info property lookup queries an empty string:
     ```lua
     local info = element:getPropertyObject("") or dialogue:getInfo({ actor = mobileActor })
     ```
  2. In line 128, the element stores this property under the key `"MenuDialog_UIEXP_info"`:
     ```lua
     element:setPropertyObject("MenuDialog_UIEXP_info", info)
     ```
     and line 72 retrieves it via `e.source:getPropertyObject("MenuDialog_UIEXP_info")`.
  3. Because `element:getPropertyObject("")` queries an empty key name, it always returns `nil`. As a result, the cached info object is never retrieved, forcing `dialogue:getInfo({ actor = mobileActor })` to re-execute unconditionally on every topic click and hyperlink update.
  4. For NPCs with actor-unique dialogue (such as Silt Strider caravaners like Darvame Hleran, quest NPCs, or faction authorities), once the player hears a unique line, `e.info.firstHeardFrom = e.actor` is recorded. However, because line 113 never retrieves the cached info, subsequent evaluations can resolve alternate unread lines or fail to reflect the recorded `firstHeardFrom` state. Consequently, topics with actor-unique responses fail to grey out (`state = 2`) and remain stuck permanently in the unique/blue active state (`state = 4`).
  5. Because `updateTopicsList` is a local closure registered directly to `preUpdate` and `mouseClick` UI callbacks, patching this behavior from an external Lua script is not feasible without overriding or rewriting the entire dialogue menu component.
* **Fix**:
  1. In `MenuDialog.lua` line 113, corrected `element:getPropertyObject("")` to `element:getPropertyObject("MenuDialog_UIEXP_info")`.
  2. Topic buttons now properly retrieve their cached info, allowing topics with exhausted actor-unique lines to transition smoothly to seen/greyed (`state = 2`).
  3. Hardlink parity (`nlink=2`) with its Vortex staging folder is preserved.

---

## 39. MWSE Core ExclusionsPage Unbounded Object UI (`KB4`)

* **Authors**: [MWSE contributors](https://github.com/MWSE/MWSE).
* **File**: `Data Files\MWSE\core\mcm\components\pages\ExclusionsPage.lua`
* **Bug**:
  `ExclusionsPage` can receive every object contributed by the full plugin set. The earlier emergency cap rendered
  only the first 200 entries in each column and offered no way to reach later entries. The original implementation
  created a native UI element for every object; on a large load order this exhausts Morrowind's 32-bit address space.
* **Fix**:
  1. Enforce a strict page size of 100 native item elements per column.
  2. Add Previous/Next controls with current page, total pages, and matching-item count.
  3. Clamp pages after moves and reset to page 1 when the search text or object/plugin filter changes.
  4. Keep filtering and bulk-toggle semantics over the complete logical list; only native UI construction is paged.
* **Luafix grade**: `(Known Bugs) KB4: MWSE Core: ExclusionsPage builds one UI element per item, unbounded`.
  This requires editing MWSE Core's local page implementation and cannot be repaired safely by a separate Lua mod.
  Its three fingerprints are exact text of MWSE's own file (unchanged upstream since 2024-07-19; a copy is in
  `tests\fixtures\mwse\`), and KB4 applies whole or not at all. `vortex_tidy.py` checks the file in
  `Data Files\MWSE\core` (or in a staged mod that ships MWSE) and writes the patch in place, journaled and marked
  `localpatch`; nothing deploys a replacement file. (The fingerprints before 2026-11-24 targeted the earlier local
  200-item edit, which MWSE never shipped, so on a stock file only one of their six parts matched.)
* **Related audit**:
  Core MCM `main.lua` also builds one entry per registered mod and `Dropdown.lua` builds one entry per supplied option.
  They are not classified as this confirmed bug: registered-mod and ordinary dropdown counts are much smaller, and
  changing their search/selection semantics without a reproduced memory failure would be speculative.

## 40. MUSE MCM Calls Do Not Parse in LuaJIT (`KB5`)

* **Author**: Rytelier. [MUSE 2](https://www.nexusmods.com/morrowind/mods/46200)
* **File**: `MWSE\mods\music\MUSE.lua`
* **Bug**:
  The MCM builder contains two `category:createOnOffButton` calls with the method name on one line and the
  parenthesized argument on the next. LuaJIT treats the following `(` as an ambiguous new statement and rejects
  the entire file at the first call (line 311), so MUSE cannot load.
* **Fix**:
  1. Join the method name and opening parenthesis for both calls.
  2. Luafix identifies only this exact MUSE fingerprint, then verifies that the repaired source compiles before
     allowing a Known Bugs patch to replace a source that did not compile.
* **Luafix grade**: `(Known Bugs) KB5: MUSE 2.02: two MCM calls split a parenthesized argument after the method name`.

## 41. OpenUI Enchanted Weapon Condition (`KB6`)

* **Author**: Spammer. [OpenHUD - MWSE Port](https://www.nexusmods.com/morrowind/mods/51220)
* **File**: `MWSE\mods\Spammer\OpenUI - MWSE\mod.lua`
* **Bug**: The enchanted-weapon HUD reads `weapon.itemData.condition` before checking whether
  instance data exists. The 2026-11-21 session produced 12,321 timer errors when it was nil.
* **Fix**: Use the weapon's maximum condition for an undamaged instance without item data;
  preserve the instance condition when present. Luafix repairs the exact vulnerable fingerprint.

## 42. Friends & Frens Companion Birthsign (`KB7`)

* **Author**: Danae CutthroatMods. [Friends & Frens](https://www.nexusmods.com/morrowind/mods/52763)
* **File**: `MWSE\mods\Danae\frens\main.lua`; the faulty line is in `Friends & Frens - base.esm`,
  topic *Abilities*, INFO `2876022601681025611`.
* **Bug**: The response says "born under the sign of the %Sign". The engine has no such dialogue variable, and
  the value is the companion's script local `birthsign` (1-13, rolled per save from `aa_ff_comp_birthsign`),
  which response text cannot show.
* **Fix**: The mod's own Lua fills in the sign of the companion being spoken to as the text is read. The master
  is not edited, so its size, the plugins built on it and existing saves are untouched. A companion with no
  birthsign (the mod gives many of them neither a sign item nor the list) says "a sign I never learned".
* **For the author**: Either the same handler, or 13 responses filtered on the local `birthsign`; and give the
  companions without a sign the levelled list.

## 43. Tamriel Data Detect Invisibility During Loading (`KB8`)

* **Author**: Tamriel Data (the same `magic.lua` also ships in Cyr_Main, Sky_Main and Tamriel Rebuilt)
* **File**: `MWSE\mods\TamrielData\magic.lua`, `detectInvisibilityValid` / `onInvisibilityEffectActivated`
* **Bug**: `magicEffectActivated` fires while a save is loading, and the handler iterates the actor's spell list.
  For an actor whose record is in the save, that list can still hold the saved ids instead of spells.
  `CS_Casimir1` (Casimir's Legacy) is such an actor: "ghost ability" is first in its list and gives it chameleon.
  MWSE reports `unknown object type ... 0x736f6867` (the bytes "ghos"), then
  `magic\tes3.lua:23: attempt to index local 'spell' (a nil value)`.
* **Fix**: During a load the actor is queued by safe handle, and judged on `loaded` (or on the first `simulate`,
  should the load be cancelled). The detection tick waits the same way. MWSE's core is not edited.
* **Earlier fix, lost**: `patch_mwse_magic_nil.py` (2026-11-05) nil-checked MWSE's core and wrapped the call in
  `pcall`. The core edit went with the MWSE update of 2026-11-10, the other with a later copy of `magic.lua`. It
  also hid the symptom only: the warning stayed, and the ghost's ability went unrecognized.
* **For the author**: Don't read `object.spells` from `magicEffectActivated` before `loaded`.

## 44. Directional Sunrays Sun Update Before There Is Weather (`KB9`)

* **Author**: Kynesifnar (Directional Sunrays v1.3)
* **File**: `MWSE\mods\DirectionalSunrays\main.lua`, `updateSun` / `disableSunrays`
* **Bug**: Every `simulate` indoors it calls the engine's `WeatherController::updateSun` (0x43FF80) through FFI.
  Just after a new game is started from inside the game there is no current weather yet; the engine reads it
  and crashes: `EXCEPTION_ACCESS_VIOLATION` in `WeatherController::updateSun`, Lua stack
  `directionalsunrays\main.lua:71` (MWSE.log 2026-11-22). Robenhood, Nocturnal Moths and Tamriel Data log
  "weather is nil" in the same moment, but those are Lua errors MWSE catches.
* **Fix**: `updateSun` returns early when `weatherController.currentWeather` is nil, and the sunray pass skips
  that frame.
* **Luafix grade**: `(Known Bugs) KB9: Directional Sunrays`.
* **For the author**: Check `tes3.worldController.weatherController.currentWeather` before calling engine
  functions through FFI.

## 45. Later Known Bugs now applied by luafix (`KB23`, `KB29`-`KB51`)

Hand repairs of released third-party Lua (and one upstream MUSE 2.02 syntax bug) are now exact Known Bugs
rules, so a Vortex reinstall or a return to the released files still gets them. The fingerprints live in
`mwdialog_luafix_kb.py` (`KB23`, `KB29`-`KB50`) and in `mwdialog_luafix.py` (`KB51`, next to `KB5`). There is still no
KB18 (the WBSR save-block conflict stays in `mwsaveguard.wbsr_bard`).

* **Removed 2026-11-26**: the asset-path entries `KB20`-`KB27` (Magicka Expanded, DRIP, OAAB Grazelands, The Garden
  of Dreams, SSQN Patches, SSQN LE, Map Icons) and the general rule `I1` that replaced four of them. Icons and
  textures stay as the mod ships them; luafix rewrites no image path or extension. `KB28`, `KB51` and `KB5`
  were retired in favour of `Y1`; they are regression fixtures in `tests/fixtures/luafix_retired_kb.py`.
* **Syntax (`KB28`, `KB51`)**: Creatures and Critters `danae\cc\main.lua` is missing three commas in the
  `_plume` ids list. MUSE 2.02 (and the official Patch for MUSE 2 v2.02) `music\cell.lua`, `combat.lua`,
  `interior.lua` and `region.lua` put a newline between `MUSE.DebugLog` and `(`, which LuaJIT rejects as
  ambiguous syntax, so MUSE never loads those modules. `KB51` joins the call onto one line.
* **Nil guards, bad handlers, stacked registration (`KB23`, `KB29`-`KB48`, `KB50`)**: Secrets of the Crystal
  City, Buying Game, Companion Leveler, Imperial Stables, Elemental Effects, Essential Indicators, Improved
  Global Map Markers, Lucid Disturbing Dreams, Morrowind Achievement Collection, Bardic Inspiration, Hidden
  Robe Armor, Just Drop It, MUSE, Memento Mori, The Achievement Framework, Onion, Small QoL Improvements,
  MWSE Set Bonus, MWSE Lanterns, Dynamic Object Replacer, and Watch the Skies (15 files). Typical defects:
  indexing `tes3.player`, a cell, item data or a mobile before it exists; starting a timer or registering an
  event again on every load; concatenating a boolean into a log line.
* **Logic (`KB49`)**: Animated Dialogue's pose blender blends the root bones and flips the actor 180 degrees
  against the engine's facing when dialogue ends.

The catalog in docs/MORE_INFO.md lists each rule and the exact relative `Data Files\MWSE` paths. First-party
mwsuite files are never patched: their names live in `lua tools\MWSE\mods\mwsuite\ownmods.json`.
