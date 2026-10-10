"use strict";

// Carregado sob demanda e preservado pela V1.23.8 R1. O módulo mantém as mesmas
// funções e regras usadas antes no arquivo principal.
(()=>{
function accessRuleEditor(level,disabled=false){
  const permissions=level.permissions||{},limits=level.limits||{};
  const sections=accessPermissionSections.map((section,index)=>`<details class="permission-section" ${index<2?"open":""}><summary>${esc(section.title)}<span>${section.items.filter(([key])=>permissions[key]).length} liberada(s)</span></summary><div class="permission-matrix">${section.items.map(([key,label])=>`<label class="check"><input type="checkbox" data-level-permission="${key}" ${permissions[key]?"checked":""} ${disabled?"disabled":""}><span>${esc(label)}</span></label>`).join("")}</div></details>`).join("");
  const limitFields=accessLimitDefinitions.map(field=>`<div class="field"><label>${esc(field.label)}</label><select data-level-limit="${field.key}" ${disabled?"disabled":""}>${field.values.map(value=>`<option value="${value}" ${Number(limits[field.key]||0)===value?"selected":""}>${value}</option>`).join("")}</select></div>`).join("");
  return `${sections}<div class="access-limit-grid">${limitFields}</div>`;
}

function accessLevelCard(level){
  const locked=level.slug==="owner";
  return `<details class="access-level-card" data-level-card="${esc(level.slug)}"><summary><span><strong>${esc(level.name)}</strong><small>${esc(level.description||"")}</small></span><span><span class="pill">${number(level.member_count||0,0)} usuário(s)</span>${level.is_active?'<span class="pill">Ativo</span>':'<span class="pill warning">Inativo</span>'}</span></summary><form class="access-level-form" data-access-level-form="${esc(level.slug)}"><div class="access-level-meta"><div class="field"><label>Nome do nível</label><input name="name" maxlength="80" value="${esc(level.name)}" ${locked?"disabled":""}></div><div class="field"><label>Descrição</label><input name="description" maxlength="500" value="${esc(level.description||"")}" ${locked?"disabled":""}></div>${locked?"":`<label class="check access-active"><input name="is_active" type="checkbox" ${level.is_active?"checked":""}> Nível disponível para novas atribuições</label>`}</div>${accessRuleEditor(level,locked)}${locked?'<div class="notice info">O nível do proprietário é permanente e não pode ser reduzido.</div>':'<button class="button primary" type="submit">Salvar regras deste nível</button>'}</form></details>`;
}

function adminPanelIsCurrent(root,context){
  return root?.dataset.panelKey===context.panelKey&&context.requestSerial===state.adminRequestSerial&&navigationIsCurrent(context.navigationSerial,"admin","admin",context.panelKey);
}

async function loadAccessLevels(root,context){
  const levels=await api("/access/levels",{requestKey:"admin-levels",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:context.force});
  if(!adminPanelIsCurrent(root,context))return;
  root.innerHTML=`<div class="notice info"><strong>Permissões por nível:</strong> altere uma vez aqui e a mudança será aplicada imediatamente a todos os usuários vinculados. Contas antigas só mudam quando você atribuir um nível.</div><div class="access-level-list">${levels.map(accessLevelCard).join("")}</div><details class="data-card create-level-card"><summary><strong>Criar nível adicional</strong></summary><form id="create-access-level-form" class="filter-grid"><div class="field"><label>Identificador interno</label><input name="slug" required pattern="[a-z][a-z0-9_-]{1,31}" placeholder="ex.: parceiro"></div><div class="field"><label>Nome exibido</label><input name="name" required maxlength="80" placeholder="Ex.: Parceiro"></div><div class="field wide-action"><label>Descrição</label><input name="description" maxlength="500"></div><button class="button primary wide-action" type="submit">Criar nível sem permissões</button></form></details>`;
}

function userStatusLabel(status){return ({pending:"Pendente",approved:"Aprovado",blocked:"Bloqueado"})[status]||status;}
async function loadAdminUsers(root,context){
  const params=new URLSearchParams({limit:"100",offset:String(state.adminUsersOffset)});if(state.adminUsersQuery)params.set("q",state.adminUsersQuery);if(state.adminUsersStatus)params.set("status",state.adminUsersStatus);if(state.adminUsersLevel)params.set("level",state.adminUsersLevel);
  const [payload,levels]=await Promise.all([api(`/access/users/manage?${params}`,{requestKey:"admin-users",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:context.force}),api("/access/levels?include_inactive=true",{requestKey:"admin-levels",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:context.force})]);
  if(!adminPanelIsCurrent(root,context))return;
  const users=payload.items||[],activeLevels=levels.filter(level=>level.slug!=="owner"&&level.is_active),from=payload.total?payload.offset+1:0,to=Math.min(payload.offset+payload.limit,payload.total);
  const levelOptions=user=>{
    const legacy=!user.access_level_slug?'<option value="legacy" selected disabled>Personalizado legado (preservado)</option>':"";
    const current=levels.find(level=>level.slug===user.access_level_slug);
    const inactive=current&&!current.is_active?`<option value="${esc(current.slug)}" selected disabled>${esc(current.name)} (inativo)</option>`:"";
    return legacy+inactive+activeLevels.map(level=>`<option value="${esc(level.slug)}" ${user.access_level_slug===level.slug?"selected":""}>${esc(level.name)}</option>`).join("");
  };
  const rows=users.map(user=>`<tr data-user-row="${esc(user.email)}" data-current-level="${esc(user.access_level_slug||"legacy")}" data-current-status="${esc(user.status)}"><td>${user.is_owner?"":`<input type="checkbox" data-user-select="${esc(user.email)}" aria-label="Selecionar ${esc(user.email)}">`}</td><td><strong>${esc(user.display_name||user.email)}</strong><br><small>${esc(user.email)}</small></td><td>${user.is_owner?'<span class="pill">Proprietário</span>':`<select data-user-level>${levelOptions(user)}</select><small class="block-hint">${user.access_inheritance?"Herda regras do nível":"Permissões atuais preservadas"}</small>`}</td><td>${user.is_owner?'<span class="pill">Permanente</span>':`<select data-user-status><option value="pending" ${user.status==="pending"?"selected":""}>Pendente</option><option value="approved" ${user.status==="approved"?"selected":""}>Aprovado</option><option value="blocked" ${user.status==="blocked"?"selected":""}>Bloqueado</option></select>`}</td><td>${user.access_overrides&&Object.keys(user.access_overrides).length?`<span class="pill warning">${Object.keys(user.access_overrides).length} ajuste(s)</span><br><button class="button ghost compact" data-clear-user-overrides="${esc(user.email)}">Remover ajustes</button>`:'<span class="pill">Sem exceções</span>'}</td><td>${dateTime(user.last_seen_at)}</td><td>${user.is_owner?"":`<button class="button primary compact" data-save-user-level="${esc(user.email)}">Salvar</button>`}</td></tr>`).join("");
  root.innerHTML=`<form id="admin-user-filter-form" class="admin-user-filters"><div class="field"><label>Buscar</label><input name="q" value="${esc(state.adminUsersQuery)}" placeholder="Nome ou e-mail"></div><div class="field"><label>Nível</label><select name="level"><option value="">Todos</option><option value="legacy" ${state.adminUsersLevel==="legacy"?"selected":""}>Personalizado legado</option>${levels.map(level=>`<option value="${esc(level.slug)}" ${state.adminUsersLevel===level.slug?"selected":""}>${esc(level.name)}</option>`).join("")}</select></div><div class="field"><label>Status</label><select name="status"><option value="">Todos</option>${["pending","approved","blocked"].map(value=>`<option value="${value}" ${state.adminUsersStatus===value?"selected":""}>${userStatusLabel(value)}</option>`).join("")}</select></div><button class="button secondary" type="submit">Filtrar</button></form><div class="bulk-access-bar"><span><strong>Atribuição em lote</strong><small>Marque usuários desta página</small></span><select id="bulk-access-level">${activeLevels.map(level=>`<option value="${esc(level.slug)}">${esc(level.name)}</option>`).join("")}</select><button class="button secondary" data-bulk-assign-level>Atribuir nível</button></div>${sectionCard("Usuários",`<div class="table-scroll"><table class="admin-users-table"><thead><tr><th></th><th>Usuário</th><th>Nível de acesso</th><th>Status individual</th><th>Exceções</th><th>Último acesso</th><th></th></tr></thead><tbody>${rows||'<tr><td colspan="7"><div class="empty-state compact">Nenhum usuário encontrado.</div></td></tr>'}</tbody></table></div>`,`Exibindo ${from}–${to} de ${payload.total} usuário(s)`)}<div class="pagination"><button class="button ghost" data-admin-users-page="prev" ${payload.offset<=0?"disabled":""}>Anterior</button><span>Página ${Math.floor(payload.offset/payload.limit)+1}</span><button class="button ghost" data-admin-users-page="next" ${to>=payload.total?"disabled":""}>Próxima</button></div>`;
}

function adminUpdateTable(updates){
  return marketTable(adminRefreshGroups.map(item=>({...item,...(updates[item.key]||{})})),[
    {label:"Atualização",render:r=>`<strong>${esc(r.label||r.key)}</strong><br><small>${esc(r.section)} • ${esc(r.frequency)}</small>`},
    {label:"Fonte",render:r=>esc(r.source||"—")},
    {label:"Status",render:r=>`<span class="pill ${["failed","stale","partial"].includes(r.status)?"warning":""}">${esc(updateStatusLabels[r.status]||r.status||"Aguardando")}</span>${r.last_error_code?`<br><small>${esc(r.last_error_code)}</small>`:""}`},
    {label:"Última atualização",render:r=>dateTime(r.last_updated_at)},
    {label:"Próxima",render:r=>dateTime(r.next_update_at)},
    {label:"",render:r=>`<button class="button secondary compact" data-refresh-groups="${esc(r.key)}" ${["queued","running"].includes(r.status)?"disabled":""}>Atualizar</button>`},
  ]);
}

async function loadAdminUpdates(root,context){
  const owner=Boolean(state.session?.access?.is_owner);
  const [summary,updatePayload,officialLaunch]=await Promise.all([
    api("/data/catalog-summary",{requestKey:"admin-catalog-summary",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:context.force}),
    api("/market-dashboard/updates",{requestKey:"admin-updates",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:context.force}),
    owner?api("/backtests/batch/official-launch",{requestKey:"admin-official-launch",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:context.force}):Promise.resolve(null),
  ]);
  if(!adminPanelIsCurrent(root,context))return;
  const updates=updatePayload.updates||{};state.marketEnvelope=state.marketEnvelope||{};state.marketEnvelope.updates={...(state.marketEnvelope.updates||{}),...updates};
  const counts=summary.counts||{},groups=summary.groups||{},allKeys=adminRefreshGroups.map(item=>item.key);
  const grouped=[
    ["Juros, inflação e agenda",["selic_current","selic_focus","macro","rates_calendar"]],
    ["Mercados, criptos e câmbio",["global_markets","crypto","fx"]],
    ["Notícias, comparador e composição do Ibovespa",["headlines","comparison","ibov_portfolio"]],
    ["Catálogo, fundamentos, técnica e métricas atuais",["catalog","fundamentals","technical_daily","technical_intraday","current_metrics"]],
    ["Proventos, CVM, agenda e índices ANBIMA",["portfolio_dividends","cvm_relevant_facts","official_calendar","ima_history"]],
    ["Qualidade e filtro ALB",["alb_monitor","data_quality"]],
  ];
  root.innerHTML=`<div class="metric-grid">${metricCard("Ações",number(groups.stock||0,0),"Ativos ativos")}${metricCard("FIIs",number(groups.fii||0,0),"Fundos imobiliários")}${metricCard("ETFs",number(counts.etf||0,0),"Fundos de índice")}${metricCard("BDRs",number(counts.bdr||0,0),"Recibos negociados na B3")}</div><div class="admin-update-actions"><button class="button secondary" data-refresh-groups="catalog">Atualizar catálogo</button><button class="button secondary" data-refresh-groups="fundamentals">Atualizar fundamentos e notas</button>${grouped.map(([label,keys])=>`<button class="button secondary" data-refresh-groups="${keys.join(",")}">${esc(label)}</button>`).join("")}<button class="button primary" data-refresh-groups="${allKeys.join(",")}" data-confirm-all-updates>Atualizar todas as ${allKeys.length} rotinas</button></div>${officialLaunch?officialRoundLaunchCard(officialLaunch):""}${sectionCard("Todas as atualizações automáticas",adminUpdateTable(updates),"As solicitações entram na fila e não bloqueiam o site")}${sectionCard("Monitor de alertas",`<div class="admin-monitor-row"><span><strong>B3: 5 minutos no pregão</strong><small>Demais mercados: 30 minutos, continuamente</small></span><button class="button secondary" data-run-alert-monitor>Executar verificação agora</button></div><div id="alert-monitor-result" class="notice info hidden"></div>`,`A execução manual respeita as mesmas regras e não envia alertas duplicados`)}`;
}

const jobTypeLabels={market_group_refresh:"Mercado e economia",economy_headlines_refresh:"Manchetes",historical_comparison_refresh:"Comparador histórico",market_catalog_refresh:"Catálogo",market_fundamentals_refresh:"Fundamentos",market_technicals_refresh:"Indicadores técnicos",market_intraday_refresh:"Cotações intradiárias",market_full_sync:"Sincronização completa de mercado",current_metrics_refresh:"Métricas atuais pré-calculadas",asset_price_ingest:"Histórico de preços do ativo",b3_index_portfolio_refresh:"Composição do Ibovespa",portfolio_prices_refresh:"Preços de carteira",user_news_refresh:"Notícias do usuário",personal_backtest_matrix:"Backtest pessoal",investor_dividends_refresh:"Proventos oficiais",cvm_relevant_facts_refresh:"Fatos relevantes CVM",official_calendar_refresh:"Agenda oficial",anbima_ima_history_refresh:"Histórico IMA-B/IRF-M",alb_universe_monitor:"Monitor do filtro ALB",data_quality_refresh:"Qualidade dos dados",operational_retention:"Retenção operacional",noop:"Verificação interna"};
function jobStatusLabel(status){return ({queued:"Na fila",running:"Executando",succeeded:"Concluído",failed:"Falhou",cancelled:"Cancelado"})[status]||status;}
async function loadAdminJobs(root,context){
  const jobs=await api("/admin/jobs?limit=100",{requestKey:"admin-jobs",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:context.force});
  if(!adminPanelIsCurrent(root,context))return;
  const table=marketTable(jobs,[{label:"Trabalho",render:r=>`<strong>${esc(jobTypeLabels[r.job_type]||r.job_type)}</strong><br><small>${esc(r.id)}</small>`},{label:"Status",render:r=>`<span class="pill ${r.status==="failed"?"danger":r.status==="running"?"warning":""}">${esc(jobStatusLabel(r.status))}</span>`},{label:"Progresso",render:r=>r.progress_total?`${number(r.progress_current||0,0)} / ${number(r.progress_total,0)}`:"—"},{label:"Tentativas",render:r=>`${number(r.attempts||0,0)} / ${number(r.max_attempts||0,0)}`},{label:"Solicitado por",render:r=>esc(r.requested_by||"Sistema")},{label:"Atualização",render:r=>dateTime(r.updated_at)},{label:"Mensagem",render:r=>`${esc(r.message||"—")}${r.last_error_code?`<br><small>${esc(r.last_error_code)}</small>`:""}`},{label:"",render:r=>["failed","cancelled"].includes(r.status)?`<button class="button secondary compact" data-retry-admin-job="${esc(r.id)}">Reprocessar</button>`:""}]);
  root.innerHTML=`<div class="admin-monitor-row"><span><strong>Fila de trabalhos em segundo plano</strong><small>Atualizações de mercado, notícias, carteiras e backtests sem travar a navegação.</small></span><button class="button secondary" data-reload-admin-jobs>Atualizar lista</button></div>${sectionCard("100 trabalhos mais recentes",table,"Falhas podem ser reprocessadas; trabalhos ativos nunca são duplicados")}`;
}

function bytesLabel(value){
  const amount=Number(value);if(!Number.isFinite(amount)||amount<0)return "—";
  const units=["B","KB","MB","GB","TB"];let index=0,current=amount;
  while(current>=1024&&index<units.length-1){current/=1024;index+=1;}
  return `${number(current,current>=10||index===0?0:1)} ${units[index]}`;
}

function operationsResourceCards(resources){
  const item=(label,data)=>metricCard(label,nullable(data?.used_pct)?"—":`${number(data.used_pct,1)}%`,`${bytesLabel(data?.used_bytes)} de ${bytesLabel(data?.total_bytes)}`);
  return `<div class="metric-grid operations-resources">${item("Memória do contêiner",resources?.container_memory?.used_pct===null?resources?.memory:resources?.container_memory)}${item("Memória da máquina",resources?.memory)}${item("Swap",resources?.swap)}${item("Disco",resources?.disk)}</div>`;
}

async function loadAdminOperations(root,context){
  const payload=await api("/admin/operations",{requestKey:"admin-operations",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:context.force});
  if(!adminPanelIsCurrent(root,context))return;
  const severityLabel={healthy:"Operacional",warning:"Atenção",critical:"Crítico"};
  const serviceRoleLabel={worker:"Processamento em segundo plano",web:"Aplicação web"};
  const routeLabel={health:"Saúde e disponibilidade",dashboard:"Painel de Mercado",screener_50:"Filtro com até 50 ativos",screener_100:"Filtro com até 100 ativos",asset_detail:"Detalhe do ativo",panel_dashboard:"Mercado",panel_analysis:"Mercado e Análises",panel_portfolio:"Minha Carteira",panel_finances:"Minhas Finanças",panel_backtests:"Backtests",panel_admin:"Administração"};
  const leaseLabel={"background-scheduler":"Agendador automático","price-alert-monitor-leader":"Monitor de alertas","price-alert-monitor-cycle":"Ciclo de verificação dos alertas"};
  const services=marketTable(payload.services||[],[
    {label:"Serviço",render:r=>`<strong>${esc(serviceRoleLabel[r.role]||r.role)}</strong><br><small>${esc(r.node_id)}</small>`},
    {label:"Ambiente",render:r=>esc(r.environment)},
    {label:"Versão",render:r=>`${esc(r.version)}${r.commit_sha?`<br><small>${esc(String(r.commit_sha).slice(0,10))}</small>`:""}`},
    {label:"Heartbeat",render:r=>`${dateTime(r.last_seen_at)}<br><small>há ${number(r.age_seconds,0)} s</small>`},
    {label:"Agendador",render:r=>r.scheduler_leader?'<span class="pill">Líder</span>':'<span class="pill warning">Espera</span>'},
    {label:"Alertas",render:r=>r.alert_monitor_leader?'<span class="pill">Líder</span>':'<span class="pill warning">Espera</span>'},
  ]);
  const latencies=marketTable(payload.route_metrics?.categories||[],[
    {label:"Rota medida",render:r=>`<strong>${esc(routeLabel[r.key]||r.key)}</strong><br><small>${number(r.count,0)} amostras</small>`},
    {label:"p50",render:r=>nullable(r.p50_ms)?"—":`${number(r.p50_ms,0)} ms`},
    {label:"p95",render:r=>nullable(r.p95_ms)?"—":`${number(r.p95_ms,0)} ms`},
    {label:"Máximo",render:r=>nullable(r.max_ms)?"—":`${number(r.max_ms,0)} ms`},
    {label:"Meta p95",render:r=>nullable(r.target_p95_ms)?"—":`${number(r.target_p95_ms,0)} ms`},
    {label:"Situação",render:r=>!r.sample_sufficient?'<span class="pill warning">Coletando</span>':r.within_target?'<span class="pill">Dentro da meta</span>':'<span class="pill danger">Acima da meta</span>'},
  ]);
  const browserRows=(payload.browser_performance||[]).slice(0,80);
  const browserPerformance=browserRows.length?marketTable(browserRows,[
    {label:"Hora",render:r=>dateTime(r.bucket_hour)},
    {label:"Painel",render:r=>`<strong>${esc(routeLabel[`panel_${r.panel}`]||r.panel)}</strong><br><small>${esc(r.device_class||"—")} • ${esc(r.cache_state||"—")}</small>`},
    {label:"Amostras",render:r=>`${number(r.sample_count,0)}<br><small>${number(r.success_pct,1)}% concluídas</small>`},
    {label:"p50 / p95",render:r=>`${number(r.p50_ms,0)} / ${number(r.p95_ms,0)} ms`},
    {label:"Máximo",render:r=>`${number(r.max_ms,0)} ms`},
    {label:"Web Vitals",render:r=>`LCP ${number(r.web_vitals?.lcp_ms?.average,0)} ms<br><small>INP ${number(r.web_vitals?.inp_ms?.average,0)} ms • CLS ${number(r.web_vitals?.cls?.average,3)}</small>`},
  ]):'<div class="empty-state compact"><strong>Coletando a experiência real</strong>Os resumos aparecerão por hora apó a navegação autenticada.</div>';
  const openIncidents=(payload.incidents||[]).filter(item=>item.status==="open");
  const incidents=marketTable(openIncidents,[
    {label:"Gravidade",render:r=>`<span class="pill ${r.severity==="critical"?"danger":"warning"}">${r.severity==="critical"?"Crítico":"Atenção"}</span>`},
    {label:"Ocorrência",render:r=>`<strong>${esc(r.title)}</strong><br><small>${esc(r.code)}</small>`},
    {label:"Detalhe",render:r=>esc(r.message)},
    {label:"Desde",render:r=>dateTime(r.first_seen_at)},
    {label:"Última detecção",render:r=>dateTime(r.last_seen_at)},
  ]);
  const leaders=(payload.leases||[]).map(item=>`<span class="operations-lease"><strong>${esc(leaseLabel[item.lease_name]||item.lease_name)}</strong><small>${esc(item.holder_id)} • até ${dateTime(item.expires_at)}</small></span>`).join("")||'<span class="empty-state compact">Nenhuma liderança ativa registrada.</span>';
  root.innerHTML=`<div class="admin-monitor-row operations-summary ${esc(payload.status)}"><span><strong>Saúde operacional: ${esc(severityLabel[payload.status]||payload.status)}</strong><small>Leitura de ${dateTime(payload.generated_at)} • ${openIncidents.length} ocorrência(s) aberta(s)</small></span><button class="button secondary" data-reload-admin-operations>Atualizar diagnóstico</button></div><div class="metric-grid">${metricCard("Worker",payload.worker_health?.status==="ok"?"Ativo":"Indisponível",payload.worker_health?.last_seen_at?`Último sinal ${dateTime(payload.worker_health.last_seen_at)}`:"Sem heartbeat")}${metricCard("Na fila",number(payload.queue?.queued||0,0),`Mais antigo: ${number(payload.queue?.oldest_due_minutes||0,0)} min`)}${metricCard("Em execução",number(payload.queue?.running||0,0),`${number(payload.queue?.stale_running||0,0)} sem heartbeat`)}${metricCard("Ocorrências",number(openIncidents.length,0),openIncidents.some(i=>i.severity==="critical")?"Há item crítico":"Sem item crítico")}</div>${operationsResourceCards(payload.resources)}${sectionCard("Serviços e liderança",services,"O esperado é um único líder para o agendador e um único líder para o monitor de alertas")}${sectionCard("Leases distribuídas",`<div class="operations-leases">${leaders}</div>`,`A liderança expira automaticamente se uma VM deixar de responder`) }${sectionCard("Tempo de resposta do servidor",latencies,`p50/p95 de até ${number(payload.route_metrics?.window_size||0,0)} medições desde ${dateTime(payload.route_metrics?.since)}`)}${sectionCard("Experiência real no navegador",browserPerformance,"Resumos horários das últimas 24 horas; nenhum clique individual é gravado no banco")}${sectionCard("Ocorrências abertas",incidents||'<div class="empty-state compact"><strong>Nenhuma ocorrência aberta.</strong>Os limites monitorados estão normais.</div>',"Fila parada, falhas repetidas, dados vencidos, memória, swap, disco e latência")}`;
}

function dataQualityStatus(value){return ({updated:"Atualizado",partial:"Cobertura parcial",stale:"Desatualizado",unavailable:"Indisponível",failed:"Falhou",queued:"Na fila",running:"Atualizando"})[value]||value||"Aguardando";}
function dataQualityClass(value){return ["failed","unavailable"].includes(value)?"danger":["partial","stale"].includes(value)?"warning":"";}

async function loadAdminQuality(root,context){
  const payload=await api("/admin/data-quality",{requestKey:"admin-quality",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:context.force});
  if(!adminPanelIsCurrent(root,context))return;
  const summary=payload.summary||{},alb=payload.alb||null,rows=payload.sources||[];
  const sourceRows=marketTable(rows,[
    {label:"Conjunto de dados",render:r=>`<strong>${esc(r.label||r.key)}</strong><br><small>${esc(r.category||"")}</small>`},
    {label:"Fonte",render:r=>r.source_url?`<a href="${esc(safeExternalUrl(r.source_url))}" target="_blank" rel="noopener noreferrer">${esc(r.source||"Fonte oficial")}</a>`:esc(r.source||"—")},
    {label:"Situação",render:r=>`<span class="pill ${dataQualityClass(r.status)}">${esc(dataQualityStatus(r.status))}</span>${r.last_error_code?`<br><small>${esc(r.last_error_code)}</small>`:""}`},
    {label:"Cobertura",render:r=>nullable(r.coverage_pct)?(nullable(r.item_count)?"—":`${number(r.item_count,0)} item(ns)`):`${pct(r.coverage_pct)}<br><small>${number(r.item_count,0)} de ${number(r.total_items,0)}</small>`},
    {label:"Última atualização",render:r=>dateTime(r.last_updated_at)},
    {label:"Próxima",render:r=>dateTime(r.next_update_at)},
  ]);
  const albBody=alb?`<div class="metric-grid summary-grid">${metricCard("Ativos no ALB",number(alb.asset_count,0),`Faixa esperada: ${number(alb.target_min,0)} a ${number(alb.target_max,0)}`)}${metricCard("Situação",alb.status==="within_range"?"Dentro da faixa":"Requer atenção","Critérios nunca são afrouxados automaticamente")}${metricCard("Referência",dateOnly(alb.reference_date),`Preset ${alb.preset_version||"—"}`)}</div>${(alb.tickers||[]).length?`<div class="tag-list">${alb.tickers.map(item=>`<span>${esc(item)}</span>`).join("")}</div>`:""}`:'<div class="empty-state compact"><strong>Primeira medição pendente</strong>O monitor será executado pela rotina diária, sem alterar o preset ALB.</div>';
  root.innerHTML=`<div class="admin-monitor-row operations-summary ${esc(payload.status)}"><span><strong>Qualidade dos dados: ${payload.status==="ok"?"normal":payload.status==="critical"?"crítica":"atenção"}</strong><small>Leitura em ${dateTime(payload.generated_at)} • somente metadados persistidos, sem bloquear o site</small></span><button class="button secondary" data-reload-admin-quality>Atualizar diagnóstico</button></div><div class="metric-grid">${metricCard("Fontes monitoradas",number(summary.total||0,0),"Séries, snapshots e cobertura por ativo")}${metricCard("Atualizadas",number(summary.updated||0,0),"Dentro do prazo esperado")}${metricCard("Parciais",number(summary.partial||0,0),"Cobertura abaixo de 80%")}${metricCard("Vencidas ou indisponíveis",number((summary.stale||0)+(summary.unavailable_or_failed||0),0),"Exigem atualização ou revisão")}</div>${sectionCard("Filtro ALB — controle diário",albBody,"A faixa esperada é de 5 a 20 ativos; um alerta operacional é aberto fora dela")}${sectionCard("Cobertura, frescor e proveniência",sourceRows,"Cada linha informa a fonte, a última atualização e eventuais falhas")}`;
}

const adminAnalysisAssetTypes=[
  {id:"stock",label:"Ações"},{id:"fii",label:"FIIs"},{id:"etf",label:"ETFs"},{id:"bdr",label:"BDRs"},{id:"future",label:"Futuros"},
];
const adminAnalysisPresetLabels={default:"Padrão",cnpi:"FDI",alb:"ALB"};
const adminFundamentalFields={
  stock:["price","pe","pbv","dividend_yield_pct","ev_ebitda","ebit_margin_pct","net_margin_pct","current_ratio","roe_pct","roic_pct","gross_debt_to_equity","net_debt_to_ebitda","revenue_cagr_5y_pct","earnings_cagr_5y_pct","daily_liquidity"],
  fii:["price","pbv","dividend_yield_pct","ffo_yield_pct","cap_rate_pct","vacancy_pct","financial_vacancy_pct","ltv_pct","daily_liquidity"],
};

function adminAnalysisLabel(group,key){
  const definitions=window.FDIFeatures.analysis?.filterDefinitions||{scores:[],fundamental:[]};
  const rows=group==="score"?definitions.scores:definitions.fundamental;
  return rows.find(([id])=>id===key)?.[1]||key.replaceAll("_"," ");
}

function adminRangeEditor(group,key,configuration){
  const source=group==="score"?configuration.score_filters:configuration.fundamental_filters,range=source?.[key]||{};
  return `<div class="field admin-analysis-range" data-admin-analysis-range="${group}" data-admin-analysis-field="${esc(key)}"><label>${esc(adminAnalysisLabel(group,key))}</label><div class="range-pair"><input type="number" step="any" data-bound="min" value="${esc(range.min??"")}" placeholder="Mín."><input type="number" step="any" data-bound="max" value="${esc(range.max??"")}" placeholder="Máx."></div></div>`;
}

function adminConfigurationSummary(configuration={}){
  const items=[];
  for(const [field,range] of Object.entries(configuration.fundamental_filters||{}))items.push(`${adminAnalysisLabel("fundamental",field)}: ${nullable(range.min)?"—":`mín. ${number(range.min)}`} ${nullable(range.max)?"":`máx. ${number(range.max)}`}`.trim());
  for(const [field,range] of Object.entries(configuration.score_filters||{}))items.push(`${adminAnalysisLabel("score",field)}: ${nullable(range.min)?"—":`mín. ${number(range.min)}`} ${nullable(range.max)?"":`máx. ${number(range.max)}`}`.trim());
  const technical=configuration.technical_filters||{};
  for(const [key,label] of [["daily_trend","Tendência diária"],["weekly_trend","Tendência semanal"],["monthly_trend","Tendência mensal"]])if(technical[key]&&technical[key]!=="any")items.push(`${label}: ${technical[key]==="up"?"alta":"baixa"}`);
  if(technical.rsi14)items.push(`RSI 14: ${nullable(technical.rsi14.min)?"—":`mín. ${number(technical.rsi14.min)}`} ${nullable(technical.rsi14.max)?"":`máx. ${number(technical.rsi14.max)}`}`.trim());
  const valuationLabels={below_graham:"Número de Graham",below_barsi_6pct:"Preço-teto por dividendos",below_relative_value:"Valuation relativo",below_economic_value:"Valor econômico"};
  Object.entries(valuationLabels).forEach(([key,label])=>{if(configuration.valuation_flags?.[key])items.push(label);});
  if(configuration.ibov_membership&&configuration.ibov_membership!=="any")items.push(configuration.ibov_membership==="inside"?"Somente IBOV":"Fora do IBOV");
  return items.length?`<div class="tag-list admin-analysis-summary-tags">${items.map(item=>`<span>${esc(item)}</span>`).join("")}</div>`:'<span class="muted">Sem critérios adicionais; utiliza o universo integral da classe.</span>';
}

function adminPresetEditor(row){
  const configuration=JSON.parse(JSON.stringify(row.owner_configuration||row.factory_configuration||{})),technical=configuration.technical_filters||{},valuation=configuration.valuation_flags||{};
  const fundamental=(adminFundamentalFields[row.asset_type]||[]).map(key=>adminRangeEditor("fundamental",key,configuration)).join("");
  const scores=["quality_score","value_score","growth_score","technical_score","risk_score","liquidity_score","alb_score","data_quality_score"].map(key=>adminRangeEditor("score",key,configuration)).join("");
  const rsi=technical.rsi14||{},economic=configuration.valuation_assumptions?.economic_value||{};
  const scenarios=economic.scenarios||{},scenario=(name,field,fallback)=>scenarios[name]?.[field]??fallback;
  const stockUniverse=row.asset_type==="stock"?`<details class="filter-subgroup"><summary>Universo de ações</summary><div class="filter-grid compact-grid"><div class="field"><label>Participação no IBOV</label><select data-admin-analysis-value="ibov_membership"><option value="any" ${configuration.ibov_membership==="any"||!configuration.ibov_membership?"selected":""}>Qualquer</option><option value="inside" ${configuration.ibov_membership==="inside"?"selected":""}>Somente no IBOV</option><option value="outside" ${configuration.ibov_membership==="outside"?"selected":""}>Fora do IBOV</option></select></div><div class="field"><label>Porte</label><select data-admin-analysis-value="company_sizes" multiple size="3"><option value="large" ${(configuration.company_sizes||[]).includes("large")?"selected":""}>Blue Chip / Large Cap</option><option value="mid" ${(configuration.company_sizes||[]).includes("mid")?"selected":""}>Mid Cap</option><option value="small" ${(configuration.company_sizes||[]).includes("small")?"selected":""}>Small Cap</option></select></div></div></details>`:"";
  const economicFields=row.asset_type==="stock"?`<details class="filter-subgroup"><summary>Cenários de valor econômico</summary><label class="check"><input type="checkbox" data-admin-analysis-economic="use_ttm_dividend" ${economic.use_ttm_dividend?"checked":""}> Confirmar proventos dos últimos 12 meses como D0</label><div class="filter-grid compact-grid">${[["conservative","Conservador",16,1],["base","Base",13,3],["optimistic","Otimista",11,4]].map(([key,label,ret,growth])=>`<div class="field"><label>${label}: retorno (%)</label><input type="number" step="0.1" data-admin-analysis-economic="${key}.required_return_pct" value="${esc(scenario(key,"required_return_pct",ret))}"></div><div class="field"><label>${label}: crescimento (%)</label><input type="number" step="0.1" data-admin-analysis-economic="${key}.growth_pct" value="${esc(scenario(key,"growth_pct",growth))}"></div>`).join("")}<div class="field"><label>Margem de segurança (%)</label><input type="number" min="0" max="99" step="0.1" data-admin-analysis-economic="margin_of_safety_pct" value="${esc(economic.margin_of_safety_pct??20)}"></div></div></details>`:"";
  return `<form class="access-level-card admin-analysis-preset" data-admin-preset-form data-asset-type="${esc(row.asset_type)}" data-preset-id="${esc(row.preset_id)}" data-revision="${Number(row.revision||0)}"><div class="admin-analysis-preset-heading"><span><strong>${esc(adminAnalysisPresetLabels[row.preset_id]||row.preset_id)}</strong><small>${row.active_variant==="owner"?"Alternativa administrativa ativa":"Padrão original ativo"} • revisão ${number(row.revision||0,0)}</small></span><span class="pill ${row.active_variant==="owner"?"":"muted"}">${row.active_variant==="owner"?"Alternativa":"Original"}</span></div><details class="filter-subgroup"><summary>Padrão original preservado</summary><div class="notice info">Esta referência é imutável e sempre poderá ser restaurada.</div>${adminConfigurationSummary(row.factory_configuration)}</details><div class="admin-analysis-owner-toggle"><label class="check"><input type="checkbox" name="owner_enabled" ${row.owner_enabled?"checked":""}> Ativar esta configuração alternativa para os usuários autorizados</label><small>Desmarcar preserva a alternativa, mas volta a usar o padrão original.</small></div>${fundamental?`<details class="filter-subgroup" open><summary>Indicadores fundamentalistas</summary><div class="filter-grid">${fundamental}</div></details>`:""}${row.asset_type==="stock"||row.asset_type==="fii"?`<details class="filter-subgroup"><summary>Notas e qualidade</summary><div class="filter-grid">${scores}</div></details>`:""}<details class="filter-subgroup" open><summary>Indicadores técnicos</summary><div class="filter-grid"><div class="field"><label>RSI 14</label><div class="range-pair"><input type="number" step="any" data-admin-rsi="min" value="${esc(rsi.min??"")}" placeholder="Mín."><input type="number" step="any" data-admin-rsi="max" value="${esc(rsi.max??"")}" placeholder="Máx."></div></div><div class="field"><label>Média da tendência</label><select data-admin-analysis-value="trend_period"><option value="20" ${Number(configuration.trend_period)===20?"selected":""}>20 períodos</option><option value="21" ${Number(configuration.trend_period)!==20?"selected":""}>21 períodos</option></select></div>${[["daily_trend","Diária"],["weekly_trend","Semanal"],["monthly_trend","Mensal"]].map(([key,label])=>`<div class="field"><label>Tendência ${label.toLowerCase()}</label><select data-admin-technical="${key}"><option value="any" ${!technical[key]||technical[key]==="any"?"selected":""}>Qualquer</option><option value="up" ${technical[key]==="up"?"selected":""}>Alta</option><option value="down" ${technical[key]==="down"?"selected":""}>Baixa</option></select></div>`).join("")}<label class="check"><input type="checkbox" data-admin-technical="volume_daily_above_ma9" ${technical.volume_daily_above_ma9?"checked":""}> Volume diário acima da média 9</label><label class="check"><input type="checkbox" data-admin-technical="volume_monthly_above_ma9" ${technical.volume_monthly_above_ma9?"checked":""}> Volume mensal acima da média 9</label></div></details><details class="filter-subgroup"><summary>Metodologias de valor</summary><div class="valuation-choice-grid">${[["below_graham","Número de Graham"],["below_barsi_6pct","Preço-teto por dividendos"],["below_relative_value","Valuation relativo"],["below_economic_value","Valor econômico"]].map(([key,label])=>`<label class="check"><input type="checkbox" data-admin-valuation="${key}" ${valuation[key]?"checked":""}> ${label}</label>`).join("")}</div><div class="filter-grid compact-grid"><div class="field"><label>Combinação</label><select data-admin-valuation="logic"><option value="all" ${(valuation.logic||"all")==="all"?"selected":""}>Todos</option><option value="any" ${valuation.logic==="any"?"selected":""}>Ao menos um</option></select></div><div class="field"><label>Potencial mínimo (%)</label><input type="number" min="0" step="0.1" data-admin-valuation="minimum_upside_pct" value="${esc(valuation.minimum_upside_pct??"")}"></div></div></details>${economicFields}${stockUniverse}<div class="admin-analysis-actions"><button type="button" class="button ghost danger" data-reset-admin-preset="${esc(row.preset_id)}" data-asset-type="${esc(row.asset_type)}">Restaurar padrão original</button><button class="button primary" type="submit">Salvar configuração alternativa</button></div></form>`;
}

function adminColumnsEditor(row){
  const available=row.available_columns||[],byId=new Map(available.map(item=>[item.id,item])),preferred=row.owner_columns||row.factory_columns||[];
  const ordered=[];preferred.forEach(id=>{if(byId.has(id)){ordered.push(byId.get(id));byId.delete(id);}});available.forEach(item=>{if(byId.has(item.id)){ordered.push(item);byId.delete(item.id);}});
  const active=new Set(preferred);
  return `<form class="access-level-card admin-column-settings" data-admin-columns-form data-asset-type="${esc(row.asset_type)}" data-revision="${Number(row.revision||0)}"><div class="admin-analysis-preset-heading"><span><strong>Colunas padrão de ${esc(adminAnalysisAssetTypes.find(item=>item.id===row.asset_type)?.label||row.asset_type)}</strong><small>${row.active_variant==="owner"?"Ordem administrativa ativa":"Ordem original ativa"}</small></span><label class="check"><input type="checkbox" name="owner_enabled" ${row.owner_enabled?"checked":""}> Ativar alternativa</label></div><div class="notice info">Marque as colunas visíveis por padrão e use as setas para definir a ordem. O Ativo permanece obrigatório. Cada usuário ainda pode personalizar sua própria tabela.</div><div class="admin-column-order">${ordered.map((item,index)=>`<div class="admin-column-row" data-admin-column-id="${esc(item.id)}"><label class="check"><input type="checkbox" ${active.has(item.id)||item.always?"checked":""} ${item.always?"disabled":""}> ${esc(item.label)}</label><span><button type="button" class="icon-button" data-move-admin-column="up" aria-label="Mover ${esc(item.label)} para cima" ${index===0?"disabled":""}>↑</button><button type="button" class="icon-button" data-move-admin-column="down" aria-label="Mover ${esc(item.label)} para baixo" ${index===ordered.length-1?"disabled":""}>↓</button></span></div>`).join("")}</div><div class="admin-analysis-actions"><button type="button" class="button ghost danger" data-reset-admin-columns="${esc(row.asset_type)}">Restaurar colunas originais</button><button class="button primary" type="submit">Salvar colunas e ordem</button></div></form>`;
}

function renderAdminAnalysisSettings(root){
  const payload=state.adminAnalysisSettings||{},type=state.adminAnalysisType;
  const presets=(payload.presets||[]).filter(item=>item.asset_type===type),columns=(payload.columns||[]).find(item=>item.asset_type===type);
  root.innerHTML=`<div class="notice info"><strong>Configurações seguras:</strong> os padrões homologados continuam imutáveis. A alternativa só passa a valer quando é salva e ativada; restaurar nunca apaga filtros pessoais nem históricos.</div><div class="admin-analysis-type-picker"><label for="admin-analysis-type"><strong>Classe de ativo</strong></label><select id="admin-analysis-type">${adminAnalysisAssetTypes.map(item=>`<option value="${item.id}" ${item.id===type?"selected":""}>${item.label}</option>`).join("")}</select></div>${sectionCard("Filtros Padrão, FDI e ALB",`<div class="admin-analysis-preset-list">${presets.map(adminPresetEditor).join("")}</div>`,`Padrão de fábrica ${esc(payload.factory_version||"V1.23.0 R7")}`)}${columns?sectionCard("Colunas padrão e ordem",adminColumnsEditor(columns),"A preferência individual continua prevalecendo para quem já personalizou a tabela"):""}`;
}

async function loadAdminAnalysisSettings(root,context=null){
  const payload=await api("/admin/analysis-settings",{requestKey:"admin-analysis-settings",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:Boolean(context?.force)});
  if(context&&!adminPanelIsCurrent(root,context))return;
  state.adminAnalysisSettings=payload;
  renderAdminAnalysisSettings(root);
}

function adminSetNested(target,path,value){const parts=path.split(".");let cursor=target;for(const part of parts.slice(0,-1)){cursor[part]??={};cursor=cursor[part];}cursor[parts.at(-1)]=value;}

function adminPresetConfigurationFromForm(form){
  const row=state.adminAnalysisSettings.presets.find(item=>item.asset_type===form.dataset.assetType&&item.preset_id===form.dataset.presetId),configuration=JSON.parse(JSON.stringify(row.owner_configuration||row.factory_configuration||{}));
  configuration.asset_type=form.dataset.assetType;configuration.fundamental_filters={};configuration.score_filters={};configuration.technical_filters={...(configuration.technical_filters||{})};configuration.valuation_flags={...(configuration.valuation_flags||{})};
  form.querySelectorAll("[data-admin-analysis-range]").forEach(group=>{const min=group.querySelector('[data-bound="min"]').value,max=group.querySelector('[data-bound="max"]').value;if(min!==""||max!==""){const target=group.dataset.adminAnalysisRange==="score"?configuration.score_filters:configuration.fundamental_filters;target[group.dataset.adminAnalysisField]={min:min===""?null:Number(min),max:max===""?null:Number(max)};}});
  const rsiMin=form.querySelector('[data-admin-rsi="min"]')?.value||"",rsiMax=form.querySelector('[data-admin-rsi="max"]')?.value||"";if(rsiMin!==""||rsiMax!=="")configuration.technical_filters.rsi14={min:rsiMin===""?null:Number(rsiMin),max:rsiMax===""?null:Number(rsiMax)};else delete configuration.technical_filters.rsi14;
  form.querySelectorAll("[data-admin-technical]").forEach(input=>{configuration.technical_filters[input.dataset.adminTechnical]=input.type==="checkbox"?input.checked:input.value;});
  form.querySelectorAll("[data-admin-valuation]").forEach(input=>{const key=input.dataset.adminValuation,value=input.type==="checkbox"?input.checked:input.value;configuration.valuation_flags[key]=key==="minimum_upside_pct"?(value===""?null:Number(value)):value;});
  const trend=form.querySelector('[data-admin-analysis-value="trend_period"]');if(trend)configuration.trend_period=Number(trend.value);
  const ibov=form.querySelector('[data-admin-analysis-value="ibov_membership"]');if(ibov)configuration.ibov_membership=ibov.value;
  const sizes=form.querySelector('[data-admin-analysis-value="company_sizes"]');if(sizes)configuration.company_sizes=[...sizes.selectedOptions].map(option=>option.value);
  const economicInputs=form.querySelectorAll("[data-admin-analysis-economic]");if(economicInputs.length){const economic={scenarios:{}};economicInputs.forEach(input=>{const path=input.dataset.adminAnalysisEconomic,value=input.type==="checkbox"?input.checked:Number(input.value);if(path.includes(".")){const [scenario,field]=path.split(".");economic.scenarios[scenario]??={};economic.scenarios[scenario][field]=value;}else economic[path]=value;});configuration.valuation_assumptions={...(configuration.valuation_assumptions||{}),economic_value:economic};}
  configuration.include_technical_columns=true;configuration.limit=Number(configuration.limit||50);
  return configuration;
}

async function saveAdminPreset(form){
  const button=form.querySelector('button[type="submit"]');button.disabled=true;
  try{const configuration=adminPresetConfigurationFromForm(form);validateAnalysisRequest(configuration);await api(`/admin/analysis-settings/presets/${encodeURIComponent(form.dataset.assetType)}/${encodeURIComponent(form.dataset.presetId)}`,{method:"PUT",body:JSON.stringify({configuration,owner_enabled:Boolean(form.elements.owner_enabled.checked),expected_revision:Number(form.dataset.revision||0)})});state.analysisCatalog={};state.analysisColumnCatalog={};state.analysisResultCache.clear();toast("Configuração alternativa salva.","success");await loadAdminAnalysisSettings($("#admin-tab-content"));}catch(error){toast(error.message,"error");button.disabled=false;}
}

async function resetAdminPreset(button){
  if(!window.confirm(`Restaurar o preset ${adminAnalysisPresetLabels[button.dataset.resetAdminPreset]||button.dataset.resetAdminPreset} ao padrão original homologado?`))return;
  const row=state.adminAnalysisSettings.presets.find(item=>item.asset_type===button.dataset.assetType&&item.preset_id===button.dataset.resetAdminPreset);
  try{await api(`/admin/analysis-settings/presets/${encodeURIComponent(button.dataset.assetType)}/${encodeURIComponent(button.dataset.resetAdminPreset)}/reset`,{method:"POST",body:JSON.stringify({expected_revision:Number(row?.revision||0)})});state.analysisCatalog={};state.analysisResultCache.clear();toast("Padrão original restaurado.","success");await loadAdminAnalysisSettings($("#admin-tab-content"));}catch(error){toast(error.message,"error");}
}

function refreshAdminColumnMoveButtons(form){const rows=$$("[data-admin-column-id]",form);rows.forEach((row,index)=>{const buttons=$$("[data-move-admin-column]",row);buttons.forEach(button=>button.disabled=button.dataset.moveAdminColumn==="up"?index===0:index===rows.length-1);});}
function moveAdminColumn(button){const row=button.closest("[data-admin-column-id]"),form=button.closest("[data-admin-columns-form]"),sibling=button.dataset.moveAdminColumn==="up"?row.previousElementSibling:row.nextElementSibling;if(!sibling)return;if(button.dataset.moveAdminColumn==="up")row.parentNode.insertBefore(row,sibling);else row.parentNode.insertBefore(sibling,row);refreshAdminColumnMoveButtons(form);}

async function saveAdminColumns(form){
  const row=state.adminAnalysisSettings.columns.find(item=>item.asset_type===form.dataset.assetType),columns=$$("[data-admin-column-id]",form).filter(item=>item.querySelector('input[type="checkbox"]').checked).map(item=>item.dataset.adminColumnId),button=form.querySelector('button[type="submit"]');button.disabled=true;
  try{await api(`/admin/analysis-settings/columns/${encodeURIComponent(form.dataset.assetType)}`,{method:"PUT",body:JSON.stringify({columns,owner_enabled:Boolean(form.elements.owner_enabled.checked),expected_revision:Number(row?.revision||0)})});state.analysisColumnCatalog={};state.analysisCatalog={};toast("Colunas padrão e ordem salvas.","success");await loadAdminAnalysisSettings($("#admin-tab-content"));}catch(error){toast(error.message,"error");button.disabled=false;}
}

async function resetAdminColumns(assetType){
  if(!window.confirm("Restaurar as colunas visíveis e a ordem originais desta classe?"))return;
  const row=state.adminAnalysisSettings.columns.find(item=>item.asset_type===assetType);
  try{await api(`/admin/analysis-settings/columns/${encodeURIComponent(assetType)}/reset`,{method:"POST",body:JSON.stringify({expected_revision:Number(row?.revision||0)})});state.analysisColumnCatalog={};state.analysisCatalog={};toast("Colunas originais restauradas.","success");await loadAdminAnalysisSettings($("#admin-tab-content"));}catch(error){toast(error.message,"error");}
}

function portalField(content,path,label,{textarea=false,wide=false,list=false}={}){
  const parts=path.split(".");let value=content;for(const part of parts)value=value?.[part];
  if(list)value=(value||[]).join("\n");
  const control=textarea?`<textarea rows="${wide?4:2}" data-portal-page-field="${esc(path)}" ${list?'data-portal-list="true"':""}>${esc(value||"")}</textarea>`:`<input data-portal-page-field="${esc(path)}" value="${esc(value||"")}">`;
  return `<div class="field ${wide?"wide-action":""}"><label>${esc(label)}</label>${control}</div>`;
}

function portalPageEditor(payload){
  const content=payload.content||{},purpose=content.purpose?.items||[];
  return `<form id="portal-page-form" class="portal-admin-sections" data-portal-revision="${Number(payload.revision||1)}">
    <details class="data-card" open><summary><strong>Título, marca e navegação</strong></summary><div class="filter-grid portal-edit-grid">
      ${portalField(content,"meta.title","Título da janela",{wide:true})}${portalField(content,"meta.description","Descrição para buscadores",{textarea:true,wide:true})}
      ${portalField(content,"brand.monogram","Monograma da marca")}${portalField(content,"brand.primary","Marca — linha principal")}${portalField(content,"brand.secondary","Marca — linha secundária")}
      ${portalField(content,"navigation.skip","Atalho de acessibilidade")}${portalField(content,"navigation.books","Menu dos livros")}${portalField(content,"navigation.purpose","Menu da proposta")}${portalField(content,"navigation.platform","Menu da plataforma")}${portalField(content,"navigation.admin","Link de ajustes")}
    </div></details>
    <details class="data-card"><summary><strong>Abertura da página</strong></summary><div class="filter-grid portal-edit-grid">
      ${portalField(content,"hero.eyebrow","Chamada curta")}${portalField(content,"hero.title","Título principal",{wide:true})}${portalField(content,"hero.intro","Texto de apresentação",{textarea:true,wide:true})}
      ${portalField(content,"hero.primary_action","Botão da plataforma")}${portalField(content,"hero.secondary_action","Botão dos livros")}${portalField(content,"hero.proof","Temas — um por linha",{textarea:true,wide:true,list:true})}
      ${portalField(content,"hero.collection_title","Título da coleção")}${portalField(content,"hero.collection_subtitle","Subtítulo da coleção")}
    </div></details>
    <details class="data-card"><summary><strong>Nossa proposta</strong></summary><div class="filter-grid portal-edit-grid">
      ${portalField(content,"purpose.eyebrow","Chamada curta")}${portalField(content,"purpose.title","Título",{wide:true})}
      ${purpose.map((item,index)=>`<fieldset class="portal-purpose-item wide-action"><legend>Bloco ${index+1}</legend><div class="field"><label>Número</label><input data-portal-purpose="${index}" data-portal-purpose-field="number" value="${esc(item.number)}"></div><div class="field"><label>Título</label><input data-portal-purpose="${index}" data-portal-purpose-field="title" value="${esc(item.title)}"></div><div class="field wide-action"><label>Texto</label><textarea rows="2" data-portal-purpose="${index}" data-portal-purpose-field="body">${esc(item.body)}</textarea></div></fieldset>`).join("")}
    </div></details>
    <details class="data-card"><summary><strong>Biblioteca e coleções</strong></summary><div class="filter-grid portal-edit-grid">
      ${portalField(content,"books.eyebrow","Chamada curta")}${portalField(content,"books.title","Título da biblioteca",{wide:true})}${portalField(content,"books.intro","Apresentação",{textarea:true,wide:true})}
      ${portalField(content,"books.primary_title","Coleção principal")}${portalField(content,"books.primary_subtitle","Subtítulo principal")}${portalField(content,"books.complementary_title","Coleção complementar")}${portalField(content,"books.complementary_subtitle","Subtítulo complementar")}${portalField(content,"books.details_label","Texto de abrir descrição")}
    </div></details>
    <details class="data-card"><summary><strong>Convite para a plataforma e rodapé</strong></summary><div class="filter-grid portal-edit-grid">
      ${portalField(content,"platform.eyebrow","Chamada curta")}${portalField(content,"platform.title","Título",{wide:true})}${portalField(content,"platform.body","Texto",{textarea:true,wide:true})}${portalField(content,"platform.button","Botão")}
      ${portalField(content,"footer.disclaimer","Aviso do rodapé",{textarea:true,wide:true})}${portalField(content,"footer.platform","Link da plataforma")}
    </div></details>
    <div class="portal-sticky-action"><span>Última alteração: ${dateTime(payload.updated_at)} por ${esc(payload.updated_by||"sistema")}</span><button class="button primary" type="submit">Salvar textos da página</button></div>
  </form>`;
}

function portalCoverUrl(book){return book.cover_media_id?`${BASE_PATH}/portal-media/${encodeURIComponent(book.cover_media_id)}`:`${BASE_PATH}${book.fallback_cover_path||"/portal-assets/books/formacao-investidor-fundamentos.webp"}?v=1.23.2-r1`;}
function portalBookForm(book,index,total){
  const links=[...(book.sales_links||[])];while(links.length<3)links.push({label:"",url:""});
  const isNew=!book.id;
  return `<details class="access-level-card portal-book-card" data-portal-book-card="${esc(book.id||"new")}" ${isNew?"open":""}><summary><span><strong>${esc(book.title||"Adicionar novo livro")}</strong><small>${isNew?"Cadastre a obra, a capa e os links de venda":`${book.collection==="primary"?"Coleção principal":"Obra complementar"} • ${book.is_published?"Publicado":"Oculto"}`}</small></span>${isNew?"":`<img class="portal-book-thumb" src="${esc(portalCoverUrl(book))}" alt="">`}</summary><form class="portal-book-form filter-grid" data-portal-book-form="${esc(book.id||"")}">
    <div class="field"><label>Título</label><input name="title" required maxlength="255" value="${esc(book.title||"")}"></div><div class="field"><label>Identificador</label><input name="slug" required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" value="${esc(book.slug||"")}" placeholder="nome-do-livro"></div>
    <div class="field"><label>Coleção</label><select name="collection"><option value="primary" ${book.collection==="primary"?"selected":""}>Coleção principal</option><option value="complementary" ${book.collection!=="primary"?"selected":""}>Obras complementares</option></select></div><div class="field"><label>Chamada curta</label><input name="kicker" maxlength="180" value="${esc(book.kicker||"")}"></div>
    <div class="field wide-action"><label>Resumo exibido</label><textarea name="summary" rows="2" maxlength="1500">${esc(book.summary||"")}</textarea></div><div class="field wide-action"><label>Descrição completa</label><textarea name="description" rows="3" maxlength="5000">${esc(book.description||"")}</textarea></div>
    <div class="field"><label>Descrição acessível da capa</label><input name="alt_text" required maxlength="500" value="${esc(book.alt_text||"")}"></div><div class="field"><label>Nova capa (PNG, JPG ou WebP; até 4 MB)</label><input name="cover_file" type="file" accept="image/png,image/jpeg,image/webp"></div>
    <div class="field"><label>Destaque no topo</label><select name="hero_position"><option value="">Não destacar</option>${[1,2,3].map(value=>`<option value="${value}" ${Number(book.hero_position)===value?"selected":""}>Posição ${value}</option>`).join("")}</select></div><label class="check portal-book-published"><input name="is_published" type="checkbox" ${book.is_published!==false?"checked":""}> Livro visível na página</label>
    <fieldset class="portal-sales-fieldset wide-action"><legend>Links de venda — até três</legend>${links.map((link,position)=>`<div class="portal-sales-row"><div class="field"><label>Descrição ${position+1}</label><input name="sales_label_${position}" maxlength="100" value="${esc(link.label||"")}" placeholder="Ex.: Comprar na Amazon"></div><div class="field"><label>Link HTTPS ${position+1}</label><input name="sales_url_${position}" type="url" value="${esc(link.url||"")}" placeholder="https://..."></div></div>`).join("")}</fieldset>
    <div class="portal-book-actions wide-action">${isNew?"":`<button type="button" class="button ghost" data-portal-book-move="up" data-portal-book-id="${esc(book.id)}" ${index===0?"disabled":""}>Subir</button><button type="button" class="button ghost" data-portal-book-move="down" data-portal-book-id="${esc(book.id)}" ${index===total-1?"disabled":""}>Descer</button><button type="button" class="button ghost danger" data-portal-book-delete="${esc(book.id)}">Excluir</button>`}<button class="button primary" type="submit">${isNew?"Adicionar livro":"Salvar livro"}</button></div>
  </form></details>`;
}

async function loadAdminPortal(root,context){
  const payload=await api("/admin/portal",{requestKey:"admin-portal",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:context.force});
  if(!adminPanelIsCurrent(root,context))return;
  state.portalAdmin=payload;
  const books=payload.books||[];
  root.innerHTML=`<div class="notice info"><strong>Publicação segura:</strong> as alterações salvas aparecem na página inicial sem substituir a plataforma. Se o banco ficar indisponível, a versão estática atual permanece como reserva.</div>${sectionCard("Textos da página inicial",portalPageEditor(payload),"Edite os campos e salve ao final")}${sectionCard("Livros publicados e futuros",`<div class="portal-book-list">${books.map((book,index)=>portalBookForm(book,index,books.length)).join("")}</div>${portalBookForm({collection:"complementary",is_published:true,sales_links:[]},books.length,books.length+1)}`,`${books.length} livro(s) cadastrado(s); capas aceitas em PNG, JPG e WebP`)}`;
}

function setPortalPageValue(target,path,value){const parts=path.split(".");let cursor=target;parts.slice(0,-1).forEach(part=>cursor=cursor[part]);cursor[parts.at(-1)]=value;}
async function savePortalPage(form){
  const content=JSON.parse(JSON.stringify(state.portalAdmin.content||{}));
  form.querySelectorAll("[data-portal-page-field]").forEach(input=>setPortalPageValue(content,input.dataset.portalPageField,input.dataset.portalList?input.value.split(/\r?\n/).map(value=>value.trim()).filter(Boolean):input.value));
  form.querySelectorAll("[data-portal-purpose]").forEach(input=>{content.purpose.items[Number(input.dataset.portalPurpose)][input.dataset.portalPurposeField]=input.value;});
  const button=form.querySelector('button[type="submit"]');button.disabled=true;
  try{await api("/admin/portal/page",{method:"PUT",body:JSON.stringify({patch:content,expected_revision:Number(form.dataset.portalRevision)})});toast("Textos da página inicial atualizados.","success");await loadAdmin();}
  catch(error){toast(error.message,"error");button.disabled=false;}
}

function readPortalFile(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(new Error("Não foi possível ler a imagem selecionada."));reader.readAsDataURL(file);});}
async function portalBookPayload(form){
  const values={title:form.elements.title.value,slug:form.elements.slug.value.trim().toLowerCase(),collection:form.elements.collection.value,kicker:form.elements.kicker.value,summary:form.elements.summary.value,description:form.elements.description.value,alt_text:form.elements.alt_text.value,hero_position:form.elements.hero_position.value||null,is_published:form.elements.is_published.checked};
  const file=form.elements.cover_file.files?.[0];if(file){if(file.size>4*1024*1024)throw new Error("A capa deve ter no máximo 4 MB.");const media=await api("/admin/portal/media",{method:"POST",body:JSON.stringify({filename:file.name,data_url:await readPortalFile(file)})});values.cover_media_id=media.id;}
  const sales_links=[];for(let index=0;index<3;index+=1){const label=form.elements[`sales_label_${index}`].value.trim(),url=form.elements[`sales_url_${index}`].value.trim();if(label||url){if(!label||!url)throw new Error(`Preencha a descrição e o link de venda ${index+1}.`);sales_links.push({label,url});}}
  return {values,sales_links};
}

