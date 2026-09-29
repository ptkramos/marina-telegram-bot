"""Agenda viva (Patrick, 27/09): o que ela sente decide — furar rolê, faltar aula, emendar, chamar a amiga,
e a conversa mexendo em qualquer dia. "Não é chegar e colocar 50% de chance de furar rolês."
"""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from agenda_viva import AgendaViva, Avaliacao, Disposicao
from db import DatabaseManager
from emotion import Episode, Feeling
from seed_world_bible_v36 import seed_world_bible

SAB = datetime(2026, 10, 3, 17, 0)          # sábado


def sentindo(now=SAB, *, energy=0.75, slept=7.5, valence=0.65, battery=0.7, discomfort=0.0, episodes=(),
             hurt=0.0) -> Feeling:
    return Feeling(now=now, energy=energy, hours_slept=slept, awake_since=None, hunger=0.3, discomfort=discomfort,
                   discomfort_why="cólica" if discomfort else "", cycle_phase="folicular", valence=valence,
                   arousal=0.5, playfulness=0.5, episodes=list(episodes), bond={"hurt": hurt}, missing=0.2,
                   social_battery=battery)


def ep(family, kind, i, target=None):
    return Episode(1, family, kind, i, i, "x", target, SAB - timedelta(hours=1), False)


CANSADA = dict(energy=0.35, slept=5.0, battery=0.2, valence=0.45)
ANIMADA = dict(energy=0.85, slept=8.0, battery=0.8, valence=0.75, episodes=(ep("alegria", "empolgacao", 0.5),))


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "v.db")
        seed_world_bible(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), "
                         "('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.commit()
        for alvo, kw in (("academia.Academia.plano", {"return_value": None}),
                         ("academia.PasseioMilo.plano", {"return_value": None}),
                         ("meals.Meals.day_plan", {"return_value": []}),
                         ("sleep_plan.SleepPlan.is_asleep", {"return_value": False}),
                         ("academic_life.AcademicLife.blocks_on", {"return_value": []})):
            p = patch(alvo, **kw)
            p.start()
            self.addCleanup(p.stop)

    def sente(self, **kw):
        p = patch.object(Disposicao, "_feeling", return_value=sentindo(**kw))
        p.start()
        self.addCleanup(p.stop)

    def role(self, ini=SAB + timedelta(hours=2, minutes=30), friends=("bia_andrade",), key="outing:2026-10-03:c1",
             place="quartinho_bar"):
        from calendar_world import CalendarWorld
        return CalendarWorld(self.db).create_commitment(
            source_key=key, event_type="social", description="Saindo com a Bia no Quartinho Bar", start_at=ini,
            end_at=ini + timedelta(hours=3), location_key=place, metadata={"friends": list(friends), "origin": "convite"})

    def status(self, cid):
        with self.db.get_connection() as conn:
            return conn.execute("SELECT status FROM eventos_pendentes WHERE id=?", (cid,)).fetchone()[0]

    def eventos(self, like="agenda:%"):
        with self.db.get_connection() as conn:
            return [r[0] for r in conn.execute("SELECT summary FROM life_events WHERE event_key LIKE ?", (like,))]


class DisposicaoTest(Base):
    def test_cansada_e_sem_bateria_quer_menos_e_diz_por_que(self):
        d = Disposicao(self.db)
        ruim = d.avaliar("role", SAB, com=("bia_andrade",), feeling=sentindo(**CANSADA))
        bom = d.avaliar("role", SAB, com=("bia_andrade",), feeling=sentindo(**ANIMADA))
        self.assertLess(ruim.vontade, 0.4)
        self.assertGreater(bom.vontade, 0.8)
        self.assertIn(ruim.motivo(-1)[1], ("dormiu mal", "sem bateria social", "sem energia"))

    def test_mesmo_estado_mesma_decisao(self):
        d = Disposicao(self.db)
        f = sentindo(**CANSADA)
        self.assertEqual(d.avaliar("role", SAB, feeling=f).vontade, d.avaliar("role", SAB, feeling=f).vontade)

    def test_triste_quer_espairecer_e_desabafar_com_a_bia(self):
        d = Disposicao(self.db)
        f = sentindo(episodes=(ep("tristeza", "decepcao", 0.6),))
        self.assertIn("precisando espairecer", [t for _, t, _ in d.avaliar("acai", SAB, feeling=f).fatores])
        self.assertIn("precisando desabafar com alguém",
                      [t for _, t, _ in d.avaliar("role", SAB, com=("bia_andrade",), feeling=f).fatores])
        self.assertIn("decepcionada", [t for _, t, _ in d.avaliar("academia", SAB, feeling=f).fatores])


