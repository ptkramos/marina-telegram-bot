"""Agenda única: o que ela decide fazer na hora, por vontade (Patrick, 26/09).

"Quero que atividades continuem aparecendo de repente, dependentes apenas da vontade dela, mas
que isso não deixe de se integrar com o mundo, nem com a agenda reagindo à conversa — o ideal é
tudo ser uma coisa só." E: "tudo que é possível atualmente no mundo dela pode ser feito de forma
espontânea, caso faça sentido."

Quando ela está livre em casa, de vez em quando dá vontade de sair: levar o Milo na Enseada,
descer pra um café ou um açaí, caminhar na orla, bater perna no shopping, treinar fora da cota,
dar um mergulho, passar no mercado ou na farmácia. No momento em que decide, vira **item da
mesma agenda** das saídas (eventos_pendentes, origem "vontade"): se arrumando a partir de agora,
a caminho, lá (com o que consome, do cardápio real das lojas do iFood dela) e voltando. O mercado
da semana e o médico entram pela mesma porta (`agendar`).
"""
from __future__ import annotations

import json
import logging
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CATALOGO = Path(__file__).parent / "webapp" / "catalogo.json"
MAX_POR_DIA = 3
CHANCE_BASE = 0.10                  # por janela de 20 min livre em casa
FOLGA_ANTES = timedelta(minutes=100)   # não sai se tem compromisso logo
SAIR_DESCONFORTO_MAX = 0.5             # soak, dia 2: passando mal (cólica forte = 0,8) não sai por vontade
HORAS = (7, 22)

# tipo → lugar fixo ou categorias do catálogo, texto (mundo/card), minutos lá, janelas de hora, peso,
# precisa de tempo seco, minutos de ida a pé
SAIDAS = {
    "milo": {"lugar": "enseada_botafogo", "texto": "Passeando com o Milo na Enseada", "mins": (20, 35),
             "horas": ((7, 11), (15.5, 21)), "peso": 1.0, "seco": True, "ida": 4,
             "motivo": "o Milo tava pedindo pra sair"},
    "academia": {"lugar": "bodytech_sao_clemente", "texto": "Treinando na Bodytech", "mins": (55, 80),
                 "horas": ((6, 20.5),), "peso": 0.4, "ida": 12, "motivo": "deu vontade de treinar"},
    "cafe": {"categorias": ("Cafés",), "texto": "Tomando um café {no}", "mins": (25, 45),
             "horas": ((8, 19),), "peso": 0.8, "motivo": "deu vontade de um café"},
    "acai": {"categorias": ("Açaí", "Sorvetes"), "texto": "Tomando {coisa} {no}", "mins": (15, 30),
             "horas": ((13, 22),), "peso": 0.7, "motivo": "deu vontade de um docinho gelado"},
    "orla": {"lugar": "enseada_botafogo", "texto": "Caminhando na orla de Botafogo", "mins": (30, 50),
             "horas": ((6.5, 9.5), (16, 19.5)), "peso": 0.6, "seco": True, "ida": 4,
             "motivo": "tava um fim de tarde bonito"},
    "shopping": {"lugar": "botafogo_praia_shopping", "texto": "Passeando no Botafogo Praia Shopping",
                 "mins": (50, 110), "horas": ((10, 20.5),), "peso": 0.5, "ida": 12,
                 "motivo": "quis bater perna"},
    "praia": {"lugar": "copacabana_beach", "texto": "Tomando sol em Copacabana", "mins": (60, 120),
              "horas": ((9, 14.5),), "peso": 0.4, "seco": True, "ida": 20, "modo": "metro",
              "motivo": "o dia tava lindo"},
    "mercado": {"categorias": ("Mercado",), "texto": "Passando {no}", "mins": (10, 20),
                "horas": ((8, 21),), "peso": 0.2, "motivo": "lembrou que faltava uma coisa"},
    "farmacia": {"categorias": ("Farmácia",), "texto": "Passando {no}", "mins": (8, 15),
                 "horas": ((8, 22),), "peso": 0.05, "motivo": "precisava de um remédio"},
}
COISA = {"Açaí": "um açaí", "Sorvetes": "um sorvete"}
FEMININO = ("agência", "estação", "drogaria", "drogarias", "officina", "kopenhagen", "enseada", "praia", "clínica",
            "orla", "novamed")