async function savePortalBook(form){
  const button=form.querySelector('button[type="submit"]');button.disabled=true;
  try{const payload=await portalBookPayload(form),id=form.dataset.portalBookForm;await api(id?`/admin/portal/books/${encodeURIComponent(id)}`:"/admin/portal/books",{method:id?"PUT":"POST",body:JSON.stringify(payload)});toast(id?"Livro atualizado.":"Livro adicionado.","success");await loadAdmin();}
  catch(error){toast(error.message,"error");button.disabled=false;}
}

async function deletePortalBook(id){if(!window.confirm("Excluir este livro e seus links da página inicial? A capa será removida apenas se nenhum outro livro a utilizar."))return;try{await api(`/admin/portal/books/${encodeURIComponent(id)}`,{method:"DELETE"});toast("Livro excluído.","success");await loadAdmin();}catch(error){toast(error.message,"error");}}
async function movePortalBook(id,direction){const books=[...(state.portalAdmin?.books||[])],index=books.findIndex(book=>book.id===id),target=index+(direction==="up"?-1:1);if(index<0||target<0||target>=books.length)return;[books[index],books[target]]=[books[target],books[index]];try{await api("/admin/portal/books/order",{method:"PUT",body:JSON.stringify({ordered_ids:books.map(book=>book.id)})});toast("Ordem dos livros atualizada.","success");await loadAdmin();}catch(error){toast(error.message,"error");}}

