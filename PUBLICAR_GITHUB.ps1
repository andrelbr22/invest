param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$sourceRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$repositoryUrl = "https://github.com/andrelbr22/invest.git"
$repositoryName = "andrelbr22/invest"
$backupBranch = "backup-versao-anterior"

function Stop-Publication([string]$message) {
    Write-Host ""
    Write-Host "PUBLICACAO INTERROMPIDA: $message" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot "app.py"))) {
    Stop-Publication "app.py nao foi encontrado na pasta extraida."
}
if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot "requirements.txt"))) {
    Stop-Publication "requirements.txt nao foi encontrado na pasta extraida."
}
if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot "investment_engine"))) {
    Stop-Publication "a pasta investment_engine nao foi encontrada."
}

$packageRoot = Join-Path $sourceRoot "investment_engine"
$nestedProjectIndicators = @(
    (Join-Path $packageRoot "app.py"),
    (Join-Path $packageRoot "requirements.txt"),
    (Join-Path $packageRoot "pyproject.toml"),
    (Join-Path $packageRoot ".github")
) | Where-Object { Test-Path -LiteralPath $_ }
if ($nestedProjectIndicators) {
    Stop-Publication "foi encontrada uma copia completa do projeto dentro da pasta investment_engine. Use o pacote completo em uma pasta nova e limpa."
}

$forbiddenDirectories = Get-ChildItem -LiteralPath $sourceRoot -Directory -Recurse -Force |
    Where-Object { $_.Name -in @(".git", ".venv", "__pycache__") }
if ($forbiddenDirectories) {
    Stop-Publication "a pasta contem arquivos internos que nao devem ser publicados. Extraia novamente o ZIP oficial."
}

$sensitiveFiles = Get-ChildItem -LiteralPath $sourceRoot -File -Recurse -Force |
    Where-Object {
        ($_.Name -in @(".env", ".env.production", "secrets.toml")) -or
        ($_.Extension -in @(".key", ".pem", ".pfx", ".p12"))
    }
if ($sensitiveFiles) {
    Stop-Publication "foi encontrado um arquivo de senha ou chave. Nenhum arquivo foi enviado."
}

$gitCommand = Get-Command git -ErrorAction SilentlyContinue
if ($gitCommand) {
    $gitPath = $gitCommand.Source
} else {
    $bundledGit = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe"
    if (-not (Test-Path -LiteralPath $bundledGit)) {
        Stop-Publication "Git nao foi encontrado neste computador."
    }
    $gitPath = $bundledGit
}

if ($ValidateOnly) {
    Write-Host "Pacote validado. Nenhum arquivo foi enviado." -ForegroundColor Green
    exit 0
}

& $gitPath credential-manager configure | Out-Null

$publicationRoot = Join-Path ([IO.Path]::GetTempPath()) ("investment-engine-publicacao-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $publicationRoot | Out-Null

Write-Host "Preparando uma copia temporaria segura do repositorio..."
& $gitPath clone $repositoryUrl $publicationRoot
if ($LASTEXITCODE -ne 0) {
    Stop-Publication "nao foi possivel acessar $repositoryName. Conclua o login do GitHub e tente novamente."
}

Push-Location $publicationRoot
try {
    & $gitPath switch main
    if ($LASTEXITCODE -ne 0) {
        Stop-Publication "a branch main nao foi encontrada."
    }

    & $gitPath ls-remote --exit-code --heads origin $backupBranch | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Stop-Publication "o backup $backupBranch nao foi localizado no GitHub."
    }

    & $gitPath rm -r --quiet .
    if ($LASTEXITCODE -ne 0) {
        Stop-Publication "nao foi possivel preparar a substituicao dos arquivos."
    }

    Get-ChildItem -LiteralPath $sourceRoot -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $publicationRoot $_.Name) -Recurse -Force
    }

    & $gitPath add --all
    if ($LASTEXITCODE -ne 0) {
        Stop-Publication "nao foi possivel preparar os novos arquivos."
    }

    $configuredName = & $gitPath config user.name
    if (-not $configuredName) {
        & $gitPath config user.name "andrelbr22"
    }
    $configuredEmail = & $gitPath config user.email
    if (-not $configuredEmail) {
        & $gitPath config user.email "andrelbr22@users.noreply.github.com"
    }

    & $gitPath diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "A pasta ja corresponde a versao publicada. Nenhum arquivo precisava ser enviado." -ForegroundColor Green
        return
    }

    & $gitPath commit -m "Publica Investment Engine V1.15.0 com painel SaaS e desempenho otimizado"
    if ($LASTEXITCODE -ne 0) {
        Stop-Publication "nao foi possivel criar a atualizacao local."
    }

    Write-Host "Enviando a nova versao ao GitHub..."
    & $gitPath push origin main
    if ($LASTEXITCODE -ne 0) {
        Stop-Publication "o GitHub recusou o envio. Verifique o login e tente novamente."
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "PUBLICACAO CONCLUIDA." -ForegroundColor Green
Write-Host "O servidor Oracle iniciara a atualizacao automaticamente."
