"""Agenda reativa (Patrick, 26/09): tudo pode ser interrompido, e o que ela topa na conversa acontece.

"Parece que tudo na vida dela é premeditado e segue o fluxo até o final." Duas portas:

1. **A conversa mexe na agenda.** Depois que a fala dela sai, se tem cara de plano ("tá bom, vou
   treinar", "vou descer com o Milo", "desisti do açaí", "vou embora daqui"), um modelo barato lê a
   fala dela e a mensagem dele e diz o que mudou. Vira item da agenda única (`vontade.agendar`,
   origem "conversa": se arrumando a partir de agora, a caminho, lá, voltando), adianta o planejado
   (academia e passeio do Milo), cancela o que ela desistiu ou encerra o que ela está fazendo.
2. **Sair mais cedo, por motivo.** Enquanto ela está num compromisso, às vezes acontece: passou mal,
   emergência de banheiro, cansou, o rolê ficou chato, bateu tédio — e tesão, que é emergência: vai
   correndo pra casa (e lá se alivia) ou se tranca num banheiro por ali, às vezes chamando ele.

Sair mais cedo só encurta o fim do compromisso (a volta é calculada a partir dele) e guarda a hora
original; a aula que ela larga no meio vira exceção na grade (`academic_class_cancelled` com "ate").
Estado em estado_relacional[KEY], sem migration.
"""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import date, datetime, time, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

KEY = "agenda_reativa_json"
SLOT_MIN = 20                      # uma chance de interromper por janela de 20 min
MIN_PASSADO = 0.3                  # só depois de 30% do compromisso (ninguém larga a academia no aquecimento)

# motivo → (texto do acontecimento, minutos até sair, quais compromissos)
MOTIVOS = {
    "passando_mal": ("não tava se sentindo bem", 5, None),
    "banheiro": ("teve uma emergência de banheiro", 2, None),
    "cansou": ("cansou antes da hora", 5, ("academia", "milo", "orla", "shopping", "praia", "noite", "encontro", "jogo")),
    "role_chato": ("o rolê ficou chato", 8, ("noite", "encontro", "jogo", "shopping")),
    "sem_bateria": ("a bateria social acabou", 8, ("noite", "encontro", "jogo")),
    "tedio": ("bateu um tédio", 5, ("faculdade", "academia", "shopping", "orla", "praia", "cafe", "noite", "encontro")),
    "tesao": ("bateu um tesão que não dava pra segurar", 2, None),
    "conversa": ("", 5, None),
}
# onde ela se tranca, por tipo de compromisso (lugar reservado)
RESERVADO = {"academia": "no banheiro da academia", "faculdade": "no banheiro da PUC",
             "shopping": "no banheiro do shopping", "noite": "no banheiro do bar", "encontro": "no banheiro",
             "jogo": "no banheiro do estádio", "cafe": "no banheiro do café", "freela": "no banheiro do estúdio",
             "mercado_semana": "no banheiro do mercado", "praia": "no banheiro do quiosque"}
SEM_PAUSA = ("milo", "orla", "medico", "pronto_atendimento", "farmacia", "mercado", "acai")
# motivo na grade do card (Patrick, 26/09: painel, seco)
MOTIVO_CURTO = {"passando_mal": "Mal-estar", "banheiro": "Banheiro", "cansou": "Cansaço", "role_chato": "Rolê chato",
                "sem_bateria": "Bateria social", "tedio": "Tédio", "tesao": "Tesão"}
# Patrick, 26/09: "dependendo do motivo eu não deixo ela ir a pé; ela teria que me avisar, eu pagaria o uber"
UBER_MOTIVOS = ("passando_mal", "banheiro", "cansou")
UBER_PIX_JANELA = timedelta(hours=3)             # pix dele nesse tempo é o do uber
LUGAR_PLANEJADO = {"academia": "bodytech_sao_clemente", "milo": "enseada_botafogo"}

# gate barato antes do modelo: a fala dela tem cara de plano?
PLANO_RE = re.compile(
    r"\b(?:vou|vo|t[oô]\s+(?:indo|saindo|descendo|voltando|me\s+trocando)|j[aá]\s+vou|partiu|bora|desisti|"
    r"n[aã]o\s+vou\s+mais|embora|me\s+trocar|t[aá]\s+bom|t[aá]\s+certo|fechou|topo|topei|ok\s+ok|beleza|"
    # 27/09 (agenda viva): outros dias, rolês, aula
    r"amanh[aã]|s[aá]bado|domingo|segunda|ter[cç]a|quarta|quinta|sexta|faltar|matar\s+aula|desmarc\w*|"
    r"remarc\w*|cancel\w*|marquei|combinei|furar|furei)\b",
    re.IGNORECASE)
# combinado de uber com o Patrick (27/09): ele pede, ela topa
UBER_PEDIDO_RE = re.compile(r"\buber\b|\bn[aã]o\s+(?:quero|vai)\s+(?:(?:que\s+)?(?:voc[eê]|vc)\s+)?(?:andando|ir|voltar)\s+a\s+p[eé]",
                            re.IGNORECASE)
TOPOU_RE = re.compile(r"\b(?:pode\s+deixar|t[aá]\s+bom|t[aá]\s+certo|combinado|fechado|fechou|beleza|prometo|"
                      r"ok|vou\s+de\s+uber|volto\s+de\s+uber|vou\s+sim|pode\s+ficar\s+tranquilo|"
                      # soak, dia 4 (02/10, 19:44): "Quer que eu pague um Uber?" → "Quero sim, melhor ir de Uber"
                      r"quero(?:\s+sim)?|aceito|melhor\s+(?:ir|voltar)\s+de\s+uber|vou\s+usar)\b", re.IGNORECASE)
