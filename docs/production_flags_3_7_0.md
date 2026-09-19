# Runtime de produção — Marina 3.7.0

A matriz histórica de release flags foi aposentada durante a migração para o runtime canônico de 19/09/2026.

Os sistemas aprovados até 3.7.0 agora formam um único caminho de produção e não dependem do `.env`: World Bible, WorldState, Memory Intelligence, Planner, Open Loops, Smart Reminders, Knowledge/Privacy, Calendar/Academic, Relationship World, Camera World, Response Rhythm e Response Availability com latência e batching.

A configuração atual mantém somente:

- kill switches que pausam jobs ou geração sem restaurar código antigo;
- seleção e disponibilidade de providers externos;
- tuning numérico;
- telemetria e debug;
- a política explícita de despertar durante o sono.

A classificação completa está em [`canonical_runtime_flags.md`](canonical_runtime_flags.md).

`/edit`, `/rollback`, `/patches`, `SAFE_PATCHER_ENABLED` e o AutoPatcher foram removidos do runtime. A migration/tabela histórica permanece inerte para compatibilidade do banco.

Durante o soak, `PHOTO_PROVIDER_MAINTENANCE=true` continua autorizado: pedidos de foto recebem uma resposta dinâmica e não iniciam a GPU.
