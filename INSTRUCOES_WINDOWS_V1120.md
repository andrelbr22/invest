# Instalar e publicar a V1.12.0 no Windows

Execute uma linha por vez no PowerShell.

```powershell
cd "C:\Users\André\Documents\formacaoInvestidor_ie"
```

```powershell
$patchV1120 = "C:\Users\André\Documents\Codex\2026-08-22\referenced-chatgpt-conversation-this-is-an\outputs\Investment_Engine_V1.12.0_PATCH_FINAL.zip"
```

```powershell
Test-Path -LiteralPath $patchV1120
```

O resultado deve ser `True`.

```powershell
Expand-Archive -LiteralPath $patchV1120 -DestinationPath "." -Force
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

Depois que aparecer `PUBLICACAO CONCLUIDA`, aguarde a atualização automática
da Oracle e siga `ATIVAR_ENTREGA_SEGURA_BACKTESTS_V1120.md`.
