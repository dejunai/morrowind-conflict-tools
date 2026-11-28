@echo off
rem vortex_tidy.bat - tidy the mods in Vortex's Morrowind staging folder (see vortex_tidy.py)
rem   vortex_tidy.bat                   show the plan (nothing is changed; full plan in plans\vortex_tidy_plan.txt)
rem   vortex_tidy.bat --only "MUSE*"    the plan for some mods
rem   vortex_tidy.bat --apply           do it (Deploy in Vortex after; Purge first is good practice)
rem   vortex_tidy.bat --undo            put back what the last --apply changed (moves, Lua, original assets)
rem   vortex_tidy.bat --no-coins        (with the others) broken models get an empty, invisible model, not the coin
setlocal
title vortex_tidy %*
set "GAME=%~dp0"
if exist "%~dp0..\Morrowind.exe" for %%I in ("%~dp0..") do set "GAME=%%~fI\"
if exist "%~dp0..\Morrowind.ini" for %%I in ("%~dp0..") do set "GAME=%%~fI\"
cd /d "%GAME%"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo Python 3 was not found. Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during setup.
    pause
    exit /b 9009
)

set "PAUSE_AT_END="
echo %CMDCMDLINE% | find /i "/c" >nul && set "PAUSE_AT_END=1"

%PY% "%~dp0vortex_tidy.py" %*
set "RC=%ERRORLEVEL%"
title vortex_tidy %* - finished (exit code %RC%)
if defined PAUSE_AT_END pause
exit /b %RC%
