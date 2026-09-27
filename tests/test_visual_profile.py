"""
Testes unitários para o Visual Profile e Continuidade de Câmera da Marina Salles (v3.7.0).
Valida o DNA visual calibrado, detecção de continuidade, seleção de poses/ângulos e persistência de estado.
"""
import time
import unittest
from visual_profile import (
    VisualProfileManager,
    KREA2_TRIGGER,
    KREA2_IDENTITY,
    KREA2_CLOTHED,
    KREA2_NUDE,
    KREA2_BODY_CANON,
)


class TestVisualProfile(unittest.TestCase):

    def setUp(self):
        self.profile = VisualProfileManager()
        self.profile.clear_state()

    def tearDown(self):
        self.profile.clear_state()

    def test_visual_dna_constants(self):
        """Traços da Marina no prompt Krea 2 (o LoRA dela usa o gatilho marinaX)."""
        self.assertEqual(KREA2_TRIGGER, "marinaX")
        self.assertIn("amber-hazel eyes", KREA2_IDENTITY)
        self.assertIn("chestnut brown hair with golden blonde tips", KREA2_IDENTITY)
        self.assertNotRegex(KREA2_IDENTITY, r"\d+\s*(yo|years?)")

    def test_continuity_detection(self):
        """Testa o reconhecimento de pedidos de continuidade e mais fotos."""
        positive_cases = [
            "manda outra foto amor",
            "mais uma por favor",
            "tira outra pra mim",
            "mostra mais",
            "de costas agora",
            "mostra de ladinho",
            "de outro ângulo",
            "muda a pose"
        ]
        for phrase in positive_cases:
            self.assertTrue(
                self.profile.is_continuity_request(phrase),
                f"Deveria detectar continuidade em: '{phrase}'"
            )

        negative_cases = [
            "o que você tá fazendo agora?",
            "bom dia meu amor",
            "como foi seu dia no trabalho?",
            "gostei muito de conversar com você"
        ]
        for phrase in negative_cases:
            self.assertFalse(
                self.profile.is_continuity_request(phrase),
                f"NÃO deveria detectar continuidade em: '{phrase}'"
            )

    def test_nsfw_and_clothed_detection(self):
        """Valida que roupas têm precedência sobre termos ambíguos e detecta NSFW adequadamente."""
        self.assertTrue(self.profile.is_nsfw_text("manda foto nua amor"))
        self.assertTrue(self.profile.is_nsfw_text("quero te ver sem roupa"))
        self.assertTrue(self.profile.is_nsfw_text("mostra seus peitos"))
        
        # Precedência de roupa
        self.assertFalse(self.profile.is_nsfw_text("manda foto vestida com seu vestidinho"))
        self.assertFalse(self.profile.is_nsfw_text("quero ver seu look de hoje"))
        self.assertFalse(self.profile.is_nsfw_text("foto de pijama na cama"))

    def test_focus_angle_extraction(self):
        """Verifica a correta extração de ângulos visuais."""
        self.assertEqual(self.profile.extract_focus_angle("manda de costas amor"), "behind")
        self.assertEqual(self.profile.extract_focus_angle("mostra a bunda"), "behind")
        self.assertEqual(self.profile.extract_focus_angle("de ladinho agora"), "side")
        self.assertEqual(self.profile.extract_focus_angle("foto de perfil lateral"), "side")
        self.assertEqual(self.profile.extract_focus_angle("olhando pra câmera"), "frontal")

    def test_build_scene_prompt_new_session_sfw(self):
        """Constrói prompt SFW garantindo zero nudez e anatomia vestida."""
        prompt, is_nsfw, angle = self.profile.build_scene_prompt(
            scene_description="sitting on sofa drinking coffee, wearing cute hoodie",
            user_intent="manda fotinho amor"
        )
        self.assertFalse(is_nsfw)
        self.assertEqual(angle, "frontal")
        self.assertIn(KREA2_TRIGGER, prompt)
        self.assertIn(KREA2_CLOTHED, prompt)
        self.assertNotIn(KREA2_BODY_CANON, prompt)
        self.assertIn("sitting on sofa", prompt)

    def test_build_scene_prompt_new_session_nsfw(self):
        """Constrói prompt NSFW com anatomia frontal explícita."""
        prompt, is_nsfw, angle = self.profile.build_scene_prompt(
            scene_description="standing in bedroom facing camera",
            user_intent="manda foto pelada amor"
        )
        self.assertTrue(is_nsfw)
        self.assertEqual(angle, "frontal")
        self.assertIn(KREA2_NUDE["frontal"], prompt)
        self.assertIn(KREA2_BODY_CANON, prompt)

    def test_camera_continuity_flow(self):
        """
        Valida a continuidade de look e ambiente:
        Primeira foto: quarto, nua, frontal.
        Segunda foto: 'manda de costas agora amor' -> preserva quarto e nudez, muda para behind.
        """
        # 1. Primeira foto
        initial_scene = "standing in bedroom facing camera"
        prompt1, nsfw1, angle1 = self.profile.build_scene_prompt(
            scene_description=initial_scene,
            user_intent="manda nude amor",
            is_nsfw=True
        )
        self.profile.record_photo_generation(
            scene_tags=initial_scene,
            full_prompt=prompt1,
            is_nsfw=nsfw1,
            focus_angle=angle1,
            location="bedroom"
        )

        state = self.profile.get_last_state()
        self.assertIsNotNone(state)
        self.assertEqual(state.location, "bedroom")
        self.assertTrue(state.is_nsfw)

        # 2. Continuidade: pede outra foto de costas
        prompt2, nsfw2, angle2 = self.profile.build_scene_prompt(
            scene_description="mais uma foto",
            user_intent="agora manda de costas amor"
        )

        self.assertTrue(nsfw2, "Deve manter o estado de nudez da sessão")
        self.assertEqual(angle2, "behind", "Deve alternar para o ângulo behind")
        self.assertIn("bedroom", prompt2, "Deve manter o mesmo ambiente (bedroom)")
        self.assertIn(KREA2_NUDE["behind"], prompt2, "Deve usar o bloco de costas")

    def test_friends_visual_contrasts_with_marina(self):
        """28/09: amiga só por texto, com contraste de estrutura e sem os traços da Marina."""
        from visual_profile import FRIENDS_VISUAL, HAIR_COLOR
        import civitai_images as ci
        from pathlib import Path
        self.assertLessEqual({"carol_menezes", "julia_azevedo", "theo_martins"}, set(FRIENDS_VISUAL))
        for key, friend in FRIENDS_VISUAL.items():
            with self.subTest(key):
                self.assertTrue(friend["en"] and friend["pt"] and len(friend["style"]) == 2)
                for trait in ("amber", "freckles", HAIR_COLOR, KREA2_TRIGGER):
                    self.assertNotIn(trait, friend["en"])
                self.assertNotRegex(friend["en"], r"\b(no|not|without)\b")
                self.assertTrue((Path(ci.__file__).resolve().parent / ci.FRIEND_RG[key]).is_file())
        self.assertNotIn("choker", FRIENDS_VISUAL["bia_andrade"]["en"], "acessório é estilo, não quem ela é")
        self.assertNotIn("gloss", FRIENDS_VISUAL["carol_menezes"]["en"], "maquiagem é estilo")
        self.assertNotIn("eyeliner", FRIENDS_VISUAL["julia_azevedo"]["en"], "maquiagem é estilo")

    def test_friend_face_swap_keeps_marina_side(self):
        """28/09: da edição fica só o lado da amiga; o lado da Marina é o original, pixel a pixel."""
        import io
        from PIL import Image
        import civitai_images as ci

        def jpg(color):
            out = io.BytesIO()
            Image.new("RGB", (400, 600), color).save(out, "JPEG", quality=100)
            return out.getvalue()
        merged = Image.open(io.BytesIO(ci.paste_side(jpg((200, 30, 30)), jpg((30, 30, 200)), "right")))
        self.assertGreater(merged.getpixel((20, 300))[0], 180)    # lado da Marina: original
        self.assertGreater(merged.getpixel((390, 300))[2], 180)   # lado da amiga: editado
        body = ci.friend_edit_body(b"a", b"b", side="right", who="the woman with wavy hair", width=400, height=600)
        step = body["steps"][0]["input"]
        self.assertEqual((step["model"], step["operation"], step["loras"]), ("edit", "editImage", {}))
        self.assertEqual(len(step["images"]), 2)
        self.assertFalse(body["allowMatureContent"])
        self.assertIn("Give the woman on the right", step["prompt"])
        man = ci.friend_edit_body(b"a", b"b", side="left", who="the man", width=400, height=600, noun="man")
        self.assertIn("the exact face of the man in the second image", man["steps"][0]["input"]["prompt"])

    def test_friend_seam_goes_where_both_images_agree(self):
        """28/09: o editor redesenha a amiga mais pro lado/embaixo; a costura não pode cortar o rosto novo
        (a emenda fixa em 56% deixava um olho fantasma). O que mudou a partir de 50% vem inteiro da edição."""
        import io
        from PIL import Image, ImageDraw
        import civitai_images as ci

        def jpg(img):
            out = io.BytesIO()
            img.save(out, "JPEG", quality=100)
            return out.getvalue()
        orig = Image.new("RGB", (400, 600), (120, 120, 120))
        ed = orig.copy()
        ImageDraw.Draw(ed).rectangle([200, 0, 399, 599], fill=(30, 30, 200))   # a amiga nova começa em 50%
        for side, probe_ed, probe_orig in (("right", (208, 300), (150, 300)), ("left", (191, 300), (249, 300))):
            src = ed if side == "right" else ed.transpose(Image.FLIP_LEFT_RIGHT)
            merged = Image.open(io.BytesIO(ci.paste_side(jpg(orig), jpg(src), side)))
            self.assertGreater(merged.getpixel(probe_ed)[2], 180, side)
            self.assertLess(abs(merged.getpixel(probe_orig)[0] - 120), 12, side)
            self.assertGreater(merged.getpixel((probe_ed[0], 598))[2], 180, "a costura vai até o pé da foto")


if __name__ == "__main__":
    unittest.main()
