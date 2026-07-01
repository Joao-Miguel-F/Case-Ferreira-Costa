"""
etapa7_recomendacoes_finais.py
==============================
Etapa 7 - Recomendacoes finais e plano de execucao comercial

Objetivos
---------
1. Consolidar as analises das Etapas 3-6 em recomendacoes acionaveis, sem
   recalcular base crua: promover/queimar estoque, descontinuar, reprecificar e
   comprar.
2. Classificar cada par loja x SKU nas quatro acoes, guardando todos os sinais
   disparados e atribuindo UMA acao primaria por precedencia para nao dupla
   contar capital/quantidade.
3. Separar sempre os tres universos (REDE_COMPLETA, rede fisica sem Loja 93 e
   Loja 93/B2B), com os totais fechando em REDE_COMPLETA.
4. Tratar financeiro (capital imobilizado, valor de encalhe, investimento de
   recompra) apenas quando ha custo valido na Etapa 5. Sem custo -> NaO avaliado
   (NaN), nunca zero.
5. Persistir fila priorizada, agregacoes, validacoes, autoaudit, resumo e
   documentacao tecnica em arquivos auditaveis.

Fontes consumidas (reaproveitadas, nao recalculadas)
----------------------------------------------------
- outputs/etapa6/plano_compras_sku_loja.csv : base loja x SKU ja com status de
  cobertura recalculado por universo (corrige a Loja 93), giro, curva ABC
  (com fallback auditavel da rede completa para Loja 93 quando necessario),
  custo, margem e a decisao de COMPRAR (QTD_RECOMENDADA_ARM).
- outputs/etapa6/priorizacao_compras.csv    : faixa de prioridade da compra.
- outputs/etapa5/candidatos_repricing.csv   : candidatos a REPRECIFICAR
  (loja x SKU x embalagem), com separacao entre sinal de margem auditavel
  (tem custo e margem baixa/negativa) e sinal de preco/lista (nao exige custo).
- outputs/etapa3/impacto_loja93.csv         : reconciliacao de receita por
  universo (checagem de que nenhum par foi perdido/duplicado).

Logica de classificacao das acoes
----------------------------------
- DESCONTINUAR : par em SEM VENDA com estoque parado (> 0), curva ABC conhecida
  e curva ABC != A.
  Guarda-corpo (autoaudit): SKU curva A nunca e descontinuado so por giro baixo
  recente; item sem curva tambem nao e descontinuado automaticamente. Ambos sao
  roteados para PROMOVER (escoar/transferir/revisar cadastro).
- PROMOVER     : estoque encalhado que ainda gira (STATUS SAUDAVEL com cobertura
  acima de LIMITE_ENCALHE_DIAS) ou campeao curva A parado (guarda-corpo acima).
- REPRECIFICAR : candidatos da Etapa 5 (faixa ALTA/MEDIA), separando sinal de
  margem auditavel (item com custo e margem baixa/negativa) de sinal de
  preco/lista (desconto alto ou preco fora da faixa, com ou sem custo).
- COMPRAR      : fila de compra da Etapa 6 (QTD_RECOMENDADA_ARM > 0).

Precedencia da acao primaria: DESCONTINUAR > PROMOVER > REPRECIFICAR > COMPRAR.
Nao se investe em recompra de item a delistar/liquidar e margem negativa se
corrige antes de comprar. A fila de execucao usa a acao primaria (cada par uma
vez); as reconciliacoes com as etapas-fonte usam os sinais (um par pode disparar
mais de um sinal).

Saidas
------
outputs/etapa7/recomendacoes_sku_loja.csv
outputs/etapa7/recomendacoes_acao_universo.csv
outputs/etapa7/recomendacoes_categoria_n1.csv
outputs/etapa7/recomendacoes_lojas.csv
outputs/etapa7/reprecificacao_candidatos.csv
outputs/etapa7/priorizacao_acoes.csv
outputs/etapa7/recomendacoes_melhoria.csv
outputs/etapa7/validacoes_etapa7.csv
outputs/etapa7/autoaudit_etapa7.csv
outputs/etapa7/resumo_etapa7.md
outputs/etapa7/documentacao_tecnica_etapa7.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from utils import LOJA_ATACADO, OUTPUTS  # noqa: E402


OUT = OUTPUTS / "etapa7"
OUT.mkdir(parents=True, exist_ok=True)

E3 = OUTPUTS / "etapa3"
E5 = OUTPUTS / "etapa5"
E6 = OUTPUTS / "etapa6"

UNIVERSO_COMPLETO = "REDE_COMPLETA"
UNIVERSO_FISICO = "REDE_FISICA_SEM_LOJA93"
ESCOPO_LOJA93 = "LOJA_93_ATACADO_B2B"

# Estoque que cobre mais de LIMITE_ENCALHE_DIAS de venda media e tratado como
# excesso/encalhe candidato a promocao. 180 = dobro do horizonte de compra da
# Etapa 6 (90 dias); acima disso o capital fica parado alem do trimestre alvo.
LIMITE_ENCALHE_DIAS = 180

# Precedencia da acao primaria (indice menor = maior prioridade de rotulo).
PRECEDENCIA_ACOES = ["DESCONTINUAR", "PROMOVER", "REPRECIFICAR", "COMPRAR"]
PESO_FAIXA = {"ALTA": 3, "MEDIA": 2, "BAIXA": 1}


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_div(numerador, denominador):
    num = np.asarray(numerador, dtype=float)
    den = np.asarray(denominador, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        resultado = np.divide(num, den)
    return np.where(den != 0, resultado, np.nan)


def fmt_brl_milhao(valor: float) -> str:
    if pd.isna(valor):
        return "sem custo"
    return f"R$ {valor / 1e6:,.1f}M".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_num(valor: float) -> str:
    if pd.isna(valor):
        return "0"
    return f"{valor:,.0f}".replace(",", ".")


def fmt_pct(valor: float) -> str:
    if pd.isna(valor):
        return "n/d"
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


# ── 1. Base de recomendacao (reaproveita Etapa 6) ─────────────────────────────

def carregar_base() -> pd.DataFrame:
    """Le a base loja x SKU da Etapa 6 (status ja recalculado por universo)."""
    base = pd.read_csv(E6 / "plano_compras_sku_loja.csv", encoding="utf-8-sig")
    base = aplicar_fallback_curva_abc(base)

    prio6 = pd.read_csv(E6 / "priorizacao_compras.csv", encoding="utf-8-sig")
    prio6 = prio6[["UNIVERSO_OPERACIONAL", "COD_EMPRESA", "CODIGO", "FAIXA_PRIORIDADE"]].rename(
        columns={"FAIXA_PRIORIDADE": "FAIXA_COMPRA_ETAPA6"}
    )
    base = base.merge(
        prio6,
        on=["UNIVERSO_OPERACIONAL", "COD_EMPRESA", "CODIGO"],
        how="left",
        validate="one_to_one",
    )
    return base


def aplicar_fallback_curva_abc(base: pd.DataFrame) -> pd.DataFrame:
    """Preenche curva ABC da Loja 93 com a rede completa quando a Etapa 6 ainda
    nao trouxer curva operacional propria.

    A Etapa 3 materializa ranking ABC para rede completa e rede fisica. Como a
    Loja 93 e segregada operacionalmente na Etapa 6/7, usamos a curva da rede
    completa como guarda-corpo conservador contra descontinuidade indevida.
    """
    d = base.copy()
    if "CURVA_ABC_ORIGEM" not in d.columns:
        d["CURVA_ABC_ORIGEM"] = np.where(d["CURVA_ABC_RECEITA"].notna(), "UNIVERSO_OPERACIONAL", "AUSENTE")

    rank = pd.read_csv(E3 / "ranking_produtos_receita.csv", encoding="utf-8-sig")
    rank = rank[rank["UNIVERSO"] == UNIVERSO_COMPLETO][
        ["CODIGO", "CURVA_ABC_RECEITA", "RANK_RECEITA"]
    ].rename(
        columns={
            "CURVA_ABC_RECEITA": "CURVA_ABC_RECEITA_REDE_COMPLETA",
            "RANK_RECEITA": "RANK_RECEITA_REDE_COMPLETA",
        }
    )
    d = d.merge(rank, on="CODIGO", how="left", validate="many_to_one")
    fallback = (
        (d["UNIVERSO_OPERACIONAL"] == ESCOPO_LOJA93)
        & d["CURVA_ABC_RECEITA"].isna()
        & d["CURVA_ABC_RECEITA_REDE_COMPLETA"].notna()
    )
    d.loc[fallback, "CURVA_ABC_RECEITA"] = d.loc[fallback, "CURVA_ABC_RECEITA_REDE_COMPLETA"]
    d.loc[fallback, "RANK_RECEITA"] = d.loc[fallback, "RANK_RECEITA_REDE_COMPLETA"]
    d.loc[fallback, "CURVA_ABC_ORIGEM"] = "REDE_COMPLETA_FALLBACK_LOJA93"
    d["CURVA_ABC_ORIGEM"] = np.where(d["CURVA_ABC_RECEITA"].isna(), "AUSENTE", d["CURVA_ABC_ORIGEM"])
    return d.drop(columns=["CURVA_ABC_RECEITA_REDE_COMPLETA", "RANK_RECEITA_REDE_COMPLETA"])


def carregar_repricing() -> pd.DataFrame:
    """Colapsa os candidatos a repricing (loja x SKU x embalagem) para loja x SKU.

    Mantem a faixa mais alta e a uniao dos sinais de margem auditavel e de
    preco/lista. So considera faixa ALTA/MEDIA nos universos operacionais.
    """
    cand = pd.read_csv(E5 / "candidatos_repricing.csv", encoding="utf-8-sig")
    cand = cand[
        cand["FAIXA_PRIORIDADE"].isin(["ALTA", "MEDIA"])
        & cand["UNIVERSO"].isin([UNIVERSO_FISICO, ESCOPO_LOJA93])
    ].copy()

    cand["_SINAL_MARGEM_AUDITAVEL"] = (
        cand["CUSTO_MEDIO_ARM"].notna()
        & ((cand["MOTIVO_MARGEM_BAIXA"] == 1) | (cand["FLAG_MARGEM_NEGATIVA"] == 1))
    ).astype(int)
    cand["_SINAL_PRECO_LISTA"] = (
        (cand["MOTIVO_DESCONTO_ALTO"] == 1) | (cand["MOTIVO_PRECO_FORA_FAIXA"] == 1)
    ).astype(int)
    cand["_FAIXA_ORD"] = cand["FAIXA_PRIORIDADE"].map(PESO_FAIXA)

    agg = (
        cand.groupby(["UNIVERSO", "COD_EMPRESA", "CODIGO"])
        .agg(
            REPRICING_N_EMBALAGENS=("EMBALAGEM", "nunique"),
            REPRICING_FAIXA_ORD=("_FAIXA_ORD", "max"),
            REPRICING_SCORE=("SCORE_PRIORIDADE", "max"),
            SINAL_MARGEM_AUDITAVEL=("_SINAL_MARGEM_AUDITAVEL", "max"),
            SINAL_PRECO_LISTA=("_SINAL_PRECO_LISTA", "max"),
            REPRICING_RECEITA=("RECEITA", "sum"),
        )
        .reset_index()
        .rename(columns={"UNIVERSO": "UNIVERSO_OPERACIONAL"})
    )
    agg["REPRICING_FAIXA"] = np.where(agg["REPRICING_FAIXA_ORD"] == 3, "ALTA", "MEDIA")
    agg["FLAG_REPRECIFICAR"] = 1
    return agg.drop(columns=["REPRICING_FAIXA_ORD"])


# ── 2. Classificacao das acoes ────────────────────────────────────────────────

def classificar(base: pd.DataFrame, repricing: pd.DataFrame) -> pd.DataFrame:
    d = base.merge(
        repricing,
        on=["UNIVERSO_OPERACIONAL", "COD_EMPRESA", "CODIGO"],
        how="left",
        validate="one_to_one",
    )
    d["FLAG_REPRECIFICAR"] = d["FLAG_REPRECIFICAR"].fillna(0).astype(int)
    d["SINAL_MARGEM_AUDITAVEL"] = d["SINAL_MARGEM_AUDITAVEL"].fillna(0).astype(int)
    d["SINAL_PRECO_LISTA"] = d["SINAL_PRECO_LISTA"].fillna(0).astype(int)

    status = d["STATUS_ESTOQUE_RECALC"].astype(str)
    sem_curva = d["CURVA_ABC_RECEITA"].isna()
    curva = d["CURVA_ABC_RECEITA"].fillna("").astype(str)
    parado = (status == "SEM VENDA") & (d["ESTOQUE_PROJ"] > 0)

    # Guarda-corpo: SKU curva A ou sem curva nao e descontinuado automaticamente.
    d["FLAG_CURVA_ABC_AUSENTE"] = sem_curva.astype(int)
    d["FLAG_PROTEGIDO_CAMPEAO"] = (parado & (curva == "A")).astype(int)
    d["FLAG_PROTEGIDO_SEM_CURVA"] = (parado & sem_curva).astype(int)
    d["FLAG_DESCONTINUAR"] = (parado & (curva != "A") & (~sem_curva)).astype(int)

    excesso = (status == "SAUDAVEL") & (d["DIAS_COBERTURA_PROJ"] > LIMITE_ENCALHE_DIAS)
    d["FLAG_PROMOVER"] = (
        excesso | (d["FLAG_PROTEGIDO_CAMPEAO"] == 1) | (d["FLAG_PROTEGIDO_SEM_CURVA"] == 1)
    ).astype(int)

    d["FLAG_COMPRAR"] = (d["QTD_RECOMENDADA_ARM"] > 0).astype(int)

    d["FLAG_ALGUMA_ACAO"] = (
        d[["FLAG_DESCONTINUAR", "FLAG_PROMOVER", "FLAG_REPRECIFICAR", "FLAG_COMPRAR"]].sum(axis=1) > 0
    ).astype(int)

    d["ACAO_PRIMARIA"] = np.select(
        [
            d["FLAG_DESCONTINUAR"] == 1,
            d["FLAG_PROMOVER"] == 1,
            d["FLAG_REPRECIFICAR"] == 1,
            d["FLAG_COMPRAR"] == 1,
        ],
        PRECEDENCIA_ACOES,
        default="",
    )
    d["N_ACOES_SINALIZADAS"] = d[
        ["FLAG_DESCONTINUAR", "FLAG_PROMOVER", "FLAG_REPRECIFICAR", "FLAG_COMPRAR"]
    ].sum(axis=1)

    # Financeiro: so com custo valido; NaN (nao avaliado) != 0 (sem necessidade).
    custo_ok = d["FLAG_CUSTO_VALIDO"] == 1
    valor_estoque = np.where(custo_ok, d["ESTOQUE_PROJ"] * d["CUSTO_MEDIO_ARM"], np.nan)
    d["CAPITAL_IMOBILIZADO"] = np.where(d["FLAG_DESCONTINUAR"] == 1, valor_estoque, np.nan)
    d["VALOR_ESTOQUE_ENCALHE"] = np.where(d["FLAG_PROMOVER"] == 1, valor_estoque, np.nan)
    d["INVESTIMENTO_RECOMPRA"] = np.where(d["FLAG_COMPRAR"] == 1, d["INVESTIMENTO_ESTIMADO"], np.nan)

    # Valor financeiro atrelado a ACAO PRIMARIA (base das agregacoes -> sem dupla
    # contagem). REPRECIFICAR nao gera investimento: e sinal de preco, financeiro
    # nao auditavel sem custo -> permanece NaN.
    d["VALOR_ACAO_PRIMARIA"] = np.select(
        [
            d["ACAO_PRIMARIA"] == "DESCONTINUAR",
            d["ACAO_PRIMARIA"] == "PROMOVER",
            d["ACAO_PRIMARIA"] == "COMPRAR",
        ],
        [d["CAPITAL_IMOBILIZADO"], d["VALOR_ESTOQUE_ENCALHE"], d["INVESTIMENTO_RECOMPRA"]],
        default=np.nan,
    )
    d["TIPO_VALOR_ACAO"] = np.select(
        [
            d["ACAO_PRIMARIA"] == "DESCONTINUAR",
            d["ACAO_PRIMARIA"] == "PROMOVER",
            d["ACAO_PRIMARIA"] == "COMPRAR",
            d["ACAO_PRIMARIA"] == "REPRECIFICAR",
        ],
        [
            "CAPITAL_IMOBILIZADO_A_LIBERAR",
            "VALOR_ESTOQUE_ENCALHE_A_LIBERAR",
            "INVESTIMENTO_RECOMPRA",
            "SEM_VALOR_FINANCEIRO_SINAL_DE_PRECO",
        ],
        default="SEM_ACAO",
    )

    # Metrica de urgencia por acao (usada para a faixa dentro de cada acao).
    d["ORDER_METRIC"] = np.select(
        [
            d["ACAO_PRIMARIA"] == "COMPRAR",
            d["ACAO_PRIMARIA"] == "REPRECIFICAR",
            d["ACAO_PRIMARIA"] == "DESCONTINUAR",
            d["ACAO_PRIMARIA"] == "PROMOVER",
        ],
        [
            d["SCORE_PRIORIDADE"],
            d["REPRICING_SCORE"],
            d["CAPITAL_IMOBILIZADO"],
            d["VALOR_ESTOQUE_ENCALHE"],
        ],
        default=np.nan,
    )
    return d


def atribuir_faixa(acionavel: pd.DataFrame) -> pd.DataFrame:
    """Faixa ALTA/MEDIA/BAIXA por (universo operacional x acao primaria).

    Top 10% por urgencia = ALTA, ate 30% = MEDIA, restante = BAIXA (mesmos cortes
    da Etapa 6). Pares sem metrica de urgencia conhecida (ex.: sem custo em
    descontinuar/promover) recebem BAIXA.
    """
    d = acionavel.copy()
    d = d.sort_values(
        ["UNIVERSO_OPERACIONAL", "ACAO_PRIMARIA", "ORDER_METRIC", "RECEITA_TOTAL"],
        ascending=[True, True, False, False],
        na_position="last",
    ).reset_index(drop=True)
    d["FAIXA_PRIORIDADE"] = "BAIXA"
    d["RANK_ACAO"] = pd.NA
    com_metrica = d["ORDER_METRIC"].notna()
    d.loc[com_metrica, "RANK_ACAO"] = (
        d.loc[com_metrica].groupby(["UNIVERSO_OPERACIONAL", "ACAO_PRIMARIA"]).cumcount() + 1
    )
    total = d.loc[com_metrica].groupby(["UNIVERSO_OPERACIONAL", "ACAO_PRIMARIA"])["RANK_ACAO"].transform("max")
    limite_alta = np.maximum(1, np.ceil(total * 0.10))
    limite_media = np.maximum(limite_alta + 1, np.ceil(total * 0.30))
    d.loc[com_metrica, "FAIXA_PRIORIDADE"] = np.select(
        [
            d.loc[com_metrica, "RANK_ACAO"] <= limite_alta,
            d.loc[com_metrica, "RANK_ACAO"] <= limite_media,
        ],
        ["ALTA", "MEDIA"],
        default="BAIXA",
    )
    d["ACAO_RECOMENDADA"] = d.apply(texto_acao, axis=1)
    return d


def texto_acao(r: pd.Series) -> str:
    acao = r["ACAO_PRIMARIA"]
    if acao == "DESCONTINUAR":
        base = ("Avaliar descontinuacao/saida: estoque parado sem giro no periodo "
                "(capital imobilizado). Validar saldo fisico e obsolescencia antes de baixar.")
        return base if r["FLAG_CUSTO_VALIDO"] == 1 else base + " Custo ausente: capital nao mensurado."
    if acao == "PROMOVER":
        if r["FLAG_PROTEGIDO_CAMPEAO"] == 1:
            return ("Escoar/transferir: SKU de alta receita historica (curva A) parado nesta loja; "
                    "priorizar transferencia entre lojas antes de promocao. Nao descontinuar.")
        if r["FLAG_PROTEGIDO_SEM_CURVA"] == 1:
            return ("Revisar antes de sair: SKU parado com curva ABC ausente; validar cadastro, saldo fisico "
                    "e historico comercial antes de promover/transferir ou descontinuar.")
        return ("Promover/queimar estoque: cobertura muito acima do giro; liberar capital com "
                "desconto controlado, respeitando a margem da Etapa 5.")
    if acao == "REPRECIFICAR":
        if r["SINAL_MARGEM_AUDITAVEL"] == 1:
            return ("Revisar preco/custo: sinal de margem baixa/negativa AUDITAVEL (item com custo na Etapa 5).")
        if r["FLAG_CUSTO_VALIDO"] == 1:
            return ("Alinhar preco/lista: sinal de desconto alto/preco fora da faixa da rede. Ha custo valido, "
                    "mas sem sinal de margem baixa/negativa; tratar como ajuste de preco/lista.")
        return ("Alinhar preco/lista: sinal de desconto alto/preco fora da faixa da rede. Sem custo -> "
                "margem nao auditavel; tratar como ajuste de preco/lista, nao de margem.")
    if acao == "COMPRAR":
        if r["FLAG_MARGEM_NEGATIVA"] == 1:
            return ("Recompor cobertura de 90 dias, MAS validar preco/margem antes: ha sinal de margem "
                    "negativa na Etapa 5.")
        if r["FLAG_CUSTO_VALIDO"] == 0:
            return ("Recompor cobertura de 90 dias; validar custo/fornecedor antes de orcar "
                    "(quantidade operacional sem investimento estimado).")
        return "Recompor cobertura de 90 dias, validando saldo fisico antes do pedido."
    return "Sem acao recomendada nesta rodada."


# ── 3. Agregacoes ─────────────────────────────────────────────────────────────

def _com_universos(acionavel: pd.DataFrame) -> pd.DataFrame:
    """Empilha rede fisica, Loja 93 e REDE_COMPLETA (uniao) para agregar."""
    fisico = acionavel[acionavel["UNIVERSO_OPERACIONAL"] == UNIVERSO_FISICO].copy()
    loja93 = acionavel[acionavel["UNIVERSO_OPERACIONAL"] == ESCOPO_LOJA93].copy()
    partes = []
    for universo, df in [
        (UNIVERSO_COMPLETO, acionavel),
        (UNIVERSO_FISICO, fisico),
        (ESCOPO_LOJA93, loja93),
    ]:
        tmp = df.copy()
        tmp["UNIVERSO"] = universo
        partes.append(tmp)
    return pd.concat(partes, ignore_index=True)


def agregar_acao_universo(acionavel: pd.DataFrame) -> pd.DataFrame:
    d = _com_universos(acionavel)
    grp = d.groupby(["UNIVERSO", "ACAO_PRIMARIA"], dropna=False)
    out = grp.agg(
        PARES=("CODIGO", "size"),
        SKUS=("CODIGO", "nunique"),
        LOJAS=("COD_EMPRESA", "nunique"),
        RECEITA_HISTORICA=("RECEITA_TOTAL", "sum"),
        PARES_COM_VALOR=("VALOR_ACAO_PRIMARIA", lambda s: int(s.notna().sum())),
        VALOR_FINANCEIRO_CONHECIDO=("VALOR_ACAO_PRIMARIA", lambda s: s.sum(min_count=1)),
    ).reset_index()
    out["PARES_SEM_VALOR"] = out["PARES"] - out["PARES_COM_VALOR"]
    out["COBERTURA_VALOR_PCT"] = safe_div(out["PARES_COM_VALOR"], out["PARES"]) * 100
    ordem = {a: i for i, a in enumerate(PRECEDENCIA_ACOES)}
    out["_ord"] = out["ACAO_PRIMARIA"].map(ordem)
    return out.sort_values(["UNIVERSO", "_ord"]).drop(columns="_ord").reset_index(drop=True)


def agregar_chaves(acionavel: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    d = _com_universos(acionavel)
    out = (
        d.groupby(["UNIVERSO", "ACAO_PRIMARIA", *keys], dropna=False)
        .agg(
            PARES=("CODIGO", "size"),
            SKUS=("CODIGO", "nunique"),
            RECEITA_HISTORICA=("RECEITA_TOTAL", "sum"),
            VALOR_FINANCEIRO_CONHECIDO=("VALOR_ACAO_PRIMARIA", lambda s: s.sum(min_count=1)),
        )
        .reset_index()
    )
    return out.sort_values(
        ["UNIVERSO", "ACAO_PRIMARIA", "PARES"], ascending=[True, True, False]
    ).reset_index(drop=True)


def fila_priorizada(acionavel: pd.DataFrame) -> pd.DataFrame:
    """Fila de execucao por universo operacional: banda de prioridade, depois
    precedencia de acao, depois urgencia."""
    d = acionavel.copy()
    d["_faixa_ord"] = d["FAIXA_PRIORIDADE"].map(PESO_FAIXA)
    d["_acao_ord"] = d["ACAO_PRIMARIA"].map({a: i for i, a in enumerate(PRECEDENCIA_ACOES)})
    d = d.sort_values(
        ["UNIVERSO_OPERACIONAL", "_faixa_ord", "_acao_ord", "ORDER_METRIC", "RECEITA_TOTAL"],
        ascending=[True, False, True, False, False],
        na_position="last",
    ).reset_index(drop=True)
    d["RANK_EXECUCAO"] = d.groupby("UNIVERSO_OPERACIONAL").cumcount() + 1
    return d.drop(columns=["_faixa_ord", "_acao_ord"])


# ── 4. Validacoes, autoaudit, textos ──────────────────────────────────────────

def validar(base: pd.DataFrame, acionavel: pd.DataFrame, acao_univ: pd.DataFrame,
            categorias: pd.DataFrame, lojas: pd.DataFrame, repricing: pd.DataFrame) -> pd.DataFrame:
    validacoes = []

    def add(nome, obs, esp, tol=1.0):
        dif = float(obs) - float(esp)
        validacoes.append({
            "VALIDACAO": nome,
            "OBSERVADO": float(obs),
            "ESPERADO": float(esp),
            "DIFERENCA": dif,
            "STATUS": "OK" if abs(dif) <= tol else "FALHA",
        })

    def add_bool(nome, cond):
        add(nome, 1.0 if cond else 0.0, 1.0, tol=0)

    # Receita total da base fecha com a Etapa 3 (nenhum par perdido/duplicado).
    imp = pd.read_csv(E3 / "impacto_loja93.csv", encoding="utf-8-sig").set_index("SEGMENTO")
    add("Receita base vs Etapa 3 - rede completa", base["RECEITA_TOTAL"].sum(),
        imp.loc[UNIVERSO_COMPLETO, "RECEITA"], tol=1e3)
    add("Receita base vs Etapa 3 - rede fisica",
        base.loc[base["UNIVERSO_OPERACIONAL"] == UNIVERSO_FISICO, "RECEITA_TOTAL"].sum(),
        imp.loc[UNIVERSO_FISICO, "RECEITA"], tol=1e3)
    add("Receita base vs Etapa 3 - Loja 93",
        base.loc[base["UNIVERSO_OPERACIONAL"] == ESCOPO_LOJA93, "RECEITA_TOTAL"].sum(),
        imp.loc[ESCOPO_LOJA93, "RECEITA"], tol=1e3)

    # REDE_COMPLETA = fisica + Loja 93 (pares por acao).
    piv = acao_univ.pivot_table(index="ACAO_PRIMARIA", columns="UNIVERSO", values="PARES",
                                aggfunc="sum", fill_value=0)
    for acao in PRECEDENCIA_ACOES:
        if acao in piv.index:
            add(f"REDE_COMPLETA = fisica + Loja 93 (pares {acao})",
                piv.loc[acao, UNIVERSO_COMPLETO],
                piv.loc[acao].get(UNIVERSO_FISICO, 0) + piv.loc[acao].get(ESCOPO_LOJA93, 0), tol=0)

    # Anti-dupla-contagem: cada par acionavel tem exatamente uma acao primaria.
    add_bool("Cada par acionavel tem uma unica acao primaria",
             bool((acionavel["ACAO_PRIMARIA"] != "").all())
             and int(acionavel[["COD_EMPRESA", "CODIGO", "UNIVERSO_OPERACIONAL"]].duplicated().sum()) == 0)
    add("Soma de pares por acao = total de pares acionaveis",
        int(acao_univ.loc[acao_univ["UNIVERSO"] == UNIVERSO_COMPLETO, "PARES"].sum()),
        len(acionavel), tol=0)

    # Reconciliacao de sinais com as etapas-fonte.
    add("Sinal COMPRAR = pares com compra na Etapa 6",
        int((base["FLAG_COMPRAR"] == 1).sum() if "FLAG_COMPRAR" in base else acionavel["FLAG_COMPRAR"].sum()),
        int((base["QTD_RECOMENDADA_ARM"] > 0).sum()), tol=0)
    esperado_repricing = len(repricing)
    add("Sinal REPRECIFICAR = candidatos ALTA/MEDIA (loja x SKU) casados na base",
        int((acionavel["FLAG_REPRECIFICAR"] == 1).sum()), esperado_repricing, tol=0)

    # Guarda-corpo: nenhum SKU curva A entra em DESCONTINUAR.
    add("Nenhum par curva A foi descontinuado",
        int(((acionavel["ACAO_PRIMARIA"] == "DESCONTINUAR")
             & (acionavel["CURVA_ABC_RECEITA"].astype(str) == "A")).sum()), 0, tol=0)
    add("Nenhum par com curva ABC ausente foi descontinuado",
        int(((acionavel["ACAO_PRIMARIA"] == "DESCONTINUAR")
             & (acionavel["FLAG_CURVA_ABC_AUSENTE"] == 1)).sum()), 0, tol=0)
    add_bool("Campeao curva A parado roteado para PROMOVER (nao DESCONTINUAR)",
             bool((acionavel.loc[acionavel["FLAG_PROTEGIDO_CAMPEAO"] == 1, "ACAO_PRIMARIA"] == "PROMOVER").all()))
    add_bool("Par parado sem curva ABC roteado para PROMOVER/revisao",
             bool((acionavel.loc[acionavel["FLAG_PROTEGIDO_SEM_CURVA"] == 1, "ACAO_PRIMARIA"] == "PROMOVER").all()))
    add_bool("Loja 93 acionavel possui curva ABC de guarda-corpo",
             bool(acionavel.loc[acionavel["UNIVERSO_OPERACIONAL"] == ESCOPO_LOJA93, "CURVA_ABC_RECEITA"].notna().all()))

    # Prioridade: sem metrica de urgencia conhecida nao pode subir para ALTA/MEDIA.
    add_bool("Pares sem metrica de prioridade ficam em BAIXA",
             bool(acionavel.loc[acionavel["ORDER_METRIC"].isna(), "FAIXA_PRIORIDADE"].eq("BAIXA").all()))

    # Financeiro so com custo valido (NaN != 0).
    add_bool("Capital/encalhe/investimento nao imputado sem custo",
             bool(acionavel.loc[acionavel["FLAG_CUSTO_VALIDO"] == 0, "VALOR_ACAO_PRIMARIA"].isna().all()))
    add_bool("Repricing nao gera valor financeiro (sinal de preco)",
             bool(acionavel.loc[acionavel["ACAO_PRIMARIA"] == "REPRECIFICAR", "VALOR_ACAO_PRIMARIA"].isna().all()))
    add_bool("Texto de repricing sem custo somente quando custo ausente",
             bool(not acionavel.loc[
                 (acionavel["ACAO_PRIMARIA"] == "REPRECIFICAR")
                 & (acionavel["FLAG_CUSTO_VALIDO"] == 1),
                 "ACAO_RECOMENDADA",
             ].astype(str).str.contains("Sem custo", case=False, na=False).any()))

    # Loja 93 fora do universo fisico.
    add_bool("Loja 93 fora do universo operacional fisico",
             bool(not ((acionavel["UNIVERSO_OPERACIONAL"] == UNIVERSO_FISICO)
                       & (acionavel["COD_EMPRESA"] == LOJA_ATACADO)).any()))

    # Agregacoes fecham pares por universo.
    add_bool("Categorias fecham pares por universo",
             bool(np.allclose(categorias.groupby("UNIVERSO")["PARES"].sum().sort_index(),
                              acao_univ.groupby("UNIVERSO")["PARES"].sum().sort_index())))
    add_bool("Lojas fecham pares por universo",
             bool(np.allclose(lojas.groupby("UNIVERSO")["PARES"].sum().sort_index(),
                              acao_univ.groupby("UNIVERSO")["PARES"].sum().sort_index())))
    return pd.DataFrame(validacoes)


def construir_autoaudit(acionavel: pd.DataFrame) -> pd.DataFrame:
    protegidos = int((acionavel["FLAG_PROTEGIDO_CAMPEAO"] == 1).sum())
    protegidos_sem_curva = int((acionavel["FLAG_PROTEGIDO_SEM_CURVA"] == 1).sum())
    descont = int((acionavel["ACAO_PRIMARIA"] == "DESCONTINUAR").sum())
    reprec_prim = acionavel[acionavel["ACAO_PRIMARIA"] == "REPRECIFICAR"]
    reprec_margem_auditavel = int((reprec_prim["SINAL_MARGEM_AUDITAVEL"] == 1).sum())
    reprec_preco_com_custo = int(
        ((reprec_prim["SINAL_PRECO_LISTA"] == 1)
         & (reprec_prim["FLAG_CUSTO_VALIDO"] == 1)
         & (reprec_prim["SINAL_MARGEM_AUDITAVEL"] == 0)).sum()
    )
    reprec_preco_sem_custo = int(
        ((reprec_prim["SINAL_PRECO_LISTA"] == 1)
         & (reprec_prim["FLAG_CUSTO_VALIDO"] == 0)).sum()
    )
    loja93_acionavel = int((acionavel["COD_EMPRESA"] == LOJA_ATACADO).sum())
    multi = int((acionavel["N_ACOES_SINALIZADAS"] > 1).sum())
    return pd.DataFrame([
        {
            "RISCO": "Descontinuar campeao historico so por giro baixo recente",
            "COMO_PODERIA_ERRAR": "Marcar para saida um SKU curva A parado nesta loja, ignorando que ele "
                                  "e um dos maiores em receita historica da rede, ou descontinuar item com "
                                  "curva ausente como se fosse comprovadamente B/C.",
            "CONTROLE_APLICADO": "Curva A parado nunca entra em DESCONTINUAR; curva ausente tambem bloqueia "
                                 "descontinue automatico. Ambos sao roteados para PROMOVER/revisao.",
            "EVIDENCIA": f"{protegidos} pares curva A parados protegidos e roteados para PROMOVER; "
                         f"{protegidos_sem_curva} pares sem curva protegidos; "
                         f"{descont} pares (curva B/C conhecida) restam como DESCONTINUAR.",
            "RISCO_REMANESCENTE": "Curva B/C parado ainda pode ter sazonalidade longa; validar antes de baixar.",
        },
        {
            "RISCO": "Promover/reprecificar item como se a margem fosse conhecida sem evidencia",
            "COMO_PODERIA_ERRAR": "Tratar desconto/preco fora da faixa como problema de margem e prometer ganho "
                                  "financeiro sem custo auditavel.",
            "CONTROLE_APLICADO": "Repricing separa SINAL_MARGEM_AUDITAVEL (tem custo) de SINAL_PRECO_LISTA "
                                 "(nao exige custo) e nao gera valor financeiro. Promover so estima capital com custo valido.",
            "EVIDENCIA": f"{reprec_margem_auditavel} pares de repricing primario com sinal de margem auditavel; "
                         f"{reprec_preco_com_custo} com custo valido mas apenas sinal de preco/lista; "
                         f"{reprec_preco_sem_custo} sem custo e apenas sinal de preco/lista.",
            "RISCO_REMANESCENTE": "Preco de lista pode estar desatualizado; desconto efetivo e aproximacao.",
        },
        {
            "RISCO": "Misturar a Loja 93 (atacado/B2B) nas recomendacoes de varejo",
            "COMO_PODERIA_ERRAR": "Usar status/demanda da rede fisica para a Loja 93 e jogar seus pares nas "
                                  "medias de varejo, distorcendo descontinuacao e promocao.",
            "CONTROLE_APLICADO": "Universo operacional segrega a Loja 93; a base herda o status recalculado da "
                                 "Etapa 6 (demanda B2B propria). REDE_COMPLETA e a soma reconciliada.",
            "EVIDENCIA": f"{loja93_acionavel} pares acionaveis sao da Loja 93 e ficam no escopo "
                         f"{ESCOPO_LOJA93}, nunca no universo fisico.",
            "RISCO_REMANESCENTE": "Pedidos B2B sao intermitentes; media historica suaviza picos.",
        },
        {
            "RISCO": "Dupla contagem de um par que dispara mais de uma acao",
            "COMO_PODERIA_ERRAR": "Somar o mesmo par em capital imobilizado E investimento de recompra, inflando "
                                  "o valor total das recomendacoes.",
            "CONTROLE_APLICADO": "Cada par recebe UMA acao primaria por precedencia "
                                 "(DESCONTINUAR > PROMOVER > REPRECIFICAR > COMPRAR); o valor financeiro agregado "
                                 "usa so a acao primaria. Os demais sinais ficam como flags.",
            "EVIDENCIA": f"{multi} pares disparam mais de um sinal; todos entram uma unica vez na fila via "
                         f"acao primaria.",
            "RISCO_REMANESCENTE": "A leitura por sinal (nao por acao primaria) pode contar um par em mais de uma acao; "
                                  "por isso as agregacoes usam a acao primaria.",
        },
    ])


def gerar_recomendacoes_melhoria() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "PRIORIDADE": "ALTA",
            "TEMA": "Custo para decisao financeira",
            "LIMITACAO_OU_PROBLEMA": "Capital imobilizado, valor de encalhe e investimento so existem para o "
                                     "subconjunto com custo valido (Etapa 5, ~16% da receita).",
            "RISCO_ANALITICO": "O valor financeiro das recomendacoes subestima o total se lido como budget fechado.",
            "RECOMENDACAO": "Completar custo por SKU/fornecedor para mensurar capital a liberar e desembolso de recompra.",
        },
        {
            "PRIORIDADE": "ALTA",
            "TEMA": "Saldo fisico e obsolescencia",
            "LIMITACAO_OU_PROBLEMA": "Estoque projetado nao inclui inventario fisico, transferencias nem validade/obsolescencia.",
            "RISCO_ANALITICO": "Descontinuar/promover por estoque projetado pode agir sobre saldo que nao existe fisicamente.",
            "RECOMENDACAO": "Validar saldo fisico e obsolescencia dos itens ALTA antes de baixar ou promover.",
        },
        {
            "PRIORIDADE": "MEDIA",
            "TEMA": "Sazonalidade e giro recente",
            "LIMITACAO_OU_PROBLEMA": "Giro usa media dos meses com venda; itens sazonais podem parecer parados fora de estacao.",
            "RISCO_ANALITICO": "Descontinuar item sazonal na baixa estacao ou promover na alta.",
            "RECOMENDACAO": "Cruzar com a sazonalidade da Etapa 3 antes de decidir saida/promocao.",
        },
        {
            "PRIORIDADE": "MEDIA",
            "TEMA": "Politica comercial de execucao",
            "LIMITACAO_OU_PROBLEMA": "Faltam profundidade de desconto, elasticidade e lead time de reposicao por categoria.",
            "RISCO_ANALITICO": "A fila prioriza o que fazer, mas nao dimensiona quanto descontar nem o lote de recompra.",
            "RECOMENDACAO": "Definir politica de desconto/elasticidade por categoria e lote/lead time para converter a fila em execucao.",
        },
    ])


# ── 5. Resumo e documentacao ──────────────────────────────────────────────────

def _linha_acao(acao_univ: pd.DataFrame, universo: str, acao: str) -> pd.Series:
    m = (acao_univ["UNIVERSO"] == universo) & (acao_univ["ACAO_PRIMARIA"] == acao)
    if m.any():
        return acao_univ[m].iloc[0]
    return pd.Series({"PARES": 0, "SKUS": 0, "VALOR_FINANCEIRO_CONHECIDO": np.nan,
                      "COBERTURA_VALOR_PCT": np.nan, "RECEITA_HISTORICA": 0.0})


def gerar_resumo(acao_univ: pd.DataFrame, fila: pd.DataFrame, autoaudit: pd.DataFrame,
                 validacoes: pd.DataFrame) -> str:
    def linha(universo, acao):
        r = _linha_acao(acao_univ, universo, acao)
        valor = "nao aplicavel" if acao == "REPRECIFICAR" else fmt_brl_milhao(r["VALOR_FINANCEIRO_CONHECIDO"])
        return (f"- **{acao}** ({universo}): {fmt_num(r['PARES'])} pares, "
                f"valor conhecido {valor} "
                f"(cobertura de custo {fmt_pct(r['COBERTURA_VALOR_PCT'])}).")

    alta_fis = fila[(fila["UNIVERSO_OPERACIONAL"] == UNIVERSO_FISICO)
                    & (fila["FAIXA_PRIORIDADE"] == "ALTA")]
    alta_por_acao = alta_fis["ACAO_PRIMARIA"].value_counts().to_dict()
    reprec_prim = fila[fila["ACAO_PRIMARIA"] == "REPRECIFICAR"]
    reprec_margem = int((reprec_prim["SINAL_MARGEM_AUDITAVEL"] == 1).sum())
    reprec_preco_com_custo = int(
        ((reprec_prim["SINAL_PRECO_LISTA"] == 1)
         & (reprec_prim["FLAG_CUSTO_VALIDO"] == 1)
         & (reprec_prim["SINAL_MARGEM_AUDITAVEL"] == 0)).sum()
    )
    reprec_preco_sem_custo = int(
        ((reprec_prim["SINAL_PRECO_LISTA"] == 1)
         & (reprec_prim["FLAG_CUSTO_VALIDO"] == 0)).sum()
    )
    tot_ok = int((validacoes["STATUS"] == "OK").sum())

    return f"""# Etapa 7 - Recomendacoes finais e plano de execucao comercial

