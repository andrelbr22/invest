# Auditoria de desempenho da VM principal — V1.22.0

## Diagnóstico confirmado

A VM principal possui aproximadamente 1 GB de RAM e estava executando duas
arquiteturas ao mesmo tempo. A pilha anterior, identificada pelo projeto Docker
Compose `invest` e pelo arquivo `docker-compose.oracle-micro.yml`, mantinha uma
segunda aplicação, um segundo PostgreSQL e um proxy sem utilidade. Durante o
diagnóstico, a aplicação antiga chegou a consumir cerca de 53% da CPU.

Depois que a pilha anterior foi pausada, o painel voltou a abrir. A demora de
aproximadamente 15 segundos mostrou que havia também um gargalo na consulta do
screener, independente da disputa causada pelos contêineres antigos. A correção
SQL e os índices dessa consulta pertencem ao ajuste específico do screener.

As tabelas observadas não são grandes para PostgreSQL, mas já exigem consultas
corretamente indexadas: cerca de 37 mil snapshots de fundamentos, 33 mil
snapshots técnicos e 37 mil snapshots de notas.

## Proteções implementadas

1. Produção e PostgreSQL recebem prioridade de CPU durante contenção.
2. Staging e worker permanecem funcionais, mas cedem CPU à navegação.
3. Os pools de conexão foram explicitamente dimensionados para o PostgreSQL de
   30 conexões da VM pequena.
4. O worker ocioso consulta leases vencidos no primeiro ciclo e, depois, no
   máximo a cada 30–120 segundos, em vez de repetir essa varredura a cada poll.
5. O poll de produção passou a 5 segundos e o de staging a 10 segundos. Isso
   reduz consultas ociosas sem alterar os intervalos funcionais das rotinas.
6. Logs Docker passaram a ter rotação: três arquivos de até 10 MB por serviço.
7. Limites de processos e memória impedem que um serviço auxiliar consuma toda
   a VM.
8. Atualizações de staging fazem o build com baixa prioridade de CPU.
9. Toda atualização e promoção procura a pilha antiga pelos três rótulos
   Docker conhecidos, remove sua política de reinício e a pausa. Nenhum
   contêiner, volume ou dado antigo é excluído.

## Limite desta etapa

Essas medidas protegem a navegação durante a disputa por recursos, mas não
transformam uma VM de 1 GB em uma arquitetura escalável. A mudança de maior
impacto continua sendo ativar a segunda VM prevista na V1.22.0 e mover o worker.
Depois de uma semana estável, o staging também pode ser transferido. O banco deve
continuar como fonte única de verdade na VM principal.

## Homologação operacional

Após publicar no ambiente de teste, validar:

```bash
docker compose -f docker-compose.oracle-web.yml config --quiet
docker compose -f docker-compose.oracle-web.yml ps
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
docker stats --no-stream
```

Confirmar também que a pilha anterior não reapareceu:

```bash
docker ps --filter label=com.docker.compose.project=invest --format "{{.Names}}"
```

O resultado esperado do último comando é vazio. Durante carregamentos pesados,
`app` e `postgres` devem ter prioridade sobre `staging` e `worker`.
