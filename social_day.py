"""Dia social da Marina (Auditoria #6).

Antes desta auditoria o mundo social era só cadastro: Bia, Theo, Júlia, Carol,
Helena, Dona Célia, o pai e a Lívia existiam com personalidade e bairro, mas
nenhuma interação acontecia (`social_evidence`, `life_events` e `story_threads`
com zero linhas). Se o Patrick perguntasse "falou com a Bia hoje?", o modelo
improvisava — e esquecia no dia seguinte.

Aqui o dia social é derivado da data e da agenda, do mesmo jeito que a
Auditoria #4 fez com academia e passeio:

- Quem ela encontra pessoalmente depende de onde ela ESTÁ: colegas e a
  professora na PUC em dia de aula, a Carol na Bodytech quando vai treinar, a
  Dona Célia no prédio na hora do passeio com o Milo.
- Quem fala com ela por mensagem ou ligação depende de quem a pessoa é: a Bia
  quase todo dia, o pai algumas vezes por semana, a Lívia de vez em quando.
- Cada contato vira `life_event` + `social_evidence` quando o horário passa
  (materialização preguiçosa no `WorldStateManager.resolve`), então fica
  registrado e é o mesmo amanhã.
- De vez em quando um contato traz um gancho (a Bia desabafou, a Helena deu
  retorno). Isso alimenta o StoryEngine, que já existia e nunca era chamado.
  A história nasce com a pessoa como participante, e dias depois um novo
  contato com ela continua ou resolve o assunto.

Nada aqui chama LLM ou rede. Detalhes finos (o que exatamente a Bia contou)
ficam para a voz da Marina; o sistema garante QUEM, QUANDO, ONDE e O ASSUNTO.
"""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

from db import DatabaseManager

logger = logging.getLogger("SocialDay")

# Nome curto, como a Marina chamaria.
SHORT_NAME = {
    "bia_andrade": "a Bia", "theo_martins": "o Theo", "julia_azevedo": "a Júlia",
    "carol_menezes": "a Carol", "helena_prado": "a professora Helena",
    "celia_ribeiro": "a Dona Célia", "henrique_salles": "o pai",
    "livia_vasconcelos": "a Lívia",
}

# Gente que ela pode conhecer onde a rotina já a leva (Auditoria #6, parte 3).
# Não são canônicos: nascem via SocialWorld.discover_person no primeiro
# encontro. Quem ela encontra em 3 dias vira `secondary`, em 6 `recurring` — e
# aí entra no cânone (pedido do Patrick: "tinham chance de se tornarem canon").
# Pesos 3/2/1: uma pessoa por lugar tende a virar "a da turma".
# (chave, nome, gênero, quem é, bairro, temas, amigo canônico ligado)
NPC_POOLS = {
    "puc": (
        ("npc_rafa_nogueira", "Rafael (Rafa) Nogueira", "m", "colega da turma de Projeto", "Gávea",
         ("trabalhos em grupo", "festas da PUC"), "theo_martins"),
        ("npc_duda_lins", "Maria Eduarda (Duda) Lins", "f", "colega de fotografia, amiga da Júlia", "Gávea",
         ("fotografia", "exposições"), "julia_azevedo"),
        ("npc_lara_pimentel", "Lara Pimentel", "f", "colega de Moda que senta perto dela", "Leblon",
         ("moda", "estágio"), None),
    ),
    "gym": (
        ("npc_bruno_tavares", "Bruno Tavares", "m", "personal da Bodytech que sempre puxa papo", "Botafogo",
         ("treino", "alimentação"), "carol_menezes"),
        ("npc_nanda_rocha", "Fernanda (Nanda) Rocha", "f", "colega da aula de funcional", "Botafogo",
         ("treino", "séries"), None),
    ),
    "walk": (
        ("npc_gabi_freitas", "Gabriela (Gabi) Freitas", "f", "tutora da spitz que brinca com o Milo", "Botafogo",
         ("cachorros", "o bairro"), None),
        ("npc_seu_ademir", "Seu Ademir", "m", "senhor que passeia com um golden na Enseada", "Botafogo",
         ("cachorros", "o tempo"), "celia_ribeiro"),
    ),
    "outing": (
        ("npc_caio_menezes", "Caio Menezes", "m", "amigo da Bia das festas", "Laranjeiras",
         ("festas", "música"), "bia_andrade"),
        ("npc_luana_prates", "Luana Prates", "f", "amiga do Theo que sempre aparece no Quartinho", "Glória",
         ("festas", "fofocas"), "theo_martins"),
    ),
}
NPC_INDEX = {row[0]: row for pool in NPC_POOLS.values() for row in pool}

# Fase D12 — laços. O pai (Henrique) liga quando está livre e manda mensagem
# quando está ocupado; checa a filha pelo menos 1×/dia e banca a comida dela.
DAD_MORNING_TOPICS = ("bom dia e se ela já tomou café", "se ela está comendo direito",
                      "o tempo no Rio e se ela vai precisar de guarda-chuva", "saudade dela",
                      "se ela chegou bem ontem")
DAD_CALL_TOPICS = ("como foi a faculdade", "se ela está comendo direito", "o Milo",
                   "as contas do apartamento", "saudade e quando ela vai visitar ele",
                   "o trabalho dele", "se ela está dormindo direito")
BIA_WINDOWS = ((time(9, 30), time(12, 0)), (time(12, 0), time(15, 0)),
               (time(15, 0), time(19, 0)), (time(19, 0), time(23, 30)))
BIA_WINDOWS_WEEKEND = ((time(10, 30), time(13, 0)), (time(13, 0), time(17, 0)),
                       (time(17, 0), time(20, 0)), (time(20, 0), time(23, 59)))
NPC_CHANCE = {"puc": 0.35, "gym": 0.25, "walk": 0.2, "outing": 0.45}
CANON_AFTER = "recurring"
# Lugares que ela pode descobrir nas saídas de sexta (ficção interna, sem
# endereço real): discovered → known → habitual → favorite pelo uso.
PLACE_POOL = (
    ("hamburgueria_voluntarios", "Hamburgueria na Voluntários da Pátria", "Botafogo", "restaurant"),
    ("barzinho_humaita", "Barzinho no Humaitá", "Humaitá", "bar"),
    ("acai_praia_botafogo", "Açaí na Praia de Botafogo", "Botafogo", "cafe"),
)
NEW_PLACE_CHANCE = 0.3


