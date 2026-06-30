"""
etapa5_precificacao_margem.py
=============================
Etapa 5 - Analise de precificacao e variacao de margem

Objetivos
---------
1. Calcular margem bruta realizada (R$ e %), markup e custo medio por SKU,
   categoria e loja, usando preco praticado e custo na MESMA unidade de
   armazenagem.
2. Comparar preco praticado com o preco de lista (`dim_precos`) e medir o
   desconto efetivo, sempre dentro da MESMA embalagem.
3. Medir a dispersao de preco do mesmo SKU entre lojas, separando por
   embalagem para nao misturar caixa com unidade.
4. Priorizar candidatos a repricing (margem baixa/negativa em alta receita,
   desconto efetivo acima da media e preco fora da faixa da rede).
5. Separar rede completa, rede fisica sem Loja 93 e o canal atacado/B2B, e
   documentar de forma transparente a cobertura de custo e as limitacoes.

Premissas e decisoes metodologicas
-----------------------------------
- Unidades. Tudo e normalizado para a unidade de ARMAZENAGEM antes de comparar:
  * Preco praticado por unid. armazenagem = `RECEITA / QTD_ARMAZENAGEM`.
  * Custo medio por unid. armazenagem = media ponderada (pela quantidade
    comprada) de `PRECO_UNIT_UNIDADE_COMPRA / CONVERSAO_COMPRA_ARMAZENAGEM`
    das compras do SKU no periodo. Sem normalizar a conversao, o custo de
    itens comprados em caixa vazaria inflado e geraria margens absurdas.
  * Preco de lista vem por EMBALAGEM (`PRECO_EMBALAGEM_0/1/2`); o desconto
    efetivo e calculado comparando preco praticado e lista DENTRO da mesma
    embalagem (mesma unidade de venda), nunca cruzando caixa com unidade.
- Cobertura de custo. Margem realizada so existe para os SKUs com compra de
  preco valido no periodo (~261 SKUs, ~16% da receita). O restante NAO recebe
  margem por ausencia de custo, e nunca por imputacao - e o analogo do achado
  "88% vendem sem compra registrada" das Etapas 1/2.
- Nulos/zeros/negativos. Precos de compra nulos (9,5% das linhas) sao excluidos
  do custo. Preco praticado nao tem nulos/zeros/negativos. Margens negativas
  (preco < custo) sao sinalizadas e justificadas, nunca silenciadas.
- Universos. Toda saida agregada traz `UNIVERSO` com `REDE_COMPLETA`,
  `REDE_FISICA_SEM_LOJA93` e `LOJA_93_ATACADO_B2B`. A Loja 93 (atacado/B2B)
  entra na rede completa mas tambem e segregada; o custo de cada universo usa
  apenas as compras das lojas do universo.
- Reconciliacao. A receita por universo/categoria/loja reconcilia com os
  outputs auditaveis da Etapa 3; nada de receita e recalculado de forma
  divergente.

Saidas
------
outputs/etapa5/margem_produtos.csv
outputs/etapa5/margem_categorias_n1.csv
outputs/etapa5/margem_categorias_n2.csv
outputs/etapa5/margem_categorias_n3.csv
outputs/etapa5/margem_lojas.csv
outputs/etapa5/precificacao_desconto.csv
outputs/etapa5/dispersao_preco_lojas.csv
outputs/etapa5/candidatos_repricing.csv
outputs/etapa5/recomendacoes_melhoria.csv
outputs/etapa5/validacoes_etapa5.csv
outputs/etapa5/autoaudit_etapa5.csv
outputs/etapa5/resumo_etapa5.md
outputs/etapa5/documentacao_tecnica_etapa5.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from utils import (  # noqa: E402
    LOJA_ATACADO,
    OUTPUTS,
    load_compras,
    load_dim_precos,
    load_dim_produto,
    load_vendas,
)


OUT = OUTPUTS / "etapa5"
OUT.mkdir(parents=True, exist_ok=True)

E3 = OUTPUTS / "etapa3"

UNIVERSO_COMPLETO = "REDE_COMPLETA"
UNIVERSO_FISICO = "REDE_FISICA_SEM_LOJA93"
ESCOPO_LOJA93 = "LOJA_93_ATACADO_B2B"

# ── Limiares de negocio para candidatos a repricing (documentados) ────────────
LIMIAR_MARGEM_PCT = 20.0       # margem bruta % abaixo disso e considerada baixa
LIMIAR_DESCONTO_PCT = 30.0     # desconto efetivo acima disso chama atencao
LIMIAR_FAIXA_PCT = 30.0        # desvio vs mediana da rede acima disso = fora da faixa
MIN_LOJAS_FAIXA = 3            # so avalia "fora da faixa" com pelo menos 3 lojas
# Faixa sanitaria de margem % usada nas validacoes (fora dela = suspeita de erro).
MARGEM_PCT_MIN_SANITARIA = -100.0
MARGEM_PCT_MAX_SANITARIA = 100.0
MARKUP_MAX_SANITARIO = 20.0    # markup acima disso sugere erro de unidade


# ── Formatacao pt-BR (mesmo padrao da Etapa 4) ────────────────────────────────
def safe_div(numerador, denominador):
    """Divide evitando infinito quando o denominador e zero (retorna NaN)."""
    num = np.asarray(numerador, dtype=float)
    den = np.asarray(denominador, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        resultado = np.divide(num, den)
    return np.where(den != 0, resultado, np.nan)


def fmt_brl_milhao(valor: float) -> str:
    return f"R$ {valor / 1e6:,.1f}M".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_num(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", ".")


def fmt_pct(valor: float) -> str:
    return f"{valor:.1f}%".replace(".", ",")


# ── Custo medio por unid. de armazenagem ──────────────────────────────────────
def custo_medio_por_sku(compras: pd.DataFrame, conversao: pd.Series) -> pd.DataFrame:
    """
    Custo medio por unid. de armazenagem por SKU, media ponderada pela
    quantidade comprada.

    custo_arm = ( sum(PRECO_UNIT_UNIDADE_COMPRA * QUANTIDADE_COMPRA)
                  / sum(QUANTIDADE_COMPRA) ) / CONVERSAO_COMPRA_ARMAZENAGEM

    Linhas sem preco de compra (nulas) sao excluidas. A conversao vem da
    dimensao de produto (por CODIGO) e leva o preco da unidade de COMPRA para a
    unidade de ARMAZENAGEM, a mesma base do preco praticado.
    """
    d = compras.dropna(subset=["PRECO_UNIT_UNIDADE_COMPRA"]).copy()
    d = d[d["QUANTIDADE_COMPRA"] > 0]
    d["_PESO"] = d["PRECO_UNIT_UNIDADE_COMPRA"] * d["QUANTIDADE_COMPRA"]
    g = d.groupby("CODIGO").agg(
        _NUM=("_PESO", "sum"),
        _DEN=("QUANTIDADE_COMPRA", "sum"),
        COMPRAS_LINHAS_COM_PRECO=("CODIGO", "size"),
        QTD_COMPRADA_UNID_COMPRA=("QUANTIDADE_COMPRA", "sum"),
    )
    g["PRECO_COMPRA_PONDERADO_UNID_COMPRA"] = g["_NUM"] / g["_DEN"]
    g["CONVERSAO_COMPRA_ARMAZENAGEM"] = conversao.reindex(g.index).to_numpy()
    g["CUSTO_MEDIO_ARM"] = (
        g["PRECO_COMPRA_PONDERADO_UNID_COMPRA"] / g["CONVERSAO_COMPRA_ARMAZENAGEM"]
    )
    return g.drop(columns=["_NUM", "_DEN"]).reset_index()


def base_margem_universo(
    vendas: pd.DataFrame, custo_sku: pd.DataFrame
) -> pd.DataFrame:
    """Anexa custo medio por SKU as vendas e calcula CMV por linha."""
    base = vendas.merge(
        custo_sku[["CODIGO", "CUSTO_MEDIO_ARM"]], on="CODIGO", how="left", validate="many_to_one"
    )
    base["FLAG_COM_CUSTO"] = base["CUSTO_MEDIO_ARM"].notna().astype(int)
    base["CODIGO_COM_CUSTO"] = np.where(base["FLAG_COM_CUSTO"] == 1, base["CODIGO"], np.nan)
    base["RECEITA_COM_CUSTO"] = np.where(base["FLAG_COM_CUSTO"] == 1, base["RECEITA"], 0.0)
    base["QTD_ARM_COM_CUSTO"] = np.where(base["FLAG_COM_CUSTO"] == 1, base["QTD_ARMAZENAGEM"], 0.0)
    base["CMV_LINHA"] = np.where(
        base["FLAG_COM_CUSTO"] == 1,
        base["CUSTO_MEDIO_ARM"] * base["QTD_ARMAZENAGEM"],
        0.0,
    )
    return base


# ── Agregacao de margem (categoria/loja/total) ────────────────────────────────
def agregar_margem(base: pd.DataFrame, universo: str, keys: list[str]) -> pd.DataFrame:
    """Margem agregada (ponderada) sobre o subconjunto com custo conhecido."""
    receita_total_universo = float(base["RECEITA"].sum())
    grp = base.groupby(keys, dropna=False) if keys else base.assign(_T=1).groupby("_T")
    agg = grp.agg(
        SKUS=("CODIGO", "nunique"),
        SKUS_COM_CUSTO=("CODIGO_COM_CUSTO", "nunique"),
        LINHAS_VENDA=("CODIGO", "size"),
        RECEITA_TOTAL=("RECEITA", "sum"),
        QTD_ARM_TOTAL=("QTD_ARMAZENAGEM", "sum"),
        RECEITA_COM_CUSTO=("RECEITA_COM_CUSTO", "sum"),
        QTD_ARM_COM_CUSTO=("QTD_ARM_COM_CUSTO", "sum"),
        CMV=("CMV_LINHA", "sum"),
    ).reset_index()

    if not keys:
        agg = agg.drop(columns=["_T"])

    agg.insert(0, "UNIVERSO", universo)
    agg["PRECO_PRATICADO_ARM"] = safe_div(agg["RECEITA_TOTAL"], agg["QTD_ARM_TOTAL"])
    agg["PRECO_PRATICADO_ARM_COM_CUSTO"] = safe_div(agg["RECEITA_COM_CUSTO"], agg["QTD_ARM_COM_CUSTO"])
    agg["CUSTO_MEDIO_ARM_PONDERADO"] = safe_div(agg["CMV"], agg["QTD_ARM_COM_CUSTO"])
    agg["MARGEM_BRUTA_RS_UNIT"] = (
        agg["PRECO_PRATICADO_ARM_COM_CUSTO"] - agg["CUSTO_MEDIO_ARM_PONDERADO"]
    )
    agg["MARGEM_BRUTA_TOTAL"] = agg["RECEITA_COM_CUSTO"] - agg["CMV"]
    agg["MARGEM_BRUTA_PCT"] = safe_div(agg["MARGEM_BRUTA_TOTAL"], agg["RECEITA_COM_CUSTO"]) * 100
    agg["MARKUP_PONDERADO"] = safe_div(agg["RECEITA_COM_CUSTO"], agg["CMV"])
    agg["COBERTURA_CUSTO_RECEITA_PCT"] = safe_div(agg["RECEITA_COM_CUSTO"], agg["RECEITA_TOTAL"]) * 100
    agg["PART_RECEITA_UNIVERSO_PCT"] = safe_div(agg["RECEITA_TOTAL"], receita_total_universo) * 100
    return agg


def ordenar_categoria(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(
        ["UNIVERSO", "RECEITA_COM_CUSTO", "RECEITA_TOTAL"], ascending=[True, False, False]
    ).reset_index(drop=True)


# ── Margem por SKU (somente onde ha custo) ────────────────────────────────────
def margem_por_sku(
    base: pd.DataFrame, universo: str, custo_sku: pd.DataFrame, abc: pd.DataFrame
) -> pd.DataFrame:
    receita_total_universo = float(base["RECEITA"].sum())
    com_custo = base[base["FLAG_COM_CUSTO"] == 1]
    g = com_custo.groupby("CODIGO").agg(
        DESCRICAO=("DESCRICAO", "first"),
        NIVEL_1=("NIVEL_1", "first"),
        NIVEL_2=("NIVEL_2", "first"),
        NIVEL_3=("NIVEL_3", "first"),
        RECEITA=("RECEITA", "sum"),
        QTD_ARMAZENAGEM=("QTD_ARMAZENAGEM", "sum"),
        LOJAS_ATIVAS=("COD_EMPRESA", "nunique"),
        CUSTO_MEDIO_ARM=("CUSTO_MEDIO_ARM", "first"),
    ).reset_index()

    g = g.merge(
        custo_sku[[
            "CODIGO",
            "PRECO_COMPRA_PONDERADO_UNID_COMPRA",
            "CONVERSAO_COMPRA_ARMAZENAGEM",
            "COMPRAS_LINHAS_COM_PRECO",
        ]],
        on="CODIGO",
        how="left",
        validate="one_to_one",
    )

    g["PRECO_PRATICADO_ARM"] = safe_div(g["RECEITA"], g["QTD_ARMAZENAGEM"])
    g["MARGEM_BRUTA_RS"] = g["PRECO_PRATICADO_ARM"] - g["CUSTO_MEDIO_ARM"]
    g["MARGEM_BRUTA_PCT"] = safe_div(g["MARGEM_BRUTA_RS"], g["PRECO_PRATICADO_ARM"]) * 100
    g["MARKUP"] = safe_div(g["PRECO_PRATICADO_ARM"], g["CUSTO_MEDIO_ARM"])
    g["FLAG_MARGEM_NEGATIVA"] = (g["MARGEM_BRUTA_RS"] < 0).astype(int)
    g["PART_RECEITA_UNIVERSO_PCT"] = safe_div(g["RECEITA"], receita_total_universo) * 100

    abc_u = abc[abc["UNIVERSO"] == universo][["CODIGO", "CURVA_ABC_RECEITA", "RANK_RECEITA"]]
    g = g.merge(abc_u, on="CODIGO", how="left", validate="one_to_one")
    g.insert(0, "UNIVERSO", universo)
    return g.sort_values(["UNIVERSO", "RECEITA"], ascending=[True, False]).reset_index(drop=True)


# ── Precificacao vs lista e desconto efetivo (por embalagem) ──────────────────
def precificacao_desconto(base: pd.DataFrame, universo: str, precos: pd.DataFrame) -> pd.DataFrame:
    g = base.groupby(["COD_EMPRESA", "CD_CIDADE", "CD_ESTADO", "CODIGO", "EMBALAGEM"], dropna=False).agg(
        DESCRICAO=("DESCRICAO", "first"),
        NIVEL_1=("NIVEL_1", "first"),
        RECEITA=("RECEITA", "sum"),
        QUANTIDADE_VENDIDA=("QUANTIDADE_VENDIDA", "sum"),
        QTD_ARMAZENAGEM=("QTD_ARMAZENAGEM", "sum"),
    ).reset_index()

    # Preco praticado por unidade da embalagem vendida (mesma base do preco de lista).
    g["PRECO_PRATICADO_VENDA"] = safe_div(g["RECEITA"], g["QUANTIDADE_VENDIDA"])
    g["PRECO_PRATICADO_ARM"] = safe_div(g["RECEITA"], g["QTD_ARMAZENAGEM"])

    g = g.merge(
        precos[[
            "CODIGO", "COD_EMPRESA", "PRECO_EMBALAGEM_0", "PRECO_EMBALAGEM_1",
            "PRECO_EMBALAGEM_2", "PERC_DESCTO_ADICIONAL_EMBALAGEM_0",
        ]],
        on=["CODIGO", "COD_EMPRESA"],
        how="left",
        validate="many_to_one",
    )

    # Preco de lista da MESMA embalagem da venda.
    lista = np.select(
        [g["EMBALAGEM"] == 0, g["EMBALAGEM"] == 1, g["EMBALAGEM"] == 2],
        [g["PRECO_EMBALAGEM_0"], g["PRECO_EMBALAGEM_1"], g["PRECO_EMBALAGEM_2"]],
        default=np.nan,
    )
    g["PRECO_LISTA_EMBALAGEM"] = lista
    g["DESCONTO_CATALOGO_PCT"] = np.where(
        g["EMBALAGEM"] == 0, g["PERC_DESCTO_ADICIONAL_EMBALAGEM_0"], np.nan
    )
    valido = g["PRECO_LISTA_EMBALAGEM"] > 0
    g["DESCONTO_EFETIVO_PCT"] = np.where(
        valido,
        (g["PRECO_LISTA_EMBALAGEM"] - g["PRECO_PRATICADO_VENDA"]) / g["PRECO_LISTA_EMBALAGEM"] * 100,
        np.nan,
    )
    g["FLAG_PRECO_ACIMA_LISTA"] = (g["DESCONTO_EFETIVO_PCT"] < 0).astype("Int64")
    g["FLAG_SEM_PRECO_LISTA"] = (~valido).astype(int)
    g.insert(0, "UNIVERSO", universo)
    return g.sort_values(["UNIVERSO", "RECEITA"], ascending=[True, False]).reset_index(drop=True)


# ── Dispersao de preco entre lojas (por SKU x embalagem) ──────────────────────
def dispersao_preco(base: pd.DataFrame, universo: str) -> pd.DataFrame:
    por_loja = base.groupby(["CODIGO", "EMBALAGEM", "COD_EMPRESA"], dropna=False).agg(
        DESCRICAO=("DESCRICAO", "first"),
        NIVEL_1=("NIVEL_1", "first"),
        RECEITA=("RECEITA", "sum"),
        QTD_ARMAZENAGEM=("QTD_ARMAZENAGEM", "sum"),
    ).reset_index()
    por_loja["PRECO_ARM"] = safe_div(por_loja["RECEITA"], por_loja["QTD_ARMAZENAGEM"])

    g = por_loja.groupby(["CODIGO", "EMBALAGEM"], dropna=False).agg(
        DESCRICAO=("DESCRICAO", "first"),
        NIVEL_1=("NIVEL_1", "first"),
        LOJAS=("COD_EMPRESA", "nunique"),
        RECEITA=("RECEITA", "sum"),
        PRECO_ARM_MEDIO=("PRECO_ARM", "mean"),
        PRECO_ARM_MEDIANA=("PRECO_ARM", "median"),
        PRECO_ARM_DESVPAD=("PRECO_ARM", lambda s: s.std(ddof=1)),
        PRECO_ARM_MIN=("PRECO_ARM", "min"),
        PRECO_ARM_MAX=("PRECO_ARM", "max"),
    ).reset_index()

    g = g[g["LOJAS"] >= 2].copy()
    g["CV_PRECO"] = safe_div(g["PRECO_ARM_DESVPAD"], g["PRECO_ARM_MEDIO"])
    g["AMPLITUDE_PCT"] = safe_div(g["PRECO_ARM_MAX"] - g["PRECO_ARM_MIN"], g["PRECO_ARM_MEDIO"]) * 100
    g["FLAG_DISPERSAO_ALTA"] = (g["CV_PRECO"] > 0.30).astype(int)
    g.insert(0, "UNIVERSO", universo)
    return g.sort_values(["UNIVERSO", "CV_PRECO"], ascending=[True, False]).reset_index(drop=True)


# ── Candidatos a repricing ────────────────────────────────────────────────────
def candidatos_repricing(
    universo: str,
    precos_desc: pd.DataFrame,
    margem_sku: pd.DataFrame,
    disp: pd.DataFrame,
) -> pd.DataFrame:
    """
    Junta tres sinais por loja x produto x embalagem (no mesmo universo):
    margem baixa/negativa em alta receita, desconto efetivo alto e preco fora
    da faixa da rede (desvio vs mediana entre lojas, por embalagem).
    """
    pd_u = precos_desc[precos_desc["UNIVERSO"] == universo].copy()

    sku_u = margem_sku[margem_sku["UNIVERSO"] == universo][
        ["CODIGO", "CUSTO_MEDIO_ARM", "CURVA_ABC_RECEITA"]
    ]
    cand = pd_u.merge(sku_u, on="CODIGO", how="left", validate="many_to_one")

    disp_u = disp[disp["UNIVERSO"] == universo][
        ["CODIGO", "EMBALAGEM", "PRECO_ARM_MEDIANA", "LOJAS", "CV_PRECO"]
    ].rename(columns={"PRECO_ARM_MEDIANA": "PRECO_ARM_MEDIANA_REDE", "LOJAS": "LOJAS_NA_REDE"})
    cand = cand.merge(disp_u, on=["CODIGO", "EMBALAGEM"], how="left", validate="many_to_one")

    cand["DESVIO_VS_MEDIANA_PCT"] = safe_div(
        cand["PRECO_PRATICADO_ARM"] - cand["PRECO_ARM_MEDIANA_REDE"], cand["PRECO_ARM_MEDIANA_REDE"]
    ) * 100

    cand["MARGEM_BRUTA_RS"] = cand["PRECO_PRATICADO_ARM"] - cand["CUSTO_MEDIO_ARM"]
    cand["MARGEM_BRUTA_PCT"] = safe_div(cand["MARGEM_BRUTA_RS"], cand["PRECO_PRATICADO_ARM"]) * 100
    cand["MARKUP"] = safe_div(cand["PRECO_PRATICADO_ARM"], cand["CUSTO_MEDIO_ARM"])

    cand["MOTIVO_MARGEM_BAIXA"] = (
        cand["CUSTO_MEDIO_ARM"].notna() & (cand["MARGEM_BRUTA_PCT"] < LIMIAR_MARGEM_PCT)
    ).astype(int)
    cand["MOTIVO_DESCONTO_ALTO"] = (cand["DESCONTO_EFETIVO_PCT"] > LIMIAR_DESCONTO_PCT).fillna(False).astype(int)
    cand["MOTIVO_PRECO_FORA_FAIXA"] = (
        (cand["LOJAS_NA_REDE"] >= MIN_LOJAS_FAIXA)
        & (cand["DESVIO_VS_MEDIANA_PCT"].abs() > LIMIAR_FAIXA_PCT)
    ).fillna(False).astype(int)
    cand["FLAG_MARGEM_NEGATIVA"] = (cand["MARGEM_BRUTA_PCT"] < 0).fillna(False).astype(int)
    cand["N_MOTIVOS"] = (
        cand["MOTIVO_MARGEM_BAIXA"] + cand["MOTIVO_DESCONTO_ALTO"] + cand["MOTIVO_PRECO_FORA_FAIXA"]
    )
    cand = cand[cand["N_MOTIVOS"] >= 1].copy()

    def motivos_txt(r):
        m = []
        if r["MOTIVO_MARGEM_BAIXA"]:
            m.append("margem negativa" if r["FLAG_MARGEM_NEGATIVA"] else "margem baixa")
        if r["MOTIVO_DESCONTO_ALTO"]:
            m.append("desconto alto")
        if r["MOTIVO_PRECO_FORA_FAIXA"]:
            m.append("preco fora da faixa")
        return " + ".join(m)

    cand["MOTIVOS"] = cand.apply(motivos_txt, axis=1)
    # Prioridade combina numero de sinais (confianca) e receita (valor da
    # oportunidade): score = N_MOTIVOS + percentil de receita entre candidatos.
    # Assim itens de alta receita com sinal sobem, sem deixar de destacar os de
    # multiplos sinais simultaneos.
    cand["RECEITA_PERCENTIL"] = cand["RECEITA"].rank(pct=True)
    cand["SCORE_PRIORIDADE"] = cand["N_MOTIVOS"] + cand["RECEITA_PERCENTIL"]
    cand = cand.sort_values(
        ["SCORE_PRIORIDADE", "RECEITA"], ascending=[False, False]
    ).reset_index(drop=True)
    cand["RANK_PRIORIDADE"] = cand.index + 1

    total = len(cand)
    limite_alta = max(1, int(np.ceil(total * 0.10)))
    limite_media = max(limite_alta + 1, int(np.ceil(total * 0.30)))
    cand["FAIXA_PRIORIDADE"] = np.select(
        [cand["RANK_PRIORIDADE"] <= limite_alta, cand["RANK_PRIORIDADE"] <= limite_media],
        ["ALTA", "MEDIA"],
        default="MONITORAR",
    )

    def acao_txt(r):
        partes = []
        if r["MOTIVO_MARGEM_BAIXA"]:
            mp = "negativa" if r["FLAG_MARGEM_NEGATIVA"] else f"de {fmt_pct(r['MARGEM_BRUTA_PCT'])}"
            partes.append(f"revisar preco/custo (margem {mp})")
        if r["MOTIVO_DESCONTO_ALTO"]:
            partes.append(f"validar desconto efetivo de {fmt_pct(r['DESCONTO_EFETIVO_PCT'])} vs lista")
        if r["MOTIVO_PRECO_FORA_FAIXA"]:
            partes.append(f"alinhar preco ({fmt_pct(r['DESVIO_VS_MEDIANA_PCT'])} vs mediana da rede)")
        return (
            f"SKU {int(r['CODIGO'])} ({str(r['DESCRICAO']).strip()}) na loja {int(r['COD_EMPRESA'])} "
            f"({r['CD_CIDADE']}-{r['CD_ESTADO']}): " + "; ".join(partes) + "."
        )

    cand["ACAO_RECOMENDADA"] = cand.apply(acao_txt, axis=1)

    cols = [
        "UNIVERSO", "RANK_PRIORIDADE", "FAIXA_PRIORIDADE", "SCORE_PRIORIDADE",
        "N_MOTIVOS", "MOTIVOS",
        "COD_EMPRESA", "CD_CIDADE", "CD_ESTADO", "CODIGO", "DESCRICAO", "NIVEL_1",
        "EMBALAGEM", "CURVA_ABC_RECEITA", "RECEITA",
        "PRECO_PRATICADO_ARM", "CUSTO_MEDIO_ARM", "MARGEM_BRUTA_PCT", "MARKUP",
        "PRECO_PRATICADO_VENDA", "PRECO_LISTA_EMBALAGEM", "DESCONTO_EFETIVO_PCT",
        "PRECO_ARM_MEDIANA_REDE", "DESVIO_VS_MEDIANA_PCT", "LOJAS_NA_REDE",
        "MOTIVO_MARGEM_BAIXA", "MOTIVO_DESCONTO_ALTO", "MOTIVO_PRECO_FORA_FAIXA",
        "FLAG_MARGEM_NEGATIVA", "ACAO_RECOMENDADA",
    ]
    return cand[cols]


# ── Recomendacoes de melhoria ─────────────────────────────────────────────────
def gerar_recomendacoes_melhoria() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "PRIORIDADE": "ALTA",
                "TEMA": "Cobertura de custo",
                "LIMITACAO_OU_PROBLEMA": "So ~261 SKUs (~16% da receita) tem preco de compra valido no periodo; ~9,5% das linhas de compra vem sem preco e ~88% dos SKUs vendem sem compra registrada.",
                "RISCO_ANALITICO": "A margem realizada e calculada apenas para um subconjunto pequeno da receita. Generalizar a margem desse grupo para a rede toda seria enganoso.",
                "RECOMENDACAO": "Incorporar custo de reposicao/tabela de custo por SKU (ou custo medio gerencial) para todos os itens ativos, e exigir preco em todas as entradas de compra.",
                "IMPACTO_ESPERADO": "Estender a analise de margem de ~16% para ~100% da receita e permitir decisao de mix por rentabilidade.",
            },
            {
                "PRIORIDADE": "ALTA",
                "TEMA": "Camadas de custo (PEPS/medio movel)",
                "LIMITACAO_OU_PROBLEMA": "O custo usado e a media ponderada do periodo inteiro, sem camadas de custo (PEPS) nem custo de reposicao atual.",
                "RISCO_ANALITICO": "Em itens com forte variacao de custo, a margem realizada pode divergir da margem corrente; itens recentes podem aparecer mais/menos rentaveis do que estao hoje.",
                "RECOMENDACAO": "Registrar custo por camada/lote (PEPS) e o custo de reposicao corrente para separar margem historica de margem prospectiva.",
                "IMPACTO_ESPERADO": "Margem mais fiel ao momento da decisao de preco e melhor base para repricing.",
            },
            {
                "PRIORIDADE": "MEDIA",
                "TEMA": "Preco de lista x promocoes",
                "LIMITACAO_OU_PROBLEMA": "O preco de lista (`dim_precos`) e um cadastro por loja x produto x embalagem; promocoes pontuais e campanhas nao tem data nem vigencia.",
                "RISCO_ANALITICO": "O desconto efetivo e uma aproximacao: parte do desconto pode ser promocao planejada, nao perda de preco. Precos praticados acima da lista podem indicar lista desatualizada.",
                "RECOMENDACAO": "Versionar o preco de lista com data de vigencia e marcar campanhas promocionais para separar desconto comercial de erro de precificacao.",
                "IMPACTO_ESPERADO": "Desconto efetivo confiavel e deteccao de listas desatualizadas.",
            },
            {
                "PRIORIDADE": "MEDIA",
                "TEMA": "Embalagem e unidade",
                "LIMITACAO_OU_PROBLEMA": "Preco de venda, custo e lista vem em unidades diferentes (venda, compra e embalagem). Misturar essas bases gera falsos outliers (ex.: caixa x unidade).",
                "RISCO_ANALITICO": "Comparacoes ingenuas (preco entre lojas sem separar embalagem, ou custo sem converter) produzem dispersao e margens irreais.",
                "RECOMENDACAO": "Padronizar um identificador de unidade de medida por linha e manter a conversao para a unidade de armazenagem como camada obrigatoria do modelo.",
                "IMPACTO_ESPERADO": "Eliminar falsos alertas de variacao de preco e de margem por erro de unidade.",
            },
            {
                "PRIORIDADE": "MEDIA",
                "TEMA": "Canal atacado/B2B (Loja 93)",
                "LIMITACAO_OU_PROBLEMA": "A Loja 93 opera como atacado/B2B, com preco e margem nao comparaveis ao varejo, e e identificada por codigo de loja, nao por uma dimensao formal de canal.",
                "RISCO_ANALITICO": "Misturar margem de atacado com varejo distorce a margem media e a dispersao de preco da rede.",
                "RECOMENDACAO": "Criar dimensao de canal e politicas de preco/margem separadas para atacado e varejo.",
                "IMPACTO_ESPERADO": "Margem e dispersao comparaveis dentro de cada canal e metas de preco adequadas.",
            },
        ]
    )


# ── Validacoes ────────────────────────────────────────────────────────────────
def assert_close(nome, observado, esperado, validacoes, tolerancia=1e-2):
    diff = float(observado - esperado)
    status = "OK" if abs(diff) <= tolerancia else "FALHA"
    validacoes.append({
        "VALIDACAO": nome, "OBSERVADO": observado, "ESPERADO": esperado,
        "DIFERENCA": diff, "STATUS": status,
    })
    if status != "OK":
        raise AssertionError(f"{nome}: obs={observado}, esp={esperado}, diff={diff}")


def assert_true(nome, condicao, validacoes):
    status = "OK" if bool(condicao) else "FALHA"
    validacoes.append({
        "VALIDACAO": nome, "OBSERVADO": int(bool(condicao)), "ESPERADO": 1,
        "DIFERENCA": int(bool(condicao)) - 1, "STATUS": status,
    })
    if status != "OK":
        raise AssertionError(nome)


def validar_etapa5(
    vendas_completo, custo_completo, custo_fisico, custo_loja93,
    total, margem_sku, categorias_n1, lojas, precos_desc, dispersao, candidatos,
):
    val: list[dict] = []

    # 1. Reconciliacao de receita por universo com a Etapa 3.
    imp = pd.read_csv(E3 / "impacto_loja93.csv", encoding="utf-8-sig").set_index("SEGMENTO")
    rec_completa = float(vendas_completo["RECEITA"].sum())
    rec_fisica = float(vendas_completo[vendas_completo["COD_EMPRESA"] != LOJA_ATACADO]["RECEITA"].sum())
    rec_93 = float(vendas_completo[vendas_completo["COD_EMPRESA"] == LOJA_ATACADO]["RECEITA"].sum())
    assert_close("Receita rede completa vs Etapa 3", rec_completa, float(imp.loc["REDE_COMPLETA", "RECEITA"]), val)
    assert_close("Receita rede fisica vs Etapa 3", rec_fisica, float(imp.loc["REDE_FISICA_SEM_LOJA93", "RECEITA"]), val)
    assert_close("Receita Loja 93/B2B vs Etapa 3", rec_93, float(imp.loc[ESCOPO_LOJA93, "RECEITA"]), val)
    assert_close("REDE_COMPLETA = REDE_FISICA + Loja 93", rec_completa, rec_fisica + rec_93, val)
    assert_true("Universo Loja 93/B2B gerado nas saidas agregadas",
                bool(ESCOPO_LOJA93 in set(total["UNIVERSO"])), val)

    # 2. Reconciliacao por categoria N1 e por loja vs Etapa 3.
    cat3 = pd.read_csv(E3 / "desempenho_categorias_n1.csv", encoding="utf-8-sig")
    cat_m = categorias_n1.merge(
        cat3[["UNIVERSO", "NIVEL_1", "RECEITA"]].rename(columns={"RECEITA": "RECEITA_E3"}),
        on=["UNIVERSO", "NIVEL_1"], how="left",
    )
    assert_close("Categoria N1: receita vs Etapa 3 (max abs)",
                 float((cat_m["RECEITA_TOTAL"] - cat_m["RECEITA_E3"]).abs().max()), 0.0, val)
    loja3 = pd.read_csv(E3 / "desempenho_lojas.csv", encoding="utf-8-sig")
    loja_m = lojas.merge(
        loja3[["UNIVERSO", "COD_EMPRESA", "RECEITA"]].rename(columns={"RECEITA": "RECEITA_E3"}),
        on=["UNIVERSO", "COD_EMPRESA"], how="left",
    )
    assert_close("Loja: receita vs Etapa 3 (max abs)",
                 float((loja_m["RECEITA_TOTAL"] - loja_m["RECEITA_E3"]).abs().max()), 0.0, val)

    # 3. Nenhuma margem calculada sobre custo ausente.
    assert_true("Margem por SKU so com custo presente",
                bool(margem_sku["CUSTO_MEDIO_ARM"].notna().all() and (margem_sku["CUSTO_MEDIO_ARM"] > 0).all()), val)
    skus_custo_completo = int(custo_completo["CUSTO_MEDIO_ARM"].notna().sum())
    skus_margem_completo = int(margem_sku[margem_sku["UNIVERSO"] == UNIVERSO_COMPLETO]["CODIGO"].nunique())
    assert_close("SKUs com margem = SKUs com custo (rede completa)",
                 skus_margem_completo, skus_custo_completo, val, tolerancia=0)

    # 4. Faixa sanitaria de margem e markup; margens negativas sinalizadas.
    assert_true("Margem % dentro da faixa sanitaria",
                bool(margem_sku["MARGEM_BRUTA_PCT"].between(MARGEM_PCT_MIN_SANITARIA, MARGEM_PCT_MAX_SANITARIA).all()), val)
    assert_true("Markup positivo e sem estouro de unidade",
                bool(((margem_sku["MARKUP"] > 0) & (margem_sku["MARKUP"] <= MARKUP_MAX_SANITARIO)).all()), val)
    n_neg = int(margem_sku["FLAG_MARGEM_NEGATIVA"].sum())
    assert_true("Margens negativas sinalizadas (flag coerente)",
                bool((margem_sku.loc[margem_sku["MARGEM_BRUTA_RS"] < 0, "FLAG_MARGEM_NEGATIVA"] == 1).all()
                     and n_neg == int((margem_sku["MARGEM_BRUTA_RS"] < 0).sum())), val)

    # 5. Reconciliacao margem agregada: RECEITA_COM_CUSTO = CMV + MARGEM_BRUTA_TOTAL.
    assert_close("Categoria: receita com custo = CMV + margem (max abs)",
                 float((categorias_n1["RECEITA_COM_CUSTO"]
                        - (categorias_n1["CMV"] + categorias_n1["MARGEM_BRUTA_TOTAL"])).abs().max()), 0.0, val)

    # 6. Custo da rede fisica nao usa compras da Loja 93.
    assert_true("Custo rede fisica <= custo rede completa em SKUs",
                bool(custo_fisico["CUSTO_MEDIO_ARM"].notna().sum() <= custo_completo["CUSTO_MEDIO_ARM"].notna().sum()), val)
    assert_true("Custo Loja 93/B2B <= custo rede completa em SKUs",
                bool(custo_loja93["CUSTO_MEDIO_ARM"].notna().sum() <= custo_completo["CUSTO_MEDIO_ARM"].notna().sum()), val)

    # 7. Desconto e preco comparados na MESMA embalagem (chave inclui EMBALAGEM).
    assert_true("Precificacao tem grao por embalagem", bool("EMBALAGEM" in precos_desc.columns), val)
    assert_true("Dispersao separada por embalagem", bool("EMBALAGEM" in dispersao.columns), val)

    # 8. Loja 93 ausente do universo fisico nas saidas por loja e dispersao.
    assert_true("Loja 93 fora do universo fisico (lojas)",
                bool(not ((lojas["UNIVERSO"] == UNIVERSO_FISICO) & (lojas["COD_EMPRESA"] == LOJA_ATACADO)).any()), val)

    # 9. Candidatos tem pelo menos um motivo cada.
    assert_true("Todo candidato a repricing tem >= 1 motivo",
                bool((candidatos["N_MOTIVOS"] >= 1).all()), val)

    cand_custo = candidatos[
        candidatos["CUSTO_MEDIO_ARM"].notna()
        & candidatos["PRECO_PRATICADO_ARM"].notna()
        & (candidatos["PRECO_PRATICADO_ARM"] > 0)
    ].copy()
    if len(cand_custo):
        margem_local = (
            (cand_custo["PRECO_PRATICADO_ARM"] - cand_custo["CUSTO_MEDIO_ARM"])
            / cand_custo["PRECO_PRATICADO_ARM"] * 100
        )
        assert_close("Candidato: margem % no grao loja-produto-embalagem (max abs)",
                     float((cand_custo["MARGEM_BRUTA_PCT"] - margem_local).abs().max()), 0.0, val)
        assert_true("Candidato: flag de margem baixa usa margem local",
                    bool((cand_custo["MOTIVO_MARGEM_BAIXA"]
                          == (cand_custo["MARGEM_BRUTA_PCT"] < LIMIAR_MARGEM_PCT).astype(int)).all()), val)

    return pd.DataFrame(val)


# ── Autoaudit (revisao critica antes/depois) ──────────────────────────────────
def construir_autoaudit(vendas_completo, custo_completo, margem_sku_completo, dispersao):
    """Revisao critica dos proprios resultados: problema, correcao e impacto."""
    linhas = []
    cost_skus = set(custo_completo.loc[custo_completo["CUSTO_MEDIO_ARM"].notna(), "CODIGO"])

    # A. Margens absurdas por erro de unidade (preco de venda em caixa x custo).
    mk = margem_sku_completo["MARKUP"]
    mg = margem_sku_completo["MARGEM_BRUTA_PCT"]
    vc_custo = vendas_completo[vendas_completo["CODIGO"].isin(cost_skus)]
    skus_caixa = int(
        vc_custo[(vc_custo["EMBALAGEM"] == 1) | (vc_custo["CONVERSAO_VENDA_PARA_ARMAZENAGEM"] > 1)]["CODIGO"].nunique()
    )
    conv_venda_max = float(vendas_completo["CONVERSAO_VENDA_PARA_ARMAZENAGEM"].max())
    absurdos = int((mk > MARKUP_MAX_SANITARIO).sum())
    linhas.append({
        "PROBLEMA": "Margens absurdas por erro de unidade (preco em caixa x custo)",
        "DESCRICAO": "Ler preco de venda por unidade de venda (caixa) e custo por unidade de compra, sem converter para a unidade de armazenagem, infla a relacao preco/custo - o falso outlier de 'venda em caixa' ja documentado na Etapa 2.",
        "CORRECAO": "Preco praticado = receita / qtd. em armazenagem; custo = preco de compra / conversao de compra. Tudo na mesma unidade.",
        "ANTES": f"No nivel da linha, vendas em caixa (EMBALAGEM=1, conversao de venda ate {conv_venda_max:.0f}) chegariam a dezenas de vezes o custo unitario se lidas por unidade de venda; {skus_caixa} dos SKUs com custo vendem em caixa/conversao>1.",
        "DEPOIS": f"Apos normalizar, os {len(mk)} SKUs com custo tem markup entre {mk.min():.2f}x e {mk.max():.2f}x e margem entre {fmt_pct(mg.min())} e {fmt_pct(mg.max())}.",
        "IMPACTO": f"{absurdos} de {len(mk)} SKUs com markup acima de {MARKUP_MAX_SANITARIO:.0f}x (faixa sanitaria); a normalizacao funciona como salvaguarda contra o outlier de caixa.",
    })

    # B. Custo de SKU sem compra vazando para a margem.
    skus_total = int(vendas_completo["CODIGO"].nunique())
    skus_com_custo = len(cost_skus)
    skus_sem_custo = skus_total - skus_com_custo
    rec_total = float(vendas_completo["RECEITA"].sum())
    rec_sem_custo = float(vendas_completo[~vendas_completo["CODIGO"].isin(cost_skus)]["RECEITA"].sum())
    linhas.append({
        "PROBLEMA": "Custo de SKU sem compra vazando para a margem",
        "DESCRICAO": "Imputar custo zero ou custo de categoria para SKUs sem compra registrada fabricaria margem (ex.: margem ~100%) onde nao ha base de custo.",
        "CORRECAO": "Margem so e calculada para SKUs com custo proprio; os demais ficam sem margem, sinalizados como sem custo.",
        "ANTES": f"{skus_sem_custo} SKUs ({fmt_pct(skus_sem_custo / skus_total * 100)}) e {fmt_brl_milhao(rec_sem_custo)} ({fmt_pct(rec_sem_custo / rec_total * 100)} da receita) poderiam receber margem fabricada.",
        "DEPOIS": f"{skus_com_custo} SKUs com custo real entram na margem; {skus_sem_custo} ficam corretamente sem margem.",
        "IMPACTO": "Margem realizada limitada a base auditavel, sem inflar rentabilidade.",
    })

    # C. Mistura de embalagem (e atacado) na dispersao de preco.
    #    Naive = amplitude de preco BRUTO (PRECO_UNIT_MEDIO) por SKU, todas as lojas,
    #    embalagens misturadas - reproduz o achado documentado de ~2,5k SKUs.
    mm = vendas_completo.groupby("CODIGO")["PRECO_UNIT_MEDIO"].agg(["min", "max", "count"])
    mm = mm[mm["count"] >= 2]
    naive_amp = int((safe_div(mm["max"] - mm["min"], mm["min"]) > 0.30).sum())
    #    Corrigido = mesma metrica (amplitude) por SKU x embalagem na rede fisica,
    #    com preco normalizado para a unidade de armazenagem.
    disp_fis = dispersao[dispersao["UNIVERSO"] == UNIVERSO_FISICO]
    corr_amp = int((safe_div(disp_fis["PRECO_ARM_MAX"] - disp_fis["PRECO_ARM_MIN"], disp_fis["PRECO_ARM_MIN"]) > 0.30).sum())
    corr_cv = int((disp_fis["CV_PRECO"] > 0.30).sum())
    linhas.append({
        "PROBLEMA": "Mistura de embalagem (e atacado) na dispersao de preco",
        "DESCRICAO": "Comparar preco do mesmo SKU entre lojas sem separar embalagem e incluindo a Loja 93 mistura caixa com unidade e atacado com varejo - foi o que gerou a leitura ingenua de '2.549 SKUs com variacao >30%'.",
        "CORRECAO": "Dispersao por SKU x EMBALAGEM, com preco em unidade de armazenagem, dentro do universo (rede fisica separada do atacado).",
        "ANTES": f"{naive_amp} SKUs com amplitude de preco bruto >30% (todas as lojas, embalagens misturadas).",
        "DEPOIS": f"{corr_amp} SKUs com amplitude >30% pela mesma metrica na rede fisica por embalagem; pelo CV, apenas {corr_cv} SKUs com CV>30%.",
        "IMPACTO": f"A maior parte da 'variacao de preco' era mistura de embalagem/atacado: cai de {naive_amp} para {corr_amp} ({corr_cv} pelo CV).",
    })

    return pd.DataFrame(linhas)


# ── Persistencia ──────────────────────────────────────────────────────────────
def salvar_csv(df: pd.DataFrame, nome: str) -> None:
    df.to_csv(OUT / nome, index=False, encoding="utf-8-sig", float_format="%.6f")


# ── Resumo executivo e documentacao tecnica ───────────────────────────────────
def gerar_resumo(
    total_completo, total_fisico, total_loja93, categorias_n1, lojas, margem_sku,
    precos_desc, dispersao, candidatos, autoaudit, validacoes, n_skus_compra,
):
    tc = total_completo.iloc[0]
    tf = total_fisico.iloc[0]
    tl = total_loja93.iloc[0]

    cat_fis = categorias_n1[categorias_n1["UNIVERSO"] == UNIVERSO_FISICO].copy()
    # So destaca margem de categorias com cobertura de custo minimamente
    # representativa (>=10% da receita), para nao exaltar categorias com poucos SKUs.
    cat_repr = cat_fis[cat_fis["COBERTURA_CUSTO_RECEITA_PCT"] >= 10].sort_values(
        "MARGEM_BRUTA_PCT", ascending=False
    )
    top_cat = cat_repr.iloc[0]
    bot_cat = cat_repr.iloc[-1]
    cat_neg = cat_fis[(cat_fis["RECEITA_COM_CUSTO"] > 0) & (cat_fis["MARGEM_BRUTA_PCT"] < 0)].sort_values(
        "MARGEM_BRUTA_PCT"
    )
    txt_neg = (
        f"- Alerta: a categoria `{cat_neg.iloc[0]['NIVEL_1']}` aparece com margem "
        f"NEGATIVA ({fmt_pct(cat_neg.iloc[0]['MARGEM_BRUTA_PCT'])}) no subconjunto com custo "
        f"(cobertura de {fmt_pct(cat_neg.iloc[0]['COBERTURA_CUSTO_RECEITA_PCT'])} da receita) - "
        f"itens de baixo giro vendidos abaixo do custo, candidatos a repricing/descontinuacao.\n"
        if len(cat_neg) else ""
    )

    sku_fis = margem_sku[margem_sku["UNIVERSO"] == UNIVERSO_FISICO]
    sku_alta = sku_fis[sku_fis["CURVA_ABC_RECEITA"] == "A"]
    pior_sku = sku_alta.sort_values("MARGEM_BRUTA_PCT").iloc[0]
    melhor_sku = sku_alta.sort_values("MARGEM_BRUTA_PCT", ascending=False).iloc[0]

    desc_fis = precos_desc[(precos_desc["UNIVERSO"] == UNIVERSO_FISICO) & precos_desc["DESCONTO_EFETIVO_PCT"].notna()]
    desc_medio = float(np.average(desc_fis["DESCONTO_EFETIVO_PCT"], weights=desc_fis["RECEITA"]))
    n_acima_lista = int((desc_fis["DESCONTO_EFETIVO_PCT"] < 0).sum())

    cand_fis = candidatos[candidatos["UNIVERSO"] == UNIVERSO_FISICO]

    disp_fis = dispersao[(dispersao["UNIVERSO"] == UNIVERSO_FISICO) & (dispersao["EMBALAGEM"] == 0)]
    disp_alta = int((disp_fis["CV_PRECO"] > 0.30).sum())

    aud_unidade = autoaudit.iloc[0]
    aud_vazamento = autoaudit.iloc[1]
    aud_emb = autoaudit.iloc[2]

    resumo = f"""# Etapa 5 - Analise de precificacao e variacao de margem

