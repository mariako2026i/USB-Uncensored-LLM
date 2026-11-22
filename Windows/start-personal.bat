@echo off
setlocal
set "OLLAMA_CONTEXT_LENGTH=4096"
call "%~dp0start-fast-chat.bat" --personal
