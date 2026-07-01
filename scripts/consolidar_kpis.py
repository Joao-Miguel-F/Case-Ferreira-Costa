"""
consolidar_kpis.py — monta o SSOT consolidado `outputs/kpis.json`.

Faz o merge determinístico dos parciais `outputs/etapaN/kpis_etapaN.json` emitidos
por cada etapa do pipeline (ver src/kpis.py). Não recalcula nada: só une.

- Chaves são namespaced por etapa (`e1.*`, `e2.*`, ...), então não deve haver
  colisão. Se houver, o script FALHA (exit != 0) apontando a chave duplicada —
  isso indicaria uma etapa gravando fora do seu prefixo.
- Saída determinística (`sort_keys=True`, `ensure_ascii=False`, `indent=2`,
  newline final, sem timestamp) → reexecutar produz bytes idênticos.

Uso:
    .venv/Scripts/python.exe scripts/consolidar_kpis.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
DESTINO = OUTPUTS / "kpis.json"


def consolidar() -> dict:
    parciais = sorted(OUTPUTS.glob("etapa*/kpis_etapa*.json"))
    if not parciais:
        raise SystemExit(
            "Nenhum kpis_etapaN.json encontrado. Rode o pipeline (etapas 1-7) primeiro."
        )
    consolidado: dict = {}
    origem: dict = {}
    for arquivo in parciais:
        parcial = json.loads(arquivo.read_text(encoding="utf-8"))
        for chave, valor in parcial.items():
            if chave in consolidado:
                raise SystemExit(
                    f"Chave de KPI duplicada '{chave}' em {arquivo.name} "
                    f"(já definida em {origem[chave]}). Chaves devem ser únicas por etapa."
                )
            consolidado[chave] = valor
            origem[chave] = arquivo.name
    return consolidado


def main() -> None:
    consolidado = consolidar()
    texto = json.dumps(consolidado, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    DESTINO.write_text(texto, encoding="utf-8")
    print(f"[OK] {DESTINO.relative_to(ROOT)} — {len(consolidado)} KPIs de "
          f"{len(sorted(OUTPUTS.glob('etapa*/kpis_etapa*.json')))} etapas.")


if __name__ == "__main__":
    sys.exit(main())
