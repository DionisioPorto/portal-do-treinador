"""Helpers para controlar porções realistas e evitar extremos artificiais."""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence, Tuple

from .equivalencias import normalizar_grupo


PORCOES_POR_GRUPO: dict[str, tuple[float, float, float]] = {
    "amido": (60.0, 150.0, 250.0),
    "pao": (40.0, 80.0, 100.0),
    "cereal": (20.0, 40.0, 70.0),
    "leguminosa": (60.0, 100.0, 160.0),
    "proteina": (80.0, 150.0, 250.0),
    "laticinio": (50.0, 140.0, 300.0),
    "fruta": (80.0, 130.0, 220.0),
    "gordura": (5.0, 12.0, 25.0),
    "doce": (10.0, 20.0, 40.0),
    "legume": (60.0, 120.0, 160.0),
    "verdura_folha": (20.0, 40.0, 80.0),
}

PORCOES_POR_NOME: dict[str, tuple[float, float, float]] = {
    "Aveia em flocos": (20.0, 40.0, 70.0),
    "Arroz branco cozido": (100.0, 180.0, 300.0),
    "Arroz integral cozido": (100.0, 180.0, 300.0),
    "Batata-doce cozida": (100.0, 200.0, 300.0),
    "Feijão preto": (60.0, 100.0, 160.0),
    "Peito de frango grelhado": (100.0, 180.0, 250.0),
    "Filé de tilápia": (100.0, 180.0, 250.0),
    "Ovo cozido": (50.0, 100.0, 200.0),
    "Banana": (70.0, 110.0, 150.0),
    "Maçã": (80.0, 130.0, 170.0),
    "Azeite de oliva": (5.0, 10.0, 15.0),
    "Iogurte natural": (100.0, 170.0, 300.0),
    "Queijo cottage": (50.0, 120.0, 200.0),
    "Brócolis": (60.0, 120.0, 160.0),
    "Alface": (20.0, 40.0, 80.0),
}


def resolve_faixa_porcao(alimento: Mapping) -> tuple[float, float, float]:
    """Resolve a faixa realista da porção do alimento."""
    if not isinstance(alimento, Mapping):
        return (50.0, 100.0, 180.0)

    porcao_min = alimento.get("porcao_min")
    porcao_max = alimento.get("porcao_max")
    porcao_padrao = alimento.get("porcao_padrao")

    if porcao_min is not None and porcao_max is not None and float(porcao_max) > 0:
        mn = float(porcao_min)
        mx = float(porcao_max)
        ide = float(porcao_padrao) if porcao_padrao not in (None, "") and float(porcao_padrao) > 0 else (mn + mx) / 2.0
        return (mn, ide, mx)

    nome = str(alimento.get("nome") or "").strip()
    if nome in PORCOES_POR_NOME:
        return PORCOES_POR_NOME[nome]

    grupo = normalizar_grupo(alimento.get("grupo_equiv") or alimento.get("grupo") or alimento.get("categoria"))
    if grupo in PORCOES_POR_GRUPO:
        return PORCOES_POR_GRUPO[grupo]

    base = float(alimento.get("porcao") or alimento.get("quantidade_padrao") or 100.0)
    return (base * 0.5, base, base * 1.6)


def clamp_portion(valor: float, faixa: Sequence[float]) -> float:
    """Mantém a quantidade dentro dos limites realistas."""
    mn, _, mx = faixa
    numero = float(valor)
    return max(float(mn), min(float(mx), numero))


def qualidade_porcoes(valor: float, faixa: Sequence[float]) -> float:
    """Retorna uma pontuação de qualidade da porção, sendo melhor perto do padrão."""
    mn, padrao, mx = [float(v) for v in faixa]
    if mx <= mn:
        return 1.0
    numero = float(valor)
    if numero < mn or numero > mx:
        numero = clamp_portion(numero, faixa)
    delta = abs(numero - padrao) / max((mx - mn) or 1.0, 1.0)
    return max(0.0, 1.0 - (delta * 1.5))


def penalidade_borda(valor: float, faixa: Sequence[float]) -> float:
    """Penaliza proporções antes demais próximas de min/max."""
    mn, padrao, mx = [float(v) for v in faixa]
    if mx <= mn:
        return 0.0
    numero = float(valor)
    if numero < mn:
        numero = mn
    if numero > mx:
        numero = mx
    proximidade_min = max(0.0, (numero - mn) / max((mx - mn), 1.0))
    proximidade_max = max(0.0, (mx - numero) / max((mx - mn), 1.0))
    melhor = max(proximidade_min, proximidade_max)
    return max(0.0, 0.75 - melhor)


def lista_porcoes(alimentos: Iterable[Mapping]) -> list:
    """Retorna uma lista de alimentos com faixa e qualidade de porção."""
    itens = []
    for item in alimentos:
        faixa = resolve_faixa_porcao(item)
        itens.append({**dict(item), "_faixa_porcao": faixa})
    return itens
