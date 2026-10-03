# Instruções Oracle • V1.23.5 R2

Esta versão reduz o tempo percebido de navegação sem retirar recursos que já
funcionam. Ela mantém os históricos como fonte oficial e acrescenta uma
projeção reconstruível com valorações e os três melhores backtests por ativo.

Pare no primeiro resultado diferente e envie a saída antes de prosseguir.
Comandos PowerShell pertencem ao Windows. Comandos `cd ~/invest` pertencem ao
terminal Ubuntu da Oracle.

## 1. Windows — validar e publicar o pacote

Depois de extrair o ZIP oficial em uma pasta nova e limpa, abra o PowerShell
nessa pasta e execute:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

Resultado esperado: `Pacote validado. Nenhum arquivo foi enviado.`

Após a autorização explícita para publicar no ambiente de teste:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

O resultado final deve informar `PUBLICACAO CONCLUIDA` e pedir a validação da
V1.23.5 R2 em `/testefdi`. O timer seguro de staging pode permanecer ativo;
ele já chama somente `update-staging-from-github.sh` e não promove a produção.

## 2. Ubuntu — atualizar somente o ambiente de teste

Conecte-se à Oracle, entre no projeto e atualize o staging:

```bash
cd ~/invest
```

```bash
./deployment/update-staging-from-github.sh
```

O processo pode demorar durante a cópia isolada do banco. Não o repita enquanto
`pg_dump`, `psql` ou o próprio atualizador estiverem ativos. O resultado final
esperado é `Teste atualizado: https://formacaodoinvestidor.com.br/testefdi/`.

Confirme a prontidão:

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Resultado esperado: versão `1.23.5`, ambiente `staging`, banco `reachable`,
migração `0030_v1_23_navigation_metrics` e `HTTP 200`.

## 3. Regressão completa

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 tests_v1230 tests_v1231 tests_v1232 tests_v1233 tests_v1234 tests_v1235 -q -p no:cacheprovider
```

Resultado esperado: todos os testes aprovados; avisos de depreciação conhecidos
não representam falha.

## 4. Acompanhar a materialização

O worker do staging preenche as projeções em lotes. Primeiro capture o commit
exato homologado:

```bash
STAGING_COMMIT="$(cat .git/investment-staging-commit)"; printf 'Commit do staging: %s\n' "$STAGING_COMMIT"
```

O resultado deve ser um identificador hexadecimal com 40 caracteres. Valide o
marcador antes de usá-lo na consulta:

```bash
[[ "$STAGING_COMMIT" =~ ^[0-9a-f]{40}$ ]] && echo "Marcador válido." || { echo "Marcador inválido; não prossiga." >&2; false; }
```

Consulte somente os trabalhos desse ciclo. A interpolação direta abaixo é
segura porque o comando anterior restringe o valor a exatamente 40 caracteres
hexadecimais:

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine_staging -c "SELECT status, result_json->>'status' AS resultado, result_json->>'remaining' AS restantes, jsonb_array_length(COALESCE(result_json::jsonb #> '{navigation,errors}', '[]'::jsonb)) AS erros_navegacao, updated_at FROM background_jobs WHERE job_type='current_metrics_refresh' AND (payload_json::jsonb->>'cycle')='release:${STAGING_COMMIT}' ORDER BY created_at;"
```

Espere a fila terminar. Todas as linhas do ciclo devem ficar `succeeded`; a
última deve indicar `resultado=complete`, `restantes=0` e
`erros_navegacao=0`. Se houver `failed`, `running` antigo ou erro de navegação,
não promova.

Confira a cobertura:

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine_staging -c "SELECT COUNT(*) FILTER (WHERE a.is_active IS TRUE) AS ativos_ativos, COUNT(m.asset_id) FILTER (WHERE a.is_active IS TRUE) AS metricas_atuais, COUNT(m.asset_id) FILTER (WHERE a.is_active IS TRUE AND COALESCE(m.technical_features_json::jsonb, '{}'::jsonb) <> '{}'::jsonb) AS tecnicos_precalculados, COUNT(m.asset_id) FILTER (WHERE a.is_active IS TRUE AND m.valuation_calculated_at IS NOT NULL) AS valoracoes_processadas, COUNT(m.asset_id) FILTER (WHERE a.is_active IS TRUE AND m.backtest_leaders_calculated_at IS NOT NULL) AS podios_processados FROM assets a LEFT JOIN asset_current_metrics m ON m.asset_id=a.id;"
```

`métricas_atuais`, `valorações_processadas` e `pódios_processados` devem alcançar
os ativos ativos ao fim do ciclo. Uma valoração explícita N/D e um pódio vazio
são coberturas válidas e impedem consultas históricas repetidas.
`técnicos_precalculados` é apenas diagnóstico e pode ser menor em ativos sem
histórico suficiente.

## 5. Desempenho obrigatório

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.benchmark_application_routes --samples 20 --warmup 2
```

