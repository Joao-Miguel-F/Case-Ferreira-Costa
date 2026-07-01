"""
etapa1_entendimento_dados.py
============================
Etapa 1 — Entendimento e Limpeza dos Dados

Objetivos
---------
1. Inspecionar estrutura, tipos e qualidade de cada base
2. Documentar decisões de tratamento com justificativa analítica
3. Identificar inconsistências e levantar hipóteses de negócio
4. Gerar bases tratadas em Parquet para uso nas etapas seguintes

Saídas
------
data/processed/*.parquet   — bases tratadas
outputs/etapa1/decisoes_tratamento.csv
outputs/etapa1/dicionario_dados.csv
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Raiz do repositório resolvida a partir do arquivo (roda de qualquer diretório)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kpis import emit_kpis, kpi  # noqa: E402

RAW       = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
OUT       = ROOT / "outputs" / "etapa1"
PROCESSED.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

# =============================================================================
# 1. CARREGAMENTO DAS BASES BRUTAS
# =============================================================================
# Todos os CSVs usam encoding latin1 (sistema legado brasileiro).
# dimensao_precos e dim_produto usam vírgula como separador decimal (padrão pt-BR).

print("Carregando bases brutas...")

# fato_vendas_1.csv (59 MB) e o unico insumo bruto NAO versionado (ver .gitignore
# e data/raw/README.md). Sem ele, so a Etapa 1 falha; as Etapas 2-7 reproduzem a
# partir dos Parquets ja versionados em data/processed/. Mensagem clara evita o
# traceback cru de "arquivo nao encontrado" num clone limpo.
_fato_vendas = RAW / "fato_vendas_1.csv"
if not _fato_vendas.exists():
    raise FileNotFoundError(
        f"Insumo bruto ausente: {_fato_vendas}.\n"
        "Coloque fato_vendas_1.csv (entregue a parte com o case) em data/raw/ "
        "para rodar a Etapa 1. Veja data/raw/README.md. As Etapas 2-7 nao precisam "
        "dele: partem dos Parquets ja versionados em data/processed/."
    )

vendas   = pd.read_csv(RAW / "fato_vendas_1.csv",            index_col=0, encoding="latin1")
compras  = pd.read_csv(RAW / "fato_compras_2.csv",           index_col=0, encoding="latin1")
estoque  = pd.read_csv(RAW / "fato_estoque_inicial_2.csv",   sep=";",     encoding="latin1")
produtos = pd.read_csv(RAW / "dim_produto_1.csv",            sep=";",     encoding="latin1")
lojas    = pd.read_csv(RAW / "dimensao_lojas_2.csv",         sep=";",     encoding="latin1")
precos   = pd.read_csv(RAW / "dimensao_precos_2.csv",        sep=";",     encoding="latin1")
unidades = pd.read_csv(RAW / "Descr_unidades_medida_2.csv",  sep=";",     encoding="latin1")
voltagem = pd.read_csv(RAW / "dimensao_voltagem_2.csv",      sep=";",     encoding="latin1")

# =============================================================================
# 2. TRATAMENTOS — com justificativa em cada decisão
# =============================================================================

# ── 2.1 Datas ────────────────────────────────────────────────────────────────
vendas["DATA_VENDA"]    = pd.to_datetime(vendas["DATA_VENDA"])
compras["DATA_ENTRADA"] = pd.to_datetime(compras["DATA_ENTRADA"])

# ── 2.2 Estoque inicial — nulos → 0 ──────────────────────────────────────────
# DECISÃO: 1.329 registros sem valor (5,2%) tratados como 0.
# Justificativa: ausência de registro indica produto sem estoque naquela loja
# no início do período. Tratar como 0 é conservador — gera alertas precoces
# de ruptura, direção segura para o negócio.
# Conta os nulos ANTES do fillna (KPI protegido: 1.329 registros, 5,2%).
_estoque_total = int(len(estoque))
_estoque_nulos = int(pd.to_numeric(estoque["ESTOQUE_INICIAL"], errors="coerce").isna().sum())
estoque["ESTOQUE_INICIAL"] = pd.to_numeric(
    estoque["ESTOQUE_INICIAL"], errors="coerce"
).fillna(0)

# ── 2.3 Preços — vírgula → ponto decimal ─────────────────────────────────────
# DECISÃO: campos numéricos em dimensao_precos usam vírgula (padrão pt-BR).
# Sem conversão, pd.to_numeric retorna NaN e inviabiliza cálculos de margem.
for col in ["PRECO_EMBALAGEM_0", "PRECO_EMBALAGEM_1", "PRECO_EMBALAGEM_2",
            "PERC_DESCTO_ADICIONAL_EMBALAGEM_0"]:
    precos[col] = (
        precos[col].astype(str).str.replace(",", ".", regex=False)
    )
    precos[col] = pd.to_numeric(precos[col], errors="coerce")

# ── 2.4 Conversão de compra em produtos ──────────────────────────────────────
# Mesmo problema de vírgula decimal. Fator errado distorce todo o cálculo
# de volume de estoque na Etapa 2.
produtos["CONVERSAO_COMPRA_ARMAZENAGEM"] = pd.to_numeric(
    produtos["CONVERSAO_COMPRA_ARMAZENAGEM"]
    .astype(str).str.replace(",", ".", regex=False),
    errors="coerce",
)

# ── 2.5 Colunas derivadas em vendas ──────────────────────────────────────────
# RECEITA: necessária para todos os rankings e análises de desempenho.
# QTD_ARMAZENAGEM: sem conversão, 1 caixa seria somada como 1 unidade —
#   distorce cobertura de estoque, compras e alertas de ruptura.
vendas["RECEITA"]         = vendas["QUANTIDADE_VENDIDA"].astype(float) * vendas["PRECO_UNIT_MEDIO"].astype(float)
vendas["QTD_ARMAZENAGEM"] = vendas["QUANTIDADE_VENDIDA"].astype(float) * vendas["CONVERSAO_VENDA_PARA_ARMAZENAGEM"].astype(float)
vendas["ANO_MES"]         = vendas["DATA_VENDA"].dt.to_period("M").astype(str)
vendas["ANO"]             = vendas["DATA_VENDA"].dt.year
vendas["MES"]             = vendas["DATA_VENDA"].dt.month

# DECISÃO: loja 93 (Alhandra-PB) opera como atacado/B2B.
# Ticket médio R$6.160 vs R$309 da rede; 76% da receita em Eletros.
# Flag criada para filtros rápidos em qualquer análise.
vendas["FLAG_LOJA93"] = (vendas["COD_EMPRESA"] == 93).astype(int)

# ── 2.6 Colunas derivadas em compras ─────────────────────────────────────────
compras["VALOR_TOTAL_COMPRA"] = (
    compras["QUANTIDADE_COMPRA"] * compras["PRECO_UNIT_UNIDADE_COMPRA"]
)
# DECISÃO: 132 entradas sem preço (9,5%) — volume físico mantido para
# cálculo de estoque; excluídos apenas do CMV e valor total de compras.
compras["FLAG_SEM_PRECO"] = compras["PRECO_UNIT_UNIDADE_COMPRA"].isna().astype(int)
compras["ANO_MES"]        = compras["DATA_ENTRADA"].dt.to_period("M").astype(str)

# ── 2.7 Join principal — vendas enriquecida ───────────────────────────────────
vendas_enr = (
    vendas
    .merge(
        produtos[["CODIGO", "DESCRICAO", "NIVEL_1", "NIVEL_2", "NIVEL_3",
                  "UNIDADE_ESTOQUE", "CONVERSAO_COMPRA_ARMAZENAGEM", "CD_VOLTAGEM"]],
        on="CODIGO", how="left",
    )
    .merge(lojas, on="COD_EMPRESA", how="left")
)

# =============================================================================
# 3. VERIFICAÇÕES DE INTEGRIDADE
# =============================================================================
print("\n--- Integridade referencial ---")
codigos_vendas   = set(vendas["CODIGO"].unique())
codigos_dim      = set(produtos["CODIGO"].unique())
codigos_compras  = set(compras["CODIGO"].unique())
lojas_vendas     = set(vendas["COD_EMPRESA"].unique())
lojas_dim        = set(lojas["COD_EMPRESA"].unique())

print(f"Produtos em vendas sem dim_produto : {len(codigos_vendas - codigos_dim)}")
print(f"Produtos em compras sem dim_produto: {len(codigos_compras - codigos_dim)}")
print(f"Lojas em vendas sem dim_lojas      : {len(lojas_vendas - lojas_dim)}")
print(f"Produtos sem nenhuma venda         : {len(codigos_dim - codigos_vendas)}")
print(f"Nulos em NIVEL_1 após join         : {vendas_enr['NIVEL_1'].isna().sum()}")
print(f"Nulos em CD_CIDADE após join       : {vendas_enr['CD_CIDADE'].isna().sum()}")

# =============================================================================
# 4. ESTATÍSTICAS RESUMO
# =============================================================================
print("\n--- Resumo geral ---")
print(f"Receita total (24M) : R$ {vendas_enr['RECEITA'].sum()/1e6:.1f}M")
print(f"Transações          : {len(vendas_enr):,}")
print(f"SKUs ativos         : {vendas_enr['CODIGO'].nunique():,}")
print(f"Período             : {vendas_enr['DATA_VENDA'].min().date()} → {vendas_enr['DATA_VENDA'].max().date()}")
print(f"Lojas               : {vendas_enr['COD_EMPRESA'].nunique()}")

# =============================================================================
# 4b. GATE DE QUALIDADE — asserts bloqueantes (falham a Etapa 1 se violados)
# =============================================================================
# As checagens impressas acima viram asserts: se qualquer premissa de base quebrar
# (join perdeu dimensao, periodo mudou, loja a mais/menos, receita fora da faixa),
# a Etapa 1 para AQUI e nao grava Parquets inconsistentes para as etapas seguintes.
print("\n--- Gate de qualidade (asserts) ---")

# Integridade referencial: nenhum produto/loja de vendas sem cadastro.
assert not (codigos_vendas - codigos_dim), \
    f"{len(codigos_vendas - codigos_dim)} produtos em vendas sem dim_produto"
assert not (lojas_vendas - lojas_dim), \
    f"{len(lojas_vendas - lojas_dim)} lojas em vendas sem dim_lojas"

# Sem nulos nas dimensoes criticas apos o join (todas as agregacoes dependem delas).
n_nulos_nivel1 = int(vendas_enr["NIVEL_1"].isna().sum())
n_nulos_cidade = int(vendas_enr["CD_CIDADE"].isna().sum())
assert n_nulos_nivel1 == 0, f"NIVEL_1 tem {n_nulos_nivel1} nulos apos o join"
assert n_nulos_cidade == 0, f"CD_CIDADE tem {n_nulos_cidade} nulos apos o join"

# Periodo esperado: 2024-01 a 2025-12 (24 meses completos).
periodo_min = vendas_enr["DATA_VENDA"].min()
periodo_max = vendas_enr["DATA_VENDA"].max()
assert (periodo_min.year, periodo_min.month) == (2024, 1), f"Inicio inesperado: {periodo_min.date()}"
assert (periodo_max.year, periodo_max.month) == (2025, 12), f"Fim inesperado: {periodo_max.date()}"

# 11 lojas esperadas (9 fisicas + loja 92 + loja 93 atacado).
n_lojas = vendas_enr["COD_EMPRESA"].nunique()
assert n_lojas == 11, f"Esperava 11 lojas, encontrou {n_lojas}"

# Receita total ~R$ 482,5M (banda de tolerancia, nao numero magico exato).
receita_total = float(vendas_enr["RECEITA"].sum())
assert 481e6 <= receita_total <= 484e6, \
    f"Receita total fora da faixa esperada (~R$482,5M): R$ {receita_total/1e6:.1f}M"

print(f"OK: integridade 0 orfaos | NIVEL_1/CD_CIDADE 0 nulos | "
      f"periodo {periodo_min.date()}..{periodo_max.date()} | {n_lojas} lojas | "
      f"receita R$ {receita_total/1e6:.1f}M")

# ── SSOT de KPI (fonte única; ver src/kpis.py) ────────────────────────────────
_compras_total = int(len(compras))
_compras_sem_preco = int(compras["FLAG_SEM_PRECO"].sum())
_orfaos = (len(codigos_vendas - codigos_dim)
           + len(codigos_compras - codigos_dim)
           + len(lojas_vendas - lojas_dim))
emit_kpis("etapa1", {
    "e1.receita_total": kpi(receita_total, "R$", "etapa1", "Receita total da rede completa (24 meses)"),
    "e1.transacoes": kpi(int(len(vendas_enr)), "linhas", "etapa1", "Linhas de venda (proxy de transações)"),
    "e1.skus_ativos": kpi(int(vendas_enr["CODIGO"].nunique()), "SKUs", "etapa1", "SKUs ativos (com venda no período)"),
    "e1.lojas": kpi(int(n_lojas), "lojas", "etapa1", "Lojas na base (físicas + 92 + 93 atacado)"),
    "e1.estoque_nulo.registros": kpi(_estoque_nulos, "reg", "etapa1", "Registros de estoque inicial sem valor (tratados como 0)"),
    "e1.estoque_nulo.pct": kpi(_estoque_nulos / _estoque_total * 100, "%", "etapa1", "% de registros de estoque inicial sem valor"),
    "e1.compras_sem_preco.registros": kpi(_compras_sem_preco, "linhas", "etapa1", "Linhas de compra sem preço (excluídas do CMV)"),
    "e1.compras_sem_preco.pct": kpi(_compras_sem_preco / _compras_total * 100, "%", "etapa1", "% de linhas de compra sem preço"),
    "e1.integridade.orfaos": kpi(int(_orfaos), "regs", "etapa1", "Órfãos de integridade referencial (vendas/compras sem dimensão)"),
    "e1.integridade.nulos_dimensoes": kpi(int(n_nulos_nivel1 + n_nulos_cidade), "regs", "etapa1", "Nulos em NIVEL_1/CD_CIDADE após o join"),
})

# =============================================================================
# 5. SALVAR BASES TRATADAS
# =============================================================================
print("\nSalvando Parquets...")

vendas_enr.to_parquet(PROCESSED / "vendas_tratadas.parquet",         index=False)
compras.to_parquet(   PROCESSED / "compras_tratadas.parquet",         index=False)
estoque.to_parquet(   PROCESSED / "estoque_inicial_tratado.parquet",  index=False)
produtos.to_parquet(  PROCESSED / "dim_produto_tratada.parquet",      index=False)
precos.to_parquet(    PROCESSED / "dim_precos_tratada.parquet",       index=False)
lojas.to_parquet(     PROCESSED / "dim_lojas.parquet",                index=False)
unidades.to_parquet(  PROCESSED / "dim_unidades.parquet",             index=False)
voltagem.to_parquet(  PROCESSED / "dim_voltagem.parquet",             index=False)

print("✓ Bases salvas em data/processed/")
