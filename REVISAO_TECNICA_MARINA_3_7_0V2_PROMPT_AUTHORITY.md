# REVISÃO TÉCNICA INDEPENDENTE — MARINA v3.7.0v2
## Prompt Authority / Canon / Legacy Cleanup

**Arquivo auditado:** `marin-telegram-bot-3.7.0v2.zip`  
**Tipo de revisão:** inspeção direta de código + testes executáveis no ambiente disponível  
**Gate:** ❌ **NÃO INICIAR SOAK AINDA**

---

# 1. RESUMO

O saneamento foi **substancial** e corrigiu vários problemas graves da primeira versão, mas **não está completo**.

Não encontrei um P0 de corrupção imediata no caminho principal moderno.

Porém ainda existem P1 suficientes para bloquear o soak:

1. rollback SafeCore pode reintroduzir memória/histórico pré-v3.6;
2. web/vision data channels ainda carregam instruções comportamentais;
3. ainda existem system/control prompts em português;
4. AutoPatcher ainda trata `prompts.py` deprecated como owner;
5. auditor de prompt authority produz falso verde;
6. legacy autonomous proactivity continua runtime-reachable;
7. StyleEngine fabrica "evidência aprendida do Patrick" em DB vazio;
8. pacote de validação continua incluindo `.env`, DB, logs e arquivos privados.

Há também P2 menores.

---

# 2. O QUE FOI CORRIGIDO CORRETAMENTE

Confirmado no código atual:

```text
prompts.py
→ MARIN_SYSTEM_PROMPT = None
→ EVENTOS_COTIDIANO = ()
→ deprecated compatibility shim

ContextBuilder
→ Living World ON usa WorldContextBuilder
→ Living World OFF usa SafeCore, não o monólito antigo

prompt_policy.py
→ CONTROL_EN centralizado
→ SafeCore identity
→ daypart neutro
→ photo turn constraint

WorldContextBuilder
→ World Bible / WorldState continuam autoridades

db._seed_default_profile()
→ Marina Salles
→ sem idade fixa antiga
→ sem rotina pré-v3.6

visual_profile.py
→ "young adult Brazilian woman"
→ sem 19yo hardcoded

bot.py visual director
→ reutiliza MARINA_VISUAL_DNA_BASE

sd_client.py
→ Marina_Salles_Dev

Planner / Consolidator / Session Reflector / Vision
→ primary system prompt constants migrados para inglês

runtime grep
→ sem "Marina Seltin"
→ sem "19yo woman"
→ sem antigo fixed-19 identity

top-level py_compile
→ 54 arquivos
→ 0 erros

Response Availability tests executáveis neste ambiente
→ 18/18 PASS
```

Também montei um prompt moderno real em banco temporário.

Resultado:

```text
[CONTROL RULES] em inglês
Marina Salles
birth_date = 2006-04-29
dynamic age = 20 em 2026-09-18
WorldState presente
sem antigo monolithic prompt
```

Isto confirma que o caminho principal moderno melhorou de verdade.

---

# 3. P1 — SAFECORE PODE RESSUSCITAR MEMÓRIA/HISTÓRICO PRÉ-v3.6

## Problema

No branch Living World OFF, `ContextBuilder.build_system_prompt()` usa `build_safe_core_prompt()`, mas depois ainda pode acrescentar selective memory.

Além disso, com Knowledge Privacy OFF, o payload pode incluir recent history.

Não há guarda obrigatória por:

```text
clean_canonical_start_done
```

antes de incluir esses dados.

## Reprodução independente

Em DB temporário, inseri:

```text
fato legado:
"CONTINUIDADE ANTIGA INVALIDA: Patrick e Marina moram juntos no apartamento antigo"

mensagem assistant legada:
"LEGACY INVALID: meu nome é Marina Seltin e tenho 19 anos"
```

Com:

```text
LIVING_WORLD_ENABLED = false
KNOWLEDGE_PRIVACY_ENABLED = false
MEMORY_INTELLIGENCE_ENABLED = true
```

o SafeCore voltou a carregar esses conteúdos.

## Impacto

O rollback pode:

```text
desativar Living World
→ reativar autobiografia/histórico pré-clean-start
```

Isso viola diretamente o contrato da limpeza.

## Correção

Se CLEAN_CANONICAL_START ainda não tiver sido concluído:

```text
SafeCore
→ identity/style mínimo
→ NO selective legacy memory
→ NO recent legacy history
→ NO legacy style evidence
```

Depois do clean marker:

```text
current post-reset history
→ pode ser reutilizado conforme privacy/retrieval policy
```

Adicionar teste adversarial obrigatório.

---

