@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "$code=(Get-Content -LiteralPath '%~f0' | Select-Object -Skip 3) -join [Environment]::NewLine; Invoke-Expression $code"
exit /b %ERRORLEVEL%

$LayoutJson = "C:\RevitBridge\Window_Layouts\bridge_window_layout_latest.json"

if (!(Test-Path $LayoutJson)) {
    Write-Host "Layout JSON not found:"
    Write-Host $LayoutJson
    pause
    exit
}

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;

public class Win32WindowRestore {
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
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [DllImport("user32.dll")]
    public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@

$SW_RESTORE = 9
$SWP_NOZORDER = 0x0004
$SWP_SHOWWINDOW = 0x0040

$Layout = Get-Content $LayoutJson -Raw | ConvertFrom-Json

$OpenWindows = New-Object System.Collections.Generic.List[object]

$Callback = [Win32WindowRestore+EnumWindowsProc]{
    param([IntPtr]$hWnd, [IntPtr]$lParam)

    if (-not [Win32WindowRestore]::IsWindowVisible($hWnd)) {
        return $true
    }

    $TextLength = [Win32WindowRestore]::GetWindowTextLength($hWnd)
    if ($TextLength -le 0) {
        return $true
    }

    $Builder = New-Object System.Text.StringBuilder ($TextLength + 1)
    [void][Win32WindowRestore]::GetWindowText($hWnd, $Builder, $Builder.Capacity)
    $Title = $Builder.ToString()

    [uint32]$ProcessIdValue = 0
    [void][Win32WindowRestore]::GetWindowThreadProcessId($hWnd, [ref]$ProcessIdValue)

    $ProcessName = ""
    try {
        $Process = Get-Process -Id $ProcessIdValue -ErrorAction Stop
        $ProcessName = $Process.ProcessName
    } catch {
        $ProcessName = ""
    }

    $OpenWindows.Add([pscustomobject]@{
        Hwnd = $hWnd
        ProcessName = $ProcessName
        WindowTitle = $Title
    }) | Out-Null

    return $true
}

[void][Win32WindowRestore]::EnumWindows($Callback, [IntPtr]::Zero)

foreach ($Saved in $Layout) {
    $Match = $OpenWindows | Where-Object {
        $_.ProcessName -eq $Saved.ProcessName -and $_.WindowTitle -eq $Saved.WindowTitle
    } | Select-Object -First 1

    if ($null -eq $Match) {
        $Match = $OpenWindows | Where-Object {
            $_.ProcessName -eq $Saved.ProcessName -and
            (
                $_.WindowTitle.Contains($Saved.WindowTitle) -or
                $Saved.WindowTitle.Contains($_.WindowTitle)
            )
        } | Select-Object -First 1
    }

    if ($null -ne $Match) {
        [void][Win32WindowRestore]::ShowWindow($Match.Hwnd, $SW_RESTORE)
        Start-Sleep -Milliseconds 100

        [void][Win32WindowRestore]::SetWindowPos(
            $Match.Hwnd,
            [IntPtr]::Zero,
            [int]$Saved.X,
            [int]$Saved.Y,
            [int]$Saved.Width,
            [int]$Saved.Height,
            $SWP_NOZORDER -bor $SWP_SHOWWINDOW
        )

        Write-Host "Restored:" $Saved.ProcessName "-" $Saved.WindowTitle
    } else {
        Write-Host "Skipped, not open:" $Saved.ProcessName "-" $Saved.WindowTitle
    }
}

Write-Host ""
Write-Host "Done restoring window layout."
pause