async function loadAdmin(force=false) {
  const panelStarted=performance.now();
  const root=$("#admin-tab-content"),panelKey=state.tabs.admin;
  const context={panelKey,navigationSerial:state.navigationSerial,requestSerial:++state.adminRequestSerial,force:Boolean(force)};
  const samePanel=root.dataset.panelKey===panelKey&&root.childElementCount>0;root.dataset.panelKey=panelKey;
  let panelSucceeded=false;
  if(!samePanel)root.innerHTML=loadingCards(6);else root.classList.add("panel-refreshing");
  try {
    if(panelKey==="portal")await loadAdminPortal(root,context);
    else if(panelKey==="levels")await loadAccessLevels(root,context);
    else if(panelKey==="users")await loadAdminUsers(root,context);
    else if(panelKey==="analysis-settings"){await loadFeature("analysis");await loadAdminAnalysisSettings(root,context);}
    else if(panelKey==="data")await loadAdminUpdates(root,context);
    else if(panelKey==="quality")await loadAdminQuality(root,context);
    else if(panelKey==="jobs")await loadAdminJobs(root,context);
    else if(panelKey==="operations")await loadAdminOperations(root,context);
    else {
      const [health,db,counts]=await Promise.all([api("/health",{requestKey:"admin-health",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:context.force}),api("/health/db",{requestKey:"admin-health-db",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:context.force}),api("/debug/db-counts",{requestKey:"admin-db-counts",cacheTtlMs:ADMIN_NAVIGATION_CACHE_TTL_MS,bypassCache:context.force})]);
      if(!adminPanelIsCurrent(root,context))return;
      root.innerHTML=`<div class="metric-grid">${metricCard("Aplicação",health.status==="ok"?"Operacional":"Atenção",`Versão ${health.version}`)}${metricCard("Banco de dados",db.status==="ok"?"Conectado":"Indisponível",db.database||"")}${metricCard("Hospedagem","Oracle Cloud",health.environment||"Produção")}${metricCard("Domínio","HTTPS ativo","Conexão segura")}</div>${sectionCard("Registros principais",`<div class="detail-list">${Object.entries(counts).map(([key,value])=>`<div><span>${esc(key.replaceAll("_"," "))}</span><strong>${number(value,0)}</strong></div>`).join("")}</div>`,`Consulta somente leitura`)}`;
    }
    panelSucceeded=true;markPanelFresh("admin",panelKey);
  } catch(error) { if(error.name!=="AbortError"&&adminPanelIsCurrent(root,context))root.innerHTML=errorState(error); }
  finally {if(adminPanelIsCurrent(root,context)){root.classList.remove("panel-refreshing");reportPanelPerformance("admin",panelStarted,{success:panelSucceeded,cacheState:samePanel?(panelSucceeded?"warm":"stale"):"cold"});}}
}

