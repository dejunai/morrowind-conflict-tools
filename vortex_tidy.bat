@echo off
rem vortex_tidy.bat - tidy the mods in Vortex's Morrowind staging folder (see vortex_tidy.py)
rem   vortex_tidy.bat                   show the plan (nothing is changed; full plan in plans\vortex_tidy_plan.txt)
rem   vortex_tidy.bat --only "MUSE*"    the plan for some mods
rem   vortex_tidy.bat --apply           do it (Purge in Vortex first, Deploy after)
rem   vortex_tidy.bat --undo            put back what the last --apply changed (moves, Lua, original assets)
rem   vortex_tidy.bat --no-coins        (with the others) broken models get an empty, invisible model, not the coin
title vortex_tidy %*
set "GAME=%~dp0"
if exist "%~dp0..\Morrowind.ini" for %%I in ("%~dp0..") do set "GAME=%%~fI\"
cd /d "%GAME%"
python "%~dp0vortex_tidy.py" %*
set RC=%ERRORLEVEL%
title vortex_tidy %* - finished (exit code %RC%)
pause
exit /b %RC%
