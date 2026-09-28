# Relatório de validação — V1.23.1 R2

## Invariantes preservadas

- Nenhum histórico financeiro é removido.
- Carteiras, finanças, alertas, eventos e backtests ficam fora da retenção.
- Pedidos de usuários, falhas e trabalhos ativos são preservados.
- O último estado de cada rotina permanece na fila quente.
- O cache não altera payloads nem decisões de autorização.
- Uma invalidação concorrente sempre prevalece sobre uma leitura antiga.

## Evidências automatizadas

| Verificação | Critério |
| --- | --- |
| Cache | TTL, limite, cópia defensiva e geração concorrente aprovados |
| Permissões | Mutação invalida a entrada correspondente |
| Presets | Alteração e restauração invalidam somente o tipo afetado |
| Respostas compartilhadas | Reuso curto e invalidação após atualização |
| Retenção | Simulação não altera banco |
| Segurança | Manual, acesso, falha, ativo, backtest e último estado preservados |
| Arquivo | Payload integral e checksum antes da exclusão |
| Ciclos | Incidente/serviço repetido gera registros independentes |
| Paginação | Linhas inelegíveis antigas não bloqueiam linhas seguras posteriores |
| Downgrade | Mantém a tabela quando apagaria cópias arquivadas |
| Migração | PostgreSQL vazio alcança `0028_v1_23_operational_retention` |
| Desempenho | Gate p50/p95 permanece obrigatório antes da promoção |

## Limite desta entrega

Esta R2 é a conclusão segura da R1 conservadora. A otimização estrutural —
tabela corrente por ativo, pré-cálculo técnico, ingestões assíncronas,
migração isolada, proxy dinâmico e ativação física da segunda VM — segue em
uma versão própria para permitir escrita dupla, comparação de resultados e
reversão sem risco.
