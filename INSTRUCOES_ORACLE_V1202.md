# Atualização Oracle V1.20.2

1. Publique o pacote pelo `PUBLICAR_GITHUB.ps1` no Windows.
2. Na Oracle, execute `./deployment/update-staging-from-github.sh` caso o timer ainda não tenha concluído.
3. Valide `/testefdi/health`, `/testefdi/ready` e as abas do Painel de Mercado.
4. Confira especialmente IPCA, cinco pares de câmbio, curva DI x Pré, comparador histórico e agenda eleitoral.
5. Somente após aprovação explícita execute `./deployment/promote-staging-to-production.sh`.

Não altere o banco de produção manualmente. Esta versão não cria tabelas nem colunas novas.