RECUSA_RE = re.compile(r"\bn[aã]o\s+precisa\b|\bexagero\b|\bvou\s+a\s+p[eé]\s+(?:sim|mesmo)\b|"
                       r"\b(?:prefiro|quero)\s+(?:ir\s+)?a\s+p[eé]\b|"
                       r"\bn[aã]o\s+(?:quero|vou)\s+(?:ir\s+|pegar\s+)?(?:de\s+)?uber\b", re.IGNORECASE)
IDA_E_VOLTA_RE = re.compile(r"\b(?:vai\s+e\s+volta|ida\s+e\s+volta|indo\s+e\s+voltando|vou\s+e\s+volto)\b",
                            re.IGNORECASE)
IDA_RE = re.compile(r"\b(?:vai|vou|ir|indo|a\s+ida)\s+de\s+uber\b|\bna\s+ida\b", re.IGNORECASE)
VOLTA_RE = re.compile(r"\b(?:volt\w*)\b|\bna\s+volta\b", re.IGNORECASE)
COMBINADO_JANELA = timedelta(hours=12)
TIPOS_CONVERSA = ("academia", "milo", "cafe", "acai", "orla", "shopping", "praia", "mercado", "farmacia")


def _rng(salt: str) -> random.Random:
    return random.Random(f"marina-reativa:{salt}")


