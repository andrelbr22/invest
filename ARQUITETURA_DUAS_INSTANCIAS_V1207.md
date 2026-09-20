# Formação do Investidor — arquitetura segura com duas instâncias

## Objetivo

Liberar memória e CPU do servidor que atende os usuários sem criar dois bancos concorrentes ou duas fontes de verdade.

- **Instância 1 — Web e dados críticos:** Caddy, API web e PostgreSQL.
- **Instância 2 — Processamento:** atualizações de mercado, notícias, fundamentos, indicadores técnicos, alertas e trabalhos pessoais de backtest.

O navegador continua acessando somente `formacaodoinvestidor.com.br`. A segunda instância não publica portas web.

## Ganhos esperados

1. Consultas e navegação deixam de competir por CPU com ingestões pesadas.
2. Falha em um provedor externo não derruba o processo web.
3. O trabalhador pode usar mais memória sem pressionar o PostgreSQL.
4. A fila persistente permite reinício e retomada dos trabalhos.

## Regras de segurança obrigatórias

1. As duas instâncias devem estar na mesma VCN/sub-rede privada ou ligadas por uma rede privada equivalente.
2. A porta 5432 deve aceitar tráfego **somente do IP privado da instância 2**.
3. Nunca publicar 5432 em `0.0.0.0`, no IP público ou para `0.0.0.0/0` em uma NSG.
4. O arquivo `worker_secrets.toml` deve ter permissão `600` e nunca entrar no Git.
5. Antes de ativar o trabalhador remoto, desativar o trabalhador local. Dois monitores de alertas simultâneos podem produzir notificações duplicadas.
6. O banco continua sendo copiado diariamente para o Object Storage.

## Ordem de implantação — sem interrupção

1. Criar a segunda VM gratuita na mesma região e VCN, preferencialmente Ampere A1 se houver disponibilidade; uma VM AMD gratuita também funciona.
2. Criar uma NSG específica. Na instância 1, permitir TCP 5432 apenas a partir do IP privado ou NSG da instância 2.
3. No firewall do Ubuntu da instância 1, repetir a mesma restrição.
4. Copiar o repositório para a instância 2 no mesmo commit que está em produção.
5. Copiar `worker_secrets.toml.example` para `worker_secrets.toml`, informar o IP privado e testar a conexão com o banco.
6. Iniciar o contêiner remoto com o agendador e o monitor ainda desativados; validar saúde e DNS.
7. Parar o serviço `worker` local.
8. Ativar agendador e alertas na instância 2 e observar a fila por 15 minutos.
9. Confirmar que existe somente um trabalho de cada agenda e somente um monitor de alertas.

## Retorno rápido

Se a instância 2 falhar, pare o trabalhador remoto e reative o serviço `worker` do `docker-compose.oracle-web.yml` na instância 1. A fila está no PostgreSQL e os trabalhos pendentes serão retomados.

## O que não será feito

- Não haverá um segundo banco gravável para os mesmos dados.
- Não haverá réplica manual sem mecanismo formal de replicação.
- O ambiente de produção não será promovido automaticamente.
- A segunda VM não receberá credenciais Google, pois não atende login de usuários.

## Evolução posterior

Depois de uma semana estável, o ambiente `/testefdi` também pode ir para a segunda instância. Essa etapa exige uma rota privada no Caddy e deve ser realizada separadamente, preservando a aprovação manual antes da produção.