# 4. P1 — WEB E VISION AINDA ESCONDEM INSTRUÇÕES DENTRO DE DADOS

## Web

`bot.py` ainda monta contexto real com algo equivalente a:

```text
[DADOS REAIS ...]
...
(Use essas informações reais na sua resposta com naturalidade,
sem citar que é uma busca formal!)
```

Isto é uma instrução comportamental dentro de um data channel.

## Vision

`vision_service.format_vision_context()` ainda inclui:

```text
(INSTRUÇÃO DE RESPOSTA:
Reaja de forma 100% natural...
NUNCA diga "vejo na imagem"...)
```

## Por que isso é incorreto

O próprio control plane moderno diz que:

```text
web context
visual context
```

são dados/evidência, não instruções.

Hoje VisionService e Web lookup continuam tendo autoridade parcial sobre estilo de resposta.

## Correção

Retornar somente evidência.

Mover comportamento para:

```text
prompt_policy.py
ou
response_rhythm.py
```

em uma única autoridade.

Testar que data blocks não contenham:

```text
INSTRUÇÃO
obrigatório
reaja
use essas informações
nunca diga
```

ou equivalentes comportamentais.

---

# 5. P1 — CONTROL PLANE AINDA NÃO ESTÁ TODO EM INGLÊS

O saneamento traduziu os quatro prompts principais, mas não todos os system-role prompts.

Ainda há system messages ativas em `bot.py`, incluindo:

```text
[INSTRUÇÃO OBRIGATÓRIA DESTE TURNO]
```

para reminder offer e:

```text
[INSTRUÇÃO CRÍTICA DESTE TURNO]
```

para reminder clarification.

Também `auto_patcher.py` ainda possui `prompt_system` em português.

## Correção

Auditar **todo**:

```text
role="system"
role='system'
*_SYSTEM_PROMPT
*_PROMPT
system_instruction
```

classificar cada um e migrar control-plane ativo para inglês.

Exemplos e user-facing output continuam pt-BR.

---

# 6. P1 — AUTOPATCHER AINDA APONTA PARA `prompts.py` DEPRECATED

`auto_patcher.py` ainda trata:

```text
prompts.py
```

como owner de:

```text
personalidade
prompts
prompt base
```

e também usa `prompts.py` como fallback em `determine_target_files()`.

Isso contradiz o novo desenho, onde `prompts.py` é apenas shim deprecated.

## Risco

Se `SAFE_PATCHER_ENABLED` for ativado:

```text
/edit sobre personalidade/prompt
→ pode editar o arquivo errado
→ pode não surtir efeito
→ ou reintroduzir autoridade legada
```

## Correção

Atualizar catálogo/routing para owners reais:

```text
prompt_policy.py
world_context.py
response_rhythm.py
visual_profile.py
etc.
```

Nunca defaultar para `prompts.py`.

Manter SafePatcher OFF até isso passar.

---

# 7. P1 — O AUDITOR DE PROMPT AUTHORITY DÁ FALSO VERDE

`scripts/audit_prompt_authority.py` passou.

Mas o status dele depende essencialmente de:

```text
forbidden_hits_runtime == empty
```

Ele não detecta:

```text
- control prompt em idioma errado;
- data channel contendo instrução;
- SafeCore ressuscitando memória legada;
- AutoPatcher apontando para owner deprecated;
- legacy proactivity ainda reachable;
- StyleEngine fabricando learned-style evidence.
```

Por isso:

```text
audit_prompt_authority.py = PASS
```

não significa que Prompt Authority está aprovado.

## Correção

O script deve validar contratos, não apenas strings proibidas.

O JSON:

```text
data/prompt_authority_validation.v370.json
```

não pode ser usado como gate até isso ser corrigido.

---

# 8. P1 — LEGACY AUTONOMOUS PROACTIVITY CONTINUA REACHABLE

`bot.py` ainda tem dois caminhos:

```text
Living World ON
→ autonomous_routine_v36()

Living World OFF
→ legacy autonomous_routine()
→ build_autonomous_decision_prompt()
```

O builder antigo foi higienizado, então não inventa mais `EVENTOS_COTIDIANO`.

Isso é uma melhoria.

Mas ainda existem:

```text
duas proatividades completas em runtime
```

O caminho legado mantém regras próprias de:

```text
avatar chance
audio chance
photo behavior
fallbacks
```

## Correção recomendada

Para safe rollback:

```text
Living World OFF
→ no autonomous world-story proactivity
```

ou fazer o caminho OFF reutilizar um único mecanismo grounded/minimal.

Não reviver um segundo motor.

---

