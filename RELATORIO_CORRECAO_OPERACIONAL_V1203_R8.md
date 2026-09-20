# Relatório da correção operacional V1.20.3 R8

## Resultado

A R8 corrige a conectividade das rotinas automáticas introduzidas na R7 sem alterar tabelas, dados de usuários, regras de negócio ou a interface.

## Causa identificada

O worker permanente estava conectado somente à rede Docker `backend`. Essa rede é intencionalmente marcada como interna para proteger o PostgreSQL e, por isso, não oferece saída DNS/HTTPS. A aplicação web continuou saudável, mas o worker não conseguia consultar Banco Central, Yahoo Finance, TradingView, Fundamentus e outras fontes.

O mecanismo de tolerância a falhas funcionou: o site permaneceu disponível, os resultados válidos anteriores foram preservados e apenas os trabalhos de fundamentos e indicadores técnicos terminaram em falha após as tentativas automáticas.

## Correção

- o worker passa a participar de `frontend` e `backend`;
- `frontend` fornece DNS e saída HTTPS para as fontes públicas;
- `backend` continua interna e atende somente a comunicação com o PostgreSQL;
- o worker não publica portas externas e não recebe tráfego do proxy;
- os dois trabalhos afetados foram reenfileirados e concluídos com sucesso.

## Publicação pelo Windows

Também foi corrigida a perda do bit executável dos scripts `.sh` durante a publicação no Windows. O `PUBLICAR_GITHUB.ps1` agora registra esses arquivos como executáveis no índice do Git antes do commit, usando uma implementação compatível com Windows PowerShell 5.1.

## Validação

- resolução DNS confirmada no worker para Banco Central, Yahoo Finance, TradingView e Fundamentus;
- fundamentos: `succeeded`;
- indicadores técnicos: `succeeded`;
- suíte automatizada: 61 testes aprovados;
- nenhuma migração nova;
- nenhuma exclusão ou alteração de dados persistidos.

## Situação da produção antes da R8

A conexão externa foi restaurada emergencialmente no container em execução, sem reiniciar o site ou o banco. Essa conexão manual seria perdida na próxima recriação do worker; por isso a R8 é necessária como correção permanente no compose.
