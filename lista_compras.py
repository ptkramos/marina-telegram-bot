"""Lista de compras da semana (Patrick, 28/09 — item 3 do freio).

Às 08:52 de 28/09 ele pediu barrinhas "quando for fazer compra da semana" e ela prometeu "vou colocar barrinhas na
lista da semana" — e não existia lista no mundo. Agora:

- O que ele pede e ela topa (ou o que ela mesma diz que vai comprar na compra da semana) entra na lista. Um modelo
  barato lê a fala dela e a mensagem dele, só quando o trecho fala de lista/mercado/compra da semana (como a agenda
  reativa).
- A lista vai no prompt (ela sabe o que anotou e quando é a compra) e no card do mercado: o passo "Fazendo a lista"
  no Se arrumando e o "Enchendo o carrinho" no Lá mostram os itens embaixo.
- Na compra da semana (`vontade.mercado_semana`, o pai paga — fora do saldo e do extrato, D9), o que foi anotado até
  ela encher o carrinho é comprado de verdade: acontecimento "Comprou barrinhas de proteína no Zona Sul (da lista,
  pedido do Patrick)", que aparece no Hoje dentro da saída e no dia dela; ela pode comentar depois.

Estado em estado_relacional[KEY], sem migration.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

KEY = "lista_compras_json"
LISTA_RE = re.compile(r"\blista\b|compras? da semana|pr[oó]xima compra|mercado|supermercado|zona sul", re.IGNORECASE)
CARRINHO = 0.35              # "Enchendo o carrinho" começa em 35% do Lá (agenda.LA_PASSOS["mercado_semana"])
COMPRADO_NO_PROMPT = timedelta(hours=48)
DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def _hhmm(at: datetime) -> str:
    return at.strftime("%H:%M")


class ListaCompras:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------- estado --
    def _load(self) -> dict:
        try:
            st = json.loads(self.db.get_estado_relacional(KEY) or "{}")
        except (TypeError, ValueError):
            st = {}
        st.setdefault("itens", [])
        return st

    def _save(self, st: dict) -> None:
        self.db.set_estado_relacional(KEY, json.dumps(st, ensure_ascii=False))

    def pendentes(self, now: Optional[datetime] = None) -> list[dict]:
        return [i for i in self._load()["itens"] if i["status"] == "pendente"
                and (now is None or datetime.fromisoformat(i["em"]) <= now)]

    def adicionar(self, item: str, quem: str, now: datetime) -> bool:
        item = re.sub(r"\s+", " ", (item or "").strip().strip(".")).lower()[:60]
        if not item:
            return False
        st = self._load()
        if any(i["item"] == item and i["status"] == "pendente" for i in st["itens"]):
            return False
        st["itens"].append({"item": item, "quem": "patrick" if quem == "patrick" else "marina",
                            "em": now.isoformat(timespec="minutes"), "status": "pendente"})
        self._save(st)
        logger.info("lista_compras.adicionou item=%s quem=%s", item, quem)
        return True

    def tirar(self, item: str, now: datetime) -> bool:
        item = (item or "").strip().lower()
        st = self._load()
        achou = False
        for i in st["itens"]:
            if i["status"] == "pendente" and (i["item"] == item or item in i["item"]):
                i["status"], i["tirado_em"] = "tirado", now.isoformat(timespec="minutes")
                achou = True
        if achou:
            self._save(st)
            logger.info("lista_compras.tirou item=%s", item)
        return achou

    # ----------------------------------------------------------- conversa --
    def observe(self, fala: str, msg_dele: str, now: datetime, *, llm=None) -> Optional[dict]:
        """Depois que a fala dela saiu: o que ela topou pôr na lista (ou tirou) vira lista de verdade."""
        if not fala or not LISTA_RE.search(f"{msg_dele or ''} {fala}"):
            return None
        data = self._classifica(fala, msg_dele, now, llm=llm)
        if not data:
            return None
        feito = {"adicionou": [], "tirou": []}
        for it in data.get("adicionar") or []:
            if isinstance(it, dict) and self.adicionar(str(it.get("item") or ""), str(it.get("quem") or ""), now):
                feito["adicionou"].append(it.get("item"))
        for it in data.get("tirar") or []:
            if self.tirar(str(it), now):
                feito["tirou"].append(it)
        return feito if feito["adicionou"] or feito["tirou"] else None

    def _classifica(self, fala: str, msg_dele: str, now: datetime, *, llm=None) -> Optional[dict]:
        from config import settings
        lista = ", ".join(i["item"] for i in self.pendentes()) or "(vazia)"
        prompt = (
            "Você lê um trecho de conversa entre a Marina e o namorado (Patrick) e diz o que entra ou sai da LISTA DE "
            "COMPRAS DA SEMANA dela (o mercado que ela faz uma vez por semana).\n"
            f"Lista agora: {lista}\n\n"
            f"Patrick: \"{(msg_dele or '')[:400]}\"\nMarina: \"{fala[:400]}\"\n\n"
            "Responda só JSON: {\"adicionar\": [{\"item\": \"nome curto em minúsculas\", \"quem\": \"patrick\"|"
            "\"marina\"}], \"tirar\": [\"item\"]}.\n"
            "Regras: só entra o que ela topou pôr na lista ou disse que vai comprar no mercado/na compra da semana "
            "(\"vou colocar na lista\", \"compro quando for no mercado\"); quem = quem pediu. Pedido dele que ela "
            "recusou, hipótese, pergunta ou brincadeira não entra. Comida pedida no iFood, compra de outra loja ou "
            "coisa que ela vai comprar hoje fora do mercado não é da lista. Tirar = ela desistiu ou disse que já "
            "tem. Nada a fazer: listas vazias."
        )
        try:
            if llm is None:
                from openai import OpenAI
                llm = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)
            model = getattr(settings, "AGENDA_LLM_MODEL", "") or settings.LLM_FALLBACK_MODEL
            from llm_options import llm_kwargs
            resp = llm.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}],
                                               temperature=0, response_format={"type": "json_object"},
                                               **llm_kwargs(150, model))
            raw = (resp.choices[0].message.content or "").strip()
            data = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        except Exception:
            logger.exception("lista_compras.classifica")
            return None
        logger.info("lista_compras.classificou adicionar=%s tirar=%s", data.get("adicionar"), data.get("tirar"))
        return data if isinstance(data, dict) else None

    # -------------------------------------------------------------- mundo --
    def _compras(self, dias: tuple) -> list[dict]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """SELECT id, source_key, event_at, end_at, location_key, metadata_json FROM eventos_pendentes
                   WHERE source_key LIKE 'mercado:%' AND status!='cancelled' AND confirmed=1""").fetchall()
        out = []
        for r in rows:
            ini = datetime.fromisoformat(r["event_at"])
            if ini.date() in dias:
                out.append({**dict(r), "inicio": ini, "fim": datetime.fromisoformat(r["end_at"])})
        return out

    @staticmethod
    def carrinho(compra: dict) -> datetime:
        return compra["inicio"] + (compra["fim"] - compra["inicio"]) * CARRINHO

    def _estava_la(self, compra: dict, at: datetime) -> bool:
        try:
            from calendar_world import CalendarWorld
            c = CalendarWorld(self.db).current(at, include_academic=False)
        except Exception:
            logger.exception("lista_compras.estava_la")
            return False
        return bool(c and c.get("calendar_event_id") == compra["id"])

    def materialize(self, now: datetime) -> int:
        """Na compra da semana, o que estava anotado até ela encher o carrinho é comprado de verdade."""
        st = self._load()
        if not any(i["status"] == "pendente" for i in st["itens"]):
            return 0
        feitos = 0
        for compra in self._compras((now.date() - timedelta(days=1), now.date())):
            at = self.carrinho(compra)
            if at > now or at > compra["fim"]:
                continue
            itens = [i for i in st["itens"] if i["status"] == "pendente" and datetime.fromisoformat(i["em"]) <= at]
            if not itens or not self._estava_la(compra, at):
                continue
            lugar = self._lugar(compra.get("location_key"))
            for n, i in enumerate(itens):
                i.update(status="comprado", comprado_em=at.isoformat(timespec="minutes"), compra=compra["source_key"])
                self._acontecimento(f"lista:{compra['source_key']}:{i['item']}", at + timedelta(minutes=n), i, lugar)
                feitos += 1
        if feitos:
            self._save(st)
        return feitos

    def _lugar(self, key: Optional[str]) -> str:
        if not key:
            return "no mercado"
        from vontade import no
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT name FROM world_places WHERE canonical_key=?", (key,)).fetchone()
        return no(row["name"]) if row else "no mercado"

    def _acontecimento(self, key: str, at: datetime, item: dict, lugar: str) -> None:
        quem = "pedido do Patrick" if item["quem"] == "patrick" else "ela tinha anotado"
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO life_events(event_key,event_at,event_type,title,summary,source_type,
                   autonomy_level,importance,participants_json,share_worthy,created_at)
                   VALUES (?,?,'consumo',?,?,'simulated',1,0.1,?,0.3,?)""",
                (key, at.isoformat(), f"lista · {item['item']}",
                 f"Comprou {item['item']} {lugar} (da lista, {quem}).", json.dumps(["marina"]), datetime.now().isoformat()))
            conn.commit()

    # --------------------------------------------------------------- card --
    def nota(self, source_key: str, now: datetime) -> str:
        """Os itens da lista nessa ida ao mercado (card: embaixo de "Fazendo a lista" e "Enchendo o carrinho")."""
        itens = self._load()["itens"]
        comprados = [i["item"] for i in itens if i.get("compra") == source_key]
        if comprados:
            return ", ".join(comprados)
        return ", ".join(i["item"] for i in self.pendentes(now))

    # ------------------------------------------------------------- prompt --
    def _proxima_compra(self, now: datetime) -> Optional[datetime]:
        compra = next((c for c in sorted(self._compras((now.date(), now.date() + timedelta(days=1))),
                                         key=lambda c: c["inicio"]) if c["fim"] > now), None)
        if compra:
            return compra["inicio"]
        try:
            from casa import Casa
            casa = Casa(self.db)
            for d in range(0, 8):
                dia = now.date() + timedelta(days=d)
                it = next((p for p in casa.day_plan(dia) if p["key"].endswith(":mercado")), None)
                if it and it["at"] > now:
                    return it["at"]
        except Exception:
            logger.exception("lista_compras.proxima")
        return None

    def _quando(self, at: datetime, now: datetime) -> str:
        dias = (at.date() - now.date()).days
        dia = "hoje" if dias == 0 else "amanhã" if dias == 1 else DIAS[at.weekday()]
        return f"{dia}, lá pelas {_hhmm(at)}"

    def prompt_lines(self, now: datetime) -> list[str]:
        itens = self._load()["itens"]
        pend = [i for i in itens if i["status"] == "pendente" and datetime.fromisoformat(i["em"]) <= now]
        comprados = [i for i in itens if i["status"] == "comprado" and i.get("comprado_em")
                     and timedelta(0) <= now - datetime.fromisoformat(i["comprado_em"]) <= COMPRADO_NO_PROMPT]
        if not pend and not comprados:
            return []
        lines = ["[LISTA DE COMPRAS DA SEMANA — anotada de verdade]"]
        for i in pend:
            em = datetime.fromisoformat(i["em"])
            quem = "o Patrick pediu" if i["quem"] == "patrick" else "você anotou"
            lines.append(f"- {i['item']} ({quem}, {DIAS[em.weekday()]} {_hhmm(em)})")
        if pend:
            prox = self._proxima_compra(now)
            if prox:
                lines.append(f"- Próxima compra da semana: {self._quando(prox, now)} (o pai paga a comida).")
        for i in comprados:
            at = datetime.fromisoformat(i["comprado_em"])
            quem = ", o Patrick que pediu" if i["quem"] == "patrick" else ""
            lines.append(f"- Já comprou {i['item']} na compra da semana ({DIAS[at.weekday()]} {_hhmm(at)}{quem}); "
                         f"está em casa.")
        return lines
