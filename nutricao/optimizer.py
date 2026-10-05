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

from typing import Iterable, Mapping, Sequence

from .equivalencias import normalizar_grupo, tipo_equivalencia
from .portions import clamp_portion, resolve_faixa_porcao
from .scoring import score_dieta


DEFAULT_REFEICOES = [
    "Café da manhã",
    "Lanche da manhã",
    "Almoço",
    "Lanche da tarde",
    "Jantar",
]

GRUPOS_POR_PAPEL = {
    "proteina": {"proteina", "laticinio"},
    "carboidrato": {"amido", "pao", "cereal"},
    "amido": {"amido", "pao", "cereal"},
    "fruta": {"fruta"},
    "leguminosa": {"leguminosa"},
    "folha": {"verdura_folha"},
    "legume": {"legume", "verdura_folha"},
    "gordura": {"gordura"},
}

PESOS_MACROS = {"proteinas": 3.0, "kcal": 2.5, "carbs": 1.5, "gorduras": 1.5}


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

    def _opcoes_por_refeicao(self, nome_refeicao: str) -> list[tuple[str, list[dict]]]:
        estrutura = self.estrutura_refeicoes if isinstance(self.estrutura_refeicoes, Mapping) else {}
        definicao = estrutura.get(nome_refeicao, [])
        if isinstance(definicao, Sequence) and not isinstance(definicao, (str, bytes)) and any(
            isinstance(item, Mapping) and "candidatos" in item for item in definicao
        ):
            opcoes = []
            for slot in definicao:
                if not isinstance(slot, Mapping):
                    continue
                papel_original = str(slot.get("papel") or slot.get("grupo") or "").lower()
                papel = normalizar_grupo(papel_original.translate(str.maketrans("áéíóúãõç", "aeiouaoc")))
                permitidos = GRUPOS_POR_PAPEL.get(papel)
                pool = []
                for nome in slot.get("candidatos", []):
                    if isinstance(nome, Mapping):
                        pool.append(dict(nome))
                    elif isinstance(nome, str):
                        pool.extend(self._buscar_por_nome(nome))
                if permitidos:
                    pool = [
                        item for item in pool
                        if normalizar_grupo(item.get("grupo_equiv") or item.get("grupo") or item.get("categoria")) in permitidos
                    ]
                opcoes.append((papel, self._deduplicar_alimentos(pool)))
            return [(papel, pool) for papel, pool in opcoes if pool]

        return [
            (normalizar_grupo(item.get("grupo_equiv") or item.get("grupo") or item.get("categoria")), [item])
            for item in self._candidatos_para_refeicao(nome_refeicao)
        ]

    @staticmethod
    def _deduplicar_alimentos(alimentos: Iterable[Mapping]) -> list[dict]:
        unicos = {}
        for alimento in alimentos:
            if isinstance(alimento, Mapping):
                chave = str(alimento.get("id") or alimento.get("nome") or "").strip().lower()
                if chave and chave not in unicos:
                    unicos[chave] = dict(alimento)
        return list(unicos.values())

    def _item_para_refeicao(self, alimento: Mapping, papel: str) -> dict:
        faixa = resolve_faixa_porcao(alimento)
        padrao = float(alimento.get("porcao_padrao") or faixa[1]) if alimento.get("porcao_padrao") else faixa[1]
        grupo = alimento.get("grupo_equiv") or alimento.get("grupo") or alimento.get("categoria") or ""
        return {
            "nome": alimento.get("nome") or "Alimento",
            "grupo": grupo,
            "quantidade": round(clamp_portion(padrao, faixa), 1),
            "porcao_min": faixa[0],
            "porcao_padrao": faixa[1],
            "porcao_max": faixa[2],
            "kcal": float(alimento.get("kcal") or 0.0),
            "proteinas": float(alimento.get("proteinas") or 0.0),
            "carbs": float(alimento.get("carbs") or 0.0),
            "gorduras": float(alimento.get("gorduras") or 0.0),
            "tipo": tipo_equivalencia(grupo),
            "_slot": papel,
        }

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
        opcoes = self._opcoes_por_refeicao(nome_refeicao)
        for papel, pool in opcoes:
            selecionado = pool[0]
            item = self._item_para_refeicao(selecionado, papel)
            if selecionado.get("quantidade") or selecionado.get("qtd"):
                faixa = (item["porcao_min"], item["porcao_padrao"], item["porcao_max"])
                item["quantidade"] = round(clamp_portion(float(selecionado.get("quantidade") or selecionado.get("qtd")), faixa), 1)
            item["_opcoes"] = [self._item_para_refeicao(candidato, papel) for candidato in pool]
            itens.append(item)

        if not itens:
            return {"nome": nome_refeicao, "alimentos": [], "totais": {"kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0}, "score": 0.0}

        return {"nome": nome_refeicao, "alimentos": itens, "totais": {"kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0}, "score": 0.0}

    def _reajustar_totais(self, refeicoes: Sequence[Mapping]) -> dict:
        totais = {"kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0}
        for refeicao in refeicoes:
            for key in totais:
                totais[key] += float((refeicao.get("totais") or {}).get(key, 0.0) or 0.0)
        return totais

    def _loss(self, refeicoes: Sequence[Mapping], alvo: Mapping[str, float]) -> float:
        totais = {"kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0}
        perda = 0.0
        for refeicao in refeicoes:
            for item in refeicao.get("alimentos", []):
                valores = self._totais_de_item(item)
                for chave in totais:
                    totais[chave] += valores[chave]
        for chave, peso in PESOS_MACROS.items():
            meta = float(alvo.get(chave) or 0.0)
            if meta > 0:
                desvio = (totais[chave] - meta) / max(meta, 1.0)
                perda += peso * desvio * desvio
        for refeicao in refeicoes:
            for item in refeicao.get("alimentos", []):
                faixa = (item["porcao_min"], item["porcao_padrao"], item["porcao_max"])
                padrao = float(item["porcao_padrao"])
                largura = max((faixa[2] - faixa[0]) / 2.0, 1.0)
                desvio = (float(item["quantidade"]) - padrao) / largura
                perda += 0.025 * desvio * desvio
        return perda

    def _recalcular_totais_refeicoes(self, refeicoes: Sequence[Mapping]) -> None:
        for refeicao in refeicoes:
            totais = {"kcal": 0.0, "proteinas": 0.0, "carbs": 0.0, "gorduras": 0.0}
            for item in refeicao.get("alimentos", []):
                valor = self._totais_de_item(item)
                for chave in totais:
                    totais[chave] += valor[chave]
            refeicao["totais"] = totais

    def _otimizar_porcoes(self, refeicoes: Sequence[Mapping], alvo: Mapping[str, float]) -> None:
        self._recalcular_totais_refeicoes(refeicoes)
        for passo in (20.0, 10.0, 5.0, 2.0):
            mudou = True
            while mudou:
                mudou = False
                perda_atual = self._loss(refeicoes, alvo)
                for refeicao in refeicoes:
                    for item in refeicao.get("alimentos", []):
                        faixa = (item["porcao_min"], item["porcao_padrao"], item["porcao_max"])
                        original = float(item["quantidade"])
                        melhor_qtd = original
                        melhor_perda = perda_atual
                        for candidata in (original - passo, original + passo):
                            candidata = clamp_portion(candidata, faixa)
                            if abs(candidata - original) < 0.01:
                                continue
                            item["quantidade"] = candidata
                            perda = self._loss(refeicoes, alvo)
                            if perda + 1e-10 < melhor_perda:
                                melhor_perda = perda
                                melhor_qtd = candidata
                        item["quantidade"] = melhor_qtd
                        if melhor_qtd != original:
                            mudou = True
                            perda_atual = melhor_perda
            self._recalcular_totais_refeicoes(refeicoes)

    def _substituir_alimentos(self, refeicoes: Sequence[Mapping], alvo: Mapping[str, float]) -> None:
        self._otimizar_porcoes(refeicoes, alvo)
        for _ in range(2):
            houve_melhoria = False
            for refeicao in refeicoes:
                for item in refeicao.get("alimentos", []):
                    opcoes = item.pop("_opcoes", [])
                    atual = dict(item)
                    melhor = atual
                    melhor_perda = self._loss(refeicoes, alvo)
                    for opcao in opcoes:
                        teste = dict(opcao)
                        teste["quantidade"] = clamp_portion(float(atual["quantidade"]), (
                            teste["porcao_min"], teste["porcao_padrao"], teste["porcao_max"]
                        ))
                        teste["_slot"] = atual.get("_slot", "")
                        item.clear()
                        item.update(teste)
                        self._recalcular_totais_refeicoes(refeicoes)
                        self._otimizar_porcoes(refeicoes, alvo)
                        perda = self._loss(refeicoes, alvo)
                        if perda + 1e-10 < melhor_perda:
                            melhor_perda = perda
                            melhor = dict(item)
                    item.clear()
                    item.update(melhor)
                    if melhor.get("nome") != atual.get("nome"):
                        houve_melhoria = True
                    if opcoes:
                        item["_opcoes"] = opcoes
                    self._recalcular_totais_refeicoes(refeicoes)
                    self._otimizar_porcoes(refeicoes, alvo)
            if not houve_melhoria:
                break

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
        self._substituir_alimentos(refeicoes, alvos)
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

        for refeicao in refeicoes:
            for item in refeicao.get("alimentos", []):
                item.pop("_opcoes", None)
                item.pop("_slot", None)
        return {"refeicoes": refeicoes, "totais": totais, "score": round(score, 2), "avisos": avisos, "status": status}

    def optimize(self):
        return self.generate()

    def gerar(self):
        return self.generate()


__all__ = ["DietPlanOptimizer"]
