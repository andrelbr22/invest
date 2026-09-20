# V1.23.0 R3 — scripts Linux preservados em LF

## Motivo

A atualização da R2 construiu a imagem de homologação, mas parou antes de
recriar o banco de teste porque alguns scripts de implantação chegaram ao
servidor com finais de linha do Windows (`CRLF`). O Linux interpretou o
início do arquivo como `bash\r` e recusou sua execução.

## Correção

- todos os scripts `*.sh` do pacote foram normalizados para `LF`;
- o repositório passa a impor `LF` a qualquer script shell por meio de
  `.gitattributes`, independentemente do computador usado para publicar;
- um teste de regressão impede que outro pacote seja aprovado contendo
  `CRLF` em scripts de implantação.

## Segurança operacional

A falha ocorreu antes da cópia do banco de homologação e antes da recriação
do contêiner de staging. A produção não foi modificada. A R3 mantém todas as
correções funcionais e de promoção resiliente da R2.

