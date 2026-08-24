$ErrorActionPreference = "Stop"

$ProjectPath = $PSScriptRoot
$RequirementsPath = Join-Path $ProjectPath "requirements.txt"
$EnvironmentPath = Join-Path $ProjectPath ".venv"
$BackupPath = Join-Path $ProjectPath (".venv_backup_" + (Get-Date -Format "yyyyMMdd_HHmmss"))

if (-not (Test-Path -LiteralPath $RequirementsPath)) {
    throw "requirements.txt não foi encontrado em $ProjectPath"
}

Set-Location -LiteralPath $ProjectPath

if (Test-Path -LiteralPath $EnvironmentPath) {
    Write-Host "Preservando o ambiente anterior em $BackupPath"
    Move-Item -LiteralPath $EnvironmentPath -Destination $BackupPath
}

$PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($PythonLauncher) {
    & py -3.14 -m venv $EnvironmentPath
    if ($LASTEXITCODE -ne 0) {
        & py -3 -m venv $EnvironmentPath
    }
} else {
    & python -m venv $EnvironmentPath
}

if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $EnvironmentPath "Scripts\python.exe"))) {
    throw "Não foi possível criar o ambiente Python. O ambiente anterior permanece em $BackupPath"
}

$EnvironmentPython = Join-Path $EnvironmentPath "Scripts\python.exe"
& $EnvironmentPython -m pip install --upgrade pip
& $EnvironmentPython -m pip install -r $RequirementsPath

$env:PYTHONPATH = $ProjectPath
& $EnvironmentPython -m pytest -q

Write-Host ""
Write-Host "Ambiente recriado e validado em $EnvironmentPath"
Write-Host "API:       .\.venv\Scripts\python.exe -m uvicorn investment_engine.api.app:app --host 127.0.0.1 --port 8000"
Write-Host "Interface: .\.venv\Scripts\python.exe -m streamlit run examples\streamlit_v15_integrated.py"
