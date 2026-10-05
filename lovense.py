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

- Como ela recebe (passo 4, `recepcao`): o ponto bom dela muda com o tesão, o lugar, o corpo e o tempo; daí
  parado, gostando, curtindo ou incomodada — e isso decide quando ela responde (response_availability), o tesão
  que o estímulo soma (`estimular` → intimacy) e, no banho, tirar ali mesmo quando está forte demais.

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
# Passo 4 (Patrick, 05/10): no fim da escada ela acaba pelo jeito mais fácil NO MOMENTO — celular na mão: corta
# (1 toque); sem celular em casa (banho): tira ali mesmo, pesa igual ao corte; sem celular fora (casting, prova):
# aguenta até conseguir pedir licença e ir ao banheiro — largar o que fazia é o mais punitivo.
LARGAR = timedelta(minutes=2)
AVISO_CORTOU = timedelta(hours=12)    # quanto tempo o app mostra "Marina encerrou o controle"

# Confiança (`trust`), números meus (calibrar no uso; regra 5 para 1 do recalibrar).
TRUST = "trust"
TRAVA = "lovense"
CONFIANCA_PAROU = +0.02
CONFIANCA_PAROU_TARDE = -0.03
CONFIANCA_BRONCA = -0.10
CONFIANCA_CORTOU = -0.08              # também quando ela tira em casa no fim da escada (tão fácil quanto cortar)
CONFIANCA_TIROU_LARGANDO = -0.15      # teve que largar a aula, a consulta, as amigas pra ir tirar
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
                    "cortou", "tirou_na_bronca", "tirou_largando", "tirou_incomodada",
                    "sessao_acabou_bateria")       # + bateria_acabou:<brinquedo>; os dela (pediu_parar,
                                                   # tirou) ela já sabe

# Passo 4 (Patrick, 05/10): como ela está recebendo decide quando ela responde. Tudo depende de ela estar
# gostando ou não: o PONTO BOM dela muda o tempo todo — sobe com o tesão; desce em lugar com gente (forte demais
# vira pânico), com cólica ou exausta, depois de muito tempo forte sem parar e logo depois de gozar (sensível).
# Acima do ponto ela reclama na hora (até saindo do banho); perto dele ela provoca e diz que tá bom; no ponto, com
# tesão alto, ela some aproveitando e fala quando ele para ou quando dá. Nada de sorteio. Números meus (calibrar).
PONTO_BASE, PONTO_TESAO = 0.05, 0.85      # ponto bom = 0,05 + 0,85 × tesão (0–1, a fração do máximo)
FOLGA_CASA, FOLGA_FORA = 0.20, 0.12       # quanto acima do ponto ainda é gostoso
ABAIXO = 0.25                             # mais que isso abaixo do ponto: gostoso, mas fraco pro tesão dela
CURTINDO_EXCITACAO = 0.45                 # excitação do momento (intimacy) pra ela se entregar
FORTE = 0.5                               # forte sem parar…
FORTE_CANSA = timedelta(minutes=15)       # …depois disso o ponto desce 0,01 por minuto (até 0,2)
SENSIVEL = timedelta(minutes=20)          # depois de gozar: até o fraco incomoda
GANHO_TESAO = 0.15                        # excitação por minuto no nível máximo, no ponto (antes do retorno)
# Fator do ponto bom por onde ela está (tipo da disponibilidade); em casa 1.
LUGAR_FATOR = {"CLASS": 0.7, "WORK": 0.75, "CASTING": 0.6, "SOCIAL": 0.75, "MANICURE": 0.75, "MEAL": 0.8,
               "GYM": 0.8, "OUT_SOLO": 0.85, "COMMUTE": 0.85, "PET_WALK": 0.9}
EM_CASA = ("HOME_RELAXING", "HOME_BUSY", "SOLO", "WAKING", "GETTING_READY", "MICRO_WAKE", "SLEEPING", "SHOWER")
SEM_CELULAR = ("SHOWER", "SLEEPING", "CASTING")     # celular fora do alcance (o banho) ou impossível (casting, job)


def _dt(raw) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None


def _efetivo(nivel: int, modo: str, padrao: Optional[str]) -> float:
    return nivel * (PADROES.get(padrao or "", 1.0) if modo == "padrao" else 1.0)


def _junto(fracoes: Iterable[float]) -> float:
    """O que ela sente somando os brinquedos (0–1): o Lush e o Hush juntos são mais que cada um."""
    resto = 1.0
    for f in fracoes:
        resto *= 1.0 - max(0.0, min(1.0, f))
    return 1.0 - resto


