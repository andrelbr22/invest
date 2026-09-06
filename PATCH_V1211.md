# Patch V1.21.1

## Escopo

Correção da descoberta dos cenários, habilitação das análises técnicas nas cinco classes, explicação do potencial mínimo e redução de consultas repetidas.

## Compatibilidade

- preserva todos os endpoints e filtros anteriores;
- preserva análises personalizadas antigas;
- não altera tabelas nem remove dados;
- mantém autorizações independentes de FDI, ALB e das quatro famílias de valoração;
- mantém ETF, BDR e futuro em modo seguro `N/D` para metodologias sem dados próprios.

## Reversão

A promoção continua usando a imagem anterior como rollback. Como não existe nova migração, uma reversão desta revisão não exige alteração no banco.
