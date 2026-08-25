# Publicar a V1.14.1

Execute cada comando separadamente no PowerShell do Windows.

```powershell
New-Item -ItemType Directory -Path "C:\Users\André\Documents\formacaoInvestidor_ie_v1141" -Force
```

```powershell
Expand-Archive -LiteralPath "C:\Users\André\Documents\Codex\2026-08-22\referenced-chatgpt-conversation-this-is-an\outputs\investment-engine-oracle-v1.14.1-full-final.zip" -DestinationPath "C:\Users\André\Documents\formacaoInvestidor_ie_v1141" -Force
```

```powershell
Set-Location "C:\Users\André\Documents\formacaoInvestidor_ie_v1141"
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

O servidor Oracle buscará a nova versão automaticamente. A atualização não altera banco, senhas, OAuth nem configuração de e-mail.

Se um navegador ainda tentar abrir a hospedagem antiga, teste primeiro uma janela anônima. Isso confirma e contorna um redirecionamento permanente guardado no cache local.
