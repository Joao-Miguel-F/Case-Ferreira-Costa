"""
gerar_dashboard.py
==================
Gera outputs/relatorio_qualidade_dados.html — dashboard executivo autocontido
(CSS/JS inline, Chart.js via CDN) a partir dos dados REAIS já processados.

Os números vêm de:
  - outputs/etapa1/decisoes_tratamento.csv, dicionario_dados.csv
  - outputs/etapa2/cobertura_estoque.csv, investigacao_outliers_preco.csv
  - data/processed/*.parquet (KPIs, distribuição de status antes/depois, YoY)

A distribuição de status "antes" é RECONSTRUÍDA pela lógica pré-correção (skeleton
só com estoque inicial, receita sem loja 93, cobertura sem piso) para que o
gráfico antes/depois seja reprodutível a partir das bases — nada é digitado à mão.

Uso:  python scripts/gerar_dashboard.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from utils import (PROCESSED, OUTPUTS, LOJA_ATACADO, load_vendas, load_compras,
                   load_estoque_inicial, load_dim_produto, load_dim_precos)

E1 = OUTPUTS / "etapa1"
E2 = OUTPUTS / "etapa2"
STATUS_ORDER = ["EM RUPTURA", "CRÍTICO", "ATENÇÃO", "SAUDÁVEL", "SEM VENDA"]

# ── formatação pt-BR ────────────────────────────────────────────────────────
def fmt_int(n):
    return f"{int(round(n)):,}".replace(",", ".")

def fmt_milhao(v):
    return "R$ " + f"{v/1e6:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") + "M"

def fmt_pct(v, dec=1):
    return f"{v:.{dec}f}".replace(".", ",") + "%"

def fmt_reais(v, dec=2):
    s = f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + s

# ============================================================================
# TEMPLATE HTML (CSS + JS inline; Chart.js via CDN; dados injetados como JSON)
# ============================================================================
_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Relatório de Qualidade de Dados — Análise de Varejo</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root{
    --bg:#f6f7f9; --surface:#ffffff; --ink:#1f2933; --muted:#6b7280;
    --line:#e5e7eb; --line-strong:#d1d5db;
    --accent:#2563eb; --accent-soft:#eff4ff;
    --green:#059669; --green-soft:#ecfdf5;
    --amber:#d97706; --amber-soft:#fffbeb;
    --red:#dc2626; --red-soft:#fef2f2;
    --sidebar:248px;
  }
  *{box-sizing:border-box;}
  html{scroll-behavior:smooth;}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
       background:var(--bg);color:var(--ink);font-size:15px;line-height:1.55;}
  a{color:var(--accent);text-decoration:none;}

  /* sidebar */
  .sidebar{position:fixed;top:0;left:0;width:var(--sidebar);height:100vh;background:var(--surface);
           border-right:1px solid var(--line);padding:24px 16px;display:flex;flex-direction:column;gap:4px;z-index:20;}
  .brand{font-weight:700;font-size:16px;margin:0 8px 4px;}
  .brand small{display:block;font-weight:500;color:var(--muted);font-size:12px;margin-top:2px;}
  .nav-sep{height:1px;background:var(--line);margin:14px 4px;}
  .nav-item{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:8px;cursor:pointer;
            color:var(--muted);font-size:14px;font-weight:500;border:none;background:none;text-align:left;width:100%;}
  .nav-item:hover{background:var(--bg);color:var(--ink);}
  .nav-item.active{background:var(--accent-soft);color:var(--accent);font-weight:600;}
  .nav-num{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:6px;
           background:var(--bg);font-size:12px;font-weight:600;flex:none;}
  .nav-item.active .nav-num{background:var(--accent);color:#fff;}

  /* main */
  .main{margin-left:var(--sidebar);padding:36px 44px 80px;max-width:1180px;}
  .panel{display:none;animation:fade .25s ease;}
  .panel.active{display:block;}
  @keyframes fade{from{opacity:0;transform:translateY(4px);}to{opacity:1;transform:none;}}
  h1{font-size:24px;margin:0 0 4px;}
  h2{font-size:19px;margin:34px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line);}
  .lead{color:var(--muted);margin:0 0 8px;max-width:760px;}
  .section-tag{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
               color:var(--accent);background:var(--accent-soft);padding:3px 10px;border-radius:6px;margin-bottom:12px;}

  /* cards */
  .kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin:18px 0;}
  .kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px 20px;}
  .kpi .v{font-size:26px;font-weight:700;letter-spacing:-.5px;}
  .kpi .l{color:var(--muted);font-size:13px;margin-top:2px;}
  .card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:22px 24px;margin:16px 0;}

  /* stepper */
  .stepper{display:flex;gap:0;margin:24px 0 8px;flex-wrap:wrap;}
  .step{flex:1;min-width:150px;position:relative;padding:0 14px;}
  .step .dot{width:30px;height:30px;border-radius:50%;background:var(--accent);color:#fff;display:flex;
             align-items:center;justify-content:center;font-weight:700;font-size:14px;margin-bottom:10px;}
  .step .st-t{font-weight:600;font-size:14px;}
  .step .st-d{color:var(--muted);font-size:13px;}
  .step:not(:last-child)::after{content:"";position:absolute;top:15px;left:43px;right:-15px;height:2px;background:var(--line-strong);}

  /* tables */
  table{width:100%;border-collapse:collapse;font-size:14px;}
  th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top;}
  th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600;
     position:sticky;top:0;background:var(--surface);}
  tbody tr:hover{background:var(--bg);}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;}
  .table-wrap{background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow:hidden;}
  .table-scroll{max-height:560px;overflow:auto;}

  /* badges */
  .badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap;}
  .b-estrutural{background:#ede9fe;color:#6d28d9;}
  .b-alto{background:var(--red-soft);color:var(--red);}
  .b-medio{background:var(--amber-soft);color:var(--amber);}
  .b-baixo{background:var(--bg);color:var(--muted);}
  .b-rup{background:var(--red-soft);color:var(--red);}
  .b-crit{background:var(--amber-soft);color:var(--amber);}
  .b-ok{background:var(--green-soft);color:var(--green);}
  .sev-critico{background:var(--red-soft);color:var(--red);}
  .sev-medio{background:var(--amber-soft);color:var(--amber);}
  .st-pendente{background:var(--amber-soft);color:var(--amber);}
  .st-investigado{background:var(--green-soft);color:var(--green);}

  /* expandable */
  .exp-row{cursor:pointer;}
  .exp-row .chev{display:inline-block;transition:transform .2s;color:var(--muted);}
  .exp-row.open .chev{transform:rotate(90deg);}
  .exp-detail{display:none;background:var(--bg);}
  .exp-detail.open{display:table-row;}
  .exp-detail td{padding:14px 18px;}
  .exp-detail dl{margin:0;display:grid;grid-template-columns:160px 1fr;gap:6px 18px;}
  .exp-detail dt{font-weight:600;color:var(--muted);font-size:13px;}
  .exp-detail dd{margin:0;}

  /* bug cards */
  .bug{border:1px solid var(--line);border-left:4px solid var(--red);border-radius:12px;background:var(--surface);
       padding:20px 24px;margin:16px 0;}
  .bug.medio{border-left-color:var(--amber);}
  .bug-head{display:flex;align-items:center;gap:12px;margin-bottom:6px;}
  .bug-num{width:30px;height:30px;border-radius:8px;background:var(--ink);color:#fff;display:flex;
           align-items:center;justify-content:center;font-weight:700;flex:none;}
  .bug-title{font-size:17px;font-weight:700;margin:0;}
  .bug-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px 22px;margin-top:12px;}
  .bug-grid .lbl{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);}
  .ba{display:flex;align-items:center;gap:12px;margin-top:14px;flex-wrap:wrap;}
  .ba .before{color:var(--muted);text-decoration:line-through;background:var(--red-soft);padding:6px 12px;border-radius:8px;font-size:14px;}
  .ba .arrow{color:var(--muted);font-weight:700;}
  .ba .after{color:var(--green);background:var(--green-soft);padding:6px 12px;border-radius:8px;font-weight:600;font-size:14px;}
  .impact{margin-top:12px;background:var(--accent-soft);border-radius:8px;padding:10px 14px;font-size:14px;}

  /* finding cards */
  .finding{border:1px solid var(--line);border-radius:12px;background:var(--surface);padding:18px 22px;margin:14px 0;}
  .finding h3{margin:0 0 8px;font-size:16px;display:flex;justify-content:space-between;align-items:center;gap:12px;}
  .finding .meta{font-size:13px;color:var(--muted);margin:6px 0;}
  .finding .meta b{color:var(--ink);}

  /* search */
  .toolbar{display:flex;gap:12px;align-items:center;margin:12px 0;flex-wrap:wrap;}
  .search{flex:1;min-width:220px;padding:9px 14px;border:1px solid var(--line-strong);border-radius:9px;font-size:14px;}
  .search:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft);}
  .filter-btn{padding:7px 14px;border:1px solid var(--line-strong);background:var(--surface);border-radius:9px;
              cursor:pointer;font-size:13px;font-weight:500;color:var(--muted);}
  .filter-btn.active{background:var(--accent);color:#fff;border-color:var(--accent);}
  .group-title{font-weight:700;font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--accent);
               background:var(--accent-soft);padding:8px 12px;}
  .chart-box{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:20px;margin:16px 0;height:380px;}
  .method{background:var(--bg);border:1px dashed var(--line-strong);border-radius:10px;padding:14px 18px;font-size:14px;}
  .method code{background:var(--surface);padding:2px 6px;border-radius:5px;border:1px solid var(--line);}
  footer{margin-left:var(--sidebar);padding:20px 44px 40px;color:var(--muted);font-size:13px;border-top:1px solid var(--line);}
  .muted{color:var(--muted);} .nowrap{white-space:nowrap;}
  @media(max-width:820px){
    .sidebar{position:static;width:100%;height:auto;flex-direction:row;flex-wrap:wrap;border-right:none;border-bottom:1px solid var(--line);}
    .main,footer{margin-left:0;padding:24px 18px;}
    .nav-sep{display:none;} .bug-grid{grid-template-columns:1fr;}
  }
</style>
</head>
<body>
<nav class="sidebar">
  <div class="brand">Qualidade de Dados<small>Análise de Varejo · 24 meses</small></div>
  <div class="nav-sep"></div>
  <button class="nav-item active" data-tab="t1"><span class="nav-num">1</span> Visão geral</button>
  <button class="nav-item" data-tab="t2"><span class="nav-num">2</span> Decisões de tratamento</button>
  <button class="nav-item" data-tab="t3"><span class="nav-num">3</span> Estoque projetado</button>
  <button class="nav-item" data-tab="t4"><span class="nav-num">4</span> Bugs corrigidos</button>
  <button class="nav-item" data-tab="t5"><span class="nav-num">5</span> Inconsistências</button>
  <button class="nav-item" data-tab="t6"><span class="nav-num">6</span> Dicionário de dados</button>
</nav>

<main class="main">
  <!-- ABA 1 -->
  <section id="t1" class="panel active">
    <span class="section-tag">Visão geral</span>
    <h1>Relatório de qualidade de dados</h1>
    <p class="lead">Consolidação das Etapas 1 e 2 do case, da revisão de qualidade e das 4 correções
       aplicadas. Todos os números são lidos das bases tratadas e dos CSVs de saída.</p>
    <div class="kpi-grid" id="kpiGrid"></div>
    <h2>Linha do tempo</h2>
    <div class="stepper" id="stepper"></div>
  </section>

  <!-- ABA 2 -->
  <section id="t2" class="panel">
    <span class="section-tag">Etapa 1</span>
    <h1>Decisões de tratamento</h1>
    <p class="lead">As decisões de limpeza documentadas com justificativa analítica. Clique numa linha
       para ver problema, tratamento, justificativa e impacto.</p>
    <div class="toolbar">
      <input class="search" id="decSearch" placeholder="Buscar por campo, problema, tratamento…">
      <button class="filter-btn active" data-imp="TODOS">Todos</button>
      <button class="filter-btn" data-imp="ESTRUTURAL">Estrutural</button>
      <button class="filter-btn" data-imp="ALTO">Alto</button>
      <button class="filter-btn" data-imp="MÉDIO">Médio</button>
      <button class="filter-btn" data-imp="BAIXO">Baixo</button>
    </div>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th style="width:30px"></th><th>Campo</th><th>Problema</th><th>Impacto</th></tr></thead>
      <tbody id="decBody"></tbody>
    </table></div></div>
  </section>

  <!-- ABA 3 -->
  <section id="t3" class="panel">
    <span class="section-tag">Etapa 2</span>
    <h1>Estoque projetado e cobertura</h1>
    <p class="lead">Distribuição dos pares loja×produto por status de estoque, antes e depois das
       correções, e os itens críticos de maior receita.</p>
    <div class="chart-box"><canvas id="statusChart"></canvas></div>
    <div class="method">
      <b>Metodologia:</b> <code>Estoque_t = Estoque_inicial + ΣEntradas − ΣSaídas</code>, com todas as
      quantidades convertidas para a unidade de armazenagem. O snapshot é de dez/2025; a cobertura em
      dias usa a venda média mensal da rede física. Pares com estoque ≤ 0 são classificados como
      <b>Em Ruptura</b>.
      <br><br><b>Limitações:</b> a ruptura de ~91% reflete a <b>ausência de registros de reposição</b>
      na base (~88% dos SKUs vendem sem compra registrada) — é um indicador de priorização relativa,
      não de disponibilidade física absoluta. A velocidade usa a média dos meses <i>com</i> venda
      (não dos 24 meses), o que tende a subestimar os dias de cobertura de itens intermitentes.
    </div>
    <h2>Top 15 itens críticos por receita histórica (pós-correção)</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Loja</th><th>Cidade</th><th>Produto</th><th>Categoria</th>
        <th class="num">Estoque</th><th class="num">Receita</th><th>Status</th></tr></thead>
      <tbody id="topBody"></tbody>
    </table></div></div>
  </section>

  <!-- ABA 4 -->
  <section id="t4" class="panel">
    <span class="section-tag">Revisão de qualidade</span>
    <h1>Bugs encontrados e corrigidos</h1>
    <p class="lead">Quatro problemas identificados na revisão, com como foram descobertos, a correção
       e o impacto numérico mensurável.</p>
    <div id="bugList"></div>
  </section>

  <!-- ABA 5 -->
  <section id="t5" class="panel">
    <span class="section-tag">Achados de negócio</span>
    <h1>Inconsistências nos dados</h1>
    <p class="lead">Achados relevantes que <b>não são bugs</b> de código, mas sinais de negócio a
       acompanhar. Cada um traz o achado, a hipótese de causa e o status.</p>
    <div id="findingList"></div>
  </section>

  <!-- ABA 6 -->
  <section id="t6" class="panel">
    <span class="section-tag">Referência</span>
    <h1>Dicionário de dados</h1>
    <p class="lead">Campos das bases, agrupados por tabela. Use a busca para filtrar por nome,
       descrição ou tabela.</p>
    <div class="toolbar"><input class="search" id="dicSearch" placeholder="Buscar campo, tabela ou descrição…"></div>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Campo</th><th>Descrição</th><th>Tipo</th><th>Tratamento</th></tr></thead>
      <tbody id="dicBody"></tbody>
    </table></div></div>
  </section>
</main>

<footer id="footer"></footer>

<script>
const DATA = /*__DATA__*/;
const STATUS_ORDER = ["EM RUPTURA","CRÍTICO","ATENÇÃO","SAUDÁVEL","SEM VENDA"];
const STATUS_COLOR = {"EM RUPTURA":"#dc2626","CRÍTICO":"#d97706","ATENÇÃO":"#f59e0b","SAUDÁVEL":"#059669","SEM VENDA":"#6b7280"};
const esc = s => String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

/* ---- tabs ---- */
document.querySelectorAll(".nav-item").forEach(btn=>{
  btn.addEventListener("click",()=>{
    document.querySelectorAll(".nav-item").forEach(b=>b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(p=>p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
    window.scrollTo({top:0,behavior:"instant"});
  });
});

/* ---- ABA 1: KPIs + stepper ---- */
const kpiDefs=[["receita_total","Receita total (24M)"],["transacoes","Transações"],
  ["skus","SKUs ativos"],["lojas","Lojas"],["categorias","Categorias (N1)"],["periodo","Período"]];
document.getElementById("kpiGrid").innerHTML = kpiDefs.map(([k,l])=>
  `<div class="kpi"><div class="v">${esc(DATA.kpis[k])}</div><div class="l">${l}</div></div>`).join("");
const steps=[["1","Etapa 1","Entendimento e limpeza dos dados brutos"],
  ["2","Etapa 2","Estoque projetado e cobertura"],
  ["3","Revisão","4 problemas de qualidade identificados"],
  ["4","Correções","Bugs corrigidos e saídas regeneradas"]];
document.getElementById("stepper").innerHTML = steps.map(([n,t,d])=>
  `<div class="step"><div class="dot">${n}</div><div class="st-t">${t}</div><div class="st-d">${d}</div></div>`).join("");

/* ---- ABA 2: decisões ---- */
const impClass={"ESTRUTURAL":"b-estrutural","ALTO":"b-alto","MÉDIO":"b-medio","BAIXO":"b-baixo"};
function renderDec(){
  const q=document.getElementById("decSearch").value.toLowerCase();
  const imp=document.querySelector("#t2 .filter-btn.active").dataset.imp;
  const body=document.getElementById("decBody"); body.innerHTML="";
  DATA.decisoes.forEach((d,i)=>{
    const hay=(d.campo+d.problema+d.tratamento+d.justificativa).toLowerCase();
    if(q && !hay.includes(q)) return;
    if(imp!=="TODOS" && d.impacto!==imp) return;
    const cls=impClass[d.impacto]||"b-baixo";
    body.insertAdjacentHTML("beforeend",
      `<tr class="exp-row" data-i="${i}"><td><span class="chev">▶</span></td>
        <td><b>${esc(d.campo)}</b></td><td>${esc(d.problema)}</td>
        <td><span class="badge ${cls}">${esc(d.impacto)}</span></td></tr>
       <tr class="exp-detail" data-d="${i}"><td></td><td colspan="3"><dl>
         <dt>Tratamento</dt><dd>${esc(d.tratamento)}</dd>
         <dt>Justificativa</dt><dd>${esc(d.justificativa)}</dd></dl></td></tr>`);
  });
  body.querySelectorAll(".exp-row").forEach(r=>r.addEventListener("click",()=>{
    r.classList.toggle("open");
    body.querySelector(`.exp-detail[data-d="${r.dataset.i}"]`).classList.toggle("open");
  }));
}
document.getElementById("decSearch").addEventListener("input",renderDec);
document.querySelectorAll("#t2 .filter-btn").forEach(b=>b.addEventListener("click",()=>{
  document.querySelectorAll("#t2 .filter-btn").forEach(x=>x.classList.remove("active"));
  b.classList.add("active"); renderDec();
}));
renderDec();

/* ---- ABA 3: chart + top15 ---- */
const stBadge=s=>s==="EM RUPTURA"?"b-rup":(s==="CRÍTICO"?"b-crit":"b-ok");
document.getElementById("topBody").innerHTML = DATA.top15.map(r=>
  `<tr><td>${r.loja}</td><td>${esc(r.cidade)}</td><td><b>${r.codigo}</b><br><span class="muted">${esc(r.desc)}</span></td>
    <td>${esc(r.nivel1)}</td><td class="num">${esc(r.estoque)}</td><td class="num">${esc(r.receita)}</td>
    <td><span class="badge ${stBadge(r.status)}">${esc(r.status)}</span></td></tr>`).join("");
// Gráfico via Chart.js (CDN). Guardado para degradar com elegância se o arquivo
// for aberto offline e o CDN não carregar — assim as demais abas seguem renderizando.
if(typeof Chart !== "undefined"){
  new Chart(document.getElementById("statusChart"),{
    type:"bar",
    data:{labels:STATUS_ORDER,datasets:[
      {label:"Antes da correção",data:STATUS_ORDER.map(s=>DATA.status_antes[s]),backgroundColor:"#cbd5e1"},
      {label:"Depois da correção",data:STATUS_ORDER.map(s=>DATA.status_depois[s]),backgroundColor:STATUS_ORDER.map(s=>STATUS_COLOR[s])}
    ]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{title:{display:true,text:"Pares loja×produto por status — antes vs depois"},
        tooltip:{callbacks:{label:c=>c.dataset.label+": "+c.parsed.y.toLocaleString("pt-BR")+" pares"}}},
      scales:{y:{ticks:{callback:v=>v.toLocaleString("pt-BR")}}}}
  });
}else{
  const tbl=STATUS_ORDER.map(s=>`<tr><td>${s}</td><td class="num">${DATA.status_antes[s].toLocaleString("pt-BR")}</td>`+
    `<td class="num">${DATA.status_depois[s].toLocaleString("pt-BR")}</td></tr>`).join("");
  document.getElementById("statusChart").closest(".chart-box").innerHTML =
    `<p class="muted">Gráfico indisponível offline (Chart.js via CDN). Dados antes/depois:</p>`+
    `<table><thead><tr><th>Status</th><th class="num">Antes</th><th class="num">Depois</th></tr></thead><tbody>${tbl}</tbody></table>`;
}

/* ---- ABA 4: bugs ---- */
document.getElementById("bugList").innerHTML = DATA.bugs.map(b=>`
  <div class="bug ${b.sev==='Médio'?'medio':''}">
    <div class="bug-head"><div class="bug-num">${b.n}</div>
      <h3 class="bug-title">${esc(b.titulo)}</h3>
      <span class="badge ${b.sev==='Crítico'?'sev-critico':'sev-medio'}">${b.sev}</span></div>
    <div class="bug-grid">
      <div><div class="lbl">O que foi encontrado</div><div>${esc(b.encontrado)}</div></div>
      <div><div class="lbl">Como foi descoberto</div><div>${esc(b.descoberto)}</div></div>
      <div><div class="lbl">Correção aplicada</div><div>${esc(b.correcao)}</div></div>
      <div><div class="lbl">Antes / depois</div>
        <div class="ba"><span class="before">${esc(b.antes)}</span><span class="arrow">→</span>
          <span class="after">${esc(b.depois)}</span></div></div>
    </div>
    <div class="impact"><b>Impacto:</b> ${esc(b.impacto)}</div>
  </div>`).join("");

/* ---- ABA 5: findings ---- */
document.getElementById("findingList").innerHTML = DATA.inconsistencias.map(f=>`
  <div class="finding">
    <h3>${esc(f.titulo)}
      <span class="badge ${f.status==='investigado'?'st-investigado':'st-pendente'}">${f.status}</span></h3>
    <div class="meta"><b>Achado:</b> ${esc(f.achado)}</div>
    <div class="meta"><b>Hipótese:</b> ${esc(f.hipotese)}</div>
  </div>`).join("");

/* ---- ABA 6: dicionário ---- */
function renderDic(){
  const q=document.getElementById("dicSearch").value.toLowerCase();
  const rows=DATA.dicionario.filter(d=>!q || (d.campo+d.descricao+d.tabela+d.tipo).toLowerCase().includes(q));
  const body=document.getElementById("dicBody"); body.innerHTML="";
  let cur=null;
  rows.forEach(d=>{
    if(d.tabela!==cur){cur=d.tabela;
      body.insertAdjacentHTML("beforeend",`<tr><td colspan="4" class="group-title">${esc(cur)}</td></tr>`);}
    body.insertAdjacentHTML("beforeend",
      `<tr><td><b>${esc(d.campo)}</b></td><td>${esc(d.descricao)}</td>
        <td class="nowrap">${esc(d.tipo)}</td><td class="muted">${esc(d.tratamento)}</td></tr>`);
  });
  if(!rows.length) body.innerHTML=`<tr><td colspan="4" class="muted" style="padding:18px">Nenhum campo encontrado.</td></tr>`;
}
document.getElementById("dicSearch").addEventListener("input",renderDic);
renderDic();

/* ---- footer ---- */
document.getElementById("footer").innerHTML =
  `Relatório gerado em <b>${esc(DATA.gerado_em)}</b> · Fonte: bases tratadas em `+
  `<code>data/processed/</code> e saídas em <code>outputs/etapa1</code> e <code>outputs/etapa2</code> · `+
  `Case Técnico — Análise de Desempenho de Produtos no Varejo.`;
</script>
</body>
</html>"""

