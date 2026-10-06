# Instruções Oracle — V1.23.6 R2C

Publique o ZIP R2C por uma pasta limpa no Windows. No Ubuntu, execute
`./deployment/update-staging-from-github.sh` somente depois de confirmar que
não existe atualização em andamento. O novo commit faz o script reconstruir o
banco isolado e aplicar novamente a migração 0031 com a coordenação corrigida.

Resultados obrigatórios:

- `/testefdi/ready` em HTTP 200, versão `1.23.6`, ambiente `staging` e revisão
  `0031_v1_23_latest_snapshot_indexes`;
- quatro índices `ix_*_latest_desc` prontos e válidos;
- ciclo R2C completo com `MAX(attempts)=1`;
- cobertura integral, suíte oficial e benchmark aprovados;
- logs novos sem timeout ou falha de trabalho.

Não tente reativar manualmente o staging da R2B que falhou. Publique a R2C e
use novamente o procedimento oficial de atualização.
