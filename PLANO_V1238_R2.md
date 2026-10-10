# Compromisso da V1.23.8 R2

A R2 será iniciada somente depois que a R1 estiver instalada, homologada e
operacional, com medições reais suficientes para comparar antes e depois.

Escopo comprometido:

1. ativar o worker na segunda VM pela rede privada, mantendo um único banco na
   VM principal, um scheduler e um monitor de alertas;
2. executar e documentar o retorno automático e manual do worker à VM principal;
3. medir consultas PostgreSQL, espera de I/O, pool e índices antes de ajustar
   qualquer parâmetro;
4. criar respostas compactas ou virtualização apenas nos painéis que a
   telemetria da R1 identificar como gargalo;
5. tornar a evidência de navegador obrigatória na promoção depois que a sessão
   automatizada estiver configurada de forma segura.

Não será criado um segundo banco gravável nem serão removidos fallbacks antes
de comprovar cobertura e estabilidade.
