# REVISÃO TÉCNICA — MARINA SELTIN v3.5.0
## Memory Intelligence — correções obrigatórias antes da v3.5.1

**Pacote auditado:** `marin-telegram-bot-3.5.rar`  
**Commit reconstruído a partir do próprio RAR:** `ebfa3f560552a01bc0a9f6a36a2c8012a17f9ca6`  
**Base confirmada:** `804aa3bc9e1947696e3204330f7468f94acbd9b6` — v3.4.3  
**Gate atual:** **NÃO AVANÇAR PARA 3.5.1 AINDA**

---

# 1. RESUMO EXECUTIVO

A v3.5.0 implementou corretamente boa parte da infraestrutura prevista no plano:

- migration `005_memory_intelligence.sql`;
- `memory_tier` (`core|standard|contextual`);
- `volatility` (`stable|medium|volatile`);
- `canonical_key`;
- `last_confirmed_at`;
- `confirmation_count`;
- FTS5 também para momentos e resumos;
- Retriever 2.0 com ranking composto;
- seleção de candidatos para o Consolidator em vez de enviar todo o banco à LLM;
- `/memorydebug` / `/memoria <termo>`;
- nova suíte `tests/test_memory_intelligence.py`.

A arquitetura é aproveitável e **não precisa ser reescrita**.

Entretanto, há um bug de integridade de memória reproduzível que impede o release de ser considerado estável. A decisão retornada pelo Consolidator (`same`, `update`, `contradiction`, etc.) ainda não é autoritativa durante a escrita no SQLite. Em uma reafirmação simples, a implementação atual pode desativar a única memória válida e falhar silenciosamente ao recriá-la.

Também há lacunas em volatilidade/confiança efetiva, ranking lexical, isolamento de side effects, feature flag e validação da saída da LLM.

**Conclusão:** corrigir a v3.5.0, rodar novamente os testes e somente depois iniciar a v3.5.1.

---

# 2. VALIDAÇÕES EXECUTADAS NA REVISÃO

## 2.1 Identidade do pacote

O RAR contém o diretório `.git`. Como os objetos Git estavam armazenados diretamente no arquivo, foi possível reconstruir o repositório sem depender do GitHub.

Resultado:

```text
HEAD = ebfa3f560552a01bc0a9f6a36a2c8012a17f9ca6
commit = feat(release): Marina Seltin v3.5.0 - Memory Intelligence
parent = 804aa3bc... (v3.4.3)
```

Portanto, esta revisão foi feita sobre o estado exato enviado no anexo.

## 2.2 Compile

Executado:

```bash
python -m compileall -q .
```

Resultado:

```text
PASS
```

Nenhum erro de sintaxe encontrado.

## 2.3 Migration real v3.4.3 → v3.5.0

Foi criado um banco com o código v3.4.3 contendo:

- conversa de teste;
- fato de teste com category/importance/confidence.

Em seguida o mesmo banco foi aberto pelo código v3.5.0.

Resultado:

```text
schema_version: 4 -> 5
conversa antiga: preservada
fato antigo: preservado
memory_tier: backfill = standard
volatility: backfill = medium
canonical_key: NULL
confirmation_count: 0
```

**Migration 005 aprovada quanto à preservação básica dos dados existentes.**

## 2.4 Testes específicos da Memory Intelligence

O sandbox não possuía o pacote `openai`, e não há resolução de rede para instalar dependências. Foi usado somente um stub de transporte `OpenAI` para impedir chamadas externas; nenhuma lógica do projeto foi substituída.

Executado:

```bash
python -W error::ResourceWarning -m unittest tests.test_memory_intelligence -v
```

Resultado:

```text
11 tests
11 PASS
```

Isso confirma que os testes adicionados pelo release passam, mas também demonstra que eles não cobrem os caminhos críticos descritos abaixo.

## 2.5 Suíte total

A tentativa da suíte completa encontrou imports ausentes no sandbox:

```text
openai
telegram
```

Os erros ocorreram na coleta/importação, antes da lógica testada. Como o sandbox não consegue baixar pacotes, isso **não deve ser classificado como regressão do projeto**.

Na máquina do projeto/agente, após as correções, é obrigatório executar novamente:

