# Relatório de validação — V1.23.8 R1

## Invariantes

- versão base: V1.23.7 R2;
- revisão do banco: `0032_v1237_browser_perf`;
- nenhuma migração, remoção de tabela ou alteração destrutiva;
- contratos de análise, carteira, finanças, backtests e administração mantidos;
- cache invalidado após qualquer escrita relacionada.

## Critérios de aceite

1. suíte completa, incluindo `tests_v1238`, sem falhas;
2. `/testefdi/ready` em HTTP 200 e versão 1.23.8;
3. benchmark interno dentro das metas existentes;
4. Mercado e Análises, Carteira, Finanças, Backtests e Administração íntegros;
5. retorno a Análises e Dashboard com p95 de até 1 segundo no Chromium;
6. demais jornadas reais com p95 de até 4 segundos;
7. nenhum erro novo nos logs do staging.

## Resultado local

Validação executada antes da geração do pacote:

- sintaxe Python: aprovada;
- sintaxe dos seis arquivos JavaScript: aprovada;
- testes específicos V1.23.8 e regressão V1.23.7: 20 aprovados;
- cenários de maior risco da interface: 49 aprovados;
- identidades e documentos históricos selecionados: 18 aprovados;
- higiene do pacote: 7 aprovados;
- descoberta integral: 503 testes coletados sem erro;
- suíte completa em Linux/contêiner: obrigatória no staging;
- benchmark real autenticado: obrigatório na homologação operacional;
- validação do publicador: executada depois da limpeza final do pacote.
