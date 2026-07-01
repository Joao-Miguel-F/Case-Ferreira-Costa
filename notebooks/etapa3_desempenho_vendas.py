"""
etapa3_desempenho_vendas.py
===========================
Etapa 3 — Análise de Desempenho de Vendas

Objetivos
---------
1. Rankear produtos por receita e quantidade vendida em unidade de armazenagem
2. Classificar produtos pela curva ABC de receita
3. Analisar desempenho por hierarquia de produto, loja e região
4. Medir sazonalidade mensal e comparar 2024 vs 2025
5. Decompor a queda de 2025 por categoria e loja

Premissas e decisões metodológicas
----------------------------------
- Todos os números partem de data/processed/vendas_tratadas.parquet.
- Quantidade é analisada em QTD_ARMAZENAGEM, mantendo consistência com as
  etapas anteriores.
- A Loja 93 (Alhandra-PB) é mantida na visão de rede completa e segregada na
  visão de rede física sem Loja 93. A exclusão nunca é implícita.
- Participações percentuais são sempre calculadas dentro do próprio universo
  analisado.
- Variação 2025 vs 2024 compara anos completos presentes na base.
- Picos e quedas são evidências descritivas por variação observada; o script
  não atribui causa sem dado adicional.

Saídas
------
outputs/etapa3/ranking_produtos_receita.csv
outputs/etapa3/ranking_produtos_quantidade.csv
outputs/etapa3/curva_abc_produtos.csv
outputs/etapa3/desempenho_categorias_n1.csv
outputs/etapa3/desempenho_categorias_n2.csv
outputs/etapa3/desempenho_categorias_n3.csv
outputs/etapa3/desempenho_lojas.csv
outputs/etapa3/desempenho_regioes.csv
outputs/etapa3/vendas_mensais.csv
outputs/etapa3/sazonalidade_picos_quedas.csv
outputs/etapa3/decomposicao_queda_2025_categorias.csv
outputs/etapa3/decomposicao_queda_2025_lojas.csv
outputs/etapa3/diagnostico_captura_mensal.csv
outputs/etapa3/diagnostico_captura_lojas_mensal.csv
outputs/etapa3/impacto_loja93.csv
outputs/etapa3/notas_metodologicas.csv
outputs/etapa3/recomendacoes_melhoria.csv
outputs/etapa3/validacoes_etapa3.csv
outputs/etapa3/resumo_etapa3.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Raiz do repositório resolvida a partir do arquivo (roda de qualquer diretório)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from utils import LOJA_ATACADO, OUTPUTS, load_vendas  # noqa: E402


OUT = OUTPUTS / "etapa3"
OUT.mkdir(parents=True, exist_ok=True)

UNIVERSO_COMPLETO = "REDE_COMPLETA"
UNIVERSO_FISICO = "REDE_FISICA_SEM_LOJA93"

DIMENSOES_OBRIGATORIAS = [
    "DESCRICAO",
    "NIVEL_1",
    "NIVEL_2",
    "NIVEL_3",
    "CD_CIDADE",
    "CD_ESTADO",
]

METRICAS_BASE = ["RECEITA", "QTD_ARMAZENAGEM", "TRANSACOES"]

OBS_TRANSACOES = (
    "A base processada não possui identificador de cupom, pedido ou nota. "
    "Assim, TRANSACOES nesta etapa é a contagem de linhas de fato_vendas "
    "e o ticket médio é uma proxy de receita média por linha de venda."
)


def safe_div(numerador: pd.Series | np.ndarray | float, denominador: pd.Series | np.ndarray | float):
    """Divide evitando infinito quando o denominador é zero."""
    num = np.asarray(numerador, dtype=float)
    den = np.asarray(denominador, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        resultado = np.divide(num, den)
    return np.where(den != 0, resultado, np.nan)


def classifica_abc(receita_acum_pct: float) -> str:
    """Classifica item na curva ABC de receita."""
    if receita_acum_pct <= 80:
        return "A"
    if receita_acum_pct <= 95:
        return "B"
    return "C"


def fmt_brl(valor: float) -> str:
    """Formata número em padrão monetário brasileiro para o resumo Markdown."""
    return f"R$ {valor:,.1f}M".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_brl_valor(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_num(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", ".")


def fmt_decimal(valor: float, casas: int = 2) -> str:
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(valor: float) -> str:
    return f"{valor:.1f}%".replace(".", ",")


def preparar_vendas(vendas: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Garante tipos e dimensões preenchidas para groupbys não perderem linhas.

    A Etapa 1 já validou integridade referencial, mas a checagem fica explícita
    aqui porque todos os totais da Etapa 3 dependem destas dimensões.
    """
    df = vendas.copy()
    df["DATA_VENDA"] = pd.to_datetime(df["DATA_VENDA"])
    df["ANO_MES"] = df["DATA_VENDA"].dt.to_period("M").astype(str)
    df["ANO"] = df["DATA_VENDA"].dt.year
    df["MES"] = df["DATA_VENDA"].dt.month

    nulos_dimensoes = {col: int(df[col].isna().sum()) for col in DIMENSOES_OBRIGATORIAS}
    for col in DIMENSOES_OBRIGATORIAS:
        df[col] = df[col].fillna("SEM CADASTRO")

    df["TIPO_OPERACAO"] = np.where(
        df["COD_EMPRESA"] == LOJA_ATACADO,
        "LOJA_93_ATACADO_B2B",
        "REDE_FISICA",
    )
    return df, nulos_dimensoes


def universos(vendas: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        UNIVERSO_COMPLETO: vendas.copy(),
        UNIVERSO_FISICO: vendas[vendas["COD_EMPRESA"] != LOJA_ATACADO].copy(),
    }


def metricas_totais(df: pd.DataFrame) -> dict[str, float]:
    return {
        "RECEITA": float(df["RECEITA"].sum()),
        "QTD_ARMAZENAGEM": float(df["QTD_ARMAZENAGEM"].sum()),
        "TRANSACOES": int(len(df)),
        "SKUS_ATIVOS": int(df["CODIGO"].nunique()),
        "LOJAS_ATIVAS": int(df["COD_EMPRESA"].nunique()),
    }