async function saveAccessLevel(form){
  const permissions={};form.querySelectorAll("[data-level-permission]").forEach(input=>permissions[input.dataset.levelPermission]=input.checked);
  const limits={};form.querySelectorAll("[data-level-limit]").forEach(input=>limits[input.dataset.levelLimit]=Number(input.value));
  const payload={name:form.elements.name?.value,description:form.elements.description?.value||null,is_active:Boolean(form.elements.is_active?.checked),permissions,limits};
  const button=form.querySelector('button[type="submit"]');if(button){button.disabled=true;button.textContent="Salvando…";}
  try{const result=await api(`/access/levels/${encodeURIComponent(form.dataset.accessLevelForm)}`,{method:"PUT",body:JSON.stringify(payload)});toast(`Nível atualizado para ${result.member_count||0} usuário(s).`,"success");await loadAdmin();}
  catch(error){toast(error.message,"error");if(button){button.disabled=false;button.textContent="Salvar regras deste nível";}}
}

async function createAccessLevel(form){
  const values=Object.fromEntries(new FormData(form));
  try{await api("/access/levels",{method:"POST",body:JSON.stringify({slug:values.slug,name:values.name,description:values.description||null,is_active:true,permissions:{},limits:{}})});toast("Novo nível criado. Agora configure suas permissões.","success");await loadAdmin();}
  catch(error){toast(error.message,"error");}
}

