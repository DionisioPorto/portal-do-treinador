"""Score de qualidade da dieta e funções de custo."""

from __future__ import annotations

from typing import Mapping, Sequence


def _precision(current: float, target: float) -> float:
    if target <= 0:
        return 1.0 if current <= 0 else 0.0
    return max(0.0, 1.0 - abs(float(current) - float(target)) / max(float(target), 1.0))


def score_dieta(totais: Mapping[str, float], metas: Mapping[str, float], *, variety: float = 1.0, meals: int = 1, portion_quality: float = 1.0, penalties: float = 0.0) -> float:
    """Avalia a dieta por qualidade realista, não apenas por acurácia matemática."""
    kcal = float(totais.get("kcal", 0.0) or 0.0)
    protein = float(totais.get("proteinas", 0.0) or 0.0)
    carbs = float(totais.get("carbs", 0.0) or 0.0)
    fats = float(totais.get("gorduras", 0.0) or 0.0)

    meta_kcal = float(metas.get("kcal", 0.0) or 0.0)
    meta_protein = float(metas.get("proteinas", 0.0) or 0.0)
    meta_carbs = float(metas.get("carbs", 0.0) or 0.0)
    meta_fats = float(metas.get("gorduras", 0.0) or 0.0)

    score = 0.0
    score += _precision(kcal, meta_kcal) * 25.0
    score += _precision(protein, meta_protein) * 25.0
    score += _precision(carbs, meta_carbs) * 20.0
    score += _precision(fats, meta_fats) * 15.0
    score += max(0.0, min(1.0, portion_quality)) * 10.0
    score += max(0.0, min(1.0, variety)) * 5.0
    score += max(0.0, min(1.0, 1.0 / max(meals, 1))) * 5.0
    score -= max(0.0, float(penalties)) * 10.0
    return round(max(0.0, min(100.0, score)), 2)


def score_refeicao(refeicao: Mapping[str, object], meta: Mapping[str, float]) -> float:
    """Avalia uma refeição individual de forma coerente com a meta diária."""
    totals = refeicao.get("totais") or {}
    kcal = float(totais.get("kcal", 0.0) or 0.0)
    protein = float(totais.get("proteinas", 0.0) or 0.0)
    carbs = float(totais.get("carbs", 0.0) or 0.0)
    fats = float(totais.get("gorduras", 0.0) or 0.0)

    targets = {
        "kcal": float(meta.get("kcal", kcal) or kcal),
        "proteinas": float(meta.get("proteinas", protein) or protein),
        "carbs": float(meta.get("carbs", carbs) or carbs),
        "gorduras": float(meta.get("gorduras", fats) or fats),
    }
    return score_dieta({"kcal": kcal, "proteinas": protein, "carbs": carbs, "gorduras": fats}, targets, meals=1, variety=0.8, portion_quality=0.9)
