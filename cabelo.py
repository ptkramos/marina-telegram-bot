"""Cabelo como status (Patrick, 26/09 — etapa 1 da frente do mundo: cuidados; mesmo molde das unhas).

O cabelo dela existe de verdade: dia de lavar, como está agora (penteado), corte, luzes e hidratação.
Regra de ouro dele: **tudo acontece de verdade e vira história** — a lavagem acontece no banho, o salão
sai do saldo dela e vira acontecimento, e o cabelo de agora manda nas fotos geradas.

Decisões do Patrick (26/09):
- **Lavagem dia sim, dia não:** lava no 2º dia, ou antes se foi à academia/praia ou vai sair à noite;
  3º dia = oleoso, fica preso. Lavar deixa o banho mais longo; depois seca natural ou no secador.
- **Salão = Ophicina do Cabelo** (a mesma das unhas). Junta o que está vencido numa ida só: corte de pontas
  (R$ 150), tonalização (R$ 250), hidratação (R$ 120), escova (R$ 70; sempre depois de corte ou cor, e
  sozinha antes de evento). **Paga do saldo dela.**
- **Em casa:** lavagem no banho, umectação no tempo livre (entediada e cabelo ressecado) e o penteado pra sair.
- **Opinião dele:** às vezes pergunta o penteado antes de sair ("solto ou preso?") e o corte/cor no salão.
  Se ele sugerir no chat ("fica linda de franja"), ela pode aderir na próxima ida.
- **Mudanças que aparecem nas fotos** (testadas em 26/09 com o LoRA, o rosto se mantém): cortes reto, repicado,
  franja cortina e franja cheia; luzes dourado (padrão), bege claro, pontas rosa (tonalizante que desbota em
  ~3–4 semanas) e loira iluminada (mudança rara). O comprimento continua longo.
- **Foto depois:** sempre se ele opinou; às vezes por vontade. No salão quem tira é alguém de lá (ela de
  capa na cadeira); em casa é selfie no espelho ou no tripé.

Estado em estado_relacional[KEY] (JSON), sem migration:
  lavado_em, secagem ("natural" | "secador" | "escova_salao"), molhado_ate, lavar (umectou: lava no próximo banho)
  corte, cortado_em · tom, tonalizado_em · rosa_em · hidratado_em, hidratado_onde
  saida  → o penteado da saída de agora {chave, estilo, opcoes, pergunta, quem, desde, ate, pronto}
  sessao → a ida ao salão {inicio, fim, chave, servicos, mudanca, opcoes, pergunta, escolha, quem, motivo}
  sugestao → a mudança que o Patrick sugeriu no chat {mudanca, em}
"""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Optional

from unhas import RESERVA, SALAO, SALAO_IDA_MIN, SALAO_NOME, motivo_txt

logger = logging.getLogger(__name__)

KEY = "cabelo_json"
VIRA_O_DIA = 5                      # 28/09 (Patrick): a madrugada antes de acordar ainda é a noite anterior


def _dia(at: datetime):
    return (at - timedelta(hours=VIRA_O_DIA)).date()


PERGUNTA_JANELA = timedelta(minutes=40)
PENTEADO_PERGUNTA_CHANCE = 0.4      # antes de sair à noite/encontro, "às vezes" pergunta solto ou preso
SALAO_PERGUNTA_CHANCE = 0.5         # corte/cor no salão
MUDAR_CHANCE = 0.15                 # numa ida de rotina, às vezes dá vontade de mudar
FOTO_SOZINHA_CHANCE = 0.25
CAPA = ("a black hairdresser cape fastened at her neck and draped over her shoulders and body, "
        "a white ribbed tank top underneath")

# serviço → (nome no acontecimento, preço, minutos, passo no card — curto, revisado com o Patrick em 26/09)
SERVICOS = {
    "loira": ("luzes no cabelo todo", 650, 220, "Luzes"),
    "retoque": ("retoque das luzes", 450, 150, "Retoque das luzes"),
    "tonalizar": ("tonalização", 250, 80, "Tonalização"),
    "rosa": ("pontas rosa", 220, 80, "Pontas rosa"),
    "hidratacao": ("hidratação", 120, 35, "Hidratação"),
    "corte": ("corte", 150, 40, "Corte das pontas"),
    "escova": ("escova", 70, 40, "Escova"),
}
ORDEM = ("loira", "retoque", "tonalizar", "rosa", "hidratacao", "corte", "escova")

# corte → (nome, o que entra no prompt da foto depois da cor)
CORTES = {
    "reto": ("Reto", ""),
    "repicado": ("Repicado", ", cut in soft long layers that frame her face"),
    "cortina": ("Franja cortina", " and soft curtain bangs parted in the middle framing her face"),
    "franja": ("Franja", " and thick full blunt bangs cut straight across that cover her forehead down to her "
                         "eyebrows"),
}
# tom → (nome, cabelo com a cor em dia, cabelo com a cor vencida, bolinha no painel, prazo em dias)
TONS = {
    "dourado": ("Dourado", "long chestnut brown hair with golden blonde tips",
                "long chestnut brown hair with brassy, faded golden blonde tips", "#d9a54a", 56),
    "bege": ("Bege claro", "long chestnut brown hair with light cool beige blonde tips",
             "long chestnut brown hair with slightly brassy beige blonde tips", "#e3d3b5", 56),
    "loira": ("Loira iluminada", "long fully blonde hair with bright golden and beige highlights from root to tips",
              "long blonde hair with bright golden and beige highlights and darker brown roots growing in",
              "#e8c77a", 49),
}
ROSA_HEX = "#f2a7c3"
ROSA_NOVO, ROSA_SOME = 12, 25       # dias: rosa vivo, desbotando, sumiu (volta o tom de base)

