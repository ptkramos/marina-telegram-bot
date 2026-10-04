"""Roupa e make de verdade (Patrick, 28/09 — frente do mundo; aba Por fora opção C).

Antes a roupa nascia na hora da foto (sorteio do guarda-roupa do photo_director) e a make era só passo do card.
Agora as duas são estado: o que ela está vestindo agora, desde quando e pra quê, e a make que ela fez (e que borra).
A foto, o prompt do chat, o Instagram e o bloco "Agora" da aba Por fora leem daqui.

Decisões do Patrick (28/09):
- **Guarda-roupa de peças fixas que repetem** (como gente de verdade): o look é montado com peças que ela tem, pela
  ocasião, sem repetir o mesmo look em 3 dias.
- **Troca pela vida dela:** acorda de pijama e tira depois do banho ou do café; chegou da rua, troca pra roupa de casa
  em 10–40 min (de rolê à noite, às vezes fica com a roupa até o Se arrumando pra dormir); pijama no fim do dia.
- **Make em níveis que borram:** sem / leve / completa / de festa (e a de ensaio, feita no freela). Feita no "Fazendo
  maquiagem", tirada no "Tirando maquiagem" ou no banho; academia, praia e choro borram; dormiu sem tirar, acorda
  borrada (vira acontecimento).
- **Ela namora e provoca:** gaveta íntima com lingerie, roupa provocante de casa, fetiche (meia e cinta-liga, couro e
  vinil, fantasias adultas) e transparências. Ela veste com tesão em casa pra provocar, no sexting quando ele pede
  (a mesma peça em todas as fotos da sessão), às vezes por baixo da roupa de sair (e conta no meio do rolê), e às
  vezes dorme com ela depois.
- **Na aba Por fora** mostra normal (a peça é o destaque); o "Por baixo" só aparece depois que ela contou.

Estado em estado_relacional[KEY] (JSON), sem migration:
  atual    → {look: [peças], ocasiao, desde, pra, chave}
  make     → {nivel, feita_em, extra, motivos, dormiu}
  por_baixo → {peca, chave, desde, contou}
  hist     → looks anteriores [{look, ocasiao, desde, ate, pra}] (5 dias; o Instagram posta o rolê de ontem)
  em_casa, chegou_em, troca_em, pos_banho, feitos (passos do card já aplicados), clima (sessão de sexting vista),
  dorme (dia em que dorme de lingerie), escolha (o look que ele escolheu nas duas opções), usado (peça → quando).
"""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

KEY = "roupa_json"
HOME = "marina_apartment"
HIST_DIAS = 5
LOOK_SEM_REPETIR = timedelta(days=3)
INTIMO_SEM_REPETIR = timedelta(days=7)

# peça → (nome no painel e no prompt, como vai no prompt da foto). Regra do Patrick: tecido macio, sem bojo.
PECAS = {
    # casa
    "camisetao_branco": ("camisetão branco", "an oversized white cotton t-shirt"),
    "short_moletom": ("short de moletom cinza", "grey cotton shorts"),
    "regata_azul": ("regata canelada azul", "a light blue ribbed cotton tank top"),
    "short_jeans": ("short jeans", "denim shorts"),
    "camisa_linho_bege": ("camisa de linho bege", "a loose beige linen shirt"),
    "short_branco": ("short branco", "white cotton shorts"),
    "moletom_cinza": ("moletom cinza largo", "an oversized grey hoodie"),
    "camiseta_banda": ("camiseta velha de banda", "a faded oversized band t-shirt"),
    "legging_preta": ("legging preta", "black leggings"),
    # pijama
    "pijama_listrado": ("pijama de short listrado", "a white cotton tank top and striped pajama shorts"),
    "pijama_cetim": ("pijama de cetim rosa", "a light pink satin camisole and matching shorts"),
    "short_pijama": ("short de pijama", "soft pajama shorts"),
    "camisola_algodao": ("camisola de algodão", "a soft grey cotton nightshirt"),
    # treino
    "top_preto": ("top preto", "a soft unpadded black sports top"),
    "top_vinho": ("top vinho", "a soft unpadded maroon sports top"),
    "short_treino": ("short de treino preto", "black high-waisted booty shorts"),
    "legging_cinza": ("legging cinza mescla", "heather grey leggings"),
    "regata_dryfit": ("regata dry-fit branca", "a loose white athletic tank top"),
    # rua
    "jeans_claro": ("jeans claro", "light blue jeans"),
    "camiseta_branca": ("camiseta branca", "a white cotton tee"),
    "vestido_linho": ("vestido de linho de alcinha", "a light linen sundress with thin straps"),
    "regata_preta": ("regata canelada preta", "a soft black ribbed tank top"),
    "saia_midi_bege": ("saia midi bege", "a flowy beige midi skirt"),
    "camisa_listrada": ("camisa listrada azul e branca", "a blue and white striped button-up shirt"),
    "calca_linho": ("calça de linho bege", "beige linen trousers"),
    "cropped_amarelo": ("cropped amarelo de tricô", "a butter yellow ribbed knit crop top"),
    "saia_jeans": ("saia jeans", "a denim mini skirt"),
    "baby_tee_lilas": ("baby tee lilás", "a fitted lilac baby tee"),
    "vestido_xadrez": ("vestido xadrez vermelho", "a red gingham summer dress"),
    # sair
    "vestido_preto": ("vestido preto de alcinha", "a black satin slip midi dress with thin straps"),
    "top_ombro_branco": ("blusa ombro a ombro branca", "a white off-shoulder linen top"),
    "cropped_azul": ("cropped azul canelado", "a light blue ribbed crop top"),
    "saia_midi_branca": ("saia midi branca", "a flowy white midi skirt"),
    "vestidinho_preto": ("vestidinho preto", "a little black cotton dress"),
    "vestido_floral": ("vestido envelope floral", "a floral wrap dress in soft terracotta tones"),
    "corset_rosa": ("corset rosê", "a dusty rose corset top"),
    "jeans_escuro": ("jeans escuro flare", "dark flared jeans"),
    "vestido_verde": ("vestido de cetim verde", "an emerald green satin slip dress"),
    "vestido_vermelho": ("vestido vermelho de um ombro só", "a cherry red one-shoulder mini dress"),
    # jogo e praia
    "camisa_botafogo": ("camisa do Botafogo", "a black and white striped Botafogo football jersey"),
    "biquini_azul": ("biquíni azul-claro", "a small soft triangle bikini in light blue"),
    "biquini_terracota": ("biquíni terracota", "a terracotta triangle bikini"),
    "biquini_preto": ("biquíni preto", "a black string bikini"),
    "biquini_lilas": ("biquíni lilás", "a lilac scrunch bikini"),
    # 03/10 (soak, /feedback de 02/10 19:06): saiu do banho do Se arrumando e ainda não se vestiu
    "toalha": ("enrolada na toalha", "a white bath towel wrapped around her body"),
}

