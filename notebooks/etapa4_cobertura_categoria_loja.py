"""
etapa4_cobertura_categoria_loja.py
==================================
Etapa 4 - Analise de cobertura por categoria e loja

Objetivos
---------
1. Agregar o snapshot de cobertura da Etapa 2 por categoria (NIVEL_1, NIVEL_2
   e NIVEL_3), loja e categoria x loja.
2. Medir pares loja x produto por status de estoque, receita historica em
   ruptura/critico e dias de cobertura finitos, tratando explicitamente
   cobertura infinita/sem venda.
3. Cruzar cobertura com os outputs auditaveis da Etapa 3 para priorizar
   categorias e lojas de alta receita com baixa cobertura.
4. Separar rede completa, rede fisica sem Loja 93 e Loja 93 quando a mistura
   de atacado/B2B com varejo fisico distorceria a leitura.
5. Gerar recomendacoes e documentar limitacoes metodologicas e de dados.

Premissas e decisoes metodologicas
----------------------------------
- O grao de origem e o par loja x produto do snapshot `cobertura_estoque`
  gerado na Etapa 2. A Etapa 4 nao recalcula estoque projetado; ela agrega e
  reconcilia o output auditavel.
- `RECEITA_TOTAL` representa a receita historica do par loja x produto no
  periodo analisado. Nulos sao tratados como zero apenas para agregacao, sem
  criar venda inexistente.
- Receita em risco = receita historica dos pares com `STATUS_ESTOQUE` em
  `EM RUPTURA` ou `CRÍTICO`.
- Medias/medianas de `DIAS_COBERTURA` sao calculadas somente em valores
  finitos. Pares com cobertura infinita sao contabilizados em coluna propria.
- A Loja 93 (Alhandra-PB) e mantida na rede completa e segregada da rede
  fisica. A priorizacao operacional compara lojas fisicas entre si e lista a
  Loja 93 em escopo separado.
- `TRANSACOES` dos outputs da Etapa 3 continua sendo proxy de linhas de venda,
  nao cupom real.

Saidas
------
outputs/etapa4/cobertura_categorias_n1.csv
outputs/etapa4/cobertura_categorias_n2.csv
outputs/etapa4/cobertura_categorias_n3.csv
outputs/etapa4/cobertura_lojas.csv
outputs/etapa4/cobertura_categoria_loja.csv
outputs/etapa4/priorizacao_reposicao_categoria_loja.csv
outputs/etapa4/recomendacoes_melhoria.csv
outputs/etapa4/validacoes_etapa4.csv
outputs/etapa4/resumo_etapa4.md
outputs/etapa4/documentacao_tecnica_etapa4.md
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
    PROCESSED,
    load_dim_lojas,
    load_dim_produto,
    load_vendas,
)


OUT = OUTPUTS / "etapa4"
OUT.mkdir(parents=True, exist_ok=True)

E2 = OUTPUTS / "etapa2"
E3 = OUTPUTS / "etapa3"

UNIVERSO_COMPLETO = "REDE_COMPLETA"
UNIVERSO_FISICO = "REDE_FISICA_SEM_LOJA93"
ESCOPO_LOJA93 = "LOJA_93_ATACADO_B2B"

STATUS_ORDER = ["EM RUPTURA", "CRÍTICO", "ATENÇÃO", "SAUDÁVEL", "SEM VENDA"]
STATUS_RISCO = ["EM RUPTURA", "CRÍTICO"]
STATUS_COLS = {
    "EM RUPTURA": "PARES_EM_RUPTURA",
    "CRÍTICO": "PARES_CRITICO",
    "ATENÇÃO": "PARES_ATENCAO",
    "SAUDÁVEL": "PARES_SAUDAVEL",
    "SEM VENDA": "PARES_STATUS_SEM_VENDA",
}


def safe_div(numerador, denominador):
    """Divide evitando infinito quando o denominador e zero."""
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


def normalizar_dimensoes(df: pd.DataFrame) -> pd.DataFrame:
    """Preenche dimensoes textuais usadas em groupby para nao perder linhas."""
    out = df.copy()
    for col in ["DESCRICAO", "NIVEL_1", "NIVEL_2", "NIVEL_3", "CD_CIDADE", "CD_ESTADO"]:
        if col in out.columns:
            out[col] = out[col].fillna("SEM CADASTRO")
    return out


def carregar_cobertura_enriquecida() -> pd.DataFrame:
    """Carrega cobertura da Etapa 2 e adiciona NIVEL_2/NIVEL_3 e flags da Etapa 4."""
    cobertura = pd.read_parquet(PROCESSED / "cobertura_estoque.parquet")
    produtos = load_dim_produto()[["CODIGO", "NIVEL_2", "NIVEL_3"]].drop_duplicates("CODIGO")
    lojas = load_dim_lojas().drop_duplicates("COD_EMPRESA")

    cobertura = cobertura.merge(produtos, on="CODIGO", how="left", validate="many_to_one")

    # O snapshot ja traz cidade/estado, mas a dimensao e mantida como fallback
    # caso a Etapa 2 seja regenerada com menos colunas.
    cobertura = cobertura.merge(lojas, on="COD_EMPRESA", how="left", suffixes=("", "_DIM"))
    for col in ["CD_CIDADE", "CD_ESTADO"]:
        dim_col = f"{col}_DIM"
        if dim_col in cobertura.columns:
            cobertura[col] = cobertura[col].fillna(cobertura[dim_col])
            cobertura = cobertura.drop(columns=[dim_col])

    cobertura = normalizar_dimensoes(cobertura)
    cobertura["RECEITA_TOTAL"] = cobertura["RECEITA_TOTAL"].fillna(0.0).astype(float)
    cobertura["FLAG_LOJA93"] = (cobertura["COD_EMPRESA"] == LOJA_ATACADO).astype(int)
    cobertura["TIPO_OPERACAO"] = np.where(
        cobertura["FLAG_LOJA93"] == 1,
        ESCOPO_LOJA93,
        "REDE_FISICA",
    )
    cobertura["FLAG_RISCO"] = cobertura["STATUS_ESTOQUE"].isin(STATUS_RISCO).astype(int)
    cobertura["FLAG_COM_RECEITA_HISTORICA"] = (cobertura["RECEITA_TOTAL"] > 0).astype(int)
    cobertura["FLAG_SEM_RECEITA_HISTORICA"] = (cobertura["RECEITA_TOTAL"] <= 0).astype(int)
    cobertura["FLAG_DIAS_COBERTURA_FINITO"] = np.isfinite(cobertura["DIAS_COBERTURA"]).astype(int)
    cobertura["FLAG_DIAS_COBERTURA_INFINITO"] = (~np.isfinite(cobertura["DIAS_COBERTURA"])).astype(int)
    cobertura["DIAS_COBERTURA_FINITO"] = np.where(
        np.isfinite(cobertura["DIAS_COBERTURA"]),
        cobertura["DIAS_COBERTURA"],
        np.nan,
    )
    cobertura["RECEITA_RUPTURA_CRITICO"] = np.where(
        cobertura["STATUS_ESTOQUE"].isin(STATUS_RISCO),
        cobertura["RECEITA_TOTAL"],
        0.0,
    )
    cobertura["RECEITA_EM_RUPTURA"] = np.where(
        cobertura["STATUS_ESTOQUE"] == "EM RUPTURA",
        cobertura["RECEITA_TOTAL"],
        0.0,
    )
    cobertura["RECEITA_CRITICO"] = np.where(
        cobertura["STATUS_ESTOQUE"] == "CRÍTICO",
        cobertura["RECEITA_TOTAL"],
        0.0,
    )
    return cobertura


def bases_por_universo(cobertura: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        UNIVERSO_COMPLETO: cobertura.copy(),
        UNIVERSO_FISICO: cobertura[cobertura["COD_EMPRESA"] != LOJA_ATACADO].copy(),
    }


def contagem_status(base: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    status = (
        base.groupby(keys + ["STATUS_ESTOQUE"], dropna=False)
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    for status_label in STATUS_ORDER:
        if status_label not in status.columns:
            status[status_label] = 0
    status = status.rename(columns=STATUS_COLS)
    return status[keys + list(STATUS_COLS.values())]


def agregar_cobertura(base: pd.DataFrame, universo: str, keys: list[str]) -> pd.DataFrame:
    """Agrega metricas de cobertura para um universo e um conjunto de chaves."""
    total_receita_universo = float(base["RECEITA_TOTAL"].sum())
    grp = base.groupby(keys, dropna=False)
    agg = (
        grp.agg(
            PARES_LOJA_PRODUTO=("CODIGO", "size"),
            SKUS_DISTINTOS=("CODIGO", "nunique"),
            LOJAS_DISTINTAS=("COD_EMPRESA", "nunique"),
            RECEITA_HISTORICA_TOTAL=("RECEITA_TOTAL", "sum"),
            RECEITA_RUPTURA_CRITICO=("RECEITA_RUPTURA_CRITICO", "sum"),
            RECEITA_EM_RUPTURA=("RECEITA_EM_RUPTURA", "sum"),
            RECEITA_CRITICO=("RECEITA_CRITICO", "sum"),
            PARES_RUPTURA_CRITICO=("FLAG_RISCO", "sum"),
            PARES_COM_RECEITA_HISTORICA=("FLAG_COM_RECEITA_HISTORICA", "sum"),
            PARES_SEM_RECEITA_HISTORICA=("FLAG_SEM_RECEITA_HISTORICA", "sum"),
            PARES_DIAS_COBERTURA_FINITO=("FLAG_DIAS_COBERTURA_FINITO", "sum"),
            PARES_DIAS_COBERTURA_INFINITO=("FLAG_DIAS_COBERTURA_INFINITO", "sum"),
            DIAS_COBERTURA_MEDIA_FINITA=("DIAS_COBERTURA_FINITO", "mean"),
            DIAS_COBERTURA_MEDIANA_FINITA=("DIAS_COBERTURA_FINITO", "median"),
            DIAS_COBERTURA_P25_FINITA=("DIAS_COBERTURA_FINITO", lambda s: s.quantile(0.25)),
            DIAS_COBERTURA_P75_FINITA=("DIAS_COBERTURA_FINITO", lambda s: s.quantile(0.75)),
            ESTOQUE_PROJ_TOTAL=("ESTOQUE_PROJ", "sum"),
            ESTOQUE_PROJ_MEDIANA=("ESTOQUE_PROJ", "median"),
            VENDA_MEDIA_MES_TOTAL=("VENDA_MEDIA_MES", "sum"),
        )
        .reset_index()
    )

    agg = agg.merge(contagem_status(base, keys), on=keys, how="left", validate="one_to_one")
    agg.insert(0, "UNIVERSO", universo)

    for col in STATUS_COLS.values():
        agg[col] = agg[col].fillna(0).astype(int)

    agg["PCT_PARES_RUPTURA_CRITICO"] = safe_div(
        agg["PARES_RUPTURA_CRITICO"], agg["PARES_LOJA_PRODUTO"]
    ) * 100
    agg["PCT_PARES_EM_RUPTURA"] = safe_div(agg["PARES_EM_RUPTURA"], agg["PARES_LOJA_PRODUTO"]) * 100
    agg["PCT_PARES_CRITICO"] = safe_div(agg["PARES_CRITICO"], agg["PARES_LOJA_PRODUTO"]) * 100
    agg["PCT_PARES_DIAS_INFINITO"] = safe_div(
        agg["PARES_DIAS_COBERTURA_INFINITO"], agg["PARES_LOJA_PRODUTO"]
    ) * 100
    agg["PCT_PARES_SEM_RECEITA_HISTORICA"] = safe_div(
        agg["PARES_SEM_RECEITA_HISTORICA"], agg["PARES_LOJA_PRODUTO"]
    ) * 100
    agg["PART_RECEITA_RISCO_PCT"] = safe_div(
        agg["RECEITA_RUPTURA_CRITICO"], agg["RECEITA_HISTORICA_TOTAL"]
    ) * 100
    agg["PART_RECEITA_UNIVERSO_PCT"] = safe_div(
        agg["RECEITA_HISTORICA_TOTAL"], total_receita_universo
    ) * 100
    agg["PART_RECEITA_RISCO_UNIVERSO_PCT"] = safe_div(
        agg["RECEITA_RUPTURA_CRITICO"], total_receita_universo
    ) * 100

    return agg.sort_values(
        ["UNIVERSO", "RECEITA_RUPTURA_CRITICO", "PCT_PARES_RUPTURA_CRITICO"],
        ascending=[True, False, False],
    ).reset_index(drop=True)


def ler_csv_etapa3(nome: str) -> pd.DataFrame:
    return pd.read_csv(E3 / nome, encoding="utf-8-sig")


def cruzar_desempenho_categoria(df: pd.DataFrame, nome_csv: str, keys: list[str]) -> pd.DataFrame:
    desempenho = ler_csv_etapa3(nome_csv)
    cols = [
        "UNIVERSO",
        *keys,
        "RECEITA",
        "TRANSACOES",
        "SKUS_ATIVOS",
        "PARTICIPACAO_RECEITA_PCT",
        "VAR_RECEITA_2025_VS_2024_PCT",
    ]
    desempenho = desempenho[cols].rename(
        columns={
            "RECEITA": "RECEITA_ETAPA3",
            "TRANSACOES": "TRANSACOES_ETAPA3_LINHAS_VENDA",
            "SKUS_ATIVOS": "SKUS_ATIVOS_ETAPA3",
            "PARTICIPACAO_RECEITA_PCT": "PART_RECEITA_ETAPA3_PCT",
            "VAR_RECEITA_2025_VS_2024_PCT": "VAR_RECEITA_2025_VS_2024_ETAPA3_PCT",
        }
    )
    out = df.merge(desempenho, on=["UNIVERSO", *keys], how="left", validate="one_to_one")
    out["DIF_RECEITA_VS_ETAPA3"] = out["RECEITA_HISTORICA_TOTAL"] - out["RECEITA_ETAPA3"].fillna(0.0)
    return out


def cruzar_desempenho_loja(df: pd.DataFrame) -> pd.DataFrame:
    desempenho = ler_csv_etapa3("desempenho_lojas.csv")
    cols = [
        "UNIVERSO",
        "COD_EMPRESA",
        "CD_CIDADE",
        "CD_ESTADO",
        "TIPO_OPERACAO",
        "FLAG_LOJA93",
        "RECEITA",
        "TRANSACOES",
        "SKUS_ATIVOS",
        "PARTICIPACAO_RECEITA_PCT",
        "VAR_RECEITA_2025_VS_2024_PCT",
    ]
    desempenho = desempenho[cols].rename(
        columns={
            "RECEITA": "RECEITA_ETAPA3",
            "TRANSACOES": "TRANSACOES_ETAPA3_LINHAS_VENDA",
            "SKUS_ATIVOS": "SKUS_ATIVOS_ETAPA3",
            "PARTICIPACAO_RECEITA_PCT": "PART_RECEITA_ETAPA3_PCT",
            "VAR_RECEITA_2025_VS_2024_PCT": "VAR_RECEITA_2025_VS_2024_ETAPA3_PCT",
        }
    )
    out = df.merge(
        desempenho,
        on=["UNIVERSO", "COD_EMPRESA", "CD_CIDADE", "CD_ESTADO", "TIPO_OPERACAO", "FLAG_LOJA93"],
        how="left",
        validate="one_to_one",
    )
    out["DIF_RECEITA_VS_ETAPA3"] = out["RECEITA_HISTORICA_TOTAL"] - out["RECEITA_ETAPA3"].fillna(0.0)
    return out


def adicionar_ranking_reposicao(df: pd.DataFrame, grupo: str = "UNIVERSO") -> pd.DataFrame:
    out = df.copy()
    out = out.sort_values(
        [grupo, "RECEITA_RUPTURA_CRITICO", "PCT_PARES_RUPTURA_CRITICO", "PARES_RUPTURA_CRITICO"],
        ascending=[True, False, False, False],
    ).reset_index(drop=True)
    out["RANK_REPOSICAO"] = out.groupby(grupo).cumcount() + 1
    return out


def montar_priorizacao(categoria_loja: pd.DataFrame) -> pd.DataFrame:
    """Monta ranking operacional sem misturar Loja 93 com lojas fisicas."""
    fisico = categoria_loja[categoria_loja["UNIVERSO"] == UNIVERSO_FISICO].copy()
    fisico["ESCOPO_PRIORIZACAO"] = UNIVERSO_FISICO

    loja93 = categoria_loja[
        (categoria_loja["UNIVERSO"] == UNIVERSO_COMPLETO)
        & (categoria_loja["COD_EMPRESA"] == LOJA_ATACADO)
    ].copy()
    loja93["ESCOPO_PRIORIZACAO"] = ESCOPO_LOJA93

    prio = pd.concat([fisico, loja93], ignore_index=True)
    prio = prio[(prio["PARES_RUPTURA_CRITICO"] > 0) & (prio["RECEITA_RUPTURA_CRITICO"] > 0)].copy()
    prio["_ORDEM_ESCOPO"] = prio["ESCOPO_PRIORIZACAO"].map({UNIVERSO_FISICO: 1, ESCOPO_LOJA93: 2}).fillna(9)
    prio = prio.sort_values(
        [
            "_ORDEM_ESCOPO",
            "RECEITA_RUPTURA_CRITICO",
            "PCT_PARES_RUPTURA_CRITICO",
            "PARES_RUPTURA_CRITICO",
        ],
        ascending=[True, False, False, False],
    ).reset_index(drop=True)
    prio["RANK_PRIORIDADE_ESCOPO"] = prio.groupby("ESCOPO_PRIORIZACAO").cumcount() + 1

    totais_escopo = prio.groupby("ESCOPO_PRIORIZACAO")["RANK_PRIORIDADE_ESCOPO"].transform("max")
    prio["PERCENTIL_PRIORIDADE_ESCOPO"] = np.where(
        totais_escopo > 1,
        safe_div(prio["RANK_PRIORIDADE_ESCOPO"] - 1, totais_escopo - 1) * 100,
        0.0,
    )
    limite_alta = np.maximum(1, np.ceil(totais_escopo * 0.10)).astype(int)
    limite_media = np.maximum(limite_alta + 1, np.ceil(totais_escopo * 0.30)).astype(int)
    prio["FAIXA_PRIORIDADE"] = np.select(
        [
            prio["RANK_PRIORIDADE_ESCOPO"] <= limite_alta,
            prio["RANK_PRIORIDADE_ESCOPO"] <= limite_media,
        ],
        ["ALTA", "MÉDIA"],
        default="MONITORAR",
    )
    prio["ACAO_RECOMENDADA"] = prio.apply(
        lambda r: (
            f"Validar saldo físico/transferências e priorizar a reposição dos "
            f"{int(r['PARES_RUPTURA_CRITICO'])} pares em ruptura/crítico de "
            f"{r['NIVEL_1']} na loja {int(r['COD_EMPRESA'])} "
            f"({r['CD_CIDADE']}-{r['CD_ESTADO']})."
        ),
        axis=1,
    )
    prio["EVIDENCIA_PRIORIZACAO"] = prio.apply(
        lambda r: (
            f"Receita histórica associada aos pares em ruptura/crítico: "
            f"{fmt_brl(r['RECEITA_RUPTURA_CRITICO'])}; "
            f"{fmt_pct(r['PCT_PARES_RUPTURA_CRITICO'])} dos pares da categoria na loja "
            f"estão em ruptura/crítico."
        ),
        axis=1,
    )

    cols_prioridade = [
        "ESCOPO_PRIORIZACAO",
        "RANK_PRIORIDADE_ESCOPO",
        "FAIXA_PRIORIDADE",
        "UNIVERSO",
        "COD_EMPRESA",
        "CD_CIDADE",
        "CD_ESTADO",
        "TIPO_OPERACAO",
        "FLAG_LOJA93",
        "NIVEL_1",
        "RECEITA_HISTORICA_TOTAL",
        "RECEITA_RUPTURA_CRITICO",
        "PART_RECEITA_RISCO_PCT",
        "PART_RECEITA_RISCO_UNIVERSO_PCT",
        "PARES_LOJA_PRODUTO",
        "PARES_RUPTURA_CRITICO",
        "PARES_EM_RUPTURA",
        "PARES_CRITICO",
        "PCT_PARES_RUPTURA_CRITICO",
        "DIAS_COBERTURA_MEDIA_FINITA",
        "DIAS_COBERTURA_MEDIANA_FINITA",
        "PARES_DIAS_COBERTURA_INFINITO",
        "ACAO_RECOMENDADA",
        "EVIDENCIA_PRIORIZACAO",
    ]
    return prio[cols_prioridade]


def gerar_recomendacoes_melhoria() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "PRIORIDADE": "ALTA",
                "TEMA": "Movimentações de estoque",
                "LIMITACAO_OU_PROBLEMA": "A base não contém foto de estoque de abertura para a maioria dos pares, transferências entre lojas, ajustes de inventário ou saldos físicos posteriores ao corte inicial.",
                "RISCO_ANALITICO": "O estoque projetado (compras − vendas) fica ≤ 0 em ~91% dos pares, marcando-os como ruptura. Isso reflete ausência de movimentação capturada, não indisponibilidade física real — a taxa de ruptura é de prioridade relativa, não literal.",
                "RECOMENDACAO": "Incorporar foto de estoque de abertura, transferências, ajustes de inventário e data/hora do saldo para recalcular a cobertura com disponibilidade mais próxima do físico.",
                "IMPACTO_ESPERADO": "Reduzir falsos positivos de ruptura e melhorar a assertividade do plano de reposição.",
            },
            {
                "PRIORIDADE": "ALTA",
                "TEMA": "Loja 93 e canal",
                "LIMITACAO_OU_PROBLEMA": "A Loja 93 foi identificada como atacado/B2B por comportamento, não por uma dimensão formal de canal.",
                "RISCO_ANALITICO": "Misturar atacado e rede física distorce a cobertura, o ranking de lojas e as recomendações de reposição.",
                "RECOMENDACAO": "Criar dimensão de canal/operação e políticas de reposição separadas para atacado/B2B e varejo físico.",
                "IMPACTO_ESPERADO": "Comparações mais justas e metas de estoque adequadas ao perfil operacional de cada canal.",
            },
            {
                "PRIORIDADE": "ALTA",
                "TEMA": "Venda média usada na cobertura",
                "LIMITACAO_OU_PROBLEMA": "A Etapa 2 usa a média dos meses COM venda para `VENDA_MEDIA_MES`, não a média sobre os 24 meses.",
                "RISCO_ANALITICO": "Itens intermitentes podem ter a velocidade superestimada e os dias de cobertura subestimados.",
                "RECOMENDACAO": "Rodar análise de sensibilidade com média sobre 24 meses e/ou sobre os meses desde a primeira venda, mantendo comparativo de mudança de status.",
                "IMPACTO_ESPERADO": "Separar falta crítica de itens recorrentes de baixa cobertura aparente em itens de venda esporádica.",
            },
            {
                "PRIORIDADE": "MÉDIA",
                "TEMA": "Lead time e políticas de estoque",
                "LIMITACAO_OU_PROBLEMA": "Não há lead time de fornecedor, estoque mínimo, lote de compra ou curva de serviço por categoria.",
                "RISCO_ANALITICO": "A priorização ordena urgência relativa, mas ainda não dimensiona a quantidade ideal de compra.",
                "RECOMENDACAO": "Adicionar lead time, lote mínimo/múltiplo, custo de carregamento e política de nível de serviço por categoria.",
                "IMPACTO_ESPERADO": "Permitir transformar a priorização em plano de compras quantitativo na Etapa 6.",
            },
            {
                "PRIORIDADE": "MÉDIA",
                "TEMA": "Identificador de transação",
                "LIMITACAO_OU_PROBLEMA": "A base de vendas não possui id de cupom, pedido ou nota.",
                "RISCO_ANALITICO": "`TRANSACOES` nos outputs de desempenho representa linhas de venda, não compras reais.",
                "RECOMENDACAO": "Incluir id_transacao/pedido/nota e número do item para medir cupom real, cesta e ticket médio verdadeiro.",
                "IMPACTO_ESPERADO": "Melhorar análises de cesta, recorrência e priorização por comportamento de compra.",
            },
        ]
    )


def assert_close(
    nome: str,
    observado: float,
    esperado: float,
    validacoes: list[dict],
    tolerancia: float = 1e-4,
) -> None:
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


def validar_etapa4(
    cobertura: pd.DataFrame,
    categorias_n1: pd.DataFrame,
    categorias_n2: pd.DataFrame,
    categorias_n3: pd.DataFrame,
    lojas: pd.DataFrame,
    categoria_loja: pd.DataFrame,
    priorizacao: pd.DataFrame,
) -> pd.DataFrame:
    validacoes: list[dict] = []

    cob_csv = pd.read_csv(E2 / "cobertura_estoque.csv", encoding="utf-8-sig")
    assert_close("Linhas cobertura parquet vs CSV Etapa 2", len(cobertura), len(cob_csv), validacoes, 0)
    assert_close(
        "Receita cobertura parquet vs CSV Etapa 2",
        cobertura["RECEITA_TOTAL"].sum(),
        cob_csv["RECEITA_TOTAL"].fillna(0).sum(),
        validacoes,
    )
    assert_true(
        "DIAS_COBERTURA negativo inexistente",
        bool((cobertura["DIAS_COBERTURA"].replace(np.inf, np.nan).dropna() < 0).sum() == 0),
        validacoes,
    )

    vendas = load_vendas(excluir_atacado=False)
    receita_vendas_total = float(vendas["RECEITA"].sum())
    receita_vendas_fisica = float(vendas[vendas["COD_EMPRESA"] != LOJA_ATACADO]["RECEITA"].sum())
    receita_cobertura_total = float(cobertura["RECEITA_TOTAL"].sum())
    receita_cobertura_fisica = float(cobertura.loc[cobertura["COD_EMPRESA"] != LOJA_ATACADO, "RECEITA_TOTAL"].sum())

    assert_close("Receita cobertura vs vendas - rede completa", receita_cobertura_total, receita_vendas_total, validacoes)
    assert_close("Receita cobertura vs vendas - rede fisica", receita_cobertura_fisica, receita_vendas_fisica, validacoes)

    bases_receita = {
        UNIVERSO_COMPLETO: receita_cobertura_total,
        UNIVERSO_FISICO: receita_cobertura_fisica,
    }
    bases_linhas = {
        UNIVERSO_COMPLETO: len(cobertura),
        UNIVERSO_FISICO: int((cobertura["COD_EMPRESA"] != LOJA_ATACADO).sum()),
    }

    for universo, receita_esperada in bases_receita.items():
        for nome, df in [
            ("categorias_n1", categorias_n1),
            ("categorias_n2", categorias_n2),
            ("categorias_n3", categorias_n3),
            ("lojas", lojas),
            ("categoria_loja", categoria_loja),
        ]:
            base = df[df["UNIVERSO"] == universo]
            assert_close(
                f"{nome} soma RECEITA_HISTORICA_TOTAL - {universo}",
                base["RECEITA_HISTORICA_TOTAL"].sum(),
                receita_esperada,
                validacoes,
            )
            assert_close(
                f"{nome} soma PARES_LOJA_PRODUTO - {universo}",
                base["PARES_LOJA_PRODUTO"].sum(),
                bases_linhas[universo],
                validacoes,
                tolerancia=0,
            )
            status_sum = base[[*STATUS_COLS.values()]].sum(axis=1)
            assert_true(
                f"{nome} status soma pares por linha - {universo}",
                bool((status_sum == base["PARES_LOJA_PRODUTO"]).all()),
                validacoes,
            )

    for nome, df in [
        ("categorias_n1", categorias_n1),
        ("categorias_n2", categorias_n2),
        ("categorias_n3", categorias_n3),
        ("lojas", lojas),
    ]:
        assert_close(
            f"{nome} diferenca maxima vs Etapa 3",
            float(df["DIF_RECEITA_VS_ETAPA3"].abs().max()),
            0.0,
            validacoes,
        )

    assert_true(
        "Loja 93 ausente do universo fisico nas agregacoes por loja",
        bool(not ((lojas["UNIVERSO"] == UNIVERSO_FISICO) & (lojas["COD_EMPRESA"] == LOJA_ATACADO)).any()),
        validacoes,
    )
    assert_true(
        "Prioridades sem duplicar fisico dentro de rede completa",
        bool(set(priorizacao["ESCOPO_PRIORIZACAO"].unique()).issubset({UNIVERSO_FISICO, ESCOPO_LOJA93})),
        validacoes,
    )
    assert_true(
        "Prioridades possuem apenas receita em risco positiva",
        bool((priorizacao["RECEITA_RUPTURA_CRITICO"] > 0).all()),
        validacoes,
    )
    assert_true(
        "Medias finitas de dias nao carregam infinito",
        bool(
            np.isfinite(
                pd.concat(
                    [
                        categorias_n1["DIAS_COBERTURA_MEDIA_FINITA"],
                        categorias_n2["DIAS_COBERTURA_MEDIA_FINITA"],
                        categorias_n3["DIAS_COBERTURA_MEDIA_FINITA"],
                        lojas["DIAS_COBERTURA_MEDIA_FINITA"],
                        categoria_loja["DIAS_COBERTURA_MEDIA_FINITA"],
                    ]
                ).dropna()
            ).all()
        ),
        validacoes,
    )

    return pd.DataFrame(validacoes)


def salvar_csv(df: pd.DataFrame, nome: str) -> None:
    df.to_csv(OUT / nome, index=False, encoding="utf-8-sig", float_format="%.6f")


def gerar_resumo(
    cobertura: pd.DataFrame,
    categorias_n1: pd.DataFrame,
    lojas: pd.DataFrame,
    priorizacao: pd.DataFrame,
    validacoes: pd.DataFrame,
) -> str:
    total_pares = len(cobertura)
    fisico = cobertura[cobertura["COD_EMPRESA"] != LOJA_ATACADO]
    risco_total = cobertura[cobertura["STATUS_ESTOQUE"].isin(STATUS_RISCO)]
    risco_fisico = fisico[fisico["STATUS_ESTOQUE"].isin(STATUS_RISCO)]

    cat_full = categorias_n1[categorias_n1["UNIVERSO"] == UNIVERSO_COMPLETO].iloc[0]
    cat_fisica = categorias_n1[categorias_n1["UNIVERSO"] == UNIVERSO_FISICO].iloc[0]
    loja_fisica = (
        lojas[(lojas["UNIVERSO"] == UNIVERSO_FISICO)]
        .sort_values("RECEITA_RUPTURA_CRITICO", ascending=False)
        .iloc[0]
    )
    loja93 = lojas[(lojas["UNIVERSO"] == UNIVERSO_COMPLETO) & (lojas["COD_EMPRESA"] == LOJA_ATACADO)].iloc[0]
    top_prio_fisico = priorizacao[priorizacao["ESCOPO_PRIORIZACAO"] == UNIVERSO_FISICO].iloc[0]
    top_prio_93 = priorizacao[priorizacao["ESCOPO_PRIORIZACAO"] == ESCOPO_LOJA93].iloc[0]

    resumo = f"""# Etapa 4 - Análise de cobertura por categoria e loja

