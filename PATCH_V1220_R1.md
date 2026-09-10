# Patch V1.22.0 R1

Correção de homologação para execução da suíte completa dentro do contêiner de staging:

1. o teste administrativo usa `localhost`, que pertence à lista segura de todos os ambientes, e substitui explicitamente a dependência de proprietário;
2. o bloqueio de `Host` inválido continua ativo e não passou a aceitar `testserver` em produção;
3. `.gitignore` e os modelos públicos `deployment/runtime/*.env.example` permanecem disponíveis na imagem para auditoria;
4. arquivos reais `deployment/runtime/*.env`, segredos, chaves e bancos continuam fora da imagem;
5. a suíte integral permanece com 212 testes aprovados.