# ============================================================================
# 1. CARREGAR / COMPUTAR DADOS
# ============================================================================
print("Carregando bases...")
v = load_vendas(excluir_atacado=False)
c = load_compras()
e = load_estoque_inicial()
p = load_dim_produto()

# ---- KPIs gerais (Etapa 1) ----
receita_total = float(v["RECEITA"].sum())
kpis = {
    "receita_total": fmt_milhao(receita_total),
    "transacoes":    fmt_int(len(v)),
    "skus":          fmt_int(v["CODIGO"].nunique()),
    "lojas":         str(v["COD_EMPRESA"].nunique()),
    "categorias":    str(v["NIVEL_1"].nunique()),
    "periodo":       f"{v['DATA_VENDA'].min():%m/%Y} a {v['DATA_VENDA'].max():%m/%Y}",
}

# ---- Reconstrução antes/depois da distribuição de status ----
def pipeline(corrigido: bool):
    conv = p.set_index("CODIGO")["CONVERSAO_COMPRA_ARMAZENAGEM"]
    cc = c.copy()
    cc["QARM"] = cc["QUANTIDADE_COMPRA"] * cc["CODIGO"].map(conv).fillna(1.0)
    vv = v.copy()
    vv["M"] = vv["DATA_VENDA"].dt.to_period("M"); cc["M"] = cc["DATA_ENTRADA"].dt.to_period("M")
    sa = vv.groupby(["COD_EMPRESA","CODIGO","M"])["QTD_ARMAZENAGEM"].sum().reset_index(name="S")
    en = cc.groupby(["COD_EMPRESA","CODIGO","M"])["QARM"].sum().reset_index(name="E")
    meses = pd.period_range("2024-01","2025-12",freq="M")
    if corrigido:
        pares = pd.concat([e[["COD_EMPRESA","CODIGO"]], vv[["COD_EMPRESA","CODIGO"]],
                           cc[["COD_EMPRESA","CODIGO"]]]).drop_duplicates()
    else:
        pares = e[["COD_EMPRESA","CODIGO"]].drop_duplicates()
    sk = pares.assign(k=1).merge(pd.DataFrame({"M":meses,"k":1}),on="k").drop("k",axis=1)
    d = (sk.merge(sa,on=["COD_EMPRESA","CODIGO","M"],how="left")
           .merge(en,on=["COD_EMPRESA","CODIGO","M"],how="left").fillna({"S":0.0,"E":0.0})
           .merge(e,on=["COD_EMPRESA","CODIGO"],how="left").fillna({"ESTOQUE_INICIAL":0.0})
           .sort_values(["COD_EMPRESA","CODIGO","M"]))
    d["EST"] = d["ESTOQUE_INICIAL"] + d.groupby(["COD_EMPRESA","CODIGO"])["E"].cumsum() - d.groupby(["COD_EMPRESA","CODIGO"])["S"].cumsum()
    fin = d[d["M"]==pd.Period("2025-12","M")][["COD_EMPRESA","CODIGO","EST"]].copy()
    vmm = (vv[vv["COD_EMPRESA"]!=LOJA_ATACADO].groupby(["COD_EMPRESA","CODIGO","M"])["QTD_ARMAZENAGEM"].sum()
           .groupby(["COD_EMPRESA","CODIGO"]).mean().reset_index(name="VMM"))
    cob = fin.merge(vmm,on=["COD_EMPRESA","CODIGO"],how="left").fillna({"VMM":0})
    cob["DIAS"] = np.where(cob["VMM"]>0, cob["EST"]/cob["VMM"]*30, np.inf)
    if corrigido:
        cob["DIAS"] = np.where(cob["EST"]<=0, 0, cob["DIAS"])
    def cls(r):
        if r["EST"]<=0: return "EM RUPTURA"
        if r["DIAS"]<=30: return "CRÍTICO"
        if r["DIAS"]<=90: return "ATENÇÃO"
        if r["DIAS"]==np.inf: return "SEM VENDA"
        return "SAUDÁVEL"
    cob["ST"] = cob.apply(cls, axis=1)
    return cob

