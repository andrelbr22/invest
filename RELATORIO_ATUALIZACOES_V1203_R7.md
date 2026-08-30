# Relatório das rotinas de atualização — V1.20.3 R7

## 1. Objetivo e estado desta revisão

Este relatório descreve como cada informação do Formação do Investidor é atualizada após a R7, onde fica armazenada, o que o usuário vê e como o sistema reage a falhas.

A R7 foi preparada e testada localmente. Ela não foi enviada ao GitHub, ao ambiente de teste ou à produção. A publicação continua condicionada à aprovação expressa do responsável pelo projeto.

Não há alteração destrutiva de banco nesta revisão. São reutilizadas as tabelas persistentes já criadas na V1.20 para fila, snapshots e séries econômicas.

## 2. Fluxo comum das atualizações

1. O agendador verifica a cada minuto quais fontes atingiram seu horário.
2. Em vez de consultar a fonte dentro da página, ele registra um trabalho na tabela `background_jobs`.
3. Um único worker retira os trabalhos da fila, por prioridade e horário.
4. O worker consulta a fonte, valida o resultado e grava o snapshot compartilhado no PostgreSQL.
5. O site lê o último snapshot válido imediatamente; o usuário não espera a consulta externa.
6. Se uma fonte falhar, o último dado válido permanece visível. A tela informa falha ou atualização parcial.
7. Trabalhos repetidos são bloqueados por idempotência e deduplicação.
8. Uma falha recebe até três tentativas, com espera progressiva. Um heartbeat protege tarefas longas e recupera trabalhos abandonados.

Todos os horários deste relatório usam `America/Sao_Paulo`, inclusive quando o servidor opera em UTC.

## 3. Painel de Mercado

| Grupo | Informações | Fonte principal | Automático | Atualização por acesso | Manual |
| --- | --- | --- | --- | --- | --- |
| Selic atual | Meta Selic vigente | BCB, SGS 432 | 06h e 13h | se tiver mais de 3 horas | intervalo mínimo de 5 minutos |
| Focus | Selic projetada para o fim do ano atual e seguinte | Relatório Focus/BCB | 04h | se tiver mais de 12 horas | intervalo mínimo de 5 minutos |
| Macro Brasil/EUA | CDI, IPCA, INPC, IGP-M, IGP-DI, INCC, IPC-Fipe, CPI, IMA-B e IRF-M | BCB, IBGE, FGV, Fipe, BLS e ANBIMA | 04h | se tiver mais de 12 horas | intervalo mínimo de 5 minutos |
| Mercados globais | Bolsas, VIX, DXY, ouro, prata e petróleo | Yahoo Finance | 06h e 13h | se tiver mais de 6 horas | intervalo mínimo de 5 minutos |
| Juros e agenda | Treasuries, curva DI e calendário | U.S. Treasury, FRED, B3, ANBIMA, BCB e BLS | 06h e 13h | se tiver mais de 6 horas | intervalo mínimo de 5 minutos |
| Criptoativos | Bitcoin e Ethereum em dólar e real, com variações | Yahoo Finance | a cada 30 minutos, de 00h05 a 23h35 | se tiver mais de 30 minutos | intervalo mínimo de 5 minutos |
| Câmbio | Pares exibidos no painel | Yahoo Finance | a cada 2 horas, de 00h05 a 22h05 | se tiver mais de 2 horas | intervalo mínimo de 5 minutos |
| Manchetes | Cinco manchetes de economia | Agência Brasil e ADVFN | a cada hora | se tiver mais de 1 hora | intervalo mínimo de 5 minutos |
| Comparador histórico | Todas as séries e índices do comparador | BCB e Yahoo Finance | 05h | se tiver mais de 24 horas | intervalo mínimo de 5 minutos |

O painel agregado não possui uma consulta redundante própria. Ele é montado com os snapshots independentes acima. Isso substitui com vantagem uma rodada geral às 03h, 09h, 12h, 15h e 20h: cada fonte passa a ser consultada na frequência adequada e a falha de uma delas não invalida as demais.

