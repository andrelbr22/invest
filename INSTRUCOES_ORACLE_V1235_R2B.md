# Instruções Oracle • V1.23.5 R2B

Siga o fluxo completo de `INSTRUCOES_ORACLE_V1235_R2A.md`. A R2B não muda
versão, migração, testes de cobertura ou metas do benchmark.

Antes de promover, confirme que o arquivo do host contém a execução por entrada
padrão e não o caminho antigo dentro do contêiner:

```bash
sed -n '119,136p' deployment/promote-staging-to-production.sh
```

O trecho deve conter `python -` e a entrada:

```text
< "${PROJECT_DIR}/deployment/second-instance/verify-worker-coordination.py"
```

Depois da regressão, cobertura, benchmark e homologação visual aprovados, use
um log novo:

```bash
PROMOTION_LOG="$(mktemp /tmp/promocao-v1235-r2b.XXXXXX.log)"; printf 'Log da promoção: %s\n' "$PROMOTION_LOG"
```

```bash
nohup ./deployment/promote-staging-to-production.sh >> "$PROMOTION_LOG" 2>&1 & echo "PID da promoção: $!"
```

```bash
tail -f "$PROMOTION_LOG"
```

O resultado esperado é a conclusão da promoção, sem a mensagem antiga
`pertence a outro processo do nó esperado`.