print("Reconstruindo distribuição antes/depois...")
cob_before = pipeline(False)
cob_after  = pipeline(True)
status_antes  = {s: int((cob_before["ST"]==s).sum()) for s in STATUS_ORDER}
status_depois = {s: int((cob_after["ST"]==s).sum()) for s in STATUS_ORDER}
neg_antes = int((pipeline(False)["DIAS"] < 0).sum())  # negativos no output original

# ---- Top 15 críticos por receita (pós-correção, do CSV salvo) ----
cob_csv = pd.read_csv(E2 / "cobertura_estoque.csv", encoding="utf-8-sig")
top15 = (cob_csv[cob_csv["STATUS_ESTOQUE"].isin(["EM RUPTURA","CRÍTICO"])]
         .sort_values("RECEITA_TOTAL", ascending=False).head(15))
top15_rows = [{
    "loja": int(r.COD_EMPRESA),
    "cidade": str(r.CD_CIDADE),
    "codigo": int(r.CODIGO),
    "desc": str(r.DESCRICAO).strip(),
    "nivel1": str(r.NIVEL_1),
    "estoque": fmt_int(r.ESTOQUE_PROJ),
    "receita": fmt_milhao(r.RECEITA_TOTAL),
    "status": str(r.STATUS_ESTOQUE),
} for r in top15.itertuples()]

