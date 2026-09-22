# V1.23.0 R8 — ajustes de análises e alocação hierárquica

Esta revisão mantém integralmente a V1.23.0 R7 homologada e acrescenta
recursos administrativos e visuais sem remover tabelas, dados ou rotinas.

## Plataforma e página principal

- A barra superior da plataforma possui um atalho direto para a página
  principal.
- A navegação não executa logout; a sessão continua válida.
- O caminho relativo funciona tanto em produção quanto em `/testefdi/`.

## Filtros e colunas administráveis

- Apenas o proprietário pode criar e ativar uma segunda configuração dos
  filtros Padrão, FDI e ALB para cada classe de ativo.
- A configuração homologada da R7 permanece imutável como padrão de
  fábrica.
- Restaurar o padrão desativa somente a alternativa, preservando a última
  configuração do proprietário e o número de revisão para reativação segura.
- O proprietário também define as colunas visíveis por padrão e sua ordem.
  Colunas protegidas por permissão continuam protegidas e a escolha pessoal do
  usuário continua disponível.

## Carteira

- O painel de alocação passa a usar dois anéis: tipo de investimento por
  dentro e setor ou segmento por fora.
- O detalhamento de cada tipo abre no mesmo painel por clique ou teclado e não
  dispara outra consulta.
- FIIs usam segmento; os demais ativos listados usam setor; investimentos
  manuais usam segmento, depois setor e, por fim, categoria.
- Posições sem cotação continuam como N/D e nunca são convertidas em zero.

## Homologação obrigatória

1. Confirmar `/testefdi/ready` com HTTP 200 e migração
   `0027_v1_23_analysis_settings`.
2. Executar toda a suíte versionada.
3. Confirmar que somente o proprietário enxerga `Filtros e colunas`.
4. Salvar e ativar uma alternativa, conferir a análise e restaurar o padrão.
5. Reordenar colunas, conferir a tabela e restaurar o padrão.
6. Abrir uma carteira e testar o gráfico principal e o detalhamento por tipo.
7. Somente depois da validação visual promover manualmente para produção.
