# PLANO COMPLEMENTAR — MARINA 3.6
## Story Dataset Ingestion & Abstract Seed Library

**Status:** complemento ao `PLANO_MARINA_V3_6_LIVING_WORLD.md`  
**Release-alvo natural:** v3.6.2 — Story Seeds & Threads

**Execução em 18/09/2026:** pipeline offline, manifests, bibliotecas abstratas e
integração local opcional implementados. DailyDialog (distribuição ConvLab)
e EmpatheticDialogues processados. Dois arquivos ROCStories manuais detectados
e preservados; o usuário forneceu aviso oficial de acesso e citação, liberando
o processamento offline sem redistribuição dos textos. O usuário aprovou o
repositório oficial `ricsinaruto/gutenberg-dialog`, sua licença MIT e a
atribuição do paper para abstração offline. A tentativa de baixar o arquivo
português do MEGA oficial retornou `-16` (recurso bloqueado); aguarda o mesmo
arquivo original na pasta raw, sem substituição por outro corpus.
`STORY_SEED_LIBRARY_ENABLED`
permanece desligada até a ativação geral da v3.6.

**Objetivo:** formalizar as fontes externas aprovadas para inspiração estrutural de situações cotidianas, definir onde os arquivos devem ficar e como transformá-los em seeds abstratos seguros para o Living World.

---

# 1. Fontes aprovadas

```text
1. DailyDialog
2. EmpatheticDialogues
3. ROCStories
4. Gutenberg Dialogue Dataset
```

Esses datasets NÃO devem ser consultados em runtime.

Eles servem apenas para processamento offline/build-time.

Regra fundamental:

> **Datasets fornecem estruturas de situação, nunca histórias ou falas para copiar.**

---

# 2. Diretório oficial

Na raiz do projeto:

```text
data/
└── external/
    └── story_datasets/
        ├── dailydialog/
        │   └── raw/
        ├── empathetic_dialogues/
        │   └── raw/
        ├── rocstories/
        │   └── raw/
        ├── gutenberg_dialogue/
        │   └── raw/
        ├── manifests/
        └── licenses/
```

## ROCStories

Patrick deve colocar o download manual em:

```text
data/external/story_datasets/rocstories/raw/
```

Exemplo Windows:

```text
marin-telegram-bot\data\external\story_datasets\rocstories\raw\
```

Preservar o nome original do arquivo.

Se vier `.zip`, manter o `.zip` original. O pipeline deve extrair apenas em área de trabalho temporária.

---

# 3. Dados externos não entram no Git

Adicionar ao `.gitignore`:

```gitignore
# External story datasets
/data/external/story_datasets/*/raw/*
/data/external/story_datasets/*/normalized/*
/data/external/story_datasets/*/work/*
```

Manter versionados somente:

```text
README
manifests
licenças/termos
biblioteca abstrata final
```

---

# 4. Biblioteca derivada

A saída final fica em:

```text
data/story_seeds/
```

Estrutura:

```text
data/story_seeds/
├── story_seed_library.v1.jsonl
├── story_seed_taxonomy.v1.json
└── provenance_summary.v1.json
```

Esses arquivos devem conter apenas abstrações próprias do projeto.

Nenhuma história ou diálogo externo integral deve sobreviver na biblioteca final.

---

# 5. Scripts

Criar:

```text
scripts/story_datasets/
├── download_story_datasets.py
├── ingest_dailydialog.py
├── ingest_empathetic_dialogues.py
├── ingest_rocstories.py
├── ingest_gutenberg_dialogue.py
├── normalize_story_situations.py
├── deduplicate_story_seeds.py
├── build_story_seed_library.py
├── validate_story_seed_library.py
└── run_pipeline.py
```

---

# 6. Download automático vs manual

## DailyDialog

Automático.

Destino:

```text
data/external/story_datasets/dailydialog/raw/
```

Não exigir API key.

Registrar:
- origem;
- data;
- hash;
- versão;
- licença/termos conhecidos.

---

## EmpatheticDialogues

Automático.

Destino:

```text
data/external/story_datasets/empathetic_dialogues/raw/
```

O repositório oficial disponibiliza download direto do corpus.

Não exige API key para o download público.