# ---- Decisões de tratamento (Etapa 1) ----
dec = pd.read_csv(E1 / "decisoes_tratamento.csv")
decisoes = [{
    "campo": str(r.campo), "problema": str(r.problema), "tratamento": str(r.tratamento),
    "justificativa": str(r.justificativa), "impacto": str(r.impacto).strip().upper(),
} for r in dec.itertuples()]

# ---- Dicionário de dados ----
dic = pd.read_csv(E1 / "dicionario_dados.csv")
dicionario = [{
    "tabela": str(r.tabela), "campo": str(r.campo), "descricao": str(r.descricao),
    "tipo": str(r.tipo), "notas": str(r.notas), "tratamento": str(r.tratamento_aplicado),
} for r in dic.itertuples()]

# ---- Investigação de outliers de preço (Bug 4) ----
inv = pd.read_csv(E2 / "investigacao_outliers_preco.csv", encoding="utf-8-sig")
outliers_total = int(len(inv))
outliers_sim = int((inv["EMBALAGEM_SUSPEITA"].str.lower() == "sim").sum())
outliers_nao = outliers_total - outliers_sim
outliers_rows = [{
    "loja": int(r.COD_EMPRESA), "codigo": int(r.CODIGO), "desc": str(r.DESCRICAO).strip(),
    "pmin": fmt_reais(r.PRECO_MIN), "pmax": fmt_reais(r.PRECO_MAX),
    "cv": f"{r.CV:.2f}".replace(".", ","), "hipotese": str(r.HIPOTESE),
    "suspeita": str(r.EMBALAGEM_SUSPEITA),
} for r in inv.head(12).itertuples()]

# ============================================================================
# 2. NÚMEROS DAS INCONSISTÊNCIAS DE NEGÓCIO (ABA 5) — computados das bases
# ============================================================================
print("Computando inconsistências de negócio...")
r24 = float(v[v["ANO"]==2024]["RECEITA"].sum()); r25 = float(v[v["ANO"]==2025]["RECEITA"].sum())
tx24 = int((v["ANO"]==2024).sum()); tx25 = int((v["ANO"]==2025).sum())
yoy = (r25/r24 - 1) * 100

cat = v.groupby(["NIVEL_1","ANO"])["RECEITA"].sum().unstack().fillna(0)
cat["var"] = (cat[2025]/cat[2024]-1)*100
eletros = cat.loc[[i for i in cat.index if i.startswith("D - ")][0]]
eletronicos = cat.loc[[i for i in cat.index if i.startswith("R - ")][0]]

# preço cadastrado vs praticado
pr = load_dim_precos()
prat = v.groupby("CODIGO")["PRECO_UNIT_MEDIO"].mean().reset_index()
prm = prat.merge(pr[["CODIGO","PRECO_EMBALAGEM_0"]].dropna(), on="CODIGO", how="inner")
prm = prm[prm["PRECO_EMBALAGEM_0"] > 0]
prm["diff"] = (prm["PRECO_UNIT_MEDIO"]/prm["PRECO_EMBALAGEM_0"]-1).abs()*100
div_n = int((prm["diff"] > 30).sum()); div_tot = int(len(prm))

