# Primeiro teste visual da V1.2

A V1.2 já pode ser testada localmente sem substituir o seu site atual.

## 1. Criar ambiente Python

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Subir PostgreSQL

Com Docker Desktop instalado:

```bash
docker compose up -d postgres
```

## 3. Criar/atualizar tabelas

```bash
alembic upgrade head
```

## 4. Carregar fundamentos e técnicos já suportados pela V1.1

```bash
python scripts/ingest.py --all
```

Consulte `python scripts/ingest.py --help` se quiser executar pipelines separadamente.

## 5. Calcular os primeiros scores e valuations da V1.2

```bash
python scripts/calculate_scores.py
```

## 6. Buscar histórico de preços para alguns ativos

```bash
python scripts/ingest_prices.py BBAS3 PETR4 ITUB4
```

Para FIIs:

```bash
python scripts/ingest_prices.py HGLG11 MXRF11 --type fii
```

## 7. Iniciar a API

```bash
uvicorn investment_engine.api.app:app --reload
```

Abra no navegador:

- http://localhost:8000/docs
- http://localhost:8000/health

Exemplos úteis:

- `GET /assets`
- `GET /assets/BBAS3`
- `GET /assets/BBAS3/intelligence`
- `GET /screen/db/stocks/alb`

## 8. Rodar uma página Streamlit de teste

Abra outro terminal, ative o mesmo ambiente e execute:

```bash
streamlit run examples/streamlit_v12_demo.py
```

Essa é a primeira forma visual de testar o novo Investment Engine sem modificar o seu Streamlit original.

## Importante

Os scores `1.2-preliminary` são modelos iniciais, transparentes e versionados. Eles servem para validar arquitetura, interface e pipeline. Antes de usá-los como ranking definitivo, os thresholds e pesos devem ser calibrados por setor e validados historicamente.
