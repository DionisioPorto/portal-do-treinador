"""
Acesso ao banco de dados nutricional do Portal do Treinador.

Responsável por:
- Importar alimentos no banco local
- Atualizar alimentos existentes
- Evitar duplicatas
- Desativar alimentos obsoletos
"""

import sqlite3
import datetime
from pathlib import Path

from .normalizer import normalizar_nome, normalizar_alimento, validar_nutricao


def get_db_path():
    """Retorna o caminho do banco de dados."""
    import os
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = os.environ.get("PORTAL_DATA_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or str(base_dir)
    return Path(data_dir) / "dados.db"


SCHEMA_ALIMENTOS = """
CREATE TABLE IF NOT EXISTS alimentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    categoria TEXT NOT NULL,
    grupo_equiv TEXT NOT NULL,
    kcal REAL DEFAULT 0,
    proteinas REAL DEFAULT 0,
    carbs REAL DEFAULT 0,
    gorduras REAL DEFAULT 0,
    porcao REAL DEFAULT 100,
    porcao_min REAL DEFAULT 0,
    porcao_max REAL DEFAULT 0,
    porcao_padrao REAL DEFAULT 0,
    refeicoes_permitidas TEXT DEFAULT '',
    tipo_equivalencia TEXT DEFAULT '',
    fonte TEXT DEFAULT 'manual',
    codigo_fonte TEXT DEFAULT '',
    marca TEXT DEFAULT '',
    nome_normalizado TEXT DEFAULT '',
    unidade_base TEXT DEFAULT 'g',
    ativo INTEGER DEFAULT 1,
    qualidade_dados TEXT DEFAULT 'media',
    origem_confiavel INTEGER DEFAULT 0,
    data_importacao TEXT DEFAULT '',
    data_atualizacao TEXT DEFAULT ''
);
"""


def init_db():
    """Inicializa o banco de dados com o schema necessário."""
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_ALIMENTOS)
        conn.commit()
    finally:
        conn.close()


