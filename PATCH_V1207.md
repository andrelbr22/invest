# Patch V1.20.7

## Migrações cumulativas desta candidata

| Migração | Finalidade | Tratamento dos dados existentes |
| --- | --- | --- |
| `0015_v1_20_personal_backtest_jobs` | limites por usuário e detalhes de consumo dos backtests pessoais | preserva as execuções anteriores |
| `0016_v1_20_custom_investments` | investimentos sem ticker e histórico de valores | somente adiciona estruturas |
| `0017_v1_20_personal_finances` | receitas, despesas e orçamentos mensais | somente adiciona estruturas e permissões |
| `0018_v1_20_interest_curve_history` | histórico diário da curva de juros futuros | começa vazio e acumula dados após a implantação |

O `head` esperado do Alembic é `0018_v1_20_curve_history`.

## Compatibilidade e segurança

- mantém o fluxo GitHub → staging → aprovação manual → produção;
- mantém a entrega em partes dos backtests oficiais;
- mantém o worker com fila persistente e último snapshot válido;
- não publica PostgreSQL e não ativa automaticamente uma segunda VM;
- não inclui senhas, chaves, bancos locais ou segredos reais;
- mensagens HTTP 500 deixam de revelar exceções internas na interface.

## Rollback operacional

A promoção existente continua criando backup e preservando a imagem anterior. Como as migrações são aditivas, retornar a aplicação anterior não exige apagar imediatamente as novas tabelas. Não execute `downgrade` nem exclusão manual durante uma recuperação de serviço.
