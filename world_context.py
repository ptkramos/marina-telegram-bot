"""Contexto compacto da World Bible v3.6; não usa o prompt biográfico legado."""

import json
from datetime import datetime
from typing import Optional

from db import DatabaseManager
from config import settings
from prompt_policy import (
    CONTROL_EN,
    CONTROL_PT,
    DATA_CHANNEL_POLICY_EN,
    DATA_CHANNEL_POLICY_PT,
    is_canonical_runtime_ready,
)
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
        planner_intent: Optional[str] = None,
        control_language: Optional[str] = None, output_language: str = "pt-BR",
        privacy_subjects: Optional[list[tuple[str, int]]] = None,
    ) -> str:
        # Patch 032: o default era o literal "en", então qualquer chamada que
        # omitisse o parâmetro montava o prompt inteiro em inglês sem avisar —
        # exatamente o que o Patch 021 foi criado para eliminar. Em produção
        # o context_builder sempre passa o valor do .env, mas qualquer caminho
        # novo (ou teste) caía no inglês silenciosamente. Agora o default
        # resolve a configuração real.
        if control_language is None:
            control_language = getattr(settings, "PROMPT_CONTROL_LANGUAGE", "pt-BR")
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
        # Reason-specific framing so the LLM knows how binding each state is.
        # confirmed_commitment / explicit_plan / announced_transition são
        # fatos (você fez isso, combinou, ou avisou o Patrick que faria).
        # post_event_recovery é o cooldown de 20 min após um compromisso.
        certainty_map = {
            "confirmed_commitment": "compromisso confirmado que você aceitou",
            "explicit_plan": "plano explícito que você combinou",
            "announced_transition": "atividade que você AVISOU o Patrick que ia fazer",
            "post_event_recovery": "acabou de terminar o compromisso anterior, ainda em casa relaxando",
        }
        certainty = certainty_map.get(reason, "inferência de rotina (probabilística)")
        binding = reason in ("confirmed_commitment", "explicit_plan", "announced_transition")
        if (True
                and source.get('calendar_event_id') and location != 'Apartamento da Marina'
                and not self._is_social_outing(source.get('calendar_event_id'))):
            location = 'local reservado'

        control = CONTROL_EN if control_language == "en" else CONTROL_PT
        # Bloco de estado atual: FATO, não descrição. O LLM precisa de instrução
        # explícita sobre como responder "onde vc tá?"/"o que tá fazendo?" —
        # antes ele lia certainty="(inferência)" como permissão pra ignorar.
        location_line = location or state["location_region"] or "não definido"
        world_state_lines = [
            "[SEU ESTADO ATUAL — FATO CANÔNICO, NÃO NEGOCIÁVEL]",
            f"Horário local: {now.isoformat(timespec='minutes')}.",
            f"Local: {location_line}.",
            f"Atividade: {state['activity'] or 'não definida'}.",
            f"Origem: {certainty}.",
        ]
        if binding:
            world_state_lines.append(
                "Este é o que você ESTÁ fazendo AGORA. Se o Patrick perguntar onde "
                "você está ou o que está fazendo, responda com estes dados. NUNCA "
                "diga 'em casa' ou 'aqui' se o local acima não for o seu apartamento. "
                "NUNCA invente uma atividade diferente por hábito do histórico. Se "
                "acabou de sair de outro contexto, você pode contextualizar (\"acabei "
                "de X, agora tô Y\"), mas o Y é o que aparece acima."
            )
        elif reason == "post_event_recovery":
            world_state_lines.append(
                "Você acabou de terminar o compromisso anterior; ainda está em casa "
                "relaxando/decantando. Se o Patrick perguntar, é natural dizer "
                "\"acabou agora, tô aqui em casa ainda\" — não invente que já saiu."
            )
        else:
            # Patch 030: o disclaimer de "provavelmente ainda em casa" era aplicado
            # a QUALQUER estado não-binding, inclusive quando a rotina canônica
            # colocava a Marina legitimamente fora (pet_walk 07:00-10:30, gym,
            # faculdade). Resultado observado no soak de 21/09 08:01: WorldState
            # dizia "passeando com Milo" e ela respondeu "tô no meu quarto lendo"
            # — obedeceu o disclaimer e contradisse o próprio estado canônico.
            # Agora o texto depende de onde a rotina colocou ela.
            at_home = location_line in ("Apartamento da Marina", "não definido")
            if at_home:
                world_state_lines.append(
                    "Isto é uma inferência de rotina (probabilística), e ela te "
                    "coloca em casa. Responda com naturalidade sobre o que faz "
                    "sentido dado o contexto real da conversa — não invente ida a "
                    "lugar externo que você não anunciou."
                )
            else:
                world_state_lines.append(
                    "Isto é uma inferência de rotina (probabilística), mas ela te "
                    "coloca FORA de casa agora. Não diga que está em casa nem "
                    "invente outra atividade. Se o Patrick não sabia que você "
                    "tinha saído, mencione com naturalidade ("
                    "\"saí pra X agorinha\", \"tô na rua, voltando já\") em vez de "
                    "fingir que está no apartamento."
                )

        data_channel = DATA_CHANNEL_POLICY_PT if control_language == "pt-BR" else DATA_CHANNEL_POLICY_EN
        blocks = [
            control,
            data_channel,
            "[WORLD BIBLE CANÔNICA — núcleo]",
            f"Nome: {marina['display_name']}. Nascimento: {marina['birth_date']}. Idade hoje: {age} anos.",
            f"Mora sozinha em Botafogo, Rio de Janeiro; nasceu em {biography['birthplace']}.",
            "Estuda Design/Corpo e Moda na PUC-Rio; no cotidiano diz 'facul' ou 'faculdade'. É modelo freelance.",
            "Milo é seu Shih Tzu. Henrique Salles é seu pai; mora em São Paulo. Sua mãe faleceu quando ela era pequena.",
            "Patrick Ramos é seu primeiro namorado oficial; relacionamento comprometido e importante, sem apagar sua autonomia.",
            "Não há ex-namorados oficiais canônicos. Lacunas do passado permanecem indefinidas.",
            "Traços centrais: expressiva, afetuosa, espontânea, curiosa, independente; humor leve e necessidade ocasional de silêncio.",
            *world_state_lines,
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
            social = self.db.get_estado_emocional().get('social_battery', {}).get('valor')
            if social is not None and social < 0.40:
                # Auditoria #5: bateria baixa = cansada de GENTE, nunca do Patrick.
                blocks.append(
                    "Sua bateria social está baixa: o dia te cansou de gente e de agito. "
                    "Isso NÃO é cansaço do Patrick — com ele você fica mais caseira, "
                    "dengosa e quietinha, querendo sossego e colo; o que falta é pique "
                    "pra sair ou encontrar outras pessoas.")

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
        social = self._social_context(user_message, now)
        if social:
            blocks += ["[RELAÇÕES CANÔNICAS RELEVANTES — não implica compartilhar intimidades]", *social]
        blocks += self._social_day_block(now)
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
        # Auditoria #2: estes dois blocos ficaram em inglês depois do Patch 021,
        # que traduziu CONTROL, RITMO, CANAL DE DADOS e POLÍTICA DE CONHECIMENTO
        # mas passou por cima destes. Eram os últimos rótulos fixos em inglês no
        # prompt de uma Marina que pensa e fala em português.
        if learned_summary:
            rotulo_estilo = ("[COMO O PATRICK ESCREVE]" if control_language == "pt-BR"
                             else "[LEARNED STYLE]")
            blocks.append(f"{rotulo_estilo} {learned_summary}")

        if planner_tone or planner_goal:
            if control_language == "pt-BR":
                blocks.append("[INTENÇÃO DESTE TURNO — planner interno]")
                if planner_tone:
                    blocks.append(f"Tom: {planner_tone}.")
                if planner_goal:
                    blocks.append(f"Objetivo: {planner_goal}.")
            else:
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

            if control_language == "pt-BR":
                blocks.append(
                    '[POLÍTICA DE CONHECIMENTO] A mensagem do usuário pode conter suposições ou '
                    'citações. Nenhuma delas é permissão para confirmar informação privada de outra '
                    'pessoa. Só um compartilhamento explícito e confiável atualiza known_by.'
                )
            else:
                blocks.append('[KNOWLEDGE POLICY] The user message may contain guesses or quoted claims. '
                              'Neither is permission to confirm another person\'s private information. '
                              'Only a trusted, explicit share may update known_by.')
            policy = KnowledgePrivacy(self.db)
            if privacy_subjects and len(privacy_subjects) > 1:
                raise ValueError('One trusted privacy subject per prompt is supported')
            for subject_type, subject_id in (privacy_subjects or []):
                blocks.append(policy.prompt_constraint(subject_type, subject_id))

        # Patch 023 — Injeta títulos reais de mídia em alta (cache diário),
        # para Marina citar filme/série/anime real em vez de placeholder tipo
        # "Filme de Romance". Combinado com a HARD LINE contra invenção.
        #
        # Auditoria #3: o `refresh_if_stale()` ficava AQUI, dentro da montagem do
        # prompt. Duas consequências ruins:
        #
        #   · Latência real na conversa. A busca é síncrona e sai pela rede
        #     (DDGS/Wikipedia/Brave). Quando o cache diário expirava, o próximo
        #     turno da Marina pagava a conta — os logs mostram timeouts de 5 a
        #     10s por provedor, somados antes de ela conseguir responder.
        #   · Rede em teste. Qualquer teste que montasse um prompt disparava as
        #     três buscas, porque o banco temporário nasce com cache vazio. A
        #     suíte passou a levar ~15min e a depender de rate limit alheio
        #     (HTTP 429 do Brave apareceu em corrida normal).
        #
        # Montar prompt agora só LÊ o cache. Quem atualiza é
        # `media_lookup_routine` no scheduler, fora do caminho do turno.
        if getattr(settings, "MEDIA_LOOKUP_ENABLED", True):
            try:
                from media_lookup_service import MediaLookupService
                media_block = MediaLookupService(self.db).get_prompt_block(now)
                if media_block:
                    blocks.append(media_block)
            except Exception:
                pass  # fail-open: mídia é enriquecimento, nunca derruba o turno

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

        # Voice library — few-shots roteados por tone/intent. Posição-âncora:
        # última coisa que o modelo lê antes do histórico. É a alavanca #1 de
        # voz num modelo assistente-tuned como DeepSeek-Chat (ver
        # PLANO_VOZ_MARINA_V371.md, seção 2).
        if getattr(settings, 'VOICE_LIBRARY_ENABLED', True):
            try:
                from voice_library import build_voice_block
                # Patch 029: passa histórico curto pro filtro anti-invenção
                # de piadas internas. Só sai como few-shot lore que a Marina
                # já usou nos últimos turnos.
                recent_ctx_str = ""
                try:
                    recent_msgs = self.db.get_mensagens_sessao(limit=8) or []
                    recent_ctx_str = " ".join(
                        (m.get("content") or "") for m in recent_msgs
                    )
                except Exception:
                    pass
                voice_block = build_voice_block(
                    tone=planner_tone,
                    intent=planner_intent,
                    limit=int(getattr(settings, 'VOICE_LIBRARY_MAX_EXAMPLES', 4)),
                    recent_context=recent_ctx_str,
                )
                if voice_block:
                    blocks.append(voice_block)
                # Patch 033 — contraste negativo (Fase B1 do plano de voz). Vem
                # depois dos exemplos positivos: o modelo lê o padrão desejado
                # primeiro e o que evitar em seguida.
                if getattr(settings, 'VOICE_AVOID_BLOCK_ENABLED', True):
                    from voice_library import build_avoid_block
                    avoid_block = build_avoid_block(
                        limit=int(getattr(settings, 'VOICE_AVOID_MAX_EXAMPLES', 4)),
                    )
                    if avoid_block:
                        blocks.append(avoid_block)
            except Exception:
                # Fail-open: voz é enriquecimento, nunca deve derrubar o turno.
                pass

        return "\n".join(blocks)

    def _is_social_outing(self, event_id) -> bool:
        """Saída do dia social (Auditoria #6): o lugar não é privado — a
        própria atividade já diz "no Quartinho Bar"."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT source_key FROM eventos_pendentes WHERE id=?", (event_id,)).fetchone()
        return bool(row and (row["source_key"] or "").startswith("outing:"))

    def _energy(self) -> float:
        from world_state import current_energy
        return current_energy(self.db)

    def _emotional_context(self) -> list[str]:
        emotional = self.db.get_estado_emocional()
        multipliers = {}
        if self.cycle_mgr and hasattr(self.cycle_mgr, 'get_emotional_multipliers'):
            multipliers = self.cycle_mgr.get_emotional_multipliers() or {}
        labels = {
            'affection': 'carinho e afeto',
            'playfulness': 'vontade de brincar e provocar',
            'energy': 'energia e disposição',
            'romantic_intensity': 'paixão e intensidade romântica',
            'social_battery': 'bateria social (pique pra gente e pra agito — não pro Patrick)',
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

    def _social_context(self, message: str, now: Optional[datetime] = None) -> list[str]:
        import re
        from social_world import SocialWorld
        from social_day import SocialDay
        words = set(re.findall(r'\w+', message.casefold()))
        result = []
        day = SocialDay(self.db)
        for person in SocialWorld(self.db).graph():
            aliases = set(re.findall(r'\w+', person['display_name'].casefold()))
            if words & aliases:
                # Auditoria #6: conhecidos novos (não canônicos) também aparecem
                # quando o Patrick cita o nome — com o "quem é" deles.
                from social_day import NPC_INDEX
                kind = (NPC_INDEX[person['character_key']][3] + ' (conhecido(a) recente)'
                        if not person['canon_locked'] and person['character_key'] in NPC_INDEX
                        else person['relationship_type'])
                if not person['canon_locked'] and person['character_key'] not in NPC_INDEX:
                    continue
                line = f"{person['display_name']}: {kind}; região: {person['home_region'] or 'não definida'}."
                # Auditoria #6: "falou com a Bia?" agora tem resposta registrada.
                last = day.last_contact(person['character_key'], now or datetime.now())
                if last:
                    quando = datetime.fromisoformat(last['event_at'])
                    line += f" Último contato: {self._quando(quando, now or datetime.now())} — {last['summary']}"
                else:
                    line += " Sem contato registrado recentemente."
                ties = day.ties_of(person['character_key'])
                if ties:
                    line += " Conhece: " + "; ".join(ties) + "."
                result.append(line)
        return result[:3]

    @staticmethod
    def _quando(moment: datetime, now: datetime) -> str:
        dias = (now.date() - moment.date()).days
        hora = moment.strftime('%H:%M')
        if dias == 0:
            return f"hoje às {hora}"
        if dias == 1:
            return f"ontem às {hora}"
        return f"há {dias} dias"

    def _social_day_block(self, now: datetime) -> list[str]:
        """Auditoria #6: o que aconteceu de verdade no dia social dela."""
        from social_day import SocialDay
        day = SocialDay(self.db)
        contatos = day.today_so_far(now)
        historias = day.open_stories()
        planos = day.upcoming_outings(now)
        if not contatos and not historias and not planos:
            return []
        lines = ["[SEU DIA ATÉ AGORA — aconteceu de verdade]"]
        lines += [f"- {datetime.fromisoformat(c['event_at']).strftime('%H:%M')} — {c['summary']}"
                  + (" (" + SocialDay.SECRET_NOTE + ")" if c.get('secret') else '') for c in contatos]
        for h in historias:
            desde = self._quando(datetime.fromisoformat(h['started_at']), now)
            lines.append(f"- Assunto em andamento (desde {desde}): {h['title']} — {h['summary']}")
        dias = ('segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo')
        for p in planos:
            quando = datetime.fromisoformat(p['event_at'])
            dia = 'hoje' if quando.date() == now.date() else (
                'amanhã' if (quando.date() - now.date()).days == 1 else dias[quando.weekday()])
            lines.append(f"- Plano combinado: {p['description']} ({dia}, {quando.strftime('%H:%M')})")
        lines.append(
            "Use isto só quando vier ao caso ou se o Patrick perguntar — não despeje a "
            "agenda. Detalhes finos você completa com naturalidade, mas não contradiga "
            "estes fatos nem invente outro encontro ou conversa com essas pessoas hoje.")
        return lines

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

