"""Auditoria #6 — o mundo social acontece.

Antes: social_evidence, life_events e story_threads com zero linhas; o
StoryEngine nunca era chamado; "falou com a Bia hoje?" era improviso.
"""
import json
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path

from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible
from seed_academic_v36 import seed_academic
from social_day import Contact, SocialDay
from world_state import RoutineEngine, WorldStateManager


class SocialDayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "social.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key,value,updated_at) "
                         "VALUES ('clean_canonical_start_done','1','2026-09-01')")
            conn.execute("INSERT INTO world_bootstrap (key,value,updated_at) "
                         "VALUES ('social_day_start','2026-09-01T00:00:00','2026-09-01')")
        self.day = SocialDay(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def _contacts(self):
        with self.db.get_connection() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT event_key, event_at, summary, participants_json FROM life_events "
                "WHERE event_type='social_contact' ORDER BY event_at")]

    def test_duas_semanas_de_vida_social_coerente_com_a_agenda(self):
        from academic_life import AcademicLife
        self.day.materialize(datetime(2026, 10, 5, 0, 0))  # só materializa ontem/hoje
        for offset in range(14):
            d = date(2026, 9, 21) + timedelta(days=offset)
            self.day.materialize(datetime.combine(d, time(23, 59)))
        contatos = self._contacts()
        bia_dias = {c["event_at"][:10] for c in contatos if "bia_andrade" in c["participants_json"]}
        self.assertGreaterEqual(len(bia_dias), 8)
        for c in contatos:
            if "PUC-Rio" in c["summary"]:
                d = datetime.fromisoformat(c["event_at"])
                blocks = AcademicLife(self.db).blocks_on(d.date())
                self.assertTrue(any(datetime.fromisoformat(b["start_at"]) <= d < datetime.fromisoformat(b["end_at"])
                                    for b in blocks), c)

    def test_primeiro_startup_nao_inventa_passado(self):
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM world_bootstrap WHERE key='social_day_start'")
        startup = datetime(2026, 9, 22, 16, 0)
        self.day.materialize(startup)
        self.assertEqual(self._contacts(), [])  # nada de ontem nem de hoje cedo
        self.day.materialize(datetime(2026, 9, 22, 23, 59))
        self.assertTrue(all(datetime.fromisoformat(c["event_at"]) >= startup for c in self._contacts()))

    def test_materializacao_idempotente_e_so_do_que_ja_passou(self):
        noite = datetime(2026, 9, 21, 23, 59)
        primeira = self.day.materialize(noite)
        self.assertEqual(self.day.materialize(noite), [])
        self.assertTrue(all(datetime.fromisoformat(c["event_at"]) <= noite for c in self._contacts()))
        self.assertEqual(len(self._contacts()), len(primeira))
        cedo = SocialDay(self.db).plan(date(2026, 9, 22))
        self.assertTrue(cedo)  # terça tem plano, mas nada dela foi gravado ainda
        self.assertFalse(any(c["event_at"].startswith("2026-09-22") for c in self._contacts()))

    def test_encontro_na_academia_so_se_ela_foi(self):
        engine = RoutineEngine(self.db)
        for offset in range(28):
            d = date(2026, 9, 21) + timedelta(days=offset)
            carol = [c for c in self.day.plan(d) if c.character_key == "carol_menezes"]
            if carol:
                break
        else:
            self.fail("nenhum encontro com a Carol em 4 semanas")
        contato = carol[0]
        # Patrick conversando bem na hora: ela não saiu pra academia.
        self.db.adicionar_mensagem("user", "oi amor", timestamp=(contato.at - timedelta(minutes=5)).isoformat())
        self.day.materialize(contato.at + timedelta(minutes=1))
        self.assertFalse(any("carol_menezes" in c["participants_json"] for c in self._contacts()))

    def test_passeio_do_milo_nunca_cai_dentro_do_sono(self):
        from academic_life import AcademicLife
        engine = RoutineEngine(self.db)
        for offset in range(14):
            d = date(2026, 9, 21) + timedelta(days=offset)
            has_class = bool(AcademicLife(self.db).blocks_on(d))
            row = engine._routine_row("milo_morning_walk")
            slot = engine._placement(d, row, "pet_walk", has_class)
            if not slot:
                continue
            with self.subTest(day=d):
                cands = engine.candidates(slot[0] + timedelta(minutes=1), has_class=has_class)
                chosen, _ = engine.pick(slot[0] + timedelta(minutes=1), cands, has_class=has_class)
                self.assertEqual(chosen.routine_type, "pet_walk")

    def test_historia_nasce_com_a_pessoa_e_continua_dias_depois(self):
        created = None
        for offset in range(40):
            d = date(2026, 9, 21) + timedelta(days=offset)
            contato = Contact(key=f"teste:{d}:bia", at=datetime.combine(d, time(20, 0)),
                              character_key="bia_andrade", channel="mensagem", place_key=None,
                              topic="relacionamentos",
                              hook=("friend_needs_support", "support_for_friend"))
            self.day._record(contato)
            with self.db.get_connection() as conn:
                created = conn.execute("SELECT * FROM story_threads WHERE status='open'").fetchone()
            if created:
                break
        self.assertIsNotNone(created, "StoryEngine nunca aceitou o gancho em 40 dias")
        meta = json.loads(created["metadata_json"])
        self.assertIn("bia_andrade", meta["participants"])
        inicio = datetime.fromisoformat(created["started_at"]).date()
        for extra in range(1, 6):
            d = inicio + timedelta(days=extra)
            self.day.materialize(datetime.combine(d, time(23, 59)))
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT status, last_event_at FROM story_threads WHERE id=?",
                               (created["id"],)).fetchone()
        self.assertGreater(row["last_event_at"], created["last_event_at"])

    def test_prompt_mostra_o_dia_e_o_ultimo_contato_com_quem_foi_citado(self):
        from context_builder import ContextBuilder
        from memory import MemoryManager
        from unittest.mock import MagicMock
        noite = datetime(2026, 9, 21, 23, 0)
        WorldStateManager(self.db).resolve(noite)
        with self.db.get_connection() as conn:  # produção: upgrade_social_v361 trava o cânone
            conn.execute("UPDATE social_relationships SET canon_locked=1")
        retriever = MagicMock()
        retriever.retrieve_context.return_value = {"fatos": [], "momentos": [], "resumos": []}
        builder = ContextBuilder(memory_mgr=MemoryManager(db=self.db), retriever=retriever)
        prompt = builder.build_system_prompt(user_message="vc falou com a Bia hoje?", now=noite)
        self.assertIn("[SEU DIA ATÉ AGORA", prompt)
        bia = self.day.last_contact("bia_andrade", noite)
        if bia:
            self.assertIn("Último contato: hoje", prompt)
        else:
            self.assertIn("Sem contato registrado", prompt)


