# Formação do Investidor no Streamlit Community Cloud

Esta variante executa a interface Streamlit e a API FastAPI no mesmo contêiner.
O banco permanece fora do GitHub em um PostgreSQL gerenciado, permitindo que a
instalação local e a publicação usem os mesmos dados.

## Arquitetura

- `app.py`: entrada compatível com o aplicativo Streamlit já publicado.
- `streamlit_app.py`: inicialização da edição completa para nuvem.
- `investment_engine/cloud_runtime.py`: migra o banco e inicia a API interna.
- Neon PostgreSQL: armazenamento persistente compartilhado.
- GitHub: apenas código; nenhum segredo, chave SSH ou arquivo de banco.

## Configuração do aplicativo

No painel do Streamlit Community Cloud, selecione:

- Repository: o repositório criado para esta edição.
- Branch: `main`.
- Main file path: `app.py` para preservar o aplicativo existente. Em uma nova
  publicação, `streamlit_app.py` também pode ser selecionado.

Para atualizar o repositório existente `andrelbr22/invest` depois de criar a
branch de segurança `backup-versao-anterior`, extraia o pacote e execute no
PowerShell, dentro da pasta extraída:

`powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1`

O assistente confere o backup e recusa arquivos de senhas ou chaves antes de
enviar a edição para a branch `main`.

Em **Settings > Secrets**, use como modelo `.streamlit/secrets.toml.example` e
substitua todos os campos de exemplo. No painel **Connect** do Neon, copie sem
publicar no GitHub:

- `DATABASE_URL`: conexão **Pooled connection**, cujo host contém `-pooler`.
- `DATABASE_ADMIN_URL`: conexão direta, com **Pooled connection** desativada.

As duas conexões devem terminar com `sslmode=require`. A primeira atende o uso
normal do aplicativo; a segunda é usada apenas para atualizar a estrutura do
banco. Se `DATABASE_ADMIN_URL` não for definida, a aplicação continuará usando
`DATABASE_URL` também nas atualizações, para manter compatibilidade.
As URLs podem ser coladas exatamente como o Neon as fornece; o adaptador ajusta
automaticamente o driver PostgreSQL usado pela aplicação.

No Google Cloud Console, inclua a URI abaixo entre as URIs de redirecionamento
autorizadas do cliente OAuth:

`https://invest-klpbhuewpmzb7njdsmha4t.streamlit.app/oauth2callback`

## Instalação local usando o mesmo banco

Defina as mesmas `DATABASE_URL` e `DATABASE_ADMIN_URL` no `.env` local. Esse
arquivo já está ignorado pelo Git e não deve ser publicado. Para desenvolvimento
com dados isolados, use posteriormente uma branch separada do banco Neon.

## Observações do plano gratuito

O Streamlit Community Cloud pode suspender o aplicativo quando estiver ocioso,
e o PostgreSQL gratuito também pode reduzir a zero sua capacidade quando não há
consultas. A primeira abertura após um período ocioso pode levar alguns segundos.
