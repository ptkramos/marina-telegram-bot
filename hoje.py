"""Linha do tempo "Hoje" da aba Agora (Patrick, 26/09).

O dia inteiro por período (Manhã, Tarde, Noite): os acontecimentos gravados em texto curto de painel,
as saídas da agenda como um item com início–fim e o que rolou lá dentro recuado embaixo, os blocos em casa
com a duração, e no fim o que ainda vem (previsto, em cinza, hora aproximada).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# tipos que não são acontecimento pro painel (texto interno do mundo)
FORA = {"father_check_in", "thread_consequence"}

PERIODOS = (("Manhã", 4, 12), ("Tarde", 12, 18), ("Noite", 18, 28))

# 26/09 (Patrick): ícones do Tabler (outline)
# 28/09 (auditoria): a farmácia saía com a xícara — toda vontade virava "cafe"
VONTADE_TIPO = {"farmacia": "farmacia", "mercado": "mercado", "acai": "acai", "orla": "orla", "shopping": "shopping",
                "praia": "praia"}
SAIDA_IC = {"farmacia": "pill", "acai": "ice-cream", "orla": "walk", "shopping": "shopping-bag",
            "faculdade": "school", "academia": "activity", "milo": "dog", "noite": "moon-stars",
            "encontro": "users", "freela": "camera", "praia": "beach", "jogo": "ball-football", "cafe": "coffee",
            "mercado": "shopping-cart", "medico": "building-hospital", "unhas": "brush", "cabelo": "scissors"}

# 26/09 (Patrick): redes com o logo próprio do Tabler; cada bloco em casa com ícone seu
MIDIA_IC = (("instagram", "brand-instagram"), ("tiktok", "brand-tiktok"), ("pinterest", "brand-pinterest"),
            ("o x", "brand-x"), ("celular", "device-mobile"), ("ouvindo", "music"), ("lendo", "book"),
            ("vendo", "device-tv"), ("série", "device-tv"), ("jogando", "device-gamepad-2"), ("look", "hanger"),
            ("closet", "hanger"), ("umect", "droplet-half"), ("unha", "brush"), ("estudando", "notebook"),
            ("trabalho", "device-laptop"), ("dormindo", "moon"), ("cochil", "moon"), ("piscina", "pool"),
            ("treinando", "activity"), ("croqui", "pencil"), ("quarto", "home-check"), ("milo", "dog"),
            ("plantas", "plant"), ("sol", "sun"), ("à toa", "sofa"))

VERBO_REFEICAO = {"café da manhã": "Tomou café", "almoço": "Almoçou", "jantar": "Jantou", "lanche": "Lanchou"}
REFEICAO_PREVISTA = {"cafe": ("Café da manhã", "coffee"), "almoco": ("Almoço", "tools-kitchen-2"),
                     "lanche": ("Lanche", "tools-kitchen-2"), "jantar": ("Jantar", "tools-kitchen-2")}


def dia_de(now: datetime) -> date:
    """O dia dela vai até as 4h (depois de meia-noite ainda é a noite de ontem)."""
    return now.date() if now.hour >= 4 else now.date() - timedelta(days=1)


def _hm(at: Optional[datetime]) -> str:
    return f"{at:%H:%M}" if at else ""


def _aprox(at: datetime) -> str:
    from agenda import aprox
    return aprox(at)


def _periodo(at: datetime, dia: date) -> str:
    h = at.hour + (24 if at.date() > dia else 0)
    for nome, ini, fim in PERIODOS:
        if ini <= h < fim:
            return nome
    return "Manhã"


def _sem_ponto(txt: str) -> str:
    return (txt or "").strip().rstrip(".").strip()


def _cap(txt: str) -> str:
    return txt[:1].upper() + txt[1:] if txt else txt


def _painel(txt: str) -> str:
    """01/10 (catálogo, regra 6): o app é dela e fala dele na terceira pessoa — "o Patrick", nunca "você"."""
    return _cap(_sem_ponto(txt).replace("pix", "Pix"))


def _de(txt: str) -> str:
    """'o bairro' → 'do bairro', 'festas' → 'de festas'."""
    for art, contr in (("os ", "dos "), ("as ", "das "), ("o ", "do "), ("a ", "da ")):
        if txt.startswith(art):
            return contr + txt[len(art):]
    return "de " + txt


def _ele(quem: str) -> str:
    return "ele" if quem.startswith("o ") else "ela"


def _itens(txt: str) -> list[str]:
    """'Cappuccino e 2x Pão de queijo 4 un' → um item por linha (regra 5)."""
    partes = [p for p in re.split(r", | e (?=\d+x |[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", txt) if p]
    return [_cap(p.strip()) for p in partes]


# 01/10 (catálogo): o ícone da desistência é o do motivo
DESISTIU_IC = (("patrick", "heart-handshake"), ("chuv", "cloud-rain"), ("chov", "cloud-rain"), ("garoa", "cloud-rain"),
               ("cansa", "battery-1"), ("energia", "battery-1"), ("bateria", "battery-1"), ("sono", "battery-1"),
               ("dormiu mal", "battery-1"), ("exausta", "battery-1"),
               ("desânim", "mood-sad"), ("sem vontade", "mood-sad"), ("preguiça", "mood-sad"), ("triste", "mood-sad"),
               ("dor", "first-aid-kit"), ("cólica", "first-aid-kit"), ("doente", "first-aid-kit"),
               ("febre", "first-aid-kit"), ("enjo", "first-aid-kit"),
               ("dinheiro", "cash-off"), ("grana", "cash-off"), ("saldo", "cash-off"), (" caro", "cash-off"))


def _ic_desistiu(motivo: str) -> str:
    m = (motivo or "").lower()
    return next((ic for chave, ic in DESISTIU_IC if chave in m), "x")


# assuntos que vêm como frase (o pai, continuação de conversa): o texto deles é de depois do soak
FRASE_ASSUNTO = re.compile(r'^(se |como |bom dia|mandou |saudade e |o tempo no |as contas|o trabalho dele|")')


# ------------------------------------------------------------ texto curto --
def curto(ev: dict, db=None) -> dict:
    """Um acontecimento em linha de painel: ícone, texto curto e (às vezes) linha de baixo e valor.
    26/09 (Patrick): sempre a ação na linha e a descrição curta, menor e cinza, embaixo — o que ainda vem cru
    do mundo se divide no parêntese do fim, no primeiro ':' ou no '—'.
    01/10 (catálogo de textos, leva 1): os textos decididos ficha a ficha; o que tem detalhe aninhado (itens do
    iFood, aulas perdidas, o que fez no banho) vem em `filhos`, um por linha. Só a tela muda: o mundo grava igual."""
    out = _curto(ev, db)
    if not out["sub"] and not out.get("filhos") and out["texto"] == _painel(ev.get("summary") or ev.get("title") or ""):
        out.update(_divide(out["texto"]))
    return out


def _divide(txt: str) -> dict:
    m = re.match(r"(.+?) \(([^()]+)\)$", txt)
    if m:
        return {"texto": m.group(1), "sub": _cap(m.group(2))}
    for sep in (": ", " — ", "; "):
        if sep in txt:
            acao, resto = txt.split(sep, 1)
            return {"texto": acao, "sub": _cap(resto)}
    return {}


def _fim(ev: dict) -> Optional[datetime]:
    return datetime.fromisoformat(ev["end_at"]) if ev.get("end_at") else None


def _curto(ev: dict, db=None) -> dict:
    tipo, title = ev["event_type"], (ev.get("title") or "")
    s = _sem_ponto(ev.get("summary") or title)
    out = {"ic": "point", "texto": _painel(s), "sub": "", "valor": None, "aviso": False, "fim": None}

    if tipo == "agenda":
        out.update(_agenda(s, db))
        return out
    if tipo == "instagram":     # 27/09 (Patrick): o post dela no Hoje, a legenda embaixo
        acao, _, legenda = s.partition(": ")
        out.update(ic="brand-instagram", texto=acao, sub=legenda)
        return out
    if tipo == "tempo_livre" and s.startswith("Fez as unhas em casa"):
        return {**out, **_salao(s)}
    if tipo == "tempo_livre" and s.startswith("Ficou ouvindo a playlist dela"):
        # 28/09: "Ouviu Sabrina Carpenter" com Chappell Roan e Liniker tocando (e o story da Liniker às 14:09)
        # 01/10 (catálogo, regra 5): enquanto ouve, um artista por linha; depois, juntos na linha de baixo
        artistas = list(dict.fromkeys(re.findall(r'"[^"]+" \(([^)]+)\)', s)))
        out.update(ic="music", texto="Ouviu a playlist dela", presente="Ouvindo a playlist dela",
                   sub=_e(artistas) if artistas else "", filhos_presente=[{"texto": a} for a in artistas])
        return out
    if tipo == "tempo_livre" and s.startswith(("Transou com o Patrick por mensagem", "Provocou o Patrick por mensagem")):
        # 03/10 (Patrick): o sexting no Hoje — "Transou com o Patrick", embaixo "No quarto por mensagem, gozou";
        # enquanto acontece, "Transando com o Patrick" (o "por mensagem" fica só na linha de baixo)
        # Soak, dia 6 (Patrick, 05/10): só ela no clima (ele pediu pra parar) é "Provocou o Patrick".
        m = re.search(r"por mensagem ((?:n[oa]s?|em) [^,.]+?)(?: e gozou)?\.?$", s)
        base = f"{_cap(m.group(1)) if m else 'Em casa'} por mensagem"
        so_ela = s.startswith("Provocou")
        out.update(ic="message-heart", texto="Provocou o Patrick" if so_ela else "Transou com o Patrick",
                   presente="Provocando o Patrick" if so_ela else "Transando com o Patrick",
                   sub_presente=base,
                   sub=base + (", gozou" if s.rstrip(".").endswith(" e gozou") else ""))
        return out
    if tipo == "tempo_livre":
        out.update(ic=_ic_midia(title), texto=passado(_cap(title)) if title else _painel(s))
        return out
    if tipo == "social_contact":
        base, _, assunto = s.partition("; assunto: ")
        base = re.sub(r"\s*\([^)]*\)$", "", base)                  # "(Bodytech São Clemente)"
        base = base.split(", ")[0]                                  # "Conheceu a Gabi" (quem é fica no sistema)
        ic = ("user-plus" if base.startswith("Conheceu") else "message-dots" if base.startswith("Trocou mensagens")
              else "microphone" if base.startswith("Trocou áudios") else "phone" if base.startswith("Falou por telefone")
              else "users")
        for antes, depois in ((r"^Trocou mensagens com (.+)$", r"Conversou com \1 no Whats"),
                              (r"^Trocou áudios com (.+)$", r"Trocou áudios com \1 no Whats"),
                              (r"^Falou por telefone com (.+)$", r"Fez ligação com \1 no Whats"),
                              (r"^Encontrou (.+)$", r"Bateu papo com \1")):
            base = re.sub(antes, depois, base)
        out.update(ic=ic, texto=_painel(base), sub=_assunto(assunto) if assunto else "")
        return out
    if tipo == "social_invite":
        m = re.match(r"(.+?) te chamou: (.+?)(?: \((.*)\))?$", s)
        if m:                                       # "A Bia chamou para sair" / "Para o Quartinho Bar às 21:00"
            quando = re.sub(r"^hoje ", "", m.group(3) or "")
            out.update(ic="calendar-plus", texto=f"{m.group(1)} chamou para sair",
                       sub=_para_onde(m.group(2)) + (f" {quando}" if quando else ""), quando=quando)
        elif s.startswith("Topou o convite"):
            plano = s.split(":", 1)[-1].strip()
            quem = re.search(r" com (.+?) n[oa]s? ", plano)
            out.update(ic="calendar-check", texto="Topou sair" + (f" com {quem.group(1)}" if quem else ""),
                       sub=_para_onde(plano))
        else:
            out.update(ic="calendar-plus")
        return out
    if tipo == "consumo" and s.startswith(("Cabelo na ", "Fez as unhas em gel")):
        return {**out, **_salao(s)}
    if tipo == "consumo" and ev.get("event_key", "").startswith("lista:"):
        # 28/09: o que estava na lista, comprado na compra da semana (o pai paga: sem valor)
        m = re.match(r"(Comprou .+?) n[oa] .+? \(da lista, (.+)\)$", s)
        if m:                                       # 01/10 (catálogo): sugestão, não pedido
            out.update(ic="list-check", texto=m.group(1),
                       sub="O Patrick sugeriu" if "Patrick" in m.group(2) else _cap(f"da lista, {m.group(2)}"))
            return out
    if tipo == "consumo":
        m = re.match(r"(Pediu|Dividiu|Comprou) (.+?)(?: com .+?)? n[oa] .+? \(R\$ (\d+)", s)
        if m:
            out.update(ic="receipt", texto=f"{m.group(1)} {m.group(2)}",
                       valor=int(m.group(3)))
        else:
            out.update(ic="receipt")
        return out
    if tipo == "transporte":                        # 01/10 (catálogo): "Pegou um Uber" / "Dividiu um Uber com a Bia"
        m = re.search(r"R\$ (\d+)", s)
        com = re.search(r"dividido com (.+?)\)", s)
        texto = ("Dividiu um Uber" + (f" com {com.group(1)}" if com else "")) if "dividido" in s else "Pegou um Uber"
        out.update(ic="car", texto=texto, valor=int(m.group(1)) if m else None)
        return out
    if tipo == "commute":                                  # "No caminho (ida, ônibus): ônibus veio lotado"
        out.update(ic="alert-circle", aviso=True, texto=_cap(s.split("): ", 1)[-1]))
        return out
    if tipo == "money":
        out.update(ic="cash", **_dinheiro(s))
        return out
    if tipo == "gift":
        out.update(ic="shopping-bag-heart")
        m = re.match(r"Mandou (.+?) do (.+?) pr[oa] Patrick pelo app(?: de surpresa)? \(R\$ (\d+)\)", s)
        if m:
            out.update(texto="Mandou um iFood para o Patrick", sub=f"Pediu no {m.group(2)}", valor=int(m.group(3)),
                       filhos=[{"texto": i} for i in _itens(m.group(1))])
            return out
        m = re.match(r"O Patrick mandou (de surpresa )?(.+?) do (.+?) pelo app", s)
        if m:
            out.update(texto="O iFood surpresa do Patrick chegou" if m.group(1) else "O Patrick mandou um iFood",
                       sub=f"De {m.group(3)}", filhos=[{"texto": i} for i in _itens(m.group(2))])
        return out
    if tipo in ("meal", "snack"):
        return {**out, **_refeicao(ev, s)}
    if tipo == "routine":
        m = re.match(r"Tomou banho( e lavou o cabelo)? \((\d\d:\d\d)–(\d\d:\d\d)\)", s)
        if m:                                       # 01/10 (catálogo, regra 5): o que fez no banho, aninhado
            fim = datetime.fromisoformat(ev["event_at"]).replace(
                hour=int(m.group(3)[:2]), minute=int(m.group(3)[3:]))
            out.update(ic="chuveiro", texto="Tomou banho", fim=fim,
                       filhos=[{"texto": "Lavou o cabelo", "presente": "Lavando o cabelo"}] if m.group(1) else [])
            return out
        m = re.match(r"Se pesou(?: na academia)?: (.+)", s)
        if m:
            out.update(ic="scale", texto=f"Se pesou e está com {m.group(1)}")
            return out
        if "masturbou" in s or "se tocou" in s:             # Patrick: hand-love-you de cabeça pra baixo
            out.update(ic="masturbacao", fim=_fim(ev), **_masturbacao(s))
            return out
        m = re.match(r"(Chegou (\d+) min atrasada)(?: (?:na|no|pra|pro) .+?)?(?: — (.+))?$", s)
        if title == "atraso" and m:                       # 28/09 (Patrick): atraso em amarelo
            # 01/10 (catálogo): por extenso; a aula e cada motivo numa linha embaixo
            onde = re.search(r"na aula de (.+?)(?: — |$)", s)
            n = int(m.group(2))
            motivos = [x for x in re.split(r", | e ", m.group(3) or "") if x]
            filhos = ([{"texto": onde.group(1)}] if onde else []) + [{"texto": _cap(x)} for x in motivos]
            out.update(ic="clock-exclamation", aviso=True, texto=f"Chegou {n} minuto{'s' if n != 1 else ''} atrasada",
                       filhos=filhos)
            return out
        if s.startswith("Cuidou da bagunça dela: "):        # Patrick: "Arrumou a casa" e o que fez embaixo
            out.update(ic="home-check", texto="Arrumou a casa", sub=_cap(s.split(": ", 1)[1]))
            return out
        if s.startswith("Pagou o passeador"):
            out.update(ic="dog", texto="Deixou o Milo com um passeador",
                       sub=_cap(s.split("— ", 1)[1]) if "— " in s else "")
            return out
        if s.startswith("O Seu Jorge contou uma fofoca do prédio"):
            out.update(ic="users", texto="Conversou com o Seu Jorge", sub="Contou uma fofoca do prédio")
            return out
        m = re.match(r"Marcou a manicure na (.+?) \((.+)\)$", s)
        if m:                                       # 01/10 (catálogo): "Campanha de moda praia depois de amanhã"
            out.update(ic="calendar-plus", texto=f"Marcou horário na {m.group(1)}", sub=_cap(m.group(2)))
            j = re.match(r"job (hoje|amanhã|depois de amanhã)$", m.group(2))
            if j and db is not None:
                out["sub"] = _job(db, datetime.fromisoformat(ev["event_at"]), j.group(1)) or out["sub"]
            return out
        m = re.match(r"O Milo (.+)$", s)
        if m:
            from milo import CHAMEGO                      # 28/09 (Patrick): dormir encostado nela é chamego, não arte
            chamego = any(m.group(1).startswith(c) for c in CHAMEGO)
            out.update(ic="dog", texto="O Milo foi carinhoso" if chamego else "O Milo foi travesso", sub=_cap(m.group(1)))
            return out
        if "Milo" in s and "xixi" in s:                  # 01/10 (catálogo): "Desceu com o Milo" e o xixi recuado
            out.update(ic="dog", texto="Desceu com o Milo", presente="Descendo com o Milo",
                       filhos=[{"texto": "O Milo se aliviou"}])
            if ev.get("end_at"):                         # 28/09: sem a volta, parecia que o Milo foi com ela pra PUC
                out["fim"] = datetime.fromisoformat(ev["end_at"])
        elif "Milo" in s or title == "Milo":
            out.update(ic="dog")
        elif title == "casa":
            out.update(ic="home-check")
        elif title == "faculdade":
            out.update(ic="school")
            m = re.match(r"Trabalhou n[oa] (.+?) \(entrega ([^)]+)\)(?:, (.+))?$", s)
            if m:                                   # 01/10 (catálogo, regra 3): "Fazendo…" → "Fez…"
                out.update(texto=f"Fez trabalho da facul para {m.group(2)}",
                           presente=f"Fazendo trabalho da facul para {m.group(2)}", fim=_fim(ev),
                           sub=_cap(m.group(1)) + (f", {m.group(3)}" if m.group(3) else ""))
            m = re.match(r"Faltou a aula hoje \((.+)\): (.+)$", s)
            if m:
                out.update(_faltou(m.group(1), m.group(2), db, dia_todo=True))
        elif title in ("vontade", "agenda reativa"):
            out.update({"ic": "bolt", **_decisao(s)})
        elif title == "tv":
            out.update(ic="device-tv", **_serie(s, ev))
        elif title == "médico":
            out.update(ic="building-hospital")
        return out
    if tipo == "midia":
        out.update(ic="music" if "música" in s or "Ouviu" in s else "book")
        m = re.match(r'Ouviu "(.+?)" \((.+?)\), que o Patrick mandou: (.+)$', s)
        if m:
            curtiu = "curtiu!" if m.group(3).startswith("curtiu") else "não curtiu muito!"
            out.update(texto="Ouviu música compartilhada", sub=f'"{m.group(1)}" de {m.group(2)} e {curtiu}')
        m = re.match(r'Descobriu que saiu música nova de (.+?): "(.+?)"', s)
        if m:
            out.update(texto="Viu que saiu música nova", sub=f'"{m.group(2)}" de {m.group(1)}')
        m = re.match(r"Terminou de ler (.+?),? vol\. (\d+)$", s)
        if m:
            out.update(texto=f"Terminou de ler {m.group(1)}", sub=f"Volume {m.group(2)}")
        return out
    if tipo == "work":
        out.update(ic="camera")
        m = re.match(r"A Lívia da agência mandou um casting: (.+)$", s)
        if m:                                       # 01/10 (catálogo)
            out.update(texto="A Lívia enviou um Casting", sub=f"Participar {_do(m.group(1))}")
        return out
    if tipo in ("manicure", "unhas"):
        out.update(ic="brush")
    return out


def _assunto(assunto: str) -> str:
    """01/10 (catálogo): "Falaram de relacionamentos e do Theo". O assunto que vem como frase segue como estava
    (texto dos assuntos: depois do soak)."""
    assunto = _painel(assunto)
    assunto = assunto[:1].lower() + assunto[1:]
    if FRASE_ASSUNTO.match(assunto):
        return f"Assunto: {assunto}"
    topico, _, falaram = assunto.partition(", e falaram ")
    topico = "do Milo" if topico == "Milo" else _de(topico)
    return f"Falaram {topico}" + (f" e {falaram}" if falaram else "")


def _do(oque: str) -> str:
    """'vídeo pra uma marca de cosméticos' → 'do vídeo de uma marca de cosméticos'."""
    oque = oque.replace(" pra uma ", " de uma ").replace(" pra um ", " de um ")
    primeira = oque.split(" ", 1)[0].lower()
    art = ("das" if primeira.endswith("s") and primeira.startswith("foto") else
           "da" if primeira in ("campanha", "sessão", "foto", "propaganda") else "do")
    return f"{art} {oque}"


def _job(db, at: datetime, dia_txt: str) -> str:
    """O tipo do trabalho marcado pra hoje/amanhã/depois de amanhã ('Sessão de fotos: campanha de moda praia')."""
    dia = at.date() + timedelta(days={"hoje": 0, "amanhã": 1, "depois de amanhã": 2}[dia_txt])
    try:
        with db.get_connection() as conn:
            row = conn.execute("""SELECT description FROM eventos_pendentes WHERE event_type='trabalho'
                                  AND confirmed=1 AND status!='cancelled' AND substr(event_at,1,10)=?
                                  ORDER BY event_at LIMIT 1""", (dia.isoformat(),)).fetchone()
    except Exception:
        logger.exception("hoje.job")
        return ""
    if not row or not row["description"]:
        return ""
    desc = row["description"]
    tipo = (desc.split(": ", 1)[1] if desc.startswith("Sessão de fotos: ") else
            "Casting" if desc.startswith("Casting") else "Prova de roupa" if desc.startswith("Prova") else desc)
    return f"{_cap(tipo)} {dia_txt}"


def _aulas(nomes: str, db=None) -> list[str]:
    """As aulas perdidas, uma por item. O college junta com " e ", e o nome da matéria também tem " e " — corta
    pelos nomes de verdade das matérias."""
    if ", " in nomes:
        return [n.strip() for n in nomes.split(", ")]
    conhecidos = []
    if db is not None:
        try:
            with db.get_connection() as conn:
                conhecidos = [r[0] for r in conn.execute("SELECT DISTINCT display_name FROM academic_courses")]
        except Exception:
            logger.exception("hoje.aulas")
    achados, resto = [], nomes
    for nome in sorted(conhecidos, key=len, reverse=True):
        i = resto.find(nome)
        if i >= 0:
            achados.append((nomes.find(nome), nome))
            resto = resto[:i] + "\0" * len(nome) + resto[i + len(nome):]
    if not achados:
        return [nomes]
    return [n for _, n in sorted(achados)]


def _faltou(nomes: str, motivo: str, db=None, dia_todo: bool = False) -> dict:
    """01/10 (catálogo): "Faltou a aula, dormiu mal" / a matéria embaixo; faltou o dia: "Faltou a facul hoje,
    cólica forte" e as aulas perdidas aninhadas, uma por linha, em amarelo (como o atraso)."""
    aulas = _aulas(nomes, db)
    motivo = motivo[:1].lower() + motivo[1:]
    if len(aulas) == 1 and not dia_todo:
        return {"ic": "school-off", "texto": f"Faltou a aula, {motivo}", "sub": aulas[0]}
    return {"ic": "school-off", "texto": f"Faltou a facul hoje, {motivo}", "sub": "",
            "filhos": [{"texto": a, "aviso": True} for a in aulas]}


