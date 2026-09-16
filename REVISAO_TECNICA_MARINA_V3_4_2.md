# Revisão Técnica — Marina Seltin v3.4.2
## Auditoria do pacote `marin-telegram-bot-3.4.2.zip`

## Parecer executivo

A v3.4.2 é uma melhoria real em relação à v3.4.1 e corrigiu corretamente quase todos os itens apontados na auditoria anterior.

Foram confirmados no código:

- versão centralizada atualizada para `3.4.2`;
- `MemoryConsolidationError`;
- cursor não avança mais quando a consolidação falha;
- fechamento explícito da conexão SQLite usada para WAL;
- parser temporal não transforma mais texto puramente descritivo em timestamp;
- follow-up é forçado para depois do evento;
- `MAX_TOTAL_CONTEXT_CHARS` passou a limitar o histórico;
- novos testes de cursor e parser;
- documentação e `.env.example` modernizados.

Também foram executados **52 dos 55 testes sem chamadas externas**, todos aprovados.

Apesar disso, encontrei **dois bugs funcionais reproduzíveis** que ainda impedem considerar a camada de confiabilidade 100% encerrada:

1. o lock da Smart Memory é adquirido tarde demais e ainda permite consolidação duplicada do mesmo lote;
2. a query de eventos considera `event_at` mesmo quando existe `follow_up_after`, permitindo Marina perguntar “como foi?” assim que o evento começa.

Recomendação: fazer uma pequena **v3.4.3 — Reliability Final Fixes** antes de iniciar a 3.5.

---

# 1. O QUE FOI CORRIGIDO CORRETAMENTE

## 1.1 Cursor não avança após falha da LLM

Em `memory_consolidator.py` foi criada:

```python
class MemoryConsolidationError(RuntimeError):
    ...
```

`consolidate_dialogue()` passa a retornar:

```python
"success": False
```

em falha.

E `consolidate_and_apply_async()` aborta com exceção antes de aplicar:

```python
if not consolidation.get("success", True) or consolidation.get("error"):
    raise MemoryConsolidationError(...)
```

No `bot.py`, o cursor só avança após resultado positivo:

```python
if res.get("success", True) and not res.get("error"):
    db.set_last_consolidated_conversation_id(end_id)
```

### Resultado

O antigo cenário:

```text
LLM indisponível
→ lote tratado como vazio
→ cursor avança
→ memória perdida
```

foi eliminado.

**Status: ✅ CORRIGIDO.**

---

# 2. SQLite ResourceWarnings

`db.py` agora usa:

```python
from contextlib import closing
```

e:

```python
with closing(sqlite3.connect(...)) as raw_conn:
    raw_conn.execute("PRAGMA journal_mode=WAL;")
```

Além disso, `_ManagedConnection` fecha as conexões comuns.

Foi executado nesta auditoria:

```bash
python -W error::ResourceWarning -m unittest ...
```

em um subconjunto de 23 testes intensivos em SQLite.

Resultado:

```text
23 testes
23 PASS
0 ResourceWarning
```

**Status: ✅ CORRIGIDO.**

---

# 3. Parser temporal de textos descritivos

Antes:

```text
"perguntar como foi a apresentação"
→ agora + 6 horas
```

Agora:

```python
parse_iso_or_relative_datetime(
    "perguntar como foi a apresentação"
)
```

retorna:

```python
None
```

Há testes explícitos para isso.

**Status: ✅ CORRIGIDO.**

---

# 4. Follow-up é ajustado para depois do evento

`planner.py` agora faz:

```python
expected_min_follow_up = event_at + timedelta(hours=2)
```

e, se a data de follow-up for ausente ou anterior ao evento, move para:

```text
evento + 2h
```

Exemplo testado:

```text
evento: amanhã 14h
follow_up_hint: "perguntar como foi"
→ follow-up: amanhã 16h
```

**Status da NORMALIZAÇÃO: ✅ CORRIGIDO.**

Há, porém, um bug na query SQL descrito adiante que ainda ignora parcialmente esse resultado.

---

# 5. Budget global do Context Builder

A constante:

```python
MAX_TOTAL_CONTEXT_CHARS = 64000
```

agora é efetivamente usada:

```python
remaining_budget = max(
    0,
    MAX_TOTAL_CONTEXT_CHARS - len(system_text)
)

allowed_history_chars = min(
    MAX_HISTORY_CHARS,
    remaining_budget
)
```

