# Instruções Oracle — V1.23.8 R2

Pare no primeiro resultado diferente. Execute comandos PowerShell somente no
Windows e comandos `ubuntu@...` somente depois de entrar por SSH.

## Fase 1 — publicar e homologar o código com o worker ainda local

No Windows, extraia o ZIP em uma pasta nova, valide e publique:

```powershell
Set-Location "C:\PASTA_NOVA_DA_V1238_R2"
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

Na VM principal:

```bash
cd ~/invest
./deployment/update-staging-from-github.sh
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Execute a suíte oficial, a cobertura, o benchmark e a linha de base:

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 tests_v1230 tests_v1231 tests_v1232 tests_v1233 tests_v1234 tests_v1235 tests_v1236 tests_v1237 tests_v1238 -q -p no:cacheprovider
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.check_navigation_coverage
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.benchmark_application_routes --samples 20 --warmup 2
./deployment/capture-performance-baseline.sh staging
```

Depois da homologação visual e da aprovação explícita, promova normalmente. A
produção deve continuar com o worker local nessa primeira fase.

## Fase 2 — preparar a VM2 sem iniciar outro consumidor

Crie a VM2 gratuita na mesma VCN. Mantenha um único PostgreSQL, na VM1. Na NSG,
autorize TCP 5432 na VM1 somente a partir do IP privado da VM2/32. Não abra
5432 para `0.0.0.0/0` nem para o IP público.

Na VM1, preencha os arquivos runtime a partir dos exemplos e confirme modos
0600. Depois crie a função exclusiva e publique o banco apenas no IP privado:

```bash
cd ~/invest
cp deployment/runtime/worker-location.env.example deployment/runtime/worker-location.env
cp deployment/runtime/primary-db.env.example deployment/runtime/primary-db.env
chmod 600 deployment/runtime/worker-location.env deployment/runtime/primary-db.env
./deployment/second-instance/create-worker-db-role.sh
./deployment/second-instance/enable-primary-private-db.sh
```

Na VM2, use o mesmo repositório e o commit registrado em
`.git/investment-production-commit`. Crie `worker.env` e
`worker_secrets.toml` a partir dos exemplos, com IP privado da VM1 e a função
`investment_worker`. Então prepare sem iniciar o worker:

```bash
cd ~/invest
cp deployment/second-instance/worker.env.example deployment/second-instance/worker.env
cp deployment/second-instance/worker_secrets.toml.example deployment/second-instance/worker_secrets.toml
chmod 600 deployment/second-instance/worker.env
sudo chown "$(id -un)":10001 deployment/second-instance/worker_secrets.toml
chmod 640 deployment/second-instance/worker_secrets.toml
./deployment/second-instance/prepare-worker.sh "$(cat .git/investment-production-commit)"
```

## Fase 3 — ensaiar retorno manual e automático

Comece com o worker local saudável. Na VM1, execute primeiro o ciclo manual e
termine local:

```bash
cd ~/invest
FDI_WORKER_DRILL_APPROVED=V1.23.8-R2 ./deployment/second-instance/run-worker-resilience-drill.sh manual local
```

Depois execute o ciclo automático e termine remoto:

```bash
FDI_WORKER_DRILL_APPROVED=V1.23.8-R2 ./deployment/second-instance/run-worker-resilience-drill.sh automatic remote
```

Valide os dois JSON mais recentes usando o commit de produção. Mantenha
`FDI_AUTO_FAILBACK_ENABLED=false` nos sete primeiros dias:

```bash
./deployment/second-instance/worker-topology-status.sh
ls -lt deployment/runtime/worker-drill-*.json | head
```

## Fase 4 — tornar o navegador real obrigatório

Em um computador confiável com navegador, instale Playwright, capture a sessão
do staging e trate o arquivo como senha:

```powershell
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
python -m scripts.capture_browser_storage_state --output storage-state-staging-owner.json
python -m scripts.benchmark_browser_journeys --storage-state storage-state-staging-owner.json --commit <COMMIT_STAGING_DE_40_CARACTERES> --samples 5 --output browser-performance-report.json
```

Transfira **somente o relatório**, nunca a sessão, para a VM1. Aplique modo
0600, valide e só então habilite o bloqueio permanente:

```bash
cd ~/invest
mkdir -p ~/.config/fdi
chmod 700 ~/.config/fdi
mv ~/browser-performance-report.json deployment/runtime/browser-performance-report.json
chmod 600 deployment/runtime/browser-performance-report.json
python3 -m scripts.verify_browser_performance_report deployment/runtime/browser-performance-report.json --expected-commit "$(cat .git/investment-staging-commit)"
./deployment/enable-browser-performance-gate.sh
```

Depois disso, toda promoção recusará relatório ausente, vencido, de outro
commit, com jornada faltante ou p95 acima da meta.