def _serie(s: str, ev: dict) -> dict:
    """01/10 (catálogo): "Viu que saiu episódio novo" / "De One Piece, temporada 23, episódio 1180";
    "Assistiu Paradise Kiss" / "Episódios 1 e 2" (o comentário dela sai do app)."""
    m = re.match(r"Saiu episódio novo de (.+?) hoje(?: \((.+)\))?$", s)
    if m:
        detalhe = re.sub(r"\bep\. ", "episódio ", m.group(2) or "")
        return {"texto": "Viu que saiu episódio novo", "sub": f"De {m.group(1)}" + (f", {detalhe}" if detalhe else "")}
    m = re.match(r"Viu (episódios?) (\d+)(?: a (\d+))? de (.+?)(?: \(.*\))?$", s)
    if m:
        a, b = int(m.group(2)), int(m.group(3) or m.group(2))
        eps = (f"Episódio {a}" if a == b else f"Episódios {a} e {b}" if b == a + 1 else f"Episódios {a} a {b}")
        return {"texto": f"Assistiu {m.group(4)}", "presente": f"Assistindo {m.group(4)}", "sub": eps, "fim": _fim(ev)}
    return {}


def _masturbacao(s: str) -> dict:
    """26/09 (Patrick): "Se masturbou no quarto" e o porquê embaixo; fora de casa, o tesão.
    01/10 (catálogo, regras 3 e 6): "Se masturbando" / "Fantasiando com o Patrick" enquanto acontece.
    O resto do texto do mundo (se conta pra ele ou guarda) é do sistema, não do painel."""
    m = re.search(r"se (?:masturbou|trancou) ((?:n[oa]s?|em) [^,.—]+?)(?= pensando| e | —|[,.]|$)", s)
    onde = f" {m.group(1)}" if m else (" antes de dormir" if s.startswith("Antes de dormir") else "")
    chamou = "chamou" in s
    base = {"texto": f"Se masturbou{onde}", "presente": f"Se masturbando{onde}"}
    if s.startswith("Bateu um tesão"):
        return {**base, "sub": "Estava com muito tesão" + (", chamou o Patrick" if chamou else "")}
    if chamou:
        return {**base, "sub": "Chamou o Patrick para ajudar"}
    return {**base, "sub": "Fantasiou com o Patrick", "sub_presente": "Fantasiando com o Patrick"}