async function saveUserLevel(email){
  const row=$(`[data-user-row="${CSS.escape(email)}"]`);if(!row)return;
  const level=row.querySelector("[data-user-level]")?.value,status=row.querySelector("[data-user-status]")?.value;
  const button=row.querySelector("[data-save-user-level]");button.disabled=true;
  try{
    if(level&&level!=="legacy"&&level!==row.dataset.currentLevel)await api(`/access/users/${encodeURIComponent(email)}/level`,{method:"PUT",body:JSON.stringify({level_slug:level,clear_overrides:true})});
    if(status&&status!==row.dataset.currentStatus)await api(`/access/users/${encodeURIComponent(email)}`,{method:"PUT",body:JSON.stringify({status})});
    toast("Usuário atualizado.","success");await loadAdmin();
  }catch(error){toast(error.message,"error");button.disabled=false;}
}

async function bulkAssignAccessLevel(){
  const emails=$$("[data-user-select]:checked").map(input=>input.dataset.userSelect),level=$("#bulk-access-level")?.value;
  if(!emails.length){toast("Selecione ao menos um usuário desta página.","error");return;}
  if(!window.confirm(`Atribuir o nível selecionado a ${emails.length} usuário(s)? Ajustes individuais anteriores serão removidos.`))return;
  try{const result=await api("/access/users/level/bulk",{method:"PUT",body:JSON.stringify({emails,level_slug:level,clear_overrides:true})});toast(`${result.updated_count||0} usuário(s) atualizado(s).`,"success");await loadAdmin();}
  catch(error){toast(error.message,"error");}
}

