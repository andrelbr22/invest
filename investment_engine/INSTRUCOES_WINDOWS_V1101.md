# Atualizar para a V1.10.1 no Windows

Baixe `Investment_Engine_V1.10.1_PATCH.zip`. Abra o PowerShell e execute cada comando separadamente.

## Entrar na pasta do projeto

```powershell
cd "C:\Users\André\Documents\formacaoInvestidor_ie"
```

## Localizar o patch baixado

```powershell
$patchV1101 = "$env:USERPROFILE\Downloads\Investment_Engine_V1.10.1_PATCH.zip"
```

```powershell
Test-Path -LiteralPath $patchV1101
```

O resultado deve ser `True`.

## Aplicar o patch

```powershell
Expand-Archive -LiteralPath $patchV1101 -DestinationPath "C:\Users\André\Documents\formacaoInvestidor_ie" -Force
```

## Conferir a versão

```powershell
Select-String -Path .\pyproject.toml -Pattern 'version ='
```

O resultado deve conter `0.11.1`.

## Validar

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

## Publicar

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

Depois configure uma única vez o token descrito em `CONFIGURAR_GITHUB_BACKTESTS.md`.