def _dinheiro(s: str) -> dict:
    """26/09 (Patrick): a ação na linha, o valor na coluna, o detalhe curto embaixo. 01/10 (catálogo): "o Patrick"."""
    m = re.match(r"O Patrick (?:fez|mandou) (?:um|o) pix de R\$ (\d+)(.*)$", s)
    if m:
        resto = m.group(2)
        nota = re.search(r"\('(.+?)'\)", resto)
        sub = ("O que tinha prometido" if "prometido" in resto else "Para o Uber" if "uber" in resto
               else "De presente" if "presente" in resto else "")
        if nota:
            sub = (sub + ", " if sub else "") + f'"{nota.group(1)}"'
        return {"texto": "Recebeu um Pix do Patrick", "valor": int(m.group(1)), "sub": sub}
    m = re.match(r"Usou o pix do Patrick: comprou (.+?) \(R\$ (\d+)\)", s)
    if m:
        return {"texto": "Usou o Pix do Patrick", "sub": _cap(m.group(1)), "valor": int(m.group(2))}
    m = re.match(r"Caiu o cachê e ela fez o pix de volta pro Patrick: R\$ (\d+)", s)
    if m:
        return {"texto": "Enviou um Pix para o Patrick", "sub": "Recebeu o cachê de um trabalho", "valor": int(m.group(1))}
    m = re.match(r"Aperto: (.+?) \(R\$ (\d+)\)", s)
    if m:
        return {"texto": "Precisou de empréstimo", "sub": _cap(m.group(1)), "valor": int(m.group(2))}
    if s.startswith("O dinheiro dela acabou"):
        return {"texto": "Precisou de empréstimo", "sub": "O dinheiro acabou antes do cachê"}
    return {}


