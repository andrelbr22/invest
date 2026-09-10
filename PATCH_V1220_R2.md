# Patch V1.22.0 R2

A R2 corrige a última diferença entre a suíte local e a suíte executada dentro do staging:

1. o teste administrativo usa `monkeypatch` para desligar autenticação apenas durante o próprio teste;
2. o proprietário local de testes exerce as permissões sobre um banco SQLite em memória;
3. o valor real de `APP_AUTH_REQUIRED` é restaurado automaticamente ao término do teste;
4. nenhuma configuração de autenticação, host ou usuário da aplicação foi flexibilizada;
5. 212 testes passam no conjunto integral.
