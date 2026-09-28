"""Roupa e make de verdade (Patrick, 28/09): o look do momento vira estado (peças fixas que repetem, troca pela vida
dela), a make é feita no Se arrumando e borra, a gaveta íntima entra quando ela quer provocar, e a foto, o prompt e
o bloco "Agora" da aba Por fora leem daqui."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from db import DatabaseManager
from seed_world_bible_v36 import seed_world_bible
from agenda import Etapa, Passo
from roupa import INTIMO, KEY, LOOKS, Roupa, en_look, nome_look

T = datetime(2026, 9, 26, 15, 0)   # sábado


def _prep(tipo: str, inicio: datetime, passos, chave: str = "prep:x") -> Etapa:
    lista, at = [], inicio
    for texto, minutos in passos:
        lista.append(Passo(texto, at))
        at += timedelta(minutes=minutos)
    return Etapa("arrumando", "Se arrumando", inicio, at, linha2="Vai sair pro Quartinho às 20:30",
                 passos=lista, chave=chave, prep_tipo=tipo)


class RoupaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "r.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES ('clean_canonical_start_done','1','2026-09-01')")
            conn.commit()
        self.casa, self.cama, self.banho, self.etapa, self.turno = True, False, False, None, None
        self.feeling = SimpleNamespace(valence=0.6, energy=0.6, libido=0.4, episodes=[])
        for alvo, kw in (("roupa.Roupa._em_casa", {"side_effect": lambda snap=None: self.casa}),
                         ("roupa.Roupa._na_cama", {"side_effect": lambda now: self.cama}),
                         ("roupa.Roupa._no_banho", {"side_effect": lambda now: self.banho}),
                         ("roupa.Roupa._feeling", {"side_effect": lambda now: self.feeling}),
                         ("roupa.Roupa._intimo_turno", {"side_effect": lambda now: (self.turno, {})}),
                         ("roupa.Roupa._acordou_ha", {"return_value": timedelta(hours=8)}),
                         ("agenda.Agenda.agora", {"side_effect": lambda now: self.etapa}),
                         ("agenda.Agenda.etapas", {"return_value": []})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)
        self.r = Roupa(self.db)

    def st(self) -> dict:
        return json.loads(self.db.get_estado_relacional(KEY))

    def eventos(self, like: str) -> list:
        with self.db.get_connection() as conn:
            return [r["summary"] for r in conn.execute("SELECT summary FROM life_events WHERE event_key LIKE ?",
                                                        (like,))]

    def test_partida_em_casa_sem_make(self):
        p = self.r.painel(T)
        self.assertIn(tuple(self.st()["atual"]["look"]), LOOKS["casa_dia"])
        self.assertEqual(p["linhas"], [["hanger", "Pra quê", "Ficar em casa, desde 15:00"],
                                       ["brush", "Make", "Sem make"]])
        self.assertIsNone(p["make"])
        self.assertIn("Make: sem make", "\n".join(self.r.prompt_lines(T)))

    def test_se_arrumando_pra_noite_make_e_roupa_de_sair(self):
        self.r.tick(T)
        self.etapa = _prep("noite", datetime(2026, 9, 26, 19, 0),
                           [("Tomando banho", 25), ("Secando cabelo", 20), ("Fazendo maquiagem", 25),
                            ("Escolhendo roupa", 20), ("Chamando uber", 10)])
        self.r.tick(datetime(2026, 9, 26, 19, 30))
        self.assertEqual(self.st()["make"]["nivel"], "sem", "no banho lavou o rosto; make só às 19:45")
        self.r.tick(datetime(2026, 9, 26, 19, 50))
        st = self.st()
        self.assertIn(st["make"]["nivel"], ("completa", "festa"))
        self.assertIn(tuple(st["atual"]["look"]), LOOKS["casa_dia"], "ainda não chegou no Escolhendo roupa")
        self.r.tick(datetime(2026, 9, 26, 20, 15))
        st = self.st()
        self.assertEqual(st["atual"]["ocasiao"], "sair")
        self.assertIn(tuple(st["atual"]["look"]), LOOKS["sair"])
        self.assertEqual(st["atual"]["desde"][11:16], "20:10", "na hora do passo, não na hora do tick")
        p = self.r.painel(datetime(2026, 9, 26, 20, 20))
        self.assertEqual(p["linhas"][0], ["hanger", "Pra quê", "Sair à noite, desde 20:10"])
        self.assertEqual(p["make"]["palavra"], "Intacta")
        self.assertEqual(p["linhas"][-1][1:], ["Feita", f"{p['linhas'][-1][2].split(',')[0]}, às 19:45"])
        # na rua continua com a mesma roupa
        self.etapa, self.casa = None, False
        self.r.tick(datetime(2026, 9, 26, 21, 0))
        self.assertEqual(self.st()["atual"]["ocasiao"], "sair")
        # 4 h de make: pedindo retoque
        self.assertEqual(self.r.painel(datetime(2026, 9, 27, 1, 0))["make"]["palavra"], "Pedindo retoque")

    def test_chegou_troca_pra_roupa_de_casa_depois(self):
        self.r.tick(T)
        self.etapa = _prep("faculdade", datetime(2026, 9, 26, 12, 0), [("Tomando banho", 20), ("Escolhendo roupa", 15)])
        self.r.tick(datetime(2026, 9, 26, 12, 40))
        self.assertEqual(self.st()["atual"]["ocasiao"], "rua")
        self.etapa, self.casa = None, False
        self.r.tick(datetime(2026, 9, 26, 14, 0))
        self.casa = True
        chegou = datetime(2026, 9, 26, 18, 0)
        self.r.tick(chegou)
        troca = datetime.fromisoformat(self.st()["troca_em"])
        self.assertTrue(chegou + timedelta(minutes=10) <= troca <= chegou + timedelta(minutes=40))
        self.r.tick(troca + timedelta(minutes=1))
        st = self.st()
        self.assertEqual(st["atual"]["ocasiao"], "casa")
        self.assertEqual(st["hist"][-1]["ocasiao"], "rua")
        self.assertEqual(self.r.ocasiao_em(datetime(2026, 9, 26, 16, 0)), "rua", "o Instagram acha a roupa do rolê")

    def test_saiu_sem_o_resolve_ver_o_se_arrumando(self):
        # banho por cima do preparo (ou resolve espaçado): na saída vale o Se arrumando que acabou de acontecer
        self.r.tick(T)
        prep = _prep("noite", datetime(2026, 9, 26, 19, 0),
                     [("Tomando banho", 25), ("Fazendo maquiagem", 25), ("Escolhendo roupa", 20), ("Saindo", 10)])
        self.casa = False
        with patch("agenda.Agenda.etapas", return_value=[prep]):
            self.r.tick(datetime(2026, 9, 26, 20, 30), {"activity": "indo pro Quartinho de uber"})
        st = self.st()
        self.assertEqual((st["atual"]["ocasiao"], st["atual"]["desde"][11:16]), ("sair", "19:50"))
        self.assertIn(st["make"]["nivel"], ("completa", "festa"))

    def test_saiu_de_pijama_sem_se_arrumar_poe_roupa_de_rua(self):
        self.cama = True
        self.r.tick(datetime(2026, 9, 26, 2, 0))
        self.assertEqual(self.st()["atual"]["ocasiao"], "pijama")
        self.cama, self.casa = False, False
        self.r.tick(datetime(2026, 9, 26, 9, 0))
        self.assertEqual(self.st()["atual"]["ocasiao"], "rua")

    def test_dormiu_de_make_acorda_borrada(self):
        st = self.r._state(T)
        self.r._make(st, "completa", datetime(2026, 9, 26, 20, 0))
        self.r._vestir(st, ["vestido_preto"], "sair", datetime(2026, 9, 26, 20, 0), "Sair à noite")
        self.r._save(st)
        self.cama = True
        self.r.tick(datetime(2026, 9, 27, 1, 30))
        st = self.st()
        self.assertEqual(st["atual"]["ocasiao"], "pijama")
        self.assertTrue(st["make"]["dormiu"])
        self.assertEqual(self.r.painel(datetime(2026, 9, 27, 8, 0))["make"]["palavra"], "Borrada")
        self.assertTrue(self.eventos("roupa:dormiu_de_make:%"))
        self.cama = False
        self.r.tick(datetime(2026, 9, 27, 9, 0))           # acordou há 8 h (mock): lavou o rosto
        self.assertEqual(self.st()["make"]["nivel"], "sem")

    def test_banho_tira_a_make_e_depois_veste_roupa_de_casa(self):
        st = self.r._state(T)
        self.r._make(st, "leve", T)
        self.r._vestir(st, ["top_preto", "legging_preta"], "treino", T, "Academia")
        self.r._save(st)
        ini = datetime(2026, 9, 26, 17, 0)
        self.r.banho(ini, ini + timedelta(minutes=15))
        self.assertEqual(self.st()["make"]["nivel"], "sem")
        self.banho = True
        self.r.tick(ini + timedelta(minutes=5))
        self.assertEqual(self.r.painel(ini + timedelta(minutes=5))["look"], "No banho")
        self.banho = False
        self.r.tick(ini + timedelta(minutes=25))
        self.assertEqual(self.st()["atual"]["ocasiao"], "casa")

    def test_provocar_com_tesao_e_a_mesma_peca_nas_fotos(self):
        self.r.tick(T)
        noite = datetime(2026, 9, 26, 22, 10)
        peca = self.r.provocar(noite, "tesao")
        self.assertTrue(peca)
        st = self.st()
        self.assertEqual(st["atual"]["ocasiao"], "provocar")
        self.assertEqual(self.r.painel(noite)["linhas"][0], ["hanger", "Pra quê", "Pra te provocar, desde 22:10"])
        self.assertIn("pra provocar o Patrick", self.eventos("roupa:provocar:%")[0])
        en = self.r.pro_clima(noite + timedelta(minutes=5), 2)
        self.assertEqual(en, self.r.pro_clima(noite + timedelta(minutes=9), 1), "mesma peça a sessão toda")
        self.assertIsNone(self.r.provocar(noite + timedelta(minutes=10), "tesao"), "já está provocando")
        # sem clima há 1 h: volta pra roupa de casa (a não ser que durma com ela)
        with patch("roupa.Roupa._dorme_hoje", return_value=False):
            self.r.tick(noite + timedelta(minutes=75))
        self.assertIn(self.st()["atual"]["ocasiao"], ("casa", "pijama"))

    def test_pedido_dele_nivel_1_depois_2(self):
        self.r.tick(T)
        en1 = self.r.pro_clima(T, 1)
        self.assertIn(en1, [v[1] for v in INTIMO.values() if v[2] == 1])
        en2 = self.r.pro_clima(T + timedelta(minutes=3), 2)
        self.assertIn(self.st()["atual"]["look"][0], [k for k, v in INTIMO.items() if v[2] == 2])
        self.assertNotEqual(en1, en2, "pediu lingerie: troca a peça de provocar pela lingerie")

    def test_por_baixo_aparece_depois_que_ela_conta(self):
        self.r.tick(T)
        self.feeling = SimpleNamespace(valence=0.6, energy=0.6, libido=0.9, episodes=[])
        with patch("roupa.POR_BAIXO_CHANCE_TESAO", 1.0):
            self.etapa = _prep("encontro", datetime(2026, 9, 26, 19, 0),
                               [("Tomando banho", 30), ("Fazendo maquiagem", 25), ("Escolhendo roupa", 20)])
            self.r.tick(datetime(2026, 9, 26, 20, 0))
        pb = self.st()["por_baixo"]
        self.assertTrue(pb and not pb["contou"])
        self.etapa = None
        agora = datetime(2026, 9, 26, 20, 10)
        self.assertNotIn("Por baixo", [l[1] for l in self.r.painel(agora)["linhas"]])
        self.assertIn("Ele não sabe", "\n".join(self.r.prompt_lines(agora)))
        self.r.observe_marina("adivinha o que eu tô usando por baixo desse vestido 😏", agora)
        self.assertIn("Por baixo", [l[1] for l in self.r.painel(agora)["linhas"]])
        # em casa, no clima: tirou o vestido e é a peça de baixo que aparece
        en = self.r.pro_clima(datetime(2026, 9, 26, 23, 50), 2)
        self.assertEqual(self.st()["atual"]["look"][0], pb["peca"])
        self.assertIn(INTIMO[pb["peca"]][1], en)

    def test_ele_escolhe_a_segunda_opcao_de_look(self):
        self.r.tick(T)
        a, b = en_look(["vestido_verde"]), en_look(["corset_rosa", "jeans_escuro"])
        self.db.set_estado_relacional("promessas_foto_json", json.dumps({"promessa": {
            "kind": "looks", "status": "cumprida", "outfits": [a, b], "due_at": "2026-09-26T18:00:00"}}))
        self.assertEqual(self.r.observe_patrick("vai com a segunda", datetime(2026, 9, 26, 18, 10)),
                         ["corset_rosa", "jeans_escuro"])
        self.etapa = _prep("noite", datetime(2026, 9, 26, 19, 0), [("Fazendo maquiagem", 25), ("Escolhendo roupa", 20)])
        self.r.tick(datetime(2026, 9, 26, 19, 40))
        self.assertEqual(self.st()["atual"]["look"], ["corset_rosa", "jeans_escuro"])
        self.assertEqual(nome_look(["corset_rosa", "jeans_escuro"]), "Corset rosê e jeans escuro flare")

    def test_foto_usa_a_roupa_e_a_make_de_agora(self):
        import photo_director
        self.r.tick(T)
        st = self.st()
        self.r._make(st, "completa", T)
        self.r._save(st)
        ctx = SimpleNamespace(place_key=photo_director.HOME, presence_assertable=True, present_people=(),
                              activity="", sublocation="", weather=None, snapshot_id=None)
        shot = photo_director.direct(self.db, T + timedelta(minutes=5), request="manda uma foto", camera_ctx=ctx,
                                     turn=SimpleNamespace(state="off", arousal=0.0))
        self.assertEqual(shot.outfit, en_look(self.st()["atual"]["look"]))
        self.assertIn("full makeup", shot.prompt)
        # sexting pedindo lingerie: veste uma e fica a mesma na próxima foto
        quente = SimpleNamespace(state="active", arousal=0.6, band="desejo")
        s1 = photo_director.direct(self.db, T + timedelta(minutes=30), request="manda de lingerie", camera_ctx=ctx,
                                   turn=quente)
        s2 = photo_director.direct(self.db, T + timedelta(minutes=33), request="manda outra de lingerie", camera_ctx=ctx,
                                   turn=quente)
        self.assertEqual(self.st()["atual"]["ocasiao"], "provocar")
        self.assertEqual(s1.outfit, s2.outfit)
        self.assertTrue(s1.is_nsfw)


if __name__ == "__main__":
    unittest.main()
