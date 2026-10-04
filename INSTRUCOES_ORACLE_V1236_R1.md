# Instruções Oracle — V1.23.6 R1

Execute os blocos na plataforma indicada. Não misture comandos PowerShell com
o terminal Ubuntu.

## 1. Windows PowerShell — validar e publicar

Na pasta extraída do pacote:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

Resultado esperado: `Pacote validado. Nenhum arquivo foi enviado.`

Após aprovação explícita da publicação em teste:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

Resultado esperado: orientação para validar a V1.23.6 R1 em `/testefdi`.

## 2. Ubuntu — atualizar staging

```bash
cd ~/invest
```

```bash
./deployment/update-staging-from-github.sh
```

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Resultado esperado: versão `1.23.6`, ambiente `staging`, banco `reachable`,
migração `0030_v1_23_navigation_metrics` e HTTP 200.

## 3. Testes oficiais

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 tests_v1230 tests_v1231 tests_v1232 tests_v1233 tests_v1234 tests_v1235 tests_v1236 -q -p no:cacheprovider
```

Resultado esperado: todos os testes aprovados; avisos de depreciação não são
falhas.

## 4. Desempenho

Gate aquecido usado pela promoção:

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.benchmark_application_routes --samples 20 --warmup 2
```

Diagnóstico frio e ampliado:

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.benchmark_application_routes --samples 10 --warmup 1 --cold --extended
```

O primeiro comando deve mostrar `OK` em todas as rotas. O segundo registra o
custo real sem cache local e inclui ETF/screener avançado; envie o resultado se
algum painel exceder a meta.

## 5. Validação visual e logs

Teste as áreas listadas no relatório e depois execute:

```bash
docker compose -f docker-compose.oracle-web.yml logs --since 30m staging | grep -Ei "error|traceback|exception|background_job_failed|unhealthy" || echo "Nenhum erro encontrado no staging."
```

Somente após todos os itens e nova aprovação explícita, execute a promoção em
segundo plano conforme o procedimento operacional já vigente.