```bash
python -W error::ResourceWarning -m unittest discover tests -v
```

## 2.6 Reprodução independente do bug crítico

Cenário usado com SQLite real:

```text
fato ativo:
"Patrick joga FFXIV"
canonical_key = current_main_game
confidence = 0.8

nova consolidação:
decision = same
fato = "Patrick joga FFXIV"
canonical_key = current_main_game
```

Resultado atual:

```text
apply_consolidation -> created = 0
memórias ativas com current_main_game = 0
memória antiga = active 0
confirmation_count = 0
```

Motivo:

```text
apply_consolidation
    -> desativa automaticamente a canonical_key
    -> tenta INSERT OR IGNORE do mesmo texto
    -> fatos_patrick.fato possui UNIQUE
    -> insert é ignorado
    -> nenhuma versão ativa sobra
```

**Bug confirmado e reproduzível.**

---

# 3. P0 — BLOQUEADORES

# P0.1 — `decision` não controla a aplicação da consolidação

## Problema

O plano da 3.5.0 define explicitamente:

```text
new | same | update | contradiction | ignore
```

Porém o prompt atual do Consolidator só formaliza:

```text
new | update | contradiction
```

E `apply_consolidation()` não usa `decision` para escolher a operação.

Hoje a existência de uma `canonical_key` causa desativação automática da memória anterior, independentemente de o conteúdo ser uma reafirmação.

O método correto já existe:

```python
DatabaseManager.confirmar_fato(fato_id)
```

mas ele está isolado e nunca é acionado pelo Consolidator.

## Correção obrigatória

O schema da resposta do Consolidator deve aceitar:

```json
{
  "decision": "new|same|update|contradiction|ignore",
  "existing_fact_id": null,
  "supersedes_id": null
}
```

Regras:

```text
same
    -> NÃO inserir nova linha
    -> NÃO desativar antiga
    -> confirmar_fato(existing_fact_id)

ignore
    -> nenhuma escrita

new
    -> inserir novo fato
    -> não desativar fato só porque canonical_key apareceu

update / contradiction
    -> criar substituição de forma atômica
    -> somente desativar o antigo se o novo fato foi persistido com sucesso
    -> supersedes_id deve apontar para o registro antigo
```

## Regra adicional de segurança

Se `decision == same` e `existing_fact_id` não vier, tentar resolver **somente** entre os candidatos apresentados à LLM:

1. `canonical_key` igual e exatamente um candidato ativo;
2. ou texto normalizado equivalente entre os candidatos.

Se continuar ambíguo:

```text
não mutar o banco
logar warning estruturado
```

Nunca escolher um fato arbitrário.

---

# P0.2 — substituição/desativação não é atômica

## Problema

A implementação atual grava cada etapa por métodos separados, cada um abrindo sua própria conexão e executando `commit()`.

Fluxo atual:

```text
desativar antigo -> COMMIT
inserir novo -> COMMIT
```

Se o segundo passo falhar por:

- `UNIQUE(fato)`;
- exceção SQLite;
- dado inválido;
- interrupção do processo;
- erro futuro de validação;

fica possível perder a única versão ativa da memória.

## Correção obrigatória

Criar em `db.py` uma operação transacional dedicada, por exemplo:

```python
substituir_fato_atomicamente(...)
```

Toda a operação deve usar **uma única conexão e uma única transação**.

Fluxo recomendado:

```text
BEGIN

1. validar fato antigo ativo
2. tentar criar/atualizar o novo estado
3. confirmar que a nova versão existe
4. desativar a antiga
5. garantir supersedes_id

COMMIT

qualquer erro
-> ROLLBACK
-> fato antigo continua ativo
```

Para texto exatamente igual, a operação correta normalmente é `same`, não replacement.

Não alterar a migration 005 já aplicada apenas para resolver isso. A solução pode ser feita na camada de aplicação sem nova migration.

---

# P0.3 — IDs/chaves retornados pela LLM são usados como autoridade de escrita

## Problema

Atualmente a LLM pode retornar:

```json
{"existing_fact_id": 123}
```

ou um item em:

```json
facts_to_deactivate
```

E o código aplica a mutação diretamente.

Mesmo sem intenção maliciosa, LLMs podem alucinar IDs ou chaves. Um ID inventado que por coincidência exista pode desativar uma memória não relacionada.

