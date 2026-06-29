# SILENT_NIGHT Revit Bridge

 LLM using a continuous observe-execute-verify state machine autonomously in Revit

A local LLM-to-Revit bridge for operating Autodesk Revit through a continuous **observe-execute-verify** state machine using Revit Python Shell output plus PNG view/sheet feedback.

## Repository description

This workflow uses a custom LLM-to-Revit bridge that creates an autonomous Vision-Language-Action agentic loop between ChatGPT, the Revit Python Interactive Shell and Revit’s visual model state. The system sends IronPython scripts from the LLM into Revit, then returns structured console output, execution errors, state reports and exported PNG views or sheets back through the browser for visual verification. This allows the LLM to operate Revit as a continuous observe-execute-verify state machine: it queries model data instead of guessing, modifies the model through controlled transactions, tags and tracks its own generated elements, exports focused QAQC images and uses both textual and visual feedback to self-correct subsequent actions. In effect, Revit becomes a live model environment controlled by an autonomous agent that can iteratively inspect, draft, revise, clean up and validate work without manual scripting between cycles.


## Recent improvements (v3.22)

The bridge now includes a robust Windows file picker guard using native Win32 APIs (`#32770` class detection). It:
- Waits for the Open dialog to actually appear after "Add files"
- Uses full quoted paths + Alt+N / Enter to avoid stale filename bugs
- Explicitly waits for the dialog to close before pasting the next prompt back to ChatGPT
This dramatically reduces stuck cycles and "text pasted into wrong window" issues during QC PNG uploads.

**Live / self-improving RAG**  
Every completed bridge cycle is immediately written to the local RAG cycle log and becomes available as retrieval context for the *very next* cycle. The agent gets better at your specific Revit project, code patterns, and this exact bridge environment over the course of a single long session without needing a manual re-ingest.


## What this contains

- `src/openai_revit_bridge_main_v3_22_rag.py`  
  Main unattended browser-to-Revit bridge runner with local RAG hook.

- `tools/calibration_ui.py`  
  Coordinate calibration UI for ChatGPT, browser, file picker and Revit Python Shell control points.

- `config/bridge_config.example.json`  
  Example bridge coordinate and timing configuration.

- `snippets/revit_qc_export_snippet.py`  
  Revit-side snippet the LLM can adapt to export views/sheets for visual QAQC.

- `scripts/windows/Bridge_Window_Layout.cmd` and `Bridge_Window_Restore.cmd`  
  Window layout helper scripts for the bridge workflow.

- `RAG/`  
  Local lightweight retrieval layer for bridge cycle memory, Revit API patterns, visual QAQC rules and project-specific lessons.


## Operating concept

The bridge runs an agentic loop:

1. **Observe**: read RPS console output, execution errors, current view/sheet PNGs and local RAG context.
2. **Execute**: send exactly one IronPython-compatible Revit script into the Revit Python Interactive Shell.
3. **Verify**: copy RPS output, upload QC PNGs and evaluate whether the change is visible and correct.
4. **Correct**: use transaction discipline, parameter discovery, element tagging and cleanup rules to revise the model without leaving clutter.

## Quickstart

See **[docs/QUICKSTART.md](docs/QUICKSTART.md)** for a complete Windows 11 + Revit guide, including a one-click PowerShell setup script.

## Install notes

1. Install Python dependencies:

```bat
pip install pyautogui pyperclip
```

2. Place the repo folder where you want to run the bridge.

3. Copy or edit:

```text
config\bridge_config.example.json
```

to the working bridge location as:

```text
bridge_config.json
```

4. Run calibration when needed:

```bat
python tools\calibration_ui.py
```

5. Build the local RAG index:

```bat
python RAG\rag_ingest.py
```

6. Run the bridge:

```bat
python src\openai_revit_bridge_main_v3_22_rag.py
```

## Runtime folders

The live workflow expects these local folders on the Windows/Revit machine:

```text
C:\RevitBridge\QC_Exports
C:\RevitBridge\QC_Upload
C:\RevitBridge\RAG
```

Generated PNGs, logs, runtime cycle records and vector-store files should generally stay out of Git unless they are intentionally committed as examples.

## Safety and model hygiene rules

- Every model-changing script must use a Revit transaction.
- Agent-created model elements should be tagged using `Comments` or a strict `AGENT_` naming convention.
- Before repeating or redesigning a layout, delete or archive prior temporary agent artifacts.
- Visual QAQC is not complete until the exported PNG clearly shows the intended change in the correct view or sheet region.
- Query parameters and element IDs before modifying. Do not guess Revit parameter names.
- Current RPS output and current QC images are authoritative over older RAG memory.

## Status

Experimental workflow automation. Use on test/detached/local models until each workflow is proven safe.
