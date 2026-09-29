"""Auditoria de funcionamento, rodada 3 (noite de 28/09, produção). Casos reais:

A. Milo 21:30–21:38 no meio do jantar (21:07–21:41): o acontecimento saía na hora sorteada e o mundo ficava em
   "jantando". Agora o xixi da noite espera ela terminar e desce em seguida.
B. "Trabalhou no trabalho de Práticas Experimentais VI" às 19:59, com ela treinando na Bodytech (18:50–20:09); a
   sessão só começou às 20:29, em casa. Agora começa quando ela está livre em casa.
C. Sem banho depois do treino: chegou 20:21, o estudo (20:29) e o jantar (21:07) pegaram a vez e o banho só veio às
   21:52. Patrick: "banho logo ao chegar" — saindo do treino, o banho fica marcado pra chegada.
D. "Vou deitar agora" às 21:45 (deitar 21:51) e banho 21:52–22:17. Patrick: "banho antes do boa noite".
"""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import rituals
from college import College
from commute import Leg
from db import DatabaseManager
from meals import Meals
from milo import Milo
from rituals import Rituals
from seed_academic_v36 import seed_academic
from seed_world_bible_v36 import seed_world_bible


class _Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "aud3.db")
        seed_world_bible(self.db)
        seed_academic(self.db)
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES "
                         "('clean_canonical_start_done','1','2026-09-01'), "
                         "('social_day_start','2026-09-01T00:00:00','2026-09-01')")
            conn.commit()

    def _estado(self, t: datetime, activity: str, reason: str = "free_time"):
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO world_state (state_date, observed_at, activity, source_json) VALUES (?,?,?,?)",
                         (t.date().isoformat(), t.isoformat(), activity, json.dumps({"reason": reason})))
            conn.commit()

    def _transicao(self, activity: str, ini: datetime, fim: datetime, tipo: str = "meal"):
        self.db.set_estado_relacional("pending_transition_json", json.dumps({
            "routine_type": tipo, "activity": activity, "place_key": "marina_apartment",
            "transition_at": ini.isoformat(), "end_at": fim.isoformat()}))

    def _pendente(self) -> dict:
        return json.loads(self.db.get_estado_relacional().get("pending_transition_json") or "{}")

    def _evento(self, key: str):
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT event_at FROM life_events WHERE event_key=?", (key,)).fetchone()
        return datetime.fromisoformat(row[0]) if row else None


class MiloEsperaOJantarTest(_Base):
    def test_xixi_da_noite_espera_o_jantar_acabar(self):
        milo = Milo(self.db)
        d = date(2026, 9, 28)
        noite = next(p for p in milo.day_plan(d) if p["key"].endswith(":noite"))
        self._estado(noite["at"] - timedelta(minutes=40), "em casa, montando looks (closet)")
        fim_jantar = noite["at"] + timedelta(minutes=11)
        self._transicao("jantando em casa", noite["at"] - timedelta(minutes=23), fim_jantar)
        milo.materialize(noite["at"] + timedelta(minutes=1))
        self.assertIsNone(self._evento(noite["key"]), "comendo: o Milo espera")
        self.assertEqual(self._pendente()["activity"], "jantando em casa")
        depois = fim_jantar + timedelta(minutes=2)
        milo.materialize(depois)
        self.assertEqual(self._evento(noite["key"]), depois, "desce quando ela termina, não na hora sorteada")
        pend = self._pendente()
        self.assertIn("Milo", pend["activity"])
        self.assertEqual(datetime.fromisoformat(pend["transition_at"]), depois)
        self.assertEqual(datetime.fromisoformat(pend["end_at"]) - depois, timedelta(minutes=noite["minutes"]))

    def test_sem_nada_no_caminho_desce_na_hora_sorteada(self):
        milo = Milo(self.db)
        d = date(2026, 9, 28)
        noite = next(p for p in milo.day_plan(d) if p["key"].endswith(":noite"))
        self._estado(noite["at"] - timedelta(minutes=40), "em casa, montando looks (closet)")
        milo.materialize(noite["at"] + timedelta(minutes=2))
        self.assertEqual(self._evento(noite["key"]), noite["at"])
        self.assertEqual(datetime.fromisoformat(self._pendente()["transition_at"]), noite["at"])