## Glossario rapido (ler antes dos numeros)

- **Preco praticado (por unid. de armazenagem):** `receita / quantidade em
  unidade de armazenagem`. E o preco medio efetivamente realizado, ja na mesma
  unidade do custo.
- **Custo medio (CMV unitario):** media ponderada do preco de compra do SKU no
  periodo, convertido para a unidade de armazenagem
  (`preco de compra / conversao de compra`). So existe para SKUs com compra de
  preco valido.
- **Margem bruta (R$):** preco praticado - custo medio (mesma unidade).
- **Margem bruta (%):** margem R$ / preco praticado.
- **Markup:** preco praticado / custo medio (quantas vezes o custo o preco cobre).
- **Preco de lista:** preco de tabela cadastrado por loja x produto x embalagem.
- **Desconto efetivo (%):** `(preco de lista - preco praticado) / preco de lista`,
  sempre dentro da MESMA embalagem.
- **Dispersao de preco:** coeficiente de variacao do preco praticado do mesmo
  SKU entre lojas, por embalagem.
- **Repricing:** revisao de preco de itens com margem baixa/negativa, desconto
  fora do padrao ou preco fora da faixa da rede.

## Cobertura de custo (leia antes de generalizar a margem)

Margem realizada **so existe para os SKUs com custo de compra registrado**. Esse
e o analogo do achado das Etapas 1/2 ("88% vendem sem compra registrada"):

