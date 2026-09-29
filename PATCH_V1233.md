# Patch V1.23.3

## Problema observado

Durante o primeiro preenchimento da tabela de métricas atuais, cada ativo
provocava consultas individuais e o recálculo de até 600 barras. Na VM de 1 GB,
o worker competia com a API e o PostgreSQL, deixando a navegação lenta mesmo
quando as rotas isoladas cumpriam as metas p50/p95.

## Correção

O processamento agora trabalha com mapas pré-carregados por lote e reutiliza a
mesma linha ORM. Dados técnicos só são recalculados quando a fonte mudou. O
trabalho pesado foi dividido em blocos menores, com pequena pausa e prioridade
inferior às rotinas que sustentam a navegação.

## Segurança

O atalho exige correspondência de identificador, data de referência, data de
observação e algoritmo. Se qualquer elemento mudar, o cálculo completo volta a
ser executado. Históricos e fallbacks permanecem intactos.

## Publicação

Esta versão deve passar primeiro pelo `/testefdi`. A promoção continua manual e
precedida pelo benchmark obrigatório. Nenhuma migração nova é criada.
