@echo off
setlocal
cd /d "%~dp0"
call "scripts\windows\Rebuild-RAG.cmd"
endlocal