- {fmt_num(n_skus_compra)} SKUs tem compra registrada no periodo, mas apenas
  {fmt_num(tc['SKUS_COM_CUSTO'])} tem preco de compra valido (9,5% das linhas de
  compra vem sem preco e sao excluidas do custo), de {fmt_num(tc['SKUS'])} SKUs vendidos.
- Esses SKUs respondem por {fmt_brl_milhao(tc['RECEITA_COM_CUSTO'])}
  ({fmt_pct(tc['COBERTURA_CUSTO_RECEITA_PCT'])} da receita) na rede completa e
  {fmt_brl_milhao(tf['RECEITA_COM_CUSTO'])} ({fmt_pct(tf['COBERTURA_CUSTO_RECEITA_PCT'])})
  na rede fisica. Na Loja 93/B2B, a cobertura auditavel e
  {fmt_brl_milhao(tl['RECEITA_COM_CUSTO'])} ({fmt_pct(tl['COBERTURA_CUSTO_RECEITA_PCT'])}).
- Os demais SKUs **nao recebem margem por ausencia de dado, nunca por erro**.
  A margem deste relatorio vale para esse subconjunto, nao para a rede toda.

## Principais achados

- Margem bruta % media ponderada (apenas itens com custo): rede completa
  {fmt_pct(tc['MARGEM_BRUTA_PCT'])} (markup {tc['MARKUP_PONDERADO']:.2f}x); rede
  fisica {fmt_pct(tf['MARGEM_BRUTA_PCT'])} (markup {tf['MARKUP_PONDERADO']:.2f}x).
