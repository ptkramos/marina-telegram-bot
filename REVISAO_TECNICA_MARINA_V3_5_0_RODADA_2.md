# Revisão técnica Marina v3.5.0 — rodada 2

> Atualização posterior: as correções locais e sua validação estão em [VALIDACAO_CORRECOES_MARINA_V3_5_0_RODADA_2.md](VALIDACAO_CORRECOES_MARINA_V3_5_0_RODADA_2.md). O diagnóstico abaixo descreve o commit original auditado e foi preservado como histórico.

**Data:** 16/09/2026.  
**Commit auditado:** `feae4d0054aec409bd7d6b21cb8f0eb9f5c9269e`.  
**Comparação:** `ebfa3f5` → `feae4d0`, confrontada com `REVISAO_TECNICA_MARINA_V3_5_0.md`.  
**Gate: NÃO APROVADA para avançar à 3.5.1.**

O caso original de `same` com texto idêntico foi corrigido, e a operação isolada de replacement preserva o antigo diante de colisão UNIQUE. Porém, continuam existindo caminhos reproduzíveis que desativam memória sem substituição e que permitem alterar fatos fora dos candidatos apresentados à LLM. O hardening precisa de mais uma rodada, sem reescrever a arquitetura.

Esta revisão não alterou a implementação, os testes versionados ou o banco real. A exclusão local preexistente de `REVISAO_TECNICA_MARINA_V3_4_2.md` foi preservada.

## 1. Método e evidências

- Cópia dos fontes Python, migrations e testes para `scratch/review_350_round2/`, sem copiar `.env` ou `marin_memory.db`.
- Python 3.10.11 do `venv` existente, com dependências reais instaladas.
- Configuração fictícia para imports e healthcheck; sem polling Telegram nem chamadas à LLM real.
- Testes independentes com SQLite real descartável e respostas JSON controladas no transporte da LLM. O caminho `consolidate_dialogue` → `apply_consolidation` é exercitado nos casos de mutação.
- `compileall` da cópia isolada passou.
- Healthcheck isolado: **28 PASS, 0 WARN, 0 FAIL**. Isso valida imports, estrutura e configuração sintética; não atesta credenciais, serviços externos ou banco de produção.
- Reproduções adicionais: **9 testes, 8 falhas de invariantes esperados, 1 sucesso**. As oito falhas comprovam os cenários abaixo; não são oito novos bugs independentes, pois algumas compartilham a mesma causa.
- Resultado final da suíte existente registrado ao final deste documento.

Arquivos locais de evidência:

- `scratch/review_350_round2/audit_runner.py`: execução offline da suíte e healthcheck.
- `scratch/review_350_round2/audit_regressions.py`: reproduções desta auditoria.
- `scratch/review_350_round2/suite_final.log`: resultado final da suíte existente.
- `scratch/review_350_round2/regressions_final.log`: oito invariantes violados e o controle positivo.
- `scratch/review_350_round2/health.log`: healthcheck.

Esses arquivos estão em `scratch`, ignorado pelo Git. Para entregar apenas este Markdown ao agente, os cenários, contratos e correções estão descritos abaixo.

## 2. [P1 — bloqueador] Allowlist continua permitindo mutação fora dos candidatos

**Locais:** `memory_consolidator.py:210`, `:221`, `:274`, `:296–298`, `:315–326`.

### Evidências reproduzidas

1. Candidato permitido A; LLM retorna `same` com ID B, que não foi apresentado. O código emite warning rejeitando B, mas o fallback das linhas 297–298 atribui novamente `target_id = existing_id`. Resultado: **B recebe `confirmation_count += 1`**.
2. Candidato A legado, sem `canonical_key`; B tem chave `protected`. O conjunto de chaves permitido é vazio. A LLM retorna `keys_to_deactivate=["protected"]`. Resultado: **B é desativado**, porque `if candidate_keys and ...` não protege quando o conjunto está vazio.
3. Nenhum candidato apresentado; LLM retorna um ID existente em `facts_to_deactivate`. Resultado: **o fato é desativado** pelo mesmo padrão de guarda condicional.

Os caminhos de `same` e `update/contradiction` também contêm `not candidate_ids` como autorização, identificado na leitura de código.