def _salao(s: str) -> dict:
    """Cabelo e unhas: "Fez o cabelo" / "Repicado e escova" e o valor na coluna.
    01/10 (catálogo): "O Patrick escolheu repicado e escova"; sem escolha, só os serviços."""
    escolheu = "Patrick escolheu" in s
    m = re.match(r"Cabelo na .+?: (.+) · R\$ (\d+)$", s)
    if m:
        feito = m.group(1).replace(" (o Patrick escolheu)", "")
        sub = f"O Patrick escolheu {feito[:1].lower()}{feito[1:]}" if escolheu else _cap(feito)
        return {"ic": "scissors", "texto": "Fez o cabelo", "sub": sub, "valor": int(m.group(2))}
    m = re.match(r"Fez as unhas em gel .+?: (.+?)(?: — .+)? \(R\$ (\d+)\)", s)
    if m:
        sub = f"O Patrick escolheu {m.group(1)}" if escolheu else _cap(m.group(1))
        return {"ic": "brush", "texto": "Colocou unhas de gel", "sub": sub, "valor": int(m.group(2))}
    m = re.match(r"Fez as unhas em casa, esmalte (.+?)(?: — .+)?$", s)
    if m:
        return {"ic": "brush", "texto": "Fez as unhas",
                "sub": f"Com esmalte {m.group(1)}" + (", o Patrick escolheu" if escolheu else "")}
    return {}


