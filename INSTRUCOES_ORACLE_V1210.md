# Homologação da V1.21.0 na Oracle

## 1. Publicação inicial

1. No Windows, extraia o ZIP em uma pasta nova e vazia.
2. Execute `powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly`.
3. Somente após conferir a validação e receber autorização, execute o mesmo script sem `-ValidateOnly`.
4. Na Oracle, atualize exclusivamente o staging com `./deployment/update-staging-from-github.sh`.
5. Não execute a promoção nesta etapa.

## 2. Saúde e migração esperadas

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

O retorno deve informar:

- `status: ready`;
- `version: 1.21.0`;
- `environment: staging`;
- `database: reachable`;
- `migration: 0020_v1_21_valuation_access`.

## 3. Testes automatizados

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 -q -p no:cacheprovider
```

Os avisos de descontinuação de bibliotecas podem aparecer, mas não deve existir teste com falha.

## 4. Roteiro visual obrigatório

1. Confirme que todos os painéis já homologados da V1.20.7 abrem normalmente.
2. Em Mercado e Análises, abra Ações e FIIs e confirme as quatro famílias de valoração.
3. Teste cada família isoladamente e depois duas famílias com as opções `todas` e `qualquer uma`.
4. Confirme cenários conservador, base e otimista, qualidade, premissas e mensagens `N/D`.
5. Confirme que Graham não calcula com LPA/VPA negativos e que FIIs não recebem Graham.
6. Confirme que ETFs, BDRs e futuros não recebem uma fórmula inadequada; deve aparecer o motivo da indisponibilidade.
7. Em Administração, libere as quatro autorizações separadamente para uma conta de teste.
8. Entre com essa conta e confirme que só aparecem filtros e colunas autorizados.
9. Libere ALB e confirme que as quatro famílias ficam disponíveis automaticamente.
10. Remova ALB e as permissões individuais e confirme que os valores protegidos deixam de ser retornados.
11. Em Backtests, confirme as 13 estratégias e abra a explicação de cada regra.
12. Rode Supertrend ATR, Momentum dual relativo e Bollinger Squeeze individualmente.
13. Combine duas ou três estratégias, conforme o limite da conta, e valide Compra, Venda ou Neutra separada de Investido/Fora.
14. Teste tendências diária/semanal/mensal com MMS 8, MME 9, MMS 21, MMS 50 e MMS 200.
15. Teste volume, RSI, ADX, ATR, MACD, Bollinger, força relativa, pivôs e liquidez.
16. Navegue para outro painel durante o processamento e confirme que o site não trava.
17. Confira histórico, métricas, operações e exportação dos resultados.
18. Valide em computador e celular.

## 5. Validação operacional

```bash
docker compose -f docker-compose.oracle-web.yml ps
docker compose -f docker-compose.oracle-web.yml logs --since 15m staging | grep -Ei "error|traceback|exception|unhealthy" || echo "Nenhum erro encontrado no staging."
```

Não coloque chaves, senhas ou conteúdo de `deployment/secrets` no GitHub ou em mensagens.

## 6. Produção

Somente depois da validação completa e de uma nova frase explícita de aprovação execute:

```bash
./deployment/promote-staging-to-production.sh
```

Depois confira `/ready`, todos os serviços e os logs do worker. Qualquer aprovação concedida a uma versão anterior não autoriza a V1.21.0.
