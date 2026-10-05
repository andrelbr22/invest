# Patch V1.23.6 R2A

## Correções

- staging com pool compatível com API, worker interno e heartbeats;
- notificações operacionais externas desativadas no ambiente de teste;
- timeout SMTP reduzido e falha de entrega tratada sem interromper a saúde;
- valuation e pódios protegidos por savepoints independentes;
- transação principal restaurável depois de uma falha transitória.

## Compatibilidade

- nenhuma migração nova;
- revisão esperada: `0030_v1_23_navigation_metrics`;
- sem remoção de dados, telas, filtros, fórmulas ou permissões;
- mantém integralmente os caches e otimizações da R2.
