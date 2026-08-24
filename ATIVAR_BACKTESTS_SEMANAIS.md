# Ativar os backtests semanais

Desde a V1.12.0, o GitHub não acessa o PostgreSQL de produção. Ele calcula em
um banco temporário e entrega os resultados por uma rota HTTPS autenticada.

Siga o guia atualizado:

`ATIVAR_ENTREGA_SEGURA_BACKTESTS_V1120.md`

O agendamento continua aos sábados às 00h01 de Brasília. O primeiro teste deve
ser feito pelo site, com somente um ativo. Não execute o workflow manualmente na
tela do GitHub, pois o pedido precisa ser registrado primeiro pela Oracle.
