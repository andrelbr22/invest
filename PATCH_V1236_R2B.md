# Patch V1.23.6 R2B

## Diagnóstico confirmado

A R2A eliminou esgotamento de conexões, transações abortadas e falhas SMTP
durante a homologação. O ciclo continuou lento porque a consulta que seleciona
o snapshot mais recente usava `row_number()` sobre o histórico. Sob carga, o
PostgreSQL cancelava essa consulta ao atingir o `statement_timeout`; a fila só
avançava depois de duas ou três tentativas.

## Correção

- PostgreSQL passa a selecionar apenas o primeiro identificador por ativo com
  `DISTINCT ON` e depois busca a linha completa pela chave primária;
- SQLite conserva a consulta por janela usada nos testes determinísticos;
- quatro índices descendentes cobrem fundamentos, técnicos, scores e preços;
- a migração cria os índices com `CONCURRENTLY`, sem apagar ou reescrever
  históricos;
- uma migração interrompida pode ser repetida sem conservar índice inválido.

## Compatibilidade

- versão pública permanece `1.23.6`;
- revisão de banco esperada: `0031_v123_latest_snapshot_idx`;
- nenhuma tela, fórmula, permissão, fonte ou dado existente foi removido;
- todas as melhorias da R2 e R2A permanecem ativas.
