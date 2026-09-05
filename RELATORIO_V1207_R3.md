# Relatório da correção V1.20.7 R3

## Sintoma observado

O Comparador Histórico ainda exibia o snapshot anterior, no qual BTC e ETH não existiam. Ao clicar em `Atualizar séries`, a interface removia esse snapshot antes de a tarefa em segundo plano terminar. Quando a API reutilizava um trabalho recente por segurança, o navegador interpretava `scheduled: false` como falha e mostrava uma tela vazia.

## Diagnóstico confirmado

O trabalho `historical_comparison_refresh` terminou com `status: succeeded`, uma tentativa e nenhum erro. Portanto, as fontes e o worker concluíram a coleta; a falha estava no acompanhamento da tarefa pelo navegador.

## Correção

- o snapshot válido nunca é removido ao solicitar atualização;
- a resposta do POST inclui o snapshot atual e o verdadeiro estado da fila;
- a interface acompanha trabalhos já existentes, inclusive dentro do cooldown;
- a espera visual foi ampliada de dois para seis minutos;
- ao fim do trabalho, os novos dados substituem automaticamente os antigos;
- indisponibilidades parciais não removem opções do catálogo;
- valores `NaN` ou infinitos são normalizados antes da persistência.

## Segurança operacional

A correção não altera banco de dados, permissões, segredos nem rotinas de produção. A migração esperada permanece `0019_v1_20_access_rules`, e a produção continua dependendo de aprovação manual posterior à homologação em `/testefdi`.