# mudança (opção no salão ou sugestão dele) → (como ela fala, regex da resposta/sugestão dele)
MUDANCAS = {
    "pontas": ("só as pontas", r"s[óo] (?:as )?pont|pontinh|mant[eé]m|do jeito que t[aá]|n[ãa]o muda"),
    "repicado": ("repicar", r"repic|camad"),
    "cortina": ("franja cortina", r"cortina|franja (?:aberta|lateral|de lado)"),
    "franja": ("franja", r"franj"),
    "reto": ("tirar as camadas e deixar reto", r"\breto\b|sem camada"),
    "dourado": ("manter o dourado", r"dourad|mel\b"),
    "bege": ("pontas bege", r"bege|mais clar|platinad|frio"),
    "rosa": ("pontas rosa", r"\brosa\b|pink|rosinha"),
    "loira": ("ficar loira", r"loir[ao]|iluminad|luzes no cabelo todo"),
}
CORTE_MUDANCAS = ("pontas", "repicado", "cortina", "franja", "reto")
_SUGESTAO_CTX = re.compile(r"cabelo|franj|luzes|mecha|loir|pontas|repic|pinta", re.IGNORECASE)
_SUGESTAO_VERBO = re.compile(r"fica(?:r|ria)? (?:linda|lindo|gata|bem|perfeita)|devia|deveria|faz(?:er)?|pinta|"
                             r"que tal|queria (?:te )?ver|imagina", re.IGNORECASE)
_TANTO_FAZ_RE = re.compile(r"tanto faz|voc[êe] (?:que )?(?:escolhe|decide)|vc (?:que )?(?:escolhe|decide)|"
                           r"qualquer um|decide (?:voc[êe]|vc)|escolhe (?:voc[êe]|vc)", re.IGNORECASE)
_PRIMEIRA_RE = re.compile(r"\b(?:a |o )?(?:primeir[ao]|1)\b", re.IGNORECASE)
_SEGUNDA_RE = re.compile(r"\b(?:a |o )?(?:segund[ao]|2)\b", re.IGNORECASE)
_EVENTO_RE = re.compile(r"anivers|festa|casamento|formatura|balada", re.IGNORECASE)

# penteado → (nome no painel/prompt, como vai no prompt da foto)
ESTILOS = {
    "natural": ("Solto natural", "semi-straight with soft waves at the ends"),
    "babyliss": ("Solto com babyliss", "styled in loose glossy curls made with a curling iron"),
    "escova": ("Escova lisa", "blow-dried smooth and straight with a glossy finish"),
    "secador": ("Escovado", "blow-dried smooth with soft volume"),
    "rabo_alto": ("Rabo alto", "pulled back in a sleek high ponytail"),
    "rabo_baixo": ("Rabo baixo", "tied back in a low ponytail"),
    "coque": ("Coque despojado", "tied up in an effortless low bun with a few loose strands framing her face"),
    "meio_preso": ("Meio preso", "half-up, half-down with soft waves"),
    "tranca": ("Trança lateral", "in a loose side braid over one shoulder"),
    "piranha": ("Preso com piranha", "twisted up and held with a claw clip"),
    "coque_oleoso": ("Preso num coque", "tied up in a messy bun, slightly greasy at the roots"),
    "coque_frouxo": ("Coque frouxo", "tied up in a loose messy bun"),
    "academia": ("Rabo de cavalo", "pulled back in a high ponytail"),
    "touca": ("Umectando", "tied up in a bun under a clear plastic shower cap, glossy with hair oil"),
    "molhado": ("Secando natural", "damp and air-drying, slightly wavy"),
    "secando": ("No secador", "half-dry, being blow-dried"),
    "banho": ("No banho", "soaking wet from the shower"),
}
PENTEADO_SAIDA = {
    "noite": ("babyliss", "escova", "rabo_alto", "meio_preso", "coque"),
    "encontro": ("babyliss", "natural", "meio_preso", "escova", "coque"),
    "jogo": ("rabo_alto", "tranca", "natural"),
    "praia": ("coque", "tranca", "piranha"),
    "academia": ("academia",),
}
PENTEADO_DIA = ("natural", "rabo_baixo", "coque", "piranha", "tranca", "meio_preso")
SEM_PENTEADO = ("dormir", "milo", "freela", "cabelo")     # freela: o cabelo é feito lá


def _nome_mudanca(m: str) -> str:
    return MUDANCAS[m][0]


