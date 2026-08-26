# Patch V1.15.0

- moderniza a estrutura da interface como painel SaaS;
- adiciona busca global e visão rápida de ativos;
- apresenta o score ALB existente como Saúde do ativo;
- permite exportar resultados de backtests em CSV;
- reutiliza conexões HTTP e reduz leituras repetidas causadas por reruns;
- isola o cache no navegador de cada usuário e o invalida depois de gravações;
- limita o pool PostgreSQL para a Oracle Micro;
- usa formulários onde a alteração deve ocorrer apenas ao confirmar;
- não altera o esquema do banco nem os segredos do servidor.
