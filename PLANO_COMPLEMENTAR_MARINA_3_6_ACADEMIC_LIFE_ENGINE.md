# PLANO COMPLEMENTAR — MARINA 3.6
## Academic Life Engine — Grade Semestral, Progressão Acadêmica e Continuidade até a Formatura

**Status:** proposta complementar ao `PLANO_MARINA_V3_6_LIVING_WORLD.md`  
**Objetivo:** definir como a vida universitária da Marina deve funcionar dentro do Living World sem transformar a rotina em agenda rígida, sem criar um segundo calendário e sem exigir definição manual de cada semestre futuro.

---

# 1. PRINCÍPIO

A World Bible já define que Marina:
- cursa graduação presencial na PUC-Rio, Gávea;
- está em Design, com foco em Corpo e Moda;
- entrou aproximadamente em 2025.1;
- possui rotina universitária principalmente pela manhã/início da tarde.

O Living World também já estabelece:

> Routine is probabilistic. Calendar commitments are authoritative.

Portanto a vida acadêmica deve possuir duas camadas:

```text
CURRÍCULO / PROGRESSÃO
→ o que Marina já cursou, está cursando e ainda precisa cursar

GRADE DO SEMESTRE
→ em quais dias e blocos de horário existem compromissos acadêmicos atuais
```

Uma aula confirmada é um compromisso acadêmico daquele semestre e vence escolhas probabilísticas incompatíveis do Routine Engine. Ao mesmo tempo, a grade não deve virar uma prisão narrativa: aula pode ser cancelada, terminar cedo, ser substituída por atividade externa, sofrer impacto de feriado, prova, apresentação etc.

---

# 2. OBJETIVO DE EXPERIÊNCIA

O sistema deve permitir que Patrick perceba naturalmente que Marina:
- sabe quais dias costuma ter faculdade;
- não aparece em locais incompatíveis durante aula sem explicação;
- organiza academia, casting, praia, jobs e encontros em torno da faculdade;
- passa por fases acadêmicas diferentes;
- tem trabalhos, apresentações, entregas e semanas mais leves/pesadas;
- entra em férias;
- inicia novos períodos;
- muda de grade de um semestre para outro;
- avança organicamente até a conclusão do curso.

O usuário não deve precisar criar manualmente cada novo semestre.

```text
grade inicial canônica bem definida
        ↓
Academic Life Engine
        ↓
progressão persistente
        ↓
novos semestres coerentes
        ↓
formatura futura quando academicamente plausível
```

---

# 3. NÃO CRIAR SEGUNDO CALENDÁRIO

REGRA CRÍTICA:

> The Academic Life Engine must not create a parallel calendar system.

O sistema acadêmico deve informar compromissos para a mesma camada de eventos/calendário utilizada pelo Living World.

```text
AcademicSchedule
terça 09:00–12:00
        ↓
Calendar/Event projection
        ↓
WorldState
        ↓
current activity/location
```

Não criar três fontes concorrentes como `academic_current_activity`, `calendar_current_activity` e `routine_current_activity`.

Prioridade conceitual:

```text
confirmed exceptional event
> academic exception/event
> fixed academic schedule block
> explicit recent plan
> active thread consequence
> routine probability
> free-time fallback
```

---

# 4. QUANDO INTEGRAR NA V3.6

O agente deve decidir o ponto exato conforme o estado real da implementação.

## Se v3.6.0 ainda estiver com migrations/schema em aberto

Adicionar apenas:
- tabelas acadêmicas;
- repository;
- seed canônico do estado acadêmico;
- feature flag;
- nenhum gerador complexo ainda.

Implementar o comportamento completo em:

```text
v3.6.4 — Real World Context & Calendar Continuity
```

Esse é o encaixe natural porque a 3.6.4 já trata:
- calendário;
- eventos;
- passagem do tempo;
- semestre/fases;
- continuidade temporal;
- lazy catch-up.

## Se v3.6.0 já estiver fechada

Não reabrir arquitetura estável só para encaixar este módulo.

Criar migration incremental na 3.6.4 e implementar nela.

## Não ativar antes de existirem

- WorldState funcional;
- fonte única de eventos/calendário;
- resolução de compromissos vs rotina;
- passagem temporal confiável;
- timezone/data consistentes.

---

# 5. FEATURE FLAGS

```env
ACADEMIC_LIFE_ENABLED=true
ACADEMIC_AUTO_TERM_GENERATION=true
```