# 9. P1 — STYLE ENGINE FABRICA "EVIDÊNCIA APRENDIDA DO PATRICK"

`StyleEngine._ensure_default_style()` popula um DB vazio com valores como:

```text
kkkk count = 5
emojis predefinidos
gírias:
trampo
codar
bora
suave
fechou
```

Depois `get_style_prompt_injection()` rotula isso como:

```text
[SINCRONIA LINGUÍSTICA DO CASAL (COMO O PATRICK ESCREVE)]
```

e frases como:

```text
"Gírias que você pegou dele..."
```

## Reprodução

Após CLEAN_CANONICAL_START:

```text
estilo_linguagem = vazio
```

Ao inicializar `StyleEngine`, os defaults voltam como se fossem observações reais.

## Problema

Exemplo de estilo default:

```text
!=
evidência observada do Patrick
```

## Correção

Separar:

```text
DEFAULT_PTBR_STYLE_EXAMPLES
```

de:

```text
LEARNED_FROM_PATRICK
```

DB vazio deve gerar:

```text
no learned-style block
```

até existir quantidade real suficiente de amostras.

---

# 10. P1 PROCESS/SECURITY — O ZIP DE VALIDAÇÃO CONTINUA SUJO

O arquivo v2 enviado ainda contém:

```text
.env
marin_memory.db
log.txt
generated images
.git
Windows venv completo
scratch/ com cópias antigas
```

`.gitignore` está correto, mas o processo de ZIP não respeitou isso.

Não abri o conteúdo do `.env`.

## Riscos

```text
secret exposure
private DB exposure
private image exposure
reviewer audits stale scratch copies by mistake
huge validation archives
```

## Correção

Criar script de packaging com allowlist ou:

```text
git archive
```

mais os artefatos necessários.

Excluir explicitamente:

```text
.env
*.db
*.sqlite
.git/
venv/
scratch/
logs/
generated private images/
provider cache/
backup/
```

---

# 11. P2 — ADMIN VOICE DEFAULTS INVENTAM ESTADO

Alguns comandos admin/debug ainda usam defaults como:

```text
"boa noite"
"tô aqui na cama pensando em você"
```

independentemente de hora/WorldState.

Baixo impacto porque são comandos operacionais, mas a regra de autoridade deve ser consistente.

Corrigir para texto neutro ou usar contexto verdadeiro.

---

# 12. P2 — `memory_cli.py` AINDA TEM DEFAULT AGE `"20"`

Há fallback administrativo com idade literal.

Não é prompt principal, mas idade é dinâmica.

Derivar de `birth_date` ou omitir quando indisponível.

---

# 13. P2 — `.env.example` DUPLICA UMA FLAG

Foi encontrado:

```text
REAL_WORLD_PLACE_LOOKUP_ENABLED=false
```

duplicado.

Remover duplicata.

---

# 14. P2 — RESPONSE RHYTHM É APLICADO EM MAIS DE UM PONTO

`ContextBuilder` aplica Response Rhythm.

`bot.py` frequentemente aplica novamente.

`apply_policy()` remove o bloco anterior antes de recolocar, então **não há duplicação textual final**, mas há layering/logging redundante.

Não é blocker, mas vale simplificar para um owner claro.

---

# 15. LIMITAÇÃO DO MEU AMBIENTE DE TESTE

Consegui executar:

```text
py_compile
→ 54 files
→ 0 errors

Response Availability subset
→ 18/18 PASS

scripts/audit_prompt_authority.py
→ PASS
```

E fiz reproduções com SQLite temporário.

Não consegui executar a full suite Windows aqui porque:

```text
project venv = Windows
current execution env = Linux
system Python lacks openai/python-telegram-bot
```

Tentar usar os site-packages do venv Windows também falha por extensões compiladas incompatíveis.

Isto é limitação deste ambiente, não erro do projeto.

A full suite deve ser executada depois no ambiente Windows do projeto pelo Composer e, principalmente, pelo Codex independente.

---

# 16. GATE

Estado atual:

```text
P0 = 0 encontrados

P1:
- SafeCore stale memory/history
- instructions hidden in web/vision data
- incomplete English control-plane migration
- AutoPatcher owner stale
- prompt auditor false-green
- second legacy proactivity path
- fake learned Patrick style
- validation package contains sensitive/private files

P2:
- admin voice hardcodes
- memory_cli fixed age
- duplicate env example flag
- redundant Response Rhythm application
```

## Decisão

```text
❌ NÃO INICIAR SOAK
❌ NÃO CONSIDERAR PROMPT AUTHORITY CLEANUP CONCLUÍDO
```

O saneamento avançou bastante, mas precisa de uma segunda rodada focada.

