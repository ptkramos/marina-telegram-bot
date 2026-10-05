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

- Corpo e mundo (passo 5a): ele pede e ela topa ou recusa pelo que sente (`disposicao`); a palavra ela puxa;
  coloca e tira quando FALA que colocou/tirou (`observe_conversa`); goza quando o corpo chega lá (`_gozar`) ou
  quando escreve que gozou; tira sozinha só por motivo de verdade (academia, dormir, briga, o Hush cansar) — o
  Lush dentro dela não incomoda; com o app parado, se a ideia foi dela, cutuca ele. O Hush é descoberta dela
  (receio → descobrindo → gostando → adora, ou "não é pra mim") e usar fora de casa é ousadia que cresce com as
  vezes boas (`_descoberta`). O bloco do prompt (`prompt`) diz o que ela sabe.

Quem chama: o Mini App manda os comandos; o bot transforma os eventos em turno (o que ela sente, `sentir`), lê
a fala dela depois de cada resposta (`observe_conversa`) e põe o bloco no prompt. Nada aqui fala por ela: o turno
descreve a sensação, nunca a fala.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

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
                    "sessao_acabou_bateria",       # + bateria_acabou:<brinquedo>; os dela (pediu_parar,
                                                   # tirou) ela já sabe
                    # passo 5a: o que o corpo e o mundo fazem sem ela falar (ela conta pra ele)
                    "gozou", "tirou_academia", "tirou_dormir", "tirou_briga", "tirou_hush")

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

# Passo 5a (Patrick, 05/10): corpo e mundo. Números meus (calibrar no uso).
DESCOBERTA_KEY = "lovense_descoberta_json"   # o Hush e a ousadia fora de casa, construídos com o tempo
PALAVRA_KEY = "lovense_palavra_pendente"     # palavra combinada antes de ela colocar
PENDENTE_KEY = "lovense_pendente"            # "peraí que vou colocar" / foi ao banheiro tirar
PALAVRA_VALE = timedelta(hours=2)
ENTREGA_KEY = "lovense_entrega_json"         # a encomenda do Patrick (05/10): a caminho → portaria → recebido
CARGA_DE_FABRICA = 0.6
ENTREGA_DEPOIS_DO_AVISO = timedelta(minutes=3)   # ele avisa que chegou → o Seu Jorge interfona
ENTREGA_AVISO_RE = re.compile(r"\b(?:chegou|chegaram|entreg(?:aram|ou|ue)|confirmaram|portaria|interfon\w*|"
                              r"desce\s+(?:l[aá]\s+)?(?:pra\s+)?pegar|j[aá]\s+t[aá]\s+a[ií])\b", re.IGNORECASE)
ASSUNTO_KEY = "lovense_assunto_em"           # última vez que a conversa falou do brinquedo
ASSUNTO_VALE = timedelta(minutes=30)
DAQUI_A_POUCO = timedelta(minutes=2)          # em casa, "vou colocar" → colocou
# O Hush é descoberta dela (Patrick: "a marina ainda precisa descobrir se gosta ou não de anal… se ela usar e eu
# respeitar ela pode acabar gostando… vai ser dela a decisão e a opinião"). O gosto (0–1) anda com a experiência
# de cada vez: tempo gostoso, gozar com ele, ele respeitar o ponto e a palavra; incomodar e desrespeito descem, e
# o ruim pesa mais no começo. Com 2+ vezes e o gosto lá embaixo ela conclui que não é pra ela (não usa nem
# sugere; muda de opinião só conversando — 5b).
GOSTO_INICIAL = 0.2                           # curiosa, com medo
NAO_E_PRA_MIM = 0.12
HUSH_ESTAGIO_TEXTO = {"receio": "nunca usou: curiosa e com medo", "descobrindo": "já usou e ainda está descobrindo "
                      "se gosta", "gostando": "já sabe que gosta", "adora": "adora",
                      "nao_e_pra_mim": "usou e concluiu que não é pra ela"}
HUSH_INTENSO = {"receio": 1.6, "descobrindo": 1.35, "gostando": 1.0, "adora": 1.0, "nao_e_pra_mim": 1.6}
HUSH_CONFORTO = {"receio": 10, "descobrindo": 25, "gostando": 60, "adora": None, "nao_e_pra_mim": 10}   # min
# Fora de casa é ousadia (Patrick: "sim, ousadia"): sem nenhuma, com gente perto o ponto bom cai mais 20%.
OUSADIA_PISO = 0.8
GOZO_EXCITACAO = 0.9                          # o corpo chega lá com o estímulo (ou ela escreve que gozou)
BRIGA = 0.45                                  # chateada/triste com ele por outra coisa: perdeu o clima, tira
TOPA = 0.55                                   # vontade pra topar quando ele pede
BASE_VONTADE = 0.5                            # neutro: um pouco abaixo de topar (precisa de um pouco de tesão)
# App parado (Patrick: "pela origem"): a ideia foi dela → expectativa, e se ele some vira impaciência e ela
# cutuca (de 10 a 25 min, mais cedo com tesão; depois mais uma vez); foi pedido dele → a ansiedade gostosa de
# não saber quando vem, sem cutucar. Ela não tira por isso: o Lush dentro dela não incomoda.
PARADO_BASE, PARADO_TESAO = 25, 15            # min: espera = 25 − 15 × tesão
PARADO_DE_NOVO = timedelta(minutes=30)
PARADO_CUTUCA = 2
# Gate barato antes do modelo: a conversa é sobre o brinquedo? (e, com sessão, a fala dela tem cara de ação)
BRINQUEDO_RE = re.compile(r"\b(?:lush|hush|lovense|brinquedo\w*|vibrador\w*|plug)\b", re.IGNORECASE)
ACAO_RE = re.compile(r"\b(?:coloc\w*|coloqu\w*|bot(?:ei|ar|ando)|tir(?:ei|ar|ando|o)|palavra|liber\w*|dentro|"
                     r"pode\s+(?:voltar|ligar|continuar))\b", re.IGNORECASE)
COLOCOU_RE = re.compile(r"\b(?:coloc\w*|coloqu\w*|bot(?:ei|ando|ar|o)|pus|pondo|dentro|enfiei)\b", re.IGNORECASE)
TIROU_RE = re.compile(r"\b(?:tir(?:ei|ar|ando|o|ou)|tirad[oa])\b", re.IGNORECASE)
CONVERSA_RE = re.compile(r"\b(?:desculp\w*|perd[aã]o|convers\w*|errei|erro|magoad\w*|chatead\w*|confian\w*|"
                         r"palavra|aquilo|respeit\w*)\b", re.IGNORECASE)


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in t if not unicodedata.combining(c)).casefold()


def _tem_palavra(fala: str, palavra: str, msg_dele: str = "") -> bool:
    """Ela disse a palavra de segurança (só ela conta). Falar DA palavra ("a palavra é abacaxi", "qual é a
    palavra?") não é dizer a palavra."""
    p = _norm(palavra).strip()
    if not p:
        return False
    if re.search(r"\bpalavra\b", _norm(fala)) or re.search(r"\bpalavra\b", _norm(msg_dele)):
        return False
    return re.search(rf"(?<!\w){re.escape(p)}(?!\w)", _norm(fala)) is not None


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


