# LLM-to-Revit Bridge Agent Protocol

Use the bridge as a Vision-Language-Action state machine: observe the current RPS output and QC PNG, write exactly one IronPython-compatible Revit script, execute, then verify. Prefer query/discovery scripts before modification when element ids, parameter names, active view, sheet viewport boxes, crop boxes, or family/type names are uncertain. Modification scripts must use transactions, rollback on failure, and print RESULTS, ERRORS, QAQC, and NEXT_RECOMMENDED_STATE.

Timing comments can be placed at the top of generated scripts when a cycle is expected to be slow:

```python
# BRIDGE_RPS_WAIT_SECONDS: 90
# BRIDGE_CHATGPT_WAIT_SECONDS: 150
# BRIDGE_RETRY_WAIT_SECONDS: 90
```

Export QC files directly to C:\RevitBridge\QC_Upload with short filenames. Use uidoc.RefreshActiveView() after graphical changes before export when possible.
