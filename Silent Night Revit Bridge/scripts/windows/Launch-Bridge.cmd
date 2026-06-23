@echo off
REM ============================================
REM SILENT_NIGHT Revit Bridge - Quick Launcher
REM ============================================

echo Starting SILENT_NIGHT Bridge...
cd /d "%~dp0\..\.."

python src\openai_revit_bridge_main_v3_22_rag.py

pause
