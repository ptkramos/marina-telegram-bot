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
import re
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
UMA_VEZ_POR_DIA = ("plantas", "plantas_tarde")        # soak, dia 2: regar as plantas não se repete no dia
CORINGA = ("instagram", "tiktok", "milo")              # quando o horário só deixava o que acabou de fazer
MASTURBANDO = ("masturbando", "Se masturbando", ("quarto",), None, (8, 27), 0.0, (15, 25))
# 26/09 (Patrick): unha gasta e entediada → faz em casa (esmalte comum; a vez em si mora no unhas.py)
UNHAS = ("unhas", "Fazendo as unhas", ("quarto", "sala", "varanda"), None, (9, 23), 0.0, (40, 60))
# 26/09 (Patrick): cabelo ressecado e entediada → umectação (óleo e touca; lava no próximo banho — cabelo.py)
UMECTACAO = ("umectacao", "Umectando o cabelo", ("quarto", "sala", "varanda"), "celular", (10, 21), 0.0, (60, 90))
# 03/10 (Patrick, soak dia 5): o sexting não aparecia no Agora nem no Hoje — das 15:04 às 15:44 o mundo tinha ela
# "olhando o Pinterest no closet", e às 15:41 ela usou isso na fala. Agora o modo íntimo vira bloco em casa.
SEXTING_TEXTO = "Transando com o Patrick por mensagem"
# Ele no clima (pede, provoca de volta, descreve) × ele pedindo pra parar (soak, dia 6: "Marinaaa paraaa é sério eu não
# quero saber… não me provoca quando eu tô no trabalho")
ENTROU_RE = re.compile(r"goz|te comer|me chupa|\bmete\b|enfia|se toca|te toca|me toca|tira a roupa|abre as pernas|"
                       r"molhad|pelad|\bnua\b|manda (?:foto|nude)|quero (?:te|você|vc|ver)|lingerie|calcinha|tes[aã]o|"
                       r"geme|safad|gostosa|\bpau\b|duro")
RECUSA_RE = re.compile(r"\bpa+ra+\b|n[aã]o me provoca|n[aã]o quero saber|para de me provocar|agora n[aã]o|"
                       r"vai (?:botar|colocar|por) (?:uma )?roupa|vai se vestir|t[oô] no trabalho")
