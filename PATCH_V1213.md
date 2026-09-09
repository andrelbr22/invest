# Patch V1.21.3

## Interface de alertas

- Substituída a visualização resumida por uma interface integral de cadastro, edição, ativação, pausa e histórico.
- Incluídos pesquisa assistida do ativo, permissão separada para cada condição, segundo e-mail opcional e envio de teste.
- Centralizados os intervalos do monitor: 5 minutos para B3 e 30 minutos para demais mercados.
- Ampliado o catálogo com índices brasileiros, moedas e criptoativos já utilizados pelo Painel de Mercado.

## Notícias

- Incluída a tela de notícias de recomendações, separada das notícias dos ativos da carteira.
- Incluídos filtros Brasil/exterior e apresentação de fonte e horário.
- A atualização diária é solicitada após autenticação e processada pelo worker, sem bloquear a navegação.

## Permissões e usuários

- Criada a administração por níveis compartilhados, incluindo convidados, acesso básico, membros, membros VIP e proprietário.
- Expostas todas as 24 permissões e os 6 limites atualmente aplicados pelo sistema.
- Incluídos criação e edição de níveis, atribuição individual/em lote, busca, filtros, paginação e remoção de exceções.
- Dependências de permissão são fechadas automaticamente; sem acesso ao módulo pai, recursos filhos e respectivos limites são desabilitados.
- Uma redução de permissão também desativa alertas excedentes ou condições que deixaram de ser autorizadas.

## Atualizações e operação

- O administrador passa a visualizar e acionar as 13 rotinas: Selic atual, Focus, macroeconomia, mercados globais, juros/agenda, criptoativos, câmbio, manchetes, comparador histórico, catálogo, fundamentos, técnica diária e técnica intradiária.
- Incluídos fila dos trabalhos recentes, reprocessamento de falhas e execução manual do monitor de alertas.

## Segurança e migração

- Criada a migração `0021_v1_21_access_levels`.
- Apenas contas de proprietário são vinculadas automaticamente ao nível permanente.
- As demais contas históricas permanecem em modo legado, sem alteração silenciosa dos acessos.
- Segredos, tokens e senhas não fazem parte do pacote.