class AgendaReativa:
    def __init__(self, db):
        self.db = db

    # ----------------------------------------------------------- estado --
    def _state(self) -> dict:
        try:
            raw = self.db.get_estado_relacional(KEY)
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    def _save(self, st: dict, now: datetime) -> None:
        corte = (now - timedelta(days=2)).isoformat()
        st["interrupcoes"] = {k: v for k, v in st.get("interrupcoes", {}).items() if v["at"] >= corte}
        st["pausas"] = [p for p in st.get("pausas", []) if p["fim"] >= corte]
        st["voltas"] = {k: v for k, v in st.get("voltas", {}).items() if v.get("at", "") >= corte}
        self.db.set_estado_relacional(KEY, json.dumps(st, ensure_ascii=False))

    def interrupcao(self, chave: str) -> Optional[dict]:
        """Como o compromisso `chave` (key da agenda) terminou mais cedo, se terminou."""
        return self._state().get("interrupcoes", {}).get(chave)

    def pausa(self, now: datetime) -> Optional[dict]:
        for p in self._state().get("pausas", []):
            if p["inicio"] <= now.isoformat() < p["fim"]:
                return p
        return None

    def pausas_de(self, chave: str) -> list[dict]:
        return [p for p in self._state().get("pausas", []) if p.get("chave") == chave]

    def volta_trocada(self, leg_key: str) -> Optional[dict]:
        """A volta que virou uber porque ela saiu mal ({mode, mins})."""
        return self._state().get("voltas", {}).get(leg_key)

    @staticmethod
    def motivo_curto(info: dict) -> str:
        if info["motivo"] in MOTIVO_CURTO:
            return MOTIVO_CURTO[info["motivo"]]
        t = (info.get("texto") or "Decidiu ir embora").strip().rstrip(".")
        return t[:1].upper() + t[1:]

    # ----------------------------------------------------------- agenda --
    def _atual(self, now: datetime):
        """O compromisso em que ela está agora (etapa "lá") e o dict da agenda."""
        from agenda import Agenda
        ag = Agenda(self.db)
        for day in (now.date(), now.date() - timedelta(days=1)):
            for c in ag._compromissos(day):
                fim = c["volta"].start if c.get("volta") else c["fim"]
                # Soak, dia 2 (30/09, 11:36): a escova era 11:22, mas a saída atrasou (ida 11:45–11:55) e ela
                # ainda estava em casa — "saiu mais cedo da Ophicina", uber de volta e escova cobrados. Só está
                # "lá" quem chegou.
                chegada = c["ida"].end if c.get("ida") else c["inicio"]
                if max(c["inicio"], chegada) <= now < fim:
                    return c
        return None

    def _registra(self, key: str, at: datetime, summary: str, *, importance: float = 0.3,
                  share: float = 0.5) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'routine','agenda reativa',?,'simulated',1,?,?,?,?)""",
                (key, at.isoformat(), summary, importance, json.dumps(["marina"]), share, at.isoformat()))
            conn.commit()

    # ------------------------------------------------------ interromper --
    def interromper(self, now: datetime, motivo: str, *, texto: str = "", c: Optional[dict] = None) -> Optional[dict]:
        """Encerra o compromisso de agora mais cedo: a volta sai do novo fim."""
        c = c or self._atual(now)
        if not c or self.interrupcao(c["key"]):
            return None
        texto = texto or MOTIVOS.get(motivo, ("",))[0]
        sai = now + timedelta(minutes=MOTIVOS.get(motivo, ("", 5))[1])
        if sai >= c["fim"] - timedelta(minutes=5):
            return None                                   # já ia acabar mesmo
        if not self._encurta(c, sai):
            return None
        from agenda import CURTO
        from vontade import no
        onde = CURTO.get(c["place"]) or no(self._nome(c["place"]))
        info = {"at": now.isoformat(), "sai": sai.isoformat(), "motivo": motivo, "texto": texto,
                "fim_original": c["fim"].isoformat(), "tipo": c["tipo"]}
        st = self._state()
        st.setdefault("interrupcoes", {})[c["key"]] = info
        uber = self._uber_na_volta(c, motivo, now, onde, st)
        if uber:
            info["uber"] = uber
        self._save(st, now)
        self._registra(f"interrupcao:{c['key']}", now,
                       f"Saiu mais cedo {onde} às {now:%H:%M}" + (f": {texto}" if texto else "")
                       + (f". Voltou de uber (R$ {uber['valor']}) e avisou o Patrick." if uber else "."))
        logger.info("agenda_reativa.interrompeu key=%s motivo=%s sai=%s", c["key"], motivo, sai.strftime("%H:%M"))
        return info

    def _uber_na_volta(self, c: dict, motivo: str, now: datetime, onde: str, st: dict) -> Optional[dict]:
        """Mal, com banheiro ou exausta ela não volta a pé nem de ônibus: uber, e avisa o Patrick
        (se ele mandar o pix, o uber sai do dinheiro dele)."""
        volta = c.get("volta")
        if motivo not in UBER_MOTIVOS or not volta:
            return None
        from commute import ROUTES
        from consumo import uber_price
        rota = ROUTES.get(volta.region) or {}
        mins = volta.end - volta.start
        mins = (int(mins.total_seconds() // 60) if volta.mode in ("uber", "uber_dividido")
                else rota.get("uber") or max(5, round(mins.total_seconds() / 60 / 2)))
        valor = uber_price(mins)
        st.setdefault("voltas", {})[volta.key] = {"mode": "uber", "mins": mins, "at": now.isoformat()}
        st["aviso"] = {"at": now.isoformat(), "motivo": motivo, "onde": onde, "valor": valor, "enviado": False}
        st["uber_pix"] = {"valor": valor, "ate": (now + UBER_PIX_JANELA).isoformat(), "onde": onde}
        return {"mins": mins, "valor": valor}

    def aviso_saida(self, now: datetime) -> Optional[dict]:
        """Ela saiu mal e ainda não avisou o Patrick (iniciativa dela)."""
        a = self._state().get("aviso")
        if not a or a.get("enviado") or now - datetime.fromisoformat(a["at"]) > timedelta(hours=1):
            return None
        return a

    def marca_aviso_enviado(self, now: datetime) -> None:
        st = self._state()
        if st.get("aviso"):
            st["aviso"]["enviado"] = True
            self._save(st, now)

    def uber_pix(self, now: datetime, *, consumir: bool = False) -> Optional[dict]:
        """O uber que o Patrick ficou de pagar (ela saiu mal e avisou), se ainda vale."""
        st = self._state()
        u = st.get("uber_pix")
        if not u or now.isoformat() > u["ate"]:
            return None
        if consumir:
            st.pop("uber_pix", None)
            self._save(st, now)
        return u

    def combinar_uber(self, fala: str, msg_dele: str, now: datetime) -> list[str]:
        """27/09 (volta do Quartinho): ele pediu "vai e volta de uber", ela prometeu e a ida saiu a pé.
        Se ele pede uber e ela topa, os próximos trechos da saída (ida, volta ou os dois) viram uber.
        Devolve as chaves dos trechos trocados."""
        if not UBER_PEDIDO_RE.search(msg_dele or "") or not TOPOU_RE.search(fala or "") \
                or RECUSA_RE.search(fala or ""):
            return []
        texto = f"{msg_dele} {fala}"
        if IDA_E_VOLTA_RE.search(texto) or not (VOLTA_RE.search(texto) or IDA_RE.search(texto)):
            direcoes = ("ida", "volta")
        else:
            direcoes = tuple(d for d, rx in (("ida", IDA_RE), ("volta", VOLTA_RE)) if rx.search(texto))
        from commute import ROUTES, Commute
        c = Commute(self.db)
        legs = [leg for day in (now.date(), now.date() + timedelta(days=1)) for leg in c.legs_on(day)
                if leg.start > now and leg.start - now <= COMBINADO_JANELA]
        if not legs:
            return []
        saida = min(legs, key=lambda leg: leg.start).key.rsplit(":", 1)[0]   # a próxima saída, ida e volta
        st = self._state()
        trocados = []
        for leg in legs:
            if (leg.key.rsplit(":", 1)[0] != saida or leg.direction not in direcoes
                    or leg.mode in ("uber", "uber_dividido", "carona")):
                continue
            atual = int((leg.end - leg.start).total_seconds() // 60)
            mins = (ROUTES.get(leg.region) or {}).get("uber") or max(5, round(atual / 2))
            st.setdefault("voltas", {})[leg.key] = {"mode": "uber", "mins": mins, "at": now.isoformat(),
                                                    "combinado": True}
            trocados.append(leg.key)
        if trocados:
            self._save(st, now)
            logger.info("agenda_reativa.uber_combinado trechos=%s", ",".join(trocados))
        return trocados

    def _nome(self, place: str) -> str:
        from agenda import Agenda
        return Agenda(self.db)._place(place)["name"]

    def _encurta(self, c: dict, sai: datetime) -> bool:
        key = c["key"]
        if key.startswith(("gym:", "milo:")):
            from academia import Academia, PasseioMilo
            p = Academia(self.db) if key.startswith("gym:") else PasseioMilo(self.db)
            st = p._load()
            dia = key.split(":", 1)[1]
            if not st.get(dia):
                return False
            st[dia] = {**st[dia], "fim": sai.isoformat(), "fim_original": st[dia]["fim"]}
            self.db.set_estado_relacional(p.key, json.dumps(st))
            return True
        if key.startswith("puc:"):
            return self._sai_da_aula(c, sai)
        with self.db.get_connection() as conn:            # vontade, mercado, médico, rolê, freela
            row = conn.execute("SELECT id, metadata_json FROM eventos_pendentes WHERE source_key=?", (key,)).fetchone()
            if not row:
                return False
            meta = json.loads(row["metadata_json"] or "{}") or {}
            meta.setdefault("fim_original", c["fim"].isoformat())
            conn.execute("UPDATE eventos_pendentes SET end_at=?, metadata_json=? WHERE id=?",
                         (sai.isoformat(), json.dumps(meta, ensure_ascii=False, sort_keys=True), row["id"]))
            conn.commit()
        return True

    def _sai_da_aula(self, c: dict, sai: datetime) -> bool:
        """A aula de agora acaba na saída dela; as seguintes do dia caem (falta)."""
        from academic_life import AcademicLife
        life = AcademicLife(self.db)
        mexeu = False
        for b in c["blocks"]:
            ini, fim = datetime.fromisoformat(b["start_at"]), datetime.fromisoformat(b["end_at"])
            if fim <= sai:
                continue
            try:
                life.cancel_class_occurrence(b["id"], ini.date(), source_key=f"saiu_cedo:{b['id']}:{ini.date()}",
                                             ate=sai if ini < sai else None)
            except ValueError:
                continue
            mexeu = True
        return mexeu

    # ------------------------------------------------------------ pausa --
    def pausar(self, now: datetime, motivo: str, *, c: Optional[dict] = None, chama_ele: bool = False,
               texto: str = "", minutos: Optional[int] = None) -> Optional[dict]:
        """Se tranca num lugar reservado por ali (tesão, banheiro ou, com o Lovense, colocar/tirar o brinquedo:
        `texto` diz o que ela faz lá, `minutos` quanto demora) e volta pro que fazia."""
        c = c or self._atual(now)
        if not c or c["tipo"] in SEM_PAUSA or self.pausa(now):
            return None
        rng = _rng(f"pausa:{c['key']}:{now:%H%M}")
        onde = RESERVADO.get(c["tipo"], "no banheiro")
        fim = now + timedelta(minutes=minutos or (rng.randint(8, 15) if motivo == "tesao" else rng.randint(5, 10)))
        if fim >= (c["volta"].start if c.get("volta") else c["fim"]):
            return None
        if motivo == "tesao":
            atividade = f"trancada {onde}, se tocando" + (" e chamando o Patrick pro sexting" if chama_ele else "")
        elif motivo == "lovense":
            atividade = f"trancada {onde}, {texto or 'mexendo no brinquedo escondida'}"
        else:
            atividade = f"trancada {onde}, passando mal"
        p = {"inicio": now.isoformat(), "fim": fim.isoformat(), "chave": c["key"], "place": c["place"],
             "onde": onde, "motivo": motivo, "atividade": atividade, "chama_ele": chama_ele}
        st = self._state()
        st.setdefault("pausas", []).append(p)
        self._save(st, now)
        if motivo == "tesao":
            self._alivio(now, fim, onde, chama_ele, key=f"pausa:{c['key']}:{now:%H%M}")
        elif motivo == "lovense":
            self._registra(f"pausa:{c['key']}:{now:%H%M}", now,
                           f"Foi {onde} uns minutos, {texto or 'mexer no brinquedo escondida'}.", share=0.3)
        else:
            self._registra(f"pausa:{c['key']}:{now:%H%M}", now,
                           f"Teve uma emergência de banheiro e ficou {onde} uns minutos.", share=0.3)
        logger.info("agenda_reativa.pausa key=%s motivo=%s chama=%s", c["key"], motivo, chama_ele)
        return p

    def _alivio(self, inicio: datetime, fim: datetime, onde: str, chama_ele: bool, *, key: str) -> None:
        """Vale no corpo como a masturbação em casa (gozo, alívio); chamando ele, vira convite."""
        from emotion import EmotionEngine, RELEASE_KEY, SOLO_TELL_CHANCE
        from tempo_livre import CONVITE_KEY
        tells = chama_ele or _rng(f"conta:{key}").random() < SOLO_TELL_CHANCE
        if chama_ele:
            summary = f"Bateu um tesão que não dava pra segurar: se trancou {onde}, se tocou e chamou o Patrick (sexting)."
            self.db.set_estado_relacional(CONVITE_KEY, json.dumps(
                {"key": key, "inicio": inicio.isoformat(), "fim": fim.isoformat(), "enviado": False,
                 "onde": onde}, ensure_ascii=False))
        else:
            summary = (f"Bateu um tesão que não dava pra segurar: se trancou {onde} e se tocou pensando no Patrick."
                       + (" Pode contar pra ele, do jeito dela, se vier a calhar." if tells
                          else " Guardou só pra ela: não conta pro Patrick."))
        self._registra(key, inicio, summary, importance=0.2, share=0.6 if tells else 0.0)
        if not tells:
            try:
                from social_day import SocialDay
                SocialDay(self.db).mark_shared(key)
            except Exception:
                pass
        gozo = inicio + (fim - inicio) * 0.8
        self.db.set_estado_relacional(RELEASE_KEY, gozo.isoformat())
        EmotionEngine(self.db).feel("alegria", "alivio", 0.3, "se aliviou fora de casa", gozo, source_key=f"{key}:alivio")

    def marcar_alivio_em_casa(self, chega: datetime, now: datetime, *, chama_ele: bool = False) -> None:
        """O primeiro bloco em casa a partir de `chega` é a masturbação (ela disse que ia se tocar)."""
        st = self._state()
        st["alivio_em_casa"] = {"chega": chega.isoformat(), "chama_ele": chama_ele}
        self._save(st, now)

    def alivio_em_casa(self, now: datetime, *, consumir: bool = True) -> Optional[bool]:
        """Voltou correndo pra casa por tesão: o primeiro bloco em casa é a masturbação.
        None: nada pendente. False/True: sozinha / chamando ele."""
        st = self._state()
        pend = st.get("alivio_em_casa")
        if not pend or now.isoformat() < pend["chega"]:
            return None
        if now - datetime.fromisoformat(pend["chega"]) > timedelta(hours=1):
            st.pop("alivio_em_casa", None)
            self._save(st, now)
            return None
        if consumir:
            st.pop("alivio_em_casa", None)
            self._save(st, now)
        return bool(pend.get("chama_ele"))

    # ------------------------------------------------ interrupção sozinha --
    def talvez(self, now: datetime) -> Optional[dict]:
        """Chamado pelo mundo: no meio de um compromisso, às vezes surge motivo pra sair (ou se trancar)."""
        with self.db.get_connection() as conn:
            if not conn.execute("SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done'").fetchone():
                return None
        slot = (now.hour * 60 + now.minute) // SLOT_MIN
        rng = _rng(f"{now.date().isoformat()}:{slot}")
        sorteio = rng.random()
        if sorteio >= 0.45:                               # barato primeiro: quase sempre para aqui
            return None
        if self.pausa(now):
            return None
        c = self._atual(now)
        if not c or self.interrupcao(c["key"]):
            return None
        fim = c["volta"].start if c.get("volta") else c["fim"]
        if (now - c["inicio"]) < (fim - c["inicio"]) * MIN_PASSADO or fim - now < timedelta(minutes=15):
            return None
        chances = self._chances(c, now)
        acc = 0.0
        for motivo, p in chances.items():
            acc += p
            if sorteio < acc:
                return self._acontece(motivo, c, now, rng)
        return None

    def _chances(self, c: dict, now: datetime) -> dict:
        """Chance por janela de 20 min de cada motivo, pelo corpo e pelo humor dela agora."""
        try:
            from emotion import EmotionEngine, SOLO_MIN_LIBIDO
            f = EmotionEngine(self.db).feeling(now)
        except Exception:
            return {}
        out = {}
        if f.discomfort >= 0.35:
            out["passando_mal"] = min(0.3, 0.5 * (f.discomfort - 0.25))
        if self._virose(now):
            out["banheiro"] = 0.12
        cabe = lambda m: MOTIVOS[m][2] is None or c["tipo"] in MOTIVOS[m][2]   # noqa: E731
        if f.energy < 0.3 and cabe("cansou"):
            out["cansou"] = 0.1 + 0.3 * (0.3 - f.energy)
        if c["tipo"] in ("noite", "encontro", "jogo"):
            if f.social_battery < 0.2:
                out["sem_bateria"] = 0.12
            elif f.valence < 0.4:
                out["role_chato"] = 0.05
        if cabe("tedio") and any(e.family == "tedio" for e in f.episodes):
            out["tedio"] = 0.05
        elif cabe("tedio"):
            out["tedio"] = 0.012                          # às vezes, mesmo leve (Patrick, 26/09)
        if f.libido >= SOLO_MIN_LIBIDO + 0.2 and f.excitation < 0.45:
            out["tesao"] = min(0.1, 0.25 * (f.libido - SOLO_MIN_LIBIDO - 0.1))
        return {m: out[m] for m in sorted(out, key=lambda m: m == "tedio")}   # tédio por último

    def _acontece(self, motivo: str, c: dict, now: datetime, rng: random.Random) -> Optional[dict]:
        if motivo == "banheiro" and c["tipo"] not in SEM_PAUSA and rng.random() < 0.6:
            return self.pausar(now, "banheiro", c=c)
        if motivo == "tesao":
            chama = self._quer_ele(now) and rng.random() < 0.4
            if c["tipo"] not in SEM_PAUSA and rng.random() < 0.5:
                return self.pausar(now, "tesao", c=c, chama_ele=chama)
            info = self.interromper(now, "tesao", c=c)
            if info:
                self._marca_alivio(c, info, chama, now)
            return info
        return self.interromper(now, motivo, c=c)

    def _marca_alivio(self, c: dict, info: dict, chama: bool, now: datetime) -> None:
        from agenda import Agenda
        chega = datetime.fromisoformat(info["sai"])
        for e in Agenda(self.db).etapas(c["inicio"].date(), now):
            if e.tipo == "voltando" and e.inicio >= chega - timedelta(minutes=1):
                chega = e.fim
                break
        st = self._state()
        st["alivio_em_casa"] = {"chega": chega.isoformat(), "chama_ele": chama}
        self._save(st, now)

    def _quer_ele(self, now: datetime) -> bool:
        try:
            from emotion import EmotionEngine
            f = EmotionEngine(self.db).feeling(now)
            return f.missing >= 0.35 or f.bond.get("romantic_intensity", 0) >= 0.85
        except Exception:
            return False

    def _virose(self, now: datetime) -> bool:
        try:
            from health import Health
            cur = Health(self.db).illness(now.date())
            return bool(cur and cur[0] == "virose")
        except Exception:
            return False


    # ------------------------------------------------------- conversa --
    def observe_conversa(self, fala: str, msg_dele: str, now: datetime, *, llm=None) -> Optional[dict]:
        """Depois que a fala dela saiu: o que ela topou/anunciou/desistiu vira agenda de verdade."""
        if not fala or not PLANO_RE.search(fala):
            return None
        decisao = self._classifica(fala, msg_dele, now, llm=llm)
        if not decisao:
            return None
        try:
            from world_state import _RESOLVE_LOCK
            with _RESOLVE_LOCK:                           # o mundo não resolve no meio da mudança
                return self._aplica(decisao, now)
        except Exception:
            logger.exception("agenda_reativa.aplica")
            return None

    def _aplica(self, decisao: dict, now: datetime) -> Optional[dict]:
        acao, tipo = decisao.get("acao"), decisao.get("tipo")
        motivo = (decisao.get("motivo") or "").strip()[:80]
        if acao == "vai_embora":
            c = self._atual(now)
            return self.interromper(now, "conversa", texto=motivo or "resolveu ir embora", c=c) if c else None
        # 27/09 (agenda viva): a conversa mexe em qualquer item dos próximos dias (rolê, convite, aula…)
        item = self._item(decisao.get("item"))
        if item is not None:
            from agenda_viva import AgendaViva
            return AgendaViva(self.db).pela_conversa(item, acao, self._quando(decisao.get("quando"), now), motivo, now)
        if acao == "desistiu" and tipo == "aula":
            from agenda_viva import AgendaViva
            aula = next((i for i in self._lista if i["tipo"] == "aula"), None)
            return AgendaViva(self.db).pela_conversa(aula, acao, now, motivo, now) if aula else None
        if tipo not in TIPOS_CONVERSA:
            return None
        if acao == "desistiu":
            return self._desiste(tipo, now, motivo)
        if acao == "vai_fazer":
            quando = self._quando(decisao.get("quando"), now)
            if quando.date() > now.date():
                from agenda_viva import AgendaViva
                return AgendaViva(self.db).marca_outro_dia(tipo, quando, motivo, now)
            return self._vai(tipo, quando, now, motivo)
        return None

    _lista: list = []

    def _item(self, n) -> Optional[dict]:
        try:
            n = int(n)
        except (TypeError, ValueError):
            return None
        return self._lista[n - 1] if 1 <= n <= len(self._lista) else None

    DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")

    @classmethod
    def _quando(cls, valor, now: datetime) -> datetime:
        """"agora", "HH:MM", "amanhã HH:MM", "sábado HH:MM" ou "AAAA-MM-DD HH:MM"."""
        if not isinstance(valor, str):
            return now
        v = valor.strip().casefold().replace("amanha", "amanhã").replace("sabado", "sábado").replace("terca", "terça")
        dia = now.date()
        m = re.match(r"(\d{4}-\d{2}-\d{2})\s*", v)
        if m:
            try:
                dia = date.fromisoformat(m.group(1))
            except ValueError:
                return now
            v = v[m.end():]
        elif v.startswith("amanhã"):
            dia, v = dia + timedelta(days=1), v[len("amanhã"):].strip()
        else:
            for i, nome in enumerate(cls.DIAS):
                if v.startswith(nome):
                    dia = dia + timedelta(days=(i - dia.weekday()) % 7 or 7)
                    v = v[len(nome):].strip()
                    break
        m = re.fullmatch(r"(?:às\s*)?(\d{1,2})(?::|h)?(\d{2})?", v.strip())
        if m:
            h, mi = int(m.group(1)), int(m.group(2) or 0)
            if 0 <= h < 24 and 0 <= mi < 60:
                at = datetime.combine(dia, time(h, mi))
                if at > now:
                    return at
        elif dia != now.date():
            return datetime.combine(dia, now.time().replace(second=0, microsecond=0))
        return now

    def _classifica(self, fala: str, msg_dele: str, now: datetime, *, llm=None) -> Optional[dict]:
        from config import settings
        agora = "livre em casa"
        try:
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT activity FROM world_state ORDER BY id DESC LIMIT 1").fetchone()
            agora = (row["activity"] if row else "") or agora
        except Exception:
            pass
        # 27/09 (agenda viva): a lista do que vem nos próximos 3 dias, pra conversa mexer em qualquer item
        self._lista = []
        try:
            from agenda_viva import AgendaViva
            self._lista = AgendaViva(self.db).lista_para_conversa(now)
        except Exception:
            logger.exception("agenda_reativa.lista")
        dias = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
        agenda = "\n".join(
            f"{n}. {i['texto']} — {('hoje' if i['inicio'].date() == now.date() else 'amanhã' if (i['inicio'].date() - now.date()).days == 1 else dias[i['inicio'].weekday()])} {i['inicio']:%H:%M}"
            + (" (convite ainda sem resposta)" if i["tipo"] == "convite" else "")
            for n, i in enumerate(self._lista, 1)) or "(nada marcado)"
        prompt = (
            "Você lê um trecho de conversa entre a Marina e o namorado (Patrick) e diz se a Marina DECIDIU AGORA "
            "mexer na agenda dela: fazer alguma coisa fora de casa (hoje ou outro dia), desistir ou remarcar algo "
            "que estava marcado, aceitar um convite, faltar aula, ou ir embora de onde está.\n"
            f"Hoje é {dias[now.weekday()]}, {now:%Y-%m-%d}, {now:%H:%M}. O que ela está fazendo: {agora}.\n"
            f"Agenda dela (próximos dias):\n{agenda}\n\n"
            f"Patrick: \"{(msg_dele or '')[:400]}\"\nMarina: \"{fala[:400]}\"\n\n"
            "Responda só JSON: {\"acao\": \"vai_fazer\"|\"desistiu\"|\"remarcou\"|\"vai_embora\"|\"nenhuma\", "
            "\"item\": número da agenda acima ou null, "
            "\"tipo\": \"academia\"|\"milo\"|\"cafe\"|\"acai\"|\"orla\"|\"shopping\"|\"praia\"|\"mercado\"|\"farmacia\"|\"aula\"|null, "
            "\"quando\": \"agora\"|\"HH:MM\"|\"amanhã HH:MM\"|\"<dia da semana> HH:MM\"|null, "
            "\"motivo\": \"frase curta em 3ª pessoa\"}.\n"
            "Regras: só vale decisão de verdade (\"tá bom, vou\", \"vou descer com o Milo\", \"desmarquei com a "
            "Bia\", \"amanhã vou na academia às 7\"); hipótese, pergunta, brincadeira ou \"talvez\" é nenhuma. Se a "
            "decisão é sobre algo da agenda, use o item (desistiu = não vai mais; remarcou = mesma coisa em outro "
            "horário, com quando; vai_fazer num convite sem resposta = aceitou; desistiu num convite = recusou). "
            "Faltar/matar aula = desistiu com tipo aula. Coisa nova fora da agenda: item null, com tipo e quando. "
            "Passear/descer com o cachorro = milo; treinar = academia; sorvete = acai; caminhar = orla. vai_embora "
            "é ela saindo de onde está AGORA (\"vou embora\", \"tô indo pra casa\"). Resposta curta dela a uma "
            "pergunta ou convite dele vale: o assunto vem da mensagem dele (\"vai pra academia hoje?\" → \"vou às "
            "18h\" é vai_fazer academia 18:00). motivo = POR QUE ela decidiu (\"o Patrick convenceu\", \"tava "
            "cansada\"), vazio se não disse."
        )
        try:
            if llm is None:
                from openai import OpenAI
                llm = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
            model = getattr(settings, "AGENDA_LLM_MODEL", "") or settings.LLM_FALLBACK_MODEL
            from llm_options import llm_kwargs
            resp = llm.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}],
                                               temperature=0, response_format={"type": "json_object"},
                                               **llm_kwargs(150, model))
            raw = (resp.choices[0].message.content or "").strip()
            if "{" not in raw:
                # Soak, dia 1 (29/09, 21:59): o modelo devolveu vazio — é "nenhuma", não traceback no relatório.
                logger.warning("agenda_reativa.classifica_vazio")
                return None
            data = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        except json.JSONDecodeError:
            # Soak, dia 2 (30/09, 13:08): JSON cortado no meio — também é "nenhuma", aviso e não traceback.
            logger.warning("agenda_reativa.classifica_json_quebrado raw=%r", raw[:120])
            return None
        except Exception:
            logger.exception("agenda_reativa.classifica")
            return None
        logger.info("agenda_reativa.classificou acao=%s item=%s tipo=%s quando=%s", data.get("acao"), data.get("item"),
                    data.get("tipo"), data.get("quando"))
        return data if data.get("acao") in ("vai_fazer", "desistiu", "remarcou", "vai_embora") else None

    def _vai(self, tipo: str, quando: datetime, now: datetime, motivo: str) -> Optional[dict]:
        from vontade import PREP_MIN, SAIDAS, Vontade
        if self._atual(now):
            return None                                   # está no meio de outra coisa
        planejada = self._planejada(tipo, now)
        if planejada:
            return self._remarca(planejada, tipo, quando, now, motivo)
        v = Vontade(self.db)
        rng = _rng(f"conversa:{now.isoformat(timespec='minutes')}")
        s = SAIDAS[tipo]
        prep = rng.randint(*PREP_MIN[tipo])
        saida = max(quando, now + timedelta(minutes=prep))
        texto, extra, lugar, ida = s["texto"], {"motivo": motivo or "combinou com o Patrick"}, None, s.get("ida", 10)
        if "categorias" in s:
            from vontade import _catalogo, no
            lojas = [l for l in _catalogo() if l.get("categoria") in s["categorias"] and l.get("area", "bf") == "bf"
                     and (l.get("abre") or 0) <= saida.hour < (l.get("fecha") or 24) - 1]
            if not lojas:
                return None
            l = min(lojas, key=lambda x: float(x.get("km") or 9))
            lugar = v._lugar_loja(l)
            texto = texto.format(no=no(l["nome"]), coisa={"Açaí": "um açaí", "Sorvetes": "um sorvete"}.get(
                l.get("categoria"), "alguma coisa"))
            ida = max(3, round(float(l.get("km") or 0.3) * 12) + 2)
            extra["loja"] = l["id"]
        else:
            lugar = s["lugar"]
        inicio = saida + timedelta(minutes=ida)
        fim = inicio + timedelta(minutes=rng.randint(*s["mins"]))
        chave = f"vontade:{now.date().isoformat()}:c{now:%H%M}"
        cid = v.agendar(tipo, lugar, inicio, fim, texto, origem="conversa", decidido_em=now, chave=chave,
                        modo=s.get("modo", "a_pe"), ida_min=ida, extra=extra)
        if not cid:
            return None
        self._registra(f"{chave}:decidiu", now, self._narra(self._sair(tipo, lugar), saida, now, motivo))
        logger.info("agenda_reativa.conversa tipo=%s inicio=%s", tipo, inicio.strftime("%H:%M"))
        return {"tipo": tipo, "inicio": inicio.isoformat(), "chave": chave}

    def _sair(self, tipo: str, lugar: str) -> str:
        """Texto de saída, como o "Vai sair pro Starbucks" do card (Patrick, 26/09: é uma saída; o lugar
        é o destino): "sair pro Starbucks", "sair com o Milo pra Enseada"."""
        from agenda import CURTO, Agenda
        from commute import _pra
        curto = CURTO.get(lugar)                          # "na academia" → "pra academia"
        pra = (("pra " if curto.startswith("na ") else "pro ") + curto.split(" ", 1)[1] if curto
               else _pra(Agenda(self.db)._place(lugar)["name"]))
        return "sair" + (" com o Milo" if tipo == "milo" else "") + " " + pra

    @staticmethod
    def _narra(sair: str, saida: datetime, now: datetime, motivo: str) -> str:
        """Acontecimento narrado, com o Patrick (decisão dele, 26/09)."""
        convenceu = "convenc" in (motivo or "").casefold()
        saiu = "saiu" + sair[len("sair"):]
        if saida - now <= timedelta(minutes=30):
            base = f"O Patrick convenceu e ela {saiu}" if convenceu else f"Combinou com o Patrick e {saiu}"
        else:
            base = (f"O Patrick convenceu e ela combinou de {sair} às {saida:%H:%M}" if convenceu
                    else f"Combinou com o Patrick de {sair} às {saida:%H:%M}")
        extra = "" if convenceu or not motivo else f": {motivo[:1].lower() + motivo[1:].rstrip('.')}"
        return base + extra + "."

    def _planejada(self, tipo: str, now: datetime):
        if tipo not in ("academia", "milo"):
            return None
        from academia import Academia, PasseioMilo
        p = (Academia if tipo == "academia" else PasseioMilo)(self.db)
        plano = p.plano(now.date(), now)
        if plano and plano["onde"] == "rua" and plano["inicio"] - timedelta(minutes=p.ida_min + 20) > now:
            return p                                      # ainda não começou a se arrumar
        return None

    def _remarca(self, p, tipo: str, quando: datetime, now: datetime, motivo: str) -> Optional[dict]:
        from vontade import PREP_MIN
        st = p._load()
        dia = now.date().isoformat()
        plano = st[dia]
        ini, fim = datetime.fromisoformat(plano["inicio"]), datetime.fromisoformat(plano["fim"])
        prep = _rng(f"adianta:{dia}:{tipo}").randint(*PREP_MIN[tipo])
        ja = quando <= now + timedelta(minutes=prep)
        novo = max(quando, now + timedelta(minutes=prep)) + timedelta(minutes=p.ida_min)
        if abs(novo - ini) < timedelta(minutes=10):
            return None                                   # já era mais ou menos essa hora
        plano = {k: v for k, v in plano.items() if k != "decidido_em"}
        st[dia] = {**plano, "inicio": novo.isoformat(), "fim": (novo + (fim - ini)).isoformat(), "origem": "conversa",
                   **({"decidido_em": now.isoformat(timespec="minutes")} if ja else {})}
        self.db.set_estado_relacional(p.key, json.dumps(st))
        saida = novo - timedelta(minutes=p.ida_min)
        self._registra(f"remarcou:{tipo}:{dia}:{now:%H%M}", now,
                       self._narra(self._sair(tipo, LUGAR_PLANEJADO[tipo]), saida, now, motivo))
        logger.info("agenda_reativa.remarcou tipo=%s inicio=%s", tipo, novo.strftime("%H:%M"))
        return {"tipo": tipo, "inicio": novo.isoformat(), "chave": f"{'gym' if tipo == 'academia' else 'milo'}:{dia}"}

    def _desiste(self, tipo: str, now: datetime, motivo: str) -> Optional[dict]:
        """Desistiu antes de sair: o item some da agenda (se já está lá, é vai_embora)."""
        dia = now.date().isoformat()
        if tipo in ("academia", "milo"):
            from academia import Academia, PasseioMilo
            p = (Academia if tipo == "academia" else PasseioMilo)(self.db)
            plano = p.plano(now.date(), now)
            if plano and plano["inicio"] - timedelta(minutes=p.ida_min) > now:
                st = p._load()
                st[dia] = None
                self.db.set_estado_relacional(p.key, json.dumps(st))
                self._registra(f"desistiu:{tipo}:{dia}", now,
                               f"Desistiu de {self._sair(tipo, LUGAR_PLANEJADO[tipo])} hoje"
                               + (f": {motivo.rstrip('.')}." if motivo else "."))
                return {"tipo": tipo, "cancelado": True}
        with self.db.get_connection() as conn:
            rows = [dict(r) for r in conn.execute(
                """SELECT id, source_key, event_at, location_key, metadata_json FROM eventos_pendentes WHERE source_key LIKE ?
                   AND status='pending' AND confirmed=1""", (f"vontade:{dia}:%",))]
        for r in rows:
            meta = json.loads(r["metadata_json"] or "{}") or {}
            ida = datetime.fromisoformat(r["event_at"]) - timedelta(minutes=int(meta.get("ida_min", 10)))
            if meta.get("tipo") == tipo and ida > now:
                from calendar_world import CalendarWorld
                CalendarWorld(self.db).cancel(r["id"])
                self._registra(f"desistiu:{r['source_key']}", now,
                               f"Desistiu de {self._sair(tipo, r['location_key'])}"
                               + (f": {motivo.rstrip('.')}." if motivo else "."))
                return {"tipo": tipo, "cancelado": True}
        return None


def classe_disponibilidade(atividade: str) -> Optional[str]:
    """Pausa num lugar reservado: celular depois (ou na mão, chamando ele)."""
    act = (atividade or "").casefold()
    if act.startswith("trancada "):
        return "HOME_RELAXING" if "chamando o patrick" in act else "SOLO"
    return None