SE_TOCAR_RE = re.compile(r"\bvou\s+me\s+(?:divertir|tocar|masturbar|aliviar)\b|\bvou\s+(?:gozar|terminar)\s+sozinha\b")
SEXTING_FOLGA = timedelta(minutes=5)   # o bloco vai até 5 min depois da última fala no clima
SEXTING_EMENDA = timedelta(minutes=15)   # voltou ao clima logo depois (o gozo dela antes do dele): mesmo bloco
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
    gozou: bool = False             # sexting: ela gozou

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

    def atividade_em(self, now: datetime) -> str:
        """28/09: o story das 14:09 era "Baby 95" (Liniker) e o mundo dizia "ouvindo Sabrina Carpenter" o bloco
        inteiro (a 1ª faixa). Na música, o mundo acompanha a faixa que está tocando."""
        if self.faixas:
            from musica import Musica
            f = Musica.tocando(self.faixas, now)
            if f:
                return (f'em casa, ouvindo "{f["nome"]}" ({f["artista"]}) na playlist dela'
                        f' ({self.comodo_nome.lower()})')
        return self.atividade


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

    def _feitos(self, dia: date, antes_de: datetime) -> list[str]:
        """Tipos dos blocos do dia que começaram antes de `antes_de`, em ordem."""
        blocos = [g for k, g in self._state().get(dia.isoformat(), {}).items() if not k.startswith("j")]
        blocos = [g for g in blocos if datetime.fromisoformat(g["inicio"]) < antes_de]
        return [g["tipo"] for g in sorted(blocos, key=lambda g: g["inicio"])]

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
            return bool(w and (w.get("heavy_rain") or w.get("condition") in ("rain", "storm")))
        except Exception:
            return False

    def _sol(self) -> bool:
        """Soak, dia 5 (03/10, 14:37): "tomando sol (piscina do prédio)" com garoa e 100% de nuvens o dia todo —
        o filtro só olhava chuva forte. Sol de verdade é céu limpo (Open-Meteo 0–1); sem tempo conhecido, não."""
        try:
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT weather_context_json FROM world_state ORDER BY id DESC LIMIT 1").fetchone()
            w = json.loads(row["weather_context_json"] or "null") if row else None
            return bool(w and w.get("condition") == "clear")
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
        umectar = False
        if chama_ele is None and not unhas:
            try:
                from cabelo import Cabelo
                umectar = Cabelo(self.db).quer_umectar(now, inicio, rng)
            except Exception:
                logger.exception("tempo_livre.umectacao")
        if chama_ele is not None:
            tipo = MASTURBANDO
        elif unhas:
            tipo = UNHAS
        elif umectar:
            tipo = UMECTACAO
        else:
            opcoes = [t for t in TIPOS if _hora(h, *t[4]) and not (t[0] == "sol" and not self._sol())
                      and not (t[0] == "plantas" and chuva)]
            # Soak, dia 2 (30/09): "Regando as plantas" 07:01, 07:26, 07:39, 07:49 — cada pedaço sorteava de novo.
            # O que ela acabou de fazer não se repete em seguida; regar as plantas é uma vez por dia.
            feitos = self._feitos(dia, inicio)

            def _pode(t) -> bool:
                return t[0] != (feitos[-1] if feitos else None) and not (t[0] in UMA_VEZ_POR_DIA and t[0] in feitos)
            sem_repetir = [t for t in opcoes if _pode(t)]
            if not sem_repetir:                           # antes das 8 só havia "plantas": celular ou o Milo
                sem_repetir = [t for t in TIPOS if t[0] in CORINGA and _pode(t)]
            opcoes = sem_repetir or opcoes
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
        fim = min(fim, self._ate(inicio, fim))
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

    def _ate(self, inicio: datetime, fim: datetime) -> datetime:
        """27/09 (linha do tempo de 26/09): "Montou looks" até 15:11 com a academia saindo às 14:53. O bloco
        acaba quando começa a próxima coisa marcada: o Se arrumando de uma saída (ou de dormir) ou uma
        refeição em casa."""
        cortes = []
        try:
            from agenda import Agenda
            cortes += [e.inicio for e in Agenda(self.db).etapas(inicio.date(), inicio)]
        except Exception:
            logger.exception("tempo_livre.ate.agenda")
        try:
            from meals import Meals
            cortes += [s.at for s in Meals(self.db).day_plan(inicio.date()) if s.where == "casa" and not s.skipped]
        except Exception:
            logger.exception("tempo_livre.ate.refeicoes")
        prox = min((c for c in cortes if inicio + timedelta(minutes=5) <= c < fim), default=fim)
        return prox

    def interrompe(self, at: datetime, now: datetime) -> bool:
        """27/09: outra coisa começou (banho, refeição, se arrumando, saída, dormir) — o bloco que cobria
        esse momento acaba ali (a música não atravessa o banho). Devolve se cortou."""
        st = self._state()
        dia = self._dia(now).isoformat()
        cortou = False
        for chave, g in st.get(dia, {}).items():
            ini, fim = datetime.fromisoformat(g["inicio"]), datetime.fromisoformat(g["fim"])
            if not (ini < at < fim) or g.get("tipo") in ("unhas", "umectacao"):
                continue                                  # esmalte secando e touca seguem por baixo do resto
            g["fim"] = at.isoformat()
            if g.get("faixas"):
                g["faixas"] = [f for f in g["faixas"] if datetime.fromisoformat(f["at"]) < at] or g["faixas"][:1]
            cortou = True
            b = Bloco(**{**g, "inicio": ini, "fim": at})
            if b.tipo not in ("masturbando", "se_tocando", "unhas") and not chave.startswith("j"):
                with self.db.get_connection() as conn:
                    conn.execute("UPDATE life_events SET summary=? WHERE event_key=?", (self._resumo(b), b.chave))
                    conn.commit()
        if cortou:
            self._save(st, now)
            logger.info("tempo_livre.interrompido at=%s", at.isoformat(timespec="minutes"))
        return cortou

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
        sexting = self._sexting_aberto(now)
        if sexting:
            return sexting
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
        # 28/09 (auditoria): "Viu o desfile 15:53–16:20" e "Montou looks" às 16:16 — o bloco da faixa anterior
        # ainda corria; o novo começa quando ele acaba
        anterior = max((datetime.fromisoformat(v["fim"]) for v in guardados.values()
                        if datetime.fromisoformat(v["inicio"]) < now), default=datetime.min)
        b = self._escolhe(now, chave, max(ini, now - timedelta(minutes=5), self._chegou(now), min(anterior, now)),
                          fim_slot, registrar)
        if not registrar:
            return b
        st.setdefault(dia, {})[chave] = {**b.__dict__, "inicio": b.inicio.isoformat(), "fim": b.fim.isoformat()}
        self._save(st, now)
        self._registra(b, now)
        return b

    def _chegou(self, now: datetime) -> datetime:
        """27/09: o bloco em casa não começa antes de ela chegar (o Instagram "no quarto" às 00:02, com ela
        no uber até 00:05)."""
        try:
            from commute import Commute
            volta = Commute(self.db).ultima_volta(now, timedelta(minutes=15))
        except Exception:
            volta = None
        chegou = volta.end if volta else datetime.min
        # 28/09 (auditoria, rodada 3): nem antes de acabar o que ela fazia em casa — "Brincando com o Milo" às
        # 21:50 com o xixi da noite indo até 21:53.
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT MAX(end_at) FROM life_events WHERE end_at<=? AND end_at>=?",
                               (now.isoformat(), (now - timedelta(minutes=15)).isoformat())).fetchone()
        if row and row[0]:
            chegou = max(chegou, datetime.fromisoformat(row[0]).replace(tzinfo=None))
        try:
            # Soak, dia 2 (30/09): "Regando as plantas" às 07:26 com o banho indo até 07:30 — o banho acabado (e a
            # refeição) também é o que ela fazia em casa.
            raw = self.db.get_estado_relacional("pending_transition_json")
            fim = datetime.fromisoformat(json.loads(raw)["end_at"]) if raw else None
            if fim and now - timedelta(minutes=15) <= fim <= now:
                chegou = max(chegou, fim)
        except (TypeError, ValueError, KeyError):
            pass
        return chegou

    def _ouviu(self, b: Bloco, now: datetime) -> None:
        try:
            from musica import Musica
            Musica(self.db).ouviu(b.faixas, now)
        except Exception:
            logger.exception("tempo_livre.musica_ouviu")

    @staticmethod
    def _onde(b: Bloco) -> str:
        return {"quarto": "no quarto", "sala": "na sala", "closet": "no closet", "varanda": "na varanda",
                "piscina": "na piscina do prédio"}.get(b.comodo, "em casa")

    def _resumo(self, b: Bloco) -> str:
        onde, texto = self._onde(b), b.texto[:1].lower() + b.texto[1:]
        if b.tipo == "sexting":
            verbo = "Provocou" if self._so_ela(b) else "Transou com"
            return f"{verbo} o Patrick por mensagem {onde}{' e gozou' if b.gozou else ''}."
        if b.faixas:
            nomes = [f"\"{f['nome']}\" ({f['artista']})" for f in b.faixas[:4]]
            return f"Ficou ouvindo a playlist dela {onde}: " + ", ".join(nomes) + "."
        if b.leitura:
            return (f"Ficou {texto} {onde}, da página {b.leitura['pag_ini']} até a {b.leitura['pag_fim']}"
                    + (" (terminou)." if b.leitura["terminou"] else "."))
        return f"Ficou {texto}{' pelo celular' if b.pelo_celular and b.aparelho == 'tela' else ''} {onde}."

    def _registra(self, b: Bloco, now: datetime) -> None:
        """Vira acontecimento do dia (e, se for o caso, efeito no corpo)."""
        if b.tipo in ("masturbando", "se_tocando"):
            return self._se_masturbou(b, now, self._onde(b))
        if b.tipo == "unhas":                             # o acontecimento sai no fim, com a cor (unhas.py)
            from unhas import Unhas
            Unhas(self.db).comecou_em_casa(b.inicio, b.fim, now, b.chave)
            return
        if b.tipo == "umectacao":                         # touca até o fim; lava no próximo banho (cabelo.py)
            from cabelo import Cabelo
            Cabelo(self.db).umectou(b.inicio, b.fim, now)
        sexting = b.tipo == "sexting"                     # foi com ele: ela lembra, mas não tem o que contar
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'tempo_livre',?,?,'simulated',1,?,?,?,?)""",
                (b.chave, b.inicio.isoformat(), b.texto, self._resumo(b), 0.3 if sexting else 0.1,
                 json.dumps(["marina", "patrick"] if sexting else ["marina"]), 0.0 if sexting else 0.3,
                 now.isoformat()))
            conn.commit()
        if sexting:
            try:
                from social_day import SocialDay
                SocialDay(self.db).mark_shared(b.chave)
            except Exception:
                pass

    # ------------------------------------------------------------ sexting --
    @staticmethod
    def _bloco(g: dict) -> Bloco:
        return Bloco(**{**g, "inicio": datetime.fromisoformat(g["inicio"]), "fim": datetime.fromisoformat(g["fim"])})

    def _sextings(self, st: dict, dia: str) -> list[tuple[str, dict]]:
        return sorted(((k, g) for k, g in st.get(dia, {}).items() if g.get("tipo") == "sexting"),
                      key=lambda kg: kg[1]["inicio"])

    def _sexting_aberto(self, now: datetime) -> Optional[Bloco]:
        for _, g in self._sextings(self._state(), self._dia(now).isoformat()):
            b = self._bloco(g)
            if b.inicio <= now < b.fim:
                return b
        return None

    def _sexting_recente(self, st: dict, now: datetime) -> Optional[dict]:
        """O último sexting do dia, se acabou há pouco e nada começou depois dele (dá pra emendar)."""
        dia = self._dia(now).isoformat()
        sextings = self._sextings(st, dia)
        if not sextings:
            return None
        chave, g = sextings[-1]
        fim = datetime.fromisoformat(g["fim"])
        if fim + SEXTING_EMENDA < now:
            return None
        if any(k != chave and not k.startswith("j") and fim <= datetime.fromisoformat(o["inicio"]) <= now
               for k, o in st.get(dia, {}).items()):
            return None
        return g

    def _so_ela(self, b: Bloco) -> bool:
        """Soak, dia 6 (04/10, 15:08–15:31; decisão do Patrick): "Transou com o Patrick" com ele dizendo "não me
        provoca no trabalho". Só ela no clima — o último "para" dele veio depois de tudo que ele entrou — é
        "Provocou o Patrick". Sem recusa dele fica "Transou" (nem todo jeito de entrar no clima casa com a lista)."""
        try:
            with self.db.get_connection() as conn:
                rows = conn.execute("SELECT content FROM conversas WHERE role='user' AND timestamp>=? AND timestamp<=?"
                                    " ORDER BY id", (b.inicio.isoformat(), b.fim.isoformat())).fetchall()
        except Exception:
            return False
        ultima = None
        for (texto,) in rows:
            t = (texto or "").lower()
            if RECUSA_RE.search(t):
                ultima = "recusa"
            elif ENTROU_RE.search(t):
                ultima = "entrou"
        return ultima == "recusa"

    def promessa_de_se_tocar(self, fala: str, dele: str, now: datetime) -> bool:
        """Soak, dia 6 (04/10, 15:26; decisão do Patrick): "Divirta-se aí sozinha" → "vou me divertir sim" e o mundo
        foi pra playlist na sala. Ela disse que vai se tocar sozinha e o tesão deixa: o próximo bloco em casa é esse.
        Gozou há menos de 1 h, ou o tesão está baixo: fica só na fala."""
        fala = (fala or "").lower()
        if not SE_TOCAR_RE.search(fala):
            return False
        if not (re.search(r"masturb|aliviar", fala) or "sozinha" in fala or "sozinha" in (dele or "").lower()):
            return False
        try:
            from emotion import EmotionEngine, TESAO_MIN
            f = EmotionEngine(self.db).feeling(now)
        except Exception:
            logger.exception("tempo_livre.promessa_de_se_tocar")
            return False
        if f.excitation < 0.45 and f.libido < TESAO_MIN:
            logger.info("tempo_livre.vai_se_tocar nao: tesao=%.2f excitacao=%.2f", f.libido, f.excitation)
            return False
        if f.hours_since_release is not None and f.hours_since_release < 1:
            return False
        from agenda_reativa import AgendaReativa
        AgendaReativa(self.db).marcar_alivio_em_casa(now, now)
        logger.info("tempo_livre.vai_se_tocar sim: tesao=%.2f excitacao=%.2f", f.libido, f.excitation)
        return True

    def _em_casa_livre(self, now: datetime) -> bool:
        """Em casa e no tempo livre dela (não numa saída, refeição, banho ou dormindo)."""
        with self.db.get_connection() as conn:
            if not conn.execute("SELECT 1 FROM world_bootstrap WHERE key='clean_canonical_start_done'").fetchone():
                return False
            row = conn.execute("SELECT activity FROM world_state WHERE observed_at<=? ORDER BY observed_at DESC, id DESC"
                               " LIMIT 1", (now.isoformat(),)).fetchone()
        return bool(row and (row["activity"] or "").casefold().startswith("em casa, "))

    def sexting(self, now: datetime) -> Optional[Bloco]:
        """Modo íntimo ligado com ela em casa: o que ela faz agora é o sexting. Abre o bloco (o que ela fazia acaba
        ali) ou estica até SEXTING_FOLGA depois desta fala."""
        st = self._state()
        g = self._sexting_recente(st, now)
        if g:
            g["fim"] = max(datetime.fromisoformat(g["fim"]), now + SEXTING_FOLGA).isoformat()
            self._save(st, now)
            b = self._bloco(g)
            with self.db.get_connection() as conn:          # quem entrou no clima pode mudar a cada fala
                conn.execute("UPDATE life_events SET summary=? WHERE event_key=?", (self._resumo(b), b.chave))
                conn.commit()
            return b
        if not self._em_casa_livre(now):
            return None
        self.interrompe(now, now)
        st = self._state()
        dia = self._dia(now).isoformat()
        n = len(self._sextings(st, dia)) + 1
        b = Bloco(f"livre:{dia}:s{n}", "sexting", SEXTING_TEXTO, "quarto", "celular", True, now, now + SEXTING_FOLGA)
        st.setdefault(dia, {})[f"s{n}"] = {**b.__dict__, "inicio": b.inicio.isoformat(), "fim": b.fim.isoformat()}
        self._save(st, now)
        self._registra(b, now)
        logger.info("tempo_livre.sexting inicio=%s", now.isoformat(timespec="minutes"))
        return b

    def sexting_acabou(self, now: datetime, *, gozou: bool = False) -> None:
        """Ele cortou/foi dormir, ou ela gozou: o bloco acaba agora (gozando, fica registrado no Hoje)."""
        st = self._state()
        g = self._sexting_recente(st, now)
        if not g:
            return
        # gozando, a cena foi até agora; cortando, acaba aqui (a folga de SEXTING_FOLGA cai)
        g["fim"] = (now if gozou else min(datetime.fromisoformat(g["fim"]), now)).isoformat()
        if gozou:
            g["gozou"] = True
        self._save(st, now)
        b = self._bloco(g)
        with self.db.get_connection() as conn:
            conn.execute("UPDATE life_events SET summary=? WHERE event_key=?", (self._resumo(b), b.chave))
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
            try:                                  # 28/09 (Patrick): chamando ele, veste algo pra provocar (roupa.py)
                from roupa import Roupa
                Roupa(self.db).provocar(max(b.inicio, min(now, b.fim)), "sexting")
            except Exception:
                logger.exception("tempo_livre.roupa.provocar")
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
