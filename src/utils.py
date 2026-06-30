"""
utils.py — Funções compartilhadas entre notebooks do case.

Carrega bases tratadas, aplica convenções de filtro (ex: excluir loja 93)
e expõe constantes usadas em múltiplas etapas.
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ── Caminhos ──────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parents[1]
PROCESSED  = ROOT / "data" / "processed"
OUTPUTS    = ROOT / "outputs"

# ── Constantes de negócio ─────────────────────────────────────────────────────
LOJA_ATACADO   = 93          # Alhandra-PB: operação B2B/atacado, tratada separadamente
PERIODO_INICIO = "2024-01-01"
PERIODO_FIM    = "2025-12-31"

# ── Loaders ───────────────────────────────────────────────────────────────────

def load_vendas(excluir_atacado: bool = True) -> pd.DataFrame:
    """
    Carrega fato_vendas tratada.

    Parameters
    ----------
    excluir_atacado : bool
        Se True (padrão), remove loja 93 (Alhandra) da base.
        Use False apenas quando analisar a rede completa explicitamente.

    Returns
    -------
    pd.DataFrame com colunas: CODIGO, COD_EMPRESA, DATA_VENDA, QUANTIDADE_VENDIDA,
        CONVERSAO_VENDA_PARA_ARMAZENAGEM, PRECO_UNIT_MEDIO, EMBALAGEM, UNIDADE_DA_VENDA,
        RECEITA, QTD_ARMAZENAGEM, ANO_MES, ANO, MES, FLAG_LOJA93,
        NIVEL_1, NIVEL_2, NIVEL_3, UNIDADE_ESTOQUE, CD_VOLTAGEM,
        CD_CIDADE, CD_ESTADO
    """
    df = pd.read_parquet(PROCESSED / "vendas_tratadas.parquet")
    df["DATA_VENDA"] = pd.to_datetime(df["DATA_VENDA"])
    # Recalcula RECEITA a partir de float64 para garantir precisão
    df["RECEITA"] = df["QUANTIDADE_VENDIDA"].astype(float) * df["PRECO_UNIT_MEDIO"].astype(float)
    df["QTD_ARMAZENAGEM"] = df["QUANTIDADE_VENDIDA"].astype(float) * df["CONVERSAO_VENDA_PARA_ARMAZENAGEM"].astype(float)
    if excluir_atacado:
        df = df[df["COD_EMPRESA"] != LOJA_ATACADO].copy()
    return df


def load_compras() -> pd.DataFrame:
    """Carrega fato_compras tratada."""
    df = pd.read_parquet(PROCESSED / "compras_tratadas.parquet")
    df["DATA_ENTRADA"] = pd.to_datetime(df["DATA_ENTRADA"])
    return df


def load_estoque_inicial() -> pd.DataFrame:
    """Carrega posição inicial de estoque (nulos → 0 já aplicado)."""
    return pd.read_parquet(PROCESSED / "estoque_inicial_tratado.parquet")


def load_dim_produto() -> pd.DataFrame:
    """Carrega dimensão de produtos com conversão em float já aplicada."""
    return pd.read_parquet(PROCESSED / "dim_produto_tratada.parquet")


def load_dim_lojas() -> pd.DataFrame:
    """Carrega dimensão de lojas."""
    return pd.read_parquet(PROCESSED / "dim_lojas.parquet")


def load_dim_precos() -> pd.DataFrame:
    """Carrega tabela de preços com decimais normalizados."""
    return pd.read_parquet(PROCESSED / "dim_precos_tratada.parquet")


# ── Helpers analíticos ────────────────────────────────────────────────────────

def receita_por_loja(vendas: pd.DataFrame) -> pd.DataFrame:
    """Agrega receita total por loja, ordena decrescente."""
    lojas = load_dim_lojas()
    return (
        vendas.groupby("COD_EMPRESA")["RECEITA"]
        .sum()
        .reset_index()
        .merge(lojas, on="COD_EMPRESA")
        .sort_values("RECEITA", ascending=False)
        .reset_index(drop=True)
    )


def curva_abc(vendas: pd.DataFrame, coluna_agrup: str = "CODIGO") -> pd.DataFrame:
    """
    Classifica itens em A/B/C pela curva de Pareto de receita.

    A = top 80% da receita cumulativa
    B = próximos 15%
    C = últimos 5%
    """
    rec = (
        vendas.groupby(coluna_agrup)["RECEITA"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    rec["RECEITA_ACUM_PCT"] = rec["RECEITA"].cumsum() / rec["RECEITA"].sum() * 100
    rec["CURVA"] = pd.cut(
        rec["RECEITA_ACUM_PCT"],
        bins=[0, 80, 95, 100],
        labels=["A", "B", "C"],
        include_lowest=True,
    )
    return rec