# look = peças combinadas (a primeira é a de cima)
LOOKS = {
    "casa_dia": (("camisetao_branco", "short_moletom"), ("regata_azul", "short_jeans"),
                 ("camisa_linho_bege", "short_branco"), ("camiseta_banda", "short_moletom"),
                 ("regata_azul", "short_branco"), ("camisetao_branco", "legging_preta")),
    "casa_noite": (("moletom_cinza", "short_moletom"), ("camiseta_banda", "legging_preta"),
                   ("camisetao_branco", "short_moletom")),
    "pijama": (("pijama_listrado",), ("pijama_cetim",), ("moletom_cinza", "short_pijama"), ("camisola_algodao",)),
    "treino": (("top_preto", "legging_preta"), ("top_vinho", "short_treino"), ("regata_dryfit", "legging_cinza"),
               ("top_preto", "short_treino"), ("top_vinho", "legging_preta")),
    "rua": (("camiseta_branca", "jeans_claro"), ("vestido_linho",), ("regata_preta", "saia_midi_bege"),
            ("camisa_listrada", "calca_linho"), ("cropped_amarelo", "jeans_claro"), ("baby_tee_lilas", "saia_jeans"),
            ("vestido_xadrez",), ("camiseta_branca", "saia_jeans"), ("regata_preta", "jeans_claro")),
    "sair": (("vestido_preto",), ("top_ombro_branco", "jeans_claro"), ("cropped_azul", "saia_midi_branca"),
             ("vestidinho_preto",), ("regata_preta", "saia_jeans"), ("vestido_floral",), ("corset_rosa", "jeans_escuro"),
             ("vestido_verde",), ("vestido_vermelho",)),
    "jogo": (("camisa_botafogo", "short_jeans"), ("camisa_botafogo", "jeans_claro"), ("camisa_botafogo", "saia_jeans")),
    "praia": (("biquini_azul",), ("biquini_terracota",), ("biquini_preto",), ("biquini_lilas",)),
}

# gaveta íntima: peça → (nome, prompt, nível da foto, tipo)
INTIMO = {
    # provocante de casa (nível 1)
    "so_camisetao": ("camisetão e calcinha branca",
                     "only an oversized white t-shirt slipping off one shoulder and white cotton panties", 1, "provoca"),
    "regatinha_calcinha": ("regatinha e calcinha de algodão", "a tiny white cotton tank top and matching cotton panties",
                           1, "provoca"),
    "shortinho_cetim": ("camisola e shortinho de cetim", "a light pink satin camisole and tiny matching shorts", 1,
                        "provoca"),
    "moletom_calcinha": ("moletom e calcinha preta", "an oversized light blue hoodie and black cotton panties", 1,
                         "provoca"),
    # lingerie
    "renda_branca": ("conjunto de renda branca", "a soft unpadded white lace bralette and matching panties", 2, "lingerie"),
    "renda_rosa": ("conjunto de renda rosa", "a light pink unpadded lace bralette and thong", 2, "lingerie"),
    "renda_preta": ("conjunto de renda preta", "a black sheer unpadded lace bralette and matching thong", 2, "lingerie"),
    "renda_vinho": ("conjunto de renda vinho", "a burgundy unpadded lace bralette and matching thong", 2, "lingerie"),
    "body_renda_preto": ("body de renda preto", "a black lace bodysuit", 2, "lingerie"),
    # fetiche (meia e cinta-liga, couro e vinil, fantasias adultas)
    "cinta_liga": ("cinta-liga e meia 7/8 pretas", "a black lace bralette and thong with a black garter belt and sheer "
                   "black thigh-high stockings", 2, "fetiche"),
    "arrastao": ("meia arrastão com renda preta", "a black lace bralette and thong with black fishnet thigh-high "
                 "stockings", 2, "fetiche"),
    "body_vinil": ("body de vinil preto", "a glossy black vinyl bodysuit", 2, "fetiche"),
    "harness": ("harness de couro por cima da renda", "a black leather strappy harness over a black lace bralette and "
                "thong", 2, "fetiche"),
    "coelhinha": ("fantasia de coelhinha", "a black satin bunny costume bodysuit with a bunny ears headband, a white "
                  "collar and cuffs, and sheer black tights", 2, "fetiche"),
    "empregada": ("fantasia de empregada francesa", "a short black and white French maid costume dress with a white "
                  "lace apron and a lace headband", 2, "fetiche"),
    "policial": ("fantasia de policial", "a fitted dark blue police costume mini dress with a police hat", 2, "fetiche"),
    # transparências
    "babydoll_tule": ("baby-doll de tule preto", "a sheer black tulle babydoll nightie over a matching thong", 2,
                      "transparencia"),
    "body_renda_branca": ("body de renda branca transparente", "a sheer white lace bodysuit", 2, "transparencia"),
    "camisola_chiffon": ("camisola transparente rosa", "a sheer light pink chiffon nightie", 2, "transparencia"),
}
# acessório do fetiche (às vezes vai junto)
ACESSORIOS = {"choker": ("choker de couro com argola", "a black leather choker with a small silver ring"),
              "salto": ("salto alto preto", "black stiletto heels")}
POR_BAIXO = ("renda_branca", "renda_rosa", "renda_preta", "renda_vinho", "body_renda_preto", "cinta_liga")
# 28/09 (bug 17, Patrick): no sexting, a foto provocante (nível 1) já é a lingerie com algo por cima; no nível 2 ela
# tira o de cima — a peça íntima é a mesma do começo ao fim da sessão.
COBRE = {"moletom_aberto": ("moletom cinza largo aberto", "an oversized grey zip hoodie left open"),
         "camisetao_por_cima": ("camisetão branco", "an oversized white t-shirt slipping off one shoulder"),
         "robe_cetim": ("robe de cetim rosa", "a short light pink satin robe loosely tied")}

# make → (nome no painel, como vai no prompt da foto, quanto borra por hora)
MAKE = {
    "sem": ("Sem make", "a bare fresh face with natural skin", 0.0),
    "leve": ("Leve", "light everyday makeup: mascara and a touch of lip gloss", 0.05),
    "completa": ("Completa", "full makeup: soft matte skin, thin winged eyeliner and nude lipstick", 0.06),
    "festa": ("De festa", "bold night-out makeup: smoky eyes, defined lashes and red lipstick", 0.07),
    "ensaio": ("De ensaio", "flawless professional photoshoot makeup with glowing skin and soft rosy lips", 0.05),
}
BORRA = {"suor": 0.4, "praia": 0.5, "choro": 0.35, "dormiu": 0.6}

# prep_tipo do Se arrumando → ocasião da roupa
OCASIAO_PREP = {"noite": "sair", "encontro": "sair", "jogo": "jogo", "praia": "praia", "academia": "treino",
                "orla": "treino", "dormir": "pijama"}
# o "pra quê" do painel
PRA = {"noite": "Sair à noite", "encontro": "Encontro", "jogo": "Jogo do Botafogo", "praia": "Praia",
       "academia": "Academia", "orla": "Caminhada na orla", "faculdade": "Faculdade", "freela": "Freela",
       "cafe": "Café", "acai": "Açaí", "farmacia": "Farmácia", "mercado": "Mercado", "mercado_semana": "Mercado",
       "shopping": "Shopping", "medico": "Médico", "pronto_atendimento": "Pronto atendimento", "manicure": "Unhas",
       "cabelo": "Salão", "milo": "Passeio do Milo", "dormir": "Dormir"}
