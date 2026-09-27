"""Instagram da Marina (Etapa 5 do PLANO_WEBAPP; decidido com o Patrick em 27/09).

- Perfil @masalles (~4 mil seguidores), bio "moda, croqui e café gelado / mãe do @milooshi / ♡ @ptkramos".
- Feed pelo dia dela, ~2 posts por semana, no máximo 1 por dia: um acontecimento de verdade (rolê com amiga,
  praia, salão, look, treino, Milo) vira vontade de postar, e o que ela sente decide (triste não posta).
- Foto do post: uma foto vestida que ela já mandou no chat (custo zero) ou uma nova (~20 Buzz; com amiga, ~61).
- Stories sem foto nova: a música que está tocando, uma foto do chat, texto. Somem em 24 h.
- Amigas (Bia, Carol, Júlia, Theo) comentam nos posts dela, aparecem marcadas e postam ~2 vezes por semana
  somando todas (foto nova pelo rosto do RG, ou a foto de grupo do rolê com a Marina).
- Ela só fica sabendo da curtida/comentário do Patrick quando abre o Insta (bloco "Olhando o Instagram", uber,
  tempo livre com o celular): responde lá e sabe do que viu no chat, sem notificação de sistema.

Aqui ficam as regras (quando, o quê, quem). Foto e texto vêm de fora (o bot passa as funções), então tudo que
decide é testável sem rede.
"""
from __future__ import annotations

import json
import logging
import math
import random
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("Instagram")

DIR = Path(__file__).resolve().parent / "data" / "instagram"

# ------------------------------------------------------------------ perfis --
# 27/09 (Patrick): bio B com @masalles e @milooshi; ~4 mil seguidores. O resto (amigas) decidi eu — revisar.
PERFIS = {
    "marina": {"handle": "masalles", "nome": "Ma Salles", "seguidores": 4118, "seguindo": 702,
               "bio": ["moda, croqui e café gelado", "mãe do @milooshi", "♡ @ptkramos"],
               "avatar": "ig/avatar_marina.jpg"},
    "bia_andrade": {"handle": "bia.andrade", "nome": "Bia Andrade", "seguidores": 2387, "seguindo": 1204,
                    "bio": ["Laranjeiras · RJ", "sexta é sagrada"], "avatar": "static/avatars/bia_andrade.jpg"},
    "carol_menezes": {"handle": "carolmenezes", "nome": "Carol Menezes", "seguidores": 1652, "seguindo": 811,
                      "bio": ["nutri em formação", "treino e comida de verdade"],
                      "avatar": "static/avatars/carol_menezes.jpg"},
    "julia_azevedo": {"handle": "juazevedo", "nome": "Júlia Azevedo", "seguidores": 934, "seguindo": 688,
                      "bio": ["design · PUC-Rio", "fotografo tudo em 35 mm"],
                      "avatar": "static/avatars/julia_azevedo.jpg"},
    "theo_martins": {"handle": "theomartins", "nome": "Theo Martins", "seguidores": 1428, "seguindo": 960,
                     "bio": ["moda · PUC-Rio", "Glória"], "avatar": "static/avatars/theo_martins.jpg"},
    "patrick": {"handle": "ptkramos", "nome": "Patrick", "avatar": ""},
}
AMIGAS = ("bia_andrade", "carol_menezes", "julia_azevedo", "theo_martins")
# seguidores de fora que às vezes comentam (curto, elogio)
DE_FORA = ("lu.mendes", "nanda.rocha", "pedroh.lima", "carolinabastos", "rafa.nogueira", "duda.lins")

# quanto cada um comenta nos posts dela (a marcada sempre comenta)
# 27/09 (Patrick): "as amigas ficaram absurdamente repetitivas". A descrição antiga tinha assunto e bordão
# embutidos ("repara na luz", "fala de treino", "chama de amiga/gata") e virou fórmula. Agora é a pessoa — quem
# ela é e como escreve —, e cada pedido leva o que ela já escreveu, pra não repetir.
COMENTA = {"bia_andrade": 0.7, "theo_martins": 0.45, "julia_azevedo": 0.35, "carol_menezes": 0.35}
JEITO = {
    "bia_andrade": "a Bia, 20 anos, melhor amiga da Marina, de Laranjeiras; intensa, exagerada, impulsiva e muito "
                   "carinhosa, solteira e namoradeira; escreve rápido, em caixa baixa, do jeito que fala",
    "theo_martins": "o Theo, 21 anos, amigo da Marina da faculdade de moda, gay, da Glória; observador, sarcástico e "
                    "leal; humor seco, escreve bem e sem exagero",
    "julia_azevedo": "a Júlia, 20 anos, colega de faculdade da Marina, do Jardim Botânico; artista, fotógrafa amadora, "
                     "meio distraída; escreve pouco e de um jeito doce",
    "carol_menezes": "a Carol, 22 anos, amiga da Marina da academia, estudante de nutrição, de Botafogo; prática, "
                     "organizada e carinhosa; escreve direto, com pontuação certinha",
}
QUEM_ESCREVE = {"marina": "a Marina (@masalles), 20 anos, paulista morando em Botafogo, estudante de Design de Moda "
                          "na PUC-Rio e modelo freelance, dona do Milo (Shih Tzu); no Insta escreve curtinho, em "
                          "caixa baixa", **JEITO}


def ja_escreveu(db, autor: str, n: int = 10) -> list[str]:
    """O que essa pessoa escreveu por último no Instagram (legendas e comentários), do mais novo pro mais velho."""
    rows = _rows(db, """SELECT texto, criado_em FROM ig_comentarios WHERE autor=?
                        UNION ALL SELECT legenda, criado_em FROM ig_posts WHERE autor=? AND legenda!=''
                        ORDER BY criado_em DESC LIMIT ?""", (autor, autor, n))
    return [r["texto"] for r in rows]


def _nao_repita(db, autor: str) -> str:
    feitos = ja_escreveu(db, autor)
    if not feitos:
        return ""
    return (" O que já escreveu por último no Instagram (não repita palavra marcante, emoji, começo nem estrutura "
            "dessas): " + " / ".join(f"\"{t}\"" for t in feitos) + ".")


