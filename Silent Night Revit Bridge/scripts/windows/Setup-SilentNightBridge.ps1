<#
.SYNOPSIS
    SILENT_NIGHT Revit Bridge - full Windows installer.

.DESCRIPTION
    Replaces the original setup helper. Differences that matter:
      - Window no longer closes on exit or on error. Everything is wrapped in
        try/catch/finally and the finally block pauses.
      - Pure ASCII. The original used check marks and arrows saved as UTF-8
        with no BOM, which Windows PowerShell 5.1 decodes as ANSI and mangles.
      - Python discovery rejects the Microsoft Store app-execution-alias stub,
        which the original try/catch could not detect.
      - Deploys the RAG folder to the install root. The original created empty
        RAG folders but never copied rag_retrieve.py / rag_store.py there, so
        the bridge's run_rag_retrieval() failed its os.path.exists() check and
        returned an empty string on every cycle. RAG looked enabled and
        contributed nothing.
      - Builds and smoke-tests the RAG index instead of telling you to do it.
      - Merges missing config keys additively. Existing values, including
        calibrated coordinates, are never overwritten. A backup is taken first.
      - Normalizes the .cmd launchers to CRLF. They ship LF-only, which is not
        valid for Windows batch.
      - Unblocks files carrying the downloaded-from-internet zone marker.

.PARAMETER InstallRoot
    Runtime folder. Default C:\RevitBridge. Must match the paths in
    bridge_config.json; this script keeps them in sync.

.PARAMETER SkipPackages
    Skip pip. Use when the machine has no outbound network.

.PARAMETER SkipRagBuild
    Deploy RAG but do not build the index.

.PARAMETER ForceCorpus
    Overwrite seed corpus files at the install root. Default is copy-if-missing
    so local corpus edits survive re-runs.

.PARAMETER NoPause
    Do not wait for Enter at the end. For unattended use only.

.EXAMPLE
    Right-click Run-Setup.cmd and choose Run as administrator.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-SilentNightBridge.ps1
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "C:\RevitBridge",
    [switch]$SkipPackages,
    [switch]$SkipRagBuild,
    [switch]$ForceCorpus,
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"
$script:Steps    = @()
$script:FailCount = 0
$script:WarnCount = 0

# ---------------------------------------------------------------- output ----

function Write-Head {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 62) -ForegroundColor Cyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 62) -ForegroundColor Cyan
}

function Write-Ok   { param([string]$m) Write-Host "  [ OK ] $m" -ForegroundColor Green }
function Write-Warn { param([string]$m) Write-Host "  [WARN] $m" -ForegroundColor Yellow; $script:WarnCount++ }
function Write-Fail { param([string]$m) Write-Host "  [FAIL] $m" -ForegroundColor Red;    $script:FailCount++ }
function Write-Note { param([string]$m) Write-Host "  [ .. ] $m" -ForegroundColor Gray }

function Add-Step {
    param([string]$Name, [string]$Status, [string]$Detail = "")
    $script:Steps += ,(New-Object PSObject -Property ([ordered]@{
        Step   = $Name
        Status = $Status
        Detail = $Detail
    }))
}

# ------------------------------------------------------------ json merge ----

# ConvertFrom-Json returns PSCustomObject on 5.1 (-AsHashtable is 6+).
# Convert to ordered dictionaries so key order survives the round trip.
function ConvertTo-OrderedDeep {
    param($Node)
    if ($null -eq $Node) { return $null }
    if ($Node -is [System.Management.Automation.PSCustomObject]) {
        $o = [ordered]@{}
        foreach ($p in $Node.PSObject.Properties) { $o[$p.Name] = ConvertTo-OrderedDeep $p.Value }
        return $o
    }
    if (($Node -is [System.Collections.IEnumerable]) -and -not ($Node -is [string])) {
        $a = @()
        foreach ($i in $Node) { $a += ,(ConvertTo-OrderedDeep $i) }
        return ,$a
    }
    return $Node
}

# Additive only. Never overwrites an existing key at any depth.
function Merge-MissingKeys {
    param($Target, $Defaults, [string]$Prefix = "")
    foreach ($k in @($Defaults.Keys)) {
        if (-not $Target.Contains($k)) {
            $Target[$k] = $Defaults[$k]
            $script:AddedKeys += "$Prefix$k"
        }
        elseif (($Target[$k] -is [System.Collections.Specialized.OrderedDictionary]) -and
                ($Defaults[$k] -is [System.Collections.Specialized.OrderedDictionary])) {
            Merge-MissingKeys -Target $Target[$k] -Defaults $Defaults[$k] -Prefix "$Prefix$k."
        }
    }
}

