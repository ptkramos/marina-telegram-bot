"""25/09 (Patrick): ela conta plano com hora certinha ("às 19h30"); gente fala o período."""
import unittest

from chat_naturalness import soften_times


class HoraExataTest(unittest.TestCase):
    def test_falas_reais_viram_periodo(self):
        casos = {
            "Vem sim, tenho um rolê hj às 19h30 no Quartinho com o Theo e a Júlia":
                "Vem sim, tenho um rolê hj à noite no Quartinho com o Theo e a Júlia",
            "acho que vou topar o Quartinho no sábado às 21h": "acho que vou topar o Quartinho no sábado à noite",
            "Tenho aula às 10:00 amanhã": "Tenho aula de manhã amanhã",
            "vou na academia lá pelas 15h": "vou na academia à tarde",
            "saio umas 18h": "saio no fim da tarde",
        }
        for antes, depois in casos.items():
            self.assertEqual(soften_times(antes), depois, antes)

    def test_nao_duplica_o_periodo(self):
        self.assertEqual(soften_times("hoje à noite às 20h eu saio"), "hoje à noite eu saio")
        self.assertEqual(soften_times("de noite às 20h eu saio"), "de noite eu saio")

    def test_se_ele_perguntou_a_hora_fica(self):
        fala = "Saio às 19h30, amor"
        self.assertEqual(soften_times(fala, "que horas você sai?"), fala)
        self.assertEqual(soften_times(fala, "qual o horário do rolê?"), fala)
        self.assertEqual(soften_times(fala, "quando você sai?"), "Saio à noite, amor", "'quando' aceita período")

    def test_lembrete_e_horario_dele_ficam(self):
        """Falas reais: a confirmação do lembrete do dentista e o eco do horário que ele deu."""
        self.assertEqual(soften_times("Lembro sim, amor. Te aviso às 9h30, uma horinha antes do dentista 🖤",
                                      "Sim princesa, vc me lembra uma hora antes?"),
                         "Lembro sim, amor. Te aviso às 9h30, uma horinha antes do dentista 🖤")
        fala = "Vou ficar te esperando pra conversar quando você sair às 19h30."
        self.assertEqual(soften_times(fala, "hoje vou sair as 19:30"), fala)
        self.assertEqual(soften_times("A aula vai até às 15h"), "A aula vai até às 15h")

    def test_intervalo_e_coisa_que_nao_e_hora_ficam(self):
        self.assertEqual(soften_times("aula das 14h às 18h"), "aula das 14h às 18h")
        self.assertEqual(soften_times("comprei 3 blusas"), "comprei 3 blusas")
        self.assertEqual(soften_times("às 8 da manhã"), "às 8 da manhã")


if __name__ == "__main__":
    unittest.main()
