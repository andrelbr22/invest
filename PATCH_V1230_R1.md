# Patch V1.23.0 R1

## Correção

O clone do banco de homologação agora é restaurado diretamente pelo papel
restrito `investment_staging`, que já é o proprietário do banco criado para o
ambiente de teste.

O lote histórico da ANBIMA também passa a calcular o dia corrente no fuso de
São Paulo. Assim, execuções noturnas não tentam consultar antecipadamente a
data UTC do dia seguinte.

A primeira edição da V1.23.0 restaurava os objetos como o administrador
`investment` e executava `REASSIGN OWNED`. Em bancos PostgreSQL existentes há
objetos internos que não podem ser transferidos dessa forma, o que interrompia
a atualização antes da subida do contêiner de staging.

## Segurança preservada

- o banco de produção continua sendo apenas a origem do `pg_dump`;
- o banco de staging continua sendo recriado isoladamente;
- o papel `investment_staging` permanece sem superusuário, criação de banco,
  criação de papel ou replicação;
- códigos de login e trabalhos ativos continuam higienizados na cópia;
- não há alteração nem transferência de propriedade no banco de produção.

## Homologação

Depois de publicar esta revisão, execute novamente
`./deployment/update-staging-from-github.sh`. O resultado esperado inclui a
criação da cópia isolada, a subida saudável do staging e a versão `1.23.0` com
migração `0026_v1_23_email_login` em `/testefdi/ready`.
