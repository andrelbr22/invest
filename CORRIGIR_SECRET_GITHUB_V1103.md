# Documento histórico da V1.10.3

As instruções antigas de conexão direta do GitHub com o banco de produção não devem mais
ser usadas.

Desde a V1.12.0:

- o GitHub usa um PostgreSQL temporário;
- o banco da Oracle permanece privado;
- os resultados retornam por HTTPS com uma credencial exclusiva;
- `DATABASE_URL` e `DATABASE_ADMIN_URL` não são usados pelo workflow.

Siga `ATIVAR_ENTREGA_SEGURA_BACKTESTS_V1120.md`.
