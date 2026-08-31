# Homologação da V1.20.7 na Oracle

> Use a revisão R2 do pacote. Ela contém as melhorias de mercado, permissões, carteira e filtros de backtests solicitadas nesta etapa.

## 1. Publicação inicial

1. No Windows, extraia o ZIP em uma pasta nova.
2. Execute primeiro `powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly`.
3. Somente depois de conferir esta versão e receber autorização, execute o mesmo script sem `-ValidateOnly`.
4. Na Oracle, atualize exclusivamente o staging com `./deployment/update-staging-from-github.sh`.
5. Não execute a promoção nesta etapa.

## 2. Saúde e migração esperadas

Confirme no ambiente de teste:

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

O retorno deve informar:

- `status: ready`;
- `version: 1.20.7`;
- `environment: staging`;
- `database: reachable`;
- `migration: 0019_v1_20_access_rules`.

## 3. Testes automatizados

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 -q -p no:cacheprovider
```

## 4. Roteiro visual obrigatório

1. Em Backtests, solicite uma análise com dois ativos e duas estratégias. Navegue para outro painel enquanto processa, volte e confira progresso, resultado e CSV.
2. Confirme no administrador os limites de ativos, estratégias, uso diário e intervalo mínimo.
3. Em Minha Carteira, cadastre um investimento sem ticker, atualize seu valor e confira o histórico e o gráfico consolidado.
4. Cadastre ou atualize uma posição com peso-alvo e confira a sugestão de rebalanceamento. Tente um código fracionário terminado em `F` e confirme o bloqueio amigável.
5. Em Minhas Finanças, crie uma receita, uma despesa e um limite mensal. Confirme os quadros realizado, previsto e consumo do orçamento.
6. Entre com outro usuário autorizado e confirme que ele não visualiza os lançamentos financeiros nem os investimentos pessoais do primeiro.
7. No Painel de Mercado, abra a curva DI, alterne entre somente a atual, uma anterior e três anteriores. No primeiro dia, é normal ainda não haver curvas passadas.
8. No Comparador Histórico, alterne `Início comum` e `Histórico próprio`; confira retorno, volatilidade, datas e observações.
9. Force uma validação inválida e confirme mensagem compreensível, sem traceback, JSON ou detalhe de banco.
10. Confirme os painéis em computador e celular.
11. Confirme IFIX, IBrX 100, IBrX 50, IDIV e SMLL; fontes alternativas devem aparecer identificadas como proxy.
12. Confirme Bitcoin, Ethereum, Solana, Ripple (XRP) e BNB, além de BTC/ETH no Comparador Histórico.
13. Na curva DI, confirme títulos nos dois eixos e ausência da opção de 30 anos.
14. Em Administração, libere FDI, ALB, Graham e preço-teto separadamente para uma conta de teste. Confirme que ALB libera os dois filtros de valuation.
15. Entre com uma conta sem essas permissões: os botões FDI e ALB devem permanecer visíveis e desativados, e as colunas protegidas não devem aparecer.
16. Na carteira, grave Setor e Segmento em uma posição e em um investimento sem ticker.
17. Em Backtests, execute uma estratégia com tendência diária MMS 8, outra com MME 9, e combine RSI/ADX/volume sem bloquear a navegação.

## 5. Segunda instância

Os arquivos em `deployment/second-instance` são modelos, não uma ordem de implantação. Leia `ARQUITETURA_DUAS_INSTANCIAS_V1207.md`. Não abra a porta 5432 publicamente e não desligue o worker atual. A ativação exige segunda VM, IP privado, NSG restrito e uma homologação separada.

## 6. Produção

Somente depois da validação completa e de uma nova frase explícita de aprovação execute:

```bash
./deployment/promote-staging-to-production.sh
```

Depois confira `/ready`, os cinco serviços esperados e os logs do worker. A aprovação anterior da R8 não autoriza esta versão.
