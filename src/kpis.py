"""
kpis.py — SSOT (Single Source of Truth) de indicadores do case.

Cada etapa do pipeline emite `outputs/etapaN/kpis_etapaN.json` no formato:

    { "<chave>": { "valor": <num>, "unidade": <str>,
                   "fonte": <str>, "descricao": <str> } }

- **chave**: hierárquica e estável, `eN.<dominio>.<detalhe>`
  (ex.: `e1.receita_total`, `e2.ruptura.pares`, `e5.acima_lista.rede_fisica`).
- **valor**: SEMPRE numérico CRU (nunca formatado). A formatação pt-BR vive aqui
  (`fmt_*`), reaproveitada pelos resumos, pelo `gerar_dashboard.py` e pelo linter
  `scripts/kpi_check.py` — fonte única de formatação.

O consolidado `outputs/kpis.json` é montado por `scripts/consolidar_kpis.py` a
partir dos parciais e é o arquivo que README/dashboard/linter consomem.

Gravação determinística: `sort_keys=True`, `ensure_ascii=False`, `indent=2`,
newline final e SEM timestamp — reexecutar produz bytes idênticos.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
KPIS_CONSOLIDADO = OUTPUTS / "kpis.json"


# ── formatação pt-BR (fonte única; verbatim de gerar_dashboard.py) ──────────────
def fmt_int(n) -> str:
    return f"{int(round(n)):,}".replace(",", ".")


def fmt_milhao(v) -> str:
    return "R$ " + f"{v / 1e6:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") + "M"


def fmt_pct(v, dec: int = 1) -> str:
    return f"{v:.{dec}f}".replace(".", ",") + "%"


def fmt_reais(v, dec: int = 2) -> str:
    s = f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + s


# Dispatcher por nome de formato, usado pelos marcadores do README e pelo dashboard.
FORMATTERS = {
    "int": lambda v: fmt_int(v),
    "milhao": lambda v: fmt_milhao(v),
    "pct": lambda v: fmt_pct(v, 1),
    "pct2": lambda v: fmt_pct(v, 2),
    "pct_abs": lambda v: fmt_pct(abs(v), 1),  # magnitude (ex.: queda narrada como "recua 54,2%")
    "reais": lambda v: fmt_reais(v, 2),
    "markup": lambda v: f"{v:.2f}".replace(".", ",") + "×",
    "raw": lambda v: str(v),
}


# ── emissão / leitura do SSOT ───────────────────────────────────────────────────
def _etapa_dir(etapa: str) -> str:
    """Normaliza 'etapa5' | '5' | 5 -> 'etapa5'."""
    s = str(etapa)
    return s if s.startswith("etapa") else f"etapa{s}"


def emit_kpis(etapa: str, kpis: dict) -> Path:
    """
    Grava `outputs/<etapa>/kpis_<etapa>.json` de forma determinística.

    `kpis` deve mapear chave -> {valor, unidade, fonte, descricao}. Valores devem
    ser numéricos crus (int/float), não strings formatadas.
    """
    nome = _etapa_dir(etapa)
    destino = OUTPUTS / nome / f"kpis_{nome}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(kpis, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    destino.write_text(texto, encoding="utf-8")
    return destino


def kpi(valor, unidade: str, fonte: str, descricao: str) -> dict:
    """Atalho para montar uma entrada de KPI no formato canônico."""
    # Normaliza numpy scalars -> tipos Python nativos p/ JSON determinístico.
    try:
        import numpy as _np

        if isinstance(valor, _np.integer):
            valor = int(valor)
        elif isinstance(valor, _np.floating):
            valor = float(valor)
    except Exception:
        pass
    return {"valor": valor, "unidade": unidade, "fonte": fonte, "descricao": descricao}


def load_kpis(path: Path | str = KPIS_CONSOLIDADO) -> dict:
    """Carrega o SSOT consolidado (ou um parcial)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def get_kpi(chave: str, field: str = "valor", kpis: dict | None = None):
    """Retorna um campo de um KPI do SSOT. `get_kpi('e5.acima_lista.rede_fisica')`."""
    kpis = kpis if kpis is not None else load_kpis()
    if chave not in kpis:
        raise KeyError(f"KPI '{chave}' não encontrado no SSOT ({KPIS_CONSOLIDADO}).")
    return kpis[chave][field]


def fmt_kpi(chave: str, fmt: str = "int", kpis: dict | None = None) -> str:
    """Valor do KPI já formatado em pt-BR. `fmt` ∈ FORMATTERS."""
    if fmt not in FORMATTERS:
        raise KeyError(f"Formato '{fmt}' desconhecido. Opções: {sorted(FORMATTERS)}")
    return FORMATTERS[fmt](get_kpi(chave, kpis=kpis))