async function clearUserOverrides(email){
  if(!window.confirm("Remover os ajustes individuais e voltar a herdar somente as regras do nível?"))return;
  try{await api(`/access/users/${encodeURIComponent(email)}/overrides`,{method:"DELETE"});toast("Ajustes individuais removidos.","success");await loadAdmin();}
  catch(error){toast(error.message,"error");}
}

async function runAlertMonitorNow(button){
  button.disabled=true;const root=$("#alert-monitor-result");
  try{const result=await api("/alerts/monitor/run",{method:"POST"});if(root){root.classList.remove("hidden");root.textContent=`Verificação concluída: ${result.checked||0} alerta(s), ${result.triggered||0} disparado(s), ${result.delivered||0} e-mail(s) entregue(s) e ${result.quote_failures||0} cotação(ões) indisponível(is).`;}toast("Monitor de alertas executado.","success");}
  catch(error){toast(error.message,"error");}
  finally{button.disabled=false;}
}

async function retryAdminJob(button){
  button.disabled=true;
  try{await api(`/admin/jobs/${encodeURIComponent(button.dataset.retryAdminJob)}/retry`,{method:"POST"});toast("Trabalho reenfileirado.","success");scheduleNavigationTask(()=>loadAdmin(true),1200);}
  catch(error){toast(error.message,"error");button.disabled=false;}
}

