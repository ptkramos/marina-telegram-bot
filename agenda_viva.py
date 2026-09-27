"""Agenda viva (Patrick, 27/09): a agenda é dela, e quem decide é o que ela sente.

"Fechar o que falta pra agenda ficar inteligente e maleável em tempo real com as emoções e decisões
dela — vontade, humor, energia, tesão, conversa mexendo em tudo." E, sobre furar um rolê: "a emoção,
os sentimentos dela precisam estar envolvidos nisso" — nada de sorteio.

**Disposição.** Pra qualquer coisa da agenda, `Disposicao.avaliar` diz a vontade que ela tem de ir
AGORA (0–1) e por quê: energia, sono, humor, o que ela está sentindo (tédio, empolgação, tristeza,
ansiedade, chateação), bateria social, dor/doença, chuva, grana, e quem vai junto. Cada fator vem
com o texto do motivo; o que mais pesou é o motivo da decisão. Mesmo estado, mesma decisão.

Em cima dela:
1. **Reconsiderar** (`reconsidera`): um pouco antes de se arrumar pra um compromisso (rolê, academia,
   passeio do Milo, aula, mercado da semana), ela pesa a vontade contra o peso do compromisso. Abaixo:
   desiste, adia ou falta — vira acontecimento com o motivo; furar rolê avisa a amiga; faltar aula
   (motivo forte, ou preguiça no máximo 1x por semana) e ela sempre corre atrás da matéria depois.
   Se o motivo é coisa que ela quer dividir (cansada, triste, doente, ansiosa, sem pique), ela conta
   pro Patrick (iniciativa `agenda_mudou`); motivo bobo (chuva, preguiça) só se ele perguntar.
2. **Emendar** (`emenda`): terminando uma saída em Botafogo com vontade de mais, ela passa num café,
   açaí, farmácia ou mercado antes de voltar — o trajeto vai direto de um lugar pro outro
   (`commute._emendas`, que também resolve rolê logo depois da aula).
3. **Planejar** (`planeja`): à noite, com pique e sem rolê nos próximos dias, ela chama uma amiga pra
   sair (quem ela não vê há mais tempo); a amiga topa ou não — vira compromisso e novidade.
A vontade na hora (`vontade.py`) e os convites das amigas (`social_day._willing`) usam a mesma
disposição; a conversa mexe em qualquer item dos próximos dias (`agenda_reativa`, com a lista daqui).
Estado em estado_relacional[KEY], sem migration.
"""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

KEY = "agenda_viva_json"
BASE = 0.6
FISICOS = ("academia", "praia", "orla", "shopping", "noite", "jogo", "milo", "encontro", "role")
SOCIAIS = ("role", "noite", "encontro", "jogo", "aula")
PAGOS = ("shopping", "cafe", "acai", "noite", "jogo", "role")
SECOS = ("milo", "orla", "praia")
ESPAIRECER = ("acai", "orla", "milo", "cafe")
MELHOR_AMIGA = "bia_andrade"

# peso do compromisso: abaixo disso de vontade, ela desiste
PESO = {"role": 0.40, "academia": 0.38, "milo": 0.28, "aula": 0.55, "mercado_semana": 0.40, "convite": 0.45}
# janela da decisão, em minutos antes de sair de casa
JANELA = {"role": (150, 30), "academia": (90, 15), "milo": (60, 10), "aula": (150, 10), "mercado_semana": (120, 15)}
IDA_APROX = {"role": 30, "academia": 12, "milo": 4, "aula": 40, "mercado_semana": 10}
FALTAS_POR_SEMANA = 1
# motivos que ela quer dividir com ele (quer colo); o resto só se ele perguntar
CONTA = ("sono", "energia", "humor", "tristeza", "desconforto", "bateria", "ansiedade", "tpm")
EMENDA_MIN = 0.72                    # vontade pra emendar mais uma parada
EMENDA_MAX_DIA = 1
PLANEJA_JANELA = (time(19, 30), time(22, 30))
AMIGAS = ("bia_andrade", "julia_azevedo", "carol_menezes", "theo_martins")
# o que ela propõe, por dia da semana (lugar, início, fim, texto)
PROPOSTAS = {
    4: ("quartinho_bar", time(20, 0), time(23, 0), "Saindo com {quem} no Quartinho Bar"),
    5: ("quartinho_bar", time(21, 0), time(23, 59), "Saindo com {quem} no Quartinho Bar"),
    6: ("shopping_gavea", time(15, 0), time(19, 0), "Cinema e shopping com {quem} no Shopping da Gávea"),
}


@dataclass
class Avaliacao:
    vontade: float
    fatores: list = field(default_factory=list)   # (chave, texto, delta)

    def motivo(self, sinal: int = -1) -> Optional[tuple[str, str]]:
        """(chave, texto) do fator que mais pesou pra baixo (-1) ou pra cima (+1)."""
        cands = [f for f in self.fatores if f[2] * sinal > 0]
        if not cands:
            return None
        k, t, _ = max(cands, key=lambda f: f[2] * sinal)
        return k, t


def _rng(salt: str) -> random.Random:
    return random.Random(f"marina-agenda-viva:{salt}")


def _jitter(salt: str) -> float:
    """Temperamento do dia (±0,04): o mesmo item no mesmo estado dá a mesma decisão."""
    return (_rng(salt).random() - 0.5) * 0.08


