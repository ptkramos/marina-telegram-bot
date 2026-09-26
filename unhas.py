"""Unhas como status (Patrick, 26/09 — etapa 1 da frente do mundo: cuidados).

A unha dela existe de verdade: cor, gel ou esmalte comum, feita quando e onde, e vai gastando.
Regra de ouro dele: **tudo acontece de verdade e vira história** — cada vez que ela faz é
acontecimento do dia, o salão sai do saldo dela e a cor manda nas fotos geradas.

Decisões do Patrick (26/09):
- **Duração:** esmalte comum (em casa) gasta em 5–7 dias; gel (no salão) dura 2–3 semanas.
- **Salão:** Ophicina do Cabelo, Rua Voluntários da Pátria, 185 (migration 030). Ela vai na rotina
  (gel a cada ~3 semanas), antes de evento/job e às vezes por mimo — **paga do saldo dela**.
- **Em casa só retoque:** esmalte comum, quando está entediada e com a unha gasta, ou quando o gel
  já passou da hora e o salão não coube.
- **Opinião dele:** às vezes, antes de fazer, ela pergunta a cor ("vermelho ou nude?"); se ele
  responde a tempo, a cor é a dele. **A foto é sempre depois:** se ele participou da escolha ela
  sempre manda a foto da mão pronta; se não, às vezes, por vontade própria.
- **Cores:** clássicas, escuras, candy e da estação — o peso muda com a estação do ano.

Estado em estado_relacional[KEY] (JSON), sem migration:
  atual  → a unha de agora {cor, tipo, feita_em, onde, escolha}
  sessao → a vez em andamento (em casa ou no salão) {onde, inicio, fim, opcoes, pergunta, cor, quem}
"""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

KEY = "unhas_json"
SALAO = "ophicina_do_cabelo_botafogo"
SALAO_NOME = "Ophicina do Cabelo"
SALAO_IDA_MIN = 10                  # Voluntários da Pátria, a pé
SALAO_MIN = 90                      # mão e pé em gel
PRECO_SALAO = 180                   # mão em gel (R$ 110) e pé (R$ 70) — Patrick, 26/09
RESERVA = 100                       # não gasta o saldo todo no salão
PERGUNTA_CHANCE = 0.5               # "às vezes" ela pede a opinião dele antes
PERGUNTA_JANELA = timedelta(minutes=40)   # depois disso a pergunta não sai mais (ela já decidiu)
FOTO_SOZINHA_CHANCE = 0.3           # sem ele na escolha, às vezes manda a foto por vontade própria

# chave → (nome no card/prompt, como vai no prompt da foto, paleta)
CORES = {
    "vermelho": ("Vermelho", "classic glossy red", "classica"),
    "vinho": ("Vinho", "deep burgundy wine", "classica"),
    "nude": ("Nude rosado", "soft pinky nude", "classica"),
    "branco": ("Branco leitoso", "milky sheer white", "classica"),
    "francesinha": ("Francesinha", "classic French manicure with thin white tips", "classica"),
    "preto": ("Preto", "glossy black", "escura"),
    "marsala": ("Marsala", "marsala reddish-brown", "escura"),
    "marinho": ("Azul-marinho", "dark navy blue", "escura"),
    "musgo": ("Verde-musgo", "dark moss green", "escura"),
    "rosa_bebe": ("Rosa bebê", "pastel baby pink", "candy"),
    "lilas": ("Lilás", "pastel lilac", "candy"),
    "azul_claro": ("Azul clarinho", "pastel baby blue", "candy"),
    "chiclete": ("Rosa chiclete", "bright bubblegum pink", "candy"),
    "coral": ("Coral", "bright coral", "estacao"),
    "laranja": ("Laranja", "vivid tangerine orange", "estacao"),
    "amarelo": ("Amarelo", "pastel butter yellow", "estacao"),
    "glitter": ("Glitter", "sparkly silver glitter", "estacao"),
}
# bolinha da cor no painel (Bastidores → Por dentro)
HEX = {"vermelho": "#c0182a", "vinho": "#6d1a2c", "nude": "#e3b5a4", "branco": "#f3eee6", "francesinha": "#f1d9d0",
       "preto": "#1b1b1d", "marsala": "#8a3b3b", "marinho": "#1f2a4d", "musgo": "#4a5a33", "rosa_bebe": "#f4c2d0",
       "lilas": "#c3a6e0", "azul_claro": "#a9cdef", "chiclete": "#f06aa6", "coral": "#f47a5f", "laranja": "#f28a2e",
       "amarelo": "#f5dc85", "glitter": "#c9c9d1"}
