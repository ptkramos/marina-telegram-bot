# PLANO COMPLEMENTAR — MARINA 3.6.4
## Real-World Lookup pontual + Feriados brasileiros completos

**Escopo:** complemento da release **3.6.4 — Real World Context & Calendar Continuity**.

**Objetivo:** aproveitar a infraestrutura de pesquisa web já existente com **DDGS/DuckDuckGo** para consultas pontuais sobre lugares/horários, e substituir a visão limitada de feriados nacionais por uma fonte brasileira capaz de representar **feriados nacionais, estaduais e municipais**, sem criar um segundo sistema de calendário e sem transformar Marina em um crawler permanente da web.

---

# 1. PRINCÍPIO GERAL

A Marina não precisa manter um banco online com o estado de todos os lugares do Rio.

Ela deve:

```text
conhecer seus lugares canônicos
        ↓
ter uma necessidade concreta
        ↓
perceber que falta um fato atual
        ↓
pesquisar somente aquele fato
        ↓
usar resultado com source + freshness + confidence
        ↓
cache temporário
        ↓
seguir a decisão
```

Exemplo:

```text
Marina quer passar na Petz depois da faculdade
+
horário atual é relevante
+
horário não está confirmado/fresco
        ↓
lookup pontual
        ↓
"Petz Botafogo horário hoje"
        ↓
fonte confiável encontrada
        ↓
WorldState usa o resultado
```

Não implementar descoberta indiscriminada de lugares nesta release.

---

# 2. NÃO ADICIONAR GOOGLE PLACES NESTA ETAPA

Para 3.6.4:

```text
NÃO:
- adicionar Google Places como dependência obrigatória;
- cadastrar milhares de Place IDs;
- pesquisar lugares o tempo todo;
- introduzir lugares aleatórios no World Bible;
- consultar API externa em todo ciclo/tick.
```

Reutilizar a capacidade de busca web que já existe no projeto.

Antes de implementar, o agente deve confirmar a interface real atual da busca DDGS e reutilizar essa infraestrutura em vez de criar outra stack paralela.

---

# 3. NOVA ABSTRAÇÃO: RealWorldLookupService

Criar uma camada pequena sobre a busca já existente:

```text
RealWorldLookupService
    ├── lookup_place_fact(...)
    ├── lookup_opening_hours(...)
    └── cache / source / freshness / confidence
```

A implementação concreta inicial pode reutilizar DDGS.

Não expor `DDGS` diretamente às demais partes do sistema.

As demais camadas devem depender da abstração, não do fornecedor.

---

# 4. TRIGGERS DE BUSCA

Uma busca só pode ocorrer quando:

```text
1. existe uma entidade/lugar específico;
2. existe uma decisão ou pergunta concreta;
3. o fato pedido pode ter mudado;
4. o cache não possui resposta ainda válida.
```

Exemplos válidos:

```text
- horário de funcionamento hoje
- abre no domingo?
- fecha que horas?
- endereço/unidade correta
- funcionamento em feriado
- estabelecimento está temporariamente fechado?
```

Exemplos inválidos:

```text
- "pesquise lugares interessantes no Rio" a cada tick
- "veja todos os restaurantes próximos"
- "descubra 30 lugares novos para Marina"
- pesquisar todos os lugares do World Bible de madrugada
```

---

# 5. FONTE E CONFIANÇA PARA PLACES/HOURS

Prioridade sugerida:

```text
1. site oficial do estabelecimento/rede
2. página oficial institucional
3. fonte primária claramente identificada
4. fonte secundária confiável
5. snippet/resultados genéricos
```

Se houver:

```text
- unidade ambígua;
- horários conflitantes;
- snippet antigo;
- fonte sem identificação;
- resultado que parece referir-se a outro bairro;
```

retornar:

```text
UNKNOWN
```

Não “escolher” um horário apenas para completar a resposta.

---

# 6. RESULTADO NORMALIZADO

Exemplo:

```json
{
  "entity_key": "shopping_gavea",
  "entity_name": "Shopping da Gávea",
  "fact_type": "opening_hours",
  "value": {
    "opens_at": "10:00",
    "closes_at": "22:00",
    "open_now": true
  },
  "source_url": "https://...",
  "source_type": "official",
  "checked_at": "2026-09-18T18:40:00-03:00",
  "expires_at": "2026-09-19T00:00:00-03:00",
  "confidence": 0.96
}
```

