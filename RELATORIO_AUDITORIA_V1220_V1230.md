# Auditoria de continuidade — V1.22.0 a V1.23.0

## Regra de leitura

Este relatório distingue três estados:

- **implementado**: código, migração, teste ou roteiro existe no pacote;
- **ativado**: depende de execução e evidência no ambiente Oracle do usuário;
- **condicionado à fonte**: depende de credencial ou resposta oficial externa.

Essa distinção impede que preparação de infraestrutura seja confundida com implantação real.

## Prioridade V1.22 — estabilidade e velocidade

| Requisito | Estado no pacote | O que ainda exige operação |
| --- | --- | --- |
| Segunda VM gratuita somente para worker | Implementado | Criar VM2, rede e chave na OCI; preparar e cortar o worker |
| PostgreSQL único na VM1, porta 5432 privada | Implementado | Aplicar override, bind no IP privado e NSG VM2 -> VM1; comprovar que não há bind amplo |
| Um scheduler e um monitor de alertas | Implementado | Validar leases e heartbeat depois do corte real |
| p50/p95 de health, dashboard, screener 50/100 e ativo | Implementado | Gerar tráfego representativo e conferir percentis no painel |
| Alertas de fila, falhas, snapshot, memória, swap e disco | Implementado | Instalar/ativar watchdog e confirmar e-mail real |
| Avaliar staging na VM2 após uma semana | Deliberadamente pendente | Somente após uma semana estável do worker remoto; não mover junto no primeiro corte |
| Teste documentado de retorno do worker | Implementado | Executar failback real e novo cutover na infraestrutura criada |

### Conclusão sobre V1.22

A base de software está preservada e foi ampliada na V1.23.0. A existência dos scripts não comprova que a segunda instância esteja ativa. Enquanto faltarem as evidências de VM2, NSG, bind privado, cutover e failback, o estado operacional correto é **worker local**.

Não se recomenda um segundo PostgreSQL gravável. A aplicação deve continuar com uma única fonte de verdade.

## Prioridade V1.23 — eventos oficiais do investidor

| Requisito | Implementação | Limite ou dependência real |
| --- | --- | --- |
| Calendário oficial de proventos | Eventos B3 ligados às posições das carteiras, lotes rotativos e API autenticada | Quantidade atual gera apenas estimativa; confirmação final é da corretora/informe oficial |
| Feed de fatos relevantes | Metadados e links do IPE/CVM, importação anual incremental | A CVM pode atrasar ou indisponibilizar o arquivo; o painel deve mostrar isso |
| Histórico integral IMA-B/IRF-M | Importador incremental do ANBIMA Feed desde data configurável | Condicionado a `ANBIMA_CLIENT_ID` e `ANBIMA_CLIENT_SECRET`; sem credencial fica indisponível |
| Agenda renovável | Geração anual de eleições e feriados, ingestão de agendas oficiais disponíveis | Alterações extraordinárias de calendário dependem da atualização da fonte oficial |
| Painel de qualidade | Cobertura, atraso, fonte, última falha e estado das rotinas | Diagnóstico usa metadados persistidos e não bloqueia a navegação com consultas externas |
| Monitor ALB 5–20 | Observação diária e incidente fora da faixa | Não afrouxa critérios automaticamente |

## Administração da página pública

| Requisito | Estado |
| --- | --- |
| Acesso exclusivo do proprietário/delegado | `can_manage_portal`, concedida ao proprietário e delegável por nível |
| Alterar textos atuais da página | Implementado por campos estruturados e validados, incluindo marca, monograma, navegação e acessibilidade |
| Gerenciar livros | Incluir, editar, ocultar, excluir e reordenar |
| Alterar capas | PNG, JPEG ou WebP, máximo 4 MB, validação real do arquivo |
| Até três links de venda | Implementado com descrição e URL HTTPS |
| Evitar sobrescrita concorrente | Revisão e resposta de conflito |
| Reserva em falha de banco | Conteúdo estático atual permanece utilizável |

As únicas imagens de conteúdo presentes hoje são as capas. O editor cobre todas elas. Uma futura imagem editorial fora dos livros — por exemplo, banner, fotografia de autor ou fundo — deverá receber um campo de mídia específico antes de ser adicionada; isso evita uploads sem destino ou HTML arbitrário.

## Autenticação

| Controle | Estado |
| --- | --- |
| Google continua disponível | Preservado |
| Código aleatório por e-mail | Seis dígitos |
| Validade | 10 minutos |
| Novo envio | No máximo um por minuto por e-mail |
| Substituição | Novo código invalida o anterior |
| Uso único | Implementado |
| Armazenamento | Hash HMAC com sal, sem texto aberto |
| Tentativas | Limitadas |
| Permissões | Mesma política de acesso do e-mail autenticado |
| Dependência | SMTP real configurado e entregável |

## Riscos controlados

- **Fonte indisponível:** mantém último dado com metadados ou informa indisponibilidade; não inventa valor.
- **Arquivo CVM grande:** leitura em fluxo reduz uso de memória.
- **Carteira grande:** lotes rotativos evitam corte silencioso e excesso de uma só execução.
- **Edição concorrente:** revisão impede sobrescrita invisível.
- **Upload malicioso:** tamanho, MIME, assinatura e extensões aceitas são validados.
- **Abuso básico de código:** limitação por e-mail, por cliente e global, expiração, substituição, uso único, tentativas máximas e serialização de pedidos simultâneos para o mesmo endereço.
- **Worker duplicado:** leases distribuídas permanecem a autoridade de liderança.

## Pendências operacionais antes de declarar tudo ativo

1. Publicar e homologar a V1.23.0 em staging.
2. Confirmar entrega real do código por SMTP.
3. Configurar credenciais ANBIMA, caso o serviço esteja contratado, e acompanhar os lotes até completar o histórico.
4. Executar manualmente as seis novas rotinas e revisar o painel de qualidade.
5. Criar a VM2 e os NSGs somente quando houver acesso à OCI e janela de mudança.
6. Validar bind privado da porta 5432, cutover, duas leases únicas e failback.
7. Esperar uma semana estável antes de decidir sobre staging na VM2.

## Próximos passos recomendados, sem inclusão automática

1. acompanhar o volume da tabela de códigos de login e ajustar a janela de retenção apenas se o crescimento real justificar;
2. acompanhar os bloqueios do limitador por cliente e global antes de considerar controles adicionais no proxy;
3. acompanhar cobertura de ISIN/ticker nos proventos e documentos CVM;
4. adicionar campos de mídia genéricos somente quando a página ganhar imagens que não sejam capas;
5. criar alarmes externos da OCI para indisponibilidade total, pois um watchdog dentro da VM não observa a própria queda;
6. registrar, em cada promoção, p50/p95 antes e depois para verificar ganho real de desempenho.

Nenhum desses próximos passos autoriza uma promoção automática nem mudança de infraestrutura sem aprovação.
