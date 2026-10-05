"""
Módulo de nutrição do Portal do Treinador.

Responsável por:
- Importação de alimentos (TBCA, Open Food Facts)
- Padronização nutricional
- Armazenamento no banco local
- Cálculo de substituições

A internet é fonte de atualização/importação.
O SQLite é a fonte operacional.
"""

from .normalizer import (
    normalizar_nome,
    normalizar_alimento,
    converter_para_100g,
    validar_nutricao,
)
from .database import (
    importar_alimento,
    atualizar_alimento,
    buscar_alimento_por_codigo,
    desativar_alimento,
)
from .tbca import importar_tbca_csv
try:
    from .openfoodfacts import importar_produto, buscar_produtos
except ModuleNotFoundError:  # pragma: no cover - depende de requests disponível no ambiente
    importar_produto = None
    buscar_produtos = None
from .optimizer import DietPlanOptimizer
from .scoring import score_dieta, score_refeicao
from .equivalencias import normalizar_grupo, tipo_equivalencia, filtrar_por_grupo
from .portions import resolve_faixa_porcao, clamp_portion, qualidade_porcoes
from .substitutions import calcular_substituicoes

__all__ = [
    "normalizar_nome",
    "normalizar_alimento",
    "converter_para_100g",
    "validar_nutricao",
    "importar_alimento",
    "atualizar_alimento",
    "buscar_alimento_por_codigo",
    "desativar_alimento",
    "importar_tbca_csv",
    "importar_produto",
    "buscar_produtos",
    "DietPlanOptimizer",
    "score_dieta",
    "score_refeicao",
    "normalizar_grupo",
    "tipo_equivalencia",
    "filtrar_por_grupo",
    "resolve_faixa_porcao",
    "clamp_portion",
    "qualidade_porcoes",
    "calcular_substituicoes",
]
