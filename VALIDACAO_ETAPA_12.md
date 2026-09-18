# Release 3.6.5 · etapa 12 — handoff de validação

O código da integração Relationship & Proactivity está pronto para validação
externa. O Codex **não executou a suíte**, conforme o combinado com o usuário.
No Antigravity, na raiz do repositório:

```powershell
& .\venv\Scripts\python.exe scripts\run_external_stage12_validation.py
```

O relatório será escrito em `data/relationship_proactivity_validation.v365.json`.
Enviar o resultado ao Codex para revisão antes de considerar a release concluída.

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
`LIVING_WORLD_ENABLED=true` e `KNOWLEDGE_PRIVACY_ENABLED=true`. A flag começa
desligada e deve permanecer assim até validação do resultado externo.