## Glossário rápido (ler antes dos números)

- **Par loja × produto:** cada combinação de uma loja com um produto. É o grão
  desta análise. A rede completa tem {fmt_num(total_pares)} pares.
- **Cobertura (dias de estoque):** `estoque projetado ÷ venda média mensal × 30`.
  Estima por quantos dias o estoque atende a venda média.
- **Estoque projetado:** **não** é contagem física. É reconstruído como
  `estoque inicial + compras − vendas` na janela jan/2024–dez/2025 (vem da Etapa 2).
- **Em ruptura / crítico:** par com estoque projetado ≤ 0 (ruptura) ou cobertura
  ≤ 30 dias (crítico). São os pares que entram na fila de reposição.
- **Receita histórica em risco:** receita **já realizada no passado** pelos pares
  hoje classificados em ruptura/crítico. É usada para **ordenar prioridade** de
  reposição — **não** é uma previsão de perda futura.

## Como interpretar a cobertura (leia antes de reagir aos 93%)

A taxa de ruptura é altíssima de propósito, por limitação de dados, não por erro:

- A base **não tem foto de estoque de abertura** para a maioria dos pares (entram
  com estoque inicial = 0) e **~88% dos SKUs vendem sem nenhuma compra registrada**.
  Com isso, o estoque projetado fica ≤ 0 na maior parte dos pares, que são então
  marcados como "EM RUPTURA".