### Falha parcial

Os grupos com mais de uma fonte são atualizados por campo. Exemplo: se a curva DI falhar e Treasuries e agenda responderem, o sistema:

- grava as novas Treasuries e a nova agenda;
- mantém a última curva DI válida;
- marca o grupo como `Atualização parcial`;
- informa nos detalhes quantos itens foram preservados;
- continua permitindo o uso de todas as outras páginas.

## 4. Catálogo, fundamentos, notas e indicadores técnicos

| Rotina | Escopo | Automático | Acesso | Armazenamento |
| --- | --- | --- | --- | --- |
| Catálogo | limpeza de ativos incompatíveis e catálogo de ETFs, BDRs e futuros | 08h30 em dias úteis | pode solicitar se o snapshot tiver mais de 6 horas | tabelas de ativos + snapshot de controle |
| Fundamentos e notas | ações, FIIs, fundamentos, notas e classificações | 19h em dias úteis | pode solicitar se tiver mais de 6 horas | ativos, fundamentos, scores + snapshot |
| Técnica diária | indicadores técnicos de ações e FIIs | 18h15 em dias úteis | pode solicitar se tiver mais de 6 horas | snapshots técnicos + snapshot de controle |
| Técnica intradiária relevante | somente ativos em carteiras ou alertas, até 100 códigos por rodada | a cada 15 minutos, das 10h05 às 17h50, mais fechamento às 18h, em dias úteis | pode solicitar se tiver mais de 6 horas | snapshot compartilhado das cotações |

A rotina intradiária não refaz catálogo nem fundamentos a cada 15 minutos. Essa separação reduz tráfego, memória, gravações e risco de bloqueio. Ativos fracionários terminados em `F` e instrumentos não suportados continuam excluídos pelas regras existentes.

Uma reinicialização noturna ou no fim de semana não tenta recuperar rodadas intradiárias antigas. Somente horários úteis presentes são executados.

## 5. Carteiras

### Cotações

- Ativos B3 relevantes recebem cotação intradiária a cada 15 minutos durante o pregão.
- A tela da carteira usa essa cotação quando ela é mais apropriada e identifica fonte e horário em cada posição.
- O quadro superior mostra situação, fonte, última atualização e próxima rodada.
- O botão manual cria um trabalho persistente que atualiza histórico diário e indicadores internos.
- Duas solicitações manuais em menos de cinco minutos não geram trabalho duplicado.
- Renda fixa personalizada continua usando o valor informado pelo usuário.
- Criptomoedas personalizadas da carteira continuam fora do comando específico de preços da carteira; as criptos do Painel de Mercado seguem a rotina própria de 30 minutos.

### Notícias da carteira e recomendações

- O primeiro acesso do usuário em cada dia cria a atualização automática.
- O resultado fica no PostgreSQL e permanece visível enquanto uma nova coleta ocorre.
- O navegador pode ser fechado sem cancelar o trabalho.
- A coleta agora é executada pelo worker, não pelo processo web.
- A atualização manual respeita cinco minutos de intervalo.
- Falha não apaga a última notícia válida.

## 6. Alertas de preço

O monitor de alertas foi retirado do processo web e passou para o worker de produção.

### Ativos B3

- verificação a cada 5 minutos;
- dias úteis, das 10h às 18h de Brasília;
- candles de 1 minuto;
- máxima e mínima para cruzamento de preço;
- variação calculada contra o fechamento anterior.

### Índices, moedas, criptos e commodities

- verificação a cada 10 minutos, continuamente;
- candles de 5 minutos;
- fonte indicativa Yahoo Finance.

Quando uma condição é atingida, o alerta é desativado, movido ao histórico e enviado ao e-mail principal e ao secundário, quando cadastrado. Falhas de e-mail mantêm as tentativas já existentes. O ambiente de teste não executa o monitor para não duplicar alertas reais.