## Leitura executiva

A Etapa 7 e a sintese de decisao: consome os artefatos auditaveis das Etapas 3-6
e classifica cada par loja x SKU em uma de quatro acoes comerciais, sem recalcular
base crua. Cada par recebe UMA acao primaria por precedencia
(DESCONTINUAR > PROMOVER > REPRECIFICAR > COMPRAR) para nao dupla contar capital
ou quantidade. Os tres universos ficam segregados e fecham em REDE_COMPLETA.

### Rede fisica sem Loja 93

{linha(UNIVERSO_FISICO, "COMPRAR")}
{linha(UNIVERSO_FISICO, "REPRECIFICAR")}
{linha(UNIVERSO_FISICO, "PROMOVER")}
{linha(UNIVERSO_FISICO, "DESCONTINUAR")}

### Loja 93 (atacado/B2B)

{linha(ESCOPO_LOJA93, "COMPRAR")}
{linha(ESCOPO_LOJA93, "REPRECIFICAR")}
{linha(ESCOPO_LOJA93, "PROMOVER")}
{linha(ESCOPO_LOJA93, "DESCONTINUAR")}

### Fila de execucao (prioridade ALTA, rede fisica)

- {fmt_num(len(alta_fis))} pares de prioridade ALTA na rede fisica, distribuidos por acao: {alta_por_acao}.

