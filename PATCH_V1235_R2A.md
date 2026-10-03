# Patch V1.23.5 R2A

## Motivo

A R2 foi instalada corretamente, mas a última verificação da promoção tratava
o identificador do scheduler e o identificador do monitor de alertas como se
fossem iguais. Eles representam o mesmo worker lógico, porém usam formatos
distintos por projeto. Isso produziu uma falha operacional falsa depois de a
aplicação e o worker já estarem saudáveis.

## Correções

- exige exatamente um worker de produção fresco no nó, ambiente e commit
  aprovados;
- exige o `service_id` canônico desse worker;
- valida o scheduler pelo `service_id` exato;
- valida o monitor pelo formato completo
  `alerts:<ambiente>:<nó>:<pid ASCII positivo>`;
- mantém obrigatórios os metadados do nó, as duas flags de liderança e o
  conjunto exato das duas leases ativas;
- aguarda por até 24 tentativas de cinco segundos a convergência normal das
  lideranças antes de interromper uma promoção;
- corrige a consulta operacional do ciclo de materialização;
- usa log exclusivo e append na promoção para impedir truncamento por uma
  segunda tentativa concorrente.

## Compatibilidade

Nenhuma funcionalidade, dado histórico, configuração, permissão ou interface
foi removida. Não há migração nova: a revisão continua
`0030_v1_23_navigation_metrics` e a versão pública continua `1.23.5`.