- É uma escolha **conservadora deliberada**: na dúvida, o método assume falta de
  estoque — ou seja, **erra para sinalizar ruptura a mais, nunca a menos**.
- Portanto, "{fmt_pct(len(risco_total) / total_pares * 100)} em ruptura/crítico"
  **não** significa "{fmt_pct(len(risco_total) / total_pares * 100)} das prateleiras
  vazias na vida real". É um **ranking de prioridade relativa** de reposição, não a
  taxa real de ruptura física.
- "Disponibilidade física real" exigiria inventário/contagem física, transferências
  entre lojas e ajustes de saldo que **não existem nesta base**.

## Principais achados

- Rede completa: {fmt_num(total_pares)} pares loja × produto; {fmt_num(len(risco_total))} ({fmt_pct(len(risco_total) / total_pares * 100)}) estão em ruptura/crítico (lembrando: prioridade relativa, ver seção acima).
- A receita histórica associada a ruptura/crítico na rede completa é {fmt_brl_milhao(risco_total["RECEITA_TOTAL"].sum())}, equivalente a {fmt_pct(risco_total["RECEITA_TOTAL"].sum() / cobertura["RECEITA_TOTAL"].sum() * 100)} da receita histórica dos pares. Leia como "concentração de receita por trás da fila de reposição", não como perda projetada.
- Rede física sem Loja 93: {fmt_num(len(fisico))} pares; {fmt_num(len(risco_fisico))} ({fmt_pct(len(risco_fisico) / len(fisico) * 100)}) em ruptura/crítico, com {fmt_brl_milhao(risco_fisico["RECEITA_TOTAL"].sum())} de receita histórica associada.
- Categoria N1 com maior receita histórica em ruptura/crítico na rede completa: `{cat_full["NIVEL_1"]}`, com {fmt_brl_milhao(cat_full["RECEITA_RUPTURA_CRITICO"])}.
- Categoria N1 com maior receita histórica em ruptura/crítico na rede física: `{cat_fisica["NIVEL_1"]}`, com {fmt_brl_milhao(cat_fisica["RECEITA_RUPTURA_CRITICO"])}.
- Loja física com maior pressão de reposição por receita histórica em ruptura/crítico: loja {int(loja_fisica["COD_EMPRESA"])} ({loja_fisica["CD_CIDADE"]}-{loja_fisica["CD_ESTADO"]}), com {fmt_brl_milhao(loja_fisica["RECEITA_RUPTURA_CRITICO"])}.
- Loja 93 deve ser analisada separadamente: no escopo de rede completa, soma {fmt_brl_milhao(loja93["RECEITA_RUPTURA_CRITICO"])} de receita histórica em ruptura/crítico.
- Maior prioridade na rede física: `{top_prio_fisico["NIVEL_1"]}` na loja {int(top_prio_fisico["COD_EMPRESA"])} ({top_prio_fisico["CD_CIDADE"]}-{top_prio_fisico["CD_ESTADO"]}), com {fmt_brl_milhao(top_prio_fisico["RECEITA_RUPTURA_CRITICO"])} de receita histórica associada.
- Maior prioridade da Loja 93: `{top_prio_93["NIVEL_1"]}`, com {fmt_brl_milhao(top_prio_93["RECEITA_RUPTURA_CRITICO"])} de receita histórica associada.

