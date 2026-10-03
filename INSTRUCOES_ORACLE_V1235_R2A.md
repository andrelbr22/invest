# Instruções Oracle • V1.23.5 R2A

Esta revisão corrige exclusivamente a coordenação operacional da R2. Pare no
primeiro resultado diferente e envie a saída antes de continuar. PowerShell é
usado no Windows; comandos `cd ~/invest` são usados somente no Ubuntu da Oracle.

## 1. Windows — validar e publicar no ambiente de teste

Extraia o ZIP em uma pasta nova, abra o PowerShell nessa pasta e execute:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

Esperado: `Pacote validado. Nenhum arquivo foi enviado.`

Após autorização explícita:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

Esperado: `PUBLICACAO CONCLUIDA` e orientação para validar a V1.23.5 R2A em
`/testefdi`.

## 2. Ubuntu — atualizar somente o staging

```bash
cd ~/invest
```

```bash
./deployment/update-staging-from-github.sh
```

Não repita enquanto houver atualização, cópia ou migração em andamento.
Esperado: `Teste atualizado: https://formacaodoinvestidor.com.br/testefdi/`.

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Esperado: versão `1.23.5`, ambiente `staging`, banco `reachable`, migração
`0030_v1_23_navigation_metrics` e `HTTP 200`.

## 3. Regressão completa

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 tests_v1230 tests_v1231 tests_v1232 tests_v1233 tests_v1234 tests_v1235 -q -p no:cacheprovider
```

Esperado: todos os testes aprovados. Avisos de depreciação conhecidos não são
falhas.

## 4. Materialização e desempenho

```bash
STAGING_COMMIT="$(cat .git/investment-staging-commit)"; printf 'Commit do staging: %s\n' "$STAGING_COMMIT"
```

```bash
[[ "$STAGING_COMMIT" =~ ^[0-9a-f]{40}$ ]] && echo "Marcador válido." || { echo "Marcador inválido; não prossiga." >&2; false; }
```

A interpolação direta da consulta seguinte só é segura porque o marcador foi
restrito a 40 caracteres hexadecimais:

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine_staging -c "SELECT status, result_json->>'status' AS resultado, result_json->>'remaining' AS restantes, jsonb_array_length(COALESCE(result_json::jsonb #> '{navigation,errors}', '[]'::jsonb)) AS erros_navegacao, updated_at FROM background_jobs WHERE job_type='current_metrics_refresh' AND (payload_json::jsonb->>'cycle')='release:${STAGING_COMMIT}' ORDER BY created_at;"
```

Todas as linhas devem terminar em `succeeded`; a última deve indicar
`complete`, zero restante e zero erro de navegação.

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.benchmark_application_routes --samples 20 --warmup 2
```

Esperado: `OK` em todas as rotas. Não promova com `ACIMA_DA_META`.

Faça também a homologação visual completa descrita em
`INSTRUCOES_ORACLE_V1235_R2.md`, incluindo painéis, filtros, valorações,
backtests, carteira, login e Administração.

## 5. Promoção autorizada

Antes de iniciar, confirme que não há outra promoção:

```bash
pgrep -af 'promote-staging-to-production|production-migration|pg_dump|oci.*object.*put' || echo "Nenhuma promoção em andamento."
```

Se houver processo ativo, não inicie outro. Caso contrário, crie um log único:

```bash
PROMOTION_LOG="$(mktemp /tmp/promocao-v1235-r2a.XXXXXX.log)"; printf 'Log da promoção: %s\n' "$PROMOTION_LOG"
```

```bash
nohup ./deployment/promote-staging-to-production.sh >> "$PROMOTION_LOG" 2>&1 & echo "PID da promoção: $!"
```

```bash
tail -f "$PROMOTION_LOG"
```

O `>>` é intencional: mesmo se uma segunda tentativa for recusada pela trava,
ela não trunca o log ativo. Saia do acompanhamento com `Ctrl+C` somente depois
da mensagem final de sucesso.

## 6. Verificação final

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/ready
```

Esperado: versão `1.23.5`, ambiente `production`, migração
`0030_v1_23_navigation_metrics` e `HTTP 200`.

```bash
docker compose -f docker-compose.oracle-web.yml ps
```

Aplicação, PostgreSQL e worker devem estar saudáveis. O staging pode estar
parado por isolamento de recursos.

```bash
docker compose -f docker-compose.oracle-web.yml logs --since 20m app worker | grep -Ei "error|traceback|exception|background_job_failed|unhealthy" || echo "Nenhum erro encontrado na produção."
```

Esperado: `Nenhum erro encontrado na produção.`

## 7. Segunda VM

A R2A melhora a validação local e remota, mas não cria a segunda VM nem altera
NSG, IP privado ou chave SSH. O corte continua separado e deve seguir
`INSTRUCOES_SEGUNDA_VM_V1232.md`, com preflight, autorização explícita e teste
de retorno para a VM principal.