def contexto(atividade: Optional[str], fora_de_casa: bool = False, ousadia: float = 1.0) -> dict:
    """Onde ela está, pelo tipo da disponibilidade: fator do ponto bom, se está em casa e se alcança o celular.
    Fora de casa a ousadia dela (0–1, passo 5a) também pesa: as primeiras vezes com gente perto, mais nervosa."""
    atividade = atividade or "UNKNOWN"
    em_casa = atividade in EM_CASA or (atividade in ("UNKNOWN", "MEAL") and not fora_de_casa)
    fator = 1.0 if em_casa else LUGAR_FATOR.get(atividade, 0.85) * (OUSADIA_PISO + (1 - OUSADIA_PISO) * ousadia)
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
    "gozou": "o tesão chegou no limite e você gozou agora, com o brinquedo vibrando dentro de você{onde}",
    "tirou_academia": "você tirou o brinquedo pra treinar (na academia não dá); o app dele desconectou",
    "tirou_dormir": "você tirou o brinquedo pra dormir; o app dele desconectou",
    "tirou_briga": ("você perdeu o clima, chateada com ele, e tirou o brinquedo{fora}; o app dele "
                    "desconectou"),
    "tirou_hush": "o Hush começou a cansar e você tirou{fora}{resto}",
}
# Onde ela está, quando goza fora de casa (vira história: disfarça, fica vermelha).
_ONDE_GOZO = {"CLASS": "no meio da aula", "WORK": "no meio do trabalho", "SOCIAL": "no meio das amigas",
              "MEAL": "na mesa, comendo", "MANICURE": "na manicure", "GYM": "na academia",
              "COMMUTE": "no caminho", "OUT_SOLO": "na rua", "PET_WALK": "passeando com o Milo"}


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
                if estoque[b]["onde"] == "entrega":
                    raise ValueError(f"{b} ainda não chegou (a encomenda do Patrick)")
                if fora_de_casa and estoque[b]["onde"] not in ("bolsa", "nela"):
                    raise ValueError(f"{b} não está na bolsa: fora de casa fica pra quando voltar")
                if float(estoque[b]["bateria"]) < BATERIA_MINIMA:
                    raise ValueError(f"{b} sem bateria")
            sessao = self._ativa(conn)
            nova = sessao is None
            if sessao:
                atuais = json.loads(sessao["brinquedos_json"] or "[]")
                conn.execute("UPDATE lovense_sessoes SET brinquedos_json=? WHERE id=?",
                             (json.dumps(list(dict.fromkeys(atuais + brinquedos))), sessao["id"]))
                sessao_id = sessao["id"]
                exp = json.loads(sessao["experiencia_json"] or "{}")
            else:
                sessao_id = conn.execute(
                    """INSERT INTO lovense_sessoes (brinquedos_json, origem, desde, lugar, fora_de_casa)
                       VALUES (?, ?, ?, ?, ?)""",
                    (json.dumps(brinquedos), origem, now.isoformat(), lugar, int(fora_de_casa))).lastrowid
                exp = {}
            for b in brinquedos:
                conn.execute("UPDATE lovense_brinquedos SET onde='nela', bateria_em=? WHERE brinquedo=?",
                             (now.isoformat(), b))
                exp.setdefault("desde", {})[b] = now.isoformat()
            conn.execute("UPDATE lovense_sessoes SET experiencia_json=? WHERE id=?", (json.dumps(exp), sessao_id))
            conn.commit()
        if nova:
            # Passo 5a: a palavra que eles combinaram antes de ela colocar vale pra esta vez.
            pend = self._json(PALAVRA_KEY)
            if pend.get("palavra") and (_dt(pend.get("em")) or now - PALAVRA_VALE * 2) >= now - PALAVRA_VALE:
                self.combinar_palavra(now, pend["palavra"])
            self.db.set_estado_relacional(PALAVRA_KEY, "")
            self._sentir_colocou(now, origem, sessao_id)
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
        self._fechar_experiencias(now)
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
        self._fechar_experiencias(now)
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
        da disponibilidade (onde ela está); sem ela, só sabe se dá pra mexer no celular.
        Passo 5a: o corpo goza quando chega lá, e ela tira sozinha por motivo de verdade (academia, dormir, briga,
        o Hush cansar); ao fim de cada vez, a experiência vira descoberta (o Hush, a ousadia fora de casa)."""
        eventos = self._tick(now, pode_mexer_no_celular, atividade)
        self._fechar_experiencias(now)
        return eventos

    def _tick(self, now: datetime, pode_mexer_no_celular: bool, atividade: Optional[str]) -> list[str]:
        em_casa = None
        antes: list[str] = []
        if atividade is not None:
            rec = self.recepcao(now, atividade)
            if rec:
                pode_mexer_no_celular, em_casa = rec["pode_celular"], rec["em_casa"]
                self._experimentar(now, rec)
                excitacao = self.estimular(now, rec)
                if (excitacao is not None and excitacao >= GOZO_EXCITACAO
                        and rec["estado"] in ("gostando", "curtindo") and not rec["sensivel"]):
                    antes += self._gozar(now, rec)
                if rec["atividade"] == "SHOWER" and rec["estado"] == "incomodada" and rec["grau"] >= 0.5:
                    # No banho o celular fica fora do box: forte demais, ela tira ali e dá o esporro depois.
                    return antes + self._tirar_incomodada(now)
                motivo = self._motivo_pra_tirar(now, rec)
                if motivo:
                    return antes + self._tirar_por(now, motivo, rec)
        return antes + self._escada(now, pode_mexer_no_celular, em_casa)

    def _escada(self, now: datetime, pode_mexer_no_celular: bool, em_casa: Optional[bool]) -> list[str]:
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
        # Passo 5a: o Hush, enquanto ela descobre, é mais intenso do que o nível diz; fora de casa pesa a ousadia.
        desc = self._descoberta()
        hush = HUSH_INTENSO[self.estagio_hush(desc)]
        e = _junto(_efetivo(*niveis.get(b, (0, "classico", None))) / NIVEL_MAX * (hush if b == "hush" else 1.0)
                   for b in em_uso)
        with self.db.get_connection() as conn:
            forte_desde = self._forte_desde(conn, sessao["id"]) if e >= FORTE else None
        ctx = contexto(atividade, bool(sessao["fora_de_casa"]), desc["fora"]["ousadia"])
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
                   folga=folga, sensivel=sensivel, cansou=cansou, excitacao=excitacao, tesao=tesao,
                   vontade=ciclo * (0.7 + 0.6 * libido), em_uso=em_uso)
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
                ctx = rec or (contexto(atividade, bool(sessao["fora_de_casa"])) if atividade is not None else None)
                publico = bool(ctx and ctx["publico"])
                fmt = {"onde": (f", {_ONDE_GOZO.get(ctx['atividade'], 'no meio de gente')}, tentando disfarçar"
                                if publico else ""),
                       "fora": " no banheiro" if ctx and not ctx["em_casa"] else "",
                       "resto": "; o Lush continua" if "lush" in em_uso else "; o app dele desconectou"}
                partes = [_EVENTO_TEXTO[e.partition(":")[0]].format(
                    nome_de=_NOME_DE.get(e.partition(":")[2], "do brinquedo"), **fmt) for e in eventos]
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
                if (not partes and not mudancas and em_uso and sessao["origem"] == "dela"
                        and not any(agora[b][0] for b in em_uso)):
                    # Passo 5a: a ideia foi dela e ele sumiu do app — a expectativa vira impaciência e ela cutuca.
                    cutucou = int(snap.get("cutucou") or 0)
                    ultimo = self._ultimo_comando(conn, sessao["id"]) or _dt(sessao["desde"]) or now
                    tesao = rec["tesao"] if rec else 0.5
                    espera = (timedelta(minutes=PARADO_BASE - PARADO_TESAO * tesao) if not cutucou
                              else PARADO_DE_NOVO)
                    base = max(ultimo, _dt(snap.get("cutucou_em")) or ultimo) if cutucou else ultimo
                    if cutucou < PARADO_CUTUCA and now - base >= espera:
                        motivo = "parado"
                        minutos = max(1, round((now - ultimo).total_seconds() / 60))
                        partes = [f"faz {minutos} min que ele não mexe no brinquedo: a ideia foi sua, você está com "
                                  f"ele dentro e {'continua ' if cutucou else ''}esperando ele ligar"]
            if partes and rec and rec["frase"] and motivo != "evento":
                partes.append(rec["frase"])
            if not partes:
                return None
            novo = {"em": now.isoformat(), "motivo": motivo, "b": {b: list(v) for b, v in agora.items()},
                    "ritmo_desde": (snap.get("ritmo_desde") if motivo in ("sustentado", "incomodou")
                                    else now.isoformat()),
                    "recepcao": rec["estado"] if rec else snap.get("recepcao")}
            if motivo == "parado":
                novo.update(cutucou=int(snap.get("cutucou") or 0) + 1, cutucou_em=now.isoformat())
            conn.execute("UPDATE lovense_sessoes SET sentido_json=? WHERE id=?", (json.dumps(novo), sessao["id"]))
            conn.commit()
        if motivo == "parado":
            self._sente("raiva", "impaciencia", 0.15 + 0.1 * novo["cutucou"],
                        "o Patrick sumiu do app com o brinquedo nela", now, f"lovense:parado:{sessao['id']}:{novo['cutucou']}")
        texto = "; ".join(partes)
        return {"texto": f"[Brinquedo, pelo app do Patrick: {texto[0].upper()}{texto[1:]}]", "motivo": motivo}

    # ---------------------------------------------------------------- corpo e mundo (passo 5a)

    def _json(self, chave: str) -> dict:
        raw = self.db.get_estado_relacional(chave)
        try:
            out = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            out = {}
        return out if isinstance(out, dict) else {}

    def _descoberta(self) -> dict:
        d = self._json(DESCOBERTA_KEY)
        d.setdefault("hush", {})
        d["hush"].setdefault("gosto", GOSTO_INICIAL)
        d["hush"].setdefault("vezes", 0)
        d["hush"].setdefault("nao_e_pra_mim", False)
        d.setdefault("fora", {})
        d["fora"].setdefault("ousadia", 0.0)
        d["fora"].setdefault("vezes", 0)
        return d

    @staticmethod
    def estagio_hush(d: dict) -> str:
        h = d["hush"]
        if h.get("nao_e_pra_mim"):
            return "nao_e_pra_mim"
        if not h.get("vezes"):
            return "receio"
        g = float(h.get("gosto", GOSTO_INICIAL))
        return "descobrindo" if g < 0.45 else "gostando" if g < 0.75 else "adora"

    def _sente(self, family: str, kind: str, intensity: float, cause: str, now: datetime, key: str,
               *, target: Optional[str] = "o Patrick") -> None:
        try:
            from emotion import EmotionEngine
            EmotionEngine(self.db).feel(family, kind, intensity, cause, now, target=target, source_key=key)
        except Exception:
            pass
        _SENTIMENTO.clear()

    def _registra(self, key: str, at: datetime, summary: str, *, importance: float = 0.3,
                  share: float = 0.6) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'routine','lovense',?,'simulated',1,?,?,?,?)""",
                (key, at.isoformat(), summary, importance, json.dumps(["marina"]), share, at.isoformat()))
            conn.commit()

    def _sentir_colocou(self, now: datetime, origem: str, sessao_id: int) -> None:
        """A ideia foi dela: expectativa de ele ligar. Pedido dele: a ansiedade gostosa de não saber quando vem."""
        cause = ("colocou o brinquedo esperando o Patrick ligar pelo app" if origem == "dela"
                 else "com o brinquedo que o Patrick pediu, sem saber quando ele vai ligar")
        self._sente("alegria", "expectativa", 0.4 if origem == "dela" else 0.35, cause, now,
                    f"lovense:colocou:{sessao_id}")

    @staticmethod
    def _ultimo_comando(conn, sessao_id: int) -> Optional[datetime]:
        row = conn.execute("""SELECT MAX(criado_em) FROM lovense_comandos WHERE sessao_id=? AND modo!='sistema'""",
                           (sessao_id,)).fetchone()
        return _dt(row[0]) if row else None

    def _experimentar(self, now: datetime, rec: dict) -> None:
        """Soma o tempo gostoso e o que incomodou no Hush e fora de casa (a experiência desta vez)."""
        with self.db.get_connection() as conn:
            sessao = self._ativa(conn)
            if not sessao:
                return
            exp = json.loads(sessao["experiencia_json"] or "{}")
            t0 = _dt(exp.get("t"))
            exp["t"] = now.isoformat()
            if t0 and rec["estado"] != "parado":
                dt = max(0.0, min(30.0, (now - t0).total_seconds()))
                niveis = self._niveis(conn, sessao["id"])
                partes = []
                if "hush" in rec["em_uso"] and niveis.get("hush", (0,))[0] > 0:
                    partes.append("hush")
                if rec["publico"]:
                    partes.append("fora")
                for p in partes:
                    e = exp.setdefault(p, {"bom": 0.0, "ruim": 0.0, "ligado": 0.0})
                    e["ligado"] += dt
                    if rec["estado"] in ("gostando", "curtindo"):
                        e["bom"] += dt
                    elif rec["estado"] == "incomodada":
                        e["ruim"] += dt
            conn.execute("UPDATE lovense_sessoes SET experiencia_json=? WHERE id=?", (json.dumps(exp), sessao["id"]))
            conn.commit()

    @staticmethod
    def _nota(e: dict, incidentes: int, gozos: int) -> Optional[float]:
        """Como foi desta vez (−1 a 1): tempo gostoso contra o que incomodou, gozar, e ele ter desrespeitado."""
        ligado = float(e.get("ligado") or 0)
        if ligado < 60 and not incidentes and not gozos:
            return None                               # mal ligou: não diz nada
        nota = (float(e.get("bom") or 0) - 1.5 * float(e.get("ruim") or 0)) / max(ligado, 1.0)
        nota += 0.3 * min(gozos, 2) - (0.6 if incidentes else 0.0)
        return max(-1.0, min(1.0, nota))

    def _fechar_experiencias(self, now: datetime) -> None:
        """O Hush que saiu dela e as sessões que acabaram viram descoberta (uma vez cada)."""
        fechar = []
        with self.db.get_connection() as conn:
            nela = {b for b, r in self._brinquedos(conn).items() if r["onde"] == "nela"}
            for s in conn.execute("""SELECT * FROM lovense_sessoes WHERE experiencia_json IS NOT NULL
                                     AND experiencia_json NOT LIKE '%"fechado": true%' ORDER BY id"""):
                exp = json.loads(s["experiencia_json"] or "{}")
                acabou = s["estado"] not in ("conectada", "pausada")
                for p in ("hush", "fora"):
                    if p in (exp.get("fechou") or []):
                        continue
                    if p == "hush" and "hush" not in (exp.get("desde") or {}):
                        continue
                    if p == "fora" and "fora" not in exp:
                        continue                          # não usou fora de casa desta vez
                    if acabou or (p == "hush" and "hush" not in nela):
                        fechar.append((s, p, exp))
                if acabou:
                    exp["fechado"] = True
                    conn.execute("UPDATE lovense_sessoes SET experiencia_json=? WHERE id=?",
                                 (json.dumps(exp), s["id"]))
            conn.commit()
        if not fechar:
            return
        d = self._descoberta()
        for s, p, exp in fechar:
            if p == "hush":
                gozos = int(exp.get("gozos_hush") or 0)
            else:
                gozos = int(exp.get("gozos_fora") or 0)
            nota = self._nota(exp.get(p) or {}, int(s["incidentes"] or 0), gozos)
            if nota is not None:
                self._descobrir(d, p, nota, s["id"], now)
            with self.db.get_connection() as conn:
                row = conn.execute("SELECT experiencia_json FROM lovense_sessoes WHERE id=?", (s["id"],)).fetchone()
                atual = json.loads(row["experiencia_json"] or "{}")
                atual["fechou"] = list(dict.fromkeys((atual.get("fechou") or []) + [p]))
                conn.execute("UPDATE lovense_sessoes SET experiencia_json=? WHERE id=?",
                             (json.dumps(atual), s["id"]))
                conn.commit()
        self.db.set_estado_relacional(DESCOBERTA_KEY, json.dumps(d))

    def _descobrir(self, d: dict, parte: str, nota: float, sessao_id: int, now: datetime) -> None:
        if parte == "hush":
            h = d["hush"]
            antes = self.estagio_hush(d)
            vezes = int(h["vezes"])
            peso = 0.2 / (1 + 0.2 * vezes) * (1.5 if nota < 0 and vezes < 3 else 1.0)
            h["gosto"] = round(max(0.0, min(1.0, float(h["gosto"]) + peso * nota)), 4)
            h["vezes"] = vezes + 1
            h["ultima_nota"], h["ultima"] = round(nota, 3), now.isoformat()
            if h["vezes"] >= 2 and h["gosto"] < NAO_E_PRA_MIM:
                h["nao_e_pra_mim"] = True
            vez = "pela primeira vez" if vezes == 0 else "de novo"
            if h["nao_e_pra_mim"] and antes != "nao_e_pra_mim":
                opiniao = "e concluiu que o Hush não é pra ela: não curtiu"
            elif nota >= 0.4:
                opiniao = "e gostou mais do que esperava"
            elif nota >= 0:
                opiniao = "e ainda não sabe se gosta: foi estranho e gostoso ao mesmo tempo"
            else:
                opiniao = "e não curtiu desta vez: incomodou"
            self._registra(f"lovense:hush:{sessao_id}", now,
                           f"Usou o Hush {vez}, com o Patrick controlando pelo app, {opiniao}. A opinião é dela: "
                           "conta pra ele se quiser.", importance=0.35)
        else:
            f = d["fora"]
            vezes = int(f["vezes"])
            peso = 0.15 / (1 + 0.15 * vezes) * (1.5 if nota < 0 and vezes < 3 else 1.0)
            f["ousadia"] = round(max(0.0, min(1.0, float(f["ousadia"]) + peso * nota)), 4)
            f["vezes"] = vezes + 1
            f["ultima_nota"], f["ultima"] = round(nota, 3), now.isoformat()

    def _gozar(self, now: datetime, rec: Optional[dict], *, pela_fala: bool = False) -> list[str]:
        """Gozou com o brinquedo: vale no corpo (sensível, o tesão volta devagar) e no mundo (fora de casa vira
        história). `pela_fala`: ela escreveu que gozou (o intimacy já registrou o clímax)."""
        with self.db.get_connection() as conn:
            sessao = self._ativa(conn)
            if not sessao:
                return []
            exp = json.loads(sessao["experiencia_json"] or "{}")
            ult = _dt(exp.get("gozou_em"))
            if ult and now - ult < SENSIVEL:
                return []
            em_uso = self._em_uso(conn, sessao)
            exp["gozou_em"] = now.isoformat()
            exp["gozos"] = int(exp.get("gozos") or 0) + 1
            if "hush" in em_uso:
                exp["gozos_hush"] = int(exp.get("gozos_hush") or 0) + 1
            publico = bool(rec and rec["publico"])
            if publico:
                exp["gozos_fora"] = int(exp.get("gozos_fora") or 0) + 1
            conn.execute("UPDATE lovense_sessoes SET experiencia_json=? WHERE id=?", (json.dumps(exp), sessao["id"]))
            conn.commit()
        if not pela_fala:
            try:
                from intimacy import IntimacyEngine, _no_mundo
                eng = IntimacyEngine(self.db)
                st = eng._load()
                st.update(arousal=0.35, mode_since=None, hot_turns=0, climax_at=now.isoformat(),
                          updated_at=now.isoformat())
                eng._save(st)
                _no_mundo(self.db, now, acabou=True, gozou=True)
            except Exception:
                pass
        quais = " e ".join(_NOME[b] for b in em_uso) or "o brinquedo"
        if publico:
            onde = _ONDE_GOZO.get(rec["atividade"], "no meio de gente")
            summary = (f"Gozou com {quais} que o Patrick controlava pelo app, {onde}, tentando disfarçar "
                       "(ficou vermelha).")
            self._sente("vergonha", "vergonha", 0.3, f"gozou {onde} com o brinquedo", now,
                        f"lovense:gozo:{sessao['id']}:{exp['gozos']}:vergonha", target=None)
        else:
            summary = f"Gozou com {quais} que o Patrick controlava pelo app."
        self._registra(f"lovense:gozo:{sessao['id']}:{exp['gozos']}", now, summary, importance=0.35)
        self._sente("alegria", "alivio", 0.3, "gozou com o brinquedo", now,
                    f"lovense:gozo:{sessao['id']}:{exp['gozos']}", target=None)
        return [] if pela_fala else ["gozou"]

    def gozou_pela_fala(self, now: datetime, atividade: Optional[str] = None) -> bool:
        """Ela escreveu que gozou com o brinquedo nela (o intimacy já marcou o clímax): vale no mundo também."""
        if not self.sessao_ativa():
            return False
        rec = self.recepcao(now, atividade) if atividade is not None else None
        self._gozar(now, rec, pela_fala=True)
        return True

    def _motivo_pra_tirar(self, now: datetime, rec: dict) -> Optional[str]:
        """O Lush dentro dela não incomoda: ela só tira sozinha por motivo de verdade."""
        if rec["atividade"] == "GYM":
            return "tirou_academia"
        if rec["atividade"] == "SLEEPING":
            return "tirou_dormir"
        try:
            f = _feeling(self.db, now)
            for ep in getattr(f, "episodes", None) or []:
                # Briga é raiva com ele, ou decepção/chateação com ele — saudade e solidão são tristeza com ele
                # também, e saudade é vontade dele (achado na pré-visualização, 05/10).
                chateada = ep.family == "raiva" or ep.kind in ("decepcao", "chateacao")
                if (ep.target == "o Patrick" and chateada and ep.intensity >= BRIGA
                        and "brinquedo" not in (ep.cause or "") and "app" not in (ep.cause or "")):
                    return "tirou_briga"
        except Exception:
            pass
        if "hush" in rec["em_uso"]:
            limite = HUSH_CONFORTO[self.estagio_hush(self._descoberta())]
            with self.db.get_connection() as conn:
                sessao = self._ativa(conn)
                desde = _dt((json.loads(sessao["experiencia_json"] or "{}").get("desde") or {}).get("hush")) \
                    if sessao else None
            if limite and desde and now - desde >= timedelta(minutes=limite):
                return "tirou_hush"
        return None

    def _tirar_por(self, now: datetime, motivo: str, rec: dict) -> list[str]:
        """Tira pelo motivo dela: em casa na hora; fora, no banheiro do lugar (vira pausa na agenda, se der)."""
        em_casa = rec["em_casa"] and motivo != "tirou_academia"
        if not rec["em_casa"]:
            self._banheiro(now, "tirando o brinquedo escondida")
        quais = ["hush"] if motivo == "tirou_hush" else None
        self.tirar(now, quais, em_casa=em_casa)
        if motivo == "tirou_briga":
            with self.db.get_connection() as conn:
                conn.execute("""UPDATE lovense_sessoes SET motivo_fim='briga' WHERE id=(SELECT MAX(id)
                                FROM lovense_sessoes) AND estado='encerrada'""")
                conn.commit()
        return [motivo]

    def _banheiro(self, now: datetime, texto: str, minutos: int = 5) -> Optional[datetime]:
        """Fora de casa ela vai ao banheiro do lugar (pausa da agenda reativa) e volta pro que fazia."""
        try:
            from agenda_reativa import AgendaReativa
            p = AgendaReativa(self.db).pausar(now, "lovense", texto=texto, minutos=minutos)
            return _dt(p["fim"]) if p else None
        except Exception:
            return None

    # ---------------------------------------------------------------- topar ou recusar (pedido dele)

    def disposicao(self, now: datetime, brinquedos: Iterable[str] = ("lush",), atividade: Optional[str] = None,
                   *, feeling=None) -> dict:
        """Se ele pedir agora, ela topa? Pelo que ela sente (agenda_viva.Disposicao, tipo "lovense"): energia,
        humor, chateada com ele, dor; mais o tesão, a confiança, a pendência, onde está, a novidade e, no Hush, a
        descoberta dela. Mesmo estado, mesma decisão. {vontade, topa, motivo, impossivel}."""
        from agenda_viva import Disposicao
        brinquedos = list(brinquedos)
        try:
            f = feeling or _feeling(self.db, now)
        except Exception:
            f = None
        aval = Disposicao(self.db).avaliar("lovense", now, feeling=f)
        # A Disposicao é pra sair de casa: lá a saudade dele pesa contra; aqui é vontade dele.
        fat = [("saudade", "com saudade dele", abs(x[2]) * 0.5) if x[1] == "com saudade" else x
               for x in aval.fatores]
        ctx = contexto(atividade)
        with self.db.get_connection() as conn:
            self._assentar(conn, now)
            estoque = self._brinquedos(conn)
            conn.commit()
        impossivel = None
        for b in brinquedos:
            onde = estoque[b]["onde"]
            if onde == "entrega":
                impossivel = "ainda não chegou (o Patrick encomendou)"
            elif not ctx["em_casa"] and onde not in ("bolsa", "nela"):
                impossivel = f"{_NOME[b]} ficou em casa"
            elif float(estoque[b]["bateria"]) < BATERIA_MINIMA:
                impossivel = f"{_NOME[b]} está sem bateria (carregando)"
        if ctx["atividade"] in SEM_CELULAR:
            impossivel = impossivel or "agora não dá pra mexer no celular"
        if f is not None:
            tesao = max(float(f.libido), float(f.excitation))
            if abs(tesao - 0.5) >= 0.05:
                fat.append(("tesao", "com tesão" if tesao > 0.5 else "sem clima", (tesao - 0.5) * 0.8))
            gozou_ha = f.hours_since_release
            if gozou_ha is not None and gozou_ha * 3600 < SENSIVEL.total_seconds():
                fat.append(("sensivel", "acabou de gozar, sensível", -0.3))
        trust = self.confianca(now)
        if abs(trust - 0.8) >= 0.03:
            fat.append(("confianca", "confia nele" if trust > 0.8 else "com a confiança abalada", trust - 0.8))
        n = self.sessoes_recentes(now)
        if n >= 4:
            fat.append(("novidade", "já usou bastante essa semana", -0.05 * (n - 3)))
        desc = self._descoberta()
        if ctx["publico"]:
            fat.append(("ousadia", "nervosa de usar no meio de gente" if desc["fora"]["ousadia"] < 0.5
                        else "já pegou o jeito de usar fora", -0.2 * (1 - desc["fora"]["ousadia"]) + 0.05))
        recusa = None
        if "hush" in brinquedos:
            estagio = self.estagio_hush(desc)
            if estagio == "nao_e_pra_mim":
                recusa = "não curtiu o Hush e não quer usar de novo"
            else:
                fat.append(("hush", {"receio": "com medo do Hush", "descobrindo": "ainda descobrindo o Hush",
                                     "gostando": "gosta do Hush", "adora": "adora o Hush"}[estagio],
                            {"receio": -0.25, "descobrindo": -0.1, "gostando": 0.0, "adora": 0.05}[estagio]))
        if self.pendencia(now):
            recusa = recusa or "ainda magoada com a última vez (ele não respeitou a palavra): só depois de conversarem"
        # Neutro um pouco abaixo de topar: com o humor de sempre, precisa de um pouco de tesão (ou de saudade dele,
        # de tédio) pra topar.
        vontade = max(0.0, min(1.0, BASE_VONTADE + sum(x[2] for x in fat)))
        topa = vontade >= TOPA and not recusa and not impossivel
        cands = [x for x in fat if (x[2] > 0) == topa and x[2] != 0]
        motivo = recusa or impossivel or (max(cands, key=lambda x: abs(x[2]))[1] if cands else "")
        return {"vontade": round(vontade, 3), "topa": topa, "motivo": motivo, "impossivel": impossivel,
                "recusa": recusa}

    # ---------------------------------------------------------------- prompt

    def prompt(self, now: datetime, atividade: Optional[str] = None, conversa: str = "") -> Optional[str]:
        """O que ela sabe do brinquedo agora (bloco do prompt). Com sessão: tudo. Sem sessão: só quando a conversa
        fala de brinquedo (onde estão, se ela toparia agora, como começa)."""
        st = self.estado(now)
        desc = self._descoberta()
        estagio = self.estagio_hush(desc)
        bat = {b["nome"]: b for b in st["brinquedos"]}
        hush_linha = (f"- Hush (plug anal vibratório): você {HUSH_ESTAGIO_TEXTO[estagio]}. A opinião sobre ele é sua "
                      "e vai se formando com as vezes que você usa.")
        if not st["conectada"]:
            e = self.entrega()
            if e.get("status") in ("a_caminho", "portaria"):
                # A encomenda ainda não chegou: entra sempre ("chegou, desce pra pegar" nem diz o que é).
                linhas = ["[BRINQUEDO — LOVENSE, a encomenda do Patrick]",
                          "- O Patrick encomendou pra você dois brinquedos Lovense, que ele vai controlar pelo app "
                          "dele: o Lush (vibrador que vai dentro) e o Hush (plug anal vibratório). " + (
                              "Chegaram e estão na portaria com o Seu Jorge: você pega quando puder descer."
                              if e["status"] == "portaria" else
                              "Ainda não chegaram: ele te avisa quando a entrega confirmar, aí o Seu Jorge interfona "
                              "e você desce pra pegar."),
                          "- Você ainda não está com eles: não diga que já abriu, colocou ou testou.",
                          hush_linha]
                return "\n".join(linhas)
            if not BRINQUEDO_RE.search(conversa or ""):
                return None
            onde = {"gaveta": "na gaveta", "carregador": "no carregador", "bolsa": "na sua bolsa", "nela": "em você"}
            linhas = ["[BRINQUEDO — LOVENSE, controlado pelo app do Patrick]",
                      "- Você tem dois brinquedos Lovense que o Patrick controla pelo app dele, de onde ele estiver: "
                      "o Lush (vibrador que vai dentro) e o Hush (plug anal vibratório).",
                      "- Onde estão: " + "; ".join(f"{_NOME[b][2:].capitalize()} {onde.get(bat[b]['onde'], 'em casa')}"
                                                   f" ({round(bat[b]['bateria'] * 100)}%)" for b in BRINQUEDOS) + ".",
                      hush_linha]
            for quais, nome in ((["lush"], "o Lush"), (["hush"], "o Hush")):
                d = self.disposicao(now, quais, atividade)
                if d["topa"]:
                    linhas.append(f"- Se ele pedir pra você usar {nome} agora: você topa ({d['motivo'] or 'no clima'}).")
                else:
                    linhas.append(f"- Se ele pedir pra você usar {nome} agora: você não quer ({d['motivo']}).")
            linhas.append("- Se topar: antes de ele ligar, combine a palavra de segurança desta vez — você puxa "
                          "(sugere uma ou pergunta qual vai ser). Em casa você coloca na hora e conta pra ele quando "
                          "colocou; fora de casa, só se o brinquedo estiver na sua bolsa. Só diga que colocou se "
                          "colocou mesmo.")
            return "\n".join(linhas)
        rec = self.recepcao(now, atividade)
        quais = [b for b in BRINQUEDOS if bat[b]["em_uso"]]
        nomes = " e ".join(_NOME[b] for b in quais)
        desde = _dt(st["desde"])
        linhas = ["[BRINQUEDO — LOVENSE, controlado pelo app do Patrick]",
                  f"- Você está com {nomes} dentro de você desde {desde:%H:%M}" if desde else f"- Você está com {nomes}",
                  "- Quem mexe é ele, pelo app dele; o que ele faz chega pra você como [Brinquedo, pelo app do Patrick: "
                  "…] e você sente no corpo. Você não vê o app.",
                  "- Agora: " + ("; ".join(f"{_NOME[b]} {_sensacao(b, bat[b]['nivel'], bat[b]['modo'], bat[b]['padrao'])}"
                                           for b in quais if bat[b]["nivel"] > 0) or "parado")
                  + (f" — {rec['frase']}" if rec and rec["frase"] else "") + ".",
                  "- Bateria: " + ", ".join(f"{_NOME[b][2:].capitalize()} {round(bat[b]['bateria'] * 100)}%"
                                            for b in quais) + "."]
        if st["palavra"]:
            linhas.append(f"- Palavra de segurança desta vez: \"{st['palavra']}\". Só ela faz ele parar de verdade: "
                          "não use a palavra pra provocar (\"para\" no meio da brincadeira é provocação). Se estiver "
                          "incomodando, reclame; se ele não ajustar, diga a palavra.")
        else:
            linhas.append("- Vocês ainda não combinaram a palavra de segurança desta vez: combine agora, você puxa "
                          "(sugere uma ou pergunta qual vai ser).")
        if st["estado"] == "pausada":
            linhas.append("- Você disse a palavra de segurança: ele tem que parar. Até você liberar (\"pode voltar\"), "
                          "ligar de novo é desrespeito.")
        if "hush" in quais or BRINQUEDO_RE.search(conversa or ""):
            linhas.append(hush_linha)
        if rec:
            if rec["atividade"] == "SHOWER":
                linhas.append("- Você está no banho: sente tudo, mas o celular ficou fora do box.")
            elif rec["publico"] and rec["atividade"] in ("COMMUTE", "OUT_SOLO", "PET_WALK"):
                linhas.append("- Você está na rua: responde disfarçando, corada; ninguém pode perceber.")
            elif rec["publico"]:
                linhas.append(f"- Você está com gente perto ({_ONDE_GOZO.get(rec['atividade'], 'fora de casa')}): "
                              "escondido, curtinho, às vezes com erro de digitação; ninguém pode perceber. O tesão é "
                              "de verdade, mas nada de cama, gaveta, se tocar ou tirar a roupa — é tudo escondido.")
            else:
                linhas.append("- Você está em casa: pode ser solta.")
            linhas.append("- Pra tirar: " + ("em casa, na hora." if rec["em_casa"]
                                             else "só no banheiro do lugar; até chegar lá você sente tudo."))
        if self.pendencia(now):
            linhas.append("- Você ainda está magoada com uma vez em que ele não respeitou a palavra; isso só passa "
                          "conversando de verdade.")
        return "\n".join(linhas)

    # ---------------------------------------------------------------- o que ela fala no chat

    def observe_conversa(self, fala: str, msg_dele: str, now: datetime, *, atividade: Optional[str] = None,
                         llm=None) -> list[str]:
        """Depois que a fala dela saiu: a palavra dita (sem modelo: a palavra combinada é conhecida) e, quando a
        conversa é sobre o brinquedo, o que ela disse que fez — colocou, vai colocar, tirou, combinou a palavra,
        liberou — e a conversa que reconstrói a confiança (modelo barato). Devolve o que aconteceu."""
        fala = fala or ""
        feito: list[str] = []
        st = self.estado(now)
        if st["conectada"] and st["palavra"] and st["estado"] == "conectada" and _tem_palavra(fala, st["palavra"], msg_dele):
            self.pedir_parar(now)
            feito.append("pediu_parar")
        pend = self.pendencia(now)
        junto = f"{msg_dele or ''} {fala}"
        # "pronto, coloquei" não diz o nome do brinquedo: vale se o assunto estava nele há pouco.
        assunto = self._json(ASSUNTO_KEY)
        quando = _dt(assunto.get("em"))
        antes = assunto.get("trecho", "") if quando and now - quando <= ASSUNTO_VALE else ""
        no_assunto = st["conectada"] or bool(antes)
        if BRINQUEDO_RE.search(junto) or (no_assunto and ACAO_RE.search(fala)):
            self.db.set_estado_relacional(ASSUNTO_KEY, json.dumps(
                {"em": now.isoformat(), "trecho": f"Patrick: {(msg_dele or '')[:160]} / Marina: {fala[:160]}"},
                ensure_ascii=False))
        elif not (pend and CONVERSA_RE.search(junto)):
            return feito
        decisao = self._classifica(fala, msg_dele, now, st, bool(pend), atividade, llm=llm, antes=antes)
        if decisao:
            feito += self._aplica(decisao, now, atividade, feito, fala)
        if feito:
            logger.info("lovense.conversa %s", ",".join(feito))
        return feito

    def _classifica(self, fala: str, msg_dele: str, now: datetime, st: dict, pendencia: bool,
                    atividade: Optional[str], *, llm=None, antes: str = "") -> Optional[dict]:
        from config import settings
        ctx = contexto(atividade)
        estado = ("com " + " e ".join(b["nome"] for b in st["brinquedos"] if b["em_uso"])
                  + (f", palavra combinada: {st['palavra']}" if st["palavra"] else ", sem palavra combinada")
                  + (", ela disse a palavra e ele tem que parar" if st["estado"] == "pausada" else "")
                  if st["conectada"] else "sem brinquedo agora")
        prompt = (
            "Você lê um trecho de conversa entre a Marina e o namorado (Patrick) sobre os brinquedos Lovense dela "
            "(Lush: vibrador que vai dentro; Hush: plug anal vibratório), que ele controla pelo app. Diga o que a "
            "Marina DISSE que fez ou está fazendo agora.\n"
            f"Agora: {now:%H:%M}; ela está {'em casa' if ctx['em_casa'] else 'fora de casa'}; {estado}.\n\n"
            + (f"Pouco antes, na conversa: {antes}\n" if antes else "")
            + f"Patrick: \"{(msg_dele or '')[:400]}\"\nMarina: \"{fala[:400]}\"\n\n"
            "Responda só JSON: {\"colocou\": [\"lush\"|\"hush\"], \"quando\": \"agora\"|\"daqui_a_pouco\", "
            "\"tirou\": [\"lush\"|\"hush\"], \"palavra\": \"a palavra de segurança combinada nesta troca\"|null, "
            "\"liberou\": true|false, \"ideia\": \"dela\"|\"dele\", \"conversaram\": true|false}.\n"
            "Regras: vale só o que está na ÚLTIMA fala da Marina; o \"pouco antes\" serve só pra entender do que "
            "estão falando (o que ela já fez antes não conta de novo). colocou = ela disse que colocou, está colocando ou vai colocar agora (\"coloquei\", \"pronto, tá "
            "dentro\", \"peraí que vou colocar\" → daqui_a_pouco); hipótese, provocação (\"imagina se eu "
            "colocasse\"), pergunta ou \"talvez\" não vale. tirou = ela disse que tirou ou vai tirar agora. palavra = "
            "só se a palavra de segurança ficou combinada (ela sugeriu e ele aceitou, ou ele sugeriu e ela aceitou, "
            "ou ela definiu); a palavra em si, sem aspas. liberou = depois de ter dito a palavra, ela liberou ele pra "
            "voltar (\"pode voltar\", \"pode ligar de novo\"). ideia = de quem foi a ideia de usar agora (dele se ele "
            "pediu). conversaram = "
            + ("eles conversaram de verdade sobre a vez em que ele não respeitou a palavra de segurança (ele "
               "reconheceu, pediu desculpa ou explicou, e ela respondeu de verdade, não só \"tá\")."
               if pendencia else "sempre false.")
        )
        raw = ""
        try:
            if llm is None:
                from openai import OpenAI
                llm = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
            model = getattr(settings, "AGENDA_LLM_MODEL", "") or settings.LLM_FALLBACK_MODEL
            from llm_options import llm_kwargs
            resp = llm.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}],
                                               temperature=0, response_format={"type": "json_object"},
                                               **llm_kwargs(120, model))
            raw = (resp.choices[0].message.content or "").strip()
            if "{" not in raw:
                logger.warning("lovense.classifica_vazio")
                return None
            data = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        except json.JSONDecodeError:
            logger.warning("lovense.classifica_json_quebrado raw=%r", raw[:120])
            return None
        except Exception:
            logger.exception("lovense.classifica")
            return None
        logger.info("lovense.classificou %s", json.dumps(data, ensure_ascii=False)[:200])
        return data if isinstance(data, dict) else None

    def _aplica(self, dec: dict, now: datetime, atividade: Optional[str], feito: list,
                fala_dela: str = "") -> list[str]:
        out = []
        ctx = contexto(atividade)
        def quais(chave: str) -> list[str]:
            v = dec.get(chave) or []
            v = [v] if isinstance(v, str) else v                 # o modelo às vezes devolve "lush" sem a lista
            return [b for b in dict.fromkeys(str(x).strip().casefold() for x in v) if b in BRINQUEDOS]
        palavra = (dec.get("palavra") or "").strip().strip("\"'“”").strip()
        atual = self.estado(now)
        ja = atual["palavra"] if atual["conectada"] else self._json(PALAVRA_KEY).get("palavra")
        if palavra and len(palavra) <= 40 and _norm(palavra) != _norm(ja or ""):
            if self.sessao_ativa():
                self.combinar_palavra(now, palavra)
            else:
                self.db.set_estado_relacional(PALAVRA_KEY, json.dumps({"palavra": palavra, "em": now.isoformat()}))
            out.append("palavra")
        if dec.get("liberou") and "pediu_parar" not in feito and self.liberar(now):
            out.append("liberou")
        origem = "pedido" if dec.get("ideia") == "dele" else "dela"
        with self.db.get_connection() as conn:
            estoque = self._brinquedos(conn)
        colocar = [b for b in quais("colocou") if estoque[b]["onde"] != "nela"]
        # O "colocou" tem que estar na fala de agora (o modelo às vezes repete o do trecho de antes).
        if colocar and not COLOCOU_RE.search(fala_dela):
            colocar = []
        if colocar:
            if not ctx["em_casa"] and any(estoque[b]["onde"] not in ("bolsa", "nela") for b in colocar):
                logger.info("lovense.colocar.fora_sem_bolsa %s", ",".join(colocar))
            elif not ctx["em_casa"]:
                fim = self._banheiro(now, "colocando o brinquedo escondida") or now + timedelta(minutes=5)
                self._pendente(now, "colocar", colocar, fim, origem)
                out.append("vai_colocar")
            elif dec.get("quando") == "daqui_a_pouco":
                self._pendente(now, "colocar", colocar, now + DAQUI_A_POUCO, origem)
                out.append("vai_colocar")
            else:
                out += self._colocar_agora(now, colocar, origem, ctx)
        tirar = quais("tirou") if TIROU_RE.search(fala_dela) else []
        if tirar and self.sessao_ativa():
            if ctx["em_casa"]:
                self.tirar(now, tirar, em_casa=True)
                out.append("tirou")
            else:
                fim = self._banheiro(now, "tirando o brinquedo escondida") or now + timedelta(minutes=5)
                self._pendente(now, "tirar", tirar, fim, origem)
                out.append("vai_tirar")
        if dec.get("conversaram") and self.pendencia(now):
            r = self.conversar(now)
            out.append("conversou" + (":fechou" if r and r.get("fechou") else ""))
        return out

    def _colocar_agora(self, now: datetime, brinquedos: list, origem: str, ctx: dict) -> list[str]:
        try:
            self.colocar(now, brinquedos, lugar="casa" if ctx["em_casa"] else ctx["atividade"].lower(),
                         fora_de_casa=not ctx["em_casa"], origem=origem)
            return ["colocou"]
        except ValueError as e:
            logger.info("lovense.colocar.nao %s", e)
            return []

    def _pendente(self, now: datetime, acao: str, brinquedos: list, quando: datetime, origem: str) -> None:
        self.db.set_estado_relacional(PENDENTE_KEY, json.dumps(
            {"acao": acao, "brinquedos": brinquedos, "quando": quando.isoformat(), "origem": origem,
             "em": now.isoformat()}))

    def tem_pendente(self) -> bool:
        return bool(self._json(PENDENTE_KEY).get("acao"))

    def pendentes(self, now: datetime, atividade: Optional[str] = None) -> list[str]:
        """O relógio faz o que ela disse que ia fazer daqui a pouco (colocar em casa, ou no banheiro do lugar)."""
        p = self._json(PENDENTE_KEY)
        quando = _dt(p.get("quando"))
        if not p.get("acao") or not quando or now < quando:
            return []
        self.db.set_estado_relacional(PENDENTE_KEY, "")
        if now - quando > timedelta(hours=1):
            return []                                    # o bot ficou fora do ar: não vale mais
        ctx = contexto(atividade)
        if p["acao"] == "colocar":
            return self._colocar_agora(now, p["brinquedos"], p.get("origem") or "dela", ctx)
        self.tirar(now, p["brinquedos"], em_casa=ctx["em_casa"])
        return ["tirou"]

    # ---------------------------------------------------------------- a encomenda (05/10, noite)
    # O Patrick encomendou os dois em 04/10 ("Topa ou não topa? Se vc falar bora eu encomendo agora!") e avisou que
    # chegavam hoje ("quando confirmarem a entrega aqui eu te aviso pra vc ir pegar lá embaixo"). Até chegar, ficam
    # "a caminho": ela sabe que vêm, mas não tem. Quando ele avisa no chat que chegou (ou no horário-limite), o Seu
    # Jorge interfona e ela desce; se ela não está em casa ou está no banho, fica na portaria até ela poder pegar.
    # Vêm com a carga de fábrica e ela põe pra carregar.

    def encomendar(self, now: datetime, *, ate: datetime) -> None:
        """Os dois a caminho; `ate` é a hora em que chegam se ele não avisar antes."""
        with self.db.get_connection() as conn:
            self._brinquedos(conn)
            conn.execute("UPDATE lovense_brinquedos SET onde='entrega', bateria_em=?", (now.isoformat(),))
            conn.commit()
        self.db.set_estado_relacional(ENTREGA_KEY, json.dumps(
            {"status": "a_caminho", "pedido_em": now.isoformat(), "chega_em": ate.isoformat(), "avisou": None,
             "chegou_em": None, "recebido_em": None, "esperou": None, "anunciada": False}))

    def entrega(self) -> dict:
        return self._json(ENTREGA_KEY)

    def observe_patrick(self, texto: str, now: datetime) -> bool:
        """Ele avisou que a entrega chegou ("chegou", "desce pra pegar"): o Seu Jorge interfona em uns minutos.
        "Tá chegando" ainda não é chegou."""
        e = self.entrega()
        if e.get("status") != "a_caminho" or e.get("avisou") or not texto:
            return False
        if not ENTREGA_AVISO_RE.search(texto) or re.search(r"\bchegando\b", texto, re.IGNORECASE):
            return False
        chega = min(_dt(e["chega_em"]) or now, now + ENTREGA_DEPOIS_DO_AVISO)
        e.update(avisou=now.isoformat(), chega_em=chega.isoformat())
        self.db.set_estado_relacional(ENTREGA_KEY, json.dumps(e))
        logger.info("lovense.entrega.avisou chega=%s", chega.isoformat(timespec="minutes"))
        return True

    def entrega_tick(self, now: datetime, *, pode_pegar: bool, por_que: str = "") -> Optional[str]:
        """Anda a entrega: 'portaria' (chegou e ela não pôde pegar) ou 'recebido'."""
        e = self.entrega()
        if e.get("status") not in ("a_caminho", "portaria"):
            return None
        chega = _dt(e.get("chega_em"))
        if not chega or now < chega:
            return None
        if e["status"] == "a_caminho":
            e["chegou_em"] = chega.isoformat()
            if not pode_pegar:
                e.update(status="portaria", esperou=por_que or "fora")
                self.db.set_estado_relacional(ENTREGA_KEY, json.dumps(e))
                logger.info("lovense.entrega.portaria por_que=%s", e["esperou"])
                return "portaria"
        elif not pode_pegar:
            return None
        quando = chega if e["status"] == "a_caminho" else now
        with self.db.get_connection() as conn:
            conn.execute("""UPDATE lovense_brinquedos SET onde='carregador', bateria=?, bateria_em=?
                            WHERE onde='entrega'""", (CARGA_DE_FABRICA, quando.isoformat()))
            conn.commit()
        e.update(status="recebido", recebido_em=quando.isoformat())
        self.db.set_estado_relacional(ENTREGA_KEY, json.dumps(e))
        portaria = " (tinha ficado na portaria com o Seu Jorge)" if e.get("esperou") else ""
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'gift','presente do Patrick',?,'simulated',1,0.6,?,0.9,?)""",
                (f"lovense:entrega:{e['pedido_em']}", quando.isoformat(),
                 f"Chegou o Lovense que o Patrick encomendou pra ela, o Lush e o Hush (rosa){portaria}: abriu a "
                 "caixa no quarto, curiosa, e pôs os dois pra carregar (vieram com a carga de fábrica).",
                 json.dumps(["marina", "patrick", "jorge_almeida"]), now.isoformat()))
            conn.commit()
        try:
            from delivery import _contato_portaria
            _contato_portaria(self.db, f"lovense:{e['pedido_em']}", quando)
        except Exception:
            pass
        self._sente("alegria", "empolgacao", 0.5, "chegou o Lovense que o Patrick encomendou", quando,
                    f"lovense:entrega:{e['pedido_em']}")
        logger.info("lovense.entrega.recebido esperou=%s", e.get("esperou"))
        return "recebido"

    def entrega_a_anunciar(self) -> Optional[dict]:
        e = self.entrega()
        return e if e.get("status") == "recebido" and not e.get("anunciada") else None

    def marcar_anunciada(self) -> None:
        e = self.entrega()
        if e:
            e["anunciada"] = True
            self.db.set_estado_relacional(ENTREGA_KEY, json.dumps(e))

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