class SessaoDeEstudoTest(_Base):
    def setUp(self):
        super().setUp()
        self.college = College(self.db)
        dias = [date(2026, 9, 21) + timedelta(days=i) for i in range(42)]
        self.s = next((s for s in map(self.college.session_on, dias) if s), None)
        if self.s is None:
            self.skipTest("grade semeada sem noite de trabalho")
        self.key = f"facul:sessao:{self.s['start'].date().isoformat()}"

    def test_na_academia_na_hora_planejada_comeca_quando_chega(self):
        ini = self.s["start"]
        self._estado(ini - timedelta(minutes=70), "treinando na academia", "gym")
        self.college.materialize(ini + timedelta(minutes=5))
        self.assertIsNone(self._evento(self.key), "na academia não senta pra trabalhar")
        self._estado(ini + timedelta(minutes=25), "em casa, montando looks (closet)")
        chegou = ini + timedelta(minutes=30)
        self.college.materialize(chegou)
        self.assertEqual(self._evento(self.key), chegou, "o Hoje não põe o trabalho dentro do treino")
        pend = self._pendente()
        self.assertEqual(datetime.fromisoformat(pend["transition_at"]), chegou)
        self.assertEqual(datetime.fromisoformat(pend["end_at"]), self.s["end"])

    def test_comendo_ou_no_banho_espera(self):
        ini = self.s["start"]
        self._estado(ini - timedelta(minutes=30), "em casa, montando looks (closet)")
        self._transicao("tomando banho", ini - timedelta(minutes=5), ini + timedelta(minutes=15), "shower")
        self.college.materialize(ini + timedelta(minutes=5))
        self.assertIsNone(self._evento(self.key))
        self.college.materialize(ini + timedelta(minutes=20))
        self.assertEqual(self._evento(self.key), ini + timedelta(minutes=20))

    def test_em_casa_na_hora_fica_na_hora_planejada(self):
        ini = self.s["start"]
        self._estado(ini - timedelta(minutes=30), "em casa, montando looks (closet)")
        self.college.materialize(ini + timedelta(minutes=4))
        self.assertEqual(self._evento(self.key), ini)

    def test_sem_tempo_sobrando_nao_senta(self):
        ini, fim = self.s["start"], self.s["end"]
        self._estado(ini - timedelta(minutes=70), "treinando na academia", "gym")
        self._estado(fim - timedelta(minutes=12), "em casa, montando looks (closet)")
        self.college.materialize(fim - timedelta(minutes=10))
        self.assertIsNone(self._evento(self.key))


class _RituaisBase(_Base):
    def setUp(self):
        super().setUp()
        self.r = Rituals(self.db)
        self.dia = next(date(2026, 9, 21) + timedelta(days=i) for i in range(14)
                        if self.r._has_class(date(2026, 9, 21) + timedelta(days=i)))
        for p in (patch.dict(rituals.DAILY_CHANCE, {"bom_dia": 1.0, "boa_noite": 1.0}),
                  patch.object(rituals, "COTIDIANO_CHANCE", 0.0)):
            p.start()
            self.addCleanup(p.stop)

    def _at(self, h, m=0):
        return datetime.combine(self.dia, datetime.min.time()).replace(hour=h, minute=m)

    def _tick(self, now, state=("HOME_RELAXING", "em casa, montando looks")):
        with patch.object(Rituals, "_state", return_value=state):
            return self.r.tick(now)


class BanhoPosTreinoTest(_RituaisBase):
    def _volta(self, direcao="volta"):
        return Leg(key="gym:volta", start=self._at(20, 9), end=self._at(20, 21), mode="a_pe", direction=direcao,
                   destination="casa" if direcao == "volta" else "Starbucks", region="Botafogo")

    def test_saindo_do_treino_o_banho_fica_marcado_pra_chegada(self):
        self._tick(self._at(20, 4), ("GYM", "treinando na academia"))
        with patch("commute.Commute.leg_at", return_value=self._volta()):
            self._tick(self._at(20, 9), ("COMMUTE", "voltando da Bodytech pra casa a pé"))
        pend = self._pendente()
        self.assertEqual(pend["activity"], "tomando banho")
        self.assertEqual(datetime.fromisoformat(pend["transition_at"]), self._at(20, 23), "logo que chega")
        self.assertFalse(pend["told_patrick"])
        meals = Meals(self.db)
        self.assertTrue(meals._transition_busy(self._at(20, 29)), "estudo, jantar e Milo esperam o banho")
        self.assertFalse(self.r.in_shower(self._at(20, 15)), "no caminho ainda não está no banho")

    def test_da_academia_pra_outro_lugar_banho_quando_voltar(self):
        self._tick(self._at(20, 4), ("GYM", "treinando na academia"))
        with patch("commute.Commute.leg_at", return_value=self._volta("ida")):
            self._tick(self._at(20, 9), ("COMMUTE", "indo pro Starbucks a pé"))
        self.assertFalse(self._pendente())
        self.assertIsNotNone(self.r._get(f"ritual:{self.dia.isoformat()}:banho_at"))

    def test_banho_da_noite_nao_repete_o_do_treino(self):
        self._tick(self._at(19, 0), ("GYM", "treinando na academia"))
        self._tick(self._at(19, 5), ("HOME_RELAXING", "em casa"))
        self.assertEqual(self._pendente()["activity"], "tomando banho")
        for minuto in range(30, 180, 5):
            self._tick(self._at(19, 5) + timedelta(minutes=minuto))
        with self.db.get_connection() as conn:
            banhos = conn.execute("SELECT COUNT(*) FROM life_events WHERE event_key LIKE 'banho:%'").fetchone()[0]
        self.assertLessEqual(banhos, 1 if self._at(21, 30) - self._at(19, 7) < rituals.SHOWER_MIN_GAP else 2)


