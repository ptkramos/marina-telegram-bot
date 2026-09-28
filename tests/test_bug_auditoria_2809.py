"""Auditoria de funcionamento: varredura do Agora e do Hoje de 28/09 (card minuto a minuto × mundo × Hoje, na
cópia do banco da produção). Casos reais do dia:

A. Belisco 16:46–16:52 com o Se arrumando do passeio do Milo às 16:47 — o mundo e o chat ficaram em "beliscando".
B. A arte do Milo adiada (ela estava na rua) caía no minuto da chegada, junto com "Brincando com o Milo" (17:43); e
   dormir encostado nela é chamego, não arte (Patrick).
C. Previsto "~22:55 Lanche" depois de "~22:30 Dormir".
D. "Pediu vitamina C Cewin… no Drogarias Pacheco" e "Pediu caramel Macchiato Grande".
E. Pão de queijo em duas linhas no Hoje ("Pediu pão de queijo R$ 13" e "Comeu pão de queijo no Starbucks").
F. Farmácia com a xícara de café no Hoje.
G. "Pulou o café da manhã 07:52–08:05".
H. "Viu o desfile da Jacquemus 15:53–16:20" com "Montou looks" começando 16:16.
I. Quem ela encontrou lá (a Gabi na Enseada às 17:07) só aparecia no Hoje; agora é passo do Lá no card.
"""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import hoje
from agenda import Agenda, Etapa, Passo
from consumo import Consumo, Item, _frase
from db import DatabaseManager
from meals import LANCHE_NOITE_ANTES_DE_DEITAR, Meals

DIA = datetime(2026, 9, 28)


def at(h, m, s=0):
    return DIA.replace(hour=h, minute=m, second=s)


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = DatabaseManager(Path(self.temp.name) / "a.db")

    def _evento(self, key, quando, tipo, title, summary):
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO life_events (event_key, event_at, event_type, title, summary, source_type, "
                         "autonomy_level, importance, created_at) VALUES (?,?,?,?,?,'simulated',1,0.1,?)",
                         (key, quando.isoformat(), tipo, title, summary, quando.isoformat()))
            conn.commit()


class BeliscoAntesDoPreparoTest(Base):
    PREPARO = Etapa("arrumando", "Se arrumando", at(16, 47), at(16, 51), chave="prep:milo:2026-09-28")

    def test_preparo_logo_depois_segura_o_belisco(self):
        with patch("agenda.Agenda.agora", return_value=None), \
                patch("agenda.Agenda.etapas", return_value=[self.PREPARO]):
            self.assertTrue(Meals(self.db)._numa_etapa(at(16, 46, 22)), "16:46 com o preparo às 16:47")
            self.assertFalse(Meals(self.db)._numa_etapa(at(16, 20)), "preparo longe: belisca")


class LancheDaNoiteTest(Base):
    def test_lanchinho_so_se_couber_antes_de_deitar(self):
        tarde = datetime(2026, 12, 1, 3, 30)
        achou = None
        with patch("academic_life.AcademicLife.blocks_on", return_value=[]), \
                patch("rituals.Rituals.wake_at", return_value=None):
            for n in range(90):
                d = date(2026, 9, 1) + timedelta(days=n)
                with patch("meals.Meals._deitar", return_value=tarde):
                    slot = next((s for s in Meals(self.db).day_plan(d) if s.key.endswith(":lanche:2")), None)
                if slot:
                    achou = (d, slot)
                    break
            if not achou:
                self.skipTest("nenhum lanchinho da noite sorteado em 90 dias")
            d, slot = achou
            cedo = slot.end + LANCHE_NOITE_ANTES_DE_DEITAR - timedelta(minutes=1)
            with patch("meals.Meals._deitar", return_value=cedo):
                self.assertFalse(any(s.key.endswith(":lanche:2") for s in Meals(self.db).day_plan(d)),
                                 "deita antes do lanchinho acabar: não entra no plano (nem no previsto do Hoje)")
            with patch("meals.Meals._deitar", return_value=slot.end + LANCHE_NOITE_ANTES_DE_DEITAR):
                self.assertTrue(any(s.key.endswith(":lanche:2") for s in Meals(self.db).day_plan(d)))