def _agenda(s: str, db=None) -> dict:
    """27/09 (agenda viva): o que ela decidiu pelo que sentia — ação na linha, motivo embaixo."""
    m = re.match(r"Saindo de lá, resolveu passar .+? antes de voltar \((.+)\)$", s)
    if m:
        return {"ic": "bolt", "motivo": f"Foi direto, {m.group(1)}"}
    m = re.match(r"Desistiu de ir: (.+?) \((.+?)\)(?:\. Avisou (.+?)(?: e combinaram outro dia)?)?$", s)
    if m:                                           # 01/10 (catálogo): "Desistiu de sair e avisou a Bia"
        motivo = m.group(2)[:1].lower() + m.group(2)[1:]
        return {"ic": "calendar-x", "texto": "Desistiu de sair" + (f" e avisou {m.group(3)}" if m.group(3) else ""),
                "sub": f"{_lugar_do_plano(m.group(1))}, {motivo}"}
    m = re.match(r"Faltou a aula de hoje \((.+?)\): (.+?)\. Vai pegar", s)
    if m:
        return _faltou(m.group(1), m.group(2), db)
    m = re.match(r"Pegou a matéria da aula que faltou \((.+?)\) com (.+?) e", s)
    if m:
        return {"ic": "notebook", "texto": f"Pegou a matéria com {m.group(2)}", "sub": _cap(m.group(1))}
    m = re.match(r"Chamou (.+?) pra sair (\S+)(?: às (\d\d:\d\d) \(.+\); .+ topou|, mas .+ não podia)$", s)
    if m:                                           # 01/10 (catálogo): "Sexta às 20:00, ela topou"
        topou = "topou" in s
        quando = _cap(m.group(2)) + (f" às {m.group(3)}" if m.group(3) else "")
        ele = _ele(m.group(1))
        return {"ic": "calendar-plus", "texto": f"Chamou {m.group(1)} para sair",
                "sub": f"{quando}, " + (f"{ele} topou" if topou else f"{ele} não pôde")}
    m = re.match(r"Remarcou pra (.+?) às (\d\d:\d\d): (.+?) \((.+)\)$", s)
    if m:
        return {"ic": "calendar-time", "texto": f"Remarcou {_lugar_do_plano(m.group(3))}",
                "sub": f"Para {m.group(1)} às {m.group(2)}"}
    m = re.match(r"Combinou com o Patrick: (.+?) (amanhã|segunda|terça|quarta|quinta|sexta|sábado|domingo) às (\d\d:\d\d)", s)
    if m:
        return {"ic": "calendar", "texto": "Combinou com o Patrick", "sub": f"{_cap(m.group(1))}, {m.group(2)} {m.group(3)}"}
    for padrao, texto in ((r"Desistiu de treinar hoje \((.+)\)$", "Desistiu de treinar"),
                          (r"Trocou a Bodytech pela academia do prédio \((.+)\)$", "Treinou no prédio"),
                          (r"Deixou o passeio do Milo pra depois \((.+)\)$", "Adiou o passeio do Milo"),
                          (r"Deixou o mercado da semana pra amanhã \((.+)\)$", "Adiou o mercado"),
                          (r"Desistiu do mercado da semana hoje \((.+)\)$", "Desistiu do mercado"),
                          (r"Desistiu: .+? \((.+)\)$", None)):
        m = re.match(padrao, s)
        if m:
            if texto is None:
                return {"ic": _ic_desistiu(m.group(1)), **_divide(s)}
            if texto == "Treinou no prédio":
                return {"ic": "calendar-time", "texto": texto, "presente": "Treinando no prédio", "sub": _cap(m.group(1))}
            return {"ic": _ic_desistiu(m.group(1)) if "Desistiu" in texto else "calendar-time", "texto": texto,
                    "sub": _cap(m.group(1))}
    return {"ic": "calendar"}


def _decisao(s: str) -> dict:
    """Por que saiu (vira a linha cinza da saída) ou desistência (linha própria)."""
    m = re.match(r"Deu vontade e foi: .+? \((.+)\)$", s)
    if m:
        return {"motivo": _cap(m.group(1))}
    if s.startswith("O Patrick convenceu"):
        return {"motivo": "O Patrick convenceu"}
    m = re.match(r"Combinou com o Patrick[^:]*(?:: (.+))?$", s)
    if m:
        return {"motivo": "Combinou com o Patrick" + (f", {m.group(1)}" if m.group(1) else "")}
    m = re.match(r"Desistiu de (.+?)(?: hoje)?(?:: (.+))?$", s)
    if m:
        return {"texto": f"Desistiu de {m.group(1)}", "sub": _cap(m.group(2) or ""), "ic": _ic_desistiu(m.group(2))}
    return {}