# peso de cada paleta pela estação (hemisfério sul): verão, outono, inverno, primavera
PESO_PALETA = {
    "verao": {"classica": 1.0, "escura": 0.3, "candy": 1.0, "estacao": 1.6},
    "outono": {"classica": 1.2, "escura": 1.2, "candy": 0.6, "estacao": 0.5},
    "inverno": {"classica": 1.0, "escura": 1.6, "candy": 0.5, "estacao": 0.3},
    "primavera": {"classica": 1.2, "escura": 0.5, "candy": 1.5, "estacao": 0.8},
}
# o que ele pode responder (a ordem importa: "azul-marinho" antes de "azul")
_COR_RE = (
    ("francesinha", r"francesinh|francesa"), ("vinho", r"vinho|bord[ôo]"), ("marsala", r"marsala"),
    ("marinho", r"marinho"), ("musgo", r"musgo|verde"), ("rosa_bebe", r"rosa\s*beb[êe]|rosinha|rosa\s*clar"),
    ("chiclete", r"chiclete|\bpink\b"), ("lilas", r"lil[áa]s|roxinh|lavanda"),
    ("azul_claro", r"azul\s*clar|azulzinh|azul\s*beb[êe]"), ("vermelho", r"vermelh"), ("nude", r"\bnude\b|natural"),
    ("branco", r"branc"), ("preto", r"pret"), ("coral", r"coral"), ("laranja", r"laranj"), ("amarelo", r"amarel"),
    ("glitter", r"glitter|brilh"),
)
_TANTO_FAZ_RE = re.compile(r"tanto faz|voc[êe] (?:que )?(?:escolhe|decide)|vc (?:que )?(?:escolhe|decide)|"
                           r"qualquer uma|as duas|decide (?:voc[êe]|vc)|escolhe (?:voc[êe]|vc)", re.IGNORECASE)
_PRIMEIRA_RE = re.compile(r"\b(?:a |o )?(?:primeir[ao]|1)\b", re.IGNORECASE)
_SEGUNDA_RE = re.compile(r"\b(?:a |o )?(?:segund[ao]|2)\b", re.IGNORECASE)
_EVENTO_RE = re.compile(r"anivers|festa|casamento|formatura|balada", re.IGNORECASE)


def estacao(when: datetime) -> str:
    m = when.month
    return ("verao" if m in (12, 1, 2) else "outono" if m in (3, 4, 5) else "inverno" if m in (6, 7, 8)
            else "primavera")


def nome(cor: str) -> str:
    return CORES.get(cor, (cor.capitalize(),))[0]


