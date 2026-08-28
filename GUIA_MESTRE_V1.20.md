# Formação do Investidor — Prompt e Guia Mestre da Versão 1.20

**Documento de especificação, continuidade e execução segura**  
**Base obrigatória:** Formação do Investidor V1.17.4  
**Data de planejamento:** 28 de agosto de 2026  
**Situação:** escopo aprovado pelo proprietário; sugestões extras permanecem bloqueadas até autorização expressa.

> **Finalidade deste documento**  
> Entregar ao programador — inclusive um programador amador ou um agente de programação — um roteiro completo para construir a V1.20 sem apagar, simplificar indevidamente ou quebrar nada que já funciona. Este documento deve ser usado junto com o guia de continuidade da V1.17.4 e com o código atualmente publicado no repositório oficial.

---

## 1. Prompt mestre para iniciar o desenvolvimento

Copie o texto desta seção e entregue ao responsável pela implementação.

> Você é o responsável técnico pela evolução do **Formação do Investidor**, da versão **1.17.4** para a família **1.20.x**. Trabalhe sobre o repositório existente e leia integralmente, antes de alterar qualquer arquivo, o guia `GUIA_COMPLETO_CONTINUIDADE_FORMACAO_INVESTIDOR_V1.17.4.md`, este guia da V1.20, o `README.md`, os arquivos de publicação e os testes existentes.
>
> A aplicação atual é uma solução própria em **FastAPI/Uvicorn, HTML, CSS e JavaScript**, PostgreSQL, Alembic, Docker, Caddy, GitHub e Oracle Cloud. Não reintroduza o serviço de hospedagem antigo, não crie atalhos paralelos e não troque a arquitetura principal sem autorização. Produção permanece em `https://formacaodoinvestidor.com.br/` e homologação em `https://formacaodoinvestidor.com.br/testefdi/`.
>
> Trate a V1.17.4 como uma linha de base imutável. Preserve autenticação Google, isolamento dos dados por usuário, permissões, carteira, filtros salvos, catálogo, alertas, notícias, backtests, homologação separada, promoção manual para produção, backups e retorno de versão. Toda mudança de banco deve usar Alembic, ser retrocompatível durante a implantação e possuir teste de migração e restauração.
>
> Implemente a V1.20 em etapas pequenas, cada uma com testes automatizados, teste visual, critérios de aceite e possibilidade de reversão. Nunca publique diretamente em produção. Publique primeiro em homologação; só promova após autorização expressa do proprietário.
>
> Antes de programar, produza um inventário de impacto: arquivos afetados, tabelas e índices novos, rotas novas, permissões novas, tarefas de segundo plano, fontes externas, custos de memória, riscos e plano de retorno. Não remova funções, arquivos, campos, migrações ou testes antigos para “facilitar” o trabalho. Se for necessário descontinuar algo, apresente a justificativa e aguarde autorização.
>
> A interface não pode ficar esperando fontes externas. Toda coleta lenta deve ocorrer em segundo plano. A tela deve abrir com o último dado válido, informar data e fonte, atualizar de forma assíncrona e continuar navegável. Consultas devem usar paginação e índices; trabalhos pesados devem entrar em fila. O sistema precisa permanecer utilizável mesmo quando uma fonte externa estiver lenta ou indisponível.
>
> Implemente exatamente o escopo aprovado nas seções 7 a 12 deste guia. As ideias da seção “Sugestões que dependem de nova aprovação” estão expressamente fora do escopo. Não as implemente sem autorização do proprietário.
>
> Ao terminar cada etapa, entregue: resumo em linguagem simples, arquivos modificados, migrações, testes executados, medição antes/depois, pendências, instruções separadas para Windows e Oracle, endereço de homologação e roteiro de validação. Nunca mostre nem registre senhas, tokens, chaves ou dados financeiros pessoais.

---

## 2. Resultado esperado da V1.20

A V1.20 deve transformar a plataforma em uma aplicação mais rápida e previsível, com quatro avanços principais:

1. **Infraestrutura dividida:** site e API em uma máquina; banco, fila e trabalhos de segundo plano em outra, quando a segunda instância gratuita estiver disponível.
2. **Leitura imediata:** os painéis abrem a partir do banco e do cache, sem aguardar coleta externa.
3. **Análises explicáveis:** filtros, médias, notas, estratégias e sinais apresentam conceitos, parâmetros, fonte e data de referência.
4. **Vida financeira completa:** a carteira passa a aceitar investimentos não negociados em bolsa e nasce o painel Minhas Finanças.

### 2.1 O que não muda

- O domínio oficial e o fluxo de login Google.
- A aplicação própria FastAPI/Uvicorn + HTML/CSS/JavaScript.
- PostgreSQL como banco transacional.
- GitHub como repositório e executor de backtests oficiais quando necessário.
- Oracle Cloud como infraestrutura de execução.
- Cloudflare no DNS e Caddy como entrada HTTPS.
- Homologação em `/testefdi/` e produção na raiz.
- Promoção manual de homologação para produção.
- Isolamento de dados por `owner_email` ou identificador interno equivalente.
- Permissões concedidas apenas pelo proprietário.
- Backups locais e no Object Storage antes de promoção ou migração.

### 2.2 Regra máxima de preservação

Nenhuma tarefa da V1.20 autoriza “começar de novo”. Antes de uma refatoração:

- congele uma referência da V1.17.4;
- rode os testes existentes;
- registre o comportamento atual;
- acrescente testes de regressão;
- faça a menor alteração suficiente;
- valide em homologação;
- mantenha retorno para a imagem e o banco anteriores.

---

## 3. Diagnóstico da arquitetura atual

A V1.17.4 já possui uma base sólida: API própria, páginas próprias, autenticação, PostgreSQL, catálogo de ativos, filtros avançados, pivôs, volume, carteira isolada, alertas, notícias, backtests, permissões, staging e publicação controlada. Os principais limites são de capacidade e concentração:

- uma VM `VM.Standard.E2.1.Micro`, com 1 GB de memória, executa site, API, PostgreSQL, homologação e proxy;
- coletas de mercado, notícias, alertas e tarefas administrativas concorrem com consultas do usuário;
- os arquivos `investment_engine/api/app.py` e `investment_engine/web/app.js` concentram responsabilidades demais;
- algumas telas ainda dependem de chamadas grandes e podem ser afetadas pelo cancelamento de uma requisição;
- a configuração de testes indica `tests`, embora o pacote atual use diretórios versionados de testes;
- fontes externas têm frequências, formatos e disponibilidade diferentes, mas precisam ser apresentadas com comportamento uniforme;
- um backtest amplo pode gerar explosão combinatória se estratégias e ativos não tiverem limites explícitos.

