# Atualizar para a V1.11.0 no Windows

Os comandos abaixo devem ser executados **um por vez**, no PowerShell.

## 1. Entrar na pasta do projeto

```powershell
cd "C:\Users\André\Documents\formacaoInvestidor_ie"
```

## 2. Informar onde o patch foi baixado

```powershell
$patchV1110 = "$env:USERPROFILE\Downloads\Investment_Engine_V1.11.0_PATCH_FINAL.zip"
```

## 3. Confirmar que o arquivo existe

```powershell
Test-Path -LiteralPath $patchV1110
```

O resultado deve ser `True`. Se aparecer `False`, não prossiga: localize o ZIP e substitua o caminho do passo 2.

## 4. Aplicar a atualização

```powershell
Expand-Archive -LiteralPath $patchV1110 -DestinationPath "." -Force
```

## 5. Validar antes de publicar

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

## 6. Publicar no GitHub

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

O Streamlit reiniciará a aplicação e aplicará a migração do Neon automaticamente. Nenhum comando SQL precisa ser executado.

## 7. Liberar as novas funções

Entre com a conta proprietária e abra:

**Administração > Usuários e permissões**

Para cada conta desejada, marque uma ou ambas:

- **Ver estudo e ranking dos backtests**;
- **Ver notícias da carteira e recomendações de bancos**.

Ao liberar notícias, a visualização da carteira também é habilitada, pois as notícias individuais usam somente os ativos da própria carteira do usuário.
