# Corrigir a conexão dos backtests no GitHub

Este ajuste é feito uma única vez. Não envie a senha ou a URL do banco por conversa, e-mail ou imagem.

## 1. Copiar a conexão correta no Neon

1. Entre no projeto do Neon.
2. Clique em **Connect**.
3. Escolha a conexão **Direct connection** ou desative **Connection pooling**.
4. Copie a connection string completa.
5. Confirme apenas visualmente que ela começa com `postgresql://` e que não contém `-pooler` no servidor.

## 2. Atualizar o Secret do GitHub

1. Abra o repositório `andrelbr22/invest` no GitHub.
2. Entre em **Settings**.
3. No menu esquerdo, abra **Secrets and variables > Actions**.
4. Em **Repository secrets**, localize `DATABASE_ADMIN_URL`.
5. Clique no ícone de editar.
6. Cole somente a connection string do Neon. Não inclua `DATABASE_ADMIN_URL =`, aspas ou formatação de link.
7. Salve em **Update secret**.

O Secret `DATABASE_URL` com a conexão pooled é opcional. A conexão direta em `DATABASE_ADMIN_URL` é a recomendada para as migrações executadas pelo workflow.

## 3. Conferir pelo site

1. Aguarde a publicação da V1.10.3 e confirme a versão no menu lateral.
2. Abra **Administração > Backtests oficiais > Lote oficial completo**.
3. Selecione inicialmente um ativo para uma verificação curta.
4. Clique em **Gerar backtests dos ativos selecionados** uma única vez.
5. O painel deve mostrar imediatamente um número de pedido e a situação **Na fila**.
6. Use a tabela de andamento do GitHub na mesma página. A situação passará para **Executando** e depois **Concluído** ou **Falhou**.
