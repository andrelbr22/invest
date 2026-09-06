# Relatório de validação — V1.21.0

## Resultado

A versão candidata foi validada localmente sem publicar ou alterar o ambiente de teste.

- **128 testes aprovados**;
- nenhum teste com falha;
- sintaxe do JavaScript aprovada pelo Node.js;
- módulos Python e migrações compilados sem erro;
- árvore de migrações com um único topo: `0020_v1_21_valuation_access`;
- migração completa, de `0001` a `0020`, validada em banco vazio;
- pacote verificado sem `.git`, ambiente virtual, banco local, cache, senha ou chave.

Os três avisos da suíte são avisos de descontinuação de dependências (`Authlib`, `Starlette` e `AnyIO`) e não representam falha funcional.

## Cobertura acrescentada

- fórmulas e aplicabilidade das quatro famílias de valoração;
- cenários, amostra mínima, pares comparáveis, outliers e unidades de FIIs;
- combinações `todas` e `qualquer uma` no screener;
- bloqueio individual e herança das quatro permissões pelo perfil ALB;
- remoção, no servidor, de resultados de valoração não autorizados;
- catálogo, parâmetros, limites e relações das 13 estratégias;
- validação de todas as 200 combinações da grade oficial;
- execução em `t+1`, pivôs sem antecipação e OHLC ajustado;
- benchmark externo para sinais relativos sem alterar o buy-and-hold do próprio ativo;
- sinal atual separado da posição e profit factor monetário;
- rotas síncronas protegidas e processamento normal de usuários pela fila;
- elementos da interface para quatro métodos, cenários e parâmetros de estratégia.

## Próxima etapa

O ZIP deve ser validado com `PUBLICAR_GITHUB.ps1 -ValidateOnly`. Depois disso, qualquer envio ao GitHub ou ao staging depende de autorização expressa. A promoção para produção exige uma segunda aprovação, concedida somente após a homologação visual e funcional em `/testefdi`.
