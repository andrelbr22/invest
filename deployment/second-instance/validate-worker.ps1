param(
    [Parameter(Mandatory = $true)][string]$PrivateDatabaseHost
)

$ErrorActionPreference = "Stop"
if ($PrivateDatabaseHost -in @("0.0.0.0", "127.0.0.1", "localhost")) {
    throw "Informe o IP privado real da primeira instância."
}

Write-Host "Validando arquivos da segunda instância..."
docker compose -f .\deployment\second-instance\docker-compose.worker.yml config --quiet
Write-Host "Configuração válida. Antes de iniciar, confirme a NSG e o firewall privado conforme o guia."

