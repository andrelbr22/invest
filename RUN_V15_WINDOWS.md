# Rodar a V1.5 no Windows

Assumindo a pasta:

`C:\Users\André\Documents\Investment\investment_engine`

## 1. Pare Streamlit e Uvicorn
Nas duas janelas, use `Ctrl + C`.

## 2. Copie o patch V1.5
Extraia o ZIP por cima da pasta do projeto e escolha **Substituir os arquivos no destino**.

## 3. Abra PowerShell na pasta do projeto

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
```

## 4. Aplique a nova migração
Esta etapa é obrigatória na V1.5 porque Carteira e Backtests criam novas tabelas.

```powershell
python -m alembic upgrade head
```

## 5. Teste opcional

```powershell
pytest -q
```

A revisão distribuída foi validada com 50 testes.

## 6. Histórico para o screener técnico
Não é obrigatório para abrir o sistema. Porém SMA 21 e Pivot Points precisam de histórico local.

Para Ações:

```powershell
python scripts/ingest_prices.py --all --type stock --range 3y
```

Para FIIs:

```powershell
python scripts/ingest_prices.py --all --type fii --range 3y
```

Se preferir carregar em lotes:

```powershell
python scripts/ingest_prices.py --all --type stock --range 3y --limit 100 --offset 0
```

Depois mude o `offset` para 100, 200 etc.

## 7. Ligue a API

```powershell
python -m uvicorn investment_engine.api.app:app --host 127.0.0.1 --port 8000
```

Teste:

`http://127.0.0.1:8000/health`

Versão esperada: `0.6.1`.

## 8. Abra outro PowerShell para o Streamlit

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
streamlit run examples/streamlit_v15_integrated.py
```

## 9. Módulos
Na barra lateral escolha:
- Mercado & Análise;
- Carteira;
- Backtests.
