@echo off
setlocal
set "MIRA_PYTHON=%~dp0..\Shared\python\python.exe"
if not exist "%MIRA_PYTHON%" set "MIRA_PYTHON=python"
"%MIRA_PYTHON%" "%~dp0..\Shared\setup_firstvds.py"
pause