## Limitações e cuidados

- A cobertura é uma métrica **conservadora** (erra para o lado de sinalizar ruptura
  a mais) e mede **prioridade relativa**, não disponibilidade física real. Ver a
  seção "Como interpretar a cobertura".
- A base não possui transferências entre lojas, ajustes de inventário nem saldo
  físico posterior ao corte inicial — daí o excesso de ruptura.
- `VENDA_MEDIA_MES` vem da Etapa 2 e usa a média dos meses **com** venda, o que pode
  superestimar a velocidade e subestimar a cobertura de itens intermitentes.
- A Loja 93 é atacado/B2B e não deve ser comparada diretamente com lojas físicas;
  por isso é segregada nas agregações e na priorização.
- `TRANSACOES` nos cruzamentos com a Etapa 3 representa **linhas de venda**, não
  cupons/pedidos/notas reais (a base não tem id de transação).

## Validações

- {len(validacoes)} validações executadas, todas com status `{validacoes["STATUS"].unique()[0]}`.
- Totais de pares e receita das agregações fecham com `outputs/etapa2/cobertura_estoque.csv`.
- Receita das agregações por categoria e loja fecha com os outputs correspondentes da Etapa 3.
- Loja 93 não aparece no universo `REDE_FISICA_SEM_LOJA93`.
- Estatísticas de dias de cobertura não carregam valores infinitos em médias/medianas.