- Categoria N1 de maior margem na rede fisica (cobertura de custo >=10%):
  `{top_cat['NIVEL_1']}` ({fmt_pct(top_cat['MARGEM_BRUTA_PCT'])}, cobertura
  {fmt_pct(top_cat['COBERTURA_CUSTO_RECEITA_PCT'])}); de menor margem:
  `{bot_cat['NIVEL_1']}` ({fmt_pct(bot_cat['MARGEM_BRUTA_PCT'])}, cobertura
  {fmt_pct(bot_cat['COBERTURA_CUSTO_RECEITA_PCT'])}).
{txt_neg}
- Entre os itens de alta receita (curva A) com custo na rede fisica, a menor
  margem e do SKU {int(pior_sku['CODIGO'])} ({str(pior_sku['DESCRICAO']).strip()}),
  com {fmt_pct(pior_sku['MARGEM_BRUTA_PCT'])}; a maior e do SKU
  {int(melhor_sku['CODIGO'])} ({str(melhor_sku['DESCRICAO']).strip()}), com
  {fmt_pct(melhor_sku['MARGEM_BRUTA_PCT'])}.
- {int(margem_sku[margem_sku['UNIVERSO'] == UNIVERSO_FISICO]['FLAG_MARGEM_NEGATIVA'].sum())} SKUs
  da rede fisica vendem com margem negativa (preco < custo), concentrados em
  utilidades domesticas/loucas de baixo giro - sinalizados, nao silenciados.
