"""Atraso de verdade (Patrick, 28/09 — frente do mundo).

Antes só a aula "atrasava", e desamarrado: perder o despertador gravava "chegou 12 min atrasada" no banco, mas a ida
pra PUC tinha hora fixa, o card mostrava ela saindo na hora e, se ela acordava depois da hora de sair, o Se arrumando
sumia. Rolê, freela, consulta e salão nunca atrasavam, e o imprevisto do caminho não empurrava a chegada.

Agora o que atrasa acontece e empurra a saída e a chegada (`commute.legs_on` aplica o que está gravado aqui):
* **despertador** (dia de aula, na hora em que ela acorda): se arruma correndo (30 min, mais o café se tomou); se nem
  assim dá, sai atrasada;
* **na hora de sair** (decidido nesse momento, pelo que aconteceu no Se arrumando): enrolou pelo que sente (sono, sem
  pique, insegura com a roupa, empolgada com o look), o Milo aprontou, ficou no celular com o Patrick, voltou pra
  pegar algo que esqueceu;
* **no caminho** (quando ela sai): o imprevisto custa minutos (`commute.INCIDENT_DELAY`) e chuva forte piora o trânsito.

Só atrasa o que tem hora e alguém esperando: aula, rolê/jogo, freela, médico e salão (academia, Milo, café sozinha só
saem mais tarde). O compromisso começa sem ela (`CalendarWorld.current` não a põe lá antes de chegar), o card mostra a
saída e a chegada de verdade, o prompt sabe, ela avisa o Patrick pelo que sente (iniciativa `atraso`) e, ao chegar,
vira acontecimento ("atraso:…" → frustração). Atraso grande (40 min ou mais): ela pesa se ainda vale ir (agenda viva);
na aula, desiste só das que perderia. Freela, médico e salão: vai mesmo atrasada.

Estado em world_bootstrap["atraso:<dia>"] = {"legs": {leg_key: {...}}, "aviso": {...}}; cada parte é decidida uma vez,
no seu momento, e congelada.
"""
from __future__ import annotations

import json
import logging
import random
import threading
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

CORRENDO_MIN = 30                  # se arrumar correndo pra aula (banho rápido, roupa, sai)
CARENCIA_MIN = 4                   # atrasinho que ela compensa andando mais rápido
GRANDE_MIN = 40                    # a partir daqui ela pesa se ainda vale ir
AVISO_MIN = 10                     # abaixo disso nem vira assunto
AVISO_FORTE_MIN = 25               # atraso que ela sempre conta (se não estiver chateada com ele)
AVISO_VALIDO = timedelta(minutes=45)
CONVERSA_JANELA = timedelta(minutes=60)
CONVERSA_MIN_MSGS = 5
ESQUECEU_CHANCE = 0.04
ESQUECEU_CHANCE_CORRENDO = 0.10
CHUVA_FATOR = 0.25
PREFIXOS = {"puc:": "aula", "outing:": "role", "freela:": "freela", "medico:": "medico", "unhas:": "salao",
            "cabelo:": "salao"}
SOCIAIS = ("role", "jogo")
ESQUECEU = {"aula": ("a carteirinha da PUC", "o carregador", "o fone"), "freela": ("o book", "o carregador"),
            "role": ("a chave", "o batom", "o cartão"), "jogo": ("a chave", "o cartão")}
MILO_APRONTA = {"deitou em cima da roupa": ("Milo deitou na roupa", "o Milo deitou em cima da roupa que ela ia usar"),
                "roubou uma meia": ("Milo roubou uma meia", "o Milo roubou uma meia e ela teve que correr atrás"),
                "xixi no tapete": ("Milo fez xixi no tapete", "o Milo fez xixi no tapete do banheiro")}

_local = threading.local()


def _rng(salt: str) -> random.Random:
    return random.Random(f"marina-atraso:{salt}")


