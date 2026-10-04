"""Bastidores → Por dentro: o que vai além das barras (Patrick, 28/09, revisão aba a aba no celular).

"O Sentindo agora é a pior parte da aba, e tá faltando muita coisa da Marina." O painel só mostrava os
sentimentos que ainda não esfriaram (meia-vida de 1h30 a 8h), então de manhã quase tudo tinha sumido.
Aqui entram, com dados que o mundo já tem:
- **Hoje por dentro** (`diario_view`): tudo o que ela sentiu no dia, com hora, mesmo o que já passou. O dia
  vira às 5h (a madrugada antes de acordar ainda é a noite anterior); se hoje ainda está vazio, mostra o de
  ontem ("Ontem por dentro").
- **Na cabeça** (`cabeca_view`): o que vem pela frente e a vontade dela de ir — a mesma conta da agenda viva
  (`agenda_viva.Disposicao`) —, mais entregas da faculdade e trabalhos. Dormindo ou longe da hora ela ainda
  não pensou nisso: aparece sem estado nem barra.
- **Vocês dois** (`voces_linhas`): quando foi a última conversa e o que está pendente entre vocês.
Tudo o mais curto possível, com o detalhe indo pro lado (Patrick): título | quando; estado | barra | detalhe.
Os dois em 3ª pessoa (04/10, catálogo leva 2, regra 6: "o Patrick", nunca "você"); o motivo sai de
`webapp_server.motivo_tela`. Textos da tela decididos no catálogo, leva 2 (04/10): título no infinitivo (regra 12),
estado em uma palavra (regra 10).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

VIRA_O_DIA = 5                    # 28/09 (Patrick): a madrugada antes de acordar conta como a noite anterior
DIAS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
DIAS_LONGOS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
QUER_DESISTIR = {"aula": "Quer faltar", "academia": "Quer pular", "milo": "Quer adiar", "role": "Quer desmarcar",
                 "mercado_semana": "Quer adiar"}
ORIGEM = {"vontade": "Espontânea", "conversa": "Combinada", "emenda": "Emendada"}
RITMO = {"adiantada": "Adiantado", "normal": "Em dia", "ultima_hora": "Apertado"}
FREELA = {"casting": "Casting", "prova": "Prova de roupa", "job": "Job"}
FOTO = {"unhas": "Foto das unhas", "cabelo": "Foto do cabelo", "intimo": "Foto do banho"}
# o fator da agenda viva que mais pesou, curto pra coluna da direita
FATOR = {"sono": "Dormiu mal", "tedio": "Entediada", "alegria": "Empolgada", "desabafo": "Quer desabafar",
         "espairecer": "Espairecer", "descarregar": "Descarregar", "remedio": "Precisa de remédio", "tpm": "TPM",
         "chuva": "Chovendo", "grana": "Sem grana", "amigos": "Com amigos", "chateada": "Chateada com o Patrick"}
PENSA_ANTES_H = 4.0               # a agenda viva repensa até ~4 h antes; mais longe ela ainda não pensou
DETALHE_MAX = 18


def dia_logico(at: datetime) -> date:
    return (at - timedelta(hours=VIRA_O_DIA)).date()


def hora(at: datetime) -> str:
    return f"{at.hour}h{at.minute:02d}" if at.minute else f"{at.hour}h"


def quando(at: datetime, now: datetime) -> str:
    """'há 20 minutos', 'hoje, 14h', 'ontem, 22h01', 'sáb, 18h', '12/09'."""
    seg = (now - at).total_seconds()
    if 0 <= seg < 60:
        return "agora"
    if 0 <= seg < 3600:
        n = int(seg // 60)
        return f"há {n} minuto{'s' if n > 1 else ''}"           # 04/10 (catálogo, regra 2): por extenso
    dias = (now.date() - at.date()).days
    if dias == 0:
        return f"hoje, {hora(at)}"
    if dias == 1:
        return f"ontem, {hora(at)}"
    if 1 < dias < 7:
        return f"{DIAS[at.weekday()]}, {hora(at)}"
    return f"{at:%d/%m}"


def adiante(at: datetime, now: datetime) -> str:
    """Pra frente: 'hoje, 9h', 'amanhã, 7h', 'qui, 14h'."""
    dias = (at.date() - now.date()).days
    dia = "hoje" if dias == 0 else "amanhã" if dias == 1 else DIAS[at.weekday()]
    return f"{dia}, {hora(at)}"


def _curto(txt: str, n: int = DETALHE_MAX) -> str:
    txt = (txt or "").strip()
    return txt if len(txt) <= n else txt[:n].rsplit(" ", 1)[0] + "…"


def materia(nome: str) -> str:
    """'Projeto: Projetar em Sociedade' → 'Projeto'; 'Práticas Experimentais VI' → 'Práticas VI'."""
    nome = nome.split(":")[0].strip()
    partes = nome.split()
    if len(nome) > 16 and len(partes) > 1 and re.fullmatch(r"[IVX]+", partes[-1]):
        return f"{partes[0]} {partes[-1]}"
    return _curto(nome, 16)


def _sentimento(word: str, target: Optional[str]) -> str:
    from webapp_server import sentimento_tela
    return sentimento_tela(word, target)


# ------------------------------------------------------------- Hoje por dentro --
def diario_view(db, now: datetime) -> dict:
    from emotion import EmotionEngine
    from webapp_server import motivo_tela
    hoje = dia_logico(now)
    eng = EmotionEngine(db)

    def do_dia(d: date) -> list[dict]:
        ini = datetime.combine(d, time(VIRA_O_DIA))
        return eng.day_log(ini, min(now, ini + timedelta(days=1)))

    itens, titulo = do_dia(hoje), "Hoje por dentro"
    if not itens:
        itens, titulo = do_dia(hoje - timedelta(days=1)), "Ontem por dentro"
    return {"titulo": titulo,
            "itens": [{"hora": f"{x['at']:%H:%M}", "texto": _sentimento(x["word"], x["target"]),
                       **motivo_tela(x["cause"], x["target"] or "")} for x in itens]}


# ------------------------------------------------------------------ Na cabeça --
def _titulo_agenda(it: dict) -> tuple[str, str]:
    """(título curto, detalhe) de um item da agenda viva."""
    tipo = it["tipo"]
    if tipo == "aula":
        nomes = [materia(b["display_name"]) for b in it.get("blocos") or []]
        if len(nomes) > 1:
            return f"Aula de {nomes[0]}", f"e +{len(nomes) - 1}"       # 04/10 (Patrick); layout depois do soak
        return (f"Aula de {nomes[0]}" if nomes else "Aula"), ""
    if tipo == "milo":
        return "Passear com o Milo", ""
    if tipo == "academia":
        return "Treinar na academia", ""
    if tipo == "mercado_semana":
        return "Fazer compras no mercado", ""
    lugar = re.search(r"\b(?:no|na|em) ([A-ZÁÉÍÓÚ][^,;(]*)$", it["texto"])
    if tipo == "role" and it.get("com"):
        from social_day import short_name
        return f"Sair com {short_name(it['com'][0])}", _curto(lugar.group(1)) if lugar else ""
    if lugar:
        return _curto(it["texto"][:lugar.start()].strip(), 24), _curto(lugar.group(1))
    return _curto(it["texto"], 24), ""


def _fator(chave: str, texto: str) -> str:
    from webapp_server import cap
    if chave in FATOR:
        return FATOR[chave]
    return _curto(cap(re.sub(r"\s+da TPM\b", "", texto)))


def _estado(av, it: dict, now: datetime, feeling, decisoes: dict) -> tuple[str, Optional[float], str]:
    """(estado, vontade 0–1 ou None, motivo) — a mesma conta que a agenda viva faz pra decidir se vai."""
    feito = decisoes.get(it["key"])
    if feito:
        v = feito.get("vontade")
        if not feito.get("vai"):
            return "Desmotivada", v, ""
        return ("Animada" if v is not None and v >= 0.7 else "Confirmada"), v, ""
    if it.get("origem") in ORIGEM:
        return ORIGEM[it["origem"]], None, ""
    if feeling is None or it["inicio"] - now > timedelta(hours=PENSA_ANTES_H):
        return "", None, ""
    aval = av.disp.avaliar(it["tipo"], now, com=it["com"], feeling=feeling)
    peso = av._peso(it, aval, now, av._state()) if it["tipo"] in QUER_DESISTIR else 0.4
    margem = aval.vontade - peso
    if margem < 0:
        estado, sinal = QUER_DESISTIR.get(it["tipo"], "Quer desistir"), -1
    elif margem < 0.15:
        estado, sinal = "Indecisa", -1
    elif aval.vontade >= 0.7:
        estado, sinal = "Animada", +1
    else:
        estado, sinal = "Confirmada", +1
    motivo = aval.motivo(sinal)
    return estado, round(aval.vontade, 2), _fator(*motivo) if motivo else ""


def cabeca_view(db, now: datetime, dormindo: bool) -> list[dict]:
    """Linhas {titulo, quando, estado, vontade, detalhe}: título | quando; estado | barra | detalhe."""
    out = []
    try:
        from agenda_viva import AgendaViva
        from emotion import EmotionEngine
        av = AgendaViva(db)
        feeling = None if dormindo else EmotionEngine(db).feeling(now)
        decisoes = av._state().get("decisoes", {})
        for it in av.itens(now, 24.0):
            titulo, lugar = _titulo_agenda(it)
            estado, vontade, motivo = _estado(av, it, now, feeling, decisoes)
            out.append({"titulo": titulo, "quando": adiante(it["inicio"], now), "estado": estado,
                        "vontade": vontade, "detalhe": motivo or lugar, "_at": it["inicio"]})
    except Exception:
        logger.exception("por_dentro.agenda")
    try:
        from college import College
        for a in College(db).assignments(now.date(), horizon_days=7):
            due = date.fromisoformat(a["due"])
            dias = (due - now.date()).days
            if dias < 0:
                continue
            estado = "Atrasado" if dias <= 1 and a["pace"] != "adiantada" else RITMO.get(a["pace"], "")
            out.append({"titulo": "Fazer trabalho da facul", "quando": "hoje" if dias == 0 else "amanhã" if dias == 1
                        else DIAS_LONGOS[due.weekday()], "estado": estado, "vontade": None,
                        "detalhe": materia(a["course"]), "_at": datetime.combine(due, time(18))})
    except Exception:
        logger.exception("por_dentro.entregas")
    try:
        from freela import Freela
        for f in Freela(db).upcoming(now, horizon_days=7):
            perto = f["start"] - now <= timedelta(hours=18)
            out.append({"titulo": FREELA.get(f["kind"], f["kind"].capitalize()), "quando": adiante(f["start"], now),
                        "estado": "Nervosa" if perto else "Marcado", "vontade": None, "detalhe": _curto(f["what"]),
                        "_at": f["start"]})
    except Exception:
        logger.exception("por_dentro.freela")
    out.sort(key=lambda x: x.pop("_at"))
    return out[:6]


# ----------------------------------------------------------------- Vocês dois --
def voces_linhas(db, now: datetime) -> list[list[str]]:
    from webapp_server import cap
    linhas, pend = [], []
    try:
        with db.get_connection() as conn:
            r = conn.execute("SELECT role, timestamp FROM conversas ORDER BY id DESC LIMIT 1").fetchone()
        if r:
            linhas.append(["message-circle", "Última mensagem", cap(quando(datetime.fromisoformat(r["timestamp"]), now))])
            if r["role"] == "user":
                pend.append("Resposta dela")                # a última mensagem é sua
    except Exception:
        logger.exception("por_dentro.conversa")
    try:
        import promessa_foto
        p = promessa_foto.pending(db)
        if p:
            pend.append(FOTO.get(p.get("kind"), "Foto"))
    except Exception:
        logger.exception("por_dentro.promessa")
    try:
        import financas
        pedido = financas._load(db).get("pedido")
        if pedido:
            pend.append(f"Pix de R$ {int(pedido['valor'])}")
    except Exception:
        logger.exception("por_dentro.pedido")
    try:
        from emotion import EmotionEngine
        eng = EmotionEngine(db)
        # mágoa "até resolver" com você ainda sem reparo, ou o vínculo ainda machucado
        magoa = any(e.sticky and e.target == "o Patrick" and e.intensity >= e.peak * 0.99 for e in eng.episodes(now))
        if magoa or eng.bond(now).get("hurt", 0) >= 0.05:
            pend.append("Mágoa")
    except Exception:
        logger.exception("por_dentro.magoa")
    linhas.append(["hourglass", "Assunto pendente", ", ".join(pend) if pend else "Nada"])
    return linhas
