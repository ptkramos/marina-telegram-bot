"""Etapas do dia (Patrick, 26/09 — aba Agora, decidida linha a linha com ele).

Todo compromisso fora de casa vira uma sequência: Se arrumando → A caminho → Lá → Voltando
→ Em casa; depois de um rolê à noite, outro Se arrumando (pra dormir). Antes só existia o
"se arrumando pra faculdade" de manhã: do "tempo livre em casa" ela pulava pro trajeto.

Tudo sai do que o mundo já decide (compromissos, aulas, trajetos com modo/carona/imprevisto,
consumo, plano de sono) — este módulo não inventa nada, só organiza. Serve:
- o WorldState (a atividade dela enquanto se arruma) e, por ele, a disponibilidade no chat;
- os rituais (o banho do "Tomando banho" acontece de verdade);
- o card da aba Agora dos Bastidores (`card`).

Textos decididos pelo Patrick: título curto (nome curto do lugar só no título e no chat),
passos no gerúndio sem artigo, horas 00:00 com "~" no que é previsto, duração "1h 10min",
"Onde" sempre o bairro, celular sempre "Olha …".
"""
from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# nome curto (título e chat) e preposição
CURTO = {"quartinho_bar": "no Quartinho", "starbucks_shopping_gavea": "no Starbucks", "puc_rio": "na PUC",
         "shopping_gavea": "no Shopping da Gávea", "copacabana_beach": "na praia", "ipanema_beach": "na praia",
         "leblon_beach": "na praia", "boutique_agency": "na agência", "bodytech_sao_clemente": "na academia",
         "estadio_nilton_santos": "no Nilton Santos", "enseada_botafogo": "na Enseada",
         "botafogo_praia_shopping": "no shopping", "hospital_samaritano_botafogo": "no Samaritano",
         "novamed_botafogo": "na Novamed", "ophicina_do_cabelo_botafogo": "na Ophicina"}
COMO = {"onibus": "Ônibus", "metro": "Metrô", "metro_onibus": "Metrô e ônibus", "uber": "Uber", "a_pe": "A pé"}

# passos do Se arrumando: (texto, peso). O último passo depende do transporte.
PREP = {
    "noite": (("Tomando banho", 25), ("Secando cabelo", 20), ("Fazendo maquiagem", 25), ("Escolhendo roupa", 20)),
    "encontro": (("Tomando banho", 40), ("Fazendo maquiagem", 25), ("Escolhendo roupa", 25)),
    "freela": (("Tomando banho", 50), ("Escolhendo roupa", 35)),        # sem make: é feita lá
    "faculdade": (("Tomando banho", 35), ("Escolhendo roupa", 25)),   # o café vem do meals (28/09)
    "praia": (("Colocando biquíni", 50), ("Passando protetor", 40)),
    "academia": (("Colocando roupa de treino", 60), ("Enchendo a garrafinha", 20)),
    # 26/09 — agenda única: passeio do Milo, saídas por vontade, mercado e médico
    "milo": (("Colocando a coleira", 60), ("Pegando os saquinhos", 40)),
    "cafe": (("Trocando de roupa", 70), ("Pegando a bolsa", 30)),
    "acai": (("Trocando de roupa", 70), ("Pegando a bolsa", 30)),
    "farmacia": (("Trocando de roupa", 70), ("Pegando a bolsa", 30)),
    "mercado": (("Trocando de roupa", 70), ("Pegando a bolsa", 30)),
    "orla": (("Colocando tênis", 60), ("Passando protetor", 40)),
    "shopping": (("Escolhendo roupa", 50), ("Fazendo maquiagem leve", 50)),
    "mercado_semana": (("Fazendo a lista", 60), ("Pegando as sacolas", 40)),
    "medico": (("Trocando de roupa", 60), ("Separando a carteirinha do plano", 40)),
    "pronto_atendimento": (("Trocando de roupa", 60), ("Separando a carteirinha do plano", 40)),
    "manicure": (("Trocando de roupa", 70), ("Pegando a bolsa", 30)),
    "cabelo": (("Trocando de roupa", 70), ("Pegando a bolsa", 30)),
    "jogo": (("Tomando banho", 40), ("Vestindo a camisa do Botafogo", 25), ("Fazendo maquiagem", 25)),
    "dormir": (("Tirando maquiagem", 25), ("Tomando banho", 50), ("Colocando pijama", 25)),
}
PREP_MIN = {"milo": (3, 5), "cafe": (8, 12), "acai": (6, 10), "farmacia": (5, 8), "mercado": (6, 10),
            "orla": (8, 12), "shopping": (20, 30), "mercado_semana": (8, 12), "medico": (12, 18),
            "pronto_atendimento": (8, 12), "manicure": (8, 12), "cabelo": (8, 12),
            "academia": (10, 15), "noite": (60, 90), "encontro": (30, 45), "jogo": (40, 55), "freela": (40, 55), "praia": (15, 20), "dormir": (30, 45)}
BANHO_DORMIR_JANELA = timedelta(minutes=90)     # banho de chegada tão perto da cama vira o banho do Se arrumando
PREP_BANHO_JANELA = timedelta(minutes=120)      # banho de verdade até 2 h antes de sair é o banho do Se arrumando
PREP_BANHO_ANTES = timedelta(minutes=45)        # ...e o Se arrumando começa nele se foi até 45 min antes do previsto
# o que acontece lá (quando não é consumo nem aula)
LA_PASSOS = {
    "milo": (("Passeando", 70), ("Xixi do Milo", 30)),
    "orla": (("Caminhando na orla", 80), ("Olhando o Pão de Açúcar", 20)),
    "shopping": (("Olhando vitrines", 60), ("Provando roupa", 40)),
    "mercado_semana": (("Pegando frutas e verduras", 35), ("Enchendo o carrinho", 45), ("No caixa", 20)),
    "medico": (("Na recepção", 25), ("Na consulta", 55), ("Pegando a receita", 20)),
    # 26/09: unha em gel na Ophicina (unhas.py)
    "manicure": (("Tirando o esmalte antigo", 18), ("Fazendo a mão em gel", 44), ("Fazendo o pé", 34), ("Pagando", 4)),
    "pronto_atendimento": (("Na triagem", 15), ("Esperando ser chamada", 40), ("No atendimento", 30),
                           ("Pegando a receita", 15)),
}
FACULDADE_CABELO_CHANCE = 0.4          # "às vezes" (nem todo dia ela lava o cabelo)

