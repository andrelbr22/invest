# Relatório de validação — V1.23.8 R2A

## Causa corrigida

A suíte histórica continha cinco asserções de identidade ainda fixadas em R1 e
uma asserção que procurava a forma textual anterior do opt-in do failback. O
código R2 continuava seguro e os demais 505 testes haviam sido aprovados.

## Garantias preservadas

- failback desativado por padrão;
- autorização efêmera exata apenas para o ensaio controlado;
- limiar mínimo de três falhas consecutivas;
- nenhuma ativação automática da VM2;
- um único worker, scheduler e monitor de alertas;
- nenhuma mudança em dados, fórmulas, permissões, interface, API ou esquema.

## Validação obrigatória no staging

- suíte histórica completa sem falhas;
- cobertura de métricas de navegação completa;
- benchmark interno dentro das metas;
- homologação visual dos painéis e da área administrativa;
- ausência de erros novos nos logs.

## Validação local do pacote

- 46 testes diretamente relacionados às seis falhas: aprovados;
- suíte `tests_v1238`: 16 testes aprovados;
- publicador em `-ValidateOnly`: pacote aprovado, nenhum arquivo enviado;
- a execução histórica completa no Windows foi interrompida após ficar presa
  numa dependência do ambiente local, sem registrar falha; por isso, os 511
  testes continuam obrigatórios no contêiner Linux do staging.
