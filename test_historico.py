"""Testes do histórico de planos (versões de treino/dieta salvas no PDF).

Como executar:
    cd portal-do-treinador
    python -m pytest test_historico.py -v
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ["PORTAL_DATA_DIR"] = tempfile.mkdtemp()
os.environ["SECRET_KEY"] = "test-secret-key"

from app import app, get_db  # noqa: E402


def _login(client):
    return client.post("/login", data={"usuario": "admin", "senha": "portal123"})


def _aluno_id():
    with app.app_context():
        return get_db().execute(
            "SELECT id FROM alunos ORDER BY id LIMIT 1"
        ).fetchone()["id"]


def _linhas(aluno_id, tipo=None):
    with app.app_context():
        con = get_db()
        if tipo:
            return con.execute(
                "SELECT * FROM historico_planos WHERE aluno_id = ? AND tipo = ? ORDER BY id",
                (aluno_id, tipo),
            ).fetchall()
        return con.execute(
            "SELECT * FROM historico_planos WHERE aluno_id = ? ORDER BY id",
            (aluno_id,),
        ).fetchall()


def test_paginas_historico_respondem():
    client = app.test_client()
    _login(client)
    assert client.get("/historico").status_code == 200
    aluno_id = _aluno_id()
    assert client.get(f"/aluno/{aluno_id}/historico").status_code == 200


def test_salva_versao_unica_de_treino():
    client = app.test_client()
    _login(client)
    aluno_id = _aluno_id()
    antes = len(_linhas(aluno_id, "treino"))

    r1 = client.get(f"/aluno/{aluno_id}/treino/imprimir")
    assert r1.status_code == 200
    assert "Plano de treino" in r1.get_data(as_text=True)
    assert len(_linhas(aluno_id, "treino")) == antes + 1

    # Reabrir sem alterações NÃO deve duplicar a versão.
    client.get(f"/aluno/{aluno_id}/treino/imprimir")
    assert len(_linhas(aluno_id, "treino")) == antes + 1


def test_nova_versao_ao_mudar_treino():
    client = app.test_client()
    _login(client)
    aluno_id = _aluno_id()
    client.get(f"/aluno/{aluno_id}/treino/imprimir")
    n = len(_linhas(aluno_id, "treino"))

    with app.app_context():
        con = get_db()
        treino = con.execute(
            "SELECT id FROM treinos WHERE aluno_id = ? ORDER BY id LIMIT 1", (aluno_id,)
        ).fetchone()
        con.execute(
            "INSERT INTO exercicios (treino_id, nome, series) VALUES (?, ?, ?)",
            (treino["id"], "Exercício de teste", "3"),
        )
        con.commit()

    client.get(f"/aluno/{aluno_id}/treino/imprimir")
    assert len(_linhas(aluno_id, "treino")) == n + 1

    with app.app_context():
        con = get_db()
        con.execute("DELETE FROM exercicios WHERE nome = 'Exercício de teste'")
        con.commit()


def test_dieta_e_alias_de_impressao():
    client = app.test_client()
    _login(client)
    aluno_id = _aluno_id()
    # rota antiga /dieta/imprimir deve continuar funcionando (alias)
    r = client.get(f"/aluno/{aluno_id}/dieta/imprimir")
    assert r.status_code == 200
    assert _linhas(aluno_id, "dieta")


def test_detalhe_serve_versao_salva():
    client = app.test_client()
    _login(client)
    aluno_id = _aluno_id()
    client.get(f"/aluno/{aluno_id}/treino/imprimir")
    hist = _linhas(aluno_id, "treino")[-1]

    r = client.get(f"/historico/{hist['id']}")
    assert r.status_code == 200
    corpo = r.get_data(as_text=True)
    assert "Versão salva em" in corpo
    assert "Plano de treino" in corpo


def test_excluir_versao():
    client = app.test_client()
    _login(client)
    aluno_id = _aluno_id()
    client.get(f"/aluno/{aluno_id}/treino/imprimir")
    hist = _linhas(aluno_id, "treino")[-1]

    client.post(
        f"/historico/{hist['id']}/excluir",
        data={"voltar": f"/aluno/{aluno_id}/historico"},
    )
    with app.app_context():
        existe = get_db().execute(
            "SELECT 1 FROM historico_planos WHERE id = ?", (hist["id"],)
        ).fetchone()
    assert existe is None
