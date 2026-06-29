# Revit Bridge V3.21 Patch Notes + Revit RAG Plan

## Patch summary

Target script: `openai_revit_bridge_main(8).py`

Output script: `openai_revit_bridge_main_v3_21_dynamic_waits_batch_upload.py`

Main changes:

1. Removed GUI Revit modal dialog click sweeps.
   - No post-run coordinate clicks for Unjoin, OK, warning OK, disconnect-style OK, or Cancel.
   - The API-level `DialogBoxShowing` guard and failure preprocessor remain in place because they do not rely on screen clicks.

2. Added cycle-specific wait functions.
   - `decide_chatgpt_wait_seconds(...)`
   - `decide_rps_wait_seconds(...)`
   - `decide_retry_wait_seconds(...)`
   - The bridge can also read explicit hint comments from a returned code block:
     - `# BRIDGE_RPS_WAIT_SECONDS: 75`
     - `# BRIDGE_CHATGPT_WAIT_SECONDS: 150`
     - `# BRIDGE_RETRY_WAIT_SECONDS: 90`

3. Reduced retries.
   - The ChatGPT code-copy logic now uses one retry only: first attempt + one retry.
   - Retry wait is dynamic rather than four fixed 60-second retries.

4. Reduced short waits to 3 seconds.
   - Default short waits, page-down pre/post copy waits, browser refresh wait, QC upload step wait, pause-after-copy, and normal paste wait are 3 seconds.
   - ChatGPT input paste keeps a longer default wait: 7 seconds.
   - File-picker Open click keeps a longer default wait: 7 seconds.

5. Batch QC upload.
   - The bridge now attempts to select all eligible QC files from `C:\RevitBridge\QC_Upload` in one Windows file-picker operation.
   - Successfully uploaded files are deleted after upload.
   - A single-file fallback path remains available through config.

6. Revit RAG seed instruction added to the bridge prompt.
   - The bridge now tells ChatGPT to prefer stable known patterns from Revit API docs, pyRevit, RevitPythonShell, RevitLookup, and prior bridge outputs before speculating.

## Suggested Revit / Python RAG corpus

Recommended starting corpus for a local RAG folder:

1. Autodesk Revit API SDK documentation and samples.
2. Revit API Docs / RevitAPIDocs pages for version-specific class and method lookup.
3. RevitLookup source and notes, for database/parameter/property discovery.
4. RevitPythonShell source and docs, for IronPython shell behavior.
5. pyRevit source and extension examples, for production Python add-in patterns.
6. The Building Coder and Jeremy Tammik SDK samples, for vetted API usage patterns.
7. Your own bridge history: RPS outputs, successful scripts, failure logs, modal guard logs, QC notes, and idempotent cleanup patterns.

## Minimal local folder structure

```text
C:\RevitBridge\RAG\
  00_manifest\
  01_autodesk_revit_sdk\
  02_revit_api_docs\
  03_revit_lookup\
  04_revit_python_shell\
  05_pyrevit\
  06_bridge_success_patterns\
  07_bridge_failure_patterns\
  08_project_specific_notes\
```

## Retrieval rules for bridge use

Use this priority order:

1. Current RPS output and active model metadata.
2. Project-specific notes and previous successful bridge scripts.
3. Revit API docs / SDK samples for the active Revit version.
4. pyRevit / RPS examples only where IronPython compatibility matters.
5. RevitLookup / database exploration notes for unknown parameters, categories, or relationships.
6. Broader web/forum examples only after the above are insufficient.

## Recommended chunking

- API docs: one class or method per chunk, with version tag.
- SDK samples: one command or transaction pattern per chunk.
- Bridge scripts: one successful operation pattern per chunk.
- Failures: one error signature plus fix per chunk.

## Metadata to store per chunk

```json
{
  "source_type": "sdk|api_doc|pyrevit|rps|revitlookup|bridge_success|bridge_failure|project_note",
  "revit_version": "2020|2023|2024|2026|unknown",
  "language": "IronPython|C#|Python.NET|mixed",
  "api_area": "View|Sheet|Element|Transaction|FailureHandling|Export|Annotation|Family|Geometry",
  "risk": "low|medium|high",
  "verified_in_bridge": true
}
```
