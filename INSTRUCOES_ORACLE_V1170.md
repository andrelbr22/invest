# Primeira migração para homologação e produção

Execute esta sequência somente uma vez. A publicação do pacote no GitHub
deve ser feita apenas depois do passo 2.

## 1. Entrar na Oracle e parar o atualizador antigo

```bash
cd ~/invest
```

```bash
sudo systemctl stop investment-github-update.timer
```

## 2. Preservar a versão oficial atual

```bash
docker tag formacao-do-investidor-oracle-app:latest formacao-do-investidor-production:current
```

Se essa imagem não existir, descubra o nome atual com:

```bash
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}'
```

## 3. Publicar a V1.17.0 no GitHub pelo Windows

Use `PUBLICAR_GITHUB.ps1` na pasta extraída. Depois retorne ao servidor.

## 4. Instalar os novos arquivos sem trocar a produção

```bash
cd ~/invest
```

```bash
git fetch origin main
```

```bash
git merge --ff-only origin/main
```

```bash
chmod 700 deployment/update-staging-from-github.sh deployment/refresh-staging-db.sh deployment/promote-staging-to-production.sh deployment/backup-local-db.sh
```

```bash
sudo cp deployment/investment-github-update.service.example /etc/systemd/system/investment-github-update.service
```

```bash
sudo cp deployment/investment-github-update.timer.example /etc/systemd/system/investment-github-update.timer
```

```bash
sudo systemctl daemon-reload
```

```bash
docker compose -f docker-compose.oracle-web.yml up -d postgres app proxy
```

## 5. Criar e abrir a homologação

```bash
./deployment/update-staging-from-github.sh
```

Abra:

`https://formacaodoinvestidor.com.br/testefdi/`

## 6. Reativar atualizações automáticas somente no teste

```bash
sudo systemctl enable --now investment-github-update.timer
```

## 7. Promover a versão aprovada

Execute somente depois de validar o endereço de teste:

```bash
./deployment/promote-staging-to-production.sh
```

A promoção reaproveita exatamente a imagem validada, cria backup do banco e
restaura a imagem oficial anterior se a nova aplicação não ficar saudável.
