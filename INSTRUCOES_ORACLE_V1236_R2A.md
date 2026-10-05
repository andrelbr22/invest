# Instruções Oracle — V1.23.6 R2A

1. Publique o pacote pelo PowerShell usando `PUBLICAR_GITHUB.ps1`.
2. No servidor Ubuntu, execute `./deployment/update-staging-from-github.sh`.
3. Confirme `/testefdi/ready`, commit do staging e ausência de marcador de falha.
4. Execute `python -m scripts.check_navigation_coverage` dentro do staging.
5. Execute a suíte oficial até `tests_v1236`.
6. Execute o benchmark de rotas com 20 amostras e duas de aquecimento.
7. Confirme que não há `QueuePool`, `InFailedSqlTransaction`, traceback ou
   `background_job_failed` nos logs novos do staging.
8. Faça a homologação visual antes de autorizar a promoção.

Resultado esperado: cobertura integral, testes aprovados, metas de p95
atendidas e processamento em segundo plano sem falhas de pool ou transação.
