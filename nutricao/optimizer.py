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

import unicodedata
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
    "vegetais": {"legume", "verdura_folha"},
    "gordura": {"gordura"},
}

PROTEINAS_CAFE_LANCHE = {
    "ovo", "omelete", "whey", "iogurte", "cottage", "queijo", "leite", "ricota",
}
PROTEINAS_CARNE_PEIXE = {
    "frango", "carne", "tilapia", "merluza", "salmao", "atum", "peixe",
    "alcatra", "lagarto", "sobrecoxa", "peru",
}
PESOS_MACROS = {"proteinas": 3.0, "kcal": 6.0, "carbs": 1.5, "gorduras": 1.5}
DISTRIBUICAO_PROTEINA_REFEICOES = {
    "Café da manhã": 0.20,
    "Lanche da manhã": 0.10,
    "Almoço": 0.30,
    "Lanche da tarde": 0.15,
    "Jantar": 0.25,
}


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

        return candidatos

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
                nomes_preferidos = {
                    nome.strip().lower()
                    for nome in slot.get("candidatos", [])
                    if isinstance(nome, str)
                }
                pool = []
                for nome in slot.get("candidatos", []):
                    if isinstance(nome, Mapping):
                        candidato = dict(nome)
                        candidato["_preferido"] = True
                        pool.append(candidato)
                    elif isinstance(nome, str):
                        encontrados = self._buscar_por_nome(nome)
                        for candidato in encontrados:
                            candidato["_preferido"] = True
                            pool.append(candidato)
                if permitidos:
                    grupos_candidatos = self.alimentos_ativos or self.alimentos_disponiveis or self.dados_nutricionais
                    for candidato in grupos_candidatos:
                        grupo = normalizar_grupo(
                            candidato.get("grupo_equiv") or candidato.get("grupo") or candidato.get("categoria")
                        )
                        if grupo not in permitidos:
                            continue
                        permitido_em = str(candidato.get("refeicoes_permitidas") or "").strip()
                        if permitido_em and nome_refeicao.lower() not in permitido_em.lower():
                            continue
                        candidato = dict(candidato)
                        candidato["_preferido"] = str(candidato.get("nome") or "").strip().lower() in nomes_preferidos
                        pool.append(candidato)
                    pool = [
                        candidato for candidato in pool
                        if normalizar_grupo(
                            candidato.get("grupo_equiv") or candidato.get("grupo") or candidato.get("categoria")
                        ) in permitidos
                    ]
                if self.preferencias:
                    restricoes = str(self.preferencias.get("grupos") or "")
                    if restricoes:
                        grupos = {
                            normalizar_grupo(grupo)
                            for grupo in restricoes.split(",")
                            if grupo.strip()
                        }
                        pool = [
                            candidato for candidato in pool
                            if normalizar_grupo(
                                candidato.get("grupo_equiv") or candidato.get("grupo") or candidato.get("categoria")
                            ) in grupos
                        ]
                pool = [
                    candidato for candidato in pool
                    if not candidato.get("refeicoes_permitidas")
                    or nome_refeicao.lower() in str(candidato["refeicoes_permitidas"]).lower()
                ]
                pool = [
                    candidato for candidato in pool
                    if self._candidato_adequado(nome_refeicao, papel, candidato)
                ]
                pool.sort(
                    key=lambda candidato: (
                        -self._pontuar_adequacao(nome_refeicao, papel, candidato),
                        str(candidato.get("nome") or "").casefold(),
                    )
                )
                deduplicados = self._deduplicar_alimentos(pool)
                for candidato in deduplicados:
                    candidato["_opcional"] = self._slot_opcional(nome_refeicao, papel)
                opcoes.append((papel, deduplicados))
            return [(papel, pool) for papel, pool in opcoes if pool]

        return [
            (normalizar_grupo(item.get("grupo_equiv") or item.get("grupo") or item.get("categoria")), [item])
            for item in self._candidatos_para_refeicao(nome_refeicao)
        ]

    def _slot_opcional(self, nome_refeicao: str, papel: str) -> bool:
        refeicao = self._sem_acentos(nome_refeicao)
        papel = normalizar_grupo(papel)
        if refeicao == "almoco":
            return papel == "leguminosa"
        if refeicao in {"lanche da manha", "lanche da tarde"}:
            if papel == "gordura":
                return True
            return refeicao == "lanche da tarde" and papel == "fruta"
        if refeicao == "jantar":
            return papel == "gordura"
        return False

    @staticmethod
    def _sem_acentos(texto: object) -> str:
        return "".join(
            caractere
            for caractere in unicodedata.normalize("NFKD", str(texto or "").casefold())
            if not unicodedata.combining(caractere)
        )

    @classmethod
    def _texto_alimento(cls, alimento: Mapping) -> str:
        return cls._sem_acentos(" ".join(
            str(alimento.get(campo) or "")
            for campo in ("nome", "categoria", "grupo_equiv", "grupo")
        ))

    @staticmethod
    def _contem_termo(texto: str, termos: set[str]) -> bool:
        return any(termo in texto for termo in termos)

    def _candidato_adequado(self, nome_refeicao: str, papel: str, alimento: Mapping) -> bool:
        if papel != "proteina":
            return True
        refeicao = self._sem_acentos(nome_refeicao)
        nome = self._texto_alimento(alimento)
        grupo = normalizar_grupo(
            alimento.get("grupo_equiv") or alimento.get("grupo") or alimento.get("categoria")
        )
        eh_laticinio = grupo == "laticinio" or self._contem_termo(
            nome, {"iogurte", "cottage", "queijo", "leite", "ricota", "whey"}
        )
        eh_ovo = self._contem_termo(nome, {"ovo", "omelete"})
        eh_carne_peixe = self._contem_termo(nome, PROTEINAS_CARNE_PEIXE)

        if refeicao == "cafe da manha":
            return eh_laticinio or eh_ovo
        if refeicao.startswith("lanche"):
            return eh_laticinio or eh_ovo
        if refeicao == "almoco":
            return grupo == "proteina" and (eh_carne_peixe or eh_ovo)
        if refeicao == "jantar":
            return grupo == "proteina" and (eh_carne_peixe or eh_ovo)
        return True

    def _pontuar_adequacao(self, nome_refeicao: str, papel: str, alimento: Mapping) -> float:
        nome = self._texto_alimento(alimento)
        grupo = normalizar_grupo(
            alimento.get("grupo_equiv") or alimento.get("grupo") or alimento.get("categoria")
        )
        pontuacao = 0.0
        refeicao = self._sem_acentos(nome_refeicao)
        if papel == "proteina":
            if refeicao in {"cafe da manha", "lanche da manha", "lanche da tarde"}:
                if self._contem_termo(nome, {"ovo", "omelete", "whey"}):
                    pontuacao += 5.0
                if grupo == "laticinio" or self._contem_termo(
                    nome, {"iogurte", "cottage", "queijo", "leite", "ricota"}
                ):
                    pontuacao += 5.0
            elif refeicao in {"almoco", "jantar"}:
                if self._contem_termo(nome, PROTEINAS_CARNE_PEIXE):
                    pontuacao += 5.0
                if self._contem_termo(nome, {"ovo", "omelete"}):
                    pontuacao += 2.0
        elif papel in {"carboidrato", "amido"}:
            if refeicao == "cafe da manha" and self._contem_termo(
                nome, {"pao", "aveia", "granola", "tapioca"}
            ):
                pontuacao += 4.0
            if refeicao in {"almoco", "jantar"} and grupo == "amido":
                pontuacao += 3.0
        elif papel == "gordura" and refeicao.startswith("lanche"):
            pontuacao += 2.0
        if alimento.get("_preferido", False):
            pontuacao += 0.5
        return pontuacao

    @staticmethod
    def _deduplicar_alimentos(alimentos: Iterable[Mapping]) -> list[dict]:
        unicos = {}
        for alimento in alimentos:
            if isinstance(alimento, Mapping):
                chave = str(alimento.get("id") or alimento.get("nome") or "").strip().lower()
                if chave and chave not in unicos:
                    unicos[chave] = dict(alimento)
        return list(unicos.values())

    def _item_para_refeicao(self, alimento: Mapping, papel: str, nome_refeicao: str) -> dict:
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
            "_preferido": bool(alimento.get("_preferido", True)),
            "_adequacao": self._pontuar_adequacao(nome_refeicao, papel, alimento),
            "_opcional": bool(alimento.get("_opcional", False)),
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
            selecionado = max(
                pool,
                key=lambda candidato: self._pontuar_adequacao(nome_refeicao, papel, candidato),
            )
            item = self._item_para_refeicao(selecionado, papel, nome_refeicao)
            if selecionado.get("quantidade") or selecionado.get("qtd"):
                faixa = (item["porcao_min"], item["porcao_padrao"], item["porcao_max"])
                item["quantidade"] = round(clamp_portion(float(selecionado.get("quantidade") or selecionado.get("qtd")), faixa), 1)
            item["_opcoes"] = [
                self._item_para_refeicao(candidato, papel, nome_refeicao)
                for candidato in pool
            ]
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
        meta_proteina = float(alvo.get("proteinas") or 0.0)
        if meta_proteina > 0 and len(refeicoes) > 1:
            for refeicao in refeicoes:
                fracao = DISTRIBUICAO_PROTEINA_REFEICOES.get(
                    str(refeicao.get("nome") or ""),
                    1.0 / len(refeicoes),
                )
                proteina_refeicao = sum(
                    self._totais_de_item(item)["proteinas"]
                    for item in refeicao.get("alimentos", [])
                )
                desvio = (proteina_refeicao - meta_proteina * fracao) / meta_proteina
                perda += 5.0 * desvio * desvio
        nomes_repetidos = {}
        for refeicao in refeicoes:
            for item in refeicao.get("alimentos", []):
                faixa = (item["porcao_min"], item["porcao_padrao"], item["porcao_max"])
                padrao = float(item["porcao_padrao"])
                largura = max((faixa[2] - faixa[0]) / 2.0, 1.0)
                desvio = (float(item["quantidade"]) - padrao) / largura
                perda += 0.025 * desvio * desvio
                if not item.get("_preferido", True):
                    perda += 0.025
                perda -= float(item.get("_adequacao") or 0.0) * 0.002
                if item.get("_slot") in {"proteina", "fruta", "gordura"}:
                    nome = str(item.get("nome") or "").strip().lower()
                    if nome:
                        nomes_repetidos.setdefault(nome, []).append(item)
        for repeticoes in nomes_repetidos.values():
            if len(repeticoes) > 1:
                perda += 0.15 * (len(repeticoes) - 1)
        quantidades_ideais = {
            "cafe da manha": (3, 0.003),
            "lanche da manha": (2, 0.01),
            "lanche da tarde": (2, 0.01),
            "almoco": (4, 0.003),
            "jantar": (3, 0.003),
        }
        for refeicao in refeicoes:
            nome = self._sem_acentos(refeicao.get("nome") or "")
            quantidade_ideal, penalidade_por_item = quantidades_ideais.get(
                nome, (3, 0.003)
            )
            itens_extras = max(
                0,
                len(refeicao.get("alimentos", [])) - quantidade_ideal,
            )
            perda += itens_extras * penalidade_por_item
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
        for _ in range(3):
            houve_melhoria = False
            for refeicao in refeicoes:
                for item in refeicao.get("alimentos", []):
                    opcoes = item.pop("_opcoes", [])
                    atual = dict(item)
                    melhor = dict(atual)
                    melhor_perda = self._loss(refeicoes, alvo)
                    for opcao in opcoes:
                        teste = dict(opcao)
                        mn, padrao, mx = (
                            float(teste["porcao_min"]),
                            float(teste["porcao_padrao"]),
                            float(teste["porcao_max"]),
                        )
                        passo = max(5.0, (mx - mn) / 12.0)
                        quantidades = {mn, padrao, mx, clamp_portion(atual["quantidade"], (mn, padrao, mx))}
                        quantidade = mn
                        while quantidade < mx:
                            quantidades.add(round(quantidade, 1))
                            quantidade += passo
                        teste["_slot"] = atual.get("_slot", "")
                        item.clear()
                        item.update(teste)
                        for quantidade in quantidades:
                            item["quantidade"] = quantidade
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
        for refeicao in refeicoes:
            itens = refeicao.get("alimentos", [])
            for indice, item in enumerate(list(itens)):
                if not item.get("_opcional"):
                    continue
                perda_com_item = self._loss(refeicoes, alvo)
                quantidade_original = item["quantidade"]
                itens.remove(item)
                self._recalcular_totais_refeicoes(refeicoes)
                self._otimizar_porcoes(refeicoes, alvo)
                if self._loss(refeicoes, alvo) >= perda_com_item:
                    itens.insert(indice, item)
                    item["quantidade"] = quantidade_original
                    self._recalcular_totais_refeicoes(refeicoes)
                    self._otimizar_porcoes(refeicoes, alvo)

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
                item.pop("_preferido", None)
                item.pop("_adequacao", None)
                item.pop("_opcional", None)
        return {"refeicoes": refeicoes, "totais": totais, "score": round(score, 2), "avisos": avisos, "status": status}

    def optimize(self):
        return self.generate()

    def gerar(self):
        return self.generate()


__all__ = ["DietPlanOptimizer"]
