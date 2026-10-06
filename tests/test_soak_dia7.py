"""Soak, dia 7 (segunda 05/10) — relatório lido em 06/10. Os casos reais do dia:
G1 14:05 "[1 foto(s): Milo, Shih Tzu, deitado no quarto, olhando pra câmera]" chegou como texto, em dois balões (/ruim 076).
G2 12:59 almoço "hambúrguer pedido no iFood"; 13:28 "tô almoçando um hambúrguer que pedi no iFood" abriu um pedido
   novo, que chegou às 14:21 — comeu o hambúrguer duas vezes.
G3 08:24 e 17:31 "a Lívia te deu alguma novidade do casting?" pra ele — o casting de óculos era dela, 06/10 15:30;
   14:04 "a Lívia não me passou nenhuma novidade" sem lembrar do casting. Cinco cópias do assunto, uma com dono trocado.
G4 13:58 "não deixa o celular engolir o plantão inteiro" — o plantão foi 04/10; o resumo de ontem entrava sem data.
G5 19:26 meia arrastão e salto pra provocar o Patrick andando na rua, na volta do sorvete.
G6 15:11 "comecei a mexer no projeto" com ela no TikTok (check-in do assunto "Começar cedo o projeto").
G7 19:04 pote de 1 litro (serve 2, R$ 98) sozinha no Officina del Gelato.
M1 14:00–14:22 "Tem novidades?" → "Só o Lovense"; "nada pra contar?" → "péssima fofoqueira"; repetiu tudo.
M2 /ruim 077: a foto do Milo saiu com a mão dela e a unha errada.
M3 18:56 "Se pesou na academia" já saindo pro sorvete.
Lote da fila: "Foi no Agência boutique da Lívia (fictícia)"; "Rolando agora" sem filtro; o ciúme DELE como ciuminho DELA.
Relatório: "Não to de plantão não marina" e "Cê já me falou isso tudo" fora do «estranhou»; post da academia no Insta.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible


def at(h, m=0, d=5):
    return datetime(2026, 10, d, h, m)


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "d7.db")
        seed_world_bible(self.db)

    def _evento(self, key, quando, tipo, summary, fim=None):
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO life_events(event_key,event_at,end_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,?,?,?,?,'simulated',1,0.3,'[\"marina\"]',0.5,?)""",
                (key, quando.isoformat(), fim.isoformat() if fim else None, tipo, tipo, summary, quando.isoformat()))
            conn.commit()
            return cur.lastrowid

    def _mundo(self, quando, activity, region="Botafogo"):
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_state (state_date, observed_at, location_region, activity, source_json) "
                         "VALUES (?,?,?,?,'{}')", (quando.date().isoformat(), quando.isoformat(), region, activity))
            conn.commit()


class MarcaDeFotoVazadaTest(unittest.TestCase):
    """G1: a marca de foto do histórico não sai como fala dela."""

    def test_marca_de_foto_refaz(self):
        from bot import _has_debug_artifact_leak, _needs_retry_for_junk
        self.assertTrue(_has_debug_artifact_leak("Mando sim, amor, ele tá uma fofura hoje\n"
                                                 "[1 foto(s): Milo, Shih Tzu, deitado no quarto, olhando pra câmera]"))
        self.assertEqual(_needs_retry_for_junk("[2 fotos: o look de hoje] olha"), (True, "debug_artifact"))
        self.assertTrue(_has_debug_artifact_leak("[Foto enviada pelo Patrick] que lindo"))

    def test_fala_normal_passa(self):
        from bot import _has_debug_artifact_leak
        self.assertFalse(_has_debug_artifact_leak("Te mando 1 foto dele já já [risos]"))
        self.assertFalse(_has_debug_artifact_leak("Ele também tava com saudade de você, olha essa carinha."))


class HamburguerDuasVezesTest(_Base):
    """G2: 'pedi no iFood' sobre a refeição que ela está comendo não abre pedido novo."""

    def test_fala_da_refeicao_de_agora_nao_pede_de_novo(self):
        import delivery
        self._evento("meal:2026-10-05:almoco", at(12, 59), "meal",
                     "Almoço em casa: hambúrguer pedido no iFood; comeu além da conta e ficou estufada.", at(13, 41))
        self.assertFalse(delivery.observe(self.db, "Tô almoçando em casa agora, um hambúrguer que pedi no iFood "
                                          "e exagerei bonito", at(13, 28)))
        self.assertIsNone(delivery.open_order(self.db))

    def test_pedido_de_verdade_continua_valendo(self):
        import delivery
        self.assertTrue(delivery.observe(self.db, "acabei de pedir um açaí no iFood", at(16, 0)))

    def test_vou_pedir_depois_do_almoco_vale(self):
        import delivery
        self._evento("meal:2026-10-05:almoco", at(12, 59), "meal", "Almoço em casa: hambúrguer pedido no iFood.")
        self.assertTrue(delivery.observe(self.db, "vou pedir um açaí agora", at(14, 30)))


