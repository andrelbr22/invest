# V1.23.0 R5 — correção das verificações de homologação

## Correções

- o teste de metadados deixou de exigir a identificação antiga da R2 e agora
  valida o publicador da revisão atual;
- a verificação PostgreSQL da consulta de proventos passou a reconhecer a
  forma parentizada de `EXISTS` gerada pelo SQLAlchemy;
- não houve alteração na lógica de negócio homologada na R4.

## Resultado esperado

A suíte completa deve concluir com 275 testes aprovados e apenas os avisos de
depreciação já conhecidos.