def _lugar_do_plano(plano: str) -> str:
    """'Saindo com a Bia no Quartinho Bar' → 'Quartinho Bar' (28/09: descritivo enxuto no Hoje)."""
    m = re.search(r" (?:no|na|nos|nas) (.+)$", plano)
    return m.group(1) if m else _cap(plano)


def _para_onde(plano: str) -> str:
    """'Saindo com a Bia no Quartinho Bar' → 'Para o Quartinho Bar' (01/10, catálogo)."""
    m = re.search(r" (no|na|nos|nas) (.+)$", plano)
    if not m:
        return "Para sair"
    return "Para " + {"no": "o", "na": "a", "nos": "os", "nas": "as"}[m.group(1)] + " " + m.group(2)


def _min(txt: str) -> str:
    return txt[:1].lower() + txt[1:] if txt else txt


def _refeicao(ev: dict, s: str) -> dict:
    """26/09 (Patrick): a refeição na linha 1 e o prato embaixo.
    01/10 (catálogo): "Jantou e comeu demais" / "Tapioca de queijo com presunto"; o lugar depois do prato
    ("Salada com frango, no restaurante da PUC"); o iFood que o Patrick mandou com um item por linha."""
    fim = datetime.fromisoformat(ev["end_at"]) if ev.get("end_at") else None
    alem = " e comeu demais" if "estufada" in s else ""
    if s.startswith("Pulou"):                       # 28/09 (auditoria): "Pulou o café 07:52–08:05" — pulou não dura
        return {"ic": "tools-kitchen-2", "texto": _painel(s.split(":")[0]), "fim": None,
                "sub": _cap(s.split(": ", 1)[1].rstrip(".")) if ": " in s else ""}
    if ev["event_type"] == "snack" or s.startswith("Beliscou"):
        texto = _painel(s.split(";")[0])
        return {"ic": "cookie", "texto": re.sub(r"^Beliscou ", "Comeu ", texto), "fim": None}
    m = re.match(r"O Patrick mandou (?:de surpresa )?(.+?) do (.+?) pelo app", s)
    if m:
        return {"ic": "shopping-bag-heart", "texto": "Comeu o iFood recebido" + alem, "fim": fim,
                "sub": f"O Patrick pediu no {m.group(2)}", "filhos": [{"texto": i} for i in _itens(m.group(1))]}
    m = re.match(r"O (.+?) do delivery chegou", s)
    if m:
        return {"ic": "shopping-bag", "texto": "Comeu o iFood pedido" + alem, "fim": fim, "sub": _cap(m.group(1))}
    m = re.match(r"(Café da manhã|Almoço|Jantar|Lanche) ([^:]+): ([^;]+)", s)
    if m:
        verbo = VERBO_REFEICAO[m.group(1).lower()]
        onde = "" if m.group(2) == "em casa" else m.group(2)
        prato = re.sub(r"^(um|uma|uns|umas) ", "", m.group(3).strip())
        prato = re.sub(r" pedido no iFood$", " do iFood", prato)
        prato = re.sub(r" n[oa] (restaurante|lanchonete|cantina|bandejão|refeitório)\b.*$", "", prato)
        return {"ic": "coffee" if verbo == "Tomou café" else "tools-kitchen-2", "texto": verbo + alem,
                "fim": fim, "sub": _cap(prato) + (f", {onde}" if onde else "")}
    m = re.match(r"Comeu (.+?) n[oa] (.+)", s)
    if m:
        return {"ic": "tools-kitchen-2", "texto": "Parou para comer", "sub": _cap(m.group(1)), "fim": fim}
    return {"ic": "tools-kitchen-2", "texto": _painel(s.split(";")[0]), "fim": fim}


IRREGULAR = {"vendo": "Viu", "lendo": "Leu", "fazendo": "Fez", "pondo": "Pôs", "tendo": "Teve", "trazendo": "Trouxe"}


FORA_DO_PADRAO = {"deitada à toa": "Ficou à toa"}


def passado(texto: str) -> str:
    """26/09 (Patrick): tudo no passado — 'Olhando o Instagram' → 'Olhou o Instagram', 'Vendo X' → 'Viu X'."""
    if texto.lower() in FORA_DO_PADRAO:
        return FORA_DO_PADRAO[texto.lower()]
    pre, _, corpo = texto.partition(" ") if texto.lower().startswith("se ") else ("", "", texto)
    palavra, _, resto = corpo.partition(" ")
    p = palavra.lower()
    if p in IRREGULAR:
        novo = IRREGULAR[p].lower()
    elif p[-4:] in ("ando", "endo", "indo"):
        novo = p[:-4] + {"ando": "ou", "endo": "eu", "indo": "iu"}[p[-4:]]
    else:
        return texto
    frase = (f"{pre} {novo}" if pre else novo) + (f" {resto}" if resto else "")
    return _cap(frase)


def _ic_midia(texto: str) -> str:
    t = texto.lower()
    for chave, ic in MIDIA_IC:
        if chave in t:
            return ic
    return "home"


# ------------------------------------------------------------------ dia --
def _eventos(db, ini: datetime, fim: datetime) -> list[dict]:
    with db.get_connection() as conn:
        rows = conn.execute(
            """SELECT event_key, event_at, end_at, event_type, title, summary FROM life_events
               WHERE event_at>=? AND event_at<=? ORDER BY event_at, id""",
            (ini.isoformat(), fim.isoformat())).fetchall()
    return [dict(r) for r in rows if r["event_type"] not in FORA]


def _saidas(db, dia: date, now: datetime) -> list[dict]:
    """Cada compromisso do dia: do pé na rua até chegar em casa, com o título do 'Lá'."""
    from agenda import Agenda
    from social_day import short_name
    try:
        ag = Agenda(db)
        etapas = ag.etapas(dia, now)
        comps = ag._compromissos(dia)
        amigos = {c["key"]: [short_name(f) for f in c["friends"]] for c in comps}
        tipos = {c["key"]: c.get("tipo", "") for c in comps}
    except Exception:
        logger.exception("hoje.saidas")
        return []
    por: dict[str, list] = {}
    for e in etapas:
        if e.compromisso and e.tipo != "arrumando":
            por.setdefault(e.compromisso, []).append(e)
    # Soak, dia 3 (01/10): dois castings seguidos na mesma agência (ela fica entre um e outro) viravam "Foi para a
    # agência 14:58–17:00" e "Foi para a agência 17:00–17:53". Emendado no mesmo lugar é uma saída só.
    anterior = None
    for key in sorted(por, key=lambda k: por[k][0].inicio):
        es = por[key]
        if anterior and not any(e.tipo == "voltando" for e in por[anterior]) \
                and es[0].inicio <= por[anterior][-1].fim \
                and _lugar(es) and _lugar(es) == _lugar(por[anterior]):
            por[anterior].extend(por.pop(key))
            continue
        anterior = key
    out = []
    for key, es in por.items():
        la = next((e for e in es if e.tipo == "la"), es[0])
        tipo = _tipo_saida(key, la, tipos.get(key, ""))
        com = amigos.get(key) or la.com_art or la.com         # "com a Bia"
        junto = f" com {_e(com)}" if com else ""
        volta = next((e for e in es if e.tipo == "voltando"), None)
        # 01/10 (catálogo, regra 4): "Indo para o…" no trajeto, "Está no…" lá, "Foi para o…" depois
        estado = ("Indo" if now < la.inicio else "Está" if now < (volta.inicio if volta else es[-1].fim) else "Foi")
        titulo = _foi(la.titulo, estado) + junto
        out.append({"key": key, "ini": es[0].inicio, "fim": es[-1].fim, "titulo": titulo,
                    "previsto": "Vai para " + _para(la.titulo) + junto,
                    "ic": SAIDA_IC.get(tipo, "map-pin"), "la": la,
                    "volta": next((e for e in es if e.tipo == "voltando"), None)})
    return sorted(out, key=lambda s: s["ini"])


