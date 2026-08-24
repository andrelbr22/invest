# Produção atual — Formação do Investidor

## Arquitetura

- `formacaodoinvestidor.com.br`: aplicativo protegido por login Google/OIDC;
- `www.formacaodoinvestidor.com.br`: aponta para o mesmo domínio oficial;
- API FastAPI: privada, exceto a rota autenticada de entrega dos backtests;
- PostgreSQL: privado e sem porta publicada;
- Caddy: entrada pública nas portas 80/443 e certificados HTTPS automáticos;
- Oracle Object Storage: cópia externa dos backups.

## Login Google

A URI autorizada do cliente OAuth deve ser exatamente:

`https://formacaodoinvestidor.com.br/oauth2callback`

As credenciais reais ficam em
`deployment/secrets/streamlit_secrets.toml` no servidor e não devem ser
publicadas no GitHub.

## Atualização

O código é publicado na branch `main` pelo script `PUBLICAR_GITHUB.ps1`. A
Oracle consulta o GitHub automaticamente. Antes de publicar, execute o script
com `-ValidateOnly` e use sempre um pacote completo extraído em pasta limpa.

## Rede e banco

Os registros DNS `@` e `www` apontam para o IP público da Oracle. Somente as
portas 80, 443 e 22 possuem regras externas. A porta 22 é usada para manutenção
SSH; banco, API interna e Streamlit não são expostos diretamente.

## Backups

O serviço `investment-db-backup.timer` gera o backup diário. A cópia é enviada
ao bucket `formacao-investidor-backups` por credencial de instância, sem chaves
gravadas no projeto.
