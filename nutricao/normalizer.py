"""
Padronização nutricional do Portal do Treinador.

Todas as funções aqui garantem que os valores nutricionais
sejam armazenados de forma padronizada: por 100 g.
"""

import re
import unicodedata


def normalizar_nome(nome):
    """Normaliza o nome de um alimento para comparação.
    
    - Remove acentos
    - Converte para minúsculas
    - Remove espaços extras
    - Remove pontuação desnecessária
    
    Args:
        nome: Nome original do alimento
        
    Returns:
        Nome normalizado para comparação
    """
    if not nome:
        return ""
    
    # Remove acentos
    nome = unicodedata.normalize('NFD', nome)
    nome = nome.encode('ascii', 'ignore').decode('utf-8')
    
    # Minúsculas e espaços
    nome = nome.lower().strip()
    
    # Remove pontuação desnecessária (mantém espaços e hífens)
    nome = re.sub(r'[^\w\s-]', '', nome)
    
    # Remove espaços extras
    nome = re.sub(r'\s+', ' ', nome)
    
    return nome


def converter_para_100kcal(kcal, quantidade_gramas):
    """Converte kcal de uma quantidade para 100 g.
    
    Args:
        kcal: Valor calórico na quantidade informada
        quantidade_gramas: Quantidade em gramas
        
    Returns:
        kcal por 100 g
    """
    if not quantidade_gramas or quantidade_gramas <= 0:
        return 0
    return (kcal / quantidade_gramas) * 100


def converter_para_100g(valor, quantidade_gramas):
    """Converte um valor nutricional para base de 100 g.
    
    Args:
        valor: Valor nutricional na quantidade informada
        quantidade_gramas: Quantidade em gramas
        
    Returns:
        Valor por 100 g
    """
    if not quantidade_gramas or quantidade_gramas <= 0:
        return 0
    return (valor / quantidade_gramas) * 100


def validar_nutricao(kcal, proteinas, carbs, gorduras):
    """Valida se os valores nutricionais são aceitáveis.
    
    Args:
        kcal: Calorias por 100 g
        proteinas: Proteínas por 100 g
        carbs: Carboidratos por 100 g
        gorduras: Gorduras por 100 g
        
    Returns:
        (bool, str): (válido, mensagem de erro)
    """
    if kcal is None or kcal < 0:
        return False, "kcal ausente ou negativo"
    if proteinas is None or proteinas < 0:
        return False, "proteína ausente ou negativa"
    if carbs is None or carbs < 0:
        return False, "carboidrato ausente ou negativo"
    if gorduras is None or gorduras < 0:
        return False, "gordura ausente ou negativa"
    
    # Verifica se pelo menos um macro tem valor > 0
    if kcal == 0 and proteinas == 0 and carbs == 0 and gorduras == 0:
        return False, "todos os macros estão zerados"
    
    return True, ""


def normalizar_alimento(dados):
    """Normaliza todos os campos de um alimento.
    
    Args:
        dados: Dict com dados do alimento
        
    Returns:
        Dict com dados normalizados
    """
    nome = dados.get("nome", "")
    nome_normalizado = normalizar_nome(nome)
    
    # Converte valores para 100 g se necessário
    quantidade_ref = dados.get("quantidade_referencia", 100)
    unidade_ref = dados.get("unidade_referencia", "g")
    
    if unidade_ref == "ml":
        # Converte ml para g (aproximação: 1ml ≈ 1g para líquidos)
        quantidade_ref = quantidade_ref
    
    kcal = converter_para_100g(dados.get("kcal", 0), quantidade_ref)
    proteinas = converter_para_100g(dados.get("proteinas", 0), quantidade_ref)
    carbs = converter_para_100g(dados.get("carbs", 0), quantidade_ref)
    gorduras = converter_para_100g(dados.get("gorduras", 0), quantidade_ref)
    
    # Valida nutrição
    valido, erro = validar_nutrition(kcal, proteinas, carbs, gorduras)
    if not valido:
        raise ValueError(f"Nutrição inválida: {erro}")
    
    return {
        "nome": nome,
        "nome_normalizado": nome_normalizado,
        "categoria": dados.get("categoria", ""),
        "grupo_equiv": dados.get("grupo_equiv", ""),
        "kcal": round(kcal, 2),
        "proteinas": round(proteinas, 2),
        "carbs": round(carbs, 2),
        "gorduras": round(gorduras, 2),
        "porcao": dados.get("porcao", 100),
        "porcao_min": dados.get("porcao_min", 0),
        "porcao_max": dados.get("porcao_max", 0),
        "porcao_padrao": dados.get("porcao_padrao", 0),
        "fonte": dados.get("fonte", "manual"),
        "codigo_fonte": dados.get("codigo_fonte", ""),
        "marca": dados.get("marca", ""),
        "unidade_base": "g",
        "tipo_equivalencia": dados.get("tipo_equivalencia", ""),
        "qualidade_dados": dados.get("qualidade_dados", "media"),
        "origem_confiavel": dados.get("origem_confiavel", 0),
    }


def validar_nutrition(kcal, proteinas, carbs, gorduras):
    """Alias para validar_nutricao (compatibilidade)."""
    return validar_nutricao(kcal, proteinas, carbs, gorduras)
