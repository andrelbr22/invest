# Arquitetura de duas instâncias — V1.22.0

## Desenho aprovado

```text
Internet
   |
   v
VM1 — principal
  Caddy :80/:443
  FastAPI (portal + plataforma)
  FastAPI staging
  PostgreSQL único
       ^
       | TCP 5432, IP privado, NSG worker -> banco
       |
VM2 — processamento
  worker de fila
  scheduler eleito por lease
  monitor de alertas eleito por lease
  sem Caddy, sem site, sem staging, sem banco
```

O PostgreSQL da VM1 é a única fonte de verdade. A VM2 não recebe réplica improvisada, volume do banco nem porta web. Se ela cair, trabalhos permanecem na fila e o worker local pode reassumir.

## Forma recomendada

Preferência: `VM.Standard.A1.Flex`, 1 OCPU e 6 GB de RAM, Ubuntu 24.04 ARM64, quando houver cota e capacidade Always Free. O projeto usa Python 3.12 e dependências com suporte ARM; a imagem é construída na própria VM2. Alternativa: uma segunda `VM.Standard.E2.1.Micro`, aceitando que ela possui apenas 1 GB de RAM.

A disponibilidade gratuita depende da região inicial, cota e capacidade da conta. A documentação atual da Oracle informa até duas VMs E2.1.Micro e, para A1 Flex, uma franquia equivalente a 2 OCPUs e 12 GB de memória. Consulte [Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) antes de confirmar a criação.

## Rede

- Preferir VM2 na mesma VCN, região e, quando possível, mesmo domínio de disponibilidade.
- Criar `fdi-primary` e `fdi-worker` como Network Security Groups.
- Em `fdi-primary`, permitir entrada TCP 5432 com origem **NSG `fdi-worker`**, nunca `0.0.0.0/0`.
- Em `fdi-worker`, permitir entrada SSH 22 somente do IP administrativo `/32` ou usar OCI Bastion.
- A saída da VM2 precisa alcançar HTTPS para BCB, Yahoo, TradingView, Fundamentus, GitHub e SMTP; pode usar IP público ou rota NAT conforme a rede existente.
- O compose da VM1 vincula 5432 apenas ao IP privado da VNIC. A regra de NSG é uma segunda barreira.

NSGs aplicam regras somente às VNICs associadas e podem usar outro NSG como origem. Isso é preferível a uma liberação ampla por CIDR; veja [Network Security Groups](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm) e [Creating an NSG](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/create-nsg.htm).

## Coordenação

As leases `background-scheduler` e `price-alert-monitor-leader` ficam no banco. Somente o detentor vigente agenda rotinas ou coordena alertas. Uma lease expira se o processo parar de renovar. A lease `price-alert-monitor-cycle` impede sobreposição entre o ciclo automático e o botão manual.

O desenho tolera uma breve coexistência acidental de dois consumidores da fila porque o PostgreSQL usa bloqueio de linha com `SKIP LOCKED`. Isso não é o estado desejado: o painel abre uma ocorrência para mais de um worker fresco.

## Retorno

O script `failback-worker.sh` encerra graciosamente a VM2, inicia o worker local no commit de produção e só altera o indicador de localização depois que o healthcheck fica saudável. O teste de retorno é obrigatório no dia da migração.

Depois de sete dias estáveis, pode-se avaliar mover staging para a VM2. Isso não faz parte desta versão e exige nova homologação.

## Monitoramento em duas camadas

1. O watchdog da aplicação detecta fila, worker e dados e usa o e-mail já configurado.
2. OCI Monitoring deve detectar queda da própria VM, CPU e infraestrutura. O agente de Compute publica métricas e a Oracle permite associar alarmes e Notifications; veja [Compute Instance Metrics](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computemetrics.htm) e [Overview of Monitoring](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Concepts/monitoringoverview.htm).