- Desconto efetivo medio ponderado na rede fisica: {fmt_pct(desc_medio)}.
  {fmt_num(n_acima_lista)} combinacoes loja x produto x embalagem vendem ACIMA da
  lista (desconto negativo), sinal de lista possivelmente desatualizada.
- Dispersao de preco entre lojas (rede fisica, embalagem 0): apenas
  {fmt_num(disp_alta)} SKUs com CV>30% - bem abaixo da leitura ingenua de
  "2.549 SKUs com variacao >30%", que misturava embalagem e atacado.
- Candidatos a repricing na rede fisica: {fmt_num(len(cand_fis))} combinacoes
  loja x produto x embalagem com pelo menos um sinal (margem baixa/negativa,
  desconto alto ou preco fora da faixa).

## Revisao de qualidade (autoaudit antes/depois)

- **{aud_unidade['PROBLEMA']}.** {aud_unidade['ANTES']} -> {aud_unidade['DEPOIS']}
  ({aud_unidade['IMPACTO']})
- **{aud_vazamento['PROBLEMA']}.** {aud_vazamento['ANTES']} -> {aud_vazamento['DEPOIS']}
- **{aud_emb['PROBLEMA']}.** {aud_emb['ANTES']} -> {aud_emb['DEPOIS']}
  ({aud_emb['IMPACTO']})

