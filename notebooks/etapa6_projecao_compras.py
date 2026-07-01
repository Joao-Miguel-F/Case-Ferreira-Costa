"""
etapa6_projecao_compras.py
==========================
Etapa 6 - Projecao de compras para o proximo periodo

Objetivos
---------
1. Transformar a priorizacao de cobertura da Etapa 4 em um plano quantitativo
   de compra para 90 dias, no grao loja x SKU.
2. Separar rede fisica e Loja 93/B2B, mantendo reconciliacao com REDE_COMPLETA.
3. Estimar investimento somente para SKUs com custo valido na Etapa 5, sem
   imputar custo ausente nem generalizar margem.
4. Cruzar sinais de venda, cobertura, categoria, loja, custo e margem para
   gerar uma fila operacional conservadora.
5. Persistir metricas, validacoes, resumo executivo, documentacao tecnica e
   revisao critica em arquivos auditaveis.

Premissas e decisoes metodologicas
----------------------------------
- Horizonte de compra: 90 dias. E uma proxy trimestral e conversa com as faixas
  da Etapa 2/4: critico <=30 dias, atencao <=90 dias.
- Demanda base: media mensal dos meses com venda do proprio par loja x SKU nos
  24 meses. Para a rede fisica, essa media reconcilia com a Etapa 2; para a
  Loja 93, a Etapa 6 recalcula a demanda porque a cobertura da Etapa 2 excluia
  a Loja 93 da referencia de consumo por decisao metodologica.
- Status de cobertura: a Etapa 6 recalcula dias de cobertura e status a partir
  dessa demanda propria (`STATUS_ESTOQUE_RECALC`). Para a rede fisica reproduz
  o status da Etapa 2; para a Loja 93 permite que o par atinja CRITICO/ATENCAO
  com sua demanda B2B real, em vez de ficar preso em SEM VENDA/EM RUPTURA. O
  gate de compra usa esse status recalculado.
- Ausencia de venda observada nao vira zero projetado para compra. Pares sem
  demanda observada recebem `MOTIVO_SEM_COMPRA = SEM_DEMANDA_OBSERVADA` e nao
  entram na quantidade recomendada.
- Estoque projetado negativo e tratado como estoque utilizavel zero apenas para
  dimensionar a necessidade de compra. Isso segue a interpretacao da Etapa 2:
  negativo indica saidas acima do estoque visivel, nao estoque fisico negativo.
- Quantidade recomendada = max(demanda_media_mensal * 3 - estoque_utilizavel, 0),
  arredondada para cima na unidade de armazenagem, apenas para pares em
  `EM RUPTURA`, `CRITICO` ou `ATENCAO`.
- Investimento estimado = quantidade recomendada * custo medio valido da Etapa 5
  no mesmo universo. Se nao ha custo valido, investimento fica nulo e o par
  permanece com quantidade operacional, mas sem orcamento estimado.
- Margem nao e calculada para itens sem custo. A margem da Etapa 5 e usada
  apenas quando ja existe custo valido para o SKU no respectivo universo.

Saidas
------
outputs/etapa6/plano_compras_sku_loja.csv
outputs/etapa6/plano_compras_total_universo.csv
outputs/etapa6/plano_compras_categorias_n1.csv
outputs/etapa6/plano_compras_lojas.csv
outputs/etapa6/priorizacao_compras.csv
outputs/etapa6/recomendacoes_melhoria.csv
outputs/etapa6/validacoes_etapa6.csv
outputs/etapa6/autoaudit_etapa6.csv
outputs/etapa6/resumo_etapa6.md
outputs/etapa6/documentacao_tecnica_etapa6.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from utils import LOJA_ATACADO, OUTPUTS, PROCESSED, load_vendas  # noqa: E402
from kpis import emit_kpis, kpi  # noqa: E402


OUT = OUTPUTS / "etapa6"
OUT.mkdir(parents=True, exist_ok=True)

E3 = OUTPUTS / "etapa3"
E4 = OUTPUTS / "etapa4"
E5 = OUTPUTS / "etapa5"

UNIVERSO_COMPLETO = "REDE_COMPLETA"
UNIVERSO_FISICO = "REDE_FISICA_SEM_LOJA93"
ESCOPO_LOJA93 = "LOJA_93_ATACADO_B2B"

STATUS_COMPRA = ["EM RUPTURA", "CRITICO", "ATENCAO"]
STATUS_ALIASES = {
    "CRITICO": "CRITICO",
    "CRÍTICO": "CRITICO",
    "ATENCAO": "ATENCAO",
    "ATENÇÃO": "ATENCAO",
    "EM RUPTURA": "EM RUPTURA",
    "SAUDAVEL": "SAUDAVEL",
    "SAUDÁVEL": "SAUDAVEL",
    "SEM VENDA": "SEM VENDA",
}
HORIZONTE_DIAS = 90
MESES_HORIZONTE = HORIZONTE_DIAS / 30


def safe_div(numerador, denominador):
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


def markdown_table(df: pd.DataFrame) -> str:
    """Gera tabela Markdown simples sem depender de `tabulate`."""
    cols = list(df.columns)
    linhas = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in df.iterrows():
        vals = [str(row[col]).replace("\n", " ").replace("|", "/") for col in cols]
        linhas.append("| " + " | ".join(vals) + " |")
    return "\n".join(linhas)


def normalizar_status(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("ascii")
        .str.upper()
        .map(STATUS_ALIASES)
        .fillna(s.astype(str).str.upper())
    )


def carregar_base_plano() -> pd.DataFrame:
    cobertura = pd.read_parquet(PROCESSED / "cobertura_estoque.parquet").copy()
    cobertura["STATUS_ESTOQUE_ORIGINAL"] = cobertura["STATUS_ESTOQUE"].astype(str)
    cobertura["STATUS_ESTOQUE_NORM"] = normalizar_status(cobertura["STATUS_ESTOQUE"])
    cobertura["RECEITA_TOTAL"] = cobertura["RECEITA_TOTAL"].fillna(0.0)

    vendas = load_vendas(excluir_atacado=False).copy()
    vendas["ANO_MES_DT"] = vendas["DATA_VENDA"].dt.to_period("M")

    demanda = (
        vendas.groupby(["COD_EMPRESA", "CODIGO", "ANO_MES_DT"])["QTD_ARMAZENAGEM"]
        .sum()
        .groupby(["COD_EMPRESA", "CODIGO"])
        .agg(VENDA_MEDIA_MES_PROJECAO="mean", MESES_COM_VENDA="size")
        .reset_index()
    )
    receita_qtd = (
        vendas.groupby(["COD_EMPRESA", "CODIGO"])
        .agg(
            RECEITA_VENDAS=("RECEITA", "sum"),
            QTD_ARM_VENDIDA=("QTD_ARMAZENAGEM", "sum"),
        )
        .reset_index()
    )

    base = (
        cobertura.merge(demanda, on=["COD_EMPRESA", "CODIGO"], how="left", validate="one_to_one")
        .merge(receita_qtd, on=["COD_EMPRESA", "CODIGO"], how="left", validate="one_to_one")
    )
    base["VENDA_MEDIA_MES_ETAPA2"] = base["VENDA_MEDIA_MES"]
    base["PRECO_MEDIO_ARM_HIST"] = safe_div(base["RECEITA_VENDAS"], base["QTD_ARM_VENDIDA"])
    base["FLAG_DEMANDA_OBSERVADA"] = base["VENDA_MEDIA_MES_PROJECAO"].notna().astype(int)
    base["VENDA_MEDIA_MES_PROJECAO"] = base["VENDA_MEDIA_MES_PROJECAO"].where(
        base["FLAG_DEMANDA_OBSERVADA"] == 1
    )
    base["MESES_COM_VENDA"] = base["MESES_COM_VENDA"].fillna(0).astype(int)
    base["UNIVERSO_OPERACIONAL"] = np.where(
        base["COD_EMPRESA"] == LOJA_ATACADO,
        ESCOPO_LOJA93,
        UNIVERSO_FISICO,
    )
    base["FLAG_LOJA93"] = (base["COD_EMPRESA"] == LOJA_ATACADO).astype(int)

    # Recalcula cobertura/status com a demanda da propria etapa. Para a rede
    # fisica isso reproduz o status da Etapa 2 (mesma demanda). Para a Loja 93,
    # que foi excluida da referencia de consumo na Etapa 2, passa a classificar
    # com a demanda B2B real, em vez de herdar "SEM VENDA"/"EM RUPTURA" de uma
    # demanda forcada a zero. Sem isso o gate de compra nunca alcancaria
    # CRITICO/ATENCAO na Loja 93.
    demanda_status = base["VENDA_MEDIA_MES_PROJECAO"].fillna(0.0)
    dias = safe_div(base["ESTOQUE_PROJ"] * 30, demanda_status)
    base["DIAS_COBERTURA_PROJ"] = np.where(base["ESTOQUE_PROJ"] <= 0, 0.0, dias)
    base["STATUS_ESTOQUE_RECALC"] = np.select(
        [
            base["ESTOQUE_PROJ"] <= 0,
            demanda_status <= 0,
            base["DIAS_COBERTURA_PROJ"] <= 30,
            base["DIAS_COBERTURA_PROJ"] <= 90,
        ],
        ["EM RUPTURA", "SEM VENDA", "CRITICO", "ATENCAO"],
        default="SAUDAVEL",
    )
    return base


def anexar_sinais_etapas(base: pd.DataFrame) -> pd.DataFrame:
    rank = pd.read_csv(E3 / "ranking_produtos_receita.csv", encoding="utf-8-sig")
    rank = rank[
        ["UNIVERSO", "CODIGO", "CURVA_ABC_RECEITA", "RANK_RECEITA", "PARTICIPACAO_RECEITA_PCT"]
    ].rename(columns={"PARTICIPACAO_RECEITA_PCT": "PART_RECEITA_SKU_UNIVERSO_PCT"})

    margem = pd.read_csv(E5 / "margem_produtos.csv", encoding="utf-8-sig")
    margem = margem[
        [
            "UNIVERSO",
            "CODIGO",
            "CUSTO_MEDIO_ARM",
            "MARGEM_BRUTA_PCT",
            "MARKUP",
            "FLAG_MARGEM_NEGATIVA",
            "CURVA_ABC_RECEITA",
        ]
    ].rename(
        columns={
            "CURVA_ABC_RECEITA": "CURVA_ABC_RECEITA_CUSTO",
            "MARGEM_BRUTA_PCT": "MARGEM_BRUTA_PCT_COM_CUSTO",
        }
    )

    out = base.merge(
        rank,
        left_on=["UNIVERSO_OPERACIONAL", "CODIGO"],
        right_on=["UNIVERSO", "CODIGO"],
        how="left",
        validate="many_to_one",
    ).drop(columns=["UNIVERSO"])

    out["CURVA_ABC_ORIGEM"] = np.where(
        out["CURVA_ABC_RECEITA"].notna(),
        "UNIVERSO_OPERACIONAL",
        "AUSENTE",
    )
    rank_completo = rank[rank["UNIVERSO"] == UNIVERSO_COMPLETO][
        ["CODIGO", "CURVA_ABC_RECEITA", "RANK_RECEITA", "PART_RECEITA_SKU_UNIVERSO_PCT"]
    ].rename(
        columns={
            "CURVA_ABC_RECEITA": "CURVA_ABC_RECEITA_REDE_COMPLETA",
            "RANK_RECEITA": "RANK_RECEITA_REDE_COMPLETA",
            "PART_RECEITA_SKU_UNIVERSO_PCT": "PART_RECEITA_SKU_REDE_COMPLETA_PCT",
        }
    )
    out = out.merge(rank_completo, on="CODIGO", how="left", validate="many_to_one")
    fallback_loja93 = (
        (out["UNIVERSO_OPERACIONAL"] == ESCOPO_LOJA93)
        & out["CURVA_ABC_RECEITA"].isna()
        & out["CURVA_ABC_RECEITA_REDE_COMPLETA"].notna()
    )
    for col, fallback_col in [
        ("CURVA_ABC_RECEITA", "CURVA_ABC_RECEITA_REDE_COMPLETA"),
        ("RANK_RECEITA", "RANK_RECEITA_REDE_COMPLETA"),
        ("PART_RECEITA_SKU_UNIVERSO_PCT", "PART_RECEITA_SKU_REDE_COMPLETA_PCT"),
    ]:
        out.loc[fallback_loja93, col] = out.loc[fallback_loja93, fallback_col]
    out.loc[fallback_loja93, "CURVA_ABC_ORIGEM"] = "REDE_COMPLETA_FALLBACK_LOJA93"
    out = out.drop(
        columns=[
            "CURVA_ABC_RECEITA_REDE_COMPLETA",
            "RANK_RECEITA_REDE_COMPLETA",
            "PART_RECEITA_SKU_REDE_COMPLETA_PCT",
        ]
    )

    out = out.merge(
        margem,
        left_on=["UNIVERSO_OPERACIONAL", "CODIGO"],
        right_on=["UNIVERSO", "CODIGO"],
        how="left",
        validate="many_to_one",
    ).drop(columns=["UNIVERSO"])
    out["FLAG_CUSTO_VALIDO"] = out["CUSTO_MEDIO_ARM"].notna().astype(int)
    out["FLAG_MARGEM_VALIDA"] = out["MARGEM_BRUTA_PCT_COM_CUSTO"].notna().astype(int)
    out["FLAG_MARGEM_NEGATIVA"] = out["FLAG_MARGEM_NEGATIVA"].fillna(0).astype(int)
    return out


def calcular_plano_operacional(base: pd.DataFrame) -> pd.DataFrame:
    out = base.copy()
    out["ESTOQUE_UTILIZAVEL_ARM"] = np.where(out["ESTOQUE_PROJ"] > 0, out["ESTOQUE_PROJ"], 0.0)
    out["DEMANDA_90D_ARM"] = out["VENDA_MEDIA_MES_PROJECAO"] * MESES_HORIZONTE
    out["FLAG_STATUS_COMPRA"] = out["STATUS_ESTOQUE_RECALC"].isin(STATUS_COMPRA).astype(int)
    out["NECESSIDADE_BRUTA_ARM"] = np.where(
        (out["FLAG_STATUS_COMPRA"] == 1) & (out["FLAG_DEMANDA_OBSERVADA"] == 1),
        out["DEMANDA_90D_ARM"] - out["ESTOQUE_UTILIZAVEL_ARM"],
        np.nan,
    )
    # clip preserva NaN nos pares nao avaliados (mantem "sem necessidade" != "nao avaliado" no CSV).
    out["NECESSIDADE_BRUTA_ARM"] = out["NECESSIDADE_BRUTA_ARM"].clip(lower=0)
    out["QTD_RECOMENDADA_ARM"] = np.where(
        out["NECESSIDADE_BRUTA_ARM"] > 0,
        np.ceil(out["NECESSIDADE_BRUTA_ARM"]),
        0.0,
    )
    out["INVESTIMENTO_ESTIMADO"] = np.where(
        (out["QTD_RECOMENDADA_ARM"] > 0) & (out["FLAG_CUSTO_VALIDO"] == 1),
        out["QTD_RECOMENDADA_ARM"] * out["CUSTO_MEDIO_ARM"],
        np.nan,
    )
    out["RECEITA_POTENCIAL_90D"] = np.where(
        (out["QTD_RECOMENDADA_ARM"] > 0) & out["PRECO_MEDIO_ARM_HIST"].notna(),
        out["DEMANDA_90D_ARM"] * out["PRECO_MEDIO_ARM_HIST"],
        np.nan,
    )

    status_peso = {"EM RUPTURA": 3, "CRITICO": 2, "ATENCAO": 1}
    abc_peso = {"A": 3, "B": 2, "C": 1}
    receita_pct = out["RECEITA_TOTAL"].rank(pct=True).fillna(0)
    out["SCORE_PRIORIDADE"] = (
        out["STATUS_ESTOQUE_RECALC"].map(status_peso).fillna(0)
        + out["CURVA_ABC_RECEITA"].map(abc_peso).fillna(0)
        + receita_pct
        + np.where(out["FLAG_CUSTO_VALIDO"] == 1, 0.25, 0)
        - np.where(out["FLAG_MARGEM_NEGATIVA"] == 1, 0.50, 0)
    )

    elegiveis = out["QTD_RECOMENDADA_ARM"] > 0
    out["RANK_PRIORIDADE"] = pd.NA
    out.loc[elegiveis, "RANK_PRIORIDADE"] = (
        out.loc[elegiveis]
        .sort_values(["SCORE_PRIORIDADE", "RECEITA_TOTAL"], ascending=[False, False])
        .groupby("UNIVERSO_OPERACIONAL")
        .cumcount()
        + 1
    )

    out["MOTIVO_SEM_COMPRA"] = np.select(
        [
            out["QTD_RECOMENDADA_ARM"] > 0,
            out["FLAG_DEMANDA_OBSERVADA"] == 0,
            out["FLAG_STATUS_COMPRA"] == 0,
            out["NECESSIDADE_BRUTA_ARM"] <= 0,
        ],
        [
            "COMPRA_RECOMENDADA",
            "SEM_DEMANDA_OBSERVADA",
            "STATUS_FORA_DA_FILA_DE_COMPRA",
            "ESTOQUE_COBRE_HORIZONTE_90D",
        ],
        default="NAO_CLASSIFICADO",
    )
    out["STATUS_ORCAMENTO"] = np.where(
        out["QTD_RECOMENDADA_ARM"] <= 0,
        "NAO_APLICAVEL_SEM_COMPRA",
        np.where(out["FLAG_CUSTO_VALIDO"] == 1, "COM_CUSTO_VALIDO", "SEM_CUSTO_VALIDO"),
    )
    out["ACAO_RECOMENDADA"] = out.apply(acao_recomendada, axis=1)
    return out


def acao_recomendada(r: pd.Series) -> str:
    if r["QTD_RECOMENDADA_ARM"] <= 0:
        return "Nao comprar nesta rodada; manter monitoramento conforme motivo metodologico."
    if r["FLAG_CUSTO_VALIDO"] == 0:
        return "Validar custo/fornecedor antes de orcar; quantidade operacional calculada sem investimento estimado."
    if r["FLAG_MARGEM_NEGATIVA"] == 1:
        return "Validar preco e margem antes de comprar; ha sinal de margem negativa na Etapa 5."
    return "Priorizar compra para recompor cobertura de 90 dias, validando saldo fisico antes do pedido."


def agregar_universo(universo: str, base: pd.DataFrame) -> pd.DataFrame:
    d = base.copy()
    compra = d[d["QTD_RECOMENDADA_ARM"] > 0]
    inv_conhecido = compra["INVESTIMENTO_ESTIMADO"].sum(min_count=1)
    return pd.DataFrame(
        [
            {
                "UNIVERSO": universo,
                "PARES_LOJA_SKU": len(d),
                "SKUS": d["CODIGO"].nunique(),
                "LOJAS": d["COD_EMPRESA"].nunique(),
                "RECEITA_HISTORICA_TOTAL": d["RECEITA_TOTAL"].sum(),
                "PARES_RUPTURA_CRITICO": d["STATUS_ESTOQUE_RECALC"].isin(["EM RUPTURA", "CRITICO"]).sum(),
                "RECEITA_RUPTURA_CRITICO": d.loc[
                    d["STATUS_ESTOQUE_RECALC"].isin(["EM RUPTURA", "CRITICO"]), "RECEITA_TOTAL"
                ].sum(),
                "PARES_COM_COMPRA_RECOMENDADA": len(compra),
                "SKUS_COM_COMPRA_RECOMENDADA": compra["CODIGO"].nunique(),
                "QTD_RECOMENDADA_ARM": compra["QTD_RECOMENDADA_ARM"].sum(),
                "DEMANDA_90D_ARM": compra["DEMANDA_90D_ARM"].sum(),
                "INVESTIMENTO_ESTIMADO_COM_CUSTO": inv_conhecido,
                "PARES_COMPRA_COM_CUSTO": int((compra["FLAG_CUSTO_VALIDO"] == 1).sum()),
                "PARES_COMPRA_SEM_CUSTO": int((compra["FLAG_CUSTO_VALIDO"] == 0).sum()),
                "COBERTURA_CUSTO_PARES_COMPRA_PCT": safe_div(
                    [(compra["FLAG_CUSTO_VALIDO"] == 1).sum()], [len(compra)]
                )[0]
                * 100,
                "RECEITA_POTENCIAL_90D": compra["RECEITA_POTENCIAL_90D"].sum(min_count=1),
            }
        ]
    )


def agregar_chaves(plano: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    compra_flag = plano["QTD_RECOMENDADA_ARM"] > 0
    d = plano.assign(
        FLAG_COMPRA=compra_flag.astype(int),
        SKU_COMPRA=np.where(compra_flag, plano["CODIGO"], np.nan),
        INVEST_CONHECIDO=plano["INVESTIMENTO_ESTIMADO"],
        QTD_COMPRA=plano["QTD_RECOMENDADA_ARM"],
    )
    agg = (
        d.groupby(["UNIVERSO", *keys], dropna=False)
        .agg(
            PARES_LOJA_SKU=("CODIGO", "size"),
            SKUS=("CODIGO", "nunique"),
            RECEITA_HISTORICA_TOTAL=("RECEITA_TOTAL", "sum"),
            PARES_COM_COMPRA_RECOMENDADA=("FLAG_COMPRA", "sum"),
            SKUS_COM_COMPRA_RECOMENDADA=("SKU_COMPRA", "nunique"),
            QTD_RECOMENDADA_ARM=("QTD_COMPRA", "sum"),
            INVESTIMENTO_ESTIMADO_COM_CUSTO=("INVEST_CONHECIDO", lambda s: s.sum(min_count=1)),
            PARES_COMPRA_COM_CUSTO=("FLAG_CUSTO_VALIDO", lambda s: int(((s == 1) & compra_flag.loc[s.index]).sum())),
            PARES_COMPRA_SEM_CUSTO=("FLAG_CUSTO_VALIDO", lambda s: int(((s == 0) & compra_flag.loc[s.index]).sum())),
        )
        .reset_index()
    )
    agg["COBERTURA_CUSTO_PARES_COMPRA_PCT"] = safe_div(
        agg["PARES_COMPRA_COM_CUSTO"], agg["PARES_COM_COMPRA_RECOMENDADA"]
    ) * 100
    return agg.sort_values(
        ["UNIVERSO", "INVESTIMENTO_ESTIMADO_COM_CUSTO", "QTD_RECOMENDADA_ARM"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def preparar_saidas(plano_operacional: pd.DataFrame):
    fisico = plano_operacional[plano_operacional["UNIVERSO_OPERACIONAL"] == UNIVERSO_FISICO].copy()
    loja93 = plano_operacional[plano_operacional["UNIVERSO_OPERACIONAL"] == ESCOPO_LOJA93].copy()
    completo = plano_operacional.copy()

    total = pd.concat(
        [
            agregar_universo(UNIVERSO_COMPLETO, completo),
            agregar_universo(UNIVERSO_FISICO, fisico),
            agregar_universo(ESCOPO_LOJA93, loja93),
        ],
        ignore_index=True,
    )

    planos_agg = []
    for universo, df in [
        (UNIVERSO_COMPLETO, completo),
        (UNIVERSO_FISICO, fisico),
        (ESCOPO_LOJA93, loja93),
    ]:
        tmp = df.copy()
        tmp["UNIVERSO"] = universo
        planos_agg.append(tmp)
    plano_universos = pd.concat(planos_agg, ignore_index=True)

    categorias = agregar_chaves(plano_universos, ["NIVEL_1"])
    lojas = agregar_chaves(plano_universos, ["COD_EMPRESA", "CD_CIDADE", "CD_ESTADO", "FLAG_LOJA93"])

    priorizacao = (
        plano_operacional[plano_operacional["QTD_RECOMENDADA_ARM"] > 0]
        .sort_values(
            ["UNIVERSO_OPERACIONAL", "SCORE_PRIORIDADE", "RECEITA_TOTAL"],
            ascending=[True, False, False],
        )
        .copy()
    )
    priorizacao["RANK_PRIORIDADE"] = priorizacao.groupby("UNIVERSO_OPERACIONAL").cumcount() + 1
    total_escopo = priorizacao.groupby("UNIVERSO_OPERACIONAL")["RANK_PRIORIDADE"].transform("max")
    limite_alta = np.maximum(1, np.ceil(total_escopo * 0.10)).astype(int)
    limite_media = np.maximum(limite_alta + 1, np.ceil(total_escopo * 0.30)).astype(int)
    priorizacao["FAIXA_PRIORIDADE"] = np.select(
        [
            priorizacao["RANK_PRIORIDADE"] <= limite_alta,
            priorizacao["RANK_PRIORIDADE"] <= limite_media,
        ],
        ["ALTA", "MEDIA"],
        default="MONITORAR",
    )
    return total, categorias, lojas, priorizacao


def validar_etapa6(plano: pd.DataFrame, total: pd.DataFrame, categorias: pd.DataFrame, lojas: pd.DataFrame) -> pd.DataFrame:
    validacoes = []

    def add(nome, obs, esp, tol=1e-4):
        dif = obs - esp
        validacoes.append(
            {
                "VALIDACAO": nome,
                "OBSERVADO": obs,
                "ESPERADO": esp,
                "DIFERENCA": dif,
                "STATUS": "OK" if abs(dif) <= tol else "FALHA",
            }
        )

    def add_bool(nome, cond):
        add(nome, 1.0 if cond else 0.0, 1.0, tol=0)

    e3_impacto = pd.read_csv(E3 / "impacto_loja93.csv", encoding="utf-8-sig").set_index("SEGMENTO")
    add(
        "Receita historica plano vs Etapa 3 - rede completa",
        total.loc[total["UNIVERSO"] == UNIVERSO_COMPLETO, "RECEITA_HISTORICA_TOTAL"].iloc[0],
        e3_impacto.loc[UNIVERSO_COMPLETO, "RECEITA"],
    )
    add(
        "Receita historica plano vs Etapa 3 - rede fisica",
        total.loc[total["UNIVERSO"] == UNIVERSO_FISICO, "RECEITA_HISTORICA_TOTAL"].iloc[0],
        e3_impacto.loc[UNIVERSO_FISICO, "RECEITA"],
    )
    add(
        "Receita historica plano vs Etapa 3 - Loja 93",
        total.loc[total["UNIVERSO"] == ESCOPO_LOJA93, "RECEITA_HISTORICA_TOTAL"].iloc[0],
        e3_impacto.loc[ESCOPO_LOJA93, "RECEITA"],
    )

    full = total.loc[total["UNIVERSO"] == UNIVERSO_COMPLETO].iloc[0]
    fis = total.loc[total["UNIVERSO"] == UNIVERSO_FISICO].iloc[0]
    l93 = total.loc[total["UNIVERSO"] == ESCOPO_LOJA93].iloc[0]
    for col in ["PARES_LOJA_SKU", "RECEITA_HISTORICA_TOTAL", "QTD_RECOMENDADA_ARM"]:
        add(f"REDE_COMPLETA = fisica + Loja 93 ({col})", full[col], fis[col] + l93[col])

    inv_full = full["INVESTIMENTO_ESTIMADO_COM_CUSTO"]
    inv_partes = fis["INVESTIMENTO_ESTIMADO_COM_CUSTO"] + l93["INVESTIMENTO_ESTIMADO_COM_CUSTO"]
    add("Investimento conhecido: REDE_COMPLETA = fisica + Loja 93", inv_full, inv_partes)

    e4_cat = pd.read_csv(E4 / "cobertura_categorias_n1.csv", encoding="utf-8-sig")
    etapa6_risco = (
        plano.assign(UNIVERSO=plano["UNIVERSO_OPERACIONAL"])
        .groupby(["UNIVERSO", "NIVEL_1"], dropna=False)["RECEITA_TOTAL"]
        .sum()
        .reset_index(name="RECEITA_TOTAL_PLANO")
    )
    # Reconciliacao de receita total por categoria com Etapa 4 nos universos operacionais.
    e4_total = e4_cat[e4_cat["UNIVERSO"].isin([UNIVERSO_FISICO])][
        ["UNIVERSO", "NIVEL_1", "RECEITA_HISTORICA_TOTAL"]
    ]
    comp = etapa6_risco.merge(e4_total, on=["UNIVERSO", "NIVEL_1"], how="inner")
    add(
        "Categoria N1: receita total vs Etapa 4 - rede fisica (max abs)",
        float((comp["RECEITA_TOTAL_PLANO"] - comp["RECEITA_HISTORICA_TOTAL"]).abs().max()),
        0.0,
    )

    add_bool(
        "Toda compra recomendada possui demanda observada",
        bool((plano.loc[plano["QTD_RECOMENDADA_ARM"] > 0, "FLAG_DEMANDA_OBSERVADA"] == 1).all()),
    )
    add_bool(
        "Toda compra recomendada esta em status elegivel",
        bool(plano.loc[plano["QTD_RECOMENDADA_ARM"] > 0, "STATUS_ESTOQUE_RECALC"].isin(STATUS_COMPRA).all()),
    )
    add_bool(
        "Rede fisica: status recalculado == status Etapa 2",
        bool(
            (
                plano.loc[plano["FLAG_LOJA93"] == 0, "STATUS_ESTOQUE_RECALC"]
                == plano.loc[plano["FLAG_LOJA93"] == 0, "STATUS_ESTOQUE_NORM"]
            ).all()
        ),
    )
    add_bool(
        "Todo par com demanda e cobertura < 90 dias entra na fila de compra",
        bool(
            (
                plano.loc[
                    (plano["FLAG_DEMANDA_OBSERVADA"] == 1)
                    & (plano["ESTOQUE_PROJ"] > 0)
                    & (plano["DIAS_COBERTURA_PROJ"] < HORIZONTE_DIAS),
                    "QTD_RECOMENDADA_ARM",
                ]
                > 0
            ).all()
        ),
    )
    add_bool(
        "Investimento nao foi imputado para custo ausente",
        bool(plano.loc[(plano["QTD_RECOMENDADA_ARM"] > 0) & (plano["FLAG_CUSTO_VALIDO"] == 0), "INVESTIMENTO_ESTIMADO"].isna().all()),
    )
    add_bool(
        "Margem so marcada como valida onde ha custo",
        bool((plano["FLAG_MARGEM_VALIDA"] <= plano["FLAG_CUSTO_VALIDO"]).all()),
    )
    add_bool(
        "Loja 93 fora do universo operacional fisico",
        bool(not ((plano["UNIVERSO_OPERACIONAL"] == UNIVERSO_FISICO) & (plano["COD_EMPRESA"] == LOJA_ATACADO)).any()),
    )
    add_bool(
        "Loja 93 com receita possui curva ABC de guarda-corpo",
        bool(plano.loc[
            (plano["UNIVERSO_OPERACIONAL"] == ESCOPO_LOJA93) & (plano["RECEITA_TOTAL"] > 0),
            "CURVA_ABC_RECEITA",
        ].notna().all()),
    )
    add_bool(
        "Categorias agregadas fecham quantidade por universo",
        bool(
            np.allclose(
                categorias.groupby("UNIVERSO")["QTD_RECOMENDADA_ARM"].sum().sort_index(),
                total.set_index("UNIVERSO")["QTD_RECOMENDADA_ARM"].sort_index(),
            )
        ),
    )
    add_bool(
        "Lojas agregadas fecham quantidade por universo",
        bool(
            np.allclose(
                lojas.groupby("UNIVERSO")["QTD_RECOMENDADA_ARM"].sum().sort_index(),
                total.set_index("UNIVERSO")["QTD_RECOMENDADA_ARM"].sort_index(),
            )
        ),
    )
    return pd.DataFrame(validacoes)


def construir_autoaudit(plano: pd.DataFrame, total: pd.DataFrame) -> pd.DataFrame:
    compra = plano[plano["QTD_RECOMENDADA_ARM"] > 0]
    sem_custo = int((compra["FLAG_CUSTO_VALIDO"] == 0).sum())
    com_custo = int((compra["FLAG_CUSTO_VALIDO"] == 1).sum())
    loja93_venda = int(((plano["COD_EMPRESA"] == LOJA_ATACADO) & (plano["FLAG_DEMANDA_OBSERVADA"] == 1)).sum())
    loja93_vmm_etapa2_zero = int(
        ((plano["COD_EMPRESA"] == LOJA_ATACADO) & (plano["VENDA_MEDIA_MES_ETAPA2"] == 0) & (plano["FLAG_DEMANDA_OBSERVADA"] == 1)).sum()
    )
    qtd_neg = int((plano["ESTOQUE_PROJ"] < 0).sum())
    loja93_reclass = int(
        ((plano["COD_EMPRESA"] == LOJA_ATACADO) & plano["STATUS_ESTOQUE_RECALC"].isin(["CRITICO", "ATENCAO"])).sum()
    )
    return pd.DataFrame(
        [
            {
                "RISCO": "Comprar para pares sem demanda observada",
                "COMO_PODERIA_ERRAR": "Tratar ausencia de venda como zero e ainda assim comprar por status de ruptura inflado.",
                "CONTROLE_APLICADO": "Quantidade recomendada so e calculada quando existe venda historica do par loja x SKU.",
                "EVIDENCIA": f"{int((compra['FLAG_DEMANDA_OBSERVADA'] == 0).sum())} compras recomendadas sem demanda observada.",
                "RISCO_REMANESCENTE": "A demanda historica pode estar subestimada se houve ruptura real prolongada.",
            },
            {
                "RISCO": "Orcamento falso para itens sem custo",
                "COMO_PODERIA_ERRAR": "Multiplicar quantidade por zero ou por custo medio de outro SKU/categoria.",
                "CONTROLE_APLICADO": "Investimento fica nulo quando o SKU nao tem custo valido na Etapa 5.",
                "EVIDENCIA": f"{sem_custo} pares recomendados sem custo e {com_custo} com custo valido.",
                "RISCO_REMANESCENTE": "O plano operacional pode ser maior que o orcamento conhecido.",
            },
            {
                "RISCO": "Apagar demanda da Loja 93/B2B",
                "COMO_PODERIA_ERRAR": "Reusar a venda media da Etapa 2 (que excluiu a Loja 93) na demanda E no status de cobertura, deixando a Loja 93 presa em SEM VENDA/EM RUPTURA e fora da fila.",
                "CONTROLE_APLICADO": "Demanda e status de cobertura da Etapa 6 sao recalculados a partir das vendas do proprio par; a Loja 93 tambem pode atingir CRITICO/ATENCAO com sua demanda B2B real.",
                "EVIDENCIA": f"{loja93_vmm_etapa2_zero} pares da Loja 93 tinham venda observada e venda media Etapa 2 igual a zero; {loja93_venda} pares da Loja 93 tem demanda propria; {loja93_reclass} pares da Loja 93 foram reclassificados como CRITICO/ATENCAO pela cobertura recalculada.",
                "RISCO_REMANESCENTE": "B2B pode ter pedidos grandes e intermitentes; media historica suaviza picos.",
            },
            {
                "RISCO": "Interpretar estoque negativo como quantidade a comprar integralmente",
                "COMO_PODERIA_ERRAR": "Somar o negativo a demanda futura e inflar compras por ausencia de transferencias/ajustes.",
                "CONTROLE_APLICADO": "Estoque negativo vira zero utilizavel, nao uma divida operacional adicional.",
                "EVIDENCIA": f"{qtd_neg} pares com estoque projetado negativo tratados como zero utilizavel.",
                "RISCO_REMANESCENTE": "Se o negativo refletir venda nao reposta, ainda pode haver subestimativa de necessidade.",
            },
        ]
    )


def gerar_recomendacoes_melhoria() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "PRIORIDADE": "ALTA",
                "TEMA": "Custo para orcamento",
                "LIMITACAO_OU_PROBLEMA": "Apenas parte dos SKUs recomendados tem custo valido na Etapa 5.",
                "RISCO_ANALITICO": "O investimento conhecido subestima o desembolso total se usado como budget fechado.",
                "RECOMENDACAO": "Completar custo por SKU/fornecedor e data de vigencia antes de transformar quantidade em pedido financeiro.",
            },
            {
                "PRIORIDADE": "ALTA",
                "TEMA": "Saldo fisico e transferencias",
                "LIMITACAO_OU_PROBLEMA": "Estoque projetado nao inclui transferencias, ajustes e inventario fisico posterior.",
                "RISCO_ANALITICO": "Falsos positivos de ruptura podem virar compra desnecessaria.",
                "RECOMENDACAO": "Validar saldo fisico dos itens de prioridade ALTA antes de emitir pedido.",
            },
            {
                "PRIORIDADE": "MEDIA",
                "TEMA": "Demanda intermitente",
                "LIMITACAO_OU_PROBLEMA": "A demanda base usa media dos meses com venda, herdando a conservacao da Etapa 2.",
                "RISCO_ANALITICO": "Itens esporadicos podem receber compra acima do ritmo medio de calendario.",
                "RECOMENDACAO": "Rodar sensibilidade com media de calendario e sazonalidade antes do pedido final.",
            },
            {
                "PRIORIDADE": "MEDIA",
                "TEMA": "Politica de estoque",
                "LIMITACAO_OU_PROBLEMA": "Nao ha lead time, lote minimo, multiplo de compra nem nivel de servico por categoria.",
                "RISCO_ANALITICO": "A quantidade recomendada recompõe cobertura alvo, mas nao otimiza lote economico.",
                "RECOMENDACAO": "Adicionar politicas de reposicao por categoria/fornecedor para converter recomendacao em pedido final.",
            },
        ]
    )


def construir_kpis(total, priorizacao, validacoes):
    """KPIs da Etapa 6 (SSOT) — mesmas expressões narradas em gerar_resumo. Ver src/kpis.py."""
    full = total[total["UNIVERSO"] == UNIVERSO_COMPLETO].iloc[0]
    fis = total[total["UNIVERSO"] == UNIVERSO_FISICO].iloc[0]
    l93 = total[total["UNIVERSO"] == ESCOPO_LOJA93].iloc[0]
    alta_fis = priorizacao[(priorizacao["UNIVERSO_OPERACIONAL"] == UNIVERSO_FISICO) & (priorizacao["FAIXA_PRIORIDADE"] == "ALTA")]
    return {
        "e6.pares.rede_completa": kpi(int(full["PARES_COM_COMPRA_RECOMENDADA"]), "pares", "etapa6", "Pares loja×SKU com compra recomendada — rede completa"),
        "e6.unidades.rede_completa": kpi(float(full["QTD_RECOMENDADA_ARM"]), "un", "etapa6", "Unidades de armazenagem recomendadas — rede completa"),
        "e6.pares.rede_fisica": kpi(int(fis["PARES_COM_COMPRA_RECOMENDADA"]), "pares", "etapa6", "Pares recomendados — rede física"),
        "e6.unidades.rede_fisica": kpi(float(fis["QTD_RECOMENDADA_ARM"]), "un", "etapa6", "Unidades recomendadas — rede física"),
        "e6.investimento.rede_fisica": kpi(float(fis["INVESTIMENTO_ESTIMADO_COM_CUSTO"]), "R$", "etapa6", "Investimento conhecido (com custo) — rede física"),
        "e6.pares.loja93": kpi(int(l93["PARES_COM_COMPRA_RECOMENDADA"]), "pares", "etapa6", "Pares recomendados — Loja 93/B2B"),
        "e6.unidades.loja93": kpi(float(l93["QTD_RECOMENDADA_ARM"]), "un", "etapa6", "Unidades recomendadas — Loja 93/B2B"),
        "e6.investimento.loja93": kpi(float(l93["INVESTIMENTO_ESTIMADO_COM_CUSTO"]), "R$", "etapa6", "Investimento conhecido (com custo) — Loja 93/B2B"),
        "e6.cobertura_custo.pct_completa": kpi(float(full["COBERTURA_CUSTO_PARES_COMPRA_PCT"]), "%", "etapa6", "Cobertura de custo dos pares recomendados — rede completa"),
        "e6.prioridade_alta.rede_fisica": kpi(int(len(alta_fis)), "pares", "etapa6", "Pares de prioridade ALTA — rede física"),
        "e6.validacoes.total": kpi(len(validacoes), "checks", "etapa6", "Validações executadas na Etapa 6"),
        "e6.validacoes.ok": kpi(int((validacoes["STATUS"] == "OK").sum()), "checks", "etapa6", "Validações OK na Etapa 6"),
    }


def gerar_resumo(total: pd.DataFrame, categorias: pd.DataFrame, lojas: pd.DataFrame, priorizacao: pd.DataFrame, autoaudit: pd.DataFrame, validacoes: pd.DataFrame) -> str:
    full = total[total["UNIVERSO"] == UNIVERSO_COMPLETO].iloc[0]
    fis = total[total["UNIVERSO"] == UNIVERSO_FISICO].iloc[0]
    l93 = total[total["UNIVERSO"] == ESCOPO_LOJA93].iloc[0]
    top_cat = categorias[categorias["UNIVERSO"] == UNIVERSO_FISICO].sort_values("QTD_RECOMENDADA_ARM", ascending=False).iloc[0]
    top_loja = lojas[(lojas["UNIVERSO"] == UNIVERSO_FISICO) & (lojas["FLAG_LOJA93"] == 0)].sort_values("QTD_RECOMENDADA_ARM", ascending=False).iloc[0]
    alta_fis = priorizacao[(priorizacao["UNIVERSO_OPERACIONAL"] == UNIVERSO_FISICO) & (priorizacao["FAIXA_PRIORIDADE"] == "ALTA")]

    return f"""# Etapa 6 - Projecao de compras para o proximo periodo

