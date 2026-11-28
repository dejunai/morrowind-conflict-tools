# Quick Start (beta)

These tools look over a modded Morrowind and fix what they safely can: plugins that fight over the same thing, broken dialogue, missing or broken files, load order, and known bugs in MWSE Lua mods. They are made for big mod lists, and for players who would rather not fix mods by hand.

You don't need to know any code. You will double-click a few files, and now and then type one short command.

**It's a beta.** Everything the tools change is backed up first, and every change can be undone. Still, back up your saved games before your first real run, just in case.

---

## 1. Install

1. **Install Python** (free): [python.org/downloads/windows](https://www.python.org/downloads/windows/), version 3.9 or newer. In the installer, tick **"Add python.exe to PATH"**.
2. **Download the tools**: `conflict-tools-<version>.zip` from the GitHub **Releases** page. Don't use the green "Code > Download ZIP" button: that one holds the developer files too.
3. **Unzip it into your Morrowind folder**, the one with `Morrowind.exe` in it. You should end up with a `conflict-tools` folder beside `Morrowind.exe`.

That's it. Nothing is installed into Windows, and deleting the `conflict-tools` folder removes the tools.

## 2. Typing a command (when this guide asks you to)

1. Open the `conflict-tools` folder in File Explorer.
2. Click the address bar at the top, type `cmd` and press Enter. A black window opens, already in the right folder.
3. Type the command shown in this guide and press Enter.

Close the game before you run any of these.

## 3. Have a look (changes nothing)

Double-click **`mwdialog_check.bat`**.

It reads your plugins and opens a report in Notepad. It changes nothing in your game. Each problem is marked:

- **ERROR**: something that can break your game (a crash, a missing master, a broken quest line).
- **WARN**: something that probably doesn't work as the mod author meant.
- **INFO** (hidden unless you ask for it): harmless notes.

Don't worry if the list is long. A big mod list always has a lot in it, and most of it gets fixed in step 5.

## 4. Tidy your mods (Vortex users only)

Skip this step if you don't use Vortex. Mod Organizer 2 isn't supported yet.

Tidy sorts each mod's folder in Vortex: it moves readmes and screenshots out of the way, sets aside files the game can't use, repairs textures, swaps broken files the game would crash on for harmless stand-ins, and patches known bugs in MWSE Lua mods.

1. Double-click **`vortex_tidy.bat`**. This only makes a **plan** and changes nothing. The plan is in `conflict-tools\plans\vortex_tidy_plan.txt`, so have a read.
2. Optional, but good practice: in Vortex, click **Purge**.
3. Type `vortex_tidy.bat --apply` (see section 2). It does exactly what the plan said. If anything changed since the plan was made, it refuses and makes a fresh plan for you to read.
4. In Vortex, click **Deploy**. Vortex removes the files tidy moved and puts the rest in place.

Changed your mind? `vortex_tidy.bat --undo` puts back everything the last `--apply` did (Deploy after, as above).

## 5. Fix everything

1. **See what it would do** (nothing is changed): type `mwdialog_check.bat --full --dry-run`.
2. **Do it**: type `mwdialog_check.bat --full`.

If you have saved games in the `Saves` folder, a bare `--full` (no `--preserve-saves`, not a dry run) asks you to confirm first, because it rewrites plugins and the load order. Mid-playthrough, use `--preserve-saves=strict` instead. `--yes` skips the question; with no console and no `--yes`, the run refuses and changes nothing.

**In the middle of a playthrough?** Add `--preserve-saves`, for example `mwdialog_check.bat --full --preserve-saves`. It holds back the fixes that could upset a saved game and tells you what it held back. For the most careful version, use `--preserve-saves=strict`, which also leaves your active plugins exactly as they are.

`--full` turns off plugins that do nothing your other plugins don't already do, cleans and fixes plugins, sorts the load order, merges what can be merged, and builds a patch for the rest. Each plugin it changes is backed up first, as a `.bak` file beside it.

Along the way it may ask you questions in the black window, for example which of two mods should win where they change the same place. It remembers your answers, so the next `--full` only asks about new conflicts.

If something is missing (for example a plugin's master file isn't installed), it stops before changing anything and tells you what to install.

**Undo**: `mwdialog_check.bat --undo-all` puts every changed plugin back to its original and turns back on the plugins it turned off. Add `--dry-run` first to see what it would do.

## 6. Play

Double-click **`Play Morrowind.bat`** in the `conflict-tools` folder (you can copy it into the Morrowind folder if you like).

It checks that every plugin's masters are there, writes your load order into `Morrowind.ini`, brings the MWSE helper mods up to date, and starts Morrowind. MGE XE and MWSE still load as usual. If it finds a problem, it doesn't start the game: the window stays open and tells you why.

---

## Where things are

| What | Where |
|---|---|
| The report | `conflict-tools\generated\mwdialog_report.txt` |
| Your load order | `conflict-tools\generated\mwdialog_load_order.txt` |
| Tidy's plan | `conflict-tools\plans\vortex_tidy_plan.txt` |
| Backups | `conflict-tools\backups\`, and `.bak` files beside changed plugins |
| Notes for mod authors | `<plugin>.bugreport.txt`, in a `bugreports` folder in the mod's Vortex folder (or in the Morrowind folder) |

## Something went wrong?

- **Undo tidy**: `vortex_tidy.bat --undo`
- **Undo plugin fixes**: `mwdialog_check.bat --undo-all`
- **"Python was not found"**: reinstall Python and tick "Add python.exe to PATH".
- **Still stuck?** Type `vortex_tidy.bat --pack-report`. It packs the report and the logs into one zip in `conflict-tools\reports\`, with your folder names and Windows user name taken out, and changes nothing in your game. Open an issue on the GitHub page and attach that zip, with a copy of what the black window said.

## Want more?

The [README](../README.md) lists every switch, and [MORE_INFO](MORE_INFO.md) explains how every part works.
