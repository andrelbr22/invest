# Relatório de validação V1.21.2

## Verificações locais

- cálculo unitário de NAV de ETF e reversão correta do prêmio/desconto;
- cenários relativos de ETF com separação por moeda e amostra mínima;
- valuation P/VP de BDR restrito a indústria/setor comparável;
- paridade de BDR fechada quando lastro, câmbio ou razão estiver ausente;
- custo de carregamento de futuro fechado sem spot, taxa ou vencimento;
- escolha do contrato frontal não vencido no scanner de futuros;
- integração do screener com valores reais de ETF;
- interface e permissões específicas por classe;
- regressão completa das versões V1.16 a V1.21.

## Homologação ainda necessária

O ZIP deve passar pelo modo `-ValidateOnly`, ser publicado somente no ambiente de teste, atualizar o catálogo no staging e cumprir o roteiro de `INSTRUCOES_ORACLE_V1212.md`. A produção permanece bloqueada até aprovação explícita posterior.