def agregar_produtos(df: pd.DataFrame, nome_universo: str) -> pd.DataFrame:
    total = metricas_totais(df)
    grp = (
        df.groupby(["CODIGO", "DESCRICAO", "NIVEL_1", "NIVEL_2", "NIVEL_3"], dropna=False)
        .agg(
            RECEITA=("RECEITA", "sum"),
            QTD_ARMAZENAGEM=("QTD_ARMAZENAGEM", "sum"),
            QUANTIDADE_VENDIDA=("QUANTIDADE_VENDIDA", "sum"),
            TRANSACOES=("RECEITA", "size"),
            LOJAS_ATIVAS=("COD_EMPRESA", "nunique"),
        )
        .reset_index()
    )
    grp["UNIVERSO"] = nome_universo
    grp["PRECO_MEDIO_ARMAZENAGEM"] = safe_div(grp["RECEITA"], grp["QTD_ARMAZENAGEM"])
    grp["TICKET_MEDIO_TRANSACAO"] = safe_div(grp["RECEITA"], grp["TRANSACOES"])
    grp["PARTICIPACAO_RECEITA_PCT"] = safe_div(grp["RECEITA"], total["RECEITA"]) * 100
    grp["PARTICIPACAO_QTD_PCT"] = safe_div(grp["QTD_ARMAZENAGEM"], total["QTD_ARMAZENAGEM"]) * 100
    grp["RANK_RECEITA_MENOR"] = grp["RECEITA"].rank(method="dense", ascending=True).astype(int)
    grp["RANK_QUANTIDADE_MENOR"] = grp["QTD_ARMAZENAGEM"].rank(method="dense", ascending=True).astype(int)

    por_receita = grp.sort_values(["RECEITA", "QTD_ARMAZENAGEM", "CODIGO"], ascending=[False, False, True]).copy()
    por_receita["RANK_RECEITA"] = np.arange(1, len(por_receita) + 1)
    por_receita["RECEITA_ACUM"] = por_receita["RECEITA"].cumsum()
    por_receita["RECEITA_ACUM_PCT"] = safe_div(por_receita["RECEITA_ACUM"], total["RECEITA"]) * 100
    por_receita["CURVA_ABC_RECEITA"] = por_receita["RECEITA_ACUM_PCT"].apply(classifica_abc)

    por_qtd = por_receita.sort_values(
        ["QTD_ARMAZENAGEM", "RECEITA", "CODIGO"], ascending=[False, False, True]
    ).copy()
    por_qtd["RANK_QUANTIDADE"] = np.arange(1, len(por_qtd) + 1)
    por_qtd["QTD_ACUM_ARMAZENAGEM"] = por_qtd["QTD_ARMAZENAGEM"].cumsum()
    por_qtd["QTD_ACUM_PCT"] = safe_div(por_qtd["QTD_ACUM_ARMAZENAGEM"], total["QTD_ARMAZENAGEM"]) * 100

    por_receita = por_receita.merge(
        por_qtd[["UNIVERSO", "CODIGO", "RANK_QUANTIDADE", "QTD_ACUM_ARMAZENAGEM", "QTD_ACUM_PCT"]],
        on=["UNIVERSO", "CODIGO"],
        how="left",
        validate="one_to_one",
    )
    ordem_cols = [
        "UNIVERSO",
        "CODIGO",
        "DESCRICAO",
        "NIVEL_1",
        "NIVEL_2",
        "NIVEL_3",
        "RECEITA",
        "QTD_ARMAZENAGEM",
        "QUANTIDADE_VENDIDA",
        "TRANSACOES",
        "LOJAS_ATIVAS",
        "PRECO_MEDIO_ARMAZENAGEM",
        "TICKET_MEDIO_TRANSACAO",
        "PARTICIPACAO_RECEITA_PCT",
        "PARTICIPACAO_QTD_PCT",
        "RANK_RECEITA",
        "RANK_RECEITA_MENOR",
        "RECEITA_ACUM",
        "RECEITA_ACUM_PCT",
        "CURVA_ABC_RECEITA",
        "RANK_QUANTIDADE",
        "RANK_QUANTIDADE_MENOR",
        "QTD_ACUM_ARMAZENAGEM",
        "QTD_ACUM_PCT",
    ]
    return por_receita[ordem_cols], por_qtd[ordem_cols]


