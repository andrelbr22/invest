# Atualizar para a V1.10.0 no Windows

## 1. Aplicar o patch

Baixe `Investment_Engine_V1.10.0_PATCH.zip` normalmente. Depois abra o PowerShell e execute uma linha por vez:

```powershell
cd "C:\Users\André\Documents\formacaoInvestidor_ie"

$patchV1100 = "$env:USERPROFILE\Downloads\Investment_Engine_V1.10.0_PATCH.zip"

Test-Path -LiteralPath $patchV1100

Expand-Archive -LiteralPath $patchV1100 -DestinationPath "." -Force

Select-String -Path .\pyproject.toml -Pattern 'version ='
```

`Test-Path` deve mostrar `True`. A última linha deve mostrar `version = "0.11.0"`.

## 2. Validar e publicar

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly

powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

## 3. Conferir no site

Depois que o Streamlit concluir a atualização:

1. Confira `motor 0.11.0` na barra lateral.
2. Em **Mercado e análise**, confirme que Ações e FIIs abrem no Padrão com até 50 resultados.
3. Confirme que Porte, IBOV e Setor aparecem como subfiltros.
4. Abra **Demais Ativos B3**. Se o catálogo estiver vazio, abra **Dados usados pelos filtros** e clique em **Carregar / atualizar dados de Demais Ativos B3**.
5. Na conta proprietária, abra **Administração** para acessar o lote manual de backtests e as permissões.

Esta versão não cria novas tabelas nem exige uma migração adicional do PostgreSQL.