class Cabelo:
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
        """Estado, com o cabelo de partida na primeira vez: lavado ontem, corte reto há 5 semanas e
        pontas douradas há 6 (Ophicina), hidratação há 8 dias."""
        st = self._load()
        if not st.get("corte") and self._limpo():
            dia = now.replace(hour=15, minute=0, second=0, microsecond=0)
            st.update({"lavado_em": (now - timedelta(days=1)).replace(hour=20, minute=0, second=0,
                                                                        microsecond=0).isoformat(),
                       "secagem": "natural", "corte": "reto", "cortado_em": (dia - timedelta(days=35)).isoformat(),
                       "tom": "dourado", "tonalizado_em": (dia - timedelta(days=42)).isoformat(),
                       "hidratado_em": (dia - timedelta(days=8)).isoformat(), "hidratado_onde": "salao"})
            self._save(st)
        return st

    @staticmethod
    def _dias(st: dict, campo: str, now: datetime) -> float:
        v = st.get(campo)
        return max(0.0, (now - datetime.fromisoformat(v)).total_seconds() / 86400) if v else 0.0

    def _dia_lavagem(self, st: dict, now: datetime) -> int:
        """0 = lavado hoje, 1 = 2º dia, 2 = 3º dia (oleoso). 28/09 (Patrick): o dia vira às 5h — lavou à 0h06
        antes de dormir é "ontem à noite", e de manhã já é o 2º dia."""
        v = st.get("lavado_em")
        return (_dia(now) - _dia(datetime.fromisoformat(v))).days if v else 1

    def sessao(self, now: datetime) -> Optional[dict]:
        s = self._load().get("sessao")
        return s if s and not s.get("finalizada") else None

    # ------------------------------------------------------------- condição --
    def _rosa(self, st: dict, now: datetime) -> Optional[str]:
        """'viva' | 'desbotando' | None (o tonalizante rosa já saiu)."""
        if not st.get("rosa_em"):
            return None
        d = self._dias(st, "rosa_em", now)
        return "viva" if d < ROSA_NOVO else "desbotando" if d < ROSA_SOME else None

    def condicao(self, now: datetime) -> Optional[dict]:
        st = self._state(now)
        if not st.get("corte"):
            return None
        lav = self._dia_lavagem(st, now)
        cd = self._dias(st, "cortado_em", now)
        tom = st.get("tom", "dourado")
        td, prazo = self._dias(st, "tonalizado_em", now), TONS[tom][4]
        hd = self._dias(st, "hidratado_em", now)
        luzes = ("Nova" if td < 14 else "Boa" if td < prazo * 0.75 else "Desbotando" if td < prazo
                 else ("Raiz aparecendo" if tom == "loira" else "Amarelada"))
        return {
            "lavagem": ("Lavado hoje" if lav <= 0 else "2º dia" if lav == 1 else "3º dia" if lav == 2 else "Oleoso"),
            "lavagem_dia": lav,
            "pontas": "Boas" if cd < 45 else "Crescendo" if cd < 70 else "Pedindo corte" if cd < 90 else "Ressecadas",
            "corte_dias": cd, "luzes": luzes, "luzes_dias": td, "luzes_prazo": prazo,
            "hidratacao": "Macio" if hd < 10 else "Normal" if hd < 18 else "Ressecado", "hidratacao_dias": hd,
            "rosa": self._rosa(st, now), "corte": self._corte_atual(st, now), "tom": tom,
        }

    def _corte_atual(self, st: dict, now: datetime) -> str:
        """A franja cresce: a cheia vira cortina em ~6 semanas; a cortina some nas camadas em ~10."""
        corte, d = st.get("corte", "reto"), self._dias(st, "cortado_em", now)
        if corte == "franja" and d >= 42:
            return "cortina" if d < 70 else "repicado"
        if corte == "cortina" and d >= 70:
            return "repicado"
        return corte

    # ------------------------------------------------------------ penteado --
    def _atividade(self) -> str:
        try:
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT activity FROM world_state ORDER BY id DESC LIMIT 1").fetchone()
            return (row["activity"] or "").lower() if row else ""
        except Exception:
            return ""

    def _no_banho(self, now: datetime) -> bool:
        try:
            from rituals import Rituals
            return Rituals(self.db).in_shower(now)
        except Exception:
            return False

    def penteado(self, now: datetime) -> str:
        """A chave de ESTILOS de agora (o que o painel mostra e a foto usa)."""
        st = self._state(now)
        if self._no_banho(now):
            return "banho"
        s = self.sessao(now)
        if s and datetime.fromisoformat(s["inicio"]) <= now:
            return "escova" if "escova" in s["servicos"] else "molhado"
        if st.get("molhado_ate") and now < datetime.fromisoformat(st["molhado_ate"]):
            return "secando" if st.get("secagem") == "secador" else "molhado"
        if st.get("umectando_ate") and now < datetime.fromisoformat(st["umectando_ate"]):
            return "touca"
        sa = st.get("saida")
        if sa and sa.get("estilo") and datetime.fromisoformat(sa["desde"]) <= now < datetime.fromisoformat(sa["ate"]):
            return sa["estilo"]
        act = self._atividade()
        if "academia" in act or "treinando" in act:
            return "academia"
        if "dormindo" in act:
            return "coque_frouxo"
        lav = self._dia_lavagem(st, now)
        if st.get("secagem") == "escova_salao" and lav <= 2:
            return "escova"
        if lav >= 2:
            return "coque_oleoso" if random.Random(f"cabelo:preso:{now.date()}").random() < 0.6 else "rabo_baixo"
        return "secador" if st.get("secagem") == "secador" else "natural"

    # ---------------------------------------------------------------- banho --
    def banho(self, inicio: datetime, minutos: int, now: datetime) -> int:
        """Chamado quando ela entra no banho (rituals.start_shower): lava o cabelo hoje? Devolve os minutos
        a mais do banho (0 = não lavou). A secagem é decidida junto."""
        st = self._state(now)
        if not st.get("corte"):
            return 0
        lav = self._dia_lavagem(st, inicio)
        rng = random.Random(f"cabelo:banho:{inicio.isoformat(timespec='minutes')}")
        saindo = self._vai_sair(inicio)
        if st.get("lavar"):
            lava = True
        elif lav <= 0:
            lava = False
        elif st.get("secagem") == "escova_salao" and lav <= 2 and not saindo:
            lava = False                                      # protege a escova do salão (touca no banho)
        elif lav >= 2:
            lava = True
        else:                                                 # 2º dia: academia, praia ou vai sair → lava
            lava = rng.random() < (0.8 if (saindo or self._suou(st, inicio)) else 0.15)
        if not lava:
            return 0
        extra = rng.randint(8, 12)
        fim = inicio + timedelta(minutes=minutos + extra)
        if saindo:
            secagem = "secador"
        elif inicio.hour >= 21:
            secagem = "secador" if rng.random() < 0.6 else "natural"
        else:
            secagem = "secador" if rng.random() < 0.4 else "natural"
        st.update({"lavado_em": inicio.isoformat(), "secagem": secagem, "lavar": False,
                   "umectando_ate": None,
                   "molhado_ate": (fim + timedelta(minutes=15 if secagem == "secador" else rng.randint(100, 150))
                                   ).isoformat()})
        sa = st.get("saida")
        if sa and datetime.fromisoformat(sa["ate"]) <= inicio:
            st["saida"] = None
        self._save(st)
        logger.info("cabelo.lavou secagem=%s", secagem)
        return extra

    def _vai_sair(self, when: datetime) -> bool:
        """Se arrumando pra noite/encontro/jogo agora (ou saída assim nas próximas 3 h)."""
        try:
            from agenda import Agenda
            for e in Agenda(self.db).etapas(when.date(), when):
                if e.tipo == "arrumando" and e.prep_tipo in ("noite", "encontro", "jogo", "freela") and \
                        e.inicio - timedelta(hours=3) <= when < e.fim:
                    return True
        except Exception:
            logger.exception("cabelo.vai_sair")
        return False

    def _suou(self, st: dict, when: datetime) -> bool:
        """Academia ou praia desde a última lavagem."""
        desde = st.get("lavado_em") or (when - timedelta(days=1)).isoformat()
        with self.db.get_connection() as conn:
            row = conn.execute(
                """SELECT 1 FROM world_state WHERE observed_at>? AND observed_at<=?
                   AND (lower(activity) LIKE '%academia%' OR lower(activity) LIKE '%praia%'
                        OR lower(activity) LIKE '%tomando sol%') LIMIT 1""", (desde, when.isoformat())).fetchone()
        return bool(row)

    # ------------------------------------------------------- penteado de sair --
    def se_arrumando(self, prep: dict, now: datetime) -> Optional[str]:
        """O "Se arrumando" começou (world_state): escolhe o penteado da saída — às vezes pergunta pra ele."""
        tipo, chave = prep.get("prep_tipo") or "", prep.get("chave") or ""
        if not chave or tipo in SEM_PENTEADO:
            return None
        st = self._state(now)
        sa = st.get("saida")
        if sa and sa.get("chave") == chave:
            return sa.get("estilo")
        ini, fim = datetime.fromisoformat(prep["start_at"]), datetime.fromisoformat(prep["end_at"])
        rng = random.Random(f"cabelo:saida:{chave}")
        lav = self._dia_lavagem(st, now)
        opcoes = list(PENTEADO_SAIDA.get(tipo, PENTEADO_DIA))
        if lav >= 2:                                          # oleoso: solto não rola
            opcoes = [o for o in opcoes if o not in ("natural", "babyliss", "escova", "meio_preso")] or ["coque"]
        if st.get("secagem") == "escova_salao" and lav <= 2 and "escova" not in opcoes:
            opcoes.insert(0, "escova")
        rng.shuffle(opcoes)
        sa = {"chave": chave, "tipo": tipo, "desde": (ini + (fim - ini) * 0.55).isoformat(),
              "ate": (fim + timedelta(hours=6)).isoformat(), "pronto": (ini + (fim - ini) * 0.75).isoformat(),
              "estilo": None, "quem": None, "foto": None}
        if tipo in ("noite", "encontro") and len(opcoes) > 1 and fim - ini >= timedelta(minutes=30) \
                and rng.random() < PENTEADO_PERGUNTA_CHANCE:
            sa["opcoes"] = opcoes[:2]
            sa["pergunta"] = {"status": "pendente", "criada": now.isoformat(), "tipo": "penteado"}
        else:
            sa["estilo"], sa["quem"] = opcoes[0], "ela"
        st["saida"] = sa
        self._save(st)
        logger.info("cabelo.saida tipo=%s pergunta=%s", tipo, bool(sa.get("opcoes")))
        return sa["estilo"]

    # -------------------------------------------------------------- umectação --
    def quer_umectar(self, now: datetime, inicio: datetime, rng: random.Random) -> bool:
        """Bloco de tempo livre: umectação (óleo no cabelo, touca, 1 h)? Entediada e cabelo ressecado."""
        if not (10 <= inicio.hour < 21) or self.sessao(now):
            return False
        c = self.condicao(now)
        if not c or c["hidratacao_dias"] < 12:
            return False
        entediada = False
        try:
            from emotion import EmotionEngine
            entediada = any(e.family == "tedio" for e in EmotionEngine(self.db).feeling(now).episodes)
        except Exception:
            pass
        return rng.random() < (0.35 if entediada else 0.04)

    def umectou(self, inicio: datetime, fim: datetime, now: datetime) -> None:
        st = self._state(now)
        st.update({"umectando_ate": fim.isoformat(), "lavar": True, "hidratado_em": fim.isoformat(),
                   "hidratado_onde": "casa"})
        self._save(st)
        logger.info("cabelo.umectacao ate=%s", fim.isoformat(timespec="minutes"))

    # ----------------------------------------------------------------- salão --
    def _saldo(self, now: datetime) -> int:
        try:
            import financas
            return int(financas._init(financas._load(self.db), now)["saldo"])
        except Exception:
            return 0

    def _evento_perto(self, now: datetime) -> Optional[tuple[str, datetime]]:
        """Job, encontro ou festa nas próximas 30 h (a escova dura até a próxima lavagem)."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """SELECT event_type, description, event_at FROM eventos_pendentes WHERE confirmed=1
                   AND status!='cancelled' AND event_at>? AND event_at<? ORDER BY event_at""",
                (now.isoformat(), (now + timedelta(hours=30)).isoformat())).fetchall()
        for r in rows:
            tipo = ("trabalho" if r["event_type"] == "trabalho" else "encontro" if r["event_type"] == "encontro"
                    else "festa" if _EVENTO_RE.search(r["description"] or "") else None)
            if tipo:
                return tipo, datetime.fromisoformat(r["event_at"])
        return None

    def _mudanca_dela(self, st: dict, now: datetime, rng: random.Random) -> Optional[str]:
        """Vontade de mudar (rara): uma mudança que ela ainda não tem."""
        corte, tom, rosa = self._corte_atual(st, now), st.get("tom", "dourado"), self._rosa(st, now)
        pesos = {"repicado": 1.0, "cortina": 1.0, "franja": 0.6, "reto": 0.5, "bege": 0.8, "dourado": 0.6,
                 "rosa": 0.5, "loira": 0.2}
        pesos = {m: p for m, p in pesos.items() if m not in (corte, tom) and not (m == "rosa" and rosa)}
        return rng.choices(list(pesos), weights=list(pesos.values()))[0] if pesos else None

    def _servicos(self, st: dict, c: dict, mudanca: Optional[str], evento: bool) -> list[str]:
        sv = []
        if mudanca == "loira":
            sv.append("loira")
        elif mudanca in ("bege", "dourado") or c["luzes_dias"] >= c["luzes_prazo"]:
            sv.append("retoque" if c["tom"] == "loira" and mudanca is None else "tonalizar")
        if mudanca == "rosa":
            sv.append("rosa")
        if c["hidratacao_dias"] >= 18:
            sv.append("hidratacao")
        if mudanca in CORTE_MUDANCAS or c["corte_dias"] >= 70:
            sv.append("corte")
        if sv or evento:
            sv.append("escova")
        return sorted(set(sv), key=ORDEM.index)

    def talvez_salao(self, now: datetime) -> Optional[int]:
        """Chamado pelo mundo quando ela está livre em casa: marca o salão (rotina, evento, sugestão ou mimo)."""
        if not self._limpo() or now.weekday() == 6 or not (9 <= now.hour < 17):
            return None
        st = self._state(now)
        if self.sessao(now) or st.get("salao_dia") == now.date().isoformat():
            return None
        try:
            from unhas import Unhas
            if Unhas(self.db).sessao(now):
                return None
        except Exception:
            pass
        c = self.condicao(now)
        if not c:
            return None
        slot = (now.hour * 60 + now.minute) // 20
        rng = random.Random(f"cabelo:salao:{now.date().isoformat()}:{slot}")
        evento = self._evento_perto(now)
        sug = st.get("sugestao")
        vencido = c["corte_dias"] >= 70 or c["luzes_dias"] >= c["luzes_prazo"]
        mudanca, quem = None, None
        if sug and (now - datetime.fromisoformat(sug["em"])) < timedelta(days=21):
            motivo, chance, mudanca, quem = "sugestao", 0.03, sug["mudanca"], "patrick"
        elif evento and c["lavagem_dia"] >= 1 and st.get("secagem") != "escova_salao":
            motivo, chance = evento[0], 0.3
        elif vencido:
            motivo, chance = "rotina", 0.12
        elif c["hidratacao_dias"] >= 24:
            motivo, chance = "hidratacao", 0.06
        elif self._saldo(now) >= 800 and c["hidratacao_dias"] >= 10:
            motivo, chance = "mimo", 0.015
        else:
            return None
        if rng.random() >= chance:
            return None
        if mudanca is None and motivo == "rotina" and rng.random() < MUDAR_CHANCE:
            mudanca = self._mudanca_dela(st, now, rng)
        sv = self._servicos(st, c, mudanca, bool(evento) or motivo == "mimo")
        if motivo in ("hidratacao", "mimo") and "hidratacao" not in sv:
            sv = sorted(set(sv) | {"hidratacao", "escova"}, key=ORDEM.index)
        saldo = self._saldo(now)
        for corta in ("hidratacao", "escova"):                # sem dinheiro pro combo: tira o supérfluo
            if sum(SERVICOS[s][1] for s in sv) + RESERVA > saldo and corta in sv and len(sv) > 1 \
                    and not (corta == "escova" and motivo in ("trabalho", "encontro", "festa")):
                sv.remove(corta)
        preco = sum(SERVICOS[s][1] for s in sv)
        if not sv or preco + RESERVA > saldo:
            return None
        minutos = sum(SERVICOS[s][2] for s in sv) + 5
        from vontade import Vontade
        v = Vontade(self.db)
        livre = v._livre_ate(now)
        inicio = now + timedelta(minutes=rng.randint(8, 12) + SALAO_IDA_MIN)
        fim = inicio + timedelta(minutes=minutos)
        if not livre or fim + timedelta(minutes=SALAO_IDA_MIN + 20) > livre or fim > now.replace(hour=20, minute=0):
            return None
        chave = f"cabelo:{now.date().isoformat()}:{now:%H%M}"
        passos = [[self._passo(s, mudanca), SERVICOS[s][2]] for s in sv] + [["Pagando", 5]]
        why = self._motivo(motivo, evento[1] if evento else None, now)
        cid = v.agendar("cabelo", SALAO, inicio, fim, f"Arrumando o cabelo na {SALAO_NOME}",
                        origem="planejado" if motivo == "rotina" else "vontade", decidido_em=now, chave=chave,
                        ida_min=SALAO_IDA_MIN, extra={"motivo": why, "preco": preco, "passos": passos})
        if not cid:
            return None
        s = {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "chave": chave, "servicos": sv, "motivo": motivo,
             "preco": preco, "mudanca": mudanca, "quem": quem, "finalizada": False}
        if quem is None and ("corte" in sv or mudanca) and rng.random() < SALAO_PERGUNTA_CHANCE:
            s["opcoes"] = self._opcoes(st, now, mudanca)
            s["pergunta"] = {"status": "pendente", "criada": now.isoformat(), "tipo": "salao"}
        elif mudanca and quem is None:
            s["quem"] = "ela"
        if sug and quem == "patrick":
            st["sugestao"] = None
        st["salao_dia"] = now.date().isoformat()
        st["sessao"] = s
        self._save(st)
        v._registra(chave, now, f"Marcou o cabelo na Ophicina: {why}.")
        logger.info("cabelo.salao motivo=%s servicos=%s mudanca=%s", motivo, sv, mudanca)
        return cid

    @staticmethod
    def _motivo(motivo: str, quando: Optional[datetime], now: datetime) -> str:
        if motivo in ("trabalho", "encontro", "festa", "mimo"):
            return motivo_txt(motivo, quando, now)
        return {"rotina": "pontas e luzes vencidas", "hidratacao": "cabelo ressecado",
                "sugestao": "o Patrick sugeriu"}[motivo]

    @staticmethod
    def _passo(servico: str, mudanca: Optional[str]) -> str:
        if servico == "corte":
            return {"repicado": "Repicado", "cortina": "Franja cortina", "franja": "Franja",
                    "reto": "Corte reto"}.get(mudanca or "", "Corte das pontas")
        if servico == "tonalizar" and mudanca == "bege":
            return "Pontas bege"
        return SERVICOS[servico][3]

    def _opcoes(self, st: dict, now: datetime, mudanca: Optional[str]) -> list[str]:
        """As duas coisas que ela pergunta: a mudança que ela quer x ficar como está, ou pontas x repicar."""
        corte = self._corte_atual(st, now)
        if mudanca in CORTE_MUDANCAS or mudanca is None:
            alvo = mudanca or ("repicado" if corte != "repicado" else "cortina")
            return [alvo, "pontas"] if mudanca else ["pontas", alvo]
        return [mudanca, "dourado" if st.get("tom") != "dourado" and mudanca != "dourado" else "pontas"]

    # ----------------------------------------------------------- as perguntas --
    def pergunta_pendente(self, now: datetime) -> Optional[dict]:
        """A pergunta que ainda não saiu (proatividade): penteado antes de sair ou corte/cor no salão."""
        st = self._load()
        for campo in ("saida", "sessao"):
            x = st.get(campo)
            p = (x or {}).get("pergunta")
            if not x or x.get("finalizada") or not p or p.get("status") != "pendente":
                continue
            if now - datetime.fromisoformat(p["criada"]) > PERGUNTA_JANELA or now >= self._prazo(campo, x):
                p["status"] = "nao_saiu"
                self._save(st)
                continue
            a, b = x["opcoes"]
            if campo == "saida":
                return {"campo": campo, "opcoes": x["opcoes"],
                        "detail": f"Você está se arrumando pra sair e em dúvida no cabelo: "
                                  f"{ESTILOS[a][0].lower()} ou {ESTILOS[b][0].lower()}."}
            return {"campo": campo, "opcoes": x["opcoes"],
                    "detail": f"Você vai no salão ({SALAO_NOME}) daqui a pouco arrumar o cabelo e está em dúvida: "
                              f"{_nome_mudanca(a)} ou {_nome_mudanca(b)}."}
        return None

    def marca_pergunta_enviada(self, now: datetime) -> None:
        st = self._load()
        for campo in ("saida", "sessao"):
            p = (st.get(campo) or {}).get("pergunta")
            if p and p.get("status") == "pendente":
                p.update(status="enviada", enviada=now.isoformat())
                self._save(st)
                return

    def _prazo(self, campo: str, x: dict) -> datetime:
        """Até quando a resposta dele conta: o penteado até ela começar a arrumar o cabelo; o salão até
        sentar na cadeira."""
        if campo == "saida":
            return datetime.fromisoformat(x["desde"])
        return datetime.fromisoformat(x["inicio"]) + timedelta(minutes=5)

    def _le_opcao(self, low: str, opcoes: list, tabela: dict) -> tuple[Optional[str], Optional[str]]:
        if _TANTO_FAZ_RE.search(low):
            return opcoes[0], "ela"
        achadas = [(m.start(), k) for k in opcoes if (m := re.search(tabela[k], low))]
        if achadas:
            return min(achadas)[1], "patrick"
        if _SEGUNDA_RE.search(low) and not _PRIMEIRA_RE.search(low):
            return opcoes[1], "patrick"
        if _PRIMEIRA_RE.search(low):
            return opcoes[0], "patrick"
        return None, None

    def observe_patrick(self, text: str, now: datetime) -> Optional[str]:
        """Resposta dele à pergunta (vale se ainda dá tempo) ou sugestão solta ("fica linda de franja")."""
        st = self._load()
        low = (text or "").lower()
        sa = st.get("saida")
        p = (sa or {}).get("pergunta")
        if sa and p and p.get("status") == "enviada" and not sa.get("estilo") \
                and now <= self._prazo("saida", sa) + timedelta(minutes=10):
            tabela = {k: _PENTEADO_RE.get(k, re.escape(ESTILOS[k][0].lower())) for k in sa["opcoes"]}
            estilo, quem = self._le_opcao(low, sa["opcoes"], tabela)
            if estilo:
                sa.update(estilo=estilo, quem=quem)
                p["status"] = "respondida"
                self._save(st)
                logger.info("cabelo.penteado estilo=%s quem=%s", estilo, quem)
                return estilo
        s = st.get("sessao")
        p = (s or {}).get("pergunta")
        if s and p and p.get("status") == "enviada" and not s.get("escolha") and not s.get("finalizada") \
                and now <= self._prazo("sessao", s) + timedelta(minutes=5):
            m, quem = self._le_opcao(low, s["opcoes"], {k: MUDANCAS[k][1] for k in s["opcoes"]})
            if m:
                self._aplica_escolha(s, m, quem)
                p["status"] = "respondida"
                self._save(st)
                logger.info("cabelo.salao escolha=%s quem=%s", m, quem)
                return m
        if _SUGESTAO_CTX.search(low) and _SUGESTAO_VERBO.search(low):
            for m in ("franja", "cortina", "repicado", "rosa", "loira", "bege"):
                if m == "franja" and re.search(MUDANCAS["cortina"][1], low):
                    continue
                if re.search(MUDANCAS[m][1], low) and not re.search(r"\bn[ãa]o\b", low):
                    st["sugestao"] = {"mudanca": m, "em": now.isoformat()}
                    self._save(st)
                    logger.info("cabelo.sugestao mudanca=%s", m)
                    return m
        return None

    def _aplica_escolha(self, s: dict, m: str, quem: str) -> None:
        """A escolha (dele ou dela) vira os serviços de verdade (o preço e os passos do card mudam junto)."""
        s["escolha"], s["quem"] = m, quem
        mud = None if m == "pontas" else m                   # "só as pontas" = fica como está
        s["mudanca"] = mud
        sv = [x for x in s["servicos"] if x not in ("loira", "rosa")]
        if mud == "loira":
            sv = ["loira"] + [x for x in sv if x not in ("tonalizar", "retoque")]
        elif mud == "rosa":
            sv.append("rosa")
        elif mud in ("bege", "dourado") and "tonalizar" not in sv:
            sv.append("tonalizar")
        if mud in CORTE_MUDANCAS and "corte" not in sv:
            sv.append("corte")
        s["servicos"] = sorted(set(sv) | {"escova"}, key=ORDEM.index)
        s["preco"] = sum(SERVICOS[x][1] for x in s["servicos"])
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT metadata_json FROM eventos_pendentes WHERE source_key=?",
                               (s["chave"],)).fetchone()
            if row:
                meta = json.loads(row["metadata_json"] or "{}")
                meta["preco"] = s["preco"]
                meta["passos"] = [[self._passo(x, mud), SERVICOS[x][2]] for x in s["servicos"]] + [["Pagando", 5]]
                conn.execute("UPDATE eventos_pendentes SET metadata_json=? WHERE source_key=?",
                             (json.dumps(meta, ensure_ascii=False), s["chave"]))
                conn.commit()

    # --------------------------------------------------------- acontecimento --
    def materialize(self, now: datetime) -> int:
        """Fecha a ida ao salão que terminou (acontecimento, saldo, cabelo novo, foto) e o penteado pronto."""
        st = self._load()
        feitos = self._penteado_pronto(st, now)
        s = st.get("sessao")
        if not s or s.get("finalizada"):
            if feitos:
                self._save(st)
            return feitos
        if self._cancelado(s["chave"]):
            st["sessao"] = None
            self._save(st)
            return feitos
        if not s.get("escolha") and now >= self._prazo("sessao", s):
            p = s.get("pergunta") or {}
            if s.get("opcoes"):
                self._aplica_escolha(s, s["opcoes"][0], "ela")
                if p.get("status") in ("pendente", "enviada"):
                    p["status"] = "sem_resposta"
        fim = datetime.fromisoformat(self._fim_real(s))
        if not s.get("foto_decidida") and now >= fim - timedelta(minutes=8):
            s["foto_decidida"] = True
            rng = random.Random(f"cabelo:foto:{s['chave']}")
            if s.get("quem") == "patrick" or s.get("mudanca") or rng.random() < FOTO_SOZINHA_CHANCE:
                self._promete_foto(self._descricao(s), max(now + timedelta(minutes=1), fim - timedelta(minutes=4)),
                                   now, pediu=s.get("quem") == "patrick", pose="salao_cabelo")
        if now < fim:
            self._save(st)
            return feitos
        self._aplica_salao(st, s, fim)
        s["finalizada"] = True
        summary = f"Cabelo na Ophicina: {self._feito(s)} · R$ {s['preco']}."
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'consumo',?,?,'simulated',1,?,?,0.6,?)""",
                (f"compra:{s['chave']}", fim.isoformat(), f"{SALAO_NOME} · cabelo", summary,
                 0.5 if s.get("mudanca") else 0.3, json.dumps(["marina"]), now.isoformat()))
            conn.commit()
        self._save(st)
        logger.info("cabelo.salao_feito servicos=%s mudanca=%s", s["servicos"], s.get("mudanca"))
        return feitos + 1

    def _aplica_salao(self, st: dict, s: dict, fim: datetime) -> None:
        sv, mud, quando = s["servicos"], s.get("mudanca"), fim.isoformat()
        if "corte" in sv:
            st["cortado_em"] = quando
            if mud in ("repicado", "cortina", "franja", "reto"):
                st["corte"] = mud
            else:
                st["corte"] = self._corte_atual(st, fim)
        if "loira" in sv:
            st.update(tom="loira", tonalizado_em=quando, rosa_em=None)
        elif "tonalizar" in sv or "retoque" in sv:
            st["tonalizado_em"] = quando
            if mud in ("bege", "dourado"):
                st["tom"] = mud
            st["rosa_em"] = None
        if "rosa" in sv:
            st["rosa_em"] = quando
        if "hidratacao" in sv:
            st.update(hidratado_em=quando, hidratado_onde="salao")
        st.update(lavado_em=quando, secagem="escova_salao" if "escova" in sv else "secador", molhado_ate=None,
                  lavar=False, umectando_ate=None)

    def _feito(self, s: dict) -> str:
        """"repicado (o Patrick escolheu), tonalização e escova" — a mudança primeiro, depois o resto."""
        m = s.get("mudanca")
        itens = [SERVICOS[x][0] for x in s["servicos"]
                 if not (m and ((x == "corte" and m in CORTE_MUDANCAS) or x == m or (x == "tonalizar" and m in ("bege", "dourado"))))]
        if m:
            nome = {"repicado": "repicado", "cortina": "franja cortina", "franja": "franja", "reto": "corte reto",
                    "bege": "pontas bege", "dourado": "pontas douradas", "rosa": "pontas rosa",
                    "loira": "luzes no cabelo todo"}[m]
            itens = [nome + (" (o Patrick escolheu)" if s.get("quem") == "patrick" else "")] + itens
        return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]

    def _descricao(self, s: dict) -> str:
        m = s.get("mudanca")
        return {"repicado": "cabelo repicado", "cortina": "franja cortina", "franja": "franja nova",
                "reto": "corte reto", "bege": "pontas bege", "dourado": "pontas douradas", "rosa": "pontas rosa",
                "loira": "loira iluminada"}.get(m or "", "cabelo feito, com escova" if "escova" in s["servicos"]
                                                 else "cabelo feito")

    def _penteado_pronto(self, st: dict, now: datetime) -> int:
        """Penteado de sair: sem resposta dele até a hora, ela decide; pronto → às vezes a foto."""
        sa = st.get("saida")
        if not sa:
            return 0
        if not sa.get("estilo") and now >= self._prazo("saida", sa):
            sa["estilo"], sa["quem"] = sa["opcoes"][0], "ela"
            p = sa.get("pergunta") or {}
            if p.get("status") in ("pendente", "enviada"):
                p["status"] = "sem_resposta"
        if sa.get("estilo") and sa.get("foto") is None and now >= datetime.fromisoformat(sa["pronto"]):
            rng = random.Random(f"cabelo:foto_saida:{sa['chave']}")
            sa["foto"] = sa.get("quem") == "patrick" or (sa.get("tipo") in ("noite", "encontro")
                                                         and rng.random() < FOTO_SOZINHA_CHANCE)
            if sa["foto"]:
                self._promete_foto(ESTILOS[sa["estilo"]][0].lower(), now + timedelta(minutes=rng.randint(1, 4)), now,
                                   pediu=sa.get("quem") == "patrick",
                                   pose="cabelo_espelho" if rng.random() < 0.6 else "cabelo_tripe")
            return 1
        return 0

    def _promete_foto(self, subject: str, due: datetime, now: datetime, *, pediu: bool, pose: str) -> None:
        try:
            import promessa_foto
            if not promessa_foto.pending(self.db):
                promessa_foto.promise_cabelo(self.db, subject, due, now, pediu=pediu, pose=pose)
        except Exception:
            logger.exception("cabelo.foto")

    def _cancelado(self, chave: str) -> bool:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT status FROM eventos_pendentes WHERE source_key=?", (chave,)).fetchone()
        return bool(row and row["status"] == "cancelled")

    def _fim_real(self, s: dict) -> str:
        """Saiu mais cedo do salão (agenda reativa)? Vale o fim novo."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT end_at FROM eventos_pendentes WHERE source_key=?", (s["chave"],)).fetchone()
        return row["end_at"] if row and row["end_at"] else s["fim"]

    # --------------------------------------------------------- foto e prompt --
    def visual(self, now: datetime) -> tuple[str, str]:
        """(cabelo com cor e corte, penteado) pro prompt da foto — substituem os traços fixos do visual_profile."""
        st = self._state(now)
        if not st.get("corte"):
            return "", ""
        c = self.condicao(now)
        tom = TONS[c["tom"]]
        cor = tom[2] if c["luzes"] in ("Amarelada", "Raiz aparecendo") else tom[1]
        if c["rosa"]:
            rosa = "pastel pink dyed tips" if c["rosa"] == "viva" else "faded, washed-out pink tips"
            cor = (f"{cor} and {rosa}" if c["tom"] == "loira"
                   else re.sub(r"with .*tips$", f"with {rosa}", cor))
        return f"{cor}{CORTES[c['corte']][1]}", ESTILOS[self.penteado(now)][1]

    def painel(self, now: datetime) -> Optional[dict]:
        """Seção "Cabelo" do Por dentro (mockup aprovado em 26/09): o penteado com a bolinha do tom, quatro
        barras (Lavagem, Pontas, Luzes, Hidratação) e as linhas Lavou, Corte e Luzes."""
        c = self.condicao(now)
        if not c:
            return None
        st = self._state(now)
        tom = TONS[c["tom"]]
        luzes = c["luzes"]
        if c["rosa"]:
            luzes = "Rosa" if c["rosa"] == "viva" else "Rosa desbotando"
        barras = [
            {"label": "Lavagem", "valor": round(min(1.0, (c["lavagem_dia"] + 0.5) / 3), 2), "palavra": c["lavagem"],
             "alerta": c["lavagem_dia"] >= 2},
            {"label": "Pontas", "valor": round(min(1.0, c["corte_dias"] / 90), 2), "palavra": c["pontas"],
             "alerta": c["corte_dias"] >= 70},
            {"label": "Luzes", "valor": round(min(1.0, c["luzes_dias"] / c["luzes_prazo"]), 2), "palavra": luzes,
             "alerta": c["luzes_dias"] >= c["luzes_prazo"] * 0.75},
            {"label": "Hidratação", "valor": round(min(1.0, c["hidratacao_dias"] / 21), 2),
             "palavra": c["hidratacao"], "alerta": c["hidratacao_dias"] >= 18},
        ]

        def quando(campo: str) -> str:
            d = int(self._dias(st, campo, now))
            return ("Hoje" if d == 0 else "Ontem" if d == 1 else f"Há {d} dias" if d < 14
                    else f"Há {d // 7} semanas")

        s = self.sessao(now)
        if s and datetime.fromisoformat(s["inicio"]) <= now:
            penteado = "No salão"
        else:
            penteado = ESTILOS[self.penteado(now)][0]
        lav = self._dia_lavagem(st, now)
        seca = {"natural": "secou natural", "secador": "secou no secador",
                "escova_salao": "escova no salão"}.get(st.get("secagem") or "", "")
        lavado = datetime.fromisoformat(st["lavado_em"]) if st.get("lavado_em") else None
        noite = lavado is not None and (lavado.hour >= 18 or lavado.hour < VIRA_O_DIA)
        lavou = ("Hoje" if lav <= 0 else ("Ontem à noite" if noite else "Ontem") if lav == 1
                 else f"Há {lav} dias") + (f", {seca}" if seca else "")
        # 28/09 (Patrick): a barra já se chama Luzes; a linha diz a cor e quando fez
        return {"penteado": penteado, "hex": ROSA_HEX if c["rosa"] == "viva" else tom[3], "barras": barras,
                "linhas": [["droplet", "Lavou", lavou],
                           ["scissors", "Corte", f"{CORTES[c['corte']][0]}, {quando('cortado_em').lower()}"],
                           ["palette", "Cor", f"{tom[0]}, {quando('tonalizado_em').lower()}"]]
                + ([["brush", "Rosa", self._linha_rosa(st, now, quando)]] if c["rosa"] else [])}

    def _linha_rosa(self, st: dict, now: datetime, quando) -> str:
        """Rosa em linha própria (Patrick, 26/09): quando pintou e quanto falta pra sair."""
        d = self._dias(st, "rosa_em", now)
        if d >= ROSA_NOVO:
            return f"{quando('rosa_em')}, desbotando"
        semanas = max(1, round((ROSA_SOME - d) / 7))
        return f"{quando('rosa_em')}, desbota em ~{semanas} semana{'s' if semanas > 1 else ''}"

    def prompt_lines(self, now: datetime) -> list[str]:
        c = self.condicao(now)
        if not c:
            return []
        st = self._state(now)
        tom = TONS[c["tom"]][0].lower() + (" com as pontas rosa" if c["rosa"] == "viva"
                                           else " com o rosa desbotando" if c["rosa"] else "")
        lines = ["[SEU CABELO — de verdade; aparece nas suas fotos, não invente outro]",
                 f"- Agora: {ESTILOS[self.penteado(now)][0].lower()}. Lavagem: {c['lavagem'].lower()}"
                 + (" (oleoso, por isso preso)" if c["lavagem_dia"] >= 2 else "") + ".",
                 f"- Corte {CORTES[c['corte']][0].lower()} ({c['pontas'].lower()}); luzes {tom} "
                 f"({c['luzes'].lower()}); hidratação: {c['hidratacao'].lower()}."]
        sa = st.get("saida")
        if sa and datetime.fromisoformat(sa["ate"]) > now:
            p = sa.get("pergunta") or {}
            if sa.get("opcoes") and p.get("status") == "enviada" and not sa.get("estilo"):
                a, b = (ESTILOS[x][0].lower() for x in sa["opcoes"])
                lines.append(f"- Você perguntou pro Patrick como fazer o cabelo pra sair ({a} ou {b}). Se ele "
                             "escolher agora, é assim que você faz.")
            elif sa.get("estilo") and sa.get("quem") == "patrick":
                lines.append(f"- Ele escolheu {ESTILOS[sa['estilo']][0].lower()} pro cabelo e é assim que você vai.")
            elif p.get("status") == "sem_resposta" and sa.get("estilo"):
                lines.append(f"- Você perguntou o penteado pro Patrick, ele não respondeu a tempo e você foi de "
                             f"{ESTILOS[sa['estilo']][0].lower()}.")
        s = self.sessao(now)
        if s:
            ini = datetime.fromisoformat(s["inicio"])
            p = s.get("pergunta") or {}
            o_que = ", ".join(SERVICOS[x][0] for x in s["servicos"])
            if s.get("opcoes") and p.get("status") == "enviada" and not s.get("escolha"):
                a, b = (_nome_mudanca(x) for x in s["opcoes"])
                lines.append(f"- Você perguntou pro Patrick o que fazer no cabelo ({a} ou {b}). Se ele escolher "
                             "agora, é o que você faz.")
            elif s.get("quem") == "patrick" and s.get("mudanca"):
                lines.append(f"- Ele escolheu: {_nome_mudanca(s['mudanca'])}. É o que você vai fazer.")
            if now < ini:
                lines.append(f"- Marcou o cabelo na {SALAO_NOME} às {ini:%H:%M}: {o_que} (R$ {s['preco']}, você paga).")
            else:
                lines.append(f"- Você está no salão ({SALAO_NOME}) arrumando o cabelo: {o_que}.")
        sug = st.get("sugestao")
        if sug:
            lines.append(f"- O Patrick sugeriu {_nome_mudanca(sug['mudanca'])} no seu cabelo; você pode fazer na "
                         "próxima ida ao salão (ou não, se não curtir).")
        return lines


# resposta dele sobre o penteado ("solto", "preso", "rabo"…)
_PENTEADO_RE = {
    "natural": r"\bsolto\b|natural|ondulad",
    "babyliss": r"babyliss|cachead|cachinh|ondas|solto",
    "escova": r"escova|lis[oa]\b",
    "rabo_alto": r"rabo|rabinho|preso",
    "rabo_baixo": r"rabo|rabinho|preso",
    "coque": r"coque|preso",
    "meio_preso": r"meio preso|semi ?preso",
    "tranca": r"tran[çc]a",
    "piranha": r"piranha|presilha|preso",
}
