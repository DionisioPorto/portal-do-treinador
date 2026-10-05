"""Utilitários para agrupar e classificar alimentos por equivalência nutricional."""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence


GRUPO_ALIASES = {
    "amido": "amido",
    "carboidrato": "amido",
    "carbo": "amido",
    "pao": "pao",
    "cereal": "cereal",
    "leguminosa": "leguminosa",
    "proteina": "proteina",
    "laticinio": "laticinio",
    "fruta": "fruta",
    "doce": "doce",
    "gordura": "gordura",
    "legume": "legume",
    "verdura_folha": "verdura_folha",
    "folha": "verdura_folha",
    "vegetal": "legume",
}


def normalizar_grupo(grupo: object) -> str:
    """Converte um grupo em uma chave determinística."""
    if grupo is None:
        return ""
    texto = str(grupo).strip().lower().replace("-", "_")
    return GRUPO_ALIASES.get(texto, texto)


def tipo_equivalencia(grupo: object) -> str:
    """Classifica o grupo pelo papel nutricional mais relevante."""
    g = normalizar_grupo(grupo)
    if g in {"amido", "pao", "cereal", "fruta", "doce", "leguminosa"}:
        return "carboidrato"
    if g in {"proteina", "laticinio"}:
        return "proteina"
    if g == "gordura":
        return "gordura"
    if g in {"legume", "verdura_folha", "folha"}:
        return "vegetal"
    return "outro"


def filtrar_por_grupo(alimentos: Iterable[Mapping], grupo: object) -> list:
    """Filtra alimentos por grupo equivalência."""
    alvo = normalizar_grupo(grupo)
    if not alvo:
        return list(alimentos)
    saida = []
    for item in alimentos:
        if normalizar_grupo(item.get("grupo_equiv") or item.get("grupo") or item.get("categoria")) == alvo:
            saida.append(item)
    return saida


def coletar_alimentos_por_tipo(alimentos: Sequence[Mapping], tipo: str) -> list:
    """Coleta candidatos pelo tipo nutricional."""
    return [item for item in alimentos if tipo_equivalencia(item.get("grupo_equiv") or item.get("grupo") or item.get("categoria")) == tipo]
