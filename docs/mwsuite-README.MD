# MW Conflict Tools Lua suite

Morrowind Conflict Tools started as a scripted dialogue repair utility. It now suffers from nuclear-powered feature creep. The Lua suite is the part that runs inside Morrowind through MWSE. It includes save and exit guards, troubleshooting tools, fixes for specific mod combinations, and a few gameplay conveniences.

## Getting to the settings

- Start the game through the project's [normal setup and launch workflow](../README.md). The launch workflow brings the Lua suite into Data Files.
- Open **Options → Mod Config → MW Conflict Tools**. Use the main tabs to select a module. If the module has more than one page, its own tabs appear below.
- Hover over a setting or button for its explanation. Settings are saved as you leave a module or close the menu. If a setting asks for a restart, exit Morrowind and start it again.
- Use the module's main switch to turn on its features, then choose the individual changes you want. If an existing mod already does the same job, check the in-game description before letting both handle it.

## Saves, transitions and troubleshooting

| Tab | What it does |
| --- | --- |
| **Save Guard** | Lets quicksaves and autosaves wait for loading to settle. Set the delay in seconds. Separate switches handle stray player copies, validation before loading a save, and notices about saves blocked by another mod. If Well Behaved Sound Replacers is detected, its tavern-performance save block can be relaxed separately. |
| **Teleport** | Holds a move triggered by dialogue until you leave the conversation. Choose whether companions follow, whether the conversation offers only **Goodbye** while a move is pending, and whether the screen fades. The fade slider is in seconds. |
| **Mouse** | Keeps the pointer within Morrowind so the wheel does not scroll a second screen. You can choose gameplay and menus separately. The pointer is released when you leave the window. |
| **Warnings** | Filters selected groups of repetitive warning messages. The general switch controls the filter and the individual switches choose the groups. Disable the filter when you need to collect those messages. |
| **Guard & Watch** | **Memory & Hang Log** shows or warns about address-space use and can record what the game was doing. **Lua Profiler** times Lua handlers and writes reports. These features have separate switches. |
| **Exit Guard** | Closes Morrowind promptly after you confirm Exit. **Save before quitting.** The optional skip-confirmation switch makes Exit immediate, and the Alt+F4 switch applies the fast exit to that shortcut. The separate **New Game** switch blocks a second game start within the same process. Loading another save still works. |

### What to turn on when the game misbehaves

- **Memory rising:** In **Guard & Watch → Memory & Hang Log**, turn on **Show memory usage on screen**. Enable the warning and set its percentage if you want an alert. The figure tracks Morrowind's address space. A Large Address Aware build on 64-bit Windows can address up to 4 GB.
- **Freeze or crash:** Enable **Record a hang log** before reproducing the problem. Find the output in **Data Files/MWSE/logs/mwhangwatch.log**. The log starts fresh each game launch, so copy it before retesting.
- **Audio problem:** Turn on **Include audio in the log** only when needed. Set **Sound lines per second** to **0** for audio summaries only, or raise the limit to capture individual starts and stops.
- **Frame-time spikes:** Enable the **Lua profiler** and restart. The report interval is in seconds and the slow-handler threshold is in milliseconds. A sample rate of **1** times every frame. Larger numbers sample less often. Reports go to **Data Files/MWSE/logs/mwguard.log**.

## World, dialogue and sound repairs

| Tab | What it does |
| --- | --- |
| **Floating Items** | Lowers loose things onto nearby surfaces. The sliders set the tolerated gap, the maximum drop and the distance that counts as wall-mounted, in game units. Carryable lights have a separate switch. Use **Moved / Never move** to exempt items from the fix. The hide hotkey and **Hidden Objects** page manage objects you hide manually. |
| **Doubled Objects** | Uses the tools' overlap results to hide overlapping copies. After rebuilding the results, use the reload action to refresh the current area. Turning the fix off restores hidden copies as you revisit areas. |
| **Stranded Objects** | Uses the tools' results for objects and actors left outside a rebuilt interior. Moving useful objects and hiding stranded scenery have separate switches. Reload the results to apply your choices to the current room. |
| **Performers** | Lets one bard or musician perform per building. You can also pause the animation during conversation, change the wait before playing resumes, or choose a performer again in the current building. |
| **Dialogue Loops** | Can check dialogue at startup when the load order changes and stop loops during conversations. Separate controls govern whether to let a line through to break a loop, skip recurring **Choice** responses, and trace every chosen reply. Clearing the last check requests a new scan on the next launch. |
| **Sound Guard** | Stops repeated object sounds from stacking up. Loop gap is in seconds. The runaway count controls when a loop is reported, and the rate setting caps rapid repeats of short sounds. Actor-loop monitoring logs repeats on actors for diagnosis. |
| **Sound Repairs** | Lists the script repairs built by the offline sound-fix pass. Use **Previous** and **Next** to browse up to 100 entries per page. If the page is empty, the suite has no repair list to display. |

## Console and gameplay

| Tab | What it does |
| --- | --- |
| **Console** | Adds console commands and completion, a selection-details panel and a magic-effect inspector. **Settings** controls what is available, when suggestions appear and which key opens the selection details. **Commands** lists available commands. **Developer** controls saved Lua commands, their safety restrictions, and their instruction limit. **Remove my active magic effects** acts immediately in a loaded game. |
| **Quick Keys** | Pressing the quick key for an item already equipped can take it off. The second switch can restore the previously equipped item, such as the shield you were holding before a two-handed weapon. |
| **Custom Classes** | Saves classes you make through **Create Class**. When starting another character, find those classes at the bottom of the class list. |
| **Crime & Locks** | Controls sneak-to-steal behavior, reading owned books and plain paper, sneaking detection, and locked-door rules. The inspector shows who can see you. The companion detection list and the separate **Blacklist** for objects have different jobs. Shift+activate an object to exempt it from this module, and use **Remove** to restore normal handling. |
| **Companions** | Controls when followers catch up, share movement abilities, join fights or recover after a killing blow. The **Excluded Plugins** page excludes creatures supplied by selected plugins. **Blacklist** excludes specific actors. **Whitelist** takes precedence for listed actors who are actually following you. Check the options you already use in Smart Companions or Attend Me before enabling overlapping features. |

## Compatibility Patches

Open **Patches** and use its master switch. Each patch heading names the mod it works with and tells you whether that mod was detected. Existing choices are saved. **Restart Morrowind after changing a patch setting.**

- **Quests:** Dialogue, quest timing, rewards and starting equipment.
- **Startup:** Answers startup questions for supported mods and handles selected startup messages.
- **Interface:** Dialogue topic display, indicators, and console output related to supported mods.
- **Gameplay:** Harvest timing, follower HUD behavior, combat visuals, and other interactions.
- **Performance:** Reduces repeated checks or lookups in supported mods.
- **Musical Instruments:** Chooses which items Bardic Inspiration can play when its instrument patch is on. Click an item to move it between the lists.

For automatic startup answers, set your choices before the target mod initializes in that save. Changing answers afterward may leave the save's existing setup in place.