Com a flag principal desligada, preservar a rotina universitária genérica já existente sem quebrar WorldState.

---

# 6. ESTADO ACADÊMICO CANÔNICO INICIAL

No bootstrap limpo da v3.6:

```json
{
  "institution": "PUC-Rio",
  "campus_area": "Gávea",
  "program": "Design",
  "focus": "Corpo e Moda",
  "entry_term": "2025.1",
  "current_term": "2026.2",
  "status": "active"
}
```

Não inventar automaticamente:
- CRA/notas exatas;
- histórico detalhado de todas as disciplinas anteriores;
- reprovações;
- trancamentos;
- bolsas;
- sala/professor de cada disciplina passada;
- data exata de formatura.

O passado anterior a 2026.2 pode permanecer resumido como progressão normal.

---

# 7. PRIMEIRA GRADE: 2026.2

A primeira grade deve ser definida manualmente e tratada como CANONICAL.

Ela serve como:
1. ponto inicial confiável;
2. benchmark de densidade semanal;
3. referência para geração futura;
4. teste de integração com WorldState.

Diretriz:

```text
3–4 dias presenciais/semana
4–6 componentes
predominância manhã/início da tarde
1–2 blocos longos de projeto/ateliê
espaço suficiente para freela/castings/modelagem
```

Blocos plausíveis:

```text
08:00–10:00
10:00–12:00
13:00–15:00
13:00–17:00
```

Este documento não fixa ainda os nomes definitivos das disciplinas. O seed da grade deve ser definido depois que o agente decidir se serão usados nomes ficcionais plausíveis, nomes realistas validados ou abordagem híbrida.

---

# 8. MODELO DE DADOS SUGERIDO

## `academic_profile`

```sql
CREATE TABLE academic_profile (
    character_key TEXT PRIMARY KEY,
    institution TEXT NOT NULL,
    campus_area TEXT,
    program_name TEXT NOT NULL,
    focus_name TEXT,
    entry_term TEXT,
    current_term TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    graduation_status TEXT NOT NULL DEFAULT 'in_progress',
    metadata_json TEXT
);
```

## `academic_terms`

```sql
CREATE TABLE academic_terms (
    id INTEGER PRIMARY KEY,
    character_key TEXT NOT NULL,
    term_key TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    status TEXT NOT NULL,
    generated_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    metadata_json TEXT,
    UNIQUE(character_key, term_key)
);
```

`generated_by`:
```text
CANONICAL_SEED
ACADEMIC_ENGINE
USER_DEFINED
```

`status`:
```text
PLANNED
ACTIVE
COMPLETED
VACATION
CANCELLED
```

## `academic_courses`

```sql
CREATE TABLE academic_courses (
    id INTEGER PRIMARY KEY,
    academic_term_id INTEGER NOT NULL,
    course_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    course_type TEXT NOT NULL,
    area TEXT,
    workload_weight REAL NOT NULL DEFAULT 1.0,
    status TEXT NOT NULL DEFAULT 'ENROLLED',
    prerequisite_keys_json TEXT,
    metadata_json TEXT,
    UNIQUE(academic_term_id, course_key)
);
```

Tipos:
```text
THEORY
STUDIO
PROJECT
LAB
ELECTIVE
SEMINAR
```

Status:
```text
ENROLLED
COMPLETED
DROPPED
FAILED
```

`FAILED` e `DROPPED` não podem aparecer por sorteio banal.

## `academic_schedule_blocks`

```sql
CREATE TABLE academic_schedule_blocks (
    id INTEGER PRIMARY KEY,
    academic_course_id INTEGER NOT NULL,
    weekday INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    location_key TEXT NOT NULL DEFAULT 'puc_rio_gavea',
    block_type TEXT NOT NULL DEFAULT 'CLASS',
    active INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT
);
```

---

# 9. NÃO DUPLICAR CADA AULA COMO EVENTO FUTURO

A grade semanal deve ser armazenada como pattern acadêmico.

Preferir:

```text
academic_schedule_block
+
current date
+
active term
=
today's academic commitment
```

Eventos extraordinários entram na camada normal de eventos:

```text
EXAM
PRESENTATION
DEADLINE
GROUP_WORK
FIELD_VISIT
WORKSHOP
CLASS_CANCELLED
CLASS_RESCHEDULED
```

---

# 10. EXCEÇÕES

