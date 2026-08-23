# Ativar os backtests semanais

O aplicativo e a migração funcionam assim que a V1.9.0 for publicada. Para ativar a rotina de sábado, faça estes passos uma única vez no GitHub.

## 1. Abrir os segredos do repositório

1. Entre em `github.com/andrelbr22/invest`.
2. Clique em **Settings**.
3. No menu esquerdo, abra **Secrets and variables** e depois **Actions**.
4. Clique em **New repository secret**.

## 2. Cadastrar a conexão do Neon

Crie o segredo abaixo:

- Nome: `DATABASE_ADMIN_URL`
- Valor: a URL direta, sem `-pooler`, exibida pelo Neon. Ela deve começar com `postgresql://`; não use o endereço `https://` do painel.

Opcionalmente, crie também `DATABASE_URL` usando a URL com `-pooler`. Nunca coloque essas URLs em arquivos publicados no GitHub.

## 3. Fazer o primeiro lote manual

1. Abra a guia **Actions** do repositório.
2. Escolha **Backtests oficiais semanais**.
3. Clique em **Run workflow**.
4. Deixe **tickers** vazio para usar as 50 ações do filtro Padrão.
5. Mantenha **200** combinações por ativo e confirme.

Para um grupo extraordinário, informe até 100 tickers separados por vírgula. Somente pessoas com permissão de escrita no repositório conseguem disparar essa ação manual.

## 4. Acompanhar

O andamento aparece no GitHub Actions e também em **Administração → Backtests oficiais**. O agendamento ocorre aos sábados às 00h01 de Brasília; o GitHub pode iniciar alguns minutos depois em períodos de fila.
