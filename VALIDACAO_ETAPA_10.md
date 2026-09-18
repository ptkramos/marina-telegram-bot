# Release 3.6.3 · etapa 10 — handoff de validação

O Gemini validou a primeira implementação em 18/09/2026: **251 testes, 0 falhas, 0 pulos** (`data/knowledge_privacy_validation.v363.json`). A primeira rodada da integração encontrou duas expectativas antigas de schema 10; ambas foram atualizadas para 11. A segunda rodada encontrou um teste legado intermitente: áudio espontâneo aleatório desviou um caso que verificava exclusivamente texto. Esse teste agora fixa o sorteio no caminho de texto. A integração aguarda nova repetição externa. Para o Gemini no Antigravity, na raiz do repositório:

```powershell
& .\venv\Scripts\python.exe scripts\run_external_stage10_validation.py
```

O comando executa a suíte inteira com SQLite descartável e grava `data/knowledge_privacy_validation.v363_integration.json`. Envie ou deixe esse arquivo no workspace para revisão do resultado; não é necessário que o Codex repita a suíte.

Os contratos cobrem: segredo da Bia não confirmado por palpite, metadados seguros sem detalhe, permissão concedida/revogada, cadeia Theo → Bia → Marina apenas após cada compartilhamento, NPC sem conhecimento implícito, replay idempotente, bloqueio de memória/histórico legado não classificados, resolução de IDs cadastrados sem inferência da LLM, colisão de aliases, assuntos com permissões diferentes e falha de envio sem compartilhamento fantasma.

`KNOWLEDGE_PRIVACY_ENABLED` continua `false` por padrão. Assuntos cadastrados em `knowledge_subjects` são resolvidos por frases revisadas em `knowledge_subject_aliases`; aliases ambíguos não produzem vínculo. Para `event`/`thread`, `subject_id` é o ID real de `life_events`/`story_threads`; para `fact`/`relationship`, é o ID do registro do assunto. Para esses assuntos, o bot monta uma resposta por sujeito com decisão de privacidade própria, sem usar a LLM, e persiste `knowledge_shares` somente após `send_message` retornar um `message_id`. Assuntos ainda não cadastrados seguem o fluxo geral sem acesso a retrieval/histórico legado quando a flag está ligada. Reintroduzir memórias classificadas fica para uma etapa posterior.

O bootstrap limpo cadastra de modo idempotente dois assuntos já canônicos, Milo e o namoro de Marina e Patrick. Para um banco v3.6 já inicializado antes dessa migração, o seed também pode ser aplicado explicitamente com `& .\venv\Scripts\python.exe seed_knowledge_v363.py --db CAMINHO_DO_BANCO`, depois de conferir o caminho e com o bot parado. Não cadastre aliases ou detalhes a partir de saída da LLM.
