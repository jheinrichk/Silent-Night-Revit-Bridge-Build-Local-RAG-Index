# Architecture

SILENT_NIGHT Bridge is a browser-mediated LLM-to-Revit control loop.

## Loop

1. Browser prompt sends bridge protocol and the current state to the LLM.
2. LLM returns one fenced IronPython-compatible Revit Python script.
3. The bridge copies that script into Revit Python Shell.
4. Revit executes the script, writing:
   - console output
   - errors
   - `NEXT_RECOMMENDED_STATE`
   - optional QC PNGs
5. The bridge uploads all QC PNGs staged for that cycle.
6. The bridge sends RPS output plus upload status back to the LLM.
7. The local RAG layer logs the cycle and retrieves relevant prior patterns for the next cycle.

## Core principles

- Observe-execute-verify state machine
- Vision-Language-Action feedback loop
- Idempotent agent-created artifacts
- Transaction discipline
- Visual QAQC
- Local retrieval for repeated Revit/API patterns