## Correção obrigatória

A chamada do Consolidator deve manter um allowlist interno, produzido pelo código e **não pela LLM**:

```text
candidate_fact_ids
candidate_canonical_keys
```

Somente permitir `same/update/contradiction/deactivate` quando o alvo estiver nesse conjunto.

Sugestão:

```python
consolidation["_candidate_fact_ids"] = {...}
consolidation["_candidate_keys"] = {...}
```

Esses campos são internos e nunca precisam vir no JSON da LLM.

Para revogação explícita:

```text
"esquece isso"
```

a chave ou ID também deve corresponder a um candidato recuperado a partir do conteúdo da conversa.

Alvo fora do allowlist:

```text
NO-OP + warning
```

---

# 4. P1 — CORREÇÕES IMPORTANTES

# P1.1 — `volatility` existe, mas não afeta a confiança efetiva

## Evidência

Teste independente no release atual:

```text
mesma memória antiga
confidence bruto = 1.0

stable_score   = 0.705
volatile_score = 0.705
```

Ou seja, `volatility` está persistida, mas não altera a certeza usada pelo Retriever.

A definição de pronto da 3.5.0 exige que uma memória volátil antiga não seja tratada como verdade absoluta.

## Correção recomendada

**Não implementar ainda o decay persistente completo da 3.5.3.**

Na 3.5.0 implementar `effective_confidence` somente em tempo de retrieval.

Exemplo conceitual:

```text
raw confidence permanece no banco
        ↓
idade desde last_confirmed_at / updated_at / created_at
        +
volatility
        ↓
effective_confidence
```

Faixas coerentes com o plano:

```text
stable
    quase sem penalidade temporal

medium
    sem penalidade inicial
    começar redução aproximadamente após 90 dias

volatile
    começar redução aproximadamente após 30 dias
```

Não apagar memória automaticamente.

O score deve usar:

```text
effective_confidence
```

em vez de `confidence` bruto.

Na saída para o Context Builder:

```text
effective_confidence >= 0.80
    -> afirmar normalmente

0.50–0.79
    -> tratar com cautela / contexto potencialmente desatualizado

< 0.50
    -> orientar reconfirmação natural
```

Importante: o decay permanente e a manutenção periódica do campo `confidence` continuam pertencendo à 3.5.3.

---

# P1.2 — `fts_rank` é recebido, mas ignorado

## Evidência

No método:

```python
compute_hybrid_score(..., fts_rank=...)
```

o parâmetro `fts_rank` não participa do cálculo.

Teste independente:

```text
fts_rank = -10.0  -> score 0.71
fts_rank = -0.001 -> score 0.71
```

O código reduz a relevância lexical a:

```text
match FTS = 1.0
sem match = 0.05
```

Portanto, um match excelente e um match fraco recebem a mesma parcela lexical.

## Correção recomendada

Não usar BM25 bruto diretamente.

Usar uma medida relativa, conforme o plano:

```text
RRF
ou
rank relativo normalizado entre os resultados recuperados
```

Uma implementação simples e robusta:

```text
para cada keyword:
    resultado na posição 1 -> maior lexical contribution
    posição 2 -> menor
    posição 3 -> menor

se o mesmo fato casar com múltiplas keywords:
    combinar os sinais

normalizar lexical relevance para 0..1
```

O `compute_hybrid_score()` deve receber o lexical score já normalizado.

---

# P1.3 — Retriever 2.0 ainda carrega todos os fatos ativos

## Problema

Fluxo atual:

```text
FTS candidates
+ Core memories
+ get_fatos_patrick_detalhados(active_only=True)  <- todos
```

Depois todos entram no ranking Python.

Isso não repete o erro antigo de enviar 500 fatos à LLM, pois apenas os selecionados seguem para o Consolidator. Porém perde a principal vantagem de seleção prévia do Retriever e escala desnecessariamente com o banco.

## Correção recomendada

Adicionar em `db.py` uma busca limitada para fallback, por exemplo:

```python
get_memory_fallback_candidates(limit=20)
```

Ordenação possível:

```text
active = 1
importance DESC
confidence DESC
last_confirmed_at/updated_at/created_at DESC
LIMIT N
```