## Como executar

```bash
cd notebooks
python etapa4_cobertura_categoria_loja.py
```

Os arquivos auditáveis são gravados em `outputs/etapa4/`.
"""
    return resumo


def gerar_documentacao_tecnica() -> str:
    return """# Documentação técnica - Etapa 4

Guia de reprodução e continuação da análise de cobertura por categoria e loja.

## O que foi implementado

A Etapa 4 agrega o snapshot de cobertura da Etapa 2 (`data/processed/cobertura_estoque.parquet` e `outputs/etapa2/cobertura_estoque.csv`) por categoria, loja e categoria × loja. O script canônico é `notebooks/etapa4_cobertura_categoria_loja.py`.

## Como interpretar a cobertura (contexto obrigatório)

- A cobertura (dias de estoque) = `estoque projetado ÷ venda média mensal × 30`.
- O **estoque projetado não é contagem física**: é reconstruído na Etapa 2 como `estoque inicial + compras − vendas` na janela jan/2024–dez/2025.
- A base não tem foto de estoque de abertura para a maioria dos pares (entram com inicial = 0) e ~88% dos SKUs vendem sem compra registrada. Por isso o estoque projetado fica ≤ 0 em ~91% dos pares, que viram "EM RUPTURA".
- Logo, a taxa de ruptura é **conservadora por construção** (erra para sinalizar ruptura a mais, nunca a menos) e mede **prioridade relativa de reposição**, não disponibilidade física real. "Receita em risco" = receita histórica já realizada pelos pares hoje em ruptura/crítico, usada para ordenar prioridade — não é perda projetada.

