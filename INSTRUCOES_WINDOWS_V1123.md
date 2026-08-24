# Publicar a V1.12.3 compacta

Use uma pasta nova para não misturar arquivos de versões anteriores.

## No PowerShell do Windows

```powershell
exit
```

Use `exit` somente se o terminal ainda estiver conectado ao Ubuntu.

```powershell
$fullV1123 = "C:\Users\André\Documents\Codex\2026-08-22\referenced-chatgpt-conversation-this-is-an\outputs\investment-engine-oracle-v1.12.3-full-final.zip"
```

```powershell
$destinoV1123 = "C:\Users\André\Documents\formacaoInvestidor_ie_v1123"
```

```powershell
New-Item -ItemType Directory -Path $destinoV1123 -Force
```

```powershell
Expand-Archive -LiteralPath $fullV1123 -DestinationPath $destinoV1123 -Force
```

```powershell
Set-Location $destinoV1123
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

Depois da mensagem `PUBLICACAO CONCLUIDA`, faça a correção única do atualizador
Oracle conforme as orientações fornecidas no atendimento. As credenciais, o
banco, o Compose ativo e o Caddy ativo não serão substituídos.
