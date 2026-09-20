# Relatório de implementações e pendências — V1.20.7

## Implementado nesta candidata

### Desempenho e estabilidade

- backtests pessoais executados pelo worker, sem bloquear a página;
- progresso persistente no PostgreSQL, recuperável após sair da tela;
- consultas externas e rotinas automáticas da R8 preservadas;
- histórico da curva DI separado do snapshot corrente;
- respostas de erro sanitizadas e mensagens compreensíveis;
- segunda instância preparada como worker, sem duplicar aplicação ou banco.

### Funcionalidades

- combinação de estratégias e limites completos de backtest;
- exportação CSV;
- carteira com ativos tradicionais e investimentos sem ticker;
- histórico de valores, composição e rebalanceamento;
- painel Minhas Finanças com receitas, despesas e orçamento;
- curva DI histórica e comparador com risco;
- administração das novas permissões e limites.

## Preparado, mas não ativado

### Segunda instância Oracle

Os arquivos operacionais estão prontos para transferir o worker. A ativação depende de criar a VM e configurar comunicação privada. Essa etapa foi deliberadamente separada para não arriscar a produção nem expor o banco.

## Melhorias que permanecem pendentes por dependerem de fonte ou decisão adicional

1. **Calendário oficial de proventos:** exige fonte corporativa confiável, cobertura consistente e regras de retificação.
2. **Feed exclusivo de fatos relevantes da CVM:** requer coleta, normalização, deduplicação e monitoramento de documentos oficiais.
3. **Valor automático de CDB, LCI, LCA e fundos bancários:** sem integração autorizada com cada instituição, um cálculo genérico poderia apresentar saldo incorreto; a V1.20.7 usa valor informado e histórico transparente.
4. **Histórico oficial integral de IMA-B e IRF-M:** continua sujeito à disponibilidade/licença da fonte; proxies devem permanecer identificados como tais.
5. **Transferência do staging para a segunda VM:** recomendada somente depois de o worker remoto operar de forma estável.

## Recomendação para a próxima etapa

Homologar primeiro toda a V1.20.7 em `/testefdi`. Depois, ativar a segunda VM em uma mudança operacional independente, começando somente pelo worker. A próxima funcionalidade de maior valor deve ser o calendário de proventos ou o feed da CVM, mas apenas após escolher e validar a fonte de dados.

## Validação local

- cadeia de migrações: uma única head em `0018_v1_20_curve_history`;
- sintaxe JavaScript: aprovada;
- testes acumulados da V1.16 à V1.20.7: 76 aprovados;
- nenhuma publicação no GitHub, staging ou produção foi feita durante o desenvolvimento desta candidata.
