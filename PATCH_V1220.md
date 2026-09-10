# Patch V1.22.0

Esta versão adiciona:

1. portal público com sete livros e acesso separado à plataforma;
2. rotas `/plataforma/` e `/testefdi/plataforma/` compatíveis com OAuth;
3. worker remoto opcional em segunda VM Oracle, sem segundo banco;
4. leases distribuídas para scheduler e monitor de alertas;
5. heartbeat, p50/p95, incidentes e painel operacional;
6. watchdog externo ao worker e notificações por e-mail;
7. corte, promoção, rollback e failback documentados e testáveis.

Migração de banco: `0022_v1_22_observability`.

