# Patch V1.20.7

## Migrações cumulativas desta candidata

| Migração | Finalidade | Tratamento dos dados existentes |
| --- | --- | --- |
| `0015_v1_20_personal_backtest_jobs` | limites por usuário e detalhes de consumo dos backtests pessoais | preserva as execuções anteriores |
| `0016_v1_20_custom_investments` | investimentos sem ticker e histórico de valores | somente adiciona estruturas |
| `0017_v1_20_personal_finances` | receitas, despesas e orçamentos mensais | somente adiciona estruturas e permissões |
| `0018_v1_20_interest_curve_history` | histórico diário da curva de juros futuros | começa vazio e acumula dados após a implantação |
| `0019_v1_20_access_rules` | permissões separadas de FDI, ALB, Graham e preço-teto; setor/segmento da carteira | apenas adiciona colunas; usuários existentes permanecem sem as novas autorizações até o administrador liberá-las |

O `head` esperado do Alembic é `0019_v1_20_access_rules`.

## Compatibilidade e segurança

- mantém o fluxo GitHub → staging → aprovação manual → produção;
- mantém a entrega em partes dos backtests oficiais;
- mantém o worker com fila persistente e último snapshot válido;
- não publica PostgreSQL e não ativa automaticamente uma segunda VM;
- não inclui senhas, chaves, bancos locais ou segredos reais;
- mensagens HTTP 500 deixam de revelar exceções internas na interface.

## Rollback operacional

A promoção existente continua criando backup e preservando a imagem anterior. Como as migrações são aditivas, retornar a aplicação anterior não exige apagar imediatamente as novas tabelas. Não execute `downgrade` nem exclusão manual durante uma recuperação de serviço.

## R1 — correção do teste autenticado

O teste de enfileiramento usava implicitamente o proprietário local, disponível somente quando a autenticação está desativada. Em staging, a proteção Google respondia corretamente com HTTP 401. A R1 injeta no teste a conta proprietária configurada e mantém a mesma validação funcional. O código executado pelos usuários não foi modificado por esta correção.

## R2 — regras de acesso e dados adicionais

A R2 mantém o mesmo número semântico `1.20.7`, mas acrescenta a migração aditiva `0019`. Nenhuma autorização antiga é ampliada silenciosamente. O proprietário conserva acesso integral; os demais usuários recebem FDI, ALB, Graham e preço-teto somente por seleção individual no painel Administração. A permissão ALB ativa automaticamente as duas permissões de valuation.

## R3 — atualização histórica sem tela vazia

A R3 não acrescenta migração. Ela corrige a comunicação entre navegador, API e worker no Comparador Histórico. O botão de atualização não apaga mais o snapshot anterior, a API devolve os dados válidos junto do estado real do trabalho e a interface continua consultando a fila até a conclusão. O `head` do Alembic permanece `0019_v1_20_access_rules`.

## R4 — recuperação da rodada semanal de backtests

A rodada agendada de 5 de setembro de 2026 falhou ao preparar o PostgreSQL descartável do GitHub. A migração inicial cria o modelo atual completo; migrações recentes ainda tentavam recriar estruturas já presentes. A R4 corrige a identificação da chave estrangeira da `0015`, torna `0017`, `0018` e `0019` idempotentes e passa a montar diretamente o esquema atual no banco temporário, com proteção que aceita apenas `backtests_ci` em `localhost`.

O CI agora executa todas as suítes V1.20 e valida o histórico de migrações em um PostgreSQL 16 vazio. As ações oficiais foram atualizadas para versões compatíveis com Node.js 24. No painel, a retomada passou a se chamar `Reprocessar ativos pendentes ou com falha` e mostra corretamente se a nova execução foi enviada a staging ou produção.
