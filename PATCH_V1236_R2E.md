# Patch V1.23.6 R2E

## Objetivo

Eliminar falsos incidentes operacionais e controlar o espaço local sem
alterar dados funcionais, cálculos, permissões ou experiência de navegação.

## Correções

- todo resultado de trabalho é convertido para JSON seguro na fronteira da
  fila;
- o monitor ALB deixa de terminar como `TypeError` depois de salvar com
  sucesso datas e horários;
- SMTP usa 30 segundos e uma única retentativa para desconexões transitórias;
- fontes diárias respeitam o último horário programado, sem alarmes durante o
  intervalo legítimo entre execuções;
- cobertura de fundamentos e scores fica restrita aos pipelines de Ações e
  FIIs que realmente geram esses registros;
- após upload confirmado, a VM tenta manter somente os três backups locais
  mais recentes, mas remove cada arquivo antigo apenas se a sua própria cópia
  remota for confirmada. Nada é removido do Object Storage.

## Compatibilidade

- versão: `1.23.6`;
- migração: `0031_v123_latest_snapshot_idx`;
- nenhuma tabela, histórico ou snapshot é removido.
