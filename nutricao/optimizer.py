"""Motor de otimização de dietas realistas.

Este módulo fornece um gerador diário de dieta que prioriza:
1) estrutura e coerência da refeição
2) porções realistas
3) qualidade nutricional
4) proteína diária
5) calorias
6) carboidratos e gorduras
7) precisão final
"""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable, Mapping, Sequence

from .equivalencias import normalizar_grupo, tipo_equivalencia
from .portions import PORCOES_POR_GRUPO, PORCOES_POR_NOME, clamp_portion, qualidade_porcoes, resolve_faixa_porcao
from .scoring import score_dieta


DEFAULT_REFEICOES = [
    "Café da manhã",
    "Lanche da manhã",
    "Almoço",
    "Lanche da tarde",
    "Jantar",
]


class DietPlanOptimizer:
    """Gera um plano alimentar coerente e realista para a meta diária."""

    def __init__(
        self,
        meta_calorica_diaria,
        proteina_diaria,
        carboidrato_diario,
        gordura_diaria,
        quantidade_refeicoes,
        estrutura_refeicoes=None,
        preferencias=None,
        restricoes=None,
        alimentos_disponiveis=None,
        alimentos_ativos=None,
        dados_nutricionais=None,
        porcoes=None,
    ):
        self.meta_calorica_diaria = float(meta_calorica_diaria or 0.0)
        self.proteina_diaria = float(proteina_diaria or 0.0)
        self.carboidrato_diario = float(carboidrato_diario or 0.0)
        self.gordura_diaria = float(gordura_diaria or 0.0)
        self.quantidade_refeicoes = int(quantidade_refeicoes or 3)
        self.estrutura_refeicoes = estrutura_refeicoes or {}
        self.preferencias = preferencias or {}
        self.restricoes = restricoes or {}
        self.porcoes = porcoes or {}
        self.alimentos_disponiveis = self._normalizar_alimentos(alimentos_disponiveis)
        self.alimentos_ativos = self._normalizar_alimentos(alimentos_ativos)
        self.dados_nutricionais = self._normalizar_alimentos(dados_nutricionais)

    def _normalizar_alimentos(self, alimentos) -> list[dict]:
        if not alimentos:
            return []
        if isinstance(alimentos, Mapping):
            alimentos = list(alimentos.values())
        itens = []
        for item in alimentos:
            if not isinstance(item, Mapping):
                continue
            copia = dict(item)
            copia.setdefault("grupo_equiv", copia.get("grupo") or copia.get("categoria") or "")
            copia.setdefault("nome", copia.get("descricao") or "Alimento")
            copia.setdefault("kcal", copia.get("calorias") or 0.0)
            copia.setdefault("proteinas", 0.0)
            copia.setdefault("carbs", 0.0)
            copia.setdefault("gorduras", 0.0)
            copia.setdefault("porcao", copia.get("porcao_padrao") or 100.0)
            itens.append(copia)
        return itens

    def _lista_de_refeicoes(self) -> list[str]:
        if isinstance(self.estrutura_refeicoes, Mapping):
            return list(self.estrutura_refeicoes.keys())
        if isinstance(self.estrutura_refeicoes, Sequence) and not isinstance(self.estrutura_refeicoes, (str, bytes)):
            return [str(item) for item in self.estrutura_refeicoes]
        if self.quantidade_refeicoes <= 0:
            return []
        return DEFAULT_REFEICOES[: min(len(DEFAULT_REFEICOES), self.quantidade_refeicoes)]

    def _candidatos_para_refeicao(self, nome_refeicao: str) -> list[dict]:
        candidatos = []
        estrutura = self.estrutura_refeicoes if isinstance(self.estrutura_refeicoes, Mapping) else {}
        itens_estrutura = estrutura.get(nome_refeicao, []) if isinstance(estrutura, Mapping) else []

        if isinstance(itens_estrutura, Sequence) and not isinstance(itens_estrutura, (str, bytes)):
            for nome in itens_estrutura:
                if isinstance(nome, str):
                    candidatos.extend(self._buscar_por_nome(nome))
                elif isinstance(nome, Mapping):
                    candidatos.append(dict(nome))

        if not candidatos:
            base = self.alimentos_ativos or self.alimentos_disponiveis or self.dados_nutricionais or []
            for item in base:
                nome = str(item.get("nome") or "")
                if not nome:
                    continue
                permitido = item.get("refeicoes_permitidas")
                if permitido and nome_refeicao not in str(permitido):
                    continue
                candidatos.append(dict(item))

        # preferências e restrições de grupo
        if self.preferencias:
            restricoes = str(self.preferencias.get("grupos") or "")
            if restricoes:
                grupos = {normalizar_grupo(g) for g in restricoes.split(",") if g.strip()}
                candidatos = [item for item in candidatos if normalizar_grupo(item.get("grupo_equiv") or item.get("grupo") or item.get("categoria")) in grupos]

        return candidatos[:12]

    def _buscar_por_nome(self, nome: str) -> list[dict]:
        alvo = str(nome or "").strip().lower()
        todos = self.alimentos_ativos or self.alimentos_disponiveis or self.dados_nutricionais or []
        saida = []
        for item in todos:
            nome_item = str(item.get("nome") or "").strip().lower()
            if nome_item == alvo or alvo in nome_item:
                saida.append(dict(item))
        return saida

    def _totais_de_item(self, item):
        qtd = float(item.get("quantidade") or item.get("qtd") or 0.0)
        kcal = float(item.get("kcal") or 0.0)
        prot = float(item.get("proteinas") or 0.0)
        carb = float(item.get("carbs") or 0.0)
        fats = float(item.get("gorduras") or 0.0)
        return {
            "kcal": kcal * qtd / 100.0,
            "proteinas": prot * qtd / 100.0,
            "carbs": carb * qtd / 100.0,
            "gorduras": fats * qtd / 100.0,
        }

    def _montar_refeicao(self, nome_refeicao: str) -> dict:
        itens = []
        for item in self._candidatos_para_refeicao(nome_refeicao):
            faixa = resolve_faixa_porcao(item)
            padrao = float(item.get("porcao_padrao") or faixa[1]) if item.get("porcao_padrao") else faixa[1]
            quantidade = clamp_portion(float(item.get("quantidade") or item.get("qtd") or padrao), faixa)
            if not self.restricoes:
                pass
            itens.append({
                "nome": item.get("nome") or "Alimento",
                "grupo": item.get("grupo_equiv") or item.get("grupo") or item.get("categoria") or "",
                "quantidade": round(quantidade, 1),
                "porcao_min": faixa[0],
                "porcao_padrao": faixa[1],
                "porcao_max": faixa[2],
                "kcal": float(item.get("kcal") or 0.0),
                "proteinas": float(item.get("proteinas") or 0.0),
                "carbs": float(item.get("carbs") or 0.0),
                "gorduras": float(item.get("gorduras") or 0.0),
                "tipo": tipo_equivalencia(item.get("grupo_equiv") or item.get("grupo") or item.get("categoria")),
            })

        if not itens:
            return {"nome": nome_refeicao, "alimentos": [], "totais": {"kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0}, "score": 0.0}

        share_kcal = {
            "Café da manhã": 0.20,
            "Lanche da manhã": 0.10,
            "Almoço": 0.30,
            "Lanche da tarde": 0.15,
            "Jantar": 0.25,
        }.get(nome_refeicao, 1.0 / max(len(self._lista_de_refeicoes()) or 1, 1))

        meta_refeicao_kcal = max(self.meta_calorica_diaria * share_kcal, 0.0)
        meta_refeicao_proteina = max(self.proteina_diaria * share_kcal, 0.0)
        meta_refeicao_carbo = max(self.carboidrato_diario * share_kcal, 0.0)
        meta_refeicao_gordura = max(self.gordura_diaria * share_kcal, 0.0)

        refeicao_totais = {"kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0}
        for item in itens:
            valor = self._totais_de_item(item)
            for key in refeicao_totais:
                refeicao_totais[key] += valor[key]

        if any(refeicao_totais.values()):
            fator = min(
                max(meta_refeicao_kcal / max(refeicao_totais["kcal"], 1.0), 0.35),
                1.8,
            )
            if meta_refeicao_proteina > 0:
                fator = min(fator, max(meta_refeicao_proteina / max(refeicao_totais["proteinas"], 1.0), 0.35))
            if meta_refeicao_carbo > 0:
                fator = min(fator, max(meta_refeicao_carbo / max(refeicao_totais["carbs"], 1.0), 0.35))
            if meta_refeicao_gordura > 0:
                fator = min(fator, max(meta_refeicao_gordura / max(refeicao_totais["gorduras"], 1.0), 0.35))
            fator = max(0.35, min(1.8, fator))
            for item in itens:
                faixa = (item["porcao_min"], item["porcao_padrao"], item["porcao_max"])
                item["quantidade"] = clamp_portion(float(item["quantidade"]) * fator, faixa)
                if item["quantidade"] <= 0:
                    item["quantidade"] = item["porcao_min"]

        refeicao_totais = {"kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0}
        for item in itens:
            valor = self._totais_de_item(item)
            for key in refeicao_totais:
                refeicao_totais[key] += valor[key]

        portion_quality = sum(qualidade_porcoes(item["quantidade"], (item["porcao_min"], item["porcao_padrao"], item["porcao_max"])) for item in itens) / max(len(itens), 1)
        meal_score = score_dieta(refeicao_totais, {
            "kcal": meta_refeicao_kcal,
            "proteinas": meta_refeicao_proteina,
            "carbs": meta_refeicao_carbo,
            "gorduras": meta_refeicao_gordura,
        }, variety=1.0, meals=1, portion_quality=portion_quality)

        return {"nome": nome_refeicao, "alimentos": itens, "totais": refeicao_totais, "score": meal_score}

    def _reajustar_totais(self, refeicoes: Sequence[Mapping]) -> dict:
        totais = {"kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0}
        for refeicao in refeicoes:
            for key in totais:
                totais[key] += float((refeicao.get("totais") or {}).get(key, 0.0) or 0.0)
        return totais

    def _ajustar_totais_diarios(self, refeicoes: Sequence[Mapping], alvo: Mapping[str, float]) -> None:
        """Escala porções de forma gradual para respeitar a meta diária sem exagerar em bordas."""
        totais = {"kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0}
        for refeicao in refeicoes:
            for chave in totais:
                totais[chave] += float((refeicao.get("totais") or {}).get(chave, 0.0) or 0.0)

        if not any(totais.values()):
            return

        fatores = []
        for chave, target in alvo.items():
            atual = totais.get(chave, 0.0)
            if target and atual > 0:
                fatores.append(min(1.5, max(0.7, float(target) / max(atual, 1.0))))

        if not fatores:
            return

        fator_global = sum(fatores) / len(fatores)
        fator_global = min(1.35, max(0.75, fator_global))

        for refeicao in refeicoes:
            for item in refeicao.get("alimentos", []):
                faixa = (item["porcao_min"], item["porcao_padrao"], item["porcao_max"])
                item["quantidade"] = clamp_portion(float(item.get("quantidade") or faixa[1]) * fator_global, faixa)
            refeicao["totais"] = {"kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0}
            for item in refeicao.get("alimentos", []):
                valor = self._totais_de_item(item)
                for chave in refeicao["totais"]:
                    refeicao["totais"][chave] += valor[chave]

    def generate(self) -> dict:
        nomes = self._lista_de_refeicoes()
        if not nomes:
            return {"refeicoes": [], "totais": {"kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0}, "score": 0.0, "avisos": ["Nenhuma refeição configurada."], "status": "impossivel"}

        refeicoes = [self._montar_refeicao(nome) for nome in nomes]
        alvos = {
            "kcal": self.meta_calorica_diaria,
            "proteinas": self.proteina_diaria,
            "carbs": self.carboidrato_diario,
            "gorduras": self.gordura_diaria,
        }
        self._ajustar_totais_diarios(refeicoes, alvos)
        totais = self._reajustar_totais(refeicoes)
        score = score_dieta(totais, alvos, variety=0.8, meals=max(len(refeicoes), 1), portion_quality=1.0)

        avisos = []
        margens = {
            "kcal": max(self.meta_calorica_diaria * 0.02, 25.0),
            "proteinas": max(self.proteina_diaria * 0.08, 5.0),
            "carbs": max(self.carboidrato_diario * 0.08, 8.0),
            "gorduras": max(self.gordura_diaria * 0.08, 5.0),
        }
        for chave, alvo in alvos.items():
            atual = totais.get(chave, 0.0)
            if alvo and abs(atual - alvo) > margens.get(chave, 0.0):
                avisos.append(f"{chave}: {atual:.0f} vs meta {alvo:.0f}.")

        if not any(refeicoes):
            status = "impossivel"
        elif total_geral := sum(totais.values()):
            status = "ok" if score >= 70 and not avisos else "aproximado"
        else:
            status = "impossivel"

        return {"refeicoes": refeicoes, "totais": totais, "score": round(score, 2), "avisos": avisos, "status": status}

    def optimize(self):
        return self.generate()

    def gerar(self):
        return self.generate()


__all__ = ["DietPlanOptimizer"]
