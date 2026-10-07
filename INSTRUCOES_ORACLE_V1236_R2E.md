# Instruções Oracle — V1.23.6 R2E

1. Publique o pacote em pasta limpa com `PUBLICAR_GITHUB.ps1`.
2. Atualize o staging uma única vez com
   `deployment/update-staging-from-github.sh`.
3. Confirme `/testefdi/ready` com versão `1.23.6` e migração
   `0031_v123_latest_snapshot_idx`.
4. Execute todos os testes até `tests_v1236` e o benchmark obrigatório.
5. Valide no staging o monitor ALB e a atualização da qualidade de dados.
6. Promova somente após aprovação manual.

Na promoção, o backup novo é criado e enviado primeiro. Cada backup local
antigo só é removido depois que a sua cópia específica é confirmada no Object
Storage; arquivos sem cópia remota permanecem preservados. O número recente
pode ser ajustado entre 1 e 30 por `LOCAL_BACKUP_KEEP_COUNT`; o padrão
aprovado é 3.
