# Patch V1.22.1

Correção permanente para o timeout de `Mercado e Análises` e para a lentidão na troca de painéis:

1. substitui janelas globais por buscas indexadas do snapshot mais recente;
2. cria a migração `0023_v1_22_screener_performance`;
3. renderiza listas antes do enriquecimento de backtests;
4. preserva e reutiliza caches de leitura;
5. prioriza produção e banco na VM de 1 GB;
6. impede o retorno automático da pilha legada sem excluir seus dados.
