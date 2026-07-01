"""
gerar_dashboard.py
==================
Gera outputs/relatorio_qualidade_dados.html — dashboard executivo autocontido
(CSS/JS inline, Chart.js via CDN) a partir dos dados REAIS já processados.

Os números vêm de:
  - outputs/etapa1/decisoes_tratamento.csv, dicionario_dados.csv
  - outputs/etapa2/cobertura_estoque.csv, investigacao_outliers_preco.csv
  - outputs/etapa3/*.csv (rankings, ABC, desempenho, notas e recomendações)
  - outputs/etapa4/*.csv (cobertura por categoria/loja, priorização e validações)
  - outputs/etapa6/*.csv (projecao de compras, priorizacao e validacoes)
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
E3 = OUTPUTS / "etapa3"
E4 = OUTPUTS / "etapa4"
E5 = OUTPUTS / "etapa5"
E6 = OUTPUTS / "etapa6"
E7 = OUTPUTS / "etapa7"
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
  <button class="nav-item" data-tab="t4"><span class="nav-num">4</span> Desempenho vendas</button>
  <button class="nav-item" data-tab="t5"><span class="nav-num">5</span> Cobertura cat./loja</button>
  <button class="nav-item" data-tab="te5"><span class="nav-num">6</span> Precificação e margem</button>
  <button class="nav-item" data-tab="te6"><span class="nav-num">7</span> Projeção compras</button>
  <button class="nav-item" data-tab="te7"><span class="nav-num">8</span> Recomendações finais</button>
  <button class="nav-item" data-tab="t6"><span class="nav-num">9</span> Bugs corrigidos</button>
  <button class="nav-item" data-tab="t7"><span class="nav-num">10</span> Inconsistências</button>
  <button class="nav-item" data-tab="t8"><span class="nav-num">11</span> Dicionário de dados</button>
  <button class="nav-item" data-tab="t9"><span class="nav-num">12</span> Glossário comercial</button>
</nav>

<main class="main">
  <!-- ABA 1 -->
  <section id="t1" class="panel active">
    <span class="section-tag">Visão geral</span>
    <h1>Relatório de qualidade de dados</h1>
    <p class="lead">Consolidação das Etapas 1 a 7 do case, da revisão de qualidade e das 4 correções
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
    <p class="lead">Distribuição dos pares loja×produto (cada produto dentro de cada loja) por status de
       estoque, antes e depois das correções, e os itens críticos de maior receita. Termos técnicos estão
       explicados em linguagem de negócio na aba <b>Glossário comercial</b>.</p>
    <div class="chart-box"><canvas id="statusChart"></canvas></div>
    <div class="method">
      <b>Metodologia:</b> <code>Estoque_t = Estoque_inicial + ΣEntradas − ΣSaídas</code>, com todas as
      quantidades convertidas para a unidade de armazenagem (a unidade padrão do estoque, p.ex. a caixa).
      O snapshot (foto do estoque) é de dez/2025; a cobertura em dias estima por quantos dias o estoque
      atende a venda média mensal da rede física. Pares com estoque ≤ 0 são classificados como
      <b>Em Ruptura</b> (sem saldo para vender).
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
    <span class="section-tag">Etapa 3</span>
    <h1>Análise de desempenho de vendas</h1>
    <p class="lead">Rankings, curva ABC, categorias, lojas e sazonalidade gerados a partir de
       <code>data/processed/vendas_tratadas.parquet</code>. A Loja 93 é exibida na rede completa e
       segregada da rede física para evitar mistura entre atacado/B2B e varejo.</p>
    <div class="kpi-grid" id="e3KpiGrid"></div>
    <div class="method">
      <b>Nota metodológica importante:</b> a base não possui identificador de cupom, pedido ou nota.
      Por isso, <code>TRANSACOES</code> na Etapa 3 é a contagem de linhas de venda e o ticket médio é
      uma proxy de receita média por linha. A recomendação de melhoria é incluir um identificador único
      de transação e número do item no fato de vendas.
    </div>

    <h2>Top categorias por receita</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Universo</th><th>Categoria N1</th><th class="num">Receita</th>
        <th class="num">Part.</th><th class="num">Variação 2025 vs 2024</th></tr></thead>
      <tbody id="e3CatBody"></tbody>
    </table></div></div>

    <h2>Top lojas por receita</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Universo</th><th>Loja</th><th>Cidade/UF</th><th>Operação</th>
        <th class="num">Receita</th><th class="num">Linhas venda</th><th class="num">Receita média/linha</th></tr></thead>
      <tbody id="e3LojaBody"></tbody>
    </table></div></div>

    <h2>Recomendações de melhoria</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Prioridade</th><th>Tema</th><th>Problema</th><th>Recomendação</th><th>Impacto esperado</th></tr></thead>
      <tbody id="e3RecBody"></tbody>
    </table></div></div>
  </section>

  <!-- ABA 5 -->
  <section id="t5" class="panel">
    <span class="section-tag">Etapa 4</span>
    <h1>Cobertura por categoria e loja</h1>
    <p class="lead">Agregacao do snapshot de cobertura da Etapa 2 por categoria, loja e categoria x loja,
       cruzada com os outputs auditaveis da Etapa 3. A priorizacao operacional separa rede fisica e Loja 93.</p>
    <div class="kpi-grid" id="e4KpiGrid"></div>
    <div class="method">
      <b>Nota metodologica:</b> "receita em risco" e a receita historica <b>ja realizada</b> pelos pares
      loja x produto com <code>STATUS_ESTOQUE</code> em <b>EM RUPTURA</b> ou <b>CRITICO</b> &mdash; serve para
      <b>ordenar prioridade</b> de reposicao, nao e perda projetada. Medias e medianas de
      <code>DIAS_COBERTURA</code> usam apenas valores finitos; cobertura infinita e contada em coluna propria.
      <br><b>Como ler a taxa de ruptura:</b> o estoque projetado e reconstruido como
      <code>estoque inicial + compras &minus; vendas</code> (nao e contagem fisica). Como a base nao tem foto de
      estoque de abertura para a maioria dos pares e ~88% dos SKUs vendem sem compra registrada, ~91% dos pares
      ficam com estoque &le; 0 e sao marcados como ruptura. A metrica e <b>conservadora por construcao</b>
      (erra para sinalizar ruptura a mais) e mede <b>prioridade relativa</b>, nao disponibilidade fisica real.
    </div>

    <h2>Top categorias por receita em risco</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Universo</th><th>Categoria N1</th><th class="num">Receita em risco</th>
        <th class="num">Pares em risco</th><th class="num">% pares</th><th class="num">Mediana dias</th></tr></thead>
      <tbody id="e4CatBody"></tbody>
    </table></div></div>

    <h2>Top lojas por receita em risco</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Universo</th><th>Loja</th><th>Cidade/UF</th><th>Operacao</th>
        <th class="num">Receita em risco</th><th class="num">% pares risco</th></tr></thead>
      <tbody id="e4LojaBody"></tbody>
    </table></div></div>

    <h2>Prioridades categoria x loja</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Escopo</th><th>Rank</th><th>Prioridade</th><th>Loja</th><th>Categoria</th>
        <th class="num">Receita em risco</th><th>Acao recomendada</th></tr></thead>
      <tbody id="e4PrioBody"></tbody>
    </table></div></div>

    <h2>Recomendacoes de melhoria</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Prioridade</th><th>Tema</th><th>Limitacao/problema</th><th>Recomendacao</th></tr></thead>
      <tbody id="e4RecBody"></tbody>
    </table></div></div>
  </section>

  <!-- ABA 5b — ETAPA 5 -->
  <section id="te5" class="panel">
    <span class="section-tag">Etapa 5</span>
    <h1>Precificação e margem</h1>
    <p class="lead">Margem bruta realizada, markup, desconto efetivo vs. preço de lista e dispersão de
       preço entre lojas. Tudo na mesma unidade (armazenagem) e com a Loja 93 (atacado/B2B) segregada.
       Termos em linguagem de negócio na aba <b>Glossário comercial</b>.</p>
    <div class="kpi-grid" id="e5KpiGrid"></div>
    <div class="method">
      <b>Metodologia:</b> preço praticado = <code>RECEITA / QTD_ARMAZENAGEM</code>; custo médio =
      <code>PRECO_UNIT_UNIDADE_COMPRA / CONVERSAO_COMPRA_ARMAZENAGEM</code> (ponderado pela quantidade
      comprada). Margem bruta % = (preço − custo) / preço; markup = preço / custo. O desconto efetivo
      compara preço praticado e preço de lista <b>dentro da mesma embalagem</b>; a dispersão é o coeficiente
      de variação do preço entre lojas, <b>separado por embalagem</b>.
      <br><br><b>Limitações:</b> a margem realizada só existe para os ~261 SKUs com custo de compra válido
      (~16% da receita) — o restante fica <b>sem margem por ausência de dado, não por erro</b>. O custo é a
      média do período (sem camadas PEPS nem custo de reposição); o preço de lista pode não refletir promoções
      pontuais, então o desconto efetivo é uma aproximação. Margens negativas (preço &lt; custo) são
      <b>sinalizadas, não silenciadas</b>.
    </div>

    <h2>Margem por categoria (rede física)</h2>
    <p class="lead">Ordenado por margem. <code>Cobertura</code> = quanto da receita da categoria tem custo
       conhecido — margens com cobertura muito baixa não são representativas.</p>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Categoria N1</th><th class="num">Receita c/ custo</th><th class="num">Cobertura</th>
        <th class="num">Margem %</th><th class="num">Markup</th><th class="num">SKUs c/ custo</th></tr></thead>
      <tbody id="e5CatBody"></tbody>
    </table></div></div>

    <h2>Melhores e piores margens (curva A, rede física)</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Tipo</th><th>Produto</th><th>Categoria</th><th class="num">Receita</th>
        <th class="num">Preço praticado</th><th class="num">Custo médio</th><th class="num">Margem %</th>
        <th class="num">Markup</th></tr></thead>
      <tbody id="e5SkuBody"></tbody>
    </table></div></div>

    <h2>Candidatos a repricing (rede física)</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Rank</th><th>Prioridade</th><th>Motivos</th><th>Loja</th><th>Produto</th>
        <th class="num">Receita</th><th class="num">Margem %</th><th class="num">Desconto efetivo</th></tr></thead>
      <tbody id="e5CandBody"></tbody>
    </table></div></div>

    <h2>Revisão de qualidade (autoaudit antes/depois)</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Problema</th><th>Antes</th><th>Depois</th></tr></thead>
      <tbody id="e5AuditBody"></tbody>
    </table></div></div>
  </section>

  <!-- ABA 5c — ETAPA 6 -->
  <section id="te6" class="panel">
    <span class="section-tag">Etapa 6</span>
    <h1>Projecao de compras para 90 dias</h1>
    <p class="lead">Plano operacional de compra no grao loja x SKU, usando cobertura, demanda historica,
       custo valido e sinais de margem. A rede fisica fica separada da Loja 93/B2B, com reconciliacao em
       <code>REDE_COMPLETA</code>.</p>
    <div class="kpi-grid" id="e6KpiGrid"></div>
    <div class="method">
      <b>Metodologia:</b> quantidade recomendada =
      <code>max(venda media mensal x 3 - estoque utilizavel, 0)</code>, arredondada para cima na unidade
      de armazenagem, apenas para pares em ruptura, critico ou atencao com demanda observada. Estoque
      projetado negativo vira zero utilizavel, nao uma divida adicional. Investimento so e estimado quando
      ha custo valido na Etapa 5; itens sem custo permanecem com quantidade operacional, mas sem budget.
    </div>

    <h2>Top categorias por quantidade recomendada</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Universo</th><th>Categoria N1</th><th class="num">Pares compra</th>
        <th class="num">Qtd recomendada</th><th class="num">Investimento conhecido</th>
        <th class="num">Cobertura custo</th></tr></thead>
      <tbody id="e6CatBody"></tbody>
    </table></div></div>

    <h2>Top lojas por quantidade recomendada</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Universo</th><th>Loja</th><th>Cidade/UF</th><th class="num">Pares compra</th>
        <th class="num">Qtd recomendada</th><th class="num">Investimento conhecido</th></tr></thead>
      <tbody id="e6LojaBody"></tbody>
    </table></div></div>

    <h2>Prioridades de compra</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Escopo</th><th>Rank</th><th>Prioridade</th><th>Loja</th><th>Produto</th>
        <th class="num">Qtd</th><th class="num">Investimento</th><th>Status orcamento</th></tr></thead>
      <tbody id="e6PrioBody"></tbody>
    </table></div></div>

    <h2>Autoaudit / revisao critica</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Risco</th><th>Controle aplicado</th><th>Evidencia</th><th>Risco remanescente</th></tr></thead>
      <tbody id="e6AuditBody"></tbody>
    </table></div></div>
  </section>

  <!-- ABA ETAPA 7 -->
  <section id="te7" class="panel">
    <span class="section-tag">Etapa 7</span>
    <h1>Recomendações finais e plano de execução</h1>
    <p class="lead">Síntese de decisão: consolida as Etapas 3-6 e classifica cada par loja × SKU em uma de quatro
       ações comerciais — <b>comprar</b>, <b>reprecificar</b>, <b>promover/queimar estoque</b> ou <b>descontinuar</b>.
       Cada par recebe uma <b>ação primária</b> por precedência, para não dupla contar capital nem quantidade.
       Termos em linguagem de negócio na aba <b>Glossário comercial</b>.</p>
    <div class="kpi-grid" id="e7KpiGrid"></div>
    <div class="method">
      <b>Metodologia:</b> precedência <code>DESCONTINUAR &gt; PROMOVER &gt; REPRECIFICAR &gt; COMPRAR</code>.
      Descontinuar = sem venda com estoque parado e curva ABC ≠ A (o campeão curva A parado é protegido e vai
      para promover/transferir). Promover = cobertura acima de 180 dias. Reprecificar vem dos candidatos da
      Etapa 5, separando <b>sinal de margem auditável</b> (item com custo e margem baixa/negativa) de
      <b>sinal de preço/lista</b> (desconto alto ou preço fora da faixa, com ou sem custo).
      Comprar vem da fila da Etapa 6. Valor financeiro (capital, encalhe, investimento) só existe com custo válido.
    </div>

    <h2>Ações por universo</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Universo</th><th>Ação</th><th class="num">Pares</th><th class="num">SKUs</th>
        <th class="num">Pares c/ valor</th><th class="num">Valor conhecido</th><th class="num">Cobertura custo</th></tr></thead>
      <tbody id="e7AcaoBody"></tbody>
    </table></div></div>

    <h2>Top categorias por ação (rede física)</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Ação</th><th>Categoria N1</th><th class="num">Pares</th>
        <th class="num">Valor conhecido</th></tr></thead>
      <tbody id="e7CatBody"></tbody>
    </table></div></div>

    <h2>Fila priorizada de execução</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Escopo</th><th class="num">Rank</th><th>Prioridade</th><th>Ação</th><th>Loja</th>
        <th>Produto</th><th class="num">Valor da ação</th></tr></thead>
      <tbody id="e7PrioBody"></tbody>
    </table></div></div>

    <h2>Autoaudit / revisão crítica</h2>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Risco</th><th>Controle aplicado</th><th>Evidencia</th><th>Risco remanescente</th></tr></thead>
      <tbody id="e7AuditBody"></tbody>
    </table></div></div>
  </section>

  <!-- ABA 6 -->
  <section id="t6" class="panel">
    <span class="section-tag">Revisão de qualidade</span>
    <h1>Bugs encontrados e corrigidos</h1>
    <p class="lead">Quatro problemas identificados na revisão, com como foram descobertos, a correção
       e o impacto numérico mensurável.</p>
    <div id="bugList"></div>
  </section>

  <!-- ABA 7 -->
  <section id="t7" class="panel">
    <span class="section-tag">Achados de negócio</span>
    <h1>Inconsistências nos dados</h1>
    <p class="lead">Achados relevantes que <b>não são bugs</b> de código, mas sinais de negócio a
       acompanhar. Cada um traz o achado, a hipótese de causa e o status.</p>
    <div id="findingList"></div>
  </section>

  <!-- ABA 8 -->
  <section id="t8" class="panel">
    <span class="section-tag">Referência</span>
    <h1>Dicionário de dados</h1>
    <p class="lead">Campos das bases tratadas e dos principais outputs analíticos, agrupados por
       tabela/arquivo. Use a busca para filtrar por nome, descrição ou tabela.</p>
    <div class="toolbar"><input class="search" id="dicSearch" placeholder="Buscar campo, tabela ou descrição…"></div>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th>Campo</th><th>Descrição</th><th>Tipo</th><th>Tratamento</th></tr></thead>
      <tbody id="dicBody"></tbody>
    </table></div></div>
  </section>

  <!-- ABA 9 -->
  <section id="t9" class="panel">
    <span class="section-tag">Referência</span>
    <h1>Glossário comercial</h1>
    <p class="lead">Tradução em linguagem de negócio dos termos técnicos usados no relatório, nos
       notebooks e na documentação. Pensado para quem é de áreas como comercial, marketing e compras
       e não precisa conhecer o detalhe técnico para ler os resultados.</p>
    <div class="card" style="background:var(--accent-soft);border-color:var(--accent)">
      <b>Leitura rápida do que mais importa:</b> esta análise reconstrói o estoque de cada produto em
      cada loja a partir do histórico (estoque de abertura + compras − vendas) e usa a receita que cada
      item já gerou para montar uma <b>fila de prioridade de reposição</b>. Os percentuais altos de
      "ruptura" indicam <b>o que olhar primeiro</b>, não que as prateleiras estejam literalmente vazias.
    </div>
    <div class="table-wrap"><div class="table-scroll"><table>
      <thead><tr><th style="width:230px">Termo técnico</th><th>O que significa, em linguagem comercial</th></tr></thead>
      <tbody>
        <tr><td><b>SKU</b></td><td>Código único de um produto. Cada item distinto do catálogo é um SKU
          (cores, tamanhos ou voltagens diferentes contam como SKUs diferentes).</td></tr>
        <tr><td><b>Par loja × produto</b></td><td>Um produto específico dentro de uma loja específica. É o
          menor nível de detalhe da análise de estoque: o mesmo produto em duas lojas são dois pares.</td></tr>
        <tr><td><b>Unidade de armazenagem</b></td><td>A unidade padrão de contagem no estoque (por ex. a caixa).
          Convertemos tudo para ela para não somar "3 caixas" com "5 unidades soltas" como se fossem iguais.</td></tr>
        <tr><td><b>Estoque projetado</b></td><td>Estimativa do saldo de cada item, reconstruída pela conta
          <i>estoque de abertura + compras − vendas</i>. <b>Não é uma contagem física</b> de prateleira.</td></tr>
        <tr><td><b>Snapshot (foto)</b></td><td>A situação do estoque num momento específico — aqui, o fim do
          período analisado (dez/2025).</td></tr>
        <tr><td><b>Cobertura (dias de estoque)</b></td><td>Por quantos dias o estoque atual daria conta da venda
          média. Pouca cobertura = risco de faltar produto em breve.</td></tr>
        <tr><td><b>Ruptura</b></td><td>Item com estoque estimado zerado ou negativo — ou seja, sem saldo para
          vender segundo o histórico disponível.</td></tr>
        <tr><td><b>Crítico / Atenção / Saudável</b></td><td>Faixas de risco de estoque: <b>crítico</b> ≤ 30 dias
          de cobertura, <b>atenção</b> até 90 dias, <b>saudável</b> acima disso.</td></tr>
        <tr><td><b>Receita em risco</b></td><td>Quanto de receita esses itens <b>já geraram no passado</b>. Serve
          para ordenar a fila de reposição (repor primeiro o que mais vende) — <b>não é uma perda prevista</b>.</td></tr>
        <tr><td><b>Curva ABC</b></td><td>Regra de Pareto aplicada à receita: a <b>classe A</b> são os poucos
          produtos que somam ~80% do faturamento; B e C têm peso decrescente.</td></tr>
        <tr><td><b>Preço praticado</b></td><td>O preço médio que de fato saiu no caixa, por unidade de
          armazenagem (receita ÷ quantidade). É o preço real de venda, não o de tabela.</td></tr>
        <tr><td><b>Custo médio (CMV)</b></td><td>Quanto custou, em média, repor uma unidade — a média
          ponderada do preço de compra no período. Só existe para itens com compra registrada.</td></tr>
        <tr><td><b>Margem bruta (R$ e %)</b></td><td>O que sobra depois de pagar o custo: em reais
          (preço − custo) e em proporção do preço (margem ÷ preço). Margem 50% = metade do preço é lucro bruto.</td></tr>
        <tr><td><b>Markup</b></td><td>Quantas vezes o preço cobre o custo (preço ÷ custo). Markup 2× = o preço
          é o dobro do custo. É outra forma de ver a margem.</td></tr>
        <tr><td><b>Preço de lista</b></td><td>O preço de tabela cadastrado para o produto em cada loja e
          embalagem — o preço "cheio", antes de desconto.</td></tr>
        <tr><td><b>Desconto efetivo</b></td><td>Quanto o preço praticado ficou abaixo da tabela
          (lista − praticado ÷ lista). Sempre comparado dentro da mesma embalagem. Desconto negativo = vendeu
          acima da tabela (lista possivelmente desatualizada).</td></tr>
        <tr><td><b>Dispersão de preço</b></td><td>O quanto o preço do mesmo produto varia entre lojas. Medido
          por embalagem, para não confundir o preço da "caixa" com o da "unidade".</td></tr>
        <tr><td><b>Repricing</b></td><td>Revisão de preço de itens com margem baixa/negativa, desconto fora do
          padrão ou preço fora da faixa da rede.</td></tr>
        <tr><td><b>Cobertura de custo</b></td><td>Quanto da receita está coberta por itens com custo conhecido.
          Aqui é ~16%: a margem realizada só vale para esse subconjunto.</td></tr>
        <tr><td><b>Rede física × atacado/B2B (Loja 93)</b></td><td>A Loja 93 vende em grande volume para outras
          empresas (atacado), com ticket ~20× o das demais. Por isso ela é mostrada à parte, para não distorcer
          a média das lojas de varejo.</td></tr>
        <tr><td><b>Linhas de venda (TRANSACOES)</b></td><td>Cada linha de item vendido. Não é o número de
          cupons/notas, porque a base não traz um identificador de cupom — por isso é uma medida aproximada.</td></tr>
        <tr><td><b>Proxy</b></td><td>Uma medida aproximada usada quando o dado ideal não existe na base
          (ex.: usar linhas de venda no lugar de número de cupons).</td></tr>
        <tr><td><b>Ticket médio</b></td><td>Receita média por linha de venda. Aqui é uma aproximação, pela mesma
          ausência de identificador de cupom.</td></tr>
        <tr><td><b>Variação ano contra ano (YoY)</b></td><td>Comparação de um período com o mesmo período do ano
          anterior (ex.: 2025 vs 2024), para isolar o efeito de sazonalidade.</td></tr>
        <tr><td><b>Conservador (por construção)</b></td><td>Quando há dúvida, o método assume o pior cenário
          (falta de estoque). Ele erra para <b>alertar a mais</b>, nunca a menos — é uma escolha de segurança.</td></tr>
        <tr><td><b>Integridade referencial</b></td><td>Garantia de que os códigos batem entre as tabelas: todo
          produto vendido existe no cadastro e toda venda pertence a uma loja válida.</td></tr>
        <tr><td><b>Parquet</b></td><td>Formato de arquivo compactado e rápido para grandes volumes de dados,
          usado internamente para acelerar o processamento (não precisa ser aberto manualmente).</td></tr>
        <tr><td><b>Skeleton (malha base)</b></td><td>A grade inicial com todas as combinações loja × produto × mês,
          montada <b>antes</b> de preencher vendas e compras — garante que nenhum item suma da conta de estoque.</td></tr>
      </tbody>
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
const kpiDefs=[["receita_total","Receita total (24M)"],["transacoes","Linhas de venda"],
  ["skus","SKUs ativos"],["lojas","Lojas"],["categorias","Categorias (N1)"],["periodo","Período"]];
document.getElementById("kpiGrid").innerHTML = kpiDefs.map(([k,l])=>
  `<div class="kpi"><div class="v">${esc(DATA.kpis[k])}</div><div class="l">${l}</div></div>`).join("");
const steps=[["1","Etapa 1","Entendimento e limpeza dos dados brutos"],
  ["2","Etapa 2","Estoque projetado e cobertura"],
  ["3","Etapa 3","Desempenho de vendas, ABC e sazonalidade"],
  ["4","Etapa 4","Cobertura por categoria e loja"],
  ["5","Etapa 5","Precificação e variação de margem"],
  ["6","Etapa 6","Projeção de compras para 90 dias"],
  ["7","Etapa 7","Recomendações finais e execução"],
  ["8","Revisão","Correções e limitações documentadas"]];
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

/* ---- ABA 5: bugs ---- */
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

/* ---- ABA 6: findings ---- */
document.getElementById("findingList").innerHTML = DATA.inconsistencias.map(f=>`
  <div class="finding">
    <h3>${esc(f.titulo)}
      <span class="badge ${f.status==='pendente'?'st-pendente':'st-investigado'}">${f.status}</span></h3>
    <div class="meta"><b>Achado:</b> ${esc(f.achado)}</div>
    <div class="meta"><b>Hipótese:</b> ${esc(f.hipotese)}</div>
  </div>`).join("");

/* ---- ABA 7: dicionário ---- */
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

/* ---- ABA 4: etapa 3 ---- */
if(DATA.etapa3){
  const e3Kpis=[
    ["receita_completa","Receita rede completa"],
    ["linhas_completa","Linhas de venda"],
    ["loja93_receita_pct","Participação Loja 93"],
    ["receita_fisica","Receita rede física"],
    ["abc_a","Curva A"],
    ["validacoes","Validações"]
  ];
  document.getElementById("e3KpiGrid").innerHTML = e3Kpis.map(([k,l])=>
    `<div class="kpi"><div class="v">${esc(DATA.etapa3.kpis[k])}</div><div class="l">${l}</div></div>`).join("");
  document.getElementById("e3CatBody").innerHTML = DATA.etapa3.categorias.map(r=>
    `<tr><td>${esc(r.universo)}</td><td>${esc(r.categoria)}</td><td class="num">${esc(r.receita)}</td>`+
    `<td class="num">${esc(r.participacao)}</td><td class="num">${esc(r.var_yoy)}</td></tr>`).join("");
  document.getElementById("e3LojaBody").innerHTML = DATA.etapa3.lojas.map(r=>
    `<tr><td>${esc(r.universo)}</td><td>${esc(r.loja)}</td><td>${esc(r.cidade)}</td>`+
    `<td>${esc(r.operacao)}</td><td class="num">${esc(r.receita)}</td>`+
    `<td class="num">${esc(r.linhas)}</td><td class="num">${esc(r.receita_media)}</td></tr>`).join("");
  document.getElementById("e3RecBody").innerHTML = DATA.etapa3.recomendacoes.map(r=>
    `<tr><td><span class="badge ${r.prioridade==='ALTA'?'sev-critico':'sev-medio'}">${esc(r.prioridade)}</span></td>`+
    `<td><b>${esc(r.tema)}</b></td><td>${esc(r.problema)}</td>`+
    `<td>${esc(r.recomendacao)}</td><td>${esc(r.impacto)}</td></tr>`).join("");
}

/* ---- ABA 5: etapa 4 ---- */
if(DATA.etapa4){
  const e4Kpis=[
    ["pares_total","Pares loja x produto"],
    ["pares_risco_pct","Pares em risco"],
    ["receita_risco_total","Receita em risco"],
    ["receita_risco_fisica","Risco rede fisica"],
    ["top_categoria_fisica","Top categoria fisica"],
    ["validacoes","Validacoes"]
  ];
  document.getElementById("e4KpiGrid").innerHTML = e4Kpis.map(([k,l])=>
    `<div class="kpi"><div class="v">${esc(DATA.etapa4.kpis[k])}</div><div class="l">${l}</div></div>`).join("");
  document.getElementById("e4CatBody").innerHTML = DATA.etapa4.categorias.map(r=>
    `<tr><td>${esc(r.universo)}</td><td>${esc(r.categoria)}</td><td class="num">${esc(r.receita_risco)}</td>`+
    `<td class="num">${esc(r.pares_risco)}</td><td class="num">${esc(r.pct_pares)}</td>`+
    `<td class="num">${esc(r.mediana_dias)}</td></tr>`).join("");
  document.getElementById("e4LojaBody").innerHTML = DATA.etapa4.lojas.map(r=>
    `<tr><td>${esc(r.universo)}</td><td>${esc(r.loja)}</td><td>${esc(r.cidade)}</td>`+
    `<td>${esc(r.operacao)}</td><td class="num">${esc(r.receita_risco)}</td>`+
    `<td class="num">${esc(r.pct_pares)}</td></tr>`).join("");
  document.getElementById("e4PrioBody").innerHTML = DATA.etapa4.prioridades.map(r=>
    `<tr><td>${esc(r.escopo)}</td><td class="num">${esc(r.rank)}</td>`+
    `<td><span class="badge ${r.faixa==='ALTA'?'sev-critico':(r.faixa==='MÉDIA'?'sev-medio':'b-baixo')}">${esc(r.faixa)}</span></td>`+
    `<td>${esc(r.loja)}</td><td>${esc(r.categoria)}</td><td class="num">${esc(r.receita_risco)}</td>`+
    `<td>${esc(r.acao)}</td></tr>`).join("");
  document.getElementById("e4RecBody").innerHTML = DATA.etapa4.recomendacoes.map(r=>
    `<tr><td><span class="badge ${r.prioridade==='ALTA'?'sev-critico':'sev-medio'}">${esc(r.prioridade)}</span></td>`+
    `<td><b>${esc(r.tema)}</b></td><td>${esc(r.problema)}</td><td>${esc(r.recomendacao)}</td></tr>`).join("");
}

/* ---- ABA 5b: etapa 5 (precificacao e margem) ---- */
if(DATA.etapa5){
  const e5Kpis=[
    ["margem_fisica","Margem % rede física"],
    ["cobertura_custo","Cobertura de custo (receita)"],
    ["skus_custo","SKUs com custo"],
    ["desconto_medio","Desconto efetivo médio"],
    ["candidatos","Candidatos a repricing"],
    ["validacoes","Validações"]
  ];
  document.getElementById("e5KpiGrid").innerHTML = e5Kpis.map(([k,l])=>
    `<div class="kpi"><div class="v">${esc(DATA.etapa5.kpis[k])}</div><div class="l">${l}</div></div>`).join("");
  document.getElementById("e5CatBody").innerHTML = DATA.etapa5.categorias.map(r=>
    `<tr><td>${esc(r.categoria)}</td><td class="num">${esc(r.receita_custo)}</td>`+
    `<td class="num">${esc(r.cobertura)}</td><td class="num">${esc(r.margem)}</td>`+
    `<td class="num">${esc(r.markup)}</td><td class="num">${esc(r.skus_custo)}</td></tr>`).join("");
  document.getElementById("e5SkuBody").innerHTML = DATA.etapa5.skus.map(r=>
    `<tr><td><span class="badge ${r.tipo==='Melhor'?'b-ok':'b-alto'}">${esc(r.tipo)}</span></td>`+
    `<td><b>${esc(r.codigo)}</b><br><span class="muted">${esc(r.desc)}</span></td>`+
    `<td>${esc(r.nivel1)}</td><td class="num">${esc(r.receita)}</td>`+
    `<td class="num">${esc(r.preco)}</td><td class="num">${esc(r.custo)}</td>`+
    `<td class="num">${esc(r.margem)}</td><td class="num">${esc(r.markup)}</td></tr>`).join("");
  document.getElementById("e5CandBody").innerHTML = DATA.etapa5.candidatos.map(r=>
    `<tr><td class="num">${esc(r.rank)}</td>`+
    `<td><span class="badge ${r.faixa==='ALTA'?'sev-critico':(r.faixa==='MEDIA'?'sev-medio':'b-baixo')}">${esc(r.faixa)}</span></td>`+
    `<td>${esc(r.motivos)}</td><td>${esc(r.loja)}</td>`+
    `<td><b>${esc(r.codigo)}</b><br><span class="muted">${esc(r.desc)}</span></td>`+
    `<td class="num">${esc(r.receita)}</td><td class="num">${esc(r.margem)}</td>`+
    `<td class="num">${esc(r.desconto)}</td></tr>`).join("");
  document.getElementById("e5AuditBody").innerHTML = DATA.etapa5.autoaudit.map(r=>
    `<tr><td><b>${esc(r.problema)}</b></td><td>${esc(r.antes)}</td><td>${esc(r.depois)}</td></tr>`).join("");
}

/* ---- ABA 5c: etapa 6 (projecao de compras) ---- */
if(DATA.etapa6){
  const e6Kpis=[
    ["pares_compra","Pares com compra"],
    ["qtd_fisica","Qtd rede fisica"],
    ["invest_fisica","Investimento conhecido"],
    ["cobertura_custo","Cobertura custo"],
    ["alta_fisica","Prioridade ALTA"],
    ["validacoes","Validacoes"]
  ];
  document.getElementById("e6KpiGrid").innerHTML = e6Kpis.map(([k,l])=>
    `<div class="kpi"><div class="v">${esc(DATA.etapa6.kpis[k])}</div><div class="l">${l}</div></div>`).join("");
  document.getElementById("e6CatBody").innerHTML = DATA.etapa6.categorias.map(r=>
    `<tr><td>${esc(r.universo)}</td><td>${esc(r.categoria)}</td>`+
    `<td class="num">${esc(r.pares)}</td><td class="num">${esc(r.qtd)}</td>`+
    `<td class="num">${esc(r.investimento)}</td><td class="num">${esc(r.cobertura)}</td></tr>`).join("");
  document.getElementById("e6LojaBody").innerHTML = DATA.etapa6.lojas.map(r=>
    `<tr><td>${esc(r.universo)}</td><td>${esc(r.loja)}</td><td>${esc(r.cidade)}</td>`+
    `<td class="num">${esc(r.pares)}</td><td class="num">${esc(r.qtd)}</td>`+
    `<td class="num">${esc(r.investimento)}</td></tr>`).join("");
  document.getElementById("e6PrioBody").innerHTML = DATA.etapa6.prioridades.map(r=>
    `<tr><td>${esc(r.escopo)}</td><td class="num">${esc(r.rank)}</td>`+
    `<td><span class="badge ${r.faixa==='ALTA'?'sev-critico':(r.faixa==='MEDIA'?'sev-medio':'b-baixo')}">${esc(r.faixa)}</span></td>`+
    `<td>${esc(r.loja)}</td><td><b>${esc(r.codigo)}</b><br><span class="muted">${esc(r.desc)}</span></td>`+
    `<td class="num">${esc(r.qtd)}</td><td class="num">${esc(r.investimento)}</td>`+
    `<td>${esc(r.status_orcamento)}</td></tr>`).join("");
  document.getElementById("e6AuditBody").innerHTML = DATA.etapa6.autoaudit.map(r=>
    `<tr><td><b>${esc(r.risco)}</b></td><td>${esc(r.controle)}</td>`+
    `<td>${esc(r.evidencia)}</td><td>${esc(r.risco_remanescente)}</td></tr>`).join("");
}

if(DATA.etapa7){
  const e7Kpis=[
    ["comprar","Pares comprar"],
    ["reprecificar","Pares reprecificar"],
    ["promover","Pares promover"],
    ["descontinuar","Pares descontinuar"],
    ["valor_encalhe","Encalhe c/ custo"],
    ["validacoes","Validacoes"]
  ];
  document.getElementById("e7KpiGrid").innerHTML = e7Kpis.map(([k,l])=>
    `<div class="kpi"><div class="v">${esc(DATA.etapa7.kpis[k])}</div><div class="l">${l}</div></div>`).join("");
  const acaoBadge=a=>{
    const m={"COMPRAR":"b-baixo","REPRECIFICAR":"sev-medio","PROMOVER":"sev-medio","DESCONTINUAR":"sev-critico"};
    return `<span class="badge ${m[a]||'b-baixo'}">${esc(a)}</span>`;
  };
  document.getElementById("e7AcaoBody").innerHTML = DATA.etapa7.acoes.map(r=>
    `<tr><td>${esc(r.universo)}</td><td>${acaoBadge(r.acao)}</td>`+
    `<td class="num">${esc(r.pares)}</td><td class="num">${esc(r.skus)}</td>`+
    `<td class="num">${esc(r.pares_valor)}</td><td class="num">${esc(r.valor)}</td>`+
    `<td class="num">${esc(r.cobertura)}</td></tr>`).join("");
  document.getElementById("e7CatBody").innerHTML = DATA.etapa7.categorias.map(r=>
    `<tr><td>${acaoBadge(r.acao)}</td><td>${esc(r.categoria)}</td>`+
    `<td class="num">${esc(r.pares)}</td><td class="num">${esc(r.valor)}</td></tr>`).join("");
  document.getElementById("e7PrioBody").innerHTML = DATA.etapa7.prioridades.map(r=>
    `<tr><td>${esc(r.escopo)}</td><td class="num">${esc(r.rank)}</td>`+
    `<td><span class="badge ${r.faixa==='ALTA'?'sev-critico':(r.faixa==='MEDIA'?'sev-medio':'b-baixo')}">${esc(r.faixa)}</span></td>`+
    `<td>${acaoBadge(r.acao)}</td><td>${esc(r.loja)}</td>`+
    `<td><b>${esc(r.codigo)}</b><br><span class="muted">${esc(r.desc)}</span></td>`+
    `<td class="num">${esc(r.valor)}</td></tr>`).join("");
  document.getElementById("e7AuditBody").innerHTML = DATA.etapa7.autoaudit.map(r=>
    `<tr><td><b>${esc(r.risco)}</b></td><td>${esc(r.controle)}</td>`+
    `<td>${esc(r.evidencia)}</td><td>${esc(r.risco_remanescente)}</td></tr>`).join("");
}

/* ---- footer ---- */
document.getElementById("footer").innerHTML =
  `Relatório gerado em <b>${esc(DATA.gerado_em)}</b> · Fonte: bases tratadas em `+
  `<code>data/processed/</code> e saídas em <code>outputs/etapa1</code>…<code>outputs/etapa7</code> · `+
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
    "campo": str(r.campo),
    "problema": str(r.problema).replace("transação de venda", "linha de venda").replace("transações de venda", "linhas de venda"),
    "tratamento": str(r.tratamento).replace("transação de venda", "linha de venda").replace("transações de venda", "linhas de venda"),
    "justificativa": str(r.justificativa).replace("transação de venda", "linha de venda").replace("transações de venda", "linhas de venda"),
    "impacto": str(r.impacto).strip().upper(),
} for r in dec.itertuples()]

# ---- Dicionário de dados consolidado ----
def tipo_coluna(series: pd.Series) -> str:
    if pd.api.types.is_integer_dtype(series):
        return "Integer"
    if pd.api.types.is_float_dtype(series):
        return "Float"
    return "String"


DESCRICOES_COLUNAS = {
    "UNIVERSO": "Universo analítico: rede completa ou rede física sem Loja 93.",
    "CODIGO": "Código do produto.",
    "COD_EMPRESA": "Código da loja.",
    "DESCRICAO": "Descrição comercial do produto.",
    "NIVEL_1": "Categoria de produto nível 1.",
    "NIVEL_2": "Categoria de produto nível 2.",
    "NIVEL_3": "Categoria de produto nível 3.",
    "CD_CIDADE": "Cidade da loja.",
    "CD_ESTADO": "Estado da loja.",
    "TIPO_OPERACAO": "Classificação operacional usada na análise: rede física ou Loja 93 atacado/B2B.",
    "FLAG_LOJA93": "Flag 1/0 indicando se a loja é a Loja 93.",
    "RECEITA": "Receita bruta calculada a partir de quantidade vendida e preço unitário médio.",
    "RECEITA_TOTAL": "Receita histórica total do par loja×produto.",
    "QTD_ARMAZENAGEM": "Quantidade vendida normalizada para unidade de armazenagem.",
    "QUANTIDADE_VENDIDA": "Quantidade vendida na unidade comercial original.",
    "TRANSACOES": "Contagem de linhas de venda; proxy, não cupom único.",
    "SKUS_ATIVOS": "Quantidade de SKUs distintos com venda no agrupamento.",
    "LOJAS_ATIVAS": "Quantidade de lojas distintas no agrupamento.",
    "PRECO_MEDIO_ARMAZENAGEM": "Receita dividida por quantidade em unidade de armazenagem.",
    "TICKET_MEDIO_TRANSACAO": "Receita média por linha de venda; proxy devido à ausência de id de cupom/pedido/nota.",
    "PARTICIPACAO_RECEITA_PCT": "Participação percentual da receita dentro do universo analisado.",
    "PARTICIPACAO_QTD_PCT": "Participação percentual da quantidade dentro do universo analisado.",
    "RANK_RECEITA": "Ranking decrescente por receita.",
    "RANK_RECEITA_MENOR": "Ranking crescente por receita, usado para identificar cauda de menor venda.",
    "RECEITA_ACUM": "Receita acumulada no ranking.",
    "RECEITA_ACUM_PCT": "Percentual acumulado da receita no ranking.",
    "CURVA_ABC_RECEITA": "Classe ABC por receita acumulada: A até 80%, B até 95%, C restante.",
    "RANK_QUANTIDADE": "Ranking decrescente por quantidade em unidade de armazenagem.",
    "RANK_QUANTIDADE_MENOR": "Ranking crescente por quantidade, usado para identificar cauda de menor venda.",
    "QTD_ACUM_ARMAZENAGEM": "Quantidade acumulada no ranking por volume.",
    "QTD_ACUM_PCT": "Percentual acumulado da quantidade no ranking por volume.",
    "ESTOQUE_PROJ": "Estoque projetado no snapshot final de dez/2025.",
    "VENDA_MEDIA_MES": "Venda média mensal em unidade de armazenagem usada para cobertura.",
    "DIAS_COBERTURA": "Dias estimados de cobertura de estoque.",
    "STATUS_ESTOQUE": "Classificação de cobertura: ruptura, crítico, atenção, saudável ou sem venda.",
    "PARES_LOJA_PRODUTO": "Quantidade de pares loja x produto no agrupamento.",
    "SKUS_DISTINTOS": "Quantidade de produtos distintos no agrupamento de cobertura.",
    "LINHAS": "Contagem de linhas de venda (proxy de transações) no agrupamento.",
    "RECEITA_MEDIA_LINHA": "Receita média por linha de venda no período (receita ÷ linhas).",
    "LOJAS_DISTINTAS": "Quantidade de lojas distintas no agrupamento de cobertura.",
    "RECEITA_HISTORICA_TOTAL": "Receita histórica dos pares loja x produto do agrupamento.",
    "RECEITA_RUPTURA_CRITICO": "Receita histórica dos pares em status EM RUPTURA ou CRÍTICO.",
    "RECEITA_EM_RUPTURA": "Receita histórica dos pares em status EM RUPTURA.",
    "RECEITA_CRITICO": "Receita histórica dos pares em status CRÍTICO.",
    "PARES_RUPTURA_CRITICO": "Quantidade de pares com status EM RUPTURA ou CRÍTICO.",
    "PARES_COM_RECEITA_HISTORICA": "Quantidade de pares com receita histórica maior que zero.",
    "PARES_SEM_RECEITA_HISTORICA": "Quantidade de pares sem receita histórica no período.",
    "PARES_DIAS_COBERTURA_FINITO": "Quantidade de pares com DIAS_COBERTURA finito.",
    "PARES_DIAS_COBERTURA_INFINITO": "Quantidade de pares com DIAS_COBERTURA infinito.",
    "DIAS_COBERTURA_MEDIA_FINITA": "Média de dias de cobertura calculada somente sobre valores finitos.",
    "DIAS_COBERTURA_MEDIANA_FINITA": "Mediana de dias de cobertura calculada somente sobre valores finitos.",
    "DIAS_COBERTURA_P25_FINITA": "Percentil 25 de dias de cobertura calculado somente sobre valores finitos.",
    "DIAS_COBERTURA_P75_FINITA": "Percentil 75 de dias de cobertura calculado somente sobre valores finitos.",
    "PCT_PARES_RUPTURA_CRITICO": "Percentual de pares em ruptura/crítico no agrupamento.",
    "PART_RECEITA_RISCO_PCT": "Participação da receita em risco dentro da receita histórica do agrupamento.",
    "PART_RECEITA_RISCO_UNIVERSO_PCT": "Participação da receita em risco do agrupamento na receita histórica do universo.",
    "RANK_REPOSICAO": "Ranking de reposição dentro do universo, ordenado por receita histórica em risco.",
    "ESCOPO_PRIORIZACAO": "Escopo operacional usado na priorização: rede física sem Loja 93 ou Loja 93 atacado/B2B.",
    "RANK_PRIORIDADE_ESCOPO": "Ranking de prioridade dentro do escopo operacional.",
    "FAIXA_PRIORIDADE": "Faixa derivada do ranking dentro do escopo: ALTA, MÉDIA ou MONITORAR.",
    "ACAO_RECOMENDADA": "Ação operacional recomendada a partir da priorização de cobertura.",
    "EVIDENCIA_PRIORIZACAO": "Resumo textual da evidência numérica usada para priorizar.",
    "ANO_MES": "Período mensal no formato YYYY-MM.",
    "ANO": "Ano da venda.",
    "MES": "Mês da venda.",
    "RECEITA_2024": "Receita agregada em 2024.",
    "RECEITA_2025": "Receita agregada em 2025.",
    "QTD_ARMAZENAGEM_2024": "Quantidade em unidade de armazenagem agregada em 2024.",
    "QTD_ARMAZENAGEM_2025": "Quantidade em unidade de armazenagem agregada em 2025.",
    "TRANSACOES_2024": "Linhas de venda agregadas em 2024.",
    "TRANSACOES_2025": "Linhas de venda agregadas em 2025.",
    "DELTA_RECEITA_2025_VS_2024": "Diferença absoluta de receita entre 2025 e 2024.",
    "VAR_RECEITA_2025_VS_2024_PCT": "Variação percentual de receita entre 2025 e 2024.",
    "DELTA_QTD_ARMAZENAGEM_2025_VS_2024": "Diferença absoluta de quantidade entre 2025 e 2024.",
    "VAR_QTD_ARMAZENAGEM_2025_VS_2024_PCT": "Variação percentual de quantidade entre 2025 e 2024.",
    "DELTA_TRANSACOES_2025_VS_2024": "Diferença absoluta de linhas de venda entre 2025 e 2024.",
    "VAR_TRANSACOES_2025_VS_2024_PCT": "Variação percentual de linhas de venda entre 2025 e 2024.",
    "SEGMENTO": "Segmento usado no resumo de impacto da Loja 93.",
    "PARTICIPACAO_RECEITA_REDE_COMPLETA_PCT": "Participação do segmento na receita da rede completa.",
    "PARTICIPACAO_QTD_REDE_COMPLETA_PCT": "Participação do segmento na quantidade da rede completa.",
    "PARTICIPACAO_TRANSACOES_REDE_COMPLETA_PCT": "Participação do segmento nas linhas de venda da rede completa.",
    # ── Etapa 5: precificação e margem ──
    "SKUS": "Quantidade de SKUs distintos no agrupamento.",
    "SKUS_COM_CUSTO": "Quantidade de SKUs com custo de compra válido no agrupamento.",
    "LINHAS_VENDA": "Quantidade de linhas de venda no agrupamento (proxy de transações).",
    "RECEITA_TOTAL": "Receita total do agrupamento (todas as vendas).",
    "QTD_ARM_TOTAL": "Quantidade total em unidade de armazenagem do agrupamento.",
    "RECEITA_COM_CUSTO": "Receita das vendas de SKUs com custo conhecido (base da margem).",
    "QTD_ARM_COM_CUSTO": "Quantidade em armazenagem das vendas com custo conhecido.",
    "CMV": "Custo da mercadoria vendida: soma de custo médio por unidade × quantidade em armazenagem.",
    "PRECO_PRATICADO_ARM": "Preço praticado por unidade de armazenagem: receita ÷ quantidade em armazenagem.",
    "PRECO_PRATICADO_ARM_COM_CUSTO": "Preço praticado por unidade de armazenagem, restrito às vendas com custo.",
    "CUSTO_MEDIO_ARM": "Custo médio por unidade de armazenagem: preço de compra ponderado ÷ conversão de compra.",
    "CUSTO_MEDIO_ARM_PONDERADO": "Custo médio por unidade de armazenagem ponderado do agrupamento (CMV ÷ quantidade com custo).",
    "MARGEM_BRUTA_RS_UNIT": "Margem bruta por unidade de armazenagem: preço praticado − custo médio.",
    "MARGEM_BRUTA_RS": "Margem bruta por unidade de armazenagem do SKU: preço praticado − custo médio.",
    "MARGEM_BRUTA_TOTAL": "Margem bruta total do agrupamento: receita com custo − CMV.",
    "MARGEM_BRUTA_PCT": "Margem bruta percentual: margem bruta ÷ preço praticado (ou ÷ receita com custo no agregado).",
    "MARKUP": "Markup do SKU: preço praticado ÷ custo médio.",
    "MARKUP_PONDERADO": "Markup ponderado do agrupamento: receita com custo ÷ CMV.",
    "COBERTURA_CUSTO_RECEITA_PCT": "Percentual da receita do agrupamento que tem custo conhecido.",
    "PART_RECEITA_UNIVERSO_PCT": "Participação da receita do agrupamento na receita do universo.",
    "FLAG_MARGEM_NEGATIVA": "Flag 1/0 indicando margem bruta negativa (preço < custo).",
    "PRECO_COMPRA_PONDERADO_UNID_COMPRA": "Preço de compra médio ponderado por unidade de compra.",
    "CONVERSAO_COMPRA_ARMAZENAGEM": "Fator que converte a unidade de compra para a unidade de armazenagem.",
    "COMPRAS_LINHAS_COM_PRECO": "Quantidade de linhas de compra com preço usadas no custo do SKU.",
    "CURVA_ABC_RECEITA": "Classe ABC por receita acumulada: A até 80%, B até 95%, C restante.",
    "RANK_RECEITA": "Ranking decrescente por receita.",
    "QUANTIDADE_VENDIDA": "Quantidade vendida na unidade comercial original.",
    "EMBALAGEM": "Código da embalagem da venda (0 unidade, 1 caixa, 2 fardo/pacote maior).",
    "PRECO_PRATICADO_VENDA": "Preço praticado por unidade da embalagem vendida (mesma base do preço de lista).",
    "PRECO_LISTA_EMBALAGEM": "Preço de lista da mesma embalagem da venda (PRECO_EMBALAGEM_0/1/2).",
    "PRECO_EMBALAGEM_0": "Preço de lista cadastrado para a embalagem 0 (unidade).",
    "PRECO_EMBALAGEM_1": "Preço de lista cadastrado para a embalagem 1 (caixa).",
    "PRECO_EMBALAGEM_2": "Preço de lista cadastrado para a embalagem 2 (fardo/pacote maior).",
    "PERC_DESCTO_ADICIONAL_EMBALAGEM_0": "Percentual de desconto adicional de catálogo para a embalagem 0.",
    "DESCONTO_EFETIVO_PCT": "Desconto efetivo: (preço de lista − preço praticado) ÷ preço de lista, na mesma embalagem.",
    "DESCONTO_CATALOGO_PCT": "Desconto adicional cadastrado em catálogo (embalagem 0).",
    "FLAG_PRECO_ACIMA_LISTA": "Flag 1/0 indicando preço praticado acima do preço de lista (desconto negativo).",
    "FLAG_SEM_PRECO_LISTA": "Flag 1/0 indicando ausência de preço de lista para a embalagem.",
    "LOJAS_ATIVAS": "Quantidade de lojas distintas com venda do SKU.",
    "LOJAS": "Quantidade de lojas distintas com preço do SKU na embalagem.",
    "PRECO_ARM_MEDIO": "Preço médio por unidade de armazenagem entre lojas (SKU × embalagem).",
    "PRECO_ARM_MEDIANA": "Preço mediano por unidade de armazenagem entre lojas (SKU × embalagem).",
    "PRECO_ARM_DESVPAD": "Desvio padrão do preço por unidade de armazenagem entre lojas.",
    "PRECO_ARM_MIN": "Menor preço por unidade de armazenagem entre lojas.",
    "PRECO_ARM_MAX": "Maior preço por unidade de armazenagem entre lojas.",
    "CV_PRECO": "Coeficiente de variação do preço entre lojas (desvio padrão ÷ média), por embalagem.",
    "AMPLITUDE_PCT": "Amplitude do preço entre lojas: (máximo − mínimo) ÷ média.",
    "FLAG_DISPERSAO_ALTA": "Flag 1/0 indicando dispersão de preço alta (CV > 30%).",
    "RANK_PRIORIDADE": "Ranking de RISCO do candidato a repricing (score = nº de sinais + percentil de receita); fila de triagem.",
    "SCORE_PRIORIDADE": "Score de risco do candidato: nº de sinais + percentil de receita.",
    "RECEITA_PERCENTIL": "Percentil de receita do candidato dentro do conjunto de candidatos.",
    "RANK_IMPACTO": "Ranking de IMPACTO comercial do candidato (por dinheiro em jogo); fila complementar ao ranking de risco.",
    "FAIXA_IMPACTO": "Faixa do ranking de impacto: ALTA, MEDIA ou MONITORAR.",
    "IMPACTO_FINANCEIRO_ESTIMADO": "Impacto estimado do candidato: receita exposta × magnitude do sinal de preço/margem.",
    "MAGNITUDE_SINAL_PCT": "Maior magnitude (%) do sinal do item: desconto efetivo, desvio vs mediana ou distância da margem-alvo.",
    "FAIXA_PRIORIDADE": "Faixa de prioridade do candidato: ALTA, MEDIA ou MONITORAR.",
    "VALIDACAO": "Nome da checagem de reconciliação numérica executada.",
    "OBSERVADO": "Valor observado na checagem.",
    "ESPERADO": "Valor esperado na checagem.",
    "DIFERENCA": "Diferença entre observado e esperado.",
    "STATUS": "Resultado da checagem: OK ou FALHA.",
    "N_MOTIVOS": "Quantidade de sinais que tornam o item candidato a repricing.",
    "MOTIVOS": "Sinais identificados: margem baixa/negativa, desconto alto e/ou preço fora da faixa.",
    "PRECO_ARM_MEDIANA_REDE": "Preço mediano da rede para o SKU × embalagem, base da comparação de faixa.",
    "DESVIO_VS_MEDIANA_PCT": "Desvio percentual do preço da loja vs. a mediana da rede.",
    "LOJAS_NA_REDE": "Quantidade de lojas com preço do SKU × embalagem na rede.",
    "MOTIVO_MARGEM_BAIXA": "Flag 1/0: margem bruta abaixo do limiar (item com custo).",
    "MOTIVO_DESCONTO_ALTO": "Flag 1/0: desconto efetivo acima do limiar.",
    "MOTIVO_PRECO_FORA_FAIXA": "Flag 1/0: preço fora da faixa da rede (desvio vs. mediana acima do limiar).",
    "PROBLEMA": "Problema, limitação ou achado de qualidade identificado.",
    "DESCRICAO_AUDIT": "Descrição do problema de qualidade na autoaudit.",
    "CORRECAO": "Correção adotada para o problema identificado.",
    "ANTES": "Situação/metragem antes da correção.",
    "DEPOIS": "Situação/metragem depois da correção.",
    "IMPACTO": "Impacto mensurável da correção.",
    "LIMITACAO_OU_PROBLEMA": "Limitação de dados/modelagem/processo identificada.",
    "PRIORIDADE": "Prioridade da recomendação de melhoria.",
    "TEMA": "Tema da nota metodológica ou recomendação.",
    "PROBLEMA": "Problema ou limitação identificada.",
    "RISCO_ANALITICO": "Risco analítico associado à limitação.",
    "RECOMENDACAO": "Recomendação prática de melhoria.",
    "IMPACTO_ESPERADO": "Impacto esperado ao implementar a recomendação.",
    # Etapa 7 — recomendações finais
    "ACAO_PRIMARIA": "Ação primária do par por precedência (DESCONTINUAR > PROMOVER > REPRECIFICAR > COMPRAR); cada par entra uma vez para não dupla contar.",
    "FLAG_DESCONTINUAR": "Flag 1/0: par em SEM VENDA com estoque parado, curva ABC conhecida e curva ABC != A (capital imobilizado a delistar).",
    "FLAG_PROMOVER": "Flag 1/0: estoque encalhado que ainda gira (cobertura > 180 dias) ou campeão curva A parado.",
    "FLAG_REPRECIFICAR": "Flag 1/0: candidato a repricing da Etapa 5 (faixa ALTA/MEDIA) para o par loja × SKU.",
    "FLAG_COMPRAR": "Flag 1/0: par com compra recomendada na Etapa 6 (QTD_RECOMENDADA_ARM > 0).",
    "FLAG_PROTEGIDO_CAMPEAO": "Flag 1/0: SKU curva A parado protegido do descontinue e roteado para promover/transferir.",
    "FLAG_PROTEGIDO_SEM_CURVA": "Flag 1/0: SKU parado com curva ABC ausente protegido do descontinue automatico e roteado para promover/revisar.",
    "FLAG_CURVA_ABC_AUSENTE": "Flag 1/0: curva ABC ausente no par apos fallback auditavel quando aplicavel.",
    "CURVA_ABC_ORIGEM": "Origem da curva ABC usada no par: universo operacional, fallback da rede completa para Loja 93 ou ausente.",
    "N_ACOES_SINALIZADAS": "Quantidade de ações que o par dispara como sinal (pode ser > 1).",
    "SINAL_MARGEM_AUDITAVEL": "Flag 1/0: repricing com sinal de margem baixa/negativa auditavel (item com custo na Etapa 5).",
    "SINAL_PRECO_LISTA": "Flag 1/0: repricing com sinal de preço/lista (desconto alto ou preço fora da faixa), sem exigir custo.",
    "REPRICING_FAIXA": "Faixa do candidato a repricing da Etapa 5 (ALTA/MEDIA) colapsada por loja × SKU.",
    "REPRICING_N_EMBALAGENS": "Quantidade de embalagens do SKU que são candidatas a repricing na loja.",
    "REPRICING_SCORE": "Maior score de priorização de repricing (Etapa 5) entre as embalagens do par.",
    "REPRICING_RECEITA": "Receita das combinações de repricing do par (magnitude de exposição, não investimento).",
    "FAIXA_COMPRA_ETAPA6": "Faixa de prioridade da compra herdada da Etapa 6 (ALTA/MEDIA/MONITORAR).",
    "TIPO_VALOR_ACAO": "Natureza do valor financeiro da ação primária (capital a liberar, investimento de recompra ou sinal de preço sem valor).",
    "CAPITAL_IMOBILIZADO": "Capital parado no par a descontinuar = estoque projetado × custo; só com custo válido, senão NaN.",
    "VALOR_ESTOQUE_ENCALHE": "Valor do estoque encalhado a promover = estoque projetado × custo; só com custo válido, senão NaN.",
    "INVESTIMENTO_RECOMPRA": "Investimento de recompra do par (Etapa 6); só com custo válido, senão NaN.",
    "VALOR_ACAO_PRIMARIA": "Valor financeiro atrelado à ação primária, base das agregações sem dupla contagem. NaN = não avaliado.",
    "RANK_EXECUCAO": "Posição do par na fila de execução do universo (banda de prioridade, precedência de ação, urgência).",
    "PARES": "Quantidade de pares loja × SKU no recorte.",
    "PARES_COM_VALOR": "Pares do recorte com valor financeiro conhecido (custo válido).",
    "PARES_SEM_VALOR": "Pares do recorte sem valor financeiro (sem custo ou ação sem valor, como repricing).",
    "VALOR_FINANCEIRO_CONHECIDO": "Soma do valor da ação primária no recorte, apenas para itens com custo (NaN se nenhum).",
    "COBERTURA_VALOR_PCT": "Percentual de pares do recorte com valor financeiro conhecido.",
    "RECEITA_HISTORICA": "Receita histórica dos pares do recorte (base para leitura relativa, não perda prevista).",
    "RISCO": "Armadilha de interpretação avaliada na autoaudit.",
    "COMO_PODERIA_ERRAR": "Como a análise poderia errar se a armadilha não fosse tratada.",
    "CONTROLE_APLICADO": "Controle aplicado no código para evitar a armadilha.",
    "EVIDENCIA": "Evidência numérica de que o controle foi aplicado.",
    "RISCO_REMANESCENTE": "Risco que permanece mesmo após o controle.",
}


def descricao_coluna(col: str) -> str:
    if col in DESCRICOES_COLUNAS:
        return DESCRICOES_COLUNAS[col]
    if col.endswith("_MOM_DELTA"):
        return "Variação absoluta mês contra mês anterior."
    if col.endswith("_MOM_VAR_PCT"):
        return "Variação percentual mês contra mês anterior."
    if col.endswith("_YOY_DELTA"):
        return "Variação absoluta contra o mesmo mês do ano anterior."
    if col.endswith("_YOY_VAR_PCT"):
        return "Variação percentual contra o mesmo mês do ano anterior."
    if col.endswith("_ACUM_ANO"):
        return "Valor acumulado dentro do ano."
    if col.startswith("CONTRIBUICAO_"):
        return "Contribuição percentual para a variação ou queda de receita."
    return "Campo do artefato analítico; ver notebook/script da etapa correspondente."


def tratamento_coluna(col: str) -> str:
    if col == "TRANSACOES" or col.startswith("TRANSACOES_"):
        return "Derivado como contagem de linhas de venda; proxy por ausência de id de cupom/pedido/nota."
    if col in {"RECEITA", "QTD_ARMAZENAGEM"}:
        return "Derivado na Etapa 1 e reaproveitado nas agregações."
    if col.startswith("PARTICIPACAO_") or col.startswith("VAR_") or col.startswith("DELTA_"):
        return "Calculado por agregação na etapa analítica."
    if col.startswith("RANK_") or col.endswith("_ACUM") or col.endswith("_ACUM_PCT"):
        return "Calculado a partir da ordenação do ranking."
    return "Gerado ou preservado pelo pipeline analítico."


def dicionario_arquivo_csv(path: Path, tabela: str) -> list[dict]:
    df_head = pd.read_csv(path, nrows=50, encoding="utf-8-sig")
    linhas = []
    for col in df_head.columns:
        linhas.append({
            "tabela": tabela,
            "campo": col,
            "descricao": descricao_coluna(col),
            "tipo": tipo_coluna(df_head[col]),
            "notas": f"Arquivo: {path.relative_to(ROOT)}",
            "tratamento": tratamento_coluna(col),
        })
    return linhas


dic = pd.read_csv(E1 / "dicionario_dados.csv")
dicionario = [{
    "tabela": str(r.tabela), "campo": str(r.campo),
    "descricao": str(r.descricao)
        .replace("Data da transação de venda", "Data da linha de venda")
        .replace("transação de venda", "linha de venda"),
    "tipo": str(r.tipo), "notas": str(r.notas), "tratamento": str(r.tratamento_aplicado),
} for r in dic.itertuples()]

artefatos_dicionario = [
    (E2 / "cobertura_estoque.csv", "output_etapa2.cobertura_estoque"),
    (E2 / "investigacao_outliers_preco.csv", "output_etapa2.investigacao_outliers_preco"),
    (E3 / "ranking_produtos_receita.csv", "output_etapa3.ranking_produtos_receita"),
    (E3 / "ranking_produtos_quantidade.csv", "output_etapa3.ranking_produtos_quantidade"),
    (E3 / "curva_abc_produtos.csv", "output_etapa3.curva_abc_produtos"),
    (E3 / "desempenho_categorias_n1.csv", "output_etapa3.desempenho_categorias_n1"),
    (E3 / "desempenho_categorias_n2.csv", "output_etapa3.desempenho_categorias_n2"),
    (E3 / "desempenho_categorias_n3.csv", "output_etapa3.desempenho_categorias_n3"),
    (E3 / "desempenho_lojas.csv", "output_etapa3.desempenho_lojas"),
    (E3 / "desempenho_regioes.csv", "output_etapa3.desempenho_regioes"),
    (E3 / "vendas_mensais.csv", "output_etapa3.vendas_mensais"),
    (E3 / "sazonalidade_picos_quedas.csv", "output_etapa3.sazonalidade_picos_quedas"),
    (E3 / "decomposicao_queda_2025_categorias.csv", "output_etapa3.decomposicao_queda_2025_categorias"),
    (E3 / "decomposicao_queda_2025_lojas.csv", "output_etapa3.decomposicao_queda_2025_lojas"),
    (E3 / "diagnostico_captura_mensal.csv", "output_etapa3.diagnostico_captura_mensal"),
    (E3 / "diagnostico_captura_lojas_mensal.csv", "output_etapa3.diagnostico_captura_lojas_mensal"),
    (E3 / "impacto_loja93.csv", "output_etapa3.impacto_loja93"),
    (E3 / "notas_metodologicas.csv", "output_etapa3.notas_metodologicas"),
    (E3 / "recomendacoes_melhoria.csv", "output_etapa3.recomendacoes_melhoria"),
    (E3 / "validacoes_etapa3.csv", "output_etapa3.validacoes_etapa3"),
    (E4 / "cobertura_categorias_n1.csv", "output_etapa4.cobertura_categorias_n1"),
    (E4 / "cobertura_categorias_n2.csv", "output_etapa4.cobertura_categorias_n2"),
    (E4 / "cobertura_categorias_n3.csv", "output_etapa4.cobertura_categorias_n3"),
    (E4 / "cobertura_lojas.csv", "output_etapa4.cobertura_lojas"),
    (E4 / "cobertura_categoria_loja.csv", "output_etapa4.cobertura_categoria_loja"),
    (E4 / "priorizacao_reposicao_categoria_loja.csv", "output_etapa4.priorizacao_reposicao_categoria_loja"),
    (E4 / "recomendacoes_melhoria.csv", "output_etapa4.recomendacoes_melhoria"),
    (E4 / "validacoes_etapa4.csv", "output_etapa4.validacoes_etapa4"),
    (E5 / "margem_produtos.csv", "output_etapa5.margem_produtos"),
    (E5 / "margem_categorias_n1.csv", "output_etapa5.margem_categorias_n1"),
    (E5 / "margem_categorias_n2.csv", "output_etapa5.margem_categorias_n2"),
    (E5 / "margem_categorias_n3.csv", "output_etapa5.margem_categorias_n3"),
    (E5 / "margem_lojas.csv", "output_etapa5.margem_lojas"),
    (E5 / "precificacao_desconto.csv", "output_etapa5.precificacao_desconto"),
    (E5 / "dispersao_preco_lojas.csv", "output_etapa5.dispersao_preco_lojas"),
    (E5 / "candidatos_repricing.csv", "output_etapa5.candidatos_repricing"),
    (E5 / "candidatos_repricing_impacto.csv", "output_etapa5.candidatos_repricing_impacto"),
    (E5 / "recomendacoes_melhoria.csv", "output_etapa5.recomendacoes_melhoria"),
    (E5 / "validacoes_etapa5.csv", "output_etapa5.validacoes_etapa5"),
    (E5 / "autoaudit_etapa5.csv", "output_etapa5.autoaudit_etapa5"),
    (E5 / "margem_total_universo.csv", "output_etapa5.margem_total_universo"),
    (E6 / "plano_compras_sku_loja.csv", "output_etapa6.plano_compras_sku_loja"),
    (E6 / "plano_compras_total_universo.csv", "output_etapa6.plano_compras_total_universo"),
    (E6 / "plano_compras_categorias_n1.csv", "output_etapa6.plano_compras_categorias_n1"),
    (E6 / "plano_compras_lojas.csv", "output_etapa6.plano_compras_lojas"),
    (E6 / "priorizacao_compras.csv", "output_etapa6.priorizacao_compras"),
    (E6 / "recomendacoes_melhoria.csv", "output_etapa6.recomendacoes_melhoria"),
    (E6 / "validacoes_etapa6.csv", "output_etapa6.validacoes_etapa6"),
    (E6 / "autoaudit_etapa6.csv", "output_etapa6.autoaudit_etapa6"),
    (E7 / "recomendacoes_sku_loja.csv", "output_etapa7.recomendacoes_sku_loja"),
    (E7 / "recomendacoes_acao_universo.csv", "output_etapa7.recomendacoes_acao_universo"),
    (E7 / "recomendacoes_categoria_n1.csv", "output_etapa7.recomendacoes_categoria_n1"),
    (E7 / "recomendacoes_lojas.csv", "output_etapa7.recomendacoes_lojas"),
    (E7 / "reprecificacao_candidatos.csv", "output_etapa7.reprecificacao_candidatos"),
    (E7 / "priorizacao_acoes.csv", "output_etapa7.priorizacao_acoes"),
    (E7 / "recomendacoes_melhoria.csv", "output_etapa7.recomendacoes_melhoria"),
    (E7 / "validacoes_etapa7.csv", "output_etapa7.validacoes_etapa7"),
    (E7 / "autoaudit_etapa7.csv", "output_etapa7.autoaudit_etapa7"),
]
for path, tabela in artefatos_dicionario:
    if path.exists():
        dicionario.extend(dicionario_arquivo_csv(path, tabela))

pd.DataFrame(dicionario).to_csv(OUTPUTS / "dicionario_dados_projeto.csv", index=False, encoding="utf-8-sig")

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
    {"titulo": "Ausência de identificador real de transação",
     "achado": "A base de vendas não possui id de cupom, pedido ou nota; a granularidade disponível "
               "é a linha do fato de vendas. Por isso, as análises da Etapa 3 tratam TRANSACOES como "
               "linhas de venda, não como cupons únicos.",
     "hipotese": "É uma limitação de modelagem/captura, não um erro de cálculo. A melhoria recomendada "
                 "é incluir id_transacao, número do item da transação e canal/origem para calcular "
                 "ticket médio real, itens por cupom e análises de cesta.",
     "status": "documentado"},
    {"titulo": "Queda sustentada de volume em 2025 (hipótese: mercado × captura)",
     "achado": f"As linhas de venda caem de forma quase monotônica ao longo de 2025; o ano fecha com "
               f"{fmt_int(tx25)} linhas contra {fmt_int(tx24)} em 2024 (−{fmt_pct(abs(tx25/tx24-1)*100)}) "
               f"e receita de {fmt_milhao(r25)} vs {fmt_milhao(r24)} ({fmt_pct(yoy)}). O nº de linhas cai "
               f"na mesma proporção da receita.",
     "hipotese": "Ainda que os 24 meses estejam presentes, a queda proporcional de linhas é assinatura "
                 "possível de TRUNCAMENTO DE CAPTURA (extração/carga incompleta dos meses finais), não "
                 "necessariamente retração de mercado. É uma HIPÓTESE A CONFIRMAR: o diagnóstico mensal e "
                 "por loja (outputs/etapa3/diagnostico_captura_mensal.csv e diagnostico_captura_lojas_mensal.csv) "
                 "testa se a queda é homogênea entre lojas (mercado) ou se lojas 'somem' da base (captura). "
                 "Como essa base alimenta VENDA_MEDIA_MES e a projeção de compras das Etapas 6/7, a incerteza "
                 "se propaga para a demanda projetada. Exige confirmação com a origem dos dados / área comercial.",
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
               f"{fmt_int(sk93)} SKUs ({fmt_pct(sk93/v['CODIGO'].nunique()*100)}); receita média por linha "
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

# ---- Etapa 3: desempenho de vendas ----
print("Carregando saídas da Etapa 3...")
rank_receita = pd.read_csv(E3 / "ranking_produtos_receita.csv", encoding="utf-8-sig")
cat_n1 = pd.read_csv(E3 / "desempenho_categorias_n1.csv", encoding="utf-8-sig")
lojas_e3 = pd.read_csv(E3 / "desempenho_lojas.csv", encoding="utf-8-sig")
impacto_e3 = pd.read_csv(E3 / "impacto_loja93.csv", encoding="utf-8-sig")
valid_e3 = pd.read_csv(E3 / "validacoes_etapa3.csv", encoding="utf-8-sig")
recs_e3 = pd.read_csv(E3 / "recomendacoes_melhoria.csv", encoding="utf-8-sig")

impacto_idx = impacto_e3.set_index("SEGMENTO")
rank_full = rank_receita[rank_receita["UNIVERSO"] == "REDE_COMPLETA"]
abc_a = rank_full[rank_full["CURVA_ABC_RECEITA"] == "A"]
abc_txt = f"{fmt_int(len(abc_a))} SKUs / {fmt_pct(abc_a['RECEITA'].sum() / rank_full['RECEITA'].sum() * 100)}"

cat_rows = []
for universo in ["REDE_COMPLETA", "REDE_FISICA_SEM_LOJA93"]:
    top_cat = cat_n1[cat_n1["UNIVERSO"] == universo].sort_values("RECEITA", ascending=False).head(5)
    for r in top_cat.itertuples():
        cat_rows.append({
            "universo": universo,
            "categoria": str(r.NIVEL_1),
            "receita": fmt_milhao(float(r.RECEITA)),
            "participacao": fmt_pct(float(r.PARTICIPACAO_RECEITA_PCT)),
            "var_yoy": fmt_pct(float(r.VAR_RECEITA_2025_VS_2024_PCT)),
        })

loja_rows = []
for universo in ["REDE_COMPLETA", "REDE_FISICA_SEM_LOJA93"]:
    top_lojas = lojas_e3[lojas_e3["UNIVERSO"] == universo].sort_values("RECEITA", ascending=False).head(6)
    for r in top_lojas.itertuples():
        loja_rows.append({
            "universo": universo,
            "loja": str(int(r.COD_EMPRESA)),
            "cidade": f"{r.CD_CIDADE}-{r.CD_ESTADO}",
            "operacao": str(r.TIPO_OPERACAO),
            "receita": fmt_milhao(float(r.RECEITA)),
            "linhas": fmt_int(float(r.TRANSACOES)),
            "receita_media": fmt_reais(float(r.TICKET_MEDIO_TRANSACAO)),
        })

rec_rows = [{
    "prioridade": str(r.PRIORIDADE),
    "tema": str(r.TEMA),
    "problema": str(r.PROBLEMA),
    "recomendacao": str(r.RECOMENDACAO),
    "impacto": str(r.IMPACTO_ESPERADO),
} for r in recs_e3.itertuples()]

etapa3 = {
    "kpis": {
        "receita_completa": fmt_milhao(float(impacto_idx.loc["REDE_COMPLETA", "RECEITA"])),
        "linhas_completa": fmt_int(float(impacto_idx.loc["REDE_COMPLETA", "TRANSACOES"])),
        "loja93_receita_pct": fmt_pct(float(impacto_idx.loc["LOJA_93_ATACADO_B2B", "PARTICIPACAO_RECEITA_REDE_COMPLETA_PCT"])),
        "receita_fisica": fmt_milhao(float(impacto_idx.loc["REDE_FISICA_SEM_LOJA93", "RECEITA"])),
        "abc_a": abc_txt,
        "validacoes": f"{int((valid_e3['STATUS'] == 'OK').sum())}/{len(valid_e3)} OK",
    },
    "categorias": cat_rows,
    "lojas": loja_rows,
    "recomendacoes": rec_rows,
}

# ---- Etapa 4: cobertura por categoria e loja ----
print("Carregando saidas da Etapa 4...")
etapa4 = None
if (E4 / "cobertura_categorias_n1.csv").exists():
    cat4 = pd.read_csv(E4 / "cobertura_categorias_n1.csv", encoding="utf-8-sig")
    lojas4 = pd.read_csv(E4 / "cobertura_lojas.csv", encoding="utf-8-sig")
    prio4 = pd.read_csv(E4 / "priorizacao_reposicao_categoria_loja.csv", encoding="utf-8-sig")
    recs4 = pd.read_csv(E4 / "recomendacoes_melhoria.csv", encoding="utf-8-sig")
    valid4 = pd.read_csv(E4 / "validacoes_etapa4.csv", encoding="utf-8-sig")

    cat4_full = cat4[cat4["UNIVERSO"] == "REDE_COMPLETA"]
    cat4_fisica = cat4[cat4["UNIVERSO"] == "REDE_FISICA_SEM_LOJA93"]
    pares_total_e4 = float(cat4_full["PARES_LOJA_PRODUTO"].sum())
    pares_risco_e4 = float(cat4_full["PARES_RUPTURA_CRITICO"].sum())
    receita_risco_total_e4 = float(cat4_full["RECEITA_RUPTURA_CRITICO"].sum())
    receita_risco_fisica_e4 = float(cat4_fisica["RECEITA_RUPTURA_CRITICO"].sum())
    top_cat_fisica = cat4_fisica.sort_values("RECEITA_RUPTURA_CRITICO", ascending=False).iloc[0]

    cat_rows4 = []
    for universo in ["REDE_COMPLETA", "REDE_FISICA_SEM_LOJA93"]:
        top_cat = (
            cat4[cat4["UNIVERSO"] == universo]
            .sort_values("RECEITA_RUPTURA_CRITICO", ascending=False)
            .head(5)
        )
        for r in top_cat.itertuples():
            cat_rows4.append(
                {
                    "universo": universo,
                    "categoria": str(r.NIVEL_1),
                    "receita_risco": fmt_milhao(float(r.RECEITA_RUPTURA_CRITICO)),
                    "pares_risco": fmt_int(float(r.PARES_RUPTURA_CRITICO)),
                    "pct_pares": fmt_pct(float(r.PCT_PARES_RUPTURA_CRITICO)),
                    "mediana_dias": fmt_int(float(r.DIAS_COBERTURA_MEDIANA_FINITA)),
                }
            )

    loja_rows4 = []
    lojas_visao = pd.concat(
        [
            lojas4[lojas4["UNIVERSO"] == "REDE_FISICA_SEM_LOJA93"]
            .sort_values("RECEITA_RUPTURA_CRITICO", ascending=False)
            .head(6),
            lojas4[(lojas4["UNIVERSO"] == "REDE_COMPLETA") & (lojas4["COD_EMPRESA"] == LOJA_ATACADO)],
        ],
        ignore_index=True,
    )
    for r in lojas_visao.itertuples():
        loja_rows4.append(
            {
                "universo": str(r.UNIVERSO),
                "loja": str(int(r.COD_EMPRESA)),
                "cidade": f"{r.CD_CIDADE}-{r.CD_ESTADO}",
                "operacao": str(r.TIPO_OPERACAO),
                "receita_risco": fmt_milhao(float(r.RECEITA_RUPTURA_CRITICO)),
                "pct_pares": fmt_pct(float(r.PCT_PARES_RUPTURA_CRITICO)),
            }
        )

    prio_visao = pd.concat(
        [
            prio4[prio4["ESCOPO_PRIORIZACAO"] == "REDE_FISICA_SEM_LOJA93"].head(10),
            prio4[prio4["ESCOPO_PRIORIZACAO"] == "LOJA_93_ATACADO_B2B"].head(4),
        ],
        ignore_index=True,
    )
    prio_rows4 = []
    for r in prio_visao.itertuples():
        prio_rows4.append(
            {
                "escopo": str(r.ESCOPO_PRIORIZACAO),
                "rank": str(int(r.RANK_PRIORIDADE_ESCOPO)),
                "faixa": str(r.FAIXA_PRIORIDADE),
                "loja": f"{int(r.COD_EMPRESA)} ({r.CD_CIDADE}-{r.CD_ESTADO})",
                "categoria": str(r.NIVEL_1),
                "receita_risco": fmt_milhao(float(r.RECEITA_RUPTURA_CRITICO)),
                "acao": str(r.ACAO_RECOMENDADA),
            }
        )

    rec_rows4 = [
        {
            "prioridade": str(r.PRIORIDADE),
            "tema": str(r.TEMA),
            "problema": str(r.LIMITACAO_OU_PROBLEMA),
            "recomendacao": str(r.RECOMENDACAO),
        }
        for r in recs4.itertuples()
    ]

    etapa4 = {
        "kpis": {
            "pares_total": fmt_int(pares_total_e4),
            "pares_risco_pct": f"{fmt_int(pares_risco_e4)} / {fmt_pct(pares_risco_e4 / pares_total_e4 * 100)}",
            "receita_risco_total": fmt_milhao(receita_risco_total_e4),
            "receita_risco_fisica": fmt_milhao(receita_risco_fisica_e4),
            "top_categoria_fisica": str(top_cat_fisica.NIVEL_1),
            "validacoes": f"{int((valid4['STATUS'] == 'OK').sum())}/{len(valid4)} OK",
        },
        "categorias": cat_rows4,
        "lojas": loja_rows4,
        "prioridades": prio_rows4,
        "recomendacoes": rec_rows4,
    }

# ---- Etapa 5: precificacao e margem ----
print("Carregando saidas da Etapa 5...")
etapa5 = None
if (E5 / "margem_total_universo.csv").exists():
    e5_total = pd.read_csv(E5 / "margem_total_universo.csv", encoding="utf-8-sig")
    e5_cat = pd.read_csv(E5 / "margem_categorias_n1.csv", encoding="utf-8-sig")
    e5_sku = pd.read_csv(E5 / "margem_produtos.csv", encoding="utf-8-sig")
    e5_cand = pd.read_csv(E5 / "candidatos_repricing.csv", encoding="utf-8-sig")
    e5_desc = pd.read_csv(E5 / "precificacao_desconto.csv", encoding="utf-8-sig")
    e5_audit = pd.read_csv(E5 / "autoaudit_etapa5.csv", encoding="utf-8-sig")
    e5_valid = pd.read_csv(E5 / "validacoes_etapa5.csv", encoding="utf-8-sig")

    tc5 = e5_total[e5_total["UNIVERSO"] == "REDE_COMPLETA"].iloc[0]
    tf5 = e5_total[e5_total["UNIVERSO"] == "REDE_FISICA_SEM_LOJA93"].iloc[0]

    def fmt_markup(v):
        return f"{float(v):.2f}x".replace(".", ",")

    def fmt_compact(v):
        v = float(v)
        return fmt_milhao(v) if abs(v) >= 1e6 else fmt_reais(v, 0)

    desc_fis5 = e5_desc[(e5_desc["UNIVERSO"] == "REDE_FISICA_SEM_LOJA93") & e5_desc["DESCONTO_EFETIVO_PCT"].notna()]
    desc_medio5 = float(np.average(desc_fis5["DESCONTO_EFETIVO_PCT"], weights=desc_fis5["RECEITA"]))

    cand_fis5 = e5_cand[e5_cand["UNIVERSO"] == "REDE_FISICA_SEM_LOJA93"]
    cand_alta5 = int((cand_fis5["FAIXA_PRIORIDADE"] == "ALTA").sum())

    # Categorias da rede fisica com cobertura representativa (>=10%), ordenadas por margem.
    cat_fis5 = e5_cat[e5_cat["UNIVERSO"] == "REDE_FISICA_SEM_LOJA93"].copy()
    cat_repr5 = cat_fis5[cat_fis5["COBERTURA_CUSTO_RECEITA_PCT"] >= 10].sort_values(
        "MARGEM_BRUTA_PCT", ascending=False)
    cat_rows5 = [{
        "categoria": str(r.NIVEL_1),
        "receita_custo": fmt_milhao(float(r.RECEITA_COM_CUSTO)),
        "cobertura": fmt_pct(float(r.COBERTURA_CUSTO_RECEITA_PCT)),
        "margem": fmt_pct(float(r.MARGEM_BRUTA_PCT)),
        "markup": fmt_markup(r.MARKUP_PONDERADO),
        "skus_custo": f"{int(r.SKUS_COM_CUSTO)}/{int(r.SKUS)}",
    } for r in cat_repr5.itertuples()]

    sku_a5 = e5_sku[(e5_sku["UNIVERSO"] == "REDE_FISICA_SEM_LOJA93") & (e5_sku["CURVA_ABC_RECEITA"] == "A")]

    def sku_row5(r, tipo):
        return {
            "tipo": tipo,
            "codigo": str(int(r.CODIGO)),
            "desc": str(r.DESCRICAO).strip(),
            "nivel1": str(r.NIVEL_1),
            "receita": fmt_compact(float(r.RECEITA)),
            "preco": fmt_reais(float(r.PRECO_PRATICADO_ARM)),
            "custo": fmt_reais(float(r.CUSTO_MEDIO_ARM)),
            "margem": fmt_pct(float(r.MARGEM_BRUTA_PCT)),
            "markup": fmt_markup(r.MARKUP),
        }

    top_sku5 = sku_a5.sort_values("MARGEM_BRUTA_PCT", ascending=False).head(5)
    bot_sku5 = sku_a5.sort_values("MARGEM_BRUTA_PCT").head(5)
    sku_rows5 = ([sku_row5(r, "Melhor") for r in top_sku5.itertuples()]
                 + [sku_row5(r, "Pior") for r in bot_sku5.itertuples()])

    cand_rows5 = [{
        "rank": str(int(r.RANK_PRIORIDADE)),
        "faixa": str(r.FAIXA_PRIORIDADE),
        "motivos": str(r.MOTIVOS),
        "loja": f"{int(r.COD_EMPRESA)} ({r.CD_CIDADE}-{r.CD_ESTADO})",
        "codigo": str(int(r.CODIGO)),
        "desc": str(r.DESCRICAO).strip(),
        "receita": fmt_reais(float(r.RECEITA), 0),
        "margem": "—" if pd.isna(r.MARGEM_BRUTA_PCT) else fmt_pct(float(r.MARGEM_BRUTA_PCT)),
        "desconto": "—" if pd.isna(r.DESCONTO_EFETIVO_PCT) else fmt_pct(float(r.DESCONTO_EFETIVO_PCT)),
    } for r in cand_fis5.head(15).itertuples()]

    audit_rows5 = [{
        "problema": str(r.PROBLEMA),
        "antes": str(r.ANTES),
        "depois": str(r.DEPOIS),
    } for r in e5_audit.itertuples()]

    etapa5 = {
        "kpis": {
            "margem_fisica": f"{fmt_pct(float(tf5.MARGEM_BRUTA_PCT))} · {fmt_markup(tf5.MARKUP_PONDERADO)}",
            "cobertura_custo": fmt_pct(float(tc5.COBERTURA_CUSTO_RECEITA_PCT)),
            "skus_custo": f"{int(tc5.SKUS_COM_CUSTO)} / {int(tc5.SKUS)}",
            "desconto_medio": fmt_pct(desc_medio5),
            "candidatos": f"{cand_alta5} ALTA / {fmt_int(len(cand_fis5))}",
            "validacoes": f"{int((e5_valid['STATUS'] == 'OK').sum())}/{len(e5_valid)} OK",
        },
        "categorias": cat_rows5,
        "skus": sku_rows5,
        "candidatos": cand_rows5,
        "autoaudit": audit_rows5,
    }

# ---- Etapa 6: projecao de compras ----
print("Carregando saidas da Etapa 6...")
etapa6 = None
if (E6 / "plano_compras_total_universo.csv").exists():
    e6_total = pd.read_csv(E6 / "plano_compras_total_universo.csv", encoding="utf-8-sig")
    e6_cat = pd.read_csv(E6 / "plano_compras_categorias_n1.csv", encoding="utf-8-sig")
    e6_lojas = pd.read_csv(E6 / "plano_compras_lojas.csv", encoding="utf-8-sig")
    e6_prio = pd.read_csv(E6 / "priorizacao_compras.csv", encoding="utf-8-sig")
    e6_audit = pd.read_csv(E6 / "autoaudit_etapa6.csv", encoding="utf-8-sig")
    e6_valid = pd.read_csv(E6 / "validacoes_etapa6.csv", encoding="utf-8-sig")

    tf6 = e6_total[e6_total["UNIVERSO"] == "REDE_FISICA_SEM_LOJA93"].iloc[0]
    tc6 = e6_total[e6_total["UNIVERSO"] == "REDE_COMPLETA"].iloc[0]
    prio_fis6 = e6_prio[e6_prio["UNIVERSO_OPERACIONAL"] == "REDE_FISICA_SEM_LOJA93"]
    alta_fis6 = int((prio_fis6["FAIXA_PRIORIDADE"] == "ALTA").sum())

    def fmt_invest6(v):
        return "sem custo" if pd.isna(v) else fmt_milhao(float(v))

    cat_rows6 = []
    for universo in ["REDE_FISICA_SEM_LOJA93", "LOJA_93_ATACADO_B2B"]:
        top_cat = (
            e6_cat[(e6_cat["UNIVERSO"] == universo) & (e6_cat["QTD_RECOMENDADA_ARM"] > 0)]
            .sort_values("QTD_RECOMENDADA_ARM", ascending=False)
            .head(6)
        )
        for r in top_cat.itertuples():
            cat_rows6.append({
                "universo": universo,
                "categoria": str(r.NIVEL_1),
                "pares": fmt_int(float(r.PARES_COM_COMPRA_RECOMENDADA)),
                "qtd": fmt_int(float(r.QTD_RECOMENDADA_ARM)),
                "investimento": fmt_invest6(r.INVESTIMENTO_ESTIMADO_COM_CUSTO),
                "cobertura": "sem pares" if pd.isna(r.COBERTURA_CUSTO_PARES_COMPRA_PCT) else fmt_pct(float(r.COBERTURA_CUSTO_PARES_COMPRA_PCT)),
            })

    loja_rows6 = []
    lojas_visao6 = pd.concat(
        [
            e6_lojas[
                (e6_lojas["UNIVERSO"] == "REDE_FISICA_SEM_LOJA93")
                & (e6_lojas["QTD_RECOMENDADA_ARM"] > 0)
            ].sort_values("QTD_RECOMENDADA_ARM", ascending=False).head(8),
            e6_lojas[
                (e6_lojas["UNIVERSO"] == "LOJA_93_ATACADO_B2B")
                & (e6_lojas["QTD_RECOMENDADA_ARM"] > 0)
            ].sort_values("QTD_RECOMENDADA_ARM", ascending=False).head(1),
        ],
        ignore_index=True,
    )
    for r in lojas_visao6.itertuples():
        loja_rows6.append({
            "universo": str(r.UNIVERSO),
            "loja": str(int(r.COD_EMPRESA)),
            "cidade": f"{r.CD_CIDADE}-{r.CD_ESTADO}",
            "pares": fmt_int(float(r.PARES_COM_COMPRA_RECOMENDADA)),
            "qtd": fmt_int(float(r.QTD_RECOMENDADA_ARM)),
            "investimento": fmt_invest6(r.INVESTIMENTO_ESTIMADO_COM_CUSTO),
        })

    prio_rows6 = []
    prio_visao6 = pd.concat(
        [
            e6_prio[e6_prio["UNIVERSO_OPERACIONAL"] == "REDE_FISICA_SEM_LOJA93"].head(12),
            e6_prio[e6_prio["UNIVERSO_OPERACIONAL"] == "LOJA_93_ATACADO_B2B"].head(5),
        ],
        ignore_index=True,
    )
    for r in prio_visao6.itertuples():
        prio_rows6.append({
            "escopo": str(r.UNIVERSO_OPERACIONAL),
            "rank": str(int(r.RANK_PRIORIDADE)),
            "faixa": str(r.FAIXA_PRIORIDADE),
            "loja": f"{int(r.COD_EMPRESA)} ({r.CD_CIDADE}-{r.CD_ESTADO})",
            "codigo": str(int(r.CODIGO)),
            "desc": str(r.DESCRICAO).strip(),
            "qtd": fmt_int(float(r.QTD_RECOMENDADA_ARM)),
            "investimento": fmt_invest6(r.INVESTIMENTO_ESTIMADO),
            "status_orcamento": str(r.STATUS_ORCAMENTO),
        })

    audit_rows6 = [{
        "risco": str(r.RISCO),
        "controle": str(r.CONTROLE_APLICADO),
        "evidencia": str(r.EVIDENCIA),
        "risco_remanescente": str(r.RISCO_REMANESCENTE),
    } for r in e6_audit.itertuples()]

    etapa6 = {
        "kpis": {
            "pares_compra": fmt_int(float(tc6.PARES_COM_COMPRA_RECOMENDADA)),
            "qtd_fisica": fmt_int(float(tf6.QTD_RECOMENDADA_ARM)),
            "invest_fisica": fmt_milhao(float(tf6.INVESTIMENTO_ESTIMADO_COM_CUSTO)),
            "cobertura_custo": fmt_pct(float(tc6.COBERTURA_CUSTO_PARES_COMPRA_PCT)),
            "alta_fisica": fmt_int(alta_fis6),
            "validacoes": f"{int((e6_valid['STATUS'] == 'OK').sum())}/{len(e6_valid)} OK",
        },
        "categorias": cat_rows6,
        "lojas": loja_rows6,
        "prioridades": prio_rows6,
        "autoaudit": audit_rows6,
    }

etapa7 = None
if (E7 / "recomendacoes_acao_universo.csv").exists():
    e7_acao = pd.read_csv(E7 / "recomendacoes_acao_universo.csv", encoding="utf-8-sig")
    e7_cat = pd.read_csv(E7 / "recomendacoes_categoria_n1.csv", encoding="utf-8-sig")
    e7_prio = pd.read_csv(E7 / "priorizacao_acoes.csv", encoding="utf-8-sig", low_memory=False)
    e7_audit = pd.read_csv(E7 / "autoaudit_etapa7.csv", encoding="utf-8-sig")
    e7_valid = pd.read_csv(E7 / "validacoes_etapa7.csv", encoding="utf-8-sig")

    ORDEM_ACAO = ["COMPRAR", "REPRECIFICAR", "PROMOVER", "DESCONTINUAR"]

    def fmt_valor7(v):
        return "sem custo" if pd.isna(v) else fmt_milhao(float(v))

    def fmt_valor_acao7(v, acao):
        return "nao aplicavel" if acao == "REPRECIFICAR" else fmt_valor7(v)

    def pares_acao(universo, acao):
        m = (e7_acao["UNIVERSO"] == universo) & (e7_acao["ACAO_PRIMARIA"] == acao)
        return int(e7_acao.loc[m, "PARES"].iloc[0]) if m.any() else 0

    def valor_acao(universo, acao):
        m = (e7_acao["UNIVERSO"] == universo) & (e7_acao["ACAO_PRIMARIA"] == acao)
        return float(e7_acao.loc[m, "VALOR_FINANCEIRO_CONHECIDO"].iloc[0]) if m.any() else float("nan")

    acao_rows7 = []
    for universo in ["REDE_FISICA_SEM_LOJA93", "LOJA_93_ATACADO_B2B"]:
        sub = e7_acao[e7_acao["UNIVERSO"] == universo].copy()
        sub["_ord"] = sub["ACAO_PRIMARIA"].map({a: i for i, a in enumerate(ORDEM_ACAO)})
        for r in sub.sort_values("_ord").itertuples():
            acao_rows7.append({
                "universo": str(r.UNIVERSO),
                "acao": str(r.ACAO_PRIMARIA),
                "pares": fmt_int(float(r.PARES)),
                "skus": fmt_int(float(r.SKUS)),
                "pares_valor": fmt_int(float(r.PARES_COM_VALOR)),
                "valor": fmt_valor_acao7(r.VALOR_FINANCEIRO_CONHECIDO, str(r.ACAO_PRIMARIA)),
                "cobertura": fmt_pct(float(r.COBERTURA_VALOR_PCT)) if pd.notna(r.COBERTURA_VALOR_PCT) else "n/d",
            })

    cat_rows7 = []
    cat_fis7 = e7_cat[e7_cat["UNIVERSO"] == "REDE_FISICA_SEM_LOJA93"].copy()
    cat_fis7["_ord"] = cat_fis7["ACAO_PRIMARIA"].map({a: i for i, a in enumerate(ORDEM_ACAO)})
    for acao in ORDEM_ACAO:
        top = cat_fis7[cat_fis7["ACAO_PRIMARIA"] == acao].sort_values("PARES", ascending=False).head(4)
        for r in top.itertuples():
            cat_rows7.append({
                "acao": acao,
                "categoria": str(r.NIVEL_1),
                "pares": fmt_int(float(r.PARES)),
                "valor": fmt_valor_acao7(r.VALOR_FINANCEIRO_CONHECIDO, acao),
            })

    prio_rows7 = []
    prio_visao7 = pd.concat([
        e7_prio[e7_prio["UNIVERSO_OPERACIONAL"] == "REDE_FISICA_SEM_LOJA93"].head(14),
        e7_prio[e7_prio["UNIVERSO_OPERACIONAL"] == "LOJA_93_ATACADO_B2B"].head(4),
    ], ignore_index=True)
    for r in prio_visao7.itertuples():
        prio_rows7.append({
            "escopo": str(r.UNIVERSO_OPERACIONAL),
            "rank": str(int(r.RANK_EXECUCAO)),
            "faixa": str(r.FAIXA_PRIORIDADE),
            "acao": str(r.ACAO_PRIMARIA),
            "loja": f"{int(r.COD_EMPRESA)} ({r.CD_CIDADE}-{r.CD_ESTADO})",
            "codigo": str(int(r.CODIGO)),
            "desc": str(r.DESCRICAO).strip(),
            "valor": fmt_valor_acao7(r.VALOR_ACAO_PRIMARIA, str(r.ACAO_PRIMARIA)),
        })

    audit_rows7 = [{
        "risco": str(r.RISCO),
        "controle": str(r.CONTROLE_APLICADO),
        "evidencia": str(r.EVIDENCIA),
        "risco_remanescente": str(r.RISCO_REMANESCENTE),
    } for r in e7_audit.itertuples()]

    etapa7 = {
        "kpis": {
            "comprar": fmt_int(pares_acao("REDE_COMPLETA", "COMPRAR")),
            "reprecificar": fmt_int(pares_acao("REDE_COMPLETA", "REPRECIFICAR")),
            "promover": fmt_int(pares_acao("REDE_COMPLETA", "PROMOVER")),
            "descontinuar": fmt_int(pares_acao("REDE_COMPLETA", "DESCONTINUAR")),
            "valor_encalhe": fmt_valor7(valor_acao("REDE_COMPLETA", "PROMOVER")),
            "validacoes": f"{int((e7_valid['STATUS'] == 'OK').sum())}/{len(e7_valid)} OK",
        },
        "acoes": acao_rows7,
        "categorias": cat_rows7,
        "prioridades": prio_rows7,
        "autoaudit": audit_rows7,
    }

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
    "etapa3": etapa3,
    "etapa4": etapa4,
    "etapa5": etapa5,
    "etapa6": etapa6,
    "etapa7": etapa7,
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
