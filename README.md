<p align="center">
  <img src="./assets/SNRB.png" alt="Silent Night Revit Bridge Logo" width="520">
</p>

<h1 align="center">Silent Night Revit Bridge</h1>

<p align="center">
  A local LLM to Revit bridge using a continuous <strong>observe-execute-verify</strong> state machine.
</p>

---

## Repository description

Silent Night Revit Bridge is a local LLM to Revit workflow that creates an autonomous Vision-Language-Action agentic loop between ChatGPT, the Revit Python Interactive Shell and Revit’s visual model state.

The system sends IronPython scripts from the LLM into Autodesk Revit, then returns structured console output, execution errors, state reports and exported PNG views or sheets back through the browser for visual verification. This allows the LLM to operate Revit as a continuous observe-execute-verify state machine. It queries model data instead of guessing, modifies the model through controlled transactions, tags and tracks its own generated elements, exports focused QAQC images and uses both textual and visual feedback to self-correct subsequent actions.

In effect, Revit becomes a live model environment controlled by an autonomous agent that can iteratively inspect, draft, revise, clean up and validate work without manual scripting between cycles.

---

## Recent improvements

### v3.22

The bridge now includes a robust Windows file picker guard using native Win32 APIs with `#32770` class detection.

It now:

- Waits for the Open dialog to actually appear after selecting “Add files”
- Uses full quoted paths plus `Alt+N` and `Enter` to avoid stale filename bugs
- Explicitly waits for the dialog to close before pasting the next prompt back to ChatGPT
- Reduces stuck cycles where text is pasted into the wrong window during QC PNG uploads

### Live self-improving RAG

Every completed bridge cycle is immediately written to the local RAG cycle log and becomes available as retrieval context for the next cycle.

The agent gets better at the specific Revit project, code patterns and bridge environment over the course of a single long session without needing a manual re-ingest.

---

## What this contains

- `src/openai_revit_bridge_main_v3_22_rag.py`  
  Main unattended browser to Revit bridge runner with local RAG hook.

- `tools/calibration_ui.py`  
  Coordinate calibration UI for ChatGPT, browser, file picker and Revit Python Shell control points.

- `config/bridge_config.example.json`  
  Example bridge coordinate and timing configuration.

- `snippets/revit_qc_export_snippet.py`  
  Revit-side snippet the LLM can adapt to export views or sheets for visual QAQC.

- `scripts/windows/Bridge_Window_Layout.cmd` and `Bridge_Window_Restore.cmd`  
  Window layout helper scripts for the bridge workflow.

- `RAG/`  
  Local lightweight retrieval layer for bridge cycle memory, Revit API patterns, visual QAQC rules and project-specific lessons.

---

## Operating concept

The bridge runs an agentic loop:

1. **Observe**: read Revit Python Shell console output, execution errors, current view or sheet PNGs and local RAG context.
2. **Execute**: send exactly one IronPython-compatible Revit script into the Revit Python Interactive Shell.
3. **Verify**: copy Revit Python Shell output, upload focused QC PNGs and evaluate whether the change is visible and correct.
4. **Correct**: use transaction discipline, parameter discovery, element tagging and cleanup rules to revise the model without leaving clutter.

---

## Quickstart

See **[docs/QUICKSTART.md](docs/QUICKSTART.md)** for a complete Windows 11 and Revit guide, including a one-click PowerShell setup script.

---

## Install notes

### 1. Install Python dependencies

```bat
pip install pyautogui pyperclip
```

### 2. Place the repository folder

Place the repo folder where you want to run the bridge.

### 3. Copy or edit the configuration

Copy or edit:

```text
config\bridge_config.example.json
```

to the working bridge location as:

```text
bridge_config.json
```

### 4. Run calibration when needed

```bat
python tools\calibration_ui.py
```

### 5. Build the local RAG index

```bat
python RAG\rag_ingest.py
```

### 6. Run the bridge

```bat
python src\openai_revit_bridge_main_v3_22_rag.py
```

---

## Runtime folders

The live workflow expects these local folders on the Windows/Revit machine:

