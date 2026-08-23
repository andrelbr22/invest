# Atualizar para a V1.9.0 no Windows

## 1. Fazer uma cópia de segurança

Copie a pasta atual `C:\Users\André\Documents\formacaoInvestidor_ie` para outro local antes da atualização.

## 2. Aplicar o patch

Abra o PowerShell e execute as linhas completas, uma por vez:

```powershell
cd "C:\Users\André\Documents\formacaoInvestidor_ie"

Expand-Archive -LiteralPath "CAMINHO_ONDE_BAIXOU\Investment_Engine_V1.9.0_PATCH.zip" -DestinationPath "." -Force

Select-String -Path .\pyproject.toml -Pattern 'version ='
```

O resultado deve mostrar `version = "0.10.0"`.

## 3. Validar e publicar

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly

powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

Não digite somente `-ExecutionPolicy`; a linha precisa começar com `powershell`.

## 4. Reiniciar o Streamlit

Espere a atualização automática. Se necessário, abra **Manage app** no Streamlit Community Cloud e clique em **Reboot app**. A primeira inicialização executará a migração aditiva do Neon.

## 5. Ativar a rotina semanal

Siga `ATIVAR_BACKTESTS_SEMANAIS.md`. Essa etapa cadastra a conexão do Neon nos segredos do GitHub Actions e permite executar o primeiro catálogo oficial.

## 6. Conferir

No aplicativo:

1. A barra lateral deve mostrar motor `0.10.0`.
2. Abra **Backtests** e confirme as áreas “Cinco melhores backtests oficiais” e “100 backtests mais recentes”.
3. Abra **Mercado e análise**; a lista dos três melhores aparecerá depois do primeiro lote oficial.
4. Em **Usuários e permissões**, escolha quem poderá ver, executar e atualizar sinais.
