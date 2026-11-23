$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$shared = Join-Path (Split-Path $PSScriptRoot -Parent) 'Shared'
$root = Join-Path $shared 'bin\mira-whisper'
$exe = Join-Path $root 'Release\whisper-cli.exe'
$model = Join-Path $root 'ggml-small-q5_1.bin'
$modelHash = 'ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb'
$zipHash = 'ecca07b277d943e9b9f4712856a144b857271a6b333104e511e1988e80db582b'
New-Item -ItemType Directory -Force -Path $root | Out-Null

function Get-VerifiedFile($Url, $Destination, $Hash) {
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash -ne $Hash) {
        throw "SHA256 check failed for $Url"
    }
}

$stage = Join-Path $root ('.setup-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        Write-Host 'Downloading Whisper for Windows x64...'
        $zip = Join-Path $stage 'whisper.zip'
        Get-VerifiedFile 'https://github.com/ggml-org/whisper.cpp/releases/download/b5907/whisper-bin-x64.zip' $zip $zipHash
        Expand-Archive -LiteralPath $zip -DestinationPath $stage
        if (-not (Test-Path -LiteralPath (Join-Path $stage 'Release\whisper-cli.exe'))) {
            throw 'Whisper executable missing from archive.'
        }
        Copy-Item -LiteralPath (Join-Path $stage 'Release') -Destination $root -Recurse -Force
    }
    if (-not (Test-Path -LiteralPath $model -PathType Leaf) -or
        (Get-FileHash -Algorithm SHA256 -LiteralPath $model).Hash -ne $modelHash) {
        Write-Host 'Downloading Whisper Small multilingual (190 MB)...'
        $download = Join-Path $stage 'ggml-small-q5_1.bin'
        Get-VerifiedFile 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small-q5_1.bin' $download $modelHash
        Move-Item -LiteralPath $download -Destination $model -Force
    }
    $stdout = Join-Path $stage 'whisper.stdout'
    $stderr = Join-Path $stage 'whisper.stderr'
    $check = Start-Process -FilePath $exe -ArgumentList '--help' -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    if ($check.ExitCode -ne 0) { throw "Whisper executable failed to start (exit $($check.ExitCode))." }
    $voiceRoot = Join-Path $shared 'bin\mira-voice'
    $piperRoot = Join-Path $voiceRoot 'piper'
    if (-not (Test-Path -LiteralPath (Join-Path $piperRoot 'piper.exe') -PathType Leaf)) {
        Write-Host 'Downloading Piper for Windows x64...'
        $piperZip = Join-Path $stage 'piper.zip'
        Get-VerifiedFile 'https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip' $piperZip 'f3c58906402b24f3a96d92145f58acba6d86c9b5db896d207f78dc80811efcea'
        Expand-Archive -LiteralPath $piperZip -DestinationPath $stage
        if (-not (Test-Path -LiteralPath (Join-Path $stage 'piper\piper.exe') -PathType Leaf)) {
            throw 'Piper executable missing from archive.'
        }
        New-Item -ItemType Directory -Force -Path $voiceRoot | Out-Null
        Copy-Item -LiteralPath (Join-Path $stage 'piper') -Destination $voiceRoot -Recurse -Force
    }
    $voiceUrl = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium'
    $voiceFiles = @{
        'ru_RU-irina-medium.onnx' = '8ff38212d23da300bbe3705c645e6e5b9475f0bfde01558eb17813e22acaaaaa'
        'ru_RU-irina-medium.onnx.json' = 'c2ec28bb38e2b59e93b959b3e40348c1afebbd272f30fed5d41205d08e98a9d7'
    }
    foreach ($file in $voiceFiles.Keys) {
        $destination = Join-Path $piperRoot $file
        $hash = $voiceFiles[$file]
        if (-not (Test-Path -LiteralPath $destination -PathType Leaf) -or
            (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash -ne $hash) {
            Write-Host "Downloading Irina voice file: $file"
            $download = Join-Path $stage $file
            Get-VerifiedFile "$voiceUrl/$file" $download $hash
            Move-Item -LiteralPath $download -Destination $destination -Force
        }
    }
    Write-Host 'Mira is ready. Start Windows\start-personal.bat.'
} finally {
    Remove-Item -LiteralPath $stage -Recurse -Force
}