class MiloChamegoTest(unittest.TestCase):
    def test_chamego_nao_e_arte(self):
        c = hoje.curto({"event_type": "routine", "title": "Milo", "event_key": "milo:2026-09-28:arte",
                        "summary": "O Milo dormiu encostado nela no sofá."})
        self.assertEqual((c["texto"], c["sub"]), ("Chamego com o Milo", "Dormiu encostado nela no sofá"))
        c = hoje.curto({"event_type": "routine", "title": "Milo", "event_key": "milo:2026-09-30:arte",
                        "summary": "O Milo roubou uma meia e saiu correndo pela casa."})
        self.assertEqual(c["texto"], "Arte do Milo")

    def test_pedir_colo_derrete(self):
        from emotion import appraise_event
        out = appraise_event({"event_key": "milo:2026-09-30:arte", "event_type": "routine",
                              "summary": "O Milo pediu colo e não quis mais sair."})
        self.assertEqual(out[0][:2], ("afeto", "ternura"))


class ConsumoNaLojaTest(Base):
    def _consumo(self, tipo, lugar, nome, valor):
        outing = {"source_key": f"vontade:2026-09-28:{tipo}", "metadata_json": json.dumps({"tipo": tipo})}
        item = Item(at(15, 42), nome, _frase(nome), valor)
        Consumo(self.db)._record(outing, 0, item, lugar, "", [], at(15, 43))
        with self.db.get_connection() as conn:
            return dict(conn.execute("SELECT * FROM life_events WHERE event_key=?",
                                     (f"consumo:vontade:2026-09-28:{tipo}:0",)).fetchone())

    def test_farmacia_comprou_na_drogaria(self):
        ev = self._consumo("farmacia", "Drogarias Pacheco", "Vitamina C Cewin 500 mg 30 comprimidos", 19)
        self.assertEqual(ev["summary"], "Comprou Vitamina C Cewin 500 mg 30 comprimidos na Drogarias Pacheco (R$ 19).")
        c = hoje.curto(ev)
        self.assertEqual((c["texto"], c["valor"]), ("Comprou Vitamina C Cewin 500 mg 30 comprimidos", 19))

    def test_cafe_pediu_com_o_nome_do_produto_inteiro(self):
        ev = self._consumo("cafe", "Starbucks", "Caramel Macchiato Grande", 27)
        self.assertEqual(ev["summary"], "Pediu Caramel Macchiato Grande no Starbucks (R$ 27).")
        self.assertEqual(_frase("Pão de queijo"), "pão de queijo")


