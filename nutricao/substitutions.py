"""Cálculo de substituições realistas, respeitando grupo nutricional e porções."""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence


def calcular_substituicoes(alimento_base: Mapping, quantidade_base: float, grupo_equiv: object, candidatos: Sequence[Mapping] | None = None) -> list[dict]:
    """Calcula substitutos do mesmo grupo com quantidades em gramas."""
    if alimento_base is None:
        return []

    base_kcal = float(alimento_base.get("kcal") or alimento_base.get("calorias") or 0.0)
    base_proteina = float(alimento_base.get("proteinas") or 0.0)
    base_carbs = float(alimento_base.get("carbs") or 0.0)
    base_gorduras = float(alimento_base.get("gorduras") or 0.0)
    quantidade = float(quantidade_base or 0.0)

    if quantidade <= 0:
        return []

    if candidatos is None:
        return []

    resultados = []
    for item in candidatos:
        item_grupo = str(item.get("grupo_equiv") or item.get("grupo") or "").strip().lower()
        if grupo_equiv is not None:
            alvo = str(grupo_equiv).strip().lower()
            if item_grupo and item_grupo != alvo:
                continue
        kcal_100 = float(item.get("kcal") or 0.0)
        if kcal_100 <= 0:
            continue
        kcal_total = (quantidade / 100.0) * kcal_100
        quantidade_sub = max(1.0, round((quantidade * (base_kcal or 1.0)) / max(kcal_100, 1.0), 1))
        resultados.append({
            "alimento": item.get("nome") or item.get("descricao") or "Alimento",
            "quantidade_g": float(quantidade_sub),
            "kcal": round(kcal_total, 2),
            "proteinas": round((quantidade_sub / 100.0) * float(item.get("proteinas") or 0.0), 2),
            "carbs": round((quantidade_sub / 100.0) * float(item.get("carbs") or 0.0), 2),
            "gorduras": round((quantidade_sub / 100.0) * float(item.get("gorduras") or 0.0), 2),
        })

    return sorted(resultados, key=lambda item: item["quantidade_g"])