Retriever candidato deve ser:

```text
FTS matches
+ poucas Core Memories
+ fallback limitado
```

Nunca carregar a tabela inteira apenas para escolher 5–12 fatos.

---

# P1.4 — `access_count` recebe side effects de operações que não são lembrança real

## Problema

`retrieve_context()` incrementa `access_count` para todo fato selecionado.

O próprio Consolidator chama `retrieve_context()` em background para escolher candidatos.

Portanto:

```text
background consolidation
-> access_count++
-> fato parece mais "popular"
-> pequeno bônus de ranking aumenta
```

O mesmo ocorre ao usar `/memorydebug`.

Isso cria exatamente o tipo de feedback loop que o plano pediu para limitar.

## Correção recomendada

Adicionar parâmetro:

```python
retrieve_context(..., record_access: bool = True)
```

Uso:

```text
ContextBuilder normal
    record_access=True

Consolidator candidate lookup
    record_access=False

/memorydebug
    record_access=False

testes/diagnósticos
    record_access=False
```

Melhor ainda, a médio prazo separar:

```text
retrieve_candidates()  -> puro, sem side effect
retrieve_context()     -> seleção final + access tracking
```

---

# P1.5 — `MEMORY_INTELLIGENCE_ENABLED` é uma feature flag morta

## Evidência

A configuração foi criada em `config.py`, mas não existe nenhuma leitura da flag fora desse arquivo.

Hoje:

```text
MEMORY_INTELLIGENCE_ENABLED=false
```

não desativa a Memory Intelligence.

## Correção obrigatória

A flag deve efetivamente restaurar o comportamento legado da v3.4.3.

Opções aceitáveis:

### Opção A — preferida

No `MemoryRetriever`:

```python
retrieve_context()
    if not MEMORY_INTELLIGENCE_ENABLED:
        return retrieve_context_legacy(...)
```

Manter uma implementação pequena do comportamento 3.4.3 como fallback.

### Opção B

`ContextBuilder` escolhe explicitamente o path legacy/intelligence.

O importante é:

```text
flag false
-> app continua funcional
-> sem novos tiers/ranking/decisions obrigatórios
-> rollback operacional sem downgrade de banco
```

Adicionar teste automatizado.

---

# P1.6 — saída da LLM não é validada antes de gravar

## Problema

Campos como estes entram praticamente direto no banco:

```text
importance
confidence
memory_tier
volatility
category
decision
canonical_key
```

LLM structured JSON reduz erros de formato, mas não substitui validação de domínio.

## Correção obrigatória

Na camada de aplicação:

```text
importance: clamp 0.0..1.0
confidence: clamp 0.0..1.0
memory_tier: whitelist core|standard|contextual
volatility: whitelist stable|medium|volatile
decision: whitelist new|same|update|contradiction|ignore
canonical_key: normalizar snake_case ou rejeitar
IDs: int positivo + allowlist de candidatos
```

Valores inválidos devem cair para default seguro ou gerar NO-OP, conforme o campo.

Nunca permitir que um valor inesperado da LLM crie um estado impossível no banco.

---

# 5. P2 — ACABAMENTOS / HIGIENE

## P2.1 — `.env.example` desatualizado

O arquivo ainda se identifica como versão antiga e não documenta as novas configs.

Adicionar pelo menos:

```env
MEMORY_INTELLIGENCE_ENABLED=true
MEMORY_MAX_FACTS=5
MEMORY_MAX_MOMENTS=3
MEMORY_MAX_SUMMARIES=2
```

Se os pesos forem configuráveis, adicionar também os pesos do ranking.

## P2.2 — pesos do ranking estão hardcoded

O plano recomenda que os pesos sejam configuráveis.

Mover para `config.py` / `.env.example`, mantendo defaults equivalentes:

```text
lexical = 0.40
importance = 0.20
effective_confidence = 0.15
freshness = 0.10
core = 0.10
access = 0.05
```

Validar na inicialização que a soma é coerente; não precisa exigir exatamente 1.0 se o código normalizar.

## P2.3 — `/memorydebug` não exibe source

O plano previa:

```text
fato
score
confidence
tier
source
```

O comando atual mostra score/confidence/tier/key/category, mas não `source_conversation_id`.

