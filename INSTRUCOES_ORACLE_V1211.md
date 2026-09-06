# Homologação da V1.21.1 na Oracle

## 1. Publicação segura

1. Extraia o ZIP em uma pasta nova e vazia no Windows.
2. Execute `powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly`.
3. Publique somente após autorização explícita.
4. Na Oracle, atualize apenas o staging com `./deployment/update-staging-from-github.sh`.
5. Não promova para produção até concluir todo o roteiro abaixo.

## 2. Saúde esperada

```bash
curl -sS -w "\nHTTP %{http_code}\n" https://formacaodoinvestidor.com.br/testefdi/ready
```

O retorno deve indicar versão `1.21.1`, ambiente `staging`, banco alcançável e migração `0020_v1_21_valuation_access`.

## 3. Conta administradora

Confira a configuração sem exibir qualquer segredo:

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -c 'from investment_engine.infrastructure.config import settings; print("Administrador configurado:", "andrelbr22@gmail.com" in settings.owner_emails)'
```

O resultado esperado é `Administrador configurado: True`. No site, o perfil deve mostrar `Administrador master`. Essa conta recebe todas as permissões automaticamente; não é necessário alterar sua linha no banco.

## 4. Testes automatizados

```bash
docker compose -f docker-compose.oracle-web.yml exec -T staging python -m pytest tests_v1160 tests_v1170 tests_v1200 tests_v1202 tests_v1203 tests_v1204 tests_v1205 tests_v1206 tests_v1207 tests_v1210 -q -p no:cacheprovider
```

Não pode existir teste com falha. Avisos de descontinuação das bibliotecas não impedem a homologação.

## 5. Roteiro visual corrigido

1. Abra Mercado e Análises > Ações > Filtros e análises.
2. Confirme que Padrão, FDI e ALB respeitam as permissões da conta.
3. Localize `Potencial mínimo (%)`, passe o mouse ou toque no `?` e confira fórmula e exemplo.
4. Marque `Valor econômico`. A seção **Cenários do valor econômico: Conservador, Base e Otimista** deve estar aberta e exibir retorno, crescimento e margem de segurança.
5. Confirme o uso explícito do provento TTM, aplique os ajustes e verifique que a coluna do método aparece automaticamente.
6. Na coluna, confira as referências C, B e O. Clique no ativo e valide valores, potenciais, qualidade, amostra, premissas e mensagens `N/D`.
7. Repita a navegação em FIIs. Graham deve continuar indisponível.
8. Abra ETFs, BDRs e Futuros. Os botões Padrão, FDI e ALB devem abrir configurações técnicas e retornar ativos conforme as autorizações.
9. Nessas três classes, confirme que as quatro metodologias continuam visíveis e cada opção indisponível explica os insumos ausentes. Não deve surgir fórmula inadequada.
10. Se houver limite de análise personalizada, grave e reabra um filtro técnico em cada classe.
11. Alterne repetidamente entre Painel de Mercado, Mercado e Análises, Carteira e Backtests. O retorno a dados recém-abertos deve ser imediato ou sensivelmente mais rápido.
12. Force uma atualização de dados e confirme que o cache é invalidado e a tela recebe os valores novos.
13. Valide em computador e celular.

## 6. Operação e produção

```bash
docker compose -f docker-compose.oracle-web.yml ps
docker compose -f docker-compose.oracle-web.yml logs --since 15m staging | grep -Ei "error|traceback|exception|unhealthy" || echo "Nenhum erro encontrado no staging."
```

Somente após uma nova aprovação explícita promova com:

```bash
./deployment/promote-staging-to-production.sh
```

Nunca envie arquivos de `deployment/secrets`, chaves, senhas ou tokens ao GitHub ou à conversa.
