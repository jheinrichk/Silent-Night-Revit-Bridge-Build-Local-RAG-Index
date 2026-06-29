<#
.SYNOPSIS
    One-time setup helper for SILENT_NIGHT Revit Bridge on Windows 11.
.DESCRIPTION
    - Checks for Python
    - Installs required Python packages
    - Creates the standard C:\RevitBridge\ folder structure
    - Copies bridge_config.example.json if needed
    - Prints clear next steps (including RevitPythonShell reminder)
#>

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "SILENT_NIGHT Revit Bridge - Windows 11 Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Resolve bridge root whether this script is run from scripts\windows or the bridge root.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ((Split-Path -Leaf $scriptDir) -ieq "windows") {
    $bridgeRoot = Resolve-Path (Join-Path $scriptDir "..\..")
} else {
    $bridgeRoot = Resolve-Path $scriptDir
}
Set-Location $bridgeRoot
Write-Host "Bridge root: $bridgeRoot" -ForegroundColor Gray

# 1. Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Python not found in PATH." -ForegroundColor Red
    Write-Host "  Please install Python 3.10+ from python.org and check 'Add Python to PATH'." -ForegroundColor Yellow
    exit 1
}

# 2. Install required packages
Write-Host "`nInstalling required Python packages..." -ForegroundColor Yellow
python -m pip install pyautogui pyperclip --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ pyautogui + pyperclip installed" -ForegroundColor Green
} else {
    Write-Host "⚠ Package installation had issues. Try running as Administrator." -ForegroundColor Yellow
}

# 3. Create folder structure
$base = "C:\RevitBridge"
$folders = @(
    "$base\QC_Exports",
    "$base\QC_Upload",
    "$base\RAG\cycles",
    "$base\RAG\vector_store"
)

Write-Host "`nCreating folder structure..." -ForegroundColor Yellow
foreach ($f in $folders) {
    if (!(Test-Path $f)) {
        New-Item -ItemType Directory -Path $f -Force | Out-Null
        Write-Host "  Created: $f" -ForegroundColor Gray
    }
}
Write-Host "✓ Folder structure ready at C:\RevitBridge\" -ForegroundColor Green

# 4. Copy example config if missing
$configExample = "config\bridge_config.example.json"
$configTarget  = "bridge_config.json"

if ((Test-Path $configExample) -and !(Test-Path $configTarget)) {
    $jsonText = Get-Content $configExample -Raw
    [System.IO.File]::WriteAllText((Join-Path (Get-Location) $configTarget), $jsonText, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "✓ Copied bridge_config.example.json → bridge_config.json using UTF-8 without BOM" -ForegroundColor Green
} elseif (Test-Path $configTarget) {
    Write-Host "ℹ bridge_config.json already exists (skipped copy)" -ForegroundColor Gray
} else {
    Write-Host "⚠ Could not find config\bridge_config.example.json in current folder." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Next Steps" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host @"

1. Install / verify RevitPythonShell (RPS)
   → The bridge does NOT install RPS for you.
   → Download latest from: https://github.com/architecture-building-systems/revitpythonshell/releases
   → Install as Administrator, then restart Revit.
   → Open the "Interactive Python Shell" window before running the bridge.

2. Calibrate mouse positions (very important)
   python tools\calibration_ui.py

3. Build the local RAG knowledge base
   python RAG\rag_ingest.py

4. Run the bridge
   python src\openai_revit_bridge_main_v3_22_rag.py

For full instructions see: docs\QUICKSTART.md

"@ -ForegroundColor White

Write-Host "Setup complete. Good luck with your redlines!" -ForegroundColor Green