# imprevisto numa linha só (card): o texto do mundo é longo demais
IMPREVISTO = {"o ônibus veio lotado": "Ônibus veio lotado", "o ônibus demorou uns 20 minutos pra passar": "Ônibus demorou 20min",
              "o metrô tava lotado": "Metrô veio lotado", "perdeu o ônibus da integração por um minuto": "Perdeu a integração",
              "o metrô parou uns minutos entre as estações": "Metrô parou uns minutos",
              "o motorista do uber errou o caminho": "Motorista errou o caminho",
              "o uber cancelou e ela teve que chamar outro": "Uber cancelou", "começou a garoar no caminho": "Começou a garoar",
              "pegaram um trânsito chato no caminho": "Pegaram trânsito", "pararam pra comprar um açaí no caminho": "Pararam pra um açaí"}

CELULAR = {"arrumando": "Olha de vez em quando", "publico": "Olha com frequência",
           "carona": "Olha de vez em quando", "aula": "Olha nos intervalos", "role": "Olha de vez em quando",
           "casa": "Olha com frequência", "banho": "Olha depois do banho", "dormindo": "Olha quando acordar",
           "comendo": "Olha de vez em quando"}


@dataclass
class Passo:
    texto: str
    inicio: datetime
    valor: Optional[int] = None
    aviso: bool = False


@dataclass
class Etapa:
    tipo: str                     # arrumando | caminho | la | voltando
    titulo: str
    inicio: datetime
    fim: datetime
    linha2: str = ""
    lugar_key: str = ""
    bairro: str = ""
    com: list = field(default_factory=list)
    como: str = ""
    celular: str = ""
    passos: list = field(default_factory=list)
    chave: str = ""
    prep_tipo: str = ""
    compromisso: str = ""         # key do compromisso da agenda (agenda reativa)

    @property
    def total(self) -> Optional[int]:
        vals = [p.valor for p in self.passos if p.valor]
        return sum(vals) if vals else None


def _rng(day: date, salt: str) -> random.Random:
    return random.Random(f"agenda:{day.isoformat()}:{salt}")


def hora(at: datetime) -> str:
    return f"{at:%H:%M}"


def aprox(at: datetime) -> str:
    """Previsto: arredonda pra 5 min ("~20:05")."""
    at = at + timedelta(minutes=2, seconds=30)
    at = at.replace(minute=at.minute - at.minute % 5, second=0, microsecond=0)
    return f"~{at:%H:%M}"


def duracao(td: timedelta) -> str:
    """'1h 10min', '12min', '2h'."""
    mins = max(0, int(round(td.total_seconds() / 60)))
    h, m = divmod(mins, 60)
    if h and m:
        return f"{h}h {m}min"
    return f"{h}h" if h else f"{m}min"


BAIRRO_PREP = {"Gávea": "na Gávea", "Leblon": "no Leblon", "Jardim Botânico": "no Jardim Botânico",
               "Humaitá": "no Humaitá", "Flamengo": "no Flamengo", "Centro": "no Centro",
               "Engenho de Dentro": "no Engenho de Dentro"}


def em_bairro(bairro: str) -> str:
    return BAIRRO_PREP.get(bairro, f"em {bairro}")


def _sem_artigo(nome: str) -> str:
    return nome.split(" ", 1)[1] if nome[:2] in ("o ", "a ") else nome


def _com(friends: list) -> list[str]:
    from social_day import short_name
    return [_sem_artigo(short_name(f)) for f in friends]


def _e(nomes: list[str]) -> str:
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1] if nomes else ""