def _foto_pros_outros(p: dict) -> str:
    """A foto descrita de fora (a descrição guardada fala com a Marina: "você com a Bia")."""
    foto = re.sub(r"\bvocê\b", "a Marina", re.sub(r"\b(sua|seu)\b", "da Marina", p["descricao"]))
    if p.get("roupa"):
        foto += f" (roupa dela: {p['roupa']})"
    return foto


def pedido_legenda(db, autor: str, foto: str, local: str = "") -> str:
    """Prompt da legenda de um post (da Marina ou de uma amiga)."""
    return (f"Quem posta: {QUEM_ESCREVE[autor]}. Vai postar no próprio Instagram uma foto: {foto}"
            + (f", em {local}" if local else "") + ". Escreva só a legenda, como essa pessoa escreveria: curta "
            "(até 8 palavras), pode ser só um emoji ou uma frase solta, sem hashtag, sem aspas, sem falar com "
            "ninguém." + _nao_repita(db, autor))

FEED_GAP_H = 36          # entre dois posts dela
LIMIAR = 1.0             # vontade de postar (motivo + dias sem postar + como ela está)
STORY_MAX_DIA = 2
STORY_GAP_H = 3
STORY_TTL_H = 24
AMIGA_POSTA_DIA = 2 / 7  # ~2 posts por semana somando as quatro (Patrick, 27/09)
JANELA_POST = (time(9, 30), time(0, 40))
OLHA_GAP_MIN = {"alto": 75, "medio": 150, "depois_de_postar": 30}

# celular na mão (webapp_server.CELULAR_POR_ATIVIDADE)
FONE_ALTO = {"HOME_RELAXING", "COMMUTE", "OUT_SOLO", "UNKNOWN"}
FONE_MEDIO = {"SOCIAL", "MEAL", "GETTING_READY", "WAKING", "PET_WALK", "HOME_BUSY", "MICRO_WAKE", "MANICURE"}

# motivo → pose do catálogo (photo_director). 27/09 (Patrick): fora de casa ela quase sempre está com gente,
# então a foto costuma ser tirada por alguém; selfie é uma entre várias. Não repete a pose dos últimos posts.
FORA_ALGUEM = ("fora_amiga_corpo", "fora_amiga_andando", "fora_amiga_rindo", "fora_amiga_sentada",
               "fora_amiga_encostada", "fora_amiga_costas")
POSES = {
    "role_amiga": ("fora_amigas_alguem_tirando", "fora_amigas_alguem_tirando", "fora_selfie_amiga",
                   "fora_selfie_amiga_abraco"),
    "role": FORA_ALGUEM + ("fora_selfie",),
    "praia": ("fora_amiga_corpo", "fora_amiga_andando", "fora_amiga_rindo", "fora_amiga_costas"),
    "salao": ("salao_cabelo", "cabelo_espelho"),
    "unhas": ("pov_unhas", "unhas_selfie"),
    "look": ("closet_look_frente", "closet_look_giro", "closet_look_andando", "closet_look_poltrona"),
    "treino": ("academia_espelho", "academia_espelho_perfil"),
    "milo": ("pov_milo_rua",),
    "vista": ("varanda_parapeito", "pov_vista", "espelho_corpo", "sala_vinho_selfie"),
}
# 27/09 (Patrick): roupa repetida no feed incomoda (4 regatas pretas em 9 fotos) e praia é de biquíni.
# Guarda-roupa do Instagram por ocasião; ela não repete roupa dos últimos ROUPA_MEMORIA posts.
ROUPAS = {
    "dia": ("a sage green linen button-up shirt tied at the waist and white wide-leg trousers",
            "a butter yellow ribbed knit top and light-wash straight jeans",
            "a white broderie anglaise sundress with thin straps",
            "an oversized blue and white striped shirt worn as a dress with a thin brown belt",
            "a terracotta cropped cardigan buttoned up and high-waisted cream shorts",
            "a lilac satin midi skirt and a fitted white baby tee",
            "a red gingham summer dress with puff sleeves",
            "a light blue halter-neck top and beige linen pants",
            "a cropped olive utility jacket over a white tank top and dark jeans",
            "a chocolate brown slip skirt and a cream knit vest",
            "a mint green wrap top and a white denim mini skirt",
            "a pale pink polo shirt and a pleated grey mini skirt"),
    "noite": ("an emerald green satin slip dress",
              "a cherry red one-shoulder mini dress",
              "a dusty rose corset top and flared dark jeans",
              "a cobalt blue satin halter top and white tailored trousers",
              "a leopard print midi skirt and a fitted chocolate brown tee",
              "a champagne satin cowl-neck top and black tailored trousers",
              "a lavender knit mini dress",
              "a gold metallic camisole and wide-leg ivory pants",
              "a burgundy velvet mini dress",
              "an orange floral silk wrap dress",
              "a white linen co-ord set with a cropped blazer",
              "a silver sequined mini skirt and a soft grey fitted top"),
    "praia": ("a terracotta triangle bikini with a sheer white sarong tied at her hip",
              "a lime green bandeau bikini",
              "a baby blue ribbed bikini with an open white crochet cover-up",
              "a leopard print bikini and gold hoop earrings",
              "a cherry red string bikini",
              "a white bikini and a wide straw hat",
              "a lilac scrunch bikini and denim cutoff shorts",
              "a brown ribbed bikini and a colorful printed sarong"),
}
ROUPA_MEMORIA = 12


def escolher_roupa(db, ocasiao: str, rng: random.Random, evitar: tuple = (), simples: bool = False) -> str:
    """simples: só a peça, sem acessório por cima (a amiga na foto de grupo: o editor da troca de rosto
    confunde saída de praia e chapéu com a roupa do RG)."""
    usadas = {r["roupa"] for r in _rows(db, "SELECT roupa FROM ig_posts WHERE autor='marina' AND roupa IS NOT NULL "
                                            "ORDER BY criado_em DESC LIMIT ?", (ROUPA_MEMORIA,))}
    todas = [r for r in ROUPAS[ocasiao] if not simples or not re.search(r" with | and ", r)] or list(ROUPAS[ocasiao])
    opcoes = [r for r in todas if r not in usadas and r not in evitar] or todas
    return rng.choice(opcoes)