PRA_OCASIAO = {"casa": "Ficar em casa", "pijama": "Dormir", "provocar": "Te provocar", "rua": "Sair",
               "treino": "Treino", "praia": "Praia", "sair": "Sair à noite", "jogo": "Jogo do Botafogo"}
RUA_OK = ("rua", "sair", "jogo", "praia", "treino", "casa")      # dá pra pôr o pé na rua assim (casa: short e camiseta)
LEVE_IMPLICITA = ("faculdade", "cafe", "acai", "medico", "manicure", "cabelo")   # rímel e gloss junto com a roupa
_ROUPA_PASSO = re.compile(r"roupa|biqu[ií]ni|camisa do|pijama|t[eê]nis", re.IGNORECASE)
_TIRA_MAKE = re.compile(r"tirando maquiagem", re.IGNORECASE)
_TROCOU_LOOK = re.compile(r"^Trocou de (?:look|roupa)")     # o que segurou a saída (atraso.py), aviso no card
_EVENTO_RE = re.compile(r"anivers|festa|casamento|formatura|balada", re.IGNORECASE)
_CONTOU_RE = re.compile(r"lingerie|calcinha|renda|por baixo|suti[aã]|conjuntinho|cinta|meia (?:7/8|arrast)|body",
                        re.IGNORECASE)
_PRIMEIRA_RE = re.compile(r"\b(?:a |o )?(?:primeir[ao]|1)\b", re.IGNORECASE)
_SEGUNDA_RE = re.compile(r"\b(?:a |o )?(?:segund[ao]|2)\b", re.IGNORECASE)
CLIMA = ("warming", "active", "climax", "afterglow")
# o look de sair que ela diz que vai usar (a ordem importa: "vestidinho preto" antes de "vestido preto")
_LOOK_DITO = ((r"vestidinho preto", ("vestidinho_preto",)), (r"vestido preto", ("vestido_preto",)),
              (r"vestido (?:de cetim )?verde|cetim verde", ("vestido_verde",)),
              (r"vestido vermelho", ("vestido_vermelho",)), (r"vestido (?:envelope )?floral", ("vestido_floral",)),
              (r"\bcorset", ("corset_rosa", "jeans_escuro")), (r"ombro a ombro", ("top_ombro_branco", "jeans_claro")),
              (r"cropped azul", ("cropped_azul", "saia_midi_branca")))
_LOOK_CONTEXTO = re.compile(r"\blook\b|\broupa\b|\bvestir\b|\busar\b|\bsair\b|\bvou de\b")
PROVOCAR_FIM = timedelta(minutes=60)       # sem clima há 1 h: volta pra roupa de casa
DORME_CHANCE, DORME_CHANCE_GOZOU = 0.3, 0.6
POR_BAIXO_CHANCE, POR_BAIXO_CHANCE_TESAO = 0.15, 0.6
CLIMA_VESTE_CHANCE = 0.35                  # entrou no clima em casa: às vezes vai vestir algo pra ele


def _nome(pid: str) -> str:
    return (PECAS.get(pid) or INTIMO.get(pid) or ACESSORIOS.get(pid) or COBRE.get(pid) or (pid,))[0]


def _en(pid: str) -> str:
    return (PECAS.get(pid) or INTIMO.get(pid) or ACESSORIOS.get(pid) or COBRE.get(pid) or ("", pid))[1]


def nome_look(look: list) -> str:
    """"Camiseta branca e jeans claro" (acessório entra com "com")."""
    if look and look[0] in COBRE:                    # "Conjunto de renda preta com moletom cinza largo aberto por cima"
        txt = nome_look(look[1:]) + f" com {_nome(look[0])} por cima"
        return txt[:1].upper() + txt[1:]
    base = [p for p in look if p not in ACESSORIOS]
    acc = [p for p in look if p in ACESSORIOS]
    txt = " e ".join(_nome(p) for p in base)
    if acc:
        txt += " com " + " e ".join(_nome(p) for p in acc)
    return txt[:1].upper() + txt[1:]


def en_look(look: list) -> str:
    if look and look[0] in COBRE:
        return f"{_en(look[0])} over {en_look(look[1:])}"
    base = [p for p in look if p not in ACESSORIOS]
    acc = [p for p in look if p in ACESSORIOS]
    txt = " and ".join(_en(p) for p in base)
    if acc:
        txt += ", with " + " and ".join(_en(p) for p in acc)
    return txt


def look_do_en(en: str) -> Optional[list]:
    """O look do guarda-roupa com esse texto de prompt (as opções de look que ela mandou pra ele)."""
    for looks in LOOKS.values():
        for look in looks:
            if en_look(list(look)) == en:
                return list(look)
    return None


def _hhmm(at: datetime) -> str:
    return at.strftime("%H:%M")