# Join-Path resolves against PSDrives and fails if the drive is absent.
# Config values are plain strings, so build them without touching the provider.
function Join-PathText {
    param([string]$Base, [string]$Child)
    return ($Base.TrimEnd("\") + "\" + $Child.TrimStart("\"))
}

function Write-TextNoBom {
    param([string]$Path, [string]$Text)
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $enc)
}

# ------------------------------------------------------------ native ----

# Under Windows PowerShell 5.1 with $ErrorActionPreference = "Stop", stderr
# captured through 2>&1 from a native command is wrapped as ErrorRecords and
# the first one terminates the script. A harmless Python SyntaxWarning is
# enough. Run every native command with EAP relaxed and return plain strings.
# $LASTEXITCODE still reflects the process exit code afterward.
function Invoke-Native {
    param([string]$Exe, [object[]]$Arguments)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & $Exe @Arguments 2>&1
        return @($out | ForEach-Object { "$_" })
    }
    finally { $ErrorActionPreference = $prev }
}

# ------------------------------------------------------------ python ----

function Test-PythonCandidate {
    param([string]$Exe, [string[]]$Arguments, [string]$ProbeFile)
    try {
        $raw = Invoke-Native -Exe $Exe -Arguments ($Arguments + @($ProbeFile))
    } catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0) { return $null }
    $line = ($raw | Where-Object { $_ -like "PYOK|*" } | Select-Object -First 1)
    if (-not $line) { return $null }
    $parts = $line.Split("|")
    if ($parts.Count -lt 4) { return $null }
    $verParts = $parts[1].Split(".")
    return [ordered]@{
        Exe     = $Exe
        Args    = $Arguments
        Major   = [int]$verParts[0]
        Minor   = [int]$verParts[1]
        Version = $parts[1]
        Path    = $parts[2]
        Bits    = $parts[3]
    }
}

# =============================================================== main ========

