# Relatório de validação — V1.23.6 R1

## Invariantes preservadas

- mesmas permissões e níveis de acesso;
- mesmas fórmulas de filtros, valuation, carteira e backtests;
- mesma prioridade de preço da carteira;
- mesmos fallbacks quando a tabela atual ou uma fonte estiver incompleta;
- nenhuma exclusão de tabela, histórico, preferência ou configuração;
- promoção para produção continua manual.

## Cobertura automatizada adicionada

- equivalência entre preço escalar e preço em lote;
- limite constante de consultas independentemente do número de posições;
- equivalência integral do snapshot da carteira, incluindo cotação intradiária;
- fallback legado do dashboard presente quando necessário e ausente do caminho
  saudável;
- consultas de cache antigo limitadas a uma linha;
- renderização localizada dos três backtests com fallback integral;
- instrumentação das três áreas adicionais;
- modos frio e estendido do benchmark;
- cobertura compacta e consulta de navegação multiativos.

## Resultado da validação local

- suíte completa: **456 testes aprovados**, sem falhas;
- único aviso: depreciação já conhecida da integração Starlette/httpx;
- sintaxe do JavaScript validada pelo Node.js;
- nenhum `__pycache__`, `.pytest_cache`, `.pyc`, `.pyo` ou arquivo de log
  incluído na fonte de publicação.

## Homologação obrigatória

1. `/testefdi/ready` deve responder HTTP 200, versão `1.23.6`, ambiente
   `staging` e revisão `0030_v1_23_navigation_metrics`.
2. A suíte oficial deve terminar sem falhas.
3. O benchmark aquecido deve cumprir todas as metas.
4. O benchmark frio/estendido deve ser registrado para comparação; ele é
   diagnóstico e não substitui o gate aquecido de promoção.
5. Conferir visualmente Dashboard, listas de Ações/FIIs/ETF/BDR/Futuros,
   detalhe de ativo, Carteira, Backtests, Finanças e Administração.
6. Confirmar ausência de `error`, `traceback`, `background_job_failed` e
   `unhealthy` nos logs do staging.

## Banco

Não há migração nova nesta revisão. O histórico e a tabela materializada atual
permanecem intactos.