class ReconsideraTest(Base):
    def test_cansada_fura_o_role_avisa_a_bia_e_te_conta(self):
        cid = self.role()
        self.sente(**CANSADA)
        res = AgendaViva(self.db).reconsidera(SAB)
        self.assertEqual(self.status(cid), "cancelled")
        self.assertTrue(res["conta"], "cansada e sem pique: quer colo")
        self.assertTrue(any("Desistiu de ir" in s and "Avisou a Bia" in s for s in self.eventos()))
        aviso = AgendaViva(self.db).aviso(SAB + timedelta(minutes=5))
        self.assertIn("Saindo com a Bia", AgendaViva.detalhe_aviso(aviso))

    def test_animada_vai(self):
        cid = self.role()
        self.sente(**ANIMADA)
        self.assertIsNone(AgendaViva(self.db).reconsidera(SAB))
        self.assertEqual(self.status(cid), "pending")

    def test_decide_uma_vez_e_so_na_janela(self):
        cid = self.role(ini=SAB + timedelta(hours=6))
        self.sente(**CANSADA)
        self.assertIsNone(AgendaViva(self.db).reconsidera(SAB), "longe ainda: não decide")
        self.assertEqual(self.status(cid), "pending")

    def test_chuva_sozinha_nao_vira_mensagem(self):
        cid = self.role(friends=())
        self.sente(energy=0.55, battery=0.45, valence=0.5)
        with patch.object(Disposicao, "_chuva", return_value=True):
            res = AgendaViva(self.db).reconsidera(SAB)
        if res:
            self.assertEqual(self.status(cid), "cancelled")
            self.assertEqual(res["chave_motivo"] in ("chuva",), not res["conta"])

    def test_chateada_com_ele_nao_conta(self):
        self.role()
        self.sente(**CANSADA, hurt=0.4)
        res = AgendaViva(self.db).reconsidera(SAB)
        self.assertFalse(res["conta"])


class AulaTest(Base):
    def blocos(self, dia):
        return [{"id": 1, "display_name": "Moda e Corpo", "start_at": f"{dia}T09:00:00", "end_at": f"{dia}T11:00:00",
                 "location_key": "puc_rio"},
                {"id": 2, "display_name": "Desenho", "start_at": f"{dia}T14:00:00", "end_at": f"{dia}T16:00:00",
                 "location_key": "puc_rio"}]

    def test_preguica_falta_so_a_manha_uma_vez_por_semana_e_corre_atras(self):
        seg = datetime(2026, 9, 28, 7, 0)
        self.sente(energy=0.4, slept=6.5, valence=0.45, battery=0.3,
                   episodes=(ep("tristeza", "desanimo", 0.4),))
        canceladas = []
        with patch("academic_life.AcademicLife.blocks_on", side_effect=lambda d: self.blocos(d.isoformat())), \
                patch("academic_life.AcademicLife.cancel_class_occurrence",
                      side_effect=lambda bid, d, source_key: canceladas.append((d, bid))):
            viva = AgendaViva(self.db)
            res = viva.reconsidera(seg)
            self.assertIsNotNone(res)
            self.assertEqual(canceladas, [(seg.date(), 1)], "preguiça: só a da manhã")
            res2 = viva.reconsidera(seg + timedelta(days=1))
            self.assertIsNone(res2, "já faltou essa semana")
        self.assertTrue(any("Faltou a aula" in s for s in self.eventos()))
        AgendaViva(self.db)._recupera_materia(datetime(2026, 9, 28, 21, 0))
        self.assertTrue(any("Pegou a matéria" in s for s in self.eventos("agenda:recuperou:%")))

    def test_doente_falta_o_dia(self):
        seg = datetime(2026, 9, 28, 7, 0)
        self.sente(discomfort=0.7, energy=0.4)
        canceladas = []
        with patch("academic_life.AcademicLife.blocks_on", side_effect=lambda d: self.blocos(d.isoformat())), \
                patch("academic_life.AcademicLife.cancel_class_occurrence",
                      side_effect=lambda bid, d, source_key: canceladas.append(bid)):
            AgendaViva(self.db).reconsidera(seg)
        self.assertEqual(canceladas, [1, 2])