def short_name(character_key: str) -> str:
    if character_key in SHORT_NAME:
        return SHORT_NAME[character_key]
    npc = NPC_INDEX.get(character_key)
    if not npc:
        return character_key
    first = npc[1].split(" (")[1].rstrip(")") if " (" in npc[1] else npc[1].split()[0]
    if first.startswith("Seu ") or npc[1].startswith("Seu "):
        return "o " + npc[1]
    return ("o " if npc[2] == "m" else "a ") + first


# Gancho → seed do StoryEngine. O flag é a precondição que o StoryEngine exige
# (`required_context`) — antes nada no sistema fornecia nenhuma delas.
HOOKS = {
    "bia_andrade": [("friend_needs_support", "support_for_friend"),
                    ("plan_cancelled_observed", "friend_plan_cancelled"),
                    ("disagreement_observed", "small_disagreement"),
                    (None, "unexpected_invitation")],
    "theo_martins": [("favor_request_observed", "small_favor_requested"),
                     ("embarrassment_observed", "minor_embarrassment")],
    "julia_azevedo": [("favor_request_observed", "small_favor_requested"),
                      ("help_received_observed", "minor_help_received")],
    "helena_prado": [("academic_feedback_observed", "academic_feedback"),
                     ("feedback_observed", "positive_feedback")],
    "carol_menezes": [("help_received_observed", "minor_help_received")],
    "henrique_salles": [("father_contact_observed", "father_check_in")],
    "livia_vasconcelos": [("professional_feedback_observed", "professional_feedback"),
                          (None, "unexpected_work_opportunity")],
}
# Amigos entre si. Theo e Júlia: ambos ligados à PUC no cânone
# (social_place_links). Bia e Theo: PROPOSTA de cânone da Auditoria #6 — os dois
# gostam de festa e a Bia é a melhor amiga da Marina; o Patrick pode vetar.
FRIEND_TIES = {
    frozenset({"theo_martins", "julia_azevedo"}): "colegas de turma na PUC",
    frozenset({"bia_andrade", "theo_martins"}): "se conheceram nas festas por causa da Marina",
}
for _npc in NPC_INDEX.values():
    if _npc[6]:
        FRIEND_TIES[frozenset({_npc[0], _npc[6]})] = _npc[3]
GOSSIP_CHANCE = 0.3
# Assuntos que às vezes são contados em segredo — a Marina sabe, o Patrick não.
SECRET_TOPICS = {"relacionamentos", "crushes", "conflitos leves", "fofocas"}
SECRET_CHANCE = 0.35
SECRET_CATEGORY = {"relacionamentos": "relationship", "crushes": "relationship",
                   "conflitos leves": "friendship", "fofocas": "friendship"}

# Saídas (Auditoria #6): viram compromissos confirmados no CalendarWorld dias
# antes — ela sabe dos próprios planos, o WorldState a coloca no lugar, a
# disponibilidade fica SOCIAL e a bateria social gasta. (dia_da_semana, chance,
# início, fim, lugar, amigos possíveis, texto)
OUTINGS = (
    (4, 0.35, time(19, 30), time(22, 30), "quartinho_bar", ("theo_martins",), ("julia_azevedo",),
     "Saindo com {quem} no Quartinho Bar"),
    (2, 0.25, time(15, 30), time(16, 45), "starbucks_shopping_gavea", ("julia_azevedo",), (),
     "Café com {quem} no Starbucks do Shopping da Gávea"),
    (3, 0.25, time(15, 30), time(16, 45), "starbucks_shopping_gavea", ("julia_azevedo", "theo_martins"), (),
     "Café com {quem} no Starbucks do Shopping da Gávea"),
)
BEACHES = ("copacabana_beach", "ipanema_beach", "leblon_beach")
OUTING_HORIZON_DAYS = 6

# Fase D8 — fim de semana (Patrick, 23/09): "ela é jovem, de uma bolha social com
# boa condição; é normal receber convites dos amigos, mais ativos no fim de
# semana — mas a decisão é dela, e o emocional é o que conta". Fim de semana
# vira CONVITE: chega antes, e ela decide no dia pelo estado de agora.
WEEKEND_INVITES = (
    (5, 0.55, time(10, 0), time(13, 0), None, ("bia_andrade", "carol_menezes"), (), "Praia com {quem}"),
    (5, 0.75, time(21, 0), time(23, 59), "quartinho_bar", ("bia_andrade",), ("theo_martins",),
     "Saindo com {quem} no Quartinho Bar"),
    (6, 0.45, time(10, 0), time(13, 0), None, ("bia_andrade", "carol_menezes"), (), "Praia com {quem}"),
    (6, 0.40, time(15, 0), time(19, 0), "shopping_gavea", ("bia_andrade", "julia_azevedo"), (),
     "Cinema e shopping com {quem} no Shopping da Gávea"),
)
INVITES_KEY = "convites_json"
INVITE_BASE_YES = 0.65

HOOK_CHANCE = 0.70  # dia com gancho; o StoryEngine ainda aplica cadência e orçamento
CONTINUE_AFTER_DAYS = (1, 4)

# Plano do dia é função da data, da grade e das histórias abertas; recalcular a
# cada resolve custava ~80 ms de SQLite. Cache por processo.
_PLAN_CACHE: dict = {}


@dataclass(frozen=True)
class Contact:
    key: str
    at: datetime
    character_key: str
    channel: str                 # presencial | mensagem | ligação
    place_key: Optional[str]
    topic: str
    valence: float = 0.3
    requires: Optional[str] = None     # 'gym' | 'pet_walk' — confere o world state
    hook: Optional[tuple] = None       # (flag, seed_key)
    continues: Optional[str] = None    # thread_key
    resolves: bool = False
    secret: bool = False               # contado em segredo à Marina
    about: Optional[str] = None        # amigo em comum de quem falaram


def _rng(day: date, salt: str) -> random.Random:
    return random.Random(f"marina-social:{day.isoformat()}:{salt}")


