@echo off
setlocal
set "MIRA_EXPORTER=%~dp0export-mira-review.py"
powershell.exe -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $pick = New-Object System.Windows.Forms.FolderBrowserDialog; $pick.Description = 'Select the installed Mira folder, the one you usually start'; if ($pick.ShowDialog() -ne 'OK') { exit 0 }; $root = $pick.SelectedPath; $pick.Dispose(); if ((Split-Path -Leaf $root) -in @('Windows','Shared')) { $root = Split-Path -Parent $root }; $save = New-Object System.Windows.Forms.SaveFileDialog; $save.Filter = 'ZIP (*.zip)|*.zip'; $save.FileName = 'Mira-review-' + (Get-Date -Format yyyyMMdd-HHmmss) + '.zip'; if ($save.ShowDialog() -ne 'OK') { exit 0 }; $output = $save.FileName; $save.Dispose(); $python = Join-Path $root 'Shared\python\python.exe'; if (-not (Test-Path -LiteralPath $python)) { $python = 'python' }; & $python $env:MIRA_EXPORTER $root $output; exit $LASTEXITCODE"
pause
