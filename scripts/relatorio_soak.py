"""Relatório diário do soak (FRENTES_MARINA.md, seção 0) — roda sozinho na VPS às 05:10.

Cobre o dia dela, das 05:00 às 05:00 do dia seguinte, e grava em `soak/dia-AAAA-MM-DD.md`
(fica na VPS, como o banco). Quem lê é o Claude, na conversa "bora no soak, dia N": o script
junta tudo e aponta suspeitas; a palavra final sobre o que é bug é de quem lê.

Trabalha numa CÓPIA do banco em /tmp (nunca grava na produção) e não paga API nenhuma: sem rotas
ao vivo (commute.BOT_VIVO fica desligado fora do bot) e sem LLM (as chaves são apagadas depois de
ler o gasto do OpenRouter).

    venv/bin/python scripts/relatorio_soak.py                 # o último dia fechado
    venv/bin/python scripts/relatorio_soak.py --dia 2026-09-28
    venv/bin/python scripts/relatorio_soak.py --dia 2026-09-28 --out /tmp/x.md --sem-custos
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata
import urllib.request
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("MARINA_ROOT") or Path(__file__).resolve().parents[1])
SOAK_DIR = ROOT / "soak"
LOGS = [ROOT / "logs" / "marina.log.1", ROOT / "logs" / "marina.log"]
VIRADA = time(5, 0)          # o dia dela vira às 5h (decidido com o Patrick, 28/09)
TOLERANCIA = timedelta(minutes=15)   # fala × mundo: o estado de até 15 min antes/depois também vale
DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


# ------------------------------------------------------------------ util --
def _dt(s: str) -> datetime:
    return datetime.fromisoformat(str(s)[:26])


def _hm(at: datetime) -> str:
    return at.strftime("%H:%M")


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def _curto(s: str, n: int = 220) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _dia_padrao(now: datetime) -> date:
    """O último dia fechado: às 05:10 de terça, é segunda."""
    return (now - timedelta(hours=VIRADA.hour)).date() - timedelta(days=1)


def _copiar_banco(origem: Path) -> Path:
    destino = Path(tempfile.gettempdir()) / f"marina_soak_{os.getpid()}.db"
    src = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)
    dst = sqlite3.connect(destino)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    return destino


# ------------------------------------------------------ mundo × fala --
def situacao(activity: str, region: str) -> str:
    """Classe do estado do mundo: casa | arrumando | banho | dormindo | caminho | aula | academia | fora | rua."""
    a = _sem_acento(activity or "")
    r = _sem_acento(region or "")
    if r.startswith("a caminho") or a.startswith(("indo ", "voltando ")):
        return "caminho"
    if a.startswith("dormindo"):
        return "dormindo"
    if "banho" in a and not a.startswith("se arrumando pra sair"):
        return "banho"
    if a.startswith("se arrumando"):
        return "arrumando"
    if "faculdade" in a or a.startswith("na puc"):
        return "aula"
    if "academia" in a or "treinando" in a:
        return "academia"
    if "rapidinho" in a:
        return "casa"          # soak, dia 4 (02/10, 23:14): "passeio rapidinho com o Milo" é na calçada do prédio
    if "passeando com" in a:
        return "rua"
    # soak, dia 2 (30/09, 05:21 e 06:16): "acabou de acordar, ainda de pijama" é em casa (não card vazio nem teleporte)
    if "em casa" in a or "sofa" in a or "que o patrick mandou" in a or a.startswith(
            ("acordando", "acabou de acordar", "tempo livre")):
        return "casa"
    return "fora"


# Lugar que ela diz que está → palavras que o texto do mundo precisa ter.
LUGARES = {
    "puc": ("puc", "faculdade"), "faculdade": ("puc", "faculdade"), "aula": ("puc", "faculdade", "aula"),
    "academia": ("academia", "bodytech", "treinando"), "bodytech": ("academia", "bodytech", "treinando"),
    "shopping": ("shopping",), "bar": ("bar",), "quartinho": ("quartinho",), "starbucks": ("starbucks",),
    "mercado": ("mercado", "zona sul", "hortifruti", "supermercado"), "farmacia": ("farmacia", "drogaria", "pacheco"),
    "drogaria": ("farmacia", "drogaria", "pacheco"), "cinema": ("cinema",), "praia": ("praia", "enseada", "orla"),
    "orla": ("praia", "enseada", "orla"), "salao": ("salao", "ophicina"), "medico": ("medico", "consulta", "clinica"),
}
_EU = r"(?:t[oô]|to|estou|j[aá] t[oô]|t[oô] aqui|aqui)"
RE_CASA = re.compile(rf"\b(?:{_EU}\s+(?:aqui\s+)?em casa|cheguei em casa|{_EU}\s+(?:no sof[aá]|na cama|deitad[ao]))\b")
RE_CAMINHO = re.compile(
    rf"\b(?:{_EU}\s+(?:no|dentro do)\s+(?:uber|[oô]nibus|metr[oô])|"
    rf"{_EU}\s+(?:indo|voltando)\s+(?:pra|pro|pa|p/|na|no)\b(?!\s*(?:banho|cama|cozinha|quarto|sala|dormir|casa\b)))")
RE_FORA = re.compile(rf"\b(?:{_EU}|cheguei)\s+(?:aqui\s+)?(?:na|no|em)\s+([a-zà-ú]+)")
RE_BANHO = re.compile(rf"\b{_EU}\s+(?:no|tomando)\s+banho\b")
COMPATIVEL = {
    "casa": {"casa", "arrumando", "banho", "dormindo"},
    "caminho": {"caminho"},
    "banho": {"banho"},
}


def alegacoes(texto: str) -> list[tuple[str, str, tuple]]:
    """O que ela afirma sobre onde está / o que está fazendo AGORA: [(classe, trecho, palavras do lugar)]."""
    t = (texto or "").lower()
    achou = []
    for rx, classe in ((RE_CASA, "casa"), (RE_CAMINHO, "caminho"), (RE_BANHO, "banho")):
        m = rx.search(t)
        if m:
            achou.append((classe, m.group(0), ()))
    for m in RE_FORA.finditer(t):
        chave = _sem_acento(m.group(1))
        if chave in LUGARES:
            achou.append(("fora", m.group(0), LUGARES[chave]))
    return achou


# "tô organizando uns looks aqui" com o mundo na praia com o Milo (28/09, 17:24): o que ela diz que está FAZENDO.
RE_GERUNDIO = re.compile(rf"\b{_EU}\s+(?:aqui\s+)?(?:me\s+)?([a-zà-ú]+ndo)\b")
FAZER_EM_CASA = {"organizando", "montando", "desenhando", "cozinhando", "lavando", "assistindo", "maratonando",
                 "jogando", "costurando", "limpando", "dobrando", "arrumando", "deitando", "cochilando", "descansando"}
FAZER_FORA = {"treinando", "malhando", "passeando", "caminhando", "correndo", "dirigindo", "pedalando", "nadando"}
PISTA_CASA = re.compile(r"\b(?:no sof[aá]|na cama|no quarto|na sala|no closet|deitad[ao]|aqui em casa)\b")
FIGURADO = re.compile(r"\s+com (?:voc[eê]|vc|tu)\b")   # ele está longe: "treinando com você" não é academia
FUTURO = re.compile(r"\b(?:vou|quando (?:eu )?chegar|chegando|daqui a pouco|mais tarde|depois|antes de)\b[^.!?]{0,30}$")
FORA_DE_CASA = {"fora", "rua", "caminho", "aula", "academia"}


# Soak, dia 1 (29/09): "tô terminando umas referências do trabalho" passeando com o Milo e "termino esse trabalho e
# fico com você" fazendo as unhas na Ophicina. Trabalho da faculdade é em casa ou na PUC.
RE_TRABALHO = re.compile(r"\b(?:(?:terminando|fazendo|finalizando|adiantando|montando)\b[^.!?\n]{0,40}\btrabalho"
                         r"|termino (?:esse|o|meu) trabalho|tô na reta final|to na reta final)")
SEM_ESTUDO = {"fora", "rua", "caminho", "academia"}


# Soak, dia 4 (02/10, 23:26): "Tô aqui, amor. Se divertindo ainda" em casa desde 23:06.
RE_AINDA_NO_ROLE = re.compile(r"\b(?:se divertindo|curtindo o rol[eê]|ainda no rol[eê]|ainda (?:no|na) (?:bar|festa|"
                              r"show|balada))\b")
EM_CASA = {"casa", "banho", "dormindo", "arrumando"}


def atividade_contradiz(texto: str, estados: list[dict]) -> str:
    """Trecho da fala quando o que ela diz que está fazendo não cabe em nenhum estado perto daquela hora."""
    t = (texto or "").lower()
    sits = {e["sit"] for e in estados}
    m = RE_AINDA_NO_ROLE.search(t)
    if m and sits and sits <= EM_CASA:
        return m.group(0)
    m = RE_TRABALHO.search(t)
    if m and sits and sits <= SEM_ESTUDO:
        return m.group(0)
    for m in RE_GERUNDIO.finditer(t):
        verbo = _sem_acento(m.group(1))
        if verbo in FAZER_EM_CASA and sits <= FORA_DE_CASA:
            return m.group(0)
        if verbo in FAZER_FORA and FIGURADO.match(t, m.end()):
            continue                                   # soak, dia 2 (15:14): "tô treinando com você" (receber elogio)
        if verbo in FAZER_FORA and not (sits & FORA_DE_CASA) and not any(
                verbo[:5] in _sem_acento(e["activity"] or "") for e in estados):
            return m.group(0)
    m = PISTA_CASA.search(t)
    if m and sits <= FORA_DE_CASA and not FUTURO.search(t[: m.start()]):
        return m.group(0)
    return ""


# O que ela diz que FEZ no dia × o que o mundo registrou até aquela hora (comida é bug grave, seção 0).
PASSADO = [
    ("Milo", re.compile(r"\b(?:desci|sa[ií]|passeei|levei)\s+(?:rapidinho\s+)?(?:com\s+)?o milo\b"), ("milo",)),
    ("academia", re.compile(r"\b(?:treinei|malhei|fui (?:na|pra) academia|voltei da academia|sa[ií] da academia)\b"),
     ("academia", "bodytech", "treino", "treinando")),
    ("banho", re.compile(r"\b(?:tomei banho|sa[ií] do banho)\b"), ("banho",)),
    ("almoço", re.compile(r"\balmocei\b"), ("almoco", "almocou", "almocando")),
    ("jantar", re.compile(r"\bjantei\b"), ("jantar", "jantou", "jantando")),
]
RE_BANHO_FEITO = re.compile(r"\b(?:banho tomado|j[aá] tomei banho|tomei banho|j[aá] sim[^.!?\n]{0,20}banho)\b")
RE_COMI = re.compile(r"\b(?:comi|comendo|tomei|pedi)\s+(?:um|uma|uns|umas|o|a)\s+([a-zà-ú]{4,})")


def feito_extra(db, eventos: list[dict], at: datetime) -> list[str]:
    """Soak, dia 3 (01/10): dois alarmes falsos. «Tomei um Buscopan» (05:31) — o remédio da cólica vem da saúde, não
    de um acontecimento; «jantei» (22:39) — a tigela que o Patrick mandou às 19:08 foi o jantar, mas o acontecimento
    se chama "presente do Patrick"."""
    extra = []
    for ev in eventos:
        quando = _dt(ev["event_at"])
        if ev.get("event_type") == "meal" and quando <= at and quando.hour >= 17:
            extra.append("jantar")
    try:
        from health import Health
        extra += [c.remedy for c in Health(db).conditions(at)]
    except Exception:
        pass
    return extra


def fez_contradiz(texto: str, feito: str) -> list[str]:
    """`feito`: acontecimentos e estados do mundo do dia até a hora da fala, sem acento."""
    t = (texto or "").lower()
    achou = []
    for rotulo, rx, provas in PASSADO:
        m = rx.search(t)
        if m and not any(p in feito for p in provas):
            achou.append(f"«{m.group(0)}» ({rotulo} não aparece no mundo até ali)")
    if re.search(r"pulei o caf[eé]|n[aã]o tomei caf[eé]", t) and "tomou cafe" in feito:
        achou.append("«pulei o café» (o mundo diz que ela tomou)")
    for m in RE_COMI.finditer(t):
        comida = _sem_acento(m.group(1))
        if comida[:5] not in feito and comida not in ("coisa", "coisinha", "besteira", "pouco", "pouquinho"):
            achou.append(f"«{m.group(0)}» ({comida} não aparece no mundo até ali)")
    return achou


def contradiz(classe: str, palavras: tuple, estados: list[dict]) -> bool:
    """True quando nenhum estado do mundo perto daquela hora combina com o que ela disse."""
    for e in estados:
        sit, act = e["sit"], _sem_acento(e["activity"] or "")
        if classe == "fora":
            if sit in ("fora", "aula", "academia", "caminho", "rua") and any(p in act for p in palavras):
                return False
        elif classe == "caminho":
            if sit == "caminho" or (sit == "arrumando" and ("saindo" in act or "chamando" in act)):
                return False
        elif sit in COMPATIVEL.get(classe, ()):
            return False
    return True


# ----------------------------------------------------- fala quebrada --
QUEBRAS = [
    ("número sem a parte inteira", re.compile(r"(?:^|[\s(])[,.]\d")),
    ("R$ sem valor", re.compile(r"R\$\s*(?!\d)")),
    ("hora sem número", re.compile(r"\b(?:às|as)\s+h\b", re.I)),
    ("resto de código", re.compile(r"\{[^}]{0,40}\}|\bNone\b|\bnull\b|\[[A-Z_ ]{4,}\]|<[a-z_]{3,}>|\bundefined\b")),
    ("letra de outro alfabeto", re.compile(r"[\u0400-\u04FF\u0600-\u06FF\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]")),
    ("palavra repetida colada", re.compile(r"\b([a-zà-ú]{3,})\s+\1\b", re.I)),
]
# Soak, dia 1 (29/09, 05:36): a resposta adiada da madrugada saiu de manhã com "Boa noite".
SAUDACAO_FORA_DE_HORA = (("boa noite", range(5, 12)), ("bom dia", range(14, 24)))


def saudacao_fora_de_hora(texto: str, at: datetime) -> str:
    t = (texto or "").lower()
    return next((s for s, horas in SAUDACAO_FORA_DE_HORA if at.hour in horas and re.search(rf"\b{s}\b", t)), "")
ROUPA_PALAVRAS = ("vestido", "saia", "calça", "calca", "short", "shorts", "top", "cropped", "camiseta", "blusa",
                  "moletom", "pijama", "lingerie", "biquíni", "biquini", "legging", "jaqueta", "camisola",
                  "sutiã", "sutia", "calcinha", "body", "regata", "jeans", "macacão", "macacao", "suéter", "sueter")


def quebras(texto: str) -> list[str]:
    achou = []
    for nome, rx in QUEBRAS:
        m = rx.search(texto or "")
        if m and not (nome == "palavra repetida colada" and m.group(1).lower().startswith("k")):
            achou.append(f"{nome} («{_curto(m.group(0), 40)}»)")
    return achou


# --------------------------------------------- o Patrick estranhou --
# Soak, dia 4 (02/10): três problemas do dia só apareceram porque ele estranhou. Fala dele com cara de "hein?" é
# pista: o relatório mostra o que ela tinha dito e o mundo daquela hora (texto sem acento, minúsculo). "Ué" ficou
# de fora: é muleta dele ("eu gosto ué", "então fica ué" — 4 alarmes falsos em 02/10).
RE_ESTRANHOU = re.compile(
    r"\?!|!\?|\?{2,}|\bcomo assim\b|\bn(?:ao)?\s+entendi\b|\boxe\b|\bha\?|\bpera(?:i| ai)\b|"
    r"\b(?:voce|vc) (?:nao )?(?:disse|falou|tinha dito)\b|\b(?:voce|vc) nao (?:tava|estava|ia)\b|"
    r"\beu (?:nao )?(?:disse|falei)\b|\bnao era\b|\bcade\b|\bkd\b|\bnao chegou\b|\bde novo\?|"
    r"\b(?:que )?estranh[oa]\b|\bbug(?:ou|ad[oa])\b|\bconfus[oa]\b|\bnada a ver\b|\bnao faz sentido\b|"
    r"\baqui onde\b|\besquec\w* de (?:me )?avisar\b")     # 02/10, 23:27 e 23:28


def estranhou(texto: str) -> str:
    m = RE_ESTRANHOU.search(_sem_acento(texto or ""))
    return m.group(0) if m else ""


# ----------------------------------------------------------- fotos --
RE_PEDE_FOTO = re.compile(
    r"\b(?:manda|me manda|mande|tira|quero ver|deixa eu ver|me mostra|mostra)\b[^.!?\n]{0,40}"
    r"\b(?:foto|fotinho|fotinha|selfie|nude|nudes|look|unha|unhas|cabelo|mais uma|outra)\b"
    r"|\b(?:cade|kd) (?:a|minha) (?:foto|fotinho)"
    r"|\b(?:quero|deixa eu|me deixa|curios[oa] (?:p|pra|para)) ver\b")    # 02/10, 14:54: "curioso p ver uq tá usando"


def pede_foto(texto: str) -> bool:
    return bool(RE_PEDE_FOTO.search(_sem_acento(texto or "")))


CASA_FOTO = {"casa", "banho", "dormindo", "arrumando"}
RUA_FOTO = {"fora", "aula", "academia", "rua", "caminho"}


def fundo_contradiz(comodo: str, cena: str, estado: dict | None) -> str:
    """Soak, dia 4 (02/10, 15:41): foto dentro do Rei do Mate com «a street in Botafogo» de fundo."""
    if not estado:
        return ""
    sit, act = estado["sit"], _sem_acento(estado["activity"] or "")
    if comodo == "fora" and sit in CASA_FOTO:
        return f"foto na rua («{_curto(cena, 60)}») com o mundo em casa"
    if comodo not in ("fora", "-", "") and sit in RUA_FOTO:
        return f"foto em casa ({comodo}) com o mundo fora"
    if comodo == "fora" and "a street in" in cena.lower() and sit == "fora" and "rua" not in act:
        return f"fundo de rua genérico («{_curto(cena, 60)}») com ela dentro de um lugar"
    return ""


# ------------------------------------------- enviado × histórico --
def _palavras(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _sem_acento(s or ""))


def no_historico(texto: str, falas: list[str]) -> bool:
    """O balão enviado está em alguma fala gravada? (as primeiras palavras dele, com folga de 25%)"""
    chave = [p for p in _palavras(texto) if len(p) > 1][:8]
    if not chave:
        return True
    for f in falas:
        tem = set(_palavras(f))
        if sum(p in tem for p in chave) >= max(1, round(len(chave) * 0.75)):
            return True
    return False


# --------------------------------------------------------------- log --
RE_LINHA = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ - ([^ ]+) - ([A-Z]+) - (.*)$")
RUIDO = ("telegram.error.NetworkError", "telegram.error.TimedOut", "Bad Gateway", "was missed by",
         "maximum number of running instances", "lastfm.fetch_falhou", "Network Retry Loop")
# "No error handlers are registered" saiu daqui (soak, dia 4): é a frase do python-telegram-bot pra QUALQUER exceção
# de handler — o BadRequest da confirmação do /ruim (02/10) caiu em "rede" por causa dela.


def ler_log(ini: datetime, fim: datetime) -> list[dict]:
    """Entradas do log do bot na janela; traceback vem junto da linha que o abriu."""
    entradas: list[dict] = []
    for path in LOGS:
        if not path.exists():
            continue
        atual = None
        with path.open(encoding="utf-8", errors="replace") as fh:
            for linha in fh:
                m = RE_LINHA.match(linha.rstrip("\n"))
                if m:
                    at = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                    atual = {"at": at, "mod": m.group(2), "nivel": m.group(3), "msg": m.group(4), "extra": []}
                    if ini <= at < fim:
                        entradas.append(atual)
                elif atual is not None and linha.strip():
                    atual["extra"].append(linha.rstrip("\n"))
    entradas.sort(key=lambda e: e["at"])
    return entradas


def _excecao(e: dict) -> str:
    fim = [x for x in e["extra"] if x and not x.startswith(" ")]
    return fim[-1] if fim else ""


# ------------------------------------------------------------ custos --
def gasto_openrouter(settings, dia: date, salvar: bool) -> dict:
    """Gasto do LLM pelo acumulado do OpenRouter: foto do acumulado a cada relatório, diferença entre dias."""
    try:
        req = urllib.request.Request("https://openrouter.ai/api/v1/credits",
                                     headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            d = json.loads(resp.read().decode("utf-8"))["data"]
        usado, total = float(d["total_usage"]), float(d["total_credits"])
    except Exception as exc:
        return {"erro": type(exc).__name__}
    fotos_path = SOAK_DIR / ".openrouter.json"
    try:
        fotos = json.loads(fotos_path.read_text(encoding="utf-8"))
    except Exception:
        fotos = {}
    chave = dia.isoformat()
    if salvar and chave not in fotos:      # rodar de novo no mesmo dia não mexe na conta
        fotos[chave] = usado
        fotos_path.write_text(json.dumps(fotos, indent=1, sort_keys=True), encoding="utf-8")
    anterior = fotos.get((dia - timedelta(days=1)).isoformat())
    agora = fotos.get(chave, usado)
    return {"dia": (agora - anterior) if anterior is not None else None, "saldo": total - usado}


# -------------------------------------------------------------- main --
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dia", type=date.fromisoformat, default=None)
    ap.add_argument("--db", type=Path, default=ROOT / "marin_memory.db")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--sem-custos", action="store_true", help="não consulta o OpenRouter nem grava a foto do gasto")
    args = ap.parse_args()

    dia = args.dia or _dia_padrao(datetime.now())
    ini = datetime.combine(dia, VIRADA)
    fim = ini + timedelta(days=1)
    SOAK_DIR.mkdir(exist_ok=True)
    out = args.out or SOAK_DIR / f"dia-{dia.isoformat()}.md"

    copia = _copiar_banco(args.db)
    os.environ["MARINA_DB_PATH"] = str(copia)       # antes de importar o projeto: o db_manager global vai pra cópia
    os.environ["COMMUTE_LIVE_TIMES"] = "false"
    sys.path.insert(0, str(ROOT))
    try:
        return _relatorio(dia, ini, fim, copia, out, args.sem_custos)
    finally:
        for sufixo in ("", "-wal", "-shm"):
            try:
                Path(str(copia) + sufixo).unlink()
            except OSError:
                pass


def _relatorio(dia: date, ini: datetime, fim: datetime, copia: Path, out: Path, sem_custos: bool) -> int:
    from config import settings
    custo_llm = {} if sem_custos else gasto_openrouter(settings, dia, salvar=True)
    for nome in ("LLM_API_KEY", "DISTANCE_MATRIX_KEY", "CIVITAI_API_KEY", "NOVITA_API_KEY", "ELEVENLABS_API_KEY",
                 "GEMINI_API_KEY", "TMDB_API_KEY"):
        if hasattr(settings, nome):
            setattr(settings, nome, "")              # daqui pra frente nada pago, nem por engano
    from db import DatabaseManager
    db = DatabaseManager(copia)

    conn = sqlite3.connect(copia)
    conn.row_factory = sqlite3.Row
    s_ini, s_fim = ini.isoformat(), fim.isoformat()
    msgs = [dict(r) for r in conn.execute(
        "SELECT id, timestamp, role, content, is_initiative, media_type FROM conversas "
        "WHERE timestamp >= ? AND timestamp < ? ORDER BY id", (s_ini, s_fim))]
    for m in msgs:
        m["at"] = _dt(m["timestamp"])
    mundo = [dict(r) for r in conn.execute(
        "SELECT observed_at, activity, location_region FROM world_state WHERE observed_at < ? "
        "AND observed_at >= (SELECT COALESCE(MAX(observed_at), '') FROM world_state WHERE observed_at < ?) "
        "ORDER BY observed_at, id", (s_fim, s_ini))]
    for w in mundo:
        w["at"] = _dt(w["observed_at"])
        w["sit"] = situacao(w["activity"], w["location_region"])
    eventos = [dict(r) for r in conn.execute(
        "SELECT event_at, end_at, event_type, title, summary FROM life_events WHERE event_at >= ? AND event_at < ? "
        "ORDER BY event_at", (s_ini, s_fim))]
    try:
        posts = [dict(r) for r in conn.execute(
            "SELECT criado_em, tipo, motivo, local, legenda, roupa, descricao FROM ig_posts "
            "WHERE autor='marina' AND criado_em >= ? AND criado_em < ? ORDER BY criado_em", (s_ini, s_fim))]
    except sqlite3.Error:
        posts = []

    def estado_em(at: datetime) -> dict | None:
        antes = [w for w in mundo if w["at"] <= at]
        return antes[-1] if antes else None

    def estados_perto(at: datetime) -> list[dict]:
        base = estado_em(at)
        perto = [w for w in mundo if at - TOLERANCIA <= w["at"] <= at + TOLERANCIA]
        return ([base] if base else []) + perto

    # --- suspeitas ---------------------------------------------------------
    s_lugar, s_card, s_quebra, s_foto, s_ordem = [], [], [], [], []
    from agenda import Agenda
    agenda = Agenda(db)

    def etapa_em(at: datetime):
        try:
            return agenda.agora(at)
        except Exception as exc:
            return exc

    marina = [m for m in msgs if m["role"] == "assistant"]
    s_fez = []
    for m in marina:
        perto = estados_perto(m["at"])
        e = estado_em(m["at"]) or (perto[0] if perto else None)
        trechos = [trecho for classe, trecho, palavras in alegacoes(m["content"])
                   if perto and contradiz(classe, palavras, perto)]
        if perto and not trechos and (t := atividade_contradiz(m["content"], perto)):
            trechos.append(t)
        for trecho in trechos:
            s_lugar.append(f"**{_hm(m['at'])}** ela: «{_curto(trecho, 60)}» → mundo: {e['activity']} "
                           f"({e['location_region']}, desde {_hm(e['at'])})")
        feito = _sem_acento(" ".join(
            [f"{ev['title']} {ev['summary']}" for ev in eventos if _dt(ev["event_at"]) <= m["at"]]
            + [w["activity"] or "" for w in mundo if w["at"] <= m["at"]]
            + feito_extra(db, eventos, m["at"])))
        for achado in fez_contradiz(m["content"], feito):
            s_fez.append(f"**{_hm(m['at'])}** ela: {achado}")
        for q in quebras(m["content"]):
            s_quebra.append(f"**{_hm(m['at'])}** {q}: «{_curto(m['content'], 120)}»")
        if s := saudacao_fora_de_hora(m["content"], m["at"]):
            s_quebra.append(f"**{_hm(m['at'])}** «{s}» fora de hora: «{_curto(m['content'], 120)}»")

    # card × mundo: nas falas dela e de hora em hora
    CARD_OK = {"la": {"fora", "aula", "academia", "rua"}, "caminho": {"caminho"}, "voltando": {"caminho"},
               "arrumando": {"arrumando", "banho", "casa"}}
    momentos = sorted({m["at"] for m in marina} | {ini + timedelta(hours=h, minutes=30) for h in range(24)})
    vistos = set()
    for at in momentos:
        if at > datetime.now():
            continue
        e = estado_em(at)
        if not e:
            continue
        et = etapa_em(at)
        if isinstance(et, Exception):
            s_card.append(f"**{_hm(at)}** card deu erro: {type(et).__name__}: {_curto(str(et), 100)}")
            continue
        perto = {w["sit"] for w in estados_perto(at)}
        if et is None:
            ruim = perto <= {"fora", "caminho", "aula", "academia"} and e["sit"] in ("fora", "caminho")
            txt = "card vazio (em casa)"
        else:
            ruim = not (perto & CARD_OK.get(et.tipo, perto))
            txt = f"card «{et.titulo}» ({et.tipo})"
        chave = (txt, e["activity"])
        if ruim and chave not in vistos:
            vistos.add(chave)
            s_card.append(f"**{_hm(at)}** {txt} × mundo: {e['activity']} ({e['location_region']})")

    # mundo × mundo (soak, dia 1: a fala seguia o mundo, e o mundo é que estava errado)
    s_mundo = []
    FORA = {"fora", "aula", "academia", "rua"}
    anterior = None
    for w in mundo:
        if anterior is None or w["activity"] == anterior["activity"]:
            anterior = anterior or w
            continue
        a, b = anterior["sit"], w["sit"]
        if "rapidinho" in (anterior["activity"] or "") + (w["activity"] or ""):
            a = b = "casa"                             # a descida do Milo é na calçada do prédio
        if "passeando com milo" in _sem_acento(anterior["activity"] or "") and b in ("casa", "banho"):
            a = "casa"                                 # soak, dia 4 (02/10, 09:37): o passeio do Milo volta pra casa
        if a in FORA and b in ("casa", "banho") and w["at"] >= ini:
            s_mundo.append(f"**{_hm(w['at'])}** teleporte: de «{anterior['activity']}» ({anterior['location_region']}) "
                           f"direto pra «{w['activity']}», sem trajeto")
        if a in ("casa", "banho") and b in FORA - {"rua"} and w["at"] >= ini:
            s_mundo.append(f"**{_hm(w['at'])}** teleporte: de «{anterior['activity']}» direto pra «{w['activity']}» "
                           f"({w['location_region']}), sem trajeto")
        origem = re.match(r"(?:indo|voltando) d[aoe]s? (.+?) (?:pra|pro|pa)\b", _sem_acento(w["activity"] or ""))
        if origem and a in ("casa", "banho") and origem.group(1) != "casa" and w["at"] >= ini:
            s_mundo.append(f"**{_hm(w['at'])}** trajeto «{w['activity']}» sai de «{origem.group(1)}», mas ela estava "
                           f"em casa («{anterior['activity']}»)")
        anterior = w
    for ev in eventos:
        if ev["event_type"] != "meal":
            continue
        e = estado_em(_dt(ev["event_at"]) + timedelta(minutes=2))
        fora_lugar = re.search(r"no restaurante da PUC|no Shopping da Gávea", ev["summary"] or "")
        if e and fora_lugar and e["sit"] in ("casa", "banho"):
            s_mundo.append(f"**{_hm(_dt(ev['event_at']))}** {ev['title']} «{fora_lugar.group(0)}» com o mundo em "
                           f"«{e['activity']}»")
        if e and "em casa" in (ev["summary"] or "") and e["sit"] in FORA | {"caminho"}:
            s_mundo.append(f"**{_hm(_dt(ev['event_at']))}** {ev['title']} «em casa» com o mundo em «{e['activity']}»")
    banhos = []
    for ev in eventos:
        if ev["title"] != "banho":
            continue
        ini_b = _dt(ev["event_at"])
        if ev["end_at"]:
            banhos.append((ini_b, _dt(ev["end_at"])))
        elif h := re.search(r"\d\d:\d\d[–-](\d\d):(\d\d)", ev["summary"] or ""):   # "(05:23–05:47)"
            fim_b = ini_b.replace(hour=int(h.group(1)), minute=int(h.group(2)))
            banhos.append((ini_b, fim_b if fim_b > ini_b else fim_b + timedelta(days=1)))
    for ev in eventos:
        if ev["title"] == "banho" or ev["event_type"] not in ("routine", "meal", "snack"):
            continue
        at = _dt(ev["event_at"])
        if any(b0 < at < b1 for b0, b1 in banhos):
            s_mundo.append(f"**{_hm(at)}** «{_curto(ev['summary'], 70)}» no meio do banho")

    # foto × roupa
    try:
        from roupa import Roupa, nome_look
        roupa = Roupa(db)
    except Exception:
        roupa = None
    fotos_dela = [m for m in marina if m["media_type"] == "photo"]
    linhas_foto = []
    for m in fotos_dela:
        look = ""
        if roupa:
            try:
                ent = roupa.entrada_em(m["at"])
                look = nome_look(ent["look"]) if ent else ""
            except Exception as exc:
                look = f"(erro: {type(exc).__name__})"
        linhas_foto.append(f"**{_hm(m['at'])}** {_curto(m['content'], 160)} → roupa no mundo: {look or '(sem registro)'}")
        desc = (m["content"].split("]")[0] if m["content"].startswith("[") else m["content"]).lower()
        falta = [p for p in ROUPA_PALAVRAS if re.search(rf"\b{p}\b", desc) and p not in _sem_acento(look)
                 and _sem_acento(p) not in _sem_acento(look)]
        if look and falta:
            s_foto.append(f"**{_hm(m['at'])}** foto fala de {', '.join(falta)}, mundo diz {look}")

    # ordem e repetição
    ult = None
    for m in msgs:
        if ult and m["at"] < ult["at"]:
            s_ordem.append(f"**{_hm(m['at'])}** mensagem {m['id']} gravada antes da {ult['id']} ({_hm(ult['at'])})")
        ult = m
    rep = Counter(re.sub(r"\W+", " ", m["content"].lower()).strip() for m in marina if len(m["content"]) > 12)
    for txt, n in rep.items():
        if n > 1:
            s_ordem.append(f"ela repetiu {n}x: «{_curto(txt, 100)}»")

    # --- log ------------------------------------------------------------------
    log = ler_log(ini, fim)
    reais, reais_at, ruido, avisos = [], [], Counter(), Counter()
    for e in log:
        texto = e["msg"] + " " + " ".join(e["extra"][-3:])
        if e["nivel"] in ("ERROR", "CRITICAL") or any("Traceback" in x for x in e["extra"]):
            if any(r in texto for r in RUIDO):
                ruido[_excecao(e) or e["msg"][:80]] += 1
            else:
                reais_at.append(e["at"])
                reais.append(f"**{_hm(e['at'])}** {e['mod']}: {_curto(e['msg'], 160)}"
                             + (f" → `{_curto(_excecao(e), 140)}`" if _excecao(e) else ""))
        elif e["nivel"] == "WARNING":
            if any(r in texto for r in RUIDO) or e["mod"].startswith("apscheduler"):
                ruido[re.sub(r"\d+(?:[:.]\d+)*", "N", re.sub(r'"[^"]*"', '"…"', e["msg"]))[:70]] += 1
            else:
                avisos[re.sub(r"\d+", "N", _curto(e["msg"], 90))] += 1
    junk = [e for e in log if "llm.junk_reply" in e["msg"]]
    reinicios = [e["at"] for e in log if "iniciado com sucesso" in e["msg"]]
    llm_chamadas = sum(1 for e in log if "openrouter.ai/api/v1/chat/completions" in e["msg"])
    payload = [int(m.group(1)) for e in log if (m := re.search(r"prompt\.payload .*total=(\d+)", e["msg"]))]
    civitai = [e for e in log if e["msg"].startswith("civitai.submitted")]
    buzz = sum(int(m.group(1)) for e in civitai if (m := re.search(r"cost=(\d+)", e["msg"])))
    nsfw = sum(1 for e in civitai if "nsfw=True" in e["msg"])
    civitai_falhas = Counter(e["msg"].split()[0] for e in log
                             if e["mod"] == "CivitaiImages" and e["nivel"] in ("ERROR", "WARNING"))
    rotas = sum(1 for e in log if e["msg"].startswith("commute.live "))
    rotas_falha = sum(1 for e in log if e["msg"].startswith("commute.live_failed"))
    audios = [float(m.group(1)) for e in log if (m := re.search(r"voice\.duration_actual seconds=([\d.]+)", e["msg"]))]
    proativo = Counter(re.sub(r"\d+(?:\.\d+)?", "N", e["msg"].split(" base=")[0])[:80] for e in log
                       if e["mod"] == "ProactivityService")

    # --- conferências da leitura melhorada (soak, dia 4) -------------------------------
    def falas_perto(at: datetime, antes: timedelta, depois: timedelta) -> list[dict]:
        return [m for m in marina if at - antes <= m["at"] <= at + depois]

    # comida × fome: comeu e a fome não caiu; fome alta logo depois da refeição; comida comprada sem refeição
    s_fome, fome_linha = [], []
    try:
        from meals import Meals
        meals = Meals(db)
        for h in range(24):
            at = ini + timedelta(hours=h, minutes=30)
            if at <= datetime.now():
                fome_linha.append(f"{_hm(at)} {meals.hunger(at):.2f}")
        for ev in eventos:
            if ev["event_type"] not in ("meal", "snack"):
                continue
            ini_c = _dt(ev["event_at"])
            fim_c = _dt(ev["end_at"]) if ev["end_at"] else ini_c + timedelta(minutes=15)
            antes, depois = meals.hunger(ini_c - timedelta(minutes=1)), meals.hunger(fim_c + timedelta(minutes=5))
            if antes >= 0.35 and antes - depois < 0.15:
                s_fome.append(f"**{_hm(ini_c)}** {ev['title']} ({_curto(ev['summary'], 70)}): a fome foi de "
                              f"{antes:.2f} pra {depois:.2f} — não caiu")
            if ev["event_type"] == "meal" and (fim_c + timedelta(hours=2)) <= datetime.now():
                volta = meals.hunger(fim_c + timedelta(hours=2))
                if volta >= 0.55:
                    s_fome.append(f"**{_hm(ini_c)}** {ev['title']}: duas horas depois a fome já estava em {volta:.2f}")
    except Exception as exc:
        s_fome.append(f"(fome deu erro: {type(exc).__name__}: {_curto(str(exc), 100)})")
    try:
        from consumo import Consumo, plan
        refeicoes = [_dt(ev["event_at"]) for ev in eventos if ev["event_type"] in ("meal", "snack")]
        for outing in Consumo(db)._outings(dia):
            for item in plan(outing):
                if item.comida and ini <= item.at < fim and item.at <= datetime.now() and not any(
                        abs((r - item.at).total_seconds()) <= 180 for r in refeicoes):
                    s_fome.append(f"**{_hm(item.at)}** comprou {item.frase} (R$ {item.valor}) e não virou refeição "
                                  f"nem lanche — a fome não sabe")
    except Exception as exc:
        s_fome.append(f"(compras de comida deram erro: {type(exc).__name__}: {_curto(str(exc), 100)})")

    # compra num lugar com ela em casa (02/10, 20:06: caipirinha no Quartinho, chegou 20:22)
    for ev in eventos:
        if ev["event_type"] != "consumo" or " · " not in (ev["title"] or ""):
            continue
        st = estado_em(_dt(ev["event_at"]))
        if st and st["sit"] in EM_CASA:
            s_mundo.append(f"**{_hm(_dt(ev['event_at']))}** {ev['title']} com o mundo em «{st['activity']}»")
    # "banho tomado" sem banho desde que voltou pra casa (02/10, 23:45)
    fins_banho = [b1 for _, b1 in banhos]
    for m in marina:
        if not RE_BANHO_FEITO.search((m["content"] or "").lower()):
            continue
        ult_banho = max((b for b in fins_banho if b <= m["at"]), default=None)
        voltas = [w["at"] for w in mundo if w["at"] <= m["at"] and _sem_acento(w["activity"] or "").startswith("voltando")]
        if voltas and (ult_banho is None or max(voltas) > ult_banho):
            s_fez.append(f"**{_hm(m['at'])}** ela: «{_curto(RE_BANHO_FEITO.search(m['content'].lower()).group(0), 40)}»"
                         f" (o último banho foi {'às ' + _hm(ult_banho) if ult_banho else 'antes do dia'}, antes de sair;"
                         f" voltou às {_hm(max(voltas))})")

    # foto pedida/prometida × foto que chegou (e o que foi no lugar)
    s_pedida = []
    fotos_at = [m["at"] for m in fotos_dela]
    pedidos = []
    # O intent=photo_request do log não serve: em 02/10 (11:35) era a foto que ELE mandou.
    for m in msgs:
        if m["role"] != "user":
            continue
        if pede_foto(m["content"]) and not (pedidos and m["at"] - pedidos[-1][0] <= timedelta(minutes=3) and pedidos[-1][1] == "pediu"):
            pedidos.append((m["at"], "pediu", f"«{_curto(m['content'], 80)}»", m["at"] + timedelta(minutes=15)))
    for e in log:
        if e["msg"].startswith("promessa_foto.made"):
            due = re.search(r"due=(\S+)", e["msg"])
            limite = max(_dt(due.group(1)) if due else e["at"], e["at"]) + timedelta(minutes=20)
            kind = re.search(r"kind=(\S+)", e["msg"])
            pedidos.append((e["at"], "prometeu", kind.group(1) if kind else "foto", limite))
        elif e["msg"].startswith("CAMERA_WORLD_CONTEXT"):
            # toda foto que o bot começou a fazer (pedida, prometida ou por vontade dela): 02/10, 15:41 no Rei do Mate
            lugar = re.search(r"place=(\S+)", e["msg"])
            pedidos.append((e["at"], "tentou", f"uma foto ({lugar.group(1) if lugar else '?'})",
                            e["at"] + timedelta(minutes=5)))
    promessas_at = [at for at, quem, _, _ in pedidos if quem == "prometeu"]
    for at, quem, o_que, limite in sorted(pedidos):
        if any(at <= f <= limite for f in fotos_at):
            continue
        if quem == "pediu" and any(at <= p <= at + timedelta(minutes=30) for p in promessas_at):
            continue          # 02/10, 19:03: virou promessa (19:29) e a promessa é conferida por ela mesma
        no_lugar = [f"«{_curto(m['content'], 90)}» ({_hm(m['at'])})" for m in falas_perto(at, timedelta(0), limite - at)][:2]
        falhas = [f"{e['msg'].split(' —')[0].split()[0]} ({_hm(e['at'])})" for e in log
                  if at <= e["at"] <= limite and (e["msg"].startswith(("civitai.", "foto.nao_saiu", "llm.photo"))
                                                 and e["nivel"] in ("ERROR", "WARNING"))]
        quem = {"pediu": "ele pediu", "prometeu": "ela prometeu", "tentou": "o bot começou"}[quem]
        s_pedida.append(f"**{_hm(at)}** {quem} {o_que} e não chegou foto "
                        f"até {_hm(limite)}" + (f"; no lugar ela mandou {', '.join(no_lugar)}" if no_lugar else
                                                "; ela não mandou nada no lugar")
                        + (f"; log: {', '.join(falhas)}" if falhas else ""))

    # enviado pro Telegram × histórico (a desculpa fixa da câmera não entrava no histórico)
    s_fora_hist = []
    enviados = [(e["at"], m.group(1), m.group(2)) for e in log
                if (m := re.match(r"chat\.enviado tipo=(\S+) texto=(.*)", e["msg"]))]
    for at, tipo, texto in enviados:
        perto = [m["content"] for m in falas_perto(at, timedelta(minutes=10), timedelta(minutes=10))]
        if not no_historico(texto, perto):
            s_fora_hist.append(f"**{_hm(at)}** {tipo} enviado e fora do histórico: «{_curto(texto, 120)}»")

    # fundo da foto × lugar do mundo
    s_fundo, cenas = [], []
    for e in log:
        if m := re.match(r"photo_director\.cena lugar=(\S+) comodo=(\S+) pose=(\S+) cena=(.*)", e["msg"]):
            cenas.append((e["at"], m.group(1), m.group(2), m.group(4)))
            if achado := fundo_contradiz(m.group(2), m.group(4), estado_em(e["at"])):
                st = estado_em(e["at"])
                s_fundo.append(f"**{_hm(e['at'])}** {achado} → mundo: {st['activity']} ({st['location_region']})")

    # o Patrick estranhou: a fala dele, o que ela tinha dito, o mundo e o que ela respondeu
    estranhos = []
    for i, m in enumerate(msgs):
        if m["role"] != "user" or not (pista := estranhou(m["content"])):
            continue
        antes = next((x for x in reversed(msgs[:i]) if x["role"] == "assistant"), None)
        depois = next((x for x in msgs[i + 1:] if x["role"] == "assistant"), None)
        st = estado_em(m["at"])
        estranhos.append(
            f"**{_hm(m['at'])}** Patrick: «{_curto(m['content'], 160)}» (pista: «{pista}»)"
            + (f"\n  - antes, ela ({_hm(antes['at'])}): «{_curto(antes['content'], 160)}»" if antes else "")
            + (f"\n  - mundo: {st['activity']} ({st['location_region']}, desde {_hm(st['at'])})" if st else "")
            + (f"\n  - depois, ela ({_hm(depois['at'])}): «{_curto(depois['content'], 160)}»" if depois else ""))

    # erro do log seguido até o que ele recebeu
    def depois_do_erro(at: datetime) -> str:
        dela = falas_perto(at, timedelta(0), timedelta(minutes=5))
        fora = [t for a, _, t in enviados if at <= a <= at + timedelta(minutes=5) and not no_historico(
            t, [m["content"] for m in falas_perto(a, timedelta(minutes=10), timedelta(minutes=10))])]
        partes = [f"ela «{_curto(m['content'], 80)}» ({_hm(m['at'])})" for m in dela[:2]]
        partes += [f"fora do histórico «{_curto(t, 80)}»" for t in fora[:2]]
        return " → depois: " + ("; ".join(partes) if partes else "nada dela em 5 min")

    reais = [r + depois_do_erro(a) for r, a in zip(reais, reais_at)]

    def cena_da_foto(at: datetime) -> str:
        c = [x for x in cenas if at - timedelta(minutes=6) <= x[0] <= at]
        return f"; cenário: {c[-1][2]}, «{_curto(c[-1][3], 90)}»" if c else ""

    linhas_foto = [linha + cena_da_foto(m["at"]) for linha, m in zip(linhas_foto, fotos_dela)]

    journal = []
    try:
        fmt = "%Y-%m-%d %H:%M:%S"
        from zoneinfo import ZoneInfo
        utc = lambda d: d.replace(tzinfo=ZoneInfo("America/Sao_Paulo")).astimezone(ZoneInfo("UTC")).strftime(fmt)
        r = subprocess.run(["journalctl", "-u", "marina", "--since", utc(ini) + " UTC", "--until", utc(fim) + " UTC",
                            "--no-pager", "-o", "cat"], capture_output=True, text=True, timeout=60)
        linhas = [ln for ln in r.stdout.splitlines() if not RE_LINHA.match(ln)]   # o log do bot já foi lido acima
        paradas = sum(1 for ln in linhas if ln.startswith("Stopped marina.service"))
        journal = ([f"{paradas} parada(s) e reinício(s) normais (deploy)"] if paradas else []) + [
            ln for ln in linhas if re.search(r"exited|Failed|Killed|oom|Main process|core-dump", ln, re.I)]
    except Exception:
        pass

    # --- /feedback ----------------------------------------------------------------
    # Soak, dia 4 (03/10): o relatório não lia a tabela `feedbacks` e 11 /feedback do Patrick (29/09–02/10) ficaram
    # sem ninguém ler. Cada um é bug a investigar, com o mundo daquela hora e o que ela tinha dito.
    feedbacks = []
    try:
        for r in conn.execute("SELECT id, timestamp, feedback FROM feedbacks WHERE timestamp >= ? AND timestamp < ? "
                              "ORDER BY timestamp", (s_ini, s_fim)):
            at = _dt(r["timestamp"])
            st = estado_em(at)
            antes = [m for m in marina if m["at"] <= at][-1:]
            feedbacks.append(
                f"**{_hm(at)}** /feedback: «{_curto(r['feedback'], 400)}»"
                + (f"\n  - mundo: {st['activity']} ({st['location_region']}, desde {_hm(st['at'])})" if st else "")
                + (f"\n  - antes, ela ({_hm(antes[0]['at'])}): «{_curto(antes[0]['content'], 160)}»" if antes else ""))
    except sqlite3.Error:
        pass

    # --- /bom e /ruim ------------------------------------------------------------
    marcas = []
    for arq, cab, rotulo in (("BIBLIOTECA_COMPORTAMENTAL_MARINA.md", r"Registro (\d+)", "/bom"),
                             ("COMO_NAO_SOAR_MARINA.md", r"Evitar (\d+)", "/ruim")):
        p = ROOT / "data" / "feedback" / arq
        if not p.exists():
            continue
        for bloco in re.split(r"\n(?=## )", p.read_text(encoding="utf-8")):
            num = re.match(rf"## {cab}", bloco)
            quando = re.search(r"\*\*Data(?: e hora)?:\*\* (\d{4}-\d\d-\d\d \d\d:\d\d)", bloco)
            if not (num and quando):
                continue
            at = datetime.strptime(quando.group(1), "%Y-%m-%d %H:%M")
            if not (ini <= at < fim) or (rotulo == "/bom" and "/bom" not in bloco):
                continue
            fala = (re.search(r"\*\*Marina respondeu \(RUIM\):\*\* (.*)", bloco)
                    or re.search(r"\*\*Exemplos naturais:\*\*\s*\n\s*- (.+)", bloco))
            motivo = re.search(r"\*\*Por que soa errado:\*\* (.*)", bloco)
            marcas.append((at, f"**{_hm(at)}** {rotulo} {num.group(1)}: «{_curto(fala.group(1) if fala else '', 140)}»"
                               + (f" (motivo: {_curto(motivo.group(1), 100)})" if motivo else "")))
    marcas.sort()

    # --- aba Hoje -----------------------------------------------------------------
    hoje_linhas = []
    try:
        from hoje import hoje_view
        view = hoje_view(db, datetime.combine(dia + timedelta(days=1), time(3, 59)))
        for per in view.get("periodos", []):
            hoje_linhas.append(f"- _{per['nome']}_")
            for it in per["itens"]:
                extra = f" ({it['sub']})" if it.get("sub") else ""
                valor = f" R$ {it['valor']}" if it.get("valor") else ""
                prev = " [previsto, não aconteceu]" if it.get("previsto") else ""
                hoje_linhas.append(f"  - {it['hora']} {it['texto']}{extra}{valor}{prev}")
                for f in it.get("filhos", []):
                    hoje_linhas.append(f"    - {f['hora']} {f['texto']}" + (f" ({f['sub']})" if f.get("sub") else ""))
    except Exception as exc:
        hoje_linhas.append(f"(a aba Hoje deu erro: {type(exc).__name__}: {_curto(str(exc), 120)})")

    # --- escrita ------------------------------------------------------------------
    inicio_soak = None
    try:
        inicio_soak = date.fromisoformat((SOAK_DIR / "inicio.txt").read_text().strip())
    except Exception:
        pass
    n_dia = f"dia {(dia - inicio_soak).days + 1}" if inicio_soak and dia >= inicio_soak else "antes do soak"
    try:
        rev = (ROOT / ".deployed").read_text().strip()
    except Exception:
        rev = "?"
    dele = sum(1 for m in msgs if m["role"] == "user")
    inic = [m for m in marina if m["is_initiative"]]
    n_audio = sum(1 for m in marina if m["media_type"] in ("voice", "audio"))
    suspeitas = (len(s_lugar) + len(s_fez) + len(s_card) + len(s_mundo) + len(s_quebra) + len(s_foto)
                 + len(s_ordem) + len(junk) + len(s_fome) + len(s_pedida) + len(s_fora_hist) + len(s_fundo))

    L = [f"# Soak, {n_dia}: {DIAS[dia.weekday()]} {dia.strftime('%d/%m')} (05:00 → 05:00)", "",
         f"_Gerado em {datetime.now().strftime('%d/%m %H:%M')} na VPS, código `{rev}`, numa cópia do banco._", "",
         "## Roteiro de leitura (pra quem lê, antes das suspeitas)", "",
         "1. Ler **a conversa inteira** com o mundo do lado, não só as suspeitas — o script só acha o que já "
         "alguém ensinou.",
         "2. Cada **/feedback** dele é bug a investigar (não é anotação): conferir um por um. Cada linha de "
         "**«O Patrick estranhou»** é pista: achar o que ela ou o mundo fez de errado ali.",
         "3. Cada **erro de verdade**: seguir até o que ele recebeu no lugar (a linha já mostra o que veio depois).",
         "4. Conferir **fome** de hora em hora com o que ela comeu, **fotos pedidas** com as que chegaram e o "
         "**cenário** de cada foto com o lugar.",
         "5. Bug novo que o script não pegou vira conferência nova aqui (com o caso real no teste).", "",
         "## Resumo", "",
         f"- Conversa: {dele} mensagens dele, {len(marina)} dela ({len(inic)} iniciativas, "
         f"{len(fotos_dela)} fotos, {n_audio} áudios)",
         f"- Suspeitas pra conferir: **{suspeitas}** (fala × mundo {len(s_lugar)}, fala × o que ela fez "
         f"{len(s_fez)}, card × mundo {len(s_card)}, mundo × mundo {len(s_mundo)}, "
         f"fala quebrada {len(s_quebra) + len(junk)}, foto × roupa {len(s_foto)}, ordem/repetição {len(s_ordem)}, "
         f"comida × fome {len(s_fome)}, foto pedida × chegou {len(s_pedida)}, fora do histórico {len(s_fora_hist)}, "
         f"fundo × lugar {len(s_fundo)})",
         f"- O Patrick estranhou: **{len(estranhos)}** fala(s) dele",
         f"- Erros: **{len(reais)}** de verdade, {sum(ruido.values())} de rede/agendador; "
         f"{len(reinicios)} reinício(s)" + (f" ({', '.join(_hm(r) for r in reinicios)})" if reinicios else ""),
         "- Custos: LLM " + (
             "não consultado" if sem_custos else
             f"erro ao consultar ({custo_llm['erro']})" if "erro" in custo_llm else
             (f"US$ {custo_llm['dia']:.3f}" if custo_llm.get("dia") is not None else "começa a contar amanhã")
             + f" (saldo US$ {custo_llm['saldo']:.2f})")
         + f", {llm_chamadas} chamadas; Civitai {buzz} Buzz em {len(civitai)} foto(s) ({nsfw} adulta); "
           f"rotas {rotas} chamada(s)" + (f" + {rotas_falha} falha(s)" if rotas_falha else "")
         + f"; voz {len(audios)} áudio(s), {sum(audios):.0f} s",
         f"- /feedback dele: **{len(feedbacks)}**; /bom e /ruim: {sum(1 for _, t in marcas if '/bom' in t)} e "
         f"{sum(1 for _, t in marcas if '/ruim' in t)}",
         ""]

    def secao(titulo: str, itens: list[str], vazio: str = "nada") -> None:
        L.extend([f"### {titulo}", ""] + ([f"- {i}" for i in itens] or [f"_{vazio}_"]) + [""])

    L += ["## Suspeitas (achadas pelo script; quem decide se é bug é quem lê)", ""]
    secao("Fala × mundo (onde ela disse que estava, o que disse que estava fazendo)", s_lugar)
    secao("Fala × o que ela fez no dia (comida, Milo, academia, banho)", s_fez)
    secao("Card da aba Agora × mundo", s_card)
    secao("Mundo × mundo (teleporte, trajeto saindo do lugar errado, refeição × lugar, coisa no meio do banho)",
          s_mundo)
    secao("Fala quebrada ou número sumido", s_quebra + [
        f"**{_hm(e['at'])}** o bot pegou e refez: {_curto(e['msg'], 170)}" for e in junk])
    secao("Foto × roupa", s_foto)
    secao("Ordem e repetição", s_ordem)
    secao("Comida × fome (comeu e não caiu, voltou rápido, comprou e não comeu)", s_fome)
    secao("Foto pedida ou prometida × foto que chegou", s_pedida)
    secao("Enviado pro Telegram × histórico", s_fora_hist,
          "nada" if enviados else "o log ainda não tem «chat.enviado» (código antes de 03/10)")
    secao("Fundo da foto × lugar do mundo", s_fundo,
          "nada" if cenas else "o log ainda não tem «photo_director.cena» (código antes de 03/10)")

    secao("/feedback do Patrick (cada um é bug a investigar)", feedbacks)
    secao("O Patrick estranhou (fala dele com cara de «hein?»: o que ela disse, o mundo, o que ela respondeu)",
          estranhos)

    L += ["## Conversa com o mundo", "",
          "_Linhas «mundo» só quando o estado muda. Marcas: (iniciativa), (foto), (áudio)._", ""]
    linha_do_tempo = [(m["at"], 1, m) for m in msgs]
    anterior = None
    for w in mundo:
        if (w["activity"], w["location_region"]) != anterior:
            anterior = (w["activity"], w["location_region"])
            linha_do_tempo.append((max(w["at"], ini), 0, w))
    for at, tipo, x in sorted(linha_do_tempo, key=lambda t: (t[0], t[1])):
        if tipo == 0:
            L.append(f"- `{_hm(at)}` _mundo: {x['activity']} ({x['location_region']})_")
        else:
            quem = "Patrick" if x["role"] == "user" else "Marina"
            marcas_msg = ([("iniciativa")] if x["is_initiative"] else []) + (
                ["foto"] if x["media_type"] == "photo" else ["áudio"] if x["media_type"] in ("voice", "audio") else [])
            L.append(f"- `{_hm(at)}` **{quem}**: {_curto(x['content'], 400)}"
                     + (f" _({', '.join(marcas_msg)})_" if marcas_msg else ""))
    L.append("")

    L += ["## Aba Hoje (como ficou no fim do dia)", ""] + (hoje_linhas or ["_vazia_"]) + [""]
    secao("Fome de hora em hora (0 = satisfeita, 1 = morrendo de fome)", [", ".join(fome_linha)] if fome_linha else [])
    secao("Acontecimentos (life_events)", [
        f"**{_hm(_dt(e['event_at']))}** {e['event_type']}: {e['title']} ({_curto(e['summary'], 140)})" for e in eventos])
    secao("Fotos que ela mandou (com a roupa do mundo)", linhas_foto)
    secao("Instagram dela", [
        f"**{_hm(_dt(p['criado_em']))}** {p['tipo']} ({p['motivo']}, {p['local'] or 'sem local'}): "
        f"«{_curto(p['legenda'], 100)}»; roupa: {p['roupa'] or '(nenhuma)'}; foto: {_curto(p['descricao'], 120)}"
        for p in posts])
    secao("/bom e /ruim", [t for _, t in marcas])
    secao("Erros de verdade", reais, "nenhum")
    secao("Avisos do log (contagem)", [f"{n}x {k}" for k, n in avisos.most_common(25)])
    secao("Rede e agendador (não conta como bug)", [f"{n}x {k}" for k, n in ruido.most_common(10)])
    secao("Serviço (journal)", [_curto(j, 160) for j in journal])
    secao("Custos e fotos geradas", [
        f"LLM: {llm_chamadas} chamadas; prompt médio {sum(payload) // len(payload) if payload else 0} "
        f"caracteres (maior {max(payload) if payload else 0})",
        f"Civitai: {len(civitai)} foto(s), {buzz} Buzz, {nsfw} adulta(s)"
        + (f"; falhas: {', '.join(f'{n}x {k}' for k, n in civitai_falhas.items())}" if civitai_falhas else ""),
        f"Rotas (API paga): {rotas} chamada(s), {rotas_falha} falha(s)",
        f"Voz (MiniMax): {len(audios)} áudio(s), {sum(audios):.0f} s"])
    secao("Iniciativas (o que ela puxou sozinha)",
          [f"**{_hm(m['at'])}** {_curto(m['content'], 160)}" for m in inic]
          + [f"decisões da proatividade: {n}x {k}" for k, n in proativo.most_common(8)])

    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
