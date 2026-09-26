"""Tempo livre em casa (Patrick, 26/09 — etapa 1 da aba Agora): nada de "tempo livre em casa".

O tempo livre vira o que ela faz de verdade, em blocos de 10 a 90 min: olhando o TikTok,
montando looks, vendo o desfile da Chanel, ouvindo Sabrina Carpenter, jogando Stardew Valley,
se tocando… Regra de ouro dele: **tudo acontece de verdade e vira história** — cada bloco é
acontecimento do dia (ela lembra e pode contar) e tem efeito quando tem (se tocando registra o
orgasmo no corpo dela, igual ao "se resolver sozinha" de antes de dormir).

- O que ela faz sai do horário, do corpo (tesão, energia) e do tempo lá fora; o cômodo não é
  travado, só precisa fazer sentido (desfile na TV do quarto, da sala ou do closet, ou pelo celular
  em qualquer lugar — e aí ela demora mais pra responder).
- O bloco é decidido quando ela está livre naquele momento e fica guardado (não muda depois).
- Mídia é real (artistas, livros, mangás, jogos do cânone 023, marcas). A etapa 2 amplia com
  progresso de leitura, músicas e busca.
- Texto no padrão decidido: gerúndio + o que é ("Ouvindo Sabrina Carpenter"). Vai na linha 2 do
  card; o título em casa é sempre "Em casa".
"""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

KEY = "tempo_livre_json"
GENERICO = ("tempo livre em casa", "curtindo a noite em casa", "em casa, ainda relaxando depois do compromisso anterior")
COMODO = {"quarto": "Quarto", "sala": "Sala", "closet": "Closet", "varanda": "Varanda", "cozinha": "Cozinha",
          "banheiro": "Banheiro", "piscina": "Piscina do prédio", "academia": "Academia do prédio"}

# mídia real (a etapa 2 amplia: progresso, músicas, busca)
ARTISTAS = ("Sabrina Carpenter", "Dua Lipa", "Taylor Swift", "Olivia Rodrigo", "Chappell Roan", "Anitta",
            "Luísa Sonza", "Marina Sena", "Pabllo Vittar", "Liniker", "YOASOBI", "Aimer", "Ado", "NewJeans",
            "BLACKPINK", "TWICE")
LEITURAS = ("o mangá de Sono Bisque Doll", "o mangá de Dandadan", "o mangá de Kaguya-sama",
            "o mangá de Sakura Card Captor", "É Assim que Acaba", "Os Sete Maridos de Evelyn Hugo",
            "De Férias com Você", "a Vogue do mês")
JOGOS = ("Stardew Valley", "The Sims")               # It Takes Two é a dois: não entra sozinha
MARCAS = ("Chanel", "Dior", "Miu Miu", "Prada", "Jacquemus", "Saint Laurent")

# (chave, texto, cômodos, aparelho, horas (de, até), peso, minutos (de, até))
TIPOS = (
    ("instagram", "Olhando o Instagram", ("quarto", "sala"), "celular", (8, 26), 3.0, (15, 40)),
    ("tiktok", "Olhando o TikTok", ("quarto", "sala"), "celular", (8, 26), 3.0, (15, 45)),
    ("x", "Olhando o X", ("quarto", "sala"), "celular", (8, 26), 1.0, (10, 25)),
    ("pinterest", "Olhando o Pinterest", ("quarto", "closet", "sala"), "celular", (8, 25), 1.5, (15, 35)),
    ("closet", "Organizando o closet", ("closet",), None, (9, 21), 0.8, (30, 60)),
    ("looks", "Montando looks", ("closet",), None, (10, 23), 1.2, (25, 50)),
    ("desfile", "Vendo o desfile da {marca}", ("quarto", "sala", "closet", "varanda"), "tela", (10, 25), 1.0, (20, 40)),
    ("croqui", "Desenhando croqui", ("closet",), None, (10, 24), 1.0, (30, 70)),
    ("quarto", "Arrumando o quarto", ("quarto",), None, (9, 20), 0.6, (20, 40)),
    ("milo", "Brincando com o Milo", ("sala", "varanda"), None, (8, 23), 1.5, (10, 25)),
    ("plantas", "Regando as plantas", ("varanda",), None, (7, 10), 0.8, (10, 15)),
    ("plantas_tarde", "Regando as plantas", ("varanda",), None, (17, 19), 0.6, (10, 15)),
    ("musica", "Ouvindo {artista}", ("quarto", "sala", "varanda", "closet"), "fone", (8, 25), 1.5, (20, 45)),
    ("lendo", "Lendo {leitura}", ("sala", "varanda", "quarto"), None, (9, 25), 1.2, (30, 60)),
    ("sol", "Tomando sol", ("varanda", "piscina"), None, (9, 16), 0.7, (30, 60)),
    ("atoa", "Deitada à toa", ("quarto",), None, (13, 26), 1.0, (15, 30)),
    ("jogando", "Jogando {jogo}", ("sala", "quarto"), "tela", (14, 25), 1.0, (40, 90)),
)
SE_TOCANDO = ("se_tocando", "Se tocando", ("quarto",), None, (10, 26), 0.0, (15, 25))
SOLO_BLOCK_CHANCE = 0.35
SOLO_COOLDOWN_H = 8


