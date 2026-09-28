# Patch V1.23.1 R2

## Finalidade

Esta revisão fecha os dois itens pendentes da R1 planejada sem mudar filtros,
fórmulas, dados do investidor, rotas ou formatos de resposta.

## Cache seguro

1. Permissões efetivas: cinco segundos.
2. Presets e colunas administrativas: quinze segundos.
3. Painel compartilhado e situação das atualizações: três segundos.
4. Limite de entradas para impedir crescimento ilimitado do processo.
5. Cópias defensivas na leitura e na gravação.
6. Invalidação explícita após cada alteração confirmada no banco.
7. Geração de invalidação para que uma leitura concorrente antiga nunca volte
   ao cache depois de uma revogação.

Na topologia atual há um único processo web. Antes de aumentar a quantidade
de processos ou réplicas da API, deve-se usar invalidação distribuída ou
definir `ACCESS_POLICY_CACHE_TTL_SECONDS=0`; a segunda VM prevista recebe
somente o worker e não altera essa garantia.

## Retenção operacional

- execução automática diária, em lotes de no máximo 200 registros;
- trabalhos automáticos concluídos: mínimo de 45 dias;
- incidentes resolvidos e serviços parados: mínimo de 180 dias;
- arquivo integral e imutável com SHA-256 antes da remoção da tabela quente;
- mesma transação para arquivo e exclusão;
- preservação do último trabalho de cada chave de atualização;
- preservação de pedidos manuais, acessos, usuários, backtests, falhas e
  trabalhos ativos;
- simulação como padrão no comando administrativo;
- downgrade preserva a tabela quando ela contém registros, em vez de apagar a
  única cópia arquivada.

## Banco

Nova migração: `0028_v1_23_operational_retention`.

Ela cria somente `operational_archive` e seus índices. Nenhuma tabela
histórica de mercado, carteira, finanças, alertas, eventos ou backtests é
alterada.