Uma exceção modifica apenas aquela ocorrência.

Exemplo:

```text
quarta 13:00–17:00 = ateliê
evento = aula cancelada nesta quarta
resultado = bloco fica livre e Routine Engine pode preenchê-lo
```

Não alterar a grade-base permanentemente.

---

# 11. SEMESTER PHASE ENGINE

Fases:

```text
TERM_START
NORMAL
DELIVERY_PERIOD
EXAM_PERIOD
TERM_END
VACATION
REGISTRATION
```

Elas mudam probabilidades e contexto, não forçam cenas.

### TERM_START
- adaptação;
- novas disciplinas;
- novos trabalhos.

### NORMAL
- maioria do semestre.

### DELIVERY_PERIOD
- projetos;
- grupo;
- impressão/material;
- mais trabalho;
- ocasionalmente dormir mais tarde.

### EXAM_PERIOD
Design pode privilegiar apresentação, banca, entrega, projeto e portfólio, sem assumir prova escrita para tudo.

### VACATION
Grade deixa de restringir rotina.

### REGISTRATION
Próximo semestre é montado.

---

# 12. PROGRESSÃO ENTRE SEMESTRES

```text
ACTIVE TERM
    ↓
term end
    ↓
resolver eventos pendentes
    ↓
ENROLLED → COMPLETED por padrão
    ↓
atualizar progresso
    ↓
VACATION
    ↓
REGISTRATION
    ↓
gerar próximo termo
    ↓
validar
    ↓
ativar na data correta
```

A geração deve ser idempotente. Rodar catch-up duas vezes não pode criar dois `2027.1`.

---

# 13. GERAÇÃO AUTOMÁTICA

Depois de 2026.2, futuros termos podem ser gerados automaticamente.

Não usar LLM livre como autoridade.

Preferir:

```text
deterministic constraints
+
controlled templates/catalog
+
seeded weighted variation
```

Considerar:
- período atual;
- componentes concluídos;
- pré-requisitos;
- carga semanal;
- máximo razoável de dias presenciais;
- conflitos;
- tipos de disciplina;
- espaço para freelas;
- férias/calendário.

---

# 14. VARIAÇÃO ENTRE SEMESTRES

Evitar repetir eternamente os mesmos dias.

Exemplo aceitável:

```text
2026.2 → ter/qua/qui/sex
2027.1 → seg/ter/qui
2027.2 → ter/qua/sex
```

Com limites:
- não ocupar 6 dias normalmente;
- não criar carga matinal absurda;
- não inviabilizar modelagem/freelas;
- não concentrar horários irreais.

---

# 15. VIDA FORA DA FACULDADE

Academic commitments são âncoras fortes, não a vida inteira.

Preservar:
- modelagem;
- castings;
- academia;
- Milo;
- amigos;
- Patrick;
- lazer;
- dias vazios.

---

# 16. MOBILIDADE

Aula não significa teleporte.

```text
Botafogo
→ se arrumar
→ transporte
→ Gávea
```

Depois:
```text
PUC
→ almoço / Shopping da Gávea / casa / outro plano
```

Não simular minuto a minuto, mas considerar conflitos plausíveis.

---

# 17. WORLDSTATE

Campos derivados úteis:

```text
academic_term
academic_phase
has_class_today
next_academic_commitment
current_academic_commitment
academic_load_today
```

Não persistir duplicações stale.

---

# 18. ROUTINE ENGINE

```python
if confirmed_calendar_event_now:
    use_event()
elif academic_exception_now:
    use_academic_exception()
elif active_academic_block_now:
    use_academic_commitment()
else:
    sample_routine()
```

Perto de aula, reduzir atividades incompatíveis.

---

# 19. CONFLITOS COM MODELAGEM

Casting/job não sobrescreve aula silenciosamente.

Um conflito deve virar situação contextual:
- recusar;
- remarcar;
- negociar;
- faltar ocasionalmente;
- aula ter prioridade;
- professor liberar.

Não resolver sempre a favor da carreira nem sempre a favor da faculdade.

---

# 20. FALTAS E PRESENÇA

Não criar simulador granular de presença.

Permitir:
- atraso;
- perder uma aula;
- matar aula ocasional;
- sair cedo;
- cancelamento.

Reprovação por faltas não pode emergir de contador aleatório invisível.

---

# 21. PERFORMANCE ACADÊMICA

