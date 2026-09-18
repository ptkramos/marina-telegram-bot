"""
Testes unitários para o Visual Profile e Continuidade de Câmera da Marina Salles (v3.7.0).
Valida o DNA visual calibrado, detecção de continuidade, seleção de poses/ângulos e persistência de estado.
"""
import time
import unittest
from visual_profile import (
    VisualProfileManager,
    MARINA_VISUAL_DNA_BASE,
    MARINA_PHYSIQUE_DNA,
    MARINA_REALISM_TAGS,
    ANATOMY_SFW,
    ANATOMY_NSFW_FRONTAL,
    ANATOMY_NSFW_BEHIND,
    ANATOMY_NSFW_SIDE
)


class TestVisualProfile(unittest.TestCase):

    def setUp(self):
        self.profile = VisualProfileManager()
        self.profile.clear_state()

    def tearDown(self):
        self.profile.clear_state()

    def test_visual_dna_constants(self):
        """Valida que o DNA visual possui os traços marcantes calibrados da Marina."""
        self.assertIn("marina_reference", MARINA_VISUAL_DNA_BASE)
        self.assertIn("19yo woman", MARINA_VISUAL_DNA_BASE)
        self.assertIn("honey-amber eyes", MARINA_VISUAL_DNA_BASE)
        self.assertIn("chocolate brown hair with golden blonde tips", MARINA_VISUAL_DNA_BASE)
        self.assertIn("athletic model physique", MARINA_PHYSIQUE_DNA)
        self.assertIn("round bubble butt", MARINA_PHYSIQUE_DNA)
        self.assertIn("beach golden tan", MARINA_PHYSIQUE_DNA)
        self.assertIn("bikini tan lines", MARINA_PHYSIQUE_DNA)
        self.assertIn("high realism", MARINA_REALISM_TAGS)


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
        self.assertIn(MARINA_VISUAL_DNA_BASE, prompt)
        self.assertIn(ANATOMY_SFW, prompt)
        self.assertIn("sitting on sofa", prompt)

    def test_build_scene_prompt_new_session_nsfw(self):
        """Constrói prompt NSFW com anatomia frontal explícita."""
        prompt, is_nsfw, angle = self.profile.build_scene_prompt(
            scene_description="standing in bedroom facing camera",
            user_intent="manda foto pelada amor"
        )
        self.assertTrue(is_nsfw)
        self.assertEqual(angle, "frontal")
        self.assertIn(ANATOMY_NSFW_FRONTAL, prompt)
        self.assertIn(MARINA_PHYSIQUE_DNA, prompt)

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
        self.assertIn(ANATOMY_NSFW_BEHIND, prompt2, "Deve usar o bloco anatômico traseiro")


if __name__ == "__main__":
    unittest.main()
