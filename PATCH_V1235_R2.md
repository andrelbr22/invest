# Patch V1.23.5 R2

## Motivo

Os benchmarks internos estavam rápidos, mas a experiência real ainda sofria
com cálculos históricos durante a navegação, respostas secundárias encadeadas
e competição de recursos entre produção, staging e worker na VM principal.

## Correções e melhorias

- materializa a valoração padrão por ativo sem substituir históricos;
- materializa as três melhores estratégias oficiais e seus sinais atuais;
- usa fallback histórico apenas enquanto houver lacuna de cobertura;
- preserva o último valor válido quando uma atualização resultar vazia;
- entrega listas primeiro e completa dados secundários progressivamente;
- cancela trabalho exclusivo de telas abandonadas durante navegação rápida;
- mantém compartilhamento de requisições GET iguais em andamento;
- estaciona o staging somente após promoção concluída, com opção explícita de
  mantê-lo ativo;
- reforça o corte e o retorno do worker da segunda VM, evitando dois
  schedulers ou dois monitores de alertas simultâneos.

## Banco de dados

A migração `0030_v1_23_navigation_metrics` acrescenta quatro campos
reconstruíveis à tabela `asset_current_metrics`. Nenhum histórico é removido,
truncado ou reescrito.

## Reversibilidade

Antes da promoção continua sendo criado backup integral. A projeção pode ser
recalculada pelo worker. O worker remoto pode retornar de forma controlada para
a VM principal, e o staging é reativado pela próxima atualização de teste.