---

## ROCStories

Manual/autorizado.

Destino:

```text
data/external/story_datasets/rocstories/raw/
```

O acesso oficial depende de formulário.

O agente NÃO deve:
- burlar o formulário;
- procurar cópia não autorizada;
- pedir credencial;
- substituir silenciosamente por outro corpus.

Se a pasta estiver vazia:

```text
ROCStories = SKIPPED_MANUAL_SOURCE
```

O restante do pipeline continua.

---

## Gutenberg Dialogue Dataset

Automático.

Destino:

```text
data/external/story_datasets/gutenberg_dialogue/raw/
```

Priorizar:

```text
Portuguese
English
```

quando houver versões prontas adequadas.

Não reconstruir todo o corpus de livros se uma versão processada legítima já for suficiente.

---

# 7. Manifest por fonte

Criar:

```text
data/external/story_datasets/manifests/
├── dailydialog.json
├── empathetic_dialogues.json
├── rocstories.json
└── gutenberg_dialogue.json
```

Schema:

```json
{
  "dataset_key": "rocstories",
  "display_name": "ROCStories",
  "source_type": "manual_download",
  "source_origin": "official",
  "downloaded_at": null,
  "source_version": null,
  "raw_files": [],
  "sha256": {},
  "license_file": null,
  "ingestion_status": "missing",
  "last_processed_at": null,
  "pipeline_version": 1
}
```

---

# 8. Licença e provenance

Antes da ingestão:

```text
1. identificar licença/termos
2. registrar origem
3. guardar hash
4. guardar referência/cópia dos termos quando permitido
5. não remover provenance
```

Diretório:

```text
data/external/story_datasets/licenses/
```

Se houver dúvida:

```text
LICENSE_REVIEW_REQUIRED
```

e a fonte não entra na biblioteca final até revisão.

---

# 9. Regra anti-cópia

Permitido:

```text
friend_cancelled_last_minute
forgot_item_before_commitment
unexpected_invitation
small_misunderstanding
schedule_conflict
project_deadline_change
pet_minor_mischief
awkward_social_overlap
good_news_from_work
```

Não permitido:
- texto original;
- fala original;
- sequência completa de uma história;
- nomes dos personagens;
- locais específicos do corpus;
- frases memoráveis;
- paráfrase quase idêntica da história.

---

# 10. Pipeline

```text
RAW DATASET
    ↓
parser específico
    ↓
candidate situation units
    ↓
structural abstraction
    ↓
proper noun stripping
    ↓
canonicalization
    ↓
deduplication
    ↓
taxonomy classification
    ↓
quality filtering
    ↓
story_seed_library
```

---

# 11. Unidade intermediária

```json
{
  "source_dataset": "rocstories",
  "source_record_hash": "sha256...",
  "actors_count": 2,
  "causal_shape": ["setup", "complication", "resolution"],
  "candidate_tags": ["social", "plans"],
  "intensity_estimate": "low"
}
```

Não persistir texto bruto na estrutura final.

---

# 12. Seed abstrato final

```json
{
  "seed_key": "friend_cancelled_last_minute",
  "category": "social",
  "intensity": "low",
  "actor_roles": [
    "protagonist",
    "close_friend"
  ],
  "preconditions": [
    "existing_plan"
  ],
  "possible_complications": [
    "schedule_conflict",
    "mild_disappointment"
  ],
  "possible_consequences": [
    "reschedule",
    "alternative_plan",
    "stay_home",
    "meet_other_friend"
  ],
  "allowed_horizons": [
    "TODAY",
    "NEAR_FUTURE"
  ],
  "hard_gated": false,
  "source_families": [
    "dailydialog",
    "rocstories"
  ]
}
```

---

# 13. Não guardar história pronta

Errado:

```text
Bia marcou cinema, esqueceu que tinha outro compromisso,
cancelou em cima da hora e Marina ficou chateada.
```

Correto:

```text
friend_double_booked_commitments
```

O Living World escolhe depois:
- quem participa;
- quando;
- onde;
- consequência;
- impacto;
- se o evento sequer acontece.

---

# 14. Papel de cada dataset

## DailyDialog

Prioridade:

```text
banal everyday interactions
daily practical situations
low-intensity social events
ordinary conversation contexts
```

Ótimo para aumentar variedade sem dramatização.

---

## EmpatheticDialogues

Prioridade:

```text
emotionally meaningful situations
embarrassment
frustration
pride
support contexts
social reactions
```

Importante:

> extrair a situação, não o estilo terapêutico/empático da resposta.

Não usar para fazer Marina responder como conselheira.

---

## ROCStories

Prioridade:

```text
causal structure
temporal progression
everyday narrative shape
setup → event → consequence
```

Especialmente útil para causalidade curta.

Nunca copiar os passos originais como storyline pronta.

---

## Gutenberg Dialogue Dataset

Prioridade:

```text
dialogue diversity
interpersonal structures
less common social configurations
Portuguese dialogue source material
```

Peso menor inicialmente.

Textos literários podem ter:
- registro antigo;
- teatralidade;
- contexto histórico;
- estilo incompatível com 2026.

Extrair somente estrutura.

---

# 15. Pesos de ingestão iniciais

```text
DailyDialog         = HIGH
EmpatheticDialogues = HIGH
ROCStories          = HIGH
Gutenberg Dialogue  = MEDIUM
Marina curated      = MAX
```

Esses pesos servem para construção da biblioteca, não para definir a frequência de eventos em runtime.

---

# 16. Biblioteca interna continua sendo principal

Composição:

```text
MARINA_CURATED
+
DATASET_DERIVED
+
CONSEQUENCE_TEMPLATES
```

Se houver seed específico para Marina equivalente a um genérico externo:

```text
MARINA_CURATED vence
```

---

# 17. Taxonomia

Categorias:

```text
daily_practical
social_light
friendship
academic
professional
romantic
family
pet
home
shopping
mobility
small_inconvenience
minor_success
embarrassment
misunderstanding
invitation
schedule_conflict
self_care
leisure
```

---

# 18. Intensidade

```text
BANAL
LOW
MEDIUM
HIGH
SIGNIFICANT
```

A ingestão deve produzir majoritariamente:

```text
BANAL
LOW
```

`HIGH` exige revisão adicional.

`SIGNIFICANT` não entra automaticamente no runtime.

---

# 19. Hard-gated filter

Descartar do pool automático situações envolvendo:

```text
death
pregnancy
severe disease
grave accident
violent crime
marriage
relationship breakup
permanent move
dropping college
major financial collapse
irreversible family rupture
```

Não transformar dataset em fonte de grandes eventos aleatórios.

---

# 20. Filtro de modernidade

Especialmente no Gutenberg, rejeitar/abstrair estruturas dependentes de:

```text
tecnologia obsoleta
normas sociais históricas
profissões de época
costumes arcaicos
cortejo incompatível com 2026
```

---

# 21. Despersonalização

Remover quando não essencial:

```text
nomes
idade específica
gênero obrigatório
cidade
empresa
instituição
marca
data
profissão específica
```

Exemplo:

```text
John perdeu o trem para Boston
```

vira:

```text
missed_transport_connection
```

---

# 22. Deduplicação

Seeds como:

```text
forgot_item
left_item_at_home
forgot_something_before_leaving
```

podem convergir para:

```text
forgot_item_before_commitment
```

Usar:

```text
canonical_key
semantic similarity
taxonomy overlap
causal shape
```

---

# 23. Frequência externa não vira frequência na Marina

Mesmo que um dataset contenha milhares de:

```text
arguments
```

isso não aumenta automaticamente discussões.

Runtime continua obedecendo:

```text
narrative budget
WorldState
personality
active threads
recent event density
relationship context
```

---

# 24. Runtime

```text
WorldState
    ↓
narrative budget
    ↓
active consequences first
    ↓
routine
    ↓
if new seed allowed:
    local abstract seed library
    ↓
WorldCoherenceValidator
    ↓
instantiate
```

Nenhum acesso aos datasets externos durante conversa.

---

# 25. Consequência antes de seed novo

Prioridade:

```text
existing consequence
>
new dataset-derived seed
```

O objetivo é continuidade causal, não novidade infinita.

---

# 26. Não usar vector DB dos textos brutos