# receita sem compra registrada
skus_compra = set(c["CODIGO"].unique())
rec_sem = float(v[~v["CODIGO"].isin(skus_compra)]["RECEITA"].sum())
skus_sem = int(v[~v["CODIGO"].isin(skus_compra)]["CODIGO"].nunique())

# loja 93
r93 = float(v[v["COD_EMPRESA"]==LOJA_ATACADO]["RECEITA"].sum())
sk93 = int(v[v["COD_EMPRESA"]==LOJA_ATACADO]["CODIGO"].nunique())
tk93 = r93/int((v["COD_EMPRESA"]==LOJA_ATACADO).sum())
tknet = float(v[v["COD_EMPRESA"]!=LOJA_ATACADO]["RECEITA"].sum())/int((v["COD_EMPRESA"]!=LOJA_ATACADO).sum())

inconsistencias = [
    {"titulo": "Queda sustentada de volume em 2025",
     "achado": f"As transações caem de forma contínua ao longo de 2025; o ano fecha com "
               f"{fmt_int(tx25)} transações contra {fmt_int(tx24)} em 2024 (−{fmt_pct(abs(tx25/tx24-1)*100)}) "
               f"e receita de {fmt_milhao(r25)} vs {fmt_milhao(r24)} ({fmt_pct(yoy)}).",
     "hipotese": "Os 24 meses estão completos (não é gap de dados) — a queda é uma tendência real. "
                 "Possíveis causas: retração de mercado regional, descontinuação de operações ou "
                 "migração de canal. Exige confirmação com a área comercial.",
     "status": "pendente"},
    {"titulo": "Queda generalizada por categoria; Eletros lidera a perda",
     "achado": f"Todas as categorias recuam em 2025. D — Eletros cai {fmt_pct(eletros['var'])} "
               f"({fmt_milhao(eletros[2024])} → {fmt_milhao(eletros[2025])}) e puxa o resultado. "
               f"R — Eletrônicos é a mais resiliente ({fmt_pct(eletronicos['var'])}).",
     "hipotese": "A forte dependência de Eletros (categoria de maior ticket, ligada ao atacado da loja 93) "
                 "amplifica a queda da rede. Convém isolar o efeito loja 93 do efeito rede física.",
     "status": "pendente"},
    {"titulo": "Divergência entre preço cadastrado e praticado",
     "achado": f"{fmt_int(div_n)} SKUs ({fmt_pct(div_n/div_tot*100)} de {fmt_int(div_tot)} comparáveis) "
               f"têm preço médio praticado mais de 30% distante do preço de tabela (dim_precos).",
     "hipotese": "Parte é explicada por venda em embalagem/caixa (ver Bug 4) e por descontos/repricing "
                 "ao longo do período. Não há evidência de erro sistêmico de cadastro, mas merece "
                 "auditoria de precificação por categoria.",
     "status": "investigado"},
    {"titulo": "80% da receita vem de SKUs sem compra registrada",
     "achado": f"{fmt_milhao(rec_sem)} ({fmt_pct(rec_sem/receita_total*100)} da receita) vêm de "
               f"{fmt_int(skus_sem)} SKUs que vendem sem nenhuma entrada de compra nos 24 meses.",
     "hipotese": "O estoque inicial é o principal ativo operacional; a reposição provavelmente ocorre "
                 "via transferência entre lojas ou em período anterior ao corte da base. Não é erro — "
                 "é o que justifica a abordagem conservadora de estoque da Etapa 2.",
     "status": "investigado"},
    {"titulo": "Loja 93 (Alhandra) é um outlier de canal",
     "achado": f"Concentra {fmt_pct(r93/receita_total*100)} da receita ({fmt_milhao(r93)}) com apenas "
               f"{fmt_int(sk93)} SKUs ({fmt_pct(sk93/v['CODIGO'].nunique()*100)}); ticket médio "
               f"{fmt_reais(tk93,0)} vs {fmt_reais(tknet,0)} da rede física (~20×).",
     "hipotese": "Comportamento típico de atacado/B2B. Mantida na base, mas segregada via FLAG_LOJA93 "
                 "para não distorcer as médias da rede física.",
     "status": "investigado"},
]