class HojeTest(Base):
    def _view(self, eventos, saidas=(), blocos=None, agora=at(18, 0)):
        with patch("hoje._saidas", return_value=list(saidas)), patch("hoje._eventos", return_value=eventos), \
                patch("hoje._blocos", return_value=blocos or {}), patch("hoje._previstos", return_value=[]), \
                patch("sleep_plan.SleepPlan.wake", return_value=at(7, 33)):
            v = hoje.hoje_view(self.db, agora)
        return [i for p in v["periodos"] for i in p["itens"]]

    def test_pao_de_queijo_uma_linha_so(self):
        eventos = [{"event_key": "consumo:vontade:2026-09-28:1440:1", "event_at": at(15, 0).isoformat(), "end_at": None,
                    "event_type": "consumo", "title": "Starbucks · Pão de queijo",
                    "summary": "Pediu pão de queijo no Starbucks (R$ 13)."},
                   {"event_key": "meal:2026-09-28:lanche:fora", "event_at": at(15, 0).isoformat(), "end_at": None,
                    "event_type": "snack", "title": "comeu fora (Starbucks)", "summary": "Comeu pão de queijo no Starbucks."}]
        textos = [i["texto"] for i in self._view(eventos)]
        self.assertEqual(textos, ["Acordou", "Pediu pão de queijo"])

    def test_pulou_o_cafe_sem_intervalo(self):
        c = hoje.curto({"event_key": "meal:2026-09-28:cafe", "event_type": "meal", "title": "café da manhã",
                        "event_at": at(7, 52).isoformat(), "end_at": at(8, 5).isoformat(),
                        "summary": "Pulou o café da manhã: acordou em cima da hora pra aula."})
        self.assertEqual((c["texto"], c["sub"], c["fim"]),
                         ("Pulou o café da manhã", "Acordou em cima da hora pra aula", None))

    def test_farmacia_com_o_icone_dela(self):
        la = Etapa("la", "Na Drogarias Pacheco", at(15, 38), at(15, 47), lugar_key="loja_pacheco")
        self.assertEqual(hoje.SAIDA_IC[hoje._tipo_saida("vontade:2026-09-28:e1519", la, "farmacia")], "pill")
        self.assertEqual(hoje.SAIDA_IC[hoje._tipo_saida("vontade:2026-09-28:1440", la, "cafe")], "coffee")

    def test_bloco_termina_quando_o_proximo_comeca(self):
        eventos = [{"event_key": "livre:2026-09-28:18", "event_at": at(15, 53).isoformat(), "end_at": None,
                    "event_type": "tempo_livre", "title": "Vendo o desfile da Jacquemus",
                    "summary": "Ficou vendo o desfile da Jacquemus pelo celular no closet."},
                   {"event_key": "livre:2026-09-28:19", "event_at": at(16, 16).isoformat(), "end_at": None,
                    "event_type": "tempo_livre", "title": "Montando looks", "summary": "Ficou montando looks no closet."}]
        itens = self._view(eventos, blocos={"livre:2026-09-28:18": at(16, 20), "livre:2026-09-28:19": at(16, 46)})
        desfile = next(i for i in itens if "desfile" in i["texto"])
        self.assertEqual(desfile["hora"], "15:53–16:16")


class PrevistoDepoisDeDormirTest(Base):
    def test_serie_depois_de_deitar_nao_e_prevista(self):
        with patch("meals.Meals.day_plan", return_value=[]),                 patch("watch.Watching.night_plan", return_value={"start": at(21, 55)}),                 patch("sleep_plan.SleepPlan.bed", return_value=at(21, 51)):
            prev = hoje._previstos(self.db, DIA.date(), at(18, 20), [])
        self.assertEqual([p["texto"] for p in prev], ["Dormir"])


class EncontroNoCardTest(Base):
    def setUp(self):
        super().setUp()
        self._evento("social:2026-09-28:npc_gabi_freitas:npc:walk", at(17, 7), "social_contact", "presencial com a Gabi",
                     "Encontrou a Gabi, tutora da spitz que brinca com o Milo (Enseada/Praia de Botafogo); assunto: cachorros.")
        self._evento("social:2026-09-28:bia_andrade:role", at(17, 10), "social_contact", "presencial com a Bia",
                     "Encontrou a Bia; assunto: fofoca.")

    def test_gabi_vira_passo_do_la_e_nao_e_o_passo_atual(self):
        ag = Agenda(self.db)
        enc = ag._encontros({"friends": ["bia_andrade"]}, at(16, 55), at(17, 39))
        self.assertEqual([(p.texto, p.inicio, p.encontro) for p in enc], [("Encontrou a Gabi", at(17, 7), True)],
                         "quem foi junto com ela não vira encontro")
        la = Etapa("la", "Na Enseada", at(16, 55), at(17, 39),
                   passos=[Passo("Passeando", at(16, 55)), *enc, Passo("Xixi do Milo", at(17, 25))])
        self.assertEqual(ag.passo_atual(la, at(17, 10)).texto, "Passeando")


if __name__ == "__main__":
    unittest.main()
