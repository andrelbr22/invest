# Atualizar para a V1.11.1 no Windows

Execute cada comando separadamente no PowerShell.

## 1. Entrar na pasta do projeto

```powershell
cd "C:\Users\André\Documents\formacaoInvestidor_ie"
```

## 2. Informar o caminho exato do patch

```powershell
$patchV1111 = "CAMINHO_EXATO_DO_ARQUIVO\Investment_Engine_V1.11.1_PATCH_FINAL.zip"
```

## 3. Confirmar o arquivo

```powershell
Test-Path -LiteralPath $patchV1111
```

O resultado precisa ser `True`.

## 4. Aplicar a atualização

```powershell
Expand-Archive -LiteralPath $patchV1111 -DestinationPath "." -Force
```

## 5. Validar

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

## 6. Publicar

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

O servidor Oracle atualizará o aplicativo automaticamente. Não é necessário alterar o PostgreSQL.
