# Atualização Oracle V1.20.3

1. Publique o pacote pelo `PUBLICAR_GITHUB.ps1` no Windows.
2. Aguarde o timer ou, na Oracle, execute `./deployment/update-staging-from-github.sh`.
3. Valide `/testefdi/health` e `/testefdi/ready`; a migração esperada na R3 é `0014_v1_20_backtest_chunks`.
4. No ambiente de teste, confira Padrão, FDI-CNPI, ALB, uma análise personalizada, o guia, as três estratégias por ativo e a aba Backtests > Estudos.
5. Em Estudos, clique em uma estratégia e confira suas configurações completas, sem códigos JSON ou valores técnicos sem tradução.
6. Em Backtests > Rodadas oficiais, abra a rodada que falhou com HTTP 413 e clique em `Repetir somente os ativos pendentes`. O novo workflow deve indicar o ambiente `staging` e entregar os resultados a `/testefdi`.
7. Confirme que o progresso mostra partes recebidas e que nenhum resultado se repete se houver nova tentativa de uma parte.
8. Execute os testes versionados dentro do contêiner de staging.
9. Somente após aprovação explícita execute `./deployment/promote-staging-to-production.sh`.

Esta revisão cria somente a tabela de controle das partes entregues. Ela não altera nem exclui resultados existentes. Não altere o banco de produção manualmente.
