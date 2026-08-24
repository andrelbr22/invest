# Atualização V1.5.3 no Windows

1. Encerre Streamlit e Uvicorn com `Ctrl+C`.
2. Faça uma cópia de segurança da pasta atual.
3. Extraia o patch sobre `C:\Users\André\Documents\Investment\investment_engine` e confirme a substituição.
4. Abra o PowerShell na pasta e execute:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
python -m pytest -q
python -m uvicorn investment_engine.api.app:app --host 127.0.0.1 --port 8000
```

5. Confirme `0.6.3` em `http://127.0.0.1:8000/health`.
6. Em outro PowerShell, na mesma pasta:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
streamlit run examples/streamlit_v15_integrated.py
```

Não execute Alembic: esta versão não altera o banco de dados.
