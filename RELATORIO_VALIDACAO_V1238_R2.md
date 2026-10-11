# Relatório de validação — V1.23.8 R2

## Controles cobertos pelo pacote

- scripts da segunda VM continuam fail-closed, com SSH por fingerprint, IP
  privado literal, função restrita do banco, commit exato e checkout limpo;
- o worker local é parado e fica com `restart=no` antes da ativação remota;
- cada transição exige exatamente um heartbeat de worker e as duas leases;
- o failback nunca inicia o worker local enquanto o remoto ainda está fresco;
- o ensaio automático exige a aprovação efêmera `V1.23.8-R2`, três falhas e
  não habilita permanentemente o guardião;
- os relatórios operacionais são 0600 e ficam em `deployment/runtime`, fora do
  Git e do ZIP;
- o bloqueio do navegador, depois de habilitado, não pode ser omitido por
  esquecimento em uma promoção futura;
- a coleta do PostgreSQL usa somente views de estatísticas e não executa DDL,
  reset de contadores ou alteração de parâmetros.

## Critérios obrigatórios antes da produção

1. suíte completa sem falhas;
2. benchmark interno com todos os p95 dentro das metas;
3. cobertura completa das métricas atuais;
4. navegação visual do staging;
5. linha de base do banco preservada;
6. após a configuração segura da sessão, benchmark Chromium válido no mesmo
   commit;
7. antes de declarar a VM2 operacional, relatórios válidos dos ensaios manual
   e automático e topologia final remota confirmada.

## Estado esperado

Versão `1.23.8`, migração `0032_v1237_browser_perf`, sem alteração de esquema.
O código R2 pode ir à produção inicialmente com o worker local. A mudança para
a VM2 é uma etapa operacional posterior e aprovada.

## Validação do pacote antes do ZIP

- `tests_v1238`: 16 testes aprovados;
- sintaxe Python: 267 arquivos analisados com sucesso;
- sintaxe dos módulos JavaScript alterados: aprovada;
- publicador em `-ValidateOnly`: pacote aprovado, nenhum arquivo enviado;
- arquivos de cache, credenciais, bancos locais e logs: ausentes;
- suíte histórica completa e benchmarks: obrigatórios novamente dentro do
  contêiner Linux do staging antes da aprovação de produção.

