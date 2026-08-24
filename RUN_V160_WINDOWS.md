# Atualização local para V1.6.0 no Windows

1. Encerre Streamlit e Uvicorn com `Ctrl+C`.
2. Faça uma cópia de segurança de `C:\Users\André\Documents\Investment\investment_engine`.
3. Extraia `Investment_Engine_V1.6.0_PATCH.zip` sobre essa pasta e confirme a substituição.
4. No PowerShell:

```powershell
Set-Location 'C:\Users\André\Documents\Investment\investment_engine'
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe -m pytest -q
```

5. Inicie a API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn investment_engine.api.app:app --host 127.0.0.1 --port 8000
```

6. Em outro PowerShell, inicie a interface:

```powershell
Set-Location 'C:\Users\André\Documents\Investment\investment_engine'
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe -m streamlit run examples\streamlit_v15_integrated.py
```

No uso local, o login permanece desligado. Confirme a versão `0.7.0` em `http://127.0.0.1:8000/health`.

Para a hospedagem privada, não use os comandos locais acima. Siga `PRODUCAO_V160.md`.
