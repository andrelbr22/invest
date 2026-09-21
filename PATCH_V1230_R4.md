# V1.23.0 R4 — proventos oficiais e diagnóstico do worker

## Correções

- a seleção dos ativos presentes nas carteiras deixou de usar `DISTINCT`
  sobre todas as colunas de `assets`, operação incompatível com a coluna JSON
  `metadata_json` no PostgreSQL;
- a consulta agora usa `EXISTS` sobre `portfolio_positions`, preservando um
  único ativo por resultado sem comparar conteúdo JSON;
- falhas de trabalhos em segundo plano passam a registrar o traceback
  original no log do worker, mantendo a mensagem pública resumida;
- a rotina ALB foi reproduzida em produção dentro de uma transação revertida
  e concluiu corretamente, identificando 33 ativos e o estado
  `outside_range`, sem alterar silenciosamente o preset.

## Validação

- teste da compilação PostgreSQL da consulta de proventos, exigindo `EXISTS`
  e proibindo `DISTINCT`;
- teste do registro de traceback do worker;
- preservação do teste de finais de linha Linux introduzido na R3.