def get_connection():
    """Cria uma conexão com o banco de dados."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Garante que o schema existe
    conn.executescript(SCHEMA_ALIMENTOS)
    return conn


def buscar_alimento_por_codigo(fonte, codigo_fonte):
    """Busca um alimento pela chave lógica (fonte + codigo_fonte).
    
    Args:
        fonte: Fonte do alimento (TBCA, OpenFoodFacts, manual)
        codigo_fonte: Código original na fonte
        
    Returns:
        Dict com dados do alimento ou None
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM alimentos WHERE fonte = ? AND codigo_fonte = ?",
            (fonte, codigo_fonte)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def buscar_alimento_por_nome_normalizado(nome_normalizado):
    """Busca um alimento pelo nome normalizado.
    
    Args:
        nome_normalizado: Nome normalizado do alimento
        
    Returns:
        Dict com dados do alimento ou None
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM alimentos WHERE nome_normalizado = ?",
            (nome_normalizado,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def importar_alimento(dados):
    """Importa um novo alimento para o banco.
    
    Args:
        dados: Dict com dados do alimento (já normalizados)
        
    Returns:
        (bool, str, int): (sucesso, mensagem, alimento_id)
    """
    # Normaliza os dados
    dados_norm = normalizar_alimento(dados)
    
    # Verifica duplicata por fonte + codigo_fonte
    if dados_norm.get("codigo_fonte"):
        existente = buscar_alimento_por_codigo(
            dados_norm["fonte"],
            dados_norm["codigo_fonte"]
        )
        if existente:
            return False, f"Alimento já existe (id={existente['id']})", existente["id"]
    
    # Verifica duplicata por nome normalizado
    existente = buscar_alimento_por_nome_normalizado(dados_norm["nome_normalizado"])
    if existente:
        return False, f"Alimento já existe com nome similar (id={existente['id']})", existente["id"]
    
    # Insere no banco
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO alimentos (
                nome, categoria, grupo_equiv, kcal, proteinas, carbs, gorduras,
                porcao, porcao_min, porcao_max, porcao_padrao,
                refeicoes_permitidas, tipo_equivalencia,
                fonte, codigo_fonte, marca, nome_normalizado, unidade_base,
                ativo, qualidade_dados, origem_confiavel,
                data_importacao, data_atualizacao
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                dados_norm["nome"],
                dados_norm["categoria"],
                dados_norm["grupo_equiv"],
                dados_norm["kcal"],
                dados_norm["proteinas"],
                dados_norm["carbs"],
                dados_norm["gorduras"],
                dados_norm["porcao"],
                dados_norm["porcao_min"],
                dados_norm["porcao_max"],
                dados_norm["porcao_padrao"],
                dados_norm.get("refeicoes_permitidas", ""),
                dados_norm["tipo_equivalencia"],
                dados_norm["fonte"],
                dados_norm["codigo_fonte"],
                dados_norm["marca"],
                dados_norm["nome_normalizado"],
                dados_norm["unidade_base"],
                1,  # ativo
                dados_norm["qualidade_dados"],
                dados_norm["origem_confiavel"],
                datetime.datetime.now().isoformat(),
                datetime.datetime.now().isoformat(),
            )
        )
        conn.commit()
        return True, "Alimento importado com sucesso", cursor.lastrowid
    finally:
        conn.close()


def atualizar_alimento(alimento_id, dados):
    """Atualiza um alimento existente.
    
    Args:
        alimento_id: ID do alimento no banco
        dados: Dict com novos dados
        
    Returns:
        (bool, str): (sucesso, mensagem)
    """
    conn = get_connection()
    try:
        # Verifica se existe
        existente = conn.execute(
            "SELECT * FROM alimentos WHERE id = ?", (aluno_id,)
        ).fetchone()
        if not existente:
            return False, "Alimento não encontrado"
        
        # Atualiza campos
        conn.execute(
            """UPDATE alimentos SET
                nome = ?, categoria = ?, grupo_equiv = ?,
                kcal = ?, proteinas = ?, carbs = ?, gorduras = ?,
                porcao = ?, porcao_min = ?, porcao_max = ?, porcao_padrao = ?,
                refeicoes_permitidas = ?, tipo_equivalencia = ?,
                marca = ?, nome_normalizado = ?,
                qualidade_dados = ?, origem_confiavel = ?,
                data_atualizacao = ?
            WHERE id = ?""",
            (
                dados.get("nome", existente["nome"]),
                dados.get("categoria", existente["categoria"]),
                dados.get("grupo_equiv", existente["grupo_equiv"]),
                dados.get("kcal", existente["kcal"]),
                dados.get("proteinas", existente["proteinas"]),
                dados.get("carbs", existente["carbs"]),
                dados.get("gorduras", existente["gorduras"]),
                dados.get("porcao", existente["porcao"]),
                dados.get("porcao_min", existente["porcao_min"]),
                dados.get("porcao_max", existente["porcao_max"]),
                dados.get("porcao_padrao", existente["porcao_padrao"]),
                dados.get("refeicoes_permitidas", existente["refeicoes_permitidas"]),
                dados.get("tipo_equivalencia", existente["tipo_equivalencia"]),
                dados.get("marca", existente["marca"]),
                normalizar_nome(dados.get("nome", existente["nome"])),
                dados.get("qualidade_dados", existente["qualidade_dados"]),
                dados.get("origem_confiavel", existente["origem_confiavel"]),
                datetime.datetime.now().isoformat(),
                alimento_id,
            )
        )
        conn.commit()
        return True, "Alimento atualizado com sucesso"
    finally:
        conn.close()


def desativar_alimento(alimento_id):
    """Desativa um alimento sem apagar o histórico.
    
    Args:
        alimento_id: ID do alimento
        
    Returns:
        (bool, str): (sucesso, mensagem)
    """
    conn = get_connection()
    try:
        existente = conn.execute(
            "SELECT * FROM alimentos WHERE id = ?", (alimento_id,)
        ).fetchone()
        if not existente:
            return False, "Alimento não encontrado"
        
        conn.execute(
            "UPDATE alimentos SET ativo = 0, data_atualizacao = ? WHERE id = ?",
            (datetime.datetime.now().isoformat(), alimento_id)
        )
        conn.commit()
        return True, "Alimento desativado com sucesso"
    finally:
        conn.close()


def listar_alimentos(fonte=None, categoria=None, grupo_equiv=None, ativo=None, qualidade=None):
    """Lista alimentos com filtros opcionais.
    
    Args:
        fonte: Filtra por fonte
        categoria: Filtra por categoria
        grupo_equiv: Filtra por grupo de equivalência
        ativo: Filtra por status ativo
        qualidade: Filtra por qualidade dos dados
        
    Returns:
        Lista de dicts com alimentos
    """
    conn = get_connection()
    try:
        query = "SELECT * FROM alimentos WHERE 1=1"
        params = []
        
        if fonte:
            query += " AND fonte = ?"
            params.append(fonte)
        if categoria:
            query += " AND categoria = ?"
            params.append(categoria)
        if grupo_equiv:
            query += " AND grupo_equiv = ?"
            params.append(grupo_equiv)
        if ativo is not None:
            query += " AND ativo = ?"
            params.append(1 if ativo else 0)
        if qualidade:
            query += " AND qualidade_dados = ?"
            params.append(qualidade)
        
        query += " ORDER BY nome"
        
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
