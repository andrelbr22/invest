# Atualização V1.5.2 no Windows

1. Pare Uvicorn e Streamlit com Ctrl+C.
2. Copie o patch sobre a pasta do projeto e substitua os arquivos.
3. Ative o ambiente:
   .\.venv\Scripts\Activate.ps1
4. Defina o PYTHONPATH:
   $env:PYTHONPATH = (Get-Location).Path
5. Não é necessário Alembic nesta versão.
6. Inicie a API:
   python -m uvicorn investment_engine.api.app:app --host 127.0.0.1 --port 8000
7. /health deve mostrar 0.6.3.
8. Em outro PowerShell, ative .venv e PYTHONPATH e rode:
   streamlit run examples/streamlit_v15_integrated.py
