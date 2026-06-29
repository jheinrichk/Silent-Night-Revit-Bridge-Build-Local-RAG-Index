@echo off
setlocal EnableExtensions
REM ============================================
REM SILENT_NIGHT Revit Bridge - Quick Launcher
REM Robust launcher: keeps window open, checks paths, installs missing Python packages.
REM ============================================

set "BRIDGE_ROOT=%~dp0\..\.."
for %%I in ("%BRIDGE_ROOT%") do set "BRIDGE_ROOT=%%~fI"
cd /d "%BRIDGE_ROOT%"

if not exist "src\openai_revit_bridge_main_v3_22_rag.py" (
  echo ERROR: src\openai_revit_bridge_main_v3_22_rag.py not found.
  echo Current folder: %CD%
  echo Expected bridge root: %BRIDGE_ROOT%
  echo.
  pause
  exit /b 1
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  set "PYEXE=py -3"
) else (
  where python >nul 2>nul
  if %ERRORLEVEL%==0 (
    set "PYEXE=python"
  ) else (
    echo ERROR: Python was not found in PATH.
    echo Install Python 3.10+ and check Add Python to PATH.
    echo.
    pause
    exit /b 1
  )
)

echo Using Python command: %PYEXE%
echo Checking required Python packages...
%PYEXE% -c "import pyautogui, pyperclip" >nul 2>nul
if not %ERRORLEVEL%==0 (
  echo Installing required packages: pyautogui pyperclip
  %PYEXE% -m pip install pyautogui pyperclip
  if not %ERRORLEVEL%==0 (
    echo.
    echo ERROR: Package installation failed.
    echo Try running this command window as Administrator or install manually:
    echo   %PYEXE% -m pip install pyautogui pyperclip
    echo.
    pause
    exit /b 1
  )
)

echo.
echo Starting SILENT_NIGHT Bridge from:
echo %CD%\src\openai_revit_bridge_main_v3_22_rag.py
echo.
%PYEXE% "src\openai_revit_bridge_main_v3_22_rag.py"

echo.
echo Bridge exited with code %ERRORLEVEL%.
pause
endlocal
