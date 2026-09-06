# Patch V1.21.2

## Correções

- ETFs deixaram de ficar globalmente N/D: NAV e prêmio/desconto agora alimentam referências patrimonial e relativa.
- BDRs passaram a usar P/VP informado pela fonte em grupos comparáveis, sem usar P/L ou LPA potencialmente incompatíveis.
- futuros passaram a ser consultados no scanner correto e recebem contrato frontal, vencimento e dados de carrego quando disponíveis;
- os controles da interface são habilitados somente para metodologias aplicáveis à classe e autorizadas para a conta;
- premissas do Modelo de Gordon não são mais enviadas nem exigidas ao selecionar valor econômico em ETF, BDR ou futuro;
- tabelas de ETF, BDR e futuro exibem suas referências próprias e os respectivos potenciais;
- detalhes do ativo exibem nome correto do método, fonte e horário dos insumos.

## Segurança dos dados

Todas as novas rotinas falham de forma fechada. Dado ausente, amostra menor que o mínimo ou classificação não confiável produz N/D explicado; nunca produz valor zero ou estimativa substituta.
