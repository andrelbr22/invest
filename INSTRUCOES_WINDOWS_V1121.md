# Instalar e publicar a V1.12.1 no Windows

Execute uma linha por vez no PowerShell.

```powershell
cd "C:\Users\André\Documents\formacaoInvestidor_ie"
```

```powershell
$patchV1121 = "C:\Users\André\Documents\Codex\2026-08-22\referenced-chatgpt-conversation-this-is-an\outputs\Investment_Engine_V1.12.1_PATCH_FINAL.zip"
```

```powershell
Test-Path -LiteralPath $patchV1121
```

O resultado deve ser `True`.

```powershell
Expand-Archive -LiteralPath $patchV1121 -DestinationPath "." -Force
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

Depois que aparecer `PUBLICACAO CONCLUIDA`, aguarde a atualização automática
da Oracle. Se a entrega segura da V1.12.0 ainda não tiver sido ativada, siga o
arquivo `ATIVAR_ENTREGA_SEGURA_BACKTESTS_V1120.md` antes de iniciar um novo
lote oficial.
