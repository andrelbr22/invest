# Relatório de validação — V1.23.8 R1B

## Diagnóstico confirmado no staging

O navegador registrou `TypeError` em `bindEvents` porque
`#apply-advanced-filters` ainda não existia quando `app.js` foi inicializado.
O HTML e o CSS carregavam, deixando visível apenas a faixa do ambiente de
teste, mas a exceção impedia a montagem do restante da plataforma.

## Proteções

- eventos dos três comandos de análises personalizados são delegados;
- não há acesso direto ao botão ausente durante a inicialização;
- token estático novo força o navegador a buscar a correção;
- teste de regressão impede a reintrodução do vínculo antecipado;
- suíte completa, benchmark e homologação visual continuam obrigatórios no
  staging.