class AssuntosEmAbertoTest(_Base):
    """G3/G4/G6: casting e faculdade são dela; sem cópias; o velho esfria."""

    def test_casting_e_projeto_sao_dela(self):
        from db import _assunto_dela
        for texto in ("Aguardar notícias da Lívia sobre os castings.",
                      "Patrick vai informar se Lívia trouxe novidades sobre o casting.",
                      "Começar cedo o projeto de Projetar em Sociedade"):
            self.assertTrue(_assunto_dela(texto), texto)
        self.assertFalse(_assunto_dela("Patrick terá um plantão amanhã e está se preparando emocionalmente."))

    def test_checkin_nao_pergunta_do_casting_dela(self):
        self.db.adicionar_open_loop("waiting_reply", "Aguardar notícias de Lívia sobre o casting.",
                                    next_check_after=at(8, 0).isoformat())
        self.db.adicionar_open_loop("task", "Começar cedo o projeto de Projetar em Sociedade",
                                    next_check_after=at(8, 0).isoformat())
        self.assertEqual(self.db.get_open_loops_para_checkin(at(15, 11)), [])

    def test_mesma_pendencia_com_outro_tipo_nao_duplica(self):
        a = self.db.adicionar_open_loop("waiting", "Aguardar notícias de Livia sobre o casting")
        b = self.db.adicionar_open_loop("ongoing_project", "Aguardar notícias da Lívia sobre os castings.")
        c = self.db.adicionar_open_loop("project", "Aguardar notícias da Lívia sobre os castings")
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_assunto_de_uma_semana_esfria(self):
        lid = self.db.adicionar_open_loop("other", "Patrick terá um plantão amanhã e está se preparando.")
        with self.db.get_connection() as conn:
            conn.execute("UPDATE open_loops SET created_at=? WHERE id=?", ("2026-09-27T18:15:31", lid))
            conn.commit()
        novo = self.db.adicionar_open_loop("promise", "Patrick vai tentar separar um fim de semana pra visitar")
        self.assertEqual(self.db.esfriar_open_loops(dias=7, now=at(23, 0)), 1)
        self.assertEqual(self.db.get_open_loop(lid)["status"], "abandoned")
        self.assertEqual(self.db.get_open_loop(novo)["status"], "open")

    def test_reflector_ve_mais_assuntos_e_sabe_quem_e_a_livia(self):
        import session_reflector
        self.assertGreaterEqual(session_reflector.REFLECTOR_LOOPS, 10)
        self.assertIn("A Lívia é a agente da Marina", session_reflector.SESSION_REFLECTOR_SYSTEM_PROMPT)


class ResumoDatadoTest(unittest.TestCase):
    """G4: o resumo de ontem diz que é de ontem."""

    def test_resumo_de_ontem(self):
        from memory_retriever import _resumo_datado
        linha = _resumo_datado({"summary": "Marina e Patrick trocaram provocações durante o plantão dele.",
                                "created_at": "2026-10-04T19:44:00"}, now=at(13, 58))
        self.assertTrue(linha.startswith("(conversa de ontem, 04/10, à noite) Marina e Patrick"), linha)

    def test_resumo_de_hoje_e_sem_data(self):
        from memory_retriever import _resumo_datado
        self.assertIn("(conversa de hoje, 05/10, à tarde)",
                      _resumo_datado({"summary": "x", "created_at": "2026-10-05T14:00:00"}, now=at(16, 0)))
        self.assertEqual(_resumo_datado({"summary": "só o texto"}), "só o texto")


