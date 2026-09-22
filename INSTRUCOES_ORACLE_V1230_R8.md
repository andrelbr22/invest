# Homologação Oracle — V1.23.0 R8

Esta revisão é aditiva. Ela não remove tabelas nem substitui carteiras,
filtros pessoais, credenciais, eventos, backtests ou configurações da R7.

## 1. Atualizar somente o ambiente de teste

```bash
cd ~/invest
./deployment/update-staging-from-github.sh
```

Esperado: imagem de staging construída, banco de teste copiado e isolado,
staging e proxy reiniciados e o endereço `/testefdi/` informado.

## 2. Validar prontidão e migração

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Esperado: versão `1.23.0`, ambiente `staging`, banco `reachable`, migração
`0027_v1_23_analysis_settings` e HTTP 200.

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine_staging -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('screening_preset_settings','analysis_column_settings') ORDER BY tablename;"
```

Esperado: duas linhas, `analysis_column_settings` e
`screening_preset_settings`.

## 3. Executar a regressão completa

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 tests_v1230 tests_v1231 -q -p no:cacheprovider
```

Esperado: todos os testes aprovados. Avisos de descontinuação das
bibliotecas HTTP não representam falha.

## 4. Homologação visual obrigatória

1. Abrir `/testefdi/plataforma/` e usar **Página principal**; confirmar que
   volta ao portal de teste e que a sessão permanece ativa.
2. Como proprietário, abrir **Administração > Filtros e colunas**.
3. Em uma classe, alterar e ativar a configuração alternativa de Padrão,
   FDI ou ALB; conferir o resultado e restaurar o padrão de fábrica.
4. Alterar a ordem/visibilidade padrão das colunas; conferir a tabela e
   restaurar o padrão.
5. Entrar com uma conta que não seja proprietária e confirmar que essa tela
   administrativa não aparece e que a API responde com acesso negado.
6. Abrir **Minha Carteira > Investimentos e Alocação** e conferir o gráfico
   de dois anéis. Clicar em um tipo e conferir o detalhamento por
   setor/segmento. Posições sem preço devem continuar indicadas como N/D.

## 5. Logs e promoção manual

```bash
docker compose -f docker-compose.oracle-web.yml logs --since 30m staging | grep -Ei "error|traceback|exception|failed" || echo "Nenhum erro encontrado no staging."
```

Somente após aprovação expressa:

```bash
./deployment/promote-staging-to-production.sh
```

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/ready
```

Esperado: versão `1.23.0`, ambiente `production`, banco `reachable`,
migração `0027_v1_23_analysis_settings` e HTTP 200.

