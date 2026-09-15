# Relatório de validação — V1.23.0

## Objetivo

Validar que os novos eventos oficiais, a administração da página inicial e o login por e-mail foram adicionados sem retirar recursos já homologados e sem criar dados financeiros artificiais.

## Cobertura automatizada específica

Os testes de `tests_v1230` cobrem:

### Autenticação por e-mail

- formato numérico de seis dígitos;
- armazenamento por hash com sal, sem código em texto aberto;
- serialização transacional de pedidos simultâneos para o mesmo e-mail;
- validade de 10 minutos;
- limite de um novo envio por minuto;
- substituição do código anterior;
- rejeição após uso;
- rejeição após expiração;
- rejeição de endereço inválido;
- criação de sessão HTTPS com `auth_method=email_code`.
- persistência do código e da espera antes do envio SMTP, inclusive quando o
  provedor falha;
- limpeza segura de desafios expirados antigos;
- proteção de rajada por cliente e global, sem persistir IP bruto.

### Portal administrável

- carga pública inicial com os sete livros atuais;
- persistência dos dados padrão no primeiro acesso;
- edição de textos com controle de revisão;
- edição do monograma, marca, navegação e texto do atalho de acessibilidade;
- conflito em edição desatualizada;
- criação e publicação de livros;
- upload e entrega de capa publicada com cache imutável;
- bloqueio público de capas ainda em rascunho ou usadas somente em livros ocultos;
- até três links de venda;
- rejeição do quarto link;
- rejeição de URL sem HTTPS;
- presença dos controles administrativos e da hidratação pública.

### Fontes oficiais

- leitura incremental do ZIP anual da CVM sem materializar o arquivo inteiro em memória;
- lote B3 sem limite silencioso em 100 ativos;
- indicação explícita quando um limite de segurança é aplicado;
- autenticação e normalização do ANBIMA Feed;
- seleção exclusiva de IMA-B e IRF-M;
- persistência incremental das séries oficiais;
- estado `unavailable` quando faltam credenciais, sem chamada de rede e sem valor alternativo;
- presença da rotina assíncrona do histórico ANBIMA.

## Validações estruturais

- versão da aplicação: `1.23.0`;
- head Alembic: `0026_v1_23_email_login`;
- workflow compila e executa `tests_v1230` junto à regressão;
- páginas administrativas usam `can_manage_portal` ou `can_sync_market`;
- proprietário recebe a permissão de portal e pode delegá-la por nível;
- configuração de exemplo não contém credenciais reais;
- nenhum endpoint público retorna dados administrativos de auditoria.
- produção e staging usam nomes de cookie e chaves de assinatura diferentes;
- o staging usa `investment_staging`, sem superusuário, criação de banco,
  criação de papel ou replicação;
- o dump é restaurado diretamente por `investment_staging`, sem tentar
  transferir objetos internos pertencentes ao administrador PostgreSQL;
- cada clone elimina códigos de e-mail ativos e cancela somente os trabalhos
  que estavam `queued` ou `running` na cópia;
- o arquivo `deployment/runtime/staging.env` é local, modo `0600`, ignorado pelo
  Git e não entra na imagem.
- todo o diretório local `deployment/secrets` é excluído do contexto Docker;
  entram no pacote somente os modelos públicos terminados em `.example`.

## Matriz de homologação manual

| Área | Verificação | Resultado esperado |
| --- | --- | --- |
| Portal público | abrir `/testefdi/` | conteúdo e livros carregam sem login |
| Administração | abrir editor como proprietário | textos, livros, capas e links editáveis |
| Permissão | abrir editor sem `can_manage_portal` | acesso negado e aba oculta |
| Login Google | autenticar | fluxo anterior preservado |
| Login por e-mail | pedir e usar código | e-mail recebido e sessão criada |
| Antirreuso | usar o mesmo código novamente | código recusado |
| Limite | pedir novamente antes de 60 s | espera informada |
| Falha SMTP | simular indisponibilidade e repetir antes de 60 s | falha transparente e espera preservada |
| Isolamento | autenticar separadamente em produção e staging | um cookie não autentica o outro ambiente |
| Proventos | abrir carteira com posições | eventos B3 e data de atualização |
| CVM | abrir fatos relevantes | metadados e links oficiais |
| Agenda | consultar ano corrente/seguinte | eventos com fonte e renovação anual |
| IMA-B/IRF-M | executar rotina com credenciais | lote oficial persistido e próximo lote indicado |
| IMA-B/IRF-M | executar sem credenciais | indisponível, sem números substitutos |
| ALB | executar monitor | contagem registrada; incidente fora de 5–20 |
| Qualidade | abrir painel | cobertura, atraso, fonte e falhas visíveis |
| Regressão | navegar por todos os painéis | nenhuma função anterior perdida |

## Critérios obrigatórios para promoção

1. `/testefdi/ready` retorna HTTP 200, `1.23.0`, `staging` e `0026_v1_23_email_login`.
2. A suíte completa termina sem `FAILED`.
3. SMTP real entrega o código de teste.
4. Google e código de e-mail criam sessões válidas no staging.
5. Editor do portal respeita a permissão e publica somente o conteúdo salvo.
6. Os três links por livro funcionam somente com HTTPS.
7. Proventos, CVM, agenda, ALB e qualidade concluem ou exibem uma indisponibilidade externa explicada.
8. ANBIMA sem credencial não gera valores.
9. Staging não altera o banco de produção.
10. O clone de staging começa sem códigos ativos ou trabalhos externos ativos
    copiados da produção.
11. O papel `investment_staging` não possui permissões administrativas.
12. Existe aprovação humana expressa antes da promoção.

## Evidência de teste atual

A suíte completa foi executada localmente após a auditoria final do pacote, com
`267 passed` e nenhuma falha. Compilação Python, sintaxe dos dois JavaScripts,
sintaxe do publicador PowerShell, cadeia Alembic e diferenças de whitespace
também foram verificadas. A contagem deve ser registrada novamente no contêiner
de staging depois que o pacote for publicado, pois é esse ambiente que vale para
a decisão de promoção.

## Itens que não podem ser declarados concluídos por teste de código

- criação física e configuração da VM2 na conta OCI;
- fechamento de NSG e bind privado da porta 5432;
- corte real do worker e failback real entre VMs;
- validade das credenciais comerciais do ANBIMA Feed;
- entregabilidade do provedor SMTP real.

Esses itens exigem evidência operacional no ambiente do usuário.