class Agenda:
    def __init__(self, db):
        self.db = db
        self._places: dict = {}

    # ----------------------------------------------------------- mundo --
    def _place(self, key: str) -> dict:
        if key not in self._places:
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT name, region FROM world_places WHERE canonical_key=?", (key,)).fetchone()
            self._places[key] = {"name": row["name"], "region": row["region"]} if row else {"name": key, "region": ""}
        return self._places[key]

    def _compromissos(self, day: date) -> list[dict]:
        """Saídas, freelas e o bloco de aulas do dia, com os trajetos casados."""
        from commute import Commute
        legs = {l.key: l for l in Commute(self.db).legs_on(day)}
        out = []
        from academic_life import AcademicLife
        blocks = sorted(AcademicLife(self.db).blocks_on(day), key=lambda b: b["start_at"])
        if blocks:
            out.append({"tipo": "faculdade", "key": f"puc:{day.isoformat()}", "place": "puc_rio",
                        "inicio": datetime.fromisoformat(blocks[0]["start_at"]),
                        "fim": datetime.fromisoformat(blocks[-1]["end_at"]), "friends": [], "blocks": blocks,
                        "ida": legs.get(f"commute:{day.isoformat()}:puc:ida"),
                        "volta": legs.get(f"commute:{day.isoformat()}:puc:volta")})
        try:
            from academia import Academia, LUGAR
            treino = Academia(self.db).plano(day)
        except Exception:
            treino = None
        if treino and treino["onde"] == "rua":
            out.append({"tipo": "academia", "key": f"gym:{day.isoformat()}", "place": LUGAR,
                        "inicio": treino["inicio"], "fim": treino["fim"], "friends": [],
                        "decidido_em": treino.get("decidido_em"), "fim_original": treino.get("fim_original"),
                        "ida": legs.get(f"commute:{day.isoformat()}:gym:ida"),
                        "volta": legs.get(f"commute:{day.isoformat()}:gym:volta")})
        try:
            from academia import PasseioMilo
            passeio = PasseioMilo(self.db).plano(day)
        except Exception:
            passeio = None
        if passeio:
            out.append({"tipo": "milo", "key": f"milo:{day.isoformat()}", "place": "enseada_botafogo",
                        "inicio": passeio["inicio"], "fim": passeio["fim"], "friends": [],
                        "decidido_em": passeio.get("decidido_em"), "fim_original": passeio.get("fim_original"),
                        "ida": legs.get(f"commute:{day.isoformat()}:milo:ida"),
                        "volta": legs.get(f"commute:{day.isoformat()}:milo:volta")})
        with self.db.get_connection() as conn:              # 26/09: agenda única (vontade, mercado, médico)
            vivos = [dict(r) for r in conn.execute(
                """SELECT source_key, event_at, end_at, location_key, metadata_json, description FROM eventos_pendentes
                   WHERE (source_key LIKE ? OR source_key LIKE ? OR source_key LIKE ? OR source_key LIKE ?
                          OR source_key LIKE ?)
                   AND confirmed=1 AND status != 'cancelled' AND end_at IS NOT NULL ORDER BY event_at""",
                (f"vontade:{day.isoformat()}:%", f"mercado:{day.isoformat()}%", f"medico:{day.isoformat()}%",
                 f"unhas:{day.isoformat()}:%", f"cabelo:{day.isoformat()}:%"))]
        for r in vivos:
            meta = json.loads(r["metadata_json"] or "{}") or {}
            out.append({"tipo": meta.get("tipo", "cafe"), "key": r["source_key"], "place": r["location_key"],
                        "inicio": datetime.fromisoformat(r["event_at"]), "fim": datetime.fromisoformat(r["end_at"]),
                        "friends": [], "outing": r, "decidido_em": meta.get("decidido_em"),
                        "fim_original": meta.get("fim_original"),
                        "ida": legs.get(f"commute:{r['source_key']}:ida"),
                        "volta": legs.get(f"commute:{r['source_key']}:volta")})
        with self.db.get_connection() as conn:
            rows = [dict(r) for r in conn.execute(
                """SELECT source_key, event_at, end_at, location_key, metadata_json, description FROM eventos_pendentes
                   WHERE (source_key LIKE ? OR source_key LIKE ?) AND confirmed=1 AND status != 'cancelled'
                   AND end_at IS NOT NULL ORDER BY event_at""",
                (f"outing:{day.isoformat()}:%", f"freela:{day.isoformat()}:%"))]
        for r in rows:
            if not r["location_key"]:
                continue
            tag = r["source_key"].split(":", 1)[1]
            inicio = datetime.fromisoformat(r["event_at"])
            freela = r["source_key"].startswith("freela:")
            place = r["location_key"]
            tipo = ("freela" if freela else "praia" if place.endswith("_beach")
                    else "jogo" if ":j" in r["source_key"] else "noite" if inicio.hour >= 18 else "encontro")
            out.append({"tipo": tipo, "key": r["source_key"], "place": place, "inicio": inicio,
                        "fim": datetime.fromisoformat(r["end_at"]), "outing": r,
                        "friends": (json.loads(r["metadata_json"] or "{}") or {}).get("friends") or [],
                        "ida": legs.get(f"commute:outing:{tag}:ida"), "volta": legs.get(f"commute:outing:{tag}:volta")})
        return sorted(out, key=lambda c: c["inicio"])

    # --------------------------------------------------------- etapas --
    def etapas(self, day: date, now: datetime) -> list[Etapa]:
        out: list[Etapa] = []
        fim_anterior = datetime.combine(day, datetime.min.time())
        try:
            from sleep_plan import SleepPlan
            wake = SleepPlan(self.db).wake(day)
        except Exception:
            wake = None
        teve_make = False
        ultimo_fim = None
        for c in self._compromissos(day):
            ida, volta = c["ida"], c["volta"]
            if not ida:
                continue
            place = self._place(c["place"])
            com = _com(c["friends"])
            # 1. Se arrumando
            rng = _rng(day, f"prep:{c['key']}")
            if c["tipo"] == "faculdade":
                inicio = max(wake or ida.start - timedelta(minutes=60), ida.start - timedelta(minutes=90))
            else:
                inicio = ida.start - timedelta(minutes=rng.randint(*PREP_MIN.get(c["tipo"], (8, 12))))
            inicio = max(inicio, fim_anterior)
            if c.get("decidido_em"):                     # decidiu na hora: se arruma a partir dali
                decidiu = datetime.fromisoformat(c["decidido_em"])
                inicio = (max(fim_anterior, decidiu) if ida.start - decidiu <= timedelta(minutes=30)
                          else max(inicio, decidiu))
            # refeição em casa que cai na janela: ela come primeiro e se arruma depois
            # 28/09 (Patrick): na faculdade o café é o 1º passo do Se arrumando, na hora real do meals — o card dizia
            # "Tomando café" 07:36–07:46 com ela pulando o café (07:52). Pulou: sem passo.
            cafe = None
            for s in self._refeicoes_em_casa(day):
                if c["tipo"] == "faculdade" and s.kind == "cafe":
                    cafe = s
                    continue
                if s.at < ida.start and s.end > inicio:
                    inicio = max(inicio, s.end)
            if cafe and not (inicio <= cafe.at < ida.start):
                if cafe.at < inicio < cafe.end:
                    inicio = cafe.end                    # o café atravessa o começo: se arruma depois dele
                cafe = None
            if inicio < ida.start:
                passos = list(PREP.get(c["tipo"], PREP["cafe"]))
                if c["tipo"] == "faculdade" and rng.random() < FACULDADE_CABELO_CHANCE:
                    passos.insert(1, ("Secando cabelo", 15))
                final = ("Esperando carona" if ida.mode == "carona" else
                         "Chamando uber" if ida.mode in ("uber", "uber_dividido") else "Saindo")
                if cafe:
                    fim_cafe = min(cafe.end, ida.start)
                    ini2, lista = self._prep_com_banho(passos + [(final, 10)], fim_cafe, ida.start, fim_anterior)
                    inicio = min(cafe.at, ini2)
                    lista = sorted([Passo("Tomando café", cafe.at)] + lista, key=lambda p: p.inicio)
                else:
                    inicio, lista = self._prep_com_banho(passos + [(final, 10)], inicio, ida.start, fim_anterior)
                lista = self._com_milo(day, lista, inicio, ida.start)
                out.append(Etapa("arrumando", "Se arrumando", inicio, ida.start,
                                 linha2=f"Vai sair {self._pra(place['name'])} às {aprox(ida.start)}",
                                 lugar_key="marina_apartment", com=com, celular=CELULAR["arrumando"],
                                 passos=lista, chave=f"prep:{c['key']}", prep_tipo=c["tipo"]))
                teve_make = teve_make or c["tipo"] in ("noite", "encontro", "jogo")
            # 2. A caminho
            out.append(self._trajeto(ida, "caminho", "A caminho",
                                     f"Chega {self._na(place['name'])} às {aprox(ida.end)}", place, c))
            # 3. Lá
            out.append(self._la(c, place, com, now, volta))
            # 4. Voltando
            if volta:
                out.append(self._trajeto(volta, "voltando", "Voltando pra casa",
                                         f"Chega em casa às {aprox(volta.end)}", place, c))
                fim_anterior = ultimo_fim = volta.end
            else:
                fim_anterior = ultimo_fim = c["fim"]
            for e in out:
                if not e.compromisso and e.chave != "prep:dormir":
                    e.compromisso = c["key"]
        # 5. Depois de um rolê à noite: Se arrumando (pra dormir)
        if teve_make and ultimo_fim and (ultimo_fim.hour >= 17 or ultimo_fim.date() > day):
            try:
                from sleep_plan import SleepPlan
                bed = SleepPlan(self.db).bed(day)
            except Exception:
                bed = None
            if bed and bed > ultimo_fim:
                rng = _rng(day, "prep:dormir")
                inicio = max(ultimo_fim + timedelta(minutes=5), bed - timedelta(minutes=rng.randint(*PREP_MIN["dormir"])))
                passos = PREP["dormir"] if teve_make else PREP["dormir"][1:]
                lista = self._distribui(list(passos), inicio, bed)
                banho = next(iter(self._banhos(ultimo_fim, bed)), None)
                if banho:
                    # 27/09 (Patrick, "um card só"): chegou do rolê e foi pro banho — é o banho do Se arrumando,
                    # não um segundo (antes o card marcava outro às 01:00 e o ritual podia dar mais um banho).
                    b_ini, b_fim, lavou = banho
                    resto = [p for p in passos if p[0] != "Tomando banho"]
                    if b_ini >= bed - BANHO_DORMIR_JANELA:
                        inicio = min(inicio, b_ini)
                        lista = [Passo("Tomando banho e lavando o cabelo" if lavou else "Tomando banho", b_ini)]
                        if resto and b_fim < bed - timedelta(minutes=5):
                            lista += self._distribui(resto, b_fim, bed)
                    else:
                        lista = self._distribui(resto, inicio, bed)
                lista = self._com_milo(day, lista, inicio, bed)
                out.append(Etapa("arrumando", "Se arrumando", inicio, bed, linha2=f"Vai dormir às {aprox(bed)}",
                                 lugar_key="marina_apartment", celular=CELULAR["arrumando"],
                                 passos=lista, chave=f"prep:dormir:{day}", prep_tipo="dormir"))
        return out

    def _prep_com_banho(self, passos: list, inicio: datetime, sai: datetime,
                        fim_anterior: datetime) -> tuple[datetime, list[Passo]]:
        """27/09, 14:03: banho de verdade às 13:51–13:59; o "vai de uber" das 14:02 mudou a ida, o Se arrumando
        recomeçou às 14:02 e o card (e o mundo) voltaram pro "Tomando banho". O banho que já aconteceu é o banho do
        Se arrumando: fica na hora dele, e o resto se distribui depois."""
        if not any(t == "Tomando banho" for t, _ in passos):
            return inicio, self._distribui(passos, inicio, sai)
        banho = next(iter(self._banhos(max(fim_anterior, sai - PREP_BANHO_JANELA), sai)), None)
        if not banho:
            return inicio, self._distribui(passos, inicio, sai)
        b_ini, b_fim, lavou = banho
        i = next(n for n, (t, _) in enumerate(passos) if t == "Tomando banho")
        antes, depois = passos[:i], passos[i + 1:]
        if b_ini < inicio - PREP_BANHO_ANTES:            # tomou banho bem antes (ex.: depois da academia): só tira o passo
            return inicio, self._distribui(antes + depois, inicio, sai)
        inicio = min(inicio, b_ini)
        lista = self._distribui(antes, inicio, b_ini) if antes and inicio < b_ini else []
        lista.append(Passo("Tomando banho e lavando o cabelo" if lavou else "Tomando banho", b_ini))
        if b_fim < sai:
            lista += self._distribui(depois, b_fim, sai)
        return inicio, lista

    def _com_milo(self, day: date, lista: list[Passo], inicio: datetime, fim: datetime) -> list[Passo]:
        """28/09: o Milo desceu pro xixi às 07:58 e o card dizia "Tomando banho" (07:46–08:06). A descida do Milo
        que cai no Se arrumando vira passo, na hora dela."""
        try:
            from milo import Milo
            descidas = [(d["at"], d["at"] + timedelta(minutes=d["minutes"])) for d in Milo(self.db).day_plan(day)
                        if d["minutes"] and not d["key"].endswith(":passeador")]
        except Exception:
            logger.exception("agenda.milo.error")
            return lista
        for ini, fim_d in descidas:
            if inicio <= ini < fim:
                lista = self._encaixa(lista, "Descendo com o Milo", ini, min(fim_d, fim), fim)
        return lista

    @staticmethod
    def _encaixa(lista: list[Passo], texto: str, ini: datetime, fim: datetime, ate: datetime) -> list[Passo]:
        """Um passo com hora marcada no meio do Se arrumando. O que começaria durante ele espera ele acabar; o que
        estava rolando volta depois — menos o banho, que ela termina antes de descer (aí o passo seguinte adianta)."""
        out = sorted(lista, key=lambda p: p.inicio)
        atual = next((p for p in reversed(out) if p.inicio < ini and not p.aviso), None)
        dentro = [p for p in out if ini <= p.inicio < fim and not p.aviso]
        depois = next((p for p in out if p.inicio >= fim and not p.aviso), None)
        if fim < ate:
            if dentro:                                  # espremidos entre a volta e o passo seguinte
                limite = depois.inicio if depois else ate
                passo = (limite - fim) / len(dentro)
                for n, p in enumerate(dentro):
                    p.inicio = fim + passo * n
            elif atual and depois and (atual.texto.startswith("Tomando banho")
                                       or depois.inicio - fim < timedelta(minutes=3)):
                depois.inicio = fim                     # banho não volta, e 1 min de volta só picota o card
            elif atual and (not depois or depois.inicio > fim):
                out.append(Passo(atual.texto, fim))
        else:
            out = [p for p in out if p not in dentro]
        out.append(Passo(texto, ini))
        return sorted(out, key=lambda p: p.inicio)

    def _banhos(self, ini: datetime, fim: datetime) -> list[tuple[datetime, datetime, bool]]:
        """Banhos de verdade (rituals.start_shower) que começaram entre `ini` e `fim`."""
        with self.db.get_connection() as conn:
            rows = conn.execute("""SELECT event_at, summary FROM life_events WHERE event_key LIKE 'banho:%'
                                   AND event_at>=? AND event_at<? ORDER BY event_at""",
                                (ini.isoformat(), fim.isoformat())).fetchall()
        out = []
        for r in rows:
            m = re.search(r"\((\d\d):(\d\d)–(\d\d):(\d\d)\)", r["summary"] or "")
            if not m:
                continue
            b_ini = datetime.fromisoformat(r["event_at"])
            b_fim = b_ini.replace(hour=int(m.group(3)), minute=int(m.group(4)), second=0, microsecond=0)
            if b_fim < b_ini:
                b_fim += timedelta(days=1)
            out.append((b_ini, b_fim, "lavou o cabelo" in (r["summary"] or "")))
        return out

    def _refeicoes_em_casa(self, day: date) -> list:
        try:
            from meals import Meals
            return [s for s in Meals(self.db).day_plan(day) if s.where == "casa" and not s.skipped]
        except Exception:
            return []

    @staticmethod
    def _distribui(passos: list, inicio: datetime, fim: datetime) -> list[Passo]:
        total = sum(p for _, p in passos) or 1
        span = (fim - inicio).total_seconds()
        out, t = [], inicio
        for texto, peso in passos:
            out.append(Passo(texto, t))
            t = t + timedelta(seconds=span * peso / total)
        return out

    @staticmethod
    def _pra(nome: str) -> str:
        from commute import _pra
        return _pra(nome)

    @staticmethod
    def _na(nome: str) -> str:
        from commute import _pra
        return _pra(nome).replace("pra ", "na ", 1).replace("pro ", "no ", 1)

    def _trajeto(self, leg, tipo: str, titulo: str, linha2: str, place: dict, c: dict) -> Etapa:
        bairro = place["region"] or leg.region
        from vontade import no as _no
        no = CURTO.get(c["place"], _no(place["name"]))          # "no Quartinho", "na PUC"
        o = ("a " if no.startswith("na ") else "o ") + no.split(" ", 1)[1]
        casa = leg.direction == "volta"
        chegando = "Chegando em casa" if casa else f"Chegando {no}"
        andando = "Andando até em casa" if casa else f"Andando até {o}"
        saltando = f"Saltando {em_bairro('Botafogo' if casa else bairro)}"
        if leg.mode == "carona":
            quem = leg.companion                                  # "o Theo" (aprovado com artigo)
            passos = [(f"No carro com {quem}", 85), (chegando, 15)]
            como, cel = f"Carona com {quem}", CELULAR["carona"]
        elif leg.mode in ("uber", "uber_dividido"):
            passos = [("Esperando uber", 15), ("No uber", 85)]
            quem = _sem_artigo(leg.companion) if leg.companion else ""
            como = "Uber" + (f" com {quem}" if leg.mode == "uber_dividido" and quem else "")
            cel = CELULAR["publico"]
        elif leg.mode == "a_pe":
            passos = [(andando, 100)]
            como, cel = "A pé", CELULAR["publico"]
        elif leg.mode == "metro":
            passos = [("Andando até a estação", 12), ("No metrô", 70), (saltando, 5), (andando, 13)]
            como, cel = COMO["metro"], CELULAR["publico"]
        elif leg.mode == "metro_onibus":
            passos = [("Andando até a estação", 10), ("No metrô", 40), ("Trocando pro ônibus", 8), ("No ônibus", 30),
                      (saltando, 4), (andando, 8)]
            como, cel = COMO["metro_onibus"], CELULAR["publico"]
        else:
            passos = [("Andando até o ponto", 15), ("No ônibus", 70), (saltando, 5), (andando, 10)]
            como, cel = COMO.get(leg.mode, "Ônibus"), CELULAR["publico"]
        lista = self._distribui(passos, leg.start, leg.end)
        if leg.mode in ("uber", "uber_dividido"):
            from consumo import uber_price
            lista[-1].valor = uber_price((leg.end - leg.start).total_seconds() / 60, leg.mode == "uber_dividido")
        if leg.incident and leg.incident_at:
            curto = IMPREVISTO.get(leg.incident, leg.incident[:1].upper() + leg.incident[1:])
            lista.append(Passo(curto, leg.incident_at, aviso=True))
            lista.sort(key=lambda p: p.inicio)
        return Etapa(tipo, titulo, leg.start, leg.end, linha2=linha2, bairro=bairro, como=como, celular=cel,
                     passos=lista, chave=leg.key)

    def _la(self, c: dict, place: dict, com: list, now: datetime, volta) -> Etapa:
        from vontade import no
        curto = CURTO.get(c["place"], no(place["name"]))
        titulo = curto[:1].upper() + curto[1:]
        passos: list[Passo] = []
        fim_real = c["fim"]
        if c.get("fim_original"):                        # saiu mais cedo: os passos seguem o plano até a saída
            c = {**c, "fim": datetime.fromisoformat(c["fim_original"])}
        if c["tipo"] == "faculdade":
            anterior = None
            for b in c["blocks"]:
                ini, fim = datetime.fromisoformat(b["start_at"]), datetime.fromisoformat(b["end_at"])
                if anterior and ini - anterior >= timedelta(minutes=10):
                    passos.append(Passo("Intervalo", anterior))
                nome = (b.get("display_name") or "Aula").split(":")[0].strip()
                passos.append(Passo(nome, ini))
                anterior = fim
            cel = CELULAR["aula"]
        elif c["tipo"] == "cabelo":                          # 26/09: os serviços da vez (cabelo.py), valor na direita
            meta = json.loads(c["outing"]["metadata_json"] or "{}")
            passos = self._distribui([tuple(x) for x in meta.get("passos") or [["No salão", 95], ["Pagando", 5]]],
                                     c["inicio"], c["fim"])
            passos[-1].valor = meta.get("preco")
            cel = CELULAR["role"]
        elif c["tipo"] in LA_PASSOS:
            passos = self._distribui(list(LA_PASSOS[c["tipo"]]), c["inicio"], c["fim"])
            cel = CELULAR["aula"] if c["tipo"] in ("medico", "pronto_atendimento", "mercado_semana") else CELULAR["role"]
            if c["tipo"] == "manicure":                      # 26/09: o valor na direita, como o consumo do rolê
                from unhas import PRECO_SALAO
                passos[-1].valor = PRECO_SALAO
        elif c["tipo"] == "academia":
            rng = _rng(c["inicio"].date(), "treino")
            meio = rng.choice((("Musculação · pernas", 55), ("Musculação · superiores", 55), ("Funcional", 55)))
            passos = self._distribui([("Aquecendo na esteira", 15), meio, ("Abdominais", 15), ("Alongando", 15)],
                                     c["inicio"], c["fim"])
            cel = CELULAR["aula"]
        else:
            from consumo import plan
            for item in plan(c["outing"]):
                passos.append(Passo(item.nome + (" (dividiu)" if item.dividido else ""), item.at, valor=item.valor))
            import cinema
            s = cinema.sessao(self.db, c["outing"])
            if s:                                        # 27/09: "Refri" das 15:13 às 19:00 — o cinema tem sessão
                passos.append(Passo(cinema.passo_sessao(s), s["inicio"]))
                if c["fim"] - s["fim"] >= timedelta(minutes=15):
                    passos += self._distribui(list(cinema.DEPOIS), s["fim"], c["fim"])
                passos.sort(key=lambda p: p.inicio)
            cel = CELULAR["role"] if c["tipo"] != "freela" else CELULAR["aula"]
        fim_la = volta.start if volta else fim_real
        passos = self._reativa(c["key"], passos, fim_la)
        return Etapa("la", titulo, c["inicio"], fim_la, linha2=f"Volta pra casa às {aprox(fim_la)}",
                     lugar_key=c["place"], bairro=place["region"], com=com, celular=cel, passos=passos,
                     chave=f"la:{c['key']}")

    def _reativa(self, key: str, passos: list, fim_la: datetime) -> list:
        """Agenda reativa (26/09): pausa no banheiro e saída mais cedo aparecem nos passos."""
        try:
            from agenda_reativa import AgendaReativa
            r = AgendaReativa(self.db)
            info = r.interrupcao(key)
            pausas = r.pausas_de(key)
        except Exception:
            return passos
        if not info and not pausas:
            return passos
        out = list(passos)
        for p in pausas:
            ini, fim = datetime.fromisoformat(p["inicio"]), datetime.fromisoformat(p["fim"])
            texto = "Se tocando no banheiro" if p["motivo"] == "tesao" else "No banheiro"
            retoma = next((q for q in reversed(out) if q.inicio <= ini and not q.aviso), None)
            out.append(Passo(texto, ini))
            if retoma:
                out.append(Passo(retoma.texto, fim))
        out.sort(key=lambda q: q.inicio)
        if info:
            at = datetime.fromisoformat(info["at"])
            out = [q for q in out if q.inicio < at or q.aviso]
            out.append(Passo(f"Saindo mais cedo · {r.motivo_curto(info)}", at, aviso=True))
        return out

    def _saiu(self, key: str) -> Optional[dict]:
        if not key:
            return None
        try:
            from agenda_reativa import AgendaReativa
            return AgendaReativa(self.db).interrupcao(key)
        except Exception:
            return None

    # ------------------------------------------------------ consultas --
    def agora(self, now: datetime) -> Optional[Etapa]:
        for day in (now.date(), now.date() - timedelta(days=1)):
            for e in self.etapas(day, now):
                if e.inicio <= now < e.fim:
                    return e
        return None

    def passo_atual(self, etapa: Etapa, now: datetime) -> Optional[Passo]:
        atuais = [p for p in etapa.passos if p.inicio <= now and not p.aviso]
        return atuais[-1] if atuais else None

    def prep_activity(self, now: datetime) -> Optional[dict]:
        """Se ela está se arrumando agora: a atividade pro WorldState (e, por ele, pro chat)."""
        e = self.agora(now)
        if not e or e.tipo != "arrumando":
            return None
        passo = self.passo_atual(e, now)
        pra = "pra dormir" if e.prep_tipo == "dormir" else e.linha2.replace("Vai sair ", "pra sair ").split(" às ")[0]
        miudo = (passo.texto[:1].lower() + passo.texto[1:]) if passo else ""   # "descendo com o Milo", não "milo"
        texto = f"se arrumando {pra}" + (f" ({miudo})" if passo else "")
        return {"activity": texto, "place_key": "marina_apartment", "start_at": e.inicio.isoformat(),
                "end_at": e.fim.isoformat(), "passo": passo.texto if passo else "", "chave": e.chave,
                "prep_tipo": e.prep_tipo}

    # ------------------------------------------------------------ card --
    def card(self, now: datetime) -> Optional[dict]:
        """O card da aba Agora (layout D aprovado). None quando ela não está numa etapa."""
        dia = now.date()
        etapas = self.etapas(dia, now)
        if not any(e.inicio <= now < e.fim for e in etapas):
            ontem = self.etapas(dia - timedelta(days=1), now)
            if any(e.inicio <= now < e.fim for e in ontem):
                etapas = ontem
        atual = next((e for e in etapas if e.inicio <= now < e.fim), None)
        if not atual:
            return None
        pos = (now - atual.inicio).total_seconds() / max(1, (atual.fim - atual.inicio).total_seconds())
        grade = []
        if atual.tipo == "la":
            grade.append(["map-pin", "Onde", atual.bairro])
        if atual.tipo in ("caminho", "voltando"):
            grade.append(["car" if "arona" in atual.como or "ber" in atual.como else "bus", "Como", atual.como])
        if atual.com and atual.tipo in ("arrumando", "la"):
            grade.append(["users", "Com", _e(atual.com)])
        saiu = self._saiu(atual.compromisso)
        if saiu and atual.tipo in ("la", "voltando") and now >= datetime.fromisoformat(saiu["at"]):
            from agenda_reativa import AgendaReativa
            grade.append(["alert-circle", "Motivo", AgendaReativa.motivo_curto(saiu)])
        celular = atual.celular
        passo = self.passo_atual(atual, now)
        if atual.tipo == "la" and passo and (passo.texto.startswith("Vendo ") or passo.texto == "Na sessão"):
            celular = "Olha depois do filme"
        grade.append(["device-mobile", "Celular", celular])
        # linha do tempo: a cadeia do compromisso atual + a próxima etapa
        i = etapas.index(atual)
        ini = i
        while ini > 0 and etapas[ini - 1].fim >= etapas[ini].inicio - timedelta(minutes=1) and etapas[ini].tipo != "arrumando":
            ini -= 1
        fim = i
        while fim + 1 < len(etapas) and etapas[fim + 1].tipo != "arrumando":
            fim += 1
        if fim + 1 < len(etapas):
            fim += 1
        linha = []
        for e in etapas[ini:fim + 1]:
            estado = "feito" if e.fim <= now else "agora" if e is atual else "depois"
            item = {"texto": e.titulo, "hora": hora(e.inicio) if estado != "depois" else aprox(e.inicio),
                    "estado": estado, "valor": e.total if estado == "feito" else None, "passos": []}
            if e.tipo == "la" and estado == "feito":
                s = self._saiu(e.compromisso)
                if s:                                    # "Saiu 33min antes", embaixo de onde ela estava
                    sai = datetime.fromisoformat(s["sai"])
                    antes = duracao(datetime.fromisoformat(s["fim_original"]) - sai)
                    item["passos"].append({"texto": f"Saiu {antes} antes", "estado": "aviso", "valor": None,
                                           "hora": hora(sai)})
            if e is atual:
                atual_passo = self.passo_atual(e, now)
                for p in e.passos:
                    feito = p.inicio <= now
                    st = "aviso" if p.aviso and feito else "agora" if p is atual_passo else "feito" if feito else "depois"
                    if e.tipo == "la" and not feito and p.valor is not None:
                        continue                    # consumo só aparece depois de pedido
                    item["passos"].append({"texto": p.texto, "estado": st, "valor": p.valor if feito else None,
                                           "hora": hora(p.inicio) if feito else ""})
            linha.append(item)
        return {"titulo": atual.titulo, "linha2": atual.linha2,
                "barra": {"inicio": hora(atual.inicio), "fim": aprox(atual.fim), "pct": round(max(0, min(1, pos)) * 100),
                          "meio": f"há {duracao(now - atual.inicio)}" + ("" if atual.tipo == "la" else f" · faltam ~{duracao(atual.fim - now)}")},
                "grade": grade, "linha": linha}

    # ------------------------------------------------------ card em casa --
    REFEICAO = {"cafe": "Tomando café", "almoco": "Almoçando", "lanche": "Beliscando", "jantar": "Jantando"}

    def _snapshot(self) -> Optional[dict]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM world_state ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def _desde(self, snap: dict) -> datetime:
        """28/09, 05:55: "Dormindo · desde 05:46 · 11min" com ela dormindo desde 00:29 — o world_state grava um
        retrato novo por hora com a mesma atividade. O começo é o do primeiro retrato da sequência."""
        t0 = datetime.fromisoformat(snap["observed_at"])
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT activity, location_place_id, observed_at FROM world_state WHERE id<=? "
                                "ORDER BY id DESC LIMIT 400", (snap["id"],)).fetchall()
        for r in rows:
            if r["activity"] != snap["activity"] or r["location_place_id"] != snap["location_place_id"]:
                break
            t0 = min(t0, datetime.fromisoformat(r["observed_at"]))
        return t0

    def _marcos(self, now: datetime) -> list[tuple[datetime, str]]:
        """O que acontece no dia, em ordem (pra linha do tempo em casa)."""
        dia = now.date() if now.hour >= 4 else now.date() - timedelta(days=1)
        out: list[tuple[datetime, str]] = []
        try:                                             # o que ela comeu de verdade + o que ainda vem
            from meals import Meals
            meals = Meals(self.db)
            feitas = meals.eaten_today(now)
            chaves = {e["event_key"] for e in feitas}
            for e in feitas:
                if not (e["summary"] or "").startswith("Pulou"):
                    kind = e["event_key"].split(":")[2]
                    out.append((datetime.fromisoformat(e["event_at"]), self.REFEICAO.get(kind, "Comendo")))
            for s in meals.day_plan(dia):
                if not s.skipped and s.key not in chaves and s.at > now:
                    out.append((s.at, self.REFEICAO.get(s.kind, "Comendo")))
        except Exception:
            pass
        try:
            from tempo_livre import TempoLivre
            out += [(b.inicio, b.texto) for b in TempoLivre(self.db).do_dia(now)]
        except Exception:
            pass
        try:
            for e in self.etapas(dia, now):
                out.append((e.inicio, e.titulo))
        except Exception:
            pass
        try:
            from watch import Watching
            plano = Watching(self.db).night_plan(dia)
            if plano:
                out.append((plano["start"], "Vendo série"))
        except Exception:
            pass
        try:
            from sleep_plan import SleepPlan
            out.append((SleepPlan(self.db).bed(dia), "Dormindo"))
        except Exception:
            pass
        return sorted(out, key=lambda m: m[0])

    def _passos_midia(self, bloco, now: datetime) -> tuple[list, list]:
        """Música: as faixas (as 2 que tocaram, a de agora e a próxima). Leitura: páginas.
        Jogo: os lances de verdade e o placar."""
        if bloco.faixas:
            idx = max((i for i, f in enumerate(bloco.faixas) if datetime.fromisoformat(f["at"]) <= now), default=0)
            janela = bloco.faixas[max(0, idx - 2): idx + 2]
            return [Passo(f["nome"], datetime.fromisoformat(f["at"])) for f in janela], []
        if bloco.leitura:
            lt = bloco.leitura
            frac = max(0.0, min(1.0, (now - bloco.inicio).total_seconds()
                                / max(60.0, (bloco.fim - bloco.inicio).total_seconds())))
            pag = round(lt["pag_ini"] + (lt["pag_fim"] - lt["pag_ini"]) * frac)
            passos = [Passo(f"Começou na pág. {lt['pag_ini']}" if lt["pag_ini"] else "Começou", bloco.inicio)]
            if bloco.inicio < now:
                passos.append(Passo(f"Pág. {pag}", now))
            passos.append(Passo("Terminar o volume" if lt["terminou"] else f"Até a pág. ~{lt['pag_fim']}", bloco.fim))
            return passos, [["book", "Progresso", f"pág. {pag} de {lt['pags']}"]]
        if bloco.jogo:
            from futebol import Futebol
            fut = Futebol(self.db)
            j = next((x for x in fut.jogos() if x["id"] == bloco.jogo), None)
            if not j:
                return [], []
            ini = datetime.fromisoformat(j["inicio"])
            lances = [x for x in fut.lances(j)["lances"] if datetime.fromisoformat(x["at"]) <= now]
            passos = [Passo(x["texto"] + (f" · {x['minuto']}" if x["texto"].startswith(("Gol", "Expulsão")) else ""),
                            datetime.fromisoformat(x["at"])) for x in lances]
            if not passos:
                passos = [Passo("1º tempo", ini)]
            if not any(p.texto == "Fim de jogo" for p in passos):
                passos.append(Passo("Fim de jogo", bloco.fim))
            return passos[-5:], [["ball-football", "Placar", fut.placar_texto(j)]]
        return [], []

    def card_casa(self, now: datetime, celular: str) -> Optional[dict]:
        """Fora de uma saída: "Em casa" (ou "Se alimentando", ou o passeio do Milo)."""
        snap = self._snapshot()
        if not snap:
            return None
        act = (snap.get("activity") or "").strip()
        low = act.casefold()
        plano = json.loads(snap.get("current_plan_json") or "null") or {}
        fonte = json.loads(snap.get("source_json") or "{}") or {}
        inicio = datetime.fromisoformat(plano["start_at"]) if plano.get("start_at") else None
        fim = datetime.fromisoformat(plano["end_at"]) if plano.get("end_at") else None
        if not fim and fonte.get("slot_end"):
            fim = datetime.fromisoformat(fonte["slot_end"])
        desde = self._desde(snap)
        titulo, linha2, comodo, passos = "Em casa", act[:1].upper() + act[1:], None, []
        grade_extra = []
        from tempo_livre import TempoLivre
        bloco = TempoLivre(self.db).atual(now) if low.startswith("em casa, ") else None
        if bloco:
            linha2, comodo, inicio, fim = bloco.texto, bloco.comodo_nome, bloco.inicio, bloco.fim
            passos, grade_extra = self._passos_midia(bloco, now)
            if bloco.faixas:                              # a linha 2 acompanha o artista que está tocando
                from musica import Musica
                tocando = Musica.tocando(bloco.faixas, now)
                if tocando:
                    linha2 = f"Ouvindo {tocando['artista']}"
        elif any(x in low for x in ("jantando", "almoçando", "almocando", "lanchando", "beliscando", "café da manhã",
                                    "comendo")):
            from meals import meal_kind, Meals
            titulo, comodo = "Se alimentando", "Sala"
            kind = next((k for k, w in (("lanche", "beliscando"), ("lanche", "lanchando"), ("jantar", "jantando"),
                                        ("almoco", "almo"), ("cafe", "café")) if w in low), None) or meal_kind(inicio or now)
            linha2 = self.REFEICAO.get(kind, "Comendo")
            slot = None
            ultima = Meals(self.db)._ultima(now)            # a refeição de verdade (prato, e quando largou)
            meta = json.loads((ultima or {}).get("metadata_json") or "{}")
            if ultima and ultima["end_at"] and meta.get("prato") and now < datetime.fromisoformat(ultima["end_at"]):
                from meals import MealSlot
                t0, t1 = datetime.fromisoformat(ultima["event_at"]), datetime.fromisoformat(ultima["end_at"])
                slot = MealSlot(kind, "", t0, int((t1 - t0).total_seconds() // 60), "casa", meta["prato"])
                inicio, fim = t0, t1
            if slot is None:
                slot = next((s for s in Meals(self.db).day_plan(now.date()) if s.at <= now <= s.end), None)
            prato = slot.dish if slot else (low.split("comendo o ", 1)[1].split(" que ")[0].split(" em casa")[0]
                                             if "comendo o " in low else "")
            if prato:
                cozinhou = slot is not None and prato in _jantar_cozinha()
                t0 = inicio or (slot.at if slot else now)
                if cozinhou:
                    passos.append(Passo(f"Preparando o {linha2.split()[-1].lower()}"
                                        if kind in ("jantar", "almoco") else "Preparando", t0 - timedelta(minutes=25)))
                passos.append(Passo(prato[:1].upper() + prato[1:], t0))
                if slot and not inicio:
                    inicio, fim = slot.at, slot.end
        elif "tomando banho" in low:
            linha2, comodo = "Tomando banho", "Banheiro"
        elif low.startswith("vendo "):
            linha2, comodo = "Vendo " + act[6:].replace(" no sofá", ""), "Sala"
        elif "trabalho de" in low:
            linha2, comodo = act[:1].upper() + act[1:].replace(" em casa", ""), "Closet"
        elif low.startswith("dormindo") or "acordou de madrugada" in low:
            linha2, comodo = "Dormindo", "Quarto"
        elif low.startswith(("acordando", "acabou de acordar")):
            linha2, comodo = "Acordando", "Quarto"
        elif "academia do prédio" in low:
            linha2, comodo = "Treinando", "Academia do prédio"
        elif "milo" in low:
            rapidinho = "rapidinho" in low
            titulo = "Na calçada" if rapidinho else "Na Enseada"
            t0 = inicio or desde
            t1 = fim or t0 + timedelta(minutes=12 if rapidinho else 30)
            inicio, fim = t0, t1
            linha2 = f"Volta pra casa às {aprox(t1)}"
            passos = self._distribui([("Colocando a coleira", 10), ("Descendo", 10),
                                      ("Xixi do Milo" if rapidinho else "Passeando", 70), ("Subindo", 10)], t0, t1)
            grade_extra = [["dog", "Com", "Milo"]]
        elif "academia" in low:
            titulo, linha2 = "Na academia", "Treinando"
        elif "mercado" in low:
            titulo, linha2 = "No mercado", "Fazendo as compras da semana"
        grade = [["map-pin", "Onde", "Botafogo"]]
        if comodo:
            grade.append(["door", "Cômodo", comodo])
        grade += grade_extra
        grade.append(["device-mobile", "Celular", celular])
        if fim and not inicio and fim > now:              # 26/09: tinha fim e não tinha início → sem barra
            inicio = desde
        if inicio and fim and fim > now:
            pos = (now - inicio).total_seconds() / max(1, (fim - inicio).total_seconds())
            barra = {"inicio": hora(inicio), "fim": aprox(fim), "pct": round(max(0, min(1, pos)) * 100),
                     "meio": f"há {duracao(now - inicio)} · faltam ~{duracao(fim - now)}"}
        else:
            t0 = inicio or desde
            barra = {"inicio": "", "fim": "", "pct": None, "meio": "", "desde": hora(t0), "duracao": duracao(now - t0)}
        # linha do tempo: o que veio antes e o que vem
        atual_txt = "Se alimentando" if titulo == "Se alimentando" else linha2 if titulo == "Em casa" else titulo
        marcos = [m for m in self._marcos(now) if abs((m[0] - (inicio or desde)).total_seconds()) > 60 or m[1] != atual_txt]
        antes = [m for m in marcos if m[0] < (inicio or desde)][-1:]
        depois = [m for m in marcos if m[0] > now][:2]
        linha = [{"texto": t, "hora": hora(a), "estado": "feito", "valor": None, "passos": []} for a, t in antes]
        item = {"texto": atual_txt, "hora": hora(inicio or desde),
                "estado": "agora", "valor": None, "passos": []}
        for p in passos:
            feito = p.inicio <= now
            item["passos"].append({"texto": p.texto, "estado": "feito" if feito else "depois",
                                   "valor": None, "hora": hora(p.inicio) if feito else ""})
        if item["passos"]:
            atuais = [x for x in item["passos"] if x["estado"] == "feito"]
            if atuais:
                atuais[-1]["estado"] = "agora"
        linha.append(item)
        linha += [{"texto": t, "hora": aprox(a), "estado": "depois", "valor": None, "passos": []} for a, t in depois]
        return {"titulo": titulo, "linha2": linha2, "barra": barra, "grade": grade, "linha": linha}


def _jantar_cozinha() -> set:
    try:
        from meals import MENU
        return set(MENU.get("jantar_cozinha", ())) | set(MENU.get("almoco_casa", ()))
    except Exception:
        return set()