Não colocar os corpora originais em retrieval runtime.

Se embeddings forem úteis, usar apenas offline para:
- deduplicação;
- clusterização;
- abstração.

---

# 27. Uso de LLM no preprocessing

Opcional.

Se usado:

```text
temperature baixa
schema JSON rígido
batch offline
validation
dedup
copyright guard
```

Prompt deve pedir:

```text
extract reusable causal/situational structure
do not preserve wording
do not preserve names
do not reconstruct the original story
```

Não pedir “resuma a história”.

---

# 28. Modos de pipeline

```text
RULE_BASED_ONLY
LLM_ABSTRACTION
```

`LLM_ABSTRACTION` deve ser manual/opt-in porque consome créditos.

Não rerodar em todo deploy.

---

# 29. Cache

Identificador:

```text
source_record_hash + pipeline_version
```

Se já processado pela mesma versão:

```text
skip
```

---

# 30. Versionamento

```text
story_seed_library.v1.jsonl
pipeline_version = 1
```

Mudança de algoritmo gera nova versão.

Threads já persistidas não são reinterpretadas retroativamente.

---

# 31. Validação de qualidade

Cada seed:

```text
has_unique_key
valid_category
valid_intensity
no_source_text
no_proper_nouns
no_specific_story_sequence
not_hard_gated
usable_preconditions
usable_consequences
```

---

# 32. Auditoria anti-cópia

Comparar seeds derivados com origem apenas durante preprocessing.

A saída final deve ser majoritariamente:
- enums;
- labels;
- relações;
- estruturas causais.

Não prosa.

---

# 33. Provenance final

Criar:

```text
data/story_seeds/provenance_summary.v1.json
```

Exemplo:

```json
{
  "library_version": 1,
  "pipeline_version": 1,
  "sources": {
    "dailydialog": {
      "enabled": true,
      "records_seen": 0
    },
    "empathetic_dialogues": {
      "enabled": true,
      "records_seen": 0
    },
    "rocstories": {
      "enabled": false,
      "reason": "manual_source_missing"
    },
    "gutenberg_dialogue": {
      "enabled": true,
      "records_seen": 0
    }
  },
  "final_seed_count": 0
}
```

Sem conteúdo original.

---

# 34. Comandos sugeridos

Download automático:

```bash
python scripts/story_datasets/download_story_datasets.py
```

Baixa:

```text
DailyDialog
EmpatheticDialogues
Gutenberg Dialogue
```

ROCStories:

```text
apenas verificar pasta manual
```

Pipeline:

```bash
python scripts/story_datasets/run_pipeline.py
```

Validação:

```bash
python scripts/story_datasets/validate_story_seed_library.py
```

---

# 35. Se ROCStories estiver ausente

Não falhar tudo.

Log:

```text
[story-datasets] ROCStories: manual source not present; skipped.
```

Os outros datasets continuam.

---

# 36. Se ROCStories já estiver presente

O downloader:

```text
detecta arquivo
calcula hash
registra manifest
não sobrescreve
não baixa substituto
```

Depois o ingestor trabalha sobre uma cópia/stream segura.

---

# 37. Proteção contra exclusão

O pipeline nunca apaga raw manual por padrão.

Limpeza só via:

```text
--clean-work
```

e apenas para arquivos intermediários regeneráveis.

---

# 38. Estrutura após primeira execução

```text
data/
├── external/
│   └── story_datasets/
│       ├── dailydialog/
│       │   ├── raw/
│       │   └── normalized/
│       ├── empathetic_dialogues/
│       │   ├── raw/
│       │   └── normalized/
│       ├── rocstories/
│       │   ├── raw/
│       │   └── normalized/
│       ├── gutenberg_dialogue/
│       │   ├── raw/
│       │   └── normalized/
│       ├── manifests/
│       └── licenses/
│
└── story_seeds/
    ├── story_seed_library.v1.jsonl
    ├── story_seed_taxonomy.v1.json
    └── provenance_summary.v1.json
```

---

# 39. Testes obrigatórios

## Download
- download idempotente;
- ROC nunca tenta burlar acesso manual;
- download incompleto não marca source ready;
- hash detecta mudança/corrupção.

