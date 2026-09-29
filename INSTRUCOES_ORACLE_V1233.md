# Instruções Oracle — V1.23.3

## Antes de publicar

1. Execute `PUBLICAR_GITHUB.ps1 -ValidateOnly` no PowerShell local.
2. Publique somente depois da aprovação explícita para o ambiente de teste.
3. No servidor Ubuntu, aguarde a atualização automática ou execute
   `./deployment/update-staging-from-github.sh`.

## Homologação obrigatória

1. Confirme `/testefdi/ready` com HTTP 200, versão `1.23.3`, ambiente `staging`
   e migração `0029_v1_23_current_metrics`.
2. Execute toda a suíte até `tests_v1233`.
3. Confirme que o trabalho `current_metrics_refresh` termina sem falhas.
4. Confirme cobertura integral de ativos ativos e recursos técnicos.
5. Execute `python -m scripts.benchmark_application_routes --samples 20 --warmup 2`.
6. Abra Painel de Mercado, Mercado e Análises, screener de 50 e 100 ativos e
   detalhe de um ativo, verificando dados e tempo de resposta.

## Promoção

Somente após a aprovação final, execute
`./deployment/promote-staging-to-production.sh`. O script repete o benchmark,
faz backup e preserva a produção anterior se qualquer etapa falhar.

## Observações

- não execute comandos PowerShell dentro do SSH;
- não interrompa o preenchimento apenas porque há intervalos curtos entre
  lotes: eles são deliberados para preservar a navegação;
- a segunda VM não é ativada por esta atualização.