O plano não deve tentar resolver tudo com mais cache em memória na mesma máquina. O ganho principal virá de separar responsabilidades, limitar concorrência e pré-calcular leituras.

---

## 4. Segunda instância gratuita: decisão e arquitetura recomendada

### 4.1 É possível criar outra instância gratuita?

Em princípio, sim. A documentação Always Free da Oracle informa que uma tenancy pode ter **até duas VMs `VM.Standard.E2.1.Micro`**, sujeitas à região principal, à cota, ao armazenamento de boot e à capacidade disponível. A franquia de Block Volume é compartilhada e deve ser conferida antes da criação. A forma `VM.Standard.A1.Flex` oferece mais recursos, porém costuma ter indisponibilidade de capacidade e usa arquitetura ARM.

Não presuma gratuidade apenas porque a forma aparece na tela. Antes de confirmar, verifique:

- selo **Always Free eligible**;
- previsão de custo igual a zero;
- quantidade de VMs E2 já usada;
- total de volumes de boot e blocos;
- região principal da tenancy;
- ausência de recursos pagos opcionais.

### 4.2 Topologia recomendada

```text
Internet
   │
Cloudflare DNS
   │ HTTPS 443
Instância 1 — WEB
   ├─ Caddy
   ├─ FastAPI/Uvicorn de produção
   ├─ autenticação e arquivos web
   └─ cache local de último painel público válido
          │ rede privada da VCN
          ▼
Instância 2 — DADOS E TRABALHOS
   ├─ PostgreSQL
   ├─ worker de fila, concorrência inicial = 1
   ├─ atualização de mercado, agenda e notícias
   ├─ monitor de alertas
   ├─ homologação sob demanda
   └─ backup para Object Storage
          │
          └─ GitHub Actions: cálculo pesado de backtests e entrega autenticada
```

### 4.3 Responsabilidades de cada máquina

| Componente | Instância 1 — web | Instância 2 — dados |
|---|---:|---:|
| Caddy e HTTPS público | Sim | Não |
| Interface e rotas HTTP | Sim | Apenas saúde interna, se necessário |
| PostgreSQL | Não, após migração | Sim |
| Coleta de fontes externas | Não | Sim |
| Fila e agendador | Enfileira | Executa |
| Alertas periódicos | Não | Sim |
| Homologação | Proxy para ela | Sob demanda |
| Backups do banco | Aciona verificação | Cria e envia |
| Portas públicas 80/443 | Sim | Não |

### 4.4 Rede e segurança

- Coloque as duas máquinas na mesma VCN e região.
- Use o endereço **privado** da Instância 2 para PostgreSQL.
- Permita a porta 5432 somente a partir do IP privado da Instância 1 e dos próprios serviços da Instância 2.
- Não exponha 5432, o worker ou a homologação diretamente à internet.
- Restrinja SSH ao endereço administrativo conhecido ou use o Bastion da OCI.
- Mantenha 80/443 públicos apenas na Instância 1.
- Permita saída HTTPS da Instância 2 para fontes oficiais e GitHub.
- Armazene segredos fora do Git; use arquivo protegido ou OCI Vault, sem exibição em logs.

### 4.5 Alternativa se uma A1 ficar disponível

Se uma `VM.Standard.A1.Flex` Always Free puder ser criada com segurança, ela é preferível para dados e tarefas por oferecer mais memória. Como é ARM, a implantação deve gerar imagens compatíveis com `linux/arm64` e `linux/amd64`, e todas as dependências devem ser testadas nas duas arquiteturas. Nunca elimine a E2 funcionando antes de homologar a A1.

### 4.6 Alternativa temporária sem segunda instância

Enquanto a segunda VM não existir:

- mantenha a arquitetura atual;
- execute um único worker por vez;
- deixe homologação desligada fora das janelas de teste;
- limite memória dos contêineres;
- mantenha 4 GB de swap;
- evite tarefas de catálogo e backtest no horário de maior uso;
- sirva dados antigos válidos enquanto ocorre atualização.

### 4.7 Migração sem perda

1. Registrar saúde, versão, tamanho do banco e commit implantado.
2. Criar backup lógico compactado e enviar ao Object Storage.
3. Testar a leitura do arquivo de backup.
4. Criar e proteger a segunda VM.
5. Instalar Docker e subir PostgreSQL vazio com a mesma versão principal.
6. Restaurar o backup em banco de homologação.
7. Validar contagens de ativos, usuários, carteiras, filtros, backtests, alertas e notícias.
8. Apontar somente a homologação para o novo banco.
9. Executar testes de regressão e carga leve.
10. Parar novas gravações por uma janela curta, criar backup final e restaurá-lo.
11. Alterar produção para o endereço privado da Instância 2.
12. Manter o banco antigo sem gravações durante 48 horas para retorno.
13. Depois da aprovação, remover apenas o contêiner antigo; nunca apagar o backup.

**Retorno:** restaurar a variável de conexão anterior, recriar o contêiner web e verificar `/health`. Não permita escrita simultânea nos dois bancos.

---

## 5. Estratégia obrigatória de desempenho e estabilidade

### 5.1 Regra de ouro

Uma requisição aberta pelo navegador **não pode coletar dados externos**. Ela deve ler o último resultado válido do banco/cache, devolver a resposta e, quando necessário, enfileirar a atualização.

### 5.2 Fila PostgreSQL, sem serviço adicional pesado

Para economizar memória, use uma fila persistida no próprio PostgreSQL, não Redis na V1.20. A tabela de trabalhos deve ter, no mínimo:

- `id`, `job_type`, `payload_json`;
- `status`: queued, running, succeeded, failed, cancelled;
- `priority`, `run_after`, `attempts`, `max_attempts`;
- `locked_by`, `locked_at`, `heartbeat_at`;
- `progress_current`, `progress_total`, `message`;
- `deduplication_key` e `idempotency_key`;
- `created_at`, `started_at`, `finished_at`, `last_error_code`.

O worker deve obter o próximo trabalho com bloqueio transacional equivalente a `FOR UPDATE SKIP LOCKED`. Comece com concorrência 1. Só aumente depois de medir memória e tempo.

### 5.3 Stale-while-revalidate

Para mercado, agenda, notícias e indicadores:

1. devolva imediatamente o último snapshot válido;
2. informe “atualizado em”, “data de referência” e “fonte”;
3. se estiver vencido, enfileire uma atualização única;
4. preserve o snapshot anterior se a fonte falhar;
5. mostre aviso discreto de dado desatualizado, sem bloquear a página.

Use chave de deduplicação por série, ativo e janela. Dois usuários não podem disparar a mesma coleta simultaneamente.

### 5.4 Proteção contra falhas externas

- tempo limite individual por fonte;
- novas tentativas com espera crescente e jitter;
- circuit breaker após falhas consecutivas;
- limite por domínio;
- validação de esquema e unidade antes de salvar;
- nunca substituir dado válido por resposta vazia;
- logar código seguro, não o conteúdo sensível da resposta;
- permitir correção manual pelo administrador quando a fonte oficial mudar.

### 5.5 Banco e consultas

- pool web inicial: `pool_size=5`, `max_overflow=2`, `pool_pre_ping=True`, reciclagem de 30 minutos;
- `statement_timeout` entre 8 e 15 segundos nas consultas da interface;
- paginação por cursor/data e identificador, evitando `OFFSET` alto;
- nada de `SELECT *` em listas;
- carregar preços e indicadores em lote, sem N+1;
- pré-calcular resumos usados em todos os acessos;
- verificar novas consultas com `EXPLAIN (ANALYZE, BUFFERS)` em homologação;
- executar `VACUUM/ANALYZE` e política de retenção fora do horário de pico;
- índices compostos conforme a seção 13.

### 5.6 Interface e rede

- carregar apenas a aba visível;
- paginação ou virtualização das tabelas grandes;
- esqueleto visual durante a leitura;
- atualizar cards e tabelas em blocos independentes;
- cancelamento limitado à requisição daquela aba, nunca ao estado global;
- preservar os dados anteriores durante uma atualização;
- usar ETag/Last-Modified em dados públicos compartilhados;
- usar `Cache-Control: no-store` em carteira, finanças e administração;
- manter compressão no Caddy;
- não transferir séries de 20 anos completas a cada clique: cache e redução visual, preservando a série integral para cálculos.

### 5.7 Metas mensuráveis

| Medida em homologação | Meta inicial V1.20 |
|---|---:|
| `/health` p95 | abaixo de 300 ms |
| shell inicial do site | abaixo de 2,5 s em rede comum |
| painel de mercado com cache p95 | abaixo de 1,5 s |
| screener com 50 linhas p95 | abaixo de 2 s |
| screener com 100 linhas p95 | abaixo de 3 s |
| troca entre abas já carregadas | resposta visual abaixo de 200 ms |
| tarefa externa bloqueando navegação | zero |
| erros não tratados no navegador | zero |
| restauração automática após reinício | abaixo de 5 min |

Registre p50, p95, quantidade de consultas, memória e tempo de cada coleta antes e depois.

### 5.8 Observabilidade mínima

- `/health`: processo vivo e versão;
- `/ready`: banco acessível, migração correta e dependências essenciais;
- logs estruturados com `request_id`, `job_id`, rota, duração e código;
- nunca registrar token, senha, e-mail completo ou valores financeiros pessoais;
- painel administrativo de trabalhos: fila, progresso, última execução, erro seguro e botão de tentar novamente;
- estado “degradado” quando dados antigos ainda podem ser mostrados.

---

## 6. Ordem segura de implementação

Não faça uma grande publicação única. Use a seguinte família de versões:

| Versão | Entrega | Dependência |
|---|---|---|
| 1.20.0 | fila, cache, métricas, correções de testes e preparação para duas VMs | nenhuma |
| 1.20.1 | segunda VM, separação web/dados e homologação sob demanda | 1.20.0 estável |
| 1.20.2 | Painel de Mercado e séries históricas | worker e snapshots |
| 1.20.3 | Mercado e Análises explicáveis e presets | séries e screener estáveis |
| 1.20.4 | Backtests combinados, limites e fila | controle de trabalhos |
| 1.20.5 | novos investimentos da carteira | novas tabelas isoladas |
| 1.20.6 | Minhas Finanças | permissões e tabelas financeiras |
| 1.20.7 | endurecimento, carga, acessibilidade e promoção final | todas as anteriores |

Cada subversão deve passar por homologação, backup e aceite. Se a segunda VM atrasar, 1.20.0 e as telas podem avançar com serviços separados no mesmo host, desde que a interface continue lendo snapshots.

---

## 7. Painel de Mercado

### 7.1 Cards iniciais

Na tela inicial do Painel de Mercado:

- mantenha IBOV e Dólar/Real;
- substitua o card S&P 500 por **IPCA acumulado em 12 meses**;
- o card IPCA deve mostrar valor, mês de referência, data da atualização e fonte IBGE;
- não misture projeção Focus com inflação já realizada.

### 7.2 Resumo de câmbio

Exiba com orientação inequívoca:

- USD/BRL — reais por dólar;
- USD/EUR — euros por dólar;
- EUR/BRL — reais por euro;
- JPY/BRL — reais por iene, preferencialmente também por 100 ienes para leitura;
- GBP/BRL — reais por libra esterlina.

O iene e a libra foram escolhidos por sua relevância no mercado global após dólar e euro. Cada linha deve apresentar valor atual, variações disponíveis, horário e fonte. Nunca inverter um par sem alterar o rótulo e a fórmula.

### 7.3 Curva de Juros Futuros

O nome correto do painel é **Curva de Juros Futuros — DI x Pré**. A curva é relevante porque mostra a taxa anual implícita nos vencimentos do contrato DI1 e ajuda a visualizar a expectativa e o prêmio de juros ao longo do tempo.

Requisitos:

- usar vencimentos DI1 e taxas de ajuste da B3;
- expressar taxa efetiva anual na base de 252 dias úteis;
- eixo X por data de vencimento; eixo Y em `% a.a.`;
- mostrar data de referência e horário da última atualização;
- permitir curva atual e comparação com 1 semana, 1 mês, 3 meses e 1 ano atrás;
- permitir período visível de vencimentos;
- tooltip com contrato, vencimento, taxa e diferença em pontos-base;
- distinguir pontos observados de pontos interpolados;
- se houver interpolação, seguir Flat Forward 252 documentado pela B3;
- nunca extrapolar ou inventar taxa depois do último vencimento disponível;
- apresentar explicação educacional e aviso de que não é recomendação.

### 7.4 Comparador histórico de investimentos e índices

