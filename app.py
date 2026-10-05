import os
import sqlite3
import datetime
import re
from pathlib import Path

from flask import Flask, g, render_template, request, redirect, url_for, abort, flash, send_from_directory, session

from nutricao.optimizer import DietPlanOptimizer
from nutricao.substitutions import calcular_substituicoes as calcular_substituicoes_por_macro

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(
    os.environ.get("PORTAL_DATA_DIR")
    or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    or str(BASE_DIR)
)
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "dados.db"
UPLOAD_DIR = DATA_DIR / "uploads"
MAX_FOTO_BYTES = 6 * 1024 * 1024
TIPOS_FOTO = {"jpg", "jpeg", "png", "webp", "gif"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "portal-treinador-local-2026")

LOGIN_USUARIO = os.environ.get("LOGIN_USUARIO", "admin")
LOGIN_SENHA = os.environ.get("LOGIN_SENHA", "portal123")

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS alunos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    nascimento TEXT,
    telefone TEXT,
    objetivo TEXT,
    plano TEXT DEFAULT 'Consultoria completa',
    mensalidade REAL DEFAULT 120,
    dia_vencimento INTEGER DEFAULT 1,
    observacoes TEXT,
    altura_cm REAL,
    peso_atual REAL,
    fator_atividade REAL DEFAULT 1.55,
    objetivo_meta TEXT DEFAULT 'emagrecer',
    ajuste_meta REAL DEFAULT -10,
    proteina_kg REAL DEFAULT 2.0,
    sexo_formula TEXT DEFAULT 'M',
    dias_treino INTEGER DEFAULT 3,
    foco_gluteo INTEGER DEFAULT 0,
    rotina TEXT,
    ativo INTEGER DEFAULT 1,
    criado_em TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS treinos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aluno_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    dia_semana TEXT,
    notas TEXT,
    ordem INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exercicios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    treino_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    series TEXT,
    repeticoes TEXT,
    carga TEXT,
    descanso TEXT,
    grupo TEXT,
    ordem INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS metas_dieta (
    aluno_id INTEGER PRIMARY KEY,
    kcal_diaria REAL,
    proteinas REAL,
    carbs REAL,
    gorduras REAL,
    observacoes TEXT
);

CREATE TABLE IF NOT EXISTS refeicoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aluno_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    horario TEXT,
    calorias REAL,
    proteinas REAL,
    carbs REAL,
    gorduras REAL,
    descricao TEXT,
    ordem INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aluno_id INTEGER NOT NULL,
    data TEXT DEFAULT (date('now','localtime')),
    peso REAL,
    dores TEXT,
    energia INTEGER,
    sono TEXT,
    kcal_consumidas REAL,
    adesao INTEGER,
    observacoes TEXT,
    criado_em TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS pagamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aluno_id INTEGER NOT NULL,
    mes TEXT NOT NULL,
    valor REAL DEFAULT 120,
    status TEXT DEFAULT 'pendente',
    data_pagamento TEXT,
    observacoes TEXT,
    UNIQUE(aluno_id, mes)
);

