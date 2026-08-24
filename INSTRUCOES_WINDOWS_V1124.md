# Publicar a V1.12.4

Esta versão corrige o título escondido pela barra superior e não exige migração
de banco de dados.

## Instalação recomendada em uma pasta nova

Execute uma linha por vez no PowerShell:

```powershell
$pacoteV1124 = "C:\Users\André\Documents\Codex\2026-08-22\referenced-chatgpt-conversation-this-is-an\outputs\investment-engine-oracle-v1.12.4-full-final.zip"
```

```powershell
$destinoV1124 = "C:\Users\André\Documents\formacaoInvestidor_ie_v1124"
```

```powershell
New-Item -ItemType Directory -Path $destinoV1124 -Force
```

```powershell
Expand-Archive -LiteralPath $pacoteV1124 -DestinationPath $destinoV1124 -Force
```

```powershell
Set-Location $destinoV1124
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

O servidor Oracle buscará a nova versão automaticamente. Os segredos e o
PostgreSQL local permanecem preservados.
