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
from .openfoodfacts import importar_produto, buscar_produtos

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
]