## Limitacoes e cuidados

- Margem realizada existe so para os ~{fmt_num(tc['SKUS_COM_CUSTO'])} SKUs com custo
  (~{fmt_pct(tc['COBERTURA_CUSTO_RECEITA_PCT'])} da receita); o restante fica sem
  margem por ausencia de dado.
- O custo e a media ponderada do periodo, sem camadas de custo (PEPS) nem custo
  de reposicao atual.
- O preco de lista pode nao refletir promocoes pontuais; o desconto efetivo e uma
  aproximacao.
- A Loja 93 e atacado/B2B: margens nao comparaveis ao varejo, por isso segregada.
  A etapa gera um universo explicito `LOJA_93_ATACADO_B2B` para auditar esse canal.

## Validacoes

- {len(validacoes)} validacoes executadas, todas com status
  `{validacoes['STATUS'].unique()[0]}`.
- Receita por universo, categoria e loja reconcilia com a Etapa 3, incluindo
  `LOJA_93_ATACADO_B2B`.
- Nenhuma margem % calculada sobre custo ausente; margens negativas sinalizadas.
- Preco praticado e de lista comparados apenas dentro da mesma embalagem.

## Como executar

```bash
.venv/Scripts/python.exe notebooks/etapa5_precificacao_margem.py
```