Adicionar source somente no debug privado.

`get_fatos_patrick_detalhados()` também precisa selecionar o campo se ainda não retornar.

## P2.4 — momentos/resumos ainda não participam do ranking híbrido completo

Eles agora possuem FTS, o que já é um avanço correto.

Entretanto o ranking híbrido detalhado é aplicado somente aos fatos. Momentos e resumos são escolhidos por primeiro match + fallback recente.

Não é bloqueador, mas vale melhorar se o ajuste não aumentar demais o escopo.

Prioridade:

```text
primeiro corrigir P0/P1
só depois este item
```

## P2.5 — release misturou infraestrutura GPU com Memory Intelligence

O commit da 3.5.0 também adicionou `gpu_manager.py` e alterou `NOVITA_SERVERLESS_MASTER.md`.

Não foi encontrada regressão direta por isso, mas futuras releases devem evitar misturar mudanças sem relação com o objetivo do release.

Ajuda a manter:

- auditoria simples;
- rollback simples;
- diffs menores;
- menos risco de regressão lateral.

---

# 6. CORREÇÃO PROPOSTA POR ARQUIVO

# `memory_consolidator.py`

Obrigatório:

1. atualizar schema do prompt para `new|same|update|contradiction|ignore`;
2. incluir `existing_fact_id`;
3. guardar allowlist interno de IDs/chaves dos candidatos apresentados;
4. reescrever `apply_consolidation()` como dispatcher por `decision`;
5. `same -> confirmar_fato()`;
6. `ignore -> NO-OP`;
7. `new -> insert sem auto-desativação por key`;
8. `update/contradiction -> método atômico do DB`;
9. impedir mutações de ID/key fora dos candidatos;
10. validar enums/números antes da escrita.

Remover esta regra implícita:

```text
"tem canonical_key" -> "desativar antigo sempre"
```

Canonical key identifica o conceito; **não define sozinha a decisão de mutação**.

---

# `db.py`

Obrigatório:

1. `confirmar_fato()` deve operar apenas em fato ativo;
2. criar operação de replacement atômico;
3. adicionar lookup seguro por ID/canonical key;
4. `adicionar_fato_patrick()` deve distinguir claramente insert efetuado de `INSERT OR IGNORE` ignorado;
5. criar fallback limitado de candidatos para Retriever;
6. se adicionar source no debug, retornar `source_conversation_id` no detalhado.

Sugestão de contrato:

```python
confirmar_fato(fato_id) -> bool
substituir_fato_atomicamente(existing_fact_id, new_fact_data) -> new_id | None
get_fato_detalhado(fato_id, active_only=True) -> dict | None
get_memory_fallback_candidates(limit=20) -> list[dict]
```

Não precisa criar tabela nova.

---

# `memory_retriever.py`

Obrigatório:

1. implementar `effective_confidence` com volatility + idade;
2. usar relevance lexical relativa/normalizada;
3. remover full-table scan de fatos ativos;
4. adicionar `record_access=False` para usos internos;
5. Consolidator não deve modificar `access_count`;
6. `/memorydebug` não deve modificar `access_count`;
7. feature flag deve possuir fallback legacy;
8. usar pesos configuráveis.

Preservar:

- FTS de fatos;
- FTS de momentos;
- FTS de resumos;
- deduplicação por canonical key;
- diversidade por categoria;
- limites atuais do Context Builder.

---

# `context_builder.py`

Manter a integração atual, mas garantir que:

```text
MEMORY_INTELLIGENCE_ENABLED=false
```

não dependa de campos novos para funcionar.

Para confidence intermediária, transmitir orientação natural à LLM sem tornar o prompt técnico demais.

Não expor ao texto final termos como:

```text
confidence=0.63
volatility=volatile
```

A Marina só deve demonstrar a incerteza de forma humana.

---

# `config.py`

Adicionar configuração dos pesos, caso a abordagem escolhida use pesos externos.

Exemplo sem obrigatoriedade de nomes exatos:

```text
MEMORY_WEIGHT_LEXICAL
MEMORY_WEIGHT_IMPORTANCE
MEMORY_WEIGHT_CONFIDENCE
MEMORY_WEIGHT_FRESHNESS
MEMORY_WEIGHT_CORE
MEMORY_WEIGHT_ACCESS
MEMORY_CANDIDATE_POOL_SIZE
```