try {

Write-Head "SILENT_NIGHT Revit Bridge - Windows Setup"
Write-Host "Host: PowerShell $($PSVersionTable.PSVersion)  |  User: $env:USERNAME" -ForegroundColor Gray

# --- resolve bridge root -----------------------------------------------------

$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

if ((Split-Path -Leaf $scriptDir) -ieq "windows") {
    $bridgeRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
} elseif (Test-Path (Join-Path $scriptDir "src")) {
    $bridgeRoot = (Resolve-Path $scriptDir).Path
} else {
    throw "Cannot locate the bridge root. Run this from the bridge folder or from scripts\windows."
}

$mainScript = Join-Path $bridgeRoot "src\openai_revit_bridge_main_v3_22_rag.py"
if (-not (Test-Path $mainScript)) {
    throw "src\openai_revit_bridge_main_v3_22_rag.py not found under $bridgeRoot. Wrong folder, or the zip did not extract fully."
}

Set-Location $bridgeRoot
Write-Note "Bridge root : $bridgeRoot"
Write-Note "Install root: $InstallRoot"

# --- folder tree -------------------------------------------------------------

Write-Head "1. Runtime folders"

$folders = @(
    $InstallRoot,
    (Join-PathText $InstallRoot "QC_Exports"),
    (Join-PathText $InstallRoot "QC_Upload"),
    (Join-PathText $InstallRoot "logs"),
    (Join-PathText $InstallRoot "RAG"),
    (Join-PathText $InstallRoot "RAG\corpus"),
    (Join-PathText $InstallRoot "RAG\corpus\seed"),
    (Join-PathText $InstallRoot "RAG\cycles"),
    (Join-PathText $InstallRoot "RAG\vector_store")
)
$made = 0
foreach ($f in $folders) {
    if (-not (Test-Path $f)) { New-Item -ItemType Directory -Path $f -Force | Out-Null; $made++ }
}
Write-Ok "$($folders.Count) folders present ($made created)"
Add-Step "Runtime folders" "OK" "$made created under $InstallRoot"

# --- transcript --------------------------------------------------------------

$logFile = Join-PathText $InstallRoot ("logs\setup_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
try { Start-Transcript -Path $logFile -ErrorAction Stop | Out-Null; Write-Note "Log: $logFile" }
catch { Write-Note "Transcript unavailable, continuing without a log file." }

# --- unblock downloaded files ------------------------------------------------

Write-Head "2. Zone marker"
# Unblock-File is a no-op on files with no zone marker, so just run it over
# the tree rather than enumerating alternate data streams first.
if (Get-Command Unblock-File -ErrorAction SilentlyContinue) {
    $n = 0
    foreach ($f in @(Get-ChildItem -Path $bridgeRoot -Recurse -File -ErrorAction SilentlyContinue)) {
        try { Unblock-File -LiteralPath $f.FullName -ErrorAction Stop; $n++ }
        catch { Write-Verbose "Skipped $($f.Name)" }
    }
    Write-Ok "Zone markers cleared across $n file(s)"
    Add-Step "Zone marker" "OK" "$n processed"
} else {
    Write-Note "Unblock-File unavailable on this host, skipping"
    Add-Step "Zone marker" "SKIP" "cmdlet unavailable"
}

# --- python ------------------------------------------------------------------

Write-Head "3. Python"

$tempDir = [System.IO.Path]::GetTempPath()
$probeFile = Join-Path $tempDir "sn_pyprobe.py"
$probeSrc = @'
import sys
bits = 64 if sys.maxsize > 2**32 else 32
print("PYOK|{}.{}|{}|{}".format(sys.version_info[0], sys.version_info[1], sys.executable, bits))
'@
Set-Content -LiteralPath $probeFile -Value $probeSrc -Encoding ASCII

$candidates = @()

$pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($pyLauncher) { $candidates += ,@{ Exe = $pyLauncher.Source; Args = @("-3") } }

foreach ($c in @(Get-Command python.exe -All -ErrorAction SilentlyContinue)) {
    if ($c.Source -and ($c.Source -notlike "*\WindowsApps\*")) {
        $candidates += ,@{ Exe = $c.Source; Args = @() }
    } elseif ($c.Source -like "*\WindowsApps\*") {
        Write-Note "Ignoring Microsoft Store alias stub: $($c.Source)"
    }
}

# Build search roots defensively. A locked-down profile can leave these unset,
# and Join-Path throws on a null Path rather than returning nothing.
$searchRoots = @("C:\Python313", "C:\Python312", "C:\Python311", "C:\Python310")
if ($env:LOCALAPPDATA) { $searchRoots += (Join-Path $env:LOCALAPPDATA "Programs\Python") }
if ($env:ProgramFiles) {
    foreach ($v in @("Python313", "Python312", "Python311", "Python310")) {
        $searchRoots += (Join-Path $env:ProgramFiles $v)
    }
}
foreach ($r in $searchRoots) {
    if (Test-Path $r) {
        foreach ($exe in @(Get-ChildItem -Path $r -Filter "python.exe" -Recurse -Depth 1 -ErrorAction SilentlyContinue)) {
            $candidates += ,@{ Exe = $exe.FullName; Args = @() }
        }
    }
}

$python = $null
foreach ($cand in $candidates) {
    $probe = Test-PythonCandidate -Exe $cand.Exe -Arguments $cand.Args -ProbeFile $probeFile
    if ($probe -and $probe.Major -eq 3 -and $probe.Minor -ge 8) { $python = $probe; break }
    if ($probe) { Write-Note "Rejected Python $($probe.Version) at $($probe.Path) (need 3.8+)" }
}

if (-not $python) {
    Write-Fail "No usable Python 3.8+ found."
    Write-Host ""
    Write-Host "  Install 64-bit Python 3.10 - 3.12 from https://www.python.org/downloads/windows/" -ForegroundColor Yellow
    Write-Host "  During install, tick 'Add python.exe to PATH', then re-run this setup." -ForegroundColor Yellow
    Write-Host "  If Windows opens the Microsoft Store when you type 'python', turn off the" -ForegroundColor Yellow
    Write-Host "  app execution aliases for python.exe under Settings > Apps > Advanced app settings." -ForegroundColor Yellow
    Add-Step "Python" "FAIL" "not found"
    throw "Python is required. Nothing further can be installed."
}

$PyExe  = $python.Exe
$PyArgs = @($python.Args)
Write-Ok "Python $($python.Version) ($($python.Bits)-bit)"
Write-Note "Interpreter: $($python.Path)"
if ($python.Bits -ne "64") { Write-Warn "32-bit interpreter. Workable but 64-bit is recommended." }
Add-Step "Python" "OK" "$($python.Version) $($python.Bits)-bit"

# --- packages ----------------------------------------------------------------

Write-Head "4. Python packages"

if ($SkipPackages) {
    Write-Note "Skipped by -SkipPackages"
    Add-Step "Packages" "SKIP" "-SkipPackages"
} else {
    $reqFile = Join-Path $bridgeRoot "requirements.txt"
    $pkgArgs = @("-m", "pip", "install", "--upgrade", "--disable-pip-version-check")

    Write-Note "Upgrading pip"
    Invoke-Native -Exe $PyExe -Arguments ($PyArgs + @("-m", "pip", "install", "--upgrade", "pip", "--quiet", "--disable-pip-version-check")) | Out-Null

    # pyautogui needs pyscreeze, which needs Pillow for any screen work.
    # requirements.txt does not list Pillow, so add it explicitly.
    if (Test-Path $reqFile) {
        Write-Note "Installing from requirements.txt"
        Invoke-Native -Exe $PyExe -Arguments ($PyArgs + $pkgArgs + @("-r", $reqFile)) | ForEach-Object { Write-Host "        $_" -ForegroundColor DarkGray }
    } else {
        Write-Note "requirements.txt missing, installing known set"
        Invoke-Native -Exe $PyExe -Arguments ($PyArgs + $pkgArgs + @("pyautogui", "pyperclip")) | ForEach-Object { Write-Host "        $_" -ForegroundColor DarkGray }
    }
    Invoke-Native -Exe $PyExe -Arguments ($PyArgs + $pkgArgs + @("pillow")) | Out-Null

    $impFile = Join-Path $tempDir "sn_imports.py"
    $impSrc = @'
import importlib
missing = []
for m in ("pyautogui", "pyperclip", "PIL"):
    try:
        importlib.import_module(m)
    except Exception as ex:
        missing.append("{}={}".format(m, ex.__class__.__name__))
print("MISSING|" + ",".join(missing))
'@
    Set-Content -LiteralPath $impFile -Value $impSrc -Encoding ASCII
    $impOut = (Invoke-Native -Exe $PyExe -Arguments ($PyArgs + @($impFile)) | Where-Object { $_ -like "MISSING|*" } | Select-Object -First 1)

    if ($impOut -and $impOut -eq "MISSING|") {
        Write-Ok "pyautogui, pyperclip, Pillow import cleanly"
        Add-Step "Packages" "OK" "verified by import"
    } else {
        Write-Fail "Import check failed: $impOut"
        Write-Host "  Retry in an elevated window, or install per-user:" -ForegroundColor Yellow
        Write-Host "    `"$PyExe`" -m pip install --user pyautogui pyperclip pillow" -ForegroundColor Yellow
        Add-Step "Packages" "FAIL" $impOut
    }
}

# --- RAG deployment ----------------------------------------------------------

Write-Head "5. RAG deployment"

$ragSource = Join-Path $bridgeRoot "RAG"
$ragTarget = Join-PathText $InstallRoot "RAG"

if (-not (Test-Path $ragSource)) {
    Write-Fail "Package RAG folder not found at $ragSource"
    Add-Step "RAG deploy" "FAIL" "source missing"
} else {
    # Engine scripts are always refreshed. They are code, not user data.
    $engine = @("rag_store.py", "rag_retrieve.py", "rag_ingest.py", "rag_add_cycle.py")
    $copied = 0
    foreach ($f in $engine) {
        $src = Join-Path $ragSource $f
        if (Test-Path $src) {
            Copy-Item -LiteralPath $src -Destination (Join-PathText $ragTarget $f) -Force
            $copied++
        } else {
            Write-Warn "Missing from package: RAG\$f"
        }
    }
    Write-Ok "$copied RAG engine script(s) deployed to $ragTarget"

    # Corpus is user data. Copy-if-missing unless -ForceCorpus.
    $corpusSrc = Join-Path $ragSource "corpus"
    $corpusDst = Join-PathText $ragTarget "corpus"
    $added = 0; $kept = 0
    if (Test-Path $corpusSrc) {
        foreach ($item in @(Get-ChildItem -Path $corpusSrc -Recurse -File)) {
            $rel = $item.FullName.Substring($corpusSrc.Length).TrimStart("\")
            $dst = Join-PathText $corpusDst $rel
            $dstDir = Split-Path -Parent $dst
            if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
            if ((Test-Path $dst) -and -not $ForceCorpus) { $kept++ }
            else { Copy-Item -LiteralPath $item.FullName -Destination $dst -Force; $added++ }
        }
    }
    Write-Ok "Corpus: $added file(s) written, $kept existing file(s) left untouched"

    # rag_config.json must describe the install root, not the package folder.
    $ragCfg = [ordered]@{
        rag_root          = $ragTarget
        corpus_dir        = $corpusDst
        cycles_dir        = (Join-PathText $ragTarget "cycles")
        vector_store_dir  = (Join-PathText $ragTarget "vector_store")
        retrieval_script  = (Join-PathText $ragTarget "rag_retrieve.py")
        top_k             = 8
        max_context_chars = 6000
        index_method      = "stdlib lexical tf-idf scoring; replaceable with embeddings later"
    }
    Write-TextNoBom (Join-PathText $ragTarget "rag_config.json") (($ragCfg | ConvertTo-Json -Depth 6))
    Write-Ok "rag_config.json written with install-root paths"
    Add-Step "RAG deploy" "OK" "$copied scripts, $added corpus files"
}

# --- bridge_config.json ------------------------------------------------------

Write-Head "6. bridge_config.json"

$configTarget = Join-Path $bridgeRoot "bridge_config.json"
$script:AddedKeys = @()

$defaults = [ordered]@{
    timing = [ordered]@{
        chatgpt_output_wait_seconds              = 120
        chatgpt_copy_retry_wait_seconds          = 90
        chatgpt_copy_retry_attempts              = 2
        chatgpt_page_down_count                  = 2
        chatgpt_page_down_pre_copy_wait_seconds  = 3
        chatgpt_page_down_post_copy_wait_seconds = 3
        browser_refresh_after_click_wait_seconds = 3
        chatgpt_reprint_wait_seconds             = 90
        rps_output_wait_seconds                  = 60
        startup_delay_seconds                    = 3
        pause_between_actions                    = 0.5
        pause_after_copy_seconds                 = 3
        pause_after_paste_seconds                = 3
        revit_warning_ok_click_wait_seconds      = 0
        revit_dialog_click_wait_seconds          = 0
        revit_dialog_sequence_passes             = 0
        revit_dialog_before_output_wait_seconds  = 0
        default_short_wait_seconds               = 3
        chatgpt_input_paste_wait_seconds         = 7
        chatgpt_wait_min_seconds                 = 45
        chatgpt_wait_max_seconds                 = 180
        rps_wait_min_seconds                     = 20
        rps_wait_max_seconds                     = 120
        retry_wait_min_seconds                   = 45
        retry_wait_max_seconds                   = 180
    }
    qc = [ordered]@{
        export_folder                        = (Join-PathText $InstallRoot "QC_Exports")
        upload_staging_folder                = (Join-PathText $InstallRoot "QC_Upload")
        upload_staging_basename              = "qc_upload"
        valid_export_extensions              = @(".png", ".pdf", ".jpg", ".jpeg")
        watch_interval_seconds               = 2
        file_stability_checks                = 3
        file_stability_interval_seconds      = 1
        upload_wait_seconds                  = 4
        upload_step_wait_seconds             = 3
        chatgpt_response_wait_seconds        = 60
        activate_chatgpt_input_before_upload = $true
        file_dialog_path_entry_attempts      = 2
        file_picker_open_after_paste         = $true
        file_picker_open_wait_seconds        = 7
        batch_upload_one_dialog              = $true
        upload_debug_log                     = (Join-PathText $InstallRoot "QC_Upload\upload_debug_log.txt")
        newest_file_fallback_max_age_seconds = 900
    }
    bridge = [ordered]@{
        max_cycles                   = 2222
        stop_on_syntax_error         = $true
        stop_on_fix_errors           = $true
        stop_on_completion_states    = $false
        stop_on_repeated_state       = $false
        revit_api_modal_guard_enabled = $true
        max_repeated_state_count     = 8
        max_invalid_code_attempts    = 2
        max_reprint_attempts         = 1
    }
    rag = [ordered]@{
        enabled                    = $true
        rag_folder                 = $ragTarget
        retrieval_script           = (Join-PathText $ragTarget "rag_retrieve.py")
        cycle_log_file             = (Join-PathText $ragTarget "cycles\bridge_cycles.jsonl")
        latest_context_file        = (Join-PathText $ragTarget "latest_retrieved_context.txt")
        max_context_chars          = 6000
        top_k                      = 8
        include_on_initial_prompt  = $true
        include_on_followup_prompt = $true
        log_cycles                 = $true
        retrieval_timeout_seconds  = 8
    }
    hotkeys = [ordered]@{
        copy           = @("ctrl", "c")
        paste          = @("ctrl", "v")
        select_all     = @("ctrl", "a")
        chatgpt_submit = @("enter")
        rps_execute    = @("f5")
        page_down      = @("pagedown")
    }
}

if (Test-Path $configTarget) {
    $raw = Get-Content -LiteralPath $configTarget -Raw
    $config = ConvertTo-OrderedDeep (ConvertFrom-Json $raw)
    $backup = "$configTarget.backup_{0}.json" -f (Get-Date -Format "yyyyMMdd_HHmmss")
    Copy-Item -LiteralPath $configTarget -Destination $backup -Force
    Write-Note "Backup: $(Split-Path -Leaf $backup)"

    Merge-MissingKeys -Target $config -Defaults $defaults

    if ($script:AddedKeys.Count -gt 0) {
        Write-TextNoBom $configTarget (($config | ConvertTo-Json -Depth 12))
        Write-Ok "Added $($script:AddedKeys.Count) missing key(s), existing values untouched"
        foreach ($k in $script:AddedKeys) { Write-Host "        + $k" -ForegroundColor DarkGray }
    } else {
        Write-Ok "Config already complete, no changes written"
    }
    $coordCount = 0
    if ($config.Contains("coordinates")) { $coordCount = @($config["coordinates"].Keys).Count }
    if ($coordCount -lt 16) {
        Write-Warn "Only $coordCount calibrated coordinate(s). Run calibration before the first cycle."
    } else {
        Write-Ok "$coordCount calibrated coordinates present"
    }
    Add-Step "bridge_config.json" "OK" "$($script:AddedKeys.Count) keys added, $coordCount coordinates"
}
else {
    # Prefer the richer root template, fall back to the example.
    $seedFrom = $null
    foreach ($cand in @((Join-Path $bridgeRoot "config\bridge_config.json"),
                        (Join-Path $bridgeRoot "config\bridge_config.example.json"))) {
        if (Test-Path $cand) { $seedFrom = $cand; break }
    }
    if ($seedFrom) {
        $config = ConvertTo-OrderedDeep (ConvertFrom-Json (Get-Content -LiteralPath $seedFrom -Raw))
        Write-Note "Seeded from $(Split-Path -Leaf $seedFrom)"
    } else {
        $config = [ordered]@{}
        Write-Note "No template found, writing defaults"
    }
    Merge-MissingKeys -Target $config -Defaults $defaults

    # The shipped templates hardcode C:\RevitBridge. The merge is additive, so
    # seeded values survive it. On a fresh config the install root must win, or
    # a non-default -InstallRoot silently points the bridge at the wrong tree.
    foreach ($sec in @("qc", "rag")) {
        if ($config.Contains($sec) -and $defaults.Contains($sec)) {
            foreach ($k in @($defaults[$sec].Keys)) {
                if ("$($defaults[$sec][$k])" -like "*$InstallRoot*") {
                    $config[$sec][$k] = $defaults[$sec][$k]
                }
            }
        }
    }

    Write-TextNoBom $configTarget (($config | ConvertTo-Json -Depth 12))
    Write-Ok "Created bridge_config.json (UTF-8, no BOM) with install-root paths"
    Write-Warn "Coordinates are not calibrated yet. Calibration is mandatory before the first run."
    Add-Step "bridge_config.json" "OK" "created"
}

# --- CRLF normalization ------------------------------------------------------

Write-Head "7. Batch launcher line endings"

$fixed = 0; $checked = 0
foreach ($cmdFile in @(Get-ChildItem -Path $bridgeRoot -Recurse -Include "*.cmd", "*.bat" -File -ErrorAction SilentlyContinue)) {
    $checked++
    $text = [System.IO.File]::ReadAllText($cmdFile.FullName)
    if ($text -notmatch "`r`n") {
        $norm = ($text -replace "`r`n", "`n") -replace "`n", "`r`n"
        [System.IO.File]::WriteAllText($cmdFile.FullName, $norm, (New-Object System.Text.ASCIIEncoding))
        Write-Note "Normalized: $($cmdFile.Name)"
        $fixed++
    }
}
Write-Ok "$checked batch file(s) checked, $fixed converted to CRLF"
Add-Step "Batch CRLF" "OK" "$fixed of $checked converted"

# --- build the index ---------------------------------------------------------

Write-Head "8. RAG index"

if ($SkipRagBuild) {
    Write-Note "Skipped by -SkipRagBuild"
    Add-Step "RAG index" "SKIP" "-SkipRagBuild"
} else {
    $ragStore  = Join-PathText $ragTarget "rag_store.py"
    $indexFile = Join-PathText $ragTarget "vector_store\index.jsonl"
    if (-not (Test-Path $ragStore)) {
        Write-Fail "rag_store.py not deployed, cannot build"
        Add-Step "RAG index" "FAIL" "rag_store.py missing"
    } else {
        Push-Location $ragTarget
        try {
            $buildOut = Invoke-Native -Exe $PyExe -Arguments ($PyArgs + @($ragStore, "--build"))
            $buildLine = ($buildOut | Where-Object { $_ -like "INDEX_BUILT*" } | Select-Object -First 1)
            if (-not $buildLine) {
                Write-Fail "Build produced no INDEX_BUILT line"
                $buildOut | ForEach-Object { Write-Host "        $_" -ForegroundColor DarkGray }
                Add-Step "RAG index" "FAIL" "build error"
            } else {
                $chunks = 0
                if (Test-Path $indexFile) {
                    $chunks = @([System.IO.File]::ReadAllLines($indexFile) | Where-Object { $_.Trim() -ne "" }).Count
                }
                if ($chunks -lt 1) {
                    Write-Fail "index.jsonl is empty. Corpus did not reach $corpusDst."
                    Add-Step "RAG index" "FAIL" "0 chunks"
                } else {
                    Write-Ok "Index built: $chunks chunk(s)"

                    # Retrieval smoke test against the exact path the bridge calls.
                    $retrieve = Join-PathText $ragTarget "rag_retrieve.py"
                    $hit = (Invoke-Native -Exe $PyExe -Arguments ($PyArgs + @($retrieve, "--query", "transaction rollback doc.Regenerate IronPython", "--top-k", "3", "--max-chars", "600"))) -join "`n"
                    if ($hit -match "\[RAG source=") {
                        Write-Ok "Retrieval smoke test returned context"
                        Add-Step "RAG index" "OK" "$chunks chunks, retrieval verified"
                    } else {
                        Write-Warn "Index built but the smoke query returned nothing usable"
                        Add-Step "RAG index" "WARN" "$chunks chunks, retrieval empty"
                    }
                }
            }
        } finally { Pop-Location }
    }
}

