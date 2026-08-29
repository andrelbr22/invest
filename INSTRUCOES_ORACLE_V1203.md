# Atualização Oracle V1.20.3

1. Publique o pacote pelo `PUBLICAR_GITHUB.ps1` no Windows.
2. Aguarde o timer ou, na Oracle, execute `./deployment/update-staging-from-github.sh`.
3. Valide `/testefdi/health` e `/testefdi/ready`; a migração esperada na R1 é `0013_v1_20_backtest_study`.
4. No ambiente de teste, confira Padrão, FDI-CNPI, ALB, uma análise personalizada, o guia, as três estratégias por ativo e a aba Backtests > Estudos.
5. Em Estudos, clique em uma estratégia e confira suas configurações completas, sem códigos JSON ou valores técnicos sem tradução.
6. Execute os testes versionados dentro do contêiner de staging.
7. Somente após aprovação explícita execute `./deployment/promote-staging-to-production.sh`.

Esta versão não cria tabelas nem colunas e não altera resultados existentes. O novo índice é criado automaticamente. Não altere o banco de produção manualmente.
