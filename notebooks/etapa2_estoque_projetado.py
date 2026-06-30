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
6. Investigar outliers de preço (variação intra-loja×produto) e documentar a causa

Premissas e decisões metodológicas
-----------------------------------
- Unidade de trabalho: unidade de ARMAZENAGEM (não de venda nem de compra).
  Vendas: QTD × CONVERSAO_VENDA_PARA_ARMAZENAGEM
  Compras: QUANTIDADE_COMPRA × CONVERSAO_COMPRA_ARMAZENAGEM (da dim_produto)
- Loja 93 (Alhandra) é operação B2B/atacado. A separação loja-93-vs-rede é
  aplicada como FILTRO POSTERIOR nas análises de portfólio da rede física —
  nunca como remoção de dados ANTES de cálculos de receita ou de estoque
  (ver correção do Bug 1 abaixo).
- Estoque negativo: indica saídas acima do estoque visível na base.
  Causa provável: transferências entre lojas não registradas, ou estoque
  real superior ao capturado na foto inicial. Tratamos negativos como ruptura
  para fins de análise conservadora de reposição.
- Universo de análise (skeleton): UNIÃO dos pares loja×produto presentes em
  estoque inicial, vendas E compras. Pares com venda/compra mas sem foto de
  estoque inicial entram com ESTOQUE_INICIAL = 0 (mesma lógica conservadora
  já adotada na Etapa 1 para nulos de estoque). Ver correção do Bug 2.
- Dias de cobertura = (Estoque_dez25 / Venda_media_mensal) × 30, com piso em 0
  para pares em ruptura (ESTOQUE_PROJ ≤ 0). Ver correção do Bug 3.
  Pares sem histórico de venda na rede física recebem cobertura ∞
  (capital imobilizado).

Revisão de qualidade (correções aplicadas nesta versão)
-------------------------------------------------------
- Bug 1 (crítico): receita por par passou a ser calculada com TODAS as lojas
  (excluir_atacado=False). Antes, a loja 93 era removida antes do cálculo,
  zerando a RECEITA_TOTAL de 263 pares da loja 93 em ruptura e tirando-os do
  ranking de prioridade de reposição.
- Bug 2 (crítico): skeleton passou a unir os pares de estoque inicial + vendas
  + compras. Antes usava só estoque inicial, ignorando 3.379 pares com venda e
  sem estoque inicial (R$ 87,5M, 18,1% da receita).
- Bug 3 (médio): DIAS_COBERTURA recebe piso 0 quando ESTOQUE_PROJ ≤ 0. Antes
  gerava valores negativos (ex: -566 dias) sem significado de negócio.
- Bug 4 (médio, investigado): variação de preço intra-loja×produto. Conclusão
  documentada em outputs/etapa2/investigacao_outliers_preco.csv.

Limitações conhecidas (sinalizadas, não corrigidas aqui)
--------------------------------------------------------
- VENDA_MEDIA_MES é a média dos meses COM venda, não dos 24 meses. Para itens
  intermitentes isso superestima a velocidade e subestima os dias de cobertura.
  Revisitar com média sobre 24 meses em iteração futura.
- A taxa de ruptura (~91%) reflete a ausência de registros de reposição na base
  (~88% dos SKUs vendem sem compra registrada) + estoque nulo = 0. É um indicador
  de PRIORIZAÇÃO RELATIVA, não de disponibilidade física absoluta.

Saídas
------
data/processed/estoque_projetado.parquet      — série histórica mensal loja×produto
data/processed/cobertura_estoque.parquet      — snapshot dez/25 com status e cobertura
outputs/etapa2/cobertura_estoque.csv          — versão CSV para consulta
outputs/etapa2/investigacao_outliers_preco.csv — diagnóstico de outliers de preço (Bug 4)
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Raiz do repositório resolvida a partir do arquivo (roda de qualquer diretório)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from utils import (PROCESSED, OUTPUTS, LOJA_ATACADO,
                   load_vendas, load_compras, load_estoque_inicial,
                   load_dim_produto, load_dim_lojas)

OUT = OUTPUTS / "etapa2"
OUT.mkdir(parents=True, exist_ok=True)

# =============================================================================
# 1. CARREGAR BASES TRATADAS
# =============================================================================
print("Carregando bases tratadas...")

