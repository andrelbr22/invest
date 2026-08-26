# Atualização da Oracle • V1.16.0

Esta versão exige uma troca única do arquivo de composição, pois a interface
e a API passam a ser um único serviço.

## 1. Pausar a atualização antiga na Oracle

Antes de publicar, entre no servidor e execute:

```bash
sudo systemctl stop investment-github-update.timer
```

Isso evita que o implantador antigo tente iniciar a nova versão com a
configuração anterior.

## 2. Publicar pelo Windows

Na pasta extraída, execute primeiro a validação e depois a publicação:

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

## 3. Baixar a versão nova na Oracle

Entre no servidor e vá para o projeto:

```bash
cd ~/invest
```

```bash
git fetch origin main
```

```bash
git merge --ff-only origin/main
```

## 4. Preparar o arquivo privado da aplicação

Crie a cópia com o novo nome:

```bash
cp deployment/secrets/*_secrets.toml deployment/secrets/app_secrets.toml
```

O comando acima deve encontrar apenas o arquivo privado que já existe no
servidor. Confirme que `redirect_uri` aponta para:

```text
https://formacaodoinvestidor.com.br/oauth2callback
```

Garanta a leitura pelo usuário da aplicação:

```bash
sudo chown ubuntu:10001 deployment/secrets/app_secrets.toml
```

```bash
chmod 640 deployment/secrets/app_secrets.toml
```

## 5. Fazer a troca única

```bash
docker compose -f docker-compose.oracle-micro.yml down
```

```bash
COMPOSE_PARALLEL_LIMIT=1 docker compose -f docker-compose.oracle-web.yml build app
```

```bash
docker compose -f docker-compose.oracle-web.yml up -d
```

## 6. Conferir

```bash
docker compose -f docker-compose.oracle-web.yml ps
```

```bash
curl -I https://formacaodoinvestidor.com.br
```

O serviço `app` e o banco devem ficar `healthy`, o proxy deve ficar `Up` e o
site deve responder `HTTP/2 200`.

## 7. Ajustar e reativar o atualizador automático

Execute:

```bash
sed -i 's|docker-compose\.oracle-micro\.yml|docker-compose.oracle-web.yml|g' deployment/update-from-github.sh
```

Confirme que a linha do arquivo de composição ficou assim:

```text
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.oracle-web.yml"
```

Reative o atualizador:

```bash
sudo systemctl enable --now investment-github-update.timer
```

Depois disso, os próximos commits voltam a ser implantados automaticamente.
