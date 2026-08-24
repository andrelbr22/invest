# Como rodar a V1.3 no Windows — passo a passo para iniciantes

Você não precisa saber programar. Siga os passos na ordem.

## O que instalar uma única vez

1. **Docker Desktop** — cria e roda o banco PostgreSQL sem você precisar configurar o banco manualmente.
2. **Python 3.12 (64-bit)** — executa o Investment Engine, a API e a página Streamlit.
3. **Opcional: Visual Studio Code** — só para abrir os arquivos com facilidade. Não é necessário para rodar.

Durante a instalação do Python, marque **Add Python to PATH**.

## Antes de começar

Descompacte `investment_engine_v1_3.zip`, por exemplo em:

`C:\InvestmentEngineV13`

Abra essa pasta no Explorador de Arquivos. Clique na barra de endereço, digite `powershell` e pressione Enter. O PowerShell abrirá já na pasta correta.

## Primeira instalação

Copie um comando por vez:

```powershell
py -m venv .venv
```

```powershell
.\.venv\Scripts\Activate.ps1
```

Se o Windows bloquear a ativação, execute uma vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Feche o PowerShell, abra novamente na pasta e execute a ativação outra vez.

Depois:

```powershell
python -m pip install --upgrade pip
```

```powershell
pip install -r requirements.txt
```

## Ligar o banco

Abra o Docker Desktop e espere aparecer que ele está em execução.

No PowerShell:

```powershell
docker compose up -d postgres
```

## Criar/atualizar as tabelas

```powershell
alembic upgrade head
```

## Buscar ações e FIIs

```powershell
python scripts/ingest.py --all
```

## Calcular scores iniciais

```powershell
python scripts/calculate_scores.py
```

## Buscar histórico de preços de alguns ativos para testar

```powershell
python scripts/ingest_prices.py BBAS3 PETR4 ITUB4
```

Para FIIs:

```powershell
python scripts/ingest_prices.py HGLG11 MXRF11 --type fii
```

## Ligar o Investment Engine

Mantenha este PowerShell aberto:

```powershell
uvicorn investment_engine.api.app:app --reload
```

Quando aparecer que está rodando em `http://127.0.0.1:8000`, o motor está ligado.

Você pode testar a API no navegador em:

`http://localhost:8000/docs`

## Abrir a nova página V1.3

Abra **outro** PowerShell na mesma pasta, ative o ambiente:

```powershell
.\.venv\Scripts\Activate.ps1
```

Depois:

```powershell
streamlit run examples/streamlit_v13_integrated.py
```

O navegador deve abrir sozinho. Se não abrir, o terminal mostrará um endereço semelhante a `http://localhost:8501`.

## Nos próximos dias

Você não precisa reinstalar nada. Normalmente fará apenas:

1. abrir Docker Desktop;
2. abrir PowerShell na pasta;
3. ativar `.venv`;
4. rodar `docker compose up -d postgres`;
5. rodar `uvicorn investment_engine.api.app:app --reload`;
6. em outro PowerShell, ativar `.venv` e rodar `streamlit run examples/streamlit_v13_integrated.py`.

A ingestão (`python scripts/ingest.py --all`) só precisa ser executada quando quiser atualizar os dados manualmente, até automatizarmos isso.
