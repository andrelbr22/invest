# Atualização V1.8.1 no Windows

## Pacote completo — recomendado

1. Extraia o ZIP completo em uma pasta nova.
2. Abra essa pasta no PowerShell.
3. Valide:

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

4. Se aparecer **Pacote validado**, publique:

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

5. Aguarde o Streamlit reiniciar e confirme: `Motor online • versão 0.9.1`.

## Patch

O patch pode ser extraído sobre uma cópia limpa da V1.8.0, aceitando a substituição dos arquivos. Depois, execute a validação e a publicação acima.

## Após publicar

Se algum ativo aparecer sem porte, abra **Dados usados pelos filtros** e clique em **Carregar / atualizar dados de Ações**. Isso preenche o valor de mercado e a classificação sem migração.
