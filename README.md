# Formação do Investidor • V1.16.0

Plataforma web educacional para análise de ativos, acompanhamento de mercado,
carteiras, alertas e backtests. A aplicação é executada integralmente na Oracle
Cloud, com banco PostgreSQL local, autenticação Google OIDC e implantação pelo
GitHub.

## Arquitetura de produção

- `Caddy`: HTTPS e encaminhamento do domínio.
- `FastAPI`: interface web, autenticação, API e tarefas em segundo plano.
- `PostgreSQL`: dados multiusuário, carteiras, permissões, alertas e resultados.
- `GitHub Actions`: backtests oficiais e entrega segura dos resultados.
- `Oracle Object Storage`: cópias de segurança externas.

O navegador acessa apenas `https://formacaodoinvestidor.com.br`. Não existe
segundo servidor de interface, porta auxiliar ou dependência de hospedagem
externa para a apresentação das páginas.

## Principais módulos

- Painel de Mercado em abas, com Selic/Focus, renda fixa, bolsas, commodities,
  Treasuries, spread, T-Bonds, cripto, câmbio, curva ANBIMA, agenda e manchetes.
- Mercado e Análises com abas para Ações, FIIs, ETFs, BDRs e Futuros.
- Carteira com posições, notícias e alertas.
- Backtests com histórico decrescente, execução, estudos e rodadas oficiais.
- Administração de permissões por usuário.

## Subida local para desenvolvimento

1. Instale Python 3.12 e as dependências de `requirements.txt`.
2. Configure as variáveis de `.env.example`.
3. Execute as migrações com `python -m alembic upgrade head`.
4. Inicie com:

```powershell
python -m uvicorn investment_engine.api.app:app --host 127.0.0.1 --port 8000
```

5. Abra `http://127.0.0.1:8000`.

## Produção

Siga [INSTRUCOES_ORACLE_V1160.md](INSTRUCOES_ORACLE_V1160.md). O arquivo real
`deployment/secrets/app_secrets.toml` nunca deve ser enviado ao GitHub.

Ferramenta educacional; não constitui recomendação de investimento.
