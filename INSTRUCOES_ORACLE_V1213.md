# Implantação e homologação da V1.21.3

> **Produção bloqueada:** a V1.21.3 deve ir primeiro para `/testefdi`. Não execute a promoção sem uma nova aprovação expressa após toda a homologação.

## 1. Validar o pacote no Windows

No PowerShell, já dentro da pasta descompactada:

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

Esse comando somente valida. Depois de autorização expressa para o ambiente de teste:

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

## 2. Atualizar somente o ambiente de teste

Conectado à Oracle por SSH:

```bash
cd ~/invest
./deployment/update-staging-from-github.sh
```

Não execute `promote-staging-to-production.sh` nesta etapa.

## 3. Verificar saúde, versão e migração

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Resultado esperado:

- `version`: `1.21.3`
- `environment`: `staging`
- `database`: `reachable`
- `migration`: `0021_v1_21_access_levels`
- HTTP `200`

## 4. Executar a regressão automatizada

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 -q -p no:cacheprovider
```

Todos os testes devem terminar aprovados. Avisos de descontinuação de bibliotecas, sem falhas, não bloqueiam esta versão.

## 5. Conferir os níveis criados

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine_staging -c "SELECT slug, name, is_active, sort_order FROM access_levels ORDER BY sort_order, name;"
```

Devem aparecer `guest`, `basic`, `member`, `vip` e `owner`.

Para conferir quantas contas ainda estão preservadas em modo legado e quantas já usam níveis:

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine_staging -c "SELECT COALESCE(l.slug,'legacy') AS nivel, COUNT(*) FROM user_access_policies u LEFT JOIN access_levels l ON l.id=u.access_level_id GROUP BY 1 ORDER BY 1;"
```

## 6. Roteiro visual obrigatório

### Alertas

1. Entre como proprietário em `https://formacaodoinvestidor.com.br/testefdi/`.
2. Abra `Minha Carteira > Alertas`.
3. Confirme os avisos `B3: 5 minutos` e `demais mercados: 30 minutos`.
4. Pesquise `BBAS3` e `BTCUSD`.
5. Confirme os quatro campos de condição conforme as permissões da conta.
6. Crie um alerta que não esteja perto de disparar, edite-o, desative-o e reative-o.
7. Salve um segundo e-mail, se desejar, e use o envio de teste.
8. Confira que o histórico mostra horário, destinatários e situação da entrega.

### Notícias

1. Abra `Minha Carteira > Notícias`.
2. Alterne entre `Ativos da carteira` e `Recomendações`.
3. Teste os filtros `Todas`, `Brasil` e `Exterior`.
4. Confirme fonte e data de publicação.
5. Em uma conta secundária autorizada, confirme que o primeiro acesso do dia inicia a atualização sem travar a navegação.
6. Solicite atualização manual e continue navegando enquanto ela ocorre.

### Níveis e usuários

1. Abra `Administração > Níveis e permissões`.
2. Confirme os cinco níveis padrão, as 24 permissões e os 6 limites.
3. Confirme que o nível Proprietário não pode ser reduzido.
4. Abra `Usuários` e teste busca, filtro por nível/status e paginação.
5. Em uma conta secundária, atribua um nível e depois altere uma permissão desse nível. Confirme que o acesso efetivo da conta mudou.
6. Teste a atribuição em lote somente com contas de homologação.
7. Confirme que contas não migradas aparecem como `Personalizado legado`.

### Atualizações, fila e sistema

1. Abra `Administração > Dados de mercado` e confirme exatamente 13 rotinas.
2. Confira fonte, estado, última atualização e próxima atualização.
3. Acione uma rotina isolada e confirme que entra na fila sem travar a página.
4. Confirme os quatro botões de grupos e `Atualizar todas as 13 rotinas`; não execute todas sem necessidade.
5. Execute o monitor manual de alertas e confira o resumo.
6. Abra `Fila de trabalhos`, confira progresso, tentativas e mensagens. A opção `Reprocessar` deve aparecer somente em falhas ou cancelamentos.
7. Abra `Sistema` e confirme saúde e contagens do banco.

## 7. Verificar fila e registros do staging

```bash
docker compose -f docker-compose.oracle-web.yml exec -T postgres psql -U investment -d investment_engine_staging -c "SELECT job_type,status,attempts,message,updated_at FROM background_jobs ORDER BY created_at DESC LIMIT 20;"
```

```bash
docker compose -f docker-compose.oracle-web.yml logs --since 20m staging | grep -Ei "error|traceback|exception|unhealthy" || echo "Nenhum erro encontrado no staging."
```

## 8. Promoção somente depois da aprovação final

Depois de o usuário escrever expressamente que aprova a V1.21.3 para produção:

```bash
./deployment/promote-staging-to-production.sh
```

Em seguida, valide `/ready`, o estado dos contêineres e os registros do worker. Sem essa aprovação, pare ao final da homologação do staging.

