"""Detectores de pedido de foto e de áudio.

Soak de 22/09: "o importante vai ser ver você feliz se divertindo na sua sexta"
foi lido como pedido de foto, e a Marina respondeu do nada que "a função tá em
manutenção". Pedido de mídia exige verbo de pedido perto do objeto.
"""
import unittest

import bot


class PhotoRequestTest(unittest.TestCase):
    def test_real_requests(self):
        for texto in [
            "manda uma foto",
            "me manda foto amor",
            "Me manda uma fotinha sua?",
            "tira uma selfie pra mim",
            "bate uma foto do look",
            "cadê minha foto?",
            "quero ver uma foto sua",
            "queria uma fotinha agora",
            "posta foto nova",
            "manda nude",
            "deixa eu te ver",
            "quero te ver agora",
            "me mostra o look",
            "me mostra como você tá",
        ]:
            with self.subTest(texto=texto):
                self.assertTrue(bot.is_photo_request(texto))

    def test_soak_false_positive(self):
        self.assertFalse(bot.is_photo_request(
            "Isso aí minha princesa, o importante vai ser ver você feliz se divertindo "
            "na sua sexta! Falar nisso, já tem algum plano?"))

    def test_mentions_that_are_not_requests(self):
        for texto in [
            "vi uma foto sua no insta",
            "gostei da foto",
            "vou te mandar uma foto do trânsito",
            "quero te mandar uma foto",
            "te mandei uma foto",
            "tirei uma selfie ridícula kkk",
            "olha essa foto que o Théo postou",
            "comprei um batom nude pra minha mãe",
            "quero te ver logo, saudade",
            "troca sua foto de perfil",
        ]:
            with self.subTest(texto=texto):
                self.assertFalse(bot.is_photo_request(texto))

    def test_unavailable_instruction_never_talks_like_a_system(self):
        instrucao = bot.PHOTO_UNAVAILABLE_INSTRUCTION.lower()
        self.assertIn("never mention maintenance", instrucao)
        self.assertNotIn("due to maintenance", instrucao)


class AudioRequestTest(unittest.TestCase):
    def test_real_requests(self):
        for texto in [
            "manda um áudio",
            "me manda audio amor",
            "grava um audinho pra mim",
            "manda mensagem de voz",
            "solta a voz",
            "fala comigo em áudio",
            "fala por voz",
            "quero ouvir sua voz",
            "queria ouvir a tua voz agora",
        ]:
            with self.subTest(texto=texto):
                self.assertTrue(bot.is_audio_request(texto))

    def test_mentions_that_are_not_requests(self):
        for texto in [
            "adoro sua voz",
            "saudade da sua voz",
            "te mandei um áudio",
            "vou te mandar um áudio no caminho",
            "quero te mandar um áudio",
            "o áudio do vídeo tava ruim",
        ]:
            with self.subTest(texto=texto):
                self.assertFalse(bot.is_audio_request(texto))


if __name__ == "__main__":
    unittest.main()
