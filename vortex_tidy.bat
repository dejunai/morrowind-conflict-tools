@echo off
rem vortex_tidy.bat - tidy the mods in Vortex's Morrowind staging folder (see vortex_tidy.py)
rem   vortex_tidy.bat                   show the plan (nothing is changed; full plan in vortex_tidy_plan.txt)
rem   vortex_tidy.bat --only "MUSE*"    the plan for some mods
rem   vortex_tidy.bat --apply           do it (Purge in Vortex first, Deploy after)
rem   vortex_tidy.bat --undo            put back what the last --apply moved
title vortex_tidy %*
cd /d "%~dp0"
python "%~dp0vortex_tidy.py" %*
set RC=%ERRORLEVEL%
title vortex_tidy %* - finished (exit code %RC%)
pause
exit /b %RC%
