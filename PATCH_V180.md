# Atualização V1.8.0 no Windows

## Opção recomendada: pacote completo

1. Extraia o ZIP completo em uma pasta nova, por exemplo `C:\Users\André\Documents\InvestmentEngineV180`.
2. Não copie `.env`, senhas, chaves ou `secrets.toml` para o GitHub.
3. No PowerShell, entre na pasta extraída.
4. Valide o pacote:

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1 -ValidateOnly
```

5. Se aparecer **Pacote validado**, publique:

```powershell
powershell -ExecutionPolicy Bypass -File .\PUBLICAR_GITHUB.ps1
```

6. Aguarde o servidor Oracle atualizar e confirme no menu lateral: `Motor online • versão 0.9.0`.

## Opção patch

Use somente se você ainda possui uma pasta limpa da V1.7.5:

1. faça uma cópia de segurança da pasta V1.7.5;
2. extraia o ZIP patch sobre essa cópia e aceite substituir os arquivos;
3. execute as duas etapas do `PUBLICAR_GITHUB.ps1` mostradas acima.

## Banco de dados

A V1.8.0 não exige migração. As URLs PostgreSQL e as credenciais Google continuam somente nos Secrets privados do servidor e não devem ser colocadas nos ZIPs ou no GitHub.
