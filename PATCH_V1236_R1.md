# Patch V1.23.6 R1

## Objetivo

Melhorar o tempo percebido de navegação com alterações de baixo risco e sem
perder recursos já homologados.

## Alterações técnicas

1. **Carteira sem N+1**
   - todas as posições são lidas uma vez;
   - os preços efetivos são resolvidos em no máximo duas consultas em lote;
   - o mesmo fallback escalar foi mantido para compatibilidade.

2. **Consultas de navegação menores**
   - a cobertura materializada usa anti-join/`NOT EXISTS`;
   - listas ETF, BDR e futuros evitam transportar documentos que não são
     necessários para o painel;
   - rotinas analíticas e de reconstrução continuam podendo solicitar o
     registro completo.

3. **Painel de Mercado**
   - o cache legado continua sendo recuperação para snapshot ausente;
   - com cobertura completa, uma consulta e a desserialização do JSON antigo
     são eliminadas;
   - consultas `latest` passam a ser limitadas a uma linha no banco.

4. **Renderização progressiva**
   - a lista principal continua aparecendo antes dos sinais secundários;
   - quando os backtests chegam, apenas as três células correspondentes são
     atualizadas;
   - se a estrutura visível não corresponder mais à consulta, o render completo
     permanece como fallback seguro.

5. **Medição operacional**
   - métricas do navegador cobrem Dashboard, Análises, Carteira, Backtests,
     Finanças e Administração;
   - o benchmark aceita `--cold` para invalidar caches locais entre amostras e
     `--extended` para incluir ETF e screener avançado.

## Fora do escopo desta R1

- reescrita SQL completa do screener avançado;
- limitação por ativo do histórico técnico de fallback;
- mudança de banco ou remoção de históricos;
- ativação automática de uma segunda VM.

Esses itens permanecem candidatos a uma R2 após dados reais de homologação.
