# Patch V1.21.0

## Objetivo

Ampliar com segurança os dois objetivos centrais da plataforma: seleção de ativos por filtros fundamentalistas/técnicos e avaliação de estratégias por backtests, acrescentando quatro famílias de valoração sem perder funcionalidades homologadas.

## Alterações principais

- catálogo canônico de famílias, métodos, aliases históricos e aplicabilidade por classe;
- resultados de valoração padronizados com cenários, qualidade, motivo e estado;
- valuation relativo robusto para ações e FIIs;
- Gordon/DDM com três cenários explícitos e margem opcional;
- quatro filtros combináveis no screener e quatro colunas de resultado;
- permissões independentes para Graham, dividend yield-alvo, pares e valor econômico;
- herança integral das permissões de valoração pelo perfil ALB;
- bloqueio e remoção no servidor de campos não autorizados;
- correção de ROIC e das unidades de dividendos e FFO yield;
- três estratégias novas e um cruzamento configurável;
- novos filtros técnicos comuns às estratégias;
- benchmark automático, parâmetros tipados, limites e execução sem look-ahead;
- grade oficial equilibrada e determinística.

## Banco

Migração aditiva: `0020_v1_21_valuation_access`.

Colunas novas em `user_access_policies`:

- `can_use_relative_valuation`;
- `can_use_economic_valuation`.

Não há remoção ou renomeação de tabelas, colunas ou dados.

## Compatibilidade

Os nomes internos antigos de Graham, preço-teto e Gordon continuam normalizados pelo catálogo. Filtros personalizados existentes permanecem válidos. As rotas e estruturas antigas são preservadas, exceto pelo reforço intencional de autorização nas rotas síncronas de backtest.

## Reversão

A promoção já mantém a imagem anterior para rollback. A reversão de banco, se estritamente necessária, deve ser feita somente com backup confirmado e remove apenas as duas permissões novas; não execute downgrade durante uso normal.
