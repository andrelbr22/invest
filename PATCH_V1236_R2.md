# Patch V1.23.6 R2

## Objetivo

Reduzir a espera ao alternar painéis, mantendo todos os recursos, resultados,
permissões, fallbacks e atualizações manuais existentes.

## Alterações técnicas

1. **Navegação sem reinício redundante**
   - selecionar a visão ou aba já ativa não cancela pedidos nem recarrega a
     tela;
   - a troca real de painel continua cancelando somente pedidos obsoletos.

2. **Cache de leitura preservado**
   - `/screen/advanced` continua sendo `POST` por causa do corpo complexo, mas
     é tratado como leitura e não apaga o cache global;
   - presets de Ações e FIIs usam as rotas `GET` que respeitam tanto o padrão
     de fábrica quanto a alternativa do proprietário;
   - Notícias e Administração reutilizam leituras por 15 segundos;
   - atualizar, reprocessar e acompanhar um trabalho sempre ignora esse cache.

3. **Respostas menores no servidor**
   - a listagem de backtests seleciona somente os campos usados no resumo;
   - curvas, negociações e resultado integral permanecem acessíveis no
     detalhe;
   - o Dashboard extrai apenas os metadados necessários das rotinas que não
     aparecem no corpo do painel;
   - a Carteira reutiliza o mesmo snapshot intradiário para preços e status.

4. **Gate contra fallback caro**
   - a promoção mede ativos ativos, métricas atuais, valorações e pódios;
   - somente cobertura integral permite avançar ao benchmark e à produção;
   - os fallbacks continuam no código para recuperação, mas não devem ser o
     caminho normal da navegação publicada.

## Banco e compatibilidade

Não há nova migração. A revisão permanece
`0030_v1_23_navigation_metrics` e nenhum histórico é removido.
