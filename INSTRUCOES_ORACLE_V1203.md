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

## Validação adicional da R4

1. Em Painel de Mercado > Mercados globais, confirme Bolsas globais à esquerda e os dois painéis menores empilhados à direita.
2. Confirme o nome `Criptos e Câmbio`.
3. No Comparador histórico, confira a ordem das 26 opções, a separação visual e somente CDI, Ibovespa e IFIX inicialmente marcados.
4. Selecione índices de diferentes regiões, Prata, VIX e DXY e alterne os períodos do gráfico.
5. Passe o cursor sobre IMA-B, IRF-M e MSCI Europe e confirme que os proxies estão identificados.
6. Valide também em tela estreita antes de aprovar a produção.

## Validação adicional da R5

1. Abra `Painel de Mercado > Comparador histórico` no ambiente de teste.
2. Clique em `Atualizar séries` e aguarde a conclusão em segundo plano.
3. Confirme dados para CDI, Poupança, IPCA, INPC, IGP-M, IGP-DI, INCC e IPC-Fipe.
4. Troque o período entre 1 ano e 20 anos e confirme que o gráfico continua responsivo.
5. Execute os testes versionados antes de aprovar a produção.

## Validação adicional da R6

1. No Comparador histórico, confira meses e anos no eixo para 6 meses, 1 ano e 5 anos.
2. Confira somente anos para 10, 15 e 20 anos.
3. Clique em `Personalizar`, escolha datas válidas em `De` e `Até` e confirme o novo recorte.
4. Inverta temporariamente as datas e confirme a mensagem de orientação, sem quebra do painel.
5. Volte a um período rápido e confirme que o modo personalizado é encerrado.
6. Confirme que `Atualizar séries` continua atualizando as fontes em segundo plano.

## Validação adicional da R7

1. Atualize somente o ambiente `/testefdi` e confirme `/testefdi/ready` antes de qualquer promoção.
2. Abra cada aba do Painel de Mercado e confira o quadro `Atualizações deste painel`, com fonte, última atualização, estado e próxima rodada.
3. Clique duas vezes em `Atualizar agora` em menos de cinco minutos e confirme que a segunda solicitação informa o intervalo de segurança, sem duplicar trabalho.
4. Abra Mercado e Análises, Carteiras > Posições, Carteiras > Notícias, Backtests e Administração > Dados de mercado e confira as datas correspondentes.
5. Confirme que o site continua navegável enquanto uma atualização estiver `Na fila` ou `Atualizando`.
6. Execute os testes versionados. O resultado local esperado para este pacote é `59 passed`.
7. Antes de promover, leia `RELATORIO_ATUALIZACOES_V1203_R7.md` e valide os horários nele registrados.
8. Após aprovação explícita, execute a promoção manual. O script inicia primeiro a aplicação, depois o worker, e somente conclui quando ambos estiverem saudáveis.
9. Confira que `docker compose -f docker-compose.oracle-web.yml ps` apresenta `app`, `worker`, `postgres`, `proxy` e `staging`; `app` e `worker` devem estar `healthy`.

Esta revisão cria somente a tabela de controle das partes entregues. Ela não altera nem exclui resultados existentes. Não altere o banco de produção manualmente.
# Complemento R8 — rede do worker e scripts executáveis

A R8 corrige a saída de rede do worker permanente. O serviço passa a participar da rede `frontend`, usada para DNS e HTTPS das fontes externas, e da rede `backend`, mantida como rede interna para acesso isolado ao PostgreSQL.

Depois da atualização do ambiente de teste, confirme:

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest -q -p no:cacheprovider
```

Na promoção, o publicador preserva no Git a permissão executável de todos os arquivos `.sh`, mesmo quando o pacote é enviado pelo Windows. Após a promoção, valide o worker:

```bash
docker compose -f docker-compose.oracle-web.yml exec -T worker python -c 'import socket; print(socket.gethostbyname("api.bcb.gov.br"))'
docker compose -f docker-compose.oracle-web.yml ps
```

O worker deve estar `healthy` e a resolução deve retornar um endereço IP. O banco continua restrito à rede interna e não publica a porta 5432 na internet.