## Entradas usadas

- `data/processed/cobertura_estoque.parquet`: grão loja × produto com estoque projetado, venda média, dias de cobertura, status e receita histórica do par.
- `outputs/etapa2/cobertura_estoque.csv`: usado nas validações de reconciliação com a Etapa 2.
- `data/processed/dim_produto_tratada.parquet`: adiciona `NIVEL_2` e `NIVEL_3`.
- `data/processed/dim_lojas.parquet`: fallback de cidade/estado.
- `data/processed/vendas_tratadas.parquet`: validação do total de receita, via loader `load_vendas(excluir_atacado=False)`.
- `outputs/etapa3/desempenho_categorias_n1.csv`, `desempenho_categorias_n2.csv`, `desempenho_categorias_n3.csv` e `desempenho_lojas.csv`: cruzamento com receita/participação/variação já auditados na Etapa 3.

## Principais fórmulas

- Receita histórica em ruptura/crítico: soma de `RECEITA_TOTAL` dos pares com `STATUS_ESTOQUE` em `EM RUPTURA` ou `CRÍTICO`.
- Percentual de pares em ruptura/crítico: `PARES_RUPTURA_CRITICO / PARES_LOJA_PRODUTO`.
- Participação da receita em risco no grupo: `RECEITA_RUPTURA_CRITICO / RECEITA_HISTORICA_TOTAL`.
- Participação da receita em risco no universo: `RECEITA_RUPTURA_CRITICO / receita_total_do_universo`.
- Estatísticas de dias de cobertura: média, mediana, p25 e p75 calculados somente sobre `DIAS_COBERTURA` finito. Pares infinitos (sem venda) são contados em `PARES_DIAS_COBERTURA_INFINITO`.

