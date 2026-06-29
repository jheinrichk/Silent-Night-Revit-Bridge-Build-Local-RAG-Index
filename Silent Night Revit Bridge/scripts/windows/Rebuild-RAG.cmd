@echo off
setlocal EnableExtensions
REM ============================================
REM SILENT_NIGHT Revit Bridge - Rebuild RAG Index
REM Robust launcher: keeps window open, checks paths.
REM ============================================

set "BRIDGE_ROOT=%~dp0\..\.."
for %%I in ("%BRIDGE_ROOT%") do set "BRIDGE_ROOT=%%~fI"
cd /d "%BRIDGE_ROOT%"

if not exist "RAG\rag_ingest.py" (
  echo ERROR: RAG\rag_ingest.py not found.
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

echo Rebuilding local RAG knowledge base from:
echo %CD%\RAG\rag_ingest.py
echo.
%PYEXE% "RAG\rag_ingest.py"

echo.
echo Rebuild RAG exited with code %ERRORLEVEL%.
pause
endlocal
