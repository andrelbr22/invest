# Rodando a V1.4 no Windows

Este guia assume que a V1.3.5 já funciona e que Docker/PostgreSQL estão configurados.

## 1. Copie o patch V1.4 para a pasta do projeto

Substitua os arquivos quando o Windows perguntar.

## 2. Abra o Docker Desktop

Na pasta do projeto, abra PowerShell e rode:

```powershell
docker compose up -d postgres
```

## 3. Ative o ambiente

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
```

## 4. Não é necessário rodar Alembic

A V1.4 não altera o schema do PostgreSQL.

## 5. Recalcule os scores V1.4

```powershell
python scripts/calculate_scores.py
```

Ao final deverá aparecer algo parecido com:

`V1.4: XXX ativos recalculados.`

## 6. Para melhorar Technical/Risk de um ticker

Se ainda não houver histórico interno, rode por exemplo:

```powershell
python scripts/ingest_prices.py BBAS3 PETR4 ITUB4
python scripts/calculate_scores.py
```

## 7. Ligue a API

```powershell
python -m uvicorn investment_engine.api.app:app --host 127.0.0.1 --port 8000
```

Teste:

`http://127.0.0.1:8000/health`

A versão esperada é `0.5.0`.

## 8. Abra outra janela PowerShell para a interface

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
streamlit run examples/streamlit_v14_integrated.py
```

## 9. Teste BBAS3

Na análise individual, selecione BBAS3. O perfil esperado é `Bancos`, e Quality não deve mais ser interpretado pela régua industrial genérica.