## Principais achados

- O plano e mais operacional do que financeiro: capital imobilizado, valor de
  encalhe e investimento de recompra so sao mensurados no subconjunto com custo
  valido (Etapa 5). Sem custo o par permanece na fila como sinal, mas sem valor.
- O guarda-corpo de descontinuacao protege os campeoes de receita: SKUs curva A
  parados sao roteados para escoar/transferir, nunca para saida do sortimento.
- Repricing separa o que e problema de margem auditavel ({fmt_num(reprec_margem)}
  pares primarios) do que e sinal de preco/lista: {fmt_num(reprec_preco_com_custo)}
  com custo valido, mas sem margem baixa/negativa, e {fmt_num(reprec_preco_sem_custo)}
  sem custo.
- A Loja 93 entra com escopo proprio e status B2B recalculado; nunca se mistura
  as medias do varejo. REDE_COMPLETA e a soma reconciliada dos dois escopos.

## Limitacoes e riscos de interpretacao

- Estoque projetado nao e contagem fisica: descontinuar/promover exige validar
  saldo e obsolescencia antes de agir.
- Giro usa media dos meses com venda; itens sazonais podem parecer parados fora
  de estacao. Cruzar com a sazonalidade da Etapa 3.
- A fila diz o que fazer e em que ordem, nao quanto descontar nem o lote de
  recompra; falta politica comercial por categoria.