def ocasiao_da_roupa(motivo: str, hora: int) -> Optional[str]:
    """Que roupa a foto pede (None: a pose decide — academia, Milo, unhas, salão)."""
    if motivo == "praia":
        return "praia"
    if motivo == "look":
        return "noite" if hora >= 17 else "dia"
    if motivo in ("role", "role_amiga", "puc", "cafe", "vista"):
        return "noite" if hora >= 18 else "dia"
    return None


def escolher_pose(db, motivo: str, rng: random.Random, amiga: str = "") -> str:
    """Pose do motivo, sem repetir a dos últimos 3 posts dela. Com amiga de RG, pose das duas."""
    opcoes = POSES["role_amiga"] if amiga and motivo in ("role_amiga", "praia") else POSES.get(motivo, POSES["vista"])
    recentes = {r["pose"] for r in _rows(db, "SELECT pose FROM ig_posts WHERE autor='marina' AND pose IS NOT NULL "
                                             "ORDER BY criado_em DESC LIMIT 3")}
    return rng.choice([p for p in opcoes if p not in recentes] or list(opcoes))


PESO = {"role_amiga": 0.9, "role": 0.7, "praia": 0.85, "salao": 0.75, "unhas": 0.45, "look": 0.5, "treino": 0.4,
        "milo": 0.35, "chat": 0.45, "vista": 0.25}


@dataclass
class Momento:
    """O que o mundo diz agora (o bot monta)."""
    asleep: bool
    act_code: str
    bloco: object = None             # tempo_livre.Bloco de agora (ou None)
    patrick_ativo: bool = False      # falou com ela há pouco: não gera foto agora (a trava do Civitai é uma só)
    feeling: object = None

    @property
    def fone(self) -> str:
        if self.asleep:
            return ""
        if getattr(self.bloco, "chave", "") == "instagram":
            return "insta"
        return "alto" if self.act_code in FONE_ALTO else "medio" if self.act_code in FONE_MEDIO else ""


# ----------------------------------------------------------------- arquivos --
def salvar_imagem(dados: bytes, prefixo: str = "p") -> str:
    DIR.mkdir(parents=True, exist_ok=True)
    nome = f"{prefixo}_{secrets.token_urlsafe(12)}.jpg"
    (DIR / nome).write_bytes(dados)
    return nome


def caminho(nome: str) -> Optional[Path]:
    if not nome or "/" in nome or "\\" in nome or ".." in nome:
        return None
    p = DIR / nome
    return p if p.is_file() else None


# ------------------------------------------------------------------- banco --
def _rows(db, sql: str, args: tuple = ()) -> list[dict]:
    with db.get_connection() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def _exec(db, sql: str, args: tuple = ()) -> int:
    with db.get_connection() as conn:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid


def publicar(db, *, autor: str, now: datetime, tipo: str = "feed", imagem: Optional[str] = None,
             legenda: str = "", local: str = "", marcados: tuple = (), motivo: str = "",
             motivo_chave: Optional[str] = None, fonte: str = "", descricao: str = "",
             story: Optional[dict] = None, alcance: Optional[float] = None, roupa: Optional[str] = None,
             pose: Optional[str] = None) -> Optional[int]:
    """Grava o post (ou story). None se esse acontecimento já tinha virado post desse autor."""
    rng = random.Random(f"ig:alcance:{autor}:{motivo_chave or now.isoformat()}")
    alcance = alcance if alcance is not None else (rng.uniform(0.05, 0.11) if tipo == "feed" else 0)
    expira = (now + timedelta(hours=STORY_TTL_H)).isoformat() if tipo == "story" else None
    try:
        pid = _exec(db, """INSERT INTO ig_posts(autor,tipo,criado_em,expira_em,imagem,legenda,local,marcados_json,
                               motivo,motivo_chave,fonte,descricao,story_json,alcance,roupa,pose)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (autor, tipo, now.isoformat(), expira, imagem, legenda.strip(), local,
                     json.dumps(list(marcados)), motivo, motivo_chave, fonte, descricao,
                     json.dumps(story, ensure_ascii=False) if story else None, alcance, roupa, pose))
    except Exception as exc:
        if "UNIQUE" in str(exc):
            return None
        raise
    if autor == "marina" and tipo == "feed" and fonte != "acervo":
        _exec(db, """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                     autonomy_level,importance,participants_json,share_worthy,created_at)
                     VALUES (?,?,'instagram','Postou uma foto no Instagram',?,'simulated',1,0.3,?,0.5,?)""",
              (f"instagram:post:{pid}", now.isoformat(), f"Postou uma foto no Instagram: {legenda.strip() or descricao}",
               json.dumps(["marina", *marcados]), now.isoformat()))
    return pid


def comentar(db, post_id: int, autor: str, texto: str, at: datetime, *, pai_id: Optional[int] = None) -> int:
    return _exec(db, "INSERT INTO ig_comentarios(post_id,pai_id,autor,texto,criado_em) VALUES (?,?,?,?,?)",
                 (post_id, pai_id, autor, texto.strip(), at.isoformat()))


def post(db, pid: int) -> Optional[dict]:
    r = _rows(db, "SELECT * FROM ig_posts WHERE id=?", (pid,))
    return r[0] if r else None


def posts_feed(db, autor: str, now: datetime) -> list[dict]:
    return _rows(db, "SELECT * FROM ig_posts WHERE autor=? AND tipo='feed' AND criado_em<=? ORDER BY criado_em DESC",
                 (autor, now.isoformat()))


def ultimo_post(db, autor: str = "marina") -> Optional[dict]:
    r = _rows(db, "SELECT * FROM ig_posts WHERE autor=? AND tipo='feed' ORDER BY criado_em DESC LIMIT 1", (autor,))
    return r[0] if r else None


def stories_ativos(db, now: datetime, autor: Optional[str] = None) -> list[dict]:
    sql = "SELECT * FROM ig_posts WHERE tipo='story' AND criado_em<=? AND expira_em>?"
    args: tuple = (now.isoformat(), now.isoformat())
    if autor:
        sql += " AND autor=?"
        args += (autor,)
    return _rows(db, sql + " ORDER BY criado_em", args)


def comentarios(db, pid: int, now: datetime) -> list[dict]:
    return _rows(db, "SELECT * FROM ig_comentarios WHERE post_id=? AND criado_em<=? ORDER BY criado_em, id",
                 (pid, now.isoformat()))


def curtidas(p: dict, now: datetime) -> int:
    """Curtidas de fora sobem rápido nas primeiras horas e estabilizam (alcance × seguidores)."""
    criado = datetime.fromisoformat(p["criado_em"])
    horas = max(0.0, (now - criado).total_seconds() / 3600)
    seg = PERFIS.get(p["autor"], {}).get("seguidores", 800)
    base = seg * float(p.get("alcance") or 0.08) * (1 - math.exp(-horas / 4))
    n = int(round(base)) + (1 if p.get("curtido_patrick_em") else 0)
    if p["autor"] != "marina" and p.get("curtido_marina_em"):
        n += 1
    return n


# ------------------------------------------------------ fotos do chat (grátis) --
def guardar_foto_do_chat(db, dados: bytes, now: datetime, *, descricao: str = "", pose: str = "",
                         lugar: str = "") -> Optional[int]:
    """Foto vestida que ela mandou pro Patrick: fica guardada pra ela poder postar (Patrick, 27/09: misto)."""
    try:
        nome = salvar_imagem(dados, "c")
    except OSError:
        logger.exception("instagram.foto_chat.erro")
        return None
    return _exec(db, "INSERT INTO ig_fotos_chat(criado_em,imagem,descricao,pose,lugar) VALUES (?,?,?,?,?)",
                 (now.isoformat(), nome, descricao, pose, lugar))


def fotos_chat_livres(db, now: datetime, horas: float) -> list[dict]:
    return _rows(db, """SELECT * FROM ig_fotos_chat WHERE usada_em IS NULL AND criado_em>=? AND criado_em<=?
                        ORDER BY criado_em DESC""", ((now - timedelta(hours=horas)).isoformat(), now.isoformat()))


def usar_foto_chat(db, fid: int, now: datetime) -> None:
    _exec(db, "UPDATE ig_fotos_chat SET usada_em=? WHERE id=?", (now.isoformat(), fid))


# ---------------------------------------------------------------- motivos --
def _place_key(db, nome: str) -> str:
    r = _rows(db, "SELECT canonical_key FROM world_places WHERE name=? LIMIT 1", (nome,))
    return r[0]["canonical_key"] if r else ""


def _participantes(raw) -> list[str]:
    try:
        return [p for p in json.loads(raw or "[]") if p != "marina"]
    except (TypeError, ValueError):
        return []


def motivos(db, now: datetime, horas: float = 30) -> list[dict]:
    """O que aconteceu de verdade e pede post (um por tipo por dia), do mais forte pro mais fraco."""
    from civitai_images import FRIEND_RG
    from social_day import short_name
    rows = _rows(db, """SELECT event_key, event_at, event_type, title, summary, participants_json FROM life_events
                        WHERE event_at>=? AND event_at<=? ORDER BY event_at""",
                 ((now - timedelta(hours=horas)).isoformat(), now.isoformat()))
    usados = {r["motivo_chave"] for r in _rows(db, "SELECT motivo_chave FROM ig_posts WHERE autor='marina'")}
    out: dict[tuple, dict] = {}

    def add(m: dict) -> None:
        if m["chave"] in usados:
            return
        k = (m["motivo"], m["at"][:10])
        if k not in out or out[k]["peso"] < m["peso"]:
            out[k] = m

    for r in rows:
        key, tipo, title, s = r["event_key"], r["event_type"], r["title"] or "", r["summary"] or ""
        base = {"chave": key, "at": r["event_at"], "local": "", "place_key": "", "amiga": ""}
        if tipo == "social_contact" and key.endswith(":saida"):
            m = re.match(r"Encontrou (?:a|o) .+? \(([^)]+)\)", s)
            lugar = m.group(1) if m else ""
            gente = _participantes(r["participants_json"])
            amiga = next((p for p in gente if p in FRIEND_RG), "")
            motivo = "praia" if "praia" in lugar.lower() else "role_amiga" if amiga else "role"
            quem = short_name(amiga or (gente[0] if gente else "")) or "uma amiga"
            add({**base, "motivo": motivo, "peso": PESO[motivo], "local": lugar, "place_key": _place_key(db, lugar),
                 "amiga": amiga, "descricao": f"você com {quem} no {lugar}" if lugar else f"você com {quem}"})
        elif tipo == "social_contact" and key.endswith(":academia"):
            add({**base, "motivo": "treino", "peso": PESO["treino"], "descricao": "você no espelho da academia"})
        elif s.startswith("Cabelo na ") or s.startswith("Fez as unhas em gel") or title == "Fez as unhas em casa":
            motivo = "salao" if s.startswith("Cabelo") else "unhas"
            add({**base, "motivo": motivo, "peso": PESO[motivo],
                 "descricao": "o cabelo recém-feito" if motivo == "salao" else "as unhas recém-feitas"})
        elif tipo == "tempo_livre" and title.startswith("Montando looks"):
            add({**base, "motivo": "look", "peso": PESO["look"], "descricao": "um look que você montou no closet"})
        elif tipo == "routine" and key.startswith("milo:") and "passe" in s.lower():
            add({**base, "motivo": "milo", "peso": PESO["milo"], "descricao": "o Milo no passeio"})
    for f in fotos_chat_livres(db, now, horas):
        add({"chave": f"chat:{f['id']}", "at": f["criado_em"], "motivo": "chat", "peso": PESO["chat"],
             "local": f["lugar"], "place_key": "", "amiga": "", "descricao": f["descricao"], "foto_chat": f["id"]})
    if not out:
        # hora fixa do dia (10h): com "agora" a espera de 20–120 min nunca acabava
        add({"chave": f"vista:{now:%Y-%m-%d}", "at": now.replace(hour=10, minute=0, second=0, microsecond=0).isoformat(),
             "motivo": "vista", "peso": PESO["vista"],
             "local": "Botafogo, Rio de Janeiro", "place_key": "", "amiga": "", "descricao": "uma selfie sua em casa"})
    return sorted(out.values(), key=lambda m: -m["peso"])


def _dias_sem_postar(db, now: datetime) -> float:
    ult = ultimo_post(db)
    if not ult:
        return 3.0
    return (now - datetime.fromisoformat(ult["criado_em"])).total_seconds() / 86400


def vontade(db, now: datetime, motivo: dict, feeling) -> float:
    """27/09 (decisão dela pelo sentimento): motivo forte + dias sem postar + como ela está. Triste não posta."""
    v = motivo["peso"] + min(_dias_sem_postar(db, now), 6) * 0.1
    if feeling is not None:
        v += (getattr(feeling, "valence", 0.6) - 0.6) * 1.0 + (getattr(feeling, "energy", 0.5) - 0.5) * 0.3
    return v


def _na_janela(now: datetime) -> bool:
    ini, fim = JANELA_POST
    t = now.time()
    return t >= ini or t <= fim


def plano_post(db, now: datetime, m: Momento) -> Optional[dict]:
    """Ela posta agora? Devolve o plano (motivo, foto do chat ou pose da foto nova) ou None."""
    if m.fone not in ("alto", "insta") or m.patrick_ativo or not _na_janela(now):
        return None
    ult = ultimo_post(db)
    if ult and now - datetime.fromisoformat(ult["criado_em"]) < timedelta(hours=FEED_GAP_H):
        return None
    for mot in motivos(db, now):
        if vontade(db, now, mot, m.feeling) < LIMIAR:
            continue
        rng = random.Random(f"ig:post:{mot['chave']}")
        quando = datetime.fromisoformat(mot["at"]) + timedelta(minutes=rng.randint(20, 120))
        if now < quando:
            continue
        plano = dict(mot)
        foto = mot.get("foto_chat") or _foto_chat_do_motivo(db, now, mot)
        if foto:
            plano.update(fonte="chat", foto_chat=foto)
        else:
            pose = escolher_pose(db, mot["motivo"], rng, mot.get("amiga", ""))
            from photo_director import GROUP_POSES
            plano.update(fonte="grupo" if pose in GROUP_POSES else "nova", pose=pose)
        return plano
    return None


def _foto_chat_do_motivo(db, now: datetime, mot: dict) -> Optional[int]:
    """Uma foto que ela mandou no chat no mesmo lugar e perto da hora do acontecimento serve de post."""
    at = datetime.fromisoformat(mot["at"])
    for f in fotos_chat_livres(db, now, 36):
        perto = abs((datetime.fromisoformat(f["criado_em"]) - at).total_seconds()) < 3 * 3600
        if perto and mot.get("local") and f["lugar"] and f["lugar"].lower() in mot["local"].lower():
            return f["id"]
    return None


# ------------------------------------------------------------------ stories --
def plano_story(db, now: datetime, m: Momento) -> Optional[dict]:
    """Story sem foto nova: a música que está tocando, uma foto que ela acabou de mandar no chat, ou texto."""
    if m.fone not in ("alto", "insta", "medio") or not _na_janela(now):
        return None
    meus = _rows(db, "SELECT * FROM ig_posts WHERE autor='marina' AND tipo='story' AND criado_em>=? ORDER BY criado_em",
                 ((now - timedelta(hours=24)).isoformat(),))
    if len(meus) >= STORY_MAX_DIA or (meus and now - datetime.fromisoformat(meus[-1]["criado_em"])
                                      < timedelta(hours=STORY_GAP_H)):
        return None
    valence = getattr(m.feeling, "valence", 0.6) if m.feeling is not None else 0.6
    if valence < 0.45:
        return None                              # pra baixo, não posta story
    b = m.bloco
    if b is not None and getattr(b, "faixas", None):
        from musica import Musica
        f = Musica.tocando(b.faixas, now)
        chave = f"musica:{getattr(b, 'chave', '')}:{now:%Y-%m-%d}"
        if f and not _rows(db, "SELECT 1 FROM ig_posts WHERE motivo_chave=?", (chave,)):
            return {"tipo": "musica", "chave": chave, "faixa": f}
    for f in fotos_chat_livres(db, now, 4):
        return {"tipo": "foto", "chave": f"chatstory:{f['id']}", "foto_chat": f["id"], "descricao": f["descricao"]}
    if valence >= 0.78 and not any(json.loads(s.get("story_json") or "{}").get("tipo") == "texto"
                                   for s in _rows(db, "SELECT story_json FROM ig_posts WHERE autor='marina' "
                                                      "AND tipo='story' AND criado_em>=?",
                                                  ((now - timedelta(hours=48)).isoformat(),))):
        return {"tipo": "texto", "chave": f"texto:{now:%Y-%m-%d}"}
    return None


FUNDOS = ("#E1306C", "#833AB4", "#F77737", "#262626", "#3F729B", "#C13584")


def publicar_story(db, now: datetime, plano: dict, *, texto: str = "", capa: str = "") -> Optional[int]:
    if plano["tipo"] == "musica":
        f = plano["faixa"]
        story = {"tipo": "musica", "nome": f.get("nome", ""), "artista": f.get("artista", ""), "capa": capa}
        return publicar(db, autor="marina", now=now, tipo="story", motivo="musica", motivo_chave=plano["chave"],
                        fonte="musica", descricao=f"a música \"{f.get('nome')}\" ({f.get('artista')}) tocando",
                        story=story, legenda=texto)
    if plano["tipo"] == "foto":
        f = _rows(db, "SELECT * FROM ig_fotos_chat WHERE id=?", (plano["foto_chat"],))[0]
        usar_foto_chat(db, f["id"], now)
        return publicar(db, autor="marina", now=now, tipo="story", imagem=f["imagem"], motivo="chat",
                        motivo_chave=plano["chave"], fonte="chat", descricao=f["descricao"], legenda=texto)
    fundo = random.Random(plano["chave"]).choice(FUNDOS)
    return publicar(db, autor="marina", now=now, tipo="story", motivo="texto", motivo_chave=plano["chave"],
                    fonte="texto", descricao=f"um story de texto: {texto}", story={"tipo": "texto", "fundo": fundo},
                    legenda=texto)


# ------------------------------------------------------------ amigas postam --
TEMAS = {   # (tema, cena pro Krea 2 em inglês, a foto em português pro texto)
    "bia_andrade": (("festa", "dancing at a crowded night party in Lapa, colorful club lights, a drink in her hand",
                     "ela dançando numa festa na Lapa, com um drink na mão"),
                    ("praia", "at Ipanema beach at sunset, wearing a black bikini top and a sarong, sand and sea behind",
                     "ela na praia de Ipanema no pôr do sol"),
                    ("espelho", "a mirror selfie in her bedroom in Laranjeiras, wearing an all-black going-out outfit",
                     "selfie no espelho de roupa preta de sair")),
    "carol_menezes": (("treino", "a mirror selfie at the gym after training, wearing a ribbed crop top and "
                                 "high-waisted leggings, hair in a high ponytail",
                       "selfie no espelho da academia depois do treino"),
                      ("comida", "at a cafe table in Botafogo with a colorful healthy bowl, smiling at the camera",
                       "ela num café de Botafogo com um bowl colorido"),
                      ("corrida", "on the Aterro do Flamengo running path in the morning, workout clothes",
                       "ela correndo no Aterro do Flamengo de manhã")),
    "julia_azevedo": (("expo", "at an art exhibition in a white gallery in Rio, looking at a large photograph",
                       "ela numa exposição de fotografia"),
                      ("camera", "holding a vintage 35 mm film camera on a street in Jardim Botânico, soft daylight",
                       "ela com a câmera analógica na rua, no Jardim Botânico"),
                      ("cafe", "at a cozy cafe window with a sketchbook and a coffee, afternoon light",
                       "ela desenhando no caderno num café, com um café do lado")),
    "theo_martins": (("look", "a full-body mirror selfie showing a stylish fashion-forward outfit with wide trousers "
                              "and a statement jacket", "selfie no espelho mostrando o look (calça larga e jaqueta)"),
                     ("festa", "at a rooftop party at night in Rio, city lights behind, laughing",
                      "ele rindo numa festa num rooftop à noite"),
                     ("carro", "leaning on his car on a street in Glória at golden hour, sunglasses on",
                      "ele encostado no carro na Glória, fim de tarde, de óculos escuros")),
}
PESO_AMIGA = {"bia_andrade": 3, "theo_martins": 2, "carol_menezes": 2, "julia_azevedo": 2}


def plano_amiga(db, now: datetime) -> Optional[dict]:
    """~2 posts por semana somando as quatro: sorteio do dia, hora de gente acordada, uma por dia no máximo."""
    dia = now.date()
    rng = random.Random(f"ig:amiga:{dia.isoformat()}")
    if rng.random() >= AMIGA_POSTA_DIA:
        return None
    at = datetime.combine(dia, time(rng.randint(11, 21), rng.choice((0, 15, 30, 45))))
    if now < at or now - at > timedelta(hours=3):
        return None
    chave = f"amiga:{dia.isoformat()}"
    if _rows(db, "SELECT 1 FROM ig_posts WHERE motivo_chave=?", (chave,)):
        return None
    # a foto de grupo do rolê com a Marina (sem custo), se for de ontem ou hoje
    grupo = _rows(db, """SELECT * FROM ig_posts WHERE autor='marina' AND tipo='feed' AND fonte='grupo'
                         AND criado_em>=? ORDER BY criado_em DESC LIMIT 1""", ((now - timedelta(hours=30)).isoformat(),))
    if grupo:
        marcadas = [a for a in json.loads(grupo[0]["marcados_json"] or "[]") if a in AMIGAS]
        if marcadas and not _rows(db, "SELECT 1 FROM ig_posts WHERE autor=? AND imagem=?",
                                  (marcadas[0], grupo[0]["imagem"])):
            return {"amiga": marcadas[0], "chave": chave, "fonte": "grupo", "imagem": grupo[0]["imagem"],
                    "local": grupo[0]["local"], "descricao": f"ela com a Marina ({grupo[0]['descricao']})"}
    amiga = rng.choices(list(PESO_AMIGA), weights=list(PESO_AMIGA.values()))[0]
    tema, cena, foto = rng.choice(TEMAS[amiga])
    return {"amiga": amiga, "chave": chave, "fonte": "nova", "tema": tema, "cena": cena, "local": "",
            "descricao": foto}


# ------------------------------------------------- comentários das amigas --
def quem_comenta(pid: int, marcados: list[str], rng: Optional[random.Random] = None) -> list[str]:
    rng = rng or random.Random(f"ig:quem:{pid}")
    out = [a for a in marcados if a in AMIGAS]
    out += [a for a, p in COMENTA.items() if a not in out and rng.random() < p]
    out += rng.sample(DE_FORA, rng.randint(0, 2))
    return out


def agendar_comentarios(db, pid: int, now: datetime, textos: dict[str, str]) -> None:
    """Os comentários chegam espalhados: a marcada em minutos, o resto ao longo do dia (de madrugada, não)."""
    p = post(db, pid)
    marcados = json.loads(p["marcados_json"] or "[]")
    rng = random.Random(f"ig:quando:{pid}")
    for autor, texto in textos.items():
        if not texto:
            continue
        minutos = rng.randint(4, 40) if autor in marcados else rng.randint(12, 8 * 60)
        at = now + timedelta(minutes=minutos)
        if at.hour < 8 and at.date() >= now.date():
            at = at.replace(hour=8) + timedelta(minutes=rng.randint(0, 90))
        comentar(db, pid, autor, texto, at)


def pedido_comentarios(db, p: dict, autores: list[str]) -> str:
    """Prompt (texto interno) pra gerar os comentários de todo mundo de uma vez, em JSON."""
    from social_day import short_name
    dona = "da Marina (@masalles)" if p["autor"] == "marina" else f"de {short_name(p['autor'])}"
    linhas = []
    for a in autores:
        if a in QUEM_ESCREVE:
            linhas.append(f"- \"{a}\": {QUEM_ESCREVE[a]}.{_nao_repita(db, a)}")
        else:
            linhas.append(f"- \"{a}\": seguidor(a) de fora, conhece de vista; comentário curtinho")
    return (f"Post no Instagram {dona}. A foto: {_foto_pros_outros(p)}. Legenda: \"{p['legenda']}\"."
            + (f" Local: {p['local']}." if p["local"] else "")
            + " Escreva o comentário de cada pessoa abaixo, como gente de verdade comenta no Instagram de uma "
              "amiga: curto (2 a 12 palavras), português informal, no máximo 1 emoji e só se ela usaria, sem "
              "hashtag. Cada um reage a algo diferente e concreto desta foto, desta legenda ou da vida delas; "
              "o jeito da pessoa aparece em como ela escreve, não em assunto fixo. Ninguém repete o que o outro "
              "disse nem o que já escreveu antes. O Patrick (@ptkramos) é o namorado da Marina; dá pra citar ele "
              "de vez em quando, não sempre.\n" + "\n".join(linhas)
            + "\nResponda só com um JSON: {\"chave\": \"comentário\", ...}")


def resposta_json(texto: str) -> dict[str, str]:
    m = re.search(r"\{.*\}", texto or "", re.DOTALL)
    try:
        data = json.loads(m.group(0)) if m else {}
    except (TypeError, ValueError):
        return {}
    return {str(k): _limpa(str(v)) for k, v in data.items() if isinstance(v, (str, int, float)) and str(v).strip()}


# ------------------------------------------------------------ ela olha o Insta --
VISTO_KEY = "ig_visto_json"


def _visto(db) -> dict:
    try:
        return json.loads(db.get_estado_relacional(VISTO_KEY) or "{}")
    except (TypeError, ValueError):
        return {}


def _guardar_visto(db, st: dict) -> None:
    db.set_estado_relacional(VISTO_KEY, json.dumps(st, ensure_ascii=False))


def olha_agora(db, now: datetime, m: Momento) -> bool:
    """Ela abre o Insta: no bloco do Instagram sempre; com o celular na mão, de tempos em tempos (logo depois
    de postar, mais vezes — fica vendo as curtidas)."""
    if not m.fone:
        return False
    ult = _visto(db).get("ultima")
    passou = (now - datetime.fromisoformat(ult)).total_seconds() / 60 if ult else 10 ** 6
    if m.fone == "insta":
        return passou >= 20
    meu = ultimo_post(db)
    recente = meu and now - datetime.fromisoformat(meu["criado_em"]) < timedelta(hours=3)
    gap = OLHA_GAP_MIN["depois_de_postar"] if recente and m.fone == "alto" else OLHA_GAP_MIN[m.fone]
    return passou >= gap


def novidades(db, now: datetime) -> dict:
    """O que ela ainda não viu: comentários nos posts dela, curtida do Patrick, posts das amigas, story curtido."""
    n = now.isoformat()
    coment = _rows(db, """SELECT c.*, p.descricao, p.legenda, p.autor AS dono FROM ig_comentarios c
                          JOIN ig_posts p ON p.id=c.post_id
                          WHERE c.visto_marina_em IS NULL AND c.criado_em<=? AND c.autor!='marina'
                            AND (p.autor='marina' OR c.autor='patrick' OR c.pai_id IN
                                 (SELECT id FROM ig_comentarios WHERE autor='marina'))
                          ORDER BY c.criado_em""", (n,))
    curtidas_dele = _rows(db, """SELECT * FROM ig_posts WHERE autor='marina' AND curtido_patrick_em IS NOT NULL
                                 AND curtido_patrick_em<=? AND visto_marina_em IS NULL""", (n,))
    das_amigas = _rows(db, """SELECT * FROM ig_posts WHERE autor!='marina' AND tipo='feed' AND criado_em<=?
                              AND visto_marina_em IS NULL""", (n,))
    return {"comentarios": coment, "curtidas": curtidas_dele, "amigas": das_amigas}


def marina_olha(db, now: datetime, fala: Callable[[str], str], rng: Optional[random.Random] = None) -> list[str]:
    """Ela abriu o Insta: vê, curte, responde. Devolve o que ela viu (vai pro prompt como fato)."""
    from social_day import short_name
    rng = rng or random.Random(f"ig:olha:{now.isoformat()}")
    nov = novidades(db, now)
    vistos: list[str] = []
    n = now.isoformat()
    respostas = 0
    for c in nov["comentarios"]:
        quem = "o Patrick" if c["autor"] == "patrick" else short_name(c["autor"]) if c["autor"] in AMIGAS \
            else f"@{c['autor']}"
        onde = f"na sua foto ({c['descricao']})" if c["dono"] == "marina" else f"no post de {short_name(c['dono'])}"
        _exec(db, "UPDATE ig_comentarios SET visto_marina_em=? WHERE id=?", (n, c["id"]))
        curte = c["autor"] == "patrick" or c["autor"] in AMIGAS or rng.random() < 0.5
        if curte:
            _exec(db, "UPDATE ig_comentarios SET curtido_marina_em=? WHERE id=?", (n, c["id"]))
        responde = c["autor"] == "patrick" or (c["autor"] in AMIGAS and respostas < 2 and rng.random() < 0.35)
        linha = f"{quem} comentou \"{c['texto']}\" {onde}"
        if responde:
            texto = _limpa(fala(
                f"Você abriu o Instagram e viu que {quem} comentou \"{c['texto']}\" {onde}"
                + (f" (legenda: \"{c['legenda']}\")" if c["legenda"] else "")
                + ". Escreva só a sua resposta a esse comentário, como você responderia no Instagram: curtinha "
                  "(até 10 palavras), sem aspas, sem @, no máximo 1 emoji." + _nao_repita(db, "marina")))
            if texto:
                comentar(db, c["post_id"], "marina", texto, now + timedelta(minutes=rng.randint(1, 3)),
                         pai_id=c["pai_id"] or c["id"])
                respostas += 1
                linha += f"; você respondeu \"{texto}\""
        vistos.append(linha)
    for p in nov["curtidas"]:
        _exec(db, "UPDATE ig_posts SET visto_marina_em=? WHERE id=?", (n, p["id"]))
        vistos.append(f"o Patrick curtiu sua foto ({p['descricao']})")
    for p in nov["amigas"]:
        _exec(db, "UPDATE ig_posts SET visto_marina_em=?, curtido_marina_em=? WHERE id=?", (n, n, p["id"]))
        linha = f"{short_name(p['autor'])} postou uma foto ({p['descricao']}) e você curtiu"
        if rng.random() < 0.5:
            texto = _limpa(fala(
                f"Você abriu o Instagram e viu que {short_name(p['autor'])} postou uma foto: {p['descricao']}"
                + (f", legenda \"{p['legenda']}\"" if p["legenda"] else "")
                + ". Escreva só o seu comentário no post dela, curtinho (até 8 palavras), do jeito que você fala "
                  "com ela, sem aspas, no máximo 1 emoji." + _nao_repita(db, "marina")))
            if texto:
                comentar(db, p["id"], "marina", texto, now + timedelta(minutes=rng.randint(1, 4)))
                linha += f" e comentou \"{texto}\""
        vistos.append(linha)
    for s in _rows(db, """SELECT * FROM ig_posts WHERE autor='marina' AND tipo='story' AND curtido_patrick_em<=?
                          AND visto_marina_em IS NULL""", (n,)):
        _exec(db, "UPDATE ig_posts SET visto_marina_em=? WHERE id=?", (n, s["id"]))
        vistos.append(f"o Patrick curtiu seu story ({s['descricao']})")
    st = _visto(db)
    st["ultima"] = n
    st["log"] = [x for x in st.get("log", []) if x["at"] >= (now - timedelta(hours=24)).isoformat()]
    st["log"] += [{"at": n, "txt": v} for v in vistos]
    _guardar_visto(db, st)
    return vistos


def _limpa(txt: str) -> str:
    txt = (txt or "").strip().strip("\"'“”‘’").strip()
    txt = re.sub(r"^@\S+\s*", "", txt)
    return txt.split("\n")[0][:220]


# --------------------------------------------------------------- prompt dela --
def prompt_lines(db, now: datetime) -> list[str]:
    """O Instagram dela como fato: o último post, os stories de hoje e o que ela viu nas últimas 24 h."""
    try:
        ult = ultimo_post(db)
        linhas = []
        if ult and now - datetime.fromisoformat(ult["criado_em"]) < timedelta(days=4):
            quando = datetime.fromisoformat(ult["criado_em"])
            dia = "hoje" if quando.date() == now.date() else "ontem" if (now.date() - quando.date()).days == 1 \
                else f"há {(now.date() - quando.date()).days} dias"
            linhas.append(f"- Seu último post ({dia}, {quando:%H:%M}): {ult['descricao']}; legenda \"{ult['legenda']}\"; "
                          f"{curtidas(ult, now)} curtidas.")
        for s in stories_ativos(db, now, "marina"):
            linhas.append(f"- Story no ar ({datetime.fromisoformat(s['criado_em']):%H:%M}): {s['descricao']}.")
        for x in _visto(db).get("log", []):
            if x["at"] >= (now - timedelta(hours=24)).isoformat():
                linhas.append(f"- {datetime.fromisoformat(x['at']):%H:%M} você viu no Instagram: {x['txt']}.")
        if not linhas:
            return []
        return (["[SEU INSTAGRAM (@masalles) — aconteceu de verdade]"] + linhas +
                ["  (Você viu isso no app, não foi aviso. Se vier ao caso, puxe com ele do seu jeito; não invente "
                 "post, curtida ou comentário que não está aqui.)"])
    except Exception:
        logger.exception("instagram.prompt_lines")
        return []


# -------------------------------------------------------- o Patrick no app --
PATRICK_VIU_KEY = "ig_patrick_viu_feed"


def feed_novo(db, now: datetime) -> bool:
    """Bolinha no ícone: post ou story novo desde a última vez que ele abriu."""
    viu = db.get_estado_relacional(PATRICK_VIU_KEY) or ""
    r = _rows(db, "SELECT 1 FROM ig_posts WHERE criado_em<=? AND criado_em>? AND (expira_em IS NULL OR expira_em>?) "
                  "LIMIT 1", (now.isoformat(), viu, now.isoformat()))
    return bool(r)


def patrick_abriu(db, now: datetime) -> None:
    db.set_estado_relacional(PATRICK_VIU_KEY, now.isoformat())


def curtir_post(db, pid: int, now: datetime, on: bool) -> None:
    _exec(db, "UPDATE ig_posts SET curtido_patrick_em=?, visto_marina_em=NULL WHERE id=?",
          (now.isoformat() if on else None, pid))


def curtir_comentario(db, cid: int, now: datetime, on: bool) -> None:
    _exec(db, "UPDATE ig_comentarios SET curtido_patrick_em=? WHERE id=?", (now.isoformat() if on else None, cid))


def resposta_de_amiga(db, pid: int, cid: int, rng: Optional[random.Random] = None) -> Optional[str]:
    """Quando o Patrick comenta, às vezes uma amiga entra na conversa (a marcada, ou a Bia)."""
    rng = rng or random.Random(f"ig:entra:{cid}")
    p = post(db, pid)
    if not p or p["autor"] != "marina" or rng.random() >= 0.35:
        return None
    marcadas = [a for a in json.loads(p["marcados_json"] or "[]") if a in AMIGAS]
    return marcadas[0] if marcadas else "bia_andrade"