Isso impede que o histórico recente ultrapasse o teto após a montagem do system prompt.

**Status: ✅ CORRIGIDO.**

### Observação

O limite ainda não reserva espaço explicitamente para:

- mensagem atual do usuário;
- system message extra de pedido de foto;
- resposta gerada.

É uma melhoria futura, não um bloqueador.

---

# 6. Release/versionamento

`config.py` agora possui:

```python
APP_VERSION = "3.4.2"
VERSION_NAME = "... Memory Reliability"
```

`README.md` e `.env.example` também foram atualizados.

**Status: ✅ CORRIGIDO.**

### Pequena inconsistência

O cabeçalho de `bot.py` ainda diz:

```text
v3.4.1 Oficial Blindada
```

É somente documentação interna; atualizar para 3.4.2.

---

# 7. TESTES EXECUTADOS NESTA AUDITORIA

## 7.1 Compilação

Executado:

```bash
python -m compileall -q .
```

Resultado:

```text
PASS
```

---

## 7.2 Testes determinísticos

O projeto possui hoje:

```text
55 testes
```

Nesta auditoria foram executados **52** sem permitir qualquer chamada externa de LLM.

Incluídos:

```text
test_auto_patcher
test_context_builder
test_memory_cursor
test_planner
test_proactivity_service
test_style_engine
test_vision_service
test_visual_profile
test_wiring_auditoria
TestMemoryConsolidatorDatabase
```

Resultado:

```text
52 testes
52 PASS
```

Os 3 testes não executados são:

```text
test_casual_chitchat_is_ignored
test_real_fact_extraction
test_contradiction_detection
```

porque explicitamente usam a LLM real/OpenRouter.

---

## 7.3 Healthcheck

Neste ambiente de auditoria:

```text
22 PASS
4 FAIL
```

Os FAILs foram exclusivamente por dependências externas não instaladas aqui:

```text
openai
python-telegram-bot
```

Não representam falha lógica do código enviado.

O `venv/` contido no ZIP é Windows e não deve ser reutilizado no ambiente Linux de auditoria.

---

# P0 — BUG 1: LOCK DA SMART MEMORY AINDA TEM RACE CONDITION

O código atual faz:

```python
if MEMORY_CONSOLIDATION_LOCK.locked():
    return

last_id = db.get_last_consolidated_conversation_id()
...
lote = ...

async def _run_consolidation():
    async with MEMORY_CONSOLIDATION_LOCK:
        ...
```

O problema é:

> o lote é lido ANTES de adquirir o lock.

Duas chamadas de `check_and_trigger_memory_consolidation()` podem ocorrer no mesmo tick do event loop.

Ambas veem:

```text
lock = unlocked
cursor = 0
lote = IDs 1..8
```

Depois são criadas duas tasks.

A primeira pega o lock.

A segunda espera.

Quando a primeira termina, a segunda pega o lock — mas já carrega em seu closure o lote antigo `1..8`.

---

## Reprodução real realizada nesta auditoria

Foram disparadas simultaneamente:

```python
await asyncio.gather(
    check_and_trigger_memory_consolidation(),
    check_and_trigger_memory_consolidation()
)
```

Resultado observado:

```text
calls = [(1, 8), (1, 8)]
cursor = 8
```

Logs:

```text
Consolidação concluída IDs 1..8
Consolidação concluída IDs 1..8
```

Portanto o mesmo lote foi processado duas vezes.

Isso pode gerar:

```text
fatos duplicados
resumos duplicados
momentos duplicados
efeitos contraditórios
custo dobrado de LLM
```

---

# CORREÇÃO CERTA DO LOCK

Mover TODA a decisão para dentro do lock.

Em vez de:

```python
if lock.locked():
    return

last_id = ...
lote = ...

create_task(
    async with lock:
        process(lote)
)
```

usar:

```python
async def _run_consolidation():
    async with MEMORY_CONSOLIDATION_LOCK:

        # RECALCULA tudo depois de adquirir o lock
        last_id = db.get_last_consolidated_conversation_id()
        novas_count = db.contar_conversas_desde(last_id)

        if novas_count < batch_size:
            return

        mensagens = db.get_conversas_desde(last_id, limit=50)
        ...

        result = await consolidator...

        if success:
            set_cursor(end_id)
```