- Valor financeiro conhecido nao e budget total; exclui itens sem custo.

## Autoaudit / revisao critica

{markdown_table(autoaudit[["RISCO", "CONTROLE_APLICADO", "EVIDENCIA"]])}

## Validacoes

- {tot_ok}/{len(validacoes)} validacoes OK; status geral: `{ 'OK' if tot_ok == len(validacoes) else 'FALHA' }`.
- Receita da base fecha com a Etapa 3; REDE_COMPLETA = rede fisica + Loja 93 por acao.
- Sinais de COMPRAR e REPRECIFICAR reconciliam com as Etapas 6 e 5.
- Nenhum curva A ou curva ausente foi descontinuado; Loja 93 tem curva de guarda-corpo.
- Pares sem metrica de prioridade ficam em BAIXA; financeiro nunca imputado sem custo.

## Proximos passos

1. Validar saldo fisico e obsolescencia dos itens ALTA de descontinuar/promover.
2. Completar custo por SKU para transformar capital e recompra em valores fechados.
3. Definir profundidade de desconto/elasticidade por categoria para a promocao.
4. Levar a fila priorizada para a apresentacao executiva (Etapa 8).
"""


def gerar_documentacao_tecnica() -> str:
    return f"""# Documentacao tecnica - Etapa 7

