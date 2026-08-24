# Atualização V1.5.4 no Windows

1. Encerre Streamlit e Uvicorn com `Ctrl+C`.
2. Faça uma cópia de segurança da pasta atual.
3. Se a V1.5.3 já estiver instalada, extraia `Investment_Engine_V1.5.4_PATCH.zip` sobre `C:\Users\André\Documents\Investment\investment_engine` e substitua os arquivos. Para uma instalação separada, extraia o pacote `COMPLETO` em uma nova pasta.
4. Como a pasta foi movida, execute uma vez o reparo do ambiente Python:

```powershell
Set-Location 'C:\Users\André\Documents\Investment\investment_engine'
powershell -ExecutionPolicy Bypass -File .\REPARAR_AMBIENTE_NOVA_PASTA.ps1
```

O reparo preserva o ambiente anterior em uma pasta de backup e recria `.venv` com o caminho correto. Depois, no PowerShell da pasta do projeto:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
python -m pytest -q
python -m uvicorn investment_engine.api.app:app --host 127.0.0.1 --port 8000
```

5. Confirme `0.6.4` em `http://127.0.0.1:8000/health`.
6. Em outro PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
streamlit run examples/streamlit_v15_integrated.py
```

Na tela Backtests, abra a aba **Testar cesta**. Não execute Alembic: esta versão não altera o banco.