E o método público pode apenas:

```python
if MEMORY_CONSOLIDATION_LOCK.locked():
    return

asyncio.create_task(_run_consolidation())
```

Ainda melhor: não confiar em `locked()` para correção. Ele é apenas otimização.

A garantia deve ser:

```text
snapshot + processamento + atualização de cursor
```

inteiros dentro da região crítica.

---

# TESTE NECESSÁRIO

O teste atual:

```python
test_memory_consolidation_lock
```

só valida:

```text
lock.locked() == True dentro do context manager
```

Isso testa o `asyncio.Lock`, não a lógica da Marina.

Substituir/adicionar teste de integração:

```text
cursor inicial = 0
8 mensagens

disparar check_and_trigger duas vezes simultaneamente

esperar tasks

assert consolidator.calls == 1
assert processed_ranges == [(1, 8)]
assert cursor == 8
```

Esse teste falha na v3.4.2 atual e deve passar após o fix.

---

# P0 — BUG 2: FOLLOW-UP PODE SER DISPARADO NO INÍCIO DO EVENTO

`db.py` atualmente usa:

```sql
WHERE status = 'pending' AND (
    (follow_up_after IS NOT NULL AND follow_up_after <= ?)
    OR
    (event_at IS NOT NULL AND event_at <= ?)
)
```

Isso significa:

```text
evento = 14:00
follow_up = 16:00
agora = 14:01
```

A segunda condição é verdadeira:

```text
event_at <= agora
```

Logo o evento já aparece como pronto para follow-up.

Isso anula a melhoria do Planner que adicionou `+2h`.

---

## Reprodução real desta auditoria

Evento inserido:

```text
event_at        = 2026-09-16T14:00:00
follow_up_after = 2026-09-16T16:00:00
```

Consulta às:

```text
2026-09-16T14:01:00
```

Resultado:

```text
evento RETORNADO
```

Quando o correto seria:

```text
nenhum evento
```

Consulta às:

```text
16:01
```

deve então retornar.

---

# CORREÇÃO SQL

Usar `follow_up_after` quando ele existir.

Só usar `event_at` como fallback quando não houver follow-up definido:

```sql
WHERE status = 'pending'
AND (
    (
        follow_up_after IS NOT NULL
        AND follow_up_after <= ?
    )
    OR
    (
        follow_up_after IS NULL
        AND event_at IS NOT NULL
        AND event_at <= ?
    )
)
```

---

# TESTE NECESSÁRIO

Adicionar:

```text
evento = 14:00
follow_up = 16:00

query 13:59 → 0 resultados
query 14:01 → 0 resultados
query 15:59 → 0 resultados
query 16:01 → 1 resultado
```

Esse teste deve ser considerado obrigatório.

---

# P1 — EVENTOS SEM DATA PARSEÁVEL AINDA GANHAM +4H

Em:

```python
event_at_iso = parse_iso_or_relative_datetime(
    raw_event_at,
    default_offset_hours=4
)
```

se o Planner retorna algo como:

```text
"semana que vem"
```

o parser atual não entende essa expressão.

Como `default_offset_hours=4`, o evento acaba virando:

```text
agora + 4 horas
```

Isso pode transformar:

```text
"semana que vem vou viajar"
```

em um evento para hoje.

---

## Recomendação

Para `event_at`, também evitar fallback artificial.

Preferir:

```python
event_at_iso = parse_iso_or_relative_datetime(
    raw_event_at,
    default_offset_hours=None
)
```

Se não for possível parsear:

Opção A:

```text
não criar evento ainda
```

Opção B, melhor:

salvar:

```text
event_at = NULL
raw_time_expression = "semana que vem"
```

e deixar um resolvedor posterior completar quando houver informação suficiente.

Também vale adicionar suporte a:

```text
semana que vem
mês que vem
fim de semana
segunda que vem
à tarde
à noite
de manhã
```

---

# P1 — FOLLOW-UP PROMPT AINDA ESTÁ EMBUTIDO NA DESCRIPTION

O Planner produz:

```json
"follow_up_prompt": "Como foi a reunião?"
```

Mas o banco não possui uma coluna própria.

O código concatena:

```python
description = (
    "Reunião | Follow-up: Como foi a reunião?"
)
```

Funciona, mas mistura:

```text
o que aconteceu
+
como Marina deve perguntar depois
```

Recomendação para migration futura:

```sql
ALTER TABLE eventos_pendentes
ADD COLUMN follow_up_prompt TEXT;
```

E manter:

```text
description
event_at
follow_up_after
follow_up_prompt
```

separados.

---

# P1 — BACKLOG DA SMART MEMORY PROCESSA NO MÁXIMO 50 POR DISPARO

O cursor usa:

```python
get_conversas_desde(last_id, limit=50)
```

Isso é bom para controlar tamanho.

Mas após processar as primeiras 50 mensagens, ele não agenda automaticamente o próximo bloco.

Depende de outra interação do usuário para chamar novamente:

```python
check_and_trigger_memory_consolidation()
```

No snapshot enviado:

```text
conversas: 70
cursor: 0
```

Isso provavelmente só significa que o ZIP foi empacotado antes de a nova versão consumir o backlog.

Porém, quando rodar:

```text
primeiro trigger → 50 mensagens
cursor → 50
20 permanecem
```

Se Patrick não enviar outra mensagem depois, as 20 ficam pendentes.

---

## Melhoria

Após uma consolidação bem-sucedida:

```python
while pending >= batch_size:
    processar próximo chunk
```

com um limite de segurança, por exemplo:

```text
máximo 3 chunks por worker
```

Ou iniciar um único worker de memória que drena a fila.

---

# P1 — RETRIEVAL CONTINUA PARCIAL

A infraestrutura possui FTS para:

```text
fatos
momentos
resumos
```

Mas `MemoryRetriever` continua usando FTS apenas para fatos.

Momentos:

```text
últimos registros
```

Resumos:

```text
mais recentes
```

Isso ainda é adequado com banco pequeno, mas será o primeiro gargalo da v3.5.

Recomendação para a 3.5:

```text
buscar_momentos_fts()
buscar_resumos_fts()
ranking híbrido
```

---

# P1 — CONSOLIDATOR AINDA INJETA TODOS OS FATOS ATIVOS

Ainda existe:

```python
existing_facts = db.get_fatos_patrick_detalhados(
    active_only=True
)
```

Com 4 fatos não importa.

Com 500 ou 2.000, o prompt de consolidação crescerá sem limite.

Essa é uma melhoria clara da próxima fase:

```text
lote atual
→ extrai keywords
→ retrieval de 10–20 fatos candidatos
→ adiciona somente memórias core globais
→ consolidator
```

---

# AUTO-PATCHER — ESTADO NA 3.4.2

A 3.4.2 não tentou resolver os pontos maiores do Auto-Patcher, o que é aceitável porque a release focou Memory Reliability.

Continuam pendentes:

## Arquivo inteiro

A LLM ainda recebe e devolve:

```text
arquivo Python completo
```

O diff é calculado somente depois.

## Health check pós-restart

O patch ainda é marcado:

```text
applied
```

antes de provar que a nova instância conseguiu iniciar completamente.

## Escrita não é atomic replace

Ainda usa:

```python
original_file.write_text(new_code)
```

em sequência.

Existe rollback, mas não `os.replace()` transacional.

## Patch planning

A seleção de arquivos continua principalmente heurística.

Esses pontos podem virar uma futura:

```text
Marina 3.6 — Safe Self-Evolution
```

Não precisam bloquear a 3.5 se o `/edit` permanecer sob feature flag e uso controlado.

---

# README: "55 TESTES OFFLINE"

O README afirma:

```text
55 testes unitários e de integração offline
```

Mas `tests/test_memory_consolidator.py` possui explicitamente:

```text
3 testes com chamadas reais ao modelo LLM configurado
```

Eles não são offline nem determinísticos.

A contagem total 55 está correta.

A descrição deve mudar para algo como:

```text
52 testes determinísticos/offline
+ 3 testes de integração LLM
```

---

# PACOTE AINDA CONTÉM DADOS QUE NÃO DEVERIAM IR EM RELEASE

O ZIP continua contendo:

```text
.env
.git/
venv/
marin_memory.db
.runtime/
scratch/
log.txt
```

Tamanho observado somente do:

```text
venv ≈ 179 MB
```

O `.gitignore` foi melhorado, mas ele não afeta ZIPs criados manualmente.

Ainda recomendo criar:

```text
package_release.py
```

usando whitelist.

Exemplo:

```text
INCLUIR:
*.py
migrations/
tests/
requirements.txt
README.md
.env.example
*.service
setup_vps.sh

EXCLUIR:
.env
.git/
venv/
*.db
.runtime/
scratch/
*.log
__pycache__/
arquivos temporários
```

---

# DOCUMENTAÇÃO DESATUALIZADA

`walkthrough.md` ainda contém textos de versões anteriores, inclusive:

```text
planner.plan_response()
```

no trecho da integração de fotos.

O código está correto (`plan_message()`), mas documentação antiga pode confundir um agente futuro.

O cabeçalho de `bot.py` também ainda diz:

```text
v3.4.1
```

Atualizar ambos.

---

# MATRIZ DA v3.4.2

| Item da auditoria 3.4.1 | v3.4.2 |
|---|---|
| Cursor avança se consolidator falha | ✅ Corrigido |
| Consolidação concorrente | ❌ Lock existe, mas lote é capturado antes dele |
| Parser transforma texto em horário falso | ✅ Corrigido para follow-up |
| Follow-up pode ficar antes do evento | ✅ Planner corrigido |
| Query respeita `follow_up_after` | ❌ Ainda dispara pelo `event_at` |
| SQLite raw connection não fecha | ✅ Corrigido |
| `MAX_TOTAL_CONTEXT_CHARS` sem uso | ✅ Corrigido |
| APP_VERSION incorreta | ✅ Corrigido |
| FTS de momentos/resumos | ⏳ Próxima fase |
| Consolidator recebe todos fatos | ⏳ Próxima fase |
| Auto-Patcher arquivo inteiro | ⏳ Pendente |
| Health check pós-restart | ⏳ Pendente |
| ZIP limpo | ❌ Pendente |

---

# RECOMENDAÇÃO: v3.4.3 — RELIABILITY FINAL FIXES

Eu faria somente este micro-patch antes da 3.5:

```text
[ ] mover leitura de cursor/lote para DENTRO do MEMORY_CONSOLIDATION_LOCK
[ ] adicionar teste de duas chamadas simultâneas processando só uma vez
[ ] corrigir query SQL para priorizar follow_up_after
[ ] adicionar teste 14:01 vs follow-up 16:00
[ ] remover fallback +4h de event_at não parseável
[ ] corrigir cabeçalho v3.4.1 do bot.py
[ ] atualizar README: 52 offline + 3 integração LLM
[ ] atualizar walkthrough antigo
```

Opcional, mas recomendado:

```text
[ ] drenar automaticamente backlog em múltiplos chunks
[ ] criar package_release.py
```

---

# DEPOIS DISSO: MARINA 3.5

Após a v3.4.3, considero razoável começar a evolução funcional novamente.

Minha prioridade para a 3.5 seria:

## Marina 3.5 — Memory Intelligence

1. **Core Memories**
   - fatos extremamente importantes;
   - identidade do relacionamento;
   - preferências centrais;
   - nunca depender apenas de recência.

2. **FTS completo**
   - fatos;
   - momentos;
   - resumos.

3. **Ranking híbrido**
   - relevância lexical/semântica;
   - importância;
   - confiança;
   - recência;
   - frequência de acesso.

4. **Selective Consolidation Candidates**
   - não mandar todos os fatos ativos ao consolidator.

5. **Deduplicação semântica**
   - detectar memórias equivalentes escritas de formas diferentes.

6. **Confidence decay**
   - fatos antigos e nunca reafirmados podem perder confiança.

7. **Open Loops**
   - promessas;
   - coisas que Patrick ficou de fazer;
   - perguntas que ficaram sem resposta;
   - assuntos que Marina quer retomar.

8. **Session reflection**
   - consolidar sessões inteiras em vez de apenas lotes mecânicos.

---

# VEREDITO

A v3.4.2 está **muito próxima** de fechar a fundação 3.x.

Ela corrigiu de verdade:

```text
falha do cursor
parser temporal
SQLite
context budget
versionamento
testes de regressão
```

e a suíte determinística está saudável:

```text
52 / 52 PASS
```

Mas os dois bugs reproduzidos nesta auditoria ainda são importantes o suficiente para justificar um último micro-patch:

```text
1. race condition do lock
2. follow-up disparado pelo event_at antes do follow_up_after
```

Corrigidos esses dois, eu consideraria a Marina pronta para sair da fase de estabilização e entrar na **3.5 — Memory Intelligence**.
