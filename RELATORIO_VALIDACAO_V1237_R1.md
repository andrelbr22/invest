# Relatório de validação — V1.23.7 R1

## Critérios obrigatórios

- nenhuma remoção de fonte, cálculo, permissão, filtro ou histórico;
- migração aditiva e encadeada à revisão 0031;
- restauração de painel antes da revalidação;
- invalidação seletiva sem `readCache.clear()` global;
- URL, voltar/avançar e última seção;
- tabela acessível e responsiva;
- medição real agregada, sem uma linha por clique;
- testes anteriores e `tests_v1237` aprovados;
- benchmark do servidor dentro das metas;
- validação visual manual no staging.

## Homologação visual

1. Abra Mercado e Análises, aplique filtros e role a tabela horizontalmente.
2. Abra outro painel e retorne: lista, filtros e posição devem reaparecer sem
   esqueleto de carregamento.
3. Use voltar/avançar e recarregue uma URL com `view`, `tab` ou `type`.
4. Ordene duas colunas, alterne densidade e abra/feche um ativo.
5. Confirme ticker fixo e etiquetas Atualizado, Sem resultado oficial e N/D.
6. Verifique os quatro grupos da Administração.
7. Em Administração > Operação, confirme o início da coleta horária.

## Resultado local

- suíte completa: **490 testes aprovados**;
- testes dirigidos da R1 e regressões relacionadas: **69 aprovados**;
- sintaxe dos dois módulos JavaScript: aprovada;
- migração integral, iniciada em banco SQLite vazio: revisão
  `0032_v1237_browser_perf` alcançada e tabela horária criada;
- validação estrutural do pacote e do publicador: aprovada.

O benchmark do servidor, o endpoint `ready`, a automação em navegador real e a
homologação visual permanecem como etapas obrigatórias no staging, pois dependem
da infraestrutura e da autenticação reais.
