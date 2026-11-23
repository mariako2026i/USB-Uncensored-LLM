$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$shared = Join-Path (Split-Path $PSScriptRoot -Parent) 'Shared'
$root = Join-Path $shared 'bin\mira-whisper'
$exe = Join-Path $root 'Release\whisper-cli.exe'
$model = Join-Path $root 'ggml-base-q5_1.bin'
$modelHash = '422f1ae452ade6f30a004d7e5c6a43195e4433bc370bf23fac9cc591f01a8898'
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
        Write-Host 'Downloading multilingual Whisper model (60 MB)...'
        $download = Join-Path $stage 'ggml-base-q5_1.bin'
        Get-VerifiedFile 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base-q5_1.bin' $download $modelHash
        Move-Item -LiteralPath $download -Destination $model -Force
    }
    $stdout = Join-Path $stage 'whisper.stdout'
    $stderr = Join-Path $stage 'whisper.stderr'
    $check = Start-Process -FilePath $exe -ArgumentList '--help' -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    if ($check.ExitCode -ne 0) { throw "Whisper executable failed to start (exit $($check.ExitCode))." }
    Write-Host 'Mira is ready. Start Windows\start-personal.bat.'
} finally {
    Remove-Item -LiteralPath $stage -Recurse -Force
}