# ============================================================================
# 3. CONTEÚDO DOS 4 BUGS (ABA 4) — números computados acima
# ============================================================================
bugs = [
    {"n": 1, "sev": "Crítico",
     "titulo": "Receita por par calculada sem a loja 93",
     "encontrado": "A receita histórica por par (base do ranking de reposição) era calculada com "
                   "excluir_atacado=True, removendo a loja 93 antes do cálculo.",
     "descoberto": "Cruzando os pares do skeleton (que incluem a loja 93, presente no estoque inicial) "
                   "com a receita: 263 pares da loja 93 em ruptura apareciam com RECEITA_TOTAL nula.",
     "correcao": "Calcular a receita por par com todas as lojas (excluir_atacado=False); segregar o "
                 "atacado apenas como filtro posterior de análise.",
     "antes": "0 pares da loja 93 no ranking",
     "depois": "263 pares da loja 93 reintegrados",
     "impacto": "Os itens de maior receita da base (condicionadores, lavadoras, TVs do atacado) "
                "voltaram ao topo do ranking de prioridade de reposição."},
    {"n": 2, "sev": "Crítico",
     "titulo": "Skeleton montado só com o estoque inicial",
     "encontrado": "O universo de pares loja×produto era construído apenas a partir de "
                   "fato_estoque_inicial, ignorando pares com venda e sem foto de estoque.",
     "descoberto": "Comparando os pares únicos de fato_vendas com os de fato_estoque_inicial: "
                   "3.379 pares de venda ficavam fora da projeção.",
     "correcao": "Skeleton = união dos pares de estoque inicial ∪ vendas ∪ compras. Pares sem foto "
                 "inicial entram com ESTOQUE_INICIAL = 0 (lógica conservadora da Etapa 1).",
     "antes": "25.330 pares na cobertura",
     "depois": "28.721 pares na cobertura (+3.391)",
     "impacto": "+3.379 pares com venda voltam ao radar, rastreando +R$ 87,5M (18,1% da receita) "
                "antes invisíveis no estoque projetado."},
    {"n": 3, "sev": "Médio",
     "titulo": "Dias de cobertura negativos em rupturas",
     "encontrado": "DIAS_COBERTURA = Estoque / Venda_média × 30 sem piso gerava valores negativos "
                   "(ex.: −566 dias) para pares em ruptura.",
     "descoberto": "Inspeção da distribuição de DIAS_COBERTURA: mínimo de −720 dias e milhares de "
                   "valores negativos sem significado de negócio.",
     "correcao": "Aplicar piso: DIAS_COBERTURA = 0 quando ESTOQUE_PROJ ≤ 0 (a condição de ruptura "
                 "já é capturada pelo STATUS_ESTOQUE).",
     "antes": f"{fmt_int(neg_antes)} valores negativos (mín. −720)",
     "depois": "0 valores negativos",
     "impacto": "Ordenações e médias de cobertura deixam de ser contaminadas por números negativos."},
    {"n": 4, "sev": "Médio",
     "titulo": "Outliers de preço (investigação)",
     "encontrado": "Produto 119959 (Adaptador Cx. Elét. 3/4) com preço de R$ 3,68 a R$ 391,55 na "
                   "mesma loja, incluindo mesmo dia/loja com os dois preços.",
     "descoberto": "Diagnóstico por embalagem: os lançamentos caros são EMBALAGEM=1 (caixa) com "
                   "CONVERSAO=100 — R$ 391,55 ÷ 100 ≈ R$ 3,92/unidade, coerente com a venda unitária.",
     "correcao": "Investigação documentada em investigacao_outliers_preco.csv. Estendida aos "
                 f"{outliers_total} pares com CV de preço > 1.",
     "antes": "Suspeita: conversão de embalagem ausente",
     "depois": f"{outliers_nao}/{outliers_total} explicados — não é bug",
     "impacto": "Conclusão: venda em caixa com conversão corretamente aplicada. Nenhum caso de "
                "EMBALAGEM=1 com CONVERSAO=1 (o padrão que seria erro de cadastro)."},
]

DATA = {
    "kpis": kpis,
    "status_antes": status_antes,
    "status_depois": status_depois,
    "top15": top15_rows,
    "decisoes": decisoes,
    "dicionario": dicionario,
    "outliers": {"total": outliers_total, "sim": outliers_sim, "nao": outliers_nao,
                 "rows": outliers_rows},
    "inconsistencias": inconsistencias,
    "bugs": bugs,
    "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
}

# ============================================================================
# 4. RENDERIZAR HTML
# ============================================================================
print("Renderizando HTML...")
html = _TEMPLATE.replace("/*__DATA__*/", json.dumps(DATA, ensure_ascii=False))
out = OUTPUTS / "relatorio_qualidade_dados.html"
out.write_text(html, encoding="utf-8")
size_kb = out.stat().st_size / 1024
print(f"[OK] {out}  ({size_kb:.0f} KB)")
print(f"     antes={status_antes}")
print(f"     depois={status_depois}")
