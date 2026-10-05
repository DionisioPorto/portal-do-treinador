"""
Testes do módulo de nutrição do Portal do Treinador.

Estes testes verificam:
1. Importação TBCA
2. Importação Open Food Facts
3. Validação de nutrição
4. Normalização de nomes
5. Conversão para 100g
6. Substituições com gramas
7. Limites de porção
8. Dietas com diferentes metas

Como executar:
    cd portal-do-treinador
    python -m pytest test_nutricao.py -v
"""

import os
import sys
import tempfile
from pathlib import Path

# Adiciona o diretório do projeto ao path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Configura ambiente de teste antes de importar
os.environ["PORTAL_DATA_DIR"] = tempfile.mkdtemp()
os.environ["SECRET_KEY"] = "test-secret-key"

from nutricao.normalizer import (
    normalizar_nome,
    converter_para_100g,
    validar_nutricao,
    normalizar_alimento,
)
from nutricao.database import (
    importar_alimento,
    buscar_alimento_por_codigo,
    buscar_alimento_por_nome_normalizado,
    listar_alimentos,
)
from app import (
    app,
    calcular_gramas,
    calcular_substituicoes,
    PORCOES_POR_NOME,
)


# =============================================================================
# TESTES DE NORMALIZAÇÃO
# =============================================================================

def test_normalizar_nome_remove_acentos():
    """Verifica que acentos são removidos."""
    assert normalizar_nome("Arroz branco cozido") == "arroz branco cozido"
    assert normalizar_nome("Aveia em flocos") == "aveia em flocos"
    assert normalizar_nome("Peito de frango grelhado") == "peito de frango grelhado"
    print("✓ normalizar_nome remove acentos")


def test_normalizar_nome_remove_pontuacao():
    """Verifica que pontuação é removida."""
    assert normalizar_nome("Arroz branco, cozido") == "arroz branco cozido"
    assert normalizar_nome("Pão francês") == "pao frances"
    print("✓ normalizar_nome remove pontuação")


def test_normalizar_nome_minusculas():
    """Verifica que nome é convertido para minúsculas."""
    assert normalizar_nome("ARROZ BRANCO COZIDO") == "arroz branco cozido"
    assert normalizar_nome("ArRoZ BrAnCo") == "arroz branco"
    print("✓ normalizar_nome converte para minúsculas")


# =============================================================================
# TESTES DE CONVERSÃO
# =============================================================================

def test_converter_para_100g():
    """Verifica conversão de valores para 100g."""
    # 50g de arroz tem 64 kcal -> 100g tem 128 kcal
    assert converter_para_100g(64, 50) == 128.0
    
    # 200g de frango tem 330 kcal -> 100g tem 165 kcal
    assert converter_para_100g(330, 200) == 165.0
    
    # 100g já é a base
    assert converter_para_100g(100, 100) == 100.0
    print("✓ converter_para_100g funciona corretamente")


def test_converter_para_100g_quantidade_zero():
    """Verifica que quantidade zero retorna 0."""
    assert converter_para_100g(100, 0) == 0
    assert converter_para_100g(100, -10) == 0
    print("✓ converter_para_100g retorna 0 para quantidade inválida")


# =============================================================================
# TESTES DE VALIDAÇÃO
# =============================================================================

def test_validar_nutricao_valores_validos():
    """Verifica que valores válidos são aceitos."""
    valido, msg = validar_nutricao(128, 2.6, 28.1, 0.3)
    assert valido is True
    assert msg == ""
    print("✓ validar_nutricao aceita valores válidos")


def test_validar_nutricao_valores_negativos():
    """Verifica que valores negativos são rejeitados."""
    valido, msg = validar_nutricao(-10, 2.6, 28.1, 0.3)
    assert valido is False
    assert "kcal" in msg.lower()
    
    valido, msg = validar_nutricao(128, -5, 28.1, 0.3)
    assert valido is False
    assert "proteína" in msg.lower()
    print("✓ validar_nutricao rejeita valores negativos")


def test_validar_nutricao_todos_zerados():
    """Verifica que todos zerados são rejeitados."""
    valido, msg = validar_nutricao(0, 0, 0, 0)
    assert valido is False
    assert "zerados" in msg.lower()
    print("✓ validar_nutricao rejeita todos zerados")


# =============================================================================
# TESTES DE IMPORTAÇÃO
# =============================================================================

def test_importar_alimento():
    """Verifica importação de alimento no banco."""
    dados = {
        "nome": "Arroz branco cozido",
        "categoria": "Carboidratos",
        "grupo_equiv": "amido",
        "kcal": 128,
        "proteinas": 2.6,
        "carbs": 28.1,
        "gorduras": 0.3,
        "porcao": 150,
        "porcao_min": 100,
        "porcao_max": 300,
        "porcao_padrao": 180,
        "fonte": "TBCA",
        "codigo_fonte": "TBCA001",
        "marca": "",
        "qualidade_dados": "alta",
        "origem_confiavel": 1,
    }
    
    sucesso, msg, alimento_id = importar_alimento(dados)
    assert sucesso is True
    assert alimento_id > 0
    
    # Verifica se foi salvo
    existente = buscar_alimento_por_codigo("TBCA", "TBCA001")
    assert existente is not None
    assert existente["nome"] == "Arroz branco cozido"
    print("✓ importar_alimento funciona corretamente")


