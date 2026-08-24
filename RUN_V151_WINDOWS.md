# Atualizar V1.5 -> V1.5.1 no Windows

1. Pare Streamlit e Uvicorn com Ctrl+C.
2. Extraia o patch sobre a pasta do projeto e escolha substituir arquivos.
3. Abra PowerShell em `C:\Users\André\Documents\Investment\investment_engine`.
4. Ative o ambiente:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
```

5. Não rode Alembic: V1.5.1 não cria tabelas nem colunas.
6. Inicie a API:

```powershell
python -m uvicorn investment_engine.api.app:app --host 127.0.0.1 --port 8000
```

7. Em `/health`, espere versão `0.6.2`.
8. Em outro PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
streamlit run examples/streamlit_v15_integrated.py
```

## Testes sugeridos
1. BBAS3, 5 anos, Bollinger 20/2 + RSI + SMA200.
2. Observe o diagnóstico caso haja 0 trades.
3. Teste `Gatilho da banda = Mínima toca a banda` e compare com `Fechamento <= banda`.
4. Compare todas as 10 estratégias.
5. Depois ative apenas tendência mensal SMA21 e compare novamente.
6. Combine mensal SMA21 + semanal SMA21; depois teste SMA50.

Filtros fundamentalistas históricos podem recusar a execução até existir histórico point-in-time suficiente. Isso é comportamento intencional.
