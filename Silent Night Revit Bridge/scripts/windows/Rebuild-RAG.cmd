@echo off
REM ============================================
REM SILENT_NIGHT Revit Bridge - Rebuild RAG Index
REM ============================================

echo Rebuilding local RAG knowledge base...
cd /d "%~dp0\..\.."

python RAG\rag_ingest.py

echo Done.
pause
