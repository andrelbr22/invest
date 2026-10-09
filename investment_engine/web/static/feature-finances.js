"use strict";

// Carregado sob demanda pela V1.23.7 R2. O módulo preserva as mesmas
// funções e regras usadas antes no arquivo principal.
(()=>{
function financeCategoryBars(rows,total) {
  if(!(rows||[]).length)return '<div class="empty-state compact"><strong>Nenhuma despesa neste mês</strong>Os grupos aparecerão à medida que você fizer lançamentos.</div>';
  const maximum=Math.max(...rows.map(row=>Number(row.value||0)),1);
  return `<div class="finance-bars">${rows.map(row=>`<div class="finance-bar-row"><span>${esc(row.category)}</span><div><i style="width:${Math.max(2,Number(row.value||0)/maximum*100)}%"></i></div><strong>${money(row.value)}</strong></div>`).join("")}</div><small>Total previsto e realizado: ${money(total)}</small>`;
}

function financeBudgetTable(rows) {
  return marketTable(rows||[],[
    {label:"Categoria",render:r=>`<strong>${esc(r.category)}</strong>`},
    {label:"Limite",render:r=>money(r.limit_value)},
    {label:"Usado",render:r=>money(r.used_value)},
    {label:"Consumo",render:r=>`<span class="pill ${Number(r.used_pct)>100?"danger":""}">${pct(r.used_pct)}</span>`},
  ]);
}

function financeTransactionTable(rows,canWrite) {
  const statusLabels={planned:"Previsto",paid:"Pago",received:"Recebido",overdue:"Atrasado"};
  return marketTable(rows||[],[
    {label:"Data",render:r=>dateOnly(r.transaction_date)},
    {label:"Descrição",render:r=>`<strong>${esc(r.description)}</strong><br><small>${esc(r.category)}${r.institution?` • ${esc(r.institution)}`:""}</small>`},
    {label:"Tipo",render:r=>r.kind==="income"?"Receita":"Despesa"},
    {label:"Valor",render:r=>money(r.amount),className:r=>r.kind==="income"?"positive":"negative"},
    {label:"Status",render:r=>`<span class="pill ${r.status==="overdue"?"danger":""}">${esc(statusLabels[r.status]||r.status)}</span>`},
    {label:"",render:r=>canWrite?`<span class="row-actions">${["paid","received"].includes(r.status)?"":`<button class="button ghost compact" data-set-finance-status="${esc(r.id)}" data-finance-kind="${esc(r.kind)}">${r.kind==="income"?"Marcar recebido":"Marcar pago"}</button>`}<button class="button ghost compact danger" data-delete-finance="${esc(r.id)}">Arquivar</button></span>`:""},
  ]);
}

async function loadFinances() {
  const panelStarted=performance.now();
  const root=$("#finances-tab-content"),monthInput=$("#finance-month");
  if(monthInput&&!monthInput.value)monthInput.value=state.financeMonth;
  const month=state.financeMonth,tab=state.tabs.finances,navigationSerial=state.navigationSerial,requestSerial=++state.financeRequestSerial,panelKey=`${month}:${tab}`;
  const isCurrent=()=>root.dataset.panelKey===panelKey&&requestSerial===state.financeRequestSerial&&navigationIsCurrent(navigationSerial,"finances","finances",tab)&&state.financeMonth===month;
  const samePanel=root.dataset.panelKey===panelKey&&root.childElementCount>0;root.dataset.panelKey=panelKey;
  let panelSucceeded=false;
  if(!samePanel)root.innerHTML=loadingCards(5);else root.classList.add("panel-refreshing");
  try {
    const [data,catalog]=await Promise.all([
      api(`/finances/summary?month=${encodeURIComponent(month)}`,{requestKey:"finances",cacheTtlMs:120000}),
      api("/finances/catalog",{requestKey:"finance-catalog",cacheTtlMs:300000}),
    ]);
    if(!isCurrent())return;
    const access=state.session.access,transactions=data.transactions||[];
    if(tab==="monthly"){
      const expenseTotal=(data.expense_by_category||[]).reduce((sum,row)=>sum+Number(row.value||0),0);
      root.innerHTML=`<div class="metric-grid summary-grid">${metricCard("Receitas recebidas",money(data.realized?.income),"Realizado")}${metricCard("Despesas pagas",money(data.realized?.expense),"Realizado")}${metricCard("Saldo realizado",money(data.realized?.balance),"Entradas menos saídas",data.realized?.balance)}${metricCard("Saldo previsto",money(data.forecast?.balance),"Inclui lançamentos pendentes",data.forecast?.balance)}</div><div class="finance-overview-grid">${sectionCard("Despesas por categoria",financeCategoryBars(data.expense_by_category||[],expenseTotal),`Competência ${state.financeMonth}`)}${sectionCard("Orçamento do mês",(data.budgets||[]).length?financeBudgetTable(data.budgets):'<div class="empty-state compact"><strong>Orçamento ainda não definido</strong>Use a aba Orçamento para criar limites por categoria.</div>')}</div>${sectionCard("Lançamentos mais recentes",financeTransactionTable(transactions.slice(0,8),access.can_write_finances),data.updated_at?`Atualizado em ${dateTime(data.updated_at)}`:"Sem lançamentos")}`;
    }else if(tab==="transactions"){
      const options=(kind)=>(catalog.categories?.[kind]||[]).map(item=>`<option data-finance-category-kind="${kind}" ${kind==="income"?"hidden disabled":""}>${esc(item)}</option>`).join("");
      const form=access.can_write_finances?`<details class="data-card" open><summary><strong>Novo lançamento</strong></summary><form id="finance-transaction-form" class="filter-grid" style="margin-top:16px"><div class="field"><label>Tipo</label><select name="kind"><option value="expense">Despesa</option><option value="income">Receita</option></select></div><div class="field"><label>Categoria</label><select name="category">${options("expense")}${options("income")}</select></div><div class="field"><label>Descrição</label><input name="description" required maxlength="200"></div><div class="field"><label>Valor</label><input name="amount" type="number" min="0.01" step="0.01" required></div><div class="field"><label>Data</label><input name="transaction_date" type="date" value="${new Date().toISOString().slice(0,10)}" required></div><div class="field"><label>Situação</label><select name="status"><option value="planned">Previsto</option><option value="paid" data-finance-status-kind="expense">Pago</option><option value="received" data-finance-status-kind="income" hidden disabled>Recebido</option><option value="overdue">Atrasado</option></select></div><div class="field"><label>Instituição</label><input name="institution" maxlength="120"></div><div class="field"><label>Forma de pagamento</label><input name="payment_method" maxlength="80"></div><div class="field wide-action"><label>Observações</label><textarea name="notes" rows="2"></textarea></div><button class="button primary wide-action" type="submit">Salvar lançamento</button></form></details>`:"";
      root.innerHTML=form+sectionCard("Planilha mensal",financeTransactionTable(transactions,access.can_write_finances),`${transactions.length} lançamento(s) em ${state.financeMonth}`);
    }else{
      const current=new Map((data.budgets||[]).map(row=>[row.category,Number(row.limit_value||0)]));
      const fields=(catalog.categories?.expense||[]).map(category=>`<div class="field"><label>${esc(category)}</label><input type="number" min="0" step="0.01" name="${esc(category)}" value="${current.get(category)||""}" placeholder="Sem limite"></div>`).join("");
      root.innerHTML=`${sectionCard("Acompanhamento",(data.budgets||[]).length?financeBudgetTable(data.budgets):'<div class="empty-state compact">Nenhum limite definido.</div>',"O consumo inclui despesas previstas e pagas")}${access.can_write_finances?`<form id="finance-budget-form" class="data-card filter-grid" style="margin-top:16px">${fields}<button class="button primary wide-action" type="submit">Salvar orçamento de ${esc(state.financeMonth)}</button></form>`:""}`;
    }
    panelSucceeded=true;
  }catch(error){if(error.name!=="AbortError"&&isCurrent())root.innerHTML=errorState(error,"finances");}
  finally {if(isCurrent()){root.classList.remove("panel-refreshing");reportPanelPerformance("finances",panelStarted,{success:panelSucceeded,cacheState:samePanel?(panelSucceeded?"warm":"stale"):"cold"});}}
}

async function saveFinanceTransaction(form){
  const values=Object.fromEntries(new FormData(form));values.amount=Number(values.amount);values.competence_month=state.financeMonth;
  try{await api("/finances/transactions",{method:"POST",body:JSON.stringify(values)});toast("Lançamento salvo.","success");loadFinances();}
  catch(error){toast(error.message,"error");}
}

async function saveFinanceBudget(form){
  const values={};new FormData(form).forEach((value,key)=>{values[key]=Number(value||0);});
  try{await api("/finances/budgets",{method:"PUT",body:JSON.stringify({competence_month:state.financeMonth,values})});toast("Orçamento atualizado.","success");loadFinances();}
  catch(error){toast(error.message,"error");}
}

async function setFinanceStatus(button){
  const status=button.dataset.financeKind==="income"?"received":"paid";
  try{await api(`/finances/transactions/${encodeURIComponent(button.dataset.setFinanceStatus)}`,{method:"PATCH",body:JSON.stringify({status})});toast("Situação atualizada.","success");loadFinances();}
  catch(error){toast(error.message,"error");}
}

async function archiveFinanceTransaction(button){
  if(!window.confirm("Arquivar este lançamento? O registro continuará preservado no banco."))return;
  try{await api(`/finances/transactions/${encodeURIComponent(button.dataset.deleteFinance)}`,{method:"DELETE"});toast("Lançamento arquivado.","success");loadFinances();}
  catch(error){toast(error.message,"error");}
}

  window.FDIFeatures=window.FDIFeatures||{};
  window.FDIFeatures.finances={
    loadFinances,
    saveFinanceTransaction,
    saveFinanceBudget,
    setFinanceStatus,
    archiveFinanceTransaction
  };
})();