## Leitura executiva

A Etapa 6 converte a fila de cobertura da Etapa 4 em uma recomendacao de compra
para 90 dias, mantendo a rede fisica separada da Loja 93/B2B e estimando
investimento apenas quando ha custo valido da Etapa 5.

- Rede completa: {fmt_num(full['PARES_COM_COMPRA_RECOMENDADA'])} pares loja x SKU com compra recomendada, somando {fmt_num(full['QTD_RECOMENDADA_ARM'])} unidades de armazenagem.
- Rede fisica sem Loja 93: {fmt_num(fis['PARES_COM_COMPRA_RECOMENDADA'])} pares recomendados, {fmt_num(fis['QTD_RECOMENDADA_ARM'])} unidades, investimento conhecido de {fmt_brl_milhao(fis['INVESTIMENTO_ESTIMADO_COM_CUSTO'])}.
- Loja 93/B2B: {fmt_num(l93['PARES_COM_COMPRA_RECOMENDADA'])} pares recomendados, {fmt_num(l93['QTD_RECOMENDADA_ARM'])} unidades, investimento conhecido de {fmt_brl_milhao(l93['INVESTIMENTO_ESTIMADO_COM_CUSTO'])}.
- Cobertura de custo dos pares recomendados: {fmt_pct(full['COBERTURA_CUSTO_PARES_COMPRA_PCT'])} na rede completa. O restante tem quantidade operacional, mas nao tem orcamento estimado.
- Na rede fisica, a categoria com maior volume recomendado e `{top_cat['NIVEL_1']}` ({fmt_num(top_cat['QTD_RECOMENDADA_ARM'])} unidades). A loja com maior volume recomendado e a loja {int(top_loja['COD_EMPRESA'])} ({top_loja['CD_CIDADE']}-{top_loja['CD_ESTADO']}), com {fmt_num(top_loja['QTD_RECOMENDADA_ARM'])} unidades.
- A fila operacional tem {fmt_num(len(alta_fis))} pares de prioridade ALTA na rede fisica.

