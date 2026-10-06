"""Redesenho dos Bastidores, passo 3 (06/10): a sub-aba Corpo do Por dentro.

PLANO_WEBAPP, "Redesenho dos Bastidores — plano": cada informação vira desenho com uma linha curta centralizada
embaixo (nada de "rótulo à esquerda, texto à direita"). Quatro seções:

* **Agora:** Energia, Saciedade e Mal-estar (barra âmbar com a palavra).
* **Sono:** a faixa do dia de 18:00 a 18:00 com o trecho dormido (a noite e o cochilo) e "Dormiu por volta de …".
* **Ciclo:** a fase, "Dia 7 de 28", os 28 quadradinhos e quanto falta pro próximo marco.
* **Intimidade:** o velocímetro (ponteiro = vontade, arco de dentro = excitação, com o "desde"), as etiquetas do que
  puxa a vontade (os termos do `EmotionEngine._libido`) e o calendário do mês com os orgasmos e a menstruação.

Só tela: ela nunca lê nada daqui, e um erro numa seção some com a seção (nunca derruba o painel).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ponteiro do velocímetro: os mesmos cortes do LIBIDO_WORDS do emotion.py
VONTADE = ((0.35, "Sem vontade"), (0.55, "Aberta"), (0.72, "Querendo"), (0.85, "Precisando"), (9, "Desesperada"))
# arco de dentro: os degraus do intimacy.py (ACTIVE_ON 0,45 entra no modo, HOT_AT 0,70 explícito)
EXCITACAO = ((0.30, "Aquecendo"), (0.45, "Excitada"), (0.70, "Molhada"), (0.85, "No limite"), (9, "Quase lá"))
FASE_TELA = {"menstrual": "Menstruada", "folicular": "Fase folicular", "ovulatoria": "Período fértil",
             "lutea_inicial": "Fase lútea", "tpm": "Pré-menstrual"}
MENSTRUACAO, FERTIL = range(1, 6), range(12, 17)
MESES = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
         "Novembro", "Dezembro")
ETIQUETA_MIN, ETIQUETAS_MAX = 0.03, 4       # o que mexe menos que isso na vontade não vira etiqueta


def _palavra(v: float, escada) -> str:
    return next(w for lim, w in escada if v < lim)


def _hm(at: datetime) -> str:
    return f"{at:%H:%M}"


def _aprox(td: timedelta) -> timedelta:
    """Duração arredondada a 5 min (a linha diz "por volta de")."""
    return timedelta(minutes=5 * round(td.total_seconds() / 300))


def _em(n: int, um: str, varios: str) -> str:
    return um if n == 1 else varios.format(n=n)


# ------------------------------------------------------------------- agora --
def mal_estar(valor: float, why: str) -> dict:
    """Barra âmbar; a palavra é a primeira coisa do `discomfort_why` ("cólica leve, dor de cabeça" → "Cólica leve").
    A fase não repete (a seção Ciclo está logo abaixo): "inchada da TPM" → "Inchada"."""
    txt = (why or "").replace("menstruada, ", "").replace(" da TPM", "")
    txt = txt.split(" (")[0].split(",")[0].strip()
    return {"label": "Mal-estar", "value": round(valor, 3) if txt else 0.0,
            "word": (txt[:1].upper() + txt[1:]) if txt else "Nenhum"}


# -------------------------------------------------------------------- sono --
def sono(db, now: datetime, dormindo: bool) -> Optional[dict]:
    """A noite mais recente que já começou (e o cochilo do dia seguinte) numa faixa de 18:00 a 18:00."""
    from agenda import aprox, duracao
    from sleep_plan import SleepPlan
    plan = SleepPlan(db)
    noite = now.date()
    while plan.bed(noite) > now:
        noite -= timedelta(days=1)
    ini = datetime.combine(noite, time(18, 0))
    fim = ini + timedelta(days=1)
    pos = lambda at: round(100 * min(1.0, max(0.0, (at - ini) / (fim - ini))), 2)
    deitou, levanta = plan.bed(noite), plan.wake(noite + timedelta(days=1))
    # acordada no meio da noite: o trecho pintado para na hora em que acordou (o micro-despertar do plano)
    acordou = next((ini for ini, fim, _ in plan.micro_wakes(noite) if ini <= now < fim), None) \
        if not dormindo and now < levanta else None
    ate = acordou or min(levanta, now)
    trechos = [{"ini": pos(deitou), "fim": pos(ate),
                "rotulo": f"{aprox(deitou)} – {aprox(ate) if acordou or levanta <= now else 'agora'}"}]
    cochilo = plan.nap(noite + timedelta(days=1))
    if cochilo and cochilo[0] <= now:
        trechos.append({"ini": pos(cochilo[0]), "fim": pos(min(cochilo[1], now)), "cochilo": True,
                        "rotulo": aprox(cochilo[0])})
    if cochilo and cochilo[0] <= now < cochilo[1]:
        linha = f"Cochilando há {duracao(_aprox(now - cochilo[0]))}"
    elif now < levanta:
        linha = (f"Dormindo há {duracao(_aprox(now - deitou))}" if dormindo
                 else "Acordou no meio da noite")          # micro-despertar: na cama, com o celular
    else:
        linha = f"Dormiu por volta de {duracao(_aprox(levanta - deitou))}"
    return {"trechos": trechos, "agora": pos(now) if ini <= now < fim else None, "linha": linha,
            "eixo": ["18:00", "00:00", "06:00", "12:00", "18:00"]}


# ------------------------------------------------------------------- ciclo --
def ciclo_inicio(db) -> Optional[date]:
    with db.get_connection() as conn:
        row = conn.execute("SELECT data_inicio_ciclo FROM ciclo_biologico ORDER BY id DESC LIMIT 1").fetchone()
    return date.fromisoformat(row["data_inicio_ciclo"][:10]) if row else None


def dia_do_ciclo(inicio: date, dia: date) -> int:
    from cycle import CYCLE_LENGTH
    return (dia - inicio).days % CYCLE_LENGTH + 1


def _proximo_marco(dia: int, total: int) -> str:
    """O que vem a seguir no ciclo, em dias."""
    em = lambda n, o_que, amanha: amanha if n == 1 else f"{o_que} em {n} dias"
    if dia in MENSTRUACAO:
        n = MENSTRUACAO[-1] - dia
        return "Último dia de menstruação" if n == 0 else em(n, "Menstruação acaba", "Menstruação acaba amanhã")
    if dia < FERTIL[0]:
        return em(FERTIL[0] - dia, "Período fértil", "Período fértil amanhã")
    if dia in FERTIL:
        n = FERTIL[-1] - dia
        return "Último dia do período fértil" if n == 0 else em(n, "Período fértil acaba", "Período fértil acaba amanhã")
    return em(total + 1 - dia, "Menstruação", "Menstruação amanhã")


def ciclo(db, now: datetime) -> Optional[dict]:
    from cycle import CYCLE_LENGTH, PHASES
    inicio = ciclo_inicio(db)
    if not inicio:
        return None
    dia = dia_do_ciclo(inicio, now.date())
    fase = next((k for k, p in PHASES.items() if dia in p["days"]), "")
    tipo = lambda d: "menstruacao" if d in MENSTRUACAO else "fertil" if d in FERTIL else "normal"
    return {"fase": FASE_TELA.get(fase, ""), "dia": f"Dia {dia} de {CYCLE_LENGTH}",
            "dias": [{"tipo": tipo(d), "hoje": d == dia, "futuro": d > dia} for d in range(1, CYCLE_LENGTH + 1)],
            "linha": _proximo_marco(dia, CYCLE_LENGTH)}


# -------------------------------------------------------------- intimidade --
def _horas(h: float) -> str:
    if h < 1:
        n = max(1, round(h * 60))
        return _em(n, "1 minuto", "{n} minutos")
    if h < 48:
        return _em(int(h), "1 hora", "{n} horas")
    return f"{int(h // 24)} dias"


def etiquetas(t: dict, fase: str, mal: dict) -> list[dict]:
    """O que mais empurrou a vontade agora, pra cima ou pra baixo (os termos do `_libido`, mesma conta)."""
    if not t:
        return []
    desde = t.get("desde")
    nomes = {
        "ciclo": FASE_TELA.get(fase, ""),
        "sem_gozar": f"{_horas(desde)} sem gozar" if desde is not None else "",
        "gozou": f"Gozou há {_horas(desde)}" if desde is not None else "",
        "desejo": ("Desejo pelo Patrick", "Pouco desejo pelo Patrick"),
        "humor": ("Bom humor", "Mau humor"),
        "energia": ("Disposição", "Cansaço"),
        "saudade": "Saudade do Patrick",
        "mal_estar": mal["word"] if mal["word"] != "Nenhum" else "Mal-estar",
        "magoa": "Mágoa",
        "patrick": "Carinho do Patrick",
    }   # a excitação não vira etiqueta: o arco de dentro já mostra (Patrick, 06/10)
    out = []
    for chave, nome in nomes.items():
        efeito = float(t.get(chave) or 0.0)
        if abs(efeito) < ETIQUETA_MIN:
            continue
        txt = nome if isinstance(nome, str) else nome[0 if efeito > 0 else 1]
        if txt:
            out.append((abs(efeito), {"texto": txt, "sobe": efeito > 0}))
    out.sort(key=lambda x: -x[0])
    return [e for _, e in out[:ETIQUETAS_MAX]]


def _como(o: dict) -> str:
    """'com o Patrick, por mensagem', 'sozinha, no banho, com o Lush', 'com o Patrick, pelo Lovense, na academia'."""
    brinq = " e o ".join(b.capitalize() for b in o.get("brinquedos") or [])
    if o.get("com") == "patrick":
        partes = ["com o Patrick", {"sexting": "por mensagem", "lovense": "pelo Lovense"}.get(o.get("como"), "")]
        if o.get("publico") and o.get("onde"):
            partes.append(o["onde"])
    else:
        partes = ["sozinha", o.get("onde") or {"antes de dormir": "antes de dormir", "em casa": "em casa",
                                               "fora de casa": "fora de casa"}.get(o.get("como"), "")]
        if brinq:
            partes.append(f"com o {brinq}")
    return ", ".join(p for p in partes if p)


def orgasmos(db, desde: datetime, ate: datetime) -> list[dict]:
    """Do histórico (passo 1) e, de antes dele, as duas últimas vezes que o mundo guardava
    (`intimacy_state.climax_at` com o Patrick, `libido_release_at` sozinha), sem repetir o mesmo gozo."""
    import bastidores_hist
    from emotion import RELEASE_KEY
    regs = bastidores_hist.lista(db, "orgasmo", desde, ate)
    legado = []
    try:
        with db.get_connection() as conn:
            row = conn.execute("SELECT climax_at FROM intimacy_state WHERE id=1").fetchone()
        if row and row["climax_at"]:
            legado.append((datetime.fromisoformat(row["climax_at"]), "patrick"))
    except Exception:
        logger.debug("corpo.orgasmos.climax", exc_info=True)
    raw = db.get_estado_relacional(RELEASE_KEY)
    if raw:
        try:
            legado.append((datetime.fromisoformat(raw), "sozinha"))
        except (TypeError, ValueError):
            pass
    for em, com in legado:
        if desde <= em <= ate and not any(abs(r["em"] - em) <= bastidores_hist.DUPLICADO for r in regs):
            regs.append({"em": em, "com": com, "como": ""})
    return sorted(regs, key=lambda r: r["em"])


def _ultimo_txt(o: dict, now: datetime) -> str:
    quem = "com o Patrick" if o["com"] == "patrick" else "sozinha"
    dias = (now.date() - o["em"].date()).days
    if dias == 0:
        quando = f"hoje às {_hm(o['em'])}"
    elif dias == 1:
        quando = f"ontem às {_hm(o['em'])}"
    elif o["em"].month == now.month and o["em"].year == now.year:
        quando = f"dia {o['em'].day}"
    else:
        quando = f"{o['em'].day} de {MESES[o['em'].month - 1].lower()}"
    return f"Último orgasmo: {quando}, {quem}"


def calendario(db, now: datetime) -> dict:
    """O mês como app de ciclo: coração com o Patrick, bolinha sozinha, menstruação pintada (prevista tracejada)."""
    ini = now.date().replace(day=1)
    prox = (ini + timedelta(days=32)).replace(day=1)
    regs = orgasmos(db, datetime.combine(ini - timedelta(days=60), time(0)), now)
    do_dia: dict = {}
    for o in regs:
        if o["em"].date() >= ini:
            do_dia.setdefault(o["em"].day, []).append(o)
    inicio = ciclo_inicio(db)
    dias = []
    d = ini
    while d < prox:
        mens = None
        if inicio and dia_do_ciclo(inicio, d) in MENSTRUACAO:
            mens = "prevista" if d > now.date() else "real"
        os_ = do_dia.get(d.day, [])
        dias.append({"n": d.day, "hoje": d == now.date(), "futuro": d > now.date(), "menstruacao": mens,
                     "patrick": any(o["com"] == "patrick" for o in os_),
                     "sozinha": any(o["com"] != "patrick" for o in os_),
                     "detalhes": [f"{_hm(o['em'])}, {_como(o)}" for o in os_]})
        d += timedelta(days=1)
    return {"mes": MESES[ini.month - 1], "vazios": (ini.weekday() + 1) % 7,     # semana começa no domingo
            "dias": dias, "ultimo": _ultimo_txt(regs[-1], now) if regs else ""}


def intimidade(db, now: datetime, panel: dict, mal: dict) -> dict:
    import bastidores_hist
    libido, exc = float(panel.get("libido") or 0.0), float(panel.get("excitation") or 0.0)
    excitacao = None
    if exc >= bastidores_hist.ACESA:
        u = bastidores_hist.ultimo(db, "excitacao", now)
        recente = u and now - u["em"] <= timedelta(hours=6)
        excitacao = {"valor": round(exc, 3), "palavra": _palavra(exc, EXCITACAO),
                     "desde": _hm(u["em"]) if recente else "",
                     "origem": (u.get("origem") if recente else "") or "conversa"}
    return {"vontade": {"valor": round(libido, 3), "palavra": _palavra(libido, VONTADE),
                        "cortes": [lim for lim, _ in VONTADE[:-1]]},
            "excitacao": excitacao,
            "etiquetas": etiquetas(panel.get("libido_termos") or {}, panel.get("cycle_phase") or "", mal),
            "calendario": calendario(db, now)}


# ------------------------------------------------------------------- tudo --
def corpo_view(db, now: datetime, panel: dict, body: list[dict], dormindo: bool) -> dict:
    """`body` é o Corpo já em palavras de tela (`webapp_server.emocao_view`): Energia, Saciedade, Excitação."""
    mal = mal_estar(float(panel.get("discomfort") or 0.0), panel.get("discomfort_why") or "")
    out: dict = {"agora": [b for b in body if b["label"] in ("Energia", "Saciedade")] + [mal]}
    for nome, fn in (("sono", lambda: sono(db, now, dormindo)), ("ciclo", lambda: ciclo(db, now)),
                     ("intimidade", lambda: intimidade(db, now, panel, mal))):
        try:
            out[nome] = fn()
        except Exception:
            logger.exception("webapp.corpo.%s", nome)
            out[nome] = None
    return out