class EmendaTest(Base):
    def test_role_logo_depois_da_aula_vai_direto(self):
        from commute import Commute, Leg
        dia = datetime(2026, 9, 28)
        volta = Leg("commute:2026-09-28:puc:volta", dia.replace(hour=18, minute=40), dia.replace(hour=19, minute=25),
                    "onibus", "volta", "da PUC", "Gávea")
        ida = Leg("commute:outing:2026-09-28:c0:ida", dia.replace(hour=18, minute=40), dia.replace(hour=19, minute=0),
                  "uber", "ida", "pro Quartinho Bar", "Botafogo")
        legs = Commute._emendas([volta, ida])
        self.assertEqual(len(legs), 1)
        self.assertEqual(legs[0].activity(dia.replace(hour=18, minute=50)), "indo da PUC pro Quartinho Bar de uber")
        self.assertEqual((legs[0].start, legs[0].end), (dia.replace(hour=18, minute=40), dia.replace(hour=19)))

    def test_com_tempo_em_casa_nao_emenda(self):
        from commute import Commute, Leg
        dia = datetime(2026, 9, 28)
        volta = Leg("v", dia.replace(hour=16), dia.replace(hour=16, minute=12), "a_pe", "volta", "da Bodytech", "Botafogo")
        ida = Leg("i", dia.replace(hour=19), dia.replace(hour=19, minute=20), "uber", "ida", "pro bar", "Botafogo")
        self.assertEqual(len(Commute._emendas([volta, ida])), 2)

    def test_animada_saindo_da_academia_passa_no_acai(self):
        now = datetime(2026, 9, 28, 15, 50)
        plano = {"inicio": datetime(2026, 9, 28, 14, 50), "fim": datetime(2026, 9, 28, 16, 0), "onde": "rua"}
        self.sente(energy=0.8, valence=0.8, episodes=(ep("alegria", "empolgacao", 0.7), ep("tedio", "tedio", 0.3)))
        with patch("academia.Academia.plano", return_value=plano):
            cid = AgendaViva(self.db).emenda(now)
            self.assertIsNotNone(cid)
            from commute import Commute
            legs = [l for l in Commute(self.db).legs_on(now.date()) if "vontade" in l.key]
        self.assertTrue(any(l.origem == "da Bodytech" for l in legs), [(l.key, l.origem) for l in legs])
        self.assertTrue(any("antes de voltar" in s for s in self.eventos("vontade:%")))

    def test_desanimada_vai_direto_pra_casa(self):
        now = datetime(2026, 9, 28, 15, 50)
        plano = {"inicio": datetime(2026, 9, 28, 14, 50), "fim": datetime(2026, 9, 28, 16, 0), "onde": "rua"}
        self.sente(**CANSADA)
        with patch("academia.Academia.plano", return_value=plano):
            self.assertIsNone(AgendaViva(self.db).emenda(now))


class PlanejaTest(Base):
    def test_com_pique_chama_uma_amiga_pro_fim_de_semana(self):
        qui = datetime(2026, 10, 1, 21, 0)
        self.sente(**ANIMADA)
        AgendaViva(self.db).planeja(qui)
        ev = self.eventos("agenda:chamou:%")
        self.assertEqual(len(ev), 1)
        self.assertTrue(ev[0].startswith("Chamou "))
        self.assertIsNone(AgendaViva(self.db).planeja(qui + timedelta(minutes=30)), "pensa nisso uma vez por noite")
        self.assertTrue(AgendaViva(self.db).prompt_lines(qui + timedelta(minutes=5)))

    def test_sem_pique_nao_chama(self):
        self.sente(**CANSADA)
        AgendaViva(self.db).planeja(datetime(2026, 10, 1, 21, 0))
        self.assertEqual(self.eventos("agenda:chamou:%"), [])