def adicionar_variacao_anual(base: pd.DataFrame, annual: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    annual_wide = annual.pivot_table(index=keys, columns="ANO", values=METRICAS_BASE, fill_value=0, aggfunc="sum")
    annual_wide.columns = [f"{metrica}_{ano}" for metrica, ano in annual_wide.columns]
    annual_wide = annual_wide.reset_index()

    for metrica in METRICAS_BASE:
        for ano in [2024, 2025]:
            col = f"{metrica}_{ano}"
            if col not in annual_wide.columns:
                annual_wide[col] = 0.0
        annual_wide[f"DELTA_{metrica}_2025_VS_2024"] = annual_wide[f"{metrica}_2025"] - annual_wide[f"{metrica}_2024"]
        annual_wide[f"VAR_{metrica}_2025_VS_2024_PCT"] = (
            safe_div(annual_wide[f"DELTA_{metrica}_2025_VS_2024"], annual_wide[f"{metrica}_2024"]) * 100
        )

    return base.merge(annual_wide, on=keys, how="left", validate="one_to_one")


def agregar_dimensao(df: pd.DataFrame, nome_universo: str, keys: list[str], incluir_lojas: bool = False) -> pd.DataFrame:
    total = metricas_totais(df)
    agg_map = {
        "RECEITA": ("RECEITA", "sum"),
        "QTD_ARMAZENAGEM": ("QTD_ARMAZENAGEM", "sum"),
        "TRANSACOES": ("RECEITA", "size"),
        "SKUS_ATIVOS": ("CODIGO", "nunique"),
    }
    if incluir_lojas:
        agg_map["LOJAS_ATIVAS"] = ("COD_EMPRESA", "nunique")

    base = df.groupby(keys, dropna=False).agg(**agg_map).reset_index()
    base["UNIVERSO"] = nome_universo
    base["PRECO_MEDIO_ARMAZENAGEM"] = safe_div(base["RECEITA"], base["QTD_ARMAZENAGEM"])
    base["TICKET_MEDIO_TRANSACAO"] = safe_div(base["RECEITA"], base["TRANSACOES"])
    base["PARTICIPACAO_RECEITA_PCT"] = safe_div(base["RECEITA"], total["RECEITA"]) * 100
    base["PARTICIPACAO_QTD_PCT"] = safe_div(base["QTD_ARMAZENAGEM"], total["QTD_ARMAZENAGEM"]) * 100

    annual = (
        df.groupby(keys + ["ANO"], dropna=False)
        .agg(RECEITA=("RECEITA", "sum"), QTD_ARMAZENAGEM=("QTD_ARMAZENAGEM", "sum"), TRANSACOES=("RECEITA", "size"))
        .reset_index()
    )
    base = adicionar_variacao_anual(base, annual, keys)
    return base.sort_values(["UNIVERSO", "RECEITA"], ascending=[True, False]).reset_index(drop=True)


def agregar_lojas(df: pd.DataFrame, nome_universo: str) -> pd.DataFrame:
    lojas = agregar_dimensao(
        df,
        nome_universo,
        ["COD_EMPRESA", "CD_CIDADE", "CD_ESTADO", "TIPO_OPERACAO"],
        incluir_lojas=False,
    )
    lojas["FLAG_LOJA93"] = (lojas["COD_EMPRESA"] == LOJA_ATACADO).astype(int)
    return lojas.sort_values(["UNIVERSO", "RECEITA"], ascending=[True, False]).reset_index(drop=True)


def agregar_mensal(df: pd.DataFrame, nome_universo: str) -> pd.DataFrame:
    mensal = (
        df.groupby(["ANO_MES", "ANO", "MES"], dropna=False)
        .agg(
            RECEITA=("RECEITA", "sum"),
            QTD_ARMAZENAGEM=("QTD_ARMAZENAGEM", "sum"),
            TRANSACOES=("RECEITA", "size"),
            SKUS_ATIVOS=("CODIGO", "nunique"),
            LOJAS_ATIVAS=("COD_EMPRESA", "nunique"),
        )
        .reset_index()
        .sort_values(["ANO", "MES"])
        .reset_index(drop=True)
    )
    mensal["UNIVERSO"] = nome_universo
    mensal["PRECO_MEDIO_ARMAZENAGEM"] = safe_div(mensal["RECEITA"], mensal["QTD_ARMAZENAGEM"])
    mensal["TICKET_MEDIO_TRANSACAO"] = safe_div(mensal["RECEITA"], mensal["TRANSACOES"])

    for metrica in METRICAS_BASE:
        mensal[f"{metrica}_MOM_DELTA"] = mensal[metrica].diff()
        mensal[f"{metrica}_MOM_VAR_PCT"] = mensal[metrica].pct_change() * 100
        mensal[f"{metrica}_YOY_DELTA"] = mensal.groupby("MES")[metrica].diff()
        mensal[f"{metrica}_YOY_VAR_PCT"] = mensal.groupby("MES")[metrica].pct_change() * 100
        mensal[f"{metrica}_ACUM_ANO"] = mensal.groupby("ANO")[metrica].cumsum()

    return mensal


def identificar_picos_quedas(mensal: pd.DataFrame, top_n: int = 3) -> pd.DataFrame:
    registros = []
    for universo, df_univ in mensal.groupby("UNIVERSO", sort=False):
        for metrica in METRICAS_BASE:
            for base_var, nome_base in [("MOM", "mês contra mês anterior"), ("YOY", "mesmo mês do ano anterior")]:
                delta_col = f"{metrica}_{base_var}_DELTA"
                pct_col = f"{metrica}_{base_var}_VAR_PCT"
                candidatos = df_univ[df_univ[delta_col].notna()].copy()
                if candidatos.empty:
                    continue

                for tipo, ordenacao, label in [
                    ("PICO", False, "maiores altas"),
                    ("QUEDA", True, "maiores quedas"),
                ]:
                    extremos = candidatos.sort_values(delta_col, ascending=ordenacao).head(top_n)
                    for _, row in extremos.iterrows():
                        registros.append(
                            {
                                "UNIVERSO": universo,
                                "METRICA": metrica,
                                "TIPO_EVENTO": f"{tipo}_{base_var}",
                                "ANO_MES": row["ANO_MES"],
                                "ANO": int(row["ANO"]),
                                "MES": int(row["MES"]),
                                "VALOR": row[metrica],
                                "DELTA": row[delta_col],
                                "VAR_PCT": row[pct_col],
                                "CRITERIO": f"Top {top_n} {label} por delta absoluto em {nome_base}",
                            }
                        )
    return pd.DataFrame(registros)


def decompor_2025_vs_2024(df: pd.DataFrame, nome_universo: str, keys: list[str]) -> pd.DataFrame:
    annual = (
        df.groupby(keys + ["ANO"], dropna=False)
        .agg(RECEITA=("RECEITA", "sum"), QTD_ARMAZENAGEM=("QTD_ARMAZENAGEM", "sum"), TRANSACOES=("RECEITA", "size"))
        .reset_index()
    )
    wide = annual.pivot_table(index=keys, columns="ANO", values=METRICAS_BASE, fill_value=0, aggfunc="sum")
    wide.columns = [f"{metrica}_{ano}" for metrica, ano in wide.columns]
    wide = wide.reset_index()

    for metrica in METRICAS_BASE:
        for ano in [2024, 2025]:
            col = f"{metrica}_{ano}"
            if col not in wide.columns:
                wide[col] = 0.0
        wide[f"DELTA_{metrica}_2025_VS_2024"] = wide[f"{metrica}_2025"] - wide[f"{metrica}_2024"]
        wide[f"VAR_{metrica}_2025_VS_2024_PCT"] = safe_div(
            wide[f"DELTA_{metrica}_2025_VS_2024"], wide[f"{metrica}_2024"]
        ) * 100

    delta_total = float(wide["DELTA_RECEITA_2025_VS_2024"].sum())
    queda_bruta = float(wide.loc[wide["DELTA_RECEITA_2025_VS_2024"] < 0, "DELTA_RECEITA_2025_VS_2024"].abs().sum())
    wide["UNIVERSO"] = nome_universo
    wide["CONTRIBUICAO_VARIACAO_TOTAL_PCT"] = safe_div(wide["DELTA_RECEITA_2025_VS_2024"], delta_total) * 100
    wide["CONTRIBUICAO_QUEDA_BRUTA_PCT"] = np.where(
        wide["DELTA_RECEITA_2025_VS_2024"] < 0,
        safe_div(wide["DELTA_RECEITA_2025_VS_2024"].abs(), queda_bruta) * 100,
        0.0,
    )
    return wide.sort_values("DELTA_RECEITA_2025_VS_2024").reset_index(drop=True)


def diagnostico_captura_mensal(vendas: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Diagnóstico da queda de 2025: mercado (retração) ou captura (truncamento)?

    A receita e o nº de linhas caem quase monotonicamente ao longo de 2025. Isso
    tanto pode ser retração real quanto **truncamento de captura** (extração/carga
    incompleta dos meses finais). Para separar as hipóteses sem afirmar causa, esta
    função materializa, por mês (24 meses, rede completa):
      - nº de lojas ativas, nº de SKUs distintos, nº de linhas e receita;
      - e a mesma quebra por loja × mês.

    Leitura: se a queda é **homogênea** entre lojas (todas encolhem juntas), pesa
    para retração de mercado; se **lojas somem** da base em meses de 2025 (linhas
    caem a zero loja a loja), pesa para truncamento de captura.
    """
    mensal = (
        vendas.groupby(["ANO_MES", "ANO", "MES"], dropna=False)
        .agg(
            LOJAS_ATIVAS=("COD_EMPRESA", "nunique"),
            SKUS_DISTINTOS=("CODIGO", "nunique"),
            LINHAS=("RECEITA", "size"),
            RECEITA=("RECEITA", "sum"),
        )
        .reset_index()
        .sort_values(["ANO", "MES"])
        .reset_index(drop=True)
    )
    mensal["RECEITA_MEDIA_LINHA"] = safe_div(mensal["RECEITA"], mensal["LINHAS"])

    lojas_mensal = (
        vendas.groupby(["COD_EMPRESA", "CD_CIDADE", "CD_ESTADO", "TIPO_OPERACAO", "ANO_MES", "ANO", "MES"], dropna=False)
        .agg(
            LINHAS=("RECEITA", "size"),
            SKUS_DISTINTOS=("CODIGO", "nunique"),
            RECEITA=("RECEITA", "sum"),
        )
        .reset_index()
        .sort_values(["COD_EMPRESA", "ANO", "MES"])
        .reset_index(drop=True)
    )
    return mensal, lojas_mensal


def calcular_impacto_loja93(vendas: pd.DataFrame) -> pd.DataFrame:
    rec_total = vendas["RECEITA"].sum()
    qtd_total = vendas["QTD_ARMAZENAGEM"].sum()
    tx_total = len(vendas)

    linhas = []
    for label, filtro in [
        ("REDE_COMPLETA", vendas.index == vendas.index),
        ("LOJA_93_ATACADO_B2B", vendas["COD_EMPRESA"] == LOJA_ATACADO),
        ("REDE_FISICA_SEM_LOJA93", vendas["COD_EMPRESA"] != LOJA_ATACADO),
    ]:
        base = vendas.loc[filtro]
        linhas.append(
            {
                "SEGMENTO": label,
                "RECEITA": base["RECEITA"].sum(),
                "QTD_ARMAZENAGEM": base["QTD_ARMAZENAGEM"].sum(),
                "TRANSACOES": len(base),
                "SKUS_ATIVOS": base["CODIGO"].nunique(),
                "LOJAS_ATIVAS": base["COD_EMPRESA"].nunique(),
                "TICKET_MEDIO_TRANSACAO": base["RECEITA"].sum() / len(base),
                "PRECO_MEDIO_ARMAZENAGEM": base["RECEITA"].sum() / base["QTD_ARMAZENAGEM"].sum(),
                "PARTICIPACAO_RECEITA_REDE_COMPLETA_PCT": base["RECEITA"].sum() / rec_total * 100,
                "PARTICIPACAO_QTD_REDE_COMPLETA_PCT": base["QTD_ARMAZENAGEM"].sum() / qtd_total * 100,
                "PARTICIPACAO_TRANSACOES_REDE_COMPLETA_PCT": len(base) / tx_total * 100,
            }
        )
    return pd.DataFrame(linhas)


def assert_close(nome: str, observado: float, esperado: float, validacoes: list[dict], tolerancia: float = 1e-5) -> None:
    diff = float(observado - esperado)
    status = "OK" if abs(diff) <= tolerancia else "FALHA"
    validacoes.append(
        {
            "VALIDACAO": nome,
            "OBSERVADO": observado,
            "ESPERADO": esperado,
            "DIFERENCA": diff,
            "STATUS": status,
        }
    )
    if status != "OK":
        raise AssertionError(f"{nome}: observado={observado}, esperado={esperado}, diff={diff}")


def assert_true(nome: str, condicao: bool, validacoes: list[dict]) -> None:
    status = "OK" if bool(condicao) else "FALHA"
    validacoes.append(
        {
            "VALIDACAO": nome,
            "OBSERVADO": int(bool(condicao)),
            "ESPERADO": 1,
            "DIFERENCA": int(bool(condicao)) - 1,
            "STATUS": status,
        }
    )
    if status != "OK":
        raise AssertionError(nome)


def validar_totais(
    bases: dict[str, pd.DataFrame],
    ranking_receita: pd.DataFrame,
    ranking_quantidade: pd.DataFrame,
    curva_abc: pd.DataFrame,
    categorias_n1: pd.DataFrame,
    lojas: pd.DataFrame,
    mensal: pd.DataFrame,
    decomposicao_categorias: pd.DataFrame,
    decomposicao_lojas: pd.DataFrame,
    impacto_loja93: pd.DataFrame,
    nulos_dimensoes: dict[str, int],
) -> pd.DataFrame:
    validacoes: list[dict] = []

    for col, nulos in nulos_dimensoes.items():
        assert_close(f"Dimensão sem nulos após Etapa 1: {col}", nulos, 0, validacoes, tolerancia=0)

    for universo, df_univ in bases.items():
        totais = metricas_totais(df_univ)
        filtros = {
            "ranking_receita": ranking_receita[ranking_receita["UNIVERSO"] == universo],
            "ranking_quantidade": ranking_quantidade[ranking_quantidade["UNIVERSO"] == universo],
            "curva_abc": curva_abc[curva_abc["UNIVERSO"] == universo],
            "categorias_n1": categorias_n1[categorias_n1["UNIVERSO"] == universo],
            "lojas": lojas[lojas["UNIVERSO"] == universo],
            "mensal": mensal[mensal["UNIVERSO"] == universo],
        }

        for nome_base, base in filtros.items():
            assert_close(f"{nome_base} soma RECEITA - {universo}", base["RECEITA"].sum(), totais["RECEITA"], validacoes)
            assert_close(
                f"{nome_base} soma QTD_ARMAZENAGEM - {universo}",
                base["QTD_ARMAZENAGEM"].sum(),
                totais["QTD_ARMAZENAGEM"],
                validacoes,
            )
            assert_close(f"{nome_base} soma TRANSACOES - {universo}", base["TRANSACOES"].sum(), totais["TRANSACOES"], validacoes)

        assert_close(
            f"Produtos ativos no ranking - {universo}",
            ranking_receita[ranking_receita["UNIVERSO"] == universo]["CODIGO"].nunique(),
            totais["SKUS_ATIVOS"],
            validacoes,
            tolerancia=0,
        )
        assert_true(
            f"Ranking receita sem duplicidade de produto - {universo}",
            not ranking_receita[ranking_receita["UNIVERSO"] == universo]["CODIGO"].duplicated().any(),
            validacoes,
        )
        assert_true(
            f"Ranking quantidade sem duplicidade de produto - {universo}",
            not ranking_quantidade[ranking_quantidade["UNIVERSO"] == universo]["CODIGO"].duplicated().any(),
            validacoes,
        )
        assert_true(
            f"Serie mensal com 24 meses - {universo}",
            mensal[mensal["UNIVERSO"] == universo]["ANO_MES"].nunique() == 24,
            validacoes,
        )

        abc_univ = curva_abc[curva_abc["UNIVERSO"] == universo]
        assert_close(
            f"Curva ABC soma 100% receita - {universo}",
            abc_univ["PARTICIPACAO_RECEITA_PCT"].sum(),
            100.0,
            validacoes,
            tolerancia=1e-4,
        )

        receita_2024 = df_univ.loc[df_univ["ANO"] == 2024, "RECEITA"].sum()
        receita_2025 = df_univ.loc[df_univ["ANO"] == 2025, "RECEITA"].sum()
        delta_receita = receita_2025 - receita_2024
        assert_close(
            f"Decomposicao categorias soma delta receita - {universo}",
            decomposicao_categorias[decomposicao_categorias["UNIVERSO"] == universo]["DELTA_RECEITA_2025_VS_2024"].sum(),
            delta_receita,
            validacoes,
        )
        assert_close(
            f"Decomposicao lojas soma delta receita - {universo}",
            decomposicao_lojas[decomposicao_lojas["UNIVERSO"] == universo]["DELTA_RECEITA_2025_VS_2024"].sum(),
            delta_receita,
            validacoes,
        )

    n_categorias_n1 = bases[UNIVERSO_COMPLETO]["NIVEL_1"].nunique()
    assert_close("Rede completa contém 23 categorias NIVEL_1", n_categorias_n1, 23, validacoes, tolerancia=0)

    impacto = impacto_loja93.set_index("SEGMENTO")
    for metrica in ["RECEITA", "QTD_ARMAZENAGEM", "TRANSACOES"]:
        assert_close(
            f"Impacto Loja 93 + rede fisica fecha {metrica}",
            impacto.loc["LOJA_93_ATACADO_B2B", metrica] + impacto.loc[UNIVERSO_FISICO, metrica],
            impacto.loc[UNIVERSO_COMPLETO, metrica],
            validacoes,
        )

    return pd.DataFrame(validacoes)


def gerar_notas_metodologicas() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "TEMA": "Fonte",
                "DECISAO": "Todos os cálculos partem de data/processed/vendas_tratadas.parquet.",
                "LIMITACAO": "Não utiliza dados brutos nem fontes externas nesta etapa.",
                "RECOMENDACAO": "Manter camada processed versionada e reexecutável; registrar hash/data de geração em ciclos futuros.",
            },
            {
                "TEMA": "Quantidade",
                "DECISAO": "Volumes analisados em QTD_ARMAZENAGEM.",
                "LIMITACAO": "Quantidade vendida original pode estar em unidade comercial diferente.",
                "RECOMENDACAO": "Preservar as duas visões nos outputs: unidade comercial original e unidade normalizada de armazenagem.",
            },
            {
                "TEMA": "Transações",
                "DECISAO": "TRANSACOES = contagem de linhas de fato_vendas.",
                "LIMITACAO": "Não há identificador de cupom/pedido/nota; ticket médio é proxy por linha de venda.",
                "RECOMENDACAO": "Incluir identificador único de cupom/pedido/nota e número do item na base de vendas para medir transações reais, itens por cupom e ticket médio verdadeiro.",
            },
            {
                "TEMA": "Loja 93",
                "DECISAO": "Visões sempre separadas entre rede completa e rede física sem Loja 93.",
                "LIMITACAO": "Operação B2B/atacado distorce médias, rankings e sazonalidade da rede física.",
                "RECOMENDACAO": "Adicionar uma dimensão formal de canal/operação (varejo físico, atacado/B2B, e-commerce etc.) em vez de depender apenas do código da loja.",
            },
            {
                "TEMA": "Curva ABC",
                "DECISAO": "Classificação por receita acumulada: A até 80%, B até 95%, C restante.",
                "LIMITACAO": "O primeiro item que ultrapassa o corte entra na classe seguinte; por isso A pode ficar ligeiramente abaixo de 80%.",
                "RECOMENDACAO": "Documentar regra de corte no dicionário de métricas e, se necessário, comparar com ABC por margem quando custo confiável estiver disponível.",
            },
            {
                "TEMA": "Queda 2025",
                "DECISAO": "Comparação de anos completos presentes na base: 2025 vs 2024. Tratada como hipótese (retração de mercado × truncamento de captura), não como achado fechado.",
                "LIMITACAO": "Análise descritiva; não atribui causa sem dado adicional. Se for truncamento de captura, contamina VENDA_MEDIA_MES e a demanda das Etapas 6/7.",
                "RECOMENDACAO": "Usar diagnostico_captura_mensal.csv e diagnostico_captura_lojas_mensal.csv para testar homogeneidade entre lojas vs lojas sumindo; cruzar com calendário comercial, ruptura e fechamento de lojas antes de tratar a queda como definitiva.",
            },
        ]
    )


def gerar_recomendacoes_melhoria() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "PRIORIDADE": "ALTA",
                "TEMA": "Identificador de transação",
                "PROBLEMA": "A base de vendas não possui id de cupom/pedido/nota.",
                "RISCO_ANALITICO": "Contar linhas como transações pode superestimar a quantidade de compras e distorcer ticket médio, itens por compra e análise de cesta.",
                "RECOMENDACAO": "Incluir id_transacao, numero_item_transacao, origem/canal e, quando aplicável, id_cliente anonimizado.",
                "IMPACTO_ESPERADO": "Permitir ticket médio real, frequência de compra, cesta de produtos e análises de retenção/canal.",
            },
            {
                "PRIORIDADE": "ALTA",
                "TEMA": "Canal da Loja 93",
                "PROBLEMA": "A Loja 93 é identificada como outlier B2B/atacado por comportamento, não por uma dimensão formal de canal.",
                "RISCO_ANALITICO": "Misturar atacado e varejo físico distorce rankings, sazonalidade, preço médio e cobertura.",
                "RECOMENDACAO": "Criar dimensão de canal/operação e manter flags de segmentação documentadas no modelo analítico.",
                "IMPACTO_ESPERADO": "Comparações mais justas entre lojas e decisões comerciais separadas para varejo e atacado.",
            },
            {
                "PRIORIDADE": "ALTA",
                "TEMA": "Movimentações de estoque",
                "PROBLEMA": "Grande parte dos SKUs vende sem compra registrada no período.",
                "RISCO_ANALITICO": "Cobertura e ruptura ficam conservadoras e podem refletir ausência de transferências/ajustes na base, não indisponibilidade física real.",
                "RECOMENDACAO": "Incluir transferências entre lojas, ajustes de inventário e saldo inicial por data de corte auditável.",
                "IMPACTO_ESPERADO": "Melhor estimativa de disponibilidade real e plano de reposição menos enviesado.",
            },
            {
                "PRIORIDADE": "MÉDIA",
                "TEMA": "Causa da queda de 2025",
                "PROBLEMA": "A queda é observada nos dados, mas a base não contém variáveis causais suficientes.",
                "RISCO_ANALITICO": "Atribuir causa a demanda, preço, ruptura ou captura sem evidência adicional.",
                "RECOMENDACAO": "Adicionar calendário promocional, mudanças operacionais, indicadores de ruptura, campanhas e contexto de mercado.",
                "IMPACTO_ESPERADO": "Separar efeito de demanda, operação, preço e disponibilidade.",
            },
            {
                "PRIORIDADE": "MÉDIA",
                "TEMA": "Dicionário de métricas",
                "PROBLEMA": "Métricas como transações, ticket e preço médio podem ser interpretadas de forma diferente por avaliadores/áreas.",
                "RISCO_ANALITICO": "Uso indevido de indicadores proxy em decisões executivas.",
                "RECOMENDACAO": "Criar dicionário de métricas com fórmula, granularidade, limitações e owner de cada indicador.",
                "IMPACTO_ESPERADO": "Maior governança e menor ambiguidade nas próximas etapas do case.",
            },
        ]
    )


def salvar_csv(df: pd.DataFrame, nome: str) -> None:
    df.to_csv(OUT / nome, index=False, encoding="utf-8-sig", float_format="%.6f")


def gerar_resumo(
    vendas: pd.DataFrame,
    impacto_loja93: pd.DataFrame,
    ranking_receita: pd.DataFrame,
    ranking_quantidade: pd.DataFrame,
    categorias_n1: pd.DataFrame,
    lojas: pd.DataFrame,
    mensal: pd.DataFrame,
    decomposicao_categorias: pd.DataFrame,
    decomposicao_lojas: pd.DataFrame,
    validacoes: pd.DataFrame,
) -> str:
    totais_full = metricas_totais(vendas)
    vendas_fisica = vendas[vendas["COD_EMPRESA"] != LOJA_ATACADO]
    totais_fisica = metricas_totais(vendas_fisica)

    loja93 = impacto_loja93[impacto_loja93["SEGMENTO"] == "LOJA_93_ATACADO_B2B"].iloc[0]

    yoy_full = (
        vendas.groupby("ANO")["RECEITA"].sum().reindex([2024, 2025], fill_value=0)
    )
    yoy_fisica = (
        vendas_fisica.groupby("ANO")["RECEITA"].sum().reindex([2024, 2025], fill_value=0)
    )
    var_full = (yoy_full.loc[2025] - yoy_full.loc[2024]) / yoy_full.loc[2024] * 100
    var_fisica = (yoy_fisica.loc[2025] - yoy_fisica.loc[2024]) / yoy_fisica.loc[2024] * 100

    top_prod_full = ranking_receita[ranking_receita["UNIVERSO"] == UNIVERSO_COMPLETO].iloc[0]
    top_prod_fisica = ranking_receita[ranking_receita["UNIVERSO"] == UNIVERSO_FISICO].iloc[0]
    top_qtd_full = ranking_quantidade[ranking_quantidade["UNIVERSO"] == UNIVERSO_COMPLETO].iloc[0]
    menor_rec_full = ranking_receita[ranking_receita["UNIVERSO"] == UNIVERSO_COMPLETO].sort_values("RECEITA").iloc[0]
    menor_qtd_full = (
        ranking_quantidade[ranking_quantidade["UNIVERSO"] == UNIVERSO_COMPLETO]
        .sort_values("QTD_ARMAZENAGEM")
        .iloc[0]
    )

    abc = (
        ranking_receita.groupby(["UNIVERSO", "CURVA_ABC_RECEITA"])
        .agg(SKUS=("CODIGO", "nunique"), RECEITA=("RECEITA", "sum"))
        .reset_index()
    )
    abc_full_a = abc[(abc["UNIVERSO"] == UNIVERSO_COMPLETO) & (abc["CURVA_ABC_RECEITA"] == "A")].iloc[0]
    abc_fisica_a = abc[(abc["UNIVERSO"] == UNIVERSO_FISICO) & (abc["CURVA_ABC_RECEITA"] == "A")].iloc[0]

    top_cat_full = categorias_n1[categorias_n1["UNIVERSO"] == UNIVERSO_COMPLETO].iloc[0]
    top_cat_fisica = categorias_n1[categorias_n1["UNIVERSO"] == UNIVERSO_FISICO].iloc[0]

    top_loja_full = lojas[lojas["UNIVERSO"] == UNIVERSO_COMPLETO].iloc[0]
    top_loja_fisica = lojas[lojas["UNIVERSO"] == UNIVERSO_FISICO].iloc[0]

    pico_full = mensal[mensal["UNIVERSO"] == UNIVERSO_COMPLETO].sort_values("RECEITA", ascending=False).iloc[0]
    menor_full = mensal[mensal["UNIVERSO"] == UNIVERSO_COMPLETO].sort_values("RECEITA", ascending=True).iloc[0]

    queda_cat_full = decomposicao_categorias[
        decomposicao_categorias["UNIVERSO"] == UNIVERSO_COMPLETO
    ].sort_values("DELTA_RECEITA_2025_VS_2024").iloc[0]
    queda_loja_full = decomposicao_lojas[
        decomposicao_lojas["UNIVERSO"] == UNIVERSO_COMPLETO
    ].sort_values("DELTA_RECEITA_2025_VS_2024").iloc[0]

    resumo = f"""# Etapa 3 — Análise de Desempenho de Vendas

## Escopo executado

- Rankings de produtos por receita e por quantidade em unidade de armazenagem, com participação, acumulado e curva ABC por receita.
- Visões separadas para rede completa e rede física sem Loja 93.
- Agregações por `NIVEL_1`, `NIVEL_2`, `NIVEL_3`, loja, cidade/estado e mês.
- Comparação 2024 vs 2025 e decomposição da queda por categoria e por loja.

## Principais achados

- A rede completa soma {fmt_brl(totais_full["RECEITA"] / 1e6)} em receita, {fmt_num(totais_full["TRANSACOES"])} linhas de venda (proxy de transações) e {fmt_num(totais_full["SKUS_ATIVOS"])} SKUs ativos.
- A Loja 93 responde por {fmt_pct(loja93["PARTICIPACAO_RECEITA_REDE_COMPLETA_PCT"])} da receita, mas por {fmt_pct(loja93["PARTICIPACAO_TRANSACOES_REDE_COMPLETA_PCT"])} das linhas de venda. A receita média por linha dela é {fmt_brl_valor(loja93["TICKET_MEDIO_TRANSACAO"])}, sinalizando operação fora do padrão da rede física.
- Sem a Loja 93, a rede física soma {fmt_brl(totais_fisica["RECEITA"] / 1e6)} e {fmt_num(totais_fisica["TRANSACOES"])} linhas de venda.
- Produto líder por receita na rede completa: `{int(top_prod_full["CODIGO"])}` — {top_prod_full["DESCRICAO"]}, com {fmt_brl(top_prod_full["RECEITA"] / 1e6)} ({fmt_pct(top_prod_full["PARTICIPACAO_RECEITA_PCT"])} do universo).
- Produto líder por receita na rede física: `{int(top_prod_fisica["CODIGO"])}` — {top_prod_fisica["DESCRICAO"]}, com {fmt_brl(top_prod_fisica["RECEITA"] / 1e6)} ({fmt_pct(top_prod_fisica["PARTICIPACAO_RECEITA_PCT"])} do universo).
- Produto líder por quantidade na rede completa: `{int(top_qtd_full["CODIGO"])}` — {top_qtd_full["DESCRICAO"]}, com {fmt_num(top_qtd_full["QTD_ARMAZENAGEM"])} unidades de armazenagem.
- A cauda dos rankings também é auditável: `RANK_RECEITA_MENOR` e `RANK_QUANTIDADE_MENOR` identificam os produtos de menor venda. Na rede completa, a menor receita é do produto `{int(menor_rec_full["CODIGO"])}` ({fmt_brl_valor(menor_rec_full["RECEITA"])}) e a menor quantidade é do produto `{int(menor_qtd_full["CODIGO"])}` ({fmt_decimal(menor_qtd_full["QTD_ARMAZENAGEM"])} unidade de armazenagem).
- A curva A concentra {fmt_pct(abc_full_a["RECEITA"] / totais_full["RECEITA"] * 100)} da receita em {fmt_num(abc_full_a["SKUS"])} SKUs na rede completa; sem a Loja 93, concentra {fmt_pct(abc_fisica_a["RECEITA"] / totais_fisica["RECEITA"] * 100)} em {fmt_num(abc_fisica_a["SKUS"])} SKUs.
- Foram observadas {vendas["NIVEL_1"].nunique()} categorias de nível 1. A maior categoria na rede completa é `{top_cat_full["NIVEL_1"]}`, com {fmt_brl(top_cat_full["RECEITA"] / 1e6)}; na rede física, `{top_cat_fisica["NIVEL_1"]}`, com {fmt_brl(top_cat_fisica["RECEITA"] / 1e6)}.
- A loja de maior receita na rede completa é {int(top_loja_full["COD_EMPRESA"])} ({top_loja_full["CD_CIDADE"]}-{top_loja_full["CD_ESTADO"]}), com {fmt_brl(top_loja_full["RECEITA"] / 1e6)}. Sem a Loja 93, a líder é {int(top_loja_fisica["COD_EMPRESA"])} ({top_loja_fisica["CD_CIDADE"]}-{top_loja_fisica["CD_ESTADO"]}), com {fmt_brl(top_loja_fisica["RECEITA"] / 1e6)}.
- **Queda de 2025 — hipótese a validar, não achado fechado.** A receita recua {fmt_pct(var_full)} na rede completa e {fmt_pct(var_fisica)} na rede física (2025 vs 2024), de forma quase monotônica ao longo de 2025, com o nº de linhas caindo na mesma proporção. Isso é assinatura possível de **truncamento de captura** (extração/carga incompleta dos meses finais), não necessariamente retração de mercado. Ver `diagnostico_captura_mensal.csv` e `diagnostico_captura_lojas_mensal.csv`: se a queda for homogênea entre lojas, pesa para mercado; se lojas "somem" da base ao longo de 2025, pesa para captura. **Impacto downstream:** essa mesma base alimenta `VENDA_MEDIA_MES` e a projeção de compras das Etapas 6/7 — a incerteza se propaga para a demanda projetada, que deve ser lida como ordem de prioridade, não previsão fechada.
- O maior mês por receita na rede completa foi {pico_full["ANO_MES"]}, com {fmt_brl(pico_full["RECEITA"] / 1e6)}; o menor foi {menor_full["ANO_MES"]}, com {fmt_brl(menor_full["RECEITA"] / 1e6)}.
- A maior contribuição bruta para a queda de receita em 2025, por categoria na rede completa, veio de `{queda_cat_full["NIVEL_1"]}` ({fmt_brl(queda_cat_full["DELTA_RECEITA_2025_VS_2024"] / 1e6)}). Por loja, veio da loja {int(queda_loja_full["COD_EMPRESA"])} ({queda_loja_full["CD_CIDADE"]}-{queda_loja_full["CD_ESTADO"]}), com {fmt_brl(queda_loja_full["DELTA_RECEITA_2025_VS_2024"] / 1e6)}.

## Limitações e cuidados metodológicos

- A análise é descritiva: variações e picos não são atribuídos a preço, demanda, ruptura ou captura de dados sem evidência adicional.
- `TRANSACOES` representa linhas de venda, não cupons únicos. A base processada não possui id de cupom, pedido ou nota. Isto está documentado como limitação relevante e recomendação de melhoria em `notas_metodologicas.csv` e `recomendacoes_melhoria.csv`.
- Ticket médio foi mantido como proxy de receita por linha de venda; preço médio foi calculado como receita por unidade de armazenagem.
- A Loja 93 é operação B2B/atacado e distorce médias, rankings e sazonalidade. Por isso todos os outputs trazem `UNIVERSO`.
- A queda de 2025 é comparada contra 2024 completo, usando apenas datas presentes em `vendas_tratadas.parquet`. Ela é tratada como **hipótese a confirmar** (retração de mercado × truncamento de captura), com o diagnóstico mensal/por loja em `diagnostico_captura_mensal.csv` e `diagnostico_captura_lojas_mensal.csv` para instruir a decisão antes de tratar o número como definitivo.
- Recomendações de melhoria foram registradas para pontos que limitam a leitura profissional dos dados: id de transação, canal formal da Loja 93, movimentações de estoque, variáveis causais da queda e dicionário de métricas.

## Validações

- {len(validacoes)} validações executadas, todas com status `{validacoes["STATUS"].unique()[0]}`.
- Somas de receita, quantidade e linhas de venda dos rankings, categorias, lojas e meses batem com os totais de cada universo.
- As decomposições de queda por categoria e por loja fecham com o delta anual 2025 vs 2024.
- A soma Loja 93 + rede física sem Loja 93 fecha com a rede completa.
- As dimensões críticas (`NIVEL_1`, `NIVEL_2`, `NIVEL_3`, cidade e estado) não possuem nulos na base processada usada na análise.

## Como executar

```bash
cd notebooks
python etapa3_desempenho_vendas.py
```

Os arquivos auditáveis são gravados em `outputs/etapa3/`.
"""
    return resumo


def main() -> None:
    print("Carregando vendas tratadas...")
    vendas_raw = load_vendas(excluir_atacado=False)
    vendas, nulos_dimensoes = preparar_vendas(vendas_raw)
    bases = universos(vendas)

    print("\n--- Totais por universo ---")
    for nome, df_univ in bases.items():
        totais = metricas_totais(df_univ)
        print(
            f"{nome:<24} | Receita: R$ {totais['RECEITA']/1e6:>7.1f}M | "
            f"Qtd arm.: {totais['QTD_ARMAZENAGEM']:>10,.0f} | "
            f"Linhas venda: {totais['TRANSACOES']:>9,} | SKUs: {totais['SKUS_ATIVOS']:>4,}"
        )

    ranking_receita_lst = []
    ranking_quantidade_lst = []
    categorias_n1_lst = []
    categorias_n2_lst = []
    categorias_n3_lst = []
    lojas_lst = []
    regioes_lst = []
    mensal_lst = []
    decomp_cat_lst = []
    decomp_loja_lst = []

    print("\nCalculando rankings, hierarquias, lojas e sazonalidade...")
    for nome, df_univ in bases.items():
        prod_receita, prod_qtd = agregar_produtos(df_univ, nome)
        ranking_receita_lst.append(prod_receita)
        ranking_quantidade_lst.append(prod_qtd)

        categorias_n1_lst.append(agregar_dimensao(df_univ, nome, ["NIVEL_1"]))
        categorias_n2_lst.append(agregar_dimensao(df_univ, nome, ["NIVEL_1", "NIVEL_2"]))
        categorias_n3_lst.append(agregar_dimensao(df_univ, nome, ["NIVEL_1", "NIVEL_2", "NIVEL_3"]))
        lojas_lst.append(agregar_lojas(df_univ, nome))
        regioes_lst.append(agregar_dimensao(df_univ, nome, ["CD_ESTADO", "CD_CIDADE"], incluir_lojas=True))
        mensal_lst.append(agregar_mensal(df_univ, nome))
        decomp_cat_lst.append(decompor_2025_vs_2024(df_univ, nome, ["NIVEL_1"]))
        decomp_loja_lst.append(decompor_2025_vs_2024(df_univ, nome, ["COD_EMPRESA", "CD_CIDADE", "CD_ESTADO", "TIPO_OPERACAO"]))

    ranking_receita = pd.concat(ranking_receita_lst, ignore_index=True)
    ranking_quantidade = pd.concat(ranking_quantidade_lst, ignore_index=True)
    curva_abc = ranking_receita.copy()
    categorias_n1 = pd.concat(categorias_n1_lst, ignore_index=True)
    categorias_n2 = pd.concat(categorias_n2_lst, ignore_index=True)
    categorias_n3 = pd.concat(categorias_n3_lst, ignore_index=True)
    lojas = pd.concat(lojas_lst, ignore_index=True)
    regioes = pd.concat(regioes_lst, ignore_index=True)
    mensal = pd.concat(mensal_lst, ignore_index=True)
    picos_quedas = identificar_picos_quedas(mensal)
    decomposicao_categorias = pd.concat(decomp_cat_lst, ignore_index=True)
    decomposicao_lojas = pd.concat(decomp_loja_lst, ignore_index=True)
    diag_captura_mensal, diag_captura_lojas = diagnostico_captura_mensal(vendas)
    impacto_loja93 = calcular_impacto_loja93(vendas)
    notas_metodologicas = gerar_notas_metodologicas()
    recomendacoes_melhoria = gerar_recomendacoes_melhoria()

    print("Validando consistência dos totais...")
    validacoes = validar_totais(
        bases,
        ranking_receita,
        ranking_quantidade,
        curva_abc,
        categorias_n1,
        lojas,
        mensal,
        decomposicao_categorias,
        decomposicao_lojas,
        impacto_loja93,
        nulos_dimensoes,
    )

    print("Salvando arquivos auditáveis...")
    salvar_csv(ranking_receita, "ranking_produtos_receita.csv")
    salvar_csv(ranking_quantidade, "ranking_produtos_quantidade.csv")
    salvar_csv(curva_abc, "curva_abc_produtos.csv")
    salvar_csv(categorias_n1, "desempenho_categorias_n1.csv")
    salvar_csv(categorias_n2, "desempenho_categorias_n2.csv")
    salvar_csv(categorias_n3, "desempenho_categorias_n3.csv")
    salvar_csv(lojas, "desempenho_lojas.csv")
    salvar_csv(regioes, "desempenho_regioes.csv")
    salvar_csv(mensal, "vendas_mensais.csv")
    salvar_csv(picos_quedas, "sazonalidade_picos_quedas.csv")
    salvar_csv(decomposicao_categorias, "decomposicao_queda_2025_categorias.csv")
    salvar_csv(decomposicao_lojas, "decomposicao_queda_2025_lojas.csv")
    salvar_csv(diag_captura_mensal, "diagnostico_captura_mensal.csv")
    salvar_csv(diag_captura_lojas, "diagnostico_captura_lojas_mensal.csv")
    salvar_csv(impacto_loja93, "impacto_loja93.csv")
    salvar_csv(notas_metodologicas, "notas_metodologicas.csv")
    salvar_csv(recomendacoes_melhoria, "recomendacoes_melhoria.csv")
    salvar_csv(validacoes, "validacoes_etapa3.csv")

    resumo = gerar_resumo(
        vendas,
        impacto_loja93,
        ranking_receita,
        ranking_quantidade,
        categorias_n1,
        lojas,
        mensal,
        decomposicao_categorias,
        decomposicao_lojas,
        validacoes,
    )
    (OUT / "resumo_etapa3.md").write_text(resumo, encoding="utf-8")

    print("\n--- Destaques ---")
    print(f"Loja 93: {impacto_loja93.loc[impacto_loja93['SEGMENTO']=='LOJA_93_ATACADO_B2B', 'PARTICIPACAO_RECEITA_REDE_COMPLETA_PCT'].iloc[0]:.1f}% da receita da rede completa")
    print(f"Categorias NIVEL_1 na rede completa: {vendas['NIVEL_1'].nunique()}")
    print(f"Validações OK: {(validacoes['STATUS'] == 'OK').sum()}/{len(validacoes)}")

    print("\n[OK] Arquivos salvos em outputs/etapa3/")
    for path in sorted(OUT.glob("*")):
        print(f"  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
