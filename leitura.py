"""Leitura de verdade (Patrick, 26/09 — etapa 1, mídia real).

Ela lê mangás dos animes dela, romance/YA, moda e os livros da faculdade — títulos **reais**, com
progresso (volume e página) que anda quando ela lê no tempo livre. Quando termina o último volume
que tem em casa, compra o próximo com o saldo dela (chega em uns dias); sem saldo, espera e lê
outra coisa. Tudo vira acontecimento (ela lembra e pode contar).

Dados conferidos em 26/09/2026: My Dress-Up Darling tem 15 volumes (Panini); Dandadan está no
volume 22 no Brasil (Panini, set/2026); Kaguya-sama tem 28 volumes (Panini).
"""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

KEY = "leitura_json"
ENTREGA_DIAS = (2, 4)

# título → (tipo, como aparece no card, volumes publicados no Brasil, páginas por volume, preço, peso)
OBRAS = {
    "Dandadan": ("manga", "Dandadan", 22, 192, 39, 1.5),
    "My Dress-Up Darling": ("manga", "My Dress-Up Darling", 15, 176, 37, 1.5),
    "Kaguya-sama": ("manga", "Kaguya-sama", 28, 192, 37, 1.0),
    "Os Sete Maridos de Evelyn Hugo": ("livro", "Os Sete Maridos de Evelyn Hugo", 1, 360, 55, 1.2),
    "De Férias com Você": ("livro", "De Férias com Você", 1, 400, 50, 1.0),
    "A Hipótese do Amor": ("livro", "A Hipótese do Amor", 1, 368, 50, 1.0),
    "Vermelho, Branco e Sangue Azul": ("livro", "Vermelho, Branco e Sangue Azul", 1, 400, 55, 0.8),
    "O Diabo Veste Prada": ("livro", "O Diabo Veste Prada", 1, 432, 45, 0.7),
    "Vogue Brasil": ("revista", "a Vogue do mês", 1, 120, 0, 0.6),
}
PAG_POR_MIN = {"manga": 3.5, "livro": 1.0, "revista": 2.5}

# Onde ela está hoje (canônico a partir de 26/09): (volume atual, página, volumes que tem em casa)
INICIO = {
    "Dandadan": (19, 0, 20),
    "My Dress-Up Darling": (9, 60, 15),
    "Kaguya-sama": (20, 0, 21),
    "Os Sete Maridos de Evelyn Hugo": (1, 120, 1),
    "De Férias com Você": (1, 0, 0),              # na lista: ainda não comprou
    "A Hipótese do Amor": (1, 0, 0),
    "Vermelho, Branco e Sangue Azul": (1, 0, 0),
    "O Diabo Veste Prada": (1, 0, 0),
    "Vogue Brasil": (1, 0, 1),
}
LIDOS_CANON = ("É Assim que Acaba",)


@dataclass
class Sessao:
    titulo: str
    texto: str               # "Lendo Dandadan vol. 19"
    vol: int
    pag_ini: int
    pag_fim: int
    pags: int
    terminou: bool

    def pagina(self, inicio: datetime, fim: datetime, now: datetime) -> int:
        frac = max(0.0, min(1.0, (now - inicio).total_seconds() / max(60.0, (fim - inicio).total_seconds())))
        return round(self.pag_ini + (self.pag_fim - self.pag_ini) * frac)


