# Instruções da segunda VM — V1.23.2

Este roteiro deve ser executado somente depois da homologação normal da
V1.23.2. Pare no primeiro resultado diferente. Nenhuma etapa cria a VM na OCI.

## 1. Arquivos e função de banco

Na VM1, atualize a função exclusiva e confirme o bind privado conforme
`INSTRUCOES_ORACLE_V1220.md`:

```bash
cd ~/invest
./deployment/second-instance/create-worker-db-role.sh
./deployment/second-instance/enable-primary-private-db.sh
```

Esperado: senha sem exibição e PostgreSQL somente em `<IP_PRIVADO_VM1>:5432`.

Na VM2, copie os exemplos, preencha somente os valores privados e aplique:

```bash
cd ~/invest
cp deployment/second-instance/worker.env.example deployment/second-instance/worker.env
cp deployment/second-instance/worker_secrets.toml.example deployment/second-instance/worker_secrets.toml
chmod 600 deployment/second-instance/worker.env
sudo chown "$(id -un)":10001 deployment/second-instance/worker_secrets.toml
chmod 640 deployment/second-instance/worker_secrets.toml
```

Mantenha `FDI_COORDINATOR_ENABLED=false` no arquivo. A ativação controlada
sobrescreve esse valor somente depois de parar o worker local.

## 2. SSH autenticado pela fingerprint

Na VM2, obtenha a fingerprint pelo console confiável da OCI:

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Na VM1, capture a chave e compare manualmente a fingerprint antes de movê-la:

```bash
ssh-keyscan -t ed25519 <IP_PRIVADO_VM2> > /tmp/fdi-worker-known-hosts
ssh-keygen -lf /tmp/fdi-worker-known-hosts
```

Somente se forem iguais:

```bash
mv /tmp/fdi-worker-known-hosts ~/.ssh/fdi-worker-known-hosts
chmod 600 ~/.ssh/fdi-worker ~/.ssh/fdi-worker-known-hosts
cp deployment/runtime/worker-location.env.example deployment/runtime/worker-location.env
chmod 600 deployment/runtime/worker-location.env
```

Preencha o IP privado, os caminhos e o mesmo `FDI_WORKER_NODE_ID` nos dois
arquivos. Deixe `FDI_WORKER_LOCATION=local` e
`FDI_AUTO_FAILBACK_ENABLED=false`.

## 3. Pré-validação sem consumidor

Na VM2:

```bash
./deployment/second-instance/prepare-worker.sh <COMMIT_PRODUCAO_DE_40_CARACTERES>
```

Esperado: checkout exato e limpo, DNS, banco privado, função restrita,
migração atual e imagem validados; nenhum consumidor iniciado.

## 4. Corte, comprovação e retorno

Na VM1:

```bash
./deployment/second-instance/cutover-worker.sh
```

Esperado: um único worker remoto e as duas lideranças confirmadas.

Teste imediatamente o retorno:

```bash
./deployment/second-instance/failback-worker.sh
```

Esperado: o remoto comprovadamente inativo antes de iniciar o local; um worker
local e duas lideranças confirmados. Faça um novo corte apenas após revisar os
logs e o painel operacional.

## 5. Guardião opcional

Pode-se instalar o timer ainda desativado:

```bash
./deployment/install-worker-failback-guard.sh
systemctl status investment-worker-failback-guard.timer --no-pager
```

Esperado: `active (waiting)`. Durante a primeira semana deixe `false`. Para
opt-in posterior, altere apenas `FDI_AUTO_FAILBACK_ENABLED=true`; mantenha o
limiar em 3 ou mais. Isso automatiza somente VM2 -> VM1, nunca VM1 -> VM2.
