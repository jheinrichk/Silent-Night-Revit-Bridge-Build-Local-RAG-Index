@echo off
setlocal EnableExtensions
REM ============================================================
REM SILENT_NIGHT Revit Bridge - setup launcher
REM
REM Use this instead of right-clicking the .ps1 and choosing
REM "Run with PowerShell". That shell verb closes the window on
REM exit, and if the machine's execution policy is locked by
REM Group Policy it closes before the script ever loads, so you
REM see nothing at all.
REM
REM This launcher pauses no matter what happens, including a
REM PowerShell parse failure or a policy block, because cmd.exe
REM owns the window rather than powershell.exe.
REM
REM Do not pass -NoPause. This launcher already supplies it.
REM Extra arguments are forwarded, for example:
REM   Run-Setup.cmd -InstallRoot D:\RevitBridge
REM   Run-Setup.cmd -SkipPackages
REM ============================================================

cd /d "%~dp0"

set "PSEXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PSEXE%" set "PSEXE=powershell.exe"

set "PS1=%~dp0Setup-SilentNightBridge.ps1"
if not exist "%PS1%" (
  echo.
  echo ERROR: Setup-SilentNightBridge.ps1 was not found next to this launcher.
  echo Expected: %PS1%
  echo.
  pause
  exit /b 1
)

echo Launching SILENT_NIGHT setup...
echo.

"%PSEXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -NoPause %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo Setup finished.
) else (
  echo Setup exited with code %RC%.
  echo.
  echo If no setup output appeared above, PowerShell could not start the script:
  echo   - Group Policy may enforce AllSigned, which overrides -ExecutionPolicy Bypass.
  echo     Check with:  powershell -Command "Get-ExecutionPolicy -List"
  echo   - The file may still be blocked as downloaded from the internet.
  echo     Right-click Setup-SilentNightBridge.ps1, Properties, tick Unblock, Apply.
  echo   - Your IT policy may block script execution entirely. Ask for an exception
  echo     scoped to this folder, or run the steps in docs\QUICKSTART.md by hand.
)

echo.
pause
endlocal