@dataclass
class Bloco:
    chave: str
    tipo: str
    texto: str               # linha 2 ("Ouvindo Sabrina Carpenter")
    comodo: str              # chave do cômodo ("quarto")
    aparelho: Optional[str]  # celular | tela | fone | None
    pelo_celular: bool
    inicio: datetime
    fim: datetime

    @property
    def comodo_nome(self) -> str:
        return COMODO.get(self.comodo, self.comodo.capitalize())

    @property
    def atividade(self) -> str:
        """Texto do mundo (WorldState → prompt e disponibilidade)."""
        extra = " pelo celular" if self.pelo_celular and self.aparelho == "tela" else ""
        return f"em casa, {self.texto[:1].lower() + self.texto[1:]}{extra} ({self.comodo_nome.lower()})"


def _rng(day: date, salt: str) -> random.Random:
    return random.Random(f"tempo_livre:{day.isoformat()}:{salt}")


def _hora(h: float, lo: int, hi: int) -> bool:
    return lo <= h < hi or lo <= h + 24 < hi         # "26" = 2h da madrugada


class TempoLivre:
    def __init__(self, db):
        self.db = db

    def _state(self) -> dict:
        raw = self.db.get_estado_relacional(KEY)
        try:
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    def _save(self, st: dict, now: datetime) -> None:
        keep = {(now.date() - timedelta(days=d)).isoformat() for d in range(3)}
        st = {k: v for k, v in st.items() if k in keep}
        self.db.set_estado_relacional(KEY, json.dumps(st, ensure_ascii=False))

    @staticmethod
    def _dia(now: datetime) -> date:
        return (now - timedelta(hours=4)).date()        # madrugada conta como a noite anterior

    def _slot(self, now: datetime) -> tuple[int, datetime, datetime]:
        """Blocos fixos por dia (a partir das 04:00): cada um com a duração sorteada do tipo."""
        dia = self._dia(now)
        t = datetime.combine(dia, time(4, 0))
        i = 0
        while True:
            dur = timedelta(minutes=_rng(dia, f"dur:{i}").randint(15, 60))
            if t <= now < t + dur:
                return i, t, t + dur
            t += dur
            i += 1

    def _chuva(self) -> bool:
        try:
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT weather_context_json FROM world_state ORDER BY id DESC LIMIT 1").fetchone()
            w = json.loads(row["weather_context_json"] or "null") if row else None
            return bool(w and (w.get("heavy_rain") or w.get("rain")))
        except Exception:
            return False

    def _quer_se_tocar(self, now: datetime, rng: random.Random) -> bool:
        try:
            from emotion import EmotionEngine, SOLO_MIN_LIBIDO
            engine = EmotionEngine(self.db)
            f = engine.feeling(now)
            last = engine.last_release(now)
        except Exception:
            return False
        if f.libido < SOLO_MIN_LIBIDO or f.excitation >= 0.45:
            return False                                  # sem vontade, ou já no clima com ele
        if last and now - last < timedelta(hours=SOLO_COOLDOWN_H):
            return False
        with self.db.get_connection() as conn:
            if conn.execute("SELECT 1 FROM life_events WHERE event_key=?", (f"solo:{now.date().isoformat()}",)).fetchone():
                return False
        return rng.random() < SOLO_BLOCK_CHANCE

    def _escolhe(self, now: datetime, i: int, inicio: datetime, fim_slot: datetime) -> Bloco:
        dia = self._dia(now)
        rng = _rng(dia, f"tipo:{i}")
        h = inicio.hour + inicio.minute / 60
        chuva = self._chuva()
        if _hora(h, *SE_TOCANDO[4]) and self._quer_se_tocar(now, rng):
            tipo = SE_TOCANDO
        else:
            opcoes = [t for t in TIPOS if _hora(h, *t[4]) and not (t[0] == "sol" and chuva)
                      and not (t[0] == "plantas" and chuva)]
            tipo = rng.choices(opcoes, weights=[t[5] for t in opcoes])[0] if opcoes else TIPOS[0]
        chave, texto, comodos, aparelho, _, _, mins = tipo
        texto = texto.format(marca=rng.choice(MARCAS), artista=rng.choice(ARTISTAS), leitura=rng.choice(LEITURAS),
                             jogo=rng.choice(JOGOS))
        comodo = rng.choice(comodos)
        pelo_celular = aparelho == "celular" or (aparelho == "tela" and comodo not in ("quarto", "sala", "closet"))
        if aparelho == "tela" and not pelo_celular and rng.random() < 0.3:
            pelo_celular = True                           # às vezes vê deitada no celular mesmo com TV
        fim = inicio + timedelta(minutes=rng.randint(*mins))
        return Bloco(f"livre:{dia.isoformat()}:{i}", chave, texto, comodo, aparelho, pelo_celular, inicio,
                     max(fim, inicio + timedelta(minutes=10)))

    def agora(self, now: datetime, *, registrar: bool = True) -> Optional[Bloco]:
        """O bloco de agora (decide e guarda na primeira vez que ela está livre nele).
        Blocos emendam: se o guardado acabou, o próximo começa no fim dele."""
        with self.db.get_connection() as conn:           # mesma trava dos outros: nada antes do início limpo
            if not conn.execute("SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done'").fetchone():
                return None
        i, ini, fim_slot = self._slot(now)
        dia = self._dia(now).isoformat()
        st = self._state()
        guardados = st.get(dia, {})
        for n in range(6):
            chave = f"{i}{'abcdef'[n - 1] if n else ''}"
            g = guardados.get(chave)
            if not g:
                break
            b = Bloco(**{**g, "inicio": datetime.fromisoformat(g["inicio"]), "fim": datetime.fromisoformat(g["fim"])})
            if b.inicio <= now < b.fim:
                return b
            if b.fim > now:
                return None
            ini = b.fim
        else:
            return None
        b = self._escolhe(now, chave, max(ini, now - timedelta(minutes=5)), fim_slot)
        if not registrar:
            return b
        st.setdefault(dia, {})[chave] = {**b.__dict__, "inicio": b.inicio.isoformat(), "fim": b.fim.isoformat()}
        self._save(st, now)
        self._registra(b, now)
        return b

    def _registra(self, b: Bloco, now: datetime) -> None:
        """Vira acontecimento do dia (e, se for o caso, efeito no corpo)."""
        onde = {"quarto": "no quarto", "sala": "na sala", "closet": "no closet", "varanda": "na varanda",
                "piscina": "na piscina do prédio"}.get(b.comodo, "em casa")
        texto = b.texto[:1].lower() + b.texto[1:]
        if b.tipo == "se_tocando":
            return self._se_tocou(b, now, onde)
        summary = f"Ficou {texto}{' pelo celular' if b.pelo_celular and b.aparelho == 'tela' else ''} {onde}."
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'tempo_livre',?,?,'simulated',1,0.1,?,0.3,?)""",
                (b.chave, b.inicio.isoformat(), b.texto, summary, json.dumps(["marina"]), now.isoformat()))
            conn.commit()

    def _se_tocou(self, b: Bloco, now: datetime, onde: str) -> None:
        """Vale no corpo: mesma marca do "se resolver sozinha" (uma por dia), orgasmo e alívio."""
        from emotion import EmotionEngine, RELEASE_KEY, SOLO_TELL_CHANCE
        key = f"solo:{b.inicio.date().isoformat()}"
        rng = _rng(self._dia(b.inicio), "conta")
        tells = rng.random() < SOLO_TELL_CHANCE
        summary = (f"Com tesão, se tocou {onde} e se resolveu sozinha, pensando no Patrick."
                   + (" Pode contar pra ele, do jeito dela, se vier a calhar." if tells
                      else " Guardou só pra ela: não conta pro Patrick."))
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'routine','sozinha',?,'simulated',1,0.2,?,?,?)""",
                (key, b.inicio.isoformat(), summary, json.dumps(["marina"]), 0.6 if tells else 0.0, now.isoformat()))
            conn.commit()
        if not cur.rowcount:
            return
        if not tells:
            try:
                from social_day import SocialDay
                SocialDay(self.db).mark_shared(key)
            except Exception:
                pass
        gozo = b.inicio + (b.fim - b.inicio) * 0.8
        self.db.set_estado_relacional(RELEASE_KEY, gozo.isoformat())
        EmotionEngine(self.db).feel("alegria", "alivio", 0.3, "se resolveu sozinha", gozo, source_key=f"{key}:alivio")

    def atual(self, now: datetime) -> Optional[Bloco]:
        """Só leitura (card): o bloco guardado que cobre agora."""
        for g in self._state().get(self._dia(now).isoformat(), {}).values():
            b = Bloco(**{**g, "inicio": datetime.fromisoformat(g["inicio"]), "fim": datetime.fromisoformat(g["fim"])})
            if b.inicio <= now < b.fim:
                return b
        return None

    def do_dia(self, now: datetime) -> list[Bloco]:
        out = [Bloco(**{**g, "inicio": datetime.fromisoformat(g["inicio"]), "fim": datetime.fromisoformat(g["fim"])})
               for g in self._state().get(self._dia(now).isoformat(), {}).values()]
        return sorted(out, key=lambda b: b.inicio)
