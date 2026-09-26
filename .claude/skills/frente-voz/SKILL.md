---
name: frente-voz
description: Frente "voz e chat" da Marina — como ela fala e responde no Telegram (balões, ritmo, ponto final, naturalidade, prompt, biblioteca de falas, proatividade/iniciativas, fotos e promessas de foto, sexting, áudio). Use quando o Patrick mandar print de conversa, reclamar de uma fala, pedir revisão de prompt ou falar de mensagens dela.
---

# Frente: voz e chat

## Regras do Patrick
- O que quebra a imersão: repetição, ponto final, ela só reagir, responder no meio, notificação de sistema no chat.
- Falas que ele sugerir podem virar Registros na biblioteca (`data/feedback/BIBLIOTECA_COMPORTAMENTAL_MARINA.md`),
  mas **nunca commitar `data/feedback/*`** — são edições dele.
- Valor de foto já aprovado se corrige por prompt, sem gastar Buzz re-testando. Nunca mostrar imagem adulta no chat.

## Comece assim
1. Leia "3. Voz e chat" em `FRENTES_MARINA.md` e o painel de pendências do `PLANO_VOZ_MARINA_V371.md`.
2. Se ele trouxer um caso real: puxe a conversa e o log da hora na VPS antes de opinar
   (`sqlite3 marin_memory.db "SELECT … FROM conversas"`, `journalctl -u marina --since …` — journal em UTC).

## Onde fica
- Envio: `bot.send_human_messages` (balões; trava por chat — uma sequência por vez), `response_rhythm.segment`.
- Iniciativas: `proactivity_service.should_trigger` (saudade, tesão, convite de sexting…), `bot.autonomous_routine_v36`
  (trava `INITIATIVE_LOCK`; desiste se outra iniciativa saiu há < 10 min), instruções em `_PROACTIVE_INSTRUCTIONS`.
- Prompt: `prompt_policy.py`, `world_context.py` (blocos do mundo), `voice_library.py`, `chat_naturalness.py`.
- Disponibilidade (quanto ela demora pra responder): `response_availability.py`.
- Fotos: `photo_director.py`, `promessa_foto.py`, `civitai_images.py` (custa Buzz — só com motivo).
- Fechar: relatórios no mesmo commit (AUDITORIA + PLANO_VOZ + PLANO_WEBAPP), deploy, `passagem-de-bastao`.