## Principais achados

- O plano e mais operacional do que financeiro: a quantidade recomendada cobre
  todos os pares elegiveis com demanda observada, mas o investimento conhecido
  cobre apenas os itens com custo valido.
- O uso de estoque projetado negativo como zero utilizavel evita inflar compra
  por uma "divida" que pode ser apenas transferencia/ajuste ausente.
- A Loja 93 precisa de rotina propria: a demanda foi recalculada para o canal
  B2B porque a venda media da Etapa 2 era referencia da rede fisica.
- Itens com margem negativa na Etapa 5 permanecem na fila quando ha demanda e
  ruptura, mas a acao recomenda validar preco/margem antes de comprar.

## Limitacoes e riscos de interpretacao

- A quantidade recomendada nao substitui pedido final: faltam saldo fisico atual,
  transferencias, lead time, lote minimo e multiplo de fornecedor.
- O investimento estimado nao e budget total; ele exclui itens sem custo valido.
- A media de meses com venda pode superestimar demanda de itens intermitentes.
- Receita potencial de 90 dias e referencia historica, nao previsao causal.

## Autoaudit / revisao critica

{markdown_table(autoaudit)}

## Validacoes

- {len(validacoes)} validacoes executadas; status geral: `{ 'OK' if (validacoes['STATUS'] == 'OK').all() else 'FALHA' }`.
- Receita, pares e quantidades reconciliam entre `REDE_COMPLETA`, `REDE_FISICA_SEM_LOJA93` e `LOJA_93_ATACADO_B2B`.
- Receita historica fecha com Etapa 3 e categorias da rede fisica fecham com Etapa 4.
- Investimento nao foi imputado para custo ausente.