Campos exatos podem ser adaptados ao schema atual.

---

# 7. TTL / CACHE DE PLACES

Valores iniciais sugeridos:

```text
address / canonical URL:
  30 dias

regular opening hours:
  24 horas

opening hours para "hoje":
  até o fim do dia, no máximo

open_now / temporary status:
  30–60 minutos

holiday-specific opening hours:
  poucas horas / somente data atual
```

Se o dado expirar, ele não deve continuar sendo tratado como atual.

Retornar `UNKNOWN` ou fazer nova consulta somente se houver necessidade real.

---

# 8. LUGARES CANÔNICOS PRIMEIRO

Busca de horário deve preferir lugares já existentes no mundo da Marina:

```text
PUC-Rio
Shopping da Gávea
Botafogo Praia Shopping
Bodytech / academia canônica
mercado canônico
Petz / veterinário
cafés/restaurantes já conhecidos
outros places existentes no World Bible
```

Novos lugares podem ser pesquisados quando surgirem por uma fonte válida da narrativa:

```text
- Bia sugere um lugar;
- Lívia menciona um local profissional;
- Patrick cita um estabelecimento;
- um evento confirmado aponta para um venue.
```

Pesquisar um novo lugar não o promove automaticamente a `canonical_place`.

---

# 9. PROMOÇÃO DE NOVO LUGAR

Fluxo futuro/permitido:

```text
candidate_place
→ pesquisado
→ validado
→ visitado/confirmado em evento real
→ pode virar known_place
```

A promoção deve ser explícita e idempotente.

Não transformar todo resultado de busca em memória permanente.

---

# 10. FERIADOS BRASILEIROS — NOVA FONTE

Adicionar suporte à **Feriados API** como fonte brasileira principal para contexto cívico.

Documentação/fonte:

`https://feriadosapi.com/`

A API suporta:

```text
- feriados nacionais;
- feriados estaduais;
- feriados municipais;
- consulta por UF;
- consulta por município/IBGE;
- API REST;
- MCP.
```

Para o Rio de Janeiro capital:

```text
UF: RJ
IBGE: 3304557
```

A consulta municipal consolidada pode representar:

```text
NACIONAL
+ ESTADUAL
+ MUNICIPAL
```

Isso é mais completo para a vida cotidiana da Marina do que uma fonte apenas nacional.

---

# 11. NÃO USAR O MCP COMO DEPENDÊNCIA PRINCIPAL DO RUNTIME

Embora o provedor ofereça MCP, para o runtime Python da Marina preferir integração REST determinística.

Motivos:

```text
- resposta JSON simples;
- cache mais fácil;
- timeout/retry explícitos;
- testes unitários simples;
- não depende de agente/MCP para saber se é feriado;
- menor superfície de falha.
```

MCP pode permanecer opcional para desenvolvimento/teste/ferramentas.

---

# 12. SEGREDO / API KEY

Nunca colocar chave:

```text
- no código;
- no README;
- no prompt;
- no banco;
- em URL persistida;
- em logs;
- no Git.
```

Usar variável de ambiente:

```text
FERIADOS_API_KEY
```

Exemplo:

```env
FERIADOS_API_KEY=...
```

Adicionar apenas o nome da variável ao `.env.example`:

```env
FERIADOS_API_KEY=
```

Como uma credencial real foi compartilhada durante a configuração, **rotacionar/revogar a chave exposta antes de uso em produção** e configurar somente a nova chave no ambiente local/secret store.

---

# 13. AUTENTICAÇÃO

Preferir header:

```text
Authorization: Bearer ${FERIADOS_API_KEY}
```

ou o header oficial equivalente suportado pelo provedor.

Evitar:

```text
...?apiKey=SEGREDO
```

quando houver opção de header, pois query strings têm maior chance de aparecer em logs/histórico/telemetria.

---

# 14. HIERARQUIA DE FERIADOS

Para contexto geral da Marina no Brasil:

```text
Feriados API (Rio/IBGE)
        ↓
Nager.Date como fallback nacional
        ↓
UNKNOWN
```

Para contexto especificamente acadêmico:

```text
calendário oficial PUC-Rio
        ↓
Feriados API
        ↓
Nager.Date
```

Ou seja:

```text
"é feriado no Rio?"
→ Feriados API

"tem aula na PUC?"
→ calendário institucional PUC é autoridade
```

Um feriado civil não deve substituir silenciosamente uma regra institucional explícita.

---

# 15. NAGER.DATE NÃO PRECISA SER REMOVIDO

Manter Nager.Date como fallback útil.

Não manter dois resultados concorrentes com igual autoridade.

Modelo:

```text
primary:
  feriados_api

fallback:
  nager_date

institutional_override:
  puc_calendar
```

Se Feriados API estiver indisponível:

```text
- nacional pode vir do Nager.Date;
- estadual/municipal fica UNKNOWN se não houver cache válido;
- não inventar que "não é feriado estadual" apenas porque Nager não retornou.
```

---

# 16. CACHE DE FERIADOS

Feriados anuais mudam pouco.

Sugestão:

```text
year calendar:
  TTL longo (dias/semanas)

current-day resolution:
  derivado do calendário anual em cache

manual/extraordinary decree:
  refresh quando necessário
```

No bootstrap/primeiro uso:

```text
get holidays for current year
→ cache
→ index by date
```

Não fazer request a cada mensagem.

---

# 17. MODELO NORMALIZADO DE HOLIDAY

Exemplo:

```json
{
  "date": "2026-04-23",
  "name": "Dia de São Jorge",
  "scope": "STATE",
  "country": "BR",
  "state": "RJ",
  "municipality_ibge": null,
  "source": "feriados_api",
  "source_checked_at": "...",
  "confidence": 1.0
}
```

Valores possíveis:

```text
NATIONAL
STATE
MUNICIPAL
OPTIONAL / PONTO_FACULTATIVO
```

Se o provedor distinguir ponto facultativo de feriado, não colapsar ambos para a mesma semântica.

---

# 18. EFEITO NO WORLDSTATE

Feriado pode alterar probabilidades de rotina, não determinar história.

Exemplo:

```text
feriado estadual
+
sem aula segundo calendário PUC
        ↓
academic commitment removed
        ↓
free-time / family / leisure / modeling plausibility changes
```

Não:

```text
feriado
→ Marina obrigatoriamente sai
→ Story Event automático
```

---

# 19. DDGS + FERIADO + HORÁRIO ESPECIAL

Integração útil:

```text
hoje é feriado no Rio
+
Marina quer ir ao lugar X
        ↓
não confiar no horário semanal normal
        ↓
lookup_place_fact(
    place=X,
    fact="holiday_opening_hours",
    date=today
)
```

Assim a Feriados API ajuda a decidir quando um horário comum pode não ser suficiente.

---

# 20. REAL-WORLD CONTEXT NORMALIZADO

Idealmente o ContextBuilder recebe algo compacto:

```text
Real World:
- Weather: rain likely, fresh
- Holiday: São Jorge / RJ state holiday
- Academic: no class today according to PUC calendar
- Place: Shopping X confirmed open until 22:00, checked 18:40
```

Nunca despejar:
- JSON bruto da API;
- resultados brutos do DuckDuckGo;
- HTML;
- dezenas de URLs;
- API keys.

---

# 21. NÃO CONFUNDIR "PESQUISOU" COM "APRENDEU PARA SEMPRE"

Resultados de lookup são `real_world_context`, não memória autobiográfica.

Exemplo:

```text
horário do shopping hoje
→ cache contextual
```

e não:

```text
memory_fact stable forever
```

Um fato pode ser promovido para conhecimento estável apenas se:
- é realmente estável;
- existe razão para persistir;
- passa pelas regras normais de memória.

---

# 22. BUSCA CONVERSACIONAL

Quando o próprio usuário perguntar algo que exige lookup:

```text
Patrick: "será que a Petz ainda tá aberta?"
```

o sistema pode fazer busca pontual.

A fala final pode ser natural:

```text
"pera, vi aqui..."
```

mas não precisa citar “DuckDuckGo” na persona.

Se não confirmar:

```text
"não consegui confirmar o horário agora"
```

é melhor que inventar.

---

# 23. RATE LIMIT / RESILIÊNCIA