class Unhas:
    def __init__(self, db):
        self.db = db

    # ---------------------------------------------------------------- estado --
    def _limpo(self) -> bool:
        with self.db.get_connection() as conn:
            return bool(conn.execute(
                "SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done'").fetchone())

    def _load(self) -> dict:
        raw = self.db.get_estado_relacional(KEY)
        try:
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    def _save(self, st: dict) -> None:
        self.db.set_estado_relacional(KEY, json.dumps(st, ensure_ascii=False))

    def _state(self, now: datetime) -> dict:
        """Estado, com a unha de partida na primeira vez: nude em gel, feita no salão há 9 dias."""
        st = self._load()
        if not st.get("atual") and self._limpo():
            st["atual"] = {"cor": "nude", "tipo": "gel", "onde": "salao", "escolha": "ela",
                           "feita_em": (now - timedelta(days=9)).replace(hour=15, minute=0, second=0,
                                                                         microsecond=0).isoformat()}
            self._save(st)
        return st

    def atual(self, now: datetime) -> Optional[dict]:
        """A unha de agora, com a idade e a condição ({cor, tipo, dias, condicao, gasta…})."""
        a = self._state(now).get("atual")
        if not a:
            return None
        dias = max(0.0, (now - datetime.fromisoformat(a["feita_em"])).total_seconds() / 86400)
        if a["tipo"] == "gel":
            condicao = ("perfeita" if dias < 12 else "crescendo" if dias < 18 else "pedindo manutenção"
                        if dias < 24 else "descascando")
            gasta = dias >= 18
        else:
            condicao = ("perfeita" if dias < 3 else "começando a gastar" if dias < 5 else "gastando"
                        if dias < 7 else "descascando")
            gasta = dias >= 5
        return {**a, "dias": dias, "condicao": condicao, "gasta": gasta}

    def sessao(self, now: datetime) -> Optional[dict]:
        s = self._load().get("sessao")
        return s if s and not s.get("finalizada") else None

    # ------------------------------------------------------------ escolha --
    def _sorteia_cor(self, when: datetime, rng: random.Random, evita: tuple = (), festa: bool = False) -> str:
        pesos = PESO_PALETA[estacao(when)]
        cores = [c for c in CORES if c not in evita and (c != "glitter" or festa)]
        return rng.choices(cores, weights=[pesos[CORES[c][2]] for c in cores])[0]

    def _nova_sessao(self, st: dict, onde: str, inicio: datetime, fim: datetime, now: datetime,
                     rng: random.Random, *, chave: str = "", motivo: str = "") -> dict:
        antes = (st.get("atual") or {}).get("cor")
        festa = motivo == "festa"
        a = self._sorteia_cor(inicio, rng, (antes,) if antes else (), festa)
        s = {"onde": onde, "inicio": inicio.isoformat(), "fim": fim.isoformat(), "chave": chave, "motivo": motivo,
             "cor": None, "quem": None, "decidida_em": None, "finalizada": False}
        if rng.random() < PERGUNTA_CHANCE:
            b = self._sorteia_cor(inicio, rng, (antes, a) if antes else (a,), festa)
            s["opcoes"] = [a, b]
            s["pergunta"] = {"status": "pendente", "criada": now.isoformat()}
        else:
            s["cor"], s["quem"], s["decidida_em"] = a, "ela", now.isoformat()
        st["sessao"] = s
        return s

    def _prazo_cor(self, s: dict) -> datetime:
        """Até quando a resposta dele ainda conta: em casa, 15 min depois de começar (tirou o esmalte
        velho e vai passar a base); no salão, quando ela senta na cadeira."""
        ini = datetime.fromisoformat(s["inicio"])
        return ini + timedelta(minutes=15) if s["onde"] == "casa" else ini + timedelta(minutes=5)

    def _decide_cor(self, st: dict, now: datetime) -> Optional[str]:
        s = st.get("sessao")
        if not s or s.get("cor"):
            return s.get("cor") if s else None
        if now < self._prazo_cor(s):
            return None
        s["cor"], s["quem"], s["decidida_em"] = s["opcoes"][0], "ela", now.isoformat()
        p = s.get("pergunta") or {}
        if p.get("status") in ("pendente", "enviada"):
            p["status"] = "sem_resposta"
        return s["cor"]

    # ------------------------------------------------------------ em casa --
    def quer_em_casa(self, now: datetime, inicio: datetime, rng: random.Random) -> bool:
        """Bloco de tempo livre: ela resolve fazer as unhas agora? (puro: não grava nada)
        Só retoque: esmalte comum gasto e ela entediada, ou gel vencido sem salão marcado."""
        if not (9 <= inicio.hour < 23) or self.sessao(now):
            return False
        a = self.atual(now)
        if not a or not a["gasta"]:
            return False
        if a["tipo"] == "gel" and a["dias"] < 24:
            return False                                  # gel: quem resolve é o salão
        if self._salao_marcado(now):
            return False
        entediada = False
        try:
            from emotion import EmotionEngine
            entediada = any(e.family == "tedio" for e in EmotionEngine(self.db).feeling(now).episodes)
        except Exception:
            pass
        chance = 0.6 if entediada else (0.15 if self._a_toa(inicio) else 0.0)
        return rng.random() < chance

    def _a_toa(self, inicio: datetime) -> bool:
        """Tarde/noite sem nada marcado pelas próximas 2 h (o tédio de quem não tem o que fazer)."""
        if not (13 <= inicio.hour < 23):
            return False
        with self.db.get_connection() as conn:
            row = conn.execute(
                """SELECT 1 FROM eventos_pendentes WHERE confirmed=1 AND status!='cancelled'
                   AND event_at>? AND event_at<? LIMIT 1""",
                (inicio.isoformat(), (inicio + timedelta(hours=2)).isoformat())).fetchone()
        return not row

    def comecou_em_casa(self, inicio: datetime, fim: datetime, now: datetime, chave: str) -> dict:
        """O bloco "Fazendo as unhas" foi registrado: vira a sessão (pode perguntar a cor pra ele)."""
        st = self._state(now)
        rng = random.Random(f"unhas:casa:{chave}")
        s = self._nova_sessao(st, "casa", inicio, fim, now, rng, chave=chave)
        self._save(st)
        logger.info("unhas.casa inicio=%s pergunta=%s", inicio.isoformat(timespec="minutes"), bool(s.get("opcoes")))
        return s

    def texto_bloco(self, now: datetime) -> str:
        s = self.sessao(now)
        return f"Fazendo as unhas · {nome(s['cor'])}" if s and s.get("cor") else "Fazendo as unhas"

    # -------------------------------------------------------------- salão --
    def _salao_marcado(self, now: datetime) -> bool:
        s = self.sessao(now)
        return bool(s and s["onde"] == "salao")

    def _evento_perto(self, now: datetime) -> Optional[str]:
        """Job, casting, encontro ou festa nas próximas 48 h: 'trabalho' | 'encontro' | 'festa'."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """SELECT event_type, description FROM eventos_pendentes WHERE confirmed=1 AND status!='cancelled'
                   AND event_at>? AND event_at<?""", (now.isoformat(), (now + timedelta(hours=48)).isoformat())).fetchall()
        for r in rows:
            if r["event_type"] == "trabalho":
                return "trabalho"
            if r["event_type"] == "encontro":
                return "encontro"
            if _EVENTO_RE.search(r["description"] or ""):
                return "festa"
        return None

    def _saldo(self, now: datetime) -> int:
        try:
            import financas
            return int(financas._init(financas._load(self.db), now)["saldo"])
        except Exception:
            return 0

    def talvez_salao(self, now: datetime) -> Optional[int]:
        """Chamado pelo mundo quando ela está livre em casa: marca a manicure (rotina, evento ou mimo)."""
        if not self._limpo() or now.weekday() == 6 or not (9 <= now.hour < 18):
            return None
        st = self._state(now)
        if self.sessao(now) or st.get("salao_dia") == now.date().isoformat():
            return None
        a = self.atual(now)
        if not a:
            return None
        d, gel = a["dias"], a["tipo"] == "gel"
        evento = self._evento_perto(now)
        slot = (now.hour * 60 + now.minute) // 20
        rng = random.Random(f"unhas:salao:{now.date().isoformat()}:{slot}")
        if evento and (d >= 8 if gel else d >= 2):
            motivo, chance = evento, 0.35
        elif d >= 18 if gel else d >= 7:
            motivo, chance = "rotina", 0.15
        elif (d >= 12 if gel else d >= 4) and self._saldo(now) >= 600:
            motivo, chance = "mimo", 0.02
        else:
            return None
        if rng.random() >= chance or self._saldo(now) < PRECO_SALAO + RESERVA:
            return None
        from vontade import Vontade
        v = Vontade(self.db)
        livre = v._livre_ate(now)
        prep = rng.randint(8, 12)
        inicio = now + timedelta(minutes=prep + SALAO_IDA_MIN)
        fim = inicio + timedelta(minutes=SALAO_MIN)
        fecha = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if not livre or fim + timedelta(minutes=SALAO_IDA_MIN + 20) > livre or fim > fecha:
            return None
        chave = f"unhas:{now.date().isoformat()}:{now:%H%M}"
        texto = f"Fazendo as unhas na {SALAO_NOME}"
        cid = v.agendar("manicure", SALAO, inicio, fim, texto, origem="planejado" if motivo == "rotina" else "vontade",
                        decidido_em=now, chave=chave, ida_min=SALAO_IDA_MIN,
                        extra={"motivo": MOTIVO_TXT[motivo], "preco": PRECO_SALAO})
        if not cid:
            return None
        st["salao_dia"] = now.date().isoformat()
        self._nova_sessao(st, "salao", inicio, fim, now, rng, chave=chave, motivo=motivo)
        self._save(st)
        v._registra(chave, now, f"Marcou a manicure na {SALAO_NOME} ({MOTIVO_TXT[motivo]}).")
        logger.info("unhas.salao motivo=%s inicio=%s", motivo, inicio.isoformat(timespec="minutes"))
        return cid

    # ----------------------------------------------------------- a pergunta --
    def pergunta_pendente(self, now: datetime) -> Optional[dict]:
        """A pergunta da cor que ainda não saiu (proatividade): {opcoes, onde, detail}."""
        st = self._load()
        s = st.get("sessao")
        p = (s or {}).get("pergunta")
        if not s or s.get("finalizada") or not p or p.get("status") != "pendente":
            return None
        if now - datetime.fromisoformat(p["criada"]) > PERGUNTA_JANELA or now >= self._prazo_cor(s):
            p["status"] = "nao_saiu"
            self._save(st)
            return None
        a, b = (nome(c).lower() for c in s["opcoes"])
        onde = "em casa agora" if s["onde"] == "casa" else f"na {SALAO_NOME} daqui a pouco"
        return {"opcoes": s["opcoes"], "onde": s["onde"],
                "detail": f"Você vai fazer as unhas {onde} e está em dúvida entre {a} e {b}."}

    def marca_pergunta_enviada(self, now: datetime) -> None:
        st = self._load()
        p = (st.get("sessao") or {}).get("pergunta")
        if p:
            p.update(status="enviada", enviada=now.isoformat())
            self._save(st)

    def observe_patrick(self, text: str, now: datetime) -> Optional[str]:
        """Resposta dele à pergunta da cor: vira a cor de verdade (se ainda dá tempo)."""
        st = self._load()
        s = st.get("sessao")
        p = (s or {}).get("pergunta")
        if not s or s.get("finalizada") or not p or p.get("status") != "enviada" or s.get("cor"):
            return None
        if now > self._prazo_cor(s) + timedelta(minutes=5):
            return None
        low = (text or "").lower()
        cor = None
        if _TANTO_FAZ_RE.search(low):
            cor, quem = s["opcoes"][0], "ela"
        else:
            achadas = [(m.start(), c) for c, rx in _COR_RE if (m := re.search(rx, low))]
            if achadas:
                cor, quem = min(achadas)[1], "patrick"
            elif _SEGUNDA_RE.search(low) and not _PRIMEIRA_RE.search(low):
                cor, quem = s["opcoes"][1], "patrick"
            elif _PRIMEIRA_RE.search(low):
                cor, quem = s["opcoes"][0], "patrick"
        if not cor:
            return None
        s["cor"], s["quem"], s["decidida_em"] = cor, quem, now.isoformat()
        p["status"] = "respondida"
        self._save(st)
        logger.info("unhas.escolha cor=%s quem=%s", cor, quem)
        return cor

    # --------------------------------------------------------- acontecimento --
    def materialize(self, now: datetime) -> int:
        """Decide a cor quando chega a hora e fecha a vez que terminou (acontecimento, saldo, foto)."""
        st = self._load()
        s = st.get("sessao")
        if not s or s.get("finalizada"):
            return 0
        if s["onde"] == "salao" and self._cancelado(s["chave"]):
            st["sessao"] = None
            self._save(st)
            return 0
        antes = s.get("cor")
        self._decide_cor(st, now)
        mudou = s.get("cor") != antes
        fim = datetime.fromisoformat(self._fim_real(s))
        if now < fim:
            if mudou:
                self._save(st)
            return 0
        cor, quem = s["cor"], s["quem"]
        gel = s["onde"] == "salao"
        st["atual"] = {"cor": cor, "tipo": "gel" if gel else "comum", "onde": s["onde"], "escolha": quem,
                       "feita_em": fim.isoformat()}
        s["finalizada"] = True
        escolha = " — a cor que o Patrick escolheu" if quem == "patrick" else ""
        if gel:
            key, tipo = f"compra:{s['chave']}", "consumo"
            title = f"{SALAO_NOME} · unhas em gel"
            summary = f"Fez as unhas em gel (mão e pé) na {SALAO_NOME}: {nome(cor).lower()}{escolha} (R$ {PRECO_SALAO})."
        else:
            key, tipo = f"unhas:{s['chave']}", "tempo_livre"
            title = "Fez as unhas em casa"
            summary = f"Fez as unhas em casa, esmalte {nome(cor).lower()}{escolha}."
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,?,?,?,'simulated',1,0.3,?,0.5,?)""",
                (key, fim.isoformat(), tipo, title, summary, json.dumps(["marina"]), now.isoformat()))
            conn.commit()
        rng = random.Random(f"unhas:foto:{s['chave']}")
        if quem == "patrick" or rng.random() < FOTO_SOZINHA_CHANCE:
            try:
                import promessa_foto
                due = fim + timedelta(minutes=rng.randint(2, 6))
                if not promessa_foto.pending(self.db):
                    promessa_foto.promise_unhas(self.db, nome(cor).lower(), due, now, pediu=quem == "patrick")
            except Exception:
                logger.exception("unhas.foto")
        self._save(st)
        logger.info("unhas.feita cor=%s onde=%s quem=%s", cor, s["onde"], quem)
        return 1

    def _cancelado(self, chave: str) -> bool:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT status FROM eventos_pendentes WHERE source_key=?", (chave,)).fetchone()
        return bool(row and row["status"] == "cancelled")

    def _fim_real(self, s: dict) -> str:
        """Saiu mais cedo do salão (agenda reativa)? Vale o fim novo."""
        if s["onde"] != "salao":
            return s["fim"]
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT end_at FROM eventos_pendentes WHERE source_key=?", (s["chave"],)).fetchone()
        return row["end_at"] if row and row["end_at"] else s["fim"]

    # --------------------------------------------------------- foto e prompt --
    def visual(self, now: datetime) -> str:
        """Frase da unha pro prompt da foto (a cor de agora manda)."""
        s = self.sessao(now)
        if s and s.get("cor") and datetime.fromisoformat(s["inicio"]) + timedelta(minutes=20) <= now:
            return f"Her fingernails are freshly painted in {CORES[s['cor']][1]} nail polish, still glossy."
        a = self.atual(now)
        if not a or a["cor"] not in CORES:
            return ""
        en = CORES[a["cor"]][1]
        kind = "gel polish" if a["tipo"] == "gel" else "nail polish"
        if a["condicao"] == "perfeita":
            return f"Her fingernails are neatly done in {en} {kind}, glossy and flawless."
        if a["condicao"] == "crescendo":
            return f"Her fingernails are done in {en} {kind}, with a thin natural gap growing at the cuticles."
        if a["condicao"] in ("começando a gastar", "gastando", "pedindo manutenção"):
            return f"Her fingernails are painted in {en} {kind}, slightly worn at the tips."
        return f"Her {en} {kind} is chipped at the tips of her fingernails."

    def painel(self, now: datetime) -> Optional[dict]:
        """Seção "Unhas" do Por dentro (Patrick, 26/09): a cor na linha 2, a barra de desgaste e,
        embaixo, Estado, Tipo e Feita."""
        s = self.sessao(now)
        if s and datetime.fromisoformat(s["inicio"]) <= now:
            cor = s.get("cor")
            return {"cor": nome(cor) if cor else "Escolhendo a cor", "hex": HEX.get(cor or "", ""), "desgaste": 0.0,
                    "gasta": False, "estado": "Fazendo agora",
                    "tipo": "Gel" if s["onde"] == "salao" else "Esmalte",
                    "feita": f"Agora, na {SALAO_NOME}" if s["onde"] == "salao" else "Agora, em casa"}
        a = self.atual(now)
        if not a:
            return None
        d = int(a["dias"])
        quando = "Hoje" if d == 0 else "Ontem" if d == 1 else f"Há {d} dias"
        onde = f"na {SALAO_NOME}" if a["onde"] == "salao" else "em casa"
        return {"cor": nome(a["cor"]), "hex": HEX.get(a["cor"], ""),
                "desgaste": round(min(1.0, a["dias"] / (24 if a["tipo"] == "gel" else 7)), 2), "gasta": a["gasta"],
                "estado": a["condicao"][:1].upper() + a["condicao"][1:],
                "tipo": "Gel" if a["tipo"] == "gel" else "Esmalte", "feita": f"{quando}, {onde}"}

    def prompt_lines(self, now: datetime) -> list[str]:
        a = self.atual(now)
        if not a:
            return []
        d = int(a["dias"])
        quando = "hoje" if d == 0 else "ontem" if d == 1 else f"há {d} dias"
        onde = f"na {SALAO_NOME}" if a["onde"] == "salao" else "em casa"
        tipo = "em gel" if a["tipo"] == "gel" else "esmalte comum"
        escolha = ", a cor que o Patrick escolheu" if a.get("escolha") == "patrick" else ""
        lines = ["[SUAS UNHAS — de verdade; a cor aparece nas suas fotos, não invente outra]",
                 f"- {nome(a['cor'])}, {tipo}, feitas {onde} {quando}{escolha} ({a['condicao']})."]
        s = self.sessao(now)
        if s:
            ini = datetime.fromisoformat(s["inicio"])
            p = s.get("pergunta") or {}
            if s.get("opcoes") and p.get("status") == "enviada" and not s.get("cor"):
                a1, b1 = (nome(c).lower() for c in s["opcoes"])
                lines.append(f"- Você perguntou pro Patrick que cor fazer ({a1} ou {b1}). Se ele escolher agora, "
                             "é essa que você faz — pode ser qualquer cor que ele disser.")
            elif s.get("cor") and s.get("quem") == "patrick":
                lines.append(f"- Ele escolheu {nome(s['cor']).lower()} e é o que você está fazendo.")
            elif p.get("status") == "sem_resposta":
                lines.append(f"- Você perguntou a cor pro Patrick, ele não respondeu a tempo e você foi de "
                             f"{nome(s['cor']).lower()}.")
            if s["onde"] == "salao" and now < ini:
                lines.append(f"- Marcou a manicure na {SALAO_NOME} às {ini:%H:%M} (mão e pé em gel, R$ {PRECO_SALAO}, "
                             "você paga).")
            elif now >= ini:
                cor = f" ({nome(s['cor']).lower()})" if s.get("cor") else ""
                lines.append(f"- Você está fazendo as unhas agora{cor}"
                             + (f" na {SALAO_NOME}." if s["onde"] == "salao" else " em casa — esmalte secando, "
                                "digita devagar."))
        return lines


MOTIVO_TXT = {"rotina": "o gel já tava pedindo manutenção", "trabalho": "tem job chegando",
              "encontro": "tem encontro chegando", "festa": "tem festa chegando", "mimo": "quis se dar um mimo"}
