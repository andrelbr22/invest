# Homologação da V1.21.2 na Oracle

## 1. Atualizar somente o ambiente de teste

Na Oracle, dentro de `/home/ubuntu/invest`, execute:

```bash
./deployment/update-staging-from-github.sh
```

Não execute a promoção para produção nesta etapa.

## 2. Validar saúde e testes

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

O retorno deve indicar versão `1.21.2`, ambiente `staging`, banco alcançável e migração `0020_v1_21_valuation_access`.

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 -q -p no:cacheprovider
```

## 3. Atualizar os novos insumos no banco de teste

Entre em `/testefdi`, abra **Administração → Atualização de dados** e clique em **Atualizar catálogo**. Aguarde o trabalho concluir. Esse passo coleta NAV/prêmio de ETFs, P/VP de BDRs e contratos/vencimentos dos futuros com o novo adaptador.

## 4. Roteiro visual obrigatório

Em **Mercado e Análises**:

1. abra **ETFs** e confirme que **Referência patrimonial do ETF (NAV)** e **Prêmio/desconto relativo ao NAV dos ETFs pares** estão habilitados para o proprietário;
2. confira que parte dos ETFs apresenta valor e potencial, enquanto linhas realmente sem NAV continuam N/D com explicação;
3. abra **BDRs** e confira valores relativos P/VP em ativos com ao menos cinco pares do mesmo setor/indústria;
4. confirme que a paridade com o lastro continua N/D quando preço do lastro, câmbio e razão não estiverem todos verificados;
5. abra **Futuros** e confira contrato frontal e vencimento; futuros de ações com lastro identificado devem exibir preço teórico usando a curva DI da B3 ou, se ela estiver indisponível, a Selic identificada como fallback;
6. confirme que Graham e preço-teto de dividendos continuam inativos para ETF e futuro;
7. aplique os filtros com lógica **Todos** e **Ao menos um** e confirme que nenhum N/D aprova um ativo artificialmente;
8. abra o detalhe de um ativo e confira método, fonte e atualização.

## 5. Conferência opcional no PostgreSQL de teste

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine_staging -c "SELECT asset_type, COUNT(*) FILTER (WHERE (metadata_json->>'nav_discount_premium_pct') IS NOT NULL) AS nav, COUNT(*) FILTER (WHERE (metadata_json->>'price_book_fq') IS NOT NULL) AS pbv, COUNT(*) FILTER (WHERE (metadata_json->>'front_contract') IS NOT NULL) AS contrato_frontal FROM assets WHERE asset_type IN ('etf','bdr','future') GROUP BY asset_type ORDER BY asset_type;"
```

## 6. Produção

Somente após a validação visual e nova aprovação explícita do proprietário:

```bash
./deployment/promote-staging-to-production.sh
```