Crie uma aba **Comparador Histórico**. O usuário seleciona várias séries e um período: 6 meses, 1, 2, 3, 5, 10, 15 ou 20 anos.

Séries obrigatórias:

- CDI;
- IBOV;
- IFIX;
- poupança;
- dólar/real;
- IPCA;
- INPC;
- IGP-M;
- IGP-DI;
- IPC-Fipe;
- INCC.

Inclua também, como séries úteis dentro do escopo autorizado: Selic, IMA-B, IRF-M, S&P 500 e ouro, desde que haja fonte e histórico confiáveis.

#### Regra matemática

Todas as linhas devem ser comparadas como **crescimento de R$ 100**, com base 100 na primeira data comum:

- preços/índices: `100 × valor_atual / valor_inicial`;
- taxas diárias, como CDI: acumular fatores diários;
- inflação mensal: multiplicar `1 + taxa_mensal/100` somente na data em que o índice passou a ser conhecido;
- poupança: acumular a remuneração da data correspondente.

Não coloque taxa anual, variação mensal e nível de índice diretamente no mesmo eixo. O gráfico deve comparar retorno acumulado equivalente. O cálculo usa a série completa; para desenhar, reduza a quantidade de pontos sem alterar extremos e resultado final.

#### Regras de qualidade

- usar a interseção de datas quando a comparação exigir o mesmo início;
- oferecer opção “usar o início disponível de cada série”, claramente marcada;
- informar quando uma série não possui os 20 anos completos;
- mostrar fonte, frequência, data inicial, data final e última atualização;
- não preencher lacunas longas silenciosamente;
- permitir ocultar/mostrar linhas, tooltip, legenda e tabela de retorno final;
- apresentar rentabilidade acumulada, anualizada e volatilidade somente quando matematicamente aplicável.

### 7.5 Agenda econômica e eleitoral

Além das reuniões, divulgações, feriados e eventos atuais, incluir:

- eleições brasileiras: primeiro e eventual segundo turno, obtidos do calendário oficial do TSE;
- eleição federal geral dos Estados Unidos, obtida da FEC;
- tipo, país, data, horário se aplicável, fonte e observação.

Não grave apenas datas fixas no JavaScript. Crie provedor com tabela de eventos e possibilidade de correção administrativa. Eventos já passados devem sair da lista “próximos”, mas permanecer no histórico.

### 7.6 Fontes e frequência

| Dado | Fonte preferencial | Atualização sugerida |
|---|---|---|
| IPCA/INPC | IBGE/SIDRA | após divulgação oficial |
| Focus/Selic projetada | BCB Expectativas/Focus | semanal, com referência |
| DI1/curva | B3 | após ajustes do pregão |
| CDI/IMA/IRF | B3/ANBIMA | diária |
| índices e câmbio | provedor configurado + validação | conforme mercado, em worker |
| eleições BR | TSE | diária quando houver mudança |
| eleições EUA | FEC | diária quando houver mudança |

Cada série precisa de adaptador próprio, validação de unidade e snapshot. Uma fonte indisponível não pode derrubar as demais.

---

## 8. Mercado e Análises

### 8.1 Presets visíveis e não destrutivos

O bloco Análises deve mostrar botões para:

- Padrão;
- CNPI-FDI;
- ALB;
- análises personalizadas do usuário.

Ao clicar em uma análise de sistema:

1. limpar os filtros temporários incompatíveis;
2. carregar todos os valores padrão daquele preset;
3. preencher e identificar visualmente cada campo utilizado;
4. permitir alteração temporária;
5. nunca salvar a alteração sobre o preset do sistema;
6. restaurar o padrão quando o botão for clicado novamente.

Ao clicar em análise personalizada:

- carregar seus valores salvos;
- permitir edição se autorizado;
- exibir **Salvar Alterações da Análise Personalizada**;
- quando não houver personalizada selecionada, exibir **Gravar Análise Personalizada**;
- respeitar o limite de filtros personalizados já concedido ao usuário;
- manter nomes únicos com sufixo numérico quando necessário.

O payload salvo deve possuir `schema_version`, para que presets antigos possam ser migrados quando novos filtros surgirem.

### 8.2 Todos os filtros devem ser identificáveis

Organize em abas ou seções recolhíveis:

1. Universo e classificação;
2. Valuation e preço justo;
3. Qualidade e rentabilidade;
4. Endividamento e crescimento;
5. Dividendos;
6. Indicadores técnicos;
7. Backtests e sinais;
8. Ordenação, limite e colunas.

Mantenha os filtros existentes: tipo de ativo, setor, segmento, tamanho, IBOV, BESST, carteira, preço justo de Graham, preço teto Barsi/Bazin conforme nomenclatura definida no sistema, fundamentos, pivôs, tendências, RSI, volume acima da média, melhores backtests e demais filtros já implementados.

### 8.3 Ajuda sobre médias e cálculos

Todo indicador técnico deve ter `help` acessível sem sair da tela, contendo:

- nome completo;
- fórmula resumida;
- periodicidade;
- janela usada;
- preço usado — fechamento, máxima, mínima ou volume;
- como interpretar;
- limitações;
- data do último cálculo.

Parâmetros existentes que devem ser documentados e testados incluem:

- SMA 20, 50 e 200;
- EMA 9 e demais médias usadas nas estratégias;
- RSI 14;
- Bollinger 20 períodos e 2 desvios;
- MACD 12, 26 e sinal 9;
- ATR 14;
- tendência diária/semanal/mensal;
- pivô PP, S1–S3 e R1–R3 do período anterior concluído;
- volume atual dividido pela média de 9 períodos no diário e mensal.

O help deve refletir o código real. Se uma fórmula mudar, o teste e o texto devem mudar juntos.

### 8.4 Biblioteca de conceitos e metodologia

Crie uma tela **Entenda os Indicadores** dentro de Mercado e Análises, com busca e categorias. Para cada filtro ou nota, explique:

- o que mede;
- fórmula e unidade;
- origem dos dados;
- frequência;
- valores geralmente observados, sem transformar isso em recomendação;
- por que entrou no preset Padrão, CNPI-FDI ou ALB;
- como a nota é atribuída;
- pesos, faixas, normalização e tratamento de dado ausente;
- versão da metodologia e data da mudança.

As notas precisam ser reproduzíveis. Proíba “nota secreta”: o usuário deve conseguir entender quais dados produziram o resultado. Mudanças de pesos devem criar nova versão, sem alterar silenciosamente resultados históricos.

### 8.5 Três melhores estratégias por ativo

