@echo off
setlocal
set "USB_AI_PERSONAL_LAUNCHER=%~dp0start-personal.bat"
powershell.exe -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $picker = New-Object System.Windows.Forms.FolderBrowserDialog; $picker.Description = 'Select the extracted or cloned mariako_crm folder'; $picker.ShowNewFolderButton = $false; if ($picker.ShowDialog() -ne 'OK') { exit 0 }; $env:USB_AI_CRM_PROJECT = $picker.SelectedPath; $picker.Dispose(); & $env:USB_AI_PERSONAL_LAUNCHER; exit $LASTEXITCODE"
if errorlevel 1 pause
