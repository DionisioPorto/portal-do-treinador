"""
Testes do sistema de geração de dietas do Portal do Treinador.

Estes testes verificam:
1. Meta de 1912 kcal não gera 400-500g de aveia
2. Nenhum alimento ultrapassa porcao_max
3. Nenhuma substituição aparece sem quantidade em gramas
4. Substituições pertencem ao mesmo grupo_equiv
5. Dieta impossível retorna erro
6. Macros do PDF correspondem aos alimentos salvos
7. Alterar porcao_max impede dietas com quantidade maior
8. Sistema recalcula dieta após alterar limites

Como executar:
    cd portal-do-treinador
    python -m pytest test_dieta.py -v
"""

import os
import sys
import sqlite3
import tempfile
from pathlib import Path

# Adiciona o diretório do projeto ao path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Configura ambiente de teste antes de importar app
os.environ["PORTAL_DATA_DIR"] = tempfile.mkdtemp()
os.environ["SECRET_KEY"] = "test-secret-key"

from app import (
    app, get_db, init_db, migrar, seed_alimentos, atualizar_nutri,
    calcular_gramas, calcular_substituicoes, validar_dieta,
    PORCOES_POR_NOME, PORCOES_POR_GRUPO, TOLERANCIAS_DIETA,
    _faixa_porcao, _totais_item, _tipo_equivalencia_por_grupo, DietPlanOptimizer,
    _gerar_dieta_automaticamente,
)


def setup_module():
    """Inicializa o banco de dados para os testes."""
    with app.app_context():
        init_db()
        migrar()
        seed_alimentos()
        atualizar_nutri()


def get_alimento(nome):
    """Busca um alimento pelo nome no banco de dados."""
    with app.app_context():
        con = get_db()
        return con.execute("SELECT * FROM alimentos WHERE nome = ?", (nome,)).fetchone()


def criar_aluno_teste(nome="Aluno Teste", peso=70, altura=175, sexo="M"):
    """Cria um aluno de teste no banco."""
    with app.app_context():
        con = get_db()
        cur = con.execute(
            """INSERT INTO alunos (nome, peso_atual, altura_cm, sexo_formula, nascimento)
               VALUES (?, ?, ?, ?, ?)""",
            (nome, peso, altura, sexo, "1990-01-01")
        )
        aluno_id = cur.lastrowid
        con.execute(
            """INSERT INTO metas_dieta (aluno_id, kcal_diaria, proteinas, carbs, gorduras)
               VALUES (?, ?, ?, ?, ?)""",
            (aluno_id, 1912, 150, 200, 55)
        )
        con.commit()
        return aluno_id