class Disposicao:
    def __init__(self, db):
        self.db = db

    def _feeling(self, now: datetime):
        from emotion import EmotionEngine
        return EmotionEngine(self.db).feeling(now)

    def _chuva(self) -> bool:
        try:
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT weather_context_json FROM world_state ORDER BY id DESC LIMIT 1").fetchone()
            w = json.loads(row["weather_context_json"] or "null") if row else None
            return bool(w and (w.get("heavy_rain") or w.get("rain")))
        except Exception:
            return False

    def _saldo(self) -> Optional[float]:
        try:
            import financas
            return float(financas._load(self.db)["saldo"])
        except Exception:
            return None

    def avaliar(self, tipo: str, now: datetime, *, com: tuple = (), feeling=None) -> Avaliacao:
        try:
            f = feeling or self._feeling(now)
        except Exception:
            logger.exception("agenda_viva.feeling")
            return Avaliacao(BASE)
        fat: list = []
        social = tipo in SOCIAIS or bool(com)
        peso_e = 0.6 if tipo in FISICOS else 0.35
        e = f.energy - 0.6
        if abs(e) >= 0.05:
            fat.append(("energia", "sem energia" if e < 0 else "cheia de energia", e * peso_e))
        dormiu = getattr(f, "hours_slept", None)
        if dormiu is not None and dormiu < 6:
            fat.append(("sono", "dormiu mal", -(6 - dormiu) * 0.06))
        v = getattr(f, "valence", 0.6) - 0.6
        if abs(v) >= 0.06:
            fat.append(("humor", "desanimada" if v < 0 else "de bom humor", v * 0.5))
        chateada_com_ele = (getattr(f, "bond", None) or {}).get("hurt", 0) >= 0.25
        for ep in getattr(f, "episodes", None) or []:
            i = ep.intensity
            dele = ep.target == "o Patrick"
            if ep.family == "tedio":
                fat.append(("tedio", "entediada em casa", -i * 0.2 if tipo == "aula" else i * 0.4))
            elif ep.family == "alegria":
                fat.append(("alegria", "empolgada", i * 0.25))
            elif ep.family == "tristeza":
                if social and (dele or MELHOR_AMIGA in com):
                    fat.append(("desabafo", "precisando desabafar com alguém", i * 0.2))
                elif tipo in ESPAIRECER:
                    fat.append(("espairecer", "precisando espairecer", i * 0.2))
                else:
                    fat.append(("tristeza", ep.word, -i * 0.35))
            elif ep.family == "raiva":
                if dele:
                    chateada_com_ele = True
                if social and com:
                    fat.append(("espairecer", "querendo espairecer", i * 0.2))
                else:
                    fat.append(("raiva", ep.word, -i * 0.15))
            elif ep.family == "medo":
                if tipo == "academia":
                    fat.append(("descarregar", "querendo descarregar a ansiedade", i * 0.2))
                elif social:
                    fat.append(("ansiedade", ep.word, -i * 0.3))
            elif ep.family == "vergonha" and social:
                fat.append(("vergonha", ep.word, -i * 0.2))
        if social:
            b = getattr(f, "social_battery", 0.7) - 0.5
            if abs(b) >= 0.08:
                fat.append(("bateria", "sem bateria social" if b < 0 else "com pique pra gente", b * 0.5))
        dor = getattr(f, "discomfort", 0.0)
        if dor >= 0.1:
            if tipo == "farmacia":
                fat.append(("remedio", "precisando de remédio", dor * 0.5))
            else:
                fat.append(("desconforto", getattr(f, "discomfort_why", "") or "passando mal", -dor * 0.8))
        if getattr(f, "cycle_phase", "") == "tpm" and social:
            fat.append(("tpm", "de TPM", -0.05))
        if (tipo in SECOS or tipo in ("role", "noite", "shopping", "cafe", "acai")) and self._chuva():
            fat.append(("chuva", "chovendo", -0.25 if tipo in SECOS else -0.1))
        if tipo in PAGOS:
            saldo = self._saldo()
            if saldo is not None and saldo < 150:
                fat.append(("grana", "sem grana", -0.15))
        if MELHOR_AMIGA in com:
            fat.append(("amiga", "é com a Bia", 0.15))
        elif com:
            fat.append(("amigos", "é com os amigos", 0.08))
        if chateada_com_ele:
            fat.append(("chateada", "chateada com o Patrick", 0.0))
        total = BASE + sum(x[2] for x in fat)
        return Avaliacao(max(0.0, min(1.0, total)), fat)