function applyAdminUserFilters(form){
  const values=Object.fromEntries(new FormData(form));state.adminUsersQuery=String(values.q||"").trim();state.adminUsersLevel=values.level||"";state.adminUsersStatus=values.status||"";state.adminUsersOffset=0;loadAdmin();
}

function changeAdminUsersPage(direction){state.adminUsersOffset=Math.max(0,state.adminUsersOffset+(direction==="next"?100:-100));loadAdmin();}

async function syncMarketCatalog(assetType, includeTechnicals) {
  const status=$("#market-sync-status");
  const buttons=$$("[data-market-sync]");
  buttons.forEach(button=>button.disabled=true);
  if(status){status.classList.remove("hidden");status.textContent="Enviando a atualização para a fila…";}
  try {
    const result=await api("/data/sync-market",{method:"POST",body:JSON.stringify({asset_type:assetType,include_technicals:includeTechnicals})});
    const jobId=result.job?.id;
    if(!jobId)throw new Error("A fila não confirmou a solicitação.");
    toast(result.scheduled?"Atualização iniciada em segundo plano.":"Esta atualização já estava na fila.","success");
    for(let attempt=0;attempt<300;attempt++){
      const job=await api(`/data/jobs/${encodeURIComponent(jobId)}`,{bypassCache:true});
      if(status){
        const progress=job.progress_total?` ${number(job.progress_current||0,0)} de ${number(job.progress_total,0)}.`:"";
        status.textContent=`${jobStatusLabel(job.status)}.${progress} ${job.message||""}`.trim();
      }
      if(job.status==="succeeded"){
        const count=job.result?.catalog_count;
        state.analysisResultCache.clear();
        toast(nullable(count)?"Catálogo atualizado.":`Catálogo atualizado: ${number(count,0)} ativo(s).`,"success");
        await loadAdmin(true);
        return;
      }
      if(["failed","cancelled"].includes(job.status))throw new Error(job.last_error_message||job.last_error_code||"A atualização não foi concluída.");
      await new Promise(resolve=>setTimeout(resolve,3000));
    }
    if(status)status.textContent="A atualização continua em segundo plano. Acompanhe pela aba Trabalhos.";
    toast("A atualização continua em segundo plano.","success");
    buttons.forEach(button=>button.disabled=false);
  } catch(error) {
    if(status){status.textContent=error.message;status.classList.remove("hidden");}
    toast(error.message,"error");
    buttons.forEach(button=>button.disabled=false);
  }
}