## Papel da etapa

Sintese de decisao. Nao le base crua: consome os CSVs auditaveis das Etapas 3-6
e a base loja x SKU da Etapa 6 (que ja traz status recalculado por universo,
giro, curva, custo e margem). Para a Loja 93, quando a Etapa 6 nao traz curva
operacional propria, a Etapa 7 aplica fallback auditavel da curva da rede
completa como guarda-corpo conservador.

## Entradas

- `outputs/etapa6/plano_compras_sku_loja.csv`: base loja x SKU nos universos
  operacionais, com `STATUS_ESTOQUE_RECALC`, `DIAS_COBERTURA_PROJ`, `ESTOQUE_PROJ`,
  `CURVA_ABC_RECEITA`, `CURVA_ABC_ORIGEM`, `CUSTO_MEDIO_ARM`, flags de margem e a decisao de compra.
- `outputs/etapa6/priorizacao_compras.csv`: faixa de prioridade da compra.
- `outputs/etapa5/candidatos_repricing.csv`: candidatos a repricing por
  loja x SKU x embalagem, com motivos de margem, desconto e preco fora da faixa.
- `outputs/etapa3/impacto_loja93.csv`: receita por universo para reconciliacao.

## Regras de classificacao

- DESCONTINUAR: `STATUS_ESTOQUE_RECALC == 'SEM VENDA'`, `ESTOQUE_PROJ > 0`,
  `CURVA_ABC_RECEITA` conhecida e `CURVA_ABC_RECEITA != 'A'`. Curva A parado vira
  `FLAG_PROTEGIDO_CAMPEAO`; curva ausente vira `FLAG_PROTEGIDO_SEM_CURVA`. Ambos
  vao para PROMOVER/revisao, nunca para descontinue automatico.
