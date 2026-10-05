"""
CLI de importação de alimentos.

Uso:
    python -m nutricao.importer --source tbca --file arquivo.csv
    python -m nutricao.importer --source openfoodfacts --ean 7891234567890
    python -m nutricao.importer --source tbca --file arquivo.csv --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

from .tbca import importar_tbca_csv
from .openfoodfacts import importar_produto, buscar_produtos
from .database import listar_alimentos


def main():
    """Função principal do CLI de importação."""
    parser = argparse.ArgumentParser(
        description="Importação de alimentos para o Portal do Treinador"
    )
    parser.add_argument(
        "--source",
        choices=["tbca", "openfoodfacts"],
        required=True,
        help="Fonte dos dados"
    )
    parser.add_argument(
        "--file",
        help="Caminho para o arquivo CSV (TBCA)"
    )
    parser.add_argument(
        "--ean",
        help="Código de barras EAN (Open Food Facts)"
    )
    parser.add_argument(
        "--search",
        help="Termo de busca (Open Food Facts)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula a importação sem alterar o banco"
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Atualiza alimentos existentes"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Lista alimentos do banco"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Mostra estatísticas do banco"
    )
    
    args = parser.parse_args()
    
    # Lista alimentos
    if args.list:
        alimentos = listar_alimentos()
        print(f"\n{'='*60}")
        print(f"ALIMENTOS NO BANCO: {len(alimentos)}")
        print(f"{'='*60}")
        for a in alimentos[:20]:  # Mostra apenas os 20 primeiros
            print(f"  {a['nome'][:40]:40} | {a['fonte']:15} | {a['kcal']:6.1f} kcal")
        if len(alimentos) > 20:
            print(f"  ... e mais {len(alimentos) - 20} alimentos")
        return
    
    # Estatísticas
    if args.stats:
        alimentos = listar_alimentos()
        fontes = {}
        for a in alimentos:
            fontes[a["fonte"]] = fontes.get(a["fonte"], 0) + 1
        
        print(f"\n{'='*60}")
        print("ESTATÍSTICAS DO BANCO NUTRICIONAL")
        print(f"{'='*60}")
        print(f"Total de alimentos: {len(alimentos)}")
        print(f"\nPor fonte:")
        for fonte, count in sorted(fontes.items()):
            print(f"  {fonte:20}: {count}")
        return
    
    # Importa TBCA
    if args.source == "tbca":
        if not args.file:
            print("Erro: --file é obrigatório para fonte TBCA")
            sys.exit(1)
        
        print(f"\n{'='*60}")
        print(f"IMPORTANDO TBCA: {args.file}")
        print(f"{'='*60}")
        
        resultado = importar_tbca_csv(args.file, dry_run=args.dry_run)
        
        if args.dry_run:
            print(f"\n[DRY RUN] Simulação de importação:")
            print(f"  Total de alimentos: {resultado['total']}")
            print(f"\nPrimeiros 10 alimentos:")
            for a in resultado.get("detalhes", [])[:10]:
                print(f"  - {a['nome']}")
        else:
            print(f"\nResultado:")
            print(f"  Importados: {resultado['importados']}")
            print(f"  Duplicados: {resultado['duplicados']}")
            print(f"  Rejeitados: {resultado['rejeitados']}")
            
            if resultado.get("detalhes"):
                print(f"\nDetalhes:")
                for d in resultado["detalhes"][:10]:
                    print(f"  - {d}")
        
        return
    
    # Importa Open Food Facts
    if args.source == "openfoodfacts":
        if args.ean:
            print(f"\n{'='*60}")
            print(f"IMPORTANDO OPEN FOOD FACTS: EAN {args.ean}")
            print(f"{'='*60}")
            
            sucesso, msg, alimento_id = importar_produto(args.ean)
            
            if sucesso:
                print(f"✓ {msg} (id={alimento_id})")
            else:
                print(f"✗ {msg}")
            
            return
        
        if args.search:
            print(f"\n{'='*60}")
            print(f"BUSCANDO OPEN FOOD FACTS: '{args.search}'")
            print(f"{'='*60}")
            
            produtos = buscar_produtos(args.search)
            
            if not produtos:
                print("Nenhum produto encontrado.")
                return
            
            print(f"\n{len(produtos)} produtos encontrados:")
            for i, p in enumerate(produtos[:10], 1):
                print(f"  {i}. {p['nome'][:40]:40} | {p['marca'][:20]:20} | {p['codigo_barras']}")
            
            return
        
        print("Erro: --ean ou --search é obrigatório para fonte Open Food Facts")
        sys.exit(1)


if __name__ == "__main__":
    main()