class Roupa:
    def __init__(self, db):
        self.db = db

    # ---------------------------------------------------------------- estado --
    def _load(self) -> dict:
        try:
            raw = self.db.get_estado_relacional(KEY)
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    def _save(self, st: dict) -> None:
        self.db.set_estado_relacional(KEY, json.dumps(st, ensure_ascii=False))

    def _limpo(self) -> bool:
        try:
            with self.db.get_connection() as conn:
                return bool(conn.execute(
                    "SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done'").fetchone())
        except Exception:
            return False

    def _state(self, now: datetime) -> dict:
        """Na primeira vez: de pijama se está deitada, senão de roupa de casa; sem make."""
        st = self._load()
        if not st.get("atual") and self._limpo():
            grupo = "pijama" if self._na_cama(now) else self._casa_ou_pijama(now)
            oc = "pijama" if grupo == "pijama" else "casa"
            look = self._escolhe(st, grupo, now, f"inicio:{now.date()}")
            st.update({"atual": {"look": look, "ocasiao": oc, "desde": now.isoformat(), "pra": PRA_OCASIAO[oc],
                                 "chave": ""},
                       "make": {"nivel": "sem", "feita_em": None, "extra": 0.0, "motivos": []},
                       "em_casa": True, "hist": [], "feitos": [], "usado": {}})
            self._save(st)
        return st

    # -------------------------------------------------------------- consultas --
    def _na_cama(self, now: datetime) -> bool:
        try:
            from sleep_plan import SleepPlan
            sp = SleepPlan(self.db)
            return sp.in_bed(now) and not sp.napping(now)
        except Exception:
            return False

    def _no_banho(self, now: datetime) -> bool:
        try:
            from rituals import Rituals
            return Rituals(self.db).in_shower(now)
        except Exception:
            return False

    def _place_key(self, snap: Optional[dict]) -> Optional[str]:
        try:
            with self.db.get_connection() as conn:
                if snap is None:
                    snap = conn.execute("SELECT location_place_id FROM world_state ORDER BY id DESC LIMIT 1").fetchone()
                    snap = dict(snap) if snap else {}
                pid = snap.get("location_place_id")
                if not pid:
                    return None
                row = conn.execute("SELECT canonical_key FROM world_places WHERE id=?", (pid,)).fetchone()
                return row["canonical_key"] if row else None
        except Exception:
            return None

    def _em_casa(self, snap: Optional[dict] = None) -> bool:
        return self._place_key(snap) in (None, HOME)

    @staticmethod
    def _casa_ou_pijama(at: datetime) -> str:
        if at.hour >= 22 or at.hour < 5:
            return "pijama"
        return "casa_noite" if at.hour >= 19 else "casa_dia"

    def _feeling(self, now: datetime):
        try:
            from emotion import EmotionEngine
            return EmotionEngine(self.db).feeling(now)
        except Exception:
            return None

    def _intimo_turno(self, now: datetime):
        try:
            from intimacy import IntimacyEngine
            eng = IntimacyEngine(self.db)
            return eng.current(now), eng._load()
        except Exception:
            return None, {}

    # ------------------------------------------------------------ guarda-roupa --
    def _escolhe(self, st: dict, grupo: str, at: datetime, semente: str) -> list:
        """Um look do grupo sem repetir o dos últimos 3 dias, de preferência sem peça usada ontem."""
        looks = [list(x) for x in LOOKS[grupo]]
        recentes = [h for h in st.get("hist", []) + ([st["atual"]] if st.get("atual") else [])
                    if at - datetime.fromisoformat(h["desde"]) < LOOK_SEM_REPETIR]
        usados = {tuple(h["look"]) for h in recentes}
        ontem = {p for h in recentes if at - datetime.fromisoformat(h["desde"]) < timedelta(hours=30)
                 for p in h["look"]}
        opcoes = [x for x in looks if tuple(x) not in usados] or looks
        frescos = [x for x in opcoes if not set(x) & ontem] or opcoes
        return random.Random(f"roupa:{semente}").choice(frescos)

    def _vestir(self, st: dict, look: list, ocasiao: str, at: datetime, pra: str, chave: str = "") -> None:
        atual = st.get("atual")
        if atual and atual.get("look") == look and atual.get("ocasiao") == ocasiao:
            return
        if atual and datetime.fromisoformat(atual["desde"]) < at:   # troca retroativa antes dela: substitui
            st.setdefault("hist", []).append({**atual, "ate": at.isoformat()})
            corte = at - timedelta(days=HIST_DIAS)
            st["hist"] = [h for h in st["hist"] if datetime.fromisoformat(h["ate"]) >= corte]
        st["atual"] = {"look": look, "ocasiao": ocasiao, "desde": at.isoformat(), "pra": pra, "chave": chave}
        for p in look:
            st.setdefault("usado", {})[p] = at.isoformat()
        st["troca_em"] = None
        if ocasiao != "provocar":
            st["dorme"] = None
        logger.info("roupa.vestiu ocasiao=%s look=%s", ocasiao, "+".join(look))

    def _make(self, st: dict, nivel: str, at: datetime) -> None:
        mk = st.setdefault("make", {})
        if mk.get("nivel") == nivel and nivel == "sem":
            return
        st["make"] = {"nivel": nivel, "feita_em": at.isoformat() if nivel != "sem" else None, "extra": 0.0,
                      "motivos": [], "dormiu": False}
        logger.info("roupa.make nivel=%s", nivel)

    def _borra(self, st: dict, motivo: str) -> None:
        mk = st.get("make") or {}
        if mk.get("nivel", "sem") == "sem" or motivo in mk.get("motivos", []):
            return
        mk["extra"] = round(mk.get("extra", 0.0) + BORRA[motivo], 2)
        mk.setdefault("motivos", []).append(motivo)

    # ------------------------------------------------------------------- tick --
    def tick(self, now: datetime, snap: Optional[dict] = None) -> None:
        """Chamado no fim de cada resolve do mundo: aplica o que mudou na roupa e na make."""
        st = self._state(now)
        if not st.get("atual"):
            return
        antes = json.dumps(st, ensure_ascii=False, sort_keys=True)
        casa = self._em_casa(snap)
        self._clima(st, now, casa)
        if casa and "academia do prédio" in ((snap or {}).get("activity") or "").lower():
            self._academia_predio(st, now)
            casa = False                                  # na volta pro apê, a troca de "chegou" vale
        elif casa and self._na_cama(now):
            self._deitada(st, now)
        else:
            etapa = None
            act = ((snap or {}).get("activity") or "").lower()
            if snap is None or act.startswith("se arrumando"):
                # o card só é consultado quando ela está se arrumando (o resolve já disse): recalcular o dia a cada
                # resolve custava ~17 ms (medido em 28/09)
                try:
                    from agenda import Agenda
                    etapa = Agenda(self.db).agora(now)
                except Exception:
                    logger.exception("roupa.agenda")
            if etapa and etapa.tipo == "arrumando":
                self._arrumando(st, etapa, now)
                casa = True
            elif not casa:
                self._na_rua(st, etapa, now, snap)
            else:
                self._em_casa_livre(st, now)
        st["em_casa"] = casa
        st["feitos"] = st.get("feitos", [])[-80:]
        if json.dumps(st, ensure_ascii=False, sort_keys=True) != antes:
            self._save(st)                                # só grava quando mudou algo

    def _feito(self, st: dict, chave: str) -> bool:
        if chave in st.setdefault("feitos", []):
            return True
        st["feitos"].append(chave)
        return False

    def _arrumando(self, st: dict, etapa, now: datetime) -> None:
        tipo, chave = etapa.prep_tipo or "", etapa.chave
        st["pos_banho"] = None                           # o banho do Se arrumando: quem veste é o passo da roupa
        passos = [p for p in etapa.passos if not p.aviso and not getattr(p, "encontro", False)]
        tem_roupa = any(_ROUPA_PASSO.search(p.texto) for p in passos)
        if not tem_roupa and etapa.inicio <= now and not self._feito(st, f"{chave}:inicio"):
            # passeio do Milo, mercado da semana: sai com o que está, se der pra pôr o pé na rua
            if st["atual"]["ocasiao"] not in RUA_OK:
                grupo = "rua" if tipo != "milo" else "casa_dia"
                self._vestir(st, self._escolhe(st, grupo, etapa.inicio, chave), "rua" if tipo != "milo" else "casa",
                             etapa.inicio, PRA.get(tipo, "Sair"), chave)
        for p in passos:
            if p.inicio > now or self._feito(st, f"{chave}:{p.texto}"):
                continue
            t = p.texto
            if _TIRA_MAKE.search(t) or t.startswith("Tomando banho"):
                self._make(st, "sem", p.inicio)           # no banho lava o rosto
            if t.startswith("Tomando banho") and tem_roupa and not (
                    tipo == "dormir" and st["atual"]["ocasiao"] == "provocar"):
                # Soak, dia 4 (/feedback de 02/10, 19:06): secando o cabelo e o Por fora com a roupa da academia.
                # Do banho até o passo da roupa ela fica de toalha (de lingerie pra provocar, fica com ela).
                self._vestir(st, ["toalha"], "toalha", p.inicio, "Saiu do banho", chave)
            elif t == "Fazendo maquiagem leve":
                self._make(st, "leve", p.inicio)
            elif t.startswith("Fazendo maquiagem"):
                festa = bool(_EVENTO_RE.search(f"{etapa.titulo} {etapa.linha2}")) or (
                    tipo == "noite" and random.Random(f"roupa:festa:{chave}").random() < 0.35)
                self._make(st, "festa" if festa else "completa", p.inicio)
            if _ROUPA_PASSO.search(t):
                self._veste_pra(st, tipo, chave, p.inicio, now)
        for p in etapa.passos:
            # Soak, dia 4 (/feedback de 02/10, 19:54): "se atrasou porque trocou de look" e o Por fora com a mesma
            # roupa. O que segurou a saída acontece de verdade: ela sai com outro look do mesmo tipo.
            if not (p.aviso and _TROCOU_LOOK.search(p.texto)) or p.inicio > now:
                continue
            atual = st["atual"]
            if self._feito(st, f"{chave}:{p.texto}") or atual.get("chave") != chave or atual["ocasiao"] not in LOOKS:
                continue
            look = self._escolhe(st, atual["ocasiao"], p.inicio, f"{chave}:trocou")
            self._vestir(st, look, atual["ocasiao"], p.inicio, atual.get("pra") or PRA.get(tipo, "Sair"), chave)

    def _veste_pra(self, st: dict, tipo: str, chave: str, at: datetime, now: datetime) -> None:
        if tipo == "dormir":
            if st["atual"]["ocasiao"] == "provocar" and self._dorme_de_lingerie(st, at):
                return
            self._vestir(st, self._escolhe(st, "pijama", at, chave), "pijama", at, PRA["dormir"], chave)
            return
        ocasiao = OCASIAO_PREP.get(tipo, "rua")
        look = None
        esc = st.get("escolha")
        if ocasiao == "sair" and esc and at <= datetime.fromisoformat(esc["ate"]):
            look, st["escolha"] = esc["look"], None       # o look que ele escolheu nas duas opções
        look = look or self._escolhe(st, ocasiao, at, chave)
        self._vestir(st, look, ocasiao, at, PRA.get(tipo, "Sair"), chave)
        f = self._feeling(now)
        rng = random.Random(f"roupa:make:{chave}")
        if tipo in LEVE_IMPLICITA and (st.get("make") or {}).get("nivel", "sem") == "sem":
            animada = f is None or (f.valence >= 0.45 and f.energy >= 0.35)
            if rng.random() < (0.7 if animada else 0.25):
                self._make(st, "leve", at)
        if tipo in ("noite", "encontro"):
            from emotion import TESAO_MIN
            tesao = f is not None and f.libido >= TESAO_MIN
            if rng.random() < (POR_BAIXO_CHANCE_TESAO if tesao else POR_BAIXO_CHANCE):
                peca = self._peca_intima(st, at, pool=POR_BAIXO, semente=f"baixo:{chave}")
                st["por_baixo"] = {"peca": peca, "chave": chave, "desde": at.isoformat(), "contou": False}
                logger.info("roupa.por_baixo peca=%s", peca)

    def _na_rua(self, st: dict, etapa, now: datetime, snap: Optional[dict]) -> None:
        st["pos_banho"] = None
        if st.get("em_casa", True):
            # acabou de sair: o Se arrumando que o resolve não viu (banho por cima, resolve espaçado) vale agora
            prep = self._prep_recente(now)
            if prep:
                self._arrumando(st, prep, now)
        oc = st["atual"]["ocasiao"]
        if oc not in RUA_OK or (oc == "casa" and st["atual"].get("pra") != PRA["milo"]):
            # saiu sem Se arrumando (de repente): pôs uma roupa de rua
            self._vestir(st, self._escolhe(st, "rua", now, f"saiu:{now:%Y%m%d%H}"), "rua", now, "Sair")
        act = ((snap or {}).get("activity") or "").lower()
        chave = getattr(etapa, "chave", "") or f"rua:{now.date()}:{st['atual'].get('chave') or st['atual']['desde']}"
        if re.search(r"academia|treinando|malhando|muscula", act) and not self._feito(st, f"{chave}:suor"):
            self._borra(st, "suor")
        if re.search(r"\bpraia\b|\bmar\b|tomando sol", act) and not self._feito(st, f"{chave}:praia"):
            self._borra(st, "praia")
        if re.search(r"ensaio|freela|sess[aã]o de fotos|job\b", act) and not self._feito(st, f"{chave}:ensaio"):
            self._make(st, "ensaio", now)                # a make do freela é feita lá
        self._choro(st, now)

    def _academia_predio(self, st: dict, now: datetime) -> None:
        """/feedback 03/10 17:44: treinando na academia do prédio "com roupa de ficar em casa". Ela desce de treino
        (não tem Se arrumando: é no prédio) e sua."""
        st["pos_banho"] = None
        chave = f"gym_predio:{now.date().isoformat()}"
        if st["atual"]["ocasiao"] != "treino":
            self._vestir(st, self._escolhe(st, "treino", now, chave), "treino", now, PRA["academia"], chave)
        if not self._feito(st, f"{chave}:suor"):
            self._borra(st, "suor")

    def _prep_recente(self, now: datetime):
        """O Se arrumando da saída de agora (acabou há até 3 h)."""
        try:
            from agenda import Agenda
            for dia in (now.date(), now.date() - timedelta(days=1)):
                for e in reversed(Agenda(self.db).etapas(dia, now)):
                    if e.tipo == "arrumando" and e.prep_tipo != "dormir" and now - timedelta(hours=3) <= e.fim <= \
                            now + timedelta(minutes=1):
                        return e
        except Exception:
            logger.exception("roupa.prep_recente")
        return None

    def _em_casa_livre(self, st: dict, now: datetime) -> None:
        atual = st["atual"]
        if not st.get("em_casa", True):                  # chegou agora
            st["chegou_em"] = now.isoformat()
            st["troca_em"] = self._quando_troca(st, now)
            if atual["ocasiao"] == "casa":               # voltou do Milo de short e camiseta: é roupa de casa de novo
                atual["pra"] = PRA_OCASIAO["casa"]
        self._choro(st, now)
        mk = st.get("make") or {}
        if mk.get("dormiu") and self._acordou_ha(now) >= timedelta(minutes=25):
            self._make(st, "sem", now)                    # acordou borrada e lavou o rosto
        if self._no_banho(now):
            return
        pos = st.get("pos_banho")
        if pos and now >= datetime.fromisoformat(pos):
            st["pos_banho"] = None
            if atual["ocasiao"] != "provocar":
                self._pra_casa(st, datetime.fromisoformat(pos))
            return
        troca = st.get("troca_em")
        if troca and now >= datetime.fromisoformat(troca):
            self._pra_casa(st, datetime.fromisoformat(troca))
            return
        if atual["ocasiao"] == "pijama" and 5 <= now.hour < 21:
            acordou = self._acordou_ha(now)
            espera = timedelta(minutes=random.Random(f"roupa:acordou:{now.date()}").randint(20, 90))
            if acordou >= espera:
                self._pra_casa(st, now)
            return
        if atual["ocasiao"] == "provocar":
            turno, _ = self._intimo_turno(now)
            no_clima = turno is not None and turno.state in CLIMA
            ultimo = max(datetime.fromisoformat(atual["desde"]),
                         datetime.fromisoformat(st["clima_em"]) if st.get("clima_em") else datetime.min)
            if not no_clima and now - ultimo >= PROVOCAR_FIM and not self._dorme_hoje(st, now):
                self._pra_casa(st, now)

    def _pra_casa(self, st: dict, at: datetime) -> None:
        grupo = self._casa_ou_pijama(at)
        oc = "pijama" if grupo == "pijama" else "casa"
        self._vestir(st, self._escolhe(st, grupo, at, f"casa:{at:%Y%m%d%H%M}"), oc, at, PRA_OCASIAO[oc])

    def _quando_troca(self, st: dict, now: datetime) -> Optional[str]:
        """Chegou da rua: troca pra roupa de casa em 10–40 min; de rolê à noite, às vezes fica até o Se arrumando
        pra dormir; se vai sair de novo logo, não troca."""
        oc = st["atual"]["ocasiao"]
        if oc in ("casa", "pijama", "provocar"):
            return None
        rng = random.Random(f"roupa:chegou:{now:%Y%m%d%H%M}")
        try:
            from agenda import Agenda
            for e in Agenda(self.db).etapas(now.date(), now):
                if e.tipo == "arrumando" and now <= e.inicio <= now + timedelta(minutes=90) and e.prep_tipo != "dormir":
                    return None
        except Exception:
            logger.exception("roupa.quando_troca")
        if oc in ("sair", "jogo") and (now.hour >= 22 or now.hour < 5) and rng.random() < 0.6:
            return None
        lo, hi = (15, 45) if oc == "treino" else (10, 40)
        return (now + timedelta(minutes=rng.randint(lo, hi))).isoformat()

    def _acordou_ha(self, now: datetime) -> timedelta:
        try:
            from sleep_plan import SleepPlan
            wakes = [w for _n, _b, w in SleepPlan(self.db).nights_around(now) if w <= now]
            return now - max(wakes) if wakes else timedelta(hours=12)
        except Exception:
            return timedelta(hours=12)

    def _deitada(self, st: dict, now: datetime) -> None:
        try:
            from sleep_plan import SleepPlan
            beds = [b for _n, b, w in SleepPlan(self.db).nights_around(now) if b <= now < w]
            bed = beds[0] if beds else now
        except Exception:
            bed = now
        oc = st["atual"]["ocasiao"]
        if oc == "provocar" and self._dorme_de_lingerie(st, bed):
            pass
        elif oc != "pijama":
            self._vestir(st, self._escolhe(st, "pijama", bed, f"deitou:{bed.date()}"), "pijama", bed, PRA["dormir"])
        mk = st.get("make") or {}
        if mk.get("nivel", "sem") != "sem" and not mk.get("dormiu"):
            self._borra(st, "dormiu")
            mk["dormiu"] = True
            self._acontecimento(f"roupa:dormiu_de_make:{bed.date()}", bed, "dormiu de make",
                                f"Dormiu sem tirar a make ({MAKE[mk['nivel']][0].lower()}) e acordou borrada.", 0.3)
        st["pos_banho"] = st["troca_em"] = None

    def _dorme_hoje(self, st: dict, now: datetime) -> bool:
        return st.get("dorme") == (now - timedelta(hours=5)).date().isoformat()

    def _dorme_de_lingerie(self, st: dict, at: datetime) -> bool:
        """Na hora de dormir, de lingerie: às vezes fica com ela (mais se gozou com ele hoje)."""
        dia = (at - timedelta(hours=5)).date().isoformat()
        if st.get("dorme") == dia:
            return True
        if st.get("dorme_decidido") == dia:
            return False
        st["dorme_decidido"] = dia
        _, ist = self._intimo_turno(at)
        gozou = bool(ist.get("climax_at")) and at - datetime.fromisoformat(ist["climax_at"]) < timedelta(hours=4)
        fica = random.Random(f"roupa:dorme:{dia}").random() < (DORME_CHANCE_GOZOU if gozou else DORME_CHANCE)
        if fica:
            st["dorme"] = dia
            st["atual"]["pra"] = "Dormir de lingerie"
        return fica

    def dorme_de_lingerie(self, day) -> bool:
        """Pro card (Se arrumando pra dormir): ela decidiu ficar de lingerie na noite de `day`."""
        return self._load().get("dorme") == day.isoformat()

    def _clima(self, st: dict, now: datetime, casa: bool) -> None:
        """Sexting rolando: guarda a hora; em casa, às vezes ela vai vestir algo pra ele (uma vez por sessão)."""
        turno, ist = self._intimo_turno(now)
        if turno is None or turno.state not in CLIMA:
            return
        st["clima_em"] = now.isoformat()
        sessao = ist.get("mode_since")
        if (turno.state == "active" and sessao and casa and st.get("clima_sessao") != sessao
                and st["atual"]["ocasiao"] != "provocar" and not self._no_banho(now) and not self._na_cama(now)):
            st["clima_sessao"] = sessao
            if random.Random(f"roupa:clima:{sessao}").random() < CLIMA_VESTE_CHANCE + turno.arousal * 0.3:
                self._provocar(st, now, "clima")

    def _choro(self, st: dict, now: datetime) -> None:
        mk = st.get("make") or {}
        if mk.get("nivel", "sem") == "sem" or "choro" in mk.get("motivos", []):
            return
        visto = st.get("choro_visto")
        if visto and now - datetime.fromisoformat(visto) < timedelta(minutes=10):
            return                                        # o sentimento não muda a cada minuto (resolve leve)
        st["choro_visto"] = now.isoformat()
        f = self._feeling(now)
        if f and any(e.family == "tristeza" and e.intensity >= 0.6 for e in (f.episodes or [])):
            self._borra(st, "choro")

    # --------------------------------------------------------------- provocar --
    def _peca_intima(self, st: dict, at: datetime, *, pool=None, nivel: int = 2, semente: str = "") -> str:
        usado = st.get("usado", {})
        if pool is None:
            f = self._feeling(at)
            muito = f is not None and f.libido >= 0.85
            pesos = {"lingerie": 0.45, "fetiche": 0.35 if muito else 0.2, "transparencia": 0.25}
            if nivel == 1:
                pesos = {"provoca": 1.0}
            rng = random.Random(f"roupa:gaveta:{semente or at.isoformat()}")
            tipo = rng.choices(list(pesos), weights=list(pesos.values()))[0]
            pool = [k for k, v in INTIMO.items() if v[3] == tipo]
        else:
            rng = random.Random(f"roupa:gaveta:{semente or at.isoformat()}")
        frescos = [k for k in pool if not usado.get(k)
                   or at - datetime.fromisoformat(usado[k]) >= INTIMO_SEM_REPETIR] or list(pool)
        return rng.choice(frescos)

    def _provocar(self, st: dict, at: datetime, motivo: str, nivel: int = 2, peca: Optional[str] = None,
                  cobre: Optional[str] = None) -> str:
        peca = peca or self._peca_intima(st, at, nivel=nivel, semente=f"{motivo}:{at:%Y%m%d%H%M}")
        look = [cobre, peca] if cobre else [peca]
        if INTIMO[peca][3] == "fetiche" and not cobre:
            rng = random.Random(f"roupa:acessorio:{peca}:{at:%Y%m%d%H}")
            if rng.random() < 0.4 and peca not in ("policial", "empregada"):
                look.append("choker")
            if rng.random() < 0.5:
                look.append("salto")
        self._vestir(st, look, "provocar", at, PRA_OCASIAO["provocar"])
        if st.get("por_baixo") and st["por_baixo"]["peca"] == peca:
            st["por_baixo"] = None                       # tirou a roupa de cima
        self._acontecimento(f"roupa:provocar:{at:%Y%m%d%H%M}", at, "provocando",
                            f"Vestiu {nome_look(look).lower()} pra provocar o Patrick.", 0.0)
        return en_look(look)

    def provocar(self, now: datetime, motivo: str) -> Optional[str]:
        """Com tesão, em casa, ela vai no quarto e veste algo pra provocar ele (iniciativa de tesão, masturbação
        chamando ele). Devolve o nome da peça, ou None (fora de casa, dormindo, no banho, já provocando)."""
        st = self._state(now)
        if not st.get("atual") or st["atual"]["ocasiao"] == "provocar":
            return None
        if not self._em_casa() or self._na_cama(now) or self._no_banho(now):
            return None
        try:
            from agenda import Agenda
            e = Agenda(self.db).agora(now)
            if e and e.tipo == "arrumando" and e.prep_tipo != "dormir":
                return None
        except Exception:
            pass
        self._provocar(st, now, motivo)
        self._save(st)
        return nome_look(st["atual"]["look"]).lower()

    def pro_clima(self, now: datetime, level: int) -> Optional[str]:
        """Foto no clima (nível 1–2) em casa: a peça que ela está usando pra ele; se não está, veste agora (e fica
        a mesma em todas as fotos da sessão). Por baixo da roupa de sair: é ela que aparece."""
        st = self._state(now)
        atual = st.get("atual")
        if not atual:
            return None
        if atual["ocasiao"] == "provocar":
            look = atual["look"]
            if look[0] in COBRE:
                if level < 2:
                    return en_look(look)
                self._vestir(st, look[1:], "provocar", now, PRA_OCASIAO["provocar"])   # tirou o de cima
                self._save(st)
                return en_look(look[1:])
            if INTIMO.get(look[0], ("", "", 2))[2] >= level:
                return en_look(look)
        pb = st.get("por_baixo")
        if level >= 2 and pb and atual["ocasiao"] in ("sair", "jogo", "rua"):
            en = self._provocar(st, now, "tirou a roupa", peca=pb["peca"])
        elif level == 1:                                  # bug 17: a lingerie já vai por baixo
            rng = random.Random(f"roupa:cobre:{now:%Y%m%d%H%M}")
            peca = self._peca_intima(st, now, pool=list(POR_BAIXO), semente=f"cobre:{now:%Y%m%d%H%M}")
            en = self._provocar(st, now, "pedido", peca=peca, cobre=rng.choice(list(COBRE)))
        else:
            en = self._provocar(st, now, "pedido", nivel=level)
        self._save(st)
        return en

    # ------------------------------------------------------------------ banho --
    def banho(self, inicio: datetime, fim: datetime) -> None:
        """Ela entrou no banho (rituals.start_shower): a make sai; depois veste roupa de casa (ou pijama)."""
        st = self._state(inicio)
        if not st.get("atual"):
            return
        if (st.get("make") or {}).get("nivel", "sem") != "sem":
            self._make(st, "sem", inicio)
        st["pos_banho"] = (fim + timedelta(minutes=5)).isoformat()
        self._save(st)

    # ------------------------------------------------------------- conversa --
    def observe_marina(self, text: str, now: datetime, his: str = "") -> None:
        """Ela contou pro Patrick o que está usando por baixo: agora aparece no painel. E o look que ela diz que vai
        usar pra sair hoje vira a escolha dela."""
        st = self._load()
        pb = st.get("por_baixo")
        if pb and not pb.get("contou") and _CONTOU_RE.search(text or ""):
            pb["contou"] = True
            self._save(st)
            logger.info("roupa.por_baixo.contou")
        self._look_dito(text or "", his or "", now)

    def _look_dito(self, text: str, his: str, now: datetime) -> None:
        """Soak, dia 5 (03/10, 19:11): "que look que tu vai sair?" → "Um vestido preto, bem básico" — e às 20:31 o
        mundo vestiu corset e jeans (depois o verde). O que ela disse que vai usar é o que ela veste no passo da roupa."""
        low = text.lower()
        look = next((list(lk) for pat, lk in _LOOK_DITO if re.search(pat, low)), None)
        if not look or not _LOOK_CONTEXTO.search(f"{his} {text}".lower()):
            return
        st = self._state(now)
        if (st.get("atual") or {}).get("ocasiao") == "sair":
            return                                        # já está vestida pra sair
        try:
            from agenda import Agenda
            etapas = Agenda(self.db).etapas(now.date(), now)
        except Exception:
            logger.exception("roupa.look_dito")
            return
        vai = any(e.tipo == "arrumando" and e.prep_tipo in ("noite", "encontro") and e.fim > now
                  and any(_ROUPA_PASSO.search(p.texto) and p.inicio > now for p in e.passos) for e in etapas)
        if not vai or (st.get("escolha") or {}).get("look") == look:
            return
        st["escolha"] = {"look": look, "ate": (now + timedelta(hours=12)).isoformat()}
        self._save(st)
        logger.info("roupa.look_dito look=%s", "+".join(look))

    def observe_patrick(self, text: str, now: datetime) -> Optional[list]:
        """Ele escolheu uma das duas opções de look que ela mandou: é essa que ela veste pra sair."""
        try:
            import promessa_foto
            p = promessa_foto._load(self.db).get("promessa") or {}
        except Exception:
            return None
        outfits = p.get("outfits") or []
        if p.get("kind") != "looks" or p.get("status") != "cumprida" or len(outfits) < 2:
            return None
        if not p.get("due_at") or now - datetime.fromisoformat(p["due_at"]) > timedelta(hours=3):
            return None
        low = (text or "").lower()
        i = 1 if _SEGUNDA_RE.search(low) and not _PRIMEIRA_RE.search(low) else (
            0 if _PRIMEIRA_RE.search(low) and not _SEGUNDA_RE.search(low) else None)
        if i is None:
            return None
        look = look_do_en(outfits[i])
        st = self._state(now)
        if not look or (st.get("escolha") or {}).get("look") == look:
            return None
        st["escolha"] = {"look": look, "ate": (now + timedelta(hours=12)).isoformat()}
        atual = st.get("atual") or {}
        if atual.get("ocasiao") == "sair" and now - datetime.fromisoformat(atual["desde"]) < timedelta(hours=2) \
                and self._em_casa():
            self._vestir(st, look, "sair", now, atual.get("pra") or "Sair à noite", atual.get("chave", ""))
            st["escolha"] = None                          # ainda em casa, já vestida: troca pro que ele escolheu
        self._save(st)
        logger.info("roupa.escolha_dele look=%s", "+".join(look))
        return look

    def opcoes_de_look(self, count: int, now: datetime, rng: random.Random) -> list[str]:
        """As opções de look de sair que ela mostra pra ele (do guarda-roupa dela)."""
        st = self._state(now)
        looks = [list(x) for x in LOOKS["sair"]]
        atual = (st.get("atual") or {}).get("look")
        pool = [x for x in looks if x != atual] or looks
        return [en_look(x) for x in rng.sample(pool, min(count, len(pool)))]

    # ------------------------------------------------------ foto e Instagram --
    def entrada_em(self, at: datetime) -> Optional[dict]:
        st = self._load()
        atual = st.get("atual")
        if atual and datetime.fromisoformat(atual["desde"]) <= at:
            return atual
        for h in reversed(st.get("hist", [])):
            if datetime.fromisoformat(h["desde"]) <= at < datetime.fromisoformat(h["ate"]):
                return h
        return None

    def en_em(self, at: datetime) -> Optional[str]:
        e = self.entrada_em(at)
        return en_look(e["look"]) if e else None

    def ocasiao_em(self, at: datetime) -> Optional[str]:
        e = self.entrada_em(at)
        return e["ocasiao"] if e else None

    def make_desgaste(self, now: datetime) -> float:
        mk = self._load().get("make") or {}
        nivel = mk.get("nivel", "sem")
        if nivel == "sem" or not mk.get("feita_em"):
            return 0.0
        horas = max(0.0, (now - datetime.fromisoformat(mk["feita_em"])).total_seconds() / 3600)
        return round(min(1.0, horas * MAKE[nivel][2] + mk.get("extra", 0.0)), 2)

    @staticmethod
    def _palavra_make(d: float) -> str:
        return "Intacta" if d < 0.35 else "Pedindo retoque" if d < 0.7 else "Borrada"

    def make_prompt(self, at: datetime) -> str:
        """A make na foto (depois da roupa)."""
        mk = self._load().get("make")
        if not mk:
            return ""
        nivel = mk.get("nivel", "sem")
        if nivel == "sem":
            return f"She has {MAKE['sem'][1]}."
        d = self.make_desgaste(at)
        extra = (", her mascara smudged under her eyes" if d >= 0.7
                 else ", slightly faded after hours of wear" if d >= 0.35 else "")
        return f"She is wearing {MAKE[nivel][1]}{extra}."

    # ----------------------------------------------------------- painel e chat --
    def painel(self, now: datetime) -> Optional[dict]:
        """Bloco "Agora" da aba Por fora (mockup aprovado em 28/09): a roupa em destaque, Pra quê, Por baixo (só
        depois que ela contou) e Make com a barra de desgaste."""
        st = self._state(now)
        atual = st.get("atual")
        if not atual:
            return None
        mk = st.get("make") or {"nivel": "sem"}
        banho = self._no_banho(now)
        out = {"look": "No banho" if banho else nome_look(atual["look"]), "linhas": [], "make": None}
        if not banho and atual["ocasiao"] != "toalha":   # de toalha não tem "pra quê"
            out["linhas"].append(["hanger", "Para", f"{atual.get('pra') or PRA_OCASIAO.get(atual['ocasiao'], '')}, "
                                                      f"desde {_hhmm(datetime.fromisoformat(atual['desde']))}"])
            pb = st.get("por_baixo")
            if pb and pb.get("contou") and atual["ocasiao"] in ("sair", "jogo", "rua"):
                out["linhas"].append(["heart", "Por baixo", _nome(pb["peca"])[:1].upper() + _nome(pb["peca"])[1:]])
        nivel = mk.get("nivel", "sem")
        if nivel == "sem":
            out["linhas"].append(["brush", "Maquiagem", "Sem maquiagem"])
        else:
            d = self.make_desgaste(now)
            out["make"] = {"valor": d, "palavra": self._palavra_make(d), "alerta": d >= 0.7}
            out["linhas"].append(["brush", "Maquiagem", f"{MAKE[nivel][0]}, às {_hhmm(datetime.fromisoformat(mk['feita_em']))}"])
        return out

    def prompt_lines(self, now: datetime) -> list[str]:
        try:
            return self._prompt_lines(now)
        except Exception:
            logger.exception("roupa.prompt_lines")    # não derruba os blocos do prompt que vêm depois
            return []

    def _prompt_lines(self, now: datetime) -> list[str]:
        st = self._state(now)
        atual = st.get("atual")
        if not atual:
            return []
        desde = _hhmm(datetime.fromisoformat(atual["desde"]))
        lines = ["[SUA ROUPA E MAKE — de verdade; é o que aparece nas suas fotos, não invente outra]"]
        if self._no_banho(now):
            lines.append(f"- No banho agora (antes estava de {nome_look(atual['look']).lower()}).")
        elif atual["ocasiao"] == "provocar":
            lines.append(f"- Você vestiu {nome_look(atual['look']).lower()} às {desde} pra provocar o Patrick. "
                         "Ele só sabe se você contar ou mandar foto — provoca do seu jeito quando der vontade.")
        else:
            lines.append(f"- Vestindo: {nome_look(atual['look']).lower()} ({(atual.get('pra') or '').lower()}, "
                         f"desde {desde}).")
        pb = st.get("por_baixo")
        if pb and atual["ocasiao"] in ("sair", "jogo", "rua"):
            lines.append(f"- Por baixo: {_nome(pb['peca'])}, escolhida pensando nele. "
                         + ("Ele já sabe." if pb.get("contou") else
                            "Ele não sabe; se der vontade no meio do rolê, provoca contando."))
        mk = st.get("make") or {}
        nivel = mk.get("nivel", "sem")
        if nivel == "sem":
            lines.append("- Make: sem make.")
        else:
            d = self.make_desgaste(now)
            estado = self._palavra_make(d).lower()
            porque = {"suor": "suou", "praia": "praia", "choro": "chorou", "dormiu": "dormiu com ela"}
            motivos = [porque[m] for m in mk.get("motivos", []) if m in porque]
            lines.append(f"- Make: {MAKE[nivel][0].lower()}, feita às {_hhmm(datetime.fromisoformat(mk['feita_em']))}; "
                         f"{estado}" + (f" ({', '.join(motivos)})" if motivos else "") + ".")
        return lines

    # -------------------------------------------------------------- história --
    def _acontecimento(self, key: str, at: datetime, title: str, summary: str, share: float) -> None:
        try:
            with self.db.get_connection() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                       autonomy_level,importance,participants_json,share_worthy,created_at)
                       VALUES (?,?,'routine',?,?,'simulated',1,0.2,?,?,?)""",
                    (key, at.isoformat(), title, summary, json.dumps(["marina"]), share, datetime.now().isoformat()))
                conn.commit()
        except Exception:
            logger.exception("roupa.acontecimento")