# Carregamos as vendas com TODAS as lojas (excluir_atacado=False). A loja 93
# também movimenta estoque e gera receita: removê-la aqui zeraria indicadores
# de pares válidos. A separação loja-93-vs-rede física é feita só como filtro
# posterior, dentro de cada análise que precise dela (Bug 1).
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
# DECISÃO (Bug 2): o universo de pares loja×produto é a UNIÃO dos pares de
# estoque inicial, vendas E compras — não apenas do estoque inicial.
# Justificativa: 3.379 pares têm venda registrada mas nenhuma foto de estoque
# inicial (R$ 87,5M, 18,1% da receita total). Usar só o estoque inicial como
# universo os apagava da projeção e da cobertura. Pares sem foto inicial entram
# com ESTOQUE_INICIAL = 0 — mesma lógica conservadora já documentada na Etapa 1
# para nulos de estoque (ausência de registro = sem estoque visível no início,
# o que gera alerta precoce de ruptura, direção segura para o negócio).
todos_meses = pd.period_range("2024-01", "2025-12", freq="M")
pares = (
    pd.concat([
        e[["COD_EMPRESA","CODIGO"]],
        v[["COD_EMPRESA","CODIGO"]],
        c[["COD_EMPRESA","CODIGO"]],
    ], ignore_index=True)
    .drop_duplicates()
    .reset_index(drop=True)
)

n_pares_estoque = len(e[["COD_EMPRESA","CODIGO"]].drop_duplicates())
print(f"Pares no skeleton: {len(pares):,} "
      f"(estoque inicial: {n_pares_estoque:,} | +{len(pares)-n_pares_estoque:,} de vendas/compras)")

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
    .fillna({"ESTOQUE_INICIAL": 0.0})   # pares sem foto inicial → 0 (ver Bug 2)
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
# Venda média mensal por par (base para dias de cobertura).
# Aqui a loja 93 é excluída de propósito: a cobertura em dias é uma referência
# de CONSUMO DA REDE FÍSICA. Esta é uma exclusão metodológica posterior (filtro
# de análise), não uma remoção de dados antes de um cálculo de receita.
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

# DECISÃO (Bug 3): pares em ruptura (ESTOQUE_PROJ ≤ 0) têm DIAS_COBERTURA = 0.
# Cobertura negativa (ex: -566 dias) não tem significado de negócio — a condição
# de ruptura já é capturada pelo STATUS_ESTOQUE "EM RUPTURA". O piso em 0 evita
# que valores negativos contaminem ordenações e médias em análises futuras.
cobertura["DIAS_COBERTURA"] = np.where(
    cobertura["ESTOQUE_PROJ"] <= 0, 0, cobertura["DIAS_COBERTURA"]
)

