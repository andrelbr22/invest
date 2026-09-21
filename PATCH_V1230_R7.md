# V1.23.0 R7 — calibração ALB e proventos oficiais

Esta revisão consolida a rota oficial de Fundos Listados da B3 introduzida
na R6 e atualiza de forma explícita o preset ALB para a versão 1.1.

## ALB 1.1

Os critérios foram medidos no banco isolado do staging em 21/09/2026. O
cenário escolhido retornou 15 ativos, dentro da faixa desejada de 5 a 20:

- ROE mínimo: 15%;
- margem líquida mínima: 8%;
- P/L: positivo e no máximo 15;
- P/VP máximo: 2,5;
- dividend yield mínimo: 5%;
- liquidez corrente mínima: 1;
- liquidez financeira diária mínima: R$ 2 milhões;
- preço abaixo do Número de Graham.

Não foi aplicado limite artificial de quantidade. O monitor continua
alertando se a população natural sair da faixa e nunca altera o preset.

## Homologação

1. A suíte completa deve permanecer aprovada.
2. A rotina de proventos deve retornar `complete`, sem erros, e receber os
   eventos oficiais do XPML11.
3. O monitor ALB deve retornar `preset_version: 1.1`, `asset_count: 15` e
   `status: within_range` com a cópia atual do banco de produção.