- PROMOVER: `STATUS_ESTOQUE_RECALC == 'SAUDAVEL'` com
  `DIAS_COBERTURA_PROJ > {LIMITE_ENCALHE_DIAS}` (excesso/encalhe) ou campeao
  protegido.
- REPRECIFICAR: candidato da Etapa 5 em faixa ALTA/MEDIA (colapsado de embalagem
  para loja x SKU). `SINAL_MARGEM_AUDITAVEL` exige custo e margem baixa/negativa;
  `SINAL_PRECO_LISTA` aponta desconto/preco fora da faixa e nao exige custo.
- COMPRAR: `QTD_RECOMENDADA_ARM > 0` na Etapa 6.

## Acao primaria e nao dupla contagem

Um par pode disparar mais de um sinal. A `ACAO_PRIMARIA` segue a precedencia
DESCONTINUAR > PROMOVER > REPRECIFICAR > COMPRAR. As agregacoes financeiras usam
so `VALOR_ACAO_PRIMARIA`, garantindo que nenhum par seja contado em duas acoes.
As reconciliacoes com as etapas-fonte usam os sinais (`FLAG_*`), nao a acao
primaria, por isso os numeros de sinal batem com as Etapas 5 e 6.

## Financeiro

- Capital imobilizado (descontinuar) e valor de encalhe (promover) =
  `ESTOQUE_PROJ * CUSTO_MEDIO_ARM`, apenas com custo valido.
