"""Acervo inicial do Instagram (27/09, decidido com o Patrick: "9 fotos de acervo geradas").

Roda na VPS (as fotos ficam em data/instagram/ e os posts no banco de lá):
    venv/bin/python scripts/instagram_acervo.py              # mostra o plano e o custo, não gera nada
    venv/bin/python scripts/instagram_acervo.py --gerar      # gera o que falta (rodar de novo só completa)
    venv/bin/python scripts/instagram_acervo.py --refoto 5   # refaz a foto do post 5 (pose e roupa novas)
    venv/bin/python scripts/instagram_acervo.py --textos     # apaga e refaz legendas e comentários de todos
    venv/bin/python scripts/instagram_acervo.py --textos --incluir 6   # e também o post de verdade 6
    venv/bin/python scripts/instagram_acervo.py --trocar 7   # só a troca de rosto da amiga (quando ela falhou)
    venv/bin/python scripts/instagram_acervo.py --trocar 7 --base novo7c.jpg   # troca sobre uma foto de fora
    venv/bin/python scripts/instagram_acervo.py --colocar 7 --base foto.jpg    # põe uma foto já aprovada

- Foto de perfil da Ma (retrato vestido, recortado quadrado).
- 9 posts dela nos últimos ~2 meses e 2 de cada amiga (foto nova sobre o RG).
- 27/09 (Patrick): roupa sem repetir (guarda-roupa do Instagram), praia de biquíni, fora de casa quase sempre
  alguém tirando a foto; textos com a pessoa (não bordão) e o que ela já escreveu, pra não repetir.
Custo: ~20 Buzz por foto; foto com amiga ~61 (troca de rosto). Nada disso entra no Hoje (fonte "acervo").
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import instagram as ig  # noqa: E402

# (dias atrás, hora, motivo, pose, lugar, amiga, local, o que a foto mostra)
MARINA = (
    (2, "17:40", "vista", "varanda_parapeito", "", "", "Botafogo, Rio de Janeiro", "selfie sua na varanda com a enseada atrás"),
    (5, "22:10", "role_amiga", "fora_selfie_amiga_abraco", "quartinho_bar", "bia_andrade", "Quartinho Bar",
     "você e a Bia abraçadas no Quartinho Bar"),
    (9, "16:20", "look", "closet_look_andando", "", "", "", "você desfilando o look no closet"),
    (13, "08:50", "milo", "pov_milo_rua", "enseada_botafogo", "", "Enseada de Botafogo", "o Milo no passeio da manhã"),
    (18, "12:30", "puc", "fora_amiga_encostada", "puc_rio", "", "PUC-Rio",
     "você na PUC entre uma aula e outra, uma amiga tirando"),
    (24, "11:15", "praia", "fora_amigas_alguem_tirando", "ipanema_beach", "carol_menezes", "Praia de Ipanema",
     "você e a Carol de biquíni na praia de Ipanema"),
    (31, "20:05", "look", "espelho_corpo", "", "", "", "você no espelho do closet pronta pra sair"),
    (40, "15:30", "cafe", "fora_amiga_sentada", "starbucks_shopping_gavea", "", "Starbucks Shopping da Gávea",
     "você sentada com o café gelado no Starbucks da Gávea, uma amiga tirando"),
    (52, "19:00", "unhas", "pov_unhas", "", "", "", "a sua mão com as unhas recém-feitas"),
)
# (amiga, índice do tema em instagram.TEMAS, dias atrás, hora)
AMIGAS = (("bia_andrade", 1, 7, "18:10"), ("bia_andrade", 2, 33, "21:40"),
          ("theo_martins", 2, 11, "17:20"), ("theo_martins", 0, 38, "19:30"),
          ("carol_menezes", 0, 4, "07:40"), ("carol_menezes", 1, 27, "13:10"),
          ("julia_azevedo", 1, 15, "16:00"), ("julia_azevedo", 2, 45, "15:10"))


def quando(dias: int, hora: str, hoje: datetime) -> datetime:
    h, m = map(int, hora.split(":"))
    return (hoje - timedelta(days=dias)).replace(hour=h, minute=m, second=0, microsecond=0)


def llm(prompt: str, max_tokens: int = 300) -> str:
    from openai import OpenAI
    from config import settings
    from llm_options import llm_kwargs
    cli = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
    res = cli.chat.completions.create(model=settings.LLM_MODEL, messages=[{"role": "user", "content": prompt}],
                                      **llm_kwargs(max_tokens, model=settings.LLM_MODEL), temperature=0.9)
    return (res.choices[0].message.content or "").strip()


async def foto_marina(db, n: int, at: datetime, pose: str = ""):
    """A foto do post n do acervo dela: pose do plano (ou a pedida), roupa do guarda-roupa sem repetir."""
    import photo_director
    from photo_director import HOME
    from sd_client import sd_client
    _, _, motivo, pose_plano, lugar, amiga, _, _ = MARINA[n]
    rng = random.Random(f"acervo:marina:{n}:{pose or pose_plano}:{datetime.now():%H%M}")
    ctx = SimpleNamespace(place_key=lugar or HOME, presence_assertable=True,
                          present_people=(amiga,) if amiga else (), activity="", sublocation="", weather=None,
                          snapshot_id=None)
    ocasiao = ig.ocasiao_da_roupa(motivo, at.hour)
    roupa = ig.escolher_roupa(db, ocasiao, rng) if ocasiao else None
    dela = ig.escolher_roupa(db, ocasiao, rng, evitar=(roupa,), simples=True) if ocasiao and amiga else None
    shot = photo_director.direct(db, at, camera_ctx=ctx, turn=SimpleNamespace(state="cut", arousal=0.0), rng=rng,
                                 force_pose=pose or pose_plano, outfit_override=roupa, friend_outfit_override=dela,
                                 expression_override="a natural confident smile, looking great for an Instagram post")
    gen = await sd_client.generate_directed(shot)
    return shot, gen.image


def textos_do_post(db, p: dict, rng: random.Random, *, legenda: bool = True, ja: frozenset = frozenset()) -> None:
    """Legenda (com a memória de quem posta) e comentários no passado, logo depois do post."""
    pid, at = p["id"], datetime.fromisoformat(p["criado_em"])
    if legenda:
        foto = p["descricao"] + (f" (roupa: {p['roupa']})" if p.get("roupa") else "")
        nova = ig._limpa(llm(ig.pedido_legenda(db, p["autor"], foto, p["local"], rng=rng,
                                               quando=ig.quando_foi(ig.momento_do_post(db, p), at)), 80))
        ig._exec(db, "UPDATE ig_posts SET legenda=? WHERE id=?", (nova, pid))
        p = ig.post(db, pid)
    marcados = json.loads(p["marcados_json"] or "[]")
    if p["autor"] == "marina":
        autores = ig.quem_comenta(pid, marcados, rng)
    else:
        autores = [a for a in ig.AMIGAS if a != p["autor"] and rng.random() < 0.4] + rng.sample(ig.DE_FORA, rng.randint(0, 1))
        if rng.random() < 0.6:
            autores.append("marina")
    autores = [a for a in autores if a not in ja]   # quem já tem comentário mantido no post não comenta de novo
    textos = ig.resposta_json(llm(ig.pedido_comentarios(db, p, autores)))
    respostas = 0
    for autor in autores:
        texto = textos.get(autor, "")
        if not texto:
            continue
        c_at = at + timedelta(minutes=rng.randint(3, 300))
        cid = ig.comentar(db, pid, autor, texto, c_at)
        ig._exec(db, "UPDATE ig_comentarios SET visto_marina_em=?, curtido_marina_em=? WHERE id=?",
                 (c_at.isoformat(), c_at.isoformat() if autor in ig.AMIGAS else None, cid))
        if p["autor"] == "marina" and autor in ig.AMIGAS and respostas < 2 and rng.random() < 0.35:
            quem = ig.PERFIS[autor]["nome"].split()[0]
            resp = ig._limpa(llm(f"Quem responde: {ig.QUEM_ESCREVE['marina']}. Na sua foto ({p['descricao']}; "
                                 f"legenda \"{p['legenda']}\"), {quem} comentou \"{texto}\". Escreva só a sua "
                                 "resposta, curtinha (até 8 palavras), caixa baixa, sem ponto final nem exclamação, sem @, no "
                                 "máximo 1 emoji ou só emoji; carinho de amiga, sem flerte."
                                 + ig._nao_repita(db, "marina"), 80))
            if resp:
                ig.comentar(db, pid, "marina", resp, c_at + timedelta(minutes=rng.randint(5, 90)), pai_id=cid)
                respostas += 1
    n = at.isoformat()
    ig._exec(db, "UPDATE ig_posts SET visto_marina_em=?, curtido_marina_em=? WHERE id=?", (n, n, pid))


async def refoto(db, pid: int, pose: str) -> None:
    import civitai_images
    p = ig.post(db, pid)
    chave = p["motivo_chave"] or ""
    at = datetime.fromisoformat(p["criado_em"])
    if chave.startswith("acervo:marina:"):
        n = int(chave.rsplit(":", 1)[1])
        shot, img = await foto_marina(db, n, at, pose)
        if not img:
            print("falhou")
            return
        nome = ig.salvar_imagem(img.getvalue())
        ig._exec(db, "UPDATE ig_posts SET imagem=?, roupa=?, pose=?, marcados_json=?, descricao=? WHERE id=?",
                 (nome, shot.outfit, shot.pose_id, json.dumps([shot.friend] if shot.friend else []),
                  MARINA[n][7], pid))
    else:
        amiga, tema_i = next((a, t) for i, (a, t, _, _) in enumerate(AMIGAS) if chave == f"acervo:{a}:{i}")
        dados = await civitai_images.friend_scene(amiga, ig.TEMAS[amiga][tema_i][1])
        if not dados:
            print("falhou")
            return
        nome = ig.salvar_imagem(dados, "a")
        ig._exec(db, "UPDATE ig_posts SET imagem=? WHERE id=?", (nome, pid))
    print(f"FOTO {nome}")


async def trocar(db, pid: int, base: str = "") -> None:
    """Só a troca de rosto da amiga na foto que já está no post (quando a troca falhou e a foto ficou boa),
    ou numa foto de fora (--base arquivo: uma tentativa anterior de que o Patrick gostou)."""
    import civitai_images
    p = ig.post(db, pid)
    amiga = next((a for a in json.loads(p["marcados_json"] or "[]") if a in civitai_images.FRIEND_RG), "")
    if not amiga:
        print("post sem amiga de RG")
        return
    foto = Path(base).read_bytes() if base else ig.caminho(p["imagem"]).read_bytes()
    trocada = await civitai_images.swap_friend_face(foto, amiga)
    if not trocada:
        print("falhou")
        return
    nome = ig.salvar_imagem(trocada)
    ig._exec(db, "UPDATE ig_posts SET imagem=? WHERE id=?", (nome, pid))
    print(f"FOTO {nome}")


def colocar(db, pid: int, arquivo: str) -> None:
    """Põe no post uma foto já pronta (aprovada pelo Patrick fora do script), sem gerar nada."""
    nome = ig.salvar_imagem(Path(arquivo).read_bytes())
    ig._exec(db, "UPDATE ig_posts SET imagem=? WHERE id=?", (nome, pid))
    print(f"FOTO {nome}")


def conversas_do_patrick(db) -> set[int]:
    """Ids dos comentários das conversas em que o Patrick entrou (o comentário de cima e tudo embaixo dele)."""
    todos = {c["id"]: c["pai_id"] for c in ig._rows(db, "SELECT id, pai_id FROM ig_comentarios")}
    raizes = set()
    for c in ig._rows(db, "SELECT id FROM ig_comentarios WHERE autor='patrick'"):
        i = c["id"]
        while todos.get(i):
            i = todos[i]
        raizes.add(i)

    def raiz(i):
        while todos.get(i):
            i = todos[i]
        return i
    return {i for i in todos if raiz(i) in raizes}


def refazer_textos(db, incluir: tuple = ()) -> None:
    """Refaz legendas e comentários dos posts do acervo em ordem de data (a memória de não repetir vai se formando).
    27/09 (Patrick): post de verdade não é tocado (só os de --incluir), e conversa em que ele comentou fica inteira."""
    manter = conversas_do_patrick(db)
    marca = ",".join("?" * len(incluir)) or "NULL"
    onde = f"tipo='feed' AND (fonte='acervo' OR id IN ({marca}))"
    acervo = [p["id"] for p in ig._rows(db, f"SELECT id FROM ig_posts WHERE {onde}", tuple(incluir))]
    for pid in acervo:
        for c in ig._rows(db, "SELECT id FROM ig_comentarios WHERE post_id=?", (pid,)):
            if c["id"] not in manter:
                ig._exec(db, "DELETE FROM ig_comentarios WHERE id=?", (c["id"],))
    ig._exec(db, f"UPDATE ig_posts SET legenda='' WHERE {onde}", tuple(incluir))
    for p in ig._rows(db, f"SELECT * FROM ig_posts WHERE {onde} ORDER BY criado_em", tuple(incluir)):
        rng = random.Random(f"textos:{p['id']}")
        ja = frozenset(c["autor"] for c in ig._rows(db, "SELECT autor FROM ig_comentarios WHERE post_id=?", (p["id"],)))
        textos_do_post(db, p, rng, ja=ja)
        p = ig.post(db, p["id"])
        if p["fonte"] != "acervo":   # post de verdade: a linha do Hoje leva a legenda
            ig._exec(db, "UPDATE life_events SET summary=? WHERE event_key=?",
                     (f"Postou uma foto no Instagram: {p['legenda']}", f"instagram:post:{p['id']}"))
        print(f"{p['id']:>3} {p['autor']:<14} {p['legenda']}")
        for c in ig._rows(db, "SELECT autor, texto, pai_id FROM ig_comentarios WHERE post_id=? ORDER BY id", (p["id"],)):
            print(f"      {'  ↳ ' if c['pai_id'] else ''}{c['autor']}: {c['texto']}")


async def main(gerar: bool, usar: dict) -> None:
    from db import DatabaseManager
    from sd_client import sd_client
    import civitai_images
    db = DatabaseManager()
    hoje = datetime.now()
    feitos = {r["motivo_chave"] for r in ig._rows(db, "SELECT motivo_chave FROM ig_posts WHERE fonte='acervo'")}
    custo = 0
    avatar = ig.DIR / "avatar_marina.jpg"
    if not avatar.is_file():
        custo += 20
        print("foto de perfil da Ma")
        if gerar:
            recorte, _ = await sd_client.generate_avatar("classica")
            if recorte:
                ig.DIR.mkdir(parents=True, exist_ok=True)
                avatar.write_bytes(recorte.getvalue())
    for n, (dias, hora, motivo, pose, lugar, amiga, local, desc) in enumerate(MARINA):
        chave = f"acervo:marina:{n}"
        if chave in feitos:
            continue
        custo += 61 if amiga else 20
        at = quando(dias, hora, hoje)
        print(f"Ma {at:%d/%m %H:%M} {motivo} ({pose})")
        if not gerar:
            continue
        shot, img = await foto_marina(db, n, at)
        if not img:
            print("  falhou (rode de novo depois)")
            continue
        pid = ig.publicar(db, autor="marina", now=at, imagem=ig.salvar_imagem(img.getvalue()), local=local,
                          marcados=(shot.friend,) if shot.friend else (), motivo=motivo, motivo_chave=chave,
                          fonte="acervo", descricao=desc, roupa=shot.outfit, pose=shot.pose_id)
        textos_do_post(db, ig.post(db, pid), random.Random(chave))
    for n, (amiga, tema_i, dias, hora) in enumerate(AMIGAS):
        chave = f"acervo:{amiga}:{n}"
        if chave in feitos:
            continue
        tema, cena, foto = ig.TEMAS[amiga][tema_i]
        arquivo = usar.get(f"{amiga}:{tema}")
        custo += 0 if arquivo else 20
        at = quando(dias, hora, hoje)
        print(f"{amiga} {at:%d/%m %H:%M} {tema}")
        if not gerar:
            continue
        dados = Path(arquivo).read_bytes() if arquivo else await civitai_images.friend_scene(amiga, cena)
        if not dados:
            print("  falhou (rode de novo depois)")
            continue
        pid = ig.publicar(db, autor=amiga, now=at, imagem=ig.salvar_imagem(dados, "a"), motivo=tema,
                          motivo_chave=chave, fonte="acervo", descricao=foto)
        textos_do_post(db, ig.post(db, pid), random.Random(chave))
    print(f"custo {'gasto' if gerar else 'previsto'}: ~{custo} Buzz")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gerar", action="store_true")
    ap.add_argument("--usar", action="append", default=[], help="amiga:tema=arquivo (foto já gerada)")
    ap.add_argument("--refoto", type=int, help="id do post: refaz a foto")
    ap.add_argument("--pose", default="", help="com --refoto: pose do catálogo")
    ap.add_argument("--textos", action="store_true", help="apaga e refaz legendas e comentários")
    ap.add_argument("--incluir", type=int, action="append", default=[], help="com --textos: post de verdade a refazer junto")
    ap.add_argument("--trocar", type=int, help="id do post: só refaz a troca de rosto da amiga")
    ap.add_argument("--base", default="", help="com --trocar: a foto de partida (em vez da que está no post)")
    ap.add_argument("--colocar", type=int, help="id do post: põe a foto --base como está, sem gerar")
    a = ap.parse_args()
    if a.refoto or a.textos or a.trocar or a.colocar:
        from db import DatabaseManager
        banco = DatabaseManager()
        if a.colocar:
            colocar(banco, a.colocar, a.base)
        elif a.trocar:
            asyncio.run(trocar(banco, a.trocar, a.base))
        elif a.refoto:
            asyncio.run(refoto(banco, a.refoto, a.pose))
        else:
            refazer_textos(banco, tuple(a.incluir))
    else:
        asyncio.run(main(a.gerar, dict(x.split("=", 1) for x in a.usar)))
