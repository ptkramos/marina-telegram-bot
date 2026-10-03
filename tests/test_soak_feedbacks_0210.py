"""Os /feedback do Patrick de 02/10 (soak, dia 4) que ficaram sem leitura — item 25 do painel:
1. 11:36 "me respondeu durante o banho": o banho começou 11:24 e o último retrato era o Instagram das 10:57, ainda
   fresco — a disponibilidade não via o banho; o tick dos rituais saía cedo no banho sem atualizar o mundo; e a foto
   dele (11:35) nem passava pela disponibilidade.
2. 18:50 "durante o se arrumando o banho coloca o telefone dela como no bolso": o card dizia "No bolso" no banho.
3. 19:06 secando o cabelo e o Por fora com a roupa da academia: do banho até o passo da roupa, de toalha.
4. 19:54 "se atrasou por ter mudado de look" e o Por fora com a mesma roupa: a troca acontece de verdade.
5. 23:36 "ela já tinha respondido e depois respondeu de novo": ele escreveu no meio dos 9 balões do resumo do dia.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agenda import Etapa, Passo
from db import DatabaseManager
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible


def at(h, m=0, s=0):
    return datetime(2026, 10, 2, h, m, s)


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "f.db")
        seed_world_bible(self.db)
        seed_academic(self.db)


class BanhoDisponibilidadeTest(_Base):
    def _instagram_das_10_57(self):
        with self.db.get_connection() as conn:
            casa = conn.execute("SELECT id FROM world_places WHERE canonical_key='marina_apartment'").fetchone()["id"]
            conn.execute("INSERT INTO world_state(state_date, observed_at, location_place_id, activity, source_json) "
                         "VALUES (?,?,?,?,?)",
                         ("2026-10-02", at(10, 57, 53).isoformat(), casa, "em casa, olhando o Instagram (sala)",
                          json.dumps({"reason": "free_time", "slot_end": at(12, 0).isoformat()})))
            conn.commit()

    def test_banho_depois_do_retrato_segura_a_resposta(self):
        from response_availability import ResponseAvailabilityPolicy
        from rituals import Rituals
        self._instagram_das_10_57()
        Rituals(self.db).start_shower(at(11, 22), 40)            # ritual.banho start=11:24 end=12:04
        d = ResponseAvailabilityPolicy(self.db).evaluate("Tá bom bb", now=at(11, 34, 55), telegram_message_id=1)
        self.assertEqual(d.activity_type, "SHOWER")
        self.assertEqual(d.decision, "DEFER")

    def test_retrato_depois_do_banho_nao_resolve_de_novo(self):
        from response_availability import ResponseAvailabilityPolicy
        from rituals import Rituals
        Rituals(self.db).start_shower(at(10, 50), 20)
        self._instagram_das_10_57()
        self.assertFalse(ResponseAvailabilityPolicy(self.db)._transition_after(
            dict(self.db.get_connection().execute("SELECT * FROM world_state ORDER BY id DESC").fetchone()),
            at(11, 0)))

    def test_tick_no_banho_atualiza_o_mundo(self):
        from rituals import Rituals
        r = Rituals(self.db)
        r.start_shower(at(11, 22), 40)
        with patch.object(Rituals, "_state", return_value=("SHOWER", "tomando banho")) as estado:
            self.assertIsNone(r.tick(at(11, 27, 53)))
        estado.assert_called_once()

    def test_foto_adiada_leva_o_que_a_foto_mostra(self):
        from vision_service import foto_adiada_texto
        repr_ = "[Foto enviada pelo Patrick: Olha 🙌]"
        self.assertEqual(foto_adiada_texto(repr_, {"scene": "um mangá novo ainda no plástico em cima da mesa"}),
                         "[Foto enviada pelo Patrick: Olha 🙌] (o que aparece na foto: um mangá novo ainda no plástico "
                         "em cima da mesa)")
        self.assertEqual(foto_adiada_texto(repr_, {"scene": "foto enviada pelo Patrick", "error": "json"}), repr_)


class CelularNoBanhoTest(_Base):
    def test_passo_do_banho_pega_apos_o_banho(self):
        from agenda import Agenda
        e = Etapa("arrumando", "Se arrumando", at(18, 31), at(19, 50), linha2="Vai sair pro Quartinho Bar",
                  celular="Olha de vez em quando", chave="prep:x", prep_tipo="noite",
                  passos=[Passo("Tomando banho", at(18, 31)), Passo("Secando cabelo", at(19, 0)),
                          Passo("Escolhendo roupa", at(19, 29)), Passo("Saindo", at(19, 43))])
        with patch.object(Agenda, "etapas", return_value=[e]):
            card = Agenda(self.db).card(at(18, 50))
            celular = next(g[2] for g in card["grade"] if g[1] == "Celular")
            self.assertEqual(celular, "Pega após o banho")
            card = Agenda(self.db).card(at(19, 6))
            self.assertEqual(next(g[2] for g in card["grade"] if g[1] == "Celular"), "No bolso")


class RoupaDoSeArrumandoTest(_Base):
    def setUp(self):
        super().setUp()
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) "
                         "VALUES ('clean_canonical_start_done','1','2026-09-01')")
            conn.commit()
        self.etapa = None
        for alvo, kw in (("roupa.Roupa._em_casa", {"return_value": True}),
                         ("roupa.Roupa._na_cama", {"return_value": False}),
                         ("roupa.Roupa._no_banho", {"return_value": False}),
                         ("roupa.Roupa._feeling", {"return_value": SimpleNamespace(valence=0.6, energy=0.6,
                                                                                   libido=0.2, episodes=[])}),
                         ("roupa.Roupa._intimo_turno", {"return_value": (None, {})}),
                         ("agenda.Agenda.agora", {"side_effect": lambda now: self.etapa}),
                         ("agenda.Agenda.etapas", {"return_value": []})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)

    def _quartinho(self, avisos=()):
        passos = [Passo("Tomando banho", at(18, 31)), Passo("Secando cabelo", at(19, 0)),
                  Passo("Fazendo maquiagem", at(19, 14)), Passo("Escolhendo roupa", at(19, 29)),
                  Passo("Saindo", at(20, 4))]
        passos += [Passo(t, a, aviso=True) for a, t in avisos]
        return Etapa("arrumando", "Se arrumando", at(18, 31), at(20, 10), linha2="Vai sair pro Quartinho Bar",
                     passos=sorted(passos, key=lambda p: p.inicio), chave="prep:outing:2026-10-02:m1931",
                     prep_tipo="noite")

    def test_secando_o_cabelo_de_toalha(self):
        from roupa import KEY, Roupa
        r = Roupa(self.db)
        r.tick(at(16, 29))                                       # (a roupa da academia no caso real)
        self.etapa = self._quartinho()
        r.tick(at(19, 6))
        p = r.painel(at(19, 6))
        self.assertEqual(p["look"], "Enrolada na toalha")
        self.assertNotIn("Para", [l[1] for l in p["linhas"]])
        self.assertIn("enrolada na toalha", "\n".join(r.prompt_lines(at(19, 6))))
        r.tick(at(19, 35))
        st = json.loads(self.db.get_estado_relacional(KEY))
        self.assertEqual(st["atual"]["ocasiao"], "sair")
        self.assertEqual(st["atual"]["desde"][11:16], "19:29")

    def test_trocou_de_look_troca_a_roupa(self):
        from roupa import KEY, Roupa
        r = Roupa(self.db)
        r.tick(at(16, 29))
        self.etapa = self._quartinho(avisos=[(at(19, 43), "Trocou de look")])
        r.tick(at(19, 35))
        primeiro = json.loads(self.db.get_estado_relacional(KEY))["atual"]["look"]
        r.tick(at(19, 54))
        st = json.loads(self.db.get_estado_relacional(KEY))
        self.assertNotEqual(st["atual"]["look"], primeiro)
        self.assertEqual((st["atual"]["ocasiao"], st["atual"]["desde"][11:16]), ("sair", "19:43"))
        r.tick(at(19, 58))
        self.assertEqual(json.loads(self.db.get_estado_relacional(KEY))["atual"]["desde"][11:16], "19:43",
                         "troca uma vez só")

    def test_de_lingerie_pra_dormir_nao_vira_toalha(self):
        from roupa import KEY, Roupa
        r = Roupa(self.db)
        r.tick(at(22, 0))
        st = json.loads(self.db.get_estado_relacional(KEY))
        st["atual"] = {"look": ["renda_preta"], "ocasiao": "provocar", "desde": at(22, 0).isoformat(),
                       "pra": "Te provocar", "chave": ""}
        self.db.set_estado_relacional(KEY, json.dumps(st))
        self.etapa = Etapa("arrumando", "Indo dormir", at(23, 0), at(23, 50), chave="prep:dormir:x", prep_tipo="dormir",
                           passos=[Passo("Tirando maquiagem", at(23, 0)), Passo("Tomando banho", at(23, 10)),
                                   Passo("Colocando pijama", at(23, 40))])
        r.tick(at(23, 20))
        self.assertEqual(json.loads(self.db.get_estado_relacional(KEY))["atual"]["ocasiao"], "provocar")


class MensagemCruzadaTest(unittest.TestCase):
    BALOES = [(at(23, 34, 7), "Kkkkk tá bom, senhor entrevistador"), (at(23, 34, 9), "Hj foi bem cheio, mas gostoso"),
              (at(23, 34, 12), "De manhã fiquei em casa, dps comi açaí e um croissant"),
              (at(23, 34, 15), "À noite saí com a Júlia pro Quartinho"),
              (at(23, 34, 19), "Depois teve fritas, caipirinha e Uber dividido"),
              (at(23, 34, 22), "Agora tô vendo Paradise Kiss")]

    def test_escreveu_no_meio_dos_baloes(self):
        from chat_naturalness import mensagem_cruzada_hint
        dica = mensagem_cruzada_hint(self.BALOES, at(23, 34, 10))
        self.assertIn("[MENSAGENS CRUZADAS]", dica)
        self.assertIn("tinha lido até «Hj foi bem cheio, mas gostoso»", dica)
        self.assertIn("De manhã fiquei em casa", dica)
        self.assertNotIn("senhor entrevistador", dica.split("chegaram depois")[1])

    def test_escreveu_depois_ou_muito_antes(self):
        from chat_naturalness import mensagem_cruzada_hint
        self.assertEqual(mensagem_cruzada_hint(self.BALOES, at(23, 34, 39)), "")
        self.assertEqual(mensagem_cruzada_hint(self.BALOES, at(23, 20)), "", "lote adiado não é cruzar")
        self.assertIn("nenhum balão", mensagem_cruzada_hint(self.BALOES, at(23, 34, 5)))


class PixDoUberTest(_Base):
    def test_pix_logo_depois_de_combinar_o_uber(self):
        """19:44 "Quer que eu pague um Uber?", 19:45 "Vou mandar aqui pera", 19:46 o pix de R$ 200."""
        import financas
        for quando, fala in ((at(19, 44, 44), "Quer que eu pague um Uber? Tá chovendo aqui, n sei aí"),
                             (at(19, 45, 36), "Vou mandar aqui pera")):
            self.db.adicionar_mensagem(role="user", content=fala, timestamp=quando.isoformat())
        res = financas.receive_pix(self.db, 200, "", at(19, 46, 49))
        texto = financas.pix_turn_text(200, "", res)
        self.assertNotIn("sem você pedir", texto)
        self.assertIn("pague um Uber", texto)
        self.assertIn("Vou mandar aqui pera", texto)

    def test_pix_do_nada_continua_presente(self):
        import financas
        self.db.adicionar_mensagem(role="user", content="Quer que eu pague um Uber?", timestamp=at(17, 0).isoformat())
        res = financas.receive_pix(self.db, 50, "", at(19, 46))
        self.assertIn("de presente, sem você pedir", financas.pix_turn_text(50, "", res))


class RisoNoComecoTest(unittest.TestCase):
    """14:34: "Kkkkk vc quer atenção premium, é?" e "Kkkkk olha ele exigente hoje", um atrás do outro."""

    def test_tique_sai_e_a_fala_fica(self):
        from chat_naturalness import thin_opening_laugh
        anteriores = ["Kkkkk vc quer atenção premium, é?"]
        self.assertEqual(thin_opening_laugh("Kkkkk olha ele exigente hoje", anteriores), "Olha ele exigente hoje")
        self.assertEqual(thin_opening_laugh("KKKK dei meu momento patricinha total hj", anteriores),
                         "Dei meu momento patricinha total hj")
        self.assertEqual(thin_opening_laugh("Kkkkk\nTá bom, senhor entrevistador", anteriores),
                         "Tá bom, senhor entrevistador")

    def test_risada_de_vez_em_quando_e_risada_sozinha_ficam(self):
        from chat_naturalness import thin_opening_laugh
        self.assertEqual(thin_opening_laugh("Kkkkk olha ele", ["Kkkk ok", "Tô aqui", "Sim, cheguei", "Boa noite", "Oi"]),
                         "Kkkkk olha ele", "a última que abriu rindo foi há 5 respostas")
        self.assertEqual(thin_opening_laugh("Kkkkk", ["Kkkkk sim"]), "Kkkkk")
        self.assertEqual(thin_opening_laugh("Kkkkk 🤣", ["Kkkkk sim"]), "Kkkkk 🤣")
        self.assertEqual(thin_opening_laugh("Kika chegou", ["Kkkkk sim"]), "Kika chegou")


class RedeSocialNaMaoTest(_Base):
    def test_olhando_o_x_e_celular_na_mao(self):
        from response_availability import ResponseAvailabilityPolicy
        mapa = ResponseAvailabilityPolicy(self.db)._map_place_activity
        self.assertEqual(mapa("marina_apartment", "em casa, olhando o X (sala)"), "HOME_RELAXING")
        self.assertEqual(mapa("marina_apartment", "em casa, vendo Botafogo x Vasco (sala)"), "HOME_BUSY")


if __name__ == "__main__":
    unittest.main()
