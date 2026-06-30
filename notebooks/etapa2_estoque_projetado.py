"""
etapa2_estoque_projetado.py
============================
Etapa 2 — Construção do Estoque Projetado e Análise de Cobertura

Objetivos
---------
1. Projetar o estoque mês a mês: Estoque_t = Estoque_inicial + ΣEntradas - ΣSaídas
2. Identificar pares loja×produto em ruptura (estoque ≤ 0) em dez/2025
3. Calcular dias de cobertura para cada par
4. Classificar o portfólio em: Em Ruptura / Crítico / Atenção / Saudável / Sem Venda
5. Priorizar por receita histórica os itens que exigem reposição urgente

Premissas e decisões metodológicas
-----------------------------------
- Unidade de trabalho: unidade de ARMAZENAGEM (não de venda nem de compra).
  Vendas: QTD × CONVERSAO_VENDA_PARA_ARMAZENAGEM
  Compras: QUANTIDADE_COMPRA × CONVERSAO_COMPRA_ARMAZENAGEM (da dim_produto)
- Loja 93 (Alhandra) é analisada em separado por ser operação B2B/atacado.
- Estoque negativo: indica saídas acima do estoque visível na base.
  Causa provável: transferências entre lojas não registradas, ou estoque
  real superior ao capturado na foto inicial. Tratamos negativos como ruptura
  para fins de análise conservadora de reposição.
- Dias de cobertura = (Estoque_dez25 / Venda_media_mensal) × 30.
  Pares sem histórico de venda recebem cobertura ∞ (capital imobilizado).

Saídas
------
data/processed/estoque_projetado.parquet  — série histórica mensal loja×produto
data/processed/cobertura_estoque.parquet  — snapshot dez/25 com status e cobertura
outputs/etapa2/cobertura_estoque.csv      — versão CSV para consulta
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.append(str(Path("..") / "src"))
from utils import (PROCESSED, OUTPUTS, LOJA_ATACADO,
                   load_vendas, load_compras, load_estoque_inicial,
                   load_dim_produto, load_dim_lojas)

OUT = OUTPUTS / "etapa2"
OUT.mkdir(parents=True, exist_ok=True)

# =============================================================================
# 1. CARREGAR BASES TRATADAS
# =============================================================================
print("Carregando bases tratadas...")

# Inclui loja 93 nas vendas para o cálculo de estoque (ela também movimenta estoques)
v = load_vendas(excluir_atacado=False)
c = load_compras()
e = load_estoque_inicial()
p = load_dim_produto()
l = load_dim_lojas()

# =============================================================================
# 2. CONVERTER COMPRAS PARA UNIDADE DE ARMAZENAGEM
# =============================================================================
# A quantidade de compra está na unidade do fornecedor (ex: caixas).
# Precisamos convertê-la para a mesma unidade do estoque para somar corretamente.
conv_map = p.set_index("CODIGO")["CONVERSAO_COMPRA_ARMAZENAGEM"]
c["CONVERSAO_COMPRA_ARM"] = c["CODIGO"].map(conv_map).fillna(1.0)
c["QTD_COMPRA_ARM"]       = c["QUANTIDADE_COMPRA"] * c["CONVERSAO_COMPRA_ARM"]

# =============================================================================
# 3. AGREGAR MOVIMENTOS MENSAIS
# =============================================================================
v["ANO_MES_DT"] = v["DATA_VENDA"].dt.to_period("M")
c["ANO_MES_DT"] = c["DATA_ENTRADA"].dt.to_period("M")

saidas_mensais = (
    v.groupby(["COD_EMPRESA","CODIGO","ANO_MES_DT"])["QTD_ARMAZENAGEM"]
    .sum().reset_index()
    .rename(columns={"QTD_ARMAZENAGEM": "SAIDA_MES"})
)

entradas_mensais = (
    c.groupby(["COD_EMPRESA","CODIGO","ANO_MES_DT"])["QTD_COMPRA_ARM"]
    .sum().reset_index()
    .rename(columns={"QTD_COMPRA_ARM": "ENTRADA_MES"})
)

# =============================================================================
# 4. CONSTRUIR SKELETON: todos os pares loja×produto × todos os meses
# =============================================================================
# Usamos os pares do estoque inicial como universo de análise.
# Isso garante que produtos sem movimento em algum mês continuem na série.
todos_meses = pd.period_range("2024-01", "2025-12", freq="M")
pares       = e[["COD_EMPRESA","CODIGO"]].drop_duplicates()

skeleton = (
    pares.assign(key=1)
    .merge(pd.DataFrame({"ANO_MES_DT": todos_meses, "key": 1}), on="key")
    .drop("key", axis=1)
)

# =============================================================================
# 5. CALCULAR ESTOQUE PROJETADO (série mensal)
# =============================================================================
df = (
    skeleton
    .merge(saidas_mensais,   on=["COD_EMPRESA","CODIGO","ANO_MES_DT"], how="left")
    .merge(entradas_mensais, on=["COD_EMPRESA","CODIGO","ANO_MES_DT"], how="left")
    .fillna({"SAIDA_MES": 0.0, "ENTRADA_MES": 0.0})
    .merge(e, on=["COD_EMPRESA","CODIGO"], how="left")
    .fillna({"ESTOQUE_INICIAL": 0.0})
    .sort_values(["COD_EMPRESA","CODIGO","ANO_MES_DT"])
    .reset_index(drop=True)
)

# Movimentação acumulada desde o início do período
df["MOVIMENTACAO"] = df["ENTRADA_MES"] - df["SAIDA_MES"]
df["MOVIM_ACUM"]   = df.groupby(["COD_EMPRESA","CODIGO"])["MOVIMENTACAO"].cumsum()
df["ESTOQUE_PROJ"] = df["ESTOQUE_INICIAL"] + df["MOVIM_ACUM"]
df["ANO_MES_STR"]  = df["ANO_MES_DT"].astype(str)

# Enriquecer com dimensões
df = (df
    .merge(p[["CODIGO","DESCRICAO","NIVEL_1","NIVEL_2","UNIDADE_ESTOQUE"]], on="CODIGO", how="left")
    .merge(l, on="COD_EMPRESA", how="left")
)

print(f"Série temporal projetada: {len(df):,} linhas ({df['COD_EMPRESA'].nunique()} lojas × {df['CODIGO'].nunique()} produtos × 24 meses)")

# =============================================================================
# 6. SNAPSHOT DE COBERTURA — DEZEMBRO 2025
# =============================================================================
# Venda média mensal por par (base para dias de cobertura)
# Excluímos loja 93 das referências de consumo da rede física
venda_mensal_media = (
    v[v["COD_EMPRESA"] != LOJA_ATACADO]
    .groupby(["COD_EMPRESA","CODIGO","ANO_MES_DT"])["QTD_ARMAZENAGEM"].sum()
    .groupby(["COD_EMPRESA","CODIGO"]).mean()
    .reset_index()
    .rename(columns={"QTD_ARMAZENAGEM": "VENDA_MEDIA_MES"})
)

estoque_final = df[df["ANO_MES_DT"] == pd.Period("2025-12","M")][
    ["COD_EMPRESA","CODIGO","ESTOQUE_PROJ"]
].copy()

cobertura = (
    estoque_final
    .merge(venda_mensal_media, on=["COD_EMPRESA","CODIGO"], how="left")
)
cobertura["VENDA_MEDIA_MES"] = cobertura["VENDA_MEDIA_MES"].fillna(0)

# Dias de cobertura: Estoque / Venda_media × 30 dias
# Se venda média = 0, cobertura é infinita (sem demanda → capital imobilizado)
cobertura["DIAS_COBERTURA"] = np.where(
    cobertura["VENDA_MEDIA_MES"] > 0,
    cobertura["ESTOQUE_PROJ"] / cobertura["VENDA_MEDIA_MES"] * 30,
    np.inf,
)

# Receita histórica por par (para priorizar reposição)
rec_por_par = (
    v[v["COD_EMPRESA"] != LOJA_ATACADO]
    .groupby(["COD_EMPRESA","CODIGO"])["RECEITA"].sum()
    .reset_index()
    .rename(columns={"RECEITA": "RECEITA_TOTAL"})
)

# Classificação de status
def classifica_estoque(row):
    if row["ESTOQUE_PROJ"] <= 0:
        return "EM RUPTURA"
    elif row["DIAS_COBERTURA"] <= 30:
        return "CRÍTICO"
    elif row["DIAS_COBERTURA"] <= 90:
        return "ATENÇÃO"
    elif row["DIAS_COBERTURA"] == np.inf:
        return "SEM VENDA"
    else:
        return "SAUDÁVEL"

cobertura["STATUS_ESTOQUE"] = cobertura.apply(classifica_estoque, axis=1)

# Enriquecer snapshot
cobertura = (cobertura
    .merge(rec_por_par, on=["COD_EMPRESA","CODIGO"], how="left")
    .merge(p[["CODIGO","DESCRICAO","NIVEL_1"]], on="CODIGO", how="left")
    .merge(l, on="COD_EMPRESA", how="left")
)

# =============================================================================
# 7. ANÁLISE DE RESULTADOS
# =============================================================================
print("\n--- Resumo de cobertura (dez/2025) ---")
status_count = cobertura["STATUS_ESTOQUE"].value_counts()
for status, n in status_count.items():
    pct = n / len(cobertura) * 100
    print(f"  {status:<15}: {n:>6,} pares ({pct:>5.1f}%)")

print("\n--- Top 10 em ruptura por receita histórica ---")
criticos = (cobertura[cobertura["STATUS_ESTOQUE"].isin(["EM RUPTURA","CRÍTICO"])]
    .sort_values("RECEITA_TOTAL", ascending=False)
    [["COD_EMPRESA","CD_CIDADE","CODIGO","DESCRICAO","NIVEL_1",
      "ESTOQUE_PROJ","DIAS_COBERTURA","RECEITA_TOTAL"]]
    .head(10)
)
print(criticos.to_string(index=False))

print("\n--- Capital imobilizado (saudável + sem venda) ---")
imob = cobertura[cobertura["STATUS_ESTOQUE"].isin(["SAUDÁVEL","SEM VENDA"])]
print(f"  Pares: {len(imob):,}")

# =============================================================================
# 8. SALVAR SAÍDAS
# =============================================================================
df.to_parquet(PROCESSED / "estoque_projetado.parquet",    index=False)
cobertura.to_parquet(PROCESSED / "cobertura_estoque.parquet", index=False)
cobertura.to_csv(OUT / "cobertura_estoque.csv",            index=False, encoding="utf-8-sig")

print("\n✓ Arquivos salvos:")
print(f"  data/processed/estoque_projetado.parquet  ({len(df):,} linhas)")
print(f"  data/processed/cobertura_estoque.parquet  ({len(cobertura):,} linhas)")
print(f"  outputs/etapa2/cobertura_estoque.csv")
