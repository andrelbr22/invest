# Relatório de validação V1.21.1

## Resultado local

- regressão integrada: **140 testes aprovados**;
- sintaxe JavaScript: aprovada;
- compilação dos módulos Python: aprovada;
- árvore Alembic: um único head, `0020_v1_21_valuation_access`;
- versão da aplicação e do motor de backtests: `1.21.1`;
- verificação de whitespace do Git: sem erro.

Os três avisos apresentados pelo pytest são avisos de descontinuação de dependências (`authlib`, `httpx`/`starlette` e `anyio`) e não representam falha funcional desta versão.

## Cobertura específica desta correção

- proprietário recebe todas as permissões granulares;
- Padrão, FDI e ALB técnicos existem para ETF, BDR e futuro;
- filtros personalizados aceitam as cinco classes;
- consulta de ETF/BDR/futuro não baixa mais todo o universo `other_b3`;
- requisitos específicos de valuation dessas classes não são sobrescritos;
- cenários, ajuda do potencial e controles de cache estão presentes na interface.

## Pendências obrigatórias antes da produção

Ainda são necessários o `-ValidateOnly` do ZIP, a atualização do staging e todo o roteiro visual de `INSTRUCOES_ORACLE_V1211.md`. A promoção para produção permanece bloqueada até nova aprovação explícita do proprietário.