def tipo_de(compromisso: str) -> Optional[str]:
    for prefixo, tipo in PREFIXOS.items():
        if compromisso.startswith(prefixo):
            if tipo == "role" and ":j" in compromisso:
                return "jogo"
            return tipo
    return None


def _key(day: date) -> str:
    return f"atraso:{day.isoformat()}"


def _load(db, day: date) -> dict:
    with db.get_connection() as conn:
        row = conn.execute("SELECT value FROM world_bootstrap WHERE key=?", (_key(day),)).fetchone()
    try:
        return json.loads(row["value"]) if row else {}
    except (TypeError, ValueError):
        return {}


def _save(db, day: date, st: dict) -> None:
    with db.get_connection() as conn:
        conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES (?, ?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                     (_key(day), json.dumps(st, ensure_ascii=False), datetime.now().isoformat()))
        conn.commit()


def _dt(raw) -> Optional[datetime]:
    return datetime.fromisoformat(raw) if raw else None


# ------------------------------------------------------------------ contas --
def saida_min(e: dict) -> int:
    return int((e.get("acordou") or {}).get("min", 0)) + int((e.get("saida") or {}).get("min", 0))


def caminho_min(e: dict, now: Optional[datetime] = None) -> int:
    c = e.get("caminho") or {}
    if now is not None and c.get("at") and now < datetime.fromisoformat(c["at"]):
        return 0                                       # ainda não aconteceu
    return int(c.get("min", 0))


def minutos(e: dict, now: Optional[datetime] = None) -> int:
    """Quanto ela chega atrasada (com `now`: o que já se sabe a essa hora)."""
    return saida_min(e) + caminho_min(e, now)


def chegada(e: dict, now: Optional[datetime] = None) -> datetime:
    return datetime.fromisoformat(e["inicio"]) + timedelta(minutes=minutos(e, now))


def causas(e: dict, now: Optional[datetime] = None) -> list[str]:
    """O porquê, no jeito do prompt e do acontecimento ("perdeu o despertador e o ônibus demorou")."""
    out = []
    a = e.get("acordou") or {}
    if a.get("min"):
        out.append("perdeu o despertador")
    out += [c[2] for c in (e.get("saida") or {}).get("causas", [])]
    if caminho_min(e, now):
        out += [c[2] for c in (e.get("caminho") or {}).get("causas", [])]
    return out


def aprox(n: int) -> str:
    """Soak, dia 4 (02/10, 20:30): "atrasada 22 min" — número de sistema na boca dela. No prompt vai redondo."""
    return "uns minutinhos" if n < 8 else f"uns {max(10, round(n / 5) * 5)} min"


def _junta(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1] if itens else ""


# -------------------------------------------------------- trechos (commute) --
def aplica(db, day: date, legs: list) -> list:
    """Empurra as idas atrasadas (chamado por `Commute.legs_on`). Só lê o que já foi decidido."""
    if getattr(_local, "busy", False):
        return legs
    st = _load(db, day).get("legs") or {}
    if not st:
        return legs
    from dataclasses import replace
    out = []
    for leg in legs:
        e = st.get(leg.key)
        if not e or leg.direction != "ida" or leg.origem or e.get("desistiu") \
                or e.get("saida_planejada") != leg.start.isoformat():
            out.append(leg)
            continue
        s, c = saida_min(e), caminho_min(e)
        avisos = []
        a = e.get("acordou") or {}
        if a.get("min"):
            avisos.append((datetime.fromisoformat(a["at"]), "Perdeu o despertador"))
        sd = e.get("saida") or {}
        for causa in sd.get("causas", []):
            avisos.append((datetime.fromisoformat(sd["at"]), causa[1]))
        cm = e.get("caminho") or {}
        for causa in cm.get("causas", []):
            if causa[0] == "chuva":                       # o imprevisto já aparece pelo próprio trecho
                avisos.append((datetime.fromisoformat(cm["at"]), causa[1]))
        leg = replace(leg, start=leg.start + timedelta(minutes=s), end=leg.end + timedelta(minutes=s + c),
                      incident_at=leg.incident_at + timedelta(minutes=s) if leg.incident_at else None,
                      atraso=s + c, saida_atraso=s, saida_extra=int(sd.get("min", 0)), caminho_atraso=c,
                      caminho_at=_dt(cm.get("at")) if c else None, avisos=tuple(avisos))
        out.append(leg)
    return out


