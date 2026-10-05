# Relatório de validação — V1.23.6 R2A

## Incidente reproduzido

Durante a homologação da R2, o staging esgotou seu pool de duas conexões. Uma
falha capturada durante a projeção deixou a transação PostgreSQL abortada, e o
flush final repetiu `InFailedSqlTransaction`. Em paralelo, o envio de um alerta
operacional aguardou o SMTP até expirar.

## Correção aplicada

- pool do staging dimensionado para suas quatro atividades concorrentes;
- e-mail operacional desativado em staging;
- timeout SMTP limitado e falha tratada como aviso recuperável;
- savepoints nas projeções de valuation e backtests;
- último resultado válido e retentativas preservados.

## Critérios de aceite

- suíte oficial integral aprovada;
- cobertura de navegação em 100%;
- benchmark dentro das metas;
- ciclo completo de métricas sem falha;
- logs novos sem esgotamento do pool, transação abortada ou falha de trabalho.
