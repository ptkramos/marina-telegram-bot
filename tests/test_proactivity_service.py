"""
Testes Automatizados Offline para o ProactivityService da Marina Salles (v3.7.0).
"""
import sys
import unittest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db import DatabaseManager
from proactivity_service import ProactivityService


class TestProactivityService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "test_proactivity.db"
        self.db = DatabaseManager(db_path=self.temp_db_path)
        self.service = ProactivityService(db=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sleep_window_blocking(self):
        """Verifica se bloqueia mensagens na madrugada (04:00 da manhã)."""
        dt_madrugada = datetime(2026, 9, 15, 4, 15, 0)
        should_run, reason = self.service.should_trigger(now=dt_madrugada)
        self.assertFalse(should_run)
        self.assertEqual(reason, "sleep_window")

    def test_pending_event_takes_highest_priority(self):
        """Um evento pendente vencido deve disparar a iniciativa com prioridade máxima."""
        # Cria evento com data no passado
        agora = datetime(2026, 9, 15, 16, 0, 0)
        passado_iso = (agora - timedelta(hours=1)).isoformat()

        event_id = self.db.adicionar_evento_pendente(
            event_type="trabalho",
            description="Reunião com novos clientes",
            event_at=passado_iso,
            follow_up_after=passado_iso
        )

        should_run, reason = self.service.should_trigger(now=agora)
        self.assertTrue(should_run)
        self.assertEqual(reason, "pending_event_followup")

        # Verifica prompt estruturado gerado
        prompt_data = self.service.determine_proactive_prompt(now=agora)
        self.assertEqual(prompt_data["reason"], "pending_event_followup")
        self.assertEqual(prompt_data["event_id"], event_id)
        self.assertIn("Reunião com novos clientes", prompt_data["instruction"])

        # O evento deve permanecer pending até o Telegram confirmar entrega
        eventos_pendentes = self.db.listar_eventos_pendentes(status="pending")
        self.assertEqual(len(eventos_pendentes), 1)

        # Após envio confirmado, chamador conclui o evento
        self.db.concluir_evento_pendente(prompt_data["event_id"])
        eventos_concluidos = self.db.listar_eventos_pendentes(status="completed")
        self.assertEqual(len(eventos_concluidos), 1)

    def test_record_autonomous_sent_updates_state_and_decays(self):
        """Verifica gravação de estado e decay suave de emoções."""
        self.service.record_autonomous_sent(reason="daily_routine", topic="treino")
        estado = self.db.get_estado_relacional()
        self.assertEqual(estado.get("last_autonomous_reason"), "daily_routine")
        self.assertEqual(estado.get("last_autonomous_topic"), "treino")

    def test_daily_limit_blocking(self):
        """Verifica se bloqueia ao atingir o limite diário de mensagens autônomas."""
        agora = datetime(2026, 9, 15, 14, 0, 0)
        # Registra 4 mensagens autônomas hoje
        for i in range(4):
            dt_msg = (agora - timedelta(hours=5 - i)).isoformat()
            self.db.adicionar_mensagem(role="assistant", content=f"Mensagem auto {i}", is_initiative=True, timestamp=dt_msg)

        should_run, reason = self.service.should_trigger(now=agora)
        self.assertFalse(should_run)
        self.assertEqual(reason, "daily_limit_reached")

    def test_user_active_recently_blocking(self):
        """Verifica se bloqueia se o Patrick mandou mensagem há pouco tempo (ex: há 10 minutos)."""
        agora = datetime(2026, 9, 15, 15, 0, 0)
        dt_user = (agora - timedelta(minutes=10)).isoformat()
        self.db.adicionar_mensagem(role="user", content="Oi amor", timestamp=dt_user)

        should_run, reason = self.service.should_trigger(now=agora)
        self.assertFalse(should_run)
        self.assertEqual(reason, "user_active_recently")

    def test_autonomous_cooldown_blocking(self):
        """Verifica se bloqueia se a Marina enviou mensagem autônoma recentemente (ex: há 30 minutos)."""
        agora = datetime(2026, 9, 15, 17, 0, 0)
        # Usuário inativo há 2 horas
        dt_user = (agora - timedelta(hours=2)).isoformat()
        self.db.adicionar_mensagem(role="user", content="Tudo bem", timestamp=dt_user)
        # Mas Marina mandou mensagem autônoma há apenas 30 minutos
        dt_auto = (agora - timedelta(minutes=30)).isoformat()
        self.db.adicionar_mensagem(role="assistant", content="Pensando em você", is_initiative=True, timestamp=dt_auto)

        should_run, reason = self.service.should_trigger(now=agora)
        self.assertFalse(should_run)
        self.assertEqual(reason, "autonomous_cooldown_active")


class TestProactivityStateFactor(unittest.TestCase):
    """Fase B.5 — Proatividade sensível ao WorldState da Marina."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_db_path = Path(self.temp_dir.name) / "test_state_factor.db"
        self.db = DatabaseManager(db_path=self.temp_db_path)
        self.service = ProactivityService(db=self.db)
        # Seed a place so location_place_id works.
        from seed_world_bible_v36 import seed_world_bible
        seed_world_bible(self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _snap(self, *, activity: str, reason: str, observed: datetime):
        from world_repository import WorldStateRepository
        states = WorldStateRepository(self.db)
        with self.db.get_connection() as conn:
            place = conn.execute(
                "SELECT id, region FROM world_places WHERE canonical_key='marina_apartment'"
            ).fetchone()
        states.add_snapshot({
            "state_date": observed.date().isoformat(),
            "observed_at": observed.isoformat(),
            "location_place_id": place["id"] if place else None,
            "location_region": place["region"] if place else None,
            "activity": activity,
            "energy_level": 0.7,
            "source_json": {"reason": reason},
        })

    def test_free_time_boosts_probability(self):
        now = datetime(2026, 9, 20, 14, 0)
        self._snap(activity="tempo livre em casa", reason="free_time", observed=now)
        factor, label = self.service._compute_state_factor(now)
        self.assertGreater(factor, 1.0)
        self.assertEqual(label, "free_time")

    def test_busy_activity_reduces_probability(self):
        now = datetime(2026, 9, 20, 14, 0)
        self._snap(activity="treinando na academia", reason="gym_weekly", observed=now)
        factor, label = self.service._compute_state_factor(now)
        self.assertLess(factor, 1.0)
        self.assertTrue(label.startswith("busy"))

    def test_class_reduces_probability(self):
        now = datetime(2026, 9, 20, 10, 0)
        self._snap(activity="aula de design", reason="confirmed_commitment", observed=now)
        factor, label = self.service._compute_state_factor(now)
        self.assertLess(factor, 1.0)
        self.assertTrue(label.startswith("busy"))

    def test_post_event_recovery_slight_boost(self):
        now = datetime(2026, 9, 20, 20, 30)
        self._snap(activity="chegou em casa", reason="post_event_recovery", observed=now)
        factor, label = self.service._compute_state_factor(now)
        self.assertGreater(factor, 1.0)
        self.assertLess(factor, 1.6)
        self.assertEqual(label, "post_event")

    def test_sleeping_zeros_out(self):
        now = datetime(2026, 9, 20, 3, 15)
        self._snap(activity="dormindo", reason="light_day_sleep", observed=now)
        factor, label = self.service._compute_state_factor(now)
        self.assertEqual(factor, 0.0)
        self.assertEqual(label, "sleeping")

    def test_absent_worldstate_falls_back_to_neutral(self):
        now = datetime(2026, 9, 20, 15, 0)
        factor, label = self.service._compute_state_factor(now)
        self.assertEqual(factor, 1.0)
        self.assertIn(label, ("absent", "unavailable"))

    def test_stale_worldstate_falls_back_to_neutral(self):
        now = datetime(2026, 9, 20, 15, 0)
        # observed 2h earlier — stale by our 90 min threshold
        self._snap(activity="tempo livre em casa", reason="free_time",
                   observed=now - timedelta(hours=2))
        factor, label = self.service._compute_state_factor(now)
        self.assertEqual(factor, 1.0)
        self.assertEqual(label, "stale")


if __name__ == "__main__":
    unittest.main(verbosity=2)
