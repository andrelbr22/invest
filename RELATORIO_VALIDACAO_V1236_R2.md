# Relatório de validação — V1.23.6 R2

## Invariantes preservadas

- mesmas permissões, filtros, fórmulas e fontes;
- mesmos valores e mesma ordenação nas listas;
- curvas e resultados completos continuam disponíveis no detalhe do backtest;
- os fallbacks históricos permanecem no servidor;
- os botões de atualizar continuam forçando leitura nova;
- nenhuma exclusão de tabela, histórico, preferência ou configuração;
- promoção para produção continua manual.

## Cobertura automatizada adicionada

- equivalência do resumo da lista compacta de backtests;
- ausência dos grandes JSONs na consulta da listagem e presença no detalhe;
- paridade do status de atualização com projeção compacta de snapshot;
- reutilização do snapshot da Carteira sem segunda leitura;
- operação nula ao selecionar a mesma visão ou aba;
- consultas avançadas sem invalidação do cache de leitura;
- cache curto e atualização forçada em Notícias e Administração;
- bloqueio da promoção com cobertura materializada incompleta.

## Resultado local

- suíte completa: **468 testes aprovados**, sem falhas;
- único aviso: depreciação já conhecida da integração Starlette/httpx;
- sintaxe do JavaScript validada pelo Node.js;
- validação dirigida das consultas e da navegação aprovada;
- nenhum cache, bytecode, log ou diagnóstico local permitido no pacote.

## Homologação obrigatória

1. `/testefdi/ready` deve responder HTTP 200, versão `1.23.6`, ambiente
   `staging` e revisão `0030_v1_23_navigation_metrics`.
2. O gate de cobertura deve informar o mesmo total para ativos ativos,
   métricas atuais, valorações e pódios.
3. A suíte oficial deve terminar sem falhas.
4. O benchmark aquecido deve cumprir todas as metas.
5. Alternar repetidamente Dashboard, Análises, Carteira, Backtests, Finanças e
   Administração sem reconstrução ou espera indevida.
6. Confirmar que os botões de atualização exibem dados novos.
7. Confirmar ausência de erros nos logs do staging.

## Banco

Não há migração nova. A revisão permanece
`0030_v1_23_navigation_metrics`.