def contexto(atividade: Optional[str], fora_de_casa: bool = False) -> dict:
    """Onde ela está, pelo tipo da disponibilidade: fator do ponto bom, se está em casa e se alcança o celular."""
    atividade = atividade or "UNKNOWN"
    em_casa = atividade in EM_CASA or (atividade in ("UNKNOWN", "MEAL") and not fora_de_casa)
    fator = 1.0 if em_casa else LUGAR_FATOR.get(atividade, 0.85)
    return {"atividade": atividade, "em_casa": em_casa, "fator": fator, "publico": fator < 1.0,
            "pode_celular": atividade not in SEM_CELULAR}


_SENTIMENTO: dict = {}


def _feeling(db, now: datetime):
    """O que ela sente agora (EmotionEngine.feeling), guardado por 1 min: o relógio do Lovense roda a cada 10 s."""
    chave = (id(db), str(getattr(db, "db_path", "")))
    guardado = _SENTIMENTO.get(chave)
    if guardado and abs((now - guardado[0]).total_seconds()) < 60:
        return guardado[1]
    from emotion import EmotionEngine
    f = EmotionEngine(db).feeling(now)
    _SENTIMENTO[chave] = (now, f)
    return f


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
    "tirou_na_bronca": ("ele não parou nem depois da palavra de segurança e da sua bronca, e você tirou o brinquedo "
                        "ali mesmo (o celular estava fora do alcance); o app dele perdeu a conexão com você"),
    "tirou_largando": ("ele não parou nem depois da palavra de segurança e da sua bronca, e você teve que largar o "
                       "que estava fazendo e ir ao banheiro tirar o brinquedo; o app dele perdeu a conexão com você"),
    "tirou_incomodada": ("estava forte demais e você tirou o brinquedo no banho, sem cortar o app; o app dele "
                         "perdeu a conexão com você"),
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


