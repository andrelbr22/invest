# Relatório de validação — V1.23.7 R2

## Critérios obrigatórios

- suíte completa e regressões da R1 aprovadas;
- `app.js` menor que 190 KB;
- quatro módulos presentes e servidos por `/ui-assets`;
- cache imutável com versão `1.23.7-r2`;
- módulo baixado somente quando necessário;
- pedidos simultâneos unificados e falhas passíveis de nova tentativa;
- nenhuma migração posterior à `0032_v1237_browser_perf`;
- benchmark do servidor aprovado no staging;
- homologação visual de todos os módulos.

## Homologação visual

1. Recarregue a plataforma e abra primeiro Mercado e Análises.
2. Abra Carteira, Backtests, Finanças e Administração, uma de cada vez.
3. Na primeira abertura, aceite somente um indicador curto de carregamento.
4. Retorne às áreas já abertas: a exibição deve ser imediata e preservar estado.
5. Confirme formulários, gravações, notícias, alertas e Administração.
6. Use voltar, avançar e URLs diretas para cada uma das quatro áreas.
7. Em conexão estável, confirme ausência de erro de carregamento de módulo.

## Resultado local

- 443 testes de regressão e estrutura aprovados no Windows;
- 14 testes específicos da R2 e de identidade da publicação aprovados;
- sintaxe aprovada pelo Node.js no arquivo principal e nos quatro módulos;
- `app.js`: 181.333 bytes, contra 338.346 bytes antes da divisão;
- módulos: Carteira 45.203 bytes, Backtests 38.463 bytes, Finanças 9.440 bytes
  e Administração 72.500 bytes;
- nenhuma alteração de banco e nenhuma migração nova.

O cliente HTTP da instalação local do Windows apresentou incompatibilidade com
o `TestClient` atual. Por isso, os 52 testes que exercitam chamadas HTTP reais
permanecem obrigatórios na suíte Linux do staging. O benchmark real e a inspeção
visual também permanecem etapas do staging, pois dependem da infraestrutura e da
autenticação reais.
