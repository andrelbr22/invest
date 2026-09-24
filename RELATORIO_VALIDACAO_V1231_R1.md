# Relatório de validação — V1.23.1 R1

## Princípio

A R1 foi construída sobre uma cópia separada da R8. Nenhuma limpeza de dados,
remoção de rota ou mudança de regra de negócio faz parte deste pacote.

## Evidências automatizadas exigidas

| Verificação | Critério |
| --- | --- |
| Regressão completa | Todos os diretórios versionados aprovados |
| Status em lote | Duas consultas para todas as rotinas, com payload equivalente |
| Painel de Mercado | Reutiliza snapshots já carregados |
| Navegação | Zero `ensure` com dados válidos; fallback preservado para ausente/vencido/falha |
| Atualização manual | Botões e polling preservados |
| Cache | URLs versionadas e cabeçalho imutável apenas em recursos estáticos |
| Logs | Erros e exceções preservados; sucessos repetitivos silenciados |
| Pacote | Sem logs, diagnósticos, caches, chaves ou segredos |
| Publicação | Backup anterior atualizado com lease antes da `main` |
| Pilha legada | Segunda execução não repete operações desnecessárias |
| Promoção | Benchmark reprova antes de backup, tag ou recriação da produção |

## Itens que exigem staging real

- resultado integral do pytest no mesmo contêiner que será promovido;
- p50/p95 das cinco rotas medidas contra a cópia real do banco;
- validação visual de todos os painéis e atualização manual;
- ausência de erros novos nos logs;
- confirmação de que produção não foi afetada durante a homologação.

## Fora do escopo desta revisão

- excluir dados antigos ou aplicar retenção;
- retirar APIs de compatibilidade;
- alterar fórmulas, filtros ou permissões;
- mudar o PostgreSQL ou o worker de instância;
- reescrever o screener ou pré-calcular indicadores técnicos.

Esses itens podem trazer ganhos adicionais, mas precisam de medição e
aprovação independentes para respeitar a exigência de não perder nada que já
funciona.
