# Relatório de validação — V1.23.2

## Escopo verificado

| Área | Critério |
|---|---|
| Histórico | tabelas anteriores preservadas e usadas como fallback |
| Métricas atuais | escrita idempotente, referências de origem e paridade |
| Screener | mesmo payload essencial no caminho atual e no histórico |
| Técnica | pré-cálculo usado sem reler `price_bars` na navegação |
| Rede | dashboard, screener, detalhe, IBOV e notícias sem provedor ao vivo |
| Fila | sincronização completa e preço individual deduplicados |
| Migração | etapa one-shot, lock PostgreSQL e head exato |
| Proxy | validação, resolução dinâmica e reload antes do fallback |
| VM2 | commit/SSH/segredos/lideranças/failback endurecidos |
| Regressão | suítes V1.16 a V1.23.2 incluídas no CI |

## Estado da segunda VM

O software e os procedimentos estão prontos. A ativação física depende de
recursos e dados da conta OCI e, por segurança, não é simulada como concluída.
O corte real somente deverá ocorrer depois de:

1. VM2 gratuita criada na mesma VCN;
2. PostgreSQL publicado apenas no IP privado e restrito no NSG;
3. preflight remoto aprovado;
4. teste de cutover;
5. teste de failback para a VM1;
6. confirmação de um único scheduler e monitor de alertas.

## Resultado automatizado

- Suíte local completa: **357 testes aprovados**.
- JavaScript da plataforma e do portal: sintaxe validada sem erros.
- Publicador: `-ValidateOnly` aprovado; nenhum arquivo foi enviado.
- Permaneceram apenas dois avisos de depreciação de dependências, sem falha.

As medições com banco e recursos reais ainda devem ser repetidas no staging
Oracle, conforme `INSTRUCOES_ORACLE_V1232.md`.