def _at(day: date, start: time, end: time, rng: random.Random) -> datetime:
    lo = datetime.combine(day, start)
    span = int((datetime.combine(day, end) - lo).total_seconds() // 60)
    return lo + timedelta(minutes=rng.randint(0, max(0, span)) // 5 * 5)


class SocialDay:
    def __init__(self, db: DatabaseManager):
        self.db = db

    # ------------------------------------------------------------------ plano
    def _topics(self, character_key: str) -> list[str]:
        if character_key in NPC_INDEX:
            return list(NPC_INDEX[character_key][5])
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT story_tendencies_json FROM world_characters WHERE canonical_key=?",
                               (character_key,)).fetchone()
        try:
            topics = json.loads(row["story_tendencies_json"] or "[]") if row else []
        except (TypeError, ValueError):
            topics = []
        return [t for t in topics if isinstance(t, str)] or ["o dia"]

    def _topic(self, character_key: str, rng: random.Random) -> str:
        return rng.choice(self._topics(character_key))

    def _slot(self, day: date, routine_type: str, source_key: str, place_key: str,
              has_class: bool) -> Optional[tuple[datetime, datetime]]:
        """Slot do dia pela agenda (energia de referência; a presença real é
        conferida na materialização)."""
        from world_state import RoutineCandidate, RoutineEngine
        engine = RoutineEngine(self.db)
        row = engine._routine_row(source_key)
        if not row:
            return None
        cand = RoutineCandidate("", place_key, float(row["probability"]) * (0.7 if routine_type == "gym" else 1.0),
                                source_key, routine_type=routine_type)
        return engine.slot_for(datetime.combine(day, time(12, 0)), cand, has_class=has_class)

    def plan(self, day: date) -> list[Contact]:
        with self.db.get_connection() as conn:
            threads = tuple(r[0] for r in conn.execute(
                "SELECT thread_key FROM story_threads WHERE status='open' ORDER BY thread_key"))
        cache_key = (str(getattr(self.db, "db_path", id(self.db))), day, threads)
        if cache_key not in _PLAN_CACHE:
            if len(_PLAN_CACHE) > 64:
                _PLAN_CACHE.clear()
            _PLAN_CACHE[cache_key] = self._build_plan(day)
        return list(_PLAN_CACHE[cache_key])

    def _build_plan(self, day: date) -> list[Contact]:
        from academic_life import AcademicLife
        blocks = AcademicLife(self.db).blocks_on(day)
        has_class = bool(blocks)
        weekend = day.weekday() >= 5
        contacts: list[Contact] = []
        outings = self._outings_on(day)

        def add(character_key, at, channel, place_key=None, *, salt, requires=None, valence=0.3, topic=None):
            rng = _rng(day, f"topic:{character_key}:{salt}")
            topic = topic or self._topic(character_key, rng)
            secret = topic in SECRET_TOPICS and rng.random() < SECRET_CHANCE
            about = None
            ties = [next(iter(pair - {character_key})) for pair in FRIEND_TIES if character_key in pair]
            if ties and not secret and rng.random() < GOSSIP_CHANCE:
                about = rng.choice(ties)
            contacts.append(Contact(
                key=f"social:{day.isoformat()}:{character_key}:{salt}", at=at,
                character_key=character_key, channel=channel, place_key=place_key,
                topic=topic, valence=valence, requires=requires, secret=secret, about=about))

        # Presencial — PUC.
        if blocks:
            for key, chance in (("theo_martins", 0.75), ("julia_azevedo", 0.6)):
                rng = _rng(day, key)
                if rng.random() < chance:
                    block = rng.choice(blocks)
                    start = datetime.fromisoformat(block["start_at"])
                    end = datetime.fromisoformat(block["end_at"])
                    at = start + timedelta(minutes=rng.randint(10, max(10, int((end - start).total_seconds() // 60) - 10)))
                    add(key, at, "presencial", "puc_rio", salt="puc")
            projeto = [b for b in blocks if "projeto" in (b.get("display_name") or "").casefold()]
            rng = _rng(day, "helena_prado")
            if projeto and rng.random() < 0.5:
                block = rng.choice(projeto)
                add("helena_prado", datetime.fromisoformat(block["start_at"]) + timedelta(minutes=rng.randint(30, 90)),
                    "presencial", "puc_rio", salt="aula", valence=0.1)

        # Presencial — Bodytech (Carol) e prédio (Dona Célia), se ela for mesmo.
        gym = self._slot(day, "gym", "gym_weekly", "bodytech_sao_clemente", has_class)
        rng = _rng(day, "carol_menezes")
        if gym and rng.random() < 0.6:
            add("carol_menezes", gym[0] + timedelta(minutes=rng.randint(10, 30)), "presencial",
                "bodytech_sao_clemente", salt="academia", requires="gym")
        walk = self._slot(day, "pet_walk", "milo_morning_walk", "enseada_botafogo", has_class)
        rng = _rng(day, "celia_ribeiro")
        if walk and rng.random() < 0.3:
            add("celia_ribeiro", walk[0] + timedelta(minutes=1), "presencial", "marina_apartment",
                salt="predio", requires="pet_walk")

        # À distância. Fase D12 (laços): pai e melhor amiga são laço, não acaso —
        # antes o pai tinha 30% de chance num dia útil e a Bia 80% de UMA mensagem;
        # em 22/09 ela não falou com nenhum dos dois.
        # Bia: de 2 a 4 trocas espalhadas no dia (mensagem ou áudio).
        rng = _rng(day, "bia_andrade")
        windows = BIA_WINDOWS_WEEKEND if weekend else BIA_WINDOWS
        for i, window in enumerate(sorted(rng.sample(windows, rng.choice((2, 3, 3, 4))))):
            add("bia_andrade", _at(day, *window, rng), "áudio" if rng.random() < 0.3 else "mensagem",
                salt="msg" if i == 0 else f"msg{i}", valence=0.4)
        # Pai: checa a filha todo dia (mensagem de manhã, quando ela já acordou),
        # liga à noite quando está livre, e toda segunda manda o dinheiro da comida.
        rng = _rng(day, "henrique_salles")
        manha = (time(9, 30), time(11, 30)) if weekend else (
            (time(7, 40), time(9, 30)) if has_class else (time(9, 0), time(11, 0)))
        add("henrique_salles", _at(day, *manha, rng), "mensagem", salt="bomdia", valence=0.4,
            topic=rng.choice(DAD_MORNING_TOPICS))
        if rng.random() < (0.6 if weekend else 0.4):
            add("henrique_salles", _at(day, time(19, 0), time(21, 30), rng), "ligação", salt="contato",
                valence=0.4, topic=rng.choice(DAD_CALL_TOPICS))
        if day.weekday() == 0:
            add("henrique_salles", _at(day, time(10, 0), time(12, 0), rng), "mensagem", salt="mercado",
                valence=0.3, topic="mandou o dinheiro do mercado e da comida da semana, sem ela pedir")
        rng = _rng(day, "livia_vasconcelos")
        if not weekend and rng.random() < 0.2:
            add("livia_vasconcelos", _at(day, time(10, 0), time(18, 0), rng), "mensagem", salt="trabalho", valence=0.2)

        # Gente nova onde ela já está (NPCs não canônicos).
        def meet(context, at, place_key, requires=None):
            rng = _rng(day, f"npc:{context}")
            if rng.random() >= NPC_CHANCE[context]:
                return
            pool = NPC_POOLS[context]
            npc = rng.choices(pool, weights=[3, 2, 1][:len(pool)], k=1)[0]
            add(npc[0], at, "presencial", place_key, salt=f"npc:{context}", requires=requires)

        if blocks:
            rng = _rng(day, "npc:puc:hora")
            block = rng.choice(blocks)
            meet("puc", datetime.fromisoformat(block["start_at"]) + timedelta(minutes=rng.randint(15, 60)), "puc_rio")
        if gym:
            meet("gym", gym[0] + timedelta(minutes=35), "bodytech_sao_clemente", requires="gym")
        if walk:
            meet("walk", walk[0] + timedelta(minutes=12), "enseada_botafogo", requires="pet_walk")

        # Presencial — saídas confirmadas no calendário.
        for outing in outings:
            meta = json.loads(outing["metadata_json"] or "{}")
            start = datetime.fromisoformat(outing["event_at"])
            for i, friend in enumerate(meta.get("friends", [])):
                add(friend, start + timedelta(minutes=5 + i), "presencial", outing["location_key"],
                    salt="saida", valence=0.5)
            meet("outing", start + timedelta(minutes=40), outing["location_key"])

        contacts = self._with_hook(day, contacts)
        contacts += self._continuations(day, contacts)
        return sorted(contacts, key=lambda c: c.at)

    def _with_hook(self, day: date, contacts: list[Contact]) -> list[Contact]:
        rng = _rng(day, "hook")
        eligible = [c for c in contacts if c.character_key in HOOKS]
        if not eligible or rng.random() >= HOOK_CHANCE:
            return contacts
        chosen = rng.choice(eligible)
        hook = rng.choice(HOOKS[chosen.character_key])
        return [Contact(**{**c.__dict__, "hook": hook}) if c is chosen else c for c in contacts]

    def _continuations(self, day: date, contacts: list[Contact]) -> list[Contact]:
        """Thread aberta com participante → um novo contato continua o assunto."""
        extra = []
        with self.db.get_connection() as conn:
            threads = conn.execute(
                "SELECT thread_key, title, last_event_at, metadata_json FROM story_threads WHERE status='open'").fetchall()
        for thread in threads:
            meta = json.loads(thread["metadata_json"] or "{}")
            people = [p for p in meta.get("participants", []) if p in SHORT_NAME or p in NPC_INDEX]
            if not people:
                continue
            # Conta da última vez que o assunto apareceu: uma continuação que não
            # resolve agenda a próxima, em vez de deixar a história morrer.
            last = datetime.fromisoformat(thread["last_event_at"]).date()
            rng = _rng(day, f"cont:{thread['thread_key']}")
            wait = random.Random(f"{thread['thread_key']}:{last.isoformat()}").randint(*CONTINUE_AFTER_DAYS)
            if (day - last).days != wait:
                continue
            person = people[0]
            same_day = [c for c in contacts if c.character_key == person]
            at = (same_day[0].at + timedelta(minutes=5)) if same_day else _at(day, time(19, 0), time(22, 0), rng)
            extra.append(Contact(
                key=f"social:{day.isoformat()}:{person}:continua", at=at, character_key=person,
                channel=same_day[0].channel if same_day else "mensagem",
                place_key=same_day[0].place_key if same_day else None,
                topic=f"\"{thread['title']}\" (continuação)", continues=thread["thread_key"],
                resolves=rng.random() < 0.6))
        return extra

    # ---------------------------------------------------------------- saídas
    def _outings_on(self, day: date) -> list[dict]:
        with self.db.get_connection() as conn:
            return [dict(r) for r in conn.execute(
                """SELECT * FROM eventos_pendentes WHERE source_key LIKE ? AND status='pending'
                   AND confirmed=1 ORDER BY event_at""", (f"outing:{day.isoformat()}:%",))]

    def schedule_outings(self, now: datetime) -> list[int]:
        """Cria as saídas dos próximos dias como compromisso confirmado.

        Só cria no futuro (nunca retroativo) e a partir do início da vida
        social; o CalendarWorld recusa conflito com aula ou outro compromisso.
        """
        from calendar_world import CalendarWorld
        created = []
        calendar = CalendarWorld(self.db)
        for offset in range(OUTING_HORIZON_DAYS + 1):
            day = now.date() + timedelta(days=offset)
            for index, (weekday, chance, start_t, end_t, place, core, extra, text) in enumerate(OUTINGS):
                if day.weekday() != weekday:
                    continue
                rng = _rng(day, f"saida:{index}")
                if rng.random() >= chance:
                    continue
                start = datetime.combine(day, start_t)
                if start <= now + timedelta(hours=2):
                    continue  # plano precisa existir antes; nada de marcar em cima da hora
                friends = [rng.choice(core)] + [f for f in extra if rng.random() < 0.4]
                place_key = place or rng.choice(BEACHES)
                quem = " e ".join(short_name(f) for f in friends)
                description = text.format(quem=quem)
                if weekday == 4 and rng.random() < NEW_PLACE_CHANCE:
                    key, name, region, _kind = rng.choice(PLACE_POOL)
                    from social_world import SocialWorld
                    SocialWorld(self.db).discover_place(key, name, region, observed_at=now.isoformat())
                    place_key = key
                    description = f"Saindo com {quem} — {name}"
                try:
                    created.append(calendar.create_commitment(
                        source_key=f"outing:{day.isoformat()}:{index}", event_type="social",
                        description=description, start_at=start,
                        end_at=datetime.combine(day, end_t), location_key=place_key,
                        metadata={"friends": friends, "origin": "social_day"}))
                except ValueError:
                    continue  # aula, outro compromisso ou replay idêntico
        return created

    # ------------------------------------------------------------- convites (D8)
    def _invites(self) -> dict:
        raw = self.db.get_estado_relacional().get(INVITES_KEY)
        try:
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    def _save_invites(self, data: dict, now: datetime) -> None:
        cutoff = (now - timedelta(days=10)).isoformat()
        data = {k: v for k, v in data.items() if v["start"] >= cutoff}
        self.db.set_estado_relacional(INVITES_KEY, json.dumps(data, ensure_ascii=False))

    def _invite_plan(self, day: date) -> list[dict]:
        out = []
        for index, (weekday, chance, start_t, end_t, place, core, extra, text) in enumerate(WEEKEND_INVITES):
            if day.weekday() != weekday:
                continue
            rng = _rng(day, f"convite:{index}")
            if rng.random() >= chance:
                continue
            start = datetime.combine(day, start_t)
            friends = [rng.choice(core)] + [f for f in extra if rng.random() < 0.4]
            quem = " e ".join(short_name(f) for f in friends)
            if rng.random() < 0.3:      # convite do próprio dia, de manhã
                invite_at = datetime.combine(day, time(8, 30)) + timedelta(minutes=rng.randint(0, 120))
            else:
                invite_at = (datetime.combine(day - timedelta(days=rng.randint(1, 3)), time(12, 0))
                             + timedelta(minutes=rng.randint(0, 9 * 60)))
            invite_at = min(invite_at, start - timedelta(hours=1))
            decide_at = max(invite_at, start - timedelta(hours=rng.randint(2, 5)))
            out.append({"key": f"outing:{day.isoformat()}:c{index}", "friends": friends, "who": quem,
                        "text": text.format(quem=quem), "place": place or rng.choice(BEACHES),
                        "start": start.isoformat(), "end": datetime.combine(day, end_t).isoformat(),
                        "invite_at": invite_at.isoformat(), "decide_at": decide_at.isoformat(),
                        "status": "pending"})
        return out

    def _willing(self, invite: dict, now: datetime) -> tuple[bool, str]:
        """Ela vai? Decidido na hora pelo estado dela (determinístico por convite)."""
        p, reasons = INVITE_BASE_YES, []
        try:
            emo = {k: v["valor"] for k, v in self.db.get_estado_emocional(now).items()}
        except Exception:
            emo = {}
        battery = float(emo.get("social_battery", 0.7))
        p += 0.3 * (battery - 0.5)
        if battery < 0.35:
            reasons.append("tava sem bateria social")
        if float(emo.get("energy", 0.7)) < 0.35:
            p -= 0.3
            reasons.append("tava sem energia")
        try:
            from sleep_plan import SleepPlan, enabled
            start = datetime.fromisoformat(invite["start"])
            if enabled() and SleepPlan(self.db).hours_slept(start.date()) < 6.0:
                p -= 0.2
                reasons.append("dormiu mal")
        except Exception:
            pass
        if "bia_andrade" in invite["friends"]:
            p += 0.1                     # é a melhor amiga
        same_day = [i for i in self._invites().values()
                    if i["start"][:10] == invite["start"][:10] and i["status"] == "accepted"]
        if same_day:
            p -= 0.2
            reasons.append("já tinha outro rolê no dia")
        roll = random.Random(f"marina-social:{invite['key']}:decide").random()
        return roll < max(0.05, min(0.95, p)), (reasons[0] if reasons else "quis ficar de boa em casa")

    def process_invites(self, now: datetime) -> int:
        """Convites chegam (acontecimento) e, na hora, ela decide ir ou não."""
        floor = self._floor(now)
        data = self._invites()
        changed = 0
        for offset in range(-1, OUTING_HORIZON_DAYS + 1):
            for inv in self._invite_plan(now.date() + timedelta(days=offset)):
                if inv["key"] in data or datetime.fromisoformat(inv["invite_at"]) > now:
                    continue
                if datetime.fromisoformat(inv["invite_at"]) < floor:
                    continue
                data[inv["key"]] = inv
                who = inv["friends"][0]
                nome = short_name(who)
                self._log(f"{inv['key']}:convite", datetime.fromisoformat(inv["invite_at"]), who,
                          f"{nome[:1].upper() + nome[1:]} te chamou: {inv['text']} "
                          f"({self._dia(datetime.fromisoformat(inv['start']), now)}).")
                changed += 1
        from calendar_world import CalendarWorld
        for key, inv in data.items():
            if inv["status"] != "pending" or now < datetime.fromisoformat(inv["decide_at"]):
                continue
            start = datetime.fromisoformat(inv["start"])
            yes, reason = self._willing(inv, now)
            if yes and start > now + timedelta(minutes=30):
                try:
                    CalendarWorld(self.db).create_commitment(
                        source_key=key, event_type="social", description=inv["text"], start_at=start,
                        end_at=datetime.fromisoformat(inv["end"]), location_key=inv["place"],
                        metadata={"friends": inv["friends"], "origin": "convite"})
                    inv["status"] = "accepted"
                    self._log(f"{key}:resposta", now, inv["friends"][0],
                              f"Topou o convite: {inv['text']}.")
                except ValueError:
                    inv["status"], inv["reason"] = "declined", "já tinha compromisso"
            else:
                inv["status"], inv["reason"] = "declined", reason
            if inv["status"] == "declined":
                self._log(f"{key}:resposta", now, inv["friends"][0],
                          f"Recusou o convite ({inv['text']}): {inv['reason']}.")
            changed += 1
        if changed:
            self._save_invites(data, now)
        return changed

    def pending_invites(self, now: datetime) -> list[dict]:
        return [i for i in self._invites().values()
                if i["status"] == "pending" and datetime.fromisoformat(i["start"]) > now]

    @staticmethod
    def _dia(moment: datetime, now: datetime) -> str:
        dias = ('segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo')
        delta = (moment.date() - now.date()).days
        quando = "hoje" if delta == 0 else "amanhã" if delta == 1 else dias[moment.weekday()]
        return f"{quando} às {moment:%H:%M}"

    def _log(self, key: str, at: datetime, who: str, summary: str) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'social_invite','convite',?,'simulated',1,0.2,?,0.5,?)""",
                (key, at.isoformat(), summary, json.dumps(["marina", who]), datetime.now().isoformat()))
            conn.commit()

    # ----------------------------------------------------------- presença real
    def _was_doing(self, at: datetime, routine_type: str) -> bool:
        """Ela estava mesmo nessa rotina às `at`? Mesma regra do resolvedor.

        1. Snapshot de slot cobrindo `at` (ela saiu e fica até o fim) → vale ele.
        2. Senão, a agenda em `at`, com o filtro de conversa ativa daquele
           momento — se o Patrick estava conversando, ela não saiu.
        """
        with self.db.get_connection() as conn:
            snap = conn.execute(
                "SELECT observed_at, activity, source_json FROM world_state WHERE observed_at<=? "
                "ORDER BY observed_at DESC, id DESC LIMIT 1", (at.isoformat(),)).fetchone()
            last_conv = conn.execute(
                "SELECT timestamp FROM conversas WHERE timestamp<=? ORDER BY timestamp DESC LIMIT 1",
                (at.isoformat(),)).fetchone()
        if snap:
            slot_end = json.loads(snap["source_json"] or "{}").get("slot_end")
            if slot_end and datetime.fromisoformat(snap["observed_at"]) <= at < datetime.fromisoformat(slot_end):
                activity = (snap["activity"] or "").casefold()
                if routine_type == "gym":
                    return "academia" in activity and "prédio" not in activity
                return "milo" in activity
        from academic_life import AcademicLife
        from world_state import CONVERSATION_ACTIVE_WINDOW_MINUTES, RoutineEngine, current_energy
        engine = RoutineEngine(self.db)
        has_class = bool(AcademicLife(self.db).blocks_on(at.date()))
        talking = bool(last_conv and at - datetime.fromisoformat(last_conv["timestamp"])
                       < timedelta(minutes=CONVERSATION_ACTIVE_WINDOW_MINUTES))
        chosen, _ = engine.pick(at, engine.candidates(at, has_class=has_class, energy=current_energy(self.db),
                                                      conversation_active=talking), has_class=has_class)
        return chosen.routine_type == routine_type

    # ------------------------------------------------------------ materializa
    def materialize(self, now: datetime) -> list[str]:
        """Grava os contatos cujo horário já passou (hoje e ontem). Idempotente."""
        created = []
        with self.db.get_connection() as conn:
            clean = conn.execute(
                "SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done'").fetchone()
        if not clean:
            return created  # o bootstrap limpo exige zero memória até terminar
        floor = self._floor(now)
        try:
            self.schedule_outings(now)
        except Exception:
            logger.exception("social_day.outings.error")
        try:
            self.process_invites(now)
        except Exception:
            logger.exception("social_day.invites.error")
        for day in (now.date() - timedelta(days=1), now.date()):
            if day < floor.date():
                continue
            pending = [c for c in self.plan(day) if floor <= c.at <= now]
            if not pending:
                continue
            done = self._processed_keys(day)
            for contact in pending:
                if contact.key in done:
                    continue
                if contact.requires and not self._was_doing(contact.at, contact.requires):
                    self._mark_skipped(contact.key)
                    continue
                self._record(contact)
                created.append(contact.key)
        return created

    def _floor(self, now: datetime) -> datetime:
        """Início da vida social registrada. Nada é gravado retroativamente antes
        disso — senão o primeiro startup inventaria encontros em horas que a
        Marina já descreveu de outro jeito ao Patrick."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT value FROM world_bootstrap WHERE key='social_day_start'").fetchone()
            if row:
                return datetime.fromisoformat(row["value"])
            conn.execute("INSERT OR IGNORE INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('social_day_start', ?, ?)", (now.isoformat(), now.isoformat()))
        return now

    def _processed_keys(self, day: date) -> set[str]:
        prefix = f"social:{day.isoformat()}:"
        with self.db.get_connection() as conn:
            done = {r[0] for r in conn.execute(
                "SELECT event_key FROM life_events WHERE event_key LIKE ?", (prefix + "%",))}
            done |= {r[0][5:] for r in conn.execute(
                "SELECT key FROM world_bootstrap WHERE key LIKE ?", ("skip:" + prefix + "%",))}
        return done

    def _exists(self, key: str) -> bool:
        with self.db.get_connection() as conn:
            return conn.execute("SELECT 1 FROM life_events WHERE event_key=?", (key,)).fetchone() is not None

    def _skipped(self, key: str) -> bool:
        with self.db.get_connection() as conn:
            return conn.execute("SELECT 1 FROM world_bootstrap WHERE key=?", (f"skip:{key}",)).fetchone() is not None

    def _mark_skipped(self, key: str) -> None:
        with self.db.get_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO world_bootstrap (key, value, updated_at) VALUES (?, '1', ?)",
                         (f"skip:{key}", datetime.now().isoformat()))

    def _record(self, contact: Contact) -> None:
        from social_world import SocialWorld
        from world_repository import WorldBibleRepository
        bible = WorldBibleRepository(self.db)
        first_meeting = False
        if contact.character_key in NPC_INDEX and not bible.get_character(contact.character_key):
            first_meeting = self._discover_npc(contact.character_key)
        place = bible.get_place(contact.place_key) if contact.place_key else None
        name = short_name(contact.character_key)
        verbo = "Conheceu" if first_meeting else "Encontrou"
        quem_e = f", {NPC_INDEX[contact.character_key][3]}" if contact.character_key in NPC_INDEX else ""
        summary = {
            "presencial": f"{verbo} {name}{quem_e}" + (f" ({place['name']})" if place else ""),
            "mensagem": f"Trocou mensagens com {name}",
            "áudio": f"Trocou áudios com {name}",
            "ligação": f"Falou por telefone com {name}",
        }[contact.channel] + f"; assunto: {contact.topic}"
        if contact.about:
            summary += f", e falaram {self._de(contact.about)}"
        summary += "."
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,location_place_id,participants_json,share_worthy,created_at)
                   VALUES (?,?,?,?,?,'simulated',1,0.1,?,?,0.3,?)""",
                (contact.key, contact.at.isoformat(), "social_contact",
                 f"{contact.channel} com {name}", summary, place["id"] if place else None,
                 json.dumps(["marina", contact.character_key]), datetime.now().isoformat()))
        if contact.secret:
            self._record_secret(contact)
        try:
            SocialWorld(self.db).record(contact.key, occurred_at=contact.at.isoformat(),
                                        character_key=contact.character_key, place_key=contact.place_key,
                                        valence=contact.valence, meaningful=True)
        except ValueError:
            logger.warning("social_day.record.conflict key=%s", contact.key)
        if contact.character_key in NPC_INDEX:
            self._maybe_canonize(contact.character_key, contact.at)
        if contact.hook:
            self._story_from_hook(contact)
        if contact.continues:
            self._continue_story(contact, name)

    def _discover_npc(self, key: str) -> bool:
        from social_world import SocialWorld
        from world_repository import WorldBibleRepository
        npc = NPC_INDEX[key]
        SocialWorld(self.db).discover_person(key, npc[1], npc[4])
        WorldBibleRepository(self.db).upsert_character(key, {
            "display_name": npc[1], "character_type": "ephemeral", "home_region": npc[4],
            "occupation": None, "relationship_to_marina": npc[3],
            "story_tendencies_json": list(npc[5]), "initial_state_json": {"gender": npc[2]},
            "canon_locked": 0, "active": 1})
        logger.info("social_day.npc.discovered key=%s", key)
        return True

    def _maybe_canonize(self, key: str, at: datetime) -> None:
        """Recorrente (6 dias de encontro bom) → entra no cânone."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT character_type, canon_locked FROM world_characters WHERE canonical_key=?",
                               (key,)).fetchone()
            if not row or row["canon_locked"] or row["character_type"] != CANON_AFTER:
                return
            conn.execute("UPDATE world_characters SET canon_locked=1 WHERE canonical_key=?", (key,))
            conn.execute("UPDATE social_relationships SET canon_locked=1, relationship_type=? "
                         "WHERE character_key=?", (NPC_INDEX[key][3], key))
            conn.execute("INSERT OR IGNORE INTO world_bootstrap (key, value, updated_at) VALUES (?, ?, ?)",
                         (f"canonized:{key}", at.isoformat(), at.isoformat()))
        logger.info("social_day.npc.canonized key=%s", key)

    @staticmethod
    def _de(character_key: str) -> str:
        name = short_name(character_key)
        return ("da " + name[2:]) if name.startswith("a ") else ("do " + name[2:]) if name.startswith("o ") else "de " + name

    @staticmethod
    def ties_of(character_key: str) -> list[str]:
        """Amigos em comum de quem foi citado, para a linha de relação no prompt."""
        return [f"{short_name(next(iter(pair - {character_key})))} ({desc})"
                for pair, desc in FRIEND_TIES.items() if character_key in pair]

    def _record_secret(self, contact: Contact) -> None:
        """A pessoa contou em segredo: proveniência no KnowledgePrivacy.

        Cadeia: a pessoa observa → autoriza a Marina → share confirmado. A
        Marina fica com CONFIDENTIAL, e decision(marina → patrick) = WITHHOLD.
        """
        from knowledge_privacy import KnowledgePrivacy
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT id FROM life_events WHERE event_key=?", (contact.key,)).fetchone()
        if not row:
            return
        privacy = KnowledgePrivacy(self.db)
        try:
            privacy.observe("event", row["id"], contact.character_key, privacy_level="CONFIDENTIAL",
                            safe_metadata={"category": SECRET_CATEGORY.get(contact.topic, "friendship"),
                                           "severity": "low"},
                            learned_at=contact.at.isoformat())
            privacy.grant("event", row["id"], contact.character_key, "marina",
                          authorized_by=contact.character_key)
            privacy.record_confirmed_share("event", row["id"], contact.character_key, "marina",
                                           detail_level="details", evidence_key=f"{contact.key}:segredo",
                                           shared_at=contact.at.isoformat())
        except (ValueError, PermissionError):
            logger.warning("social_day.secret.skip key=%s", contact.key, exc_info=True)

    def _story_from_hook(self, contact: Contact) -> None:
        from story_engine import StoryEngine
        from world_state import current_energy
        flag, seed_key = contact.hook
        context = {"allowed_seed_keys": {seed_key}, "participant_hint": contact.character_key,
                   "academic_available": contact.place_key == "puc_rio" or contact.character_key == "helena_prado",
                   "work_available": contact.character_key == "livia_vasconcelos",
                   "energy": current_energy(self.db), "relationship_committed": True}
        if flag:
            context[flag] = True
        try:
            StoryEngine(self.db).daily_tick(contact.at, context=context)
        except Exception:
            logger.exception("social_day.story.error key=%s", contact.key)

    def _continue_story(self, contact: Contact, name: str) -> None:
        from story_engine import StoryEngine
        with self.db.get_connection() as conn:
            thread = conn.execute("SELECT title FROM story_threads WHERE thread_key=?", (contact.continues,)).fetchone()
        if not thread:
            return
        desfecho = " e o assunto ficou resolvido" if contact.resolves else ", mas ainda não se resolveu"
        try:
            StoryEngine(self.db).continue_thread(
                contact.continues, evidence_key=f"{contact.key}:thread", occurred_at=contact.at.isoformat(),
                summary=f"Marina voltou a falar com {name} sobre \"{thread['title']}\"{desfecho}.",
                participants=("marina", contact.character_key), resolved=contact.resolves)
        except ValueError:
            logger.warning("social_day.continue.skip thread=%s", contact.continues)

    # ---------------------------------------------------------------- leitura
    def today_so_far(self, now: datetime, *, limit: int = 5) -> list[dict]:
        start = datetime.combine(now.date(), time(0, 0)).isoformat()
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """SELECT e.event_at, e.summary,
                          EXISTS (SELECT 1 FROM knowledge_items k WHERE k.subject_type='event'
                                  AND k.subject_id=e.id AND k.holder_character_key='marina'
                                  AND k.privacy_level='CONFIDENTIAL' AND k.revoked_at IS NULL) AS secret
                   FROM life_events e WHERE e.event_type IN ('social_contact', 'social_invite', 'commute', 'routine')
                   AND e.event_at>=? AND e.event_at<=? ORDER BY e.event_at DESC LIMIT ?""",
                (start, now.isoformat(), limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def world_summary(self, now: datetime) -> str:
        """Texto do /mundo: o mundo dela visto de fora. Não mostra assunto de
        conversa (pode ser segredo de amiga) — só quem, quando e em que pé está."""
        nivel = {"ephemeral": "acabou de conhecer", "secondary": "já é conhecido(a)",
                 "recurring": "entrou pro círculo"}
        fam = {"discovered": "descoberto", "known": "conhecido", "habitual": "habitual",
               "occasional": "de vez em quando", "favorite": "favorito ⭐"}
        with self.db.get_connection() as conn:
            people = conn.execute(
                """SELECT w.canonical_key, w.display_name, w.character_type, w.canon_locked,
                          r.last_interaction_at, r.contact_frequency
                   FROM world_characters w JOIN social_relationships r ON r.character_key=w.canonical_key
                   WHERE w.active=1 AND w.canonical_key NOT IN ('marina','patrick_ramos')
                   ORDER BY r.last_interaction_at DESC""").fetchall()
            places = conn.execute(
                """SELECT p.name, COALESCE(s.familiarity, p.familiarity) AS familiarity
                   FROM world_places p LEFT JOIN social_place_state s ON s.place_key=p.canonical_key
                   WHERE p.canon_locked=0 AND p.active=1""").fetchall()
        lines = ["🌍 O mundo da Marina", "", "👭 Círculo"]
        for p in people:
            if p["canonical_key"] in NPC_INDEX and not p["canon_locked"]:
                continue
            quando = (self._quando(datetime.fromisoformat(p["last_interaction_at"]), now)
                      if p["last_interaction_at"] else "sem contato ainda")
            novo = " (novo no cânone)" if p["canonical_key"] in NPC_INDEX else ""
            lines.append(f"• {p['display_name']}{novo} — último contato {quando}; "
                         f"{p['contact_frequency']} nos últimos 30 dias")
        novos = [p for p in people if p["canonical_key"] in NPC_INDEX and not p["canon_locked"]]
        if novos:
            lines += ["", "🙋 Conhecidos novos"]
            lines += [f"• {p['display_name']}, {NPC_INDEX[p['canonical_key']][3]} — "
                      f"{nivel.get(p['character_type'], p['character_type'])}" for p in novos]
        if places:
            lines += ["", "📍 Lugares que ela anda descobrindo"]
            lines += [f"• {p['name']} — {fam.get(p['familiarity'], p['familiarity'])}" for p in places]
        stories = self.open_stories()
        if stories:
            lines += ["", "📖 Rolando agora"]
            for s in stories:
                people_s = [short_name(k) for k in json.loads(s["metadata_json"] or "{}").get("participants", [])
                            if k != "marina"]
                lines.append(f"• {s['title']}" + (f" (com {', '.join(people_s)})" if people_s else ""))
        plans = self.upcoming_outings(now)
        if plans:
            lines += ["", "🗓️ Planos"]
            lines += [f"• {p['description']} — {datetime.fromisoformat(p['event_at']).strftime('%d/%m %H:%M')}"
                      for p in plans]
        return "\n".join(lines)

    @staticmethod
    def _quando(moment: datetime, now: datetime) -> str:
        dias = (now.date() - moment.date()).days
        if dias == 0:
            return f"hoje às {moment.strftime('%H:%M')}"
        if dias == 1:
            return f"ontem às {moment.strftime('%H:%M')}"
        return f"há {dias} dias"

    def upcoming_outings(self, now: datetime, *, limit: int = 3) -> list[dict]:
        with self.db.get_connection() as conn:
            return [dict(r) for r in conn.execute(
                """SELECT event_at, description FROM eventos_pendentes WHERE source_key LIKE 'outing:%'
                   AND status='pending' AND confirmed=1 AND event_at>? ORDER BY event_at LIMIT ?""",
                (now.isoformat(), limit))]

    def open_stories(self) -> list[dict]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """SELECT title, summary, started_at, last_event_at, metadata_json FROM story_threads
                   WHERE status='open' ORDER BY last_event_at DESC LIMIT 2""").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------ novidade pro Patrick
    SHARED_KEY = "social_news_shared"
    SECRET_NOTE = "contado EM SEGREDO: você sabe, mas não conta os detalhes pro Patrick — no máximo diz que prometeu guardar"

    def _shared(self) -> list[str]:
        raw = self.db.get_estado_relacional(self.SHARED_KEY)
        try:
            return list(json.loads(raw)) if raw else []
        except (TypeError, ValueError):
            return []

    def fresh_news(self, now: datetime, *, within: timedelta = timedelta(hours=3)) -> Optional[dict]:
        """Acontecimento recente que ela ainda não contou: história > contato."""
        shared = set(self._shared())
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """SELECT e.event_key, e.event_at, e.event_type, e.summary, e.participants_json,
                          EXISTS (SELECT 1 FROM knowledge_items k WHERE k.subject_type='event'
                                  AND k.subject_id=e.id AND k.holder_character_key='marina'
                                  AND k.privacy_level='CONFIDENTIAL' AND k.revoked_at IS NULL) AS secret
                   FROM life_events e
                   WHERE e.source_type IN ('simulated','user_shared') AND e.event_at<=? AND e.event_at>=?
                   ORDER BY CASE WHEN e.event_type='social_contact' THEN 1 ELSE 0 END, e.event_at DESC""",
                (now.isoformat(), (now - within).isoformat())).fetchall()
        for row in rows:
            if row["event_key"] not in shared:
                news = dict(row)
                if news["event_type"] != "social_contact":
                    # História: a semente é genérica ("um contato conhecido..."),
                    # então o nome de quem está envolvido vai junto.
                    people = [short_name(p) for p in json.loads(news["participants_json"] or "[]")
                              if p in SHORT_NAME or p in NPC_INDEX]
                    if people:
                        news["summary"] = f"Envolve {', '.join(people)}. {news['summary']}"
                if news.get("secret"):
                    news["summary"] += f" ({self.SECRET_NOTE}.)"
                return news
        return None

    def mark_shared(self, event_key: str) -> None:
        shared = [k for k in self._shared() if k != event_key][-49:] + [event_key]
        self.db.set_estado_relacional(self.SHARED_KEY, json.dumps(shared))

    def last_contact(self, character_key: str, now: datetime) -> Optional[dict]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """SELECT e.event_at, e.summary,
                          EXISTS (SELECT 1 FROM knowledge_items k WHERE k.subject_type='event'
                                  AND k.subject_id=e.id AND k.holder_character_key='marina'
                                  AND k.privacy_level='CONFIDENTIAL' AND k.revoked_at IS NULL) AS secret
                   FROM life_events e WHERE e.event_type='social_contact'
                   AND e.participants_json LIKE ? AND e.event_at<=? ORDER BY e.event_at DESC LIMIT 1""",
                (f'%"{character_key}"%', now.isoformat())).fetchone()
        if not row:
            return None
        contact = dict(row)
        if contact["secret"]:
            contact["summary"] += f" ({self.SECRET_NOTE})"
        return contact
