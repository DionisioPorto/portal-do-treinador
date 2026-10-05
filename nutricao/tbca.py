"""
Importador da TBCA (Tabela Brasileira de Composição de Alimentos).

A TBCA é a fonte principal para alimentos brasileiros e preparações.

IMPORTANTE: A TBCA é mantida pela UNICAMP/NEPA. Os dados são públicos
para uso acadêmico e pesquisa. Para uso comercial, verifique os termos
de licenciamento em https://www.nepa.unicamp.br/tbca/

Este módulo NÃO faz scraping do site. Ele recebe um arquivo CSV/XLSX
oficialmente disponibilizado pelo usuário.
"""

import csv
import io
from pathlib import Path

from .normalizer import normalizar_alimento, validar_nutricao


# Mapeamento de colunas esperadas no CSV da TBCA
COLUNAS_TBCA = {
    "codigo": ["codigo", "id", "código", "code"],
    "nome": ["nome", "alimento", "food", "descricao"],
    "grupo": ["grupo", "categoria", "group", "tipo"],
    "marca": ["marca", "brand", ""],
    "kcal": ["kcal", "calorias", "energy", "valor_energetico"],
    "proteina": ["proteina", "proteinas", "protein"],
    "carbo": ["carbo", "carboidrato", "carboidratos", "carbohydrate"],
    "gordura": ["gordura", "gorduras", "fat", "lipideos"],
}


def _encontrar_coluna(header, opcoes):
    """Encontra a coluna no header do CSV.
    
    Args:
        header: Lista de colunas do CSV
        opcoes: Lista de nomes possíveis para a coluna
        
    Returns:
        Índice da coluna ou -1
    """
    header_lower = [h.lower().strip() for h in header]
    for opcao in opcoes:
        if opcao.lower() in header_lower:
            return header_lower.index(opcao.lower())
    return -1


def _extrair_valor(row, idx, default=0):
    """Extrai um valor numérico de uma célula do CSV.
    
    Args:
        row: Linha do CSV
        idx: Índice da coluna
        default: Valor padrão se não encontrar
        
    Returns:
        Valor float
    """
    if idx < 0 or idx >= len(row):
        return default
    try:
        valor = str(row[idx]).replace(",", ".").strip()
        return float(valor) if valor else default
    except (ValueError, TypeError):
        return default


def parsear_csv_tbca(conteudo_csv):
    """Parseia um arquivo CSV da TBCA.
    
    Args:
        conteudo_csv: Conteúdo do CSV (string ou bytes)
        
    Returns:
        Lista de dicts com alimentos parseados
    """
    if isinstance(conteudo_csv, bytes):
        conteudo_csv = conteudo_csv.decode('utf-8')
    
    reader = csv.reader(io.StringIO(conteudo_csv))
    header = next(reader)
    
    # Encontra índices das colunas
    idx_codigo = _encontrar_coluna(header, COLUNAS_TBCA["codigo"])
    idx_nome = _encontrar_coluna(header, COLUNAS_TBCA["nome"])
    idx_grupo = _encontrar_coluna(header, COLUNAS_TBCA["grupo"])
    idx_marca = _encontrar_coluna(header, COLUNAS_TBCA["marca"])
    idx_kcal = _encontrar_coluna(header, COLUNAS_TBCA["kcal"])
    idx_proteina = _encontrar_coluna(header, COLUNAS_TBCA["proteina"])
    idx_carbo = _encontrar_coluna(header, COLUNAS_TBCA["carbo"])
    idx_gordura = _encontrar_coluna(header, COLUNAS_TBCA["gordura"])
    
    if idx_nome < 0:
        raise ValueError("Coluna 'nome' não encontrada no CSV")
    
    alimentos = []
    for row in reader:
        if not row or not row[idx_nome].strip():
            continue
        
        nome = row[idx_nome].strip()
        codigo = row[idx_codigo].strip() if idx_codigo >= 0 else ""
        grupo = row[idx_grupo].strip() if idx_grupo >= 0 else ""
        marca = row[idx_marca].strip() if idx_marca >= 0 else ""
        
        kcal = _extrair_valor(row, idx_kcal)
        proteina = _extrair_valor(row, idx_proteina)
        carbo = _extrair_valor(row, idx_carbo)
        gordura = _extrair_valor(row, idx_gordura)
        
        # Valida nutrição
        valido, erro = validar_nutricao(kcal, proteina, carbo, gordura)
        if not valido:
            continue  # Pula alimentos sem dados nutricionais
        
        alimentos.append({
            "nome": nome,
            "codigo_fonte": codigo,
            "grupo": grupo,
            "marca": marca,
            "kcal": kcal,
            "proteinas": proteina,
            "carbs": carbo,
            "gorduras": gordura,
            "fonte": "TBCA",
            "qualidade_dados": "alta",
            "origem_confiavel": 1,
        })
    
    return alimentos


def importar_tbca_csv(caminho_arquivo, dry_run=False):
    """Importa alimentos de um arquivo CSV da TBCA.
    
    Args:
        caminho_arquivo: Caminho para o arquivo CSV
        dry_run: Se True, apenas simula a importação
        
    Returns:
        Dict com resultados da importação
    """
    caminho = Path(caminho_arquivo)
    if not caminho.exists():
        return {
            "sucesso": False,
            "erro": f"Arquivo não encontrado: {caminho}",
            "importados": 0,
            "atualizados": 0,
            "duplicados": 0,
            "rejeitados": 0,
        }
    
    with open(caminho, 'r', encoding='utf-8') as f:
        conteudo = f.read()
    
    alimentos = parsear_csv_tbca(conteudo)
    
    resultado = {
        "sucesso": True,
        "total": len(alimentos),
        "importados": 0,
        "atualizados": 0,
        "duplicados": 0,
        "rejeitados": 0,
        "detalhes": [],
    }
    
    if dry_run:
        resultado["detalhes"] = [
            {"nome": a["nome"], "acao": "novo"} for a in alimentos
        ]
        return resultado
    
    from .database import importar_alimento, buscar_alimento_por_codigo
    
    for alimento in alimentos:
        # Verifica se já existe
        existente = buscar_alimento_por_codigo("TBCA", alimento["codigo_fonte"])
        if existente:
            resultado["duplicados"] += 1
            continue
        
        # Importa
        sucesso, msg, _ = importar_alimento(alimento)
        if sucesso:
            resultado["importados"] += 1
        else:
            resultado["rejeitados"] += 1
            resultado["detalhes"].append({"nome": alimento["nome"], "erro": msg})
    
    return resultado