```text
C:\RevitBridge\QC_Exports
C:\RevitBridge\QC_Upload
C:\RevitBridge\RAG
```

Typical runtime files include:

```text
C:\RevitBridge\rps_last_output.txt
C:\RevitBridge\QC_Exports\*.png
C:\RevitBridge\QC_Upload\*.png
C:\RevitBridge\RAG\cycle_logs\*.jsonl
```

Generated PNGs, logs, runtime cycle records and vector store files should generally stay out of Git unless they are intentionally committed as examples.

---

## Bridge prompt contract

The bridge is designed around strict prompt and output discipline.

Typical Revit bridge prompt requirements:

```text
MODE:REVIT_BRIDGE
RETURN:FIRST_EXECUTABLE_REVIT_PYTHON_CODE_BLOCK_ONLY
SCRIPT:IRONPYTHON_COMPATIBLE;NO_F_STRINGS;NO_TYPE_HINTS
REQ:PRINT_RESULTS_ERRORS_NEXT_RECOMMENDED_STATE
REQ:COPY_FINAL_OUTPUT_TO_WINDOWS_CLIPBOARD
REQ:WRITE_FINAL_OUTPUT_TO_C:\RevitBridge\rps_last_output.txt
REQ:QC_EXPORT_SHORT_FILENAME
IF_MODIFY:USE_TRANSACTION;ROLLBACK_OR_REPORT_FAILURE
OUTPUT:CODE_FIRST;NO_PROSE_BEFORE_CODE
```

The LLM response should normally contain one executable IronPython-compatible Revit script and nothing before the first code block.

---

## Visual QAQC

Visual QAQC is treated as authoritative.

The agent should not mark a task complete unless the exported PNG clearly shows the intended change in the intended view, sheet or detail region.

Preferred QAQC behavior:

- Export only the focused views needed to verify the current change
- Avoid unnecessary PNG uploads
- Use short QC filenames
- Compare the visual output against the instruction
- Continue correcting until the change is visible and correct or until the workflow stops for error handling

---

## Safety and model hygiene rules

- Every model-changing script must use a Revit transaction.
- Agent-created model elements should be tagged using `Comments` or a strict `AGENT_` naming convention.
- Before repeating or redesigning a layout, delete or archive prior temporary agent artifacts.
- Visual QAQC is not complete until the exported PNG clearly shows the intended change in the correct view or sheet region.
- Query parameters and element IDs before modifying. Do not guess Revit parameter names.
- Current Revit Python Shell output and current QC images are authoritative over older RAG memory.

---

## Revit transaction discipline

Any script that modifies the Revit model should follow this pattern:

```python
t = Transaction(doc, "Agent operation")
try:
    t.Start()

    # Modify the model here.

    t.Commit()
    print("STATUS: COMMITTED")
except Exception as ex:
    if t.HasStarted():
        t.RollBack()
    print("STATUS: ROLLED_BACK")
    print("ERROR: " + str(ex))
```

The bridge should report:

```text
RESULT
ERRORS
NEXT_RECOMMENDED_STATE
```

at the end of each Revit Python Shell run.

---

## Local RAG behavior

The local RAG layer is used to retrieve:

- Recent successful cycle patterns
- Previous Revit API errors and fixes
- Project-specific conventions
- Visual QAQC rules
- Cleanup requirements
- Parameter discovery results
- Model state summaries
- Long-running workflow decisions

The current cycle always overrides stale retrieval memory.

RAG should help the agent avoid repeating mistakes without replacing direct model queries.

---

## Suggested `.gitignore`

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.venv/
venv/

# Runtime logs
*.log
rps_last_output.txt

# Revit Bridge runtime folders
QC_Exports/
QC_Upload/
cycle_logs/
vector_store/

# Local config
bridge_config.json
*.local.json

# Revit and CAD working files
*.rvt
*.rfa
*.rte
*.rws
*.slog
*.dwg
*.bak

# Large generated image output
*.tmp.png
*_qc.png
```

---

## Status

Experimental workflow automation.

Use on test, detached or local models until each workflow is proven safe.
