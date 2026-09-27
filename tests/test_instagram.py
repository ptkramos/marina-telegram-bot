"""Instagram da Marina (27/09, Etapa 5 do PLANO_WEBAPP): quando ela posta, o que vira post, stories, amigas,
o que ela vê quando abre o app, e a API do Mini App."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp.test_utils import TestClient, TestServer

import instagram as ig
import webapp_server
from db import DatabaseManager
from tests.test_webapp import PATRICK, TOKEN, signed

T = datetime(2026, 9, 27, 18, 30)
FELIZ = SimpleNamespace(valence=0.7, energy=0.6)
TRISTE = SimpleNamespace(valence=0.3, energy=0.4)


def evento(db, key, at, tipo, title, summary, gente=("marina",)):
    with db.get_connection() as conn:
        conn.execute("""INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,autonomy_level,
                        importance,participants_json,share_worthy,created_at) VALUES (?,?,?,?,?,'simulated',1,0.3,?,0.5,?)""",
                     (key, at.isoformat(), tipo, title, summary, json.dumps(list(gente)), at.isoformat()))
        conn.commit()


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "ig.db")
        self._dir = ig.DIR
        ig.DIR = Path(self.temp.name) / "instagram"

    def tearDown(self):
        ig.DIR = self._dir
        self.temp.cleanup()

    def rolê(self, at=T - timedelta(hours=3)):
        evento(self.db, "social:2026-09-27:bia_andrade:saida", at, "social_contact", "presencial com a Bia",
               "Encontrou a Bia (Shopping da Gávea); assunto: relacionamentos.", ("marina", "bia_andrade"))

    def momento(self, feeling=FELIZ, act="HOME_RELAXING", **kw):
        return ig.Momento(asleep=kw.pop("asleep", False), act_code=act, feeling=feeling, **kw)


class MotivosTest(Base):
    def test_role_com_amiga_de_rg_e_o_motivo_mais_forte(self):
        self.rolê()
        evento(self.db, "livre:2026-09-27:14", T - timedelta(hours=5), "tempo_livre", "Montando looks",
               "Ficou montando looks no closet.")
        ms = ig.motivos(self.db, T)
        self.assertEqual(ms[0]["motivo"], "role_amiga")
        self.assertEqual((ms[0]["amiga"], ms[0]["local"]), ("bia_andrade", "Shopping da Gávea"))
        self.assertIn("look", [m["motivo"] for m in ms])

    def test_acontecimento_que_ja_virou_post_nao_volta(self):
        self.rolê()
        ig.publicar(self.db, autor="marina", now=T, motivo="role_amiga",
                    motivo_chave="social:2026-09-27:bia_andrade:saida", descricao="x")
        self.assertNotIn("role_amiga", [m["motivo"] for m in ig.motivos(self.db, T)])

    def test_sem_nada_sobra_a_selfie_em_casa(self):
        self.assertEqual([m["motivo"] for m in ig.motivos(self.db, T)], ["vista"])


class PostTest(Base):
    def test_feliz_depois_do_role_posta_com_foto_de_grupo(self):
        self.rolê()
        p = ig.plano_post(self.db, T, self.momento())
        self.assertEqual((p["motivo"], p["fonte"]), ("role_amiga", "grupo"))
        self.assertIn(p["pose"], ig.POSES["role_amiga"])

    def test_triste_nao_posta(self):
        self.rolê()
        self.assertIsNone(ig.plano_post(self.db, T, self.momento(TRISTE)))

    def test_nao_posta_dormindo_ocupada_com_o_patrick_no_chat_ou_logo_depois_de_postar(self):
        self.rolê()
        self.assertIsNone(ig.plano_post(self.db, T, self.momento(asleep=True)))
        self.assertIsNone(ig.plano_post(self.db, T, self.momento(act="CLASS")))
        self.assertIsNone(ig.plano_post(self.db, T, self.momento(patrick_ativo=True)))
        ig.publicar(self.db, autor="marina", now=T - timedelta(hours=20), motivo="look", motivo_chave="l", descricao="x")
        self.assertIsNone(ig.plano_post(self.db, T, self.momento()))

    def test_dias_sem_nada_e_de_bom_humor_posta_a_selfie_em_casa(self):
        ig.publicar(self.db, autor="marina", now=T - timedelta(days=7), motivo_chave="velho", descricao="x")
        radiante = SimpleNamespace(valence=0.85, energy=0.7)
        self.assertEqual(ig.plano_post(self.db, T, self.momento(radiante))["motivo"], "vista")
        self.assertIsNone(ig.plano_post(self.db, T.replace(hour=9, minute=45), self.momento(radiante)))

    def test_espera_um_pouco_depois_do_acontecimento(self):
        self.rolê(at=T - timedelta(minutes=5))
        self.assertIsNone(ig.plano_post(self.db, T, self.momento()))

    def test_foto_do_chat_no_mesmo_lugar_vira_o_post_sem_custo(self):
        self.rolê()
        fid = ig.guardar_foto_do_chat(self.db, b"jpg", T - timedelta(hours=2, minutes=30),
                                      descricao="selfie com a amiga", pose="fora_selfie_amiga", lugar="Shopping da Gávea")
        p = ig.plano_post(self.db, T, self.momento())
        self.assertEqual((p["fonte"], p["foto_chat"]), ("chat", fid))

    def test_post_dela_entra_no_hoje_e_o_acervo_nao(self):
        ig.publicar(self.db, autor="marina", now=T, legenda="sábado é sagrado", motivo="role", motivo_chave="a",
                    descricao="x")
        ig.publicar(self.db, autor="marina", now=T - timedelta(days=30), legenda="velha", motivo="acervo",
                    motivo_chave="b", fonte="acervo", descricao="y")
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT summary FROM life_events WHERE event_type='instagram'").fetchall()
        self.assertEqual([r["summary"] for r in rows], ["Postou uma foto no Instagram: sábado é sagrado"])
        import hoje
        linha = hoje.curto({"event_type": "instagram", "title": "Postou uma foto no Instagram",
                            "summary": rows[0]["summary"]})
        self.assertEqual((linha["ic"], linha["texto"], linha["sub"]),
                         ("brand-instagram", "Postou uma foto no Instagram", "sábado é sagrado"))


class StoryTest(Base):
    def test_musica_tocando_vira_story_uma_vez_e_no_maximo_dois_por_dia(self):
        faixa = {"nome": "Houdini", "artista": "Dua Lipa", "at": (T - timedelta(minutes=2)).isoformat(), "id": 1}
        bloco = SimpleNamespace(chave="musica", faixas=[faixa])
        p = ig.plano_story(self.db, T, self.momento(bloco=bloco))
        self.assertEqual(p["tipo"], "musica")
        ig.publicar_story(self.db, T, p, capa="https://capa")
        self.assertIsNone(ig.plano_story(self.db, T + timedelta(minutes=5), self.momento(bloco=bloco)))
        s = ig.stories_ativos(self.db, T + timedelta(hours=1))
        self.assertEqual(json.loads(s[0]["story_json"])["capa"], "https://capa")
        self.assertEqual(ig.stories_ativos(self.db, T + timedelta(hours=25)), [])

    def test_triste_nao_posta_story(self):
        ig.guardar_foto_do_chat(self.db, b"jpg", T - timedelta(hours=1), descricao="o Milo")
        self.assertIsNone(ig.plano_story(self.db, T, self.momento(TRISTE)))
        self.assertEqual(ig.plano_story(self.db, T, self.momento())["tipo"], "foto")


class AmigaTest(Base):
    def test_cerca_de_dois_posts_por_semana_somando_as_quatro(self):
        dias = 0
        for d in range(140):
            dia = T + timedelta(days=d)
            postou = [ig.plano_amiga(self.db, dia.replace(hour=h, minute=55)) for h in range(8, 24)]
            planos = [p for p in postou if p]
            if planos:
                dias += 1
                ig.publicar(self.db, autor=planos[0]["amiga"], now=dia, motivo_chave=planos[0]["chave"], descricao="x")
                self.assertTrue(all(p["chave"] == planos[0]["chave"] for p in planos))
        self.assertTrue(25 <= dias <= 55, dias)          # 140 dias × 2/7 = 40

    def test_amiga_reposta_a_foto_de_grupo_de_ontem_sem_custo(self):
        dia = next(T + timedelta(days=d) for d in range(30)
                   if __import__("random").Random(f"ig:amiga:{(T + timedelta(days=d)).date().isoformat()}").random()
                   < ig.AMIGA_POSTA_DIA)
        at = next(t for h in range(10, 24) if ig.plano_amiga(self.db, t := dia.replace(hour=h, minute=59)))
        ig.publicar(self.db, autor="marina", now=at - timedelta(hours=5), imagem="g.jpg", marcados=("bia_andrade",),
                    fonte="grupo", motivo_chave="g", descricao="você com a Bia")
        plano = ig.plano_amiga(self.db, at)
        self.assertEqual((plano["amiga"], plano["fonte"], plano["imagem"]), ("bia_andrade", "grupo", "g.jpg"))


class OlhaTest(Base):
    def _post(self):
        pid = ig.publicar(self.db, autor="marina", now=T, legenda="sábado é sagrado", marcados=("bia_andrade",),
                          motivo_chave="p", descricao="você com a Bia no shopping")
        ig.agendar_comentarios(self.db, pid, T, {"bia_andrade": "gatas", "lu.mendes": "linda"})
        return pid

    def test_comentario_agendado_so_aparece_na_hora(self):
        pid = self._post()
        self.assertEqual(ig.comentarios(self.db, pid, T), [])
        self.assertEqual(len(ig.comentarios(self.db, pid, T + timedelta(hours=9))), 2)

    def test_ela_ve_responde_e_curte_o_comentario_do_patrick_e_sabe_disso_no_chat(self):
        pid = self._post()
        cid = ig.comentar(self.db, pid, "patrick", "linda demais", T + timedelta(minutes=10))
        ig.curtir_post(self.db, pid, T + timedelta(minutes=10), True)
        antes = T + timedelta(minutes=5)
        self.assertNotIn("linda demais", json.dumps(ig.novidades(self.db, antes), ensure_ascii=False))
        depois = T + timedelta(hours=9)
        pedidos = []
        vistos = ig.marina_olha(self.db, depois, lambda instr: pedidos.append(instr) or "você que é 🥺",
                                rng=__import__("random").Random(1))
        self.assertTrue(any("o Patrick comentou \"linda demais\"" in v and "você que é" in v for v in vistos), vistos)
        self.assertTrue(any("o Patrick curtiu sua foto" in v for v in vistos))
        resp = [c for c in ig.comentarios(self.db, pid, depois + timedelta(minutes=5)) if c["pai_id"] == cid]
        self.assertEqual((resp[0]["autor"], resp[0]["texto"]), ("marina", "você que é 🥺"))
        with self.db.get_connection() as conn:
            self.assertIsNotNone(conn.execute("SELECT curtido_marina_em FROM ig_comentarios WHERE id=?",
                                              (cid,)).fetchone()[0])
        self.assertFalse(any("@lu.mendes" in p for p in pedidos), "de fora ela não responde")
        linhas = "\n".join(ig.prompt_lines(self.db, depois))
        self.assertIn("linda demais", linhas)
        self.assertIn("SEU INSTAGRAM", linhas)
        self.assertEqual(ig.novidades(self.db, depois)["comentarios"], [], "já viu")

    def test_quando_ela_abre_o_app(self):
        m = self.momento()
        self.assertFalse(ig.olha_agora(self.db, T, self.momento(asleep=True)))
        self.assertFalse(ig.olha_agora(self.db, T, self.momento(act="CLASS")))
        self.assertTrue(ig.olha_agora(self.db, T, m))
        ig.marina_olha(self.db, T, lambda i: "")
        self.assertFalse(ig.olha_agora(self.db, T + timedelta(minutes=30), m))
        self.assertTrue(ig.olha_agora(self.db, T + timedelta(minutes=80), m))
        no_insta = self.momento(bloco=SimpleNamespace(chave="instagram", faixas=None))
        self.assertTrue(ig.olha_agora(self.db, T + timedelta(minutes=25), no_insta))

    def test_curtidas_sobem_e_estabilizam(self):
        pid = self._post()
        p = ig.post(self.db, pid)
        uma, dez, dois_dias = (ig.curtidas(p, T + timedelta(hours=h)) for h in (1, 10, 48))
        self.assertLess(uma, dez)
        self.assertLessEqual(dez, dois_dias)
        self.assertLess(dois_dias, ig.PERFIS["marina"]["seguidores"] * 0.12)

    def test_json_dos_comentarios(self):
        self.assertEqual(ig.resposta_json('ok ```json\n{"bia_andrade": "gatas", "x": ""}\n```'), {"bia_andrade": "gatas"})
        self.assertEqual(ig.resposta_json("nada"), {})


class ApiInstagramTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "a.db")
        self._dir = ig.DIR
        ig.DIR = Path(self.temp.name) / "instagram"
        self.reply = AsyncMock()
        hooks = webapp_server.Hooks(db=self.db, bot_token=TOKEN, allowed_user_id=PATRICK,
                                    status=lambda now: {"now": now}, pix=AsyncMock(), now=lambda: T,
                                    ig_story_reply=self.reply)
        self.client = TestClient(TestServer(webapp_server.make_app(hooks)))
        await self.client.start_server()
        self.h = {"X-Telegram-Init-Data": signed()}
        nome = ig.salvar_imagem(b"\xff\xd8jpg")
        self.pid = ig.publicar(self.db, autor="marina", now=T - timedelta(hours=2), imagem=nome, legenda="oi",
                               marcados=("bia_andrade",), motivo_chave="p", descricao="você com a Bia")
        self.sid = ig.publicar(self.db, autor="marina", now=T - timedelta(minutes=30), tipo="story",
                               motivo_chave="s", descricao="a música", story={"tipo": "musica", "nome": "Houdini"})
        self.nome = nome

    async def asyncTearDown(self):
        await self.client.close()
        ig.DIR = self._dir
        self.temp.cleanup()

    async def test_feed_com_stories_e_bolinha_some_depois_de_abrir(self):
        self.assertTrue((await (await self.client.get("/api/inicio", headers=self.h)).json())["insta_novo"])
        d = await (await self.client.get("/api/ig", headers=self.h)).json()
        self.assertEqual(d["posts"][0]["autor"]["handle"], "masalles")
        self.assertEqual(d["posts"][0]["marcados"][0]["handle"], "bia.andrade")
        self.assertEqual(d["stories"][0]["itens"][0]["story"]["nome"], "Houdini")
        self.assertFalse((await (await self.client.get("/api/inicio", headers=self.h)).json())["insta_novo"])

    async def test_comentar_curtir_e_responder(self):
        r = await self.client.post("/api/ig/comentar", headers=self.h, json={"post": self.pid, "texto": "linda"})
        cid = (await r.json())["id"]
        await self.client.post("/api/ig/comentar", headers=self.h,
                               json={"post": self.pid, "texto": "@masalles de novo", "pai": cid})
        await self.client.post("/api/ig/curtir", headers=self.h, json={"post": self.pid, "on": True})
        d = await (await self.client.get(f"/api/ig/post/{self.pid}", headers=self.h)).json()
        self.assertTrue(d["curtiu"])
        self.assertEqual(d["comentarios"][0]["texto"], "linda")
        self.assertEqual(d["comentarios"][0]["respostas"][0]["texto"], "@masalles de novo")
        vazio = await self.client.post("/api/ig/comentar", headers=self.h, json={"post": self.pid, "texto": " "})
        self.assertEqual(vazio.status, 400)

    async def test_resposta_ao_story_vai_pro_chat(self):
        r = await self.client.post("/api/ig/story", headers=self.h,
                                   json={"id": self.sid, "acao": "responder", "texto": "que música boa"})
        self.assertEqual(r.status, 200)
        story, texto, query_id = self.reply.await_args.args
        self.assertEqual((story["id"], texto, query_id), (self.sid, "que música boa", "AAE"))

    async def test_perfil_e_foto(self):
        d = await (await self.client.get("/api/ig/perfil/bia_andrade", headers=self.h)).json()
        self.assertEqual(d["marcadas"][0]["id"], self.pid)
        self.assertEqual((await self.client.get("/api/ig/perfil/patrick", headers=self.h)).status, 404)
        self.assertEqual((await self.client.get(f"/ig/{self.nome}")).status, 200)
        self.assertEqual((await self.client.get("/ig/..%2Fig.db")).status, 404)
        self.assertEqual((await self.client.get("/api/ig", headers={})).status, 403)


if __name__ == "__main__":
    unittest.main()