Defaults devem reproduzir a intenção do plano.

---

# `.env.example`

Documentar todas as configs da v3.5.0.

Não adicionar credenciais reais.

---

# `bot.py`

No `/memoria` / `/memorydebug`:

```text
record_access=False
```

Adicionar `source_conversation_id` se disponível.

Preservar autorização `TARGET_CHAT_ID` e auto-delete.

---

# `tests/test_memory_intelligence.py`

Expandir obrigatoriamente.

A suíte atual passa, porém testa componentes isolados e não o wiring decisório completo.

---

# 7. TESTES OBRIGATÓRIOS NOVOS

## 7.1 SAME com texto idêntico

```text
Given:
  fato ativo "Patrick joga FFXIV"
  key=current_main_game
  confidence=0.7

When:
  decision=same
  mesmo texto
  mesmo existing_fact_id

Then:
  quantidade de fatos ativos dessa key = 1
  mesmo ID continua ativo
  confirmation_count += 1
  confidence aumenta até no máximo 1.0
  last_confirmed_at atualiza
  created = 0
```

Esse teste deve falhar na versão atual e passar depois da correção.

## 7.2 SAME semanticamente igual, texto diferente

A decisão da LLM é `same`.

```text
não criar segunda linha
confirmar existing_fact_id
```

## 7.3 IGNORE

```text
snapshot DB antes
apply decision=ignore
snapshot DB depois
-> nenhuma alteração em fatos
```

## 7.4 UPDATE

```text
antigo ativo
novo diferente

-> novo ativo
-> antigo inativo
-> new.supersedes_id = old.id
-> exatamente 1 ativo para o conceito
```

## 7.5 CONTRADICTION

Mesmo requisito transacional do update.

## 7.6 Falha durante replacement

Mockar/forçar erro na inserção.

Esperado:

```text
old.active == 1
nenhuma perda de memória
```

## 7.7 `UNIQUE(fato)` não apaga memória

Reproduzir exatamente o caso encontrado na auditoria.

Resultado esperado depois do fix:

```text
1 fato ativo
não 0
```

## 7.8 ID alucinado pela LLM

```text
candidate IDs = {5, 8}
LLM pede deactivate id=42

-> NO-OP
-> warning
-> ID 42 não é tocado
```

## 7.9 Key fora do allowlist

Mesma regra.

## 7.10 Volatilidade

Criar dois fatos com mesma idade/confidence:

```text
stable
volatile
```

Após janela suficiente:

```text
effective_confidence(volatile) < effective_confidence(stable)
```

O `confidence` bruto persistido não deve ser alterado pela leitura.

## 7.11 Relevância lexical

Dois candidatos FTS com ranks diferentes.

```text
melhor posição/rank relativo
-> lexical score maior
```

## 7.12 Background retrieval sem popularity feedback

```text
access_count antes = N
Consolidator busca candidates
access_count depois = N
```

## 7.13 Context Builder incrementa acesso normalmente

O path conversacional final pode continuar registrando acesso.

## 7.14 `/memorydebug` não altera access_count

Debug deve ser observacional.

## 7.15 Feature flag OFF

```text
MEMORY_INTELLIGENCE_ENABLED=false
```

O Retriever deve executar path compatível com v3.4.3 sem crash e sem exigir metadados 3.5 para construir contexto.

## 7.16 Migration regression

Preservar teste:

```text
DB schema 4 com dados
-> inicializar v3.5.0
-> schema 5
-> dados continuam intactos
```

---

# 8. TESTES FINAIS DE REGRESSÃO

Após implementar os fixes, o agente deve executar:

```bash
python -m compileall -q .
```

Depois:

```bash
python -W error::ResourceWarning -m unittest discover tests -v
```

Esperado:

```text
0 failures
0 errors
0 ResourceWarning
```

Também executar `healthcheck.py`:

```bash
python healthcheck.py
```

E verificar manualmente:

```text
schema_version = 5 (ou versão superior somente se uma migration nova tiver sido realmente necessária)
```

**Preferência:** resolver o hardening sem migration adicional para não ocupar o número que poderá ser usado pela v3.5.1.

---

