$ErrorActionPreference = "Stop"

$ProjectPath = $PSScriptRoot
$ProductionEnv = Join-Path $ProjectPath ".env.production"
$ProductionEnvExample = Join-Path $ProjectPath ".env.production.example"
$SecretsDirectory = Join-Path $ProjectPath "deployment\secrets"
$SecretsFile = Join-Path $SecretsDirectory "streamlit_secrets.toml"
$SecretsExample = Join-Path $SecretsDirectory "streamlit_secrets.toml.example"
$ComposeFile = Join-Path $ProjectPath "docker-compose.production.yml"

Set-Location -LiteralPath $ProjectPath

function New-RandomHex([int]$ByteCount) {
    $Bytes = New-Object byte[] $ByteCount
    $Generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $Generator.GetBytes($Bytes) } finally { $Generator.Dispose() }
    return -join ($Bytes | ForEach-Object { $_.ToString("x2") })
}

function New-RandomBase64([int]$ByteCount) {
    $Bytes = New-Object byte[] $ByteCount
    $Generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $Generator.GetBytes($Bytes) } finally { $Generator.Dispose() }
    return [Convert]::ToBase64String($Bytes)
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker nao foi encontrado. Instale e inicie o Docker antes de continuar."
}

if (-not (Test-Path -LiteralPath $ProductionEnv)) {
    $EnvironmentTemplate = Get-Content -LiteralPath $ProductionEnvExample -Raw
    $EnvironmentTemplate = $EnvironmentTemplate.Replace("TROQUE_POR_UMA_SENHA_LONGA_E_ALEATORIA", (New-RandomHex 32))
    Set-Content -LiteralPath $ProductionEnv -Value $EnvironmentTemplate -Encoding utf8
    Write-Host "Criado: .env.production, com senha PostgreSQL aleatoria. Preencha e-mail e dominio."
}

if (-not (Test-Path -LiteralPath $SecretsFile)) {
    New-Item -ItemType Directory -Force -Path $SecretsDirectory | Out-Null
    $SecretsTemplate = Get-Content -LiteralPath $SecretsExample -Raw
    $SecretsTemplate = $SecretsTemplate.Replace("GERE_UMA_CHAVE_ALEATORIA_LONGA", (New-RandomBase64 48))
    Set-Content -LiteralPath $SecretsFile -Value $SecretsTemplate -Encoding utf8
    Write-Host "Criado: deployment\secrets\streamlit_secrets.toml, com chave de cookie aleatoria. Preencha as credenciais OIDC."
}

$ProductionText = Get-Content -LiteralPath $ProductionEnv -Raw
$SecretsText = Get-Content -LiteralPath $SecretsFile -Raw
$Placeholders = @(
    "TROQUE_POR_UMA_SENHA_LONGA_E_ALEATORIA",
    "seu-email@gmail.com",
    "GERE_UMA_CHAVE_ALEATORIA_LONGA",
    "CLIENT_ID_DO_GOOGLE",
    "CLIENT_SECRET_DO_GOOGLE"
)
$Missing = $Placeholders | Where-Object { $ProductionText.Contains($_) -or $SecretsText.Contains($_) }
if ($Missing) {
    Write-Host ""
    Write-Warning "A configuracao ainda possui campos de exemplo:"
    $Missing | ForEach-Object { Write-Host " - $_" }
    Write-Host "Edite .env.production e deployment\secrets\streamlit_secrets.toml e execute novamente."
    exit 2
}

docker compose --env-file $ProductionEnv -f $ComposeFile config --quiet
if ($LASTEXITCODE -ne 0) { throw "A configuracao de producao e invalida." }

docker compose --env-file $ProductionEnv -f $ComposeFile build
if ($LASTEXITCODE -ne 0) { throw "A construcao dos conteineres falhou." }

Write-Host ""
Write-Host "Configuracao validada e imagens construidas."
Write-Host "Para iniciar: docker compose --env-file .env.production -f docker-compose.production.yml up -d"