Evitar notas numéricas diárias.

Estados leves:

```text
doing_well
normal
struggling_temporarily
excellent_project
```

Só quando houver evento concreto que justifique.

---

# 22. NPCs ACADÊMICOS

Usar Social Graph existente.

Prof. Helena Prado é canônica. Theo e Júlia podem participar quando plausível.

Novos NPCs seguem:
```text
EPHEMERAL → SECONDARY → RECURRING
```

Não criar elenco permanente para cada matéria.

---

# 23. KNOWLEDGE / PRIVACY

Evento acadêmico não implica que Patrick sabe.

Usar a mesma arquitetura `known_by` / privacy / sharing já prevista no Living World.

---

# 24. STORY ENGINE

Faculdade deve gerar principalmente eventos banais:

```text
grupo atrasado
arquivo errado
professora pediu ajuste
material acabou
impressão ruim
apresentação boa
aula cancelada
workshop
atividade terminou cedo
```

Preferir consequências persistentes em vez de novos problemas todo dia.

---

# 25. CONTEXT BUILDER

Não enviar a grade completa em toda chamada.

Exemplo compacto:

```text
Academic:
- Term: 2026.2
- Today: class day
- Current: free until 13:00
- Next: studio class 13:00–17:00 at PUC/Gávea
- Phase: normal semester
```

Detalhes adicionais apenas quando relevantes.

---

# 26. CAMERA

Camera deve obedecer o mesmo WorldState.

Se Marina está na faculdade, não gerar praia/apartamento sem transição explícita.

---

# 27. PROATIVIDADE

Faculdade pode gerar mensagens share-worthy, mas não check-in diário mecânico.

Válido:
```text
“terminei a apresentação 😭”
```

Evitar:
```text
“indo pra aula”
“cheguei”
“saí”
```
todos os dias.

---

# 28. AUTONOMIA

## FREE
- aula normal;
- cancelamento;
- liberação cedo;
- trabalho em grupo;
- entrega;
- apresentação;
- atraso;
- falta ocasional;
- férias;
- matrícula;
- novas disciplinas futuras.

## CAUSAL
- conflito importante carreira/faculdade;
- disciplina temporariamente difícil;
- projeto com destaque.

## SIGNIFICANT
- reprovação;
- abandono de disciplina;
- atraso relevante;
- redução estrutural de carga.

## HARD_GATED
- abandonar faculdade;
- trocar curso;
- trancar semestre;
- transferir instituição;
- mudar de cidade por estudo;
- formatura artificialmente antecipada.

---

# 29. FORMATURA

O motor pode conduzir Marina até uma conclusão normal, mas não hardcodar agora uma data exata de formatura.

Preferir:

```text
progression state
+
completed requirements
+
minimum plausible terms
=
graduation eligible
```

Quando elegível:
```text
graduation_status = ELIGIBLE
```

A formatura deve virar evento relevante do Living World, não atualização silenciosa.

---

# 30. ESTRATÉGIA CURRICULAR

O agente deve escolher explicitamente:

### A — catálogo ficcional controlado
Estável e simples.

### B — currículo real validado
Mais realista, mas exige versionamento e manutenção.

### C — híbrido (recomendado)
Estrutura/tipos plausíveis e nomes controlados pelo projeto, sem afirmar que reproduz exatamente a matriz oficial atual.

---

# 31. TERM GENERATOR

Interface conceitual:

```python
AcademicTermGenerator.generate_next_term(
    current_progress,
    completed_courses,
    recent_schedule_patterns,
    world_constraints,
    rng_seed
)
```

Persistir somente após:
```text
no_conflicts
workload_ok
progression_ok
```

---

# 32. DETERMINISMO

Usar seed derivável:

```text
character_key + term_key + generator_version
```

Uma vez ativado um semestre, não regenerá-lo silenciosamente.

---

# 33. LAZY CATCH-UP

Se o bot ficar meses offline, não simular cada aula.

Catch-up:
1. fecha termo antigo;
2. consolida estado sem inventar dezenas de cenas;
3. aplica férias;
4. gera/ativa termo seguinte;
5. produz no máximo poucos fatos agregados;
6. evita avalanche de `life_events`.

---

# 34. CLEAN CANONICAL START

No bootstrap limpo:

Preservar/seedar:
- perfil acadêmico;
- termo atual;
- grade canônica aprovada.

