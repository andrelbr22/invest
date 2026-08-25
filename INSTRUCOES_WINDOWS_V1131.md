# Publicar a V1.13.1 no Windows

Execute somente o conteúdo de cada bloco, um comando por vez. Não copie `PS C:\...>` nem `ubuntu@...$`.

## 1. Abrir a pasta descompactada

```powershell
Set-Location "C:\Users\André\Documents\formacaoInvestidor_ie_v1131"
```

## 2. Validar

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

## 3. Publicar

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

## 4. Confirmar o GitHub

```powershell
Invoke-RestMethod -Uri "https://raw.githubusercontent.com/andrelbr22/invest/main/pyproject.toml"
```

O resultado deve conter `version = "0.14.1"`.

## 5. Configurar a devolução dos backtests — uma única vez

Entre na Oracle:

```powershell
ssh -i "$env:USERPROFILE\Downloads\ssh-key-2026-08-22.key" ubuntu@129.148.36.14
```

No terminal `ubuntu@...`, abra a pasta:

```bash
cd ~/invest
```

Gere uma credencial e copie o resultado para um local temporário seguro. Não envie a chave em conversa:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Abra o arquivo privado:

```bash
nano deployment/secrets/streamlit_secrets.toml
```

Antes de `[auth]`, acrescente esta linha, substituindo o texto pela chave gerada:

```toml
BACKTEST_CALLBACK_TOKEN = "COLE_A_CHAVE_GERADA"
```

Salve com `Ctrl+O`, confirme com `Enter` e saia com `Ctrl+X`.

No GitHub, abra o repositório `andrelbr22/invest` e siga:

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

- Nome: `BACKTEST_CALLBACK_TOKEN`
- Secret: cole exatamente a mesma chave gerada na Oracle.

## 6. Reiniciar o aplicativo

De volta ao terminal da Oracle:

```bash
sudo chown ubuntu:10001 deployment/secrets/streamlit_secrets.toml
```

```bash
chmod 640 deployment/secrets/streamlit_secrets.toml
```

```bash
docker compose -f docker-compose.oracle-micro.yml up -d --no-deps --force-recreate app
```

```bash
docker compose -f docker-compose.oracle-micro.yml ps
```

O `app` deve ficar `healthy`.

## 7. Teste controlado

No site, abra `Administração` → `Backtests oficiais`, selecione apenas `PETR4` e envie. O workflow deve passar pela etapa **Validar entrega segura dos resultados** e iniciar os cálculos.
