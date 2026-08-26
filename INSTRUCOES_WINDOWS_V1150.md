# Publicar a V1.15.0

Execute cada bloco separadamente no PowerShell do Windows.

```powershell
New-Item -ItemType Directory -Path "C:\Users\André\Documents\formacaoInvestidor_ie_v1150" -Force
```

```powershell
Expand-Archive -LiteralPath "C:\Users\André\Documents\Codex\2026-08-22\referenced-chatgpt-conversation-this-is-an\outputs\investment-engine-oracle-v1.15.0-full-final.zip" -DestinationPath "C:\Users\André\Documents\formacaoInvestidor_ie_v1150" -Force
```

```powershell
Set-Location "C:\Users\André\Documents\formacaoInvestidor_ie_v1150"
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

O servidor Oracle buscará a atualização automaticamente. Não há migração de banco.