## Proximos passos

1. Validar saldo fisico dos itens de prioridade ALTA antes de emitir pedido.
2. Completar custo de SKUs sem custo valido para transformar quantidade em budget.
3. Adicionar lead time, lote minimo e politica de servico por categoria.
4. Rodar sensibilidade de demanda com media de calendario e sazonalidade.
"""


def gerar_documentacao_tecnica() -> str:
    return f"""# Documentacao tecnica - Etapa 6

## Entradas

- `data/processed/cobertura_estoque.parquet`: snapshot dez/2025 no grao loja x SKU, com estoque projetado, status, dias de cobertura e receita historica.
- `data/processed/vendas_tratadas.parquet`: recalculo da demanda media mensal por par loja x SKU, incluindo Loja 93 em escopo proprio.
- `outputs/etapa3/ranking_produtos_receita.csv` e `impacto_loja93.csv`: curva ABC e reconciliacao de receita por universo. Como a Etapa 3 materializa ABC para rede completa e rede fisica, a Loja 93 recebe fallback auditavel da curva da rede completa (`CURVA_ABC_ORIGEM = REDE_COMPLETA_FALLBACK_LOJA93`) para compor score e guarda-corpos posteriores.
- `outputs/etapa4/cobertura_categorias_n1.csv`: reconciliacao de receita por categoria na rede fisica.
- `outputs/etapa5/margem_produtos.csv`: custo medio, margem e flags apenas para SKUs com custo valido.

