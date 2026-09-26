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
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# nome curto (título e chat) e preposição
CURTO = {"quartinho_bar": "no Quartinho", "starbucks_shopping_gavea": "no Starbucks", "puc_rio": "na PUC",
         "shopping_gavea": "no Shopping da Gávea", "copacabana_beach": "na praia", "ipanema_beach": "na praia",
         "leblon_beach": "na praia", "boutique_agency": "na agência", "bodytech_sao_clemente": "na academia"}
COMO = {"onibus": "Ônibus", "metro": "Metrô", "metro_onibus": "Metrô e ônibus", "uber": "Uber", "a_pe": "A pé"}

# passos do Se arrumando: (texto, peso). O último passo depende do transporte.
PREP = {
    "noite": (("Tomando banho", 25), ("Secando cabelo", 20), ("Fazendo maquiagem", 25), ("Escolhendo roupa", 20)),
    "encontro": (("Tomando banho", 40), ("Fazendo maquiagem", 25), ("Escolhendo roupa", 25)),
    "freela": (("Tomando banho", 50), ("Escolhendo roupa", 35)),        # sem make: é feita lá
    "faculdade": (("Tomando café", 25), ("Tomando banho", 35), ("Escolhendo roupa", 25)),
    "praia": (("Colocando biquíni", 50), ("Passando protetor", 40)),
    "dormir": (("Tirando maquiagem", 25), ("Tomando banho", 50), ("Colocando pijama", 25)),
}
PREP_MIN = {"noite": (60, 90), "encontro": (30, 45), "freela": (40, 55), "praia": (15, 20), "dormir": (30, 45)}
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
               "Humaitá": "no Humaitá", "Flamengo": "no Flamengo", "Centro": "no Centro"}


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
                    else "noite" if inicio.hour >= 18 else "encontro")
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
                inicio = ida.start - timedelta(minutes=rng.randint(*PREP_MIN[c["tipo"]]))
            inicio = max(inicio, fim_anterior)
            if inicio < ida.start:
                passos = list(PREP[c["tipo"]])
                if c["tipo"] == "faculdade" and rng.random() < FACULDADE_CABELO_CHANCE:
                    passos.insert(2, ("Secando cabelo", 15))
                final = ("Esperando carona" if ida.mode == "carona" else
                         "Chamando uber" if ida.mode in ("uber", "uber_dividido") else "Saindo")
                out.append(Etapa("arrumando", "Se arrumando", inicio, ida.start,
                                 linha2=f"Vai sair {self._pra(place['name'])} às {aprox(ida.start)}",
                                 lugar_key="marina_apartment", com=com, celular=CELULAR["arrumando"],
                                 passos=self._distribui(passos + [(final, 10)], inicio, ida.start),
                                 chave=f"prep:{c['key']}", prep_tipo=c["tipo"]))
                teve_make = teve_make or c["tipo"] in ("noite", "encontro")
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
                out.append(Etapa("arrumando", "Se arrumando", inicio, bed, linha2=f"Vai dormir às {aprox(bed)}",
                                 lugar_key="marina_apartment", celular=CELULAR["arrumando"],
                                 passos=self._distribui(list(passos), inicio, bed), chave=f"prep:dormir:{day}",
                                 prep_tipo="dormir"))
        return out

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
        no = CURTO.get(c["place"], f"no {place['name']}")          # "no Quartinho", "na PUC"
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
        curto = CURTO.get(c["place"], f"no {place['name']}")
        titulo = curto[:1].upper() + curto[1:]
        passos: list[Passo] = []
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
        else:
            from consumo import plan
            for item in plan(c["outing"]):
                passos.append(Passo(item.nome + (" (dividiu)" if item.dividido else ""), item.at, valor=item.valor))
            cel = CELULAR["role"] if c["tipo"] != "freela" else CELULAR["aula"]
        fim_la = volta.start if volta else c["fim"]
        return Etapa("la", titulo, c["inicio"], fim_la, linha2=f"Volta pra casa às {aprox(fim_la)}",
                     lugar_key=c["place"], bairro=place["region"], com=com, celular=cel, passos=passos,
                     chave=f"la:{c['key']}")

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
        texto = f"se arrumando {pra}" + (f" ({passo.texto.lower()})" if passo else "")
        return {"activity": texto, "place_key": "marina_apartment", "start_at": e.inicio.isoformat(),
                "end_at": e.fim.isoformat(), "passo": passo.texto if passo else "", "chave": e.chave}

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
            grade.append(["geo-alt", "Onde", atual.bairro])
        if atual.tipo in ("caminho", "voltando"):
            grade.append(["car-front" if "arona" in atual.como or "ber" in atual.como else "bus-front", "Como", atual.como])
        if atual.com and atual.tipo in ("arrumando", "la"):
            grade.append(["people", "Com", _e(atual.com)])
        grade.append(["phone", "Celular", atual.celular])
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