Não importar:
- matérias inventadas por chats antigos;
- notas antigas;
- professores não canônicos;
- histórias acadêmicas antigas não aprovadas.

---

# 35. TESTES OBRIGATÓRIOS

### Schema
- migration idempotente;
- seed 2026.2 não duplica;
- FKs válidas;
- feature flag funciona.

### Grade
- sem conflito interno;
- aula somente em termo ativo;
- férias desligam blocos;
- exceção afeta ocorrência correta.

### Progressão
- curso normal conclui;
- próximo termo gera uma vez;
- pré-requisitos respeitados;
- sem reprovação aleatória;
- sem mudança de curso/instituição.

### WorldState
- aula vence rotina;
- evento excepcional pode vencer aula quando configurado;
- localização coerente;
- deslocamento plausível;
- sem atividade impossível antes de aula.

### Calendar
- nenhum segundo source of truth;
- provas/entregas usam eventos existentes;
- cancelamento não destrói schedule base.

### Catch-up
- sem centenas de eventos;
- termo antigo fecha;
- novo termo ativa;
- idempotência.

### Context
- não despejar grade inteira;
- próximo compromisso aparece;
- assunto acadêmico recupera detalhes.

### Camera
- aula ativa não produz contexto incompatível.

### Autonomy
- nenhuma reprovação/trancamento/mudança de curso por sorteio;
- graduação só quando progressão permite.

---

# 36. SIMULAÇÃO DE LONGO PRAZO

Adicionar teste acelerado de 12–24 meses e, idealmente, até `graduation eligible`.

Validar:
- vários termos;
- grades diferentes e plausíveis;
- férias;
- carga saudável;
- vida social/profissional preservada;
- sem acúmulo infinito;
- nunca dois termos ACTIVE;
- sem duplicação indevida;
- sem formatura precoce.

---

# 37. OBSERVABILIDADE

Logs:
```text
academic.term.started
academic.term.completed
academic.term.generated
academic.schedule.resolved
academic.exception.applied
academic.progress.updated
academic.graduation.eligible
```

Opcional:
```text
/academicdebug
```

Mostrar:
- term;
- phase;
- classes today;
- next commitment;
- courses;
- progress summary.

Somente chat autorizado e auto-delete.

---

# 38. DEFINITION OF DONE

```text
Marina possui grade canônica 2026.2
        ↓
WorldState respeita aulas
        ↓
rotina continua probabilística fora dos blocos
        ↓
exceções não destroem grade-base
        ↓
semestre termina
        ↓
férias
        ↓
próximo termo é criado automaticamente
        ↓
nova grade é diferente mas plausível
        ↓
progressão persiste
        ↓
processo pode continuar até formatura
```

> A vida universitária deve produzir continuidade; não transformar Marina em uma agenda ambulante.

---

# 39. ORDEM SUGERIDA

```text
1. identificar estágio atual da v3.6
2. decidir se schema entra agora ou em 3.6.4
3. criar repository/schema
4. criar seed 2026.2
5. integrar schedule resolver ao WorldState
6. integrar exceptions ao Calendar existente
7. implementar SemesterPhase
8. implementar fechamento de termo
9. implementar gerador do próximo termo
10. implementar lazy catch-up
11. simulação 12–24 meses
12. somente depois progressão longa até graduation eligibility
```

---

# 40. PERGUNTAS QUE O AGENTE DEVE RESPONDER ANTES DE IMPLEMENTAR

```text
A) Em qual release/subfase da v3.6 isso entra?

B) O schema entra agora ou apenas em 3.6.4?

C) Qual sistema atual é a fonte autoritativa de compromissos?

D) Qual estratégia curricular será usada:
   ficcional / real validada / híbrida?

E) Como a grade 2026.2 será seedada?

F) Como garantir que não será criado um segundo planner/calendar/routine engine?
```

Depois dessa decisão, atualizar o plano principal apenas nos pontos necessários.

---

# 41. PRINCÍPIO FINAL

```text
World Bible
    define quem Marina é

Academic Profile
    define onde ela está na graduação

Academic Term
    define o semestre atual

Academic Schedule
    define compromissos recorrentes

Calendar
    define exceções/eventos datados

WorldState
    resolve o que acontece agora

Routine Engine
    preenche o restante

Story Engine
    gera consequências plausíveis

Memory
    guarda o que virou memória
```

> **A faculdade é uma âncora da vida da Marina, não o centro de toda a vida dela.**
