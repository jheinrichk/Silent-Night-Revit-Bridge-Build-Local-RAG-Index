@echo off
setlocal
cd /d "%~dp0"
call "scripts\windows\Run-Calibration.cmd"
endlocal
