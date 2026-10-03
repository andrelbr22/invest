# Relatório de validação • V1.23.5 R2A

## Escopo

Correção operacional de baixo risco sobre a R2, sem alteração de banco ou da
experiência funcional. A validação cobre o identificador real de cada
liderança, a rejeição de identidades estrangeiras ou malformadas, a espera de
convergência e os comandos de homologação/publicação.

## Validações automatizadas • 03/10/2026

- testes focados da correção: **40 aprovados**;
- regressão funcional completa: **435 aprovados**, com um aviso de depreciação
  conhecido e sem falhas;
- sintaxe Python: **240 arquivos** analisados com sucesso;
- sintaxe dos dois arquivos JavaScript: aprovada;
- validação do publicador: `Pacote validado. Nenhum arquivo foi enviado.`;
- integridade do ZIP: **412 arquivos** extraídos e comparados por SHA-256 com a
  origem, sem ausências ou divergências; o publicador extraído também foi
  validado em modo `ValidateOnly`.

## Casos operacionais cobertos

1. Scheduler local e remoto com identidade canônica.
2. Monitor local e remoto com ambiente, nó e PID positivo.
3. Rejeição de nó, ambiente, serviço, metadado ou PID divergente.
4. Rejeição de PID vazio, zero, negativo, não numérico, Unicode ou com sufixo.
5. Espera limitada pela convergência do worker e das leases.
6. Validação do commit antes da consulta SQL do ciclo.
7. Preservação do log de uma promoção ativa.

## Critério de homologação na Oracle

Promover somente se a regressão completa, o benchmark, a cobertura materializada
e a inspeção visual da R2 continuarem aprovados. A segunda VM permanece uma
operação separada: este patch não cria recursos OCI nem muda a localização do
worker automaticamente.