Cada ativo deve mostrar as três melhores estratégias de backtest disponíveis e o sinal atual:

- Compra;
- Venda;
- Neutro;
- Sem dados.

Para cada uma, mostre:

- nome da estratégia;
- parâmetros completos;
- período e data do backtest;
- quantidade de operações;
- métricas usadas no ranking;
- data e cotação de referência do sinal;
- motivo resumido do sinal;
- selo de dado antigo quando aplicável.

Não apresente uma estratégia como “melhor” com amostra insuficiente. O ranking deve penalizar poucos negócios, drawdown excessivo e instabilidade. O sinal atual deve usar os mesmos parâmetros do resultado exibido.

### 8.6 Contrato da resposta e estabilidade da tela

- o screener deve responder por páginas;
- a API deve retornar filtros aplicados, ordenação, total e cursor;
- a abertura do detalhe do ativo não pode cancelar a tabela;
- o detalhe deve carregar blocos independentes;
- se backtests não existirem, fundamentos e preço continuam visíveis;
- falha de um provedor não produz a mensagem genérica “painel não disponível” para tudo.

---

## 9. Painel Backtests

### 9.1 Estratégias disponíveis

Preserve todas as estratégias já implementadas e documente seus parâmetros, incluindo cruzamentos de médias, MACD, RSI, Donchian, Bollinger, momentum e configurações personalizadas. A lista da interface deve vir de um catálogo de estratégias do backend, não ser duplicada manualmente no JavaScript.

Cada estratégia deve declarar:

- identificador e versão;
- nome e descrição;
- parâmetros e limites;
- requisitos mínimos de histórico;
- frequência;
- regras de entrada e saída;
- compatibilidade com outras estratégias.

### 9.2 Combinação de estratégias

O usuário autorizado pode selecionar até 1, 2, 3 ou 5 estratégias, conforme a permissão `backtest_strategy_limit`.

Operadores permitidos:

- **Todas (AND):** entrada quando todas concordarem; saída conforme regra conservadora documentada;
- **Qualquer (OR):** entrada quando ao menos uma sinalizar, com saída documentada;
- **Maioria:** disponível com três ou mais estratégias, exigindo a maioria dos sinais.

O operador e a regra de saída fazem parte da configuração persistida e do hash do teste. Não gere automaticamente todas as combinações possíveis. O usuário escolhe a combinação; o backend valida o limite e estima o custo antes de aceitar.

### 9.3 Limites por usuário

Adicionar às permissões:

- `backtest_strategy_limit`: 0, 1, 2, 3 ou 5;
- `backtest_asset_limit`: 0, 1, 3, 5 ou 10;
- `backtest_daily_limit`: 0, 1, 5, 10 ou 20;
- `backtest_cooldown_seconds`: padrão 60;
- permissões separadas para visualizar, executar, comparar, exportar e atualizar sinais, se já não existirem.

Uma solicitação aceita conta como um teste diário, independentemente da quantidade de ativos, mas o custo interno deve ser limitado por `ativos × estratégias × cenários`. Falha de infraestrutura antes de iniciar não consome cota; teste efetivamente iniciado consome. Reexecução administrativa deve ficar auditada.

### 9.4 Intervalo mínimo

Um novo teste só pode começar pelo menos **60 segundos após a conclusão** do teste anterior daquele usuário. Enquanto houver teste queued ou running, não aceite outro. A resposta deve informar o motivo e o horário exato em que poderá tentar novamente.

Use transação e bloqueio no banco para impedir duas abas de contornarem a regra.

### 9.5 Execução assíncrona

1. validar permissão, cota, cooldown, ativos e configuração;
2. procurar resultado idêntico ainda válido pelo hash;
3. criar trabalho e devolver HTTP 202 com `job_id`;
4. apresentar fila e progresso sem bloquear a interface;
5. executar localmente no worker ou despachar ao GitHub conforme o tamanho;
6. receber resultados de forma autenticada e idempotente;
7. persistir resultado parcial por ativo;
8. finalizar como completed, completed_with_errors, failed ou cancelled;
9. permitir repetir apenas ativos com erro.

### 9.6 Resultados e comparação

Mostrar configuração completa, período, benchmark, retorno, retorno anualizado, volatilidade, drawdown, Sharpe quando aplicável, taxa de acerto, payoff, quantidade de negócios, custos considerados e advertências. Permitir comparação lado a lado dentro da cota de visualização; nunca recalcular apenas para abrir um resultado salvo.

### 9.7 Proteção contra viés

Preserve a recusa de fundamentos sem histórico point-in-time suficiente. Dados atuais não podem ser usados como se fossem conhecidos no passado. Toda exceção administrativa deve ser separada, sinalizada e nunca misturada ao ranking oficial.

---

## 10. Minha Carteira

### 10.1 Não misturar produtos privados ao catálogo B3

Fundos bancários, CDB, LCI, LCA e aplicações manuais não devem virar registros comuns na tabela `assets`, pois não têm ticker padronizado nem preço público confiável. Crie uma entidade própria de investimentos personalizados, sempre isolada pelo usuário.

### 10.2 Produtos aceitos

- Fundo de Renda Fixa;
- Fundo Multimercado;
- Fundo de Renda Variável;
- CDB;
- LCI;
- LCA;
- Tesouro Direto;
- Previdência Privada;
- Debênture;
- CRI/CRA;
- Caixa/Conta remunerada;
- Outro.

### 10.3 Campos

- nome do investimento;
- instituição/banco;
- categoria e subcategoria;
- data da aplicação;
- data do vencimento, opcional;
- valor aplicado;
- valor atual;
- moeda, padrão BRL;
- benchmark opcional;
- liquidez opcional;
- observações;
- data da última atualização do valor.

Variação percentual: `(valor_atual - valor_aplicado) / valor_aplicado × 100`, somente quando o valor aplicado for positivo. Mostre também a variação em reais.

### 10.4 Histórico de valores

Ao salvar um novo valor atual, preserve uma linha de avaliação com data. Isso permite evolução futura sem perder o valor anterior. Correções no mesmo dia devem atualizar a avaliação daquele dia ou criar uma revisão auditável, conforme a regra definida.

### 10.5 Gráfico de composição

Exiba gráfico de pizza ou rosca com valor e percentual por grupo:

- Ações;
- FIIs;
- ETFs;
- BDRs;
- Futuros;
- Renda Fixa;
- Fundos;
- Previdência;
- Caixa;
- Outros.