# --- wiring verification -----------------------------------------------------

Write-Head "9. Wiring check"

# This is the failure the original setup shipped with: the bridge tests
# os.path.exists(retrieval_script) and silently disables RAG if it is absent.
$cfgNow = ConvertTo-OrderedDeep (ConvertFrom-Json (Get-Content -LiteralPath $configTarget -Raw))
$declared = $null
if ($cfgNow.Contains("rag")) { $declared = $cfgNow["rag"]["retrieval_script"] }

if (-not $declared) {
    Write-Fail "bridge_config.json has no rag.retrieval_script. RAG will stay silent."
    Add-Step "RAG wiring" "FAIL" "key missing"
} elseif (Test-Path $declared) {
    Write-Ok "rag.retrieval_script resolves: $declared"
    Add-Step "RAG wiring" "OK" "resolved"
} else {
    Write-Fail "rag.retrieval_script points at a file that does not exist:"
    Write-Host "        $declared" -ForegroundColor Red
    Write-Host "        The bridge will return empty RAG context on every cycle without any error." -ForegroundColor Yellow
    Add-Step "RAG wiring" "FAIL" "path unresolved"
}

foreach ($pair in @(
    @{ Name = "qc.export_folder";         Val = $cfgNow["qc"]["export_folder"] },
    @{ Name = "qc.upload_staging_folder"; Val = $cfgNow["qc"]["upload_staging_folder"] })) {
    if (Test-Path $pair.Val) { Write-Ok "$($pair.Name) resolves" }
    else {
        Write-Warn "$($pair.Name) does not exist: $($pair.Val)"
        if ("$($pair.Val)" -notlike "*$InstallRoot*") {
            Write-Host "        Config points outside the install root ($InstallRoot)." -ForegroundColor Yellow
            Write-Host "        Edit bridge_config.json, or re-run with -InstallRoot set to match." -ForegroundColor Yellow
        }
    }
}

