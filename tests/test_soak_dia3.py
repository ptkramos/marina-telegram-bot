"""Soak, dia 3 (quinta 01/10) — relatório de 02/10 05:10, o dia dos dois castings.

1. 05:32 "Hoje é dia livre da facul, não tenho aula pra faltar" — ela tinha faltado (agenda viva, `agenda:faltou:`).
2. 11:29 "só sei que a canja chegou mais cedo" — a canja era de 30/09; a promessa "avisar quando a canja chegar"
   ficou aberta.
3. 18:30 Hoje: "Fez o casting na agência" — ela saiu passando mal às 17:30, no meio do 2º casting (17:00–18:30).
4. 08:04 a foto dele ficou sem leitura (JSON mal formado da visão).
5. Hoje: "Foi para a agência" 14:58–17:00 e de novo 17:00–17:53 (castings emendados na mesma agência).
6. 05:22 bom dia e 05:24 "Acordei agora e vi isso" — a resposta da madrugada saiu depois do bom dia.
7. Relatório: «tomei um Buscopan» (o remédio da cólica moderada é do mundo) e «jantei» (a tigela das 19:08).
"""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from college import College
from db import DatabaseManager

DIA = datetime(2026, 10, 1)


def at(h, m):
    return DIA.replace(hour=h, minute=m)


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "d.db")

    def _evento(self, key, at_, summary, tipo="agenda"):
        with self.db.get_connection() as conn:
            conn.execute("""INSERT INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                            autonomy_level,importance,participants_json,share_worthy,created_at)
                            VALUES (?,?,?,?,?,'simulated',1,0.3,'[]',0.5,?)""",
                         (key, at_.isoformat(), tipo, tipo, summary, at_.isoformat()))
            conn.commit()

    def _summary(self, key):
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT summary FROM life_events WHERE event_key=?", (key,)).fetchone()
        return row["summary"] if row else None


class FaltaDaAgendaVivaTest(Base):
    def test_falta_da_agenda_viva_conta(self):
        self.assertIsNone(College(self.db).falta(DIA.date()))
        texto = ("Faltou a aula de hoje (Práticas Experimentais VI, Linguagem e Estruturas): cólica moderada e "
                 "desanimada. Vai pegar a matéria com a Júlia depois.")
        self._evento("agenda:faltou:2026-10-01", at(5, 2), texto)
        self.assertEqual(College(self.db).falta(DIA.date()), texto)
        self.assertIsNone(College(self.db).falta(datetime(2026, 10, 2).date()))


class PromessaDoPedidoFechaTest(Base):
    def test_canja_chegou_fecha_a_promessa(self):
        from delivery import fecha_promessas_do_pedido
        canja = self.db.adicionar_open_loop("promise", "Avisar o Patrick quando a canja chegar para ele pedir o suco")
        outra = self.db.adicionar_open_loop("promise", "Contar pro Patrick quando a Bia chegar de viagem")
        self.assertEqual(fecha_promessas_do_pedido(self.db, "Canja de galinha 500 ml"), 1)
        self.assertEqual(self.db.get_open_loop(canja)["status"], "resolved")
        self.assertEqual(self.db.get_open_loop(outra)["status"], "open")


class CastingInterrompidoTest(Base):
    """2º casting 17:00–18:30; às 17:30 "Saiu mais cedo na agência: não tava se sentindo bem"."""

    def _estado(self, interrompeu: bool):
        from agenda_reativa import KEY
        inter = {"freela:2026-10-01:casting:2026-09-29": {
            "at": at(17, 30).isoformat(), "sai": at(17, 35).isoformat(), "motivo": "passando_mal",
            "texto": "não tava se sentindo bem", "fim_original": at(18, 30).isoformat(), "tipo": "freela"}}
        self.db.set_estado_relacional(KEY, json.dumps({"interrupcoes": inter if interrompeu else {}}))

    def _avanca(self, now):
        from freela import Freela
        plan = {"key": "freela:2026-09-29", "what": "vídeo pra uma marca de cosméticos", "result_days": 2,
                "result_minutes": 0}
        st = {"what": plan["what"], "step": "casting_marcado", "casting_id": 7, "casting_at": at(17, 0).isoformat()}
        with patch("freela.Freela._health_blocks", return_value=None):
            Freela(self.db)._advance(plan, st, now)
        return st

    def test_saiu_no_meio_nao_fez_o_casting(self):
        self._estado(True)
        st = self._avanca(at(18, 31))
        self.assertEqual(st["step"], "fim")
        self.assertIsNone(self._summary("freela:2026-09-29:casting"))
        self.assertEqual(self._summary("freela:2026-09-29:casting_perdido"),
                         "Não terminou o casting (vídeo pra uma marca de cosméticos): saiu no meio, não tava se "
                         "sentindo bem.")

    def test_sem_interrupcao_fez(self):
        self._estado(False)
        st = self._avanca(at(18, 31))
        self.assertEqual(st["step"], "esperando")
        self.assertIn("Fez o casting", self._summary("freela:2026-09-29:casting"))