class ConversaTest(Base):
    def test_quando_entende_outros_dias(self):
        from agenda_reativa import AgendaReativa
        now = datetime(2026, 9, 30, 10, 0)             # quarta
        self.assertEqual(AgendaReativa._quando("amanhã 07:00", now), datetime(2026, 10, 1, 7, 0))
        self.assertEqual(AgendaReativa._quando("sábado 21:00", now), datetime(2026, 10, 3, 21, 0))
        self.assertEqual(AgendaReativa._quando("2026-10-02 18:30", now), datetime(2026, 10, 2, 18, 30))
        self.assertEqual(AgendaReativa._quando("18:00", now), datetime(2026, 9, 30, 18, 0))

    def test_desmarcar_role_de_outro_dia_pela_conversa(self):
        from agenda_reativa import AgendaReativa
        now = datetime(2026, 10, 1, 20, 0)
        cid = self.role()
        r = AgendaReativa(self.db)
        r._lista = AgendaViva(self.db).lista_para_conversa(now)
        self.assertEqual(r._lista[0]["tipo"], "role")
        res = r._aplica({"acao": "desistiu", "item": 1, "motivo": "vai ficar com o Patrick"}, now)
        self.assertIsNotNone(res)
        self.assertEqual(self.status(cid), "cancelled")
        self.assertIsNone(AgendaViva(self.db).aviso(now), "ele está na conversa: já sabe")

    def test_remarcar_pela_conversa(self):
        from agenda_reativa import AgendaReativa
        now = datetime(2026, 10, 1, 20, 0)
        cid = self.role()
        r = AgendaReativa(self.db)
        r._lista = AgendaViva(self.db).lista_para_conversa(now)
        r._aplica({"acao": "remarcou", "item": 1, "quando": "domingo 18:00"}, now)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT event_at FROM eventos_pendentes WHERE id=?", (cid,)).fetchone()[0],
                             "2026-10-04T18:00:00")

    def test_amanha_vou_na_academia_vira_plano_de_amanha(self):
        from agenda_reativa import AgendaReativa
        from academia import Academia
        now = datetime(2026, 9, 30, 22, 0)
        AgendaReativa(self.db)._aplica({"acao": "vai_fazer", "tipo": "academia", "quando": "amanhã 07:00",
                                        "motivo": "o Patrick convenceu"}, now)
        st = Academia(self.db)._load()
        self.assertEqual(st["2026-10-01"]["inicio"], "2026-10-01T07:00:00")
        self.assertTrue(any("Combinou com o Patrick" in s for s in self.eventos("agenda:marcou:%")))

    def test_aceitar_convite_pela_conversa(self):
        from social_day import INVITES_KEY
        now = datetime(2026, 10, 2, 12, 0)
        inv = {"key": "outing:2026-10-03:c1", "friends": ["bia_andrade"], "who": "a Bia",
               "text": "Saindo com a Bia no Quartinho Bar", "place": "quartinho_bar",
               "start": "2026-10-03T21:00:00", "end": "2026-10-03T23:59:00", "invite_at": "2026-10-02T10:00:00",
               "decide_at": "2026-10-03T17:00:00", "status": "pending"}
        self.db.set_estado_relacional(INVITES_KEY, json.dumps({inv["key"]: inv}))
        viva = AgendaViva(self.db)
        item = next(i for i in viva.lista_para_conversa(now) if i["tipo"] == "convite")
        viva.pela_conversa(item, "vai_fazer", now, "", now)
        with self.db.get_connection() as conn:
            self.assertIsNotNone(conn.execute("SELECT 1 FROM eventos_pendentes WHERE source_key=?",
                                              (inv["key"],)).fetchone())


class ConviteTest(Base):
    def test_convite_decidido_pelo_que_ela_sente(self):
        from social_day import SocialDay
        inv = {"key": "outing:2026-10-03:c1", "friends": ["bia_andrade"], "start": "2026-10-03T21:00:00"}
        self.sente(**CANSADA)
        vai, porque = SocialDay(self.db)._willing(inv, SAB)
        self.assertFalse(vai)
        self.assertTrue(porque)
        with patch.object(Disposicao, "_feeling", return_value=sentindo(**ANIMADA)):
            self.assertTrue(SocialDay(self.db)._willing(inv, SAB)[0])


class HojeTest(unittest.TestCase):
    def test_linhas_da_agenda(self):
        from hoje import curto
        def c(s):
            return curto({"event_type": "agenda", "title": "agenda", "summary": s})
        self.assertEqual(c("Desistiu de ir: Saindo com a Bia no Quartinho Bar (dormiu mal e sem bateria social). "
                           "Avisou a Bia e combinaram outro dia."),
                         {**c("x"), "ic": "calendar-x", "texto": "Desistiu de ir pro Quartinho Bar",
                          "sub": "Dormiu mal e sem bateria social, avisou a Bia"})
        self.assertEqual(c("Faltou a aula de hoje (Moda e Corpo): dormiu mal. Vai pegar a matéria com a Júlia depois.")
                         ["sub"], "Moda e Corpo, dormiu mal")
        self.assertEqual(c("Chamou a Bia pra sair sábado às 21:00 (Saindo com a Bia no Quartinho Bar); Bia topou.")
                         ["sub"], "Sábado 21:00, topou")
        self.assertEqual(c("Desistiu de treinar hoje (sem energia).")["texto"], "Desistiu de treinar")


if __name__ == "__main__":
    unittest.main()