O total combina posições negociadas com o valor atual dos investimentos personalizados. Permita clicar no grupo para ver os itens. Não some contratos futuros pelo valor nominal sem uma metodologia explícita; use valor líquido/alocado configurado.

### 10.6 Experiência e segurança

- edição dentro de formulário e gravação somente no botão Salvar;
- validação de datas, moeda e valores;
- confirmação antes de excluir, preferindo arquivamento recuperável;
- nenhum usuário pode consultar ou alterar investimento de outro;
- respeitar `can_view_portfolio` e `can_write_portfolio`;
- cards de total, valor aplicado, ganho/perda e última atualização;
- notícia e alerta continuam em suas abas já definidas.

---

## 11. Novo painel Minhas Finanças

### 11.1 Objetivo

Criar um controle mensal simples, eficiente e semelhante a uma boa planilha financeira, sem tentar substituir um banco ou sistema contábil.

### 11.2 Permissões

Adicionar:

- `can_view_finances`;
- `can_write_finances`;
- `can_export_finances`, se a exportação básica for incluída no escopo técnico;
- proprietário com todas habilitadas; demais usuários bloqueados por padrão.

### 11.3 Estrutura da tela

1. seletor de mês e ano;
2. cards: receitas, despesas, saldo e taxa de poupança;
3. tabela mensal de lançamentos;
4. orçamento por categoria versus realizado;
5. despesas por categoria;
6. evolução mensal;
7. lançamentos previstos, pagos/recebidos e atrasados;
8. ação para copiar planejamento do mês anterior sem duplicar transações pagas.

### 11.4 Colunas da planilha

| Campo | Regra |
|---|---|
| Data | data do evento financeiro |
| Competência | mês ao qual pertence |
| Tipo | receita ou despesa |
| Categoria | categoria do usuário ou padrão |
| Descrição | texto curto |
| Valor | positivo; o tipo define o sinal |
| Conta | conta/cartão opcional |
| Forma de pagamento | opcional |
| Situação | previsto, pago, recebido ou atrasado |
| Recorrência | nenhuma, mensal ou regra definida |
| Observações | opcional |

### 11.5 Categorias iniciais

Receitas: salário, pró-labore, bônus, renda extra, aluguel, dividendos/proventos, juros, reembolso e outras.

Despesas: moradia, alimentação, transporte, saúde, educação, lazer, assinaturas, impostos, seguros, dependentes, doações, dívidas, investimentos/aportes e outras.

Categorias do sistema podem ser ocultadas; categorias pessoais podem ser criadas e renomeadas. Transferências entre contas e aportes não devem ser confundidos automaticamente com consumo.

### 11.6 Regras financeiras

- saldo = receitas recebidas − despesas pagas;
- saldo previsto = receitas previstas − despesas previstas;
- taxa de poupança = aportes ou saldo positivo / receitas, conforme metodologia escolhida e explicada;
- edição em lote só é enviada ao confirmar;
- recorrências geram ocorrências futuras idempotentes;
- valores financeiros usam Decimal no backend, nunca float;
- datas e competência são armazenadas separadamente;
- exclusão é auditável ou recuperável;
- nenhum dado financeiro pessoal entra em log, analytics público ou cache compartilhado.

### 11.7 Escopo negativo

Na V1.20 não conectar automaticamente contas bancárias, não pedir senha bancária, não iniciar pagamento e não compartilhar dados entre usuários.

---

## 12. UX comum a todos os painéis

- menu lateral fixo, recolhível a ícones, sem borda vazia entre menu e conteúdo;
- cabeçalho compacto com busca global, alertas e perfil;
- busca por ticker direciona para Ações, FIIs, ETFs, BDRs, Futuros ou painel correspondente;
- cards de resumo no topo e detalhes abaixo;
- filtros avançados recolhidos, mas fáceis de abrir;
- abas reais em vez de checkboxes para navegação;
- estado da URL ou history para permitir voltar sem perder filtros;
- painel lateral ou modal de ativo suficientemente largo e rolável;
- tabelas com seletor de colunas, cabeçalho fixo e paginação;
- mensagens de erro específicas, com “tentar novamente” apenas no bloco afetado;
- data, fonte e estado de atualização sempre visíveis;
- contraste, foco de teclado, labels e navegação acessíveis;
- layout responsivo sem esconder dados essenciais;
- textos educacionais claros e aviso de que não constitui recomendação.

---

## 13. Modelo de dados e migrações

### 13.1 Tabelas novas ou ampliadas

#### `background_jobs`

Fila persistente descrita na seção 5.2, com índices por estado e agendamento.

#### `economic_series`

Catálogo da série: código, nome, unidade, frequência, fonte, URL oficial, timezone, método de acumulação, data inicial, ativo.

#### `economic_series_points`

`series_id`, `observed_at`, `value`, `reference_period`, `published_at`, `source_payload_hash`, `quality_status`; chave única por série/data/período.

#### `yield_curve_snapshots` e `yield_curve_points`

Data de referência, fonte, método; pontos com contrato, vencimento, taxa, tipo observado/interpolado e prazo em dias úteis.

#### `economic_events`

País, categoria, título, início, timezone, fonte, URL, importância, observação, estado e chave externa.

#### `custom_investments`

`id`, `owner_email`, `portfolio_id`, categoria, subcategoria, nome, instituição, datas, valores Decimal, moeda, benchmark, liquidez, notas, timestamps e arquivamento.

#### `custom_investment_valuations`

Investimento, data da avaliação, valor, origem manual/automática e timestamps.

#### `finance_categories`

Usuário, tipo, nome, categoria-pai, cor, ordem, padrão/pessoal e ativo.

#### `finance_entries`

Usuário, data, competência, tipo, categoria, descrição, valor Decimal, conta, forma, situação, recorrência, notas e auditoria.

#### `finance_recurring_rules`

Usuário, frequência, início, fim, dia, valor, categoria, próximo processamento, ativo e chave idempotente.

#### `finance_monthly_budgets`

Usuário, competência, categoria e valor planejado.

#### Controle de backtest

Adicionar `backtest_strategy_limit`, `backtest_cooldown_seconds`, configuração combinada versionada, operador, hash e registros de uso diário.

### 13.2 Índices mínimos