def _lugar(es: list) -> str:
    return next((e.lugar_key for e in es if e.tipo == "la"), "")


def _para(titulo: str) -> str:
    """'No Quartinho' → 'o Quartinho', 'Na academia' → 'a academia'."""
    m = re.match(r"(No|Na|Nos|Nas) (.+)$", titulo)
    if not m:
        return titulo
    return {"No": "o", "Na": "a", "Nos": "os", "Nas": "as"}[m.group(1)] + " " + m.group(2)


def _foi(titulo: str, estado: str = "Foi") -> str:
    """Título do 'Lá' (01/10, catálogo): 'No Quartinho' → 'Foi para o Quartinho' depois, 'Indo para o Quartinho'
    no caminho, 'Está no Quartinho' lá."""
    m = re.match(r"(No|Na|Nos|Nas) (.+)$", titulo)
    if not m:
        return titulo
    if estado == "Está":
        return f"Está {titulo[:1].lower()}{titulo[1:]}"
    return f"{estado} para {_para(titulo)}"


def _e(nomes: list) -> str:
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _tipo_saida(key: str, la, tipo_vontade: str = "") -> str:
    if key.startswith("puc:"):
        return "faculdade"
    if key.startswith("gym:"):
        return "academia"
    if key.startswith("milo:"):
        return "milo"
    if key.startswith("freela:"):
        return "freela"
    for t in ("mercado", "medico", "unhas", "cabelo"):
        if key.startswith(t + ":"):
            return t
    if key.startswith("vontade:"):
        return VONTADE_TIPO.get(tipo_vontade, "cafe")
    if la.lugar_key.endswith("_beach"):
        return "praia"
    if la.lugar_key == "estadio_nilton_santos":
        return "jogo"
    return "noite" if la.inicio.hour >= 18 else "encontro"


def _blocos(db, now: datetime) -> dict[str, datetime]:
    """Fim de cada bloco em casa (pela chave do acontecimento)."""
    try:
        from tempo_livre import TempoLivre
        return {b.chave: b.fim for b in TempoLivre(db).do_dia(now)}
    except Exception:
        logger.exception("hoje.blocos")
        return {}


def _previstos(db, dia: date, now: datetime, saidas: list[dict]) -> list[dict]:
    out = []
    comidas = set()
    try:
        from meals import Meals
        meals = Meals(db)
        comidas = {e["event_key"] for e in meals.eaten_today(now)}
        for s in meals.day_plan(dia):
            if s.skipped or s.key in comidas or s.at <= now:
                continue
            if any(x["ini"] <= s.at < x["fim"] for x in saidas):
                continue                                 # come fora: já está na saída
            nome, ic = REFEICAO_PREVISTA.get(s.kind, ("Refeição", "tools-kitchen-2"))
            out.append({"at": s.at, "ic": ic, "texto": nome})
    except Exception:
        logger.exception("hoje.previsto.refeicoes")
    for s in saidas:
        if s["ini"] > now:                      # 01/10 (catálogo): "Vai para o Shopping da Gávea", na hora em que sai
            out.append({"at": s["ini"], "ic": s["ic"], "texto": s["previsto"]})
    try:
        from watch import Watching
        plano = Watching(db).night_plan(dia)
        if plano and plano["start"] > now and not any(x["ini"] <= plano["start"] < x["fim"] for x in saidas):
            out.append({"at": plano["start"], "ic": "device-tv", "texto": "Série"})
    except Exception:
        logger.exception("hoje.previsto.serie")
    try:
        from sleep_plan import SleepPlan
        bed = SleepPlan(db).bed(dia)
        if bed > now:
            # 28/09 (auditoria): "~21:50 Dormir" e "~21:55 Série" (treinou e o corpo pediu cama) — depois de
            # deitar não tem mais nada previsto
            out = [p for p in out if p["at"] < bed]
            out.append({"at": bed, "ic": "moon", "texto": "Dormir"})
    except Exception:
        logger.exception("hoje.previsto.dormir")
    return sorted(out, key=lambda p: p["at"])


def hoje_view(db, now: datetime) -> dict:
    from db import rodada
    with rodada(db):                  # 28/09 (infra): o plano do dia calculado uma vez pela tela
        return _hoje_view(db, now)


