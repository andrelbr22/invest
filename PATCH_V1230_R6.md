# V1.23.0 R6 — proventos oficiais de FIIs

Esta revisão completa a correção iniciada na R4/R5 para o calendário de
proventos. A B3 publica eventos de ações e de fundos em serviços oficiais
distintos; o coletor agora escolhe a fonte correta conforme o tipo do ativo.

## Correções

- FIIs passam a usar a rota oficial de Fundos Listados da B3.
- A cota principal é validada por ISIN. Direitos e recibos de subscrição
  retornados junto com o fundo são ignorados e contabilizados no diagnóstico.
- Ações, BDRs e ETFs preservam o fluxo já homologado de Empresas Listadas.
- O tipo do ativo acompanha cada solicitação interna, sem alterar carteiras,
  permissões ou registros existentes.

## Validação obrigatória

1. Atualizar o staging e executar toda a suíte automatizada.
2. Executar manualmente `handle_investor_dividends_refresh` no staging.
3. Confirmar `status: complete`, lista `errors` vazia e eventos recebidos para
   o XPML11.
4. O monitor ALB deve executar sem exceção. Enquanto retornar 33 ativos, o
   estado `outside_range` é um alerta válido e não impede esta correção; os
   critérios serão recalibrados apenas após medir alternativas nos dados reais.
