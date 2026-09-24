# Patch V1.23.1 R1

## Correções e melhorias

1. Consultas em lote para snapshots compartilhados e últimos trabalhos de
   atualização.
2. Reutilização dos snapshots no Painel de Mercado.
3. Remoção de pedidos automáticos redundantes quando os dados estão válidos,
   preservando o fallback de acesso para dados ausentes, vencidos ou com falha,
   a atualização manual e o acompanhamento de trabalho em andamento.
4. Cache versionado para recursos estáticos e capas.
5. Remoção do access log duplicado e redução de sucessos repetitivos,
   preservando integralmente erros, requisições de negócio e medições.
6. Publicação com branch de segurança atualizada e proteção contra
   concorrência.
7. Bloqueio de logs, diagnósticos e caches no pacote.
8. Pausa idempotente da pilha antiga.
9. Inclusão da suíte `tests_v1231` na regressão padrão.
10. Gate de desempenho p50/p95 antes de qualquer mutação da produção.

## Compatibilidade

- `refresh_status` individual permanece disponível e com o mesmo formato.
- Rotas, respostas públicas e botões manuais existentes foram preservados.
- Não há migração nova nem alteração destrutiva de banco.
- A migração esperada continua sendo `0027_v1_23_analysis_settings`.