CREATE TABLE IF NOT EXISTS exercicios_padrao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    grupo TEXT NOT NULL,
    grande INTEGER DEFAULT 0,
    series INTEGER DEFAULT 2,
    repeticoes TEXT,
    descanso TEXT
);

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
    data_importacao TEXT DEFAULT (datetime('now','localtime')),
    data_atualizacao TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS refeicao_alimentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    refeicao_id INTEGER NOT NULL,
    alimento_id INTEGER NOT NULL,
    qtd REAL DEFAULT 0,
    ordem INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fotos_aluno (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aluno_id INTEGER NOT NULL,
    data TEXT DEFAULT (date('now','localtime')),
    peso REAL,
    legenda TEXT,
    arquivo TEXT NOT NULL,
    criado_em TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS despesas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao TEXT NOT NULL,
    categoria TEXT,
    valor REAL DEFAULT 0,
    data TEXT DEFAULT (date('now','localtime')),
    criado_em TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    telefone TEXT,
    origem TEXT,
    status TEXT DEFAULT 'novo',
    valor_servico REAL,
    observacoes TEXT,
    data TEXT DEFAULT (date('now','localtime')),
    criado_em TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS avaliacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aluno_id INTEGER NOT NULL,
    data TEXT DEFAULT (date('now','localtime')),
    peso REAL,
    percentual_gordura REAL,
    peito REAL,
    ombro REAL,
    biceps REAL,
    antebraco REAL,
    cintura REAL,
    abdomen REAL,
    quadril REAL,
    coxa REAL,
    panturrilha REAL,
    observacoes TEXT,
    criado_em TEXT DEFAULT (datetime('now','localtime'))
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    get_db().executescript(SCHEMA).connection.commit()


def num(v, default=None):
    try:
        s = str(v).replace(",", ".").strip()
        if s == "":
            return default
        return float(s)
    except Exception:
        return default


def intnum(v, default=None):
    valor = num(v, default)
    return int(valor) if valor is not None else default


def mes_atual():
    return datetime.date.today().strftime("%Y-%m")


def mes_label(mes):
    try:
        ano, mo = mes.split("-")
        return f"{MESES[int(mo) - 1]} de {ano}"
    except Exception:
        return mes


def brl(v):
    if v is None:
        return "—"
    return "R$ {:.2f}".format(float(v)).replace(".", ",")


def formatar_data(d):
    if not d:
        return "—"
    try:
        return datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return d


def iniciais(nome):
    partes = [p for p in str(nome or "").split() if p]
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


def idade(data_nasc):
    if not data_nasc:
        return None
    try:
        d = datetime.datetime.strptime(str(data_nasc), "%Y-%m-%d").date()
        h = datetime.date.today()
        return h.year - d.year - ((h.month, h.day) < (d.month, d.day))
    except Exception:
        return None


def salvar_foto(arquivo, aluno_id):
    """Salva a imagem em static/uploads/<aluno_id>/ e devolve o nome seguro, ou None."""
    if not arquivo or not arquivo.filename:
        return None
    nome_orig = Path(arquivo.filename.replace("\\", "/")).name or "foto"
    ext = nome_orig.rsplit(".", 1)[-1].lower() if "." in nome_orig else ""
    if ext not in TIPOS_FOTO:
        return None
    dados = arquivo.read()
    if not dados or len(dados) > MAX_FOTO_BYTES:
        return None
    limpo = re.sub(r"[^a-zA-Z0-9_.-]", "_", nome_orig)[:60]
    nome = "%s_%s" % (datetime.datetime.now().strftime("%Y%m%d%H%M%S"), limpo)
    sub = UPLOAD_DIR / str(aluno_id)
    sub.mkdir(parents=True, exist_ok=True)
    (sub / nome).write_bytes(dados)
    return nome


def serie_peso(con, aluno_id):
    return [
        {"data": r["data"], "peso": r["peso"]}
        for r in con.execute(
            "SELECT data, peso FROM checkins WHERE aluno_id = ? AND peso IS NOT NULL ORDER BY data, id",
            (aluno_id,),
        ).fetchall()
    ]


def preparar_grafico_peso(serie):
    """Mapeia a série de pesos para um SVG (pontos x/y) pronto para renderizar."""
    if not serie:
        return None
    LAR, ALT, M = 620, 220, 36
    pesos = [p["peso"] for p in serie]
    gmin, gmax = min(pesos), max(pesos)
    if len(pesos) == 1:
        return {
            "pontos": [{"x": round(LAR / 2, 1), "y": round(ALT / 2, 1), "peso": pesos[0], "data": serie[0]["data"]}],
            "min": round(gmin, 1), "max": round(gmax, 1), "w": LAR, "h": ALT, "m": M, "n": 1,
            "yb": ALT - M,
        }
    if gmax - gmin < 0.5:
        gmin, gmax = gmin - 1, gmax + 1
    span = gmax - gmin or 1.0
    pontos = []
    n = len(pesos)
    for i, s in enumerate(serie):
        x = M + (i * (LAR - 2 * M) / (n - 1))
        y = ALT - M - ((s["peso"] - gmin) / span) * (ALT - 2 * M)
        pontos.append({"x": round(x, 1), "y": round(y, 1), "peso": s["peso"], "data": s["data"]})
    yb = ALT - M
    seg = ["%s,%s" % (p["x"], p["y"]) for p in pontos]
    return {
        "pontos": pontos, "min": round(gmin, 1), "max": round(gmax, 1),
        "w": LAR, "h": ALT, "m": M, "n": n,
        "line": " ".join(seg),
        "area": "M %s,%s L %s L %s,%s Z" % (pontos[0]["x"], yb, " L ".join(seg), pontos[-1]["x"], yb),
        "yb": yb,
    }


def tendencia_peso(objetivo, primeiro, ultimo):
    if primeiro is None or ultimo is None or primeiro == ultimo:
        return None
    var = ultimo - primeiro
    alinhado = (objetivo == "emagrecer" and var < 0) or (objetivo == "ganhar" and var > 0)
    if objetivo == "manter":
        classe = ""
        texto = "estável" if abs(var) < 0.3 else ("desceu" if var < 0 else "subiu")
    else:
        classe = "green" if alinhado else "red"
        texto = "desceu" if var < 0 else "subiu"
    return {"variacao": var, "texto": texto, "classe": classe, "label": "%+.1f kg" % var}


def ultimos_meses(n=6):
    """Lista dos últimos n meses no formato YYYY-MM, do mais antigo ao mais novo."""
    lista = []
    y, m = datetime.date.today().year, datetime.date.today().month
    for _ in range(n):
        lista.append("%04d-%02d" % (y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(lista))


def grafico_barras_mes(rotulos, entradas, saidas):
    """Prepara um gráfico de barras agrupadas (entradas x saídas) por mês em SVG."""
    LAR, ALT, M = 660, 260, 46
    serie = [e for e in entradas] + [s for s in saidas]
    max_v = max(serie + [1])
    n = len(rotulos)
    gap = (LAR - 2 * M) / n
    bw = min(gap * 0.30, 26)
    base = ALT - M
    area = ALT - 2 * M
    ent, sai = [], []
    for i, (e, s) in enumerate(zip(entradas, saidas)):
        x = M + i * gap + gap / 2
        he = (e / max_v) * area
        hs = (s / max_v) * area
        ent.append({"x": round(x - bw - 3, 1), "y": round(base - he, 1), "h": round(he, 1), "v": e, "w": bw})
        sai.append({"x": round(x + 3, 1), "y": round(base - hs, 1), "h": round(hs, 1), "v": s, "w": bw})
    rot = [r[3:].replace("-", "/") for r in rotulos]
    return {
        "w": LAR, "h": ALT, "m": M, "base": base,
        "rotulos": rot, "entradas": ent, "saidas": sai, "max": round(max_v, 2),
    }


def grafico_donut(items):
    """Prepara um gráfico de rosca (distribuição de despesas por categoria) em SVG."""
    items = [i for i in items if i["s"] > 0]
    total = sum(i["s"] for i in items)
    if total <= 0:
        return None
    cores = ["#58a6ff", "#2fb344", "#ffb73e", "#ff6369", "#a371f7", "#39c5cf", "#8b949e"]
    CX, CY, R, IR = 230, 140, 110, 62
    segs = []
    ang = 0.0
    for idx, it in enumerate(items):
        frac = round(it["s"] / total * 100, 2)
        segs.append({
            "cat": it["cat"], "s": it["s"], "frac": frac,
            "color": cores[idx % len(cores)],
            "dash": "%.2f %.2f" % (frac, 100 - frac),
            "offset": "%.2f" % (-ang),
        })
        ang += frac
    return {"segs": segs, "total": total, "cx": CX, "cy": CY, "r": R, "ir": IR, "sw": R - IR}


def _grafico_linha(serie, um=""):
    """Mapa de uma série de valores para um gráfico de linha em SVG."""
    if not serie:
        return None
    LAR, ALT, M = 640, 220, 40
    vals = [s["valor"] for s in serie]
    gmin, gmax = min(vals), max(vals)
    if len(vals) == 1:
        return {
            "pontos": [{"x": round(LAR / 2, 1), "y": round(ALT / 2, 1), "valor": vals[0], "data": serie[0]["data"]}],
            "min": round(gmin, 1), "max": round(gmax, 1), "w": LAR, "h": ALT, "m": M, "n": 1,
            "yb": ALT - M, "um": um,
        }
    if gmax - gmin < 0.5:
        gmin, gmax = gmin - 1, gmax + 1
    span = gmax - gmin or 1.0
    n = len(vals)
    pontos = []
    for i, s in enumerate(serie):
        x = M + (i * (LAR - 2 * M) / (n - 1))
        y = ALT - M - ((s["valor"] - gmin) / span) * (ALT - 2 * M)
        pontos.append({"x": round(x, 1), "y": round(y, 1), "valor": s["valor"], "data": s["data"]})
    yb = ALT - M
    seg = ["%s,%s" % (p["x"], p["y"]) for p in pontos]
    area = "M %s,%s L %s L %s,%s Z" % (pontos[0]["x"], yb, " L ".join(seg), pontos[-1]["x"], yb)
    return {
        "pontos": pontos, "min": round(gmin, 1), "max": round(gmax, 1),
        "w": LAR, "h": ALT, "m": M, "n": n, "yb": yb, "um": um,
        "line": " ".join(seg), "area": area,
    }


def grafico_evolucao(avaliacoes):
    """Gera um gráfico de linha por medida (peso, % gordura, cintura, etc.)."""
    sequencia = list(reversed(avaliacoes))
    graficos = {}
    for chave, nome, um in MEDIDAS_GRAFICO:
        serie = [{"data": a["data"], "valor": a[chave]} for a in sequencia if a[chave]]
        g = _grafico_linha(serie, um)
        if g:
            g["nome"] = nome
            graficos[chave] = g
    return graficos


OBJETIVOS_META = {
    "emagrecer": "Emagrecer (déficit)",
    "manter": "Manter peso",
    "ganhar": "Ganhar massa (superávit)",
}

GRUPOS_LIB = [
    "Peito", "Costas", "Ombro", "Bíceps", "Tríceps", "Trapézio",
    "Quadríceps", "Posterior", "Glúteo", "Abdômen", "Panturrilha",
]

GRUPOS = {
    "fullbody": [
        ["Peito", "Costas", "Quadríceps", "Ombro", "Posterior", "Bíceps"],
        ["Costas", "Peito", "Posterior", "Ombro", "Quadríceps", "Tríceps"],
        ["Ombro", "Costas", "Quadríceps", "Peito", "Posterior", "Bíceps"],
    ],
    "upper": [
        ["Peito", "Costas", "Ombro", "Bíceps", "Tríceps", "Peito"],
        ["Costas", "Peito", "Ombro", "Bíceps", "Tríceps", "Costas"],
    ],
    "lower": [
        ["Quadríceps", "Posterior", "Quadríceps", "Panturrilha", "Posterior", "Quadríceps"],
        ["Posterior", "Quadríceps", "Posterior", "Quadríceps", "Panturrilha", "Posterior"],
    ],
    "push": [
        ["Peito", "Ombro", "Tríceps", "Peito", "Ombro", "Tríceps"],
        ["Ombro", "Peito", "Tríceps", "Ombro", "Peito", "Tríceps"],
    ],
    "pull": [
        ["Costas", "Bíceps", "Costas", "Trapézio", "Bíceps", "Abdômen"],
        ["Costas", "Bíceps", "Trapézio", "Costas", "Bíceps", "Abdômen"],
    ],
    "legs": [
        ["Quadríceps", "Posterior", "Quadríceps", "Panturrilha", "Posterior"],
        ["Posterior", "Quadríceps", "Posterior", "Quadríceps", "Panturrilha"],
    ],
}

REFEICOES_MODELO = [
    ("Café da manhã", "07:00", 0.20),
    ("Lanche da manhã", "10:00", 0.10),
    ("Almoço", "12:30", 0.30),
    ("Lanche da tarde", "16:00", 0.15),
    ("Jantar", "20:00", 0.25),
]

DIAS_SEMANA = [
    "Segunda-feira", "Terça-feira", "Quarta-feira",
    "Quinta-feira", "Sexta-feira", "Sábado", "Domingo",
]

_PALAVRAS_DIA = [
    "segunda-feira", "segunda", "seg",
    "terça-feira", "terça", "terca-feira", "terca", "ter",
    "quarta-feira", "quarta", "qua",
    "quinta-feira", "quinta", "qui",
    "sexta-feira", "sexta", "sex",
    "sábado", "sáb", "sabado", "sab",
    "domingo", "dom",
]
_DIA_INDICE = {
    "segunda-feira": 0, "segunda": 0, "seg": 0,
    "terça-feira": 1, "terça": 1, "terca-feira": 1, "terca": 1, "ter": 1,
    "quarta-feira": 2, "quarta": 2, "qua": 2,
    "quinta-feira": 3, "quinta": 3, "qui": 3,
    "sexta-feira": 4, "sexta": 4, "sex": 4,
    "sábado": 5, "sáb": 5, "sabado": 5, "sab": 5,
    "domingo": 6, "dom": 6,
}
_DIA_RE = re.compile(
    r"(?<![a-zà-ú0-9])(?:"
    + "|".join(re.escape(p) for p in sorted(_PALAVRAS_DIA, key=len, reverse=True))
    + r")(?![-a-zà-ú0-9])"
)

_TEMPO_RE = re.compile(r"(\d{1,2})\s*[:h]\s*(\d{2})?")

_HORA_PALAVRA = {
    "uma": 1, "um": 1, "duas": 2, "dois": 2, "três": 3, "tres": 3,
    "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9,
    "dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14,
    "quatorze": 14, "quinze": 15, "dezesseis": 16, "dezasseis": 16,
    "dezessete": 17, "dezassete": 17, "dezoito": 18, "dezenove": 19,
    "dezanove": 19, "vinte": 20, "vinte e uma": 21, "vinte e um": 21,
    "vinte e duas": 22, "vinte e dois": 22, "vinte e três": 23,
    "vinte e tres": 23,
}
_MINUTOS_PALAVRA = {
    "cinco": 5, "dez": 10, "quinze": 15, "vinte": 20, "vinte e cinco": 25,
    "trinta": 30, "meia": 30, "quarenta": 40, "quarenta e cinco": 45,
}
_HORA_ALT = "|".join(re.escape(k) for k in sorted(_HORA_PALAVRA, key=len, reverse=True))
_MIN_ALT = "|".join(re.escape(k) for k in sorted(_MINUTOS_PALAVRA, key=len, reverse=True))
_HORA_PALAVRA_RE = re.compile(
    r"(?<![a-zà-ú0-9])"
    r"((?:às?|as|ás|ao|à|á)\s+)?"
    r"(" + _HORA_ALT + r")"
    r"(?:\s+e\s+(" + _MIN_ALT + r"))?"
    r"(\s*(?:horas?|hrs?|\bh\b|da manhã|da manha|da tarde|da noite|,|;|:|\.))?",
    re.IGNORECASE,
)

_DIA_ALT = "|".join(re.escape(p) for p in sorted(_PALAVRAS_DIA, key=len, reverse=True))
_FAIXA_RE = re.compile(
    r"(?<![a-zà-ú0-9])(" + _DIA_ALT + r")(?![a-zà-ú-])\s+"
    r"(?:a|às|as|até|ate)\s+"
    r"(?<![a-zà-ú])(?![0-9])(" + _DIA_ALT + r")(?![a-zà-ú0-9])",
    re.IGNORECASE,
)

_REFEICOES_CHAVE = [
    ("Café da manhã", ["café da manhã", "café da manha", "desjejum", "café", "cafe"]),
    ("Lanche da manhã", ["lanche da manhã", "lanche da manha"]),
    ("Almoço", ["almoço", "almoco", "almoçar", "almocar", "almocei"]),
    ("Lanche da tarde", ["lanche da tarde", "café da tarde", "cafe da tarde"]),
    ("Jantar", ["jantar", "janto", "ceia", "ceio", "jantarei"]),
]
_ACORDAR_CHAVE = ["acordo", "acordar", "acordou", "levanto", "levantar", "levantei", "desperto"]
_FREQ_X_RE = re.compile(r"(\d)\s*(?:x|vezes)\s*(?:por\s*)?(?:semana|sem)|(?:^|\s)(\d)\s*(?:x|vezes)", re.IGNORECASE)
_FREQ_PALAVRA = [
    ("três", 3), ("tres", 3), ("quatro", 4), ("cinco", 5), ("seis", 6),
]


def _meu_tempo(m):
    h = int(m.group(1))
    if h > 23:
        return None
    if m.group(2):
        mini = int(m.group(2))
        if mini > 59:
            return None
    else:
        mini = 0
    return f"{h:02d}:{mini:02d}"


def _tempos_no_texto(t):
    """Lista eventos de horário (numérico + por extenso) com posição no texto."""
    evs = []
    for m in _TEMPO_RE.finditer(t):
        val = _meu_tempo(m)
        if val is not None:
            evs.append((m.start(), m.end(), val))
    for m in _HORA_PALAVRA_RE.finditer(t):
        pre = m.group(1)
        minu = m.group(3)
        cauda = m.group(4) or ""
        if pre is None and minu is None:
            if not re.search(r"(horas?|hrs|\bh\b|manhã|manha|tarde|noite)", cauda):
                continue
        h = _HORA_PALAVRA[m.group(2).lower()]
        mini = _MINUTOS_PALAVRA.get(minu.lower(), 0) if minu else 0
        if h <= 23:
            evs.append((m.start(), m.end(), f"{h:02d}:{mini:02d}"))
    return evs


def _tempo_proximo(t, pos, antes=30, depois=60):
    evs = sorted(_tempos_no_texto(t))
    for s, e, val in evs:
        if s >= pos and s <= pos + depois:
            return val
    for s, e, val in evs:
        if e <= pos and e >= pos - antes:
            return val
    return None


def _detectar_dias(t):
    ordem = []
    for m in _DIA_RE.finditer(t):
        ind = _DIA_INDICE[m.group(0).lower()]
        if ind not in ordem:
            ordem.append(ind)
    for m in _FAIXA_RE.finditer(t):
        d1 = _DIA_INDICE[m.group(1).lower()]
        d2 = _DIA_INDICE[m.group(2).lower()]
        if d1 < d2:
            pos = ordem.index(d1) if d1 in ordem else len(ordem)
            for d in range(d2 - 1, d1, -1):
                if d not in ordem:
                    ordem.insert(pos + 1, d)
        elif d1 > d2:
            for d in list(range(d1 + 1, 7)) + list(range(0, d2)):
                if d not in ordem:
                    ordem.append(d)
    return ordem[:6]


def _detectar_frequencia(t):
    m = re.search(r"(?:treino|academia|malho|treinar)(?:s)?\s*(?:[e,\s]|de\s+)?(\d)\s*(?:x|vezes)", t)
    if not m:
        m = re.search(r"(\d)\s*(?:x|vezes)\s*(?:por\s*)?(?:semana|sem)", t)
    if not m:
        for palavra, val in _FREQ_PALAVRA:
            if re.search(rf"{re.escape(palavra)}\s*(?:vezes|v)|{re.escape(palavra)}\s*(?:por\s*)?semana", t):
                return val
    if m:
        val = int(m.group(1)) if m.group(1) else int(m.group(2))
        if 3 <= val <= 6:
            return val
    return None


def analisar_rotina(texto):
    """Analisa a rotina colada e devolve dias de treino + horários de refeição."""
    if not texto or not str(texto).strip():
        return None
    t = " " + str(texto).lower() + " "
    dias = _detectar_dias(t)
    freq = _detectar_frequencia(t)

    horarios = {}
    algum_tempo = False
    despertar = _tempo_proximo(t, 0, antes=0, depois=len(t))  # primeiro horário citado
    for i, (nome, padrao, frac) in enumerate(REFEICOES_MODELO):
        pos = None
        for k in _REFEICOES_CHAVE[i][1]:
            p = t.find(k)
            if p != -1:
                pos = p
                break
        tempo = _tempo_proximo(t, pos, depois=70) if pos is not None else None
        if tempo is None and i == 0 and pos is None:
            for k in _ACORDAR_CHAVE:
                p = t.find(k)
                if p != -1:
                    tempo = _tempo_proximo(t, p, antes=20, depois=50)
                    break
        horarios[nome] = tempo or padrao
        if tempo:
            algum_tempo = True

    return {
        "dias_ordem": [DIAS_SEMANA[d] for d in dias],
        "qtd_dias": len(dias),
        "frequencia": freq,
        "horarios": horarios,
        "tem_tempos": algum_tempo,
    }


def semana_para_aluno(a, n_sessoes):
    """Devolve a lista de dias da semana alinhada às sessões do split."""
    rot = analisar_rotina(a["rotina"] or "")
    if not rot or rot["qtd_dias"] not in (3, 4, 5, 6) or rot["qtd_dias"] != n_sessoes:
        return [None] * n_sessoes
    lista = rot["dias_ordem"] + [None] * n_sessoes
    return lista[:n_sessoes]

LIBRARY = [
    ("Supino reto com barra", "Peito", 1, 3, "6-8", "120s"),
    ("Supino inclinado com halteres", "Peito", 1, 3, "8-10", "120s"),
    ("Crucifixo com halteres", "Peito", 0, 2, "12-15", "75s"),
    ("Crossover na polia", "Peito", 0, 2, "12-15", "75s"),
    ("Puxada pela frente", "Costas", 1, 3, "8-10", "120s"),
    ("Remada curvada com barra", "Costas", 1, 3, "8-10", "120s"),
    ("Remada na polia baixa", "Costas", 1, 3, "8-12", "120s"),
    ("Puxada fechada supinada", "Costas", 1, 3, "8-10", "120s"),
    ("Desenvolvimento militar", "Ombro", 1, 3, "8-10", "120s"),
    ("Desenvolvimento com halteres", "Ombro", 1, 3, "8-10", "120s"),
    ("Elevação lateral", "Ombro", 0, 2, "12-15", "75s"),
    ("Elevação frontal", "Ombro", 0, 2, "12-15", "75s"),
    ("Encolhimento com halteres", "Trapézio", 0, 2, "12-15", "75s"),
    ("Rosca direta com barra", "Bíceps", 0, 2, "10-12", "75s"),
    ("Rosca alternada com halteres", "Bíceps", 0, 2, "12", "75s"),
    ("Rosca martelo", "Bíceps", 0, 2, "12", "75s"),
    ("Tríceps na polia (corda)", "Tríceps", 0, 2, "12-15", "75s"),
    ("Tríceps testa", "Tríceps", 0, 2, "10-12", "75s"),
    ("Paralelas", "Tríceps", 1, 3, "8-12", "90s"),
    ("Agachamento livre", "Quadríceps", 1, 3, "6-8", "150s"),
    ("Leg press 45", "Quadríceps", 1, 3, "8-12", "120s"),
    ("Cadeira extensora", "Quadríceps", 0, 2, "12-15", "75s"),
    ("Afundo búlgaro", "Quadríceps", 1, 3, "8-10", "120s"),
    ("Levantamento terra romeno", "Posterior", 1, 3, "8-10", "150s"),
    ("Stiff com barra", "Posterior", 1, 3, "8-10", "120s"),
    ("Mesa flexora", "Posterior", 0, 2, "12-15", "75s"),
    ("Hip thrust", "Glúteo", 1, 3, "10-12", "120s"),
    ("Cadeira abdutora", "Glúteo", 0, 2, "15", "75s"),
    ("Coice na polia", "Glúteo", 0, 2, "15", "75s"),
    ("Prancha", "Abdômen", 0, 2, "30-45s", "60s"),
    ("Elevação de pernas", "Abdômen", 0, 2, "12-15", "60s"),
    ("Panturrilha em pé", "Panturrilha", 0, 2, "12-15", "60s"),
    ("Panturrilha sentado", "Panturrilha", 0, 2, "12-15", "60s"),
]

PADROES_MOVIMENTO = [
    "Empurrar horizontal", "Empurrar vertical", "Puxar horizontal", "Puxar vertical",
    "Agachar", "Articulação de quadril", "Afundo", "Extensão de joelhos",
    "Flexão de joelhos", "Extensão de quadril", "Abdução de quadril", "Adução de quadril",
    "Extensão de cotovelo", "Flexão de cotovelo", "Elevação lateral", "Elevação frontal",
    "Adução horizontal", "Flexão de coluna (core)", "Isométrico", "Panturrilha",
    "Encolhimento", "Outro",
]

EQUIPAMENTOS_LISTA = [
    "Barra", "Halteres", "Polia/cabo", "Máquina", "Peso corporal", "Elástico", "Kettlebell",
]
NIVEIS_TREINO = ["Iniciante", "Intermediário", "Avançado"]
OBJETIVOS_TREINO = ["Hipertrofia", "Força", "Resistência", "Outro"]
DURACOES_TREINO = ["30", "45", "60", "75", "90"]

META_OBJETIVO = {
    "Hipertrofia": {"series": None, "repeticoes": None, "rir": None, "descanso": None},
    "Força": {"series": 5, "repeticoes": "3-6", "rir": "0-1", "descanso": "150-180s"},
    "Resistência": {"series": 3, "repeticoes": "15-20", "rir": "2-3", "descanso": "60s"},
    "Outro": {"series": None, "repeticoes": None, "rir": None, "descanso": None},
}

MODELOS_TREINO = {
    "push": {"label": "Push (Peito · Ombro · Tríceps)", "grupos": GRUPOS["push"][0]},
    "pull": {"label": "Pull (Costas · Bíceps · Trapézio)", "grupos": GRUPOS["pull"][0]},
    "legs": {"label": "Legs (Quadríceps · Posterior · Panturrilha)", "grupos": GRUPOS["legs"][0]},
    "upper": {"label": "Upper (tronco completo)", "grupos": GRUPOS["upper"][0]},
    "lower": {"label": "Lower (pernas completas)", "grupos": GRUPOS["lower"][0]},
    "fullbody": {"label": "Full Body (corpo completo)", "grupos": GRUPOS["fullbody"][0]},
}

DETALHES_EXERCICIOS = {
    "Supino reto com barra": {"grupo": "Peito", "grande": 1, "series": 3, "repeticoes": "6-8", "descanso": "120s",
        "secundarios": "Tríceps, Deltoide anterior", "padrao": "Empurrar horizontal", "equipamento": "Barra",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Cotovelos a ~45°; escápulas retraídas e apoiadas."},
    "Supino inclinado com halteres": {"grupo": "Peito", "grande": 1, "series": 3, "repeticoes": "8-10", "descanso": "120s",
        "secundarios": "Deltoide anterior, Tríceps", "padrao": "Empurrar horizontal", "equipamento": "Halteres",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Banco ~30°; desça até o peitoral alongar."},
    "Supino reto com halteres": {"grupo": "Peito", "grande": 1, "series": 3, "repeticoes": "8-12", "descanso": "120s",
        "secundarios": "Tríceps, Deltoide anterior", "padrao": "Empurrar horizontal", "equipamento": "Halteres",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Variação com maior amplitude que a barra."},
    "Supino máquina": {"grupo": "Peito", "grande": 1, "series": 3, "repeticoes": "10-12", "descanso": "90s",
        "secundarios": "Tríceps, Deltoide anterior", "padrao": "Empurrar horizontal", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "1-2", "observacoes": "Ajuste o assento para alinhar a pegada ao peitoral."},
    "Crucifixo com halteres": {"grupo": "Peito", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Deltoide anterior, Tríceps", "padrao": "Adução horizontal", "equipamento": "Halteres",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Braços quase estendidos; sinta o peitoral."},
    "Crossover na polia": {"grupo": "Peito", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Deltoide anterior, Tríceps", "padrao": "Adução horizontal", "equipamento": "Polia/cabo",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Pequena inclinação do tronco à frente."},
    "Flexão de braços": {"grupo": "Peito", "grande": 1, "series": 3, "repeticoes": "10-15", "descanso": "60s",
        "secundarios": "Tríceps, Deltoide anterior, Core", "padrao": "Empurrar horizontal", "equipamento": "Peso corporal",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Corpo em linha; cotovelos ~45° do tronco."},
    "Puxada pela frente": {"grupo": "Costas", "grande": 1, "series": 3, "repeticoes": "8-10", "descanso": "120s",
        "secundarios": "Bíceps, Posterior do ombro", "padrao": "Puxar vertical", "equipamento": "Polia/cabo",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Puxe até o peito; tronco estável."},
    "Puxada fechada supinada": {"grupo": "Costas", "grande": 1, "series": 3, "repeticoes": "8-10", "descanso": "120s",
        "secundarios": "Bíceps, Posterior do ombro", "padrao": "Puxar vertical", "equipamento": "Polia/cabo",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Pegada supinada fechada; puxe ao peito."},
    "Puxada aberta (barra)": {"grupo": "Costas", "grande": 1, "series": 4, "repeticoes": "6-10", "descanso": "120s",
        "secundarios": "Bíceps, Posterior do ombro", "padrao": "Puxar vertical", "equipamento": "Barra",
        "nivel": "Avançado", "rir": "1-2", "observacoes": "Dominada com pegada aberta; não balançar."},
    "Barra fixa prona": {"grupo": "Costas", "grande": 1, "series": 4, "repeticoes": "6-10", "descanso": "120s",
        "secundarios": "Bíceps, Posterior do ombro", "padrao": "Puxar vertical", "equipamento": "Peso corporal",
        "nivel": "Avançado", "rir": "1-2", "observacoes": "Assistência permitida (elástico/máquina)."},
    "Remada curvada com barra": {"grupo": "Costas", "grande": 1, "series": 3, "repeticoes": "8-10", "descanso": "120s",
        "secundarios": "Bíceps, Lombar, Posterior do ombro", "padrao": "Puxar horizontal", "equipamento": "Barra",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Tronco inclinado ~45°; escápulas se aproximam."},
    "Remada na polia baixa": {"grupo": "Costas", "grande": 1, "series": 3, "repeticoes": "8-12", "descanso": "120s",
        "secundarios": "Bíceps, Posterior do ombro", "padrao": "Puxar horizontal", "equipamento": "Polia/cabo",
        "nivel": "Iniciante", "rir": "1-2", "observacoes": "Tronco estável; puxe sem compensar com a lombar."},
    "Remada unilateral com halteres": {"grupo": "Costas", "grande": 1, "series": 3, "repeticoes": "8-12", "descanso": "90s",
        "secundarios": "Bíceps, Posterior do ombro", "padrao": "Puxar horizontal", "equipamento": "Halteres",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Apoie uma mão no banco; tronco quase paralelo."},
    "Remada máquina": {"grupo": "Costas", "grande": 1, "series": 3, "repeticoes": "10-12", "descanso": "90s",
        "secundarios": "Bíceps, Posterior do ombro", "padrao": "Puxar horizontal", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "1-2", "observacoes": "Escápulas se aproximam no final do movimento."},
    "Desenvolvimento militar": {"grupo": "Ombro", "grande": 1, "series": 3, "repeticoes": "8-10", "descanso": "120s",
        "secundarios": "Tríceps, Deltoide lateral, Trapézio superior", "padrao": "Empurrar vertical", "equipamento": "Barra",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Core firme; não arqueie a lombar."},
    "Desenvolvimento com halteres": {"grupo": "Ombro", "grande": 1, "series": 3, "repeticoes": "8-10", "descanso": "120s",
        "secundarios": "Tríceps, Deltoide lateral", "padrao": "Empurrar vertical", "equipamento": "Halteres",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Sente-se em banco com encosto para estabilizar."},
    "Desenvolvimento máquina": {"grupo": "Ombro", "grande": 1, "series": 3, "repeticoes": "10-12", "descanso": "90s",
        "secundarios": "Tríceps, Deltoide lateral", "padrao": "Empurrar vertical", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "1-2", "observacoes": "Ajuste o encosto para os ombros."},
    "Elevação lateral": {"grupo": "Ombro", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Trapézio superior, Serrátil", "padrao": "Elevação lateral", "equipamento": "Halteres",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Sem balanço; controle na descida."},
    "Elevação lateral na polia": {"grupo": "Ombro", "grande": 0, "series": 3, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Trapézio superior", "padrao": "Elevação lateral", "equipamento": "Polia/cabo",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Tensão constante durante todo o movimento."},
    "Elevação frontal": {"grupo": "Ombro", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Deltoide lateral", "padrao": "Elevação frontal", "equipamento": "Halteres",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Eleve até a altura dos ombros apenas."},
    "Encolhimento com halteres": {"grupo": "Trapézio", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Sem secundários relevantes", "padrao": "Encolhimento", "equipamento": "Halteres",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Subida e descida controladas; sem rotação dos ombros."},
    "Rosca direta com barra": {"grupo": "Bíceps", "grande": 0, "series": 2, "repeticoes": "10-12", "descanso": "75s",
        "secundarios": "Antebraço, Braquial", "padrao": "Flexão de cotovelo", "equipamento": "Barra",
        "nivel": "Iniciante", "rir": "1-2", "observacoes": "Cotovelos fixos ao tronco; sem balanço."},
    "Rosca alternada com halteres": {"grupo": "Bíceps", "grande": 0, "series": 2, "repeticoes": "12", "descanso": "75s",
        "secundarios": "Antebraço, Braquial", "padrao": "Flexão de cotovelo", "equipamento": "Halteres",
        "nivel": "Iniciante", "rir": "1-2", "observacoes": "Supine o punho na subida."},
    "Rosca martelo": {"grupo": "Bíceps", "grande": 0, "series": 2, "repeticoes": "12", "descanso": "75s",
        "secundarios": "Braquiorradial, Antebraço", "padrao": "Flexão de cotovelo", "equipamento": "Halteres",
        "nivel": "Iniciante", "rir": "1-2", "observacoes": "Pegada neutra (palmas para dentro)."},
    "Rosca scott": {"grupo": "Bíceps", "grande": 0, "series": 3, "repeticoes": "10-12", "descanso": "75s",
        "secundarios": "Braquial, Antebraço", "padrao": "Flexão de cotovelo", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "1-2", "observacoes": "Braços apoiados no banco; sem descolar na subida."},
    "Tríceps na polia (corda)": {"grupo": "Tríceps", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Sem secundários relevantes", "padrao": "Extensão de cotovelo", "equipamento": "Polia/cabo",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Cotovelos fixos; estenda até o final."},
    "Tríceps testa": {"grupo": "Tríceps", "grande": 0, "series": 2, "repeticoes": "10-12", "descanso": "75s",
        "secundarios": "Sem secundários relevantes", "padrao": "Extensão de cotovelo", "equipamento": "Barra",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Cotovelos apontando para frente; controle na descida."},
    "Tríceps banco (fundo)": {"grupo": "Tríceps", "grande": 0, "series": 3, "repeticoes": "10-15", "descanso": "75s",
        "secundarios": "Peitoral, Deltoide anterior", "padrao": "Extensão de cotovelo", "equipamento": "Peso corporal",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Desça até os cotovelos à ~90°; não deixe os ombros caírem."},
    "Paralelas": {"grupo": "Tríceps", "grande": 1, "series": 3, "repeticoes": "8-12", "descanso": "90s",
        "secundarios": "Peitoral, Deltoide anterior", "padrao": "Extensão de cotovelo", "equipamento": "Peso corporal",
        "nivel": "Avançado", "rir": "1-2", "observacoes": "Tronco levemente inclinado para ênfase no peitoral."},
    "Agachamento livre": {"grupo": "Quadríceps", "grande": 1, "series": 3, "repeticoes": "6-8", "descanso": "150s",
        "secundarios": "Posterior, Glúteo, Abdômen", "padrao": "Agachar", "equipamento": "Barra",
        "nivel": "Avançado", "rir": "1-2", "observacoes": "Profundidade controlada; joelhos alinhados aos pés."},
    "Agachamento goblet": {"grupo": "Quadríceps", "grande": 1, "series": 3, "repeticoes": "10-12", "descanso": "120s",
        "secundarios": "Glúteo, Core", "padrao": "Agachar", "equipamento": "Halteres",
        "nivel": "Iniciante", "rir": "1-2", "observacoes": "Segure o halter junto ao peito; tronco ereto."},
    "Leg press 45": {"grupo": "Quadríceps", "grande": 1, "series": 3, "repeticoes": "8-12", "descanso": "120s",
        "secundarios": "Glúteo, Posterior", "padrao": "Agachar", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "1-2", "observacoes": "Não trave os joelhos no topo."},
    "Leg press unilateral": {"grupo": "Quadríceps", "grande": 1, "series": 3, "repeticoes": "10-12", "descanso": "90s",
        "secundarios": "Glúteo, Posterior", "padrao": "Agachar", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "1-2", "observacoes": "Corrija assimetrias de perna."},
    "Cadeira extensora": {"grupo": "Quadríceps", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Sem secundários relevantes", "padrao": "Extensão de joelhos", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Pausa de 1s no topo."},
    "Afundo búlgaro": {"grupo": "Quadríceps", "grande": 1, "series": 3, "repeticoes": "8-10", "descanso": "120s",
        "secundarios": "Glúteo, Posterior, Abdômen", "padrao": "Afundo", "equipamento": "Halteres",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Tronco vertical; pé de trás sobre o banco."},
    "Levantamento terra romeno": {"grupo": "Posterior", "grande": 1, "series": 3, "repeticoes": "8-10", "descanso": "150s",
        "secundarios": "Glúteo, Lombar, Trapézio", "padrao": "Articulação de quadril", "equipamento": "Barra",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Coluna neutra; quadris para trás."},
    "Stiff com barra": {"grupo": "Posterior", "grande": 1, "series": 3, "repeticoes": "8-10", "descanso": "120s",
        "secundarios": "Glúteo, Lombar", "padrao": "Articulação de quadril", "equipamento": "Barra",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Joelhos semiflexionados; sinta o alongamento posterior."},
    "Mesa flexora": {"grupo": "Posterior", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Sem secundários relevantes", "padrao": "Flexão de joelhos", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Controle na descida (fase excêntrica)."},
    "Cadeira flexora": {"grupo": "Posterior", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Sem secundários relevantes", "padrao": "Flexão de joelhos", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Pés apoiados; quadril colado ao banco."},
    "Hip thrust": {"grupo": "Glúteo", "grande": 1, "series": 3, "repeticoes": "10-12", "descanso": "120s",
        "secundarios": "Posterior, Abdômen", "padrao": "Extensão de quadril", "equipamento": "Barra",
        "nivel": "Avançado", "rir": "1-2", "observacoes": "Empurre com os calcanhares; extensão máxima do quadril."},
    "Elevação pélvica (peso corporal)": {"grupo": "Glúteo", "grande": 0, "series": 3, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Posterior, Abdômen", "padrao": "Extensão de quadril", "equipamento": "Peso corporal",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Variação do hip thrust para iniciar a progressão."},
    "Cadeira abdutora": {"grupo": "Glúteo", "grande": 0, "series": 2, "repeticoes": "15", "descanso": "75s",
        "secundarios": "Glúteo médio", "padrao": "Abdução de quadril", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Controle; não deixe o peso 'bater'."},
    "Coice na polia": {"grupo": "Glúteo", "grande": 0, "series": 2, "repeticoes": "15", "descanso": "75s",
        "secundarios": "Posterior", "padrao": "Extensão de quadril", "equipamento": "Polia/cabo",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Não arquear a lombar na extensão."},
    "Prancha": {"grupo": "Abdômen", "grande": 0, "series": 2, "repeticoes": "30-45s", "descanso": "60s",
        "secundarios": "Ombro, Glúteo", "padrao": "Isométrico", "equipamento": "Peso corporal",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Corpo em linha; não deixe o quadril cair."},
    "Prancha lateral": {"grupo": "Abdômen", "grande": 0, "series": 2, "repeticoes": "30-45s", "descanso": "60s",
        "secundarios": "Oblíquos, Ombro", "padrao": "Isométrico", "equipamento": "Peso corporal",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Quadril alinhado; cotovelo sob o ombro."},
    "Elevação de pernas": {"grupo": "Abdômen", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "60s",
        "secundarios": "Flexores de quadril", "padrao": "Flexão de coluna (core)", "equipamento": "Peso corporal",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Lombar colada ao chão/banco."},
    "Abdominal na polia": {"grupo": "Abdômen", "grande": 0, "series": 3, "repeticoes": "12-15", "descanso": "60s",
        "secundarios": "Oblíquos", "padrao": "Flexão de coluna (core)", "equipamento": "Polia/cabo",
        "nivel": "Intermediário", "rir": "2-3", "observacoes": "Curve a coluna torácica; não puxe só com os braços."},
    "Panturrilha em pé": {"grupo": "Panturrilha", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "60s",
        "secundarios": "Sem secundários relevantes", "padrao": "Panturrilha", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Amplitude completa; pausa no topo."},
    "Panturrilha sentado": {"grupo": "Panturrilha", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "60s",
        "secundarios": "Sóleo", "padrao": "Panturrilha", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Enfatiza o sóleo; controle na descida."},
    "Supino declinado com barra": {"grupo": "Peito", "grande": 1, "series": 3, "repeticoes": "8-10", "descanso": "120s",
        "secundarios": "Tríceps, Deltoide anterior", "padrao": "Empurrar horizontal", "equipamento": "Barra",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Ênfase no peitoral inferior; mantenha os pés fixos."},
    "Peck deck": {"grupo": "Peito", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Deltoide anterior", "padrao": "Adução horizontal", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Ajuste o encosto; movimento sem rebater os pesos."},
    "Voador com halteres": {"grupo": "Peito", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Deltoide anterior", "padrao": "Adução horizontal", "equipamento": "Halteres",
        "nivel": "Intermediário", "rir": "2-3", "observacoes": "Cotovelos levemente flexionados e fixos."},
    "Puxada com corda (polia)": {"grupo": "Costas", "grande": 1, "series": 3, "repeticoes": "10-12", "descanso": "90s",
        "secundarios": "Bíceps, Posterior", "padrao": "Puxar vertical", "equipamento": "Polia/cabo",
        "nivel": "Iniciante", "rir": "1-2", "observacoes": "Mantenha o tronco ereto; puxe com os cotovelos."},
    "Remada T (cavalinho)": {"grupo": "Costas", "grande": 1, "series": 3, "repeticoes": "8-10", "descanso": "120s",
        "secundarios": "Bíceps, Posterior, Lombar", "padrao": "Puxar horizontal", "equipamento": "Barra",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Tronco próximo de 45°; escápulas retraídas."},
    "Crucifixo inverso na polia": {"grupo": "Costas", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Deltoide posterior, Trapézio", "padrao": "Adução horizontal", "equipamento": "Polia/cabo",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Deltoide posterior; abra até a linha dos ombros."},
    "Desenvolvimento Arnold": {"grupo": "Ombro", "grande": 1, "series": 3, "repeticoes": "8-12", "descanso": "120s",
        "secundarios": "Tríceps, Trapézio", "padrao": "Empurrar vertical", "equipamento": "Halteres",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Rotações das palmas durante o movimento."},
    "Elevação posterior no crossover": {"grupo": "Ombro", "grande": 0, "series": 2, "repeticoes": "12-15", "descanso": "75s",
        "secundarios": "Trapézio, Deltoide posterior", "padrao": "Adução horizontal", "equipamento": "Polia/cabo",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Deltoide posterior; sem balanço de tronco."},
    "Encolhimento com barra": {"grupo": "Trapézio", "grande": 0, "series": 2, "repeticoes": "10-12", "descanso": "75s",
        "secundarios": "Sem secundários relevantes", "padrao": "Encolhimento", "equipamento": "Barra",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Suba os ombros em linha reta; sem rotação."},
    "Rosca concentrada": {"grupo": "Bíceps", "grande": 0, "series": 3, "repeticoes": "10-12", "descanso": "75s",
        "secundarios": "Braquial, Antebraço", "padrao": "Flexão de cotovelo", "equipamento": "Halteres",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Cotovelo apoiado; contração máxima no topo."},
    "Rosca no banco inclinado": {"grupo": "Bíceps", "grande": 0, "series": 3, "repeticoes": "10-12", "descanso": "75s",
        "secundarios": "Braquial, Antebraço", "padrao": "Flexão de cotovelo", "equipamento": "Halteres",
        "nivel": "Intermediário", "rir": "2-3", "observacoes": "Banco ~45°; alonga bem o bíceps na descida."},
    "Tríceps francês com halteres": {"grupo": "Tríceps", "grande": 0, "series": 3, "repeticoes": "10-12", "descanso": "75s",
        "secundarios": "Sem secundários relevantes", "padrao": "Extensão de cotovelo", "equipamento": "Halteres",
        "nivel": "Intermediário", "rir": "2-3", "observacoes": "Cotovelos fixos apontando para cima."},
    "Tríceps na polia com barra reta": {"grupo": "Tríceps", "grande": 0, "series": 3, "repeticoes": "12-15", "descanso": "60s",
        "secundarios": "Sem secundários relevantes", "padrao": "Extensão de cotovelo", "equipamento": "Polia/cabo",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Cotovelos junto ao corpo durante todo o movimento."},
    "Agachamento frontal com barra": {"grupo": "Quadríceps", "grande": 1, "series": 3, "repeticoes": "6-8", "descanso": "150s",
        "secundarios": "Glúteo, Core", "padrao": "Agachar", "equipamento": "Barra",
        "nivel": "Avançado", "rir": "0-1", "observacoes": "Cotovelos altos e core rígido; tórax ereto."},
    "Agachamento hack": {"grupo": "Quadríceps", "grande": 1, "series": 3, "repeticoes": "8-10", "descanso": "120s",
        "secundarios": "Glúteo", "padrao": "Agachar", "equipamento": "Máquina",
        "nivel": "Intermediário", "rir": "1-2", "observacoes": "Pés apoiados na plataforma; depth confortável."},
    "Levantamento terra (pegada sumô)": {"grupo": "Posterior", "grande": 1, "series": 3, "repeticoes": "6-8", "descanso": "150s",
        "secundarios": "Glúteo, Quadríceps, Lombar", "padrao": "Articulação de quadril", "equipamento": "Barra",
        "nivel": "Avançado", "rir": "0-1", "observacoes": "Pés afastados; empurre o chão para longe."},
    "Crunch na máquina": {"grupo": "Abdômen", "grande": 0, "series": 3, "repeticoes": "12-15", "descanso": "60s",
        "secundarios": "Sem secundários relevantes", "padrao": "Flexão de coluna (core)", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Flexione a coluna; expira na contração."},
    "Adução de quadril na máquina": {"grupo": "Glúteo", "grande": 0, "series": 2, "repeticoes": "15", "descanso": "60s",
        "secundarios": "Adutores", "padrao": "Adução de quadril", "equipamento": "Máquina",
        "nivel": "Iniciante", "rir": "2-3", "observacoes": "Mantenha o encosto encostado; controle na volta."},
}


CATEGORIAS = [
    "Carboidratos", "Proteínas", "Laticínios", "Verduras e Legumes",
    "Frutas", "Gorduras", "Extras",
]

STATUS_LEADS = ("novo", "em contato", "proposta", "convertido", "perdido")

MEDIDAS = [
    ("peso", "Peso (kg)"),
    ("percentual_gordura", "% Gordura"),
    ("peito", "Peito (cm)"),
    ("ombro", "Ombro (cm)"),
    ("biceps", "Bíceps (cm)"),
    ("antebraco", "Antebraço (cm)"),
    ("cintura", "Cintura (cm)"),
    ("abdomen", "Abdômen (cm)"),
    ("quadril", "Quadril (cm)"),
    ("coxa", "Coxa (cm)"),
    ("panturrilha", "Panturrilha (cm)"),
]

MEDIDAS_GRAFICO = [
    ("peso", "Peso", "kg"),
    ("percentual_gordura", "% gordura", "%"),
    ("biceps", "Bíceps", "cm"),
    ("cintura", "Cintura", "cm"),
    ("quadril", "Quadril", "cm"),
    ("coxa", "Coxa", "cm"),
]

LEAD_ORIGENS = ["Instagram", "Indicação", "WhatsApp", "Google", "Rua/Redes", "Outro"]

DESPESA_CATEGORIAS = ["Ferramentas", "Marketing", "Impostos", "Aluguel", "Suplementos", "Transporte", "Outros"]

EQUIV_LABELS = {
    "amido": "Amidos (arroz, batata, mandioca...)",
    "pao": "Pães (francês, integral, torrada...)",
    "cereal": "Cereais (aveia, granola...)",
    "leguminosa": "Leguminosas (feijão, lentilha...)",
    "proteina": "Proteínas (frango, peixe, carne, ovo...)",
    "laticinio": "Laticínios (leite, iogurte, queijo...)",
    "verdura_folha": "Folhas (alface, rúcula, espinafre...)",
    "legume": "Legumes (brócolis, cenoura, abobrinha...)",
    "fruta": "Frutas (banana, maçã, mamão...)",
    "gordura": "Gorduras (azeite, castanhas, abacate...)",
    "doce": "Extras/doces (mel...)",
}

ALIMENTOS = [
    # Carboidratos - amidos
    ("Arroz branco cozido", "Carboidratos", "amido"),
    ("Arroz integral cozido", "Carboidratos", "amido"),
    ("Batata inglesa cozida", "Carboidratos", "amido"),
    ("Batata-doce cozida", "Carboidratos", "amido"),
    ("Mandioca cozida", "Carboidratos", "amido"),
    ("Inhame cozido", "Carboidratos", "amido"),
    ("Cará cozido", "Carboidratos", "amido"),
    ("Macarrão cozido", "Carboidratos", "amido"),
    ("Polenta", "Carboidratos", "amido"),
    # Carboidratos - pães
    ("Pão francês", "Carboidratos", "pao"),
    ("Pão integral", "Carboidratos", "pao"),
    ("Pão de forma", "Carboidratos", "pao"),
    ("Torrada integral", "Carboidratos", "pao"),
    ("Panqueca integral", "Carboidratos", "pao"),
    ("Tapioca", "Carboidratos", "pao"),
    # Carboidratos - cereais
    ("Aveia em flocos", "Carboidratos", "cereal"),
    ("Granola", "Carboidratos", "cereal"),
    ("Cereal integral", "Carboidratos", "cereal"),
    ("Farinha de mandioca", "Carboidratos", "cereal"),
    # Carboidratos - leguminosas
    ("Feijão carioca", "Carboidratos", "leguminosa"),
    ("Feijão preto", "Carboidratos", "leguminosa"),
    ("Lentilha", "Carboidratos", "leguminosa"),
    ("Grão-de-bico", "Carboidratos", "leguminosa"),
    ("Ervilha", "Carboidratos", "leguminosa"),
    # Proteínas
    ("Peito de frango grelhado", "Proteínas", "proteina"),
    ("Sobrecoxa sem pele", "Proteínas", "proteina"),
    ("Peito de peru", "Proteínas", "proteina"),
    ("Filé de tilápia", "Proteínas", "proteina"),
    ("Filé de merluza", "Proteínas", "proteina"),
    ("Atum em água", "Proteínas", "proteina"),
    ("Salmão grelhado", "Proteínas", "proteina"),
    ("Carne moída magra", "Proteínas", "proteina"),
    ("Bife magro (alcatra)", "Proteínas", "proteina"),
    ("Filé mignon", "Proteínas", "proteina"),
    ("Lagarto cozido", "Proteínas", "proteina"),
    ("Ovo cozido", "Proteínas", "proteina"),
    ("Omelete", "Proteínas", "proteina"),
    ("Tofu", "Proteínas", "proteina"),
    # Laticínios
    ("Leite desnatado", "Laticínios", "laticinio"),
    ("Iogurte natural", "Laticínios", "laticinio"),
    ("Iogurte grego", "Laticínios", "laticinio"),
    ("Queijo cottage", "Laticínios", "laticinio"),
    ("Ricota", "Laticínios", "laticinio"),
    ("Queijo minas frescal", "Laticínios", "laticinio"),
    ("Muçarela (moderado)", "Laticínios", "laticinio"),
    # Verduras e Legumes - folhas
    ("Alface", "Verduras e Legumes", "verdura_folha"),
    ("Rúcula", "Verduras e Legumes", "verdura_folha"),
    ("Espinafre", "Verduras e Legumes", "verdura_folha"),
    ("Couve", "Verduras e Legumes", "verdura_folha"),
    ("Agrião", "Verduras e Legumes", "verdura_folha"),
    ("Escarola", "Verduras e Legumes", "verdura_folha"),
    # Verduras e Legumes
    ("Brócolis", "Verduras e Legumes", "legume"),
    ("Couve-flor", "Verduras e Legumes", "legume"),
    ("Abobrinha", "Verduras e Legumes", "legume"),
    ("Chuchu", "Verduras e Legumes", "legume"),
    ("Cenoura", "Verduras e Legumes", "legume"),
    ("Beterraba", "Verduras e Legumes", "legume"),
    ("Vagem", "Verduras e Legumes", "legume"),
    ("Pepino", "Verduras e Legumes", "legume"),
    ("Tomate", "Verduras e Legumes", "legume"),
    # Frutas
    ("Banana", "Frutas", "fruta"),
    ("Maçã", "Frutas", "fruta"),
    ("Pera", "Frutas", "fruta"),
    ("Mamão papaia", "Frutas", "fruta"),
    ("Melancia", "Frutas", "fruta"),
    ("Melão", "Frutas", "fruta"),
    ("Abacaxi", "Frutas", "fruta"),
    ("Laranja", "Frutas", "fruta"),
    ("Tangerina", "Frutas", "fruta"),
    ("Morango", "Frutas", "fruta"),
    ("Uva", "Frutas", "fruta"),
    (# Gorduras
    "Azeite de oliva", "Gorduras", "gordura"),
    ("Abacate", "Gorduras", "gordura"),
    ("Castanha-do-pará", "Gorduras", "gordura"),
    ("Amêndoas", "Gorduras", "gordura"),
    ("Nozes", "Gorduras", "gordura"),
    ("Pasta de amendoim", "Gorduras", "gordura"),
    ("Manteiga (moderado)", "Gorduras", "gordura"),
    # Extras
    ("Mel", "Extras", "doce"),
]

# Nutrição por 100 g e porção padrão (g): kcal, proteína, carbo, gordura, porção
NUTRI_ALIMENTOS = {
    # amidos
    "Arroz branco cozido": (128, 2.6, 28.1, 0.3, 150),
    "Arroz integral cozido": (124, 2.6, 25.8, 1.0, 150),
    "Batata inglesa cozida": (77, 2.0, 17.0, 0.1, 200),
    "Batata-doce cozida": (86, 1.6, 20.1, 0.1, 150),
    "Mandioca cozida": (125, 0.6, 30.1, 0.3, 150),
    "Inhame cozido": (98, 1.5, 23.2, 0.1, 150),
    "Cará cozido": (92, 0.9, 21.0, 0.2, 150),
    "Macarrão cozido": (158, 5.8, 30.9, 0.9, 150),
    "Polenta": (85, 1.5, 18.0, 0.5, 200),
    # pães
    "Pão francês": (300, 8.0, 58.0, 3.0, 50),
    "Pão integral": (253, 9.0, 44.0, 3.5, 50),
    "Pão de forma": (270, 8.0, 50.0, 3.5, 50),
    "Torrada integral": (345, 12.0, 62.0, 4.0, 40),
    "Panqueca integral": (200, 7.0, 30.0, 5.0, 80),
    "Tapioca": (170, 0.4, 40.0, 0.0, 80),
    # cereais
    "Aveia em flocos": (394, 13.9, 66.3, 6.9, 40),
    "Granola": (400, 10.0, 66.0, 9.0, 40),
    "Cereal integral": (340, 7.0, 76.0, 2.0, 50),
    "Farinha de mandioca": (350, 1.5, 85.0, 1.0, 30),
    # leguminosas
    "Feijão carioca": (76, 4.8, 13.6, 0.5, 100),
    "Feijão preto": (77, 4.5, 14.0, 0.5, 100),
    "Lentilha": (106, 8.3, 18.0, 0.4, 100),
    "Grão-de-bico": (120, 6.4, 20.5, 1.1, 100),
    "Ervilha": (84, 5.4, 14.5, 0.4, 100),
    # proteínas
    "Peito de frango grelhado": (165, 31.0, 0.0, 3.6, 110),
    "Sobrecoxa sem pele": (190, 25.0, 0.0, 9.0, 110),
    "Peito de peru": (104, 22.0, 0.0, 2.0, 120),
    "Filé de tilápia": (128, 26.0, 0.0, 2.6, 130),
    "Filé de merluza": (90, 18.0, 0.0, 1.5, 130),
    "Atum em água": (116, 25.0, 0.0, 0.8, 120),
    "Salmão grelhado": (200, 24.0, 0.0, 11.0, 120),
    "Carne moída magra": (250, 26.0, 0.0, 15.0, 100),
    "Bife magro (alcatra)": (180, 28.0, 0.0, 7.0, 130),
    "Filé mignon": (200, 28.0, 0.0, 9.0, 130),
    "Lagarto cozido": (200, 30.0, 0.0, 8.0, 120),
    "Ovo cozido": (155, 13.0, 1.1, 11.0, 100),
    "Omelete": (200, 13.0, 1.0, 15.0, 120),
    "Tofu": (76, 8.0, 1.9, 4.2, 100),
    # laticínios
    "Leite desnatado": (42, 3.4, 5.0, 0.2, 200),
    "Iogurte natural": (62, 4.0, 5.0, 3.0, 200),
    "Iogurte grego": (97, 9.0, 3.9, 5.0, 170),
    "Queijo cottage": (98, 11.0, 3.4, 4.3, 100),
    "Ricota": (150, 11.0, 3.0, 10.0, 60),
    "Queijo minas frescal": (265, 18.0, 3.0, 20.0, 50),
    "Muçarela (moderado)": (300, 22.0, 2.0, 22.0, 40),
    # folhas
    "Alface": (15, 1.4, 2.9, 0.2, 30),
    "Rúcula": (25, 2.6, 3.6, 0.7, 30),
    "Espinafre": (23, 2.9, 3.6, 0.4, 30),
    "Couve": (31, 2.9, 4.4, 0.5, 30),
    "Agrião": (19, 2.6, 2.3, 0.4, 30),
    "Escarola": (17, 1.2, 2.8, 0.2, 30),
    # legumes
    "Brócolis": (34, 2.8, 6.6, 0.4, 120),
    "Couve-flor": (25, 1.9, 5.0, 0.3, 120),
    "Abobrinha": (17, 1.2, 3.1, 0.3, 120),
    "Chuchu": (20, 0.7, 4.2, 0.1, 100),
    "Cenoura": (34, 0.9, 7.9, 0.2, 80),
    "Beterraba": (43, 1.6, 9.6, 0.2, 80),
    "Vagem": (31, 1.8, 7.0, 0.1, 100),
    "Pepino": (15, 0.7, 3.6, 0.1, 80),
    "Tomate": (18, 1.0, 4.0, 0.2, 100),
    # frutas
    "Banana": (89, 1.1, 22.8, 0.3, 100),
    "Maçã": (52, 0.3, 13.8, 0.2, 130),
    "Pera": (57, 0.4, 15.2, 0.1, 130),
    "Mamão papaia": (43, 0.5, 11.0, 0.3, 200),
    "Melancia": (30, 0.6, 7.5, 0.2, 240),
    "Melão": (34, 0.8, 8.2, 0.2, 200),
    "Abacaxi": (50, 0.5, 13.1, 0.1, 150),
    "Laranja": (47, 0.9, 11.8, 0.1, 150),
    "Tangerina": (53, 0.8, 13.3, 0.3, 130),
    "Morango": (32, 0.7, 7.7, 0.3, 150),
    "Uva": (69, 0.7, 18.1, 0.2, 120),
    # gorduras
    "Azeite de oliva": (884, 0.0, 0.0, 100.0, 10),
    "Abacate": (160, 2.0, 8.5, 14.7, 60),
    "Castanha-do-pará": (656, 14.3, 12.3, 66.0, 20),
    "Amêndoas": (579, 21.2, 21.6, 50.0, 20),
    "Nozes": (654, 15.2, 13.7, 65.0, 20),
    "Pasta de amendoim": (588, 25.0, 20.0, 50.0, 20),
    "Manteiga (moderado)": (717, 0.9, 0.1, 81.0, 10),
    # extras
    "Mel": (304, 0.0, 82.0, 0.0, 20),
}

ALIMENTOS_PADRAO = {
    "Café da manhã": ["Banana", "Aveia em flocos", "Iogurte natural"],
    "Lanche da manhã": ["Maçã", "Castanha-do-pará"],
    "Almoço": ["Arroz branco cozido", "Feijão preto", "Peito de frango grelhado", "Alface", "Tomate"],
    "Lanche da tarde": ["Pão integral", "Queijo cottage"],
    "Jantar": ["Batata-doce cozida", "Filé de tilápia", "Brócolis", "Azeite de oliva"],
}


# ---------------------------------------------------------------------------
# Porções realistas por grupo e por alimento (g): (mínimo, ideal, máximo).
# O assistente NUNCA passa desses limites: porção realista vence a matemática.
# ---------------------------------------------------------------------------
PORCOES_POR_GRUPO = {
    "amido":         (60, 150, 250),
    "pao":           (40, 80, 100),
    "cereal":        (20, 40, 70),
    "leguminosa":    (60, 100, 160),
    "proteina":      (80, 150, 250),
    "laticinio":     (50, 140, 300),
    "fruta":         (80, 130, 220),
    "gordura":       (5, 12, 25),
    "doce":          (10, 20, 40),
    "legume":        (60, 120, 160),
    "verdura_folha": (20, 40, 80),
}

PORCOES_POR_NOME = {
    "Iogurte natural":        (100, 170, 300),
    "Iogurte grego":          (100, 170, 300),
    "Leite desnatado":        (100, 200, 300),
    "Arroz branco cozido":    (100, 180, 300),
    "Arroz integral cozido":  (100, 180, 300),
    "Batata-doce cozida":     (100, 200, 300),
    "Batata inglesa cozida":  (80, 200, 300),
    "Macarrão cozido":        (80, 180, 280),
    "Mandioca cozida":        (80, 180, 280),
    "Feijão preto":           (60, 100, 160),
    "Feijão carioca":         (60, 100, 160),
    "Lentilha":               (60, 100, 160),
    "Grão-de-bico":           (60, 100, 160),
    "Peito de frango grelhado": (100, 180, 250),
    "Filé de tilápia":        (100, 180, 250),
    "Filé de merluza":        (100, 180, 250),
    "Peito de peru":          (80, 150, 200),
    "Bife magro (alcatra)":   (100, 180, 250),
    "Carne moída magra":      (80, 150, 220),
    "Salmão grelhado":        (100, 160, 220),
    "Atum em água":           (80, 150, 200),
    "Ovo cozido":             (50, 100, 200),
    "Tofu":                   (80, 150, 250),
    "Pão integral":           (40, 60, 100),
    "Pão francês":            (40, 80, 100),
    "Torrada integral":       (30, 40, 60),
    "Tapioca":                (60, 80, 120),
    "Aveia em flocos":        (20, 40, 70),
    "Granola":                (20, 40, 60),
    "Cereal integral":        (30, 50, 70),
    "Castanha-do-pará":       (10, 20, 30),
    "Amêndoas":               (10, 20, 30),
    "Nozes":                  (10, 20, 30),
    "Pasta de amendoim":      (10, 20, 30),
    "Azeite de oliva":        (5, 10, 15),
    "Banana":                 (70, 110, 150),
    "Maçã":                   (80, 130, 170),
    "Pera":                   (80, 130, 170),
    "Laranja":                (100, 160, 240),
    "Mamão papaia":           (100, 200, 300),
    "Morango":                (80, 150, 250),
    "Uva":                    (80, 120, 150),
    "Abacaxi":                (100, 150, 240),
    "Queijo cottage":         (50, 120, 200),
    "Ricota":                 (50, 80, 120),
    "Queijo minas frescal":   (40, 60, 90),
    "Alface":                 (20, 40, 80),
    "Rúcula":                 (20, 40, 80),
    "Espinafre":              (20, 40, 80),
    "Couve":                  (20, 40, 80),
    "Tomate":                 (60, 100, 160),
    "Brócolis":               (60, 120, 160),
    "Couve-flor":             (60, 120, 160),
    "Cenoura":                (50, 80, 120),
    "Abobrinha":              (60, 120, 160),
    "Chuchu":                 (60, 100, 150),
    "Vagem":                  (60, 100, 150),
    "Pepino":                 (50, 80, 130),
    "Beterraba":              (50, 80, 120),
}

# Tolerâncias aceitáveis: a dieta é considera pronta dentro desses desvios.
TOLERANCIAS_DIETA = {"kcal_pct": 1.5, "proteina": 5.0, "carbo": 10.0, "gordura": 5.0}

# Distribuição diária por refeição: (kcal, proteína, carbo, gordura) - somam 1.0.
DISTRIBUICAO_REFEICOES = {
    "Café da manhã":   (0.20, 0.18, 0.22, 0.18),
    "Lanche da manhã": (0.10, 0.10, 0.08, 0.12),
    "Almoço":          (0.30, 0.32, 0.30, 0.30),
    "Lanche da tarde": (0.15, 0.14, 0.13, 0.16),
    "Jantar":          (0.25, 0.26, 0.27, 0.24),
}

# Estrutura da montagem automática por refeição: cada item é uma "função" da refeição
# com uma lista de alimentos candidatos. Escolhemos 1 de cada (rotação por aluno).
MONTAGEM_REFEICOES = {
    "Café da manhã": [
        ("proteína", ["Iogurte natural", "Iogurte grego", "Queijo cottage", "Ovo cozido"]),
        ("carboidrato", ["Aveia em flocos", "Granola", "Pão integral", "Tapioca"]),
        ("fruta", ["Banana", "Maçã", "Pera", "Mamão papaia", "Morango"]),
    ],
    "Lanche da manhã": [
        ("proteína", ["Queijo cottage", "Iogurte natural", "Ovo cozido", "Ricota"]),
        ("fruta", ["Maçã", "Banana", "Laranja", "Pera", "Morango"]),
        ("gordura", ["Castanha-do-pará", "Amêndoas", "Nozes", "Pasta de amendoim"]),
    ],
    "Almoço": [
        ("amido", ["Arroz branco cozido", "Arroz integral cozido", "Macarrão cozido", "Batata inglesa cozida"]),
        ("leguminosa", ["Feijão preto", "Feijão carioca", "Lentilha", "Grão-de-bico"]),
        ("proteína", ["Peito de frango grelhado", "Filé de tilápia", "Bife magro (alcatra)", "Carne moída magra", "Filé mignon", "Lagarto cozido"]),
        ("folha", ["Alface", "Rúcula", "Espinafre"]),
        ("legume", ["Tomate", "Cenoura", "Brócolis", "Abobrinha"]),
    ],
    "Lanche da tarde": [
        ("carboidrato", ["Pão integral", "Pão francês", "Tapioca", "Torrada integral"]),
        ("proteína", ["Queijo cottage", "Iogurte grego", "Ricota", "Peito de peru"]),
        ("fruta", ["Banana", "Maçã", "Pera", "Uva"]),
        ("gordura", ["Amêndoas", "Castanha-do-pará", "Pasta de amendoim"]),
    ],
    "Jantar": [
        ("amido", ["Batata-doce cozida", "Arroz branco cozido", "Batata inglesa cozida", "Mandioca cozida"]),
        ("proteína", ["Filé de tilápia", "Peito de frango grelhado", "Filé de merluza", "Salmão grelhado", "Ovo cozido"]),
        ("folha", ["Brócolis", "Espinafre", "Couve"]),
        ("legume", ["Cenoura", "Abobrinha", "Chuchu", "Vagem"]),
        ("gordura", ["Azeite de oliva"]),
    ],
}


def seed_alimentos():
    con = get_db()
    if con.execute("SELECT COUNT(*) AS n FROM alimentos").fetchone()["n"] > 0:
        return
    for nome, categoria, equiv in ALIMENTOS:
        k, p, c, g, porcao = NUTRI_ALIMENTOS.get(nome, (0, 0, 0, 0, 100))
        mn, ide, mx = PORCOES_POR_NOME.get(nome, PORCOES_POR_GRUPO.get(equiv, (porcao * 0.5, porcao, porcao * 1.6)))
        tipo_eq = _tipo_equivalencia_por_grupo(equiv)
        con.execute(
            "INSERT INTO alimentos (nome, categoria, grupo_equiv, kcal, proteinas, carbs, gorduras, porcao, "
            "porcao_min, porcao_max, porcao_padrao, refeicoes_permitidas, tipo_equivalencia) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (nome, categoria, equiv, k, p, c, g, porcao, mn, mx, ide, "", tipo_eq),
        )
    con.commit()


def _tipo_equivalencia_por_grupo(grupo):
    """Determina o tipo de equivalência baseado no grupo alimentar."""
    if grupo in ("amido", "pao", "cereal", "leguminosa"):
        return "carboidrato"
    if grupo in ("proteina", "laticinio"):
        return "proteina"
    if grupo == "gordura":
        return "gordura"
    if grupo in ("fruta", "doce"):
        return "carboidrato"
    if grupo in ("legume", "verdura_folha"):
        return "vegetal"
    return "outro"


def atualizar_nutri():
    """Preenche a nutrição dos alimentos já cadastrados (base por 100 g)."""
    con = get_db()
    for nome, (k, p, c, g, porcao) in NUTRI_ALIMENTOS.items():
        mn, ide, mx = PORCOES_POR_NOME.get(nome, PORCOES_POR_GRUPO.get(
            con.execute("SELECT grupo_equiv FROM alimentos WHERE nome = ?", (nome,)).fetchone()["grupo_equiv"] if con.execute("SELECT grupo_equiv FROM alimentos WHERE nome = ?", (nome,)).fetchone() else "amido",
            (porcao * 0.5, porcao, porcao * 1.6)
        ))
        grupo = con.execute("SELECT grupo_equiv FROM alimentos WHERE nome = ?", (nome,)).fetchone()
        grupo = grupo["grupo_equiv"] if grupo else "amido"
        tipo_eq = _tipo_equivalencia_por_grupo(grupo)
        con.execute(
            """UPDATE alimentos SET kcal = ?, proteinas = ?, carbs = ?, gorduras = ?, porcao = ?,
               porcao_min = ?, porcao_max = ?, porcao_padrao = ?, tipo_equivalencia = ?
               WHERE nome = ? AND (kcal IS NULL OR kcal = 0)""",
            (k, p, c, g, porcao, mn, mx, ide, tipo_eq, nome),
        )
    con.commit()


def montar_alimentos(con, refeicoes):
    ids = [r["id"] for r in refeicoes]
    mapa = {rid: [] for rid in ids}
    if not ids:
        return mapa
    ph = ",".join("?" * len(ids))
    rows = con.execute(
        f"""SELECT ra.refeicao_id AS rid, a.id AS aid, a.nome, a.categoria, a.grupo_equiv,
                 a.kcal, a.proteinas, a.carbs, a.gorduras, a.porcao, ra.qtd,
                 a.porcao_min, a.porcao_max, a.porcao_padrao, a.tipo_equivalencia
            FROM refeicao_alimentos ra
            JOIN alimentos a ON a.id = ra.alimento_id
            WHERE ra.refeicao_id IN ({ph})
            ORDER BY a.categoria, a.nome""",
        ids,
    ).fetchall()
    for r in rows:
        mapa[r["rid"]].append(r)
    for rid, itens in mapa.items():
        mapa[rid] = []
        for r in itens:
            # Calcula substituições com gramas
            subs_com_gramas = calcular_substituicoes(
                {
                    "nome": r["nome"],
                    "kcal": r["kcal"] or 0,
                    "proteinas": r["proteinas"] or 0,
                    "carbs": r["carbs"] or 0,
                    "gorduras": r["gorduras"] or 0,
                    "porcao_min": r["porcao_min"] or 0,
                    "porcao_max": r["porcao_max"] or 0,
                },
                r["qtd"] or 0,
                r["grupo_equiv"],
                con
            )
            mapa[rid].append({
                "nome": r["nome"],
                "categoria": r["categoria"],
                "qtd": r["qtd"] or 0,
                "kcal": r["kcal"] or 0,
                "proteinas": r["proteinas"] or 0,
                "carbs": r["carbs"] or 0,
                "gorduras": r["gorduras"] or 0,
                "porcao": r["porcao"] or 100,
                "subs": subs_com_gramas,
            })
    return mapa


_PROT_GRUPOS = ("proteina", "laticinio")
_CARB_GRUPOS = ("amido", "pao", "cereal", "fruta", "doce", "leguminosa")
_FAT_GRUPOS = ("gordura",)


def _faixa_porcao(x):
    """Faixa (mínimo, ideal, máximo) de um alimento.
    
    Prioridade:
    1. Valores do banco (porcao_min, porcao_max, porcao_padrao) se definidos
    2. Constantes do código (PORCOES_POR_NOME, PORCOES_POR_GRUPO) como fallback
    """
    # Se tem valores do banco, usa eles (permite edição via admin)
    porcao_min = x.get("porcao_min")
    porcao_max = x.get("porcao_max")
    porcao_padrao = x.get("porcao_padrao")
    
    if porcao_min is not None and porcao_max is not None and porcao_max > 0:
        mn = float(porcao_min)
        mx = float(porcao_max)
        ide = float(porcao_padrao) if porcao_padrao and porcao_padrao > 0 else (mn + mx) / 2
        return (mn, ide, mx)
    
    # Fallback para constantes do código
    nome = (x.get("nome") or "").strip()
    if nome in PORCOES_POR_NOME:
        return PORCOES_POR_NOME[nome]
    grup = x.get("grupo") or ""
    if grup in PORCOES_POR_GRUPO:
        return PORCOES_POR_GRUPO[grup]
    base = float(x.get("porcao") or 100)
    return (base * 0.5, float(base), base * 1.6)


def _totais_item(it):
    k = p = c = g = 0.0
    for x in it:
        w = float(x["qtd"]) / 100.0
        k += (x["k"] or 0) * w
        p += (x["p"] or 0) * w
        c += (x["c"] or 0) * w
        g += (x["g"] or 0) * w
    return k, p, c, g


def calcular_gramas(itens, kcal_t=0, p_t=0, c_t=0, g_t=0):
    """Calcula as gramas respeitando faixas realistas de porção.

    itens: lista de dicts com k, p, c, g (por 100 g), porcao, grupo e nome.
    Hierarquia: porções sempre dentro de [mínimo, máximo] > estrutura da
    refeição > kcal > proteína > carboidratos/gorduras. As metas são
    aproximadas dentro das tolerâncias configuradas — nunca se infla a
    quantidade de um alimento além do máximo para "bater" o número.
    Determinístico (mesma entrada gera sempre a mesma saída).
    """
    PROTEICOS = ("proteina", "laticinio")
    CARBUOS = ("amido", "pao", "cereal", "fruta", "doce", "leguminosa")

    it = [dict(x) for x in itens]
    for x in it:
        x["qtd"] = float(x.get("porcao") or 100)

    def nutri(lista):
        return _totais_item(lista)

    def fixar(livres):
        for x in livres:
            x["qtd"] = x["_ideal"]

    for x in it:
        mn, ide, mx = _faixa_porcao(x)
        x["_min"], x["_ideal"], x["_max"] = mn, ide, mx

    # Fase A - base: folhas/legumes na porção ideal; proteína/carboidrato no mínimo
    for x in it:
        if x["grupo"] in ("legume", "verdura_folha"):
            x["qtd"] = x["_ideal"]
        elif x["grupo"] in ("gordura", "doce"):
            x["qtd"] = x["_ideal"]
        else:
            x["qtd"] = x["_min"]

    def escalar(lista, attr, alvo, fixos):
        """Distribui alvo entre os alimentos de 'lista' dentro de [min, max]."""
        base = sum(((x[attr] or 0) / 100.0) * x["_min"] for x in lista)
        topo = sum(((x[attr] or 0) / 100.0) * x["_max"] for x in lista)
        ja = sum(((x[attr] or 0) / 100.0) * x["qtd"] for x in fixos)
        if topo <= base + 1e-9:
            return
        t = (max(float(alvo or 0) - ja - base, 0.0)) / max(topo - base, 1e-9)
        t = max(0.0, min(1.0, t))
        for x in lista:
            x["qtd"] = x["_min"] + (x["_max"] - x["_min"]) * t

    prot = [x for x in it if x["grupo"] in PROTEICOS]
    carb = [x for x in it if x["grupo"] in CARBUOS]
    fixos_p = [x for x in it if x not in prot]
    fixos_c = [x for x in it if x not in carb]
    if prot:
        escalar(prot, "p", p_t, fixos_p)
    if carb:
        escalar(carb, "c", c_t, fixos_c)

    # Fase A.2 - reequilíbrio: aproxima P e C das metas (dentro da tolerância),
    # corrigindo o acúmulo de macro vindo de feijão/oleaginosas/legumes.
    def reequilibrar(lista, attr, alvo, tol, fixos):
        for _ in range(4):
            atual = sum(((x[attr] or 0) / 100.0) * x["qtd"] for x in lista)
            fixo = sum(((x[attr] or 0) / 100.0) * x["qtd"] for x in fixos)
            err = float(alvo or 0) - (atual + fixo)
            if abs(err) <= tol:
                return
            alvo_lista = max(float(alvo or 0) - fixo, 0.0)
            if atual <= 1e-9:
                return
            mult = alvo_lista / atual
            novo_topo = sum(((x[attr] or 0) / 100.0) * x["_max"] for x in lista)
            mult = min(mult, novo_topo / max(atual, 1e-9))
            for x in lista:
                x["qtd"] = max(float(x["_min"]), min(float(x["_max"]),
                                                     float(x["qtd"]) * mult))

    reequilibrar(prot, "p", p_t, TOLERANCIAS_DIETA["proteina"], fixos_p)
    reequilibrar(carb, "c", c_t, TOLERANCIAS_DIETA["carbo"], fixos_c)

    # Fase B - fecha as kcal ajustando dentro dos limites, sem nunca sair das faixas
    def ajustar_kcal():
        k, p, c, g = nutri(it)
        tol = max(TOLERANCIAS_DIETA["kcal_pct"] * (kcal_t or 0) / 100.0, 25.0)
        diff = float(kcal_t or 0) - k
        for _ in range(10):
            if abs(diff) <= tol or not it:
                break
            # sabores de redução (quem sai antes quando sobrou kcal)
            reduzir_ordem = ("doce", "fruta", "gordura", "cereal", "pao",
                             "leguminosa", "amido", "laticinio", "proteina")
            if diff > 0:
                mex = [x for x in it if (x["k"] or 0) > 0 and x["qtd"] < x["_max"] - 0.5]
                if not mex:
                    break
                mex.sort(key=lambda x: (x["qtd"] - x["_min"]) /
                         (x["_max"] - x["_min"]), reverse=True)
            else:
                mex = [x for x in it if (x["k"] or 0) > 0 and x["qtd"] > x["_min"] + 0.5]
                if not mex:
                    break
                mex.sort(key=lambda x: (reduzir_ordem.index(x["grupo"])
                                        if x["grupo"] in reduzir_ordem else 99,
                                        x["qtd"]))
            x = mex[0]
            kp = max((x["k"] or 0) / 100.0, 1e-9)
            delta = diff / kp
            mx = x["_max"] - x["qtd"] if diff > 0 else x["qtd"] - x["_min"]
            delta = max(-mx, min(mx, delta))
            if abs(delta) < 1.0:
                break
            x["qtd"] += delta
            k, p, c, g = nutri(it)
            diff = float(kcal_t or 0) - k
        return k, p, c, g

    k, p, c, g = ajustar_kcal()

    for x in it:
        x["qtd"] = max(float(x["_min"]), min(float(x["_max"]), float(x["qtd"])))
        x.pop("_min", None)
        x.pop("_ideal", None)
        x.pop("_max", None)
    return it


def _resolver_qtds(con, itens, kcal_t, p_t, c_t, g_t):
    """Aplica calcular_gramas e formata pares (alimento_id, gramas) redondos."""
    base = []
    for it in itens:
        base.append({
            "aid": it["id"], "nome": it["nome"], "grupo": it["grupo_equiv"],
            "k": it["kcal"] or 0, "p": it["proteinas"] or 0,
            "c": it["carbs"] or 0, "g": it["gorduras"] or 0,
            "porcao": it["porcao"] or 100,
        })
    res = calcular_gramas(base, kcal_t=kcal_t, p_t=p_t, c_t=c_t, g_t=g_t)
    return [(int(x["aid"]), max(0, int(round(x["qtd"])))) for x in res]


def calcular_substituicoes(alimento_base, quantidade_base, grupo_equiv, con=None):
    """Calcula substituições com quantidades em gramas para um alimento.
    
    Args:
        alimento_base: dict com dados do alimento original (nome, kcal, proteinas, carbs, gorduras, porcao_min, porcao_max)
        quantidade_base: quantidade em gramas do alimento original
        grupo_equiv: grupo de equivalência para buscar substitutos
        con: conexão com o banco (opcional)
    
    Returns:
        lista de dicts com substituições calculadas:
        [{"alimento": str, "quantidade_g": float, "kcal": float, "proteinas": float, "carbs": float, "gorduras": float}, ...]
    """
    if con is None:
        con = get_db()
    
    # Busca alimentos do mesmo grupo de equivalência
    candidatos = con.execute(
        """SELECT * FROM alimentos 
           WHERE grupo_equiv = ? AND nome != ?
           ORDER BY nome""",
        (grupo_equiv, alimento_base.get("nome", ""))
    ).fetchall()
    
    if not candidatos:
        return []
    
    return calcular_substituicoes_por_macro(
        alimento_base,
        quantidade_base,
        grupo_equiv,
        [dict(candidato) for candidato in candidatos],
    )


def migrar():
    con = get_db()
    cols = [r["name"] for r in con.execute("PRAGMA table_info(alunos)").fetchall()]
    novas = {
        "altura_cm": "REAL",
        "peso_atual": "REAL",
        "fator_atividade": "REAL DEFAULT 1.55",
        "objetivo_meta": "TEXT DEFAULT 'emagrecer'",
        "ajuste_meta": "REAL DEFAULT -10",
        "proteina_kg": "REAL DEFAULT 2.0",
        "sexo_formula": "TEXT DEFAULT 'M'",
        "dias_treino": "INTEGER DEFAULT 3",
        "foco_gluteo": "INTEGER DEFAULT 0",
        "rotina": "TEXT",
    }
    for col, tipo in novas.items():
        if col not in cols:
            con.execute(f"ALTER TABLE alunos ADD COLUMN {col} {tipo}")
    cols_a = [r["name"] for r in con.execute("PRAGMA table_info(alimentos)").fetchall()]
    novas_a = {
        "kcal": "REAL DEFAULT 0",
        "proteinas": "REAL DEFAULT 0",
        "carbs": "REAL DEFAULT 0",
        "gorduras": "REAL DEFAULT 0",
        "porcao": "REAL DEFAULT 100",
        "porcao_min": "REAL DEFAULT 0",
        "porcao_max": "REAL DEFAULT 0",
        "porcao_padrao": "REAL DEFAULT 0",
        "refeicoes_permitidas": "TEXT DEFAULT ''",
        "tipo_equivalencia": "TEXT DEFAULT ''",
        "fonte": "TEXT DEFAULT 'manual'",
        "codigo_fonte": "TEXT DEFAULT ''",
        "marca": "TEXT DEFAULT ''",
        "nome_normalizado": "TEXT DEFAULT ''",
        "unidade_base": "TEXT DEFAULT 'g'",
        "ativo": "INTEGER DEFAULT 1",
        "qualidade_dados": "TEXT DEFAULT 'media'",
        "origem_confiavel": "INTEGER DEFAULT 0",
        "data_importacao": "TEXT DEFAULT ''",
        "data_atualizacao": "TEXT DEFAULT ''",
    }
    for col, tipo in novas_a.items():
        if col not in cols_a:
            con.execute(f"ALTER TABLE alimentos ADD COLUMN {col} {tipo}")
    cols_ra = [r["name"] for r in con.execute("PRAGMA table_info(refeicao_alimentos)").fetchall()]
    if "qtd" not in cols_ra:
        con.execute("ALTER TABLE refeicao_alimentos ADD COLUMN qtd REAL DEFAULT 0")
    cols_ep = [r["name"] for r in con.execute("PRAGMA table_info(exercicios_padrao)").fetchall()]
    novas_ep = {
        "secundarios": "TEXT",
        "padrao": "TEXT",
        "equipamento": "TEXT",
        "nivel": "TEXT",
        "rir": "TEXT",
        "observacoes": "TEXT",
        "ativo": "INTEGER DEFAULT 1",
    }
    for col, tipo in novas_ep.items():
        if col not in cols_ep:
            con.execute(f"ALTER TABLE exercicios_padrao ADD COLUMN {col} {tipo}")
    cols_ex = [r["name"] for r in con.execute("PRAGMA table_info(exercicios)").fetchall()]
    novas_ex = {
        "rir": "TEXT",
        "observacoes": "TEXT",
        "metodo_progressao": "TEXT",
    }
    for col, tipo in novas_ex.items():
        if col not in cols_ex:
            con.execute(f"ALTER TABLE exercicios ADD COLUMN {col} {tipo}")
    con.commit()


def seed_library():
    con = get_db()
    if con.execute("SELECT COUNT(*) AS n FROM exercicios_padrao").fetchone()["n"] > 0:
        return
    for nome, grupo, grande, series, rep, desc in LIBRARY:
        con.execute(
            "INSERT INTO exercicios_padrao (nome, grupo, grande, series, repeticoes, descanso) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (nome, grupo, grande, series, rep, desc),
        )
    con.commit()


def seed_library_v2():
    """Enriquece a biblioteca com os campos novos (movimento, equipamento,
    nível, RIR, observações) e adiciona exercícios extras. Idempotente."""
    con = get_db()
    cols = [r["name"] for r in con.execute("PRAGMA table_info(exercicios_padrao)").fetchall()]
    if "padrao" not in cols:
        return
    for nome, d in DETALHES_EXERCICIOS.items():
        existe = con.execute(
            "SELECT COUNT(*) AS n FROM exercicios_padrao WHERE nome = ?", (nome,)
        ).fetchone()["n"]
        if existe:
            con.execute(
                """UPDATE exercicios_padrao
                   SET grupo = ?, grande = ?, series = ?, repeticoes = ?, descanso = ?,
                       secundarios = ?, padrao = ?, equipamento = ?, nivel = ?, rir = ?,
                       observacoes = ?, ativo = 1
                   WHERE nome = ?""",
                (d["grupo"], 1 if d["grande"] else 0, d["series"], d["repeticoes"], d["descanso"],
                 d["secundarios"], d["padrao"], d["equipamento"], d["nivel"], d["rir"],
                 d["observacoes"], nome),
            )
        else:
            con.execute(
                """INSERT INTO exercicios_padrao
                   (nome, grupo, grande, series, repeticoes, descanso, secundarios, padrao,
                    equipamento, nivel, rir, observacoes, ativo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (nome, d["grupo"], 1 if d["grande"] else 0, d["series"], d["repeticoes"],
                 d["descanso"], d["secundarios"], d["padrao"], d["equipamento"], d["nivel"],
                 d["rir"], d["observacoes"]),
            )
    # Backfill: enriquece qualquer exercício que ainda não tenha os campos novos
    # (cobre exercícios antigos da biblioteca e os criados pelo próprio treinador).
    PADRAO_POR_GRUPO = {
        "Peito": "Empurrar horizontal", "Costas": "Puxar vertical", "Ombro": "Empurrar vertical",
        "Bíceps": "Flexão de cotovelo", "Tríceps": "Extensão de cotovelo",
        "Quadríceps": "Agachar", "Posterior": "Articulação de quadril",
        "Glúteo": "Extensão de quadril", "Abdômen": "Flexão de coluna (core)",
        "Panturrilha": "Panturrilha", "Trapézio": "Encolhimento", "Core": "Isométrico",
    }
    EQUIP_POR_PADRAO = {
        "Agachar": "Barra", "Articulação de quadril": "Barra", "Afundo": "Halteres",
        "Isométrico": "Peso corporal", "Flexão de coluna (core)": "Peso corporal",
        "Extensão de joelhos": "Máquina", "Flexão de joelhos": "Máquina",
        "Extensão de quadril": "Máquina", "Abdução de quadril": "Máquina",
        "Adução de quadril": "Máquina",
    }
    SECUND_POR_GRUPO = {
        "Peito": "Tríceps, Deltoide anterior", "Costas": "Bíceps, Posterior",
        "Ombro": "Tríceps, Trapézio", "Quadríceps": "Glúteo",
        "Posterior": "Glúteo, Quadríceps", "Glúteo": "Posterior", "Bíceps": "Antebraço",
        "Tríceps": "Peito, Deltoide posterior",
    }
    por_preencher = con.execute(
        """SELECT id, nome, grupo, grande FROM exercicios_padrao
           WHERE padrao IS NULL OR nivel IS NULL OR rir IS NULL OR equipamento IS NULL"""
    ).fetchall()
    for e in por_preencher:
        padrao = PADRAO_POR_GRUPO.get((e["grupo"] or "").strip().title(), "Outro")
        con.execute(
            """UPDATE exercicios_padrao
               SET padrao = ?, nivel = ?, rir = ?, equipamento = ?,
                   secundarios = COALESCE(NULLIF(secundarios, ''), ?),
                   observacoes = COALESCE(observacoes, ''),
                   ativo = 1,
                   grande = CASE WHEN grande IS NULL THEN ? ELSE grande END
               WHERE id = ?""",
            (padrao, "Intermediário", "0-2" if e["grande"] else "2-3",
             EQUIP_POR_PADRAO.get(padrao, "Barra"), SECUND_POR_GRUPO.get((e["grupo"] or "").strip().title(), ""),
             1 if e["grande"] else 0, e["id"]),
        )
    con.commit()


def calcular_plano(a):
    sexo = (a["sexo_formula"] or "M").upper()
    peso = a["peso_atual"] or 70
    altura = a["altura_cm"] or 175
    idd = idade(a["nascimento"]) or 30
    if sexo == "F":
        tmb = 447.593 + (9.247 * peso) + (3.098 * altura) - (4.330 * idd)
    else:
        tmb = 88.362 + (13.397 * peso) + (4.799 * altura) - (5.677 * idd)
    fator = a["fator_atividade"] or 1.55
    tdee = tmb * fator
    obj = a["objetivo_meta"] or "emagrecer"
    ajuste = a["ajuste_meta"]
    if not ajuste:
        ajuste = {"emagrecer": -10, "manter": 0, "ganhar": 10}.get(obj, 0)
    meta = tdee * (1 + ajuste / 100)
    proteina = (a["proteina_kg"] or 2.0) * peso
    gordura = meta * 0.25 / 9
    carbo = (meta - proteina * 4 - gordura * 9) / 4
    return {
        "sexo": "Masculina" if sexo == "M" else "Feminina",
        "peso": peso, "altura": altura, "idade": idd,
        "tmb": tmb, "tdee": tdee, "meta_kcal": meta,
        "proteina": proteina, "gordura": gordura, "carbo": carbo,
        "objetivo": obj, "ajuste": ajuste, "fator": fator,
    }


def montar_template(aluno):
    dias = max(1, min(6, intnum(aluno["dias_treino"], 3) or 3))
    g = GRUPOS
    if dias <= 3:
        template = [(f"Full Body {chr(65 + i)}", g["fullbody"][i]) for i in range(dias)]
    elif dias == 4:
        template = [
            ("Upper A", g["upper"][0]), ("Lower A", g["lower"][0]),
            ("Upper B", g["upper"][1]), ("Lower B", g["lower"][1]),
        ]
    elif dias == 5:
        template = [
            ("Push A", g["push"][0]), ("Pull A", g["pull"][0]), ("Legs A", g["legs"][0]),
            ("Upper A", g["upper"][0]), ("Lower A", g["lower"][0]),
        ]
    else:
        template = [
            ("Push A", g["push"][0]), ("Pull A", g["pull"][0]), ("Legs A", g["legs"][0]),
            ("Push B", g["push"][1]), ("Pull B", g["pull"][1]), ("Legs B", g["legs"][1]),
        ]
    if aluno["foco_gluteo"]:
        template = [(nome, grupos + ["Glúteo"]) for nome, grupos in template]
    return template


def selecionar_exercicios(con, template):
    exs = con.execute("SELECT * FROM exercicios_padrao ORDER BY id").fetchall()
    por_grupo = {}
    for e in exs:
        por_grupo.setdefault(e["grupo"], []).append(e)
    treinos = []
    for idx, (nome, grupos) in enumerate(template):
        usados = set()
        itens = []
        for g in grupos:
            if len(itens) >= 6:
                break
            pool = [e for e in por_grupo.get(g, []) if e["id"] not in usados]
            if not pool:
                continue
            e = pool[idx % len(pool)]
            usados.add(e["id"])
            itens.append(e)
        treinos.append({"nome": nome, "itens": itens})
    return treinos


def buscar_exercicios(con, q="", limite=25):
    q = (q or "").strip().lower()
    rows = con.execute(
        "SELECT * FROM exercicios_padrao WHERE ativo = 1 ORDER BY grupo, nome"
    ).fetchall()
    if not q:
        return rows[:limite]
    termos = [t for t in re.split(r"[^a-zà-ú0-9]+", q) if len(t) >= 2]
    res = []
    for e in rows:
        bloco = " ".join([
            (e["nome"] or ""), (e["grupo"] or ""), (e["padrao"] or ""),
            (e["secundarios"] or ""), (e["equipamento"] or ""),
        ]).lower()
        if termos and all(t in bloco for t in termos) or all(t in (e["nome"] or "").lower() for t in termos):
            res.append(e)
        elif not termos and q in (e["nome"] or "").lower():
            res.append(e)
    res.sort(key=lambda e: (0 if (e["nome"] or "").lower().startswith(q) else 1, e["nome"] or ""))
    return res[:limite]


def _escolher_da_lista(cands, rot, usados):
    candidatos = [c for c in cands if c["id"] not in usados]
    if not candidatos:
        return None
    return candidatos[rot % len(candidatos)]


def montar_sugestao(con, objetivo, divisao, nivel, duracao, prioridades, restricoes, equipamentos, rot=0):
    """Monta uma sugestão de treino determinística (assistente, não autoridade).
    Devolve {'itens': [...], 'avisos': [...]}; nada é gravado aqui."""
    avisos = []
    modelo = MODELOS_TREINO.get(divisao) or MODELOS_TREINO["fullbody"]
    grupos = modelo["grupos"]
    prior = [p for p in (prioridades or []) if p in GRUPOS_LIB]
    n_alvo = {"30": 5, "45": 6, "60": 8, "75": 9, "90": 10}.get(str(duracao), 8)

    exs = con.execute("SELECT * FROM exercicios_padrao WHERE ativo = 1").fetchall()
    if not exs:
        return {"itens": [], "avisos": ["Biblioteca de exercícios vazia. Cadastre exercícios primeiro."]}

    termos = []
    if restricoes:
        termos = [t for t in re.split(r"[^a-zà-ú0-9]+", (restricoes or "").lower()) if len(t) >= 2]
        avisos.append("Restrições: " + restricoes.strip() + ". Exercícios relacionados foram evitados.")
    nivel_ordem = {"Iniciante": 0, "Intermediário": 1, "Avançado": 2}
    max_nivel = nivel_ordem.get(nivel, 2)

    def elegivel(e):
        nome_l = (e["nome"] or "").lower()
        if termos:
            for t in termos:
                if t in nome_l or t in (e["observacoes"] or "").lower() or t in (e["padrao"] or "").lower():
                    return False
        if equipamentos and e["equipamento"] and e["equipamento"] not in equipamentos:
            return False
        if e["nivel"] and nivel_ordem.get(e["nivel"], 2) > max_nivel:
            return False
        return True

    pool = [e for e in exs if elegivel(e)]
    if not pool:
        return {"itens": [], "avisos": [
            "Nenhum exercício disponível com os equipamentos, restrições ou nível escolhidos. Amplie os filtros.",
        ]}

    usados = set()
    sequencia = []

    def adicionar(e, tipo):
        if e is None or e["id"] in usados:
            return
        usados.add(e["id"])
        sequencia.append((tipo, e))

    for g in prior:
        cands = [e for e in pool if e["grupo"] == g]
        adicionar(_escolher_da_lista(cands, rot, usados), "prioridade")
    for g in grupos:
        cands = [e for e in pool if e["grupo"] == g and e["grande"]]
        adicionar(_escolher_da_lista(cands, rot, usados), "composto")
    rodada = 0
    while len(sequencia) < n_alvo:
        parou = True
        for g in grupos:
            if len(sequencia) >= n_alvo:
                break
            cands = [e for e in pool if e["grupo"] == g and not e["grande"]]
            e = _escolher_da_lista(cands, rot + rodada, usados)
            if e is not None:
                adicionar(e, "isolado")
                parou = False
        if parou:
            break
        rodada += 1
    if len(sequencia) < n_alvo and len(pool) > len(sequencia):
        for e in pool:
            if len(sequencia) >= n_alvo:
                break
            adicionar(e, "composto")

    if not sequencia:
        avisos.append("Não foi possível montar a sugestão com os filtros atuais.")
        return {"itens": [], "avisos": avisos}

    meta = META_OBJETIVO.get(objetivo, META_OBJETIVO["Outro"])
    itens = []
    for tipo, e in sequencia[:n_alvo]:
        series = meta["series"] if meta["series"] else (e["series"] or 3)
        repeticoes = meta["repeticoes"] if meta["repeticoes"] else (e["repeticoes"] or "10-12")
        rir = meta["rir"] if meta["rir"] else (e["rir"] or "1-2")
        descanso = meta["descanso"] if meta["descanso"] else (e["descanso"] or "90s")
        itens.append({
            "ex_id": e["id"],
            "nome": e["nome"],
            "grupo": e["grupo"],
            "padrao": e["padrao"] or "",
            "series": series,
            "repeticoes": repeticoes,
            "rir": rir,
            "descanso": descanso,
            "carga": "",
            "equipamento": e["equipamento"] or "",
            "nivel": e["nivel"] or "",
            "grande": e["grande"],
            "secundarios": e["secundarios"] or "",
            "observacoes": e["observacoes"] or "",
        })
    if len(sequencia) == len(pool) and len(itens) < n_alvo:
        avisos.append(f"A biblioteca filtrada tem {len(itens)} exercícios; a sugestão ficou menor que a duração estimada.")
    if objetivo == "Força" and nivel == "Iniciante":
        avisos.append("Meta de força com aluno iniciante: considere validar a técnica antes de cargas altas.")
    return {"itens": itens, "avisos": avisos}


def duplicar_treino_db(con, treino_id, novo_nome=None):
    t = con.execute("SELECT * FROM treinos WHERE id = ?", (treino_id,)).fetchone()
    if not t:
        return None
    nome = (novo_nome or "").strip() or (t["nome"] and f"{t['nome']} (cópia)" or "Cópia")
    cur = con.execute(
        "INSERT INTO treinos (aluno_id, nome, dia_semana, notas, ordem) VALUES (?, ?, ?, ?, ?)",
        (t["aluno_id"], nome, t["dia_semana"], t["notas"],
         (t["ordem"] or 0) + 1),
    )
    novo_id = cur.lastrowid
    for e in con.execute(
        "SELECT * FROM exercicios WHERE treino_id = ? ORDER BY ordem, id", (treino_id,)
    ).fetchall():
        con.execute(
            """INSERT INTO exercicios (treino_id, nome, series, repeticoes, carga, descanso, grupo, ordem, rir, observacoes, metodo_progressao)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (novo_id, e["nome"], e["series"], e["repeticoes"], e["carga"], e["descanso"], e["grupo"],
             e["ordem"], e["rir"], e["observacoes"], e["metodo_progressao"]),
        )
    return novo_id


def _txt(v):
    return str(v).strip() if v is not None else ""


def gravar_sugestao(con, aluno_id, nome, dia_semana, notas, itens):
    cur = con.execute(
        "INSERT INTO treinos (aluno_id, nome, dia_semana, notas, ordem) VALUES (?, ?, ?, ?, ?)",
        (aluno_id, (nome or "").strip() or "Treino montado", (dia_semana or "").strip(),
         (notas or "").strip(), 0),
    )
    treino_id = cur.lastrowid
    for i, x in enumerate(itens, start=1):
        ex_id = x.get("ex_id")
        if ex_id:
            e = con.execute("SELECT * FROM exercicios_padrao WHERE id = ?", (ex_id,)).fetchone()
            if e:
                con.execute(
                    """INSERT INTO exercicios (treino_id, nome, series, repeticoes, carga, descanso, grupo, ordem, rir, observacoes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (treino_id, _txt(x.get("nome")) or e["nome"],
                     _txt(x.get("series")), _txt(x.get("repeticoes")),
                     _txt(x.get("carga")), _txt(x.get("descanso")),
                     _txt(x.get("grupo")) or e["grupo"], i,
                     _txt(x.get("rir")), _txt(x.get("observacoes"))),
                )
                continue
        con.execute(
            """INSERT INTO exercicios (treino_id, nome, series, repeticoes, carga, descanso, grupo, ordem, rir, observacoes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (treino_id, _txt(x.get("nome")) or "Exercício", _txt(x.get("series")),
             _txt(x.get("repeticoes")), _txt(x.get("carga")), _txt(x.get("descanso")),
             _txt(x.get("grupo")), i, _txt(x.get("rir")), _txt(x.get("observacoes"))),
        )
    return treino_id


def get_aluno_or_404(aluno_id):
    con = get_db()
    a = con.execute("SELECT * FROM alunos WHERE id = ?", (aluno_id,)).fetchone()
    if a is None:
        abort(404)
    return a


@app.context_processor
def inject_helpers():
    return dict(
        mes_label=mes_label,
        mes_atual=mes_atual,
        brl=brl,
        formatar_data=formatar_data,
        iniciais=iniciais,
        idade=idade,
        OBJETIVOS_META=OBJETIVOS_META,
        GRUPOS_LIB=GRUPOS_LIB,
        EQUIV_LABELS=EQUIV_LABELS,
        CATEGORIAS=CATEGORIAS,
        STATUS_LEADS=STATUS_LEADS,
        LEAD_ORIGENS=LEAD_ORIGENS,
        DESPESA_CATEGORIAS=DESPESA_CATEGORIAS,
        MEDIDAS=MEDIDAS,
        MEDIDAS_GRAFICO=MEDIDAS_GRAFICO,
        MODELOS_TREINO=MODELOS_TREINO,
        NIVEIS_TREINO=NIVEIS_TREINO,
        DURACOES_TREINO=DURACOES_TREINO,
        EQUIPAMENTOS_LISTA=EQUIPAMENTOS_LISTA,
        OBJETIVOS_TREINO=OBJETIVOS_TREINO,
        PADROES_MOVIMENTO=PADROES_MOVIMENTO,
        hoje=datetime.date.today().isoformat(),
    )


def seed():
    con = get_db()
    if con.execute("SELECT COUNT(*) AS n FROM alunos").fetchone()["n"] > 0:
        return
    cur = con.execute(
        """INSERT INTO alunos
           (nome, telefone, objetivo, nascimento, plano, mensalidade, dia_vencimento, observacoes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "Exemplo (pode excluir)",
            "(11) 90000-0000",
            "Hipertrofia e bem-estar",
            "2000-05-10",
            "Consultoria completa",
            120,
            5,
            "Este é um aluno de demonstração. Explore os treinos e depois exclua.",
        ),
    )
    aluno_id = cur.lastrowid

    con.execute(
        "INSERT INTO metas_dieta (aluno_id, kcal_diaria, proteinas, carbs, gorduras, observacoes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (aluno_id, 2500, 150, 250, 80, "Meta diária de exemplo."),
    )
    con.execute(
        "INSERT INTO refeicoes (aluno_id, nome, horario, calorias, proteinas, carbs, gorduras, descricao, ordem) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (aluno_id, "Café da manhã", "07:00", 500, 30, 60, 12, "Pão integral + ovos + fruta", 1),
    )
    con.execute(
        "INSERT INTO refeicoes (aluno_id, nome, horario, calorias, proteinas, carbs, gorduras, descricao, ordem) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (aluno_id, "Almoço", "12:30", 700, 45, 70, 22, "Arroz + feijão + frango + salada", 2),
    )
    con.execute(
        "INSERT INTO refeicoes (aluno_id, nome, horario, calorias, proteinas, carbs, gorduras, descricao, ordem) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (aluno_id, "Jantar", "20:00", 600, 40, 80, 18, "Batata doce + peixe ou carne magra", 3),
    )

    t_a = con.execute(
        "INSERT INTO treinos (aluno_id, nome, dia_semana, notas, ordem) VALUES (?, ?, ?, ?, ?)",
        (aluno_id, "Treino A", "Segunda e Quinta", "Peito e tríceps", 1),
    ).lastrowid
    t_b = con.execute(
        "INSERT INTO treinos (aluno_id, nome, dia_semana, notas, ordem) VALUES (?, ?, ?, ?, ?)",
        (aluno_id, "Treino B", "Terça e Sexta", "Costas e bíceps", 2),
    ).lastrowid
    t_c = con.execute(
        "INSERT INTO treinos (aluno_id, nome, dia_semana, notas, ordem) VALUES (?, ?, ?, ?, ?)",
        (aluno_id, "Treino C", "Quarta e Sábado", "Pernas e ombros", 3),
    ).lastrowid

    ex = [
        (t_a, "Supino reto", "4", "8-12", "20 kg", "60s", "Peito"),
        (t_a, "Supino inclinado com halteres", "3", "10", "12 kg", "60s", "Peito"),
        (t_a, "Crucifixo", "3", "12", "10 kg", "45s", "Peito"),
        (t_a, "Tríceps corda", "3", "12-15", "22,5 kg", "45s", "Tríceps"),
        (t_b, "Puxada frente", "4", "10", "35 kg", "60s", "Costas"),
        (t_b, "Remada curvada", "3", "10", "20 kg", "60s", "Costas"),
        (t_b, "Rosca direta", "3", "12", "9 kg", "45s", "Bíceps"),
        (t_c, "Agachamento livre", "4", "8-10", "40 kg", "90s", "Perna"),
        (t_c, "Leg press", "3", "12", "100 kg", "60s", "Perna"),
        (t_c, "Desenvolvimento", "3", "10", "9 kg", "60s", "Ombro"),
        (t_c, "Panturrilha", "4", "15", "30 kg", "30s", "Perna"),
    ]
    for treino_id, nome, series, reps, carga, desc, grupo in ex:
        con.execute(
            "INSERT INTO exercicios (treino_id, nome, series, repeticoes, carga, descanso, grupo) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (treino_id, nome, series, reps, carga, desc, grupo),
        )

    con.execute(
        "INSERT INTO checkins (aluno_id, data, peso, dores, energia, sono, kcal_consumidas, adesao, observacoes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (aluno_id, "2026-09-05", 72.5, "Nenhuma", 4, "Dormiu bem", 2350, 85, "Semana tranquila."),
    )
    con.execute(
        "INSERT INTO checkins (aluno_id, data, peso, dores, energia, sono, kcal_consumidas, adesao, observacoes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (aluno_id, "2026-09-12", 72.1, "Dor leve no ombro", 3, "Acordou cansado", 2600, 90, "Ajustar carga do supino."),
    )
    con.commit()


with app.app_context():
    db_antes = DB_PATH.exists()
    init_db()
    migrar()
    seed_library()
    seed_library_v2()
    seed_alimentos()
    atualizar_nutri()
    seed()
    n_alunos = get_db().execute("SELECT COUNT(*) AS n FROM alunos").fetchone()["n"]
    print(f"[boot] DATA_DIR={DATA_DIR.resolve()} banco_ja_existia={db_antes} alunos={n_alunos}", flush=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.before_request
def exigir_login():
    if request.endpoint == "static" or request.endpoint in ("login", "logout"):
        return
    if not session.get("logado"):
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("usuario", "").strip()
        s = request.form.get("senha", "")
        if u == LOGIN_USUARIO and s == LOGIN_SENHA:
            session.clear()
            session["logado"] = True
            session["usuario"] = u
            flash("Bem-vindo!", "success")
            return redirect(url_for("dashboard"))
        flash("Usuário ou senha inválidos.", "danger")
        return redirect(url_for("login"))
    senha_padrao = os.environ.get("LOGIN_SENHA") in (None, "")
    return render_template("login.html", senha_padrao=senha_padrao)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def dashboard():
    con = get_db()
    mes = mes_atual()
    alunos_ativos = con.execute(
        "SELECT * FROM alunos WHERE ativo = 1 ORDER BY nome"
    ).fetchall()
    total_alunos = len(alunos_ativos)
    receita_esperada = con.execute(
        "SELECT COALESCE(SUM(mensalidade), 0) AS s FROM alunos WHERE ativo = 1"
    ).fetchone()["s"]
    receita_recebida = con.execute(
        "SELECT COALESCE(SUM(valor), 0) AS s FROM pagamentos WHERE mes = ? AND status = 'pago'",
        (mes,),
    ).fetchone()["s"]

    hoje = datetime.date.today().day
    atrasados = []
    for a in alunos_ativos:
        p = con.execute(
            "SELECT status FROM pagamentos WHERE aluno_id = ? AND mes = ?",
            (a["id"], mes),
        ).fetchone()
        pago = p is not None and p["status"] == "pago"
        if not pago and hoje > a["dia_vencimento"]:
            atrasados.append(a)

    checkins = con.execute(
        """SELECT c.*, a.nome AS aluno_nome
           FROM checkins c JOIN alunos a ON a.id = c.aluno_id
           ORDER BY c.data DESC, c.id DESC LIMIT 6"""
    ).fetchall()
    return render_template(
        "dashboard.html",
        active="inicio",
        mes_nome=mes_label(mes),
        total_alunos=total_alunos,
        receita_esperada=receita_esperada,
        receita_recebida=receita_recebida,
        atrasados=atrasados,
        checkins=checkins,
    )


@app.route("/alunos")
def alunos():
    con = get_db()
    mes = mes_atual()
    lista = con.execute(
        "SELECT * FROM alunos WHERE ativo = 1 ORDER BY nome"
    ).fetchall()
    hoje = datetime.date.today().day
    rows = []
    for a in lista:
        p = con.execute(
            "SELECT * FROM pagamentos WHERE aluno_id = ? AND mes = ?",
            (a["id"], mes),
        ).fetchone()
        status = p["status"] if p else "pendente"
        if status == "pendente" and hoje > a["dia_vencimento"]:
            status = "atrasado"
        rows.append({"aluno": a, "status": status})
    return render_template("alunos.html", active="alunos", rows=rows)


@app.route("/alunos/novo", methods=["POST"])
def novo_aluno():
    nome = request.form.get("nome", "").strip()
    if not nome:
        return redirect(url_for("alunos"))
    con = get_db()
    cur = con.execute(
        """INSERT INTO alunos
           (nome, telefone, objetivo, nascimento, observacoes,
            altura_cm, peso_atual, fator_atividade, objetivo_meta, ajuste_meta,
            proteina_kg, sexo_formula, dias_treino, foco_gluteo, rotina)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            nome,
            request.form.get("telefone", "").strip(),
            request.form.get("objetivo", "").strip(),
            request.form.get("nascimento", "") or None,
            request.form.get("observacoes", "").strip(),
            num(request.form.get("altura_cm", "")),
            num(request.form.get("peso_atual", "")),
            num(request.form.get("fator_atividade", ""), 1.55) or 1.0,
            request.form.get("objetivo_meta", "emagrecer"),
            num(request.form.get("ajuste_meta", "")),
            num(request.form.get("proteina_kg", ""), 2.0) or 0.5,
            request.form.get("sexo_formula", "M"),
            intnum(request.form.get("dias_treino", ""), 3) or 1,
            1 if request.form.get("foco_gluteo") else 0,
            request.form.get("rotina", "").strip() or None,
        ),
    )
    con.commit()
    flash("Aluno criado com sucesso.", "success")
    return redirect(url_for("gerar_plano", aluno_id=cur.lastrowid))


@app.route("/aluno/<int:aluno_id>/editar", methods=["POST"])
def editar_aluno(aluno_id):
    a = get_aluno_or_404(aluno_id)
    nome = request.form.get("nome", "").strip() or a["nome"]
    con = get_db()
    con.execute(
        """UPDATE alunos
           SET nome = ?, telefone = ?, objetivo = ?, nascimento = ?, plano = ?,
               mensalidade = ?, dia_vencimento = ?, observacoes = ?,
               altura_cm = ?, peso_atual = ?, fator_atividade = ?, objetivo_meta = ?,
               ajuste_meta = ?, proteina_kg = ?, sexo_formula = ?, dias_treino = ?, foco_gluteo = ?,
                rotina = ?
           WHERE id = ?""",
        (
            nome,
            request.form.get("telefone", "").strip(),
            request.form.get("objetivo", "").strip(),
            request.form.get("nascimento", "") or None,
            request.form.get("plano", "").strip() or a["plano"],
            num(request.form.get("mensalidade", ""), a["mensalidade"]) or 0,
            min(max(intnum(request.form.get("dia_vencimento", ""), a["dia_vencimento"]) or 1, 1), 31),
            request.form.get("observacoes", "").strip(),
            num(request.form.get("altura_cm", ""), a["altura_cm"]),
            num(request.form.get("peso_atual", ""), a["peso_atual"]),
            num(request.form.get("fator_atividade", ""), a["fator_atividade"]) or 1.0,
            request.form.get("objetivo_meta", a["objetivo_meta"] or "emagrecer"),
            num(request.form.get("ajuste_meta", ""), a["ajuste_meta"]),
            num(request.form.get("proteina_kg", ""), a["proteina_kg"]) or 0.5,
            request.form.get("sexo_formula", a["sexo_formula"] or "M"),
            min(max(intnum(request.form.get("dias_treino", ""), a["dias_treino"]) or 1, 1), 6),
            1 if request.form.get("foco_gluteo") else 0,
            request.form.get("rotina", "").strip() or None,
            aluno_id,
        ),
    )
    con.commit()
    flash("Dados atualizados.", "success")
    return redirect(request.form.get("voltar") or url_for("treino", aluno_id=aluno_id))


@app.route("/aluno/<int:aluno_id>/excluir", methods=["POST"])
def excluir_aluno(aluno_id):
    get_aluno_or_404(aluno_id)
    con = get_db()
    con.execute(
        "DELETE FROM exercicios WHERE treino_id IN (SELECT id FROM treinos WHERE aluno_id = ?)",
        (aluno_id,),
    )
    con.execute("DELETE FROM treinos WHERE aluno_id = ?", (aluno_id,))
    con.execute("DELETE FROM refeicoes WHERE aluno_id = ?", (aluno_id,))
    con.execute("DELETE FROM metas_dieta WHERE aluno_id = ?", (aluno_id,))
    con.execute("DELETE FROM checkins WHERE aluno_id = ?", (aluno_id,))
    con.execute("DELETE FROM pagamentos WHERE aluno_id = ?", (aluno_id,))
    for f in con.execute("SELECT arquivo FROM fotos_aluno WHERE aluno_id = ?", (aluno_id,)).fetchall():
        try:
            p = UPLOAD_DIR / str(aluno_id) / f["arquivo"]
            if p.is_file():
                p.unlink()
        except OSError:
            pass
    con.execute("DELETE FROM fotos_aluno WHERE aluno_id = ?", (aluno_id,))
    try:
        pasta_aluno = UPLOAD_DIR / str(aluno_id)
        if pasta_aluno.is_dir():
            pasta_aluno.rmdir()
    except OSError:
        pass
    con.execute("DELETE FROM alunos WHERE id = ?", (aluno_id,))
    con.commit()
    flash("Aluno excluído.", "info")
    return redirect(url_for("alunos"))


@app.route("/aluno/<int:aluno_id>")
def aluno_inicio(aluno_id):
    return redirect(url_for("treino", aluno_id=aluno_id))


SAFE_ABA = {"treino", "dieta", "acompanhamento", "financeiro", "progresso"}


def _user_aba_destino(aluno_id, aba):
    return redirect(url_for("treino", aluno_id=aluno_id))


@app.route("/aluno/<int:aluno_id>/treino")
def treino(aluno_id):
    a = get_aluno_or_404(aluno_id)
    con = get_db()
    treinos = con.execute(
        "SELECT * FROM treinos WHERE aluno_id = ? ORDER BY ordem, id", (aluno_id,)
    ).fetchall()
    exercicios = {}
    for t in treinos:
        exercicios[t["id"]] = con.execute(
            "SELECT * FROM exercicios WHERE treino_id = ? ORDER BY ordem, id", (t["id"],)
        ).fetchall()
    lib = con.execute(
        "SELECT * FROM exercicios_padrao WHERE ativo = 1 ORDER BY grupo, nome"
    ).fetchall()
    outros_treinos = []
    if aluno_id:
        for out in con.execute(
            "SELECT id, nome FROM alunos WHERE id != ? ORDER BY nome", (aluno_id,)
        ).fetchall():
            ts = con.execute(
                "SELECT id, nome, dia_semana FROM treinos WHERE aluno_id = ? ORDER BY ordem, id",
                (out["id"],),
            ).fetchall()
            if ts:
                outros_treinos.append({
                    "aluno": dict(out),
                    "treinos": [dict(t) for t in ts],
                })
    return render_template(
        "treino.html", active="alunos", aba="treino", aluno=a,
        treinos=treinos, exercicios=exercicios, lib=lib, outros_treinos=outros_treinos,
    )


@app.route("/aluno/<int:aluno_id>/treino/novo", methods=["POST"])
def novo_treino(aluno_id):
    get_aluno_or_404(aluno_id)
    nome = request.form.get("nome", "").strip()
    if nome:
        con = get_db()
        con.execute(
            "INSERT INTO treinos (aluno_id, nome, dia_semana, notas, ordem) VALUES (?, ?, ?, ?, ?)",
            (aluno_id, nome, request.form.get("dia_semana", "").strip(),
             request.form.get("notas", "").strip(), num(request.form.get("ordem", ""), 0) or 0),
        )
        con.commit()
        flash("Treino criado.", "success")
    return redirect(url_for("treino", aluno_id=aluno_id))


@app.route("/aluno/<int:aluno_id>/treino/<int:treino_id>/excluir", methods=["POST"])
def excluir_treino(aluno_id, treino_id):
    con = get_db()
    con.execute("DELETE FROM exercicios WHERE treino_id = ?", (treino_id,))
    con.execute("DELETE FROM treinos WHERE id = ? AND aluno_id = ?", (treino_id, aluno_id))
    con.commit()
    flash("Treino excluído.", "info")
    return redirect(url_for("treino", aluno_id=aluno_id))


@app.route("/treino/<int:treino_id>/exercicio/novo", methods=["POST"])
def novo_exercicio(treino_id):
    nome = request.form.get("nome", "").strip()
    con = get_db()
    t = con.execute("SELECT aluno_id FROM treinos WHERE id = ?", (treino_id,)).fetchone()
    if t and nome:
        con.execute(
            """INSERT INTO exercicios (treino_id, nome, series, repeticoes, carga, descanso, grupo, ordem)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (treino_id, nome, request.form.get("series", "").strip(),
             request.form.get("repeticoes", "").strip(), request.form.get("carga", "").strip(),
             request.form.get("descanso", "").strip(), request.form.get("grupo", "").strip(),
             num(request.form.get("ordem", ""), 0) or 0),
        )
        con.commit()
        flash("Exercício adicionado.", "success")
        return redirect(url_for("treino", aluno_id=t["aluno_id"]))
    return redirect(url_for("treino", aluno_id=t["aluno_id"])) if t else redirect(url_for("alunos"))


@app.route("/exercicio/<int:exercicio_id>/excluir", methods=["POST"])
def excluir_exercicio(exercicio_id):
    con = get_db()
    r = con.execute("SELECT treino_id FROM exercicios WHERE id = ?", (exercicio_id,)).fetchone()
    if r:
        t = con.execute("SELECT aluno_id FROM treinos WHERE id = ?", (r["treino_id"],)).fetchone()
        con.execute("DELETE FROM exercicios WHERE id = ?", (exercicio_id,))
        con.commit()
        flash("Exercício removido.", "info")
        if t:
            return redirect(url_for("treino", aluno_id=t["aluno_id"]))
    return redirect(url_for("alunos"))


@app.route("/aluno/<int:aluno_id>/treino/<int:treino_id>/editar", methods=["POST"])
def editar_treino(aluno_id, treino_id):
    con = get_db()
    t = con.execute("SELECT * FROM treinos WHERE id = ? AND aluno_id = ?", (treino_id, aluno_id)).fetchone()
    if t:
        nome = request.form.get("nome", "").strip()
        if nome:
            con.execute(
                "UPDATE treinos SET nome = ?, dia_semana = ?, notas = ?, ordem = ? WHERE id = ?",
                (nome, request.form.get("dia_semana", "").strip(),
                 request.form.get("notas", "").strip(),
                 num(request.form.get("ordem", ""), 0) or 0, treino_id),
            )
            con.commit()
            flash("Treino atualizado.", "success")
    return redirect(url_for("treino", aluno_id=aluno_id))


@app.route("/exercicio/<int:exercicio_id>/editar", methods=["POST"])
def editar_exercicio(exercicio_id):
    con = get_db()
    e = con.execute("SELECT * FROM exercicios WHERE id = ?", (exercicio_id,)).fetchone()
    if e:
        t = con.execute("SELECT aluno_id FROM treinos WHERE id = ?", (e["treino_id"],)).fetchone()
        nome = request.form.get("nome", "").strip()
        if nome:
            con.execute(
                """UPDATE exercicios SET nome = ?, series = ?, repeticoes = ?, carga = ?, descanso = ?, grupo = ?,
                   rir = ?, observacoes = ?, metodo_progressao = ? WHERE id = ?""",
                (nome, request.form.get("series", "").strip(),
                 request.form.get("repeticoes", "").strip(),
                 request.form.get("carga", "").strip(),
                 request.form.get("descanso", "").strip(),
                 request.form.get("grupo", "").strip(),
                 request.form.get("rir", "").strip(),
                 request.form.get("observacoes", "").strip(),
                 request.form.get("metodo_progressao", "").strip() or None, exercicio_id),
            )
            con.commit()
            flash("Exercício atualizado.", "success")
        if t:
            return redirect(url_for("treino", aluno_id=t["aluno_id"]))
    return redirect(url_for("alunos"))


@app.route("/exercicios/buscar")
def buscar_exercicios_rota():
    con = get_db()
    res = buscar_exercicios(con, request.args.get("q", ""), 25)
    return {
        "itens": [
            {
                "id": e["id"], "nome": e["nome"], "grupo": e["grupo"],
                "padrao": e["padrao"] or "", "equipamento": e["equipamento"] or "",
                "nivel": e["nivel"] or "", "grande": e["grande"],
                "series": e["series"], "repeticoes": e["repeticoes"] or "",
                "descanso": e["descanso"] or "", "rir": e["rir"] or "",
                "observacoes": e["observacoes"] or "",
            }
            for e in res
        ],
    }


@app.route("/treino/<int:treino_id>/exercicio/padrao", methods=["POST"])
def novo_exercicio_padrao_no_treino(treino_id):
    con = get_db()
    t = con.execute("SELECT aluno_id FROM treinos WHERE id = ?", (treino_id,)).fetchone()
    ex_id = intnum(request.form.get("ex_id"))
    if t and ex_id:
        e = con.execute("SELECT * FROM exercicios_padrao WHERE id = ? AND ativo = 1", (ex_id,)).fetchone()
        if e:
            ultima = con.execute(
                "SELECT COALESCE(MAX(ordem), 0) AS m FROM exercicios WHERE treino_id = ?", (treino_id,)
            ).fetchone()["m"]
            con.execute(
                """INSERT INTO exercicios (treino_id, nome, series, repeticoes, carga, descanso, grupo, ordem, rir, observacoes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (treino_id, e["nome"], e["series"], e["repeticoes"], "", e["descanso"],
                 e["grupo"], (ultima or 0) + 1, e["rir"], e["observacoes"]),
            )
            con.commit()
            flash(f"{e['nome']} adicionado ao treino.", "success")
            return redirect(url_for("treino", aluno_id=t["aluno_id"]))
    return redirect(url_for("treino", aluno_id=t["aluno_id"])) if t else redirect(url_for("alunos"))


@app.route("/exercicio/<int:exercicio_id>/duplicar", methods=["POST"])
def duplicar_exercicio(exercicio_id):
    con = get_db()
    e = con.execute("SELECT * FROM exercicios WHERE id = ?", (exercicio_id,)).fetchone()
    if not e:
        return redirect(url_for("alunos"))
    t = con.execute("SELECT aluno_id FROM treinos WHERE id = ?", (e["treino_id"],)).fetchone()
    ultima = con.execute(
        "SELECT COALESCE(MAX(ordem), 0) AS m FROM exercicios WHERE treino_id = ?", (e["treino_id"],)
    ).fetchone()["m"]
    con.execute(
        """INSERT INTO exercicios (treino_id, nome, series, repeticoes, carga, descanso, grupo, ordem, rir, observacoes, metodo_progressao)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (e["treino_id"], e["nome"], e["series"], e["repeticoes"], e["carga"], e["descanso"],
         e["grupo"], (ultima or 0) + 1, e["rir"], e["observacoes"], e["metodo_progressao"]),
    )
    con.commit()
    flash("Exercício duplicado.", "info")
    return redirect(url_for("treino", aluno_id=t["aluno_id"])) if t else redirect(url_for("alunos"))


@app.route("/exercicio/<int:exercicio_id>/substituir", methods=["POST"])
def substituir_exercicio(exercicio_id):
    con = get_db()
    e = con.execute("SELECT * FROM exercicios WHERE id = ?", (exercicio_id,)).fetchone()
    if not e:
        return redirect(url_for("alunos"))
    t = con.execute("SELECT aluno_id FROM treinos WHERE id = ?", (e["treino_id"],)).fetchone()
    ex_id = intnum(request.form.get("ex_id"))
    if ex_id:
        novo = con.execute(
            "SELECT * FROM exercicios_padrao WHERE id = ? AND ativo = 1", (ex_id,)
        ).fetchone()
        if novo:
            con.execute(
                """UPDATE exercicios SET nome = ?, grupo = ?, observacoes = ? WHERE id = ?""",
                (novo["nome"], novo["grupo"], novo["observacoes"] or e["observacoes"], exercicio_id),
            )
            con.commit()
            flash(f"Substituído por {novo['nome']} (séries/reps/RIR/descanso preservados).", "success")
    return redirect(url_for("treino", aluno_id=t["aluno_id"])) if t else redirect(url_for("alunos"))


@app.route("/treino/<int:treino_id>/exercicios/ordem", methods=["POST"])
def reordenar_exercicios(treino_id):
    con = get_db()
    t = con.execute("SELECT aluno_id FROM treinos WHERE id = ?", (treino_id,)).fetchone()
    if not t:
        return {"ok": False, "erro": "Treino não encontrado."}
    dados = request.get_json(silent=True) or {}
    ids = dados.get("ids") or []
    existentes = {r["id"] for r in con.execute(
        "SELECT id FROM exercicios WHERE treino_id = ?", (treino_id,)
    ).fetchall()}
    if ids and set(ids) == existentes and len(ids) == len(existentes):
        for i, eid in enumerate(ids, start=1):
            con.execute("UPDATE exercicios SET ordem = ? WHERE id = ?", (i, eid))
        con.commit()
        return {"ok": True}
    return {"ok": False, "erro": "Lista de exercícios incompatível."}


@app.route("/treino/<int:treino_id>/duplicar", methods=["POST"])
def duplicar_treino(treino_id):
    con = get_db()
    t = con.execute("SELECT * FROM treinos WHERE id = ?", (treino_id,)).fetchone()
    if not t:
        return redirect(url_for("alunos"))
    duplicar_treino_db(con, treino_id, request.form.get("nome"))
    con.commit()
    flash("Treino duplicado (cópia independente).", "success")
    return redirect(url_for("treino", aluno_id=t["aluno_id"]))


@app.route("/aluno/<int:aluno_id>/treino/copiar", methods=["POST"])
def copiar_treino_outro_aluno(aluno_id):
    get_aluno_or_404(aluno_id)
    origem_aluno = intnum(request.form.get("aluno_origem"))
    origem_treino = intnum(request.form.get("treino_origem"))
    con = get_db()
    t = con.execute(
        "SELECT * FROM treinos WHERE id = ? AND aluno_id = ?", (origem_treino, origem_aluno)
    ).fetchone()
    if not t:
        flash("Treino de origem não encontrado.", "error")
        return redirect(url_for("treino", aluno_id=aluno_id))
    cur = con.execute(
        "INSERT INTO treinos (aluno_id, nome, dia_semana, notas, ordem) VALUES (?, ?, ?, ?, ?)",
        (aluno_id, t["nome"], t["dia_semana"], t["notas"], 0),
    )
    novo_id = cur.lastrowid
    for e in con.execute(
        "SELECT * FROM exercicios WHERE treino_id = ? ORDER BY ordem, id", (origem_treino,)
    ).fetchall():
        con.execute(
            """INSERT INTO exercicios (treino_id, nome, series, repeticoes, carga, descanso, grupo, ordem, rir, observacoes, metodo_progressao)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (novo_id, e["nome"], e["series"], e["repeticoes"], e["carga"], e["descanso"], e["grupo"],
             e["ordem"], e["rir"], e["observacoes"], e["metodo_progressao"]),
        )
    con.commit()
    flash("Treino copiado para este aluno (registros independentes).", "success")
    return redirect(url_for("treino", aluno_id=aluno_id))


@app.route("/aluno/<int:aluno_id>/treino/modelo", methods=["POST"])
def novo_treino_modelo(aluno_id):
    get_aluno_or_404(aluno_id)
    modelo = request.form.get("modelo")
    nome = request.form.get("nome", "").strip()
    if modelo not in MODELOS_TREINO:
        flash("Modelo inválido.", "error")
        return redirect(url_for("treino", aluno_id=aluno_id))
    con = get_db()
    sugestao = montar_sugestao(
        con, "Outro", modelo, "Intermediário", "60", [], "", [], rot=aluno_id,
    )
    treino_id = gravar_sugestao(
        con, aluno_id, nome or f"Treino {MODELOS_TREINO[modelo]['label']}", "", "",
        sugestao["itens"],
    )
    con.commit()
    flash("Treino criado a partir do modelo.", "success")
    return redirect(url_for("treino", aluno_id=aluno_id))


@app.route("/aluno/<int:aluno_id>/assistente/sugestao", methods=["POST"])
def assistente_sugestao(aluno_id):
    get_aluno_or_404(aluno_id)
    dados = request.get_json(silent=True) or {}
    con = get_db()
    res = montar_sugestao(
        con,
        dados.get("objetivo") or "Hipertrofia",
        dados.get("divisao") or "fullbody",
        dados.get("nivel") or "Intermediário",
        dados.get("duracao") or "60",
        dados.get("prioridades") or [],
        dados.get("restricoes") or "",
        dados.get("equipamentos") or [],
        rot=intnum(dados.get("rot"), aluno_id) or aluno_id,
    )
    return {"itens": res["itens"], "avisos": res["avisos"]}


@app.route("/aluno/<int:aluno_id>/assistente/salvar", methods=["POST"])
def assistente_salvar(aluno_id):
    get_aluno_or_404(aluno_id)
    dados = request.get_json(silent=True) or {}
    itens = dados.get("itens") or []
    con = get_db()
    mouse = gravar_sugestao(
        con, aluno_id, dados.get("nome") or "Treino montado",
        dados.get("dia_semana") or "", dados.get("notas") or "", itens,
    )
    con.commit()
    flash("Treino montado pelo assistente criado com sucesso.", "success")
    return {"ok": True, "treino_id": mouse}


@app.route("/aluno/<int:aluno_id>/dieta")
def dieta(aluno_id):
    a = get_aluno_or_404(aluno_id)
    con = get_db()
    metas = con.execute("SELECT * FROM metas_dieta WHERE aluno_id = ?", (aluno_id,)).fetchone()
    refeicoes = con.execute(
        "SELECT * FROM refeicoes WHERE aluno_id = ? ORDER BY ordem, id", (aluno_id,)
    ).fetchall()
    alim = montar_alimentos(con, refeicoes)
    catalogo = con.execute("SELECT * FROM alimentos ORDER BY categoria, nome").fetchall()
    totais = {
        "calorias": con.execute("SELECT COALESCE(SUM(calorias), 0) AS s FROM refeicoes WHERE aluno_id = ?", (aluno_id,)).fetchone()["s"],
        "proteinas": con.execute("SELECT COALESCE(SUM(proteinas), 0) AS s FROM refeicoes WHERE aluno_id = ?", (aluno_id,)).fetchone()["s"],
        "carbs": con.execute("SELECT COALESCE(SUM(carbs), 0) AS s FROM refeicoes WHERE aluno_id = ?", (aluno_id,)).fetchone()["s"],
        "gorduras": con.execute("SELECT COALESCE(SUM(gorduras), 0) AS s FROM refeicoes WHERE aluno_id = ?", (aluno_id,)).fetchone()["s"],
    }
    refeicoes_json = {}
    nutri = {}
    for r in refeicoes:
        d = dict(r)
        lista = alim[r["id"]]
        d["alimentos"] = [f["nome"] for f in lista]
        d["alim_qtd"] = {f["nome"]: f["qtd"] for f in lista}
        refeicoes_json[r["id"]] = d
    for al in catalogo:
        nutri[al["id"]] = {
            "nome": al["nome"],
            "grupo": al["grupo_equiv"],
            "k": al["kcal"] or 0,
            "p": al["proteinas"] or 0,
            "c": al["carbs"] or 0,
            "g": al["gorduras"] or 0,
            "porcao": al["porcao"] or 100,
        }
    return render_template(
        "dieta.html", active="alunos", aba="dieta", aluno=a,
        metas=metas, refeicoes=refeicoes, totais=totais,
        alim=alim, catalogo=catalogo, refeicoes_json=refeicoes_json, nutri=nutri,
    )


@app.route("/aluno/<int:aluno_id>/metas", methods=["POST"])
def salvar_metas(aluno_id):
    get_aluno_or_404(aluno_id)
    con = get_db()
    con.execute(
        """INSERT INTO metas_dieta (aluno_id, kcal_diaria, proteinas, carbs, gorduras, observacoes)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(aluno_id) DO UPDATE SET
              kcal_diaria = excluded.kcal_diaria,
              proteinas = excluded.proteinas,
              carbs = excluded.carbs,
              gorduras = excluded.gorduras,
              observacoes = excluded.observacoes""",
        (
            aluno_id,
            num(request.form.get("kcal_diaria", ""), 0) or 0,
            num(request.form.get("proteinas", ""), 0) or 0,
            num(request.form.get("carbs", ""), 0) or 0,
            num(request.form.get("gorduras", ""), 0) or 0,
            request.form.get("observacoes", "").strip(),
        ),
    )
    con.commit()
    return redirect(url_for("dieta", aluno_id=aluno_id))


def _alimentos_info(con, ids):
    if not ids:
        return []
    ph = ",".join("?" * len(ids))
    return con.execute(f"SELECT * FROM alimentos WHERE id IN ({ph})", ids).fetchall()


def _gerar_pares_otimizados(con, pares, macros, nome_refeicao=None):
    """Calcula quantidades reais usando o novo motor de otimização quando há metas."""
    if not pares:
        return []
    kcal_t, p_t, c_t, g_t = (float(m) if m is not None else 0.0 for m in macros)
    if not (kcal_t or p_t or c_t or g_t):
        return _pares_padrao(con, pares)

    ids = [int(a) for a, _ in pares]
    itens = _alimentos_info(con, ids)
    if not itens:
        return _pares_padrao(con, pares)

    estrutura = {nome_refeicao or "Refeição": [it["nome"] for it in itens if it.get("nome")]}
    optimizer = DietPlanOptimizer(
        meta_calorica_diaria=kcal_t,
        proteina_diaria=p_t,
        carboidrato_diario=c_t,
        gordura_diaria=g_t,
        quantidade_refeicoes=1,
        estrutura_refeicoes=estrutura,
        alimentos_disponiveis=[dict(it) for it in itens],
        alimentos_ativos=[dict(it) for it in itens],
        dados_nutricionais=[dict(it) for it in itens],
    )
    plan = optimizer.generate()
    meal = plan.get("refeicoes", [{}])[0]
    itens_plan = meal.get("alimentos", []) if isinstance(meal, dict) else []
    if not itens_plan:
        return _resolver_qtds(con, itens, kcal_t, p_t, c_t, g_t)

    mapa_nome = {str(it["nome"]).strip().lower(): it for it in itens}
    saida = []
    for item in itens_plan:
        nome = str(item.get("nome") or "").strip().lower()
        alimento = mapa_nome.get(nome)
        if not alimento:
            continue
        qtd = float(item.get("quantidade") or item.get("qtd") or 0.0)
        if qtd <= 0:
            continue
        saida.append((int(alimento["id"]), max(0, round(float(qtd), 1))))
    if saida:
        return saida
    return _resolver_qtds(con, itens, kcal_t, p_t, c_t, g_t)


def _pares_formulario():
    """Lê alimentos + gramas enviados do formulário de refeição."""
    qtd_map = {}
    for part in request.form.getlist("alimento_qtd"):
        if ":" in part:
            a, q = part.split(":", 1)
            try:
                qtd_map[int(a)] = float(q)
            except (ValueError, TypeError):
                pass
    pares = []
    for aid in request.form.getlist("alimentos"):
        aid_i = intnum(aid)
        if aid_i:
            pares.append((aid_i, qtd_map.get(aid_i, 0.0)))
    return pares


def _pares_padrao(con, pares):
    """Gramas padrão (porção base) quando a refeição não tem metas numéricas."""
    q = {x["id"]: (x["porcao"] or 100) for x in _alimentos_info(con, [a for a, _ in pares])}
    return [(a, max(0, int(round(float(q.get(a, 100)))))) for a, _ in pares]


def _pares_automaticos(con, pares, macros):
    kcal_t, p_t, c_t, g_t = macros
    if not pares:
        return pares
    if not (kcal_t or p_t or c_t or g_t):
        return _pares_padrao(con, pares)
    # Primeiro tenta o motor novo para respeitar porções e qualidade.
    otimizados = _gerar_pares_otimizados(con, pares, macros)
    if otimizados:
        return otimizados
    itens = _alimentos_info(con, [a for a, _ in pares])
    return _resolver_qtds(con, itens, kcal_t, p_t, c_t, g_t)


def _gerar_dieta_automaticamente(con, aluno_id, c):
    """Gera uma dieta diária coerente usando o motor novo e preserva as metas do app."""
    estrutura = {}
    alimentos = con.execute("SELECT * FROM alimentos WHERE ativo = 1").fetchall()
    nomes_disponiveis = {str(alimento["nome"]).strip().lower() for alimento in alimentos}
    for nome, slots in MONTAGEM_REFEICOES.items():
        estrutura[nome] = []
        for papel, candidatos in slots:
            candidatos_validos = [
                candidato for candidato in candidatos
                if candidato.strip().lower() in nomes_disponiveis
            ]
            if not candidatos_validos:
                continue
            inicio = aluno_id % len(candidatos_validos)
            rotacionados = candidatos_validos[inicio:] + candidatos_validos[:inicio]
            estrutura[nome].append({"papel": papel, "candidatos": rotacionados})
        if not estrutura[nome]:
            del estrutura[nome]
    if not estrutura:
        return None

    optimizer = DietPlanOptimizer(
        meta_calorica_diaria=float(c["meta_kcal"] or 0.0),
        proteina_diaria=float(c["proteina"] or 0.0),
        carboidrato_diario=float(c["carbo"] or 0.0),
        gordura_diaria=float(c["gordura"] or 0.0),
        quantidade_refeicoes=len(REFEICOES_MODELO),
        estrutura_refeicoes=estrutura,
        alimentos_disponiveis=[dict(a) for a in alimentos],
        alimentos_ativos=[dict(a) for a in alimentos],
        dados_nutricionais=[dict(a) for a in alimentos],
    )
    return optimizer.generate()


@app.route("/aluno/<int:aluno_id>/refeicao/novo", methods=["POST"])
def nova_refeicao(aluno_id):
    get_aluno_or_404(aluno_id)
    nome = request.form.get("nome", "").strip()
    if nome:
        con = get_db()
        macros = (
            num(request.form.get("calorias", ""), 0) or 0,
            num(request.form.get("proteinas", ""), 0) or 0,
            num(request.form.get("carbs", ""), 0) or 0,
            num(request.form.get("gorduras", ""), 0) or 0,
        )
        cur = con.execute(
            """INSERT INTO refeicoes (aluno_id, nome, horario, calorias, proteinas, carbs, gorduras, descricao, ordem)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (aluno_id, nome, request.form.get("horario", "").strip(),
             macros[0], macros[1], macros[2], macros[3],
             request.form.get("descricao", "").strip(),
             num(request.form.get("ordem", ""), 0) or 0),
        )
        pares = _pares_automaticos(con, _pares_formulario(), macros)
        gravar_alimentos(con, cur.lastrowid, pares)
        con.commit()
        flash("Refeição adicionada.", "success")
    return redirect(url_for("dieta", aluno_id=aluno_id))


def gravar_alimentos(con, refeicao_id, pares):
    con.execute("DELETE FROM refeicao_alimentos WHERE refeicao_id = ?", (refeicao_id,))
    for i, (aid, qtd) in enumerate(pares):
        aid = intnum(aid)
        if aid:
            con.execute(
                "INSERT INTO refeicao_alimentos (refeicao_id, alimento_id, qtd, ordem) VALUES (?, ?, ?, ?)",
                (refeicao_id, aid, round(float(qtd or 0)), i),
            )


def _selecionar_alimentos(con, nome_refeicao, aluno_id):
    """Escolhe 1 alimento de cada papel estrutural da refeição (variedade por aluno).

    A seleção acontece ANTES de ajustar quantidades: primeiro montamos um almoço
    com proteína + carbo + verdura, depois o solver só dimensiona dentro da faixa.
    """
    out = []
    for _, candidatos in MONTAGEM_REFEICOES.get(nome_refeicao, []):
        if not candidatos:
            continue
        nome = candidatos[aluno_id % len(candidatos)]
        if con.execute("SELECT 1 FROM alimentos WHERE nome = ?", (nome,)).fetchone():
            out.append(nome)
    return out


def _avaliar_porcoes(itens, macros, dia=False):
    """Gera avisos quando as porções/desvios saem das tolerâncias configuradas.

    itens: lista com qtd, _min/_max já resolvidos (ou 'k/p/c/g/qtd')."""
    avisos = []
    for x in itens:
        mn, mx = x.get("_min"), x.get("_max")
        if mn is None:
            mn, ide, mx = _faixa_porcao({"nome": x.get("nome"), "grupo": x.get("grupo"),
                                         "porcao": x.get("porcao")})
        q = float(x.get("qtd") or 0)
        if q > mx + 0.5:
            avisos.append(f"{x.get('nome')}: {round(q)} g acima do máximo ({round(mx)} g).")
        elif q < mn - 0.5:
            avisos.append(f"{x.get('nome')}: {round(q)} g abaixo do mínimo ({round(mn)} g).")
    if not macros:
        return avisos
    kcal_t, p_t, c_t, g_t = macros
    if not any(macros):
        return avisos
    k, p, c, g = _totais_item(itens)
    tol_k = max(TOLERANCIAS_DIETA["kcal_pct"] * (kcal_t or 0) / 100.0, 25.0)
    if kcal_t and abs(k - kcal_t) > tol_k:
        avisos.append(f"kcal: {round(k)} vs meta {round(kcal_t)} (dif. {round(k - kcal_t):+d}).")
    if p_t and abs(p - p_t) > TOLERANCIAS_DIETA["proteina"]:
        avisos.append(f"proteína: {round(p)} g vs meta {round(p_t)} g.")
    if c_t and abs(c - c_t) > TOLERANCIAS_DIETA["carbo"]:
        avisos.append(f"carboidratos: {round(c)} g vs meta {round(c_t)} g.")
    if g_t and abs(g - g_t) > TOLERANCIAS_DIETA["gordura"]:
        avisos.append(f"gordura: {round(g)} g vs meta {round(g_t)} g.")
    return avisos


@app.route("/refeicao/calcular", methods=["POST"])
def calcular_refeicao():
    """Fonte única do preview: o cliente envia ids + metas e recebe as gramas
    calculadas pelo mesmo solver usado ao salvar. Evita duplicar a lógica em JS."""
    dados = request.get_json(silent=True) or {}
    itens = []
    for i in dados.get("itens", []):
        aid = intnum(i.get("aid"))
        if aid:
            itens.append((aid, num(i.get("qtd"), 0) or 0))
    m = [num(x, 0) or 0 for x in (dados.get("macros") or [])]
    m = (list(m) + [0, 0, 0, 0])[:4]
    con = get_db()
    pares = _pares_automaticos(con, itens, tuple(m))
    rows = {int(r["id"]): r for r in _alimentos_info(con, [a for a, _ in pares])}
    qmap = dict(pares)
    resultado = []
    for aid, qtd in pares:
        r = rows.get(int(aid))
        if not r:
            continue
        mn, ide, mx = _faixa_porcao(dict(r))
        resultado.append({
            "aid": int(aid), "nome": r["nome"], "grupo": r["grupo_equiv"],
            "k": r["kcal"] or 0, "p": r["proteinas"] or 0,
            "c": r["carbs"] or 0, "g": r["gorduras"] or 0,
            "porcao": r["porcao"] or 100,
            "qtd": qtd, "min": round(mn), "ideal": round(ide), "max": round(mx),
        })
    avisos = _avaliar_porcoes(
        [{"nome": r["nome"], "grupo": r["grupo_equiv"], "porcao": r["porcao"] or 100,
          "k": r["kcal"] or 0, "p": r["proteinas"] or 0,
          "c": r["carbs"] or 0, "g": r["gorduras"] or 0,
          "qtd": qmap[int(r["id"])]} for r in rows.values()], tuple(m)
    )
    return {"itens": resultado, "avisos": avisos}


@app.route("/refeicao/<int:refeicao_id>/editar", methods=["POST"])
def editar_refeicao(refeicao_id):
    con = get_db()
    r = con.execute("SELECT * FROM refeicoes WHERE id = ?", (refeicao_id,)).fetchone()
    if not r:
        return redirect(url_for("alunos"))
    aluno_id = r["aluno_id"]
    nome = request.form.get("nome", "").strip()
    macros = (
        num(request.form.get("calorias", ""), 0) or 0,
        num(request.form.get("proteinas", ""), 0) or 0,
        num(request.form.get("carbs", ""), 0) or 0,
        num(request.form.get("gorduras", ""), 0) or 0,
    )
    macros_antes = (r["calorias"] or 0, r["proteinas"] or 0, r["carbs"] or 0, r["gorduras"] or 0)
    ids_antes = {int(x["alimento_id"]) for x in con.execute(
        "SELECT alimento_id FROM refeicao_alimentos WHERE refeicao_id = ?", (refeicao_id,))}
    pares = _pares_formulario()
    ids_novos = {a for a, _ in pares}
    macros_mudaram = any(round(float(a)) != round(float(b)) for a, b in zip(macros, macros_antes))
    alimentos_mudaram = ids_antes != ids_novos
    if pares and (macros_mudaram or alimentos_mudaram):
        pares = _pares_automaticos(con, pares, macros)
    con.execute(
        """UPDATE refeicoes SET nome = ?, horario = ?, calorias = ?, proteinas = ?, carbs = ?, gorduras = ?, descricao = ?
           WHERE id = ?""",
        (
            nome or "Refeição",
            request.form.get("horario", "").strip(),
            macros[0], macros[1], macros[2], macros[3],
            request.form.get("descricao", "").strip(),
            refeicao_id,
        ),
    )
    gravar_alimentos(con, refeicao_id, pares)
    con.commit()
    flash("Refeição atualizada.", "success")
    return redirect(url_for("dieta", aluno_id=aluno_id))


@app.route("/refeicao/<int:refeicao_id>/excluir", methods=["POST"])
def excluir_refeicao(refeicao_id):
    con = get_db()
    r = con.execute("SELECT aluno_id FROM refeicoes WHERE id = ?", (refeicao_id,)).fetchone()
    if r:
        con.execute("DELETE FROM refeicao_alimentos WHERE refeicao_id = ?", (refeicao_id,))
        con.execute("DELETE FROM refeicoes WHERE id = ?", (refeicao_id,))
        con.commit()
        flash("Refeição removida.", "info")
        return redirect(url_for("dieta", aluno_id=r["aluno_id"]))
    return redirect(url_for("alunos"))


@app.route("/alimento/novo", methods=["POST"])
def novo_alimento():
    nome = request.form.get("nome", "").strip()
    categoria = request.form.get("categoria", "").strip()
    grupo_equiv = request.form.get("grupo_equiv", "").strip()
    aluno_id = intnum(request.form.get("aluno_id"))
    if nome and categoria and grupo_equiv:
        con = get_db()
        con.execute(
            """INSERT INTO alimentos (nome, categoria, grupo_equiv, kcal, proteinas, carbs, gorduras, porcao,
               porcao_min, porcao_max, porcao_padrao, refeicoes_permitidas, tipo_equivalencia)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (nome, categoria, grupo_equiv,
             num(request.form.get("kcal", ""), 0) or 0,
             num(request.form.get("proteinas", ""), 0) or 0,
             num(request.form.get("carbs", ""), 0) or 0,
             num(request.form.get("gorduras", ""), 0) or 0,
             num(request.form.get("porcao", ""), 100) or 1,
             num(request.form.get("porcao_min", ""), 0) or 0,
             num(request.form.get("porcao_max", ""), 0) or 0,
             num(request.form.get("porcao_padrao", ""), 0) or 0,
             request.form.get("refeicoes_permitidas", "").strip(),
             request.form.get("tipo_equivalencia", "").strip()),
        )
        con.commit()
        flash("Alimento adicionado ao catálogo.", "success")
        return redirect(url_for("dieta", aluno_id=aluno_id)) if aluno_id else redirect(url_for("alunos"))
    flash("Preencha nome, categoria e grupo de substituição.", "error")
    return redirect(url_for("dieta", aluno_id=aluno_id)) if aluno_id else redirect(url_for("alunos"))


@app.route("/alimento/<int:alimento_id>/dados")
def alimento_dados(alimento_id):
    """Retorna os dados de um alimento em JSON (para edição via AJAX)."""
    con = get_db()
    a = con.execute("SELECT * FROM alimentos WHERE id = ?", (alimento_id,)).fetchone()
    if not a:
        return {"erro": "Alimento não encontrado"}, 404
    return {
        "id": a["id"],
        "nome": a["nome"],
        "categoria": a["categoria"],
        "grupo_equiv": a["grupo_equiv"],
        "kcal": a["kcal"],
        "proteinas": a["proteinas"],
        "carbs": a["carbs"],
        "gorduras": a["gorduras"],
        "porcao": a["porcao"],
        "porcao_min": a["porcao_min"],
        "porcao_max": a["porcao_max"],
        "porcao_padrao": a["porcao_padrao"],
        "refeicoes_permitidas": a["refeicoes_permitidas"],
        "tipo_equivalencia": a["tipo_equivalencia"],
    }


@app.route("/alimento/<int:alimento_id>/editar", methods=["POST"])
def editar_alimento(alimento_id):
    """Rota para editar um alimento existente (interface administrativa)."""
    con = get_db()
    alimento = con.execute("SELECT * FROM alimentos WHERE id = ?", (alimento_id,)).fetchone()
    if not alimento:
        flash("Alimento não encontrado.", "error")
        return redirect(url_for("alunos"))
    
    nome = request.form.get("nome", "").strip()
    if not nome:
        flash("Nome do alimento é obrigatório.", "error")
        return redirect(url_for("alunos"))
    
    grupo_equiv = request.form.get("grupo_equiv", "").strip()
    tipo_equivalencia = request.form.get("tipo_equivalencia", "").strip()
    
    con.execute(
        """UPDATE alimentos SET
           nome = ?, categoria = ?, grupo_equiv = ?,
           kcal = ?, proteinas = ?, carbs = ?, gorduras = ?, porcao = ?,
           porcao_min = ?, porcao_max = ?, porcao_padrao = ?,
           refeicoes_permitidas = ?, tipo_equivalencia = ?
           WHERE id = ?""",
        (nome,
         request.form.get("categoria", "").strip(),
         grupo_equiv,
         num(request.form.get("kcal", ""), 0) or 0,
         num(request.form.get("proteinas", ""), 0) or 0,
         num(request.form.get("carbs", ""), 0) or 0,
         num(request.form.get("gorduras", ""), 0) or 0,
         num(request.form.get("porcao", ""), 100) or 1,
         num(request.form.get("porcao_min", ""), 0) or 0,
         num(request.form.get("porcao_max", ""), 0) or 0,
         num(request.form.get("porcao_padrao", ""), 0) or 0,
         request.form.get("refeicoes_permitidas", "").strip(),
         tipo_equivalencia,
         alimento_id),
    )
    con.commit()
    flash(f"Alimento '{nome}' atualizado com sucesso.", "success")
    return redirect(url_for("alimentos_admin"))


@app.route("/alimento/<int:alimento_id>/excluir", methods=["POST"])
def excluir_alimento(alimento_id):
    """Rota para excluir um alimento (apenas se não estiver em uso)."""
    con = get_db()
    alimento = con.execute("SELECT * FROM alimentos WHERE id = ?", (alimento_id,)).fetchone()
    if not alimento:
        flash("Alimento não encontrado.", "error")
        return redirect(url_for("alimentos_admin"))
    
    # Verifica se o alimento está em uso em alguma refeição
    em_uso = con.execute(
        "SELECT COUNT(*) AS n FROM refeicao_alimentos WHERE alimento_id = ?",
        (alimento_id,)
    ).fetchone()["n"]
    
    if em_uso > 0:
        flash(f"Não é possível excluir '{alimento['nome']}' porque está em uso em {em_uso} refeição(ões).", "error")
        return redirect(url_for("alimentos_admin"))
    
    con.execute("DELETE FROM alimentos WHERE id = ?", (alimento_id,))
    con.commit()
    flash(f"Alimento '{alimento['nome']}' excluído com sucesso.", "success")
    return redirect(url_for("alimentos_admin"))


@app.route("/alimentos/admin")
def alimentos_admin():
    """Interface administrativa para gerenciar alimentos."""
    con = get_db()
    alimentos = con.execute("SELECT * FROM alimentos ORDER BY categoria, nome").fetchall()
    return render_template(
        "alimentos_admin.html",
        active="alimentos",
        alimentos=alimentos,
        CATEGORIAS=CATEGORIAS,
        EQUIV_LABELS=EQUIV_LABELS,
    )


@app.route("/aluno/<int:aluno_id>/acompanhamento")
def acompanhamento(aluno_id):
    a = get_aluno_or_404(aluno_id)
    con = get_db()
    checkins = con.execute(
        "SELECT * FROM checkins WHERE aluno_id = ? ORDER BY data DESC, id DESC", (aluno_id,)
    ).fetchall()
    return render_template(
        "acompanhamento.html", active="alunos", aba="acompanhamento",
        aluno=a, checkins=checkins,
    )


@app.route("/aluno/<int:aluno_id>/checkin/novo", methods=["POST"])
def novo_checkin(aluno_id):
    get_aluno_or_404(aluno_id)
    data = request.form.get("data", "").strip() or datetime.date.today().isoformat()
    con = get_db()
    con.execute(
        """INSERT INTO checkins (aluno_id, data, peso, dores, energia, sono, kcal_consumidas, adesao, observacoes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            aluno_id, data,
            num(request.form.get("peso", "")) or None,
            request.form.get("dores", "").strip(),
            intnum(request.form.get("energia", "")) or None,
            request.form.get("sono", "").strip(),
            num(request.form.get("kcal_consumidas", "")) or None,
            intnum(request.form.get("adesao", "")),
            request.form.get("observacoes", "").strip(),
        ),
    )
    con.commit()
    flash("Check-in salvo.", "success")
    return redirect(url_for("acompanhamento", aluno_id=aluno_id))


@app.route("/checkin/<int:checkin_id>/excluir", methods=["POST"])
def excluir_checkin(checkin_id):
    con = get_db()
    r = con.execute("SELECT aluno_id FROM checkins WHERE id = ?", (checkin_id,)).fetchone()
    if r:
        con.execute("DELETE FROM checkins WHERE id = ?", (checkin_id,))
        con.commit()
        flash("Check-in excluído.", "info")
        return redirect(url_for("acompanhamento", aluno_id=r["aluno_id"]))
    return redirect(url_for("alunos"))


@app.route("/aluno/<int:aluno_id>/avaliacao")
def avaliacao(aluno_id):
    a = get_aluno_or_404(aluno_id)
    con = get_db()
    avaliacoes = con.execute(
        "SELECT * FROM avaliacoes WHERE aluno_id = ? ORDER BY data DESC, id DESC", (aluno_id,)
    ).fetchall()
    graficos = grafico_evolucao(avaliacoes)
    imc_atual = None
    altura = a["altura_cm"]
    if avaliacoes and avaliacoes[0]["peso"] and altura and altura > 0:
        imc_atual = round(avaliacoes[0]["peso"] / ((altura / 100) ** 2), 2)
    ultima = avaliacoes[0] if avaliacoes else None
    anterior = avaliacoes[1] if len(avaliacoes) > 1 else None
    return render_template(
        "avaliacao.html", active="alunos", aba="avaliacao", aluno=a,
        avaliacoes=avaliacoes, graficos=graficos, imc_atual=imc_atual,
        ultima=ultima, anterior=anterior,
    )


@app.route("/aluno/<int:aluno_id>/avaliacao/novo", methods=["POST"])
def nova_avaliacao(aluno_id):
    get_aluno_or_404(aluno_id)
    data = request.form.get("data", "").strip() or datetime.date.today().isoformat()
    con = get_db()
    cols = [k for k, _ in MEDIDAS]
    vals = [num(request.form.get(k, "")) for k, _ in MEDIDAS]
    con.execute(
        "INSERT INTO avaliacoes (aluno_id, data, %s, observacoes) VALUES (?, ?, %s, ?)"
        % (", ".join(cols), ", ".join("?" * len(cols))),
        (aluno_id, data, *vals, request.form.get("observacoes", "").strip()),
    )
    con.commit()
    flash("Avaliação registrada.", "success")
    return redirect(url_for("avaliacao", aluno_id=aluno_id))


@app.route("/avaliacao/<int:avaliacao_id>/editar", methods=["POST"])
def editar_avaliacao(avaliacao_id):
    con = get_db()
    r = con.execute("SELECT aluno_id FROM avaliacoes WHERE id = ?", (avaliacao_id,)).fetchone()
    if r:
        data = request.form.get("data", "").strip()
        cols = [k for k, _ in MEDIDAS]
        vals = [num(request.form.get(k, "")) for k, _ in MEDIDAS]
        con.execute(
            "UPDATE avaliacoes SET data = ?, %s, observacoes = ? WHERE id = ?"
            % (", ".join(["%s = ?" % c for c in cols])),
            (data, *vals, request.form.get("observacoes", "").strip(), avaliacao_id),
        )
        con.commit()
        flash("Avaliação atualizada.", "success")
        return redirect(url_for("avaliacao", aluno_id=r["aluno_id"]))
    return redirect(url_for("alunos"))


@app.route("/avaliacao/<int:avaliacao_id>/excluir", methods=["POST"])
def excluir_avaliacao(avaliacao_id):
    con = get_db()
    r = con.execute("SELECT aluno_id FROM avaliacoes WHERE id = ?", (avaliacao_id,)).fetchone()
    if r:
        con.execute("DELETE FROM avaliacoes WHERE id = ?", (avaliacao_id,))
        con.commit()
        flash("Avaliação excluída.", "info")
        return redirect(url_for("avaliacao", aluno_id=r["aluno_id"]))
    return redirect(url_for("alunos"))


@app.route("/aluno/<int:aluno_id>/progresso")
def progresso(aluno_id):
    a = get_aluno_or_404(aluno_id)
    con = get_db()
    fotos = con.execute(
        "SELECT * FROM fotos_aluno WHERE aluno_id = ? ORDER BY data DESC, id DESC", (aluno_id,)
    ).fetchall()
    serie = serie_peso(con, aluno_id)
    grafico = preparar_grafico_peso(serie)
    ultimo_peso = serie[-1]["peso"] if serie else None
    peso_atual = a["peso_atual"] or ultimo_peso
    altura = a["altura_cm"]
    imc = None
    if peso_atual and altura and altura > 0:
        imc = round(peso_atual / ((altura / 100) ** 2), 2)
    primeiro = serie[0]["peso"] if serie else None
    ultimo = ultimo_peso
    tendencia = tendencia_peso(a["objetivo_meta"] or "", primeiro, ultimo)
    if tendencia and len(serie) > 1:
        try:
            d0 = datetime.datetime.strptime(serie[0]["data"], "%Y-%m-%d").date()
            d1 = datetime.datetime.strptime(serie[-1]["data"], "%Y-%m-%d").date()
            tendencia["periodo"] = (d1 - d0).days
        except Exception:
            tendencia["periodo"] = None
    plano = calcular_plano(a)
    return render_template(
        "progresso.html", active="alunos", aba="progresso", aluno=a,
        fotos=fotos, serie=serie, grafico=grafico, peso_atual=peso_atual,
        altura=altura, imc=imc, tendencia=tendencia, plano=plano,
    )


@app.route("/aluno/<int:aluno_id>/foto", methods=["POST"])
def adicionar_foto(aluno_id):
    get_aluno_or_404(aluno_id)
    arq = request.files.get("foto")
    nome = salvar_foto(arq, aluno_id) if arq else None
    if nome:
        con = get_db()
        con.execute(
            "INSERT INTO fotos_aluno (aluno_id, data, peso, legenda, arquivo) VALUES (?, ?, ?, ?, ?)",
            (
                aluno_id,
                request.form.get("data", "").strip() or datetime.date.today().isoformat(),
                num(request.form.get("peso", "")) or None,
                request.form.get("legenda", "").strip(),
                nome,
            ),
        )
        con.commit()
        flash("Foto adicionada ao progresso.", "success")
    else:
        flash("Não foi possível salvar a foto (formato permitido: JPG, PNG, WEBP, GIF · até 6 MB).", "error")
    return redirect(url_for("progresso", aluno_id=aluno_id))


@app.route("/foto/<int:foto_id>/excluir", methods=["POST"])
def excluir_foto(foto_id):
    con = get_db()
    f = con.execute("SELECT * FROM fotos_aluno WHERE id = ?", (foto_id,)).fetchone()
    if f:
        caminho = UPLOAD_DIR / str(f["aluno_id"]) / f["arquivo"]
        try:
            if caminho.is_file():
                caminho.unlink()
        except OSError:
            pass
        con.execute("DELETE FROM fotos_aluno WHERE id = ?", (foto_id,))
        con.commit()
        flash("Foto excluída.", "info")
        return redirect(url_for("progresso", aluno_id=f["aluno_id"]))
    return redirect(url_for("alunos"))


@app.route("/uploads/<int:aluno_id>/<path:arquivo>")
def foto_arquivo(aluno_id, arquivo):
    return send_from_directory(UPLOAD_DIR / str(aluno_id), arquivo)


@app.route("/aluno/<int:aluno_id>/financeiro")
def financeiro_aluno(aluno_id):
    a = get_aluno_or_404(aluno_id)
    con = get_db()
    pagamentos = con.execute(
        "SELECT * FROM pagamentos WHERE aluno_id = ? ORDER BY mes DESC", (aluno_id,)
    ).fetchall()
    return render_template(
        "financeiro_aluno.html", active="alunos", aba="financeiro",
        aluno=a, pagamentos=pagamentos,
    )


@app.route("/financeiro/status", methods=["POST"])
def financeiro_status():
    aluno_id = intnum(request.form.get("aluno_id"))
    mes = request.form.get("mes", "").strip() or mes_atual()
    status = request.form.get("status")
    a = get_aluno_or_404(aluno_id)
    if status in ("pago", "pendente"):
        con = get_db()
        con.execute(
            """INSERT INTO pagamentos (aluno_id, mes, valor, status, data_pagamento)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(aluno_id, mes) DO UPDATE SET
                  status = excluded.status,
                  data_pagamento = excluded.data_pagamento""",
            (
                aluno_id, mes, a["mensalidade"], status,
                datetime.date.today().isoformat() if status == "pago" else None,
            ),
        )
        con.commit()
        if status == "pago":
            flash("Pagamento confirmado!", "success")
        else:
            flash("Marcado como pendente.", "info")
    voltar = request.form.get("voltar", "global")
    if voltar == "aluno":
        return redirect(url_for("financeiro_aluno", aluno_id=aluno_id))
    return redirect(url_for("financeiro", m=mes))


@app.route("/financeiro")
def financeiro():
    mes = request.args.get("m", "").strip() or mes_atual()
    con = get_db()
    alunos_ativos = con.execute(
        "SELECT * FROM alunos WHERE ativo = 1 ORDER BY nome"
    ).fetchall()
    esperado = con.execute(
        "SELECT COALESCE(SUM(mensalidade), 0) AS s FROM alunos WHERE ativo = 1"
    ).fetchone()["s"]
    recebido = con.execute(
        "SELECT COALESCE(SUM(valor), 0) AS s FROM pagamentos WHERE mes = ? AND status = 'pago'",
        (mes,),
    ).fetchone()["s"]

    hoje = datetime.date.today().day
    rows = []
    for a in alunos_ativos:
        p = con.execute(
            "SELECT * FROM pagamentos WHERE aluno_id = ? AND mes = ?", (a["id"], mes)
        ).fetchone()
        if p is None:
            con.execute(
                "INSERT OR IGNORE INTO pagamentos (aluno_id, mes, valor, status) VALUES (?, ?, ?, ?)",
                (a["id"], mes, a["mensalidade"], "pendente"),
            )
            con.commit()
            p = con.execute(
                "SELECT * FROM pagamentos WHERE aluno_id = ? AND mes = ?", (a["id"], mes)
            ).fetchone()
        status = p["status"]
        if status != "pago" and hoje > a["dia_vencimento"]:
            status = "atrasado"
        rows.append({"aluno": a, "pag": p, "status": status})

    atrasados_n = sum(1 for r in rows if r["status"] == "atrasado")
    return render_template(
        "financeiro.html", active="financeiro",
        rows=rows, mes=mes, mes_nome=mes_label(mes),
        esperado=esperado, recebido=recebido,
        pendente=esperado - recebido, atrasados_n=atrasados_n,
    )


def _relatorio_dados():
    con = get_db()
    meses = ultimos_meses(6)
    mes = mes_atual()
    entradas_mes, saidas_mes = [], []
    for m in meses:
        entradas_mes.append(con.execute(
            "SELECT COALESCE(SUM(valor), 0) AS s FROM pagamentos WHERE mes = ? AND status = 'pago'", (m,)
        ).fetchone()["s"])
        saidas_mes.append(con.execute(
            "SELECT COALESCE(SUM(valor), 0) AS s FROM despesas WHERE substr(data, 1, 7) = ?", (m,)
        ).fetchone()["s"])
    grafico = grafico_barras_mes(meses, entradas_mes, saidas_mes)

    entradas = sum(entradas_mes)
    saidas = sum(saidas_mes)
    entradas_mes_atual = entradas_mes[-1]
    saidas_mes_atual = saidas_mes[-1]
    saldo_mes = entradas_mes_atual - saidas_mes_atual
    saldo_geral = entradas - saidas

    categorias = con.execute(
        """SELECT COALESCE(NULLIF(categoria, ''), 'Geral') AS cat, SUM(valor) AS s
           FROM despesas WHERE substr(data, 1, 7) >= ? GROUP BY cat ORDER BY s DESC""",
        (meses[0],),
    ).fetchall()
    donut = grafico_donut(categorias)

    maiores_despesas = con.execute("SELECT * FROM despesas ORDER BY valor DESC LIMIT 5").fetchall()
    despesas = con.execute("SELECT * FROM despesas ORDER BY data DESC, id DESC LIMIT 60").fetchall()

    leads = con.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()
    total_leads = len(leads)
    leads_mes = sum(1 for l in leads if (l["data"] or "")[:7] == mes)
    convertidos = sum(1 for l in leads if l["status"] == "convertido")
    em_contato = sum(1 for l in leads if l["status"] in ("em contato", "proposta"))
    em_aberto = sum(1 for l in leads if l["status"] in ("novo", "em contato", "proposta"))
    taxa_conversao = round(convertidos * 100 / total_leads, 1) if total_leads else 0

    alunos_ativos = con.execute("SELECT COUNT(*) AS n FROM alunos WHERE ativo = 1").fetchone()["n"]
    novos_mes = con.execute(
        "SELECT COUNT(*) AS n FROM alunos WHERE substr(criado_em, 1, 7) = ?", (mes,)
    ).fetchone()["n"]
    recebido_geral = con.execute(
        "SELECT COALESCE(SUM(valor), 0) AS s FROM pagamentos WHERE status = 'pago'"
    ).fetchone()["s"]
    ticket_medio = round(recebido_geral / alunos_ativos, 2) if alunos_ativos else 0
    top_alunos = con.execute(
        """SELECT a.nome, COALESCE(SUM(p.valor), 0) AS v
           FROM pagamentos p JOIN alunos a ON a.id = p.aluno_id
           WHERE p.status = 'pago' GROUP BY a.id ORDER BY v DESC LIMIT 5"""
    ).fetchall()

    return dict(
        mes=mes, mes_nome=mes_label(mes), meses=meses,
        grafico=grafico, donut=donut,
        entradas_mes=entradas_mes, saidas_mes=saidas_mes,
        entradas=entradas, saidas=saidas, saldo_geral=saldo_geral,
        entradas_mes_atual=entradas_mes_atual, saidas_mes_atual=saidas_mes_atual, saldo_mes=saldo_mes,
        despesas=despesas, maiores_despesas=maiores_despesas,
        leads=leads, total_leads=total_leads, leads_mes=leads_mes,
        convertidos=convertidos, em_contato=em_contato, em_aberto=em_aberto, taxa_conversao=taxa_conversao,
        alunos_ativos=alunos_ativos, novos_mes=novos_mes, ticket_medio=ticket_medio, top_alunos=top_alunos,
    )


@app.route("/relatorios")
def relatorios():
    dados = _relatorio_dados()
    return render_template("relatorios.html", active="relatorios", **dados)


@app.route("/relatorios/imprimir")
def imprimir_relatorio():
    dados = _relatorio_dados()
    return render_template("imprimir_relatorio.html", **dados)


@app.route("/financeiro/despesa/novo", methods=["POST"])
def nova_despesa():
    con = get_db()
    descricao = request.form.get("descricao", "").strip()
    if descricao:
        con.execute(
            "INSERT INTO despesas (descricao, categoria, valor, data) VALUES (?, ?, ?, ?)",
            (descricao, request.form.get("categoria", "").strip(),
             num(request.form.get("valor", ""), 0) or 0,
             request.form.get("data", "").strip() or datetime.date.today().isoformat()),
        )
        con.commit()
        flash("Despesa registrada.", "success")
    return redirect(url_for("relatorios"))


@app.route("/financeiro/despesa/<int:despesa_id>/editar", methods=["POST"])
def editar_despesa(despesa_id):
    con = get_db()
    d = con.execute("SELECT * FROM despesas WHERE id = ?", (despesa_id,)).fetchone()
    if d:
        descricao = request.form.get("descricao", "").strip()
        if descricao:
            con.execute(
                "UPDATE despesas SET descricao = ?, categoria = ?, valor = ?, data = ? WHERE id = ?",
                (descricao, request.form.get("categoria", "").strip(),
                 num(request.form.get("valor", ""), 0) or 0,
                 request.form.get("data", "").strip() or d["data"], despesa_id),
            )
            con.commit()
            flash("Despesa atualizada.", "success")
    return redirect(url_for("relatorios"))


@app.route("/financeiro/despesa/<int:despesa_id>/excluir", methods=["POST"])
def excluir_despesa(despesa_id):
    con = get_db()
    con.execute("DELETE FROM despesas WHERE id = ?", (despesa_id,))
    con.commit()
    flash("Despesa excluída.", "info")
    return redirect(url_for("relatorios"))


@app.route("/financeiro/lead/novo", methods=["POST"])
def novo_lead():
    con = get_db()
    nome = request.form.get("nome", "").strip()
    if nome:
        status = request.form.get("status", "").strip() or "novo"
        if status not in STATUS_LEADS:
            status = "novo"
        con.execute(
            "INSERT INTO leads (nome, telefone, origem, status, valor_servico, observacoes, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (nome, request.form.get("telefone", "").strip(),
             request.form.get("origem", "").strip(), status,
             num(request.form.get("valor_servico", ""), None),
             request.form.get("observacoes", "").strip(),
             request.form.get("data", "").strip() or datetime.date.today().isoformat()),
        )
        con.commit()
        flash("Lead cadastrado.", "success")
    return redirect(url_for("relatorios"))


@app.route("/financeiro/lead/<int:lead_id>/editar", methods=["POST"])
def editar_lead(lead_id):
    con = get_db()
    l = con.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if l:
        nome = request.form.get("nome", "").strip()
        if nome:
            status = request.form.get("status", "").strip()
            if status not in STATUS_LEADS:
                status = l["status"]
            con.execute(
                "UPDATE leads SET nome = ?, telefone = ?, origem = ?, status = ?, valor_servico = ?, observacoes = ?, data = ? WHERE id = ?",
                (nome, request.form.get("telefone", "").strip(),
                 request.form.get("origem", "").strip(), status,
                 num(request.form.get("valor_servico", ""), None),
                 request.form.get("observacoes", "").strip(),
                 request.form.get("data", "").strip() or l["data"], lead_id),
            )
            con.commit()
            flash("Lead atualizado.", "success")
    return redirect(url_for("relatorios"))


@app.route("/financeiro/lead/<int:lead_id>/excluir", methods=["POST"])
def excluir_lead(lead_id):
    con = get_db()
    con.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    con.commit()
    flash("Lead excluído.", "info")
    return redirect(url_for("relatorios"))


@app.route("/financeiro/lead/<int:lead_id>/status", methods=["POST"])
def lead_status(lead_id):
    con = get_db()
    status = request.form.get("status", "").strip()
    if status in STATUS_LEADS:
        con.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id))
        con.commit()
        flash("Status do lead atualizado.", "info")
    return redirect(url_for("relatorios"))


@app.route("/aluno/<int:aluno_id>/treino/imprimir")
def imprimir_treino(aluno_id):
    a = get_aluno_or_404(aluno_id)
    con = get_db()
    treinos = con.execute(
        "SELECT * FROM treinos WHERE aluno_id = ? ORDER BY ordem, id", (aluno_id,)
    ).fetchall()
    exercicios = {}
    for t in treinos:
        exercicios[t["id"]] = con.execute(
            "SELECT * FROM exercicios WHERE treino_id = ? ORDER BY ordem, id", (t["id"],)
        ).fetchall()
    return render_template(
        "imprimir_treino.html", aluno=a, treinos=treinos, exercicios=exercicios
    )


@app.route("/aluno/<int:aluno_id>/dieta/imprimir")
def validar_dieta(aluno_id):
    """Valida a dieta salva antes do PDF: porções dentro das faixas, totais
    reais próximos das metas diárias e substituições com gramas.
    Devolve (avisos, reais, metas)."""
    con = get_db()
    metas = con.execute("SELECT * FROM metas_dieta WHERE aluno_id = ?", (aluno_id,)).fetchone()
    refeicoes = con.execute(
        "SELECT * FROM refeicoes WHERE aluno_id = ? ORDER BY ordem, id", (aluno_id,)
    ).fetchall()
    alim = montar_alimentos(con, refeicoes)
    avisos = []
    k = p = c = g = 0.0
    for rid, itens in alim.items():
        for x in itens:
            k += (x["kcal"] or 0) * (x["qtd"] or 0) / 100.0
            p += (x["proteinas"] or 0) * (x["qtd"] or 0) / 100.0
            c += (x["carbs"] or 0) * (x["qtd"] or 0) / 100.0
            g += (x["gorduras"] or 0) * (x["qtd"] or 0) / 100.0
            mn, ide, mx = _faixa_porcao(x)
            q = float(x["qtd"] or 0)
            if q > mx + 0.5:
                avisos.append(f"{x['nome']}: {round(q)} g ultrapassa o máximo ({round(mx)} g).")
            elif 0 < q < mn - 0.5:
                avisos.append(f"{x['nome']}: {round(q)} g abaixo do mínimo ({round(mn)} g).")
            # Verifica se substituições têm quantidades em gramas
            subs = x.get("subs") or []
            if not subs:
                avisos.append(f"{x['nome']}: sem substituições calculadas.")
            else:
                for s in subs:
                    if not s.get("quantidade_g"):
                        avisos.append(f"{x['nome']}: substituição '{s.get('alimento')}' sem quantidade em gramas.")
    reais = {"calorias": k, "proteinas": p, "carbs": c, "gorduras": g}
    alvo = {
        "calorias": (metas["kcal_diaria"] or 0) if metas else 0,
        "proteinas": (metas["proteinas"] or 0) if metas else 0,
        "carbs": (metas["carbs"] or 0) if metas else 0,
        "gorduras": (metas["gorduras"] or 0) if metas else 0,
    }
    if metas and alvo["calorias"]:
        tol_k = max(TOLERANCIAS_DIETA["kcal_pct"] * alvo["calorias"] / 100.0, 35.0)
        if abs(k - alvo["calorias"]) > tol_k:
            avisos.append(f"kcal totais: {round(k)} vs meta {round(alvo['calorias'])}.")
        if abs(p - alvo["proteinas"]) > TOLERANCIAS_DIETA["proteina"]:
            avisos.append(f"proteína total: {round(p)} g vs meta {round(alvo['proteinas'])} g.")
        if abs(c - alvo["carbs"]) > TOLERANCIAS_DIETA["carbo"]:
            avisos.append(f"carboidratos totais: {round(c)} g vs meta {round(alvo['carbs'])} g.")
        if abs(g - alvo["gorduras"]) > TOLERANCIAS_DIETA["gordura"]:
            avisos.append(f"gordura total: {round(g)} g vs meta {round(alvo['gorduras'])} g.")
    return avisos, reais, alvo


@app.route("/aluno/<int:aluno_id>/imprimir-dieta")
def imprimir_dieta(aluno_id):
    a = get_aluno_or_404(aluno_id)
    con = get_db()
    metas = con.execute("SELECT * FROM metas_dieta WHERE aluno_id = ?", (aluno_id,)).fetchone()
    refeicoes = con.execute(
        "SELECT * FROM refeicoes WHERE aluno_id = ? ORDER BY ordem, id", (aluno_id,)
    ).fetchall()
    totais = {
        "calorias": con.execute("SELECT COALESCE(SUM(calorias), 0) AS s FROM refeicoes WHERE aluno_id = ?", (aluno_id,)).fetchone()["s"],
        "proteinas": con.execute("SELECT COALESCE(SUM(proteinas), 0) AS s FROM refeicoes WHERE aluno_id = ?", (aluno_id,)).fetchone()["s"],
        "carbs": con.execute("SELECT COALESCE(SUM(carbs), 0) AS s FROM refeicoes WHERE aluno_id = ?", (aluno_id,)).fetchone()["s"],
        "gorduras": con.execute("SELECT COALESCE(SUM(gorduras), 0) AS s FROM refeicoes WHERE aluno_id = ?", (aluno_id,)).fetchone()["s"],
    }
    alim = montar_alimentos(con, refeicoes)
    avisos, reais, alvo = validar_dieta(aluno_id)
    if avisos:
        flash("Dieta com ajustes sugeridos antes da impressão:", "warn")
        for av in avisos:
            flash(av, "warn")
    return render_template(
        "imprimir_dieta.html", aluno=a, metas=metas, refeicoes=refeicoes,
        totais=totais, alim=alim, avisos=avisos, reais=reais, alvo=alvo,
    )


@app.route("/aluno/<int:aluno_id>/gerar")
def gerar_plano(aluno_id):
    a = get_aluno_or_404(aluno_id)
    c = calcular_plano(a)
    rot = analisar_rotina(a["rotina"] or "")
    con = get_db()
    refeicoes = [
        (nome, hora, frac, round(c["meta_kcal"] * frac))
        for nome, hora, frac in REFEICOES_MODELO
    ]
    if rot and rot["tem_tempos"]:
        refeicoes = [
            (nome, rot["horarios"].get(nome, hora), frac, round(c["meta_kcal"] * frac))
            for nome, hora, frac in REFEICOES_MODELO
        ]
    template = montar_template(a)
    treinos = selecionar_exercicios(con, template)
    semana = semana_para_aluno(a, len(treinos))
    lib = [dict(r) for r in con.execute("SELECT * FROM exercicios_padrao ORDER BY grupo, nome").fetchall()]
    return render_template(
        "gerar.html", active="alunos", aba="gerar", aluno=a, c=c,
        refeicoes=refeicoes, treinos=treinos, lib=lib, rot=rot, semana=semana,
    )


@app.route("/aluno/<int:aluno_id>/rotina", methods=["POST"])
def analisar_rotina_aluno(aluno_id):
    a = get_aluno_or_404(aluno_id)
    texto = request.form.get("rotina", "").strip()
    con = get_db()
    con.execute("UPDATE alunos SET rotina = ? WHERE id = ?", (texto or None, aluno_id))
    res = analisar_rotina(texto)
    novas_dias = None
    if res:
        if 3 <= res["qtd_dias"] <= 6:
            novas_dias = res["qtd_dias"]
        elif res["frequencia"]:
            novas_dias = res["frequencia"]
    if novas_dias and novas_dias != (a["dias_treino"] or 3):
        con.execute("UPDATE alunos SET dias_treino = ? WHERE id = ?", (novas_dias, aluno_id))
    con.commit()
    partes = []
    if res and 3 <= res["qtd_dias"] <= 6:
        partes.append("Dias de treino: " + ", ".join(res["dias_ordem"]))
    elif novas_dias:
        partes.append(f"Frequência detectada: {novas_dias} dias/semana")
    else:
        partes.append("dias de treino não identificados no texto (mantido)")
    if res and res["tem_tempos"]:
        partes.append("horários das refeições ajustados à rotina")
    else:
        partes.append("horários de refeição não citados (padrões mantidos)")
    flash("Rotina analisada: " + ". ".join(partes) + ".", "success")
    return redirect(url_for("gerar_plano", aluno_id=aluno_id))


@app.route("/aluno/<int:aluno_id>/parametros", methods=["POST"])
def parametros_plano(aluno_id):
    get_aluno_or_404(aluno_id)
    con = get_db()
    con.execute(
        """UPDATE alunos
           SET altura_cm = ?, peso_atual = ?, fator_atividade = ?, objetivo_meta = ?,
               ajuste_meta = ?, proteina_kg = ?, sexo_formula = ?, dias_treino = ?, foco_gluteo = ?,
               nascimento = ?
           WHERE id = ?""",
        (
            num(request.form.get("altura_cm", "")),
            num(request.form.get("peso_atual", "")),
            num(request.form.get("fator_atividade", ""), 1.55) or 1.0,
            request.form.get("objetivo_meta", "emagrecer"),
            num(request.form.get("ajuste_meta", "")),
            num(request.form.get("proteina_kg", ""), 2.0) or 0.5,
            request.form.get("sexo_formula", "M"),
            min(max(intnum(request.form.get("dias_treino", ""), 3) or 1, 1), 6),
            1 if request.form.get("foco_gluteo") else 0,
            request.form.get("nascimento", "") or None,
            aluno_id,
        ),
    )
    con.commit()
    flash("Parâmetros atualizados.", "success")
    return redirect(url_for("gerar_plano", aluno_id=aluno_id))


@app.route("/aluno/<int:aluno_id>/aplicar-dieta", methods=["POST"])
def aplicar_dieta(aluno_id):
    a = get_aluno_or_404(aluno_id)
    c = calcular_plano(a)
    con = get_db()
    con.execute("DELETE FROM refeicoes WHERE aluno_id = ?", (aluno_id,))
    con.execute("DELETE FROM metas_dieta WHERE aluno_id = ?", (aluno_id,))
    con.execute(
        """INSERT INTO metas_dieta (aluno_id, kcal_diaria, proteinas, carbs, gorduras, observacoes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            aluno_id,
            round(c["meta_kcal"]), round(c["proteina"]), round(c["carbo"]), round(c["gordura"]),
            f"Meta calculada pelo assistente (Harris-Benedict, {OBJETIVOS_META.get(c['objetivo'], c['objetivo']).lower()}, ajuste {c['ajuste']:+.0f}%). Preencha os alimentos de cada refeição.",
        ),
    )
    rot = analisar_rotina(a["rotina"] or "")
    horarios = {}
    for nome, hora, frac in REFEICOES_MODELO:
        horarios[nome] = rot["horarios"].get(nome, hora) if rot else hora
    for i, (nome, hora, frac) in enumerate(REFEICOES_MODELO, start=1):
        kF, pF, cF, gF = DISTRIBUICAO_REFEICOES.get(nome, (frac, frac, frac, frac))
        cur = con.execute(
            """INSERT INTO refeicoes
               (aluno_id, nome, horario, calorias, proteinas, carbs, gorduras, descricao, ordem)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                aluno_id, nome, horarios[nome],
                round(c["meta_kcal"] * kF),
                round(c["proteina"] * pF),
                round(c["carbo"] * cF),
                round(c["gordura"] * gF),
                "", i,
            ),
        )
    con.commit()
    refs = con.execute(
        "SELECT * FROM refeicoes WHERE aluno_id = ? ORDER BY ordem, id", (aluno_id,)
    ).fetchall()
    dieta_gerada = _gerar_dieta_automaticamente(con, aluno_id, c)

    if dieta_gerada and dieta_gerada.get("refeicoes"):
        por_nome = {r["nome"]: r for r in refs}
        for refeicao in dieta_gerada["refeicoes"]:
            r = por_nome.get(refeicao.get("nome"))
            if not r:
                continue
            totais = refeicao.get("totais", {})
            con.execute(
                "UPDATE refeicoes SET calorias = ?, proteinas = ?, carbs = ?, gorduras = ? WHERE id = ?",
                (
                    round(float(totais.get("kcal", 0.0) or 0.0)),
                    round(float(totais.get("proteinas", 0.0) or 0.0)),
                    round(float(totais.get("carbs", 0.0) or 0.0)),
                    round(float(totais.get("gorduras", 0.0) or 0.0)),
                    r["id"],
                ),
            )
            pares = []
            mapa_nome = {str(it["nome"]).strip().lower(): it for it in con.execute("SELECT * FROM alimentos WHERE ativo = 1").fetchall()}
            for item in refeicao.get("alimentos", []):
                nome = str(item.get("nome") or "").strip().lower()
                alimento = mapa_nome.get(nome)
                if not alimento:
                    continue
                qtd = float(item.get("quantidade") or item.get("qtd") or 0.0)
                if qtd <= 0:
                    continue
                pares.append((int(alimento["id"]), max(0, round(float(qtd), 1))))
            if not pares:
                nomes = _selecionar_alimentos(con, r["nome"], aluno_id)
                ids = []
                for pn in nomes:
                    row = con.execute(
                        "SELECT id FROM alimentos WHERE nome = ? ORDER BY id LIMIT 1", (pn,)
                    ).fetchone()
                    if row:
                        ids.append(row["id"])
                pares = _pares_automaticos(
                    con,
                    [(aid, 0) for aid in ids],
                    (r["calorias"] or 0, r["proteinas"] or 0, r["carbs"] or 0, r["gorduras"] or 0),
                )
            gravar_alimentos(con, r["id"], pares)
    else:
        for r in refs:
            nomes = _selecionar_alimentos(con, r["nome"], aluno_id)
            ids = []
            for pn in nomes:
                row = con.execute(
                    "SELECT id FROM alimentos WHERE nome = ? ORDER BY id LIMIT 1", (pn,)
                ).fetchone()
                if row:
                    ids.append(row["id"])
            pares = _pares_automaticos(
                con,
                [(aid, 0) for aid in ids],
                (r["calorias"] or 0, r["proteinas"] or 0, r["carbs"] or 0, r["gorduras"] or 0),
            )
            gravar_alimentos(con, r["id"], pares)
    con.commit()
    flash("Dieta gerada e aplicada ao aluno.", "success")
    return redirect(url_for("dieta", aluno_id=aluno_id))


@app.route("/aluno/<int:aluno_id>/aplicar-treino", methods=["POST"])
def aplicar_treino(aluno_id):
    a = get_aluno_or_404(aluno_id)
    con = get_db()
    template = montar_template(a)
    treinos = selecionar_exercicios(con, template)
    semana = semana_para_aluno(a, len(treinos))
    con.execute(
        "DELETE FROM exercicios WHERE treino_id IN (SELECT id FROM treinos WHERE aluno_id = ?)",
        (aluno_id,),
    )
    con.execute("DELETE FROM treinos WHERE aluno_id = ?", (aluno_id,))
    for i, t in enumerate(treinos, start=1):
        cur = con.execute(
            "INSERT INTO treinos (aluno_id, nome, dia_semana, notas, ordem) VALUES (?, ?, ?, ?, ?)",
            (aluno_id, t["nome"], semana[i - 1] or "", "", i),
        )
        for j, e in enumerate(t["itens"], start=1):
            con.execute(
                """INSERT INTO exercicios (treino_id, nome, series, repeticoes, carga, descanso, grupo, ordem, rir, observacoes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (cur.lastrowid, e["nome"], e["series"], e["repeticoes"], "", e["descanso"], e["grupo"], j,
                 e["rir"], e["observacoes"]),
            )
    con.commit()
    flash("Treino gerado e aplicado ao aluno.", "success")
    return redirect(url_for("treino", aluno_id=aluno_id))


@app.route("/exercicio-padrao/novo", methods=["POST"])
def novo_exercicio_padrao():
    nome = request.form.get("nome", "").strip()
    grupo = request.form.get("grupo", "").strip()
    aluno_id = intnum(request.form.get("aluno_id"))
    if nome and grupo:
        con = get_db()
        con.execute(
            """INSERT INTO exercicios_padrao
               (nome, grupo, grande, series, repeticoes, descanso, secundarios, padrao,
                equipamento, nivel, rir, observacoes, ativo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                nome, grupo,
                1 if request.form.get("grande") else 0,
                min(max(intnum(request.form.get("series", ""), 2) or 1, 1), 5),
                request.form.get("repeticoes", "").strip() or "10-12",
                request.form.get("descanso", "").strip() or "90s",
                request.form.get("secundarios", "").strip(),
                request.form.get("padrao", "").strip(),
                request.form.get("equipamento", "").strip(),
                request.form.get("nivel", "").strip(),
                request.form.get("rir", "").strip() or "1-2",
                request.form.get("observacoes", "").strip(),
            ),
        )
        con.commit()
        flash("Exercício adicionado à biblioteca.", "success")
    return redirect(url_for("gerar_plano", aluno_id=aluno_id)) if aluno_id else redirect(url_for("alunos"))


@app.route("/exercicio-padrao/<int:ex_id>/editar", methods=["POST"])
def editar_exercicio_padrao(ex_id):
    aluno_id = intnum(request.form.get("aluno_id"))
    nome = request.form.get("nome", "").strip()
    con = get_db()
    if nome:
        con.execute(
            """UPDATE exercicios_padrao SET nome = ?, grupo = ?, grande = ?, series = ?, repeticoes = ?,
               descanso = ?, secundarios = ?, padrao = ?, equipamento = ?, nivel = ?, rir = ?,
               observacoes = ?, ativo = ? WHERE id = ?""",
            (
                nome,
                request.form.get("grupo", "").strip(),
                1 if request.form.get("grande") else 0,
                min(max(intnum(request.form.get("series", ""), 2) or 1, 1), 5),
                request.form.get("repeticoes", "").strip() or "10-12",
                request.form.get("descanso", "").strip() or "90s",
                request.form.get("secundarios", "").strip(),
                request.form.get("padrao", "").strip(),
                request.form.get("equipamento", "").strip(),
                request.form.get("nivel", "").strip(),
                request.form.get("rir", "").strip() or "1-2",
                request.form.get("observacoes", "").strip(),
                1 if request.form.get("ativo") else 0,
                ex_id,
            ),
        )
        con.commit()
        flash("Exercício da biblioteca atualizado.", "success")
    return redirect(url_for("gerar_plano", aluno_id=aluno_id)) if aluno_id else redirect(url_for("alunos"))


@app.route("/exercicio-padrao/<int:ex_id>/excluir", methods=["POST"])
def excluir_exercicio_padrao(ex_id):
    aluno_id = intnum(request.form.get("aluno_id"))
    con = get_db()
    con.execute("DELETE FROM exercicios_padrao WHERE id = ?", (ex_id,))
    con.commit()
    flash("Exercício removido da biblioteca.", "info")
    return redirect(url_for("gerar_plano", aluno_id=aluno_id)) if aluno_id else redirect(url_for("alunos"))


@app.errorhandler(404)
def nao_encontrado(e):
    return render_template("404.html", active=""), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)