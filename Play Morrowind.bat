@echo off
rem Play Morrowind.bat - start Morrowind directly, skipping the Morrowind Launcher (MGE XE and MWSE still load).
rem Runs mwdialog_check with --play: checks every active plugin's masters, writes the load order into
rem Morrowind.ini, brings the lua tools up to date in Data Files, then starts Morrowind.exe.
rem Works from the conflict-tools folder or from the Morrowind folder (next to conflict-tools\).
rem Add steps before --play if you want them every time, e.g.:  call ... --sort --yes --play
setlocal
set "MWCHECK=%~dp0mwdialog_check.bat"
if not exist "%MWCHECK%" set "MWCHECK=%~dp0conflict-tools\mwdialog_check.bat"
call "%MWCHECK%" --play
if errorlevel 1 pause
