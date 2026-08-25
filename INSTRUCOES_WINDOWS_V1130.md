# Publicar a V1.13.0 no Windows

Copie e execute **um comando por vez** no PowerShell. Não copie o texto `PS C:\...>` que aparece antes do cursor.

## 1. Abrir a pasta descompactada

```powershell
Set-Location "C:\Users\André\Documents\formacaoInvestidor_ie_v1130"
```

## 2. Validar antes de publicar

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

O resultado correto é: `Pacote validado. Nenhum arquivo foi enviado.`

## 3. Publicar no GitHub

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

## 4. Confirmar a versão publicada

```powershell
Invoke-RestMethod -Uri "https://raw.githubusercontent.com/andrelbr22/invest/main/pyproject.toml"
```

O arquivo deve mostrar `version = "0.14.0"`.

## 5. Se quiser antecipar a atualização automática da Oracle

```powershell
ssh -i "$env:USERPROFILE\Downloads\ssh-key-2026-08-22.key" ubuntu@129.148.36.14
```

Depois que o prompt mudar para `ubuntu@...`, execute:

```bash
cd ~/invest
```

```bash
sudo systemctl start investment-github-update.service
```

```bash
systemctl show investment-github-update.service -p Result -p ExecMainStatus
```

O resultado esperado é `Result=success` e `ExecMainStatus=0`.

```bash
cat investment_engine/__init__.py
```

O resultado esperado é `__version__ = "0.14.0"`.
