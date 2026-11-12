@echo off
rem ------------------------------------------------------------------
rem  mwdialog_check.bat - run the Morrowind dialogue checker
rem
rem  Double-click: scans "Data Files" using Morrowind.ini's load order,
rem                saves the report to mwdialog_report.txt and opens it.
rem
rem  From a command prompt, any arguments are passed straight through:
rem    mwdialog_check.bat --only MyMod.esp
rem    mwdialog_check.bat --min-severity WARN --csv report.csv
rem    mwdialog_check.bat --no-sounds
rem    mwdialog_check.bat --help
rem
rem  Fixing ERRORs:
rem    .esp files are fixed in place (backed up to .esp.bak first)
rem    .esm files are never changed; their fixes go into
rem    "mwdialog_check - ESM fixes.esp" - activate it after the first run
rem
rem    mwdialog_check.bat --fix --dry-run          (show the plan only)
rem    mwdialog_check.bat --fix                    (asks before writing)
rem    mwdialog_check.bat --only MyMod.esp --fix   (one plugin)
rem    mwdialog_check.bat --restore MyMod.esp      (undo: put the .bak back)
rem    mwdialog_check.bat --restore-all            (undo everything: all plugins to originals)
rem    mwdialog_check.bat --fix --no-placeholders  (no stand-in coins for missing script objects)
rem    mwdialog_check.bat --min-severity INFO      (also show harmless notes)
rem
rem  tes3cmd features (in place, .bak first, file dates kept, no Clean_ copies):
rem    mwdialog_check.bat --all --dry-run          (clean + fix + multipatch: plan only)
rem    mwdialog_check.bat --all                    (clean, then fix, then multipatch)
rem    mwdialog_check.bat --full                   (everything, from scratch. Stops first if a plugin's
rem       master isn't in Data Files, naming both. Then: turn back on what earlier runs turned off,
rem       --unmerge, --cell-conflicts (report), --sort, --all --asset-check. Any ERROR left: it stops
rem       and opens mwdialog_report.txt. Else --auto-merge, --sort, --all; any ERROR left: stops and
rem       opens the report. Else it offers the interactive --cell-conflicts. --yes: no questions;
rem       --add-all-esp: add every plugin first; --play: start the game at the end)
rem    mwdialog_check.bat --clean                  (like tes3cmd clean)
rem    mwdialog_check.bat --multipatch             (like tes3cmd multipatch; load it LAST)
rem    mwdialog_check.bat --header MyMod.esp       (show Author/Description)
rem    mwdialog_check.bat --header MyMod.esp --set-author "Me"
rem    mwdialog_check.bat --trace SomeObjectID > trace.txt   (who defines/places/scripts it)
rem    mwdialog_check.bat --cell-conflicts > conflicts.txt  (plugins that build in the same spot,
rem                                                 change the same objects or cell settings)
rem    mwdialog_check.bat --cell-conflicts --only MyMod.esp  (just the conflicts of one plugin)
rem    mwdialog_check.bat --cell-conflicts   (in the window it then asks, per conflict: add an
rem       [Order] rule either way, turn one plugin off, Enter skip, q stop; then offers --sort.
rem       --no-interactive, --dry-run or "> file" only report)
rem    --fix also turns off a plugin when another active one places the same objects twice
rem    (two versions of one mod); listed in mwdialog_disabled.txt, skipped by --add-all-esp:
rem    mwdialog_check.bat --reenable "Some Mod.esp"   (turn it back on; no name = all of them)
rem    mwdialog_check.bat --fix --no-doubled       (fix without that step)
rem    --fix also removes doubled bards: where two plugins each put a performer in one inn, the
rem    plugin loading last keeps its bard; the earlier one's added bards are deleted through
rem    "mwdialog_check Performers Patch.esp" (rebuilt each --fix). --no-performers skips it.
rem    --fix also drops leveled list entries naming objects that exist nowhere.
rem    Asset check (off unless asked for; adds a few minutes):
rem    mwdialog_check.bat --asset-check           (report missing files: models and their
rem                                                textures, icons, sounds, landscape and
rem                                                birthsign textures, music/voice/video
rem                                                named by scripts, fonts and sky textures)
rem    mwdialog_check.bat --asset-check --fix     (and fix them)
rem    With --fix, a placed or used object whose file can't load gets, in this order:
rem      0. the file back from .Orphaned (TextureAudit's orphan isolator moved it)
rem      1. the real file, found in a Vortex mod folder but never deployed: copied in
rem      2. the file an earlier version of the record uses (e.g. Bloodmoon.esm's model)
rem      3. a stand-in of the same kind (statics/activators: the invisible editor marker)
rem    A broken version that a later plugin replaces with a working one is removed.
rem    Missing textures of used models: real file from Vortex, or a 4x4 placeholder.
rem    Missing sounds and music: silent stand-in files. Files MWSE Lua mods load are
rem    moved back from .Orphaned. Files put in Data Files are listed in
rem    mwdialog_generated_files.txt:
rem    mwdialog_check.bat --remove-generated      (delete them again)
rem    mwdialog_check.bat --asset-check --fix --no-vortex  (don't search Vortex folders)
rem
rem  Load order: the active plugins are kept in mwdialog_load_order.txt (made from
rem  Morrowind.ini the first time). Any run that changes that list (--sort, --add-all-esp,
rem  merges, plugins turned off...) writes it into Morrowind.ini's [Game Files] as it ends,
rem  so MGE XE's distant land generator sees the same order; --play writes it again.
rem  The order itself is set by plugin dates, one day apart from 2000-01-01:
rem    mwdialog_check.bat --sort --dry-run         (show what would move)
rem    mwdialog_check.bat --sort                   (masters first, then mwdialog_check.rules.txt,
rem                                                 mlox\mlox_user.txt, mlox\mlox_base.txt)
rem    mwdialog_check.bat --restore-dates          (undo the last sort)
rem    mwdialog_check.bat --add-all-esp --dry-run  (list plugins that would be activated)
rem    mwdialog_check.bat --add-all-esp --sort     (activate every .esm/.esp in Data Files, then sort)
rem    mwdialog_check.bat --play                   (start Morrowind.exe directly, no Launcher)
rem                                                (checks first: if a plugin's master is off,
rem                                                 missing or loads after it, it doesn't start;
rem                                                 --play-anyway starts it regardless)
rem    mwdialog_check.bat --sort --play            (sort the load order, then start the game)
rem    mwdialog_check.bat --clean-up --dry-run     (list .bak backups that would be deleted)
rem    mwdialog_check.bat --clean-up               (delete backups of removed plugins; keep 1 per plugin)
rem    mwdialog_check.bat --merge "Merged.esp" "Extras\some-folder" --dry-run   (preview a merge)
rem    mwdialog_check.bat --merge "Merged.esp" a.esp b.esp ...   (merge; inputs for uninstalled mods are left out)
rem    mwdialog_check.bat --auto-merge --dry-run   (find small script-free plugins that can be merged)
rem    mwdialog_check.bat --auto-merge             (merge them and deactivate the originals)
rem                                                (run again to rebuild: the old merge is kept as .bak,
rem                                                 its plugins come back and are sorted, then it is
rem                                                 rebuilt from scratch)
rem    mwdialog_check.bat --unmerge                (undo: reactivate the originals, remove the merge)
rem    mwdialog_check.bat --update-rules --dry-run (mlox rules the sort skips, and why)
rem    mwdialog_check.bat --update-rules           (remove those steps from mlox\mlox_*.txt; .bak first)
rem    mwdialog_check.bat --sort --no-content-order  (sort without the automatic patch-after-mod rules)
rem    mwdialog_check.bat --sort --no-mlox-rules   (sort with mwdialog_check.rules.txt only)
rem
rem  Rules file (mwdialog_check.rules.txt), mlox format:
rem    [Order] a / b / c     a before b before c (wildcards * ? <VER> allowed)
rem    [Exact] a / b / c     exactly this order, nothing in between (exact names)
rem    [NearStart] / [NearEnd]   as early / as late as masters allow
rem    [Context] at the top  written by --sort: the patch-after-mod rules it found (read only)
rem
rem  Always, whatever the rules say:
rem    "mwdialog_check - ESM fixes.esp" is the first .esp; the last three are
rem    AutoMerge, then PlaceholderCell ESP Patch, then Multipatch
rem    --sort also rewrites mwdialog_load_order.txt in the new order
rem    --sort, --auto-merge and --unmerge then rebuild the patches (--fix --multipatch);
rem    add --no-follow-up to skip that
rem
rem  Before any command, mwdialog_check repairs the load order first if:
rem    an [Exact] block came apart (a plugin in it was resaved and got
rem      today's date)                          -> runs --sort --yes
rem    With --dry-run it only reports these.
rem ------------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo Python 3 was not found. Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during setup.
    pause
    exit /b 9009
)

if "%~1"=="" goto :doubleclick

title mwdialog_check %*
rem started from Explorer or a shortcut (cmd /c): mwdialog_check.py waits at the end so the
rem window stays open - but only when its output is on screen, not redirected to a file
set "MWDIALOG_PAUSE="
echo %CMDCMDLINE% | find /i "/c" >nul && set "MWDIALOG_PAUSE=1"

%PY% "%~dp0mwdialog_check.py" "%~dp0Data Files" %*
set "RC=%ERRORLEVEL%"
rem cmd puts its own title back when a batch file ends, so the result is also printed (and stays)
set "WHAT=failed"
if "%RC%"=="0" set "WHAT=done"
if "%RC%"=="1" set "WHAT=done, issues reported"
title mwdialog_check %* - finished (exit code %RC%: %WHAT%)
echo.
echo ==== mwdialog_check %* - finished: exit code %RC% (%WHAT%) ====
exit /b %RC%

:doubleclick
title mwdialog_check (scan, report to mwdialog_report.txt)
echo Scanning Data Files for dialogue errors...
%PY% "%~dp0mwdialog_check.py" "%~dp0Data Files" > "%~dp0mwdialog_report.txt"
set "RC=%ERRORLEVEL%"
title mwdialog_check (scan) - finished (exit code %RC%)
echo.
echo ==== scan finished: exit code %RC% ====
echo Report saved to mwdialog_report.txt
start "" notepad "%~dp0mwdialog_report.txt"
exit /b %RC%
