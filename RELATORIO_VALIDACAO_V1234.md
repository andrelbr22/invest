# Relatório de validação V1.23.4

## Escopo automatizado

- pódio de três estratégias distintas por ativo;
- escolha da melhor configuração de cada estratégia;
- preservação de todos os ativos solicitados;
- bloqueio de 12 horas no serviço e na API;
- conversão da coluna combinada salva anteriormente;
- exposição canônica do preço-teto por DY;
- cálculo relativo com pares locais e permissões fail-closed;
- presença do controle exclusivo do proprietário na Administração;
- identidade da versão, CI, documentos, token de cache e head Alembic.

## Resultado antes da publicação

Validação local do pacote:

- suíte integral: `378 passed`;
- JavaScript: sintaxe válida;
- `PUBLICAR_GITHUB.ps1 -ValidateOnly`: pacote validado;
- avisos: duas depreciações conhecidas de Authlib/Starlette, sem falhas.

Preencher após a execução no staging:

- suíte completa no contêiner: `PENDENTE`;
- `/testefdi/ready`: `PENDENTE`;
- homologação das valorações: `PENDENTE`;
- homologação das três estratégias distintas: `PENDENTE`;
- controle administrativo e trava de 12 horas: `PENDENTE`;
- autorização para produção: `PENDENTE`.

## Invariantes preservadas

Não há nova migração nem exclusão de snapshots, carteiras, análises,
permissões, resultados de backtests ou configurações de coluna. Métodos sem
insumos suficientes permanecem `N/D` e não recebem estimativas silenciosas.