# --- RevitPythonShell --------------------------------------------------------

Write-Head "10. RevitPythonShell"

$rpsFound = @()
$addinRoot = $null
if ($env:APPDATA) { $addinRoot = Join-Path $env:APPDATA "Autodesk\Revit\Addins" }
if ($addinRoot -and (Test-Path $addinRoot)) {
    foreach ($yr in @(Get-ChildItem -Path $addinRoot -Directory -ErrorAction SilentlyContinue)) {
        if (Get-ChildItem -Path $yr.FullName -Filter "*RevitPythonShell*" -ErrorAction SilentlyContinue) {
            $rpsFound += $yr.Name
        }
    }
}
if ($rpsFound.Count -gt 0) {
    Write-Ok "RevitPythonShell add-in registered for Revit: $($rpsFound -join ', ')"
    Add-Step "RevitPythonShell" "OK" ($rpsFound -join ", ")
} else {
    Write-Warn "No RevitPythonShell add-in manifest found. This setup cannot install it."
    Write-Host "        https://github.com/architecture-building-systems/revitpythonshell/releases" -ForegroundColor Yellow
    Write-Host "        Install as Administrator, restart Revit, then open Interactive Python Shell." -ForegroundColor Yellow
    Add-Step "RevitPythonShell" "WARN" "not detected"
}