def nao_chegou(db, now: datetime, compromisso: dict) -> bool:
    """O compromisso já começou, mas ela ainda está a caminho (ou se arrumando): não está lá."""
    st = _load(db, now.date()).get("legs") or {}
    for e in st.values():
        if e.get("desistiu") or not minutos(e):
            continue
        if not (datetime.fromisoformat(e["inicio"]) <= now < chegada(e)):
            continue
        k = e.get("compromisso", "")
        if k.startswith("puc:"):
            if compromisso.get("academic_block_id") or compromisso.get("place_key") == "puc_rio":
                return True
        elif k and k == compromisso.get("source_key"):
            return True
    return False


class Atraso:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------ fontes --
    def _feeling(self, now: datetime):
        from emotion import EmotionEngine
        return EmotionEngine(self.db).feeling(now)

    def _legs(self, day: date) -> list:
        from commute import Commute
        return [l for l in Commute(self.db).legs_on(day, planejado=True)
                if l.direction == "ida" and not l.origem and tipo_de(l.compromisso)]

    def _onde(self, leg) -> str:
        if leg.compromisso.startswith("puc:"):
            try:
                from academic_life import AcademicLife
                blocos = sorted(AcademicLife(self.db).blocks_on(leg.end.date()), key=lambda b: b["start_at"])
                nome = (blocos[0].get("display_name") or "").split(":")[0].strip() if blocos else ""
                return f"na aula de {nome}" if nome else "na aula"
            except Exception:
                return "na aula"
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT location_key FROM eventos_pendentes WHERE source_key=?",
                               (leg.compromisso,)).fetchone()
        lugar = row["location_key"] if row else ""
        from agenda import CURTO
        if lugar in CURTO:
            return CURTO[lugar]
        from commute import _pra
        return _pra(leg.destination.split(" ", 1)[-1]).replace("pra ", "na ", 1).replace("pro ", "no ", 1)

    # ------------------------------------------------------------- mundo --
    def materialize(self, now: datetime) -> int:
        """Decide, cada coisa no seu momento: despertador (ao acordar), saída (na hora de sair), caminho (ao sair);
        pesa o atraso grande, decide o aviso e, na chegada, vira acontecimento."""
        with self.db.get_connection() as conn:
            if not conn.execute("SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done'").fetchone():
                return 0
        if getattr(_local, "busy", False):
            return 0
        _local.busy = True
        try:
            return self._materialize(now)
        finally:
            _local.busy = False

    def _materialize(self, now: datetime) -> int:
        day = now.date()
        st = _load(self.db, day)
        legs_st = st.setdefault("legs", {})
        mudou = 0
        for leg in self._legs(day):
            e = legs_st.get(leg.key)
            if e and e.get("saida_planejada") != leg.start.isoformat() and not e.get("registrado"):
                e = None                                  # o compromisso mudou (remarcou, pulou a 1ª aula)
            if e is None:
                if now < leg.start - timedelta(hours=4):
                    continue
                e = {"compromisso": leg.compromisso, "tipo": tipo_de(leg.compromisso),
                     "saida_planejada": leg.start.isoformat(), "inicio": leg.end.isoformat(),
                     "dur": int((leg.end - leg.start).total_seconds() // 60), "onde": self._onde(leg)}
                legs_st[leg.key] = e
                mudou += 1
            if e.get("registrado") or e.get("desistiu"):
                continue
            antes = json.dumps(e, sort_keys=True)
            if e["tipo"] == "aula" and "acordou" not in e:
                e.update(self._despertador(leg, now))
            t_saida = leg.start + timedelta(minutes=int((e.get("acordou") or {}).get("min", 0)))
            if "saida" not in e and now >= t_saida and ("acordou" in e or e["tipo"] != "aula"):
                e["saida"] = self._na_hora_de_sair(leg, e, t_saida)
            if "saida" in e and "caminho" not in e:
                e["caminho"] = self._caminho(leg, e)
            if minutos(e, now) >= GRANDE_MIN and not e.get("pesou") and now < chegada(e):   # sabe assim que acorda
                e["pesou"] = True
                self._pesa(leg, e, now)
            if not e.get("desistiu") and minutos(e, now) >= AVISO_MIN and not e.get("aviso_decidido") \
                    and now < chegada(e):
                e["aviso_decidido"] = True
                if self._conta(e, now):
                    st["aviso"] = {"leg": leg.key, "em": now.isoformat(timespec="minutes"), "enviado": False,
                                   "detail": self.detalhe(e, now)}
            if "saida" in e and "caminho" in e and now >= chegada(e) and not e.get("registrado"):
                e["registrado"] = True
                if minutos(e) > 0:
                    self._registra(leg, e)
            if json.dumps(e, sort_keys=True) != antes:
                mudou += 1
        if mudou:
            _save(self.db, day, st)
        return mudou

    def _despertador(self, leg, now: datetime) -> dict:
        from sleep_plan import SleepPlan
        sp = SleepPlan(self.db)
        wake = sp.wake(leg.start.date())
        if now < wake:
            return {}
        over = sp.overslept(leg.start.date())
        if not over:
            return {"acordou": {"min": 0}}
        pronta = wake + timedelta(minutes=CORRENDO_MIN)
        try:
            from meals import Meals
            cafe = next((s for s in Meals(self.db).day_plan(leg.start.date())
                         if s.kind == "cafe" and s.where == "casa" and not s.skipped and s.at < leg.start), None)
            if cafe:
                pronta += cafe.end - cafe.at
        except Exception:
            logger.debug("atraso.cafe", exc_info=True)
        falta = max(0, int((pronta - leg.start).total_seconds() // 60))
        return {"acordou": {"min": falta if falta >= CARENCIA_MIN else 0, "at": wake.isoformat(), "over": over}}

    def _na_hora_de_sair(self, leg, e: dict, t: datetime) -> dict:
        """O que segurou a saída, decidido na hora de sair (pelo que ela sente e pelo que aconteceu)."""
        tipo = e["tipo"]
        causas: list[list] = []
        total = 0
        try:
            f = self._feeling(t)
        except Exception:
            logger.debug("atraso.feeling", exc_info=True)
            f = None
        enrolou = self._enrolou(tipo, f, leg.key)
        if enrolou:
            total += enrolou[0]
            causas.append(["enrolou", enrolou[1], enrolou[2]])
        milo = self._milo(t)
        if milo:
            total += milo[0]
            causas.append(["milo", milo[1], milo[2]])
        conversa = self._conversa(t)
        if conversa and tipo != "freela":
            total += conversa
            causas.append(["conversa", "No celular com o Patrick", "ficou no celular conversando com o Patrick"])
        rng = _rng(f"{leg.key}:esqueceu")
        correndo = bool((e.get("acordou") or {}).get("over")) or bool(f and (getattr(f, "hours_slept", None) or 9) < 6)
        if rng.random() < (ESQUECEU_CHANCE_CORRENDO if correndo else ESQUECEU_CHANCE):
            coisa = rng.choice(ESQUECEU.get(tipo, ("a chave", "o carregador")))
            total += rng.randint(5, 8)
            causas.append(["esqueceu", f"Voltou pra pegar {coisa}", f"saiu e voltou pra pegar {coisa}"])
        if total < CARENCIA_MIN:
            return {"min": 0, "at": t.isoformat(), "causas": []}
        return {"min": min(total, 45), "at": t.isoformat(), "causas": causas}

    @staticmethod
    def _enrolou(tipo: str, f, salt: str) -> Optional[tuple[int, str, str]]:
        """Enrolar se arrumando vem do que ela sente (nunca sorteio): sono, sem pique, insegura, empolgada."""
        if f is None:
            return None
        fatores = []
        dormiu = getattr(f, "hours_slept", None)
        if dormiu is not None and dormiu < 6:
            fatores.append(((6 - dormiu) * 0.2, "Lerda de sono", "tava lerda de sono"))
        energia = getattr(f, "energy", 0.6)
        if energia < 0.4:
            fatores.append(((0.4 - energia) * 1.2, "Sem pique pra se arrumar", "tava sem pique nenhum"))
        eps = getattr(f, "episodes", None) or []
        social = tipo in SOCIAIS
        if any(ep.family == "vergonha" for ep in eps) or (social and getattr(f, "cycle_phase", "") == "tpm"):
            fatores.append((0.35, "Trocou de roupa três vezes", "trocou de roupa três vezes, insegura com o look"))
        if social and any(ep.family == "alegria" and ep.intensity >= 0.3 for ep in eps):
            fatores.append((0.25, "Trocou de look", "tava empolgada e trocou de look"))
        if social:
            fatores.append((0.1, "Enrolou se arrumando", "enrolou se arrumando"))   # rolê carioca
        if not fatores:
            return None
        score = sum(x[0] for x in fatores)
        score *= 0.4 if tipo == "freela" else 0.8 if tipo in ("aula", "medico") else 1.0
        score += (_rng(f"{salt}:enrolou").random() - 0.5) * 0.16
        if score < 0.3:
            return None
        _, curto, longo = max(fatores, key=lambda x: x[0])
        return 6 + round(24 * min(1.0, (score - 0.3) / 0.5)), curto, longo

    def _milo(self, t: datetime) -> Optional[tuple[int, str, str]]:
        try:
            from milo import Milo
            plano = Milo(self.db).day_plan(t.date())
        except Exception:
            return None
        for item in plano:
            if not item["key"].endswith(":arte") or not (t - CONVERSA_JANELA <= item["at"] <= t):
                continue
            for trecho, (curto, longo) in MILO_APRONTA.items():
                if trecho in item["summary"]:
                    return _rng(item["key"]).randint(5, 10), curto, longo
        return None

    def _conversa(self, t: datetime) -> int:
        with self.db.get_connection() as conn:
            n = conn.execute("SELECT COUNT(*) FROM conversas WHERE role='user' AND timestamp>=? AND timestamp<=?",
                             ((t - CONVERSA_JANELA).isoformat(), t.isoformat())).fetchone()[0]
        return min(15, round(n * 1.5)) if n >= CONVERSA_MIN_MSGS else 0

    def _caminho(self, leg, e: dict) -> dict:
        s = saida_min(e)
        causas, total, at = [], 0, None
        if leg.incident and leg.incident_at:
            from commute import INCIDENT_DELAY
            from agenda import IMPREVISTO
            d = INCIDENT_DELAY.get(leg.incident, 0)
            if d:
                total += d
                at = leg.incident_at + timedelta(minutes=s)
                curto = IMPREVISTO.get(leg.incident, leg.incident)
                causas.append(["imprevisto", curto, leg.incident.replace("uns 20 minutos", "demais")])
        if leg.mode in ("uber", "uber_dividido", "onibus", "metro_onibus", "carona"):
            try:
                from commute import Commute
                if Commute(self.db)._heavy_rain(leg.start + timedelta(minutes=s)):
                    total += max(3, round(e["dur"] * CHUVA_FATOR))
                    meio = leg.start + timedelta(minutes=s + e["dur"] // 2)
                    at = min(at, meio) if at else meio
                    causas.append(["chuva", "Trânsito da chuva", "o trânsito tava horrível com a chuva"])
            except Exception:
                logger.debug("atraso.chuva", exc_info=True)
        if not total:
            return {"min": 0}
        return {"min": total, "at": at.isoformat(), "causas": causas}

    # ------------------------------------------------------- atraso grande --
    def _pesa(self, leg, e: dict, now: datetime) -> None:
        """Atraso grande: ainda vale ir? Pesa pelo que ela sente (agenda viva). Freela, médico e salão: vai."""
        if e["tipo"] not in ("aula", "role", "jogo"):
            return
        try:
            from agenda_viva import AgendaViva, Avaliacao, PESO, _jitter
            viva = AgendaViva(self.db)
            it = self._item(leg, e, now)
            if not it:
                return
            n = minutos(e, now)
            aval = viva.disp.avaliar("aula" if e["tipo"] == "aula" else "role", now, com=it["com"])
            fator = ("atraso", f"ia chegar {n} min atrasada", -round(0.006 * (n - 30) + 0.25, 3))
            aval = Avaliacao(aval.vontade, [fator, *aval.fatores])
            vontade = aval.vontade - 0.006 * (n - 30) + _jitter(f"atraso:{leg.key}")
            st = viva._state()
            peso = PESO["aula" if e["tipo"] == "aula" else "role"]
            if e["tipo"] == "aula" and viva._peso(it, aval, now, st) < 0:
                return                                    # já matou aula essa semana: vai assim mesmo
            if vontade >= peso:
                return
            res = viva._desiste(it, aval, now, st)
            viva._save(st, now)
            if res:
                e["desistiu"] = True
                logger.info("atraso.desistiu key=%s min=%s vontade=%.2f", leg.key, n, vontade)
        except Exception:
            logger.exception("atraso.pesa")

    def _item(self, leg, e: dict, now: datetime) -> Optional[dict]:
        if e["tipo"] == "aula":
            from academic_life import AcademicLife
            blocos = sorted(AcademicLife(self.db).blocks_on(leg.end.date()), key=lambda b: b["start_at"])
            try:
                from college import College
                if any(a["due"] == leg.end.date().isoformat() for a in College(self.db).assignments(leg.end.date(), 0)):
                    return None                           # dia de entrega: vai de qualquer jeito
            except Exception:
                pass
            ch = chegada(e, now)
            perdidas = [b for b in blocos if datetime.fromisoformat(b["start_at"]) < ch]
            if not perdidas:
                return None
            return {"key": f"aula:{leg.end.date().isoformat()}", "tipo": "aula", "blocos": perdidas,
                    "texto": "Aula na PUC (" + ", ".join(b["display_name"] for b in perdidas) + ")",
                    "inicio": datetime.fromisoformat(perdidas[0]["start_at"]),
                    "fim": datetime.fromisoformat(perdidas[-1]["end_at"]), "com": (), "origem": "grade",
                    "ida": e["dur"]}
        with self.db.get_connection() as conn:
            r = conn.execute("SELECT id, source_key, description, event_at, end_at, metadata_json FROM eventos_pendentes "
                             "WHERE source_key=? AND status='pending'", (leg.compromisso,)).fetchone()
        if not r:
            return None
        meta = json.loads(r["metadata_json"] or "{}") or {}
        return {"key": r["source_key"], "id": r["id"], "tipo": "role", "texto": r["description"],
                "inicio": datetime.fromisoformat(r["event_at"]), "fim": datetime.fromisoformat(r["end_at"]),
                "com": tuple(meta.get("friends") or ()), "origem": meta.get("origem") or meta.get("origin"),
                "ida": e["dur"]}

    # --------------------------------------------------------------- aviso --
    def _conta(self, e: dict, now: datetime) -> bool:
        """Conta pro Patrick pelo que sente: atraso grande, aula/freela/médico ou chateada consigo mesma, sim;
        atrasinho de rolê de bom humor, não (é normal). Chateada com ele, não. Conversando agora: fala no chat."""
        try:
            f = self._feeling(now)
        except Exception:
            f = None
        if f is not None and (getattr(f, "bond", None) or {}).get("hurt", 0) >= 0.25:
            return False
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT timestamp FROM conversas WHERE role='user' ORDER BY id DESC LIMIT 1").fetchone()
        if row and now - datetime.fromisoformat(row["timestamp"]) < timedelta(minutes=10):
            return False
        n = minutos(e, now)
        if n >= AVISO_FORTE_MIN:
            return True
        if e["tipo"] in ("aula", "freela", "medico"):
            return True
        mal = f is not None and getattr(f, "valence", 0.6) < 0.5
        return mal or bool((e.get("acordou") or {}).get("min"))

    def detalhe(self, e: dict, now: datetime) -> str:
        porque = _junta(causas(e, now)) or "se enrolou"
        ini = datetime.fromisoformat(e["inicio"])
        oque = e["onde"].replace("na aula", "pra aula", 1) if e["tipo"] == "aula" else e["onde"]
        return (f"Você está atrasada ({oque}, que começa {ini:%H:%M}): {porque}. "
                f"Vai chegar ~{chegada(e, now):%H:%M}, {aprox(minutos(e, now))} depois.")

    def aviso(self, now: datetime) -> Optional[dict]:
        a = _load(self.db, now.date()).get("aviso")
        if not a or a.get("enviado"):
            return None
        if now - datetime.fromisoformat(a["em"]) > AVISO_VALIDO:
            return None
        e = (_load(self.db, now.date()).get("legs") or {}).get(a["leg"]) or {}
        if e.get("desistiu") or (e and now >= chegada(e)):
            return None
        return a

    def marca_aviso_enviado(self, now: datetime) -> None:
        st = _load(self.db, now.date())
        if st.get("aviso"):
            st["aviso"]["enviado"] = True
            _save(self.db, now.date(), st)

    # ------------------------------------------------------------ memória --
    def _registra(self, leg, e: dict) -> None:
        n = minutos(e)
        porque = _junta(causas(e))
        summary = f"Chegou {n} min atrasada {e['onde']}" + (f" — {porque}." if porque else ".")
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'routine','atraso',?,'simulated',1,0.3,?,0.5,?)""",
                (f"atraso:{leg.key}", chegada(e).isoformat(), summary, json.dumps(["marina"]), datetime.now().isoformat()))
            conn.commit()

    # -------------------------------------------------------------- prompt --
    def prompt_lines(self, now: datetime) -> list[str]:
        st = _load(self.db, now.date())
        out = []
        for key, e in (st.get("legs") or {}).items():
            if e.get("desistiu") or "saida" not in e and not (e.get("acordou") or {}).get("min"):
                continue
            n = minutos(e, now)
            if not n:
                continue
            ch = chegada(e, now)
            ini = datetime.fromisoformat(e["inicio"])
            porque = _junta(causas(e, now))
            if now < ch:
                avisou = (st.get("aviso") or {}).get("leg") == key and (st.get("aviso") or {}).get("enviado")
                out.append(f"- Você está ATRASADA {e['onde']} (começa {ini:%H:%M}): {porque}. Chega ~{ch:%H:%M}, "
                           f"{aprox(n)} depois — o compromisso começa sem você."
                           + (" Você já avisou o Patrick." if avisou else
                              " O Patrick ainda não sabe; se estiverem conversando, conte do seu jeito."))
            elif now - ch <= timedelta(minutes=90):
                out.append(f"- Às {ch:%H:%M} você chegou {aprox(n)} atrasada {e['onde']}" + (f" ({porque})." if porque else "."))
        return (["[ATRASO — aconteceu de verdade]", *out]) if out else []
