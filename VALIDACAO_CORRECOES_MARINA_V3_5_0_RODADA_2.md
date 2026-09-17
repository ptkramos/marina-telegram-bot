# Validação das correções — Marina v3.5.0, rodada 2

**Data:** 16/09/2026.  
**Base:** `feae4d0054aec409bd7d6b21cb8f0eb9f5c9269e`, com alterações locais ainda sem commit.  
**Resultado final:** correções da rodada 2 aprovadas na regressão offline e na integração com LLM real. **Gate da 3.5.0 aprovado; liberado iniciar a 3.5.1.**

## Correções realizadas

- **Allowlist:** conjuntos vazios não autorizam mutações; IDs rejeitados não são reutilizados por fallback. Revogação por chave só alcança os IDs apresentados. IDs explícitos inválidos, tipos incorretos e IDs conflitantes são rejeitados.
- **Operações conflitantes:** desativação redundante de um alvo em update/contradiction é absorvida pelo replacement. Conflitos de revogação com same/ignore são rejeitados antes de gravar.
- **Validação do lote:** listas, itens, textos, decisões, IDs, resumo, momentos e números finitos são validados antes da primeira escrita. Números válidos são limitados a 0..1; enums de classificação têm defaults seguros.
- **Atomicidade:** todas as escritas do lote compartilham uma conexão e uma transação `BEGIN IMMEDIATE`. Commits internos não publicam etapas intermediárias. Falha de replacement, gravação de momento ou resumo reverte também confirmações e inserções anteriores; o erro chega ao chamador assíncrono, impedindo sucesso indevido.
- **Concorrência:** replacement isolado também inicia transação antes de ler o antigo. Dois replacements simultâneos do mesmo ID não criam duas versões ativas.
- **Metadados:** FTS, core e fallback fornecem idade e origem; memórias migradas com confirmação nula mantêm confiança coerente entre as rotas de recuperação.
- **Confiança:** redução temporal não aumenta o valor bruto; timestamps com timezone são aceitos. O texto enviado ao Context Builder diferencia certeza, cautela e reconfirmação.
- **Ranking:** pesos precisam ser finitos e não negativos, com soma positiva, e são normalizados. `.env.example` documenta o contrato. A contribuição lexical relativa do caminho principal tem teste discriminante.
- **Testes legados:** a contradição usa o contrato por decisão e candidatos; o teste de migração verifica também a conversa preservada.

Nenhuma migration foi alterada ou adicionada. A versão continua 3.5.0.

## Evidência de validação

Execução com Python 3.10.11 e dependências do venv existente, em cópia isolada em `scratch/verify_350_round2`, sem copiar `.env` nem banco real. Respostas externas dos novos testes são simuladas; a lógica do projeto e o SQLite são reais.

- **96 testes descobertos: 93 PASS, 3 SKIP, 0 FAIL, 0 ERROR**, em 36,799 segundos.
- Os **24 novos testes** em `tests/test_memory_hardening_regressions.py` passaram.
- Os **16 testes** de Memory Intelligence anteriores passaram, incluindo migration 4 → 5.
- `compileall` passou.
- Healthcheck isolado: **28 PASS, 0 WARN, 0 FAIL**.
- `git diff --check` passou.
- Sem `ResourceWarning` na execução final.

Os novos testes incluem os cenários reproduzidos na revisão, snapshots de fatos não autorizados, rollback após falha SQL real no fim do lote, retry sem duplicar confirmação após rollback, proteção de FTS no rollback, replacements concorrentes, falha assíncrona, prompt final nas fronteiras 0.49/0.50/0.79/0.80, comando real de debug com transporte Telegram simulado e busca de candidatos sem tracking indevido.

## Reproduzir a execução isolada existente

A partir de `scratch/verify_350_round2`, usando o Python do venv do projeto:

```text
python -m compileall -q .
python -W error::ResourceWarning audit_runner.py
python audit_runner.py --health
```

Logs: `scratch/verify_350_round2/suite.log` e `scratch/verify_350_round2/health.log`. O diretório scratch é ignorado pelo Git; os testes permanentes estão no diretório versionável `tests`.

## Limites e gate

Na etapa offline, os três testes que exigem o provedor real foram ignorados. Eles foram executados posteriormente com sucesso, conforme a seção seguinte. Não houve polling Telegram, deploy ou reinício do bot. O healthcheck valida a configuração sintética e o banco descartável; não verifica a operação em produção.

**Os bloqueadores reproduzidos na rodada 2 foram corrigidos e cobertos por testes.** A pendência de integração real foi encerrada pela execução abaixo.

A revisão anterior permanece como registro dos problemas no commit original, não como descrição do código local corrigido. A exclusão preexistente de `REVISAO_TECNICA_MARINA_V3_4_2.md` foi preservada. Nenhum commit foi criado.

## Integração real e encerramento do gate

Executada em 16/09/2026, com autorização do usuário, usando **OpenRouter** e o modelo configurado **`deepseek/deepseek-chat`**. Credenciais lidas da configuração local, sem exibição e sem cópia do `.env` para a área de testes.

O código foi copiado para `scratch/live_350_gate`; todos os dados do teste são sintéticos e a sequência usa SQLite descartável. O banco real não foi aberto pelos testes. A primeira tentativa foi bloqueada pela restrição de rede do ambiente; após aprovação de acesso externo, a execução real passou.

**Resultado: 4 testes aprovados, 0 falhas, 0 erros, 0 skips, em 54,053 segundos; 7 chamadas reais à LLM.**

1. Chitchat: nenhuma criação de fato permanente.
2. Contradição: retorno de decisão de substituição do ID conhecido e novo conteúdo coerente.
3. Extração: reconhecimento do fato sobre Final Fantasy XIV.
4. Sequência integrada, usando o Retriever, Consolidator e banco reais:
   - Criação de FFXIV como jogo principal: 1 fato criado, com chave canônica.
   - Reafirmação: 0 criações, 1 confirmação, mesmo ID ativo e contador aumentado.
   - Mudança para Guild Wars 2: 1 atualização, antigo inativo, `supersedes_id` correto e uma única versão ativa do conceito.
   - Revogação: 1 desativação, nenhuma versão ativa restante do jogo principal; fato de controle sobre café permaneceu idêntico.

O runner trata qualquer erro de transporte/provedor como falha, evitando aprovação acidental por respostas vazias. As respostas do modelo não foram simuladas. Logs e respostas sintéticas estão em `scratch/live_350_gate/live_escalated.log` e `scratch/live_350_gate/responses.json`; o executor está em `scratch/live_350_gate/live_gate.py`.

Somados aos 93 testes offline aprovados, os três testes externos completam os **96 testes existentes**, executados em etapas separadas; a sequência integrada é uma verificação adicional. Não foi necessário modificar a implementação nesta etapa.

**Decisão: aprovado iniciar o desenvolvimento da 3.5.1 sobre este estado local corrigido.** Esta aprovação se refere aos critérios e cenários executados, não a deploy em produção nem a garantia de determinismo de todas as futuras respostas da LLM.