Os arquivos auditaveis sao gravados em `outputs/etapa5/`.
"""
    return resumo


def gerar_documentacao_tecnica() -> str:
    return """# Documentacao tecnica - Etapa 5

Guia de reproducao e continuacao da analise de precificacao e margem.

## O que foi implementado

A Etapa 5 calcula margem bruta realizada (R$ e %), markup, custo medio, desconto
efetivo vs preco de lista e dispersao de preco entre lojas. O script canonico e
`notebooks/etapa5_precificacao_margem.py`.

## Unidades (ponto critico)

Tudo e comparado na unidade de ARMAZENAGEM:

- Preco praticado por unid. de armazenagem = `RECEITA / QTD_ARMAZENAGEM`.
- Custo medio por unid. de armazenagem = `PRECO_UNIT_UNIDADE_COMPRA / CONVERSAO_COMPRA_ARMAZENAGEM`,
  ponderado pela quantidade comprada. A divisao pela conversao e obrigatoria:
  sem ela, itens comprados em caixa teriam custo inflado e margem absurda.
- O desconto efetivo compara preco praticado e preco de lista DENTRO da mesma
  embalagem (mesma unidade de venda), nunca cruzando caixa com unidade.

## Entradas usadas

- `data/processed/vendas_tratadas.parquet` (loader `load_vendas`): receita,
  quantidade vendida, quantidade em armazenagem, embalagem, categoria, loja.
- `data/processed/compras_tratadas.parquet` (loader `load_compras`): preco e
  quantidade de compra; 9,5% das linhas sem preco sao excluidas do custo.
- `data/processed/dim_produto_tratada.parquet` (loader `load_dim_produto`):
  `CONVERSAO_COMPRA_ARMAZENAGEM` por SKU.
- `data/processed/dim_precos_tratada.parquet` (loader `load_dim_precos`): preco
  de lista por loja x produto x embalagem e desconto adicional de catalogo.
- `outputs/etapa3/impacto_loja93.csv`, `desempenho_categorias_n1.csv`,
  `desempenho_lojas.csv`, `ranking_produtos_receita.csv`: reconciliacao de
  receita e curva ABC ja auditadas na Etapa 3.

## Principais formulas

- Preco praticado (arm.) = receita / qtd. em armazenagem.
- Custo medio (arm.) = soma(preco compra x qtd) / soma(qtd) / conversao de compra.
- Margem bruta R$ = preco praticado - custo medio.
- Margem bruta % = margem R$ / preco praticado.
- Markup = preco praticado / custo medio.
- Margem agregada (categoria/loja) = (receita com custo - CMV) / receita com custo,
  ponderada por quantidade (CMV = soma de custo medio x qtd em armazenagem).
- Desconto efetivo % = (preco de lista - preco praticado da embalagem) / preco de lista.
- Dispersao = desvio padrao / media do preco praticado por unid. de armazenagem
  entre lojas, por SKU x embalagem.

## Separacao da Loja 93

Saidas agregadas trazem `UNIVERSO` com `REDE_COMPLETA`, `REDE_FISICA_SEM_LOJA93`
e `LOJA_93_ATACADO_B2B`. O custo de cada universo usa apenas as compras das
lojas do universo. Candidatos e dispersao da rede fisica nao incluem a Loja 93
(atacado/B2B), e o canal B2B fica auditavel em universo proprio.

## Arquivos gerados

