# Ativar a entrega segura dos backtests na Oracle

Faça isto somente depois de publicar a V1.12.0 no GitHub e a Oracle atualizar o código.

## 1. Gerar a credencial exclusiva

No terminal da Oracle:

```bash
cd ~/invest
```

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copie o resultado para um local temporário seguro. Não envie essa chave em conversa.

## 2. Guardar a mesma credencial na Oracle

```bash
nano deployment/secrets/streamlit_secrets.toml
```

Antes da seção `[auth]`, acrescente:

```toml
BACKTEST_CALLBACK_TOKEN = "COLE_A_CHAVE_GERADA"
```

Salve e feche o editor. Depois execute:

```bash
sudo chown ubuntu:10001 deployment/secrets/streamlit_secrets.toml
```

```bash
chmod 640 deployment/secrets/streamlit_secrets.toml
```

## 3. Guardar a mesma credencial no GitHub

No repositório `andrelbr22/invest`, abra:

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`.

Nome:

```text
BACKTEST_CALLBACK_TOKEN
```

Valor: a mesma chave gerada no passo 1.

Os Secrets antigos `DATABASE_URL` e `DATABASE_ADMIN_URL` não são mais usados pelo
workflow e podem ser removidos do GitHub depois que o novo teste for concluído.

## 4. Ativar somente a rota protegida no Caddy

No terminal da Oracle:

```bash
cd ~/invest
```

```bash
cp deployment/Caddyfile.oracle-micro.example deployment/Caddyfile.oracle-micro
```

```bash
docker compose -f docker-compose.oracle-micro.yml up -d --force-recreate app proxy
```

```bash
docker compose -f docker-compose.oracle-micro.yml ps
```

`app`, `postgres` e `proxy` devem aparecer ativos; o `app` deve ficar `healthy`.

## 5. Confirmar a proteção

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://formacaodoinvestidor.com.br/automation/backtests/jobs/start -H "Content-Type: application/json" -H "X-Backtest-Callback-Version: 1" -d '{}'
```

O resultado esperado é `401`. Isso confirma que a rota existe e rejeita quem não
possui a credencial.

## 6. Teste controlado

Entre em `Administração` → `Backtests manuais e catálogo oficial`, selecione
somente `PETR4` e clique em `Gerar backtests dos ativos selecionados`.

Use `Atualizar andamento`. O painel deve mostrar:

- 1 ativo processado;
- 100% recebido pela Oracle;
- situação `Concluído` ou `Concluído com falhas`;
- nenhum pedido duplicado ao clicar novamente enquanto houver lote ativo.
