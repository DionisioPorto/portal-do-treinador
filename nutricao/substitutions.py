"""Cálculo de substituições realistas, respeitando grupo nutricional e porções."""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from .equivalencias import normalizar_grupo
from .portions import clamp_portion, resolve_faixa_porcao


GRUPOS_MACRO_PRINCIPAL = {
    "proteinas": {"proteina", "laticinio"},
    "carbs": {"amido", "pao", "cereal", "fruta", "doce", "leguminosa"},
    "gorduras": {"gordura"},
}


def calcular_substituicoes(alimento_base: Mapping, quantidade_base: float, grupo_equiv: object, candidatos: Sequence[Mapping] | None = None) -> list[dict]:
    """Calcula substitutos priorizando o macro característico do grupo."""
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
    grupo_alvo = normalizar_grupo(grupo_equiv)
    macro_principal = next(
        (macro for macro, grupos in GRUPOS_MACRO_PRINCIPAL.items() if grupo_alvo in grupos),
        "kcal",
    )
    quantidade_base_macro = {
        "kcal": base_kcal,
        "proteinas": base_proteina,
        "carbs": base_carbs,
        "gorduras": base_gorduras,
    }[macro_principal] * quantidade / 100.0
    for item in candidatos:
        item_grupo = normalizar_grupo(item.get("grupo_equiv") or item.get("grupo") or "")
        if grupo_equiv is not None:
            if item_grupo and item_grupo != grupo_alvo:
                continue
        kcal_100 = float(item.get("kcal") or 0.0)
        nutriente_100 = float(item.get(macro_principal) or 0.0) if macro_principal != "kcal" else kcal_100
        if nutriente_100 <= 0:
            continue
        quantidade_sub = quantidade_base_macro / nutriente_100 * 100.0
        quantidade_sub = clamp_portion(quantidade_sub, resolve_faixa_porcao(item))
        quantidade_sub = round(quantidade_sub, 1)
        fator = quantidade_sub / 100.0
        resultados.append({
            "alimento": item.get("nome") or item.get("descricao") or "Alimento",
            "quantidade_g": float(quantidade_sub),
            "kcal": round(kcal_100 * fator, 2),
            "proteinas": round(float(item.get("proteinas") or 0.0) * fator, 2),
            "carbs": round(float(item.get("carbs") or 0.0) * fator, 2),
            "gorduras": round(float(item.get("gorduras") or 0.0) * fator, 2),
        })

    return sorted(
        resultados,
        key=lambda item: abs(item[macro_principal] - quantidade_base_macro),
    )