## Git
- raw não aparece em `git status`;
- manifests podem ser versionados;
- biblioteca abstrata final pode ser versionada.

## Parsing
- raw nunca é alterado;
- encoding tratado;
- arquivo inesperado gera erro seguro.

## Abstraction
- nomes removidos;
- texto original não chega ao seed;
- canonical key obrigatória;
- causal shape válida.

## Dedup
- equivalentes convergem;
- frequência externa não duplica seed.

## Safety
- hard-gated fora do pool;
- Gutenberg arcaico não vira evento moderno direto;
- EmpatheticDialogues não aumenta dramaticidade automaticamente.

## Runtime
- funciona sem internet;
- nenhum raw é lido em conversa;
- StorySeedEngine usa somente biblioteca derivada;
- consequência ativa ganha de seed novo.

---

# 40. Long simulation

Rodar:

```text
30 dias
90 dias
365 dias
```

Medir:

```text
event repetition
seed repetition
category distribution
intensity distribution
banal-day ratio
active-thread count
major-event count
```

Os datasets não podem diminuir artificialmente a proporção planejada de dias banais.

---

# 41. Feature flags

Build/preprocessing:

```env
STORY_DATASET_INGESTION_ENABLED=true
STORY_DATASET_DAILYDIALOG_ENABLED=true
STORY_DATASET_EMPATHETIC_DIALOGUES_ENABLED=true
STORY_DATASET_ROCSTORIES_ENABLED=true
STORY_DATASET_GUTENBERG_ENABLED=true
```

Runtime:

```env
STORY_SEED_LIBRARY_ENABLED=true
```

---

# 42. Anti-patterns proibidos

1. consultar dataset durante conversa;
2. colocar corpus no prompt;
3. vectorizar raw para retrieval runtime;
4. copiar história inteira;
5. traduzir história e chamar de seed;
6. preservar personagens externos;
7. reproduzir frases;
8. usar frequência externa como frequência narrativa;
9. substituir Story Thread Engine;
10. gerar evento grande porque apareceu no corpus;
11. buscar ROCStories por fonte não autorizada;
12. commitar raw;
13. apagar arquivo manual do ROC;
14. depender de download no startup normal.

---

# 43. Prioridade final

```text
Marina curated      = MAX
DailyDialog         = HIGH
EmpatheticDialogues = HIGH
ROCStories          = HIGH
Gutenberg Dialogue  = MEDIUM
```

---

# 44. Definition of Done

```text
Patrick coloca ROCStories em rocstories/raw/
        ↓
agente baixa os outros três
        ↓
origem/licença/hash registrados
        ↓
raw processado offline
        ↓
situações abstraídas
        ↓
texto original excluído da biblioteca final
        ↓
seeds deduplicados/classificados
        ↓
hard-gated filtrado
        ↓
story_seed_library.v1.jsonl gerado
        ↓
Story Seed Engine usa somente biblioteca local
        ↓
Marina cria acontecimentos próprios e causais
```

---

# 45. Instrução imediata para Patrick

Criar:

```text
data/external/story_datasets/rocstories/raw/
```

Colocar ali o arquivo original recebido pelo acesso oficial.

**Não renomear.**

Se vier compactado, preservar o arquivo compactado original.

---

# 46. Instrução imediata para o agente

Ao receber este plano:

```text
1. verificar convenção existente de data/
2. adotar os paths acima se não houver conflito real
3. criar diretórios necessários
4. atualizar .gitignore
5. nunca apagar arquivo manual de rocstories/raw/
6. automatizar os três downloads públicos
7. registrar license/provenance/hash
8. implementar ingestão na v3.6.2 ou etapa equivalente
9. produzir somente seeds abstratos
10. integrar runtime apenas com a biblioteca derivada
```

---

# 47. Princípio final

> **External datasets provide patterns of life, not Marina's life itself.**

Eles podem ensinar ao sistema que existem situações como:

```text
esquecer algo
desmarcar em cima da hora
receber convite inesperado
errar horário
ter pequeno mal-entendido
receber boa notícia
```

Mas quem vive a situação, com quem, quando, onde, por quê e quais consequências ela terá deve nascer do estado persistente da própria Marina.