# Receita histórica por par (para priorizar reposição).
# DECISÃO (Bug 1): calculada com TODAS as lojas (sem remover a loja 93). O
# skeleton inclui pares da loja 93 (ela está em fato_estoque_inicial); remover
# a loja 93 aqui zerava a RECEITA_TOTAL desses pares e os apagava do ranking de
# prioridade. A receita é um fato do par — a separação atacado×rede é feita
# depois, por análise.
rec_por_par = (
    v
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
# 7. INVESTIGAÇÃO DE OUTLIERS DE PREÇO (Bug 4)
# =============================================================================
# Há pares loja×produto com variação enorme de PRECO_UNIT_MEDIO (CV > 1).
# Caso emblemático: CODIGO 119959 (Adaptador Cx. Elét. 3/4), preço de R$3,68 a
# R$391,55 na mesma loja. Hipótese a testar: os lançamentos caros são vendas em
# EMBALAGEM=1 (caixa/pack). Se a CONVERSAO_VENDA_PARA_ARMAZENAGEM dessas linhas
# fosse 1, seria um bug (preço da caixa lançado como unitário, conversão ausente).
# Se a conversão estiver presente (> 1), o preço alto é legítimo: a caixa custa
# o preço unitário × tamanho do pack, e a QTD_ARMAZENAGEM já é normalizada.
print("\nInvestigando outliers de preço (Bug 4)...")

preco_stats = (
    v.groupby(["COD_EMPRESA","CODIGO"])["PRECO_UNIT_MEDIO"]
    .agg(PRECO_MIN="min", PRECO_MAX="max", PRECO_MEDIO="mean",
         PRECO_STD="std", N_LANC="count")
    .reset_index()
)
preco_stats["CV"] = preco_stats["PRECO_STD"] / preco_stats["PRECO_MEDIO"]
outliers = preco_stats[preco_stats["CV"] > 1].copy()

# Estatísticas dos lançamentos em EMBALAGEM=1 (embalagem alternativa) por par
emb1 = (
    v[v["EMBALAGEM"] == 1]
    .groupby(["COD_EMPRESA","CODIGO"])
    .agg(EMB1_N=("PRECO_UNIT_MEDIO","count"),
         EMB1_CONV_MIN=("CONVERSAO_VENDA_PARA_ARMAZENAGEM","min"),
         EMB1_CONV_MAX=("CONVERSAO_VENDA_PARA_ARMAZENAGEM","max"),
         EMB1_PRECO_MAX=("PRECO_UNIT_MEDIO","max"))
    .reset_index()
)
outliers = outliers.merge(emb1, on=["COD_EMPRESA","CODIGO"], how="left")
outliers["EMB1_N"] = outliers["EMB1_N"].fillna(0).astype(int)

def diagnostica_outlier(r):
    """Classifica a causa da variação de preço e a 'suspeita de bug de embalagem'."""
    if r["EMB1_N"] > 0:
        # tem vendas em embalagem alternativa (caixa/pack)
        conv = r["EMB1_CONV_MAX"]
        if pd.notna(conv) and conv > 1:
            # conversão presente (> 1) → o preço alto é o da caixa/pack, e a
            # QTD_ARMAZENAGEM já é normalizada (QTD × conversão). Não é o bug de
            # conversão ausente; a variação de preço é esperada.
            unit = r["EMB1_PRECO_MAX"] / conv
            hip = (f"Preço alto = venda em embalagem/caixa (EMBALAGEM=1, "
                   f"CONVERSAO={conv:g}); preço por unidade de armazenagem ≈ "
                   f"R${unit:.2f}. Conversão presente (≠1) — não é o bug de "
                   f"conversão ausente.")
            return pd.Series({"HIPOTESE": hip, "EMBALAGEM_SUSPEITA": "não"})
        else:
            # EMBALAGEM=1 com CONVERSAO=1 → conversão ausente, preço da caixa como unitário
            hip = ("EMBALAGEM=1 com CONVERSAO=1: preço de caixa lançado como "
                   "unitário sem conversão — provável erro de cadastro (bug).")
            return pd.Series({"HIPOTESE": hip, "EMBALAGEM_SUSPEITA": "sim"})
    else:
        # CV alto sem embalagem alternativa → variação de preço no tempo
        hip = ("Variação de preço sem mudança de embalagem (EMBALAGEM=0 em todos "
               "os lançamentos): repricing/desconto ao longo do período.")
        return pd.Series({"HIPOTESE": hip, "EMBALAGEM_SUSPEITA": "não"})

diag = outliers.apply(diagnostica_outlier, axis=1)
outliers = pd.concat([outliers, diag], axis=1)
outliers = outliers.merge(p[["CODIGO","DESCRICAO"]], on="CODIGO", how="left")

# Arredonda para leitura (evita ruído de ponto flutuante no CSV)
outliers["PRECO_MIN"] = outliers["PRECO_MIN"].round(2)
outliers["PRECO_MAX"] = outliers["PRECO_MAX"].round(2)
outliers["CV"]        = outliers["CV"].round(3)

investigacao = (outliers
    .sort_values("CV", ascending=False)
    [["COD_EMPRESA","CODIGO","DESCRICAO","PRECO_MIN","PRECO_MAX","CV",
      "HIPOTESE","EMBALAGEM_SUSPEITA"]]
    .reset_index(drop=True)
)

print(f"  Pares loja×produto com CV de preço > 1: {len(investigacao)}")
print(f"  Classificados como suspeita de bug de embalagem (sim): "
      f"{(investigacao['EMBALAGEM_SUSPEITA']=='sim').sum()}")
print(f"  Explicados (venda em caixa com conversão / repricing): "
      f"{(investigacao['EMBALAGEM_SUSPEITA']=='não').sum()}")

# =============================================================================
# 8. ANÁLISE DE RESULTADOS
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
# 9. SALVAR SAÍDAS
# =============================================================================
df.to_parquet(PROCESSED / "estoque_projetado.parquet",    index=False)
cobertura.to_parquet(PROCESSED / "cobertura_estoque.parquet", index=False)
cobertura.to_csv(OUT / "cobertura_estoque.csv",            index=False, encoding="utf-8-sig")
investigacao.to_csv(OUT / "investigacao_outliers_preco.csv", index=False, encoding="utf-8-sig")

print("\n[OK] Arquivos salvos:")
print(f"  data/processed/estoque_projetado.parquet  ({len(df):,} linhas)")
print(f"  data/processed/cobertura_estoque.parquet  ({len(cobertura):,} linhas)")
print(f"  outputs/etapa2/cobertura_estoque.csv")
print(f"  outputs/etapa2/investigacao_outliers_preco.csv  ({len(investigacao):,} linhas)")