PREP_MIN = {"milo": (3, 5), "cafe": (8, 12), "acai": (6, 10), "orla": (8, 12), "shopping": (20, 30),
            "praia": (15, 20), "mercado": (6, 10), "farmacia": (5, 8), "academia": (10, 15),
            "mercado_semana": (8, 12), "medico": (12, 18), "pronto_atendimento": (8, 12), "manicure": (8, 12),
            "cabelo": (8, 12)}


def no(nome: str) -> str:
    return ("na " if nome.lower().startswith(FEMININO) else "no ") + nome


def _catalogo() -> list[dict]:
    try:
        return json.loads(CATALOGO.read_text(encoding="utf-8"))["lojas"]
    except Exception:
        return []


def loja(loja_id: str) -> Optional[dict]:
    return next((l for l in _catalogo() if l["id"] == loja_id), None)


class Vontade:
    def __init__(self, db):
        self.db = db
        self._motivos: dict = {}           # 27/09: o sentimento que mais puxou cada tipo ("entediada em casa")

    # --------------------------------------------------------------- lugares --
    def _lugar_loja(self, l: dict) -> str:
        """A loja do iFood dela vira lugar do mundo (real, pertinho de casa)."""
        key = f"loja_{l['id'].replace('-', '_')}"
        from world_repository import WorldBibleRepository
        repo = WorldBibleRepository(self.db)
        if not repo.get_place(key):
            repo.upsert_place(key, {"name": l["nome"], "region": "Botafogo", "place_type": l.get("categoria", "loja"),
                                    "truth_type": "real_world", "familiarity": "known", "distance_class": "near_home",
                                    "usage_rules_json": {"catalogo": l["id"], "abre": l.get("abre"), "fecha": l.get("fecha")},
                                    "canon_locked": 0})
        return key

    # --------------------------------------------------------------- agendar --
    def agendar(self, tipo: str, lugar: str, inicio: datetime, fim: datetime, texto: str, *, origem: str,
                decidido_em: datetime, chave: str, modo: str = "a_pe", ida_min: int = 10,
                extra: Optional[dict] = None) -> Optional[int]:
        """Porta única da agenda: vira compromisso confirmado com ida e volta (commute lê o metadata)."""
        from calendar_world import CalendarWorld
        meta = {"origem": origem, "tipo": tipo, "decidido_em": decidido_em.isoformat(timespec="minutes"),
                "modo": modo, "ida_min": ida_min, **(extra or {})}
        try:
            return CalendarWorld(self.db).create_commitment(
                source_key=chave, event_type="lazer", description=texto, start_at=inicio, end_at=fim,
                location_key=lugar, metadata=meta)
        except ValueError:
            logger.info("vontade.agendar.conflito chave=%s", chave)
            return None

    # ---------------------------------------------------------------- vontade --
    def _hoje(self, day: date) -> list[dict]:
        with self.db.get_connection() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT source_key, metadata_json FROM eventos_pendentes WHERE source_key LIKE ? AND status!='cancelled'",
                (f"vontade:{day.isoformat()}:%",))]

    def _sem_condicao(self, now: datetime) -> bool:
        """Soak, dia 2 (30/09, 11:03): com cólica forte (desconforto 0,8), no horário das aulas que faltou por ela e
        com o Patrick escolhendo a comida dela, marcou escova na Ophicina. Mal, na hora da aula que faltou ou com
        comida chegando, ela não sai por vontade (salão, unhas, café…)."""
        try:
            from emotion import EmotionEngine
            if EmotionEngine(self.db).feeling(now).discomfort >= SAIR_DESCONFORTO_MAX:
                return True
        except Exception:
            logger.exception("vontade.sem_condicao.corpo")
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT MAX(end_at) FROM eventos_pendentes WHERE source_key LIKE ?",
                               (f"falta:{now.date().isoformat()}:%",)).fetchone()
        if row and row[0] and now < datetime.fromisoformat(row[0]):
            return True
        try:
            from meals import Meals
            return Meals(self.db)._comida_chegando(now)
        except Exception:
            return False

    def _livre_ate(self, now: datetime) -> Optional[datetime]:
        """Até quando ela está livre (próxima etapa da agenda ou refeição em casa)."""
        if self._sem_condicao(now):
            return None
        limite = datetime.combine(now.date(), time(23, 30))
        try:
            from agenda import Agenda
            for e in Agenda(self.db).etapas(now.date(), now):
                if e.fim > now:
                    if e.inicio <= now:
                        return None                       # já está numa etapa
                    limite = min(limite, e.inicio)
        except Exception:
            logger.exception("vontade.agenda")
        with self.db.get_connection() as conn:          # compromisso marcado: precisa de tempo pra ir
            row = conn.execute(
                """SELECT MIN(event_at) FROM eventos_pendentes WHERE confirmed=1 AND status='pending'
                   AND event_at>? AND event_at<?""", (now.isoformat(), limite.isoformat())).fetchone()
        if row and row[0]:
            limite = min(limite, datetime.fromisoformat(row[0]) - timedelta(minutes=45))
        try:
            from meals import Meals
            for s in Meals(self.db).day_plan(now.date()):
                if s.where == "casa" and not s.skipped:
                    if s.at <= now < s.end:
                        return None
                    if s.at > now:
                        limite = min(limite, s.at)
        except Exception:
            pass
        return limite

    def _pesos(self, now: datetime, feito: set) -> dict:
        h = now.hour + now.minute / 60
        chuva, sol = self._chuva(), self._sol()
        try:
            from emotion import EmotionEngine
            f = EmotionEngine(self.db).feeling(now)
        except Exception:
            f = None
        pesos = {}
        for tipo, s in SAIDAS.items():
            if tipo in feito or not any(a <= h < b for a, b in s["horas"]) or (s.get("seco") and chuva) \
                    or (tipo == "praia" and not sol):
                continue
            p = s["peso"]
            if f:
                if tipo == "academia":
                    if f.energy < 0.55 or self._treinou(now):
                        continue
                    p *= 1.5 if any(e.family == "medo" for e in f.episodes) else 1.0
                if tipo == "farmacia" and f.discomfort >= 0.15:
                    p = 1.5
                if tipo == "acai" and f.hunger >= 0.5:
                    p *= 1.4
                if tipo in ("shopping", "praia", "orla") and f.energy < 0.45:
                    p *= 0.3
            if tipo == "praia" and (now.weekday() < 5 and self._tem_aula(now.date())):
                continue
            if tipo == "milo" and self._milo_saiu(now):
                continue
            if f:
                # 27/09 (Patrick): o que ela sente escolhe — entediada sai, triste quer espairecer (açaí, orla,
                # Milo), sem bateria foge de gente, com dor não vai longe.
                from agenda_viva import Disposicao
                aval = Disposicao(self.db).avaliar(tipo, now, feeling=f)
                p *= (aval.vontade / 0.6) ** 2
                self._motivos[tipo] = (aval.motivo(+1) or ("", ""))[1]
            pesos[tipo] = p
        return pesos

    def _inquietude(self, now: datetime) -> float:
        """27/09: quanto ela está a fim de sair de casa agora (tédio e empolgação empurram, tristeza segura)."""
        try:
            from emotion import EmotionEngine
            f = EmotionEngine(self.db).feeling(now)
        except Exception:
            return 1.0
        x = 1.0
        for ep in f.episodes:
            if ep.family == "tedio":
                x += 1.5 * ep.intensity
            elif ep.family == "alegria":
                x += 0.5 * ep.intensity
            elif ep.family == "tristeza":
                x -= 0.4 * ep.intensity
        x -= max(0.0, 0.4 - f.social_battery)
        return max(0.3, min(2.5, x))

    def talvez(self, now: datetime) -> Optional[int]:
        """Chamado pelo mundo quando ela está livre em casa: às vezes decide sair agora."""
        with self.db.get_connection() as conn:
            if not conn.execute("SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done'").fetchone():
                return None
        if not (HORAS[0] <= now.hour < HORAS[1]):
            return None
        slot = (now.hour * 60 + now.minute) // 20
        rng = random.Random(f"marina-vontade:{now.date().isoformat()}:{slot}")
        sorteio = rng.random()
        if sorteio >= CHANCE_BASE * 1.5 * 2.5:            # barato primeiro: quase sempre para aqui
            return None
        energia = 0.6
        try:
            from world_state import current_energy
            energia = current_energy(self.db, now)
        except Exception:
            pass
        if sorteio >= CHANCE_BASE * (0.5 + energia) * self._inquietude(now) or self._na_cama(now):
            return None
        hoje = self._hoje(now.date())
        if len(hoje) >= MAX_POR_DIA:
            return None
        livre = self._livre_ate(now)
        if not livre or livre - now < FOLGA_ANTES:
            return None
        feito = {(json.loads(r["metadata_json"] or "{}") or {}).get("tipo") for r in hoje}
        pesos = {k: p for k, p in self._pesos(now, feito).items() if p > 0}
        if not pesos:
            return None                                   # 27/09: sem vontade de nada (vontade zero em tudo)
        tipo = rng.choices(list(pesos), weights=list(pesos.values()))[0]
        return self._sair(tipo, now, rng, livre)

    def _sair(self, tipo: str, now: datetime, rng: random.Random, livre: datetime) -> Optional[int]:
        s = SAIDAS[tipo]
        texto = s["texto"]
        sentiu = self._motivos.get(tipo)
        motivo = {"entediada em casa": "tava entediada em casa", "empolgada": "tava animada",
                  "precisando espairecer": "precisava espairecer", "cheia de energia": "tava cheia de energia",
                  "de bom humor": s["motivo"]}.get(sentiu, s["motivo"])
        extra = {"motivo": motivo}
        if "categorias" in s:
            h = now.hour
            lojas = [l for l in _catalogo() if l.get("categoria") in s["categorias"] and l.get("area", "bf") == "bf"
                     and (l.get("abre") or 0) <= h < (l.get("fecha") or 24) - 1]
            if not lojas:
                return None
            l = rng.choices(lojas, weights=[1 / (float(l.get("km") or 0) + 0.3) for l in lojas])[0]
            lugar = self._lugar_loja(l)
            texto = texto.format(no=no(l["nome"]), coisa=COISA.get(l.get("categoria"), "alguma coisa"))
            ida = max(3, round(float(l.get("km") or 0.3) * 12) + 2)
            extra["loja"] = l["id"]
        else:
            lugar, ida = s["lugar"], s.get("ida", 10)
        prep = rng.randint(*PREP_MIN[tipo])
        inicio = now + timedelta(minutes=prep + ida)
        fim = inicio + timedelta(minutes=rng.randint(*s["mins"]))
        if fim + timedelta(minutes=ida + 10) > livre:
            return None                                   # não dá tempo antes do próximo compromisso
        chave = f"vontade:{now.date().isoformat()}:{now:%H%M}"
        cid = self.agendar(tipo, lugar, inicio, fim, texto, origem="vontade", decidido_em=now, chave=chave,
                           modo=s.get("modo", "a_pe"), ida_min=ida, extra=extra)
        if cid:
            self._registra(chave, now, f"Deu vontade e foi: {texto[:1].lower() + texto[1:]} ({motivo}).")
            logger.info("vontade.saiu tipo=%s inicio=%s", tipo, inicio.isoformat(timespec="minutes"))
        return cid

    def _registra(self, chave: str, at: datetime, summary: str) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'routine','vontade',?,'simulated',1,0.2,?,0.4,?)""",
                (f"{chave}:decidiu", at.isoformat(), summary, json.dumps(["marina"]), at.isoformat()))
            conn.commit()

    # -------------------------------------------------------------- contexto --
    def _chuva(self) -> bool:
        try:
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT weather_context_json FROM world_state ORDER BY id DESC LIMIT 1").fetchone()
            w = json.loads(row["weather_context_json"] or "null") if row else None
            return bool(w and (w.get("heavy_rain") or w.get("condition") in ("rain", "storm")))
        except Exception:
            return False

    def _sol(self) -> bool:
        """Soak, dia 5 (03/10, 14:37): "tomando sol" na piscina com garoa e 100% de nuvens (tempo_livre); a praia
        em Copacabana tinha o mesmo furo — só a chuva barrava. Sol de verdade é céu limpo (Open-Meteo 0–1); sem
        tempo conhecido, não."""
        try:
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT weather_context_json FROM world_state ORDER BY id DESC LIMIT 1").fetchone()
            w = json.loads(row["weather_context_json"] or "null") if row else None
            return bool(w and w.get("condition") == "clear")
        except Exception:
            return False

    def _na_cama(self, now: datetime) -> bool:
        try:
            from sleep_plan import SleepPlan
            return SleepPlan(self.db).in_bed(now)
        except Exception:
            return False

    def _tem_aula(self, day: date) -> bool:
        try:
            from academic_life import AcademicLife
            return bool(AcademicLife(self.db).blocks_on(day))
        except Exception:
            return False

    def _treinou(self, now: datetime) -> bool:
        try:
            from academia import Academia
            if Academia(self.db).plano(now.date(), now):
                return True
        except Exception:
            pass
        return False

    def _milo_saiu(self, now: datetime) -> bool:
        """O Milo saiu há menos de 3 h (passeio da manhã ou outro por vontade)?"""
        try:
            from academia import PasseioMilo
            p = PasseioMilo(self.db).plano(now.date(), now)
            if p and p["inicio"] - timedelta(hours=1) <= now <= p["fim"] + timedelta(hours=3):
                return True
        except Exception:
            pass
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT event_at, metadata_json FROM eventos_pendentes WHERE source_key LIKE ?",
                                (f"vontade:{now.date().isoformat()}:%",)).fetchall()
        return any((json.loads(r["metadata_json"] or "{}") or {}).get("tipo") == "milo"
                   and abs((now - datetime.fromisoformat(r["event_at"])).total_seconds()) < 3 * 3600 for r in rows)

    # ---------------------------------------------------------- mercado/médico --
    def mercado_semana(self, at: datetime, minutos: int, now: datetime) -> Optional[int]:
        l = loja("zona-sul")
        lugar = self._lugar_loja(l) if l else "zona_sul_sao_clemente"
        chave = f"mercado:{at.date().isoformat()}"
        return self.agendar("mercado_semana", lugar, at, at + timedelta(minutes=minutos),
                            "Fazendo as compras da semana no Zona Sul", origem="planejado", decidido_em=now,
                            chave=chave, ida_min=6, extra={"pago_por": "pai"})

    def medico(self, at: datetime, quem: str, now: datetime, *, kind: str = "resfriado") -> Optional[int]:
        """Consulta pelo Bradesco Saúde (cânone): virose → pronto-atendimento do Samaritano Botafogo;
        o resto → consulta marcada na Novamed Botafogo. Doente, vai de uber."""
        urgente = kind == "virose"
        lugar = "hospital_samaritano_botafogo" if urgente else "novamed_botafogo"
        texto = "No pronto-atendimento do Samaritano" if urgente else "Na consulta na Novamed"
        chave = f"medico:{at.date().isoformat()}"
        return self.agendar("pronto_atendimento" if urgente else "medico", lugar, at,
                            at + timedelta(minutes=90 if urgente else 50), texto, origem="planejado",
                            decidido_em=now, chave=chave, modo="uber", ida_min=8,
                            extra={"mandou": quem, "plano": "Bradesco Saúde Top Nacional"})