Resultado esperado: `OK` em health, dashboard, screener 50, screener 100 e
detalhe do ativo. Não promova se aparecer `ACIMA_DA_META`.

## 6. Homologação visual

Em `https://formacaodoinvestidor.com.br/testefdi/`, confira:

- Dashboard, Mercado e Análises, Carteira, Backtests, Alertas, Notícias e Administração;
- listas principais visíveis antes dos dados secundários de backtest;
- Preço-teto DY, Valor relativo e três estratégias distintas quando houver dados;
- alternância rápida entre abas sem erro falso nem resultado da tela anterior;
- detalhe de ações, FIIs, ETFs, BDRs e futuros;
- filtros Padrão, FDI e ALB e configurações exclusivas do proprietário;
- login Google e código por e-mail, portal, livros e links de venda;
- tempos reais no painel Administração > Operação.

## 7. Promoção autorizada

Somente após aprovação explícita, execute no Ubuntu:

```bash
cd ~/invest
```

```bash
PROMOTION_LOG="$(mktemp /tmp/promocao-v1235-r2.XXXXXX.log)"; printf 'Log da promoção: %s\n' "$PROMOTION_LOG"
```

```bash
nohup ./deployment/promote-staging-to-production.sh >> "$PROMOTION_LOG" 2>&1 & echo "PID da promoção: $!"
```

Acompanhe sem depender da conexão SSH. O uso de `>>` é intencional: uma
segunda tentativa recusada pela trava não apaga o log da promoção ativa.

```bash
tail -f "$PROMOTION_LOG"
```

Saia do acompanhamento com `Ctrl+C` somente depois da mensagem final. O script
faz benchmark, backup, migração isolada, troca da aplicação e validação do
worker. O resultado esperado é `Produção, proxy e rotinas automáticas
atualizados após aprovação manual.` ou a variante que confirma o worker remoto.

Para reservar recursos à produção, o staging fica parado e com reinício
automático desativado depois da promoção. Isso é intencional; a próxima chamada
de `update-staging-from-github.sh` o reativa automaticamente.

## 8. Verificação final da produção

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/ready
```

Resultado esperado: versão `1.23.5`, ambiente `production`, migração
`0030_v1_23_navigation_metrics` e `HTTP 200`.

```bash
docker compose -f docker-compose.oracle-web.yml ps
```

Aplicação, PostgreSQL e worker devem estar saudáveis. O staging pode aparecer
parado por decisão de isolamento de recursos.

```bash
docker compose -f docker-compose.oracle-web.yml logs --since 20m app worker | grep -Ei "error|traceback|exception|background_job_failed|unhealthy" || echo "Nenhum erro encontrado na produção."
```

Resultado esperado: `Nenhum erro encontrado na produção.`

## 9. Segunda VM — etapa separada e controlada

Este pacote prepara, valida e protege o corte do worker, mas não cria a VM nem
altera regras da OCI sozinho. A criação da segunda VM, IPs privados, NSG e chave
SSH continuam exigindo dados reais da conta e autorização operacional.

Depois de preencher os arquivos privados conforme
`INSTRUCOES_SEGUNDA_VM_V1232.md`, execute na VM principal:

```bash
./deployment/second-instance/preflight-cutover.sh
```

Resultado esperado: pré-validação concluída sem iniciar outro consumidor.

Depois de revisar o resultado e autorizar o corte:

```bash
./deployment/second-instance/cutover-worker.sh
```

Resultado esperado: um único worker remoto, um único scheduler e um único
monitor de alertas confirmados.

Comprove a topologia:

```bash
./deployment/second-instance/worker-topology-status.sh
```

Para testar ou executar o retorno seguro à VM principal:

```bash
./deployment/second-instance/failback-worker.sh
```

O worker local só é iniciado depois de o remoto estar comprovadamente inativo.
O retorno automático é opt-in e permanece desativado até decisão posterior.
