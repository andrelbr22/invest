# Relatório de validação • V1.23.5 R2

## Validação local do pacote • 02/10/2026

- regressão completa: **413 testes aprovados**, com 1 aviso de depreciação
  conhecido e sem falhas;
- sintaxe Python: **240 arquivos** analisados com sucesso;
- sintaxe do JavaScript principal: aprovada;
- validação de publicação: `Pacote validado. Nenhum arquivo foi enviado.`;
- caches, bytecode e artefatos temporários removidos antes da compactação.

O benchmark real, a cobertura do banco copiado e a inspeção visual continuam
obrigatórios no ambiente `/testefdi` porque dependem dos dados e dos recursos
da Oracle.

## Garantias que devem ser comprovadas

1. A migração final é `0030_v1_23_navigation_metrics`.
2. Todos os testes até `tests_v1235` passam.
3. O benchmark obrigatório aprova health, dashboard, screener 50/100 e detalhe.
4. A cobertura das métricas atuais alcança todos os ativos ativos elegíveis.
5. Valorações e pódios preenchidos aparecem sem consulta externa durante a
   navegação.
6. Ativos explicitamente solicitados e ainda não preenchidos usam o caminho
   histórico; consultas globais parciais não reabrem uma varredura completa.
7. Uma atualização vazia não apaga uma projeção válida anterior.
8. A lista principal aparece antes dos sinais secundários, sem piscar ou
   misturar resultado da tela anterior.
9. Produção, proxy, banco e worker permanecem saudáveis após a promoção.
10. Não há erros novos em aplicação ou worker.

## Homologação visual

- abrir Dashboard, Mercado e Análises, detalhe de ações/FIIs/ETFs/BDRs/futuros,
  Carteira, Backtests, Alertas, Notícias e Administração;
- alternar rapidamente entre painéis e filtros e confirmar que somente a tela
  atual recebe o resultado;
- conferir Preço-teto DY, Valor relativo e as três colunas de backtests;
- validar filtros Padrão, FDI e ALB e configurações do proprietário;
- conferir login Google e código por e-mail, portal, livros e links de venda;
- verificar tempos reais em Administração > Operação.

## Critério de promoção

Promover apenas com regressão, benchmark, cobertura e inspeção visual
aprovados. A criação física ou o corte para a segunda VM continua sendo uma
operação separada e não deve ser presumida pelo pacote.