def _frase(rec: dict) -> Optional[str]:
    """Como ela está recebendo, pro turno (texto interno: a sensação, nunca a fala)."""
    estado = rec["estado"]
    if estado == "incomodada":
        if rec["sensivel"]:
            return "você gozou há pouco e está sensível: até o fraco incomoda"
        if rec["cansou"]:
            return "faz tempo que está forte sem parar e já cansou: está incomodando"
        onde = "pra onde você está" if rec["publico"] else "agora"
        return f"forte demais {onde}: " + ("está te incomodando de verdade" if rec["grau"] >= 0.5
                                            else "está começando a incomodar")
    if estado == "curtindo":
        return "está no ponto, delicioso; você está entregue ao que sente"
    if estado == "gostando":
        return ("está gostoso, mas fraco pro tesão que você está" if rec["e"] < rec["ponto"] - ABAIXO
                else "está gostoso")
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

    def tick(self, now: datetime, *, pode_mexer_no_celular: bool = True,
             atividade: Optional[str] = None) -> list[str]:
        """Anda o relógio: bateria, o tesão que o estímulo soma e a escada da palavra (firme aos 30 s, bronca aos
        60 s e, aos 90 s, ela acaba pelo jeito mais fácil no momento: corta pelo celular; sem celular em casa, tira
        ali; sem celular fora, aguenta até conseguir largar o que faz e ir tirar no banheiro). `atividade` é o tipo
        da disponibilidade (onde ela está); sem ela, só sabe se dá pra mexer no celular."""
        em_casa = None
        if atividade is not None:
            rec = self.recepcao(now, atividade)
            if rec:
                pode_mexer_no_celular, em_casa = rec["pode_celular"], rec["em_casa"]
                self.estimular(now, rec)
                if rec["atividade"] == "SHOWER" and rec["estado"] == "incomodada" and rec["grau"] >= 0.5:
                    # No banho o celular fica fora do box: forte demais, ela tira ali e dá o esporro depois.
                    return self._tirar_incomodada(now)
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
            if escada == 2 and now >= t0 + CORTE:
                sessao = conn.execute("SELECT * FROM lovense_sessoes WHERE id=?", (sessao["id"],)).fetchone()
                if pode_mexer_no_celular:
                    eventos += self._cortar(conn, sessao, now)
                    ajustes.append(CONFIANCA_CORTOU)
                    abrir = True
                elif em_casa:
                    eventos += self._encerrar_tirando(conn, sessao, now, em_casa=True, motivo="tirou_na_bronca")
                    ajustes.append(CONFIANCA_CORTOU)
                    abrir = True
                elif em_casa is False and now >= t0 + CORTE + LARGAR:
                    eventos += self._encerrar_tirando(conn, sessao, now, em_casa=False, motivo="tirou_largando")
                    ajustes.append(CONFIANCA_TIROU_LARGANDO)
                    abrir = True
            conn.commit()
        if abrir:
            self._abrir_pendencia(now)
        for delta in ajustes:
            self.db.ajustar_emocao(TRUST, delta, now=now)
        return eventos

    def _encerrar_tirando(self, conn, sessao, now: datetime, *, em_casa: bool, motivo: str) -> list[str]:
        """Ela tira todos (em casa vão pro carregador; fora, pra bolsa) e a sessão acaba. No fim da escada conta o
        incidente (se a bronca ainda não contou) e, largando o que fazia, conta em dobro: a pendência dura mais."""
        for b in self._em_uso(conn, sessao):
            self._registrar(conn, sessao["id"], b, 0, "sistema", None, now)
            conn.execute("UPDATE lovense_brinquedos SET onde=?, bateria_em=? WHERE brinquedo=?",
                         ("carregador" if em_casa else "bolsa", now.isoformat(), b))
        conn.execute("UPDATE lovense_sessoes SET estado='encerrada', fim_em=?, motivo_fim=? WHERE id=?",
                     (now.isoformat(), motivo, sessao["id"]))
        if motivo != "tirou_incomodada":                            # o fim da escada da palavra
            incidentes = (1 if int(sessao["escada"]) < 2 else 0) + (1 if motivo == "tirou_largando" else 0)
            conn.execute("UPDATE lovense_sessoes SET escada=3, respeitou=0, incidentes=incidentes+? WHERE id=?",
                         (incidentes, sessao["id"]))
        return [motivo]

    def _tirar_incomodada(self, now: datetime) -> list[str]:
        """No banho, forte demais: ela tira ali mesmo sem cortar o app (não é desrespeito à palavra — ele nem
        sabia), fica irritada com ele e dá o esporro quando sair."""
        with self.db.get_connection() as conn:
            eventos = self._assentar(conn, now)
            sessao = self._ativa(conn)
            if not sessao:
                conn.commit()
                return eventos
            eventos += self._encerrar_tirando(conn, sessao, now, em_casa=True, motivo="tirou_incomodada")
            conn.commit()
        try:
            from emotion import EmotionEngine, PATRICK
            EmotionEngine(self.db).feel("raiva", "irritacao", 0.35, "o Patrick exagerou no brinquedo", now,
                                        target=PATRICK, source_key=f"lovense:tirou:{sessao['id']}")
        except Exception:
            pass
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

    # ---------------------------------------------------------------- como ela está recebendo (passo 4)

    @staticmethod
    def _forte_desde(conn, sessao_id: int) -> Optional[datetime]:
        """Desde quando está forte (os brinquedos somados) sem parar."""
        niveis, desde = {}, None
        for c in conn.execute("""SELECT brinquedo, nivel, modo, padrao, criado_em FROM lovense_comandos
                                 WHERE sessao_id=? ORDER BY criado_em, id""", (sessao_id,)):
            niveis[c["brinquedo"]] = _efetivo(c["nivel"], c["modo"], c["padrao"]) / NIVEL_MAX
            desde = (desde or _dt(c["criado_em"])) if _junto(niveis.values()) >= FORTE else None
        return desde

    def recepcao(self, now: datetime, atividade: Optional[str] = None, *, feeling=None) -> Optional[dict]:
        """Como ela está recebendo o estímulo agora: parado, gostando, curtindo ou incomodada (com o grau), o ponto
        bom dela e onde ela está. None sem sessão aberta."""
        with self.db.get_connection() as conn:
            sessao = self._ativa(conn)
            if not sessao:
                return None
            em_uso = self._em_uso(conn, sessao)
            niveis = self._niveis(conn, sessao["id"])
            e = _junto(_efetivo(*niveis.get(b, (0, "classico", None))) / NIVEL_MAX for b in em_uso)
            forte_desde = self._forte_desde(conn, sessao["id"]) if e >= FORTE else None
        ctx = contexto(atividade, bool(sessao["fora_de_casa"]))
        from intimacy import CYCLE_LIBIDO, IntimacyEngine
        try:
            f = feeling or _feeling(self.db, now)
            libido, excitacao = float(f.libido), float(f.excitation)
            desconforto, energia = float(f.discomfort), float(f.energy)
            gozou_ha, fase = f.hours_since_release, f.cycle_phase or ""
            if feeling is None:      # o sentimento fica guardado 1 min; a excitação muda a cada 10 s: lê na hora
                excitacao = float(IntimacyEngine(self.db).current(now).arousal)
        except Exception:
            libido, excitacao, desconforto, energia, gozou_ha, fase = 0.5, 0.0, 0.0, 0.6, None, ""
        ciclo = next((v for k, v in CYCLE_LIBIDO.items() if fase and fase.startswith(k.split("_")[0])), 1.0)
        tesao = max(libido, excitacao)
        ponto = (PONTO_BASE + PONTO_TESAO * tesao) * ctx["fator"]
        ponto -= 0.35 * desconforto + (0.1 if energia < 0.35 else 0.0)
        cansou = bool(forte_desde and now - forte_desde > FORTE_CANSA)
        if cansou:
            ponto -= min(0.2, 0.01 * (now - forte_desde - FORTE_CANSA).total_seconds() / 60)
        folga = FOLGA_FORA if ctx["publico"] else FOLGA_CASA
        sensivel = gozou_ha is not None and gozou_ha * 3600 < SENSIVEL.total_seconds()
        if sensivel:
            ponto, folga = 0.1, 0.05                # só um toque bem de leve (nível 3) não incomoda
        ponto = max(0.1, min(1.0, ponto))
        if e <= 0.02:
            estado, grau = "parado", 0.0
        elif e > ponto + folga:
            estado, grau = "incomodada", min(1.0, (e - ponto - folga) / 0.25)
        elif excitacao >= CURTINDO_EXCITACAO and e >= ponto - ABAIXO:
            estado, grau = "curtindo", min(1.0, (excitacao - CURTINDO_EXCITACAO) / 0.4)
        else:
            estado, grau = "gostando", 0.0
        rec = dict(ctx, estado=estado, grau=round(grau, 3), e=round(e, 3), ponto=round(ponto, 3),
                   folga=folga, sensivel=sensivel, cansou=cansou, excitacao=excitacao,
                   vontade=ciclo * (0.7 + 0.6 * libido))
        rec["frase"] = _frase(rec)
        return rec

    def estimular(self, now: datetime, rec: Optional[dict]) -> Optional[float]:
        """O estímulo soma excitação de verdade (intimacy): mais forte, mais rápido; incomodando, quase nada."""
        if not rec or rec["e"] <= 0.02:
            return None
        taxa = GANHO_TESAO * rec["e"] * (0.25 if rec["estado"] == "incomodada" else 1.0) * rec["vontade"]
        from intimacy import IntimacyEngine
        return IntimacyEngine(self.db).estimular(now, taxa)

    def sentir(self, now: datetime, eventos: Iterable[str] = (), atividade: Optional[str] = None) -> Optional[dict]:
        """Os comandos dele (e os eventos da palavra e da bateria) viram o que ela sente: {texto, motivo} pro bot
        transformar em turno, ou None quando ela não sente diferença. Guarda o que ela já sentiu na sessão
        (`sentido_json`), então a rajada de comandos e o que mudou no intervalo entram juntos no turno seguinte.
        Com `atividade` (passo 4), o turno diz como ela está recebendo, e começar a incomodar sem ele mexer (cansou,
        ficou sensível, chegou na aula) também vira turno."""
        eventos = list(dict.fromkeys(e for e in eventos
                                     if e in EVENTOS_DE_TURNO or e.startswith("bateria_acabou:")))
        rec = self.recepcao(now, atividade) if atividade is not None else None
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
                    incomoda = bool(rec and rec["estado"] == "incomodada")
                    if (ligados and now - ult >= espera
                            and not (incomoda and snap.get("recepcao") != "incomodada")):
                        ritmo = _dt(snap.get("ritmo_desde")) or ult
                        minutos = max(1, round((now - ritmo).total_seconds() / 60))
                        motivo = "sustentado"
                        partes = [f"faz {minutos} min que " + " e ".join(
                            f"{_NOME[b]} vibra no mesmo ritmo dentro de você ({_sensacao(b, *agora[b], so_ritmo=True)})"
                            for b in ligados) + ("" if incomoda else "; o tesão vai acumulando")]
                    elif (incomoda and snap.get("recepcao") != "incomodada" and now - ult >= ENTRE_TURNOS):
                        # Ele não mexeu, mas começou a incomodar: cansou, ficou sensível, chegou num lugar com gente.
                        motivo = "incomodou"
                        partes = [f"{_NOME[b]} continua {_sensacao(b, *agora[b])}" for b in em_uso
                                  if agora[b][0] > 0]
            if partes and rec and rec["frase"] and motivo != "evento":
                partes.append(rec["frase"])
            if not partes:
                return None
            novo = {"em": now.isoformat(), "motivo": motivo, "b": {b: list(v) for b, v in agora.items()},
                    "ritmo_desde": (snap.get("ritmo_desde") if motivo in ("sustentado", "incomodou")
                                    else now.isoformat()),
                    "recepcao": rec["estado"] if rec else snap.get("recepcao")}
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