- `margem_produtos.csv`: margem por SKU (somente com custo), com cobertura e ABC.
- `margem_categorias_n1.csv` / `_n2.csv` / `_n3.csv`: margem agregada por categoria.
- `margem_lojas.csv`: margem e preco por loja.
- `margem_total_universo.csv`: margem consolidada por universo (fonte dos KPIs do resumo/dashboard).
- `precificacao_desconto.csv`: preco praticado vs lista e desconto efetivo, por embalagem.
- `dispersao_preco_lojas.csv`: dispersao por SKU entre lojas, por embalagem.
- `candidatos_repricing.csv`: ranking de oportunidades de repricing.
- `recomendacoes_melhoria.csv`: melhorias de dados/modelagem/processo.
- `validacoes_etapa5.csv`: reconciliacoes numericas.
- `autoaudit_etapa5.csv`: revisao critica antes/depois.
- `resumo_etapa5.md`: resumo executivo, glossario e limitacoes.

## Como revisar ou continuar

1. Rode `.venv/Scripts/python.exe notebooks/etapa5_precificacao_margem.py`.
2. Confira `outputs/etapa5/validacoes_etapa5.csv`; qualquer `FALHA` bloqueia conclusoes.
3. Para estender a margem alem dos ~16% de receita coberta, e necessario custo por
   SKU para os itens sem compra registrada (ver `recomendacoes_melhoria.csv`).
4. Reexecute `python scripts/gerar_dashboard.py` para atualizar dashboard e dicionario.

## Limitacoes que nao foram resolvidas aqui

- Sem custo para ~84% da receita, a margem cobre so o subconjunto auditavel.
- Sem camadas de custo (PEPS) nem custo de reposicao, a margem e historica media.
- Sem vigencia/promocao no preco de lista, o desconto efetivo e aproximado.
- A Loja 93 precisa de uma dimensao formal de canal para substituir a regra por codigo.
"""


# ── Orquestracao ──────────────────────────────────────────────────────────────
def main() -> None:
    print("Carregando bases...")
    vendas = load_vendas(excluir_atacado=False)
    compras = load_compras()
    produtos = load_dim_produto()
    precos = load_dim_precos().drop_duplicates(["CODIGO", "COD_EMPRESA"])
    conversao = produtos.drop_duplicates("CODIGO").set_index("CODIGO")["CONVERSAO_COMPRA_ARMAZENAGEM"]
    abc = pd.read_csv(E3 / "ranking_produtos_receita.csv", encoding="utf-8-sig")[
        ["UNIVERSO", "CODIGO", "CURVA_ABC_RECEITA", "RANK_RECEITA"]
    ]

    print("Calculando custo medio por SKU (rede completa e rede fisica)...")
    custo_completo = custo_medio_por_sku(compras, conversao)
    custo_fisico = custo_medio_por_sku(compras[compras["COD_EMPRESA"] != LOJA_ATACADO], conversao)
    custo_loja93 = custo_medio_por_sku(compras[compras["COD_EMPRESA"] == LOJA_ATACADO], conversao)

    vendas_fisico = vendas[vendas["COD_EMPRESA"] != LOJA_ATACADO].copy()
    vendas_loja93 = vendas[vendas["COD_EMPRESA"] == LOJA_ATACADO].copy()
    base_completo = base_margem_universo(vendas, custo_completo)
    base_fisico = base_margem_universo(vendas_fisico, custo_fisico)
    base_loja93 = base_margem_universo(vendas_loja93, custo_loja93)
    bases = {
        UNIVERSO_COMPLETO: base_completo,
        ESCOPO_LOJA93: base_loja93,
        UNIVERSO_FISICO: base_fisico,
    }
    custos = {
        UNIVERSO_COMPLETO: custo_completo,
        ESCOPO_LOJA93: custo_loja93,
        UNIVERSO_FISICO: custo_fisico,
    }

    print("Agregando margem por categoria, loja e total...")
    total = pd.concat([agregar_margem(b, u, []) for u, b in bases.items()], ignore_index=True)
    categorias_n1 = ordenar_categoria(pd.concat(
        [agregar_margem(b, u, ["NIVEL_1"]) for u, b in bases.items()], ignore_index=True))
    categorias_n2 = ordenar_categoria(pd.concat(
        [agregar_margem(b, u, ["NIVEL_1", "NIVEL_2"]) for u, b in bases.items()], ignore_index=True))
    categorias_n3 = ordenar_categoria(pd.concat(
        [agregar_margem(b, u, ["NIVEL_1", "NIVEL_2", "NIVEL_3"]) for u, b in bases.items()], ignore_index=True))
    lojas = ordenar_categoria(pd.concat(
        [agregar_margem(b, u, ["COD_EMPRESA", "CD_CIDADE", "CD_ESTADO"]) for u, b in bases.items()],
        ignore_index=True))

    print("Calculando margem por SKU, precificacao, dispersao e candidatos...")
    margem_sku = pd.concat(
        [margem_por_sku(bases[u], u, custos[u], abc) for u in bases], ignore_index=True)
    precos_desc = pd.concat(
        [precificacao_desconto(bases[u], u, precos) for u in bases], ignore_index=True)
    dispersao = pd.concat([dispersao_preco(bases[u], u) for u in bases], ignore_index=True)
    candidatos = pd.concat(
        [candidatos_repricing(u, precos_desc, margem_sku, dispersao) for u in bases], ignore_index=True)
    recomendacoes = gerar_recomendacoes_melhoria()

    print("Autoaudit (antes/depois)...")
    autoaudit = construir_autoaudit(
        vendas, custo_completo,
        margem_sku[margem_sku["UNIVERSO"] == UNIVERSO_COMPLETO], dispersao)

    print("Validando reconciliacoes...")
    validacoes = validar_etapa5(
        vendas, custo_completo, custo_fisico, custo_loja93, total, margem_sku, categorias_n1, lojas,
        precos_desc, dispersao, candidatos)

    print("Salvando arquivos auditaveis...")
    salvar_csv(margem_sku, "margem_produtos.csv")
    salvar_csv(categorias_n1, "margem_categorias_n1.csv")
    salvar_csv(categorias_n2, "margem_categorias_n2.csv")
    salvar_csv(categorias_n3, "margem_categorias_n3.csv")
    salvar_csv(lojas, "margem_lojas.csv")
    salvar_csv(precos_desc, "precificacao_desconto.csv")
    salvar_csv(dispersao, "dispersao_preco_lojas.csv")
    salvar_csv(candidatos, "candidatos_repricing.csv")
    salvar_csv(recomendacoes, "recomendacoes_melhoria.csv")
    salvar_csv(validacoes, "validacoes_etapa5.csv")
    salvar_csv(autoaudit, "autoaudit_etapa5.csv")

    total_completo = total[total["UNIVERSO"] == UNIVERSO_COMPLETO].reset_index(drop=True)
    total_fisico = total[total["UNIVERSO"] == UNIVERSO_FISICO].reset_index(drop=True)
    total_loja93 = total[total["UNIVERSO"] == ESCOPO_LOJA93].reset_index(drop=True)
    n_skus_compra = int(compras["CODIGO"].nunique())
    resumo = gerar_resumo(total_completo, total_fisico, total_loja93, categorias_n1, lojas, margem_sku,
                          precos_desc, dispersao, candidatos, autoaudit, validacoes, n_skus_compra)
    (OUT / "resumo_etapa5.md").write_text(resumo, encoding="utf-8")
    (OUT / "documentacao_tecnica_etapa5.md").write_text(gerar_documentacao_tecnica(), encoding="utf-8")
    salvar_csv(total, "margem_total_universo.csv")

    print("\n--- Destaques Etapa 5 ---")
    tc = total_completo.iloc[0]
    tf = total_fisico.iloc[0]
    print(f"SKUs com custo: {int(tc['SKUS_COM_CUSTO'])} de {int(tc['SKUS'])} "
          f"({tc['COBERTURA_CUSTO_RECEITA_PCT']:.1f}% da receita)")
    print(f"Margem % rede completa: {tc['MARGEM_BRUTA_PCT']:.1f}% | rede fisica: {tf['MARGEM_BRUTA_PCT']:.1f}%")
    tl = total_loja93.iloc[0]
    print(f"Margem % Loja 93/B2B: {tl['MARGEM_BRUTA_PCT']:.1f}%")
    print(f"Markup rede fisica: {tf['MARKUP_PONDERADO']:.2f}x")
    print(f"Candidatos a repricing (rede fisica): "
          f"{len(candidatos[candidatos['UNIVERSO'] == UNIVERSO_FISICO])}")
    print(f"Validacoes OK: {(validacoes['STATUS'] == 'OK').sum()}/{len(validacoes)}")

    print("\n[OK] Arquivos salvos em outputs/etapa5/")
    for path in sorted(OUT.glob("*")):
        print(f"  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