## Separação da Loja 93

Os outputs agregados trazem `UNIVERSO` com `REDE_COMPLETA` e `REDE_FISICA_SEM_LOJA93`. A priorização operacional evita duplicidade: compara lojas físicas apenas no escopo `REDE_FISICA_SEM_LOJA93` e lista a Loja 93 no escopo separado `LOJA_93_ATACADO_B2B`.

## Arquivos gerados

- `cobertura_categorias_n1.csv`: cobertura agregada por `NIVEL_1`.
- `cobertura_categorias_n2.csv`: cobertura agregada por `NIVEL_1` + `NIVEL_2`.
- `cobertura_categorias_n3.csv`: cobertura agregada por `NIVEL_1` + `NIVEL_2` + `NIVEL_3`.
- `cobertura_lojas.csv`: cobertura por loja, cidade, estado e tipo de operação.
- `cobertura_categoria_loja.csv`: cobertura por `NIVEL_1` × loja.
- `priorizacao_reposicao_categoria_loja.csv`: ranking operacional por receita histórica em risco, sem misturar Loja 93 com rede física.
- `recomendacoes_melhoria.csv`: melhorias de dados/modelagem/processo.
- `validacoes_etapa4.csv`: reconciliações numéricas.
- `resumo_etapa4.md`: resumo executivo e metodológico.

