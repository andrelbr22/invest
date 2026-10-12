# Instruções Oracle — V1.23.8 R2A

1. publique o pacote pelo `PUBLICAR_GITHUB.ps1` no Windows;
2. atualize o staging com `deployment/update-staging-from-github.sh`;
3. confirme `/testefdi/ready` com versão `1.23.8`, ambiente `staging` e migração
   `0032_v1237_browser_perf`;
4. execute a suíte histórica completa, a cobertura de navegação, os benchmarks
   e a homologação visual;
5. não promova enquanto existir qualquer falha.

A R2A não muda a topologia. A criação/ativação da VM2 e os ensaios do worker
continuam sendo uma etapa operacional posterior, separada e explicitamente
aprovada.