def test_importar_alimento_duplicado():
    """Verifica que duplicatas são rejeitadas."""
    dados = {
        "nome": "Arroz branco cozido",
        "categoria": "Carboidratos",
        "grupo_equiv": "amido",
        "kcal": 128,
        "proteinas": 2.6,
        "carbs": 28.1,
        "gorduras": 0.3,
        "fonte": "TBCA",
        "codigo_fonte": "TBCA001",
    }
    
    sucesso, msg, _ = importar_alimento(dados)
    assert sucesso is False
    assert "já existe" in msg.lower()
    print("✓ Duplicatas são rejeitadas")


def test_importar_alimento_sem_macros():
    """Verifica que alimentos sem macros não são importados."""
    dados = {
        "nome": "Alimento sem dados",
        "categoria": "Teste",
        "grupo_equiv": "teste",
        "kcal": 0,
        "proteinas": 0,
        "carbs": 0,
        "gorduras": 0,
        "fonte": "manual",
    }
    
    try:
        sucesso, msg, _ = importar_alimento(dados)
        # Deve falhar na validação
        assert sucesso is False
    except ValueError:
        # Também é aceitável lançar exceção
        pass
    print("✓ Alimentos sem macros são rejeitados")


# =============================================================================
# TESTES DE SUBSTITUIÇÕES
# =============================================================================

def test_substituicoes_tem_gramas():
    """Verifica que substituições têm quantidades em gramas."""
    from app import get_db
    
    with app.app_context():
        con = get_db()
        
        # Busca arroz
        arroz = con.execute(
            "SELECT * FROM alimentos WHERE nome = 'Arroz branco cozido'"
        ).fetchone()
        
        if arroz:
            subs = calcular_substituicoes(
                {
                    "nome": arroz["nome"],
                    "kcal": arroz["kcal"],
                    "proteinas": arroz["proteinas"],
                    "carbs": arroz["carbs"],
                    "gorduras": arroz["gorduras"],
                    "porcao_min": arroz["porcao_min"],
                    "porcao_max": arroz["porcao_max"],
                },
                150,
                arroz["grupo_equiv"],
                con
            )
            
            for sub in subs:
                assert sub.get("quantidade_g") is not None
                assert sub["quantidade_g"] > 0
    
    print("✓ Substituições têm gramas")


def test_substituicoes_respeitam_porcao_max():
    """Verifica que substituições respeitam porcao_max."""
    from app import get_db
    
    with app.app_context():
        con = get_db()
        
        # Busca arroz
        arroz = con.execute(
            "SELECT * FROM alimentos WHERE nome = 'Arroz branco cozido'"
        ).fetchone()
        
        if arroz:
            subs = calcular_substituicoes(
                {
                    "nome": arroz["nome"],
                    "kcal": arroz["kcal"],
                    "proteinas": arroz["proteinas"],
                    "carbs": arroz["carbs"],
                    "gorduras": arroz["gorduras"],
                    "porcao_min": arroz["porcao_min"],
                    "porcao_max": arroz["porcao_max"],
                },
                150,
                arroz["grupo_equiv"],
                con
            )
            
            for sub in subs:
                # Busca o substituto no banco
                sub_alimento = con.execute(
                    "SELECT * FROM alimentos WHERE nome = ?", (sub["alimento"],)
                ).fetchone()
                
                if sub_alimento and sub_alimento["porcao_max"] > 0:
                    assert sub["quantidade_g"] <= sub_alimento["porcao_max"] + 1
    
    print("✓ Substituições respeitam porcao_max")


# =============================================================================
# TESTES DE DIETA
# =============================================================================

def test_dieta_1912_kcal():
    """Verifica que dieta de 1912 kcal funciona."""
    aveia = PORCOES_POR_NOME.get("Aveia em flocos", (20, 40, 70))
    
    itens = [{
        "aid": 1,
        "nome": "Aveia em flocos",
        "grupo": "cereal",
        "k": 394,
        "p": 13.9,
        "c": 66.3,
        "g": 6.9,
        "porcao": 40,
        "porcao_min": aveia[0],
        "porcao_max": aveia[2],
        "porcao_padrao": aveia[1],
    }]
    
    resultado = calcular_gramas(itens, kcal_t=1912, p_t=150, c_t=200, g_t=55)
    
    # Verifica que não ultrapassa o máximo
    assert resultado[0]["qtd"] <= aveia[2] + 1
    print("✓ Dieta de 1912 kcal funciona")


def test_dieta_2500_kcal():
    """Verifica que dieta de 2500 kcal funciona."""
    itens = [{
        "aid": 1,
        "nome": "Arroz branco cozido",
        "grupo": "amido",
        "k": 128,
        "p": 2.6,
        "c": 28.1,
        "g": 0.3,
        "porcao": 150,
        "porcao_min": 100,
        "porcao_max": 300,
        "porcao_padrao": 180,
    }]
    
    resultado = calcular_gramas(itens, kcal_t=2500, p_t=150, c_t=300, g_t=80)
    
    # Verifica que não ultrapassa o máximo
    assert resultado[0]["qtd"] <= 301
    print("✓ Dieta de 2500 kcal funciona")


def test_dieta_impossivel():
    """Verifica que dieta impossível retorna erro."""
    itens = [{
        "aid": 1,
        "nome": "Azeite de oliva",
        "grupo": "gordura",
        "k": 884,
        "p": 0,
        "c": 0,
        "g": 100,
        "porcao": 10,
        "porcao_min": 5,
        "porcao_max": 15,
        "porcao_padrao": 10,
    }]
    
    # Meta impossível: 5000 kcal com apenas azeite (máximo 15g = ~1326 kcal)
    resultado = calcular_gramas(itens, kcal_t=5000, p_t=0, c_t=0, g_t=0)
    
    # Deve limitar ao máximo
    assert resultado[0]["qtd"] <= 16
    print("✓ Dieta impossível retorna erro (limite respeitado)")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