```text
economic_series_points(series_id, observed_at DESC)
yield_curve_snapshots(reference_date DESC)
yield_curve_points(snapshot_id, maturity_date)
economic_events(starts_at, country, category)
background_jobs(status, run_after, priority, created_at)
background_jobs(deduplication_key) WHERE status IN ('queued','running')
custom_investments(owner_email, portfolio_id, category, maturity_date)
custom_investment_valuations(investment_id, valuation_date DESC)
finance_entries(owner_email, competence_month, occurred_on, id)
finance_entries(owner_email, category_id, competence_month)
finance_monthly_budgets(owner_email, competence_month, category_id)
backtest_usage(owner_email, market_date)
```

Confirme nomes e seletividade com o esquema real. Não crie índices redundantes ou gigantes sem medir.

### 13.3 Regras de migração

- uma migração Alembic por entrega coerente;
- `upgrade` e `downgrade` testados quando reversão for segura;
- valores padrão conservadores: novas permissões desabilitadas para usuários comuns;
- backfill em lotes pelo worker, não em transação longa de implantação;
- novas colunas primeiro opcionais; preencher; depois impor restrição quando necessário;
- backup antes de qualquer migração em produção;
- não alterar migrações já publicadas.

---

## 14. Contratos de API sugeridos

Use versionamento compatível e adapte nomes ao padrão atual.

### Mercado

```text
GET  /market/dashboard
GET  /market/fx
GET  /market/yield-curve?reference=&compare=
GET  /market/comparison/catalog
POST /market/comparison/query
GET  /market/calendar
POST /admin/market/refresh
```

`POST /market/comparison/query` recebe séries e período, limita quantidade, devolve metadados e série normalizada. Cache por hash dos parâmetros.

### Análises

```text
GET  /screening/presets
POST /screening/run
GET  /screening/indicators/catalog
POST /saved-filters
PATCH /saved-filters/{id}
GET  /assets/{ticker}/backtest-leaders
```

O catálogo de indicadores alimenta interface e documentação, evitando divergência.

### Backtests

```text
GET  /backtests/strategies/catalog
POST /backtests/jobs
GET  /backtests/jobs/{id}
POST /backtests/jobs/{id}/cancel
POST /backtests/jobs/{id}/retry-failed-assets
GET  /backtests/usage/me
```

### Carteira personalizada

```text
GET    /portfolio/custom-investments
POST   /portfolio/custom-investments
PATCH  /portfolio/custom-investments/{id}
DELETE /portfolio/custom-investments/{id}
POST   /portfolio/custom-investments/{id}/valuations
GET    /portfolio/allocation
```

### Finanças

```text
GET   /finances/months/{yyyy-mm}
POST  /finances/entries
PATCH /finances/entries/{id}
DELETE /finances/entries/{id}
GET   /finances/categories
POST  /finances/categories
GET   /finances/budgets/{yyyy-mm}
PUT   /finances/budgets/{yyyy-mm}
POST  /finances/recurring-rules
```

Todas as rotas pessoais resolvem o proprietário pelo usuário autenticado. Nunca aceite `owner_email` arbitrário do corpo da requisição.

---

## 15. Segurança, privacidade e permissões

- validar autenticação e permissão no backend, não apenas ocultar botão;
- acesso negado por padrão para novas funções;
- usuário master continua identificado por configuração segura e política no banco;
- limites de backtest são validados em transação;
- proteção CSRF onde houver sessão e mutação;
- cookies Secure, HttpOnly e SameSite apropriado;
- Content Security Policy e headers atuais preservados;
- valores Decimal e validação de moeda;
- auditoria de alterações administrativas, alertas, permissões e promoção;
- mascarar dados em logs e telas de administração;
- rotação de segredos sem reinserção no repositório;
- análise de dependências e atualização controlada, sem atualizar tudo automaticamente em produção.

---

## 16. Testes obrigatórios

### 16.1 Correção do conjunto de testes

Alinhar `pyproject.toml` aos diretórios reais ou consolidar testes cuidadosamente. Não excluir testes antigos. O pipeline deve descobrir e executar toda a suíte vigente.

### 16.2 Testes unitários

- normalização base 100 e acumulação de taxas;
- inflação mensal sem look-ahead;
- pares cambiais e inversões;
- curva DI1, vencimentos e interpolação;
- presets e restauração de valores;
- fórmulas e help dos indicadores consistentes;
- ranking e sinal dos três backtests;
- limites 1/2/3/5 estratégias, 1/3/5/10 ativos e 1/5/10/20 por dia;
- cooldown de 60 segundos com concorrência;
- variação de investimentos personalizados;
- consolidação da carteira;
- receitas, despesas, recorrências, competência e orçamento;
- isolamento por usuário.

### 16.3 Integração

- migração em banco vazio e cópia da produção;
- worker pegando trabalho com idempotência;
- fonte externa falha e snapshot anterior continua servido;
- GitHub entrega backtest autenticado sem duplicar resultado;
- staging usa banco separado;
- produção não muda quando staging muda;
- backup e restauração.

### 16.4 Interface e ponta a ponta

- login, menu, busca e retorno do navegador;
- filtros e presets em Ações, FIIs, ETFs e BDRs;
- salvamento de personalizada conforme autorização;
- curva, comparador e agenda;
- execução/progresso de backtest;
- cadastro, edição e arquivamento de investimento;
- planilha mensal e troca de competência;
- teclado, foco, contraste e telas menores;
- falha de um bloco sem congelar os demais.

### 16.5 Carga e recuperação

- 10 a 20 sessões de leitura leve em homologação, respeitando os limites da VM;
- lista com 100 ativos;
- comparação de 20 anos com várias séries;
- fila com tarefas duplicadas;
- reinício do worker durante trabalho;
- indisponibilidade temporária do banco;
- reinício das duas VMs;
- medição de memória e swap.

---

## 17. Critérios de aceite por módulo

### Infraestrutura

- [ ] Segunda instância confirmada como gratuita antes da criação.
- [ ] Somente a instância web expõe 80/443.
- [ ] PostgreSQL usa rede privada.
- [ ] Backup restaurado e contagens conferidas.
- [ ] Homologação liga/desliga sem afetar produção.
- [ ] Retorno testado.

### Desempenho

- [ ] Nenhuma rota de leitura chama fonte externa.
- [ ] Dados antigos válidos aparecem durante atualização.
- [ ] Metas p95 registradas.
- [ ] Interface permanece navegável durante notícias, catálogo e backtest.
- [ ] Reinício automático validado.

### Painel de Mercado

- [ ] IPCA 12 meses substitui S&P 500 no início.
- [ ] Cinco pares cambiais corretos e identificados.
- [ ] Curva DI x Pré com fonte, data e comparação.
- [ ] Comparador base 100 e períodos solicitados.
- [ ] Séries sem histórico completo são sinalizadas.
- [ ] Eleições do Brasil e EUA aparecem por fonte oficial.

