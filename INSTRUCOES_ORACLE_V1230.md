# Instruções Oracle — V1.23.0

Execute somente um bloco por vez. Não copie o texto do prompt (`PS C:\...>` ou `ubuntu@...$`). Se um resultado for diferente do esperado, pare e envie a saída antes de continuar.

Estas instruções atualizam primeiro o ambiente de teste. Não promova a produção sem aprovação expressa após a homologação.

## 1. Entrar no projeto da VM principal

```bash
cd ~/invest
```

Esperado: o prompt termina em `~/invest$`.

```bash
git status --short
```

Esperado: somente arquivos locais já conhecidos e não controlados, como cópias de segurança. Se aparecer arquivo controlado com `M`, pare antes da atualização.

## 2. Conferir os segredos sem mostrá-los

O arquivo real deve continuar apenas no servidor:

```bash
test -f deployment/secrets/app_secrets.toml && echo "Arquivo de segredos localizado."
```

Esperado: `Arquivo de segredos localizado.`

```bash
python3 -c 'import pathlib,tomllib; p=pathlib.Path("deployment/secrets/app_secrets.toml"); d=tomllib.loads(p.read_text()); print("TOML válido:",bool(d)); print("SMTP configurado:",bool(str(d.get("SMTP_HOST","")).strip() and str(d.get("SMTP_FROM_EMAIL","")).strip())); print("ANBIMA configurada:",bool(str(d.get("ANBIMA_CLIENT_ID","")).strip() and str(d.get("ANBIMA_CLIENT_SECRET","")).strip()))'
```

Esperado: `TOML válido: True` e `SMTP configurado: True`. `ANBIMA configurada` pode ser `False`; nesse caso, IMA-B/IRF-M aparecerá como indisponível até a contratação/configuração da fonte oficial.

Se o SMTP ainda não estiver completo, edite o arquivo:

```bash
nano deployment/secrets/app_secrets.toml
```

Inclua ou confira, sem enviar os valores a ninguém:

```text
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "seu-remetente@gmail.com"
SMTP_PASSWORD = "SENHA_DE_APLICATIVO"
SMTP_FROM_EMAIL = "seu-remetente@gmail.com"
SMTP_FROM_NAME = "Formação do Investidor"
SMTP_STARTTLS = true
```

Para ativar o ANBIMA Feed, inclua as credenciais oficiais fornecidas pela ANBIMA:

```text
ANBIMA_CLIENT_ID = "CLIENT_ID_OFICIAL"
ANBIMA_CLIENT_SECRET = "CLIENT_SECRET_OFICIAL"
ANBIMA_IMA_HISTORY_START_DATE = "2004-04-30"
ANBIMA_IMA_HISTORY_BATCH_DAYS = 90
```

Não invente credenciais nem copie valores para o Git. Salve no nano com `Ctrl+O`, confirme com `Enter` e saia com `Ctrl+X`.

```bash
chmod 600 deployment/secrets/app_secrets.toml
```

Esperado: nenhuma mensagem.

O staging passa a ter automaticamente outro usuário de banco, outra chave de
sessão e outro nome de cookie. O arquivo privado
`deployment/runtime/staging.env` é gerado pelo atualizador e está excluído do
Git e da imagem. Não copie esse arquivo para outro computador e não o envie em
mensagens.

Para manter também o acesso Google na homologação, confira uma única vez no
Google Cloud Console se este endereço consta entre os URIs de redirecionamento
autorizados do cliente OAuth existente:

```text
https://formacaodoinvestidor.com.br/testefdi/oauth2callback
```

Isso não substitui nem remove o URI de produção. Caso ainda não possa cadastrar
o URI de staging, a homologação continua possível pelo novo acesso por código de
e-mail.

## 3. Atualizar somente o staging

```bash
./deployment/update-staging-from-github.sh
```

Esperado ao final:

```text
Banco de teste atualizado a partir de uma cópia isolada da produção.
Credenciais, sessão, códigos de acesso e trabalhos ativos do staging foram isolados.
Teste atualizado: https://formacaodoinvestidor.com.br/testefdi/
```

Na primeira execução, também aparece a confirmação de criação da configuração
isolada. Isso é esperado; nenhum valor secreto é impresso.

```bash
stat -c "%a %n" deployment/runtime/staging.env
```

Esperado: permissão `600` para `deployment/runtime/staging.env`.

## 4. Verificar prontidão e migração

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Esperado: versão `1.23.0`, ambiente `staging`, banco `reachable`, migração `0026_v1_23_email_login` e HTTP 200.

```bash
docker compose -f docker-compose.oracle-web.yml ps
```

Esperado: `postgres`, `app`, `staging` e `proxy` saudáveis ou ativos; `worker` saudável se ainda estiver na VM principal.

## 5. Executar a validação automatizada

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 tests_v1220 tests_v1230 -q -p no:cacheprovider
```

Esperado: 100% e nenhum `FAILED`. Avisos de depreciação não são falhas.

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1230 -q -p no:cacheprovider
```

Esperado: todos os testes da V1.23.0 aprovados.

## 6. Homologar o portal e sua administração

Abra `https://formacaodoinvestidor.com.br/testefdi/` e confira:

1. página pública abre mesmo sem autenticação;
2. sete livros atuais continuam visíveis;
3. entrar na plataforma mantém o prefixo `/testefdi/`;
4. o proprietário vê `Administração > Página inicial e livros`;
5. textos podem ser editados e salvos;
6. livro pode ser criado, ocultado, editado e reordenado;
7. capa PNG/JPEG/WebP pode ser enviada;
8. até três links HTTPS, com descrição, podem ser gravados;
9. a alteração aparece no portal de teste.

Use um livro de teste claramente identificado e exclua-o ao final. Não altere o conteúdo definitivo durante a homologação.

## 7. Homologar o acesso por e-mail

Na entrada da plataforma de teste:

1. informe um e-mail ao qual você tenha acesso;
2. solicite o código;
3. confirme que chegou uma mensagem com seis dígitos;
4. use o código antes de 10 minutos;
5. confirme que a plataforma abre com a política correta daquele e-mail;
6. tente reutilizar o mesmo código e confirme que ele é recusado;
7. solicite outro código em menos de um minuto e confirme a espera informada;
8. após um minuto, solicite novo código e confirme que o antigo deixa de funcionar.

O login Google também deve continuar funcionando.

Se o SMTP estiver temporariamente indisponível, a solicitação retorna uma
mensagem de falha, mas a espera de um minuto permanece ativa. Esse comportamento
é proposital: uma indisponibilidade do provedor não pode provocar disparos
repetidos. Há ainda uma proteção adicional contra rajadas vindas da mesma
conexão, sem armazenar o endereço IP bruto.

## 8. Homologar eventos oficiais e qualidade

Na plataforma de teste:

1. abra uma carteira que possua ativos e confira a área de proventos;
2. abra `Painel de Mercado > Fatos relevantes` e confira links da CVM;
3. confira a agenda oficial e a indicação de fonte;
4. abra `Administração > Atualizações` e confirme os 19 grupos;
5. execute, um por vez, `Proventos oficiais das carteiras`, `Fatos relevantes oficiais`, `Agenda oficial renovável`, `Histórico oficial IMA-B e IRF-M`, `Monitor diário do filtro ALB` e `Qualidade e frescor dos dados`;
6. aguarde o worker concluir cada trabalho;
7. abra `Administração > Qualidade dos dados` e confira fonte, data, cobertura e falhas.

Se ANBIMA não estiver configurada, o resultado correto do histórico é `indisponível` com motivo explícito. Não é correto aparecer valor estimado.

## 9. Verificar banco sem expor conteúdo sensível

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine_staging -c "SELECT version_num FROM alembic_version;"
```

Esperado: `0026_v1_23_email_login`.

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine_staging -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('corporate_events','relevant_facts','official_calendar_events','alb_universe_observations','portal_pages','portal_media','portal_books','portal_book_links','email_login_codes') ORDER BY tablename;"
```

Esperado: nove linhas, uma para cada tabela listada.

Logo após uma nova cópia e antes de solicitar um código no staging:

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine_staging -c "SELECT COUNT(*) AS codigos_copiados_da_producao FROM email_login_codes;"
```

Esperado: `0`.

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d postgres -c "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication FROM pg_roles WHERE rolname='investment_staging';"
```

Esperado: uma linha para `investment_staging`, com `f` nas quatro permissões
administrativas. Não consulte nem imprima a senha desse usuário.

## 10. Conferir os logs de staging

```bash
docker compose -f docker-compose.oracle-web.yml logs --since 30m staging | grep -Ei "error|traceback|exception|failed" || echo "Nenhum erro encontrado no staging."
```

Esperado: `Nenhum erro encontrado no staging.` Falhas transparentes de fonte externa devem ser analisadas pelo painel de qualidade, mas não podem derrubar a aplicação.

## 11. Promover somente depois da aprovação expressa

Após homologação visual, testes aprovados e autorização explícita:

```bash
./deployment/promote-staging-to-production.sh
```

Esperado: backup local e Object Storage concluídos, aplicação e worker reiniciados, e mensagem de produção atualizada.

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/ready
```

Esperado: versão `1.23.0`, ambiente `production`, banco `reachable`, migração `0026_v1_23_email_login` e HTTP 200.

```bash
docker compose -f docker-compose.oracle-web.yml ps
```

Esperado: serviços de produção saudáveis.

```bash
docker compose -f docker-compose.oracle-web.yml logs --since 10m app worker | grep -Ei "error|traceback|exception|background_job_failed|unhealthy" || echo "Nenhum erro encontrado na produção."
```

Esperado: `Nenhum erro encontrado na produção.`

## 12. Segunda VM — etapa separada

Não execute um corte para a VM2 apenas por instalar a V1.23.0. Primeiro é necessário criar a instância e os NSGs na OCI, configurar a credencial exclusiva do banco, validar a porta 5432 somente no endereço privado e executar o teste de failback.

O roteiro completo continua em `ARQUITETURA_DUAS_INSTANCIAS_V1220.md` e `INSTRUCOES_ORACLE_V1220.md`. Até a conclusão dessa operação, preserve `FDI_WORKER_LOCATION=local` e mantenha um único worker coordenador.

## Em caso de resultado diferente

Não use `git reset --hard`, não apague volumes e não recrie o banco. Envie:

```bash
git status --short
```

```bash
docker compose -f docker-compose.oracle-web.yml ps
```

```bash
docker compose -f docker-compose.oracle-web.yml logs --tail=150 staging app worker
```

Essas três saídas permitem diagnosticar sem arriscar os dados.