Implementar:

```text
timeout curto
retry limitado
cache
negative cache curto
circuit-breaker simples opcional
```

Nunca bloquear a resposta inteira da Marina por muito tempo porque uma busca externa falhou.

Falha de lookup:

```text
UNKNOWN
→ Planner continua
```

---

# 24. FEATURE FLAGS

Sugestão:

```env
REAL_WORLD_PLACE_LOOKUP_ENABLED=false
FERIADOS_API_ENABLED=false
```

Ativar depois de validação.

Nager.Date pode continuar ativo independentemente.

---

# 25. OBSERVABILIDADE

Logar somente:

```text
lookup_type
entity_key
query class / normalized query
source domain
result status
confidence
cache hit/miss
latency
```

Não logar:
- API key;
- Authorization header;
- URL com segredo;
- conteúdo privado desnecessário de conversa.

---

# 26. TESTES — FERIADOS

Obrigatórios:

```text
- feriado nacional retornado;
- feriado estadual RJ retornado;
- feriado municipal Rio retornado quando disponível;
- enum/scope preservado;
- Nager fallback funciona para nacional;
- ausência de estadual no fallback não vira FALSE;
- cache evita chamadas repetidas;
- API failure → cached valid value ou UNKNOWN;
- PUC calendar vence para pergunta "tem aula?";
- API key nunca aparece em logs;
- bootstrap é idempotente.
```

---

# 27. TESTES — PLACE LOOKUP

Obrigatórios:

```text
- não busca sem necessidade;
- cache hit evita DDGS;
- busca exata por unidade específica;
- fonte oficial ganha de snippet genérico;
- conflito entre fontes → UNKNOWN ou baixa confiança;
- unidade ambígua → UNKNOWN;
- resultado expirado não é usado como current;
- holiday-specific lookup invalida horário semanal comum;
- novo lugar pesquisado não vira canonical automaticamente;
- search failure não bloqueia resposta principal.
```

---

# 28. TESTE DE NÃO-PESQUISA

Criar explicitamente testes onde NÃO deve haver web call:

```text
- conversa casual sem lugar;
- Marina está em casa e não planeja sair;
- horário de lugar é irrelevante;
- cache ainda é válido;
- Story Engine apenas avalia seeds abstratos;
- routine tick comum.
```

Esse teste é importante para controlar custo, latência e comportamento compulsivo de busca.

---

# 29. INTEGRAÇÃO COM O QUE JÁ EXISTE NA 3.6.4

Não reverter:

```text
Open-Meteo
Nager.Date
PUC Academic Life
Calendar/Event priority
Story Thread future commitment protection
RealWorld cache já criado
```

Adicionar apenas:

```text
A) Feriados API como primary BR holiday provider
B) Nager.Date como fallback nacional
C) RealWorldLookupService sobre DDGS existente
D) primeira capability: places/opening-hours sob demanda
```

---

# 30. FORA DE ESCOPO — DEIXAR PARA 3.7

Não implementar agora:

```text
- discovery autônomo de restaurantes/bares;
- eventos públicos;
- Ticketmaster/PredictHQ;
- recommendation engine de lugares;
- mobilidade/rotas em tempo real;
- curiosidade espontânea;
- aprendizado autônomo amplo da web;
- navegação contínua;
- Associative Life Recall.
```

3.6.4 deve apenas preparar a fundação.

---

# 31. DEFINITION OF DONE

A extensão está pronta quando:

```text
Marina conhece lugares canônicos
+
só pesquisa quando precisa
+
DDGS existente é reutilizado
+
resultado tem source/freshness/confidence
+
cache impede buscas repetidas
+
falha = UNKNOWN
        ↓
places/hours ficam plausíveis
```

e:

```text
Feriados API
→ nacional + estadual + municipal do Rio
→ cache anual
→ WorldState
→ PUC ainda é autoridade acadêmica
→ Nager.Date é fallback
```

sem:

```text
- API key no código;
- chave em logs;
- segundo calendário;
- scraping compulsivo;
- places aleatórios virando canon;
- eventos públicos entrando antes da 3.7.
```

> **Objetivo da 3.6.4: o mundo real pode ser consultado quando Marina realmente precisa dele; não precisa ser monitorado o tempo inteiro.**
