@echo off
setlocal
set "USB_AI_PERSONAL_LAUNCHER=%~dp0start-personal.bat"
powershell.exe -NoProfile -Command "$key = Read-Host 'OpenAI API key (input is hidden)' -AsSecureString; if ($key.Length -eq 0) { exit 1 }; $env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $key).Password; try { & $env:USB_AI_PERSONAL_LAUNCHER; exit $LASTEXITCODE } finally { Remove-Item Env:OPENAI_API_KEY; $key.Dispose() }"
if errorlevel 1 pause
