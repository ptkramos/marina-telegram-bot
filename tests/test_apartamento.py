"""C.1b — cânone visual do apartamento (claro e praiano, Patrick 24/09)."""
import unittest
from datetime import datetime

import apartamento
import civitai_images as ci
import visual_profile as vp


class ApartamentoTest(unittest.TestCase):
    def test_room_from_text(self):
        self.assertEqual(apartamento.room_for("deitada na cama"), "quarto")
        self.assertEqual(apartamento.room_for("saindo do banho"), "banheiro")
        self.assertEqual(apartamento.room_for("selfie no espelho do closet"), "closet")
        self.assertEqual(apartamento.room_for("no sofá vendo série"), "sala")
        self.assertEqual(apartamento.room_for("living room"), "sala")
        self.assertIsNone(apartamento.room_for("na rua"))

    def test_same_words_every_time(self):
        a = apartamento.scene("quarto", datetime(2026, 9, 24, 9, 0))
        b = apartamento.scene("quarto", datetime(2026, 9, 25, 9, 0))
        self.assertEqual(a, b)
        self.assertIn("rattan headboard", a)

    def test_light_follows_the_hour_and_weather(self):
        self.assertIn("morning", apartamento.light("quarto", datetime(2026, 9, 24, 7, 0)))
        self.assertIn("golden", apartamento.light("sala", datetime(2026, 9, 24, 17, 0)))
        self.assertIn("lamp", apartamento.light("quarto", datetime(2026, 9, 24, 22, 0)))
        self.assertIn("overcast", apartamento.light("sala", datetime(2026, 9, 24, 12, 0), "chuva fraca"))
        self.assertIn("ring light", apartamento.light("closet", datetime(2026, 9, 24, 12, 0)))

    def test_no_negation_in_the_canon(self):
        for room in apartamento.ROOMS.values():
            self.assertNotRegex(room["scene"].lower(), r"\b(no|without|not)\b")

    def test_room_canon_does_not_trigger_wetness(self):
        bath = apartamento.scene("banheiro", datetime(2026, 9, 24, 21, 0))
        loras, _ = ci.conditional_loras(f"Scene: brushing her hair. {bath}.", is_nsfw=False)
        self.assertNotIn(ci.KREA2_WETNESS, loras)
        loras, _ = ci.conditional_loras(f"Scene: under the shower, water running. {bath}.", is_nsfw=False)
        self.assertIn(ci.KREA2_WETNESS, loras)

    def test_propped_phone_is_not_a_selfie(self):
        p = vp.krea2_prompt("standing by the bed, phone propped on the shelf with the timer", is_nsfw=False)
        self.assertTrue(p.startswith(vp.KREA2_FRAMING_PROPPED))
        self.assertIn(ci.NOT_SELFIE_MARK, p)
        self.assertNotIn("friend", p)


if __name__ == "__main__":
    unittest.main()
