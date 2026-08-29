# Atualização Oracle V1.20.3

1. Publique o pacote pelo `PUBLICAR_GITHUB.ps1` no Windows.
2. Aguarde o timer ou, na Oracle, execute `./deployment/update-staging-from-github.sh`.
3. Valide `/testefdi/health` e `/testefdi/ready`.
4. No ambiente de teste, confira Padrão, FDI-CNPI, ALB, uma análise personalizada, o guia e as três estratégias de backtest.
5. Execute os testes versionados dentro do contêiner de staging.
6. Somente após aprovação explícita execute `./deployment/promote-staging-to-production.sh`.

Esta versão não cria tabelas nem colunas. Não altere o banco de produção manualmente.