### Correção exigida

- Allowlist vazia significa **nenhum alvo autorizado**, nunca autorização irrestrita.
- Exigir pertencimento para toda mutação de fatos existentes, inclusive reafirmação.
- Remover o fallback que reutiliza um ID previamente rejeitado. Não deixar exceção de segurança em código de produção para facilitar testes diretos.
- Quando houver ID explícito inválido/fora da lista, aplicar NO-OP com warning. Resolver por chave/texto somente quando o ID estiver ausente, entre candidatos válidos e sem ambiguidade.
- Validar IDs como inteiros positivos, excluindo booleanos, floats, listas e objetos.
- Resolver desativação por chave para os IDs candidatos autorizados; não ampliar a mutação para registros que não foram apresentados apenas porque compartilham uma chave.
- Ajustar os testes legados diretos para fornecer o contrato interno de candidatos, em vez de relaxar a proteção.

**Aceitação:** snapshots dos fatos não candidatos permanecem idênticos para `same`, `update`, `contradiction`, desativação por ID e por chave, com allowlists vazias e não vazias.

## 3. [P1 — bloqueador] Desativação antecipada ainda pode deixar zero versões ativas

**Locais:** `memory_consolidator.py:205–225` e `:312–349`.

Reprodução: um fato ativo `Patrick joga FFXIV`, chave `game`, é candidato autorizado. A resposta inclui simultaneamente:

```json
{
  "facts_to_deactivate": [{"existing_fact_id": 5}],
  "facts_to_create": [{
    "decision": "update",
    "existing_fact_id": 5,
    "fato": "Patrick joga GW2",
    "canonical_key": "game"
  }]
}
```

O ID 5 é ilustrativo: deve ser substituído pelo ID criado no teste.

**Resultado observado:** a desativação é commitada primeiro. `substituir_fato_atomicamente()` encontra o antigo já inativo e retorna `None`; nenhuma nova memória é criada. Restam **zero fatos ativos para `game`**. O warning ainda diz que o original foi preservado, embora já tenha sido desativado.

Não basta tornar o método do DB atômico se o dispatcher faz uma escrita destrutiva antes dele. O teste LLM legado `test_contradiction_detection` inclusive espera desativação separada, em conflito com o novo contrato por decisão.

### Correção exigida

- Validar e reconciliar todas as operações do payload antes de gravar.
- Para um alvo em `update/contradiction`, executar apenas replacement atômico; remover/rejeitar a desativação redundante por ID ou chave.
- Rejeitar conflitos entre `same/ignore` e revogação do mesmo alvo, ou definir uma regra explícita e testada sem perder memória acidentalmente.
- Manter revogação explícita independente funcionando para candidatos autorizados.
- Não retornar sucesso irrestrito para falhas que deveriam impedir avanço do cursor; distinguir NO-OP intencional de lote inválido/falha de persistência.

**Aceitação:** `deactivate + update` e `deactivate + contradiction`, tanto por ID como por chave, mantêm uma versão ativa; falha de insert preserva o antigo. Uma revogação isolada válida continua desativando corretamente.

## 4. [P1] Validação estrutural da resposta ocorre depois de escritas

**Locais:** `memory_consolidator.py:148–159`, `:205–230`, `:376–399`.

Enums e números de fatos receberam validação parcial, mas o formato dos containers e itens continua sendo assumido. Exemplos aceitos pelo parser JSON: `facts_to_create=null`, um item não objeto, `fato=123`, IDs de tipos inválidos e momentos de estrutura inválida.

**Reprodução:** payload com desativação autorizada e depois `facts_to_create=[{"fato":123,"decision":"new"}]`. A desativação é persistida; em seguida `.strip()` levanta `AttributeError`. O fato permanece inativo apesar da falha do lote. Isso dificulta retries, pois o cursor pode não avançar enquanto parte das escritas já foi commitada.

### Correção exigida

- Validar a resposta inteira antes da primeira escrita: objeto raiz, listas, objetos de cada item, textos, IDs, enums, números finitos, momentos e resumo.
- Definir claramente se um item inválido invalida o lote ou é ignorado. Nenhuma mutação deve preceder a validação das operações relacionadas.
- Não converter decisão desconhecida em criação automaticamente sem um contrato seguro explícito.
- Para falhas durante persistência, usar unidade transacional apropriada ou operações idempotentes e status de falha que permitam retry seguro.