- Investimento de recompra (comprar) = `INVESTIMENTO_ESTIMADO` da Etapa 6.
- REPRECIFICAR nao gera valor financeiro (sinal de preco). Sem custo -> NaN
  (nao avaliado), nunca zero.

## Prioridade

Faixa ALTA/MEDIA/BAIXA por (universo x acao): top 10% por urgencia = ALTA, ate
30% = MEDIA, restante = BAIXA, calculado apenas entre pares com metrica de
urgencia conhecida. Pares sem metrica (ex.: descontinuar/promover sem custo)
ficam em BAIXA. Urgencia = score da Etapa 6 (comprar), score da Etapa 5
(repricing), capital imobilizado (descontinuar) e valor de encalhe (promover).
A fila de execucao ordena por banda de prioridade, precedencia de acao e
urgencia.

## Arquivos gerados

- `recomendacoes_sku_loja.csv`: detalhe loja x SKU com flags, acao primaria e valores.
- `recomendacoes_acao_universo.csv`: KPIs por universo x acao.
- `recomendacoes_categoria_n1.csv`: agregacao por categoria N1 x acao.
- `recomendacoes_lojas.csv`: agregacao por loja x acao.
- `reprecificacao_candidatos.csv`: candidatos a repricing por loja x SKU com sinais.
- `priorizacao_acoes.csv`: fila de execucao ranqueada com faixa ALTA/MEDIA/BAIXA.
- `validacoes_etapa7.csv`, `autoaudit_etapa7.csv`, `recomendacoes_melhoria.csv`.
- `resumo_etapa7.md`, `documentacao_tecnica_etapa7.md`.

