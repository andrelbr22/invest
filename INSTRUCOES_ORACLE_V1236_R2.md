# Instruções Oracle — V1.23.6 R2

Execute cada bloco na plataforma indicada. Não misture comandos do Windows
PowerShell com os do terminal Ubuntu.

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

Resultado esperado: orientação para validar a V1.23.6 R2 em `/testefdi`.

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

## 3. Cobertura materializada

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.check_navigation_coverage
```

Resultado esperado: os quatro totais devem ser iguais e a última linha deve
ser `navigation coverage ok`. Se houver diferença, aguarde o trabalho
`current_metrics_refresh`; não promova.

## 4. Testes oficiais

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 tests_v1230 tests_v1231 tests_v1232 tests_v1233 tests_v1234 tests_v1235 tests_v1236 -q -p no:cacheprovider
```

Resultado esperado: todos os testes aprovados. Avisos de depreciação não são
falhas.

## 5. Desempenho

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.benchmark_application_routes --samples 20 --warmup 2
```

Todas as rotas devem terminar com `OK`.

## 6. Homologação visual e logs

Alterne entre os painéis e retorne a cada um; a resposta anterior deve aparecer
sem nova espera longa. Em seguida, use os botões de atualização de Mercado,
Notícias e Administração e confirme que a leitura realmente muda.

```bash
docker compose -f docker-compose.oracle-web.yml logs --since 30m staging | grep -Ei "error|traceback|exception|background_job_failed|unhealthy" || echo "Nenhum erro encontrado no staging."
```

Somente depois da homologação e de nova aprovação explícita execute a
promoção para produção pelo procedimento operacional vigente.
