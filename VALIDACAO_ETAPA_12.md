# Release 3.6.5 · etapa 12 — validação concluída

O Gemini concluiu a validação externa em 18/09/2026: **291 testes, 0 falhas,
0 pulos** (`data/relationship_proactivity_validation.v365.json`). O Codex
revisou o relatório e as alterações de integração sem repetir a suíte, conforme
o combinado. Para reproduzir no Antigravity, na raiz do repositório:

```powershell
& .\venv\Scripts\python.exe scripts\run_external_stage12_validation.py
```

O relatório é escrito em `data/relationship_proactivity_validation.v365.json`.
O Gemini também ajustou a migration 014 para o replay de bootstrap, incluiu as
novas tabelas na limpeza canônica e atualizou as expectativas de schema 14.

Verificações centrais:

- migração 014 e cultura do casal exigem mensagem recebida, frase literal e
  reforço em conversas distintas antes de aparecer no contexto;
- ranking prioriza follow-up confirmado, open loop, evento compartilhável,
  assunto já compartilhado e carinho leve, preservando sono, cooldown e limite;
- evento só vira candidato se Marina o conhece, a política permite detalhes
  espontâneos e Patrick ainda não recebeu os detalhes; metadados seguros já
  compartilhados não revelam o título no histórico;
- falha de envio não toca open loop, não conclui follow-up e não cria
  `knowledge_share`; sucesso confirmado registra o ID do Telegram;
- a proatividade Living World não inventa evento cotidiano e não interrompe
  compromisso atual do calendário.

Ativação futura: `RELATIONSHIP_WORLD_ENABLED=true` exige
`LIVING_WORLD_ENABLED=true` e `KNOWLEDGE_PRIVACY_ENABLED=true`. A flag continua
desligada por padrão até ativação explícita do runtime.