class VisaoToleranteTest(unittest.TestCase):
    def test_defeitos_comuns(self):
        from vision_service import _json_tolerante
        self.assertEqual(_json_tolerante('```json\n{"scene": "café", "food": ["pão",],}\n```'),
                         {"scene": "café", "food": ["pão"]})
        self.assertEqual(_json_tolerante('Aqui: {"scene": "rua"} pronto'), {"scene": "rua"})
        with self.assertRaises(ValueError):
            _json_tolerante('{"scene": "rua", people: []}')

    def test_tenta_de_novo_uma_vez(self):
        import asyncio
        from types import SimpleNamespace
        from vision_service import VisionService
        respostas = iter(['{\n  "scene": "trabalho",\n  people: [}', '{"scene": "uniforme no trabalho"}'])
        create = lambda **k: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=next(respostas)))])
        llm = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        vs = VisionService(llm_client=llm, vision_model="x")
        with patch.object(VisionService, "resize_and_encode_image", return_value="b64"):
            data = asyncio.run(vs.analyze_image(b"img"))
        self.assertEqual(data["scene"], "uniforme no trabalho")
        self.assertNotIn("error", data)


class AgenciaUmaSaidaSoTest(Base):
    def test_castings_emendados_no_mesmo_lugar(self):
        from agenda import Etapa
        from hoje import _saidas
        ag, lugar = "Na agência", "boutique_agency"
        a, b = "freela:2026-10-01:casting:2026-09-28", "freela:2026-10-01:casting:2026-09-29"
        etapas = [Etapa("caminho", "Indo pra agência", at(14, 58), at(15, 30), compromisso=a),
                  Etapa("la", ag, at(15, 30), at(17, 0), lugar_key=lugar, compromisso=a),
                  Etapa("la", ag, at(17, 0), at(17, 35), lugar_key=lugar, compromisso=b),
                  Etapa("voltando", "Voltando pra casa", at(17, 35), at(17, 53), compromisso=b)]
        comps = [{"key": a, "friends": [], "tipo": "freela"}, {"key": b, "friends": [], "tipo": "freela"}]
        with patch("agenda.Agenda.etapas", return_value=etapas), \
                patch("agenda.Agenda._compromissos", return_value=comps):
            out = _saidas(self.db, DIA.date(), at(20, 0))
        self.assertEqual([(s["titulo"], s["ini"], s["fim"]) for s in out],
                         [("Foi para a agência", at(14, 58), at(17, 53))])
        self.assertEqual(out[0]["volta"].inicio, at(17, 35))

    def test_lugares_diferentes_continuam_separados(self):
        from agenda import Etapa
        from hoje import _saidas
        etapas = [Etapa("la", "Na agência", at(15, 30), at(17, 0), lugar_key="boutique_agency", compromisso="x"),
                  Etapa("la", "No Starbucks", at(17, 0), at(18, 0), lugar_key="starbucks", compromisso="y")]
        with patch("agenda.Agenda.etapas", return_value=etapas), \
                patch("agenda.Agenda._compromissos", return_value=[]):
            self.assertEqual(len(_saidas(self.db, DIA.date(), at(20, 0))), 2)


