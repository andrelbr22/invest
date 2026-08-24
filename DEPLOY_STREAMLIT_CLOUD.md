# Hospedagem atual na Oracle Cloud

> O nome deste arquivo foi preservado apenas para não quebrar links de versões
> antigas. As instruções de hospedagem externa anteriores estão desativadas.

## Endereço oficial

O aplicativo é servido exclusivamente por:

`https://formacaodoinvestidor.com.br`

O endereço `www` pode redirecionar para o mesmo aplicativo. O login Google usa
exatamente esta URI autorizada:

`https://formacaodoinvestidor.com.br/oauth2callback`

## Arquitetura atual

- máquina virtual Oracle Cloud;
- Streamlit e API FastAPI no contêiner `app`;
- PostgreSQL privado no contêiner `postgres`;
- Caddy no contêiner `proxy`, com HTTPS automático;
- GitHub como origem do código e executor isolado dos cálculos oficiais;
- backups locais e cópia no Object Storage da Oracle.

O banco não é hospedado no GitHub e não possui porta pública. Os segredos reais
ficam somente no servidor em `deployment/secrets/streamlit_secrets.toml`.

## Publicação

Publique o pacote validado no GitHub com `PUBLICAR_GITHUB.ps1`. O temporizador
do servidor consulta a branch `main`, instala a nova versão e reinicia os
contêineres necessários.

Não configure redirecionamento OAuth, DNS ou links para endereços de hospedagem
anteriores. Os exemplos do projeto usam somente o domínio oficial acima.
