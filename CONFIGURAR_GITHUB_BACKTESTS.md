# Configuração única para solicitar backtests pelo site

## 1. Criar a credencial no GitHub

1. Entre no GitHub com a conta proprietária.
2. Abra **Settings > Developer settings > Personal access tokens > Fine-grained tokens**.
3. Crie um token para o repositório `andrelbr22/invest`.
4. Em **Repository permissions**, defina **Actions: Read and write**.
5. Copie o token quando o GitHub o mostrar. Ele não será exibido novamente.

## 2. Guardar no servidor ativo

1. Na Oracle, abra `deployment/secrets/streamlit_secrets.toml`.
2. Acrescente somente esta linha, substituindo o texto pelo token real:

```toml
GITHUB_ACTIONS_TOKEN = "COLE_AQUI_O_TOKEN_CRIADO_NO_GITHUB"
```

3. Salve e reinicie o contêiner `app`.

Não coloque esse token em arquivo do projeto, GitHub, conversa, imagem ou e-mail.

## 3. Usar

Entre como proprietário e abra **Administração > Backtests oficiais > Lote oficial completo**. Escolha os ativos e clique em **Gerar backtests dos ativos selecionados**.

Esta credencial apenas aciona e consulta o GitHub. A credencial diferente usada
para o retorno dos resultados está explicada em
`ATIVAR_ENTREGA_SEGURA_BACKTESTS_V1120.md`.
