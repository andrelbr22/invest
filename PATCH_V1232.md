# Patch V1.23.2 — otimização estrutural

## Dados e velocidade

- Nova tabela materializada de métricas atuais, preservando todos os
  históricos como fonte auditável.
- Campos quentes tipados para filtros e JSON versionado para recursos
  técnicos pré-calculados.
- Referência explícita aos snapshots de fundamentos, técnica, score e preço.
- Backfill diário em lotes retomáveis, com deduplicação por ciclo.
- Escrita dupla nas ingestões de fundamentos, técnica, scores e preços.
- Fallback histórico automático até a cobertura total.
- Carregamento de `price_bars` somente para ativos ainda não materializados.

## Navegação sem dependência externa

- `/data/sync-market` agenda a sincronização no worker e retorna HTTP 202.
- `/assets/{ticker}/prices/ingest` agenda a ingestão e retorna HTTP 202.
- A interface acompanha os trabalhos por identificador.
- Carteira do IBOV vem de snapshot local e agenda atualização se ausente ou
  vencida.
- Rotas legadas de notícias servem o cache persistente e apenas enfileiram a
  renovação necessária.

## Publicação

- API e worker apenas verificam a migração exigida.
- Serviços one-shot executam as migrações de staging e produção sob advisory
  lock PostgreSQL.
- O candidato é migrado antes de recriar a aplicação.
- O Caddy valida e recarrega a configuração sem interromper conexões; restart
  é fallback validado.
- A nova carga materializada é enfileirada somente depois da saúde do serviço.

## Segunda instância

- Preflight da VM2 confirma commit exato, repositório limpo, arquitetura,
  arquivos privados, destino PostgreSQL privado, DNS, migração e privilégios.
- SSH exige chave 0600, `known_hosts` 0600 e `StrictHostKeyChecking=yes`.
- Worker remoto não recebe acesso a códigos de login, usuários, portal,
  finanças ou configurações pessoais.
- Cutover e failback só concluem com exatamente um worker fresco e as duas
  lideranças no nó esperado.
- Guardião de failback é opt-in e exige falhas consecutivas.

