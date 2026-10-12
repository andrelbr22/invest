# Patch V1.23.8 R2A

Esta revisão corrige exclusivamente seis falhas de compatibilidade encontradas
pela suíte histórica no staging da R2.

- cinco testes de identidade deixam de exigir o rótulo antigo R1 e passam a
  validar a revisão R2A vigente;
- o teste do failback passa a reconhecer a variável intermediária segura usada
  para combinar a configuração persistente com a autorização efêmera do ensaio;
- os controles de produção, banco, worker, navegador e publicação permanecem
  inalterados.

Não há migração nova. A revisão esperada continua sendo
`0032_v1237_browser_perf`.
