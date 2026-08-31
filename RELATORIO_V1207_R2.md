# Relatório de implementação — V1.20.7 R2

Esta revisão é uma candidata de homologação. Ela não altera a produção enquanto não for validada em `/testefdi` e aprovada expressamente.

## Painel de Mercado

- IFIX preserva o nível oficial e completa somente as variações ausentes com XFIX11, sempre identificado como proxy.
- IBrX 100, IBrX 50, IDIV e SMLL usam primeiro o índice; BRAX11, PIBB11, DIVO11 e SMAL11 são contingências identificadas.
- O painel de criptoativos passa a conter BTC, ETH, SOL, XRP e BNB em dólar e real quando a fonte disponibilizar as cotações.
- BTC e ETH entram no Comparador Histórico.
- A curva DI mostra taxa anual no eixo vertical, vencimento em anos no horizontal e não oferece mais o recorte de 30 anos.
- Copom e Fed no mesmo dia formam uma única linha “Super Quarta”.
- Notícias passam a exibir até dez manchetes, fonte e data/hora informada pelo publicador.

## Mercado e Análises

- Padrão permanece aberto a todos que podem visualizar mercado.
- FDI e ALB possuem autorizações separadas.
- Graham e preço-teto de dividendos possuem autorizações separadas para filtro e colunas.
- ALB concede automaticamente Graham e preço-teto.
- As verificações são feitas na interface e também no servidor, evitando contorno por chamada direta da API.
- Os demais filtros gerais ficam ativos para quem visualiza o mercado.

## Carteira

- Posições com ticker aceitam Setor e Segmento opcionais, sem apagar a classificação original do catálogo.
- Investimentos sem ticker também aceitam Setor e Segmento.
- A tabela de alocação mostra a nova subcategoria.

## Backtests

- Tendências diária, semanal e mensal podem ser ativadas de forma independente.
- Médias disponíveis: MMS 8, MME 9, MMS 21, MMS 50 e MMS 200.
- Condições disponíveis: posição do preço, inclinação da média, confirmação conjunta ou alternativa.
- Combinação das tendências: todas, maioria ou qualquer uma.
- Filtros adicionais: RSI mínimo/máximo, ADX mínimo, relação de volume, ATR mínimo/máximo e saída por falha do filtro.
- Os cálculos usam apenas períodos concluídos e não antecipam observações futuras.

## Banco e segurança

- A migração `0019_v1_20_access_rules` é aditiva.
- Novas permissões começam desativadas para usuários existentes.
- Nenhuma credencial, segredo, banco local ou chave faz parte do pacote.
- O fluxo permanece GitHub → staging → aprovação manual → produção.

## Validação local

- `81 passed` na suíte integral;
- JavaScript validado sintaticamente;
- módulos Python compilados;
- Alembic com um único head: `0019_v1_20_access_rules`.
