"use strict";

// Carregado sob demanda e preservado pela V1.23.8 R1. O módulo mantém as mesmas
// funções e regras usadas antes no arquivo principal.
(()=>{
async function loadPortfolios() {
  const panelStarted=performance.now(),hadCached=Boolean(state.portfolios.length),navigationSerial=state.navigationSerial,requestSerial=++state.portfolioListRequestSerial;
  const root=$("#portfolio-tab-content"),expectedPanelKey=`${state.portfolioId||"none"}:${state.tabs.portfolio}`;
  if(root.dataset.panelKey!==expectedPanelKey||!root.childElementCount)root.innerHTML=loadingCards(5);
  else root.classList.add("panel-refreshing");
  try {
    const portfolios=await api("/portfolios",{requestKey:"portfolios",cacheTtlMs:120000});
    if(requestSerial!==state.portfolioListRequestSerial||!navigationIsCurrent(navigationSerial,"portfolio"))return;
    state.portfolios=portfolios;
    if (!state.portfolios.length) {
      state.portfolioId=null;$("#portfolio-selector-wrap").innerHTML="";
      root.dataset.panelKey=`none:${state.tabs.portfolio}`;
      if(state.tabs.portfolio==="alerts"){await renderAlerts(root);markPanelFresh("portfolio",state.tabs.portfolio);return;}
      if(state.tabs.portfolio==="news"){await renderNewsWorkspace(root);markPanelFresh("portfolio",state.tabs.portfolio);return;}
      root.innerHTML='<div class="data-card empty-state"><strong>Você ainda não criou uma carteira</strong>A criação estará disponível aqui para contas com permissão de edição.</div>';markPanelFresh("portfolio",state.tabs.portfolio);return;
    }
    if (!state.portfolioId || !state.portfolios.some(p=>p.id===state.portfolioId)) state.portfolioId=state.portfolios[0].id;
    $("#portfolio-selector-wrap").innerHTML=`<select id="portfolio-selector" class="button secondary">${state.portfolios.map(p=>`<option value="${esc(p.id)}" ${p.id===state.portfolioId?"selected":""}>${esc(p.name)}</option>`).join("")}</select>`;
    await renderPortfolioTab();
    if(requestSerial===state.portfolioListRequestSerial&&navigationIsCurrent(navigationSerial,"portfolio")){markPanelFresh("portfolio",state.tabs.portfolio);reportPanelPerformance("portfolio",panelStarted,{cacheState:hadCached?"warm":"cold"});}
  } catch(error) { if(error.name!=="AbortError"&&requestSerial===state.portfolioListRequestSerial&&navigationIsCurrent(navigationSerial,"portfolio")){root.innerHTML=errorState(error,"portfolio");reportPanelPerformance("portfolio",panelStarted,{success:false,cacheState:hadCached?"stale":"cold"});} }
  finally {if(requestSerial===state.portfolioListRequestSerial&&navigationIsCurrent(navigationSerial,"portfolio"))root.classList.remove("panel-refreshing");}
}

function portfolioPanelIsCurrent(root,panelKey,requestSerial,navigationSerial){
  return root?.dataset.panelKey===panelKey&&requestSerial===state.portfolioRequestSerial&&navigationIsCurrent(navigationSerial,"portfolio","portfolio",state.tabs.portfolio);
}

function allocationDonut(items) {
  const rows=(items||[]).filter(item=>Number(item.value)>0);
  if(!rows.length)return '<div class="empty-state"><strong>Composição ainda vazia</strong>Cadastre posições ou investimentos para visualizar a distribuição.</div>';
  const colors=["#0b5d4b","#c79b3b","#4f7cac","#9b5de5","#e07a5f","#2a9d8f","#6c757d","#f4a261"];
  let cursor=0;const stops=rows.map((item,index)=>{const start=cursor;cursor+=Number(item.weight_pct||0);return `${colors[index%colors.length]} ${start}% ${cursor}%`;});
  return `<div class="allocation-visual"><div class="allocation-donut" style="background:conic-gradient(${stops.join(",")})"><span>${money(rows.reduce((sum,item)=>sum+Number(item.value||0),0))}</span></div><div class="allocation-legend">${rows.map((item,index)=>`<div><i class="legend-dot" style="background:${colors[index%colors.length]}"></i><span>${esc(item.label)}</span><strong>${pct(item.weight_pct)}</strong></div>`).join("")}</div></div>`;
}

const allocationTypeColors={
  stock:"#0b5d4b",fii:"#c79b3b",etf:"#4f7cac",bdr:"#8b5fbf",future:"#e07a5f",
  fixed_income:"#2a9d8f",crypto:"#5b6ee1",funds:"#7a8b3a",pension:"#b56576",cash:"#6c757d",other:"#9a8f82",
};
const allocationFallbackColors=["#0b5d4b","#c79b3b","#4f7cac","#8b5fbf","#e07a5f","#2a9d8f","#5b6ee1","#7a8b3a","#b56576","#6c757d"];

function allocationPolar(cx,cy,radius,angle){return [cx+radius*Math.cos(angle),cy+radius*Math.sin(angle)];}

function allocationArcPath(start,end,innerRadius,outerRadius,cx=160,cy=160){
  const span=Math.max(0,end-start),full=span>=Math.PI*2-.000001;
  if(full){
    return `M ${cx} ${cy-outerRadius} A ${outerRadius} ${outerRadius} 0 1 1 ${cx} ${cy+outerRadius} A ${outerRadius} ${outerRadius} 0 1 1 ${cx} ${cy-outerRadius} L ${cx} ${cy-innerRadius} A ${innerRadius} ${innerRadius} 0 1 0 ${cx} ${cy+innerRadius} A ${innerRadius} ${innerRadius} 0 1 0 ${cx} ${cy-innerRadius} Z`;
  }
  const [outerStartX,outerStartY]=allocationPolar(cx,cy,outerRadius,start),[outerEndX,outerEndY]=allocationPolar(cx,cy,outerRadius,end);
  const [innerEndX,innerEndY]=allocationPolar(cx,cy,innerRadius,end),[innerStartX,innerStartY]=allocationPolar(cx,cy,innerRadius,start);
  const large=span>Math.PI?1:0;
  return `M ${outerStartX.toFixed(3)} ${outerStartY.toFixed(3)} A ${outerRadius} ${outerRadius} 0 ${large} 1 ${outerEndX.toFixed(3)} ${outerEndY.toFixed(3)} L ${innerEndX.toFixed(3)} ${innerEndY.toFixed(3)} A ${innerRadius} ${innerRadius} 0 ${large} 0 ${innerStartX.toFixed(3)} ${innerStartY.toFixed(3)} Z`;
}

function allocationChildColor(typeIndex,childIndex){
  const hues=[160,42,210,274,18,174,231,78,342,205,28],hue=hues[typeIndex%hues.length];
  const lightness=[42,53,63,72][childIndex%4];
  return `hsl(${hue} 48% ${lightness}%)`;
}

function allocationDetailPanel(hierarchy){
  const selected=(hierarchy?.types||[]).find(item=>item.id===state.portfolioAllocationType);
  if(!selected)return "";
  const rows=(selected.breakdown||[]).filter(item=>Number(item.value)>0);
  let cursor=-Math.PI/2;
  const paths=rows.map((item,index)=>{
    const span=Math.PI*2*(Number(item.within_type_weight_pct||0)/100),start=cursor,end=cursor+span;cursor=end;
    const color=allocationChildColor((hierarchy.types||[]).indexOf(selected),index);
    return `<path d="${allocationArcPath(start,end,72,126)}" fill="${color}" tabindex="0"><title>${esc(item.label)}: ${money(item.value)} • ${pct(item.within_type_weight_pct)} de ${esc(selected.label)}</title></path>`;
  }).join("");
  const legend=rows.map((item,index)=>`<div><i class="legend-dot" style="background:${allocationChildColor((hierarchy.types||[]).indexOf(selected),index)}"></i><span>${esc(item.label)}${item.sector&&item.segment?`<small>${esc(item.sector)} • ${esc(item.segment)}</small>`:""}</span><strong>${pct(item.within_type_weight_pct)}</strong></div>`).join("");
  return `<section class="data-card allocation-detail-card" aria-live="polite"><div class="card-heading"><div><p class="eyebrow">Detalhamento de ${esc(selected.label)}</p><h3>Setores e segmentos</h3><small>${pct(selected.weight_pct)} do patrimônio conhecido</small></div><button type="button" class="icon-button" data-allocation-close aria-label="Fechar detalhamento">×</button></div><div class="allocation-visual allocation-detail-visual"><div class="allocation-svg-wrap"><svg class="allocation-svg allocation-detail-svg" viewBox="0 0 320 320" role="img" aria-label="Distribuição por setor ou segmento de ${esc(selected.label)}">${paths}<circle cx="160" cy="160" r="66" class="allocation-center"/><text x="160" y="155" class="allocation-center-label">${esc(selected.label)}</text><text x="160" y="176" class="allocation-center-value">${esc(money(selected.value))}</text></svg></div><div class="allocation-legend">${legend}</div></div></section>`;
}

function hierarchicalAllocationDonut(hierarchy,fallbackItems=[]){
  const types=(hierarchy?.types||[]).filter(item=>Number(item.value)>0);
  if(!types.length)return allocationDonut(fallbackItems);
  let cursor=-Math.PI/2;
  const inner=[],outer=[],legend=[];
  types.forEach((type,typeIndex)=>{
    const typeSpan=Math.PI*2*(Number(type.weight_pct||0)/100),typeStart=cursor,typeEnd=cursor+typeSpan;
    const color=allocationTypeColors[type.id]||allocationFallbackColors[typeIndex%allocationFallbackColors.length];
    inner.push(`<path class="allocation-type-slice ${state.portfolioAllocationType===type.id?"selected":""}" d="${allocationArcPath(typeStart,typeEnd,55,91)}" fill="${color}" role="button" tabindex="0" data-allocation-type="${esc(type.id)}"><title>${esc(type.label)}: ${money(type.value)} • ${pct(type.weight_pct)}</title></path>`);
    let childCursor=typeStart;
    (type.breakdown||[]).filter(item=>Number(item.value)>0).forEach((item,childIndex)=>{
      const span=Math.PI*2*(Number(item.global_weight_pct||0)/100),start=childCursor,end=Math.min(typeEnd,childCursor+span);childCursor=end;
      outer.push(`<path class="allocation-breakdown-slice" d="${allocationArcPath(start,end,98,142)}" fill="${allocationChildColor(typeIndex,childIndex)}" tabindex="0"><title>${esc(type.label)} › ${esc(item.label)}: ${money(item.value)} • ${pct(item.global_weight_pct)} do total • ${pct(item.within_type_weight_pct)} de ${esc(type.label)}</title></path>`);
    });
    legend.push(`<button type="button" class="allocation-legend-row ${state.portfolioAllocationType===type.id?"selected":""}" data-allocation-type="${esc(type.id)}"><i class="legend-dot" style="background:${color}"></i><span>${esc(type.label)}<small>Clique para detalhar setores e segmentos</small></span><strong>${pct(type.weight_pct)}</strong></button>`);
    cursor=typeEnd;
  });
  const partial=hierarchy.allocation_complete===false?`<div class="notice warning allocation-partial"><strong>Composição parcial.</strong> ${number(hierarchy.missing_price_positions||0,0)} posição(ões) sem cotação não foi(foram) tratada(s) como zero.</div>`:"";
  return `<div class="allocation-hierarchy">${partial}<div class="allocation-visual"><div class="allocation-svg-wrap"><svg class="allocation-svg" viewBox="0 0 320 320" role="img" aria-label="Alocação da carteira: tipos no anel interno e setores ou segmentos no anel externo">${outer.join("")}${inner.join("")}<circle cx="160" cy="160" r="49" class="allocation-center"/><text x="160" y="154" class="allocation-center-label">Patrimônio conhecido</text><text x="160" y="176" class="allocation-center-value">${esc(money(hierarchy.known_total_value))}</text></svg><small class="allocation-ring-help">Interno: tipo • externo: setor ou segmento</small></div><div class="allocation-legend">${legend.join("")}</div></div><div id="allocation-detail-panel">${allocationDetailPanel(hierarchy)}</div></div>`;
}

function showPortfolioAllocationType(type){
  state.portfolioAllocationType=type||null;
  const panel=$("#allocation-detail-panel");
  if(panel)panel.innerHTML=allocationDetailPanel(state.portfolioAllocationHierarchy);
  $$("[data-allocation-type]").forEach(node=>node.classList.toggle("selected",node.dataset.allocationType===state.portfolioAllocationType));
  panel?.scrollIntoView({behavior:"smooth",block:"nearest"});
}

function newsCacheStatus(cache) {
  const labels={not_requested:"Aguardando primeira atualização",pending:"Na fila",queued:"Na fila",running:"Atualizando",completed:"Atualizado",failed:"Falha na última tentativa"};
  return labels[cache?.status]||cache?.status||"Aguardando";
}

function newsHeadline(item,index,{recommendation=false}={}) {
  const institution=recommendation?(item.institution||item.bank_group_label):null;
  const metadata=[institution,item.source,item.published_at?dateTime(item.published_at):null].filter(Boolean);
  const tickers=(item.mentioned_tickers||[]).map(ticker=>`<span class="pill">${esc(ticker)}</span>`).join("");
  return `<a class="headline" href="${esc(safeExternalUrl(item.url))}" target="_blank" rel="noopener noreferrer"><span class="headline-number">${index+1}</span><span><strong>${esc(item.title)}</strong><small>${esc(metadata.join(" • "))}</small>${tickers?`<span class="headline-tags">${tickers}</span>`:""}</span><small>Abrir fonte</small></a>`;
}

function queueNewsPanelReload(cache) {
  clearTimeout(state.newsRefreshTimer);
  state.newsRefreshTimer=null;
  if(!["pending","queued","running"].includes(cache?.status))return;
  const navigationSerial=state.navigationSerial,portfolioId=state.portfolioId,newsMode=state.portfolioNewsMode;
  state.newsRefreshTimer=setTimeout(()=>{
    state.newsRefreshTimer=null;
    if(navigationIsCurrent(navigationSerial,"portfolio","portfolio","news")&&state.portfolioId===portfolioId&&state.portfolioNewsMode===newsMode)renderPortfolioTab({forceNews:true});
  },4500);
}

async function renderPortfolioNews(root,{force=false}={}) {
  const panelKey=root.dataset.panelKey;
  if(!state.portfolioId) {
    root.innerHTML='<div class="data-card empty-state"><strong>Nenhuma carteira cadastrada</strong>Crie uma carteira para receber notícias relacionadas aos ativos. As notícias de recomendações continuam disponíveis acima.</div>';
    return;
  }
  const cache=await api(`/insights/news/cache/portfolios/${state.portfolioId}`,{requestKey:"portfolio-news",cacheTtlMs:NEWS_NAVIGATION_CACHE_TTL_MS,bypassCache:force});
  if(root.dataset.panelKey!==panelKey||state.view!=="portfolio"||state.tabs.portfolio!=="news")return;
  const data=cache.data||{},groups=data.assets||data.items||[];
  const update=`<div class="update-panel"><div class="update-summary"><span><strong>Notícias dos ativos da carteira</strong><small>${cache.finished_at?`Última atualização: ${dateTime(cache.finished_at)}`:"A atualização diária será iniciada no primeiro acesso autenticado."}</small></span><span><span class="pill ${cache.status==="failed"?"danger":""}">${esc(newsCacheStatus(cache))}</span><button class="button secondary compact" data-portfolio-news-refresh="${esc(state.portfolioId)}" ${["pending","queued","running"].includes(cache.status)?"disabled":""}>Atualizar novamente hoje</button></span></div>${cache.error?`<div class="notice danger">A última tentativa não foi concluída. Os dados anteriores foram preservados.</div>`:""}</div>`;
  const content=groups.length?groups.map(group=>`<div class="card-section"><div class="card-heading"><h3>${esc(group.ticker||group.label||"Ativo")}</h3><small>${(group.items||group.news||[]).length} notícia(s)</small></div><div class="headline-list">${(group.items||group.news||[]).map((item,index)=>newsHeadline(item,index)).join("")}</div></div>`).join(""):'<div class="empty-state"><strong>Notícias sendo preparadas</strong>O carregamento ocorre em segundo plano e a página continua disponível para outras tarefas.</div>';
  root.innerHTML=update+sectionCard("Notícias da carteira",content,"Até 3 notícias relevantes por ativo, sem bloquear a navegação");
  queueNewsPanelReload(cache);
}

async function renderRecommendationNews(root,{force=false}={}) {
  const panelKey=root.dataset.panelKey;
  const category=state.recommendationCategory;
  const cache=await api(`/insights/news/cache/recommendations?category=${encodeURIComponent(category)}`,{requestKey:"portfolio-news",cacheTtlMs:NEWS_NAVIGATION_CACHE_TTL_MS,bypassCache:force});
  if(root.dataset.panelKey!==panelKey||state.view!=="portfolio"||state.tabs.portfolio!=="news"||category!==state.recommendationCategory)return;
  const data=cache.data||{},items=data.items||[];
  const categories=[{id:"all",label:"Todas"},{id:"brazil",label:"Instituições brasileiras"},{id:"global",label:"Instituições globais"}];
  const controls=`<div class="recommendation-controls"><div class="segmented-control">${categories.map(item=>`<button class="button ${item.id===category?"primary":"ghost"} compact" data-recommendation-category="${item.id}">${item.label}</button>`).join("")}</div><button class="button secondary compact" data-recommendation-news-refresh="${esc(category)}" ${["pending","queued","running"].includes(cache.status)?"disabled":""}>Atualizar novamente hoje</button></div>`;
  const update=`<div class="update-panel"><div class="update-summary"><span><strong>Notícias de recomendações</strong><small>${cache.finished_at?`Última atualização: ${dateTime(cache.finished_at)}`:"A primeira busca do dia será feita automaticamente."}</small></span><span class="pill ${cache.status==="failed"?"danger":""}">${esc(newsCacheStatus(cache))}</span></div>${cache.error?'<div class="notice danger">A fonte não respondeu na última tentativa. Uma nova tentativa pode ser solicitada sem apagar os dados anteriores.</div>':""}</div>`;
  const content=items.length?`<div class="headline-list"><div class="headline headline-header"><span>#</span><span>Manchete • instituição • fonte • publicação</span><span>Link</span></div>${items.map((item,index)=>newsHeadline(item,index,{recommendation:true})).join("")}</div>`:'<div class="empty-state"><strong>Recomendações sendo pesquisadas</strong>As fontes públicas estão sendo consultadas em segundo plano.</div>';
  root.innerHTML=controls+update+sectionCard("Recomendações de instituições",content,"Links informativos encontrados em fontes públicas; não constituem recomendação do Formação do Investidor.");
  queueNewsPanelReload(cache);
}

async function renderNewsWorkspace(root,{force=false}={}) {
  const allowed=state.session.access.can_view_news_insights;
  if(!allowed){root.innerHTML='<div class="data-card empty-state"><strong>Notícias não liberadas para esta conta</strong>O administrador pode liberar este módulo no nível de acesso do usuário.</div>';return;}
  let content=$("#portfolio-news-content",root);
  if(!content){
    root.innerHTML=`<div class="subtabs"><button class="tab ${state.portfolioNewsMode==="portfolio"?"active":""}" data-portfolio-news-mode="portfolio">Ativos da carteira</button><button class="tab ${state.portfolioNewsMode==="recommendations"?"active":""}" data-portfolio-news-mode="recommendations">Recomendações</button></div><div id="portfolio-news-content">${loadingCards(4)}</div>`;
    content=$("#portfolio-news-content",root);
  }else{
    $$('[data-portfolio-news-mode]',root).forEach(button=>button.classList.toggle("active",button.dataset.portfolioNewsMode===state.portfolioNewsMode));
  }
  if(state.portfolioNewsMode==="recommendations")await renderRecommendationNews(content,{force});
  else await renderPortfolioNews(content,{force});
}

async function renderPortfolioTab({forceNews=false}={}) {
  const root=$("#portfolio-tab-content"), tab=state.tabs.portfolio;
  clearTimeout(state.newsRefreshTimer);state.newsRefreshTimer=null;
  const portfolioId=state.portfolioId,navigationSerial=state.navigationSerial,requestSerial=++state.portfolioRequestSerial,panelKey=`${portfolioId||"none"}:${tab}`;
  const samePanel=root.dataset.panelKey===panelKey&&root.childElementCount>0;
  root.dataset.panelKey=panelKey;
  if(!samePanel)root.innerHTML=loadingCards(5);else root.classList.add("panel-refreshing");
  try {
    if (tab==="positions") {
      const data=await api(`/portfolios/${portfolioId}`,{requestKey:"portfolio-detail",cacheTtlMs:120000});
      if(!portfolioPanelIsCurrent(root,panelKey,requestSerial,navigationSerial))return;
      const positions=data.positions||data.items||[];
      const summary=data.summary||{};
      const cards=`<div class="metric-grid summary-grid">${metricCard("Patrimônio",money(data.consolidated_summary?.total_value??data.consolidated_summary?.known_total_value??summary.market_value))}${metricCard("Posições",String(positions.length))}${metricCard("Outros investimentos",money(data.custom_summary?.current_value||0))}${metricCard("Caixa",money(data.portfolio?.cash_balance))}</div>`;
      const priceDates=positions.map(item=>item.current_price_as_of).filter(Boolean).sort();
      const priceUpdate=data.price_update||{};
      const quoteUpdate=`<div class="update-panel"><div class="update-summary"><span><strong>Cotações da carteira</strong><small>${priceDates.length?`Mais recente: ${dateTime(priceDates[priceDates.length-1])}`:"Nenhuma cotação disponível"} • ${esc(priceUpdate.source||"Yahoo Finance")}${priceUpdate.next_update_at?` • próxima ${dateTime(priceUpdate.next_update_at)}`:""}</small></span><span><span class="pill ${["failed","stale","partial"].includes(priceUpdate.status)?"warning":""}">${esc(updateStatusLabels[priceUpdate.status]||priceUpdate.status||"Sob demanda")}</span><button class="button secondary compact" data-portfolio-prices-refresh="${esc(state.portfolioId)}">Atualizar agora</button></span></div></div>`;
      const positionForm=state.session.access.can_write_portfolio?`<details class="data-card"><summary><strong>Adicionar ou atualizar posição</strong></summary><form id="portfolio-position-form" class="filter-grid" style="margin-top:16px"><div class="field"><label>Código do ativo</label><input name="ticker" required maxlength="24" placeholder="PETR4"></div><div class="field"><label>Tipo</label><select name="asset_type"><option value="stock">Ação</option><option value="fii">FII</option><option value="etf">ETF</option><option value="bdr">BDR</option><option value="future">Futuro</option><option value="crypto">Cripto</option><option value="other">Outro</option></select></div><div class="field"><label>Quantidade total</label><input name="quantity" type="number" min="0" step="0.000001" required></div><div class="field"><label>Preço médio</label><input name="average_price" type="number" min="0" step="0.000001"></div><div class="field"><label>Meta na carteira (%)</label><input name="target_weight_pct" type="number" min="0" max="100" step="0.01" value="0"></div><div class="field"><label>Categoria opcional</label><input name="classification_override" maxlength="120" placeholder="Ex.: Renda variável"></div><div class="field"><label>Setor</label><input name="sector_override" maxlength="120" placeholder="Ex.: Financeiro"></div><div class="field"><label>Segmento</label><input name="segment_override" maxlength="120" placeholder="Ex.: Bancos"></div><button class="button primary wide-action" type="submit">Salvar posição</button></form></details>`:"";
      const positionTable=marketTable(positions,[{label:"Ativo",render:r=>`<span class="ticker-cell">${esc(r.ticker)}</span>`},{label:"Quantidade",render:r=>Number(r.quantity||0).toLocaleString("pt-BR",{maximumFractionDigits:6})},{label:"Preço médio",render:r=>money(r.average_price)},{label:"Preço atual",render:r=>`${money(r.current_price)}${r.current_price_as_of?`<br><small>${dateTime(r.current_price_as_of)} • ${esc(r.price_source||"")}</small>`:""}`},{label:"Valor",render:r=>money(r.market_value??(Number(r.quantity)*Number(r.current_price)))},{label:"Peso / meta",render:r=>`${pct(r.current_weight_pct)}<br><small>meta ${pct(r.effective_target_weight_pct??r.target_weight_pct)}</small>`},{label:"Rebalanceamento",render:r=>nullable(r.rebalance_value)?"—":`<strong class="${variationClass(r.rebalance_value)}">${Number(r.rebalance_value)>=0?"Comprar":"Reduzir"} ${money(Math.abs(Number(r.rebalance_value)))}</strong>${nullable(r.rebalance_quantity)?"":`<br><small>aprox. ${number(Math.abs(Number(r.rebalance_quantity)),0)} unidade(s)</small>`}`},{label:"Setor / segmento",render:r=>`${esc(r.sector||r.classification||"—")}<br><small>${esc(r.segment||"—")}</small>`},{label:"",render:r=>state.session.access.can_write_portfolio?`<button class="button ghost compact danger" data-delete-position="${esc(r.ticker)}">Remover</button>`:""}]);
      root.innerHTML=quoteUpdate+cards+sectionCard("Posições",positionTable,"Sugestão matemática baseada nas metas informadas; não constitui recomendação de investimento.")+positionForm;
    } else if (tab==="allocation") {
      const [data,catalog]=await Promise.all([api(`/portfolios/${portfolioId}`,{requestKey:"portfolio-detail",cacheTtlMs:120000}),api(`/portfolios/${portfolioId}/custom-investments/catalog`,{requestKey:"portfolio-catalog",cacheTtlMs:300000})]);
      if(!portfolioPanelIsCurrent(root,panelKey,requestSerial,navigationSerial))return;
      const rows=data.custom_investments||[],summary=data.consolidated_summary||{},today=new Date().toISOString().slice(0,10);
      state.portfolioAllocationHierarchy=data.consolidated_allocation_hierarchy||null;
      if(state.portfolioAllocationType&&!state.portfolioAllocationHierarchy?.types?.some(item=>item.id===state.portfolioAllocationType))state.portfolioAllocationType=null;
      const form=state.session.access.can_write_portfolio?`<details class="data-card" ${rows.length?"":"open"}><summary><strong>Adicionar investimento sem ticker</strong></summary><form id="custom-investment-form" class="filter-grid" style="margin-top:16px"><div class="field"><label>Tipo</label><select name="category" required>${catalog.map(item=>`<option value="${esc(item.id)}">${esc(item.label)}</option>`).join("")}</select></div><div class="field"><label>Nome do investimento</label><input name="name" required maxlength="200" placeholder="Ex.: CDB Banco X 110% CDI"></div><div class="field"><label>Instituição</label><input name="institution" maxlength="160" placeholder="Banco ou corretora"></div><div class="field"><label>Setor</label><input name="sector" maxlength="120" placeholder="Ex.: Renda fixa"></div><div class="field"><label>Segmento</label><input name="segment" maxlength="120" placeholder="Ex.: Bancário pós-fixado"></div><div class="field"><label>Data da aplicação</label><input type="date" name="application_date" required value="${today}"></div><div class="field"><label>Vencimento (opcional)</label><input type="date" name="maturity_date"></div><div class="field"><label>Valor aplicado</label><input type="number" name="invested_value" min="0.01" step="0.01" required></div><div class="field"><label>Valor atual</label><input type="number" name="current_value" min="0" step="0.01" required></div><div class="field"><label>Data do valor atual</label><input type="date" name="current_value_as_of" required value="${today}"></div><div class="field"><label>Indexador / referência</label><input name="benchmark" maxlength="80" placeholder="Ex.: 110% do CDI"></div><div class="field"><label>Liquidez</label><input name="liquidity" maxlength="120" placeholder="Ex.: no vencimento ou D+1"></div><div class="field wide-action"><label>Observações</label><textarea name="notes" rows="2"></textarea></div><button class="button primary wide-action" type="submit">Salvar investimento</button></form></details>`:"";
      root.innerHTML=`<div class="metric-grid summary-grid">${metricCard("Patrimônio conhecido",money(summary.known_total_value))}${metricCard("Investimentos sem ticker",money(data.custom_summary?.current_value||0),`${rows.length} cadastro(s)`)}${metricCard("Valor aplicado",money(data.custom_summary?.invested_value||0))}${metricCard("Variação",pct(data.custom_summary?.variation_pct,true))}</div>${sectionCard("Composição consolidada",hierarchicalAllocationDonut(state.portfolioAllocationHierarchy,data.consolidated_allocation||[]),summary.allocation_complete?"Valores de mercado e valores informados manualmente":"Composição parcial: existe posição sem cotação")}${sectionCard("Renda fixa, fundos e outros",marketTable(rows,[{label:"Investimento",render:r=>`<strong>${esc(r.name)}</strong><br><small>${esc(r.category_label)}</small>`},{label:"Setor / segmento",render:r=>`${esc(r.sector||"—")}<br><small>${esc(r.segment||"—")}</small>`},{label:"Instituição",render:r=>esc(r.institution||"—")},{label:"Aplicação",render:r=>dateOnly(r.application_date)},{label:"Vencimento",render:r=>dateOnly(r.maturity_date)},{label:"Aplicado",render:r=>money(r.invested_value)},{label:"Atual",render:r=>`${money(r.current_value)}<br><small>${dateOnly(r.current_value_as_of)}</small>`},{label:"Variação",render:r=>pct(r.variation_pct,true),className:r=>variationClass(r.variation_pct)},{label:"",render:r=>state.session.access.can_write_portfolio?`<span class="row-actions"><button class="button ghost compact" data-update-custom-investment="${esc(r.id)}" data-current-value="${esc(r.current_value)}">Atualizar valor</button><button class="button ghost compact danger" data-delete-custom-investment="${esc(r.id)}">Arquivar</button></span>`:""}]),"O histórico preserva cada valor informado por data")}${form}`;
    } else if (tab==="dividends") {
      await renderPortfolioDividends(root);
    } else if (tab==="news") {
      await renderNewsWorkspace(root,{force:forceNews});
    } else {
      await renderAlerts(root);
    }
    if(portfolioPanelIsCurrent(root,panelKey,requestSerial,navigationSerial))markPanelFresh("portfolio",tab);
  } catch(error) { if(error.name!=="AbortError"&&portfolioPanelIsCurrent(root,panelKey,requestSerial,navigationSerial))root.innerHTML=errorState(error); }
  finally {if(portfolioPanelIsCurrent(root,panelKey,requestSerial,navigationSerial))root.classList.remove("panel-refreshing");}
}

async function renderAlerts(root) {
  const panelKey=root.dataset.panelKey;
  const access=state.session.access;
  if (!access.can_use_price_alerts) { root.innerHTML='<div class="data-card empty-state"><strong>Alertas não liberados para esta conta</strong>O administrador pode conceder um limite de 1, 3, 5 ou 10 ativos.</div>'; return; }
  const [catalog,data,history]=await Promise.all([
    api("/alerts/catalog?limit=1",{requestKey:"portfolio-alerts-catalog",cacheTtlMs:600000}),
    api("/alerts",{requestKey:"portfolio-alerts-list",cacheTtlMs:30000}),
    api("/alerts/history?limit=100",{requestKey:"portfolio-alerts-history",cacheTtlMs:30000}),
  ]);
  if(root.dataset.panelKey!==panelKey||state.view!=="portfolio"||state.tabs.portfolio!=="alerts")return;
  state.alertCatalog=catalog;state.alertData={...data,history};
  const alerts=data.alerts||[],active=alerts.filter(item=>item.status==="active");
  const permissions=catalog.permissions||data.permissions||{};
  const conditionFields=[
    {key:"price_above",label:"Preço subindo até ou acima de",placeholder:"Ex.: 42,50",suffix:"valor"},
    {key:"price_below",label:"Preço caindo até ou abaixo de",placeholder:"Ex.: 38,00",suffix:"valor"},
    {key:"change_positive_pct",label:"Variação positiva desde o fechamento",placeholder:"Ex.: 3,00",suffix:"%"},
    {key:"change_negative_pct",label:"Variação negativa desde o fechamento",placeholder:"Ex.: 2,50",suffix:"%"},
  ];
  const ruleInputs=conditionFields.map(field=>`<div class="field alert-condition ${permissions[field.key]?"":"disabled-condition"}"><label>${esc(field.label)} ${permissions[field.key]?"":'<span class="pill">Não liberado</span>'}</label><div class="input-suffix"><input name="${field.key}" type="number" min="0.000001" step="any" placeholder="${esc(field.placeholder)}" ${permissions[field.key]?"":"disabled"}><span>${field.suffix}</span></div></div>`).join("");
  const alertForm=`<form id="price-alert-form" class="alert-form"><div class="filter-grid"><div class="field"><label>Mercado</label><select name="market_scope" id="alert-market-scope"><option value="b3">Ativos negociados na B3</option><option value="market">Índices, moedas, criptos e commodities</option></select></div><div class="field alert-symbol-field"><label>Código ou nome do ativo</label><input name="symbol" id="alert-symbol" autocomplete="off" required maxlength="32" placeholder="Digite, por exemplo, BBAS3"><div id="alert-symbol-suggestions" class="alert-suggestions hidden"></div></div>${ruleInputs}<button class="button primary wide-action" type="submit">Criar ou atualizar alerta</button></div><div class="notice info alert-form-help">Cada ativo consome uma vaga, mesmo quando possui mais de uma condição. Campos vazios não serão monitorados. Regravar um ativo atualiza o alerta existente.</div></form>`;
  const preferenceForm=`<form id="alert-preference-form" class="filter-grid"><div class="field"><label>E-mail principal do cadastro</label><input value="${esc(data.primary_email||state.session.user.email)}" disabled></div><div class="field"><label>Segundo e-mail (opcional)</label><input name="secondary_email" type="email" maxlength="320" value="${esc(data.secondary_email||"")}" placeholder="outro@email.com"></div><button class="button primary" type="submit">Salvar e-mails</button><button class="button secondary" type="button" data-alert-test-email ${data.delivery_configured?"":"disabled"}>Enviar e-mail de teste</button></form>`;
  const alertTable=marketTable(alerts,[
    {label:"Ativo",render:r=>`<strong>${esc(r.symbol)}</strong><br><small>${esc(r.display_name||"")}</small>`},
    {label:"Condições",render:r=>alertConditionSummary(r)},
    {label:"Última cotação",render:r=>`${nullable(r.last_price)?"—":number(r.last_price,4)}${nullable(r.last_change_pct)?"":`<br><small class="${variationClass(r.last_change_pct)}">${pct(r.last_change_pct,true)}</small>`}`},
    {label:"Verificado em",render:r=>dateTime(r.last_checked_at)},
    {label:"Situação",render:r=>`<span class="pill ${r.status==="disabled"?"warning":r.status==="triggered"?"danger":""}">${esc(alertStatusLabel(r.status))}</span>`},
    {label:"Ações",render:r=>`<span class="row-actions"><button class="button ghost compact" data-edit-alert="${esc(r.id)}">Editar</button><button class="button ${r.status==="active"?"ghost danger":"secondary"} compact" data-alert-status="${esc(r.id)}" data-next-status="${r.status==="active"?"disabled":"active"}">${r.status==="active"?"Desativar":"Reativar"}</button></span>`},
  ]);
  const historyTable=marketTable(history,[
    {label:"Ativo",render:r=>`<strong>${esc(r.symbol)}</strong><br><small>${esc(r.display_name||"")}</small>`},
    {label:"O que ocorreu",render:r=>alertEventSummary(r)},
    {label:"Cotação",render:r=>`${nullable(r.observed?.price)?"—":number(r.observed.price,4)}${nullable(r.observed?.change_pct)?"":`<br><small class="${variationClass(r.observed.change_pct)}">${pct(r.observed.change_pct,true)}</small>`}`},
    {label:"Disparo",render:r=>dateTime(r.sent_at||r.created_at)},
    {label:"Destinatários",render:r=>(r.recipients||[]).map(esc).join("<br>")||"—"},
    {label:"Entrega",render:r=>`<span class="pill ${r.delivery_status==="failed"?"danger":""}">${esc(({sent:"E-mail enviado",pending:"Envio pendente",failed:"Falha no envio"})[r.delivery_status]||r.delivery_status||"—")}</span>`},
  ]);
  root.innerHTML=`<div class="notice info alert-schedule"><strong>Como funciona:</strong> ${esc(catalog.b3_schedule)} ${esc(catalog.market_schedule)}<br><small>${esc(catalog.quote_notice||"")}</small></div><div class="metric-grid summary-grid">${metricCard("Alertas ativos",`${active.length} / ${data.limit??access.alert_asset_limit}`,"Cada ativo conta como um alerta")}${metricCard("Condições liberadas",String(Object.values(permissions).filter(Boolean).length),"Até quatro por ativo")}${metricCard("Envio por e-mail",data.delivery_configured?"Configurado":"Pendente",data.secondary_email?"Dois destinatários":"E-mail principal")}${metricCard("Alertas disparados",String(history.length),"Histórico preservado")}</div><div class="alerts-workspace">${sectionCard("Novo alerta",alertForm,"B3 a cada 5 minutos; mercados internacionais a cada 30 minutos")}${sectionCard("Destinatários",preferenceForm,"O e-mail principal é o mesmo utilizado no acesso à plataforma")}</div>${sectionCard("Alertas cadastrados",alerts.length?alertTable:'<div class="empty-state compact"><strong>Nenhum alerta cadastrado</strong>Escolha um ativo e ao menos uma condição acima.</div>',`Limite autorizado: ${data.limit??access.alert_asset_limit} ativo(s)`)}`+
    `<details class="data-card alert-history" ${history.length?"":"open"}><summary><strong>Histórico de alertas disparados</strong><span class="pill">${history.length}</span></summary><div class="alert-history-body">${history.length?historyTable:'<div class="empty-state compact">Nenhum alerta foi disparado até agora.</div>'}</div></details>`;
  $("#notification-count").textContent=active.length;
  $("#notification-count").classList.toggle("hidden",!active.length);
}

function alertStatusLabel(status){return ({active:"Ativo",disabled:"Desativado",triggered:"Disparado"})[status]||status||"—";}
function alertConditionSummary(alert){
  const parts=[];
  if(!nullable(alert.price_above))parts.push(`Preço ≥ ${number(alert.price_above,4)}`);
  if(!nullable(alert.price_below))parts.push(`Preço ≤ ${number(alert.price_below,4)}`);
  if(!nullable(alert.change_positive_pct))parts.push(`Alta ≥ ${pct(alert.change_positive_pct)}`);
  if(!nullable(alert.change_negative_pct))parts.push(`Queda ≥ ${pct(alert.change_negative_pct)}`);
  return parts.length?parts.map(esc).join("<br>"):"—";
}
function alertEventSummary(event){
  const configured=event.configured_values||{};
  return (event.triggered_rules||[]).map(rule=>({price_above:`Preço atingiu ou superou ${number(configured.price_above,4)}`,price_below:`Preço atingiu ou caiu abaixo de ${number(configured.price_below,4)}`,change_positive_pct:`Alta atingiu ${pct(configured.change_positive_pct)}`,change_negative_pct:`Queda atingiu ${pct(configured.change_negative_pct)}`})[rule]||rule).map(esc).join("<br>")||"Condição atingida";
}
function alertCatalogItems(){
  const scope=$("#alert-market-scope")?.value||"b3";
  return state.alertCatalog?.[scope]||[];
}
function drawAlertSuggestions(query=""){
  const root=$("#alert-symbol-suggestions");if(!root)return;
  const term=String(query||"").trim().toLocaleUpperCase("pt-BR");
  if(!term){root.classList.add("hidden");root.innerHTML="";return;}
  const items=alertCatalogItems().filter(item=>`${item.key} ${item.label}`.toLocaleUpperCase("pt-BR").includes(term)).slice(0,12);
  root.innerHTML=items.length?items.map(item=>`<button type="button" data-alert-suggestion="${esc(item.key)}"><strong>${esc(item.key)}</strong><span>${esc(item.label||item.key)}</span><small>${esc(item.asset_type||item.group||"")}</small></button>`).join(""):'<div class="empty-state compact">Nenhum ativo correspondente.</div>';
  root.classList.remove("hidden");
}
function renderAlertSuggestions(query=""){
  clearTimeout(state.alertSuggestionTimer);
  const term=String(query||"").trim();
  if(!term){drawAlertSuggestions("");return;}
  if((document.querySelector("#alert-market-scope")?.value||"b3")==="market"){drawAlertSuggestions(term);return;}
  const root=$("#alert-symbol-suggestions");
  if(root){root.innerHTML='<div class="empty-state compact">Buscando ativos…</div>';root.classList.remove("hidden");}
  state.alertSuggestionTimer=setTimeout(async()=>{
    try{
      const payload=await api(`/alerts/catalog?q=${encodeURIComponent(term)}&limit=12`,{requestKey:"alert-suggestions",cacheTtlMs:600000});
      if(String($("#alert-symbol")?.value||"").trim()!==term)return;
      state.alertCatalog={...(state.alertCatalog||{}),...payload,b3:payload.b3||[]};drawAlertSuggestions(term);
    }catch(error){if(error.name!=="AbortError"&&root)root.innerHTML='<div class="empty-state compact">Não foi possível consultar o catálogo agora.</div>';}
  },180);
}
async function savePriceAlert(form){
  const values=Object.fromEntries(new FormData(form));
  const payload={market_scope:values.market_scope,symbol:String(values.symbol||"").trim().toUpperCase()};
  for(const key of ["price_above","price_below","change_positive_pct","change_negative_pct"])payload[key]=values[key]?Number(String(values[key]).replace(",",".")):null;
  const button=form.querySelector('button[type="submit"]');button.disabled=true;button.textContent="Salvando…";
  try{await api("/alerts",{method:"POST",body:JSON.stringify(payload)});toast("Alerta salvo e monitoramento ativado.","success");await renderPortfolioTab();}
  catch(error){toast(error.message,"error");button.disabled=false;button.textContent="Criar ou atualizar alerta";}
}
async function saveAlertPreferences(form){
  const secondary=String(new FormData(form).get("secondary_email")||"").trim()||null;
  try{await api("/alerts/preferences",{method:"PUT",body:JSON.stringify({secondary_email:secondary})});toast("Destinatários atualizados.","success");await renderPortfolioTab();}
  catch(error){toast(error.message,"error");}
}
async function sendAlertTestEmail(button){
  button.disabled=true;
  try{const result=await api("/alerts/test-email",{method:"POST"});toast(`E-mail de teste enviado para ${(result.recipients||[]).length||1} destinatário(s).`,"success");}
  catch(error){toast(error.message,"error");}
  finally{button.disabled=false;}
}
async function setAlertStatus(button){
  button.disabled=true;
  try{await api(`/alerts/${encodeURIComponent(button.dataset.alertStatus)}/status`,{method:"PATCH",body:JSON.stringify({status:button.dataset.nextStatus})});toast(button.dataset.nextStatus==="active"?"Alerta reativado.":"Alerta desativado.","success");await renderPortfolioTab();}
  catch(error){toast(error.message,"error");button.disabled=false;}
}
function editPriceAlert(alertId){
  const alert=(state.alertData?.alerts||[]).find(item=>item.id===alertId),form=$("#price-alert-form");if(!alert||!form)return;
  form.elements.market_scope.value=alert.market_scope;form.elements.symbol.value=alert.symbol;
  for(const key of ["price_above","price_below","change_positive_pct","change_negative_pct"])if(form.elements[key])form.elements[key].value=nullable(alert[key])?"":alert[key];
  form.scrollIntoView({behavior:"smooth",block:"start"});form.elements.symbol.focus();
}

async function refreshRecommendationNews(category){
  try{const result=await api(`/insights/news/cache/recommendations/refresh?category=${encodeURIComponent(category)}`,{method:"POST"});toast(result.scheduled===false?"As recomendações já estão sendo atualizadas.":"Atualização das recomendações solicitada.",result.scheduled===false?"info":"success");scheduleNavigationTask(()=>renderPortfolioTab({forceNews:true}),2500);}
  catch(error){toast(error.message,"error");}
}

async function refreshPortfolioNews(portfolioId) {
  try {
    const result=await api(`/insights/news/cache/portfolios/${encodeURIComponent(portfolioId)}/refresh`,{method:"POST"});
    toast(result.scheduled===false?"As notícias já estão sendo atualizadas.":"Atualização das notícias solicitada.",result.scheduled===false?"info":"success");
    scheduleNavigationTask(()=>renderPortfolioTab({forceNews:true}),2500);
  } catch(error) { toast(error.message,"error"); }
}

async function saveCustomInvestment(form) {
  const values=Object.fromEntries(new FormData(form));
  for(const key of ["invested_value","current_value"])values[key]=Number(values[key]);
  for(const key of ["maturity_date","institution","sector","segment","benchmark","liquidity","notes"])if(!values[key])values[key]=null;
  try{await api(`/portfolios/${encodeURIComponent(state.portfolioId)}/custom-investments`,{method:"POST",body:JSON.stringify(values)});toast("Investimento salvo.","success");renderPortfolioTab();}
  catch(error){toast(error.message,"error");}
}

async function savePortfolioPosition(form){
  const values=Object.fromEntries(new FormData(form)),ticker=String(values.ticker||"").trim().toUpperCase();
  const payload={asset_type:values.asset_type,stage:"position",quantity:Number(values.quantity||0),average_price:values.average_price?Number(values.average_price):null,target_weight_pct:Number(values.target_weight_pct||0),classification_override:values.classification_override||null,sector_override:values.sector_override||null,segment_override:values.segment_override||null,notes:null};
  try{await api(`/portfolios/${encodeURIComponent(state.portfolioId)}/positions/${encodeURIComponent(ticker)}`,{method:"PUT",body:JSON.stringify(payload)});toast("Posição salva e alocação recalculada.","success");renderPortfolioTab();}
  catch(error){toast(error.message,"error");}
}

async function deletePortfolioPosition(button){
  if(!window.confirm(`Remover ${button.dataset.deletePosition} desta carteira?`))return;
  try{await api(`/portfolios/${encodeURIComponent(state.portfolioId)}/positions/${encodeURIComponent(button.dataset.deletePosition)}`,{method:"DELETE"});toast("Posição removida.","success");renderPortfolioTab();}
  catch(error){toast(error.message,"error");}
}

async function updateCustomInvestmentValue(button) {
  const dialog=$("#custom-value-dialog"),form=$("#custom-value-form");
  form.elements.investment_id.value=button.dataset.updateCustomInvestment;
  form.elements.current_value.value=button.dataset.currentValue||"";
  form.elements.current_value_as_of.value=new Date().toISOString().slice(0,10);
  dialog.showModal();
}

async function saveCustomInvestmentValue(form){
  const values=Object.fromEntries(new FormData(form)),value=Number(values.current_value);
  if(!Number.isFinite(value)||value<0){toast("Informe um valor válido.","error");return;}
  try{await api(`/portfolios/${encodeURIComponent(state.portfolioId)}/custom-investments/${encodeURIComponent(values.investment_id)}`,{method:"PATCH",body:JSON.stringify({current_value:value,current_value_as_of:values.current_value_as_of})});$("#custom-value-dialog").close();toast("Valor e histórico atualizados.","success");renderPortfolioTab();}
  catch(error){toast(error.message,"error");}
}

async function deleteCustomInvestment(button) {
  if(!window.confirm("Arquivar este investimento? O histórico será preservado."))return;
  try{await api(`/portfolios/${encodeURIComponent(state.portfolioId)}/custom-investments/${encodeURIComponent(button.dataset.deleteCustomInvestment)}`,{method:"DELETE"});toast("Investimento arquivado.","success");renderPortfolioTab();}
  catch(error){toast(error.message,"error");}
}

async function refreshPortfolioPrices(portfolioId) {
  try {
    const result=await api(`/portfolios/${encodeURIComponent(portfolioId)}/refresh-prices`,{method:"POST"});
    toast(result.scheduled?"Atualização das cotações solicitada.":"As cotações foram solicitadas há menos de 5 minutos.",result.scheduled?"success":"info");
    scheduleNavigationTask(()=>renderPortfolioTab(),3000);
  } catch(error) { toast(error.message,"error"); }
}

  window.FDIFeatures=window.FDIFeatures||{};
  window.FDIFeatures.portfolio={
    loadPortfolios,
    renderPortfolioTab,
    refreshPortfolioNews,
    refreshRecommendationNews,
    renderAlertSuggestions,
    setAlertStatus,
    editPriceAlert,
    sendAlertTestEmail,
    savePriceAlert,
    saveAlertPreferences,
    refreshPortfolioPrices,
    showPortfolioAllocationType,
    updateCustomInvestmentValue,
    deleteCustomInvestment,
    deletePortfolioPosition,
    saveCustomInvestment,
    savePortfolioPosition,
    saveCustomInvestmentValue
  };
})();
