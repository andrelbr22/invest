# Relatório de validação da V1.21.3

## Escopo verificado automaticamente

- metadados da versão e cabeça única da migração;
- criação e propagação de níveis compartilhados;
- precedência do bloqueio individual;
- preservação integral das permissões de contas legadas;
- rotas de níveis, usuários, atribuição em lote, exceções, fila, reprocessamento e monitor;
- presença das 24 permissões e das 13 rotinas na interface administrativa;
- intervalos exatos de 5 e 30 minutos e janela de negociação da B3;
- catálogo ampliado de ativos alertáveis;
- interface integral de alertas;
- tela de recomendações e solicitação diária no primeiro acesso autenticado;
- sintaxe JavaScript e Python;
- compatibilidade dos testes das versões anteriores;
- ausência de erros de espaços em branco no diff.

## Resultado local

Regressão integral executada localmente: **159 testes aprovados e nenhuma falha**. Permaneceram somente três avisos de descontinuação de dependências, sem impacto funcional. A mesma regressão deve ser repetida no contêiner do staging depois da publicação autorizada.

## Itens que dependem de homologação no ambiente de teste

- envio SMTP real para um e dois destinatários;
- criação, edição, pausa, reativação e histórico de alertas;
- atualização diária ao autenticar uma conta autorizada pela primeira vez no dia;
- tela de recomendações com Brasil/exterior;
- propagação de uma permissão de nível para uma conta secundária;
- atribuição individual e em lote sem alterar a conta proprietária;
- exibição e acionamento das 13 rotinas;
- fila, reprocessamento e monitor manual de alertas;
- ausência de exceções nos registros do staging.

## Regra de liberação

A produção permanece bloqueada até que todos os itens visuais sejam homologados e haja uma nova aprovação expressa para promover a V1.21.3.