## Como revisar ou continuar

1. Rode `cd notebooks && python etapa4_cobertura_categoria_loja.py`.
2. Confira `outputs/etapa4/validacoes_etapa4.csv`; qualquer `FALHA` deve bloquear conclusões.
3. Se alterar a Etapa 2, verifique se `STATUS_ESTOQUE`, `RECEITA_TOTAL` e `DIAS_COBERTURA` mantêm a semântica esperada.
4. Se alterar a Etapa 3, reexecute a Etapa 4 para atualizar cruzamentos de receita/participação.
5. Reexecute `python scripts/gerar_dashboard.py` para atualizar dashboard e dicionário consolidado.

## Limitações que não foram resolvidas aqui

- Sem transferências/ajustes/inventário, a cobertura segue conservadora (superestima ruptura).
- Sem lead time, lote mínimo e política de serviço, a Etapa 4 prioriza urgência relativa, mas não calcula a quantidade ideal de compra.
- Sem id de cupom/pedido/nota, `TRANSACOES` continua sendo linhas de venda.
- A Loja 93 precisa de uma dimensão formal de canal para substituir a regra por código da loja.
"""


def main() -> None:
    print("Carregando cobertura da Etapa 2 e dimensoes...")
    cobertura = carregar_cobertura_enriquecida()
    bases = bases_por_universo(cobertura)

    print("Agregando cobertura por categoria, loja e categoria x loja...")
    categorias_n1 = pd.concat(
        [agregar_cobertura(df, universo, ["NIVEL_1"]) for universo, df in bases.items()],
        ignore_index=True,
    )
    categorias_n2 = pd.concat(
        [agregar_cobertura(df, universo, ["NIVEL_1", "NIVEL_2"]) for universo, df in bases.items()],
        ignore_index=True,
    )
    categorias_n3 = pd.concat(
        [
            agregar_cobertura(df, universo, ["NIVEL_1", "NIVEL_2", "NIVEL_3"])
            for universo, df in bases.items()
        ],
        ignore_index=True,
    )
    lojas = pd.concat(
        [
            agregar_cobertura(
                df,
                universo,
                ["COD_EMPRESA", "CD_CIDADE", "CD_ESTADO", "TIPO_OPERACAO", "FLAG_LOJA93"],
            )
            for universo, df in bases.items()
        ],
        ignore_index=True,
    )
    categoria_loja = pd.concat(
        [
            agregar_cobertura(
                df,
                universo,
                ["COD_EMPRESA", "CD_CIDADE", "CD_ESTADO", "TIPO_OPERACAO", "FLAG_LOJA93", "NIVEL_1"],
            )
            for universo, df in bases.items()
        ],
        ignore_index=True,
    )

    print("Cruzando com outputs auditaveis da Etapa 3...")
    categorias_n1 = cruzar_desempenho_categoria(categorias_n1, "desempenho_categorias_n1.csv", ["NIVEL_1"])
    categorias_n2 = cruzar_desempenho_categoria(
        categorias_n2,
        "desempenho_categorias_n2.csv",
        ["NIVEL_1", "NIVEL_2"],
    )
    categorias_n3 = cruzar_desempenho_categoria(
        categorias_n3,
        "desempenho_categorias_n3.csv",
        ["NIVEL_1", "NIVEL_2", "NIVEL_3"],
    )
    lojas = cruzar_desempenho_loja(lojas)

    categorias_n1 = adicionar_ranking_reposicao(categorias_n1)
    categorias_n2 = adicionar_ranking_reposicao(categorias_n2)
    categorias_n3 = adicionar_ranking_reposicao(categorias_n3)
    lojas = adicionar_ranking_reposicao(lojas)
    categoria_loja = adicionar_ranking_reposicao(categoria_loja)
    priorizacao = montar_priorizacao(categoria_loja)
    recomendacoes = gerar_recomendacoes_melhoria()

    print("Validando reconciliacoes numericas...")
    validacoes = validar_etapa4(
        cobertura,
        categorias_n1,
        categorias_n2,
        categorias_n3,
        lojas,
        categoria_loja,
        priorizacao,
    )

    print("Salvando arquivos auditaveis...")
    salvar_csv(categorias_n1, "cobertura_categorias_n1.csv")
    salvar_csv(categorias_n2, "cobertura_categorias_n2.csv")
    salvar_csv(categorias_n3, "cobertura_categorias_n3.csv")
    salvar_csv(lojas, "cobertura_lojas.csv")
    salvar_csv(categoria_loja, "cobertura_categoria_loja.csv")
    salvar_csv(priorizacao, "priorizacao_reposicao_categoria_loja.csv")
    salvar_csv(recomendacoes, "recomendacoes_melhoria.csv")
    salvar_csv(validacoes, "validacoes_etapa4.csv")

    resumo = gerar_resumo(cobertura, categorias_n1, lojas, priorizacao, validacoes)
    (OUT / "resumo_etapa4.md").write_text(resumo, encoding="utf-8")
    (OUT / "documentacao_tecnica_etapa4.md").write_text(gerar_documentacao_tecnica(), encoding="utf-8")

    print("\n--- Destaques Etapa 4 ---")
    risco = cobertura[cobertura["STATUS_ESTOQUE"].isin(STATUS_RISCO)]
    print(f"Pares totais: {len(cobertura):,}")
    print(f"Pares em ruptura/critico: {len(risco):,} ({len(risco) / len(cobertura) * 100:.1f}%)")
    print(f"Receita historica em risco: R$ {risco['RECEITA_TOTAL'].sum() / 1e6:.1f}M")
    print(f"Validacoes OK: {(validacoes['STATUS'] == 'OK').sum()}/{len(validacoes)}")

    print("\n[OK] Arquivos salvos em outputs/etapa4/")
    for path in sorted(OUT.glob("*")):
        print(f"  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