class AgendaViva:
    def __init__(self, db):
        self.db = db
        self.disp = Disposicao(db)

    # ----------------------------------------------------------- estado --
    def _state(self) -> dict:
        raw = self.db.get_estado_relacional(KEY)
        try:
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    def _save(self, st: dict, now: datetime) -> None:
        corte = (now - timedelta(days=10)).isoformat()
        st["decisoes"] = {k: v for k, v in st.get("decisoes", {}).items() if v.get("em", "") >= corte}
        self.db.set_estado_relacional(KEY, json.dumps(st, ensure_ascii=False))

    def _registra(self, key: str, at: datetime, summary: str, *, quem: tuple = (), share: float = 0.6,
                  importance: float = 0.35) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'agenda','agenda',?,'simulated',1,?,?,?,?)""",
                (key, at.isoformat(), summary, importance, json.dumps(["marina", *quem]), share, now_iso(at)))
            conn.commit()

    def _livre(self) -> bool:
        with self.db.get_connection() as conn:
            return bool(conn.execute("SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done'").fetchone())

    def _dormindo(self, now: datetime) -> bool:
        try:
            from sleep_plan import SleepPlan
            return SleepPlan(self.db).is_asleep(now)
        except Exception:
            return False

    # ------------------------------------------------------------ itens --
    def itens(self, now: datetime, horas: float = 4.0) -> list[dict]:
        """O que vem pela frente e ainda pode ser repensado (hoje e, pro chat, os próximos dias)."""
        fim = now + timedelta(hours=horas)
        out = []
        with self.db.get_connection() as conn:
            rows = [dict(r) for r in conn.execute(
                """SELECT id, source_key, description, event_at, end_at, location_key, metadata_json FROM eventos_pendentes
                   WHERE confirmed=1 AND status='pending' AND owner_character_key='marina'
                   AND (source_key LIKE 'outing:%' OR source_key LIKE 'mercado:%' OR source_key LIKE 'vontade:%')
                   AND event_at>? AND event_at<=? ORDER BY event_at""", (now.isoformat(), fim.isoformat()))]
        for r in rows:
            meta = json.loads(r["metadata_json"] or "{}") or {}
            if r["source_key"].startswith("outing:"):
                tipo = "role"
            elif r["source_key"].startswith("mercado:"):
                tipo = "mercado_semana"
            else:
                tipo = meta.get("tipo", "cafe")
            out.append({"key": r["source_key"], "id": r["id"], "tipo": tipo, "texto": r["description"],
                        "inicio": datetime.fromisoformat(r["event_at"]), "fim": datetime.fromisoformat(r["end_at"]),
                        "com": tuple(meta.get("friends") or ()), "origem": meta.get("origem") or meta.get("origin"),
                        "ida": int(meta.get("ida_min") or IDA_APROX.get(tipo, 20))})
        dia = now.date()
        while datetime.combine(dia, time(0)) < fim:
            try:
                from academia import Academia, PasseioMilo
                for tipo, cls, texto in (("academia", Academia, "Treino na Bodytech"),
                                         ("milo", PasseioMilo, "Passeio do Milo na Enseada")):
                    p = cls(self.db).plano(dia, now)
                    if p and p["onde"] == "rua" and now < p["inicio"] <= fim:
                        out.append({"key": f"{'gym' if tipo == 'academia' else 'milo'}:{dia.isoformat()}", "tipo": tipo,
                                    "texto": texto, "inicio": p["inicio"], "fim": p["fim"], "com": (),
                                    "origem": p.get("origem", "planejado"), "ida": IDA_APROX[tipo]})
            except Exception:
                logger.exception("agenda_viva.planejados")
            try:
                from academic_life import AcademicLife
                blocos = sorted(AcademicLife(self.db).blocks_on(dia), key=lambda b: b["start_at"])
            except Exception:
                blocos = []
            if blocos:
                ini = datetime.fromisoformat(blocos[0]["start_at"])
                if now < ini <= fim:
                    out.append({"key": f"aula:{dia.isoformat()}", "tipo": "aula", "blocos": blocos,
                                "texto": "Aula na PUC (" + ", ".join(b["display_name"] for b in blocos) + ")",
                                "inicio": ini, "fim": datetime.fromisoformat(blocos[-1]["end_at"]), "com": (),
                                "origem": "grade", "ida": IDA_APROX["aula"]})
            dia += timedelta(days=1)
        return sorted(out, key=lambda x: x["inicio"])

    # ------------------------------------------------------ reconsidera --
    def reconsidera(self, now: datetime) -> Optional[dict]:
        """Um pouco antes de se arrumar: ela ainda quer ir? (uma decisão por item)"""
        if not self._livre() or self._dormindo(now):
            return None
        self._recupera_materia(now)
        st = self._state()
        feitas = st.setdefault("decisoes", {})
        for it in self.itens(now, 4.0):
            if it["tipo"] not in PESO or it["key"] in feitas:
                continue
            if it["origem"] in ("vontade", "conversa", "emenda"):
                continue                                  # decidiu agora há pouco, pelo mesmo humor
            antes, ate = JANELA[it["tipo"]]
            saida = it["inicio"] - timedelta(minutes=it["ida"])
            if not (saida - timedelta(minutes=antes) <= now <= saida - timedelta(minutes=ate)):
                continue
            aval = self.disp.avaliar(it["tipo"], now, com=it["com"])
            peso = self._peso(it, aval, now, st)
            vai = aval.vontade + _jitter(it["key"]) >= peso
            feitas[it["key"]] = {"em": now.isoformat(timespec="minutes"), "vontade": round(aval.vontade, 2),
                                 "peso": round(peso, 2), "vai": vai}
            if vai:
                self._save(st, now)
                continue
            res = self._desiste(it, aval, now, st)
            self._save(st, now)
            if res:
                logger.info("agenda_viva.desistiu key=%s vontade=%.2f peso=%.2f motivo=%s", it["key"],
                            aval.vontade, peso, res.get("motivo"))
                return res
        return None

    def _peso(self, it: dict, aval: Avaliacao, now: datetime, st: dict) -> float:
        p = PESO[it["tipo"]]
        if it["tipo"] == "role" and MELHOR_AMIGA in it["com"]:
            p += 0.05                                     # a Bia conta com ela
        if it["origem"] in ("ela_chamou",):
            p += 0.1                                      # foi ela que chamou
        if it["tipo"] == "aula":
            forte = self._motivo_forte(aval)
            semana = now.isocalendar()[:2]
            faltas = [d for d in st.get("faltas", []) if tuple(date.fromisoformat(d).isocalendar()[:2]) == semana]
            if not forte and len(faltas) >= FALTAS_POR_SEMANA:
                return -1.0                               # já matou aula essa semana: vai de qualquer jeito
            if forte:
                p -= 0.1
        return p

    @staticmethod
    def _motivo_forte(aval: Avaliacao) -> bool:
        return any((k == "desconforto" and d <= -0.4) or (k == "sono" and d <= -0.06) for k, _, d in aval.fatores)

    def _desiste(self, it: dict, aval: Avaliacao, now: datetime, st: dict) -> Optional[dict]:
        chave_motivo, motivo = aval.motivo(-1) or ("humor", "sem vontade")
        # os dois que mais pesaram, no jeito seco do painel ("dormiu mal e tava sem bateria social")
        neg = sorted((f for f in aval.fatores if f[2] < 0), key=lambda f: f[2])[:2]
        porque = " e ".join(t for _, t, _ in neg) or motivo
        tipo, dia = it["tipo"], it["inicio"].date()
        info = {"key": it["key"], "tipo": tipo, "texto": it["texto"], "motivo": porque, "chave_motivo": chave_motivo,
                "em": now.isoformat(timespec="minutes")}
        if tipo == "role":
            from calendar_world import CalendarWorld
            CalendarWorld(self.db).cancel(it["id"])
            from social_day import short_name
            quem = short_name(it["com"][0]) if it["com"] else ""
            aviso = f" Avisou {quem}" + (" e combinaram outro dia." if it["com"] and it["com"][0] == MELHOR_AMIGA
                                        else ".") if quem else ""
            self._registra(f"agenda:desistiu:{it['key']}", now,
                           f"Desistiu de ir: {it['texto']} ({porque}).{aviso}", quem=it["com"][:1])
            self._sente("vergonha", "culpa", 0.15, f"furou o rolê ({it['texto']})", now, it["key"])
            if it["com"]:
                try:
                    from social_world import SocialWorld
                    SocialWorld(self.db).record(f"agenda:{it['key']}", occurred_at=now.isoformat(),
                                                character_key=it["com"][0], valence=-0.1)
                except Exception:
                    logger.debug("agenda_viva.contato_amiga", exc_info=True)
        elif tipo in ("academia", "milo"):
            from academia import Academia, PasseioMilo
            p = (Academia if tipo == "academia" else PasseioMilo)(self.db)
            plano_st = p._load()
            k = dia.isoformat()
            if chave_motivo == "chuva" and tipo == "academia" and plano_st.get(k):
                plano_st[k] = {**plano_st[k], "onde": "predio"}
                texto = f"Trocou a Bodytech pela academia do prédio ({porque})."
                info["trocou"] = "predio"
            else:
                plano_st[k] = None
                texto = ("Desistiu de treinar hoje" if tipo == "academia" else "Deixou o passeio do Milo pra depois") \
                    + f" ({porque})."
            self.db.set_estado_relacional(p.key, json.dumps(plano_st))
            self._registra(f"agenda:desistiu:{it['key']}", now, texto, share=0.4 if tipo == "academia" else 0.1)
        elif tipo == "aula":
            from academic_life import AcademicLife
            forte = self._motivo_forte(aval) or any(k == "conversa" for k, _, _ in aval.fatores)
            futuros = [b for b in it["blocos"] if datetime.fromisoformat(b["start_at"]) > now]
            # preguiça: só as da manhã; motivo forte (ou combinado com ele): o dia
            blocos = futuros if forte else [b for b in futuros if b["start_at"][11:13] < "12"] or futuros
            if not blocos:
                return None
            academic = AcademicLife(self.db)
            for b in blocos:
                try:
                    academic.cancel_class_occurrence(b["id"], dia, source_key=f"falta:{dia.isoformat()}:{b['id']}")
                except ValueError:
                    pass
            nomes = ", ".join(b["display_name"] for b in blocos)
            st.setdefault("faltas", []).append(dia.isoformat())
            st["faltas"] = st["faltas"][-12:]
            # ela sempre corre atrás da matéria depois (Patrick, 27/09)
            amiga = "a Júlia"
            quando = datetime.combine(dia, time(20, 30)) if now.hour < 17 else datetime.combine(
                dia + timedelta(days=1), time(19, 0))
            st.setdefault("recuperar", []).append({"at": quando.isoformat(), "aulas": nomes, "amiga": amiga,
                                                   "key": f"agenda:recuperou:{dia.isoformat()}"})
            self._registra(f"agenda:faltou:{dia.isoformat()}", now,
                           f"Faltou a aula de hoje ({nomes}): {porque}. Vai pegar a matéria com {amiga} depois.",
                           share=0.5)
            self._sente("vergonha", "culpa", 0.12, f"faltou a aula ({nomes})", now, it["key"])
            info["aulas"] = nomes
        elif tipo == "mercado_semana":
            from calendar_world import CalendarWorld
            ini = it["inicio"] + timedelta(days=1)
            try:
                CalendarWorld(self.db).reschedule(it["id"], start_at=ini, end_at=it["fim"] + timedelta(days=1))
                texto = f"Deixou o mercado da semana pra amanhã ({porque})."
            except ValueError:
                CalendarWorld(self.db).cancel(it["id"])
                texto = f"Desistiu do mercado da semana hoje ({porque})."
            self._registra(f"agenda:desistiu:{it['key']}", now, texto, share=0.1)
        else:
            return None
        info["conta"] = self._conta(tipo, chave_motivo, aval)
        if info["conta"]:
            st["aviso"] = {**info, "enviado": False}
        st.setdefault("hoje", []).append(info)
        st["hoje"] = [h for h in st["hoje"] if h["em"][:10] >= (now - timedelta(days=1)).date().isoformat()]
        return info

    @staticmethod
    def _conta(tipo: str, chave_motivo: str, aval: Avaliacao) -> bool:
        """Conta pro Patrick quando o motivo é coisa que ela quer dividir; chateada com ele, não."""
        if tipo in ("milo", "mercado_semana"):
            return False
        if any(k == "chateada" for k, _, _ in aval.fatores):
            return False
        return chave_motivo in CONTA

    def _sente(self, family: str, kind: str, intensity: float, cause: str, now: datetime, key: str) -> None:
        try:
            from emotion import EmotionEngine
            EmotionEngine(self.db).feel(family, kind, intensity, cause, now, source_key=f"agenda:{key}:{kind}")
        except Exception:
            logger.debug("agenda_viva.sente", exc_info=True)

    def _recupera_materia(self, now: datetime) -> None:
        st = self._state()
        pend = st.get("recuperar", [])
        feitas = [r for r in pend if datetime.fromisoformat(r["at"]) <= now]
        if not feitas:
            return
        for r in feitas:
            at = datetime.fromisoformat(r["at"])
            self._registra(r["key"], at, f"Pegou a matéria da aula que faltou ({r['aulas']}) com {r['amiga']} "
                                         "e estudou o resumo.", share=0.3)
            try:
                from emotion import EmotionEngine
                EmotionEngine(self.db).resolve(f"agenda:aula:{at.date().isoformat()}:culpa")
            except Exception:
                pass
        st["recuperar"] = [r for r in pend if r not in feitas]
        self._save(st, now)

    # ----------------------------------------------------------- aviso --
    def aviso(self, now: datetime) -> Optional[dict]:
        a = self._state().get("aviso")
        if not a or a.get("enviado"):
            return None
        if now - datetime.fromisoformat(a["em"]) > timedelta(hours=2):
            return None
        return a

    def marca_aviso_enviado(self, now: datetime) -> None:
        st = self._state()
        if st.get("aviso"):
            st["aviso"]["enviado"] = True
            self._save(st, now)

    @staticmethod
    def detalhe_aviso(a: dict) -> str:
        if a["tipo"] == "aula":
            return f"Você decidiu faltar a aula de hoje ({a.get('aulas', '')}): {a['motivo']}."
        if a["tipo"] == "academia":
            return (f"Você trocou a Bodytech pela academia do prédio: {a['motivo']}." if a.get("trocou")
                    else f"Você desistiu de treinar hoje: {a['motivo']}.")
        return f"Você desistiu de ir ({a['texto']}): {a['motivo']}."

    # ----------------------------------------------------------- emenda --
    def emenda(self, now: datetime) -> Optional[int]:
        """Terminando uma saída em Botafogo com vontade de mais: passa em outro lugar antes de voltar."""
        if not self._livre():
            return None
        c = self._acabando(now)
        if not c:
            return None
        st = self._state()
        dia = now.date().isoformat()
        feitas = st.setdefault("emendas", {})
        if c["key"] in feitas or sum(1 for v in feitas.values() if v.get("dia") == dia) >= EMENDA_MAX_DIA:
            return None
        feitas[c["key"]] = {"dia": dia, "tipo": None}
        from vontade import SAIDAS, Vontade, _catalogo, no, COISA
        try:
            f = self.disp._feeling(now)
        except Exception:
            self._save(st, now)
            return None
        melhor, aval_m = None, None
        for tipo in ("acai", "cafe", "farmacia", "mercado"):
            if tipo == c["tipo"] or not any(a <= now.hour + now.minute / 60 < b for a, b in SAIDAS[tipo]["horas"]):
                continue
            aval = self.disp.avaliar(tipo, now, com=c["com"], feeling=f)
            if tipo == "farmacia" and not any(k == "remedio" for k, _, _ in aval.fatores):
                continue
            if tipo == "mercado":
                continue                                  # sem motivo concreto ainda (lista de compras)
            if aval_m is None or aval.vontade > aval_m.vontade:
                melhor, aval_m = tipo, aval
        if not melhor or aval_m.vontade + _jitter(f"emenda:{c['key']}") < EMENDA_MIN:
            self._save(st, now)
            return None
        s = SAIDAS[melhor]
        lojas = [l for l in _catalogo() if l.get("categoria") in s["categorias"] and l.get("area", "bf") == "bf"
                 and (l.get("abre") or 0) <= c["fim"].hour < (l.get("fecha") or 24) - 1]
        if not lojas:
            self._save(st, now)
            return None
        l = min(lojas, key=lambda x: float(x.get("km") or 9))
        v = Vontade(self.db)
        inicio = c["fim"] + timedelta(minutes=6)
        fim = inicio + timedelta(minutes=_rng(c["key"]).randint(*s["mins"]))
        prox = self._proximo_depois(c["fim"])
        if prox and fim + timedelta(minutes=40) > prox:
            self._save(st, now)
            return None
        texto = s["texto"].format(no=no(l["nome"]), coisa=COISA.get(l.get("categoria"), "alguma coisa"))
        porque = (aval_m.motivo(+1) or ("", "deu vontade"))[1]
        chave = f"vontade:{now.date().isoformat()}:e{now:%H%M}"
        cid = v.agendar(melhor, v._lugar_loja(l), inicio, fim, texto, origem="emenda", decidido_em=now, chave=chave,
                        ida_min=6, extra={"motivo": porque, "loja": l["id"], "emendou": c["key"]})
        feitas[c["key"]] = {"dia": dia, "tipo": melhor, "chave": chave}
        self._save(st, now)
        if cid:
            self._registra(f"{chave}:decidiu", now, f"Saindo de lá, resolveu passar {no(l['nome'])} antes de voltar "
                                                    f"({porque}).", share=0.4, importance=0.2)
            logger.info("agenda_viva.emenda de=%s tipo=%s inicio=%s", c["key"], melhor, inicio.strftime("%H:%M"))
        return cid

    def _acabando(self, now: datetime) -> Optional[dict]:
        """O compromisso em Botafogo que acaba nos próximos 15 min (ela está lá)."""
        cands = []
        with self.db.get_connection() as conn:
            rows = [dict(r) for r in conn.execute(
                """SELECT e.source_key, e.event_at, e.end_at, e.metadata_json, p.region FROM eventos_pendentes e
                   LEFT JOIN world_places p ON p.canonical_key=e.location_key
                   WHERE e.confirmed=1 AND e.status='pending' AND (e.source_key LIKE 'outing:%' OR e.source_key LIKE 'vontade:%')
                   AND e.event_at<=? AND e.end_at>? AND e.end_at<=?""",
                (now.isoformat(), now.isoformat(), (now + timedelta(minutes=15)).isoformat()))]
        for r in rows:
            meta = json.loads(r["metadata_json"] or "{}") or {}
            if (r["region"] or "Botafogo") != "Botafogo" or meta.get("origem") == "emenda":
                continue
            tipo = meta.get("tipo") or "role"
            if tipo in ("milo", "mercado", "farmacia"):
                continue                                  # com o cachorro/sacolas vai direto pra casa
            cands.append({"key": r["source_key"], "tipo": tipo, "fim": datetime.fromisoformat(r["end_at"]),
                          "com": tuple(meta.get("friends") or ())})
        try:
            from academia import Academia
            p = Academia(self.db).plano(now.date(), now)
            if p and p["onde"] == "rua" and p["inicio"] <= now < p["fim"] <= now + timedelta(minutes=15):
                cands.append({"key": f"gym:{now.date().isoformat()}", "tipo": "academia", "fim": p["fim"], "com": ()})
        except Exception:
            pass
        return cands[0] if cands else None

    def _proximo_depois(self, at: datetime) -> Optional[datetime]:
        with self.db.get_connection() as conn:
            row = conn.execute("""SELECT MIN(event_at) FROM eventos_pendentes WHERE confirmed=1 AND status='pending'
                                  AND event_at>?""", (at.isoformat(),)).fetchone()
        prox = datetime.fromisoformat(row[0]) if row and row[0] else None
        try:
            from meals import Meals
            refeicao = next((s.at for s in Meals(self.db).day_plan(at.date())
                             if s.where == "casa" and not s.skipped and s.at > at), None)
            if refeicao and (not prox or refeicao < prox):
                prox = refeicao
        except Exception:
            pass
        return prox

    # ---------------------------------------------------------- planeja --
    def planeja(self, now: datetime) -> Optional[int]:
        """À noite, com pique e nada combinado pros próximos dias: ela chama uma amiga pra sair."""
        if not self._livre() or not (PLANEJA_JANELA[0] <= now.time() < PLANEJA_JANELA[1]):
            return None
        st = self._state()
        dia = now.date().isoformat()
        if st.get("planejou") == dia:
            return None
        with self.db.get_connection() as conn:
            marcado = conn.execute(
                """SELECT 1 FROM eventos_pendentes WHERE source_key LIKE 'outing:%' AND status='pending' AND confirmed=1
                   AND event_at>? AND event_at<?""",
                (now.isoformat(), (now + timedelta(days=3)).isoformat())).fetchone()
        if marcado:
            return None
        alvo = next((now.date() + timedelta(days=d) for d in (1, 2, 3)
                     if (now.date() + timedelta(days=d)).weekday() in PROPOSTAS), None)
        if not alvo:
            return None
        amiga = self._amiga(now)
        aval = self.disp.avaliar("role", now, com=(amiga,))
        st["planejou"] = dia                              # pensa nisso uma vez por noite
        if aval.vontade + _jitter(f"planeja:{dia}") < 0.68:
            self._save(st, now)
            return None
        lugar, ini_t, fim_t, texto = PROPOSTAS[alvo.weekday()]
        from social_day import short_name
        quem = short_name(amiga)
        descricao = texto.format(quem=quem)
        ini = datetime.combine(alvo, ini_t)
        fim = datetime.combine(alvo, fim_t)
        topou = _rng(f"topou:{alvo.isoformat()}:{amiga}").random() < 0.8
        porque = (aval.motivo(+1) or ("", "com vontade de sair"))[1]
        dias = ('segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo')
        quando = "amanhã" if alvo == now.date() + timedelta(days=1) else dias[alvo.weekday()]
        cid = None
        if topou:
            from calendar_world import CalendarWorld
            try:
                cid = CalendarWorld(self.db).create_commitment(
                    source_key=f"outing:{alvo.isoformat()}:m{now:%H%M}", event_type="social", description=descricao,
                    start_at=ini, end_at=fim, location_key=lugar,
                    metadata={"friends": [amiga], "origin": "ela_chamou", "origem": "ela_chamou"})
            except ValueError:
                topou = False
        Quem = quem[:1].upper() + quem[1:]
        resumo = (f"Chamou {quem} pra sair {quando} às {ini:%H:%M} ({descricao}); {quem} topou."
                  if topou else f"Chamou {quem} pra sair {quando}, mas {quem} não podia.")
        self._registra(f"agenda:chamou:{alvo.isoformat()}:{amiga}", now, resumo, quem=(amiga,), share=0.8)
        st.setdefault("hoje", []).append({"key": f"chamou:{alvo.isoformat()}", "tipo": "planejou", "texto": resumo,
                                          "motivo": porque, "em": now.isoformat(timespec="minutes")})
        self._save(st, now)
        logger.info("agenda_viva.planejou amiga=%s dia=%s topou=%s (%s)", amiga, alvo, topou, Quem)
        return cid

    def _amiga(self, now: datetime) -> str:
        """Quem ela não vê/fala há mais tempo (a Bia desempata)."""
        try:
            from social_day import SocialDay
            day = SocialDay(self.db)
            def ultimo(k):
                c = day.last_contact(k, now)
                return datetime.fromisoformat(c["event_at"]) if c and c.get("event_at") else datetime.min
            return min(AMIGAS, key=lambda k: (ultimo(k), k != MELHOR_AMIGA))
        except Exception:
            return MELHOR_AMIGA

    # --------------------------------------------------------- conversa --
    def lista_para_conversa(self, now: datetime) -> list[dict]:
        """O que vem nos próximos 3 dias, numerado pro classificador da conversa (agenda_reativa)."""
        out = [i for i in self.itens(now, 72.0) if i.get("origem") != "grade" or i["inicio"].date() <= now.date() + timedelta(days=1)]
        try:
            from social_day import SocialDay
            for inv in SocialDay(self.db).pending_invites(now):
                out.append({"key": inv["key"], "tipo": "convite", "texto": inv["text"], "inv": inv,
                            "inicio": datetime.fromisoformat(inv["start"]), "fim": datetime.fromisoformat(inv["end"]),
                            "com": tuple(inv["friends"]), "origem": "convite"})
        except Exception:
            logger.exception("agenda_viva.convites")
        return sorted(out, key=lambda x: x["inicio"])[:12]

    def pela_conversa(self, it: dict, acao: str, quando: datetime, motivo: str, now: datetime) -> Optional[dict]:
        """Ela decidiu na conversa com o Patrick: aceitar, desistir ou remarcar um item da agenda."""
        motivo = motivo or "combinou com o Patrick"
        st = self._state()
        tipo = it["tipo"]
        res = None
        if tipo == "convite":
            res = self._responde_convite(it, acao == "vai_fazer", motivo, now)
        elif acao == "desistiu":
            aval = Avaliacao(0.0, [("conversa", motivo, -1.0)])
            if tipo in ("role", "academia", "milo", "aula", "mercado_semana"):
                res = self._desiste(it, aval, now, st)
                if res:
                    res["conta"] = False                  # ele está na conversa: já sabe
                    st.pop("aviso", None)
            elif it.get("id"):
                from calendar_world import CalendarWorld
                CalendarWorld(self.db).cancel(it["id"])
                self._registra(f"agenda:desistiu:{it['key']}", now, f"Desistiu: {it['texto']} ({motivo}).", share=0.2)
                res = {"key": it["key"], "tipo": tipo, "texto": it["texto"], "motivo": motivo,
                       "em": now.isoformat(timespec="minutes")}
                st.setdefault("hoje", []).append(res)
        elif acao == "remarcou" and quando > now:
            res = self._remarca(it, quando, motivo, now, st)
        if res:
            st.setdefault("decisoes", {})[it["key"]] = {"em": now.isoformat(timespec="minutes"), "vai": acao != "desistiu",
                                                         "conversa": True}
            self._save(st, now)
            logger.info("agenda_viva.conversa acao=%s key=%s", acao, it["key"])
        return res

    def _responde_convite(self, it: dict, aceita: bool, motivo: str, now: datetime) -> Optional[dict]:
        from social_day import INVITES_KEY, SocialDay
        day = SocialDay(self.db)
        data = day._invites()
        inv = data.get(it["key"])
        if not inv or inv["status"] != "pending":
            return None
        if aceita:
            from calendar_world import CalendarWorld
            try:
                CalendarWorld(self.db).create_commitment(
                    source_key=inv["key"], event_type="social", description=inv["text"],
                    start_at=datetime.fromisoformat(inv["start"]), end_at=datetime.fromisoformat(inv["end"]),
                    location_key=inv["place"], metadata={"friends": inv["friends"], "origin": "convite"})
            except ValueError:
                return None
            inv["status"] = "accepted"
            day._log(f"{inv['key']}:resposta", now, inv["friends"][0], f"Topou o convite: {inv['text']} ({motivo}).")
        else:
            inv["status"], inv["reason"] = "declined", motivo
            day._log(f"{inv['key']}:resposta", now, inv["friends"][0], f"Recusou o convite ({inv['text']}): {motivo}.")
        data[inv["key"]] = inv
        self.db.set_estado_relacional(INVITES_KEY, json.dumps(data, ensure_ascii=False))
        return {"key": inv["key"], "tipo": "convite", "aceitou": aceita}

    def _remarca(self, it: dict, quando: datetime, motivo: str, now: datetime, st: dict) -> Optional[dict]:
        dur = it["fim"] - it["inicio"]
        tipo = it["tipo"]
        if tipo in ("academia", "milo"):
            from academia import Academia, PasseioMilo
            p = (Academia if tipo == "academia" else PasseioMilo)(self.db)
            plano = p._load()
            plano[it["inicio"].date().isoformat()] = None
            plano[quando.date().isoformat()] = {"inicio": quando.isoformat(), "fim": (quando + dur).isoformat(),
                                                "onde": "rua", "origem": "conversa"}
            self.db.set_estado_relacional(p.key, json.dumps(plano))
        elif it.get("id"):
            from calendar_world import CalendarWorld
            try:
                CalendarWorld(self.db).reschedule(it["id"], start_at=quando, end_at=quando + dur)
            except ValueError:
                return None
        else:
            return None
        dias = ('segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo')
        dia = ("hoje" if quando.date() == now.date() else "amanhã" if (quando.date() - now.date()).days == 1
               else dias[quando.weekday()])
        texto = f"Remarcou pra {dia} às {quando:%H:%M}: {it['texto']} ({motivo})."
        self._registra(f"agenda:remarcou:{it['key']}:{now:%H%M}", now, texto, quem=it.get("com", ())[:1], share=0.4)
        res = {"key": it["key"], "tipo": "remarcou", "texto": texto, "motivo": motivo, "em": now.isoformat(timespec="minutes")}
        st.setdefault("hoje", []).append(res)
        return res

    def marca_outro_dia(self, tipo: str, quando: datetime, motivo: str, now: datetime) -> Optional[dict]:
        """"Amanhã vou na academia às 7": vira item da agenda daquele dia, igual ao que ela decide no dia."""
        from vontade import PREP_MIN, SAIDAS, Vontade, _catalogo, no, COISA
        motivo = motivo or "combinou com o Patrick"
        if tipo in ("academia", "milo"):
            from academia import Academia, PasseioMilo
            p = (Academia if tipo == "academia" else PasseioMilo)(self.db)
            plano = p._load()
            dur = timedelta(minutes=70 if tipo == "academia" else 30)
            plano[quando.date().isoformat()] = {"inicio": quando.isoformat(), "fim": (quando + dur).isoformat(),
                                                "onde": "rua", "origem": "conversa"}
            self.db.set_estado_relacional(p.key, json.dumps(plano))
            texto = "Treino na Bodytech" if tipo == "academia" else "Passeio do Milo na Enseada"
        else:
            s = SAIDAS.get(tipo)
            if not s:
                return None
            v = Vontade(self.db)
            extra, ida = {"motivo": motivo}, s.get("ida", 10)
            texto = s["texto"]
            if "categorias" in s:
                lojas = [l for l in _catalogo() if l.get("categoria") in s["categorias"] and l.get("area", "bf") == "bf"
                         and (l.get("abre") or 0) <= quando.hour < (l.get("fecha") or 24) - 1]
                if not lojas:
                    return None
                l = min(lojas, key=lambda x: float(x.get("km") or 9))
                lugar = v._lugar_loja(l)
                texto = texto.format(no=no(l["nome"]), coisa=COISA.get(l.get("categoria"), "alguma coisa"))
                ida = max(3, round(float(l.get("km") or 0.3) * 12) + 2)
                extra["loja"] = l["id"]
            else:
                lugar = s["lugar"]
            ini = quando + timedelta(minutes=ida)
            fim = ini + timedelta(minutes=_rng(f"outro_dia:{quando.isoformat()}").randint(*s["mins"]))
            if not v.agendar(tipo, lugar, ini, fim, texto, origem="conversa", decidido_em=now,
                             chave=f"vontade:{quando.date().isoformat()}:c{quando:%H%M}", modo=s.get("modo", "a_pe"),
                             ida_min=ida, extra=extra):
                return None
        dias = ('segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo')
        dia = "amanhã" if (quando.date() - now.date()).days == 1 else dias[quando.weekday()]
        resumo = f"Combinou com o Patrick: {texto[:1].lower() + texto[1:]} {dia} às {quando:%H:%M} ({motivo})."
        self._registra(f"agenda:marcou:{tipo}:{quando:%Y-%m-%dT%H%M}", now, resumo, share=0.3)
        st = self._state()
        st.setdefault("hoje", []).append({"key": f"marcou:{tipo}:{quando:%Y-%m-%d}", "tipo": "marcou", "texto": resumo,
                                          "motivo": motivo, "em": now.isoformat(timespec="minutes")})
        self._save(st, now)
        logger.info("agenda_viva.marcou tipo=%s quando=%s", tipo, quando.isoformat(timespec="minutes"))
        return {"tipo": tipo, "inicio": quando.isoformat(), "outro_dia": True}

    # ----------------------------------------------------------- prompt --
    def prompt_lines(self, now: datetime) -> list[str]:
        st = self._state()
        hoje = [h for h in st.get("hoje", []) if now - datetime.fromisoformat(h["em"]) <= timedelta(hours=18)]
        linhas = []
        for h in hoje:
            quando = datetime.fromisoformat(h["em"]).strftime("%H:%M")
            if h["tipo"] == "planejou":
                linhas.append(f"- {quando}: {h['texto']} (você mesma que chamou; pode contar como novidade)")
            elif h["tipo"] in ("remarcou", "marcou"):
                linhas.append(f"- {quando}: {h['texto']}")
            else:
                linhas.append(f"- {quando}: {self.detalhe_aviso(h)} (decisão sua, pelo que você estava sentindo)")
        if not linhas:
            return []
        return ["[SUA AGENDA — o que você decidiu]", *linhas,
                "A agenda é sua: se na conversa você mudar de ideia de novo (ir, desistir, remarcar), vale de verdade."]


def now_iso(at: datetime) -> str:
    return datetime.now().isoformat() if at is None else at.isoformat()