class Leitura:
    def __init__(self, db):
        self.db = db

    def estado(self) -> dict:
        raw = self.db.get_estado_relacional(KEY)
        try:
            st = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            st = {}
        if not st:
            st = {"obras": {t: {"vol": v, "pag": p, "tem": tem} for t, (v, p, tem) in INICIO.items()},
                  "pedidos": [], "lidos": list(LIDOS_CANON)}
        return st

    def _save(self, st: dict) -> None:
        self.db.set_estado_relacional(KEY, json.dumps(st, ensure_ascii=False))

    def _chegadas(self, st: dict, now: datetime) -> None:
        for p in list(st["pedidos"]):
            if datetime.fromisoformat(p["chega"]) <= now:
                o = st["obras"][p["titulo"]]
                o["tem"] = max(o["tem"], p["vol"])
                st["pedidos"].remove(p)
                self._evento(f"leitura:chegou:{p['titulo']}:{p['vol']}", datetime.fromisoformat(p["chega"]),
                             f"Chegou {self._nome(p['titulo'], p['vol'])} que ela comprou.", now)

    @staticmethod
    def _nome(titulo: str, vol: int) -> str:
        tipo, curto, total, *_ = OBRAS[titulo]
        return f"{curto} vol. {vol}" if tipo == "manga" else curto

    def disponiveis(self, st: dict) -> list[str]:
        return [t for t, o in st["obras"].items() if o["tem"] >= o["vol"] and t not in st["lidos"]]

    def sessao(self, inicio: datetime, fim: datetime, rng: random.Random, now: datetime) -> Optional[Sessao]:
        """Decide o que ela lê no bloco e avança o progresso de verdade (idempotência é do tempo_livre)."""
        st = self.estado()
        self._chegadas(st, now)
        opcoes = self.disponiveis(st)
        if not opcoes:
            self._save(st)
            return None
        titulo = rng.choices(opcoes, weights=[OBRAS[t][5] for t in opcoes])[0]
        tipo, curto, total, pags, preco, _ = OBRAS[titulo]
        o = st["obras"][titulo]
        minutos = (fim - inicio).total_seconds() / 60
        pag_fim = min(pags, o["pag"] + round(minutos * PAG_POR_MIN[tipo]))
        s = Sessao(titulo, f"Lendo {self._nome(titulo, o['vol'])}", o["vol"], o["pag"], pag_fim, pags, pag_fim >= pags)
        if s.terminou:
            fim_at = inicio + timedelta(minutes=(pags - o["pag"]) / PAG_POR_MIN[tipo])
            self._evento(f"leitura:terminou:{titulo}:{o['vol']}", fim_at,
                         f"Terminou de ler {self._nome(titulo, o['vol'])}.", now)
            if tipo == "manga" and o["vol"] < total:
                o["vol"] += 1
                o["pag"] = 0
                if o["tem"] < o["vol"]:
                    self._compra(st, titulo, o["vol"], preco, fim_at, rng, now)
            elif tipo == "revista":
                o["pag"] = 0                                # a do mês que vem
            else:
                st["lidos"].append(titulo)
                proximo = next((t for t, x in st["obras"].items() if OBRAS[t][0] == "livro" and x["tem"] < 1
                                and t not in st["lidos"] and not any(p["titulo"] == t for p in st["pedidos"])), None)
                if proximo:
                    self._compra(st, proximo, 1, OBRAS[proximo][4], fim_at, rng, now)
        else:
            o["pag"] = pag_fim
        self._save(st)
        return s

    def _compra(self, st: dict, titulo: str, vol: int, preco: int, at: datetime, rng: random.Random,
                now: datetime) -> None:
        """Compra o próximo com o saldo dela (financas debita pelo acontecimento)."""
        try:
            import financas
            saldo = int(financas._load(self.db).get("saldo", 0))
        except Exception:
            saldo = 0
        nome = self._nome(titulo, vol)
        if saldo < preco:
            self._evento(f"leitura:semsaldo:{titulo}:{vol}", at,
                         f"Queria comprar {nome}, mas o dinheiro do mês tá curto: vai esperar.", now)
            return
        chega = at + timedelta(days=rng.randint(*ENTREGA_DIAS))
        chega = chega.replace(hour=rng.randint(10, 17), minute=rng.choice((0, 15, 30, 45)))
        st["pedidos"].append({"titulo": titulo, "vol": vol, "chega": chega.isoformat()})
        self._evento(f"compra:leitura:{titulo}:{vol}", at,
                     f"Comprou {nome} na Amazon por R$ {preco} (chega {chega:%d/%m}).", now, titulo=nome)

    def _evento(self, key: str, at: datetime, summary: str, now: datetime, *, titulo: str = "leitura") -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'midia',?,?,'simulated',1,0.2,?,0.4,?)""",
                (key, at.isoformat(), titulo, summary, json.dumps(["marina"]), now.isoformat()))
            conn.commit()

    def prompt_lines(self, now: datetime) -> list[str]:
        st = self.estado()
        lendo = []
        for t in self.disponiveis(st):
            o = st["obras"][t]
            if o["pag"] or OBRAS[t][0] == "manga":
                lendo.append(f"{self._nome(t, o['vol'])}" + (f" (pág. {o['pag']})" if o["pag"] else ""))
        linhas = ["[LEITURA — real; não invente livro nem volume fora daqui]",
                  "- Lendo: " + ", ".join(lendo) + "."]
        if st["pedidos"]:
            linhas.append("- Esperando chegar: " + ", ".join(
                f"{self._nome(p['titulo'], p['vol'])} ({datetime.fromisoformat(p['chega']):%d/%m})" for p in st["pedidos"]) + ".")
        if st["lidos"]:
            linhas.append("- Já leu: " + ", ".join(st["lidos"][-4:]) + ".")
        return linhas
