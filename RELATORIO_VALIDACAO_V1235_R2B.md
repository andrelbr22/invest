# Relatório de validação • V1.23.5 R2B

## Escopo

Correção do bootstrap da promoção, preservando integralmente a R2A.

## Evidência do ambiente

- host, `origin/main` e staging estavam no mesmo commit R2A;
- o arquivo do host já continha a validação nova;
- o erro exibido correspondia exclusivamente à cópia R2 dentro do contêiner
  de produção anterior;
- não havia trabalho `running` ou `queued` no staging;
- a cobertura materializada era 2266/2266 em todas as projeções;
- o benchmark repetido aprovou todas as rotas, inclusive screener 100 com
  p95 de 1093,07 ms para uma meta de 3000 ms.

## Validação local • 03/10/2026

- testes focados da transição: **41 aprovados**;
- regressão completa: **436 aprovados**, com um aviso de depreciação conhecido;
- sintaxe Python e JavaScript: verificada antes da compactação;
- publicador: validado em modo `ValidateOnly`;
- integridade do ZIP: comparada arquivo a arquivo depois da compactação.
