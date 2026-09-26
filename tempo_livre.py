"""Tempo livre em casa (Patrick, 26/09 — etapa 1 da aba Agora): nada de "tempo livre em casa".

O tempo livre vira o que ela faz de verdade, em blocos de 10 a 90 min: olhando o TikTok,
montando looks, vendo o desfile da Chanel, ouvindo Sabrina Carpenter, jogando Stardew Valley,
se masturbando… Regra de ouro dele: **tudo acontece de verdade e vira história** — cada bloco é
acontecimento do dia (ela lembra e pode contar) e tem efeito quando tem (a masturbação registra
o orgasmo no corpo dela).

Masturbação (Patrick, 26/09): sem limite — com tesão, em casa, ela goza quando quiser; quem segura
é o próprio corpo (depois do gozo a vontade cai e volta aos poucos). Com saudade ou desejo por ele,
às vezes ela aproveita o momento e chama ele pro sexting.

- O que ela faz sai do horário, do corpo (tesão, energia) e do tempo lá fora; o cômodo não é
  travado, só precisa fazer sentido (desfile na TV do quarto, da sala ou do closet, ou pelo celular
  em qualquer lugar — e aí ela demora mais pra responder).
- O bloco é decidido quando ela está livre naquele momento e fica guardado (não muda depois).
- Mídia é real (Patrick, 26/09): a música é a playlist dela com faixas reais (`musica.py`), a
  leitura anda de verdade, com volume e página (`leitura.py`), e em dia de jogo do Botafogo ela vê
  na TV da sala (`futebol.py`), a não ser que tenha saído pra ver fora.
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

from musica import ARTISTAS  # noqa: E402  (mídia real: a playlist dela sai do musica.py)
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
MASTURBANDO = ("masturbando", "Se masturbando", ("quarto",), None, (8, 27), 0.0, (15, 25))
# 26/09 (Patrick): unha gasta e entediada → faz em casa (esmalte comum; a vez em si mora no unhas.py)
UNHAS = ("unhas", "Fazendo as unhas", ("quarto", "sala", "varanda"), None, (9, 23), 0.0, (40, 60))
SOLO_BLOCK_CHANCE = 0.45            # com tesão (>= SOLO_MIN_LIBIDO); mais tesão, mais chance
CHAMA_ELE_CHANCE = 0.5              # com saudade/desejo por ele, chama pro sexting
CONVITE_KEY = "sexting_convite_json"


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
    chama_ele: bool = False  # masturbação: aproveita e chama o Patrick pro sexting
    faixas: Optional[list] = None   # música: a playlist real que toca no bloco
    leitura: Optional[dict] = None  # leitura: título, volume, páginas (início → fim)
    jogo: Optional[str] = None      # jogo do Botafogo (id da ESPN)

    @property
    def comodo_nome(self) -> str:
        return COMODO.get(self.comodo, self.comodo.capitalize())

    @property
    def atividade(self) -> str:
        """Texto do mundo (WorldState → prompt e disponibilidade)."""
        extra = " pelo celular" if self.pelo_celular and self.aparelho == "tela" else ""
        if self.chama_ele:
            extra = " pensando no Patrick e chamando ele pro sexting"
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

    def _quer_se_masturbar(self, now: datetime, rng: random.Random) -> Optional[bool]:
        """None: não quer. False: quer, sozinha. True: quer e chama o Patrick (saudade/desejo por ele).
        Sem cota nem intervalo fixo: o tesão depois do gozo cai sozinho (emotion._libido)."""
        try:
            from emotion import EmotionEngine, SOLO_MIN_LIBIDO, PATRICK_TARGET
            f = EmotionEngine(self.db).feeling(now)
        except Exception:
            return None
        if f.libido < SOLO_MIN_LIBIDO or f.excitation >= 0.45:
            return None                                   # sem vontade, ou já no clima com ele
        if rng.random() >= SOLO_BLOCK_CHANCE + 1.5 * (f.libido - SOLO_MIN_LIBIDO):
            return None
        chateada = f.bond.get("hurt", 0) >= 0.25 or any(
            e.target == PATRICK_TARGET and e.family in ("tristeza", "raiva") and e.intensity >= 0.15 for e in f.episodes)
        quer_ele = f.missing >= 0.35 or f.bond.get("romantic_intensity", 0) >= 0.85
        return bool(quer_ele and not chateada and rng.random() < CHAMA_ELE_CHANCE)

    def _escolhe(self, now: datetime, i: int, inicio: datetime, fim_slot: datetime, registrar: bool = True) -> Bloco:
        dia = self._dia(now)
        rng = _rng(dia, f"tipo:{i}")
        h = inicio.hour + inicio.minute / 60
        chuva = self._chuva()
        chama_ele = self._quer_se_masturbar(now, rng) if _hora(h, *MASTURBANDO[4]) else None
        try:                                              # 26/09: voltou correndo pra casa por tesão
            from agenda_reativa import AgendaReativa
            alivio = AgendaReativa(self.db).alivio_em_casa(inicio, consumir=registrar)
            if alivio is not None:
                chama_ele = alivio
        except Exception:
            logger.exception("tempo_livre.alivio")
        unhas = False
        if chama_ele is None:
            try:
                from unhas import Unhas
                unhas = Unhas(self.db).quer_em_casa(now, inicio, rng)
            except Exception:
                logger.exception("tempo_livre.unhas")
        if chama_ele is not None:
            tipo = MASTURBANDO
        elif unhas:
            tipo = UNHAS
        else:
            opcoes = [t for t in TIPOS if _hora(h, *t[4]) and not (t[0] == "sol" and chuva)
                      and not (t[0] == "plantas" and chuva)]
            tipo = rng.choices(opcoes, weights=[t[5] for t in opcoes])[0] if opcoes else TIPOS[0]
            musica_dele = self._musica_dele()
            if musica_dele and any(t[0] == "musica" for t in opcoes) and rng.random() < 0.7:
                tipo = next(t for t in TIPOS if t[0] == "musica")   # o Patrick mandou música: ela vai ouvir
        chave, texto, comodos, aparelho, _, _, mins = tipo
        texto = texto.format(marca=rng.choice(MARCAS), artista=rng.choice(ARTISTAS), leitura=rng.choice(LEITURAS),
                             jogo=rng.choice(JOGOS))
        comodo = rng.choice(comodos)
        pelo_celular = aparelho == "celular" or (aparelho == "tela" and comodo not in ("quarto", "sala", "closet"))
        if aparelho == "tela" and not pelo_celular and rng.random() < 0.3:
            pelo_celular = True                           # às vezes vê deitada no celular mesmo com TV
        fim = max(inicio + timedelta(minutes=rng.randint(*mins)), inicio + timedelta(minutes=10))
        faixas = leitura = None
        if chave == "musica":
            from musica import Musica
            faixas = Musica(self.db).playlist(inicio, fim, rng) or None
            if faixas:
                texto = f"Ouvindo {faixas[0]['artista']}"
        elif chave == "lendo" and registrar:
            from leitura import Leitura
            sessao = Leitura(self.db).sessao(inicio, fim, rng, now)
            if sessao:
                texto = sessao.texto
                leitura = {"titulo": sessao.titulo, "vol": sessao.vol, "pag_ini": sessao.pag_ini,
                           "pag_fim": sessao.pag_fim, "pags": sessao.pags, "terminou": sessao.terminou}
            else:                                         # nada pra ler em casa: fica no celular
                chave, texto, aparelho, pelo_celular = "instagram", "Olhando o Instagram", "celular", True
        return Bloco(f"livre:{dia.isoformat()}:{i}", chave, texto, comodo, aparelho, pelo_celular, inicio,
                     fim, bool(chama_ele), faixas, leitura)

    def _musica_dele(self) -> bool:
        try:
            from musica import Musica
            return bool(Musica(self.db).dela()["ouvir"])
        except Exception:
            return False

    def _jogo(self, now: datetime, st: dict, dia: str, registrar: bool) -> Optional[Bloco]:
        """Dia de jogo do Botafogo e ela em casa: vê na TV da sala (o bloco é o jogo inteiro)."""
        try:
            from futebol import Futebol, DURACAO
            fut = Futebol(self.db)
            j = fut.jogo_em(now)
        except Exception:
            return None
        if not j:
            return None
        chave = f"j{j['id']}"
        g = st.get(dia, {}).get(chave)
        if g:
            return Bloco(**{**g, "inicio": datetime.fromisoformat(g["inicio"]), "fim": datetime.fromisoformat(g["fim"])})
        ini = datetime.fromisoformat(j["inicio"])
        b = Bloco(f"jogo:{j['id']}", "jogo", f"Vendo {fut.titulo(j)}", "sala", "tela", False,
                  max(ini - timedelta(minutes=5), now - timedelta(minutes=2)), ini + DURACAO, jogo=j["id"])
        if registrar:
            st.setdefault(dia, {})[chave] = {**b.__dict__, "inicio": b.inicio.isoformat(), "fim": b.fim.isoformat()}
            self._save(st, now)
            with self.db.get_connection() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                       autonomy_level,importance,participants_json,share_worthy,created_at)
                       VALUES (?,?,'tempo_livre',?,?,'real_world',1,0.4,?,0.6,?)""",
                    (b.chave, b.inicio.isoformat(), b.texto,
                     f"Viu {fut.titulo(j)} ({j['competicao']}) na TV da sala, torcendo pelo Botafogo.",
                     json.dumps(["marina"]), now.isoformat()))
                conn.commit()
        return b

    def agora(self, now: datetime, *, registrar: bool = True) -> Optional[Bloco]:
        """O bloco de agora (decide e guarda na primeira vez que ela está livre nele).
        Blocos emendam: se o guardado acabou, o próximo começa no fim dele."""
        with self.db.get_connection() as conn:           # mesma trava dos outros: nada antes do início limpo
            if not conn.execute("SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done'").fetchone():
                return None
        i, ini, fim_slot = self._slot(now)
        dia = self._dia(now).isoformat()
        st = self._state()
        jogo = self._jogo(now, st, dia, registrar)
        if jogo:
            return jogo
        guardados = {k: v for k, v in st.get(dia, {}).items() if not k.startswith("j")}
        for n in range(6):
            chave = f"{i}{'abcdef'[n - 1] if n else ''}"
            g = guardados.get(chave)
            if not g:
                break
            b = Bloco(**{**g, "inicio": datetime.fromisoformat(g["inicio"]), "fim": datetime.fromisoformat(g["fim"])})
            if b.inicio <= now < b.fim:
                if b.faixas and registrar:
                    self._ouviu(b, now)
                if b.tipo == "unhas":                     # a cor aparece quando ela decide (ou ele escolhe)
                    from unhas import Unhas
                    b.texto = Unhas(self.db).texto_bloco(now)
                return b
            if b.fim > now:
                return None
            ini = b.fim
        else:
            return None
        b = self._escolhe(now, chave, max(ini, now - timedelta(minutes=5)), fim_slot, registrar)
        if not registrar:
            return b
        st.setdefault(dia, {})[chave] = {**b.__dict__, "inicio": b.inicio.isoformat(), "fim": b.fim.isoformat()}
        self._save(st, now)
        self._registra(b, now)
        return b

    def _ouviu(self, b: Bloco, now: datetime) -> None:
        try:
            from musica import Musica
            Musica(self.db).ouviu(b.faixas, now)
        except Exception:
            logger.exception("tempo_livre.musica_ouviu")

    def _registra(self, b: Bloco, now: datetime) -> None:
        """Vira acontecimento do dia (e, se for o caso, efeito no corpo)."""
        onde = {"quarto": "no quarto", "sala": "na sala", "closet": "no closet", "varanda": "na varanda",
                "piscina": "na piscina do prédio"}.get(b.comodo, "em casa")
        texto = b.texto[:1].lower() + b.texto[1:]
        if b.tipo in ("masturbando", "se_tocando"):
            return self._se_masturbou(b, now, onde)
        if b.tipo == "unhas":                             # o acontecimento sai no fim, com a cor (unhas.py)
            from unhas import Unhas
            Unhas(self.db).comecou_em_casa(b.inicio, b.fim, now, b.chave)
            return
        summary = f"Ficou {texto}{' pelo celular' if b.pelo_celular and b.aparelho == 'tela' else ''} {onde}."
        if b.faixas:
            nomes = [f"\"{f['nome']}\" ({f['artista']})" for f in b.faixas[:4]]
            summary = f"Ficou ouvindo a playlist dela {onde}: " + ", ".join(nomes) + "."
        elif b.leitura:
            summary = (f"Ficou {texto} {onde}, da página {b.leitura['pag_ini']} até a {b.leitura['pag_fim']}"
                       + (" (terminou)." if b.leitura["terminou"] else "."))
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'tempo_livre',?,?,'simulated',1,0.1,?,0.3,?)""",
                (b.chave, b.inicio.isoformat(), b.texto, summary, json.dumps(["marina"]), now.isoformat()))
            conn.commit()

    def _se_masturbou(self, b: Bloco, now: datetime, onde: str) -> None:
        """Vale no corpo: orgasmo e alívio. Chamando ele, vira convite pro sexting (proatividade)."""
        from emotion import EmotionEngine, RELEASE_KEY, SOLO_TELL_CHANCE
        key = f"solo:{b.chave}"
        rng = _rng(self._dia(b.inicio), f"conta:{b.chave}")
        tells = b.chama_ele or rng.random() < SOLO_TELL_CHANCE
        if b.chama_ele:
            summary = (f"Com tesão e querendo o Patrick, se masturbou {onde} e chamou ele pra entrar no clima "
                       "junto (sexting).")
            self.db.set_estado_relacional(CONVITE_KEY, json.dumps(
                {"key": key, "inicio": b.inicio.isoformat(), "fim": b.fim.isoformat(), "enviado": False}))
        else:
            summary = (f"Com tesão, se masturbou {onde} pensando no Patrick."
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
        EmotionEngine(self.db).feel("alegria", "alivio", 0.3, "se masturbou e gozou", gozo, source_key=f"{key}:alivio")

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


def convite_sexting(db, now: datetime) -> Optional[dict]:
    """O convite pro sexting de agora (masturbação chamando ele), se ainda não foi mandado."""
    raw = db.get_estado_relacional(CONVITE_KEY)
    try:
        c = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return None
    if not c or c.get("enviado"):
        return None
    if not datetime.fromisoformat(c["inicio"]) <= now < datetime.fromisoformat(c["fim"]):
        return None
    return c


def marca_convite_enviado(db) -> None:
    raw = db.get_estado_relacional(CONVITE_KEY)
    try:
        c = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return
    if c:
        c["enviado"] = True
        db.set_estado_relacional(CONVITE_KEY, json.dumps(c))
