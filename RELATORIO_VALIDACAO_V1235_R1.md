# Validação da V1.23.5 R1

## Verificações obrigatórias

1. Executar toda a regressão, incluindo `tests_v1235`.
2. Executar o benchmark p50/p95 com cache aquecido.
3. Abrir Dashboard, Mercado e Análises e Minha Carteira em janela privada.
4. Confirmar em Administração > Operação as categorias
   `panel_dashboard`, `panel_analysis` e `panel_portfolio`.
5. Trocar repetidamente entre filtros e confirmar que o último resultado
   permanece visível durante a renovação.
6. Confirmar que fontes ausentes podem ser reenfileiradas sem apagar o último
   snapshot válido.
7. Confirmar `ready`, saúde dos contêineres e ausência de erros no worker.

