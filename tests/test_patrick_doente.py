"""25/09: Patrick com amigdalite e ela respondeu como farmacêutica (dose, bula, sinais de alerta)."""
import unittest

from health import PATRICK_SICK_HINT, patrick_sick_hint


class PatrickDoenteTest(unittest.TestCase):
    def test_the_morning_messages_trigger_the_hint(self):
        for t in ("Bom dia princesa, dormi sim, mas acordei dodói",
                  "Minha amigdalite atacou, então tô com a garganta fechada, um pouco de dor no corpo…",
                  "Já tomei um ibuprofeno aqui", "tô gripado", "passando mal aqui"):
            self.assertEqual(patrick_sick_hint([t]), PATRICK_SICK_HINT, t)

    def test_follow_up_without_symptom_still_counts_from_recent(self):
        self.assertTrue(patrick_sick_hint(["Nem fui trabalhar hoje", "acordei dodói"]))

    def test_normal_chat_does_not(self):
        for t in ("bom dia amor", "tô morrendo de saudade", "que calor hoje", "fui na academia"):
            self.assertEqual(patrick_sick_hint([t]), "", t)

    def test_hint_forbids_the_pharmacist_voice(self):
        for w in ("bula", "dose", "namorada"):
            self.assertIn(w, PATRICK_SICK_HINT)


if __name__ == "__main__":
    unittest.main()
