# Instruções Oracle — V1.23.4

## 1. Publicar apenas no ambiente de teste

No Windows, extraia o ZIP para uma pasta nova, execute
`PUBLICAR_GITHUB.ps1 -ValidateOnly` e, depois da validação, execute
`PUBLICAR_GITHUB.ps1`. Aguarde a atualização automática ou rode no servidor:

```bash
cd ~/invest
./deployment/update-staging-from-github.sh
```

## 2. Verificações técnicas obrigatórias

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Resultado esperado: HTTP 200, versão `1.23.4`, ambiente `staging`, banco
acessível e migração `0029_v1_23_current_metrics`.

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 tests_v1230 tests_v1231 tests_v1232 tests_v1233 tests_v1234 -q -p no:cacheprovider
```

Resultado esperado: todos os testes aprovados; somente avisos de depreciação
já conhecidos podem permanecer.

## 3. Homologação visual e funcional

1. Abra `Mercado e Análises > Ações` com uma conta autorizada.
2. Confirme valores em Preço-teto DY-alvo quando houver preço e proventos TTM.
3. Confirme Valor relativo em setores com ao menos cinco pares válidos; uma
   amostra menor deve continuar como `N/D`.
4. Confirme as colunas `1º backtest`, `2º backtest` e `3º backtest`.
5. Abra ABEV3 ou outro ativo com catálogo oficial e confirme três estratégias
   distintas quando existirem três estratégias elegíveis.
6. Como proprietário, abra `Administração > Atualizações`; o cartão “Iniciar
   rodada oficial completa” deve aparecer também em `Backtests > Oficiais`.
7. Se a rodada anterior tiver menos de 12 horas, o botão deve ficar bloqueado
   e informar a próxima liberação. Não force o teste criando outra rodada.

## 4. Promoção

Promova somente depois da autorização explícita do proprietário:

```bash
cd ~/invest
./deployment/promote-staging-to-production.sh
```

Depois, valide `/ready`, os contêineres e os logs de `app` e `worker`. Nenhuma
migração nova é esperada nesta versão.
