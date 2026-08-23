# Atualizar para a V1.10.3 no Windows

Execute cada comando separadamente no PowerShell.

```powershell
cd "C:\Users\André\Documents\formacaoInvestidor_ie"
```

```powershell
$patchV1103 = "C:\Users\André\Documents\Codex\2026-08-22\referenced-chatgpt-conversation-this-is-an\outputs\Investment_Engine_V1.10.3_PATCH.zip"
```

```powershell
Test-Path -LiteralPath $patchV1103
```

O resultado deve ser `True`.

```powershell
Expand-Archive -LiteralPath $patchV1103 -DestinationPath "C:\Users\André\Documents\formacaoInvestidor_ie" -Force
```

```powershell
Select-String -Path .\pyproject.toml -Pattern 'version ='
```

O resultado deve conter `0.11.3`.

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

Depois da publicação, siga `CORRIGIR_SECRET_GITHUB_V1103.md` para substituir o valor incorreto de `DATABASE_ADMIN_URL` no GitHub.