class TrabalhoAVistaTest(_Base):
    """G3: o casting de amanhã aparece no prompt mesmo com a aula antes."""

    def test_casting_de_amanha(self):
        from world_context import WorldContextBuilder
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO eventos_pendentes (event_type, description, event_at, end_at, status, confirmed,
                            source_key, location_key, owner_character_key, created_at)
                            VALUES ('trabalho','Casting na agência: campanha de uma marca de óculos',?,?,'pending',1,
                                    'freela:2026-10-06:casting:2026-10-01','boutique_agency','marina',?)""",
                         ("2026-10-06T15:30:00", "2026-10-06T17:00:00", "2026-10-01T11:25:00"))
            conn.commit()
        wc = WorldContextBuilder(self.db)
        aula = {"activity": "Aula", "start_at": "2026-10-06T07:00:00"}
        linha = wc._trabalho_a_vista(at(14, 4), aula)
        self.assertIn("Casting na agência: campanha de uma marca de óculos amanhã (06/10) às 15:30", linha)
        self.assertEqual(wc._trabalho_a_vista(at(14, 4), {"start_at": "2026-10-06T15:30:00"}), "")
        self.assertEqual(wc._trabalho_a_vista(at(14, 4, d=8), aula), "")


class ProvocarNaRuaTest(_Base):
    """G5: a caminho não é casa."""

    def test_a_caminho_nao_e_casa(self):
        from roupa import Roupa
        r = Roupa(self.db)
        self.assertFalse(r._em_casa({"location_region": "a caminho (Botafogo)", "location_place_id": None}))
        self.assertTrue(r._em_casa({"location_region": "Botafogo", "location_place_id": None}))

    def test_sem_snap_le_o_ultimo_estado(self):
        from roupa import Roupa
        self._mundo(at(19, 26), "voltando do Officina del Gelato pra casa a pé", "a caminho (Botafogo)")
        self.assertFalse(Roupa(self.db)._em_casa())


class PoteDeUmLitroTest(unittest.TestCase):
    """G7: sozinha, nada de item pra dividir."""

    def _plan(self, n, friends=()):
        import consumo
        return consumo.plan({"source_key": f"vontade:2026-10-05:gelato:{n}", "event_at": "2026-10-05T18:52:00",
                             "end_at": "2026-10-05T19:24:00", "location_key": "loja_officina_gelato",
                             "metadata_json": json.dumps({"loja": "officina-gelato", "tipo": "sorvete",
                                                          "friends": list(friends)})})

    def test_sozinha_nao_pede_pote(self):
        nomes = {i.nome for n in range(60) for i in self._plan(n)}
        self.assertTrue(nomes)
        self.assertNotIn("Pote 1 litro", nomes)

    def test_com_amiga_pode(self):
        nomes = {i.nome for n in range(80) for i in self._plan(n, ["bia_andrade"])}
        self.assertIn("Pote 1 litro", nomes)


class PediuAssuntoTest(_Base):
    """M1: quando ele pede assunto, ela conta uma coisa de verdade do dia."""

    def test_frases_dele(self):
        from chat_naturalness import pediu_assunto
        for t in ("Tem novidades?", "Po ta saindo todo fim de semana e n tem nada pra contar amor?",
                  "Enfim… Então tu não tem nada pra gente conversar?", "me conta as fofocas"):
            self.assertTrue(pediu_assunto(t), t)
        for t in ("Como foi a faculdade hj?", "O Milo tá por aí?", "Quais os planos p tarde?"):
            self.assertFalse(pediu_assunto(t), t)

    def test_conta_o_contato_do_dia(self):
        from chat_naturalness import share_nudge, share_constraint
        self._evento("contato:pai:1020", at(10, 20), "social_contact",
                     "Trocou mensagens com o pai; assunto: mandou o dinheiro do mercado e da comida da semana, sem ela "
                     "pedir.")
        self._evento("tempo_livre:1405", at(14, 5), "tempo_livre", "Ficou ouvindo a playlist dela no closet.")
        news = share_nudge(self.db, at(14, 0), intent="nada_disso", pediu=True)
        self.assertIn("pai", news["summary"])
        txt = share_constraint(news, pediu=True)
        self.assertIn("ELE PEDIU ASSUNTO", txt)
        self.assertIn("Não diga que não tem nada pra contar", txt)


class UnhaNaFotoDoMiloTest(_Base):
    """M2: a foto do ponto de vista dela leva a cor da unha (a mão pode aparecer na borda)."""

    def test_pov_milo_com_a_unha(self):
        import random
        from types import SimpleNamespace
        import photo_director
        ctx = SimpleNamespace(place_key="marina_apartment", presence_assertable=True, present_people=(),
                              activity="em casa", sublocation="sala")
        with patch("photo_director._nails", return_value="Her fingernails are painted in deep red nail polish."):
            shot = photo_director.direct(self.db, at(14, 5), request="Manda foto dele? Tô com sdds",
                                         her_line="Mando sim, amor, ele tá uma fofura hoje", camera_ctx=ctx,
                                         force_pose="pov_milo", rng=random.Random(1))
        self.assertIn("deep red nail polish", shot.prompt)


class PesoNoFimDoTreinoTest(_Base):
    """M3: a balança é antes de sair da academia."""

    def test_pesou_antes_de_sair(self):
        from meals import Meals
        self._mundo(at(17, 46), "treinando na academia")
        self._mundo(at(18, 56), "indo da Bodytech pro Officina del Gelato a pé", "a caminho (Botafogo)")
        self.assertEqual(Meals(self.db)._fim_do_treino(at(18, 57)), at(18, 51))

    def test_sem_treino_fica_a_hora(self):
        from meals import Meals
        self.assertEqual(Meals(self.db)._fim_do_treino(at(18, 57)), at(18, 57))


class CiumeDeleTest(unittest.TestCase):
    """Achado 3 do recalibrar: o ciuminho dela só com outra mulher na mensagem dele."""

    def test_ciume_dele_nao_e_dela(self):
        from planner import _fala_de_outra
        for t in ("Tô com ciúmes de você", "Sai dessa varanda, tá todo mundo te olhando",
                  "Esse vestido tá curto demais pra sair", "A Bia tá te namorando mais que eu"):
            self.assertFalse(_fala_de_outra(t), t)

    def test_outra_mulher_vale(self):
        from planner import _fala_de_outra
        for t in ("a colega nova do trabalho me chamou pra almoçar", "minha ex me mandou mensagem",
                  "tinha uma mina linda no plantão"):
            self.assertTrue(_fala_de_outra(t), t)


class ExtratoERolandoTest(_Base):
    """Lote da fila: o extrato sem "(fictícia)" e com o artigo certo; o Rolando agora só com o que ela contou."""

    def test_agencia_e_feminino(self):
        from vontade import no
        self.assertEqual(no("Agência boutique da Lívia"), "na Agência boutique da Lívia")

    def _historia(self, key, titulo):
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO story_threads(thread_key, thread_type, title, summary, status, started_at,
                            last_event_at, metadata_json) VALUES (?,?,?,?, 'open', ?, ?, ?)""",
                         (key, "social", titulo, titulo, at(10).isoformat(), at(10).isoformat(),
                          json.dumps({"participants": ["marina", "bia_andrade"]})))
            conn.commit()
        return self._evento(f"{key}:start", at(10), "story", titulo)

    def test_rolando_so_o_que_ela_contou(self):
        from social_day import SocialDay
        self._historia("story:bia:caio", "A Bia e o Caio")
        day = SocialDay(self.db)
        self.assertEqual(day.world_panel(at(12))["rolando"], [])
        day.mark_shared("story:bia:caio:start")
        self.assertEqual([r["titulo"] for r in day.world_panel(at(12))["rolando"]], ["A Bia e o Caio"])

    def test_segredo_nunca(self):
        from social_day import SocialDay
        eid = self._historia("story:bia:segredo", "O segredo da Bia")
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO knowledge_items(subject_type, subject_id, holder_character_key, privacy_level,
                            learned_at) VALUES ('event', ?, 'marina', 'CONFIDENTIAL', ?)""", (eid, at(10).isoformat()))
            conn.commit()
        day = SocialDay(self.db)
        day.mark_shared("story:bia:segredo:start")
        self.assertEqual(day.world_panel(at(12))["rolando"], [])


def _relatorio():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "relatorio_soak", Path(__file__).resolve().parents[1] / "scripts" / "relatorio_soak.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RelatorioDia7Test(unittest.TestCase):
    def test_estranhou_as_correcoes_dele(self):
        rel = _relatorio()
        for t in ("Não to de plantão não marina", "O plantão foi ontem", "Cê já me falou isso tudo marina",
                  "Nossa que formalidade em ma kkkk"):
            self.assertTrue(rel.estranhou(t), t)
        for t in ("Ss, pretendo ficar o dia todo deitado hj", "Pode deixar, mas vamos bater papo",
                  "Não sei não, amor"):
            self.assertFalse(rel.estranhou(t), t)


class FaxinaDaMemoriaTest(_Base):
    """06/10: a faxina era "a cada 24 h" desde o início do bot e cada reinício zerava o relógio (1 vez em 11 dias)."""

    def test_quando_roda(self):
        from memory_hygiene import faxina_devida
        self.assertTrue(faxina_devida(None, at(15, 0)))
        self.assertTrue(faxina_devida(at(4, 0, d=5), at(4, 10, d=6)))       # 04h, passou de 20 h
        self.assertFalse(faxina_devida(at(4, 0, d=6), at(15, 0, d=6)))      # já rodou hoje
        self.assertFalse(faxina_devida(at(23, 0, d=5), at(4, 30, d=6)))     # 04h, mas só 5 h e meia
        self.assertTrue(faxina_devida(at(4, 0, d=5), at(11, 0, d=6)))       # passou de 30 h: roda a qualquer hora

    def test_reinicio_nao_zera(self):
        from memory_hygiene import MemoryHygieneService, FAXINA_KEY
        svc = MemoryHygieneService(self.db)
        with patch.object(svc, "run_hygiene_cycle", return_value={"ok": True}) as ciclo:
            self.assertEqual(svc.run_if_due(at(15, 0)), {"ok": True})
            self.assertIsNone(svc.run_if_due(at(16, 0)))                    # "reiniciou": a última fica no banco
            self.assertEqual(ciclo.call_count, 1)
        self.assertEqual(self.db.get_estado_relacional(FAXINA_KEY), at(15, 0).isoformat())
