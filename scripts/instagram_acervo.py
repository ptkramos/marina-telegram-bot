"""Acervo inicial do Instagram (27/09, decidido com o Patrick: "9 fotos de acervo geradas").

Roda UMA vez na VPS (as fotos ficam em data/instagram/ e os posts no banco de lá):
    venv/bin/python scripts/instagram_acervo.py            # mostra o plano e o custo, não gera nada
    venv/bin/python scripts/instagram_acervo.py --gerar    # gera o que falta (rodar de novo só completa)

- Foto de perfil da Ma (retrato vestido, recortado quadrado).
- 9 posts dela nos últimos ~2 meses (look, Milo, vista, PUC, rolê com a Bia, praia com a Carol, espelho, café,
  unhas), com legenda do jeito dela e comentários das amigas (e ela respondendo algumas).
- 2 posts de cada amiga (foto nova sobre o RG). Foto já gerada no teste pode entrar por --usar amiga=arquivo.
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

PERSONA = ("Você é a Marina Salles (@masalles), 20 anos, paulista morando em Botafogo, estudante de Design de Moda na "
           "PUC-Rio e modelo freelance, dona do Milo (um Shih Tzu). No Instagram você escreve curtinho, em caixa "
           "baixa, às vezes só um emoji, sem hashtag.")

# (dias atrás, hora, motivo, pose, lugar, amiga, roupa, local, o que a foto mostra)
MARINA = (
    (2, "17:40", "vista", "varanda_parapeito", "", "", "fora", "Botafogo, Rio de Janeiro",
     "selfie sua na varanda com a enseada atrás"),
    (5, "22:10", "role_amiga", "fora_selfie_amiga_abraco", "quartinho_bar", "bia_andrade", "sair", "Quartinho Bar",
     "você e a Bia abraçadas no Quartinho Bar"),
    (9, "16:20", "look", "closet_look_giro", "", "", "sair", "", "você girando pra mostrar o look no closet"),
    (13, "08:50", "milo", "pov_milo_rua", "enseada_botafogo", "", "", "Enseada de Botafogo", "o Milo no passeio da manhã"),
    (18, "12:30", "puc", "fora_selfie", "puc_rio", "", "fora", "PUC-Rio", "selfie sua na PUC entre uma aula e outra"),
    (24, "11:15", "praia", "fora_selfie_amiga", "ipanema_beach", "carol_menezes", "fora", "Praia de Ipanema",
     "você e a Carol na praia de Ipanema"),
    (31, "20:05", "look", "espelho_corpo", "", "", "sair", "", "você no espelho do closet pronta pra sair"),
    (40, "15:30", "cafe", "fora_selfie", "starbucks_shopping_gavea", "", "fora", "Starbucks Shopping da Gávea",
     "selfie sua com o café gelado no Starbucks da Gávea"),
    (52, "19:00", "unhas", "pov_unhas", "", "", "", "", "a sua mão com as unhas recém-feitas"),
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


def comentarios_do_acervo(db, pid: int, at: datetime, rng: random.Random) -> None:
    """Comentários das amigas (no passado, logo depois do post) e a Marina respondendo uma ou duas."""
    p = ig.post(db, pid)
    marcados = json.loads(p["marcados_json"] or "[]")
    autores = (ig.quem_comenta(pid, marcados) if p["autor"] == "marina"
               else [a for a in ig.AMIGAS if a != p["autor"] and rng.random() < 0.5] + ["marina"]
               + rng.sample(ig.DE_FORA, 1))
    pedido = ig.pedido_comentarios(p, [a for a in autores if a != "marina"])
    textos = ig.resposta_json(llm(pedido))
    if "marina" in autores:
        textos["marina"] = ig._limpa(llm(f"{PERSONA} A {ig.PERFIS[p['autor']]['nome'].split()[0]} postou uma foto: "
                                         f"{p['descricao']} (legenda \"{p['legenda']}\"). Escreva só o seu comentário, "
                                         "curtinho (até 8 palavras), pode ter 1 emoji.", 60))
    n = at.isoformat()
    for autor, texto in textos.items():
        if autor not in autores or not texto:
            continue
        c_at = at + timedelta(minutes=rng.randint(3, 300))
        cid = ig.comentar(db, pid, autor, texto, c_at)
        ig._exec(db, "UPDATE ig_comentarios SET visto_marina_em=?, curtido_marina_em=? WHERE id=?",
                 (c_at.isoformat(), c_at.isoformat() if autor in ig.AMIGAS else None, cid))
        if p["autor"] == "marina" and autor in ig.AMIGAS and rng.random() < 0.5:
            resp = ig._limpa(llm(f"{PERSONA} Na sua foto ({p['descricao']}), {ig.PERFIS[autor]['nome'].split()[0]} "
                                 f"comentou \"{texto}\". Escreva só a sua resposta, curtinha (até 8 palavras), "
                                 "sem @, pode ter 1 emoji.", 60))
            if resp:
                ig.comentar(db, pid, "marina", resp, c_at + timedelta(minutes=rng.randint(5, 90)), pai_id=cid)
    ig._exec(db, "UPDATE ig_posts SET visto_marina_em=?, curtido_marina_em=? WHERE id=?", (n, n, pid))


async def main(gerar: bool, usar: dict) -> None:
    from db import DatabaseManager
    import photo_director
    from photo_director import WARDROBE, HOME
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
                print("  ok")
    for n, (dias, hora, motivo, pose, lugar, amiga, roupa, local, desc) in enumerate(MARINA):
        chave = f"acervo:marina:{n}"
        if chave in feitos:
            continue
        custo += 61 if amiga else 20
        at = quando(dias, hora, hoje)
        print(f"Ma {at:%d/%m %H:%M} {motivo} ({pose})")
        if not gerar:
            continue
        rng = random.Random(chave)
        fora = bool(lugar)
        ctx = SimpleNamespace(place_key=lugar if fora else HOME, presence_assertable=True,
                              present_people=(amiga,) if amiga else (), activity="", sublocation="", weather=None,
                              snapshot_id=None)
        shot = photo_director.direct(db, at, camera_ctx=ctx, turn=SimpleNamespace(state="cut", arousal=0.0), rng=rng,
                                     force_pose=pose, outfit_override=rng.choice(WARDROBE[roupa]) if roupa else None,
                                     expression_override="a natural confident smile, looking great for an Instagram post")
        gen = await sd_client.generate_directed(shot)
        if not gen.image:
            print("  falhou (rode de novo depois)")
            continue
        imagem = ig.salvar_imagem(gen.image.getvalue())
        legenda = ig._limpa(llm(f"{PERSONA} Você vai postar uma foto: {desc}" + (f", em {local}" if local else "")
                                + ". Escreva só a legenda: curtinha (até 8 palavras), pode ser só um emoji.", 60))
        pid = ig.publicar(db, autor="marina", now=at, imagem=imagem, legenda=legenda, local=local,
                          marcados=(shot.friend,) if shot.friend else (), motivo=motivo, motivo_chave=chave,
                          fonte="acervo", descricao=desc)
        comentarios_do_acervo(db, pid, at, rng)
        print(f"  ok: {legenda}")
    for n, (amiga, tema_i, dias, hora) in enumerate(AMIGAS):
        chave = f"acervo:{amiga}:{n}"
        if chave in feitos:
            continue
        tema, cena, foto = ig.TEMAS[amiga][tema_i]
        arquivo = usar.get(f"{amiga}:{tema}")
        custo += 0 if arquivo else 20
        at = quando(dias, hora, hoje)
        print(f"{amiga} {at:%d/%m %H:%M} {tema}" + (" (foto do teste)" if arquivo else ""))
        if not gerar:
            continue
        dados = Path(arquivo).read_bytes() if arquivo else await civitai_images.friend_scene(amiga, cena)
        if not dados:
            print("  falhou (rode de novo depois)")
            continue
        imagem = ig.salvar_imagem(dados, "a")
        nome = ig.PERFIS[amiga]["nome"].split()[0]
        legenda = ig._limpa(llm(f"Escreva a legenda que {nome} ({ig.JEITO[amiga]}) poria num post do Instagram. "
                                f"A foto: {foto}. Curtinha (até 8 palavras), português informal, pode ter 1 emoji, "
                                "sem hashtag. Responda só com a legenda.", 60))
        pid = ig.publicar(db, autor=amiga, now=at, imagem=imagem, legenda=legenda, motivo=tema, motivo_chave=chave,
                          fonte="acervo", descricao=foto)
        comentarios_do_acervo(db, pid, at, random.Random(chave))
        print(f"  ok: {legenda}")
    print(f"custo {'gasto' if gerar else 'previsto'}: ~{custo} Buzz")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gerar", action="store_true")
    ap.add_argument("--usar", action="append", default=[], help="amiga:tema=arquivo (foto já gerada)")
    a = ap.parse_args()
    asyncio.run(main(a.gerar, dict(x.split("=", 1) for x in a.usar)))
