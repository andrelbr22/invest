$ErrorActionPreference = "Stop"

$ProjectPath = $PSScriptRoot
$ProductionEnv = Join-Path $ProjectPath ".env.production"
$ComposeFile = Join-Path $ProjectPath "docker-compose.production.yml"
$BackupDirectory = Join-Path $ProjectPath "backups"
$BackupFile = Join-Path $BackupDirectory ("investment_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".sql")

if (-not (Test-Path -LiteralPath $ProductionEnv)) {
    throw ".env.production não foi encontrado."
}

New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
Set-Location -LiteralPath $ProjectPath

docker compose --env-file $ProductionEnv -f $ComposeFile exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | Set-Content -LiteralPath $BackupFile -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw "O backup do PostgreSQL falhou." }

Write-Host "Backup criado em $BackupFile"