# 9. TESTE MANUAL MÍNIMO ANTES DO GATE

Com um banco descartável:

### Passo A

Registrar:

```text
"Amor, lembra que meu jogo principal agora é FFXIV"
```

Esperar consolidação.

Verificar:

```text
memory_tier apropriado
canonical_key presente
1 fato ativo
```

### Passo B

Depois:

```text
"sim, ainda tô jogando FFXIV"
```

Esperar nova consolidação.

Verificar:

```text
mesmo conceito continua com 1 fato ativo
confirmation_count aumentou
não surgiu duplicata
```

### Passo C

Depois:

```text
"na real parei FFXIV, agora tô jogando outro jogo como principal"
```

Verificar:

```text
fato antigo inativo
novo ativo
supersedes_id correto
```

### Passo D

Depois:

```text
"esquece essa informação de jogo principal"
```

Verificar:

```text
memória correspondente inativa
nenhum fato não relacionado foi alterado
```

---

# 10. CRITÉRIO DE PRONTO — v3.5.0 CORRIGIDA

A v3.5.0 somente recebe **APROVADA** quando todos forem verdadeiros:

```text
[ ] migration 005 preserva banco antigo
[ ] same confirma em vez de substituir
[ ] ignore não escreve
[ ] update é atômico
[ ] contradiction é atômico
[ ] falha de insert não apaga memória antiga
[ ] IDs/chaves da LLM são limitados ao allowlist de candidatos
[ ] volatile antigo perde confiança efetiva
[ ] stable não sofre penalidade equivalente
[ ] FTS usa relevância relativa real
[ ] Retriever não faz full scan desnecessário
[ ] background candidate retrieval não aumenta access_count
[ ] memorydebug não aumenta access_count
[ ] feature flag OFF funciona
[ ] valores da LLM são validados/clampados
[ ] novos testes passam
[ ] suíte legada inteira continua verde
[ ] compileall passa
[ ] healthcheck passa
```

---

# 11. ORDEM RECOMENDADA PARA O AGENTE

Implementar nesta ordem:

```text
1. corrigir contrato de decision do Consolidator
2. criar operações DB atômicas
3. adicionar allowlist de candidate IDs/keys
4. criar testes P0 (same/update/contradiction/ignore/failure)
5. corrigir effective_confidence + volatility
6. corrigir FTS relevance
7. remover full scan de candidatos
8. remover side effects de background/debug
9. ligar feature flag de verdade
10. validar/clamp output da LLM
11. atualizar config/.env.example/debug
12. rodar suíte inteira
13. gerar relatório final da 3.5.0 corrigida
```

Não iniciar Open Loops/Smart Reminders enquanto estes itens estiverem pendentes.

---

# 12. NOTA DE SEGURANÇA DO ARQUIVO DE HANDOFF

O RAR enviado para auditoria contém:

```text
.env
.git/
```

Isso é útil para uma revisão privada e permitiu reconstruir o commit exato, mas o arquivo `.env` pode conter credenciais reais.

**Não publicar esse RAR.**

O repositório Git público analisado anteriormente não tinha `.env` nem `marin_memory.db` versionados, e o `.gitignore` já protege esses caminhos. Portanto esta é uma recomendação de higiene para os pacotes de handoff, não evidência de vazamento no repositório.

Se quiser reduzir risco nos próximos envios, gerar o pacote sem:

```text
.env
venv/
__pycache__/
.runtime/
temp_audio/
```

O `.git/` é opcional. Para nossa auditoria ele é útil, mas não é necessário se o ZIP/RAR contiver todos os fontes e você informar a versão/commit.

---

# 13. GATE FINAL DESTA AUDITORIA

## STATUS: ⛔ NÃO AVANÇAR PARA v3.5.1

Motivo principal:

> a v3.5.0 possui um caminho reproduzível em que uma reafirmação de memória pode deixar o conceito sem nenhuma versão ativa.

A arquitetura geral está correta e deve ser preservada. O agente deve executar este plano como **hardening da própria v3.5.0**, sem começar ainda Open Loops, Smart Reminders ou Adaptive Voice.

Depois das correções, gerar novo pacote/commit e submeter novamente para revisão.

---

**Fim da revisão técnica v3.5.0.**
