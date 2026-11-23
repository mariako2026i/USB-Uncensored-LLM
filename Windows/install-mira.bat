@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-mira.ps1"
set "MIRA_EXIT=%ERRORLEVEL%"
if not "%MIRA_EXIT%"=="0" echo Mira installation failed. See the error above.
pause
exit /b %MIRA_EXIT%
