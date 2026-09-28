# Homologação Oracle — V1.23.1 R2

Não promova antes de concluir todas as etapas no ambiente de teste.

## 1. Atualizar o staging

```bash
cd ~/invest
./deployment/update-staging-from-github.sh
```

Esperado: construção concluída, cópia isolada do banco, staging saudável e
proxy disponível.

## 2. Conferir versão e migração

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

Esperado: versão `1.23.1`, ambiente `staging`, banco `reachable`, migração
`0028_v1_23_operational_retention` e HTTP 200.

## 3. Executar a regressão completa

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest -q -p no:cacheprovider
```

Esperado: todos os testes aprovados. Avisos de descontinuação não são falhas.

## 4. Simular a retenção sem excluir

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.prune_operational_history
```

Esperado: JSON com `"mode": "dry_run"`, `"archived": 0` e `"deleted": 0`.
As quantidades em `eligible` podem ser zero ou maiores conforme a idade da
cópia do banco.

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.verify_operational_archive
```

Esperado: JSON com `"valid": true` e `"mismatch_count": 0`.

## 5. Medir desempenho

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m scripts.benchmark_application_routes --samples 20 --warmup 2
```

Esperado: health, dashboard, screener 50, screener 100 e detalhe terminados em
`OK`. Não promova se aparecer `ACIMA_DA_META`.

## 6. Validar visualmente

1. Entrar na plataforma e alternar entre todos os painéis.
2. Confirmar usuários, níveis e permissões na Administração.
3. Alterar e restaurar um preset no staging e confirmar efeito imediato.
4. Confirmar o Painel de Mercado e a situação das atualizações.
5. Em Administração, verificar a rotina “Retenção operacional”.
6. Confirmar que CSS e JavaScript correspondem à R2 após recarregar a página.

## 7. Conferir serviços e logs

```bash
docker compose -f docker-compose.oracle-web.yml ps
```

Esperado: `app`, `postgres`, `staging` e `worker` saudáveis; `proxy` ativo.

```bash
docker compose -f docker-compose.oracle-web.yml logs --since 30m staging | grep -Ei "error|traceback|exception|failed|unhealthy" || echo "Nenhum erro encontrado no staging."
```

Esperado: `Nenhum erro encontrado no staging.`

## 8. Promover somente após aprovação expressa

```bash
./deployment/promote-staging-to-production.sh
```

O benchmark será repetido antes de qualquer alteração da produção. Depois da
promoção, `/ready` deve informar versão `1.23.1`, ambiente `production`,
migração `0028_v1_23_operational_retention` e HTTP 200.
