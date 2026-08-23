# Atualizar para a V1.10.4 no Windows

Execute cada comando separadamente no PowerShell.

```powershell
cd "C:\Users\André\Documents\formacaoInvestidor_ie"
```

```powershell
$patchV1104 = "C:\Users\André\Documents\Codex\2026-08-22\referenced-chatgpt-conversation-this-is-an\outputs\Investment_Engine_V1.10.4_PATCH.zip"
```

```powershell
Test-Path -LiteralPath $patchV1104
```

O resultado deve ser `True`.

```powershell
Expand-Archive -LiteralPath $patchV1104 -DestinationPath "C:\Users\André\Documents\formacaoInvestidor_ie" -Force
```

```powershell
Select-String -Path .\pyproject.toml -Pattern 'version ='
```

O resultado deve conter `0.11.4`.

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```
