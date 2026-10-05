"""
Integração com Open Food Facts.

Open Food Facts é uma base colaborativa de produtos alimentícios.
API: https://world.openfoodfacts.org/

Usado para produtos industrializados/marcas quando o alimento não
está disponível na TBCA.
"""

import requests
from .normalizer import normalizar_alimento, validar_nutricao


API_BASE = "https://world.openfoodfacts.org/api/v2"


def buscar_produto_por_codigo_barras(codigo_barras):
    """Busca um produto pelo código de barras (EAN).
    
    Args:
        codigo_barras: Código EAN do produto
        
    Returns:
        Dict com dados do produto ou None
    """
    url = f"{API_BASE}/product/{codigo_barras}.json"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") != 1:
            return None
        
        produto = data.get("product", {})
        
        # Extrai valores nutricionais (por 100g)
        nutriments = produto.get("nutriments", {})
        
        kcal = nutriments.get("energy-kcal_100g", 0)
        proteina = nutriments.get("proteins_100g", 0)
        carbo = nutriments.get("carbohydrates_100g", 0)
        gordura = nutriments.get("fat_100g", 0)
        
        # Valida nutrição
        valido, erro = validar_nutricao(kcal, proteina, carbo, gordura)
        if not valido:
            return None
        
        return {
            "codigo_barras": codigo_barras,
            "nome": produto.get("product_name", ""),
            "marca": produto.get("brands", ""),
            "kcal": kcal,
            "proteinas": proteina,
            "carbs": carbo,
            "gorduras": gordura,
            "fonte": "OpenFoodFacts",
            "qualidade_dados": "media",
            "origem_confiavel": 1,
        }
    except requests.RequestException:
        return None


def buscar_produtos(termo, pagina=1, tamanho_pagina=20):
    """Busca produtos por termo.
    
    Args:
        termo: Termo de busca
        pagina: Número da página
        tamanho_pagina: Tamanho da página
        
    Returns:
        Lista de produtos encontrados
    """
    url = f"{API_BASE}/search"
    params = {
        "search_terms": termo,
        "page": pagina,
        "page_size": tamanho_pagina,
        "fields": "code,product_name,brands,nutriments",
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        produtos = []
        for produto in data.get("products", []):
            nutriments = produto.get("nutriments", {})
            
            kcal = nutriments.get("energy-kcal_100g", 0)
            proteina = nutriments.get("proteins_100g", 0)
            carbo = nutriments.get("carbohydrates_100g", 0)
            gordura = nutriments.get("fat_100g", 0)
            
            # Valida nutrição
            valido, _ = validar_nutricao(kcal, proteina, carbo, gordura)
            if not valido:
                continue
            
            produtos.append({
                "codigo_barras": produto.get("code", ""),
                "nome": produto.get("product_name", ""),
                "marca": produto.get("brands", ""),
                "kcal": kcal,
                "proteinas": proteina,
                "carbs": carbo,
                "gorduras": gordura,
            })
        
        return produtos
    except requests.RequestException:
        return []


def importar_produto(codigo_barras):
    """Importa um produto do Open Food Facts para o banco local.
    
    Args:
        codigo_barras: Código EAN do produto
        
    Returns:
        (bool, str, int): (sucesso, mensagem, alimento_id)
    """
    from .database import importar_alimento, buscar_alimento_por_codigo
    
    # Verifica se já existe
    existente = buscar_alimento_por_codigo("OpenFoodFacts", codigo_barras)
    if existente:
        return False, f"Produto já existe (id={existente['id']})", existente["id"]
    
    # Busca produto
    produto = buscar_produto_por_codigo_barras(codigo_barras)
    if not produto:
        return False, "Produto não encontrado ou sem dados nutricionais", None
    
    # Importa
    return importar_alimento(produto)