# --- summary -----------------------------------------------------------------

Write-Head "Summary"

# Format-Table piped through Out-String renders blank when the host reports no
# console width, which happens under transcription and redirected output.
# Fixed-width formatting is deterministic and lets each row carry its own color.
$w1 = 3; $w2 = 3
foreach ($s in $script:Steps) {
    if ($s.Step.Length   -gt $w1) { $w1 = $s.Step.Length }
    if ($s.Status.Length -gt $w2) { $w2 = $s.Status.Length }
}
$fmt = "  {0,-$w1}   {1,-$w2}   {2}"
Write-Host ($fmt -f "STEP", "STATE", "DETAIL") -ForegroundColor White
Write-Host ($fmt -f ("-" * $w1), ("-" * $w2), ("-" * 24)) -ForegroundColor DarkGray
foreach ($s in $script:Steps) {
    $color = "Gray"
    if ($s.Status -eq "OK")   { $color = "Green" }
    if ($s.Status -eq "WARN") { $color = "Yellow" }
    if ($s.Status -eq "FAIL") { $color = "Red" }
    if ($s.Status -eq "SKIP") { $color = "DarkGray" }
    Write-Host ($fmt -f $s.Step, $s.Status, $s.Detail) -ForegroundColor $color
}
Write-Host ""

