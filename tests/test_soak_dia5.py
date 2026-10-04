"""Soak, dia 5 (sábado 03/10) — relatório lido em 04/10. Os casos reais do dia:
G1 19:49 "a Lívia deu notícias do casting?" → "Ainda não" (o resultado tinha chegado às 10:48).
G2 09:29 "tenho um compromisso de manhã" (o prompt dizia só "compromisso hoje às 10:58": era o mercado).
G3 12:04 "Tô indo pra casa a pé, te aviso quando chegar" no aviso de saída — e não avisou.
G4 19:11 "te mando uma foto quando fechar o look" — a selfie de camiseta das 19:15 "cumpriu" a promessa.
G5 /feedback 17:44: academia do prédio com o card "Em casa" e a roupa de casa.
G6 /feedback 19:52: a série começou 19:37 por cima do Se arrumando das 19:41 (card no banho, mundo no sofá).
G7 "Comprou vestidos" e "lingerie transparente" no Zona Sul.
G8 brunch 12:40 e almoço 13:44.
M1 08:57 "lembrei do seu plantão de segunda" (assunto de 28/09) e antes do bom dia.
M2 15:08 "deixa eu ver você com ela" (o conjunto de renda) virou foto pelada.
M3 19:11 "Um vestido preto, bem básico" e o mundo vestiu outro.
"""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agenda import Etapa, Passo
from db import DatabaseManager
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible


def at(h, m=0, s=0, d=3):
    return datetime(2026, 10, d, h, m, s)


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "d5.db")
        seed_world_bible(self.db)
        seed_academic(self.db)

    def _evento(self, key, quando, summary, tipo="work"):
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                            autonomy_level,importance,share_worthy,created_at)
                            VALUES (?,?,?,?,?,'simulated',1,0.5,0.6,?)""",
                         (key, quando.isoformat(), tipo, "freela de modelo", summary, quando.isoformat()))
            conn.commit()

    def _mundo(self, quando, activity):
        with self.db.get_connection() as conn:
            casa = conn.execute("SELECT id FROM world_places WHERE canonical_key='marina_apartment'").fetchone()["id"]
            conn.execute("INSERT INTO world_state(state_date, observed_at, location_place_id, activity, source_json) "
                         "VALUES (?,?,?,?,?)", (quando.date().isoformat(), quando.isoformat(), casa, activity, "{}"))
            conn.commit()
            return casa


def _quartinho():
    passos = [Passo("Tomando banho", at(19, 41)), Passo("Secando cabelo", at(19, 57)),
              Passo("Fazendo maquiagem", at(20, 11)), Passo("Escolhendo roupa", at(20, 27)),
              Passo("Trocou de look", at(20, 48), aviso=True), Passo("Saindo", at(20, 53))]
    return Etapa("arrumando", "Se arrumando", at(19, 41), at(20, 58), linha2="Vai sair para o Quartinho Bar",
                 passos=passos, chave="prep:outing:2026-10-03:m2004", prep_tipo="noite")


class CastingJaSabeTest(_Base):
    """G1: depois do resultado, o bloco do trabalho diz o que a Lívia avisou."""

    def test_resultado_de_hoje_vai_no_prompt(self):
        from freela import Freela
        self._evento("freela:2026-09-28:resultado", at(10, 48),
                     "A Lívia avisou: não passou no casting (vídeo pra uma marca de cosméticos). Escolheram outra menina.")
        linhas = "\n".join(Freela(self.db).prompt_lines(at(19, 49)))
        self.assertIn("Você já sabe (hoje às 10:48): A Lívia avisou: não passou no casting", linhas)

    def test_resultado_velho_sai(self):
        from freela import Freela
        self._evento("freela:2026-09-28:resultado", at(10, 48), "A Lívia avisou: não passou no casting (x).")
        self.assertNotIn("Você já sabe", "\n".join(Freela(self.db).prompt_lines(at(11, 0, d=6))))


class ProximoCompromissoTest(_Base):
    """G2: o próximo compromisso diz o que é."""

    def test_mercado_tem_nome(self):
        from calendar_world import CalendarWorld
        cw = CalendarWorld(self.db)
        cw.create_commitment(source_key="mercado:2026-10-03", event_type="lazer",
                             description="Fazendo as compras da semana no Zona Sul", start_at=at(10, 58),
                             end_at=at(12, 0))
        self.assertEqual(cw.next(at(9, 29), include_academic=False)["activity"],
                         "Fazendo as compras da semana no Zona Sul")


class AvisoNaIniciativaTest(_Base):
    """G3: a promessa de avisar a chegada vale também quando está dentro do aviso de saída."""

    def setUp(self):
        super().setUp()
        volta = SimpleNamespace(key="commute:2026-10-03:mercado:volta", start=at(12, 0), end=at(12, 6),
                                direction="volta", destination="pra casa", how="a pé")
        p = patch("arrival_promise._legs", return_value=[volta])
        p.start()
        self.addCleanup(p.stop)

    def test_indo_pra_casa_te_aviso_quando_chegar(self):
        import arrival_promise
        p = arrival_promise.observe(self.db, "Amor, saí do Zona Sul agora\nTô indo pra casa a pé, te aviso quando "
                                             "chegar 🖤", "", at(12, 4, 28))
        self.assertEqual((p["kind"], p["where"]), ("chegada", "em casa"))
        self.assertIsNotNone(arrival_promise.due(self.db, at(12, 12)))

    def test_quando_estiver_indo_pra_casa_continua_saida(self):
        import arrival_promise
        for fala in ("te aviso quando estiver indo pra casa", "Quando eu estiver indo pra casa te aviso"):
            self.db.set_estado_relacional(arrival_promise.KEY, "")
            self.assertEqual(arrival_promise.observe(self.db, fala, "", at(11, 18))["kind"], "saida", fala)


class PromessaDoLookTest(_Base):
    """G4: "quando fechar o look" vence quando ela termina de se vestir, e só foto de look cumpre."""

    def setUp(self):
        super().setUp()
        p = patch("agenda.Agenda.etapas", return_value=[_quartinho()])
        p.start()
        self.addCleanup(p.stop)

    def test_vence_no_fim_da_roupa(self):
        import promessa_foto
        p = promessa_foto.observe_marina_line(self.db, "Agora você aprovou, né? kkkk Vou me arrumar mais tarde e te "
                                                       "mando uma foto quando fechar o look", "", at(19, 11, 41))
        self.assertEqual((p["kind"], p["due_at"][11:16]), ("looks", "20:53"))

    def test_selfie_de_camiseta_nao_cumpre(self):
        import promessa_foto
        promessa_foto.observe_marina_line(self.db, "te mando uma foto quando fechar o look", "", at(19, 11))
        promessa_foto.cumpre_com(self.db, "unhas_selfie")
        self.assertIsNotNone(promessa_foto.pending(self.db))
        promessa_foto.cumpre_com(self.db, "closet_look_frente")
        self.assertIsNone(promessa_foto.pending(self.db))

    def test_outra_promessa_cumpre_com_qualquer_foto(self):
        import promessa_foto
        promessa_foto.observe_marina_line(self.db, "jaja te mando uma foto", "", at(16, 0))
        promessa_foto.cumpre_com(self.db, "unhas_selfie")
        self.assertIsNone(promessa_foto.pending(self.db))


class AcademiaDoPredioTest(_Base):
    """G5: o card e a roupa do treino no prédio."""

    def test_card(self):
        from agenda import Agenda
        self._mundo(at(17, 44), "treinando na academia do prédio")
        card = Agenda(self.db).card_casa(at(17, 44), "No bolso")
        self.assertEqual((card["titulo"], card["linha2"]), ("Na academia", "Treinando"))
        self.assertIn(["map-pin", "Onde", "Academia do prédio"], card["grade"])
        self.assertNotIn("Cômodo", [g[1] for g in card["grade"]])

    def test_roupa_de_treino_e_troca_na_volta(self):
        from roupa import KEY, Roupa
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) "
                         "VALUES ('clean_canonical_start_done','1','2026-09-01')")
            conn.commit()
        for alvo, kw in (("roupa.Roupa._na_cama", {"return_value": False}),
                         ("roupa.Roupa._no_banho", {"return_value": False}),
                         ("roupa.Roupa._choro", {"return_value": None}),
                         ("agenda.Agenda.etapas", {"return_value": []})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)
        casa = self._mundo(at(16, 0), "em casa, olhando o TikTok (quarto)")
        r = Roupa(self.db)
        r.tick(at(16, 0), {"activity": "em casa, olhando o TikTok (quarto)", "location_place_id": casa})
        r.tick(at(17, 0), {"activity": "treinando na academia do prédio", "location_place_id": casa})
        st = json.loads(self.db.get_estado_relacional(KEY))
        self.assertEqual(st["atual"]["ocasiao"], "treino")
        r.tick(at(18, 6), {"activity": "em casa, olhando o TikTok (quarto)", "location_place_id": casa})
        st = json.loads(self.db.get_estado_relacional(KEY))
        self.assertTrue(st["em_casa"])
        self.assertIsNotNone(st.get("troca_em"), "chegou do treino: troca de roupa em 15–45 min")


class SerieAntesDoPreparoTest(_Base):
    """G6: a série da noite não começa por cima do Se arrumando."""

    def _materialize(self, etapas):
        from watch import Watching
        plano = {"start": at(19, 37), "bed": at(0, 30, d=4), "episodes": 2, "one_piece": False}
        with patch("watch.Watching.night_plan", return_value=plano), \
                patch("meals.Meals._floor", return_value=at(18, 0)), \
                patch("meals.Meals._at_home", return_value=True), \
                patch("meals.Meals._transition_busy", return_value=False), \
                patch("watch.Watching.new_episodes", return_value=0), \
                patch("agenda.Agenda.etapas", return_value=etapas):
            Watching(self.db).materialize(at(19, 37))
        return self.db.get_estado_relacional("pending_transition_json")

    def test_com_preparo_logo_depois_nao_comeca(self):
        self.assertFalse(self._materialize([_quartinho()]))

    def test_sem_preparo_comeca(self):
        self.assertIn("no sofá", self._materialize([]))


class ListaDoMercadoTest(_Base):
    """G7: roupa não entra na lista do mercado."""

    def test_roupa_fica_fora(self):
        from lista_compras import ListaCompras
        lista = ListaCompras(self.db)
        self.assertFalse(lista.adicionar("vestidos", "patrick", at(15, 36, d=2)))
        self.assertFalse(lista.adicionar("lingerie transparente", "patrick", at(15, 36, d=2)))
        self.assertTrue(lista.adicionar("barrinhas de proteína", "patrick", at(15, 36, d=2)))
        self.assertEqual([i["item"] for i in lista.pendentes()], ["barrinhas de proteína"])


class BrunchEAlmocoTest(unittest.TestCase):
    """G8: café que acaba depois do meio-dia é o almoço do dia."""

    def test_brunch_tira_o_almoco_perto(self):
        from meals import Meals, MealSlot
        cafe = MealSlot("cafe", "meal:2026-10-03:cafe", at(12, 40), 50, "casa", "brunch com panqueca e café gelado")
        almoco = MealSlot("almoco", "meal:2026-10-03:almoco", at(13, 44), 30, "casa", "arroz, feijão e frango")
        jantar = MealSlot("jantar", "meal:2026-10-03:jantar", at(18, 46), 25, "casa", "arroz e ovo")
        self.assertEqual([s.kind for s in Meals._brunch_e_almoco([cafe, almoco, jantar])], ["cafe", "jantar"])

    def test_cafe_cedo_mantem_o_almoco(self):
        from meals import Meals, MealSlot
        cafe = MealSlot("cafe", "meal:2026-10-05:cafe", at(9, 30, d=5), 20, "casa", "pão na chapa")
        almoco = MealSlot("almoco", "meal:2026-10-05:almoco", at(12, 30, d=5), 30, "casa", "arroz")
        self.assertEqual(len(Meals._brunch_e_almoco([cafe, almoco])), 2)


class AssuntoVencidoTest(_Base):
    """M1: assunto com data que já passou não vira lembrete."""

    def test_data_vencida(self):
        from db import _data_vencida
        hoje = date(2026, 10, 3)
        self.assertTrue(_data_vencida("Patrick terá um plantão na segunda-feira (28/09).", hoje))
        self.assertFalse(_data_vencida("Patrick terá um plantão na segunda (05/10).", hoje))
        self.assertFalse(_data_vencida("Patrick comeu 1/2 pizza", hoje))
        self.assertFalse(_data_vencida("Patrick tá ansioso com a prova", hoje))

    def test_checkin_pula_o_vencido(self):
        with self.db.get_connection() as conn:
            for txt in ("Patrick terá um plantão na segunda-feira (28/09) e está se preparando.",
                        "Patrick vai contar como foi a consulta."):
                conn.execute("INSERT INTO open_loops (loop_type, content, status, importance, next_check_after, "
                             "created_at, last_touched_at) VALUES ('followup', ?, 'open', 0.5, ?, ?, ?)",
                             (txt, at(8, 0).isoformat(), at(7, 0, d=2).isoformat(), at(7, 0, d=2).isoformat()))
            conn.commit()
        loops = self.db.get_open_loops_para_checkin(now=at(8, 57))
        self.assertEqual([l["content"] for l in loops], ["Patrick vai contar como foi a consulta."])

    def test_bom_dia_pendente(self):
        from rituals import Rituals, PREFIX
        r = Rituals(self.db)
        with patch.object(Rituals, "wake_at", return_value=at(8, 44)):
            self.assertTrue(r.bom_dia_pendente(at(8, 57)))
            self.assertFalse(r.bom_dia_pendente(at(8, 30)))
            r._set(f"{PREFIX}2026-10-03:bom_dia", "sent", at(9, 12))
            self.assertFalse(r.bom_dia_pendente(at(9, 13)))


class VerComAPecaTest(_Base):
    """M2: "deixa eu ver você com ela" com a lingerie de provocar vestida é foto com a peça."""

    def test_regex(self):
        from photo_director import _VER_COM_A_PECA
        self.assertTrue(_VER_COM_A_PECA.search("aaaah marina não brinca comigo não por favorzinho, deixa eu ver você "
                                               "com ela por favor!"))
        self.assertFalse(_VER_COM_A_PECA.search("manda uma foto sua"))

    def test_nivel_dois_com_a_peca(self):
        import photo_director
        from intimacy import IntimacyTurn
        ctx = SimpleNamespace(place_key="marina_apartment", presence_assertable=True, present_people=())
        turno = IntimacyTurn("active", 0.51)
        with patch("photo_director._vestida_pra_ele", return_value=True):
            shot = photo_director.direct(self.db, at(15, 9), request="deixa eu ver você com ela por favor!",
                                         her_line="", camera_ctx=ctx, turn=turno, rng=__import__("random").Random(1))
        self.assertEqual(shot.level, 2)


class LookDitoTest(_Base):
    """M3: o look que ela diz que vai usar vira a escolha dela."""

    def test_vestido_preto(self):
        from roupa import KEY, Roupa
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) "
                         "VALUES ('clean_canonical_start_done','1','2026-09-01')")
            conn.commit()
        with patch("agenda.Agenda.etapas", return_value=[_quartinho()]), \
                patch("roupa.Roupa._na_cama", return_value=False):
            Roupa(self.db).observe_marina("Um vestido preto, bem básico", at(19, 11), "Que look que tu vai sair amor")
        st = json.loads(self.db.get_estado_relacional(KEY))
        self.assertEqual(st["escolha"]["look"], ["vestido_preto"])

    def test_sem_saida_nao_escolhe(self):
        from roupa import KEY, Roupa
        with patch("agenda.Agenda.etapas", return_value=[]):
            Roupa(self.db).observe_marina("Um vestido preto, bem básico", at(19, 11), "Que look que tu vai sair amor")
        st = json.loads(self.db.get_estado_relacional(KEY) or "{}")
        self.assertFalse(st.get("escolha"))


def _relatorio():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "relatorio_soak", Path(__file__).resolve().parents[1] / "scripts" / "relatorio_soak.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RelatorioDia5Test(unittest.TestCase):
    def test_academia_do_predio_e_casa(self):
        situacao = _relatorio().situacao
        self.assertEqual(situacao("treinando na academia do prédio", "Botafogo"), "casa")
        self.assertEqual(situacao("treinando na Bodytech", "Botafogo"), "academia")

    def test_aviso_de_chegada(self):
        RE_AVISO_CHEGADA = _relatorio().RE_AVISO_CHEGADA
        self.assertTrue(RE_AVISO_CHEGADA.search("tô indo pra casa a pé, te aviso quando chegar 🖤"))


if __name__ == "__main__":
    unittest.main()
