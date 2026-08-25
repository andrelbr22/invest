# Ativar o envio dos alertas por e-mail

O encaminhamento de e-mail da Cloudflare recebe mensagens, mas não envia os alertas do sistema. Para enviar, o servidor precisa de uma conta SMTP. A aplicação aceita Gmail ou outro provedor SMTP.

No servidor Oracle, acrescente estas chaves na parte principal de `deployment/secrets/streamlit_secrets.toml`, antes de `[auth]`:

```toml
ALERT_MONITOR_ENABLED = "true"
ALERT_MONITOR_POLL_SECONDS = "60"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = "587"
SMTP_USERNAME = "CONTA_QUE_ENVIA_NO_GMAIL"
SMTP_PASSWORD = "SENHA_DE_APLICATIVO_DO_GOOGLE"
SMTP_FROM_EMAIL = "contato@formacaodoinvestidor.com.br"
SMTP_FROM_NAME = "Formação do Investidor"
SMTP_STARTTLS = "true"
```

Use uma senha de aplicativo exclusiva, nunca a senha normal da conta Google. Se o Gmail ainda não estiver autorizado a enviar como `contato@formacaodoinvestidor.com.br`, configure primeiro esse endereço como remetente na conta ou use temporariamente o próprio Gmail em `SMTP_FROM_EMAIL`.

Depois de salvar:

1. valide o TOML sem exibir credenciais;
2. recrie somente o contêiner `app`;
3. aguarde o estado `healthy`;
4. abra **Minha carteira → Alertas → E-mails que receberão os alertas**;
5. clique em **Enviar e-mail de teste**.

O monitor inicia dentro da API privada incorporada. Não é necessário manter o navegador aberto.

