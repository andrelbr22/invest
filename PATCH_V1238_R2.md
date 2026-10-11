# Patch V1.23.8 R2

## Objetivo

Separar o processamento pesado da navegação sem criar uma segunda fonte de
verdade e tornar toda decisão de desempenho comparável, reversível e auditável.

## Alterações

- diagnóstico somente leitura de PostgreSQL, sessões, pool, cache, I/O,
  tabelas, índices e, quando disponível, `pg_stat_statements`;
- apresentação resumida dessas métricas em Administração > Operação, exclusiva
  para o proprietário;
- captura de linhas de base da aplicação e da máquina antes e depois do corte;
- ensaio protegido do worker remoto com corte, retorno manual ou automático,
  verificação de um único scheduler/monitor e localização final explícita;
- evidência JSON do ensaio vinculada ao commit de produção;
- captura local segura da sessão Playwright e bloqueio persistente das
  promoções depois que o benchmark real for habilitado;
- token R2 dos arquivos estáticos para impedir mistura de JavaScript entre
  revisões.

## Preservação

Não há migração nova, alteração de fórmula, exclusão de histórico, mudança de
permissão nem quebra de API. O banco gravável continua único na VM principal.
O R2 não cria índices ou muda parâmetros automaticamente: primeiro mede e só
autoriza uma otimização posterior quando houver evidência.