async function saveUserAccess(email) {
  const row=$(`[data-user-row="${CSS.escape(email)}"]`);
  if(!row)return;
  const value=name=>row.querySelector(`[data-user-field="${name}"]`);
  const canRun=Boolean(value("can_run_backtests")?.checked);
  const canViewFinances=Boolean(value("can_view_finances")?.checked);
  const canWriteFinances=Boolean(value("can_write_finances")?.checked);
  const payload={
    status:value("status")?.value,
    can_use_fdi_analysis:Boolean(value("can_use_fdi_analysis")?.checked),
    can_use_alb_analysis:Boolean(value("can_use_alb_analysis")?.checked),
    can_use_graham_valuation:Boolean(value("can_use_graham_valuation")?.checked),
    can_use_dividend_ceiling:Boolean(value("can_use_dividend_ceiling")?.checked),
    can_use_relative_valuation:Boolean(value("can_use_relative_valuation")?.checked),
    can_use_economic_valuation:Boolean(value("can_use_economic_valuation")?.checked),
    can_view_finances:canViewFinances||canWriteFinances,
    can_write_finances:canWriteFinances,
    can_run_backtests:canRun,
    can_view_backtests:canRun,
    backtest_asset_limit:canRun?Number(value("backtest_asset_limit")?.value||1):0,
    backtest_daily_limit:canRun?Number(value("backtest_daily_limit")?.value||1):0,
    backtest_strategy_limit:canRun?Number(value("backtest_strategy_limit")?.value||1):0,
    backtest_cooldown_seconds:60,
  };
  try{await api(`/access/users/${encodeURIComponent(email)}`,{method:"PUT",body:JSON.stringify(payload)});toast("Permissões atualizadas.","success");loadAdmin();}
  catch(error){toast(error.message,"error");}
}

  window.FDIFeatures=window.FDIFeatures||{};
  window.FDIFeatures.admin={
    loadAdmin,
    renderAdminAnalysisSettings,
    saveAdminPreset,
    resetAdminPreset,
    saveAdminColumns,
    resetAdminColumns,
    moveAdminColumn,
    deletePortalBook,
    movePortalBook,
    savePortalPage,
    savePortalBook,
    saveAccessLevel,
    createAccessLevel,
    saveUserLevel,
    bulkAssignAccessLevel,
    clearUserOverrides,
    runAlertMonitorNow,
    retryAdminJob,
    applyAdminUserFilters,
    changeAdminUsersPage,
    syncMarketCatalog,
    saveUserAccess
  };
})();
