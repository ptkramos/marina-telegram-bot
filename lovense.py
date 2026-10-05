"""Lovense da Marina pelo Mini App (PLANO_WEBAPP, "Lovense pelo Mini App — plano"; Patrick, 02–05/10).

O brinquedo é o dela na história e o Patrick controla pelo app. Este módulo é só o ESTADO (passo 1):

- Brinquedos (Lush e Hush): bateria de verdade, que gasta pelo nível (forte gasta mais) e carrega quando ela
  põe no carregador em casa; e onde cada um está (gaveta, carregador, bolsa, nela).
- Sessão: com qual, desde quando, onde colocou, a palavra de segurança combinada no chat desta vez, e o estado
  (conectada, pausada depois da palavra, cortada por ela, encerrada).
- Linha do tempo dos comandos (nível 0–20, modo clássico/toque/padrão).
- Palavra de segurança (Patrick: "ia ser legal eu ter que parar realmente antes dela se irritar"): ele tem uns
  30 s pra parar. Parou: a confiança sobe um pouco. Não parou: ela repete firme, depois bronca de verdade (a
  confiança cai e abre pendência) e, como último recurso, corta pelo celular dela, se conseguir mexer nele.
- Confiança é a barra geral `trust` do vínculo. Com pendência aberta ela não volta sozinha (`emocao_travas`) e
  ela recusa a próxima vez; volta só conversando — mais de um incidente no mês pede mais de uma conversa.

Quem chama (passos seguintes): o Mini App manda os comandos; o bot transforma os eventos em turno (o que ela
sente, `sentir`, passo 3), a agenda decide quando ela coloca, tira e se consegue mexer no celular. Nada aqui fala
por ela: o turno descreve a sensação, nunca a fala.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Iterable, Optional

BRINQUEDOS = ("lush", "hush")
NIVEL_MAX = 20
MODOS = ("classico", "toque", "padrao")
# Padrão do app: quanto do nível escolhido ele entrega em média (bateria e, depois, tesão).
PADROES = {"pulso": 0.55, "onda": 0.6, "fogos": 0.7, "terremoto": 0.85}

# Bateria por hora: (conectado e parado, a mais no nível 20). Lush no máximo dura ~2 h; o Hush, menor, ~1,7 h.
GASTO_POR_HORA = {"lush": (0.01, 0.49), "hush": (0.02, 0.58)}
CARGA_POR_HORA = 0.7                  # vazio → cheio em ~1 h 30
BATERIA_MINIMA = 0.05                 # abaixo disso ela não coloca (põe pra carregar)

# Palavra de segurança: prazo dele, repetir firme, bronca, cortar.
PRAZO = timedelta(seconds=30)
BRONCA = timedelta(seconds=60)
CORTE = timedelta(seconds=90)
AVISO_CORTOU = timedelta(hours=12)    # quanto tempo o app mostra "Marina encerrou o controle"

# Confiança (`trust`), números meus (calibrar no uso; regra 5 para 1 do recalibrar).
TRUST = "trust"
TRAVA = "lovense"
CONFIANCA_PAROU = +0.02
CONFIANCA_PAROU_TARDE = -0.03
CONFIANCA_BRONCA = -0.10
CONFIANCA_CORTOU = -0.08
CONFIANCA_CONVERSA = +0.02            # conversa que ainda não fecha a pendência
CONFIANCA_FECHOU = +0.04
JANELA_INCIDENTES = timedelta(days=30)
CONVERSAS_NO_MAXIMO = 3               # 1 incidente no mês: 1 conversa; 2: duas; 3+: três
ENTRE_CONVERSAS = timedelta(hours=6)  # a mesma conversa não conta duas vezes

# O que ela sente vira turno (passo 3). Ela não fala a cada mexida na barra: fala quando sente diferença.
JUNTAR = timedelta(seconds=4)             # o bot espera ele assentar a mão: a rajada de comandos vira um turno só
ENTRE_TURNOS = timedelta(seconds=45)      # mudança comum: no máximo um turno a cada 45 s (o que muda nesse meio
                                          # tempo não se perde: entra no turno seguinte)
SALTO = 4                                 # diferença de nível (0–20, já com o padrão) que ela sente
SUSTENTADO = timedelta(minutes=5)         # no mesmo ritmo há 5 min: o tesão acumulando
SUSTENTADO_DE_NOVO = timedelta(minutes=10)
NIVEL_QUE_SENTE = 3                       # abaixo disso, ficar no mesmo nível não vira turno
EVENTOS_DE_TURNO = ("respeitou", "parou_tarde", "parou_depois_da_bronca", "religou", "firme", "bronca",
                    "cortou", "sessao_acabou_bateria")       # + bateria_acabou:<brinquedo>; os dela (pediu_parar,
                                                             # tirou) ela já sabe


def _dt(raw) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None


def _efetivo(nivel: int, modo: str, padrao: Optional[str]) -> float:
    return nivel * (PADROES.get(padrao or "", 1.0) if modo == "padrao" else 1.0)


# Texto interno do turno (eu decido; descreve a sensação e o que ele fez, nunca a fala dela).
_NOME = {"lush": "o Lush", "hush": "o Hush"}
_NOME_DE = {"lush": "do Lush", "hush": "do Hush"}
_RITMO = {"classico": "constante", "toque": "no ritmo do dedo dele, mexendo agora",
          "pulso": "em pulsos", "onda": "em ondas que sobem e descem", "fogos": "em estouros sem aviso",
          "terremoto": "tremendo forte, sem ritmo"}
_EVENTO_TEXTO = {
    "respeitou": "você disse a palavra de segurança e ele parou na hora, como combinado",
    "parou_tarde": "ele só parou depois que você repetiu a palavra de segurança; demorou",
    "parou_depois_da_bronca": "ele só parou depois da sua bronca, bem depois da palavra de segurança",
    "religou": "você tinha dito a palavra de segurança e ele ligou de novo sem você liberar",
    "firme": "faz 30 s que você disse a palavra de segurança e continua ligado: ele não parou",
    "bronca": "já faz 1 min que você disse a palavra de segurança e ele continua, ignorando você",
    "cortou": ("você cortou o controle dele pelo seu celular, porque ele não parou depois da palavra de "
               "segurança; o brinquedo continua em você, desligado"),
    "bateria_acabou": "a bateria {nome_de} acabou e ele parou de vibrar sozinho",
    "sessao_acabou_bateria": "sem bateria, o app dele perdeu a conexão com você",
}


def _intensidade(e: float) -> tuple[str, str]:
    """Nível efetivo → (intensidade, o que o corpo sente)."""
    if e <= 4:
        return "fraquinho", "um zumbido que dá pra ignorar se quiser"
    if e <= 8:
        return "médio", "dá pra sentir bem"
    if e <= 13:
        return "forte", "difícil de ignorar"
    if e <= 17:
        return "muito forte", "difícil de disfarçar"
    return "no máximo", "quase insuportável"


def _sensacao(b: str, nivel: int, modo: str, padrao: Optional[str], *, so_ritmo: bool = False) -> str:
    forca, corpo = _intensidade(_efetivo(nivel, modo, padrao))
    ritmo = _RITMO[padrao if modo == "padrao" and padrao else modo if modo in _RITMO else "classico"]
    return f"{forca}, {ritmo}" if so_ritmo else f"vibrando {forca} ({corpo}), {ritmo}"


def _mudanca(b: str, antes: tuple, agora: tuple, mexida: Optional[dict], *, sistema: bool = False) -> Optional[str]:
    """O que ela sente de diferença num brinquedo desde o último turno (None: nada que ela note)."""
    if sistema:
        return None                       # parou pela bateria ou porque ela tirou: o evento (ou ela) já conta
    e0, e1 = _efetivo(*antes), _efetivo(*agora)
    pico = mexida["pico"] if mexida else 0.0
    nome = _NOME[b]
    prov = " (ele ficou mexendo, provocando)" if mexida and mexida["n"] >= 6 and agora[1] != "toque" else ""
    if e0 == 0 and e1 == 0:
        if pico >= NIVEL_QUE_SENTE:
            return f"ele ligou {nome} por uns segundos (chegou a {_intensidade(pico)[0]}) e desligou, provocando"
        return None
    if e0 == 0:
        return f"ele ligou {nome}{prov}, {_sensacao(b, *agora)}"
    if e1 == 0:
        subiu = f" depois de subir até {_intensidade(pico)[0]}" if pico >= e0 + SALTO else ""
        if agora[1] == "toque":           # o 0 veio de soltar o dedo no Toque
            return f"ele tirou o dedo e {nome} parou{subiu}"
        return f"ele parou {nome}{subiu}{prov}"
    agora_sente = f"agora {_sensacao(b, *agora)}"
    if (antes[1], antes[2]) != (agora[1], agora[2]):
        return f"ele mudou o ritmo {_NOME_DE[b]}{prov}: {agora_sente}"
    if abs(e1 - e0) >= SALTO:
        return f"ele {'aumentou' if e1 > e0 else 'diminuiu'} {nome}{prov}: {agora_sente}"
    if pico >= max(e0, e1) + SALTO:
        return f"ele subiu {nome} até {_intensidade(pico)[0]} e voltou{prov}: {agora_sente}"
    return None


class Lovense:
    def __init__(self, db):
        self.db = db

    # ---------------------------------------------------------------- leitura

    @staticmethod
    def _ativa(conn):
        return conn.execute("""SELECT * FROM lovense_sessoes WHERE estado IN ('conectada', 'pausada')
                               ORDER BY id DESC LIMIT 1""").fetchone()

    @staticmethod
    def _brinquedos(conn) -> dict:
        out = {r["brinquedo"]: dict(r) for r in conn.execute("SELECT * FROM lovense_brinquedos")}
        if len(out) < len(BRINQUEDOS):
            # Início limpo (bootstrap_v36) esvazia a tabela: os brinquedos voltam cheios, na gaveta.
            agora = datetime.now().isoformat()
            for b in BRINQUEDOS:
                if b not in out:
                    conn.execute("""INSERT OR IGNORE INTO lovense_brinquedos (brinquedo, bateria, bateria_em, onde)
                                    VALUES (?, 1.0, ?, 'gaveta')""", (b, agora))
                    out[b] = {"brinquedo": b, "bateria": 1.0, "bateria_em": agora, "onde": "gaveta"}
        return out

    @staticmethod
    def _niveis(conn, sessao_id: int) -> dict:
        """Último comando de cada brinquedo na sessão: {brinquedo: (nivel, modo, padrao)}."""
        out = {}
        for r in conn.execute("""SELECT brinquedo, nivel, modo, padrao FROM lovense_comandos
                                 WHERE sessao_id=? ORDER BY criado_em, id""", (sessao_id,)):
            out[r["brinquedo"]] = (r["nivel"], r["modo"], r["padrao"])
        return out

    def _em_uso(self, conn, sessao) -> list[str]:
        """Os brinquedos da sessão que ainda estão nela."""
        nela = {b for b, r in self._brinquedos(conn).items() if r["onde"] == "nela"}
        return [b for b in json.loads(sessao["brinquedos_json"] or "[]") if b in nela]

    # ---------------------------------------------------------------- bateria

    def _assentar(self, conn, now: datetime) -> list[str]:
        """Leva a bateria de cada brinquedo até `now` (gasta nela, carrega no carregador). Idempotente."""
        eventos = []
        mortos = {}
        for b, r in self._brinquedos(conn).items():
            t0 = _dt(r["bateria_em"]) or now
            bat = float(r["bateria"])
            if now <= t0 or r["onde"] not in ("nela", "carregador"):
                conn.execute("UPDATE lovense_brinquedos SET bateria_em=? WHERE brinquedo=?",
                             (max(now, t0).isoformat(), b))
                continue
            if r["onde"] == "carregador":
                bat = min(1.0, bat + CARGA_POR_HORA * (now - t0).total_seconds() / 3600)
            elif bat > 0:
                parado, cheio = GASTO_POR_HORA[b]
                antes = conn.execute("""SELECT nivel, modo, padrao FROM lovense_comandos
                                        WHERE brinquedo=? AND criado_em<=? ORDER BY criado_em DESC, id DESC
                                        LIMIT 1""", (b, t0.isoformat())).fetchone()
                trechos = [(t0, _efetivo(antes["nivel"], antes["modo"], antes["padrao"]) if antes else 0.0)]
                for c in conn.execute("""SELECT nivel, modo, padrao, criado_em FROM lovense_comandos
                                         WHERE brinquedo=? AND criado_em>? AND criado_em<=?
                                         ORDER BY criado_em, id""", (b, t0.isoformat(), now.isoformat())):
                    trechos.append((_dt(c["criado_em"]), _efetivo(c["nivel"], c["modo"], c["padrao"])))
                for i, (ini, nivel) in enumerate(trechos):
                    fim = trechos[i + 1][0] if i + 1 < len(trechos) else now
                    taxa = parado + cheio * nivel / NIVEL_MAX
                    horas = (fim - ini).total_seconds() / 3600
                    if bat - taxa * horas <= 0:
                        mortos[b] = ini + timedelta(hours=bat / taxa)
                        bat = 0.0
                        break
                    bat -= taxa * horas
            conn.execute("UPDATE lovense_brinquedos SET bateria=?, bateria_em=? WHERE brinquedo=?",
                         (round(bat, 4), now.isoformat(), b))
        sessao = self._ativa(conn)
        if sessao and mortos:
            em_uso = self._em_uso(conn, sessao)
            for b, quando in mortos.items():
                if b in em_uso:
                    self._registrar(conn, sessao["id"], b, 0, "sistema", None, quando)
                    eventos.append(f"bateria_acabou:{b}")
            vivos = [b for b in em_uso if b not in mortos]
            if em_uso and not vivos:
                fim = max(mortos[b] for b in em_uso if b in mortos)
                conn.execute("""UPDATE lovense_sessoes SET estado='encerrada', fim_em=?, motivo_fim='bateria'
                                WHERE id=?""", (fim.isoformat(), sessao["id"]))
                eventos.append("sessao_acabou_bateria")
        return eventos

    @staticmethod
    def _registrar(conn, sessao_id: int, brinquedo: str, nivel: int, modo: str, padrao: Optional[str],
                   quando: datetime):
        conn.execute("""INSERT INTO lovense_comandos (sessao_id, brinquedo, nivel, modo, padrao, criado_em)
                        VALUES (?, ?, ?, ?, ?, ?)""", (sessao_id, brinquedo, nivel, modo, padrao, quando.isoformat()))

    # ---------------------------------------------------------------- o que ela faz

    def colocar(self, now: datetime, brinquedos: Iterable[str] = ("lush",), *, lugar: str = "",
                fora_de_casa: bool = False, origem: str = "dela") -> dict:
        """Ela coloca (e avisa no chat): o ícone acende. Com sessão aberta, junta o outro brinquedo nela."""
        brinquedos = [b for b in dict.fromkeys(brinquedos)]
        with self.db.get_connection() as conn:
            self._assentar(conn, now)
            estoque = self._brinquedos(conn)
            for b in brinquedos:
                if b not in BRINQUEDOS:
                    raise ValueError(f"brinquedo desconhecido: {b}")
                if fora_de_casa and estoque[b]["onde"] not in ("bolsa", "nela"):
                    raise ValueError(f"{b} não está na bolsa: fora de casa fica pra quando voltar")
                if float(estoque[b]["bateria"]) < BATERIA_MINIMA:
                    raise ValueError(f"{b} sem bateria")
            sessao = self._ativa(conn)
            if sessao:
                atuais = json.loads(sessao["brinquedos_json"] or "[]")
                conn.execute("UPDATE lovense_sessoes SET brinquedos_json=? WHERE id=?",
                             (json.dumps(list(dict.fromkeys(atuais + brinquedos))), sessao["id"]))
                sessao_id = sessao["id"]
            else:
                sessao_id = conn.execute(
                    """INSERT INTO lovense_sessoes (brinquedos_json, origem, desde, lugar, fora_de_casa)
                       VALUES (?, ?, ?, ?, ?)""",
                    (json.dumps(brinquedos), origem, now.isoformat(), lugar, int(fora_de_casa))).lastrowid
            for b in brinquedos:
                conn.execute("UPDATE lovense_brinquedos SET onde='nela', bateria_em=? WHERE brinquedo=?",
                             (now.isoformat(), b))
            conn.commit()
        return {"sessao_id": sessao_id, "brinquedos": brinquedos}

    def combinar_palavra(self, now: datetime, palavra: str) -> bool:
        """A palavra de segurança combinada no chat a cada vez que ela coloca."""
        with self.db.get_connection() as conn:
            sessao = self._ativa(conn)
            if not sessao:
                return False
            conn.execute("UPDATE lovense_sessoes SET palavra=? WHERE id=?", ((palavra or "").strip(), sessao["id"]))
            conn.commit()
        return True

    def pedir_parar(self, now: datetime) -> list[str]:
        """Ela disse a palavra (só ela conta; "para" no meio da brincadeira é provocação). Começa o prazo dele."""
        with self.db.get_connection() as conn:
            eventos = self._assentar(conn, now)
            sessao = self._ativa(conn)
            if not sessao or sessao["estado"] == "pausada":
                conn.commit()
                return eventos       # repetir a palavra não reinicia o prazo
            parado = max((n for n, _, _ in self._niveis(conn, sessao["id"]).values()), default=0) == 0
            conn.execute("""UPDATE lovense_sessoes SET estado='pausada', pediu_parar_em=?, escada=0, respeitou=?
                            WHERE id=?""", (now.isoformat(), 1 if parado else None, sessao["id"]))
            conn.commit()
        return eventos + ["pediu_parar"]

    def liberar(self, now: datetime) -> bool:
        """Ela libera de novo depois da palavra ("pode voltar"): o controle volta ao normal."""
        with self.db.get_connection() as conn:
            sessao = self._ativa(conn)
            if not sessao or sessao["estado"] != "pausada":
                return False
            conn.execute("""UPDATE lovense_sessoes SET estado='conectada', pediu_parar_em=NULL, escada=0,
                            respeitou=NULL WHERE id=?""", (sessao["id"],))
            conn.commit()
        return True

    def cortar(self, now: datetime) -> list[str]:
        """Ela corta o controle pelo celular dela (último recurso; já é a briga). O brinquedo continua nela."""
        with self.db.get_connection() as conn:
            eventos = self._assentar(conn, now)
            sessao = self._ativa(conn)
            if not sessao:
                conn.commit()
                return eventos
            eventos += self._cortar(conn, sessao, now)
            conn.commit()
        self._abrir_pendencia(now)
        self.db.ajustar_emocao(TRUST, CONFIANCA_CORTOU, now=now)
        return eventos

    def _cortar(self, conn, sessao, now: datetime) -> list[str]:
        for b in self._em_uso(conn, sessao):
            self._registrar(conn, sessao["id"], b, 0, "sistema", None, now)
        novo_incidente = 1 if int(sessao["escada"]) < 2 else 0      # a bronca já contou este
        conn.execute("""UPDATE lovense_sessoes SET estado='cortada', escada=3, respeitou=0, fim_em=?,
                        motivo_fim='cortou', incidentes=incidentes+? WHERE id=?""",
                     (now.isoformat(), novo_incidente, sessao["id"]))
        return ["cortou"]

    def tirar(self, now: datetime, brinquedos: Optional[Iterable[str]] = None, *, em_casa: bool = True) -> list[str]:
        """Ela tira. Em casa vai pro carregador; fora (só no banheiro do lugar) volta pra bolsa."""
        with self.db.get_connection() as conn:
            eventos = self._assentar(conn, now)
            estoque = self._brinquedos(conn)
            alvo = [b for b in (brinquedos or BRINQUEDOS) if estoque.get(b, {}).get("onde") == "nela"]
            sessao = self._ativa(conn)
            for b in alvo:
                conn.execute("UPDATE lovense_brinquedos SET onde=?, bateria_em=? WHERE brinquedo=?",
                             ("carregador" if em_casa else "bolsa", now.isoformat(), b))
                if sessao:
                    self._registrar(conn, sessao["id"], b, 0, "sistema", None, now)
            if sessao and alvo and not self._em_uso(conn, sessao):
                conn.execute("""UPDATE lovense_sessoes SET estado='encerrada', fim_em=?, motivo_fim='tirou'
                                WHERE id=?""", (now.isoformat(), sessao["id"]))
                eventos.append("tirou")
            conn.commit()
        return eventos

    def levar_na_bolsa(self, now: datetime, brinquedo: str = "lush") -> bool:
        """Ela sai sabendo que pode rolar: o brinquedo vai na bolsa (com a bateria que tiver)."""
        return self._mover(now, brinquedo, ("gaveta", "carregador"), "bolsa")

    def guardar(self, now: datetime, brinquedo: str = "lush", *, carregar: bool = True) -> bool:
        """De volta em casa: sai da bolsa pro carregador (ou pra gaveta)."""
        return self._mover(now, brinquedo, ("bolsa", "gaveta", "carregador"), "carregador" if carregar else "gaveta")

    def _mover(self, now: datetime, brinquedo: str, de: tuple, para: str) -> bool:
        with self.db.get_connection() as conn:
            self._assentar(conn, now)
            r = self._brinquedos(conn).get(brinquedo)
            if not r or r["onde"] not in de:
                conn.commit()
                return False
            conn.execute("UPDATE lovense_brinquedos SET onde=?, bateria_em=? WHERE brinquedo=?",
                         (para, now.isoformat(), brinquedo))
            conn.commit()
        return True

    # ---------------------------------------------------------------- o que ele faz (Mini App)

    def comando(self, now: datetime, brinquedo: str, nivel: int, modo: str = "classico",
                padrao: Optional[str] = None) -> dict:
        """Um comando do app. `brinquedo` = lush | hush | todos. Devolve {ok, erro, eventos}."""
        nivel = max(0, min(NIVEL_MAX, int(nivel)))
        if modo not in MODOS:
            return {"ok": False, "erro": "modo", "eventos": []}
        if modo == "padrao" and padrao not in PADROES:
            return {"ok": False, "erro": "padrao", "eventos": []}
        padrao = padrao if modo == "padrao" else None
        with self.db.get_connection() as conn:
            eventos = self._assentar(conn, now)
            sessao = self._ativa(conn)
            if not sessao:
                conn.commit()
                return {"ok": False, "erro": "desconectada", "eventos": eventos}
            em_uso = self._em_uso(conn, sessao)
            alvos = em_uso if brinquedo == "todos" else [brinquedo]
            if not alvos or any(b not in em_uso for b in alvos):
                conn.commit()
                return {"ok": False, "erro": "brinquedo", "eventos": eventos}
            estoque = self._brinquedos(conn)
            vivos = [b for b in alvos if float(estoque[b]["bateria"]) > 0]
            if not vivos:
                conn.commit()
                return {"ok": False, "erro": "sem_bateria", "eventos": eventos}
            niveis = self._niveis(conn, sessao["id"])
            for b in vivos:
                if niveis.get(b, (0, "classico", None)) != (nivel, modo, padrao):
                    self._registrar(conn, sessao["id"], b, nivel, modo, padrao, now)
            ajustes = []
            if sessao["estado"] == "pausada":
                eventos += self._depois_da_palavra(conn, sessao, now, ajustes)
            conn.commit()
        for delta in ajustes:
            self.db.ajustar_emocao(TRUST, delta, now=now)
        return {"ok": True, "erro": None, "eventos": eventos}

    def parar(self, now: datetime) -> dict:
        """Botão Parar: tudo em zero (não é desligar nem tirar)."""
        return self.comando(now, "todos", 0)

    def _depois_da_palavra(self, conn, sessao, now: datetime, ajustes: list) -> list[str]:
        """Comando com a palavra dita: ele parou (a tempo ou tarde) ou voltou a ligar."""
        ligado = max((n for n, _, _ in self._niveis(conn, sessao["id"]).values()), default=0) > 0
        escada = int(sessao["escada"])
        if not ligado and sessao["respeitou"] is None:
            conn.execute("UPDATE lovense_sessoes SET respeitou=? WHERE id=?",
                         (1 if escada == 0 else 0, sessao["id"]))
            if escada == 0:
                ajustes.append(CONFIANCA_PAROU)
                return ["respeitou"]
            if escada == 1:
                ajustes.append(CONFIANCA_PAROU_TARDE)
                return ["parou_tarde"]
            return ["parou_depois_da_bronca"]
        if ligado and sessao["respeitou"] is not None:
            # Tinha parado e voltou a ligar sem ela liberar: o prazo já passou. A escada segue de onde estava
            # (firme agora; se já teve bronca, o corte vem em 30 s).
            escada = max(1, escada)
            conn.execute("""UPDATE lovense_sessoes SET respeitou=NULL, escada=?, pediu_parar_em=? WHERE id=?""",
                         (escada, (now - (PRAZO if escada < 2 else BRONCA)).isoformat(), sessao["id"]))
            return ["religou"]
        return []

    # ---------------------------------------------------------------- relógio

    def tick(self, now: datetime, *, pode_mexer_no_celular: bool = True) -> list[str]:
        """Anda o relógio: bateria e a escada da palavra (firme aos 30 s, bronca aos 60 s, corta aos 90 s se
        ela consegue mexer no celular — na aula ou no meio de gente pode não conseguir na hora)."""
        abrir = False
        ajustes = []
        with self.db.get_connection() as conn:
            eventos = self._assentar(conn, now)
            sessao = self._ativa(conn)
            if not sessao or sessao["estado"] != "pausada" or sessao["respeitou"] is not None:
                conn.commit()
                return eventos
            ligado = max((n for n, _, _ in self._niveis(conn, sessao["id"]).values()), default=0) > 0
            escada = int(sessao["escada"])
            if not ligado:
                # Parou sem comando dele (a bateria acabou): não conta a favor.
                conn.execute("UPDATE lovense_sessoes SET respeitou=0 WHERE id=?", (sessao["id"],))
                conn.commit()
                return eventos
            t0 = _dt(sessao["pediu_parar_em"]) or now
            if escada < 1 and now >= t0 + PRAZO:
                escada = 1
                eventos.append("firme")
            if escada < 2 and now >= t0 + BRONCA:
                escada = 2
                eventos.append("bronca")
                ajustes.append(CONFIANCA_BRONCA)
                conn.execute("UPDATE lovense_sessoes SET incidentes=incidentes+1 WHERE id=?", (sessao["id"],))
                abrir = True
            conn.execute("UPDATE lovense_sessoes SET escada=? WHERE id=?", (escada, sessao["id"]))
            if escada == 2 and now >= t0 + CORTE and pode_mexer_no_celular:
                sessao = conn.execute("SELECT * FROM lovense_sessoes WHERE id=?", (sessao["id"],)).fetchone()
                eventos += self._cortar(conn, sessao, now)
                ajustes.append(CONFIANCA_CORTOU)
                abrir = True
            conn.commit()
        if abrir:
            self._abrir_pendencia(now)
        for delta in ajustes:
            self.db.ajustar_emocao(TRUST, delta, now=now)
        return eventos

    # ---------------------------------------------------------------- confiança

    def _incidentes(self, now: datetime) -> int:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT COALESCE(SUM(incidentes), 0) FROM lovense_sessoes WHERE desde>=?",
                               ((now - JANELA_INCIDENTES).isoformat(),)).fetchone()
        return int(row[0] or 0)

    def _abrir_pendencia(self, now: datetime):
        """Incidente novo: a confiança fica presa e a conversa recomeça do zero (mais incidentes, mais conversa)."""
        self.db.travar_emocao(TRUST, TRAVA, now=now, detalhe={"conversas": 0, "ultima_conversa": None})

    def pendencia(self, now: datetime) -> Optional[dict]:
        trava = self.db.get_trava_emocao(TRUST, TRAVA)
        if not trava:
            return None
        precisa = max(1, min(CONVERSAS_NO_MAXIMO, self._incidentes(now)))
        feitas = int(trava["detalhe"].get("conversas") or 0)
        return {"desde": trava["desde"], "incidentes": self._incidentes(now),
                "conversas": feitas, "faltam": max(0, precisa - feitas)}

    def pode_topar(self, now: datetime) -> bool:
        """Com pendência aberta ela recusa a próxima vez, até vocês conversarem."""
        return self.pendencia(now) is None

    def conversar(self, now: datetime) -> Optional[dict]:
        """Uma conversa de verdade sobre o que aconteceu (detectada no chat). Devolve {fechou, faltam} ou None."""
        p = self.pendencia(now)
        if not p:
            return None
        trava = self.db.get_trava_emocao(TRUST, TRAVA)
        ultima = _dt(trava["detalhe"].get("ultima_conversa"))
        if ultima and now - ultima < ENTRE_CONVERSAS:
            return {"fechou": False, "faltam": p["faltam"]}
        feitas = p["conversas"] + 1
        if feitas >= p["conversas"] + p["faltam"]:
            self.db.destravar_emocao(TRUST, TRAVA, now=now)
            self.db.ajustar_emocao(TRUST, CONFIANCA_FECHOU, now=now)
            return {"fechou": True, "faltam": 0}
        self.db.travar_emocao(TRUST, TRAVA, now=now,
                              detalhe={"conversas": feitas, "ultima_conversa": now.isoformat()})
        self.db.ajustar_emocao(TRUST, CONFIANCA_CONVERSA, now=now)
        return {"fechou": False, "faltam": p["faltam"] - 1}

    def confianca(self, now: datetime) -> float:
        return float(self.db.get_estado_emocional(now).get(TRUST, {}).get("valor", 0.8))

    # ---------------------------------------------------------------- o que ela sente (passo 3)

    def sessao_ativa(self) -> bool:
        """Consulta leve pro relógio do bot (não mexe na bateria)."""
        with self.db.get_connection() as conn:
            return self._ativa(conn) is not None

    def sentir(self, now: datetime, eventos: Iterable[str] = ()) -> Optional[dict]:
        """Os comandos dele (e os eventos da palavra e da bateria) viram o que ela sente: {texto, motivo} pro bot
        transformar em turno, ou None quando ela não sente diferença. Guarda o que ela já sentiu na sessão
        (`sentido_json`), então a rajada de comandos e o que mudou no intervalo entram juntos no turno seguinte."""
        eventos = list(dict.fromkeys(e for e in eventos
                                     if e in EVENTOS_DE_TURNO or e.startswith("bateria_acabou:")))
        with self.db.get_connection() as conn:
            sessao = self._ativa(conn)
            if not sessao and eventos:            # cortou / bateria: a sessão acabou neste mesmo passo
                sessao = conn.execute("SELECT * FROM lovense_sessoes ORDER BY id DESC LIMIT 1").fetchone()
            if not sessao:
                return None
            snap = json.loads(sessao["sentido_json"] or "{}")
            ult = _dt(snap.get("em"))
            em_uso = self._em_uso(conn, sessao)
            niveis = self._niveis(conn, sessao["id"])
            agora = {b: niveis.get(b, (0, "classico", None)) for b in em_uso}
            antes = {b: tuple(v) for b, v in (snap.get("b") or {}).items()}
            desde = (ult or _dt(sessao["desde"]) or now).isoformat()
            mexidas = {}
            for c in conn.execute("""SELECT brinquedo, nivel, modo, padrao FROM lovense_comandos
                                     WHERE sessao_id=? AND criado_em>? AND criado_em<=? AND modo!='sistema'""",
                                  (sessao["id"], desde, now.isoformat())):
                m = mexidas.setdefault(c["brinquedo"], {"n": 0, "pico": 0.0})
                m["n"] += 1
                m["pico"] = max(m["pico"], _efetivo(c["nivel"], c["modo"], c["padrao"]))

            partes, motivo = [], None
            if eventos:
                motivo = "evento"
                partes = [_EVENTO_TEXTO[e.partition(":")[0]].format(
                    nome_de=_NOME_DE.get(e.partition(":")[2], "do brinquedo")) for e in eventos]
                if any(e in ("religou", "firme", "bronca") for e in eventos):
                    ligados = [_sensacao(b, *agora[b]) for b in em_uso if agora[b][0] > 0]
                    if ligados:
                        partes.append("agora " + " e ".join(ligados))
            elif sessao["estado"] == "conectada":
                mudancas = [m for b in em_uso if (m := _mudanca(b, antes.get(b, (0, "classico", None)), agora[b],
                                                                 mexidas.get(b), sistema=agora[b][1] == "sistema"))]
                if mudancas and (ult is None or now - ult >= ENTRE_TURNOS):
                    motivo, partes = "mudou", mudancas
                elif not mudancas and ult is not None:
                    ligados = [b for b in em_uso if _efetivo(*agora[b]) >= NIVEL_QUE_SENTE]
                    espera = SUSTENTADO_DE_NOVO if snap.get("motivo") == "sustentado" else SUSTENTADO
                    if ligados and now - ult >= espera:
                        ritmo = _dt(snap.get("ritmo_desde")) or ult
                        minutos = max(1, round((now - ritmo).total_seconds() / 60))
                        motivo = "sustentado"
                        partes = [f"faz {minutos} min que " + " e ".join(
                            f"{_NOME[b]} vibra no mesmo ritmo dentro de você ({_sensacao(b, *agora[b], so_ritmo=True)})"
                            for b in ligados) + "; o tesão vai acumulando"]
            if not partes:
                return None
            novo = {"em": now.isoformat(), "motivo": motivo, "b": {b: list(v) for b, v in agora.items()},
                    "ritmo_desde": snap.get("ritmo_desde") if motivo == "sustentado" else now.isoformat()}
            conn.execute("UPDATE lovense_sessoes SET sentido_json=? WHERE id=?", (json.dumps(novo), sessao["id"]))
            conn.commit()
        texto = "; ".join(partes)
        return {"texto": f"[Brinquedo, pelo app do Patrick: {texto[0].upper()}{texto[1:]}]", "motivo": motivo}

    # ---------------------------------------------------------------- painel

    def sessoes_recentes(self, now: datetime, dias: int = 7) -> int:
        """Quantas vezes ela usou na semana (a novidade cansa: ela propõe menos)."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM lovense_sessoes WHERE desde>=?",
                               ((now - timedelta(days=dias)).isoformat(),)).fetchone()
        return int(row[0] or 0)

    def estado(self, now: datetime) -> dict:
        """O que o app mostra: conectada ou não, aviso, e cada brinquedo com bateria e nível."""
        with self.db.get_connection() as conn:
            eventos = self._assentar(conn, now)
            conn.commit()
            sessao = self._ativa(conn)
            ultima = sessao or conn.execute("SELECT * FROM lovense_sessoes ORDER BY id DESC LIMIT 1").fetchone()
            estoque = self._brinquedos(conn)
            niveis = self._niveis(conn, sessao["id"]) if sessao else {}
            em_uso = self._em_uso(conn, sessao) if sessao else []
        aviso = None
        if sessao and sessao["estado"] == "pausada":
            aviso = "pediu_parar"
        elif not sessao and ultima and ultima["estado"] == "cortada" and (
                (_dt(ultima["fim_em"]) or now) >= now - AVISO_CORTOU):
            aviso = "cortou"
        brinquedos = []
        for b in BRINQUEDOS:
            nivel, modo, padrao = niveis.get(b, (0, "classico", None))
            brinquedos.append({"nome": b, "bateria": round(float(estoque[b]["bateria"]), 3),
                               "onde": estoque[b]["onde"], "em_uso": b in em_uso,
                               "nivel": nivel if b in em_uso else 0, "modo": modo, "padrao": padrao})
        return {"conectada": bool(sessao), "estado": sessao["estado"] if sessao else "desconectada",
                "aviso": aviso, "sessao_id": sessao["id"] if sessao else None,
                "desde": sessao["desde"] if sessao else None, "lugar": sessao["lugar"] if sessao else "",
                "fora_de_casa": bool(sessao["fora_de_casa"]) if sessao else False,
                "palavra": sessao["palavra"] if sessao else None,
                "brinquedos": brinquedos, "eventos": eventos}