### Mercado e Análises

- [ ] Presets mostram todos os valores.
- [ ] Mudança temporária não altera preset do sistema.
- [ ] Personalizada salva apenas com permissão.
- [ ] Help corresponde às fórmulas.
- [ ] Metodologia das notas é reproduzível.
- [ ] Top 3 backtests e sinais aparecem ou informam “Sem dados”.

### Backtests

- [ ] Limites por usuário aplicados no backend.
- [ ] Combinações e operador persistidos.
- [ ] Cota e cooldown resistentes a duas abas simultâneas.
- [ ] Trabalho assíncrono não bloqueia a tela.
- [ ] Resultado idêntico salvo não é recalculado sem necessidade.

### Carteira

- [ ] Produtos personalizados não contaminam catálogo B3.
- [ ] Valores e variação corretos.
- [ ] Composição combina posições e personalizados.
- [ ] Isolamento por usuário testado.

### Minhas Finanças

- [ ] Receitas, despesas, categorias e competência funcionam.
- [ ] Totais e orçamento estão corretos.
- [ ] Recorrências não duplicam.
- [ ] Dados de outro usuário nunca aparecem.
- [ ] Nenhuma senha bancária é solicitada.

---

## 18. Publicação, homologação e retorno

1. Desenvolver em cópia/branch identificada.
2. Rodar testes e análise estática.
3. Gerar changelog e migrações.
4. Publicar no GitHub.
5. Atualizar somente homologação.
6. Criar banco de homologação separado ou snapshot seguro.
7. Validar critérios com o proprietário em `/testefdi/`.
8. Criar backup de produção e enviar ao Object Storage.
9. Promover com script manual.
10. Observar saúde, logs, memória e erros por pelo menos 30 minutos.
11. Se houver regressão, voltar imagem e banco conforme o runbook.

Uma publicação nunca deve apagar arquivos locais protegidos, segredos ou volumes. Corrija a automação para distinguir mudança de conteúdo e mudança apenas de permissão executável, sem ignorar alteração real.

---

## 19. Entregáveis do programador

Para cada subversão:

- código completo;
- migrações Alembic;
- testes novos e regressão antiga;
- documentação de API e fontes;
- instruções Windows, Oracle e GitHub em blocos separados;
- arquivo de exemplo de segredos sem valores reais;
- medição de desempenho;
- capturas ou roteiro visual de homologação;
- changelog;
- plano de retorno;
- lista do que ficou pendente.

Ao final da V1.20, atualizar o guia geral arquivo por arquivo. O próximo responsável não deve depender desta conversa para operar o sistema.

---

## 20. Sugestões que dependem de nova aprovação

As sugestões abaixo **não fazem parte do escopo autorizado** e não podem ser implementadas até o proprietário aprovar uma ou mais pelo número.

1. **Importação CSV/OFX e exportação Excel nas Finanças.** Reduz digitação, mas exige mapeamento, deduplicação e cuidados com arquivos bancários.
2. **Metas financeiras e reserva de emergência.** Planejamento de objetivos, prazo e progresso mensal.
3. **Calendário de proventos e rebalanceamento da carteira.** Já foi sugerido anteriormente; exige fonte de eventos e regras claras para não parecer recomendação.
4. **CNY/BRL como sexto par cambial.** Relevante para o comércio brasileiro, embora o pedido atual limite os adicionais às duas moedas globais mais negociadas.
5. **Painel de qualidade dos dados para usuários.** Mostra fontes, atrasos e estado de cada série; melhora transparência, mas amplia a interface.
6. **Aplicação instalável no celular (PWA).** Melhora acesso e notificações, porém exige projeto próprio de cache e segurança.
7. **Armazenar históricos grandes e artefatos de backtest no Object Storage.** Pode reduzir o banco, mas altera recuperação e consulta.
8. **Página pública de contingência com último snapshot de mercado.** Mantém informação básica se o banco de dados ficar fora do ar, sem expor carteira ou finanças.

---

## 21. Fontes oficiais para a implementação

Use fontes primárias e registre a URL, licença/termos, frequência e adaptador.

- Oracle Always Free: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- Oracle Ampere A1: https://docs.oracle.com/en-us/iaas/Content/Compute/References/arm.htm
- B3 — Futuro DI1: https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/juros/futuro-de-taxa-media-de-depositos-interfinanceiros-de-um-dia.htm
- B3 — Manual de Curvas V16: https://www.b3.com.br/data/files/46/82/9A/9B/78C3491029BEEC39AC094EA8/Manual%20de%20Curvas_V16_20250106.pdf
- Banco Central — Relatório Focus: https://bcb.gov.br/controleinflacao/relatoriofocus
- Banco Central — Expectativas de Mercado: https://dadosabertos.bcb.gov.br/dataset/expectativas-mercado
- IBGE/SIDRA: https://sidra.ibge.gov.br/
- ANBIMA — IMA: https://www.anbima.com.br/informacoes/ima/ima.asp
- B3 — IFIX histórico: https://b3.com.br/pt_br/market-data-e-indices/indices/indices-de-segmentos-e-setoriais/indice-fundos-de-investimentos-imobiliarios-ifix-estatisticas-historicas.htm
- BIS — pesquisa cambial 2025: https://www.bis.org/statistics/rpfx25.htm
- TSE — calendário eleitoral: https://www.tse.jus.br/eleicoes/calendario-eleitoral
- FEC — eleições federais: https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/

Se uma fonte exigir licença, chave paga ou proibir redistribuição, não contorne a restrição. Informe a limitação e proponha uma alternativa legal antes de programar.

---

## 22. Decisão final recomendada

A melhor V1.20 não é uma tela maior sobre a mesma máquina sobrecarregada. A sequência recomendada é:

1. criar fila, snapshots, métricas e testes;
2. separar a segunda instância quando a Oracle confirmar gratuidade e capacidade;
3. mover coleta, alertas, banco e homologação para a camada de dados;
4. entregar Painel de Mercado e Análises sobre leituras pré-calculadas;
5. controlar backtests por configuração, cota e fila;
6. acrescentar carteira personalizada;
7. acrescentar Minhas Finanças;
8. testar, homologar e promover em pequenas versões.

Esse caminho preserva o que já foi construído, melhora a experiência antes de adicionar volume e evita que uma única consulta lenta derrube o site inteiro.

