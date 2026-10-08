# Patch V1.23.7 R1

## Interface

- restaura instantaneamente painéis e abas já visitados;
- preserva rolagem, filtros, ativo aberto, mês, densidade e ordenação;
- usa URLs profundas e histórico nativo do navegador;
- mantém dados anteriores visíveis durante atualizações silenciosas;
- diferencia carregando, atualizado, sem resultado oficial, N/D e falha;
- adiciona tabela ordenável, ticker fixo e modos compacto/confortável;
- reorganiza a Administração em quatro grupos;
- respeita preferência do dispositivo por menos movimento.

## Cache

As escritas invalidam apenas os dados relacionados. Atualizar carteira não
descarta mercado, alterar permissões não descarta backtests e sincronizar mercado
não apaga finanças.

## Observabilidade

- novo módulo isolado `web-vitals.js`;
- tempos do navegador continuam sem gravação síncrona por clique;
- agregação em memória e persistência horária;
- painel do proprietário mostra p50/p95, dispositivo, cache, LCP, INP e CLS;
- roteiro Playwright para o staging mede a entrada, Mercado e Análises, ativo,
  Carteira, Backtests e retorno a painel visitado.

## Migração

`0032_v1237_browser_perf` cria somente `client_performance_hourly` e seus
índices. Não modifica as tabelas funcionais nem os históricos existentes.
