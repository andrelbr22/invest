# Patch V1.23.6 R2C

## Incidente

Na instalação da R2B, o executor obteve a trava consultiva em uma transação
que permaneceu aberta. O `CREATE INDEX CONCURRENTLY`, executado por outra
conexão, precisava aguardar snapshots anteriores e encontrou a própria sessão
coordenadora. As duas tentativas terminaram por `lock timeout`; o staging foi
mantido parado e a produção não foi alterada.

## Correção

- a trava consultiva continua sendo exclusiva e vinculada à sessão;
- a conexão coordenadora usa `AUTOCOMMIT` e não conserva snapshot transacional;
- desbloqueio e verificação exata da revisão continuam obrigatórios;
- a migração R2B permanece repetível após a tentativa interrompida.

Não há nova migração. A revisão esperada continua
`0031_v1_23_latest_snapshot_indexes`.
