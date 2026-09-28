# Segunda VM — endurecimento operacional da V1.23.2

Esta entrega prepara o código para mover **somente o worker**. Ela não cria,
altera nem exclui recursos na Oracle Cloud. A VM, VNIC, NSGs e regras de rede
continuam exigindo uma janela aprovada pelo proprietário.

## Invariantes de segurança

- Existe um único PostgreSQL gravável, na VM principal.
- A VM2 usa `investment_worker`, sem superuser, criação de banco, função,
  schema ou objeto. Ela conserva somente leitura e DML porque as rotinas do
  worker gravam fila, snapshots, indicadores, eventos, alertas e backtests.
- O PostgreSQL é alcançado pelo IP privado da VM1 na porta 5432 e a NSG aceita
  origem somente da NSG da VM2.
- A VM2 executa exatamente um commit publicado em `origin/main`, em checkout
  limpo e destacado. Alterações locais bloqueiam o procedimento.
- A chave SSH, o arquivo `known_hosts` e `worker-location.env` usam modo 0600,
  pertencem ao usuário de implantação e não podem ser links simbólicos.
- O SSH rejeita chave de host desconhecida ou alterada; não existe aceite
  automático de fingerprint.
- Depois de cada corte ou retorno, a operação exige um worker fresco, uma lease
  de scheduler e uma lease de monitor, todas no nó e commit esperados.
- O contêiner remoto roda como UID/GID 10001, filesystem somente leitura,
  capabilities removidas, `no-new-privileges`, sem portas e com `/tmp` isolado.

## Retorno automático

O guardião é entregue **desativado**. Instalar seu timer não muda esse estado.
Quando habilitado manualmente, ele exige no mínimo três falhas consecutivas,
usa trava exclusiva e chama o mesmo failback conservador do operador. Se o SSH
cair mas o heartbeat remoto continuar fresco, o retorno é recusado. O guardião
nunca transfere o worker automaticamente de volta à VM2.

## Critério de ativação

Ative a VM2 somente depois de homologar a V1.23.2 na VM principal, confirmar
backup e executar um ciclo completo de corte, failback e novo corte. Durante os
sete primeiros dias, mantenha `FDI_AUTO_FAILBACK_ENABLED=false`; prefira retorno
manual acompanhado. O staging continua na VM1 até uma decisão posterior.
