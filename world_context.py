"""Contexto compacto da World Bible v3.6; não usa o prompt biográfico legado."""

import json
from datetime import datetime
from typing import Optional

from db import DatabaseManager
from config import settings
from prompt_policy import CONTROL_EN, CONTROL_PT, DATA_CHANNEL_POLICY_EN, is_canonical_runtime_ready
from world_repository import WorldBibleRepository
from world_state import WorldStateManager


class WorldContextBuilder:
    def __init__(self, db: DatabaseManager, *, cycle_mgr=None, retriever=None, stale_minutes: int = 60):
        self.db = db
        self.bible = WorldBibleRepository(db)
        self.state = WorldStateManager(db, stale_minutes=stale_minutes)
        self.cycle_mgr = cycle_mgr
        self.retriever = retriever

    def build(
        self, *, now: Optional[datetime] = None, user_message: str = "",
        quoted_context: str = "", web_context: str = "", vision_context: str = "",
        planner_tone: Optional[str] = None, planner_goal: Optional[str] = None,
        control_language: str = "en", output_language: str = "pt-BR",
        privacy_subjects: Optional[list[tuple[str, int]]] = None,
    ) -> str:
        now = now or datetime.now()
        if True:
            from calendar_world import local_time

            now = local_time(now)
        marina = self.bible.get_character("marina")
        if not marina or marina["canon_locked"] != 1:
            raise RuntimeError("World Bible v3.6 ausente ou não bloqueada; não usar prompt legado")
        if not is_canonical_runtime_ready(self.db):
            raise RuntimeError("CLEAN_CANONICAL_START ainda não concluído; não ativar Living World")
        if control_language not in ("en", "pt-BR"):
            raise ValueError("PROMPT_CONTROL_LANGUAGE deve ser 'en' ou 'pt-BR'")
        if output_language != "pt-BR":
            raise ValueError("Saída v3.6 suporta pt-BR nesta etapa")

        biography = json.loads(marina["initial_state_json"])
        age = self.bible.age_on("marina", now.date())
        if age is None:
            raise RuntimeError("Data de nascimento canônica ausente")
        state = self.state.resolve(now, energy=self._energy())
        location = self._location_name(state["location_place_id"])
        source = json.loads(state["source_json"] or "{}")
        reason = source.get("reason", "unknown")
        certainty = "compromisso/plano explícito" if reason in ("confirmed_commitment", "explicit_plan") else "inferência de rotina"
        if (True
                and source.get('calendar_event_id')):
            location = 'local reservado'

        control = CONTROL_EN if control_language == "en" else CONTROL_PT
        blocks = [
            control,
            DATA_CHANNEL_POLICY_EN,
            "[WORLD BIBLE CANÔNICA — núcleo]",
            f"Nome: {marina['display_name']}. Nascimento: {marina['birth_date']}. Idade hoje: {age} anos.",
            f"Mora sozinha em Botafogo, Rio de Janeiro; nasceu em {biography['birthplace']}.",
            "Estuda Design/Corpo e Moda na PUC-Rio; no cotidiano diz 'facul' ou 'faculdade'. É modelo freelance.",
            "Milo é seu Shih Tzu. Henrique Salles é seu pai; mora em São Paulo. Sua mãe faleceu quando ela era pequena.",
            "Patrick Ramos é seu primeiro namorado oficial; relacionamento comprometido e importante, sem apagar sua autonomia.",
            "Não há ex-namorados oficiais canônicos. Lacunas do passado permanecem indefinidas.",
            "Traços centrais: expressiva, afetuosa, espontânea, curiosa, independente; humor leve e necessidade ocasional de silêncio.",
            "[WORLD STATE — agora]",
            f"Horário local: {now.isoformat(timespec='minutes')}. Local: {location or state['location_region'] or 'não definido'}.",
            f"Atividade: {state['activity'] or 'não definida'} ({certainty}).",
        ]
        if state["weather_context_json"]:
            weather = json.loads(state["weather_context_json"])
            if weather.get("heavy_rain"):
                blocks.append("Condição contextual: chuva forte; deslocamentos externos menos prováveis.")

        if True:
            from calendar_world import CalendarWorld

            calendar = CalendarWorld(self.db)
            upcoming = calendar.next(
                now, include_academic=True)
            if upcoming:
                blocks.append('[PRÓXIMO COMPROMISSO — calendário único] '
                              f"{upcoming['activity']} em {upcoming['start_at']}.")
            holiday = calendar.context.get(f'holiday:{now.date().isoformat()}', now=now)
            if holiday and holiday['payload']['date'] == now.date().isoformat():
                label = ('PONTO FACULTATIVO OBSERVADO' if holiday['payload']['scope'] == 'optional'
                         else 'FERIADO OBSERVADO')
                blocks.append(f'[{label}] '
                              f"{holiday['payload']['name']} ({holiday['payload']['scope']}); "
                              f"fonte: {holiday['source_name']}.")
            if True:
                from academic_life import AcademicLife

                academic = AcademicLife(self.db)
                term = academic._active_term_on(now.date())
                phase = academic.phase(now, term)
                classes = academic.blocks_on(now.date())
                compact = (f"[VIDA ACADÊMICA] PUC-Rio, Design 2023, foco Corpo e Moda; "
                           f"semestre: {term['term_key'] if term else 'férias'}; "
                           f"fase: {phase}; aulas hoje: {len(classes)}.")
                current = next((item for item in classes
                                if item['start_at'] <= now.isoformat() < item['end_at']), None)
                following = next((item for item in classes if item['start_at'] > now.isoformat()), None)
                if current:
                    compact += f" Aula atual: {current['display_name']} até {current['end_time']}."
                if following:
                    compact += f" Próxima: {following['display_name']} às {following['start_time']}."
                elif not classes:
                    compact += " Hoje NÃO tem aula (dia livre da faculdade); não invente que teve ou foi à aula hoje."
                blocks.append(compact)
            with self.db.get_connection() as conn:
                reminders = conn.execute("""SELECT COUNT(*) FROM reminders
                    WHERE status='confirmed'""").fetchone()[0]
                open_loops = conn.execute("""SELECT COUNT(*) FROM open_loops
                    WHERE status='open' AND COALESCE(is_archived,0)=0""").fetchone()[0]
            blocks.append(f'[CONTINUIDADE] {reminders} lembretes confirmados; '
                          f'{open_loops} assuntos em aberto.')

        emotional = self._emotional_context()
        if emotional:
            blocks.extend(["[SEU ESTADO EMOCIONAL INTERNO ATUAL]", *emotional])

        active_loops = self.db.get_open_loops_ativos(
            limit=getattr(settings, 'MAX_ACTIVE_OPEN_LOOPS_CONTEXT', 2))
        if active_loops:
            blocks.append("[ASSUNTOS AINDA EM ABERTO COM O PATRICK]")
            blocks.extend(f"- {loop['content']}" for loop in active_loops)
            blocks.append("Assuntos em andamento: demonstre interesse natural, sem cobrança.")

        reconfirm = self.db.get_memorias_para_reconfirmacao(limit=1)
        if reconfirm:
            blocks.append("[OPORTUNIDADE DE RECONFIRMAÇÃO SUTIL]")
            blocks.append(
                "Checar carinhosamente se ainda vale: "
                f"'{reconfirm[0].get('fato') or ''}'."
            )

        preferences = self._compact_preferences()
        if preferences:
            blocks += ["[GOSTOS CANÔNICOS RELEVANTES]", ", ".join(preferences) + "."]
        social = self._social_context(user_message)
        if social:
            blocks += ["[RELAÇÕES CANÔNICAS RELEVANTES — não implica compartilhar intimidades]", *social]
        if True:
            from relationship_world import RelationshipWorld

            relationship = RelationshipWorld(self.db)
            culture = relationship.culture_context(now=now)
            if culture:
                blocks.append('[CULTURA DO CASAL — evidência repetida] ' + '; '.join(culture))
            shared = relationship.shared_history(limit=2)
            if shared:
                blocks.append('[JÁ CONTADO A PATRICK — não apresentar como novidade] '
                              + '; '.join(item['title'] for item in shared))
        with self.db.get_connection() as conn:
            learned = conn.execute("""SELECT p.category,COALESCE(w.name,p.value) AS value,p.preference_type
                FROM character_preferences p LEFT JOIN world_places w ON p.category='place' AND w.canonical_key=p.value
                WHERE p.character_key='marina' AND p.canon_locked=0 AND p.active=1
                AND p.strength>=0.6 AND p.times_reinforced>=3
                AND NOT (p.preference_type='current_interest' AND p.strength < 0.35)
                ORDER BY p.last_seen_at DESC,p.id LIMIT 3""").fetchall()
        if learned:
            blocks += ['[INTERESSES E PREFERÊNCIAS APRENDIDOS — não substituem gostos canônicos]']
            blocks.extend(f"{r['category']}: {r['value']} ({r['preference_type']})" for r in learned)

        if self.cycle_mgr:
            cycle = self.cycle_mgr.get_cycle_info()
            blocks.append(
                f"[CICLO — fonte única: MenstrualCycleManager] {cycle['name']}; influência sutil, não determina ações."
            )
        from style_engine import StyleEngine
        _style_eng = StyleEngine(self.db)
        learned_summary = _style_eng.get_learned_style_summary()
        if learned_summary:
            blocks.append(f"[LEARNED STYLE] {learned_summary}")

        if planner_tone or planner_goal:
            blocks.append("[PLANNER 3.5 — TURN INTENT]")
            if planner_tone:
                blocks.append(f"Tone: {planner_tone}.")
            if planner_goal:
                blocks.append(f"Goal: {planner_goal}.")
        if quoted_context:
            blocks.append("[MENSAGEM CITADA] " + quoted_context)
        if web_context:
            blocks.append("[CONTEXTO WEB — conferir origem/validade] " + web_context)
        if vision_context:
            blocks.append("[CONTEXTO VISUAL] " + vision_context)

        if True:
            from knowledge_privacy import KnowledgePrivacy

            blocks.append('[KNOWLEDGE POLICY] The user message may contain guesses or quoted claims. '
                          'Neither is permission to confirm another person\'s private information. '
                          'Only a trusted, explicit share may update known_by.')
            policy = KnowledgePrivacy(self.db)
            if privacy_subjects and len(privacy_subjects) > 1:
                raise ValueError('One trusted privacy subject per prompt is supported')
            for subject_type, subject_id in (privacy_subjects or []):
                blocks.append(policy.prompt_constraint(subject_type, subject_id))

        # Memória autobiográfica e fatos consolidados da relação com Patrick.
        # Quando um sujeito confidencial de terceiros estiver em consulta, o retriever permanece isolado.
        if self.retriever and not privacy_subjects:
            recalled = self.retriever.retrieve_context(
                user_message=user_message, max_facts=3, max_moments=2, max_summaries=1,
            )
            memory_lines = [*recalled.get("fatos", []), *recalled.get("momentos", []),
                            *recalled.get("resumos", [])]
            if memory_lines:
                blocks.append("[MEMÓRIA — continuidade e fatos relevantes]")
                blocks.extend(f"- {line}" for line in memory_lines)
        return "\n".join(blocks)

    def _energy(self) -> float:
        emotional = self.db.get_estado_emocional()
        return max(0.0, min(1.0, float(emotional.get("energy", {}).get("valor", 0.7))))

    def _emotional_context(self) -> list[str]:
        emotional = self.db.get_estado_emocional()
        multipliers = {}
        if self.cycle_mgr and hasattr(self.cycle_mgr, 'get_emotional_multipliers'):
            multipliers = self.cycle_mgr.get_emotional_multipliers() or {}
        labels = {
            'affection': 'carinho e afeto',
            'energy': 'energia e disposição',
            'romantic_intensity': 'paixão e intensidade romântica',
            'social_battery': 'bateria social para conversar',
        }
        lines = []
        for key, data in emotional.items():
            if not isinstance(data, dict):
                continue
            value = max(0.0, min(1.0, float(data.get('valor', 0.7)) * float(multipliers.get(key, 1.0))))
            if value >= 0.85:
                level = 'muito alto / intenso'
            elif value >= 0.65:
                level = 'alto'
            elif value >= 0.40:
                level = 'moderado / equilibrado'
            elif value >= 0.20:
                level = 'baixo'
            else:
                level = 'muito sutil'
            lines.append(f"- {labels.get(key, key)}: {level}")
        return lines

    def _social_context(self, message: str) -> list[str]:
        import re
        from social_world import SocialWorld
        words = set(re.findall(r'\w+', message.casefold()))
        result = []
        for person in SocialWorld(self.db).graph():
            aliases = set(re.findall(r'\w+', person['display_name'].casefold()))
            if person['canon_locked'] and words & aliases:
                result.append(f"{person['display_name']}: {person['relationship_type']}; região: {person['home_region'] or 'não definida'}.")
        return result[:3]

    def _location_name(self, place_id: Optional[int]) -> Optional[str]:
        if place_id is None:
            return None
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT name FROM world_places WHERE id = ?", (place_id,)).fetchone()
            return row["name"] if row else None

    def _compact_preferences(self) -> list[str]:
        with self.db.get_connection() as conn:
            return [row["value"] for row in conn.execute(
                """SELECT value FROM character_preferences
                   WHERE character_key = 'marina' AND preference_type = 'core_like'
                     AND canon_locked = 1 AND active = 1
                   ORDER BY category, id LIMIT 10"""
            )]

    def _clean_start_done(self) -> bool:
        return is_canonical_runtime_ready(self.db)