class ProactiveGroundedTests(unittest.TestCase):
    """A proatividade viva mandava 4 frases fixas; agora usa o LLM ancorado."""

    def test_texto_gerado_passa_pelos_guards_e_cai_no_fallback(self):
        import bot
        from unittest.mock import patch
        with patch.object(bot, "generate_dynamic_speech", return_value="a Bia me contou uma fofoca agora kkk"):
            self.assertEqual(bot._proactive_text("social_day_share", "x", "fallback"),
                             "a Bia me contou uma fofoca agora kkk")
        with patch.object(bot, "generate_dynamic_speech", return_value="debug_mode=true"):
            self.assertEqual(bot._proactive_text("light_affection", None, "fallback"), "fallback")
        with patch.object(bot, "generate_dynamic_speech", side_effect=RuntimeError("offline")):
            self.assertEqual(bot._proactive_text("light_affection", None, "fallback"), "fallback")

    def test_instrucao_deixa_claro_que_e_iniciativa_dela(self):
        import bot
        from unittest.mock import patch
        with patch.object(bot, "generate_dynamic_speech", return_value="oi") as gen:
            bot._proactive_text("social_day_share", "Trocou mensagens com a Bia; assunto: festas.", "f")
        instrucao = gen.call_args.args[0]
        self.assertIn("o Patrick NÃO mandou mensagem", instrucao)
        self.assertIn("a Bia", instrucao)

    def test_novidade_recente_e_contada_uma_vez(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = DatabaseManager(Path(temp.name) / "news.db")
        seed_world_bible(db)
        seed_academic(db)
        with db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key,value,updated_at) "
                         "VALUES ('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.execute("INSERT INTO world_bootstrap (key,value,updated_at) "
                         "VALUES ('clean_canonical_start_done','1','2026-09-01')")
        day = SocialDay(db)
        noite = datetime(2026, 9, 21, 23, 0)
        day.materialize(noite)
        news = day.fresh_news(noite, within=timedelta(hours=24))
        self.assertIsNotNone(news)
        day.mark_shared(news["event_key"])
        again = day.fresh_news(noite, within=timedelta(hours=24))
        self.assertTrue(again is None or again["event_key"] != news["event_key"])