class BanhoAntesDoBoaNoiteTest(_RituaisBase):
    def test_banho_da_noite_acaba_antes_do_boa_noite(self):
        for i in range(21):
            d = date(2026, 9, 21) + timedelta(days=i)
            bed = self.r.bed_at(d)
            t = datetime.combine(d, datetime.min.time()).replace(hour=19, minute=30)
            while t < bed and self.r._shower_due(t, d) != "banho_noite":
                t += timedelta(minutes=1)
            with self.subTest(dia=d):
                self.assertLessEqual(t, bed - rituals.SHOWER_EVENING_BEFORE_BED)

    def test_sem_banho_na_hora_do_boa_noite_toma_primeiro(self):
        bed = self.r.bed_at(self.dia)
        self.assertIsNone(self._tick(bed - timedelta(minutes=4)), "não diz 'vou deitar' antes do banho")
        pend = self._pendente()
        self.assertEqual(pend["activity"], "tomando banho")
        fim = datetime.fromisoformat(pend["end_at"])
        novo = self.r.bed_at(self.dia)
        self.assertEqual(novo, fim + rituals.BOA_NOITE_DEPOIS_DO_BANHO, "deita depois do banho")
        self.assertIsNone(self._tick(fim - timedelta(minutes=1)), "de dentro do chuveiro não")
        enviados = []
        t = fim + timedelta(minutes=1)
        while t < novo:
            ritual = self._tick(t)
            if ritual:
                enviados.append(ritual.kind)
                self.r.mark(ritual, t)
            t += timedelta(minutes=5)
        self.assertEqual(enviados, ["boa_noite"], "boa noite de banho tomado")

    def _boa_noite_ate_deitar(self, desde: datetime) -> list[str]:
        enviados, t = [], desde
        while t < self.r.bed_at(self.dia):
            ritual = self._tick(t)
            if ritual:
                enviados.append(ritual.kind)
                self.r.mark(ritual, t)
            t += timedelta(minutes=5)
        return enviados

    def test_jantando_na_hora_do_boa_noite_espera(self):
        bed = self.r.bed_at(self.dia)
        self.r.start_shower(bed - timedelta(hours=2), 20, told_patrick=False)
        self._transicao("jantando em casa", bed - timedelta(minutes=35), bed - timedelta(minutes=2))
        self.assertEqual(self._boa_noite_ate_deitar(bed - timedelta(minutes=34)), ["boa_noite"])

    def test_milo_na_janela_do_boa_noite_nao_rouba_o_boa_noite(self):
        # réplica de 28/09 com o Milo esperando o jantar: desceu 21:45–21:53 com o deitar às 21:51 e ela dormiu
        # às 21:55 sem boa noite. O deitar vai pra 15 min depois do Milo.
        bed = self.r.bed_at(self.dia)
        self.r.start_shower(bed - timedelta(hours=2), 20, told_patrick=False)
        fim_milo = bed + timedelta(minutes=2)
        self._transicao("passeio rapidinho com o Milo (xixi da noite)", bed - timedelta(minutes=6), fim_milo, "pet_walk")
        self.assertIsNone(self._tick(bed - timedelta(minutes=5)))
        self.assertEqual(self.r.bed_at(self.dia), fim_milo + rituals.BOA_NOITE_DEPOIS_DO_BANHO)
        self.assertEqual(self._boa_noite_ate_deitar(fim_milo + timedelta(minutes=1)), ["boa_noite"])


class BlocoEmCasaDepoisDoMiloTest(_Base):
    def test_bloco_nao_comeca_antes_do_milo_voltar(self):
        from tempo_livre import TempoLivre
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO life_events(event_key,event_at,end_at,event_type,title,summary,source_type,
                            autonomy_level,created_at) VALUES ('milo:2026-09-28:noite','2026-09-28T21:45:00',
                            '2026-09-28T21:53:00','routine','Milo','Levou o Milo pro xixi da noite, rapidinho.',
                            'simulated',1,'2026-09-28T21:45:00')""")
            conn.commit()
        self.assertEqual(TempoLivre(self.db)._chegou(datetime(2026, 9, 28, 21, 55)), datetime(2026, 9, 28, 21, 53))
        self.assertEqual(TempoLivre(self.db)._chegou(datetime(2026, 9, 28, 22, 30)), datetime.min, "só o que acabou de acabar")


class AvisoDoBanhoNaChegadaTest(_Base):
    def test_ele_escreve_no_caminho_de_casa(self):
        import bot
        agora = datetime(2026, 9, 28, 20, 12)
        pend = {"routine_type": "shower", "activity": "tomando banho", "told_patrick": False,
                "transition_at": datetime(2026, 9, 28, 20, 23).isoformat(),
                "end_at": datetime(2026, 9, 28, 20, 45).isoformat()}
        with patch.object(bot.memory_manager, "db", self.db):
            texto = bot._quiet_transition_hint(pend, agora)
        self.assertIn("Assim que chegar em casa", texto)
        self.assertIn("20:23", texto)
        self.assertNotIn("agora mesmo", texto)


if __name__ == "__main__":
    unittest.main()