## Granularidade

O arquivo principal `plano_compras_sku_loja.csv` esta no grao loja x SKU, com
`UNIVERSO_OPERACIONAL` separando `REDE_FISICA_SEM_LOJA93` e
`LOJA_93_ATACADO_B2B`. Os agregados tambem trazem `REDE_COMPLETA` como soma
reconciliada desses dois escopos.

## Formulas

- Demanda 90 dias = `VENDA_MEDIA_MES_PROJECAO * {MESES_HORIZONTE:.0f}`.
- Dias de cobertura recalculados = `ESTOQUE_PROJ / VENDA_MEDIA_MES_PROJECAO * 30`
  (0 quando estoque <= 0). `STATUS_ESTOQUE_RECALC` deriva desses dias com os
  mesmos cortes da Etapa 2 (<=30 CRITICO, <=90 ATENCAO), agora tambem para a
  Loja 93. Reproduz o status da Etapa 2 na rede fisica.
- Curva ABC = classe por receita do universo operacional. Na Loja 93, enquanto
  nao houver ranking ABC B2B dedicado na Etapa 3, usa fallback da `REDE_COMPLETA`
  e grava `CURVA_ABC_ORIGEM` para auditoria.
- Estoque utilizavel = `max(ESTOQUE_PROJ, 0)`.
- Necessidade bruta = `max(demanda_90d - estoque_utilizavel, 0)`.
- Quantidade recomendada = teto da necessidade bruta, somente para
  `STATUS_ESTOQUE_RECALC` em `EM RUPTURA`, `CRITICO` ou `ATENCAO` e com demanda
  observada.
