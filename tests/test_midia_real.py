"""Mídia real (Patrick, 26/09): playlist com faixas reais, música que ele manda, leitura com progresso e
compra pelo saldo, jogos do Botafogo pela agenda da ESPN."""
import json
import random
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import futebol
import musica
from db import DatabaseManager
from futebol import Futebol
from leitura import Leitura
from musica import Musica
from seed_world_bible_v36 import seed_world_bible
from tempo_livre import TempoLivre

T = datetime(2026, 9, 26, 15, 0)
FAIXAS = [{"trackName": n, "artistName": "Sabrina Carpenter", "collectionName": "Short n' Sweet",
           "trackTimeMillis": 180000, "releaseDate": "2024-08-23T00:00:00Z", "trackId": i}
          for i, n in enumerate(("Espresso", "Please Please Please", "Taste", "Juno", "Bed Chem"), start=1)]
FAIXAS.append({"trackName": "Espresso (feat. X)", "artistName": "Outro", "trackId": 99})


def _itunes(url, timeout=8):
    if "lookup" in url:
        return {"results": [{"wrapperType": "track", "trackName": "Garota de Ipanema", "artistName": "Tom Jobim",
                             "collectionName": "Getz/Gilberto", "trackTimeMillis": 240000, "trackId": 555}]}
    return {"results": FAIXAS}


def _db(tmp):
    db = DatabaseManager(Path(tmp) / "m.db")
    seed_world_bible(db)
    with db.get_connection() as conn:
        conn.execute("INSERT INTO world_bootstrap (key, value, updated_at) VALUES ('clean_canonical_start_done','1','2026-09-01')")
        conn.commit()
    return db


class MusicaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = _db(self.temp.name)
        p = patch("musica._get_json", side_effect=_itunes)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.temp.cleanup)

    def test_catalogo_so_do_artista_e_sem_repetir(self):
        faixas = Musica(self.db).buscar_artista("Sabrina Carpenter")
        self.assertEqual([f["nome"] for f in faixas][:2], ["Espresso", "Please Please Please"])
        self.assertTrue(all(f["artista"] == "Sabrina Carpenter" for f in faixas))

    def test_aquecer_e_playlist_real(self):
        with patch.object(musica, "ARTISTAS", ("Sabrina Carpenter",)):
            self.assertEqual(Musica(self.db).aquecer(T), 1)
            self.assertEqual(Musica(self.db).aquecer(T + timedelta(hours=1)), 0, "renova só por semana")
            pl = Musica(self.db).playlist(T, T + timedelta(minutes=12), random.Random(1))
        self.assertEqual(len(pl), 4)                      # 3 min cada, 12 min de bloco
        self.assertEqual(datetime.fromisoformat(pl[1]["at"]) - datetime.fromisoformat(pl[0]["at"]), timedelta(minutes=3))
        self.assertEqual(Musica.tocando(pl, T + timedelta(minutes=4))["nome"], pl[1]["nome"])

    def test_musica_do_patrick_ela_ouve_de_verdade(self):
        f = Musica(self.db).link_do_patrick("ouve essa https://music.apple.com/br/album/x/123?i=555", T)
        self.assertEqual((f["nome"], f["artista"]), ("Garota de Ipanema", "Tom Jobim"))
        self.assertIn("AINDA NÃO OUVIU", "\n".join(Musica(self.db).prompt_lines(T)))
        pl = Musica(self.db).playlist(T, T + timedelta(minutes=10), random.Random(2))
        self.assertTrue(pl[0]["dele"], "a música dele toca primeiro")
        Musica(self.db).ouviu(pl, T + timedelta(minutes=2))
        self.assertTrue(Musica(self.db).dela()["ouvir"], "só conta depois que a faixa acabou")
        with patch("musica.random.Random.random", return_value=0.0):
            Musica(self.db).ouviu(pl, T + timedelta(minutes=5))
        dela = Musica(self.db).dela()
        self.assertFalse(dela["ouvir"])
        self.assertEqual(dela["adotadas"][0]["nome"], "Garota de Ipanema")
        with self.db.get_connection() as conn:
            ev = conn.execute("SELECT summary FROM life_events WHERE event_key LIKE 'musica:ouviu:%'").fetchone()[0]
        self.assertIn("curtiu e botou na playlist", ev)

    def test_bloco_de_musica_no_tempo_livre_e_card(self):
        with patch.object(musica, "ARTISTAS", ("Sabrina Carpenter",)):
            Musica(self.db).aquecer(T)
        tipo = next(t for t in __import__("tempo_livre").TIPOS if t[0] == "musica")
        with patch.object(TempoLivre, "_quer_se_masturbar", return_value=None), \
                patch("tempo_livre.random.Random.choices", return_value=[tipo]):
            b = TempoLivre(self.db).agora(T)
        self.assertTrue(b.faixas)
        self.assertEqual(b.texto, f"Ouvindo {b.faixas[0]['artista']}")
        from agenda import Agenda
        from world_state import WorldStateManager
        WorldStateManager(self.db).states.add_snapshot({
            "state_date": T.date().isoformat(), "observed_at": T.isoformat(), "location_place_id": 1,
            "location_region": "Botafogo", "activity": b.atividade, "energy_level": 0.6,
            "weather_context_json": None, "current_plan_json": None, "source_json": {"reason": "x"}})
        with patch("commute.Commute.legs_on", return_value=[]):
            c = Agenda(self.db).card_casa(b.inicio + timedelta(minutes=4), "Olha com frequência")
        passos = next(x for x in c["linha"] if x["estado"] == "agora")["passos"]
        self.assertIn(b.faixas[1]["nome"], [p["texto"] for p in passos])
        self.assertTrue(c["linha2"].startswith("Ouvindo "))


class LeituraTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = _db(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_progresso_anda(self):
        with patch("leitura.random.Random.choices", return_value=["Os Sete Maridos de Evelyn Hugo"]):
            s = Leitura(self.db).sessao(T, T + timedelta(minutes=40), random.Random(1), T)
        self.assertEqual((s.texto, s.pag_ini, s.pag_fim), ("Lendo Os Sete Maridos de Evelyn Hugo", 120, 160))
        self.assertEqual(Leitura(self.db).estado()["obras"]["Os Sete Maridos de Evelyn Hugo"]["pag"], 160)

    def test_termina_o_volume_e_compra_o_proximo_com_o_saldo(self):
        import financas
        financas._save(self.db, financas._init({}, T))
        with patch("leitura.random.Random.choices", return_value=["Dandadan"]):
            Leitura(self.db).sessao(T, T + timedelta(minutes=60), random.Random(1), T)        # vol. 19 inteiro
            s = Leitura(self.db).sessao(T + timedelta(hours=2), T + timedelta(hours=3), random.Random(2), T)
        self.assertEqual(s.texto, "Lendo Dandadan vol. 20")
        self.assertTrue(s.terminou)
        st = Leitura(self.db).estado()
        self.assertEqual(st["obras"]["Dandadan"]["vol"], 21)
        self.assertEqual(st["pedidos"][0]["vol"], 21)
        with self.db.get_connection() as conn:
            compra = conn.execute("SELECT title, summary FROM life_events WHERE event_key LIKE 'compra:%'").fetchone()
        self.assertEqual(compra["title"], "Dandadan vol. 21")
        saldo = financas._load(self.db)["saldo"]
        financas.materialize(self.db, T + timedelta(hours=4))
        self.assertEqual(financas._load(self.db)["saldo"], saldo - 39)
        self.assertNotIn("Dandadan", [t for t in Leitura(self.db).disponiveis(Leitura(self.db).estado())],
                         "o volume 21 ainda não chegou")


ESPN_JOGO = {"id": "401", "date": "2026-10-07T23:30Z", "competitions": [{
    "competitors": [{"homeAway": "home", "team": {"id": "6086", "displayName": "Botafogo", "shortDisplayName": "Botafogo"}},
                    {"homeAway": "away", "team": {"id": "3454", "displayName": "Vasco da Gama", "shortDisplayName": "Vasco"}}],
    "venue": {"fullName": "Estádio Nilton Santos"}, "status": {"type": {"name": "STATUS_SCHEDULED"}}}]}
ESPN_LANCES = {"keyEvents": [
    {"type": {"text": "Kickoff"}, "clock": {"displayValue": ""}},
    {"type": {"text": "Goal"}, "clock": {"displayValue": "28'"}, "team": {"displayName": "Botafogo"}},
    {"type": {"text": "Halftime"}, "clock": {"displayValue": "45'+2'"}},
    {"type": {"text": "Start 2nd Half"}, "clock": {"displayValue": "45'"}}],
    "header": {"competitions": [{"competitors": [{"homeAway": "home", "score": "1"}, {"homeAway": "away", "score": "0"}]}]}}


def _espn(url):
    if "summary" in url:
        return ESPN_LANCES
    return {"events": [ESPN_JOGO] if "bra.1" in url else []}


class FutebolTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = _db(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        p = patch("futebol._get", side_effect=_espn)
        p.start()
        self.addCleanup(p.stop)
        Futebol(self.db).atualizar(T)
        self.ini = datetime(2026, 10, 7, 20, 30)

    def test_agenda_real_em_horario_local(self):
        j = Futebol(self.db).proximo(T)
        self.assertEqual((j["inicio"], Futebol.titulo(j), j["mandante"]), (self.ini.isoformat(), "Botafogo x Vasco", True))
        self.assertTrue(Futebol(self.db).classico(j))
        self.assertIn("Próximo jogo: Botafogo x Vasco", "\n".join(Futebol(self.db).prompt_lines(T)))

    def test_lances_viram_linha_do_tempo(self):
        agora = self.ini + timedelta(minutes=70)
        Futebol(self.db).atualizar(agora)
        j = Futebol(self.db).jogo_em(agora)
        lances = Futebol(self.db).lances(j)["lances"]
        self.assertEqual([x["texto"] for x in lances], ["1º tempo", "Gol do Botafogo", "Intervalo", "2º tempo"])
        self.assertEqual(datetime.fromisoformat(lances[1]["at"]), self.ini + timedelta(minutes=28))
        self.assertEqual(datetime.fromisoformat(lances[3]["at"]), self.ini + timedelta(minutes=60))
        self.assertEqual(Futebol(self.db).placar_texto(j), "Botafogo 1 x 0 Vasco")

    def test_em_casa_ve_na_tv_da_sala(self):
        agora = self.ini + timedelta(minutes=30)
        Futebol(self.db).atualizar(agora)
        b = TempoLivre(self.db).agora(agora)
        self.assertEqual((b.tipo, b.texto, b.comodo), ("jogo", "Vendo Botafogo x Vasco", "sala"))
        from response_availability import ResponseAvailabilityPolicy
        self.assertEqual(ResponseAvailabilityPolicy(self.db)._map_place_activity("marina_apartment", b.atividade),
                         "HOME_BUSY")

    def test_convite_pro_jogo(self):
        from social_day import SocialDay
        with patch("social_day.random.Random.random", return_value=0.05):
            convites = SocialDay(self.db)._convites_jogo(self.ini.date())
        self.assertEqual(len(convites), 1)
        self.assertEqual(convites[0]["place"], "estadio_nilton_santos")
        self.assertIn("Botafogo x Vasco no Nilton Santos", convites[0]["text"])
        with patch("social_day.random.Random.random", return_value=0.3):
            bar = SocialDay(self.db)._convites_jogo(self.ini.date())[0]
        self.assertEqual(bar["place"], "quartinho_bar")


if __name__ == "__main__":
    unittest.main()


class LastFmTest(unittest.TestCase):
    def test_o_que_ele_esta_ouvindo(self):
        import io
        import os
        from lastfm import LastFm
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = _db(temp.name)
        resp = {"recenttracks": {"track": [{"name": "Espresso", "artist": {"#text": "Sabrina Carpenter"},
                                            "@attr": {"nowplaying": "true"}}]}}
        with patch.dict(os.environ, {"LASTFM_USER": "u", "LASTFM_API_KEY": "k"}), \
                patch("lastfm.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(resp).encode())):
            self.assertTrue(LastFm(db).atualizar(T))
        linha = "\n".join(LastFm(db).prompt_lines(T + timedelta(minutes=2)))
        self.assertIn("está ouvindo agora \"Espresso\" (Sabrina Carpenter)", linha)
        self.assertEqual(LastFm(db).prompt_lines(T + timedelta(hours=1)), [], "dado velho não vale")
