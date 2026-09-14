# Patch V1.23.0

## Resumo funcional

1. calendário oficial de proventos das carteiras;
2. fatos relevantes oficiais da CVM;
3. agenda renovável do investidor;
4. histórico incremental oficial de IMA-B e IRF-M;
5. painel administrativo de qualidade e frescor;
6. alerta diário para quantidade do ALB fora de 5 a 20 ativos;
7. editor da página pública, livros, capas e links de venda;
8. login por código de e-mail, além do Google.

## Novas rotas

| Área | Rota | Proteção |
| --- | --- | --- |
| Portal | `GET /public/portal` | Pública, somente conteúdo publicado |
| Portal | `GET /portal-media/{id}` | Pública, mídia publicada/cacheável |
| Portal | `GET /admin/portal` | `can_manage_portal` |
| Portal | `PUT /admin/portal/page` | `can_manage_portal` |
| Portal | CRUD e ordem em `/admin/portal/books` | `can_manage_portal` |
| Portal | mídia em `/admin/portal/media` | `can_manage_portal` |
| Autenticação | `POST /auth/email/request` | Pública, limitada por e-mail |
| Autenticação | `POST /auth/email/verify` | Pública, código válido e de uso único |
| Eventos | `GET /investor-events/dividends` | `can_view_portfolio` |
| Eventos | `GET /investor-events/relevant-facts` | `can_view_market` |
| Eventos | `GET /investor-events/calendar` | `can_view_market` |
| Qualidade | `GET /admin/data-quality` | `can_sync_market` |

## Novas rotinas

| Chave administrativa | Trabalho | Fonte principal |
| --- | --- | --- |
| `portfolio_dividends` | `investor_dividends_refresh` | B3 Empresas Listadas |
| `cvm_relevant_facts` | `cvm_relevant_facts_refresh` | CVM Dados Abertos IPE |
| `official_calendar` | `official_calendar_refresh` | BCB, Fed, BLS e calendários de bolsa |
| `ima_history` | `anbima_ima_history_refresh` | ANBIMA Feed |
| `alb_monitor` | `alb_universe_monitor` | Preset ALB e dados consolidados |
| `data_quality` | `data_quality_refresh` | Metadados internos persistidos |

## Banco de dados

- `0024_v1_23_investor_events` cria `corporate_events`, `relevant_facts`, `official_calendar_events` e `alb_universe_observations`.
- `0025_v1_23_portal_cms` cria `portal_pages`, `portal_media`, `portal_books` e `portal_book_links`, além de `can_manage_portal` nos níveis e usuários.
- `0026_v1_23_email_login` cria `email_login_codes`.
- Head esperado: `0026_v1_23_email_login`.

## Configuração

SMTP é obrigatório para o login por e-mail:

- `SMTP_HOST`;
- `SMTP_PORT`;
- `SMTP_USERNAME` e `SMTP_PASSWORD`, quando exigidos pelo provedor;
- `SMTP_FROM_EMAIL`;
- `SMTP_FROM_NAME`;
- `SMTP_STARTTLS`.

O histórico ANBIMA é opcional na instalação, mas necessário para obter o histórico oficial integral:

- `ANBIMA_CLIENT_ID`;
- `ANBIMA_CLIENT_SECRET`;
- `ANBIMA_IMA_HISTORY_START_DATE`;
- `ANBIMA_IMA_HISTORY_BATCH_DAYS`.

Sem credenciais ANBIMA, a rotina registra `unavailable`; ela não usa ETF, estimativa ou outra série como substituto.

## Compatibilidade e operação

- A autenticação Google permanece inalterada.
- A política de usuário é a mesma para login Google e login por e-mail.
- O worker da V1.22 continua podendo ser local ou remoto.
- A segunda VM não é criada por este patch; sua ativação continua sendo uma tarefa operacional controlada.
- Não há promoção automática para produção.