class BomDiaNaRespostaTest(unittest.TestCase):
    """22:52 ele: "Te amo mais que tudo!" (ela dormindo); 05:22 o bom dia; 05:24 "Acordei agora e vi isso"."""

    def test_com_mensagem_dele_esperando_o_bom_dia_vai_na_resposta(self):
        import bot
        lote = {"id": 41}
        with patch.object(bot.availability_service.repo, "get_active_batch", return_value=lote), \
                patch.object(bot.availability_service.repo, "list_items", return_value=[{"received_at": "x"}]), \
                patch.object(bot.availability_service.repo, "antecipar", return_value=True) as antecipa, \
                patch.object(bot.memory_manager.db, "set_estado_relacional") as grava:
            self.assertTrue(bot._bom_dia_na_resposta("Hoje TINHA aula e você faltou.", at(5, 22)))
        antecipa.assert_called_once_with(41, at(5, 22))
        self.assertEqual(json.loads(grava.call_args[0][1])["batch_id"], 41)
        with patch.object(bot.memory_manager.db, "get_estado_relacional",
                          return_value=json.dumps({"batch_id": 41, "detail": "Hoje TINHA aula e você faltou."})):
            hint = bot._hint_bom_dia(41)
            self.assertIn("bom dia na mesma resposta", hint)
            self.assertIn("faltou", hint)
            self.assertIsNone(bot._hint_bom_dia(42))

    def test_sem_mensagem_esperando_bom_dia_normal(self):
        import bot
        with patch.object(bot.availability_service.repo, "get_active_batch", return_value=None):
            self.assertFalse(bot._bom_dia_na_resposta("x", at(5, 22)))


class AnteciparLoteTest(Base):
    def test_antecipa_so_o_que_esta_pendente(self):
        from pending_response import PendingResponseRepository
        alvo, criado = at(5, 40).isoformat(), at(0, 0).isoformat()
        with self.db.get_connection() as conn:
            for i, status in enumerate(("PENDING", "SENT"), start=1):
                conn.execute("""INSERT INTO response_pending_batches(id,conversation_key,active_key,status,created_at,
                                updated_at,decision,reason_code,activity_type,activity_source,urgency_max,
                                response_complexity,selected_target_at,decision_seed)
                                VALUES (?,'patrick_marina',?,?,?,?,'DEFER','sleeping','SLEEP','routine','NORMAL',
                                'SHORT',?,'s')""", (i, f"k{i}", status, criado, criado, alvo))
            conn.commit()
        repo = PendingResponseRepository(self.db)
        self.assertTrue(repo.antecipar(1, at(5, 22)))
        self.assertFalse(repo.antecipar(2, at(5, 22)))
        self.assertEqual(repo.get_batch(1)["selected_target_at"], at(5, 22).isoformat())


class RelatorioDia3Test(Base):
    def setUp(self):
        super().setUp()
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "relatorio_soak", Path(__file__).resolve().parents[1] / "scripts" / "relatorio_soak.py")
        self.rs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.rs)

    def test_jantei_com_a_tigela_que_ele_mandou(self):
        tigela = [{"event_at": at(19, 8).isoformat(), "event_type": "meal", "title": "presente do Patrick",
                   "summary": "O Patrick mandou Tigela Fit do Estação do Açaí pelo app; ela recebeu e foi comer."}]
        feito = self.rs._sem_acento(" ".join(self.rs.feito_extra(self.db, tigela, at(22, 39))))
        self.assertEqual(self.rs.fez_contradiz("Jantei sim, amor, chocolate depois kkk", feito), [])
        self.assertTrue(self.rs.fez_contradiz("Jantei sim, amor", ""))

    def test_buscopan_da_colica_moderada(self):
        from types import SimpleNamespace
        with patch("health.Health.conditions",
                   return_value=[SimpleNamespace(remedy="tomou um Buscopan de manhã")]):
            feito = self.rs._sem_acento(" ".join(self.rs.feito_extra(self.db, [], at(5, 31))))
        self.assertEqual(self.rs.fez_contradiz("Tomei um Buscopan e vou comer daqui a pouco", feito), [])


if __name__ == "__main__":
    unittest.main()
