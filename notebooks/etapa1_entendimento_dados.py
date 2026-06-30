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

# Ajusta path para importar src/utils
sys.path.append(str(Path("..") / "src"))

RAW       = Path("..") / "data" / "raw"
PROCESSED = Path("..") / "data" / "processed"
OUT       = Path("..") / "outputs" / "etapa1"
PROCESSED.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

# =============================================================================
# 1. CARREGAMENTO DAS BASES BRUTAS
# =============================================================================
# Todos os CSVs usam encoding latin1 (sistema legado brasileiro).
# dimensao_precos e dim_produto usam vírgula como separador decimal (padrão pt-BR).

print("Carregando bases brutas...")

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
