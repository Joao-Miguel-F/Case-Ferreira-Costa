"""
kpi_check.py — linter de consistência entre o texto narrado e o SSOT de KPI.

Marca os KPIs no README (e em qualquer .md alvo) com comentários HTML invisíveis:

    <!--kpi:CHAVE:FMT-->valor renderizado<!--/kpi-->

Exemplo:

    ...vendem **<!--kpi:e5.acima_lista.rede_fisica:int-->2.079<!--/kpi-->** acima da lista...

`CHAVE` é a chave do SSOT (outputs/kpis.json) e `FMT` é um formatador de
src/kpis.py (int, milhao, pct, pct2, pct_abs, reais, raw). O linter formata o valor
do SSOT com esse formatador e o compara ao texto entre os marcadores.

Modos:
    (padrão / --check)  FALHA (exit 1) se qualquer texto divergir do SSOT.
    --inject / --fix    reescreve o texto dos marcadores a partir do SSOT.

Uso:
    .venv/Scripts/python.exe scripts/kpi_check.py            # verifica (CI-friendly)
    .venv/Scripts/python.exe scripts/kpi_check.py --inject   # normaliza a partir do SSOT

Alvos padrão: README.md. Passe caminhos como argumentos para checar outros arquivos.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kpis import fmt_kpi, load_kpis  # noqa: E402

# Grupos: 1=chave, 2=fmt, 3=texto renderizado. `.*?` sem newline (KPI é inline).
MARCADOR = re.compile(r"<!--kpi:([A-Za-z0-9_.]+):([A-Za-z0-9_]+)-->(.*?)<!--/kpi-->", re.DOTALL)
ALVOS_PADRAO = ["README.md"]


def _alvos(args: list[str]) -> list[Path]:
    caminhos = [a for a in args if not a.startswith("-")]
    return [(Path(c) if Path(c).is_absolute() else ROOT / c) for c in (caminhos or ALVOS_PADRAO)]


def _nome(alvo: Path) -> str:
    """Nome amigável: relativo à raiz quando possível, caminho cru caso contrário."""
    try:
        return str(alvo.relative_to(ROOT))
    except ValueError:
        return str(alvo)


def verificar(texto: str, kpis: dict) -> list[tuple[str, str, str, str]]:
    """Retorna divergências: (chave, fmt, esperado, encontrado)."""
    divergencias = []
    for chave, fmt, encontrado in MARCADOR.findall(texto):
        esperado = fmt_kpi(chave, fmt, kpis=kpis)
        if esperado != encontrado:
            divergencias.append((chave, fmt, esperado, encontrado))
    return divergencias


def injetar(texto: str, kpis: dict) -> str:
    def _sub(m: re.Match) -> str:
        chave, fmt = m.group(1), m.group(2)
        esperado = fmt_kpi(chave, fmt, kpis=kpis)
        return f"<!--kpi:{chave}:{fmt}-->{esperado}<!--/kpi-->"

    return MARCADOR.sub(_sub, texto)


def main(argv: list[str]) -> int:
    inject = ("--inject" in argv) or ("--fix" in argv)
    kpis = load_kpis()
    alvos = _alvos(argv)

    total_marcadores = 0
    total_divergencias = 0
    for alvo in alvos:
        if not alvo.exists():
            print(f"[AVISO] alvo inexistente: {alvo}")
            continue
        texto = alvo.read_text(encoding="utf-8")
        n = len(MARCADOR.findall(texto))
        total_marcadores += n
        if inject:
            novo = injetar(texto, kpis)
            if novo != texto:
                alvo.write_text(novo, encoding="utf-8")
                print(f"[INJETADO] {_nome(alvo)} — {n} marcadores normalizados do SSOT.")
            else:
                print(f"[OK] {_nome(alvo)} — {n} marcadores já sincronizados.")
        else:
            divergencias = verificar(texto, kpis)
            total_divergencias += len(divergencias)
            if divergencias:
                print(f"[FALHA] {_nome(alvo)} — {len(divergencias)} divergência(s):")
                for chave, fmt, esperado, encontrado in divergencias:
                    print(f"    {chave} ({fmt}): SSOT='{esperado}'  README='{encontrado}'")
            else:
                print(f"[OK] {_nome(alvo)} — {n} marcadores conferem com o SSOT.")

    if inject:
        return 0
    if total_marcadores == 0:
        print("[FALHA] nenhum marcador <!--kpi:...--> encontrado nos alvos.")
        return 1
    if total_divergencias:
        print(f"\n[FALHA] {total_divergencias} KPI(s) divergem do SSOT. "
              f"Rode `python scripts/kpi_check.py --inject` ou corrija o texto.")
        return 1
    print(f"\n[OK] {total_marcadores} KPIs narrados conferem com outputs/kpis.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
