# Patch V1.23.8 R1

## Interface

- controlador de frescor por painel e aba;
- limite de 192 leituras compartilhadas e 24 resultados de screener no cache;
- coalescência de GETs idênticos, inclusive quando possuem chave de painel;
- Análises em `feature-analysis.js`, carregada por demanda e antecipada por
  mouse ou teclado;
- manutenção de rolagem, filtros, ordenação, densidade e ativo selecionado.

## Alertas

- `/alerts/catalog` aceita `q` e `limit`;
- consulta vazia não varre a B3;
- a interface pesquisa após pequena pausa e recebe no máximo 12 sugestões;
- índices, câmbio, criptos e commodities continuam disponíveis imediatamente.

## Operação

- TTLs: permissões 60 s, presets 300 s, respostas compartilhadas 60 s e
  screener 120 s;
- benchmark real com cinco amostras, p50/p95 e metas diferentes para abertura
  fria e retorno aquecido;
- verificador de relatório por commit, idade, staging, amostras e p95;
- nenhum esquema ou histórico alterado.
