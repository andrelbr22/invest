# Patch V1.23.5 R2B

## Motivo

O código R2A estava corretamente no host e no staging, mas a verificação
inicial da promoção era executada dentro do contêiner de produção anterior.
Esse contêiner ainda continha o verificador R2 e interrompia a promoção antes
que a nova imagem pudesse substituí-lo.

## Correção

O script aprovado no host é transmitido pela entrada padrão ao Python do
contêiner atual. Desse modo ele usa as bibliotecas, credenciais e banco da
produção, porém aplica exatamente as regras do commit homologado.

Não há alteração de tela, API, banco, dados, cálculos ou permissões. A versão
continua `1.23.5` e a migração continua `0030_v1_23_navigation_metrics`.
