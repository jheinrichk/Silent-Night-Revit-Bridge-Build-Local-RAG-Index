@echo off
REM ============================================
REM SILENT_NIGHT Revit Bridge - Calibration Tool
REM ============================================

echo Launching Calibration UI...
cd /d "%~dp0\..\.."

python tools\calibration_ui.py

pause
