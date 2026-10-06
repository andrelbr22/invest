# Instruções Oracle — V1.23.6 R2B

## Windows PowerShell

1. Extraia o ZIP oficial em uma pasta nova e vazia.
2. Entre nessa pasta.
3. Execute `powershell -NoProfile -ExecutionPolicy Bypass -File
   .\PUBLICAR_GITHUB.ps1 -ValidateOnly`.
4. Depois da mensagem de validação, execute `powershell -NoProfile
   -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1`.

Resultado esperado: `PUBLICACAO CONCLUIDA` e orientação para validar a
V1.23.6 R2B em `/testefdi`.

## Ubuntu — atualização do ambiente de teste

1. Entre em `~/invest`.
2. Execute `./deployment/update-staging-from-github.sh` apenas uma vez.
3. Aguarde o processo terminar. A migração pode demorar enquanto constrói os
   quatro índices concorrentes.
4. Confirme que `/testefdi/ready` informa versão `1.23.6`, ambiente `staging`,
   banco acessível e migração `0031_v123_latest_snapshot_idx`.

## Homologação obrigatória

1. Confirme que os quatro índices `ix_*_latest_desc` existem e estão válidos.
2. Inicie um ciclo de métricas para o commit do staging.
3. Aguarde `cycle_completed=true`.
4. Exija `MAX(attempts)=1`, nenhuma falha e nenhuma ocorrência de `statement
   timeout` nos logs novos.
5. Confirme cobertura integral com `scripts.check_navigation_coverage`.
6. Execute a suíte oficial até `tests_v1236`.
7. Execute o benchmark com vinte amostras e duas de aquecimento.
8. Homologue visualmente os painéis antes de autorizar a produção.

Somente depois de todos esses resultados estarem corretos execute a promoção
manual. Não promova a R2A atualmente instalada no staging.
