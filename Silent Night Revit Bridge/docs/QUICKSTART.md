# SILENT_NIGHT Bridge – Quickstart for Windows 11 + Revit 202x

This guide gets you from zero to a running unattended Revit bridge on Windows 11.

## 1. Prerequisites

| Component              | Recommended                          | Notes |
|------------------------|--------------------------------------|-------|
| **Revit**              | 2024 or 2025                         | Works with 2023+ |
| **RevitPythonShell**   | Latest from GitHub                   | **Required** – see section below |
| **Python**             | 3.10, 3.11 or 3.12 (64-bit)          | Add to PATH during install |
| **Windows**            | 11 (22H2 or newer)                   | Tested on 23H2 / 24H2 |
| **Display scaling**    | 100% or 125%                         | Higher scaling may need re-calibration |

### Installing RevitPythonShell (RPS)

**The bridge does NOT install RevitPythonShell.**  
You must install it first.

Recommended method (2025–2026):

1. Go to: https://github.com/architecture-building-systems/revitpythonshell/releases
2. Download the latest `.msi` or `.zip` installer for your Revit version.
3. Run the installer **as Administrator**.
4. Restart Revit.
5. You should now see **"Interactive Python Shell"** under the Add-ins tab (or in the RevitPythonShell panel).

Alternative: Some pyRevit distributions include a compatible RPS version.

> **Important**: Leave the Interactive Python Shell window **open** before starting the bridge. The bridge sends code into this window via automation.

## 2. One-time Setup (Recommended PowerShell method)

Open **PowerShell 7** (or Windows PowerShell) **as Administrator** and run:

```powershell
# Download and run the setup script
irm https://raw.githubusercontent.com/your-org/silent-night-revit-bridge/main/scripts/windows/Setup-SilentNightBridge.ps1 | iex
```

Or do it manually:

```bat
pip install pyautogui pyperclip

mkdir C:\RevitBridge\QC_Exports
mkdir C:\RevitBridge\QC_Upload
mkdir C:\RevitBridge\RAG\cycles
mkdir C:\RevitBridge\RAG\vector_store

copy config\bridge_config.example.json bridge_config.json
```

## 3. Calibrate Mouse Coordinates

This is the most important step for reliability.

```bat
python tools\calibration_ui.py
```

Follow the on-screen countdown capture for:
- ChatGPT input box
- ChatGPT submit button
- ChatGPT code block **Copy** button (after Page Down)
- RPS input area, Run button, and output area
- ChatGPT attach / Add files buttons
- File picker filename field + Open button
- Browser refresh button (Edge/Chrome)

Save when done. The coordinates are stored in `bridge_config.json`.

## 4. Build the Local RAG Index

```bat
python RAG\rag_ingest.py
```

This indexes the seed documentation + any previous bridge cycles.

## 5. Run the Bridge

```bat
python src\openai_revit_bridge_main_v3_22_rag.py
```

Paste your initial redline prompt, then type `END` on its own line.

The bridge will now run unattended for up to 2222 cycles (or until it hits a `FIX_ERRORS` state you configured it to stop on).

## 6. Safety & Best Practices

- **Always test first** on a detached/local copy of your model.
- Keep the **Interactive Python Shell** window visible but not necessarily focused.
- The bridge disables PyAutoGUI failsafe — use **Ctrl+C** in the terminal to stop.
- Monitor the first 3–5 cycles closely until you trust the coordinates and timing.
- For very long sessions, occasionally run `python RAG\rag_ingest.py` to fully refresh the index.

## Folder Layout (Created by setup)

```
C:\RevitBridge\
├── QC_Exports\          ← Revit should export QC PNGs here
├── QC_Upload\           ← Bridge stages files here for upload
├── RAG\
│   ├── cycles\          ← Live cycle history (self-improving)
│   └── vector_store\    ← Indexed knowledge
├── bridge_config.json
└── revit_modal_guard_last_log.txt
```

## Troubleshooting

| Problem                        | Likely Cause                          | Fix |
|--------------------------------|---------------------------------------|-----|
| Bridge pastes into wrong window | File picker still open                | v3.22 file dialog guard should prevent this |
| Coordinates stop working       | Windows scaling changed / DPI         | Re-run `calibration_ui.py` |
| RPS never receives code        | RPS window not open or wrong title    | Open Interactive Python Shell first |
| Upload fails                   | Dialog detection missed             | Check `upload_debug_log.txt` in QC_Upload |

Need help with a specific error? Paste the terminal output + the relevant section of `upload_debug_log.txt`.