def _hoje_view(db, now: datetime) -> dict:
    dia = dia_de(now)
    ini = datetime.combine(dia, datetime.min.time()) + timedelta(hours=4)
    saidas = _saidas(db, dia, now)
    fins = _blocos(db, now)
    itens: list[dict] = []

    try:
        from sleep_plan import SleepPlan
        wake = SleepPlan(db).wake(dia)
        if wake and ini <= wake <= now:
            itens.append({"at": wake, "ic": "sunrise", "texto": "Acordou", "sub": "", "valor": None,
                          "aviso": False, "fim": None})
    except Exception:
        logger.exception("hoje.acordou")

    for ev in _eventos(db, ini, now):
        if ev["event_type"] in ("meal", "snack") and (ev["event_key"].endswith(":fora") or ":lanche:rua:" in ev["event_key"]
                                                       or ":fora:" in ev["event_key"]):   # 02/10: lanche fora, 2º item
            continue          # 28/09 (auditoria): "Pediu pão de queijo R$ 13" e "Comeu pão de queijo no Starbucks"
        at = datetime.fromisoformat(ev["event_at"])
        it = {"at": at, "key": ev["event_key"], **curto(ev, db)}
        if ev["event_type"] == "tempo_livre" and ev["event_key"] in fins:
            it["fim"] = fins[ev["event_key"]]
            if ev.get("title") and not it.get("presente"):
                it["presente"] = _cap(ev["title"])
        itens.append(it)

    # 27/09: o banho interrompe o que ela fazia em casa (o Instagram 00:02–00:38 com banho às 00:31)
    # e a saída também (27/09: "Montou looks" até 15:11 com a academia às 14:53)
    banhos = [it["at"] for it in itens if it["ic"] == "chuveiro"] + [s["ini"] for s in saidas]
    # 28/09 (auditoria): "Viu o desfile 15:53–16:20" com "Montou looks" começando 16:16
    banhos += [it["at"] for it in itens if it.get("key", "").startswith("livre:")]
    for it in itens:
        corte = next((b for b in banhos if it["ic"] != "chuveiro" and it.get("fim") and it["at"] < b < it["fim"]), None)
        if corte:
            it["fim"] = corte
    # 27/09: o que ainda está acontecendo fica no presente ("Tomando banho 00:31–"), não "Tomou banho 00:31–01:12"
    for it in itens:
        if it.get("fim") and it["fim"] > now:
            it["texto"] = it.get("presente") or _presente(it["texto"])
            it["fim"], it["agora"] = None, True
            if it.get("sub_presente"):
                it["sub"] = it["sub_presente"]
            if it.get("filhos_presente"):          # 01/10 (catálogo): os artistas um por linha enquanto ouve
                it["filhos"], it["sub"] = it["filhos_presente"], ""
            it["filhos"] = [{**f, "texto": f.get("presente") or f["texto"]} for f in it.get("filhos") or []]
    # 01/10 (catálogo): "Topou sair com a Bia" / "Para o Quartinho Bar às 21:00" — a hora vem do convite
    convites = {it["key"].rsplit(":", 1)[0]: it.get("quando") for it in itens
                if it.get("key", "").endswith(":convite") and it.get("quando")}
    for it in itens:
        q = convites.get(it.get("key", "").rsplit(":", 1)[0])
        if it.get("key", "").endswith(":resposta") and q and it.get("sub", "").startswith("Para "):
            it["sub"] += f" {q}"

    # blocos iguais em seguida viram um só ("Montando looks no closet" 13:59 e 14:38)
    juntos: list[dict] = []
    for it in sorted(itens, key=lambda x: x["at"]):
        ant = juntos[-1] if juntos else None
        if ant and ant["texto"] == it["texto"] and ant["ic"] == it["ic"] and not it["valor"]:
            ant["fim"] = max(filter(None, (ant["fim"], it["fim"], it["at"])))
            continue
        juntos.append(it)

    # saídas já começadas: viram item, e o que aconteceu no período entra recuado
    raiz: list[dict] = []
    abertas = [s for s in saidas if s["ini"] <= now]
    for s in abertas:
        raiz.append({"at": s["ini"], "key": s["key"], "fim": s["fim"] if s["fim"] <= now else None, "ic": s["ic"],
                     "texto": s["titulo"], "sub": "", "valor": None, "aviso": False, "filhos": [], "saida": True})
    for it in list(juntos):                           # por que saiu: vira a linha cinza da saída
        if it.get("motivo"):
            chave = (it.get("key") or "").removesuffix(":decidiu")
            alvo = next((r for r in raiz if r.get("key") == chave), None) or next(
                (r for r in raiz if r.get("saida") and it["at"] <= r["at"] + timedelta(minutes=5)
                 and r["at"] - it["at"] <= timedelta(hours=3)), None)
            if alvo:
                alvo["sub"] = it["motivo"]
                juntos.remove(it)
            else:
                it["sub"] = it["motivo"]
    for it in juntos:
        # 28/09: "Olhou o Pinterest 13:35" (já em casa) caía dentro da PUC, que acabava às 13:35
        dono = next((r for r in raiz if r.get("saida") and r["at"] <= it["at"]
                     and (it["at"] < r["fim"] if r["fim"] else it["at"] <= now)), None)
        if dono:
            dono["filhos"].append(it)
            dono["filhos"] += [{"at": it["at"], "fim": None, "valor": None, **f} for f in it.get("filhos") or []]
        else:
            raiz.append({**it, "filhos": [{"at": it["at"], "fim": None, **f} for f in it.get("filhos") or []]})
    # 28/09 (Patrick): a volta pra casa não aparecia — "Foi pra PUC 08:19–13:35" engolia a carona com o Theo
    for s in abertas:
        v, dono = s.get("volta"), next((r for r in raiz if r.get("key") == s["key"] and r.get("saida")), None)
        if v and dono and v.inicio <= now:
            chegou = v.fim <= now
            dono["filhos"].append({"at": v.inicio, "fim": v.fim if chegou else None, "ic": "home",
                                   "texto": "Voltou para casa" if chegou else "Voltando para casa", "sub": v.como,
                                   "valor": None, "aviso": False})       # o uber já tem a linha dele, com valor
    for r in raiz:
        if r.get("filhos"):
            r["filhos"].sort(key=lambda f: f["at"])
    raiz.sort(key=lambda x: x["at"])

    previstos = _previstos(db, dia, now, saidas)
    periodos: dict[str, list] = {}
    for it in raiz:
        periodos.setdefault(_periodo(it["at"], dia), []).append(_linha(it))
    for p in previstos:
        periodos.setdefault(_periodo(p["at"], dia), []).append(
            {"ic": p["ic"], "texto": p["texto"], "sub": "", "hora": _aprox(p["at"]), "valor": None,
             "aviso": False, "filhos": [], "previsto": True})
    ordem = [n for n, *_ in PERIODOS if n in periodos]
    return {"periodos": [{"nome": n, "itens": periodos[n]} for n in ordem]}


PRESENTE = (("Tomou banho e lavou o cabelo", "Tomando banho e lavando o cabelo"), ("Tomou banho", "Tomando banho"),
            ("Tomou café", "Tomando café"), ("Almoçou", "Almoçando"), ("Jantou", "Jantando"), ("Lanchou", "Lanchando"),
            ("Comeu", "Comendo"), ("Assistiu", "Assistindo"), ("Fez as unhas", "Fazendo as unhas"),
            ("Parou para comer", "Comendo"))


def _presente(texto: str) -> str:
    for antes, agora in PRESENTE:
        if texto.startswith(antes):
            return (agora + texto[len(antes):]).replace(" e comeu demais", " e comendo demais")
    return texto


def _linha(it: dict) -> dict:
    fim = it.get("fim")
    em_curso = (it.get("saida") or it.get("agora")) and not fim
    hora = _hm(it["at"]) + ("–" + _hm(fim) if fim and _hm(fim) != _hm(it["at"]) else "–" if em_curso else "")
    return {"ic": it["ic"], "texto": it["texto"], "sub": it.get("sub") or "", "hora": hora,
            "valor": it.get("valor"), "aviso": it.get("aviso", False), "previsto": False,
            "filhos": [{"texto": f["texto"], "sub": f.get("sub") or "", "valor": f.get("valor"),
                        "aviso": f.get("aviso", False),
                        "hora": _hm(f["at"]) + ("–" + _hm(f["fim"]) if f.get("fim") and _hm(f["fim"]) != _hm(f["at"]) else "")}
                       for f in it.get("filhos", [])]}
