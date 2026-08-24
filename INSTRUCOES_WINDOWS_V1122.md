# Publicar a V1.12.2 usando uma pasta limpa

Não publique a pasta `formacaoInvestidor_ie` atual: ela contém uma cópia antiga
duplicada dentro de `investment_engine`.

Execute uma linha por vez no PowerShell.

```powershell
$newFolderV1122 = "$env:USERPROFILE\Documents\formacaoInvestidor_ie_v1122"
```

```powershell
Test-Path -LiteralPath $newFolderV1122
```

O resultado deve ser `False`. Em seguida:

```powershell
New-Item -ItemType Directory -Path $newFolderV1122
```

```powershell
$fullV1122 = "C:\Users\André\Documents\Codex\2026-08-22\referenced-chatgpt-conversation-this-is-an\outputs\investment-engine-oracle-v1.12.2-full-final.zip"
```

```powershell
Test-Path -LiteralPath $fullV1122
```

O resultado deve ser `True`. Depois:

```powershell
Expand-Archive -LiteralPath $fullV1122 -DestinationPath $newFolderV1122
```

```powershell
cd $newFolderV1122
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

Após `PUBLICACAO CONCLUIDA`, aguarde o temporizador da Oracle aplicar a versão.