class TransitionAnnouncementLiveTests(unittest.TestCase):
    """O aviso de saída estava em código morto; agora sai na resposta."""

    def test_aviso_sai_uma_vez_quando_o_slot_comeca(self):
        import bot
        from unittest.mock import patch
        from proactivity_service import ProactivityService
        from tests.test_world_agenda_audit4 import AgendaTests
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = DatabaseManager(Path(temp.name) / "tr.db")
        seed_world_bible(db)
        seed_academic(db)
        helper = AgendaTests("test_estado_nao_depende_do_rng")
        helper.db, helper.engine = db, RoutineEngine(db)
        _day, (start, end) = helper._gym_day()
        service = ProactivityService(db)
        with patch.object(bot, "proactivity_service", service),              patch.object(bot.memory_manager, "db", db):
            hint = bot._maybe_announce_transition(start)
            self.assertIsNotNone(hint)
            self.assertIn("academia", hint)
            self.assertIsNone(bot._maybe_announce_transition(start + timedelta(minutes=1)))
        state = WorldStateManager(db).resolve(start + timedelta(minutes=5))
        self.assertIn("academia", state["activity"])


class WorldClosureTests(unittest.TestCase):
    """Saídas, segredos e amigos entre si."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "closure.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key,value,updated_at) "
                         "VALUES ('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.execute("INSERT INTO world_bootstrap (key,value,updated_at) "
                         "VALUES ('clean_canonical_start_done','1','2026-09-01')")
        self.day = SocialDay(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def _saidas(self):
        with self.db.get_connection() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM eventos_pendentes WHERE source_key LIKE 'outing:%' ORDER BY event_at")]

    def test_saidas_viram_compromisso_e_ela_esta_la(self):
        from academic_life import AcademicLife
        for week in range(4):
            self.day.schedule_outings(datetime(2026, 9, 21, 8, 0) + timedelta(days=7 * week))
        saidas = self._saidas()
        self.assertGreaterEqual(len(saidas), 4)
        for s in saidas:
            start = datetime.fromisoformat(s["event_at"])
            self.assertFalse(AcademicLife(self.db).conflicting_blocks(start, datetime.fromisoformat(s["end_at"])))
        primeira = datetime.fromisoformat(saidas[0]["event_at"])
        state = WorldStateManager(self.db).resolve(primeira + timedelta(minutes=30))
        self.assertEqual(json.loads(state["source_json"])["reason"], "confirmed_commitment")
        from response_availability import ResponseAvailabilityPolicy
        kind = ResponseAvailabilityPolicy(self.db)._resolve_activity(primeira + timedelta(minutes=31))[0]
        self.assertEqual(kind, "SOCIAL")
        amigos = json.loads(saidas[0]["metadata_json"])["friends"]
        self.day.materialize(primeira + timedelta(minutes=40))
        with self.db.get_connection() as conn:
            encontro = conn.execute("SELECT participants_json FROM life_events WHERE event_key LIKE ?",
                                    (f"social:{primeira.date()}:{amigos[0]}:saida",)).fetchone()
        self.assertIsNotNone(encontro)

    def test_saida_nunca_e_criada_em_cima_da_hora(self):
        self.day.schedule_outings(datetime(2026, 9, 26, 20, 0))  # sábado 20h, bar às 21h
        self.assertFalse(any(s["event_at"].startswith("2026-09-26") for s in self._saidas()))

    def test_segredo_da_amiga_fica_com_a_marina(self):
        from knowledge_privacy import KnowledgePrivacy
        segredo = None
        for offset in range(60):
            d = date(2026, 9, 21) + timedelta(days=offset)
            segredo = next((c for c in self.day.plan(d) if c.secret), None)
            if segredo:
                break
        self.assertIsNotNone(segredo, "nenhum segredo em 60 dias")
        self.day._record(segredo)
        with self.db.get_connection() as conn:
            event_id = conn.execute("SELECT id FROM life_events WHERE event_key=?", (segredo.key,)).fetchone()[0]
        privacy = KnowledgePrivacy(self.db)
        self.assertTrue(privacy.known_by("event", event_id, "marina"))
        self.assertEqual(privacy.decision("event", event_id, "marina", "patrick_ramos").level, "WITHHOLD")
        self.assertEqual(privacy.source_chain("event", event_id, "marina"), (segredo.character_key, "marina"))
        contato = self.day.last_contact(segredo.character_key, segredo.at + timedelta(minutes=1))
        self.assertIn("EM SEGREDO", contato["summary"])

    def test_amigos_falam_uns_dos_outros(self):
        sobre = []
        for offset in range(30):
            sobre += [c for c in self.day.plan(date(2026, 9, 21) + timedelta(days=offset)) if c.about]
        self.assertTrue(sobre)
        from social_day import FRIEND_TIES
        for c in sobre:
            self.assertIn(frozenset({c.character_key, c.about}), FRIEND_TIES)


class LivingCircleTests(unittest.TestCase):
    """NPCs não canônicos nascem, voltam, sobem de nível e entram no cânone."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp.name) / "circle.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key,value,updated_at) "
                         "VALUES ('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.execute("INSERT INTO world_bootstrap (key,value,updated_at) "
                         "VALUES ('clean_canonical_start_done','1','2026-09-01')")
        self.day = SocialDay(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def _encontro(self, d, key="npc_gabi_freitas"):
        return Contact(key=f"teste:{d}:{key}", at=datetime.combine(d, time(9, 30)), character_key=key,
                       channel="presencial", place_key="enseada_botafogo", topic="cachorros")

    def test_primeiro_encontro_cria_npc_e_diz_conheceu(self):
        from world_repository import WorldBibleRepository
        from social_day import short_name
        self.assertIsNone(WorldBibleRepository(self.db).get_character("npc_gabi_freitas"))
        self.day._record(self._encontro(date(2026, 9, 21)))
        npc = WorldBibleRepository(self.db).get_character("npc_gabi_freitas")
        self.assertEqual((npc["character_type"], npc["canon_locked"]), ("ephemeral", 0))
        with self.db.get_connection() as conn:
            resumo = conn.execute("SELECT summary FROM life_events WHERE event_key LIKE 'teste:%'").fetchone()[0]
        self.assertTrue(resumo.startswith("Conheceu a Gabi"))
        self.assertEqual(short_name("npc_seu_ademir"), "o Seu Ademir")

    def test_seis_dias_de_encontro_viram_canone(self):
        from world_repository import WorldBibleRepository
        for offset in range(6):
            self.day._record(self._encontro(date(2026, 9, 21) + timedelta(days=offset)))
            tipo = WorldBibleRepository(self.db).get_character("npc_gabi_freitas")["character_type"]
            if offset == 2:
                self.assertEqual(tipo, "secondary")
        npc = WorldBibleRepository(self.db).get_character("npc_gabi_freitas")
        self.assertEqual((npc["character_type"], npc["canon_locked"]), ("recurring", 1))

    def test_mundo_nao_expoe_assunto_de_conversa(self):
        for offset in range(14):
            self.day.materialize(datetime.combine(date(2026, 9, 21) + timedelta(days=offset), time(23, 59)))
        texto = self.day.world_summary(datetime(2026, 10, 4, 23, 59))
        self.assertIn("O mundo da Marina", texto)
        self.assertNotIn("assunto", texto)

    def test_saida_de_sexta_pode_descobrir_lugar_novo(self):
        from social_day import PLACE_POOL
        for week in range(20):
            self.day.schedule_outings(datetime(2026, 9, 21, 8, 0) + timedelta(days=7 * week))
        chaves = {p[0] for p in PLACE_POOL}
        with self.db.get_connection() as conn:
            usados = {r[0] for r in conn.execute("SELECT location_key FROM eventos_pendentes "
                                                  "WHERE source_key LIKE 'outing:%'")}
            novos = conn.execute("SELECT canon_locked, familiarity FROM world_places WHERE canonical_key IN (%s)"
                                 % ",".join("?" * len(chaves)), tuple(chaves)).fetchall()
        self.assertTrue(usados & chaves)
        self.assertTrue(all(r["canon_locked"] == 0 for r in novos))


if __name__ == "__main__":
    unittest.main()
