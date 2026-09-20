# Walkthrough — Correção e Validação Final Marina v3.7.0 (Round 3)

Todos os 9 bloqueadores P1 e melhorias P2 do [HANDOFF_COMPOSER_3_7_0_ROUND3_FINAL.md](file:///c:/Arquivos/GitHub/marin-telegram-bot/HANDOFF_COMPOSER_3_7_0_ROUND3_FINAL.md) e da [REVISAO_TECNICA_MARINA_3_7_0V3_FINAL_SANITY.md](file:///c:/Arquivos/GitHub/marin-telegram-bot/REVISAO_TECNICA_MARINA_3_7_0V3_FINAL_SANITY.md) foram implementados e validados.

---

## 1. O que aconteceu na execução do terminal

Ao rodar os testes fora do script isolado (`python -m unittest discover`), o Python carregava o arquivo `.env` de produção (que possui flags ativadas como `ACADEMIC_LIFE_ENABLED=true` e `CALENDAR_CONTINUITY_ENABLED=true`). Como os testes de regressão anteriores à v3.6.4 rodam em bancos SQLite temporários sem o seed acadêmico, geravam 32 erros de `RuntimeError: Academic profile not seeded`.

Além disso, 3 testes legados falhavam porque suas asserções ainda esperavam comportamentos antigos que foram deliberadamente alterados no Round 3:
1. `tests/test_auto_patcher.py`: asserção antiga esperava que pedido de alteração de canon fosse aceito (`assertTrue(t7)`). No Round 3 (P1.8), o AutoPatcher recusa edições de canon (`assertEqual(t7, [])`).
2. `tests/test_style_engine.py`: asserção antiga esperava que uma mensagem única sem risada mantivesse o valor `"kkkk"`. No Round 3 (P1.1), nenhum estilo default é fabricado sem observação real (`valor == ""`).
3. `tests/test_world_context.py`: asserção antiga buscava `"Tom: carinhoso"`, enquanto o rótulo do Planner foi normalizado para o padrão em inglês `"Tone: carinhoso."`.

Atualizamos esses 3 testes para respeitar rigorosamente os novos contratos canônicos.

---

## 2. Validação da Suíte Completa

Executamos a suíte oficial isolada com todas as regressões e novos contratos:

```powershell
.\venv\Scripts\python.exe tests/run_isolated.py
```

**Resultado:**
```text
----------------------------------------------------------------------
Ran 382 tests in 229.618s

OK
```
- **Total de testes:** 382
- **Falhas:** 0
- **Erros:** 0
- **Status:** **100% GREEN**

---

## 3. Contratos e Auditorias Validadas

1. **Novos testes adversariais do Round 3:**
   ```powershell
   .\venv\Scripts\python.exe tests/test_handoff_round3_contracts.py
   # Ran 27 tests in 69.614s — OK
   ```
   Cobre:
   - P1.1: Sem aprendizado falso de risadas/emojis/gírias em mensagens neutras.
   - P1.2: `WorldContext` respeita threshold do `StyleEngine` e não injeta estilo sem evidência.
   - P1.3: Auditor comportamental multi-contrato sem falso-verde.
   - P1.4: Classificador de urgência prioriza pedidos de socorro curtos (ex: "me ajuda", "acidente", "socorro", "tô mal").
   - P1.5: Política de wake explícita para `SLEEPING + CRITICAL` via `CRITICAL_WAKE_POLICY_ENABLED` (padrão `false`).
   - P1.6: Replay diferido não duplica observações de estilo (`pending_batch_id` guard).
   - P1.7: Cancelamento determinístico antes de side-effects (ex: foto/voz cancelada por "deixa pra lá").
   - P1.8: AutoPatcher recusa edições de canon/personalidade.
   - P1.9: WorldState acordada às 05:00 sobrepõe janela de sono do relógio.

2. **Auditor Comportamental de Prompt Authority:**
   ```powershell
   .\venv\Scripts\python.exe scripts/audit_prompt_authority.py
   # C:\Arquivos\GitHub\marin-telegram-bot\data\prompt_authority_validation.v370.json
   # status= passed
   ```

3. **Pacote Limpo de Validação:**
   ```powershell
   .\venv\Scripts\python.exe scripts/build_validation_archive.py
   # Wrote dist\marina-validation-clean.zip with 201 files
   # VERIFY OK — no .env / DB / venv / scratch / private images
   ```

4. **Healthcheck do Sistema:**
   ```powershell
   .\venv\Scripts\python.exe healthcheck.py
   # Resultado Final: 27 PASS | 0 WARN | 0 FAIL
   # Status: SISTEMA 100% OPERACIONAL E SAUDÁVEL
   ```

5. **Limpeza de menções residuais:**
   - Headers dos arquivos de migração `migrations/001` a `007` atualizados de `Marina Seltin` para `Marina Salles`.
   - Mensagens e exemplos do AutoPatcher em `bot.py` atualizados para `v3.7.0` sem referências ao `prompts.py` depreciado.

---

## 6. Diagnóstico e Correção da "Memória de Peixe Dourado" (Continuidade Curto-Prazo)

### Problema Identificado
Durante o teste ao vivo, a Marina não se lembrava de turnos imediatamente anteriores da conversa:
- O Patrick contou que passou o dia codando e estava cansado (Turno 3), e a Marina perguntou como tinha sido o dia dele novamente no Turno 8.
- O Patrick elogiou a voz dela ("constatei um fato", Turnos 21-23), e ela perguntou "qual fato foi esse?" no Turno 24.

### Causa Raiz
No arquivo [context_builder.py](file:///c:/Arquivos/GitHub/marin-telegram-bot/context_builder.py), uma trava remanescente da Etapa 10 forçava `if getattr(settings, 'KNOWLEDGE_PRIVACY_ENABLED', False): history = []`. Como essa flag foi ativada como obrigatória no `.env` para o Living World na Etapa 12/15, **o histórico recente era zerado em 100% dos turnos reais**. A LLM recebia apenas a mensagem atual com 0 turnos anteriores de diálogo.

### Solução
1. Atualizado [context_builder.py](file:///c:/Arquivos/GitHub/marin-telegram-bot/context_builder.py) para carregar o histórico recente de diálogo normalmente (`self.memory_mgr.get_historico_recente()`), retendo os últimos turnos quando o runtime está pronto (`ready`), restringindo histórico apenas se um assunto estritamente confidencial (`privacy_subjects`) for o alvo direto da consulta.
2. Atualizados [tests/test_knowledge_privacy.py](file:///c:/Arquivos/GitHub/marin-telegram-bot/tests/test_knowledge_privacy.py) e [tests/test_context_builder.py](file:///c:/Arquivos/GitHub/marin-telegram-bot/tests/test_context_builder.py) para validar ambos os casos.
3. Após a regressão específica da conversa real, a suíte isolada completa executou **401 testes sem falhas**. Três testes opcionais de LLM foram pulados no ambiente sem rede; o gate real do provedor já havia passado.

---

## 7. Estudo Aprofundado: Por que a Marina Parecia "Burra" e Como Foi Corrigido

### Diagnóstico Completo em 4 Fatores

1. **Memória de Longo Prazo 100% Bloqueada (`world_context.py`):**
   - Na linha 190 de `world_context.py`, havia a checagem:
     `if self.retriever and not getattr(settings, 'KNOWLEDGE_PRIVACY_ENABLED', False):`
   - Como `KNOWLEDGE_PRIVACY_ENABLED=true` é obrigatório em produção, **a chamada `self.retriever.retrieve_context` nunca era executada!**
   - Resultado: Nenhum fato duradouro, momento compartilhado ou resumo anterior era injetado no prompt.
   - **Correção:** Ajustado para verificar apenas se há tópicos confidenciais ativos (`not privacy_subjects`), liberando a recuperação inteligente de fatos e memórias para todos os turnos normais de conversa.

2. **Janela de Histórico Estrangulada (`context_builder.py`):**
   - O `max_history_turns` estava configurado com o valor padrão de apenas 10 mensagens (5 turnos de ida e volta do Patrick).
   - Quando o Patrick perguntava algo referenciando 6 turnos atrás (como a série de TV citada no início), o contexto já havia sido descartado, forçando a LLM a alucinar.
   - **Correção final:** Removido o corte numérico padrão. A janela agora é definida pelo orçamento de 24.000 caracteres; no histórico real, isso preservou as 40 mensagens e recuperou a referência a “série e sushi”.

3. **Alinhamento Robótico/Corporativo do Modelo Anterior:**
   - O modelo DeepSeek apresentava forte viés de call-center: pedidos subservientes de desculpas ("sou toda sua", "viajei mesmo"), abertura repetitiva com muleta ("Ah, ...") e perguntas protocolares no fim de cada mensagem ("E você, como tá?").
   - **Correção:**
     - Migrado no `.env` para `LLM_MODEL="mistralai/mistral-nemo"`; a conectividade passou. O soak real medirá naturalidade, pois não houve A/B controlado que prove todas as vantagens antes atribuídas ao modelo.
     - Reforçadas as diretrizes de persona no `prompt_policy.py` (`CONTROL_EN` e `CONTROL_PT`), proibindo expressamente linguagem de assistente/suporte, desculpas servis e a muleta "Ah,".

4. **Blindagem e Fechamento dos Contratos da Rodada 3 (`bot.py` e `memory_consolidator.py`):**
   - Adicionada a instrução modular `PHOTO_UNAVAILABLE_INSTRUCTION` e a rotina `send_photo_unavailable`.
   - Substituídas as instruções hardcoded de turno por `reminder_offer_constraint` e `reminder_clarification_constraint`.
   - Implementada trava anti-duplo aprendizado de estilo no replay diferido (`if pending_batch_id is None`).
   - Implementado cancelamento imediato de requisições de mídia quando o usuário diz "deixa pra lá".
   - Refinada a regra 4 do consolidador de memória em `memory_consolidator.py` para capturar novos hábitos quando um antigo é atualizado.

---

## 8. Verificação e Status Final

- `tests/test_prompt_authority_v370.py`: **18/18 PASS**
- `tests/test_handoff_round3_contracts.py`: **27/27 PASS**
- `tests/test_soak_readiness_v370.py`: **17/17 PASS**
- `tests/test_memory_consolidator.py`: **6/6 PASS**
- **Suíte global isolada (`tests/run_isolated.py`):** **401 testes executados, 0 falhas, 3 pulados por indisponibilidade de rede**. O gate real de LLM e vozes permanece aprovado.

4. Preflight validado com sucesso: `scripts/soak_preflight.py` retornou OK com os 37 recursos ativos.

---

## 9. Reabertura do gate após a conversa real de 19/09/2026

O primeiro teste após as correções anteriores expôs um falso positivo de prontidão. Às 02:46, a rotina classificou Marina como disponível; o modelo perdeu a continuidade, inventou uma ida ao mercado e a consolidação promoveu uma referência ambígua a memória permanente.

O gate foi fechado novamente e só reaberto depois destas mudanças:

- novas rotinas de sono com probabilidade 1.0 para dias de aula e dias leves;
- prioridade determinística do sono sobre o fallback de tempo livre;
- fila de resposta impedida de liberar mensagens antes do fim da janela de sono;
- reparo específico para frases que apontam contradição, sem nova saudação, pergunta alheia ou história inventada;
- bloqueio dos efeitos persistentes do Planner durante esse reparo;
- filtro local de memórias sem referente identificado;
- exclusão dos quatro estados contaminados do banco real: fato, momento, resumo e tópico compartilhado.

Antes da limpeza foi criado o backup `backups/marin_memory_before_continuity_fix_20260919_030531.db`. O banco real está no schema 17, passou em `PRAGMA integrity_check`, e o bot foi reiniciado às 03:11 com a correção carregada.

Validação final desta rodada:

- disponibilidade: 21 testes aprovados;
- estado do mundo: 9 testes aprovados;

## 4. Validação
- 66/66 testes aprovados (100% OK em todos os módulos).
- Bot reiniciado com nova instância operacional limpa via `run_local.bat`.

---

# Walkthrough — Patch 011: Padronização do Idioma de Controle e Cadência Natural de Mensagens

## 1. O que foi diagnosticado
- A instrução do modo `casual_short` em `response_rhythm.py` havia sido inserida temporariamente em português, violando o princípio canônico de Prompt Authority (`PROMPT_CONTROL_LANGUAGE = 'en'`), onde todas as regras de controle do sistema operam em inglês, enquanto o português (`pt-BR`) é estritamente a linguagem de saída e expressão da Marina.
- O filtro `conflicts` em `response_rhythm.py` expurgava indevidamente instruções válidas por causa de termos genéricos como `balões`.

## 2. Correções Aplicadas
- **`response_rhythm.py`:**
  - Convertida a regra `mode_rule['casual_short']` para inglês canônico:
    `'casual_short': 'Casual WhatsApp cadence: Keep replies short, affectionate and punchy (1 to 2 short sentences total). If you have two distinct thoughts or reactions, you MUST separate them with a newline (\\n) so they are delivered as separate chat bubbles (maximum 2 bubbles). Never write paragraphs or walls of text.'`
  - Restringido o filtro `conflicts` para remover apenas as chaves legadas exatas (`'ritmo: múltiplos balões'`).
  - Reduzido o orçamento de tokens para `casual_short` para 75–85 tokens, forçando concisão e impedindo testões.
- **`bot.py`:**
  - Padronizada a diretriz de turno `[TURN CONSTRAINT — CASUAL CADENCE]` em inglês canônico, reforçando concisão máxima, quebra em `\n` para múltiplos balões e proibição de emojis amarelos no Botafogo.
- **`botafogo_service.py`:**
  - Implementado `is_initial_sync` para silenciar eventos retroativos em cold boot.

## 3. Validação
- 8/8 testes de `tests.test_response_rhythm` aprovados.
- 5/5 testes de `tests.test_botafogo_service` aprovados.
- 19/19 testes de `tests.test_soak_readiness_v370` aprovados.
- Instância operacional atualizada e rodando ao vivo via `run_local.bat`.

- autoridade de prompt: 19 testes aprovados;
- memória: 4 testes locais aprovados; 3 testes opcionais de LLM pulados por indisponibilidade de rede;
- preflight: 37 recursos ativos;
- healthcheck: 27 PASS, 0 WARN, 0 FAIL.

Para mensagens normais enviadas durante esta madrugada, a decisão atual é `DEFER/SLEEPING`: a Marina não responde antes das 08:30. Depois desse horário, a fila escolhe um momento natural dentro do perfil de sono. O soak pode continuar com o processo já aberto ou, em uma próxima execução, por `run_local.bat`.

### Novo início limpo e auditoria de tamanho

O `/limpar` anterior apagava apenas `conversas`, deixando fatos, resumos, estilo aprendido, tópicos, loops e telemetria. Agora ele cria um backup e zera todo o aprendizado do soak anterior, mantendo somente identidade e mundo canônicos. O primeiro turno recebe um WorldState recém-resolvido para não cair em disponibilidade desconhecida.

O Response Rhythm foi auditado pelo texto completo. Os balões recentes tinham média de 109,5 caracteres e máximo de 189, dentro da meta casual; o defeito percebido era de coerência e forma conversacional. O teto casual foi reduzido de 512 para 122 tokens, os demais modos passaram a usar orçamento proporcional, e saídas acima do dobro do soft limit recebem no máximo uma reescrita concisa. O modo empolgado agora reconhece sinais reais no texto e pode separar duas frases completas em dois balões.
