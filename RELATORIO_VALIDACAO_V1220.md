# Relatório de validação — V1.22.0

## Escopo

- preservação funcional da V1.21.3;
- portal público, sete livros e SPA em rota separada;
- staging com prefixo e OAuth seguros;
- migração de coordenação/observabilidade;
- worker local e remoto;
- segurança do banco privado;
- promoção, rollback e failback;
- painel e alertas operacionais.

## Validações automatizadas específicas

Os testes em `tests_v1220` cobrem:

- GET/HEAD do portal e da plataforma;
- as sete capas WebP, cache e tipo de conteúdo;
- redirects relativos e destinos OAuth permitidos;
- Caddy e `/testefdi`;
- arquivos sensíveis fora do Git e da imagem;
- flags de coordenação local/remota;
- scripts de preparação, ativação, corte e retorno;
- commit homologado e metadados de rollback;
- percentis, classificação das rotas e janela limitada;
- exclusividade e expiração das leases;
- heartbeat e ciclo de vida de incidentes;
- isolamento entre escopos de incidentes;
- detecção de fila parada, falhas, recursos e latência.

## Critérios de homologação

1. Todos os testes versionados passam.
2. O portal é legível em desktop e celular e exibe sete capas.
3. O login de staging nunca retorna à produção.
4. A plataforma preserva os painéis existentes.
5. `/ready` aponta `0022_v1_22_observability`.
6. `Administração > Operação` mostra recursos, fila, serviços e p50/p95.
7. O teste de failback termina com worker local saudável.
8. O novo corte termina com somente o worker remoto ativo.
9. A VM1 não escuta PostgreSQL em endereço público/amplo.
10. Não há publicação em produção sem aprovação expressa.

