# Homologação Oracle — V1.23.1 R1

Esta revisão deve passar primeiro pelo ambiente de teste. Não promova para
produção antes da regressão, da validação visual e da aprovação expressa.

## 1. Atualizar somente o staging

```bash
cd ~/invest
./deployment/update-staging-from-github.sh
```

Esperado: construção concluída, banco de teste copiado e isolado, staging e
proxy iniciados e o endereço `/testefdi/` informado.

## 2. Conferir prontidão

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Esperado: versão `1.23.1`, ambiente `staging`, banco `reachable`, migração
`0027_v1_23_analysis_settings` e HTTP 200.

## 3. Regressão completa

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest -q -p no:cacheprovider
```

Esperado: todos os testes aprovados. Avisos de descontinuação das bibliotecas
HTTP não representam falha.

## 4. Medir as rotas principais

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.benchmark_application_routes --samples 20 --warmup 2
```

Esperado: cinco linhas para health, dashboard, screener 50, screener 100 e
detalhe do ativo, todas terminadas em `OK`. Se houver `ACIMA_DA_META`, não
promova antes de repetir a medição e investigar a causa.

## 5. Validação visual

1. Abrir a página principal e a plataforma em `/testefdi/`.
2. Alternar entre Painel de Mercado, Mercado e Análises, Carteira,
   Backtests, Notícias, Alertas e Administração.
3. Confirmar que dados aparecem sem uma atualização forçada a cada troca.
4. Usar o botão de atualização manual do Painel de Mercado e confirmar que o
   trabalho é acompanhado até a conclusão.
5. Confirmar filtros Padrão, FDI, ALB e personalizados, detalhes de ativo,
   gráficos da carteira, alertas, eventos e backtests.
6. Recarregar a página e confirmar que CSS, JavaScript e capas correspondem
   à R1, sem mistura visual com a versão anterior.

## 6. Logs e contêineres

```bash
docker compose -f docker-compose.oracle-web.yml ps
```

Esperado: `app`, `postgres`, `staging` e `worker` saudáveis; `proxy` ativo.

```bash
docker compose -f docker-compose.oracle-web.yml logs --since 30m staging | grep -Ei "error|traceback|exception|failed|unhealthy" || echo "Nenhum erro encontrado no staging."
```

Esperado: `Nenhum erro encontrado no staging.`

## 7. Promoção manual

Somente após aprovação expressa:

```bash
./deployment/promote-staging-to-production.sh
```

O próprio script repetirá o benchmark como gate antes de tocar a produção.
Esperado: cinco linhas terminadas em `OK`, seguidas do backup e da promoção.
Se aparecer `ACIMA_DA_META`, a promoção será interrompida sem backup, troca de
imagem ou recriação do site.

Depois:

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/ready
```

Esperado: versão `1.23.1`, ambiente `production`, banco `reachable`, migração
`0027_v1_23_analysis_settings` e HTTP 200.
