# Patch V1.23.8 R1A

## Motivo

A suíte oficial encontrou duas verificações textuais antigas que ainda
procuravam as chamadas anteriores de cache depois da modularização da R1.

## Correção

- a verificação de renderização antecipada agora reconhece o cache limitado;
- a verificação de requisições simultâneas reconhece a chave lógica usada pela
  deduplicação;
- os testes continuam exigindo a ordem correta de renderização, as proteções
  contra respostas atrasadas e o compartilhamento de GETs simultâneos.

Não houve alteração no código de produção, banco, fórmulas, permissões,
interface ou desempenho.
