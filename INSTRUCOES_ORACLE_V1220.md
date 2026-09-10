# Instruções Oracle — V1.22.0

Execute uma etapa por vez. Se o resultado divergir do esperado, pare e envie a saída antes de prosseguir. Nunca cole o texto do prompt (`PS C:\...>` ou `ubuntu@...$`) junto do comando.

## Fase 1 — staging, ainda com uma VM

Na VM1:

```bash
cd ~/invest
```

```bash
./deployment/update-staging-from-github.sh
```

Esperado: `Teste atualizado: https://formacaodoinvestidor.com.br/testefdi/`.

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Esperado: versão `1.22.0`, ambiente `staging`, banco acessível e migração `0022_v1_22_observability`.

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 -q -p no:cacheprovider
```

Esperado: todos os testes aprovados; avisos de depreciação não são falhas.

Homologue visualmente:

1. `/testefdi/` abre o portal público;
2. as sete capas aparecem e a página se adapta ao celular;
3. `Acessar plataforma` abre `/testefdi/plataforma/`;
4. login Google retorna ao ambiente de teste;
5. todos os painéis existentes continuam funcionais;
6. proprietário vê `Administração > Operação`.

Somente depois da aprovação explícita, promova com o fluxo já conhecido. Nesse primeiro momento, `deployment/runtime/worker-location.env` não existe e o worker permanece local.

## Fase 2 — criar a VM2

Na Console OCI:

1. crie uma instância `formacao-investidor-worker` na mesma VCN;
2. prefira A1 Flex, 1 OCPU e 6 GB, Ubuntu 24.04; use E2.1.Micro se A1 não estiver disponível;
3. anote IP privado da VM1 e IP privado da VM2;
4. crie os NSGs descritos em `ARQUITETURA_DUAS_INSTANCIAS_V1220.md`;
5. a única regra de entrada 5432 deve ter como origem o NSG da VM2;
6. não crie PostgreSQL na VM2.

Instale Git e Docker na VM2, clone o repositório em `/home/ubuntu/invest` e confirme que `git rev-parse HEAD` corresponde ao commit vigente em produção.

## Fase 3 — preparar o banco privado na VM1

```bash
cd ~/invest
```

```bash
cp deployment/runtime/primary-db.env.example deployment/runtime/primary-db.env
```

Edite somente o IP privado da VM1:

```bash
nano deployment/runtime/primary-db.env
```

Crie a credencial exclusiva. Guarde a senha gerada no gerenciador de senhas; ela será usada uma vez também na VM2:

```bash
./deployment/second-instance/create-worker-db-role.sh
```

Habilite a porta vinculada apenas ao IP privado:

```bash
./deployment/second-instance/enable-primary-private-db.sh
```

Esperado: backup concluído e `PostgreSQL disponível somente em <IP_PRIVADO_VM1>:5432`.

Confirme que não há bind amplo:

```bash
sudo ss -lntp | grep 5432
```

Esperado: somente `<IP_PRIVADO_VM1>:5432`. Não prossiga se aparecer `0.0.0.0:5432`, `*:5432` ou `[::]:5432`.

## Fase 4 — configurar a VM2

Na VM2:

```bash
cd ~/invest
```

```bash
cp deployment/second-instance/worker.env.example deployment/second-instance/worker.env
```

```bash
cp deployment/second-instance/worker_secrets.toml.example deployment/second-instance/worker_secrets.toml
```

Preencha o IP privado da VM1 e a senha exclusiva em `worker_secrets.toml`. Preserve SMTP e proprietários para os alertas operacionais e de preço.

```bash
nano deployment/second-instance/worker_secrets.toml
```

```bash
sudo chown ubuntu:10001 deployment/second-instance/worker_secrets.toml
```

```bash
chmod 640 deployment/second-instance/worker_secrets.toml
```

```bash
cp deployment/second-instance/worker.env.example deployment/second-instance/worker.env
```

```bash
nano deployment/second-instance/worker.env
```

Mantenha `FDI_COORDINATOR_ENABLED=false` durante a preparação e coloque o commit vigente.

```bash
./deployment/second-instance/validate-worker.sh
```

Esperado: endereço privado, DNS externo, banco e migração V1.22.0 validados.

## Fase 5 — acesso da VM1 à VM2

Use uma chave exclusiva para a comunicação entre as VMs. Na VM1, crie:

```bash
cp deployment/runtime/worker-location.env.example deployment/runtime/worker-location.env
```

```bash
nano deployment/runtime/worker-location.env
```

Preencha os IPs/caminhos e mantenha inicialmente `FDI_WORKER_LOCATION=local`. A chave privada deve ter modo 600.

Instale o watchdog na VM1 antes do corte:

```bash
./deployment/install-operational-watchdog.sh
```

```bash
systemctl status investment-operational-watchdog.timer --no-pager
```

Esperado: `active (waiting)`.

## Fase 6 — corte controlado

Na VM1:

```bash
./deployment/second-instance/cutover-worker.sh
```

Esperado: `Worker transferido para a VM2`.

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/health/worker
```

Esperado: HTTP 200 e worker acessível.

```bash
docker compose -f docker-compose.oracle-web.yml ps worker
```

Esperado: worker local parado.

Na VM2:

```bash
docker compose --env-file deployment/second-instance/worker.env -f deployment/second-instance/docker-compose.worker.yml ps
```

Esperado: worker remoto `healthy`.

Na VM1, valide as duas lideranças:

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine -c "SELECT lease_name, holder_id, expires_at FROM runtime_leases WHERE expires_at > now() AND lease_name IN ('background-scheduler','price-alert-monitor-leader') ORDER BY lease_name;"
```

Esperado: duas linhas, uma por lease; nunca duas linhas para a mesma lease.

## Fase 7 — teste obrigatório de retorno

Na VM1:

```bash
./deployment/second-instance/failback-worker.sh
```

Valide `/health/worker` e o worker local `healthy`. Depois execute novamente o corte:

```bash
./deployment/second-instance/cutover-worker.sh
```

O teste comprova que a plataforma não fica dependente da VM2.

## Fase 8 — alarmes OCI

Na Console OCI, habilite o Compute Instance Monitoring plugin nas duas VMs, crie um Topic no Notifications e alarmes para indisponibilidade/infraestrutura, CPU sustentada e espaço de boot volume. O watchdog interno complementa esses alarmes, mas não substitui um observador fora da VM.

## Conferência final

- `/ready`: 1.22.0, production, 0022;
- `/health/worker`: HTTP 200;
- Administração > Operação: um worker fresco, um scheduler líder e um monitor líder;
- nenhum erro recente no worker;
- portal e plataforma abrem na raiz e em staging;
- nenhuma porta 5432 pública;
- backup no Object Storage confirmado.

