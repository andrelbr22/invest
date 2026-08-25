# Publicar a V1.12.5

Use o pacote completo em uma pasta nova. Execute **uma linha por vez** no PowerShell.

```powershell
$pacoteV1125 = "C:\Users\André\Documents\Codex\2026-08-22\referenced-chatgpt-conversation-this-is-an\outputs\investment-engine-oracle-v1.12.5-full-final.zip"
```

```powershell
$destinoV1125 = "C:\Users\André\Documents\formacaoInvestidor_ie_v1125"
```

```powershell
New-Item -ItemType Directory -Path $destinoV1125 -Force
```

```powershell
Expand-Archive -LiteralPath $pacoteV1125 -DestinationPath $destinoV1125 -Force
```

```powershell
Set-Location $destinoV1125
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

O servidor Oracle buscará a versão automaticamente. Na inicialização, o Alembic cria o cache diário de notícias. Os segredos e o PostgreSQL local permanecem preservados.