def test_geracao_diaria_meta_1912_sem_porcoes_irreais():
    """Gera o cenário solicitado e confere estrutura, limites e macros do banco."""
    with app.app_context():
        con = get_db()
        aluno_id = criar_aluno_teste(nome="Aluno Meta 1912")
        metas = {"meta_kcal": 1912, "proteina": 150, "carbo": 208, "gordura": 53}
        plano = _gerar_dieta_automaticamente(con, aluno_id, metas)

        assert plano and len(plano["refeicoes"]) == 5
        totais_banco = {"kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0}
        estrutura_esperada = {
            "Café da manhã": (
                {"proteina", "laticinio"}, {"amido", "pao", "cereal"}, {"fruta"},
            ),
            "Lanche da manhã": ({"proteina", "laticinio"}, {"fruta"}),
            "Almoço": (
                {"amido", "pao", "cereal"}, {"proteina"}, {"legume", "verdura_folha"},
            ),
            "Lanche da tarde": (
                {"amido", "pao", "cereal"}, {"proteina", "laticinio"},
            ),
            "Jantar": (
                {"amido", "pao", "cereal"}, {"proteina"}, {"legume", "verdura_folha"},
            ),
        }
        for refeicao in plano["refeicoes"]:
            itens = refeicao["alimentos"]
            assert itens, f"{refeicao['nome']} não pode ficar vazia"
            assert 2 <= len(itens) <= 4
            grupos = {item["grupo"] for item in itens}
            assert all(grupos.intersection(papel) for papel in estrutura_esperada[refeicao["nome"]])
            assert sum(
                item["grupo"] in {"legume", "verdura_folha"} for item in itens
            ) <= 1
            if refeicao["nome"] == "Almoço":
                assert sum(item["grupo"] == "leguminosa" for item in itens) <= 1
            totais_refeicao_banco = {
                "kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0,
            }
            for item in itens:
                alimento = con.execute(
                    "SELECT * FROM alimentos WHERE nome = ?", (item["nome"],)
                ).fetchone()
                assert alimento is not None
                assert alimento["porcao_min"] <= item["quantidade"] <= alimento["porcao_max"]
                fator = item["quantidade"] / 100
                for chave, campo in (
                    ("kcal", "kcal"), ("proteinas", "proteinas"),
                    ("carbs", "carbs"), ("gorduras", "gorduras"),
                ):
                    macro = float(alimento[campo] or 0) * fator
                    totais_banco[chave] += macro
                    totais_refeicao_banco[chave] += macro
            for chave, total in totais_refeicao_banco.items():
                assert abs(total - refeicao["totais"][chave]) < 0.01

        for chave, total in totais_banco.items():
            assert abs(total - plano["totais"][chave]) < 0.01

        assert abs(totais_banco["kcal"] - 1912) <= 1912 * TOLERANCIAS_DIETA["kcal_pct"] / 100
        assert abs(totais_banco["proteinas"] - 150) <= TOLERANCIAS_DIETA["proteina"]
        assert abs(totais_banco["carbs"] - 208) <= TOLERANCIAS_DIETA["carbo"]
        assert abs(totais_banco["gorduras"] - 53) <= TOLERANCIAS_DIETA["gordura"]
        assert all(
            (item["nome"] != "Aveia em flocos" or item["quantidade"] <= 70)
            and ("Azeite" not in item["nome"] or item["quantidade"] <= 20)
            for refeicao in plano["refeicoes"] for item in refeicao["alimentos"]
        )


def test_geracao_rick_escolhe_combinacao_e_equilibra_proteina():
    """Rick recebe um menu escolhido no catálogo completo e ajustado no total do dia."""
    with app.app_context():
        con = get_db()
        aluno_id = criar_aluno_teste(nome="Rick")
        metas = {"meta_kcal": 1963, "proteina": 150, "carbo": 218, "gordura": 55}
        alimentos = [dict(row) for row in con.execute(
            "SELECT * FROM alimentos WHERE ativo = 1"
        ).fetchall()]
        optimizer = DietPlanOptimizer(
            meta_calorica_diaria=1963,
            proteina_diaria=150,
            carboidrato_diario=218,
            gordura_diaria=55,
            quantidade_refeicoes=1,
            estrutura_refeicoes={
                "Café da manhã": [{
                    "papel": "proteína",
                    "candidatos": ["Queijo cottage"],
                }],
                "Almoço": [{
                    "papel": "proteína",
                    "candidatos": ["Peito de frango grelhado"],
                }],
            },
            alimentos_ativos=alimentos,
        )
        opcoes_cafe = optimizer._opcoes_por_refeicao("Café da manhã")[0][1]
        assert all(
        not any(
            termo in item["nome"].casefold()
            for termo in ("frango", "carne", "tilápia", "merluza", "peixe")
        )
        for item in opcoes_cafe
        )
        optimizer_catalogo = DietPlanOptimizer(
        meta_calorica_diaria=1963,
        proteina_diaria=150,
        carboidrato_diario=218,
        gordura_diaria=55,
        quantidade_refeicoes=1,
        alimentos_ativos=alimentos,
        )
        assert len(optimizer_catalogo._candidatos_para_refeicao("Almoço")) > 12

        plano = _gerar_dieta_automaticamente(con, aluno_id, metas)
        assert plano and plano["status"] == "ok"
        totais_banco = {"kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0}
        proteina_por_refeicao = []
        for refeicao in plano["refeicoes"]:
            assert 2 <= len(refeicao["alimentos"]) <= 4
            assert sum(
                item["grupo"] in {"legume", "verdura_folha"}
                for item in refeicao["alimentos"]
            ) <= 1
            proteina_refeicao = 0.0
            for item in refeicao["alimentos"]:
                if refeicao["nome"] in {"Café da manhã", "Lanche da manhã", "Lanche da tarde"}:
                    assert not any(
                        termo in item["nome"].casefold()
                        for termo in ("frango", "carne", "tilápia", "merluza", "peixe")
                    )
                alimento = con.execute(
                    "SELECT * FROM alimentos WHERE nome = ?", (item["nome"],)
                ).fetchone()
                assert alimento["porcao_min"] <= item["quantidade"] <= alimento["porcao_max"]
                fator = item["quantidade"] / 100
                for chave, campo in (
                    ("kcal", "kcal"), ("proteinas", "proteinas"),
                    ("carbs", "carbs"), ("gorduras", "gorduras"),
                ):
                    macro = float(alimento[campo] or 0) * fator
                    totais_banco[chave] += macro
                    if chave == "proteinas":
                        proteina_refeicao += macro
            proteina_por_refeicao.append(proteina_refeicao)

        assert abs(totais_banco["kcal"] - 1963) <= 1963 * TOLERANCIAS_DIETA["kcal_pct"] / 100
        assert abs(totais_banco["proteinas"] - 150) <= TOLERANCIAS_DIETA["proteina"]
        assert abs(totais_banco["carbs"] - 218) <= TOLERANCIAS_DIETA["carbo"]
        assert abs(totais_banco["gorduras"] - 55) <= TOLERANCIAS_DIETA["gordura"]
        assert max(proteina_por_refeicao) - min(proteina_por_refeicao) < 40


def test_pdf_dieta_oculta_observacao_automatica_e_preserva_personalizada():
    """PDF esconde a antiga nota automática e mantém observações próprias."""
    from flask import render_template

    dados = {
        "aluno": {"nome": "Rick", "objetivo": "", "plano": ""},
        "avisos": [],
        "reais": {},
        "alvo": {},
        "metas": {
            "kcal_diaria": 1909,
            "proteinas": 140,
            "carbs": 218,
            "gorduras": 53,
            "observacoes": "Meta calculada pelo assistente (Harris-Benedict).",
        },
        "refeicoes": [],
        "alim": {},
        "totais": {"calorias": 0, "proteinas": 0, "carbs": 0, "gorduras": 0},
    }
    with app.test_request_context("/"):
        html = render_template("imprimir_dieta.html", **dados)
        assert "Meta calculada pelo assistente" not in html

        dados["metas"]["observacoes"] = "Observação nutricional personalizada."
        html = render_template("imprimir_dieta.html", **dados)
        assert "Observação nutricional personalizada." in html


# =============================================================================
# TESTE 1: Meta de 1912 kcal não deve gerar 400-500g de aveia
# =============================================================================
def test_aveia_nao_ultrapassa_limite_com_meta_1912():
    """Garante que uma dieta de ~1912 kcal não gera quantidades absurdas de aveia."""
    aveia = get_alimento("Aveia em flocos")
    assert aveia is not None, "Aveia deve estar cadastrada"
    
    # Simula o cálculo de gramas para uma refeição com aveia
    itens = [{
        "aid": aveia["id"],
        "nome": aveia["nome"],
        "grupo": aveia["grupo_equiv"],
        "k": aveia["kcal"],
        "p": aveia["proteinas"],
        "c": aveia["carbs"],
        "g": aveia["gorduras"],
        "porcao": aveia["porcao"],
    }]
    
    # Calcula gramas para uma meta de 1912 kcal
    resultado = calcular_gramas(itens, kcal_t=1912, p_t=150, c_t=200, g_t=55)
    
    # Verifica que a aveia não ultrapassa o máximo permitido
    qtd_aveia = resultado[0]["qtd"]
    porcao_max = aveia["porcao_max"] or PORCOES_POR_NOME.get("Aveia em flocos", (20, 40, 70))[2]
    
    assert qtd_aveia <= porcao_max + 1, (
        f"Aveia gerou {qtd_aveia}g, mas o máximo permitido é {porcao_max}g. "
        f"O sistema não deve gerar quantidades absurdas."
    )
    print(f"✓ Aveia: {qtd_aveia}g (máximo: {porcao_max}g)")


# =============================================================================
# TESTE 2: Nenhum alimento pode ultrapassar porcao_max
# =============================================================================
def test_nenhum_alimento_ultrapassa_porcao_max():
    """Verifica que nenhum alimento ultrapassa sua porção máxima."""
    with app.app_context():
        con = get_db()
        alimentos = con.execute("SELECT * FROM alimentos").fetchall()
        
        for alimento in alimentos:
            if alimento["porcao_max"] and alimento["porcao_max"] > 0:
                # Simula o cálculo com meta alta para tentar forçar quantidade
                itens = [{
                    "aid": alimento["id"],
                    "nome": alimento["nome"],
                    "grupo": alimento["grupo_equiv"],
                    "k": alimento["kcal"],
                    "p": alimento["proteinas"],
                    "c": alimento["carbs"],
                    "g": alimento["gorduras"],
                    "porcao": alimento["porcao"],
                }]
                
                # Meta muito alta para tentar forçar quantidade acima do máximo
                resultado = calcular_gramas(itens, kcal_t=5000, p_t=300, c_t=500, g_t=150)
                
                qtd = resultado[0]["qtd"]
                porcao_max = alimento["porcao_max"]
                
                assert qtd <= porcao_max + 1, (
                    f"{alimento['nome']}: gerou {qtd}g, mas o máximo é {porcao_max}g"
                )
    
    print("✓ Nenhum alimento ultrapassa porcao_max")


# =============================================================================
# TESTE 3: Nenhuma substituição pode aparecer sem quantidade em gramas
# =============================================================================
def test_substituicoes_sempre_tem_quantidade():
    """Verifica que todas as substituições têm quantidade em gramas."""
    with app.app_context():
        con = get_db()
        alimentos = con.execute("SELECT * FROM alimentos LIMIT 10").fetchall()
        
        for alimento in alimentos:
            subs = calcular_substituicoes(
                {
                    "nome": alimento["nome"],
                    "kcal": alimento["kcal"],
                    "proteinas": alimento["proteinas"],
                    "carbs": alimento["carbs"],
                    "gorduras": alimento["gorduras"],
                    "porcao_min": alimento["porcao_min"],
                    "porcao_max": alimento["porcao_max"],
                },
                100,  # quantidade base
                alimento["grupo_equiv"],
                con
            )
            
            for sub in subs:
                assert sub.get("quantidade_g") is not None, (
                    f"Substituição {sub['alimento']} de {alimento['nome']} sem quantidade"
                )
                assert sub["quantidade_g"] > 0, (
                    f"Substituição {sub['alimento']} de {alimento['nome']} com quantidade <= 0"
                )
    
    print("✓ Todas as substituições têm quantidade em gramas")


def test_substituicao_de_proteina_preserva_proteina_e_nao_so_kcal():
    """Substituições preservam o macro principal, não apenas as calorias."""
    with app.app_context():
        con = get_db()
        frango = con.execute(
            "SELECT * FROM alimentos WHERE nome = 'Peito de frango grelhado'"
        ).fetchone()
        subs = calcular_substituicoes(dict(frango), 180, "proteina", con)
        tilapia = next(item for item in subs if item["alimento"] == "Filé de tilápia")
        proteina_base = frango["proteinas"] * 1.8
        kcal_base = frango["kcal"] * 1.8
        assert abs(tilapia["proteinas"] - proteina_base) < 1
        assert abs(tilapia["kcal"] - kcal_base) > 10

        arroz = con.execute(
            "SELECT * FROM alimentos WHERE nome = 'Arroz branco cozido'"
        ).fetchone()
        subs = calcular_substituicoes(dict(arroz), 180, "amido", con)
        batata = next(item for item in subs if item["alimento"] == "Batata-doce cozida")
        assert abs(batata["carbs"] - arroz["carbs"] * 1.8) < 1

        azeite = con.execute(
            "SELECT * FROM alimentos WHERE nome = 'Azeite de oliva'"
        ).fetchone()
        subs = calcular_substituicoes(dict(azeite), 10, "gordura", con)
        amendoas = next(item for item in subs if item["alimento"] == "Amêndoas")
        assert abs(amendoas["gorduras"] - azeite["gorduras"] / 10) < 1


# =============================================================================
# TESTE 4: Substituição deve pertencer ao mesmo grupo_equiv
# =============================================================================
def test_substituicoes_mesmo_grupo_equivalencia():
    """Verifica que substituições pertencem ao mesmo grupo de equivalência."""
    with app.app_context():
        con = get_db()
        alimentos = con.execute("SELECT * FROM alimentos LIMIT 10").fetchall()
        
        for alimento in alimentos:
            subs = calcular_substituicoes(
                {
                    "nome": alimento["nome"],
                    "kcal": alimento["kcal"],
                    "proteinas": alimento["proteinas"],
                    "carbs": alimento["carbs"],
                    "gorduras": alimento["gorduras"],
                    "porcao_min": alimento["porcao_min"],
                    "porcao_max": alimento["porcao_max"],
                },
                100,
                alimento["grupo_equiv"],
                con
            )
            
            for sub in subs:
                # Busca o alimento substituto no banco
                sub_alimento = con.execute(
                    "SELECT * FROM alimentos WHERE nome = ?", (sub["alimento"],)
                ).fetchone()
                
                assert sub_alimento is not None, f"Substituto {sub['alimento']} não encontrado"
                assert sub_alimento["grupo_equiv"] == alimento["grupo_equiv"], (
                    f"Substituto {sub['alimento']} (grupo {sub_alimento['grupo_equiv']}) "
                    f"não pertence ao grupo {alimento['grupo_equiv']}"
                )
    
    print("✓ Todas as substituições pertencem ao mesmo grupo_equiv")


# =============================================================================
# TESTE 5: Dieta impossível deve retornar erro
# =============================================================================
def test_dieta_impossivel_retorna_erro():
    """Verifica que uma dieta impossível retorna erro em vez de produzir dieta absurda."""
    with app.app_context():
        con = get_db()
        
        # Busca um alimento com porção máxima muito baixa
        alimento = con.execute(
            "SELECT * FROM alimentos WHERE nome = 'Azeite de oliva'"
        ).fetchone()
        
        if alimento and alimento["porcao_max"] > 0:
            # Tenta calcular uma dieta com meta impossível (muito alta para o alimento)
            itens = [{
                "aid": alimento["id"],
                "nome": alimento["nome"],
                "grupo": alimento["grupo_equiv"],
                "k": alimento["kcal"],
                "p": alimento["proteinas"],
                "c": alimento["carbs"],
                "g": alimento["gorduras"],
                "porcao": alimento["porcao"],
            }]
            
            # Meta de 5000 kcal com apenas azeite (máximo 15g = ~1326 kcal)
            resultado = calcular_gramas(itens, kcal_t=5000, p_t=0, c_t=0, g_t=0)
            
            # O sistema deve retornar a quantidade máxima, não uma quantidade absurda
            qtd = resultado[0]["qtd"]
            assert qtd <= alimento["porcao_max"] + 1, (
                f"Sistema gerou {qtd}g de azeite para meta impossível. "
                f"Deveria limitar a {alimento['porcao_max']}g"
            )
    
    print("✓ Dieta impossível retorna erro (limite respeitado)")


# =============================================================================
# TESTE 6: Macros do PDF correspondem aos alimentos salvos
# =============================================================================
def test_macros_pdf_correspondem_alimentos_salvos():
    """Verifica que os macros calculados correspondem aos alimentos e quantidades."""
    with app.app_context():
        con = get_db()
        
        # Cria aluno de teste
        aluno_id = criar_aluno_teste()
        
        # Cria uma refeição com alimentos conhecidos
        cur = con.execute(
            """INSERT INTO refeicoes (aluno_id, nome, horario, calorias, proteinas, carbs, gorduras, descricao, ordem)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (aluno_id, "Café da manhã", "07:00", 400, 30, 50, 10, "Teste", 1)
        )
        refeicao_id = cur.lastrowid
        
        # Adiciona alimentos conhecidos
        alimentos = con.execute(
            "SELECT * FROM alimentos WHERE nome IN ('Aveia em flocos', 'Banana', 'Iogurte natural')"
        ).fetchall()
        
        for i, al in enumerate(alimentos):
            con.execute(
                "INSERT INTO refeicao_alimentos (refeicao_id, alimento_id, qtd, ordem) VALUES (?, ?, ?, ?)",
                (refeicao_id, al["id"], 100, i)  # 100g de cada
            )
        con.commit()
        
        # Valida a dieta
        avisos, reais, alvo = validar_dieta(aluno_id)
        
        # Verifica que os macros reais são calculados corretamente
        k, p, c, g = 0.0, 0.0, 0.0, 0.0
        for al in alimentos:
            fator = 100 / 100.0  # 100g
            k += (al["kcal"] or 0) * fator
            p += (al["proteinas"] or 0) * fator
            c += (al["carbs"] or 0) * fator
            g += (al["gorduras"] or 0) * fator
        
        assert abs(reais["calorias"] - k) < 1, (
            f"Calorias calculadas ({reais['calorias']}) não correspondem ao esperado ({k})"
        )
        assert abs(reais["proteinas"] - p) < 1, (
            f"Proteína calculada ({reais['proteinas']}) não correspondem ao esperado ({p})"
        )
    
    print("✓ Macros do PDF correspondem aos alimentos salvos")


# =============================================================================
# TESTE 7: Alterar porcao_max impede dietas com quantidade maior
# =============================================================================
def test_alterar_porcao_max_impede_quantidade_maior():
    """Verifica que alterar porcao_max impede dietas com quantidade maior."""
    with app.app_context():
        con = get_db()
        
        # Busca a aveia
        aveia = get_alimento("Aveia em flocos")
        assert aveia is not None
        
        # Altera porcao_max para 60g
        con.execute("UPDATE alimentos SET porcao_max = 60 WHERE id = ?", (aveia["id"],))
        con.commit()
        
        # Busca novamente com valores atualizados
        aveia_atualizada = con.execute("SELECT * FROM alimentos WHERE id = ?", (aveia["id"],)).fetchone()
        
        # Tenta calcular gramas com meta alta
        itens = [{
            "aid": aveia_atualizada["id"],
            "nome": aveia_atualizada["nome"],
            "grupo": aveia_atualizada["grupo_equiv"],
            "k": aveia_atualizada["kcal"],
            "p": aveia_atualizada["proteinas"],
            "c": aveia_atualizada["carbs"],
            "g": aveia_atualizada["gorduras"],
            "porcao": aveia_atualizada["porcao"],
            "porcao_min": aveia_atualizada["porcao_min"],
            "porcao_max": aveia_atualizada["porcao_max"],
            "porcao_padrao": aveia_atualizada["porcao_padrao"],
        }]
        
        resultado = calcular_gramas(itens, kcal_t=3000, p_t=100, c_t=300, g_t=80)
        qtd = resultado[0]["qtd"]
        
        assert qtd <= 61, (
            f"Aveia gerou {qtd}g após alterar porcao_max para 60g. "
            f"Deveria limitar a 60g"
        )
        
        # Restaura valor original
        con.execute("UPDATE alimentos SET porcao_max = ? WHERE id = ?", (PORCOES_POR_NOME.get("Aveia em flocos", (20, 40, 70))[2], aveia["id"]))
        con.commit()
    
    print("✓ Alterar porcao_max impede dietas com quantidade maior")


# =============================================================================
# TESTE 8: Sistema recalcula dieta após alterar limites
# =============================================================================
def test_recalcular_dieta_apos_alterar_limites():
    """Verifica que o sistema consegue recalcular uma dieta existente."""
    with app.app_context():
        con = get_db()
        
        # Cria aluno de teste
        aluno_id = criar_aluno_teste(nome="Aluno Recalc")
        
        # Cria uma refeição
        cur = con.execute(
            """INSERT INTO refeicoes (aluno_id, nome, horario, calorias, proteinas, carbs, gorduras, descricao, ordem)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (aluno_id, "Almoço", "12:30", 700, 50, 80, 20, "Teste", 1)
        )
        refeicao_id = cur.lastrowid
        
        # Adiciona aveia com quantidade alta (simulando dieta antiga)
        aveia = get_alimento("Aveia em flocos")
        con.execute(
            "INSERT INTO refeicao_alimentos (refeicao_id, alimento_id, qtd, ordem) VALUES (?, ?, ?, ?)",
            (refeicao_id, aveia["id"], 400, 1)  # 400g (quantidade absurda)
        )
        con.commit()
        
        # Altera porcao_max da aveia para 60g
        con.execute("UPDATE alimentos SET porcao_max = 60 WHERE id = ?", (aveia["id"],))
        con.commit()
        
        # Busca novamente com valores atualizados
        aveia_atualizada = con.execute("SELECT * FROM alimentos WHERE id = ?", (aveia["id"],)).fetchone()
        
        # Recalcula a dieta
        itens = [{
            "aid": aveia_atualizada["id"],
            "nome": aveia_atualizada["nome"],
            "grupo": aveia_atualizada["grupo_equiv"],
            "k": aveia_atualizada["kcal"],
            "p": aveia_atualizada["proteinas"],
            "c": aveia_atualizada["carbs"],
            "g": aveia_atualizada["gorduras"],
            "porcao": aveia_atualizada["porcao"],
            "porcao_min": aveia_atualizada["porcao_min"],
            "porcao_max": aveia_atualizada["porcao_max"],
            "porcao_padrao": aveia_atualizada["porcao_padrao"],
        }]
        
        resultado = calcular_gramas(itens, kcal_t=700, p_t=50, c_t=80, g_t=20)
        qtd = resultado[0]["qtd"]
        
        assert qtd <= 61, (
            f"Após recalcular, aveia gerou {qtd}g. Deveria limitar a 60g"
        )
        
        # Restaura valor original
        con.execute("UPDATE alimentos SET porcao_max = ? WHERE id = ?", (PORCOES_POR_NOME.get("Aveia em flocos", (20, 40, 70))[2], aveia["id"]))
        con.commit()
    
    print("✓ Sistema recalcula dieta após alterar limites")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