**Aceitação:** JSON estruturalmente inválido não causa desativações parciais nem contagens de confirmação duplicadas após retry; erros são reportados de forma controlada.

## 5. [P1] FTS perde a idade da memória e anula a redução de confiança

**Locais:** `db.py:599–602`, `db.py:354–355`, `memory_retriever.py:85–95` e montagem do `candidates_map`.

`buscar_fatos_fts()` não retorna `created_at`/`updated_at`. `get_core_memories()` também não retorna esses timestamps. A migration 005 deixa `last_confirmed_at=NULL` para fatos existentes. Como o Retriever mantém o registro FTS/core e não o completa com os dados do fallback, falta a idade necessária para calcular a confiança.

**Reprodução:** mesmo fato volátil, confidence 1.0, criado há 180 dias, `last_confirmed_at=NULL`, `updated_at=NULL`:

- Consulta sem termo, via fallback: **effective_confidence = 0.4**.
- Consulta com termo presente no fato, via FTS: **effective_confidence = 1.0**.

Uma busca relevante passa a transformar uma lembrança antiga e incerta em afirmação de confiança total.

### Correção exigida

- Padronizar os metadados retornados por FTS/core/fallback, incluindo os timestamps usados pelo cálculo.
- Retornar também `source_conversation_id` no FTS: sua ausência atualmente faz `/memorydebug` exibir `Src: init` para memórias que possuem origem real.
- Preservar metadados ao combinar resultados de várias fontes.

**Aceitação:** o mesmo ID tem a mesma confiança efetiva independentemente da origem do candidato; fatos migrados com confirmação nula continuam sujeitos à idade. Source real permanece disponível no debug.

## 6. [P1] Confiança intermediária não chega ao prompt como incerteza

**Locais:** `memory_retriever.py:337–345`, `context_builder.py:51`.

O Retriever só qualifica texto quando a confiança é menor que 0.50. Na faixa **0.50–0.79**, a string é inserida como afirmação simples. O Context Builder usa essas strings e não consulta `effective_confidence` nos detalhes.

**Reprodução:** fato com confidence 0.65 retorna exatamente `Patrick joga xadrez`, sem qualificação. A faixa de cautela exigida na primeira revisão não foi implementada.

**Correção:** comunicar lembrança possivelmente desatualizada para 0.50–0.79 e necessidade de reconfirmação abaixo de 0.50, em linguagem natural; não expor números/metadados ao usuário.

**Aceitação:** testar o prompt final do Context Builder para 0.49, 0.50, 0.79 e 0.80, com representação apropriada em cada faixa.

## 7. [P2] Envelhecimento pode aumentar a confiança

**Local:** `memory_retriever.py:106–111`.

Os pisos absolutos `max(0.30, ...)` e `max(0.10, ...)` podem superar o valor bruto.

**Reprodução:** confidence 0.10, volatility `medium`, idade 200 dias → **effective_confidence 0.30**.

**Correção:** garantir `0 <= effective_confidence <= raw_confidence <= 1` para entradas válidas. Um eventual piso deve ser limitado pelo valor bruto; alternativamente aplicar fator multiplicativo de redução.

**Aceitação:** valores baixos não aumentam ao atravessar a janela temporal; incluir as três volatilidades e idades nas bordas.

## 8. [P2] Pesos configuráveis sem validação ou normalização

**Locais:** `config.py:70–75`, `Settings.validate()`, `memory_retriever.py:149–164`.

Os pesos foram externalizados, mas não existe verificação de soma, finitude ou sinal. O score é descrito como normalizado em 0..1, mas a soma ponderada não divide pela soma dos pesos. Configurações negativas, todas zero ou não finitas não são rejeitadas.

**Correção:** validar pesos finitos/não negativos, soma positiva e normalizar, ou exigir soma coerente de maneira explícita. Documentar o contrato e testar configuração inválida.

## 9. Correções reconhecidas e cobertura restante

Foram implementados corretamente nos caminhos examinados:

- Dispatcher com `same`, `ignore`, `new`, `update` e `contradiction`.
- Reafirmação idêntica com allowlist válida mantém o ID e incrementa confirmação.
- `confirmar_fato()` restringe atualização a fato ativo.
- Replacement isolado usa insert e desativação na mesma transação; colisão UNIQUE real preservou o antigo no teste independente.
- `adicionar_fato_patrick()` distingue insert ignorado de insert efetuado.
- Pool limitado de fallback para fatos no modo Intelligence; contribuição lexical por posição relativa no fluxo principal.
- `record_access=False` conectado ao Consolidator e ao comando de debug; Context Builder mantém tracking normal.
- Flag OFF seleciona um caminho legado no Retriever. Isso não significa desligamento global do novo Consolidator, mas corresponde à opção de fallback no Retriever aceita na primeira revisão.
- Configs documentadas em `.env.example`; source incluída em parte das consultas, com a lacuna FTS descrita acima.
- Migration 005 não foi alterada no hardening; nenhum novo número de migration foi consumido.

Limitações dos testes atuais:

- `test_7_8` cobre desativação por ID com allowlist não vazia, mas não cobre `same` com ID rejeitado nem listas vazias.
- `test_7_6` usa conexão mockada; a auditoria adicionou um controle com falha UNIQUE real.
- `test_7_11` verifica apenas que a lista final está ordenada, o que não prova discriminação lexical. Testar contribuição relativa com os demais sinais iguais.
- `test_7_12`, `7_13` e `7_14` chamam o Retriever diretamente; seus nomes não equivalem a testes dos chamadores reais. Adicionar cobertura de integração do Consolidator, Context Builder e comando.
- A migração testa os fatos, mas o teste existente não verifica explicitamente a conversa inserida. Acrescentar essa asserção.
- O ranking híbrido de momentos/resumos continua sendo melhoria opcional P2 da primeira revisão; não ampliar o escopo antes de corrigir integridade.

## 10. Ordem para o Antigravity e novo gate

1. Fechar allowlists e remover reutilização de IDs rejeitados.
2. Validar/reconciliar o payload inteiro antes de qualquer escrita, eliminando desativação antecipada de replacements.
3. Padronizar metadados de candidatos FTS/core/fallback.
4. Completar faixas de incerteza no prompt e impedir aumento de confiança por idade.
5. Validar pesos e completar os testes faltantes.
6. Executar regressão offline, migration, healthcheck e cenários de reafirmação/atualização/revogação em banco descartável.
7. Atualizar os testes de integração LLM ao contrato por decisão e executar o gate com o provedor real separadamente.

Não iniciar a 3.5.1 ainda. Para aprovar, os cenários de integridade desta revisão precisam passar sem alterar fatos não autorizados, sem deixar conceitos sem versão ativa após replacement e sem apresentar dados antigos como certeza por falta de metadados.

## 11. Resultado final da suíte existente

**72 testes descobertos: 69 aprovados, 3 ignorados, 0 falhas e 0 erros**, em 134,933 segundos. Os 16 testes de Memory Intelligence passaram, inclusive o de migration 4 → 5. Não houve `ResourceWarning` no log final.

Os três ignorados pertencem a `TestMemoryConsolidatorLLM` e exigem chamadas reais ao provedor. Portanto, este resultado não equivale a aprovação da integração externa nem à execução integral sem skips exigida pelo gate original.

Comandos executados a partir de `scratch/review_350_round2`, usando o caminho absoluto do Python do `venv` do projeto:

```text
python -m compileall -q .
python -W error::ResourceWarning audit_runner.py
python audit_runner.py --health
python -W error::ResourceWarning audit_regressions.py
```

O runner faz descoberta via `unittest`, exclui explicitamente os três testes externos e impede conexões externas. Loopback é permitido para os sockets internos do asyncio no Windows. Uma tentativa inicial bloqueou também esse mecanismo interno, produzindo dois erros do próprio isolamento; a suíte inteira foi reexecutada após corrigir o runner, com o resultado limpo acima. Não são regressões do projeto.

**Resultado dos testes adicionais:** oito falhas esperadas ao verificar invariantes ainda não atendidos; o teste de preservação do antigo diante de UNIQUE passou. As falhas foram verificadas com respostas controladas e SQLite real, sem substituir a lógica do projeto.