## 7. Backtests

### Pessoais

Continuam sob demanda, com limites por usuário, quantidade de ativos, estratégias combinadas, uso diário e intervalo mínimo já definidos. Os resultados são gravados no histórico e a tela informa a data do resultado mais recente.

### Oficiais

Continuam agendados pelo GitHub aos sábados, 00h01 de Brasília. A entrega autenticada em partes, idempotência, repetição somente dos ativos pendentes, progresso e recuperação do erro HTTP 413 permanecem inalterados. O painel usa os horários de criação, progresso e conclusão registrados no PostgreSQL.

## 8. Dados cadastrados pelo usuário

Carteiras, posições, preferências, alertas, permissões e demais dados pessoais continuam no PostgreSQL. Eles não dependem das rotinas de mercado para serem salvos e não são substituídos por snapshots externos.

## 9. Atualização do código, staging e produção

1. O pacote é validado no Windows sem envio.
2. Depois da autorização, o script publica o código no GitHub.
3. A Oracle atualiza somente o ambiente `/testefdi` e cria uma cópia isolada do banco de produção.
4. O staging executa migrações, testes e homologação sem monitorar alertas reais.
5. A produção só muda por aprovação manual expressa.
6. Antes da promoção, o banco é copiado localmente e enviado ao Object Storage.
7. A promoção inicia primeiro a aplicação e aguarda sua saúde.
8. Depois inicia o worker e também aguarda sua saúde.
9. Se qualquer um falhar, aplicação e worker voltam juntos para a imagem anterior.

## 10. Uso de recursos na instância atual

- worker com concorrência unitária: uma carga pesada por vez;
- pool do worker limitado a uma conexão, sem conexões excedentes;
- limite de memória do worker: 260 MB;
- aplicação web sem monitor de alertas e sem agendador externo;
- staging com worker interno somente para homologação, evitando mais um contêiner permanente;
- snapshots evitam repetir consultas a cada usuário ou clique.

### Segunda instância gratuita

A divisão já foi preparada no código: o worker não depende do navegador e pode ser movido para outra instância. A mudança física não deve ser feita ainda porque exige:

1. confirmação de disponibilidade de uma segunda VM gratuita na tenancy;
2. rede privada entre as VMs;
3. PostgreSQL acessível somente pela rede privada, com credencial dedicada;
4. firewall sem exposição pública da porta 5432;
5. implantação da mesma imagem e dos mesmos secrets no worker remoto;
6. desligamento do worker local somente após o remoto ficar saudável.

Até isso ocorrer, a configuração de uma única instância é a opção segura. O worker poderá ser transferido depois sem mudar API, telas, fila ou dados.

## 11. Informações de atualização visíveis ao usuário

Os painéis correspondentes passam a apresentar, conforme aplicável:

- última atualização obtida;
- fonte da informação;
- estado: atualizado, desatualizado, na fila, atualizando, parcial, falhou ou aguardando;
- próxima rodada prevista;
- quantidade de itens preservados quando uma fonte falhar;
- botão manual com proteção de cinco minutos.

Carteiras identificam também a fonte e o horário por posição. Notícias informam a conclusão da coleta. Alertas mostram a última verificação. Backtests mostram criação, progresso e conclusão.

## 12. Validação realizada antes do pacote

- compilação de todos os módulos Python: aprovada;
- validação sintática do JavaScript: aprovada;
- suíte integral: 59 testes aprovados;
- cobertura funcional adicionada para horários, janela intradiária, ausência de recuperação fora do pregão, cooldown, persistência parcial, fila de notícias, worker separado e metadados da interface;
- nenhum segredo, banco local ou credencial incluído;
- nenhuma publicação ou promoção realizada.

O único aviso dos testes é uma depreciação futura entre bibliotecas de teste (`Starlette/httpx`), sem impacto no site, no banco ou nas rotinas em produção.