- Investimento estimado = `QTD_RECOMENDADA_ARM * CUSTO_MEDIO_ARM`, somente
  quando o custo medio existe na Etapa 5 para o mesmo universo.

## Premissas

- Horizonte de compra: {HORIZONTE_DIAS} dias.
- A demanda usa media dos meses com venda. Ausencia de dado nao e imputada como zero para comprar.
- Estoque negativo nao aumenta a compra; e tratado como zero utilizavel.
- Margem e investimento nao sao calculados para itens sem custo valido.
- Loja 93 e canal B2B/atacado e nao deve ser misturada com rede fisica.

## Validacoes

`validacoes_etapa6.csv` cobre reconciliacao de receita com Etapa 3, soma dos
universos, fechamento de agregados por categoria/loja, restricao de compras a
status elegiveis e garantia de que investimento nao foi imputado para custo
ausente. Verifica ainda que o status recalculado reproduz o da Etapa 2 na rede
fisica, que a Loja 93 possui curva ABC de guarda-corpo e que nenhum par com
demanda e cobertura < 90 dias fica fora da fila.

## Arquivos gerados

- `plano_compras_sku_loja.csv`: plano operacional detalhado.
- `plano_compras_total_universo.csv`: KPIs por universo.
- `plano_compras_categorias_n1.csv`: agregacao por categoria N1.
- `plano_compras_lojas.csv`: agregacao por loja.
- `priorizacao_compras.csv`: fila de compra ranqueada.
- `validacoes_etapa6.csv`: reconciliacoes numericas e status OK/FALHA.
- `autoaudit_etapa6.csv`: riscos de interpretacao e controles aplicados.
- `recomendacoes_melhoria.csv`: proximas melhorias de dados/processo.
- `resumo_etapa6.md`: leitura executiva.