## Riscos e falsos positivos

- Estoque projetado pode nao existir fisicamente (sem inventario/transferencias).
- Itens sazonais podem parecer parados fora de estacao.
- Valor financeiro conhecido subestima o total (so itens com custo).
- Repricing por preco/lista, com ou sem custo, nao prova margem baixa sem o sinal
  `SINAL_MARGEM_AUDITAVEL`.
"""


# ── 6. Persistencia ───────────────────────────────────────────────────────────

def salvar_csv(df: pd.DataFrame, nome: str) -> None:
    df.to_csv(OUT / nome, index=False, encoding="utf-8-sig", float_format="%.6f")


COLS_DETALHE = [
    "UNIVERSO_OPERACIONAL", "COD_EMPRESA", "CD_CIDADE", "CD_ESTADO", "FLAG_LOJA93",
    "CODIGO", "DESCRICAO", "NIVEL_1", "STATUS_ESTOQUE_RECALC", "DIAS_COBERTURA_PROJ",
    "ESTOQUE_PROJ", "VENDA_MEDIA_MES_PROJECAO", "RECEITA_TOTAL", "CURVA_ABC_RECEITA",
    "CURVA_ABC_ORIGEM", "RANK_RECEITA", "CUSTO_MEDIO_ARM", "FLAG_CUSTO_VALIDO", "MARGEM_BRUTA_PCT_COM_CUSTO",
    "FLAG_MARGEM_VALIDA", "FLAG_MARGEM_NEGATIVA", "QTD_RECOMENDADA_ARM", "INVESTIMENTO_ESTIMADO",
    "FLAG_DESCONTINUAR", "FLAG_PROMOVER", "FLAG_REPRECIFICAR", "FLAG_COMPRAR",
    "FLAG_PROTEGIDO_CAMPEAO", "FLAG_PROTEGIDO_SEM_CURVA", "FLAG_CURVA_ABC_AUSENTE",
    "N_ACOES_SINALIZADAS", "SINAL_MARGEM_AUDITAVEL", "SINAL_PRECO_LISTA",
    "REPRICING_FAIXA", "FAIXA_COMPRA_ETAPA6", "ACAO_PRIMARIA", "TIPO_VALOR_ACAO",
    "CAPITAL_IMOBILIZADO", "VALOR_ESTOQUE_ENCALHE", "INVESTIMENTO_RECOMPRA", "VALOR_ACAO_PRIMARIA",
    "FAIXA_PRIORIDADE", "ACAO_RECOMENDADA",
]


def main() -> None:
    print("Carregando base da Etapa 6 e candidatos de repricing da Etapa 5...")
    base = carregar_base()
    repricing = carregar_repricing()

    print("Classificando acoes (promover/descontinuar/reprecificar/comprar)...")
    d = classificar(base, repricing)
    acionavel = d[d["FLAG_ALGUMA_ACAO"] == 1].copy()
    acionavel = atribuir_faixa(acionavel)

    print("Agregando por universo, categoria e loja...")
    acao_univ = agregar_acao_universo(acionavel)
    categorias = agregar_chaves(acionavel, ["NIVEL_1"])
    lojas = agregar_chaves(acionavel, ["COD_EMPRESA", "CD_CIDADE", "CD_ESTADO", "FLAG_LOJA93"])
    fila = fila_priorizada(acionavel)

    print("Validando e construindo autoaudit...")
    validacoes = validar(d, acionavel, acao_univ, categorias, lojas, repricing)
    autoaudit = construir_autoaudit(acionavel)
    recomendacoes = gerar_recomendacoes_melhoria()

    # Detalhe de repricing por loja x SKU (com sinais), universos operacionais.
    reprec_det = acionavel.loc[
        acionavel["FLAG_REPRECIFICAR"] == 1,
        ["UNIVERSO_OPERACIONAL", "COD_EMPRESA", "CD_CIDADE", "CD_ESTADO", "CODIGO", "DESCRICAO",
         "NIVEL_1", "CURVA_ABC_RECEITA", "CURVA_ABC_ORIGEM", "REPRICING_N_EMBALAGENS", "REPRICING_FAIXA",
         "SINAL_MARGEM_AUDITAVEL", "SINAL_PRECO_LISTA", "FLAG_CUSTO_VALIDO",
         "MARGEM_BRUTA_PCT_COM_CUSTO", "FLAG_MARGEM_NEGATIVA", "REPRICING_RECEITA",
         "ACAO_PRIMARIA", "FAIXA_PRIORIDADE"],
    ].sort_values(["UNIVERSO_OPERACIONAL", "REPRICING_FAIXA", "REPRICING_RECEITA"],
                  ascending=[True, True, False])

    print("Salvando arquivos auditaveis...")
    salvar_csv(acionavel[COLS_DETALHE].sort_values(
        ["UNIVERSO_OPERACIONAL", "ACAO_PRIMARIA", "FAIXA_PRIORIDADE"]), "recomendacoes_sku_loja.csv")
    salvar_csv(acao_univ, "recomendacoes_acao_universo.csv")
    salvar_csv(categorias, "recomendacoes_categoria_n1.csv")
    salvar_csv(lojas, "recomendacoes_lojas.csv")
    salvar_csv(reprec_det, "reprecificacao_candidatos.csv")
    salvar_csv(fila[["RANK_EXECUCAO", *COLS_DETALHE]], "priorizacao_acoes.csv")
    salvar_csv(recomendacoes, "recomendacoes_melhoria.csv")
    salvar_csv(validacoes, "validacoes_etapa7.csv")
    salvar_csv(autoaudit, "autoaudit_etapa7.csv")

    (OUT / "resumo_etapa7.md").write_text(
        gerar_resumo(acao_univ, fila, autoaudit, validacoes), encoding="utf-8")
    (OUT / "documentacao_tecnica_etapa7.md").write_text(
        gerar_documentacao_tecnica(), encoding="utf-8")

    print("\n--- Destaques Etapa 7 (rede fisica) ---")
    for acao in PRECEDENCIA_ACOES:
        r = _linha_acao(acao_univ, UNIVERSO_FISICO, acao)
        valor = "nao aplicavel" if acao == "REPRECIFICAR" else fmt_brl_milhao(r["VALOR_FINANCEIRO_CONHECIDO"])
        print(f"  {acao:<13}: {int(r['PARES']):>6,} pares | valor conhecido "
              f"{valor}")
    print(f"  Loja 93 acionaveis: {int((acionavel['COD_EMPRESA'] == LOJA_ATACADO).sum()):,}")
    print(f"  Validacoes OK: {(validacoes['STATUS'] == 'OK').sum()}/{len(validacoes)}")

    print("\n[OK] Arquivos salvos em outputs/etapa7/")
    for path in sorted(OUT.glob("*")):
        print(f"  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