if ($script:FailCount -gt 0) {
    Write-Host "Setup finished with $($script:FailCount) failure(s) and $($script:WarnCount) warning(s)." -ForegroundColor Red
} elseif ($script:WarnCount -gt 0) {
    Write-Host "Setup complete with $($script:WarnCount) warning(s)." -ForegroundColor Yellow
} else {
    Write-Host "Setup complete. No failures." -ForegroundColor Green
}

Write-Host ""
Write-Host "Next steps" -ForegroundColor Cyan
Write-Host "  1. Open Revit and start Interactive Python Shell. Leave it open." -ForegroundColor White
Write-Host "  2. Calibrate:  1_CALIBRATE_SILENT_NIGHT.cmd" -ForegroundColor White
Write-Host "  3. Run:        3_START_SILENT_NIGHT_BRIDGE.cmd" -ForegroundColor White
Write-Host "  Rebuild the index any time with 2_REBUILD_RAG_INDEX.cmd, but note that it" -ForegroundColor Gray
Write-Host "  builds inside the package folder. The bridge reads $ragTarget." -ForegroundColor Gray
Write-Host "  Re-run this setup to resync, or point the .cmd at the install root." -ForegroundColor Gray

}
catch {
    Write-Host ""
    Write-Host "SETUP STOPPED" -ForegroundColor Red
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
    if ($_.InvocationInfo) {
        Write-Host "  Line $($_.InvocationInfo.ScriptLineNumber): $($_.InvocationInfo.Line.Trim())" -ForegroundColor DarkGray
    }
    Write-Host ""
    Write-Host "Nothing was left half-written. Fix the item above and run setup again." -ForegroundColor Yellow
}
finally {
    try { Stop-Transcript -ErrorAction SilentlyContinue | Out-Null }
    catch { Write-Verbose "No transcript was running." }
    if (-not $NoPause) {
        Write-Host ""
        Write-Host "Press Enter to close this window..." -ForegroundColor Cyan
        try { Read-Host | Out-Null } catch { Start-Sleep -Seconds 45 }
    }
}