## Riscos e falsos positivos

- Ruptura projetada pode refletir transferencia/ajuste ausente, nao prateleira vazia.
- Demanda historica pode nao representar pedidos B2B futuros.
- Quantidade recomendada sem custo nao tem investimento estimado.
- Itens de margem negativa exigem validacao comercial antes de compra.
"""


def salvar_csv(df: pd.DataFrame, nome: str) -> None:
    df.to_csv(OUT / nome, index=False, encoding="utf-8-sig", float_format="%.6f")


def main() -> None:
    print("Carregando cobertura, vendas e sinais das etapas anteriores...")
    base = carregar_base_plano()
    base = anexar_sinais_etapas(base)

    print("Calculando plano operacional de 90 dias...")
    plano = calcular_plano_operacional(base)
    total, categorias, lojas, priorizacao = preparar_saidas(plano)

    print("Construindo autoaudit e validacoes...")
    autoaudit = construir_autoaudit(plano, total)
    validacoes = validar_etapa6(plano, total, categorias, lojas)
    recomendacoes = gerar_recomendacoes_melhoria()

    print("Salvando arquivos auditaveis...")
    cols_plano = [
        "UNIVERSO_OPERACIONAL",
        "COD_EMPRESA",
        "CD_CIDADE",
        "CD_ESTADO",
        "FLAG_LOJA93",
        "CODIGO",
        "DESCRICAO",
        "NIVEL_1",
        "STATUS_ESTOQUE_ORIGINAL",
        "STATUS_ESTOQUE_NORM",
        "STATUS_ESTOQUE_RECALC",
        "DIAS_COBERTURA_PROJ",
        "ESTOQUE_PROJ",
        "ESTOQUE_UTILIZAVEL_ARM",
        "VENDA_MEDIA_MES_ETAPA2",
        "VENDA_MEDIA_MES_PROJECAO",
        "MESES_COM_VENDA",
        "DEMANDA_90D_ARM",
        "NECESSIDADE_BRUTA_ARM",
        "QTD_RECOMENDADA_ARM",
        "RECEITA_TOTAL",
        "PRECO_MEDIO_ARM_HIST",
        "RECEITA_POTENCIAL_90D",
        "CURVA_ABC_RECEITA",
        "CURVA_ABC_ORIGEM",
        "RANK_RECEITA",
        "CUSTO_MEDIO_ARM",
        "FLAG_CUSTO_VALIDO",
        "INVESTIMENTO_ESTIMADO",
        "STATUS_ORCAMENTO",
        "MARGEM_BRUTA_PCT_COM_CUSTO",
        "FLAG_MARGEM_VALIDA",
        "FLAG_MARGEM_NEGATIVA",
        "SCORE_PRIORIDADE",
        "RANK_PRIORIDADE",
        "MOTIVO_SEM_COMPRA",
        "ACAO_RECOMENDADA",
    ]
    salvar_csv(plano[cols_plano], "plano_compras_sku_loja.csv")
    salvar_csv(total, "plano_compras_total_universo.csv")
    salvar_csv(categorias, "plano_compras_categorias_n1.csv")
    salvar_csv(lojas, "plano_compras_lojas.csv")
    salvar_csv(priorizacao[cols_plano + ["FAIXA_PRIORIDADE"]], "priorizacao_compras.csv")
    salvar_csv(recomendacoes, "recomendacoes_melhoria.csv")
    salvar_csv(validacoes, "validacoes_etapa6.csv")
    salvar_csv(autoaudit, "autoaudit_etapa6.csv")

    # ── SSOT de KPI (fonte única; ver src/kpis.py) ────────────────────────────
    emit_kpis("etapa6", construir_kpis(total, priorizacao, validacoes))

    (OUT / "resumo_etapa6.md").write_text(
        gerar_resumo(total, categorias, lojas, priorizacao, autoaudit, validacoes),
        encoding="utf-8",
    )
    (OUT / "documentacao_tecnica_etapa6.md").write_text(
        gerar_documentacao_tecnica(),
        encoding="utf-8",
    )

    full = total[total["UNIVERSO"] == UNIVERSO_COMPLETO].iloc[0]
    fis = total[total["UNIVERSO"] == UNIVERSO_FISICO].iloc[0]
    print("\n--- Destaques Etapa 6 ---")
    print(f"Pares com compra recomendada - rede completa: {int(full['PARES_COM_COMPRA_RECOMENDADA']):,}")
    print(f"Quantidade recomendada - rede fisica: {fis['QTD_RECOMENDADA_ARM']:,.0f} unid. armazenagem")
    print(f"Investimento conhecido - rede fisica: R$ {fis['INVESTIMENTO_ESTIMADO_COM_CUSTO'] / 1e6:,.1f}M")
    print(f"Cobertura de custo dos pares recomendados - rede completa: {full['COBERTURA_CUSTO_PARES_COMPRA_PCT']:.1f}%")
    print(f"Validacoes OK: {(validacoes['STATUS'] == 'OK').sum()}/{len(validacoes)}")

    print("\n[OK] Arquivos salvos em outputs/etapa6/")
    for path in sorted(OUT.glob("*")):
        print(f"  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
