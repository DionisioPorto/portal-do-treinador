"""
Importador de dados da TBCA a partir do arquivo alimentos.txt.

Formato do arquivo:
- Cada linha é um JSON com campos: codigo, classe, descricao, nutrientes
- nutrientes é uma lista de objetos com: Componente, Unidades, Valor por 100g
- Os valores nutricionais já estão por 100g

Uso:
    python -m nutricao.tbca_importer --file alimentos.txt
    python -m nutricao.tbca_importer --file alimentos.txt --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

# Adiciona o diretório pai ao path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nutricao.database import (
    importar_alimento,
    buscar_alimento_por_codigo,
    get_connection,
)
from nutricao.normalizer import normalizar_nome, validar_nutricao


def parsear_alimentos_txt(caminho_arquivo):
    """Parseia o arquivo alimentos.txt da TBCA.
    
    Args:
        caminho_arquivo: Caminho para o arquivo alimentos.txt
        
    Yields:
        Dict com dados do alimento parseado
    """
    with open(caminho_arquivo, 'r', encoding='utf-8') as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            
            try:
                data = json.loads(linha)
            except json.JSONDecodeError:
                continue
            
            codigo = data.get("codigo", "")
            classe = data.get("classe", "")
            descricao = data.get("descricao", "")
            nutrientes = data.get("nutrientes", [])
            
            # Extrai valores nutricionais
            kcal = 0
            proteina = 0
            carbo = 0
            gordura = 0
            
            for nut in nutrientes:
                componente = nut.get("Componente", "").lower()
                valor = nut.get("Valor por 100g", "0")
                
                # Converte valor para float ( substitui vírgula por ponto)
                try:
                    valor = float(str(valor).replace(",", "."))
                except (ValueError, TypeError):
                    valor = 0
                
                # Mapeia componentes
                if componente == "energia" and nut.get("Unidades") == "kcal":
                    kcal = valor
                elif componente == "proteína":
                    proteina = valor
                elif componente == "carboidrato total":
                    carbo = valor
                elif componente == "lipídeos":
                    gordura = valor
            
            # Valida nutrição
            valido, erro = validar_nutricao(kcal, proteina, carbo, gordura)
            if not valido:
                continue
            
            yield {
                "codigo": codigo,
                "classe": classe,
                "descricao": descricao,
                "kcal": kcal,
                "proteinas": proteina,
                "carbs": carbo,
                "gorduras": gordura,
            }


def mapear_grupo_equiv(classe):
    """Mapeia a classe TBCA para grupo de equivalência.
    
    Args:
        classe: Classe do alimento na TBCA
        
    Returns:
        Grupo de equivalência
    """
    classe_lower = classe.lower()
    
    if "cereal" in classe_lower or "arroz" in classe_lower or "massa" in classe_lower:
        return "amido"
    if "vegetal" in classe_lower or "verdura" in classe_lower or "legume" in classe_lower:
        return "legume"
    if "fruta" in classe_lower:
        return "fruta"
    if "carne" in classe_lower or "proteína" in classe_lower or "frango" in classe_lower or "peixe" in classe_lower:
        return "proteina"
    if "laticínio" in classe_lower or "leite" in classe_lower or "queijo" in classe_lower:
        return "laticinio"
    if "gordura" in classe_lower or "óleo" in classe_lower or "azeite" in classe_lower:
        return "gordura"
    if "leguminosa" in classe_lower or "feijão" in classe_lower or "grão" in classe_lower:
        return "leguminosa"
    
    return "outro"


def importar_tbca_txt(caminho_arquivo, dry_run=False):
    """Importa alimentos do arquivo alimentos.txt da TBCA.
    
    Args:
        caminho_arquivo: Caminho para o arquivo alimentos.txt
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
    
    alimentos = list(parsear_alimentos_txt(caminho_arquivo))
    
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
            {"codigo": a["codigo"], "nome": a["descricao"][:50], "acao": "novo"}
            for a in alimentos[:20]
        ]
        return resultado
    
    for alimento in alimentos:
        # Verifica se já existe
        existente = buscar_alimento_por_codigo("TBCA", alimento["codigo"])
        if existente:
            resultado["duplicados"] += 1
            continue
        
        # Mapeia grupo de equivalência
        grupo_equiv = mapear_grupo_equiv(alimento["classe"])
        
        # Prepara dados para importação
        dados = {
            "nome": alimento["descricao"],
            "categoria": alimento["classe"],
            "grupo_equiv": grupo_equiv,
            "kcal": alimento["kcal"],
            "proteinas": alimento["proteinas"],
            "carbs": alimento["carbs"],
            "gorduras": alimento["gorduras"],
            "porcao": 100,
            "porcao_min": 50,
            "porcao_max": 300,
            "porcao_padrao": 150,
            "fonte": "TBCA",
            "codigo_fonte": alimento["codigo"],
            "marca": "",
            "qualidade_dados": "alta",
            "origem_confiavel": 1,
        }
        
        # Importa
        sucesso, msg, _ = importar_alimento(dados)
        if sucesso:
            resultado["importados"] += 1
        else:
            resultado["rejeitados"] += 1
            if len(resultado["detalhes"]) < 10:
                resultado["detalhes"].append({
                    "codigo": alimento["codigo"],
                    "nome": alimento["descricao"][:50],
                    "erro": msg,
                })
    
    return resultado


def main():
    """Função principal do importador TBCA."""
    parser = argparse.ArgumentParser(
        description="Importação de dados da TBCA a partir de alimentos.txt"
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Caminho para o arquivo alimentos.txt"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula a importação sem alterar o banco"
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print(f"IMPORTANDO TBCA: {args.file}")
    print(f"{'='*60}")
    
    resultado = importar_tbca_txt(args.file, dry_run=args.dry_run)
    
    if args.dry_run:
        print(f"\n[DRY RUN] Simulação de importação:")
        print(f"  Total de alimentos: {resultado['total']}")
        print(f"\nPrimeiros 20 alimentos:")
        for a in resultado.get("detalhes", []):
            print(f"  - [{a['codigo']}] {a['nome']}")
    else:
        print(f"\nResultado:")
        print(f"  Total processados: {resultado['total']}")
        print(f"  Importados: {resultado['importados']}")
        print(f"  Duplicados: {resultado['duplicados']}")
        print(f"  Rejeitados: {resultado['rejeitados']}")
        
        if resultado.get("detalhes"):
            print(f"\nDetalhes dos erros:")
            for d in resultado["detalhes"]:
                print(f"  - [{d['codigo']}] {d['nome']}: {d['erro']}")


if __name__ == "__main__":
    main()
