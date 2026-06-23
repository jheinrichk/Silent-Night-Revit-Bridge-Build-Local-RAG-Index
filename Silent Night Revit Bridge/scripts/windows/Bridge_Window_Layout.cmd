@echo off
set "BRIDGE_LAYOUT_MODE=%~1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$code=(Get-Content -LiteralPath '%~f0' | Select-Object -Skip 4) -join [Environment]::NewLine; Invoke-Expression $code"
exit /b %ERRORLEVEL%

$ErrorActionPreference = "Stop"

$OutDir = "C:\RevitBridge\Window_Layouts"
if (!(Test-Path $OutDir)) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
}

$TimeStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$JsonPath = Join-Path $OutDir ("bridge_window_layout_" + $TimeStamp + ".json")
$CsvPath = Join-Path $OutDir ("bridge_window_layout_" + $TimeStamp + ".csv")
$LatestJsonPath = Join-Path $OutDir "bridge_window_layout_latest.json"
$LatestCsvPath = Join-Path $OutDir "bridge_window_layout_latest.csv"

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;

public class Win32WindowCapture {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool IsZoomed(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }
}
"@

$Windows = New-Object System.Collections.Generic.List[object]

$Callback = [Win32WindowCapture+EnumWindowsProc]{
    param([IntPtr]$hWnd, [IntPtr]$lParam)

    if (-not [Win32WindowCapture]::IsWindowVisible($hWnd)) {
        return $true
    }

    $TextLength = [Win32WindowCapture]::GetWindowTextLength($hWnd)
    if ($TextLength -le 0) {
        return $true
    }

    $Builder = New-Object System.Text.StringBuilder ($TextLength + 1)
    [void][Win32WindowCapture]::GetWindowText($hWnd, $Builder, $Builder.Capacity)
    $Title = $Builder.ToString()

    if ([string]::IsNullOrWhiteSpace($Title)) {
        return $true
    }

    $Rect = New-Object Win32WindowCapture+RECT
    [void][Win32WindowCapture]::GetWindowRect($hWnd, [ref]$Rect)

    $Width = $Rect.Right - $Rect.Left
    $Height = $Rect.Bottom - $Rect.Top

    if ($Width -lt 80 -or $Height -lt 80) {
        return $true
    }

    [uint32]$ProcessIdValue = 0
    [void][Win32WindowCapture]::GetWindowThreadProcessId($hWnd, [ref]$ProcessIdValue)

    $ProcessName = ""
    $ProcessPath = ""

    try {
        $Process = Get-Process -Id $ProcessIdValue -ErrorAction Stop
        $ProcessName = $Process.ProcessName
        try {
            $ProcessPath = $Process.Path
        } catch {
            $ProcessPath = ""
        }
    } catch {
        $ProcessName = ""
        $ProcessPath = ""
    }

    $State = "Normal"
    if ([Win32WindowCapture]::IsIconic($hWnd)) {
        $State = "Minimized"
    } elseif ([Win32WindowCapture]::IsZoomed($hWnd)) {
        $State = "Maximized"
    }

    $Windows.Add([pscustomobject]@{
        Hwnd        = $hWnd.ToInt64()
        ProcessId   = $ProcessIdValue
        ProcessName = $ProcessName
        ProcessPath = $ProcessPath
        WindowTitle = $Title
        X           = $Rect.Left
        Y           = $Rect.Top
        Width       = $Width
        Height      = $Height
        Right       = $Rect.Right
        Bottom      = $Rect.Bottom
        State       = $State
    }) | Out-Null

    return $true
}

[void][Win32WindowCapture]::EnumWindows($Callback, [IntPtr]::Zero)

$Sorted = $Windows |
    Sort-Object X, Y, ProcessName, WindowTitle

$Sorted |
    ConvertTo-Json -Depth 5 |
    Set-Content -Path $JsonPath -Encoding UTF8

$Sorted |
    Export-Csv -Path $CsvPath -NoTypeInformation -Encoding UTF8

Copy-Item $JsonPath $LatestJsonPath -Force
Copy-Item $CsvPath $LatestCsvPath -Force

Write-Host ""
Write-Host "Captured visible window layout:"
Write-Host $JsonPath
Write-Host $CsvPath
Write-Host ""
Write-Host "Latest copies:"
Write-Host $LatestJsonPath
Write-Host $LatestCsvPath
Write-Host ""
Write-Host "Captured windows:"
$Sorted | Format-Table ProcessName, X, Y, Width, Height, State, WindowTitle -AutoSize

Write-Host ""
Write-Host "Done."
pause
