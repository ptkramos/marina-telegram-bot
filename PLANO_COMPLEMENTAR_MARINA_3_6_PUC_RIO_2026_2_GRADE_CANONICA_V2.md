# PLANO COMPLEMENTAR — MARINA 3.6.4 — V2
## PUC-Rio 2026.2 · Grade canônica com identidade Corpo e Moda

**Esta V2 substitui a versão anterior deste complemento.**

**Escopo:** complemento do `PLANO_COMPLEMENTAR_MARINA_3_6_ACADEMIC_LIFE_ENGINE.md` para a release **3.6.4 — Real World Context & Calendar Continuity**.

**Objetivo:** ancorar a vida acadêmica de Marina em fontes oficiais da PUC-Rio, preservar a progressão do **currículo Design 2023.0** e, ao mesmo tempo, dar ao semestre 2026.2 uma identidade mais clara de **Corpo e Moda**, sem criar segundo calendário, sem tornar rotina rígida e sem transformar docentes reais em NPCs.

---

# 1. DECISÃO CANÔNICA

Considerar canônico:

```text
character: Marina Salles
institution: PUC-Rio
campus_area: Gávea
program: Design
curriculum: 2023.0
focus: Corpo e Moda
entry_term: 2025.1
current_term: 2026.2
approximate_period: 4
academic_status: active
```

## Regra de interpretação

O currículo 2023.0 é geral de Design nos primeiros períodos.

Portanto:

```text
4º período oficial
+
optativa antecipada compatível com Corpo e Moda
=
identidade acadêmica da Marina em 2026.2
```

Não usar a matriz legada separada de “Design – Moda” como currículo da Marina.

---

# 2. FONTES OFICIAIS

## 2.1 Currículo / periodização

Fonte oficial:

`https://www.puc-rio.br/ensinopesq/ccg/design.html`

Usar para:
- currículo 2023;
- componentes obrigatórios por período;
- créditos;
- grupos de optativas;
- progressão curricular.

## 2.2 Calendário acadêmico

Fonte oficial:

`https://www.puc-rio.br/sobrepuc/depto/dar/calendario/`

Para 2026.2:

```text
início das aulas: 11/08/2026
término das atividades acadêmicas: 14/12/2026
```

A fonte institucional vence Nager.Date quando o assunto é:
- início/fim de período;
- recessos internos;
- calendário acadêmico;
- matrícula/ajustes;
- datas institucionais da PUC.

## 2.3 Snapshot oficial do MicroHorário

Arquivo fornecido pelo usuário:

`HORARIO_DAS_DISCIPLINAS_18092026 (1).csv`

Metadados do arquivo:

```text
Período: 20262
Emitido em: 18/09/2026 06:26
Última atualização: 17/09/2026 22:00
```

Usar como snapshot de:
- ofertas reais de 2026.2;
- turmas;
- horários;
- salas;
- códigos;
- créditos.

**Não usar número atual de vagas como prova de que Marina poderia ou não ter se matriculado**, pois o snapshot é posterior ao início do semestre.

---

# 3. CORREÇÃO IMPORTANTE DA V2 — IDENTIDADE DE MODA

A V1 preservava corretamente o 4º período, mas a grade ainda estava muito generalista.

A V2 adiciona:

```text
DSG1985 — Acessórios de Moda e Extensões do Corpo
```

como **optativa adicional antecipada de Corpo e Moda**.

Dados verificados:

```text
código: DSG1985
nome: Acessórios de Moda e Extensões do Corpo
créditos: 2
turma: 1AA
horário: QUA 07:00–09:00
local no snapshot: LAB
pré-requisito no snapshot: NÃO
currículo compatível: 2023.0
ênfase: Corpo e Moda
grupo: DSG0011 — Oficinas de Corpo e Moda
```

## Regra curricular obrigatória

**DSG1985 NÃO substitui o grupo `DSG0860` do 4º período.**

O componente usado para cumprir o `DSG0860` continua sendo:

```text
DSG1866 — Práticas Experimentais VI
```

Assim:

```text
DSG1866
→ cumpre optativa de Práticas Experimentais do 4º período

DSG1985
→ optativa adicional de Corpo e Moda feita antecipadamente
```

Não contabilizar os dois como se cumprissem o mesmo requisito.

---

# 4. POR QUE DSG1985 É A ESCOLHA CANÔNICA

Entre as ofertas reais de 2026.2, ela é especialmente adequada à Marina porque combina:

- corpo;
- mobilidade;
- acessório;
- extensão do corpo;
- prática/materialidade;
- construção de objeto relacionado ao vestir.

Ela cria uma ponte direta entre:

```text
Design
+
Corpo e Moda
+
experiência pessoal da Marina como modelo
```

sem transformar a faculdade em mera extensão da carreira de modelo.

## Alternativas reais identificadas, mas NÃO usadas na grade atual

### DSG1927 — Fashion Business / Moda e Gestão
```text
SEG 07:00–09:00
2 créditos
Corpo e Moda + Estratégia e Gestão
```

Excelente candidata para semestre futuro, sobretudo pela relação com mercado, marcas e carreira internacional.

### DSG1946 — Moda e o Corpo Contemporâneo
```text
TER/QUI 09:00–11:00
4 créditos
```

Muito alinhada conceitualmente, mas conflita com a grade-base escolhida.

### DSG1807 — Desenho de Corpo e Moda
```text
TER/QUI 11:00–13:00
4 créditos
```

Também muito alinhada, mas conflita com obrigatórias do 4º período.

### DSG1515 — Técnicas de Costura
```text
QUI 11:00–13:00
2 créditos
```

Boa candidata futura, mas conflita com Desenho Técnico no arranjo atual.

### DSG1981 / DSG1997 / DSG1998
São alternativas de moda/representação interessantes, porém conflitam com blocos atuais ou são menos adequadas ao balanceamento desta primeira grade canônica.

---

# 5. GRADE CANÔNICA FINAL — 2026.2

Total:

```text
9 componentes
26 créditos
4 dias presenciais por semana
sexta-feira sem aula canônica
```

A carga é deliberadamente um pouco acima dos 24 créditos recomendados do 4º período porque Marina cursa **uma optativa adicional de Corpo e Moda de 2 créditos**.

Isso deve ser tratado como:

```text
plausible_extra_elective = true
```

e não como regra de que Marina sempre pega carga extra.

---

## DSG1400 — Projeto: Projetar em Sociedade

```text
turma: 1AB
créditos: 6
SEG 09:00–13:00 — ARTE1
QUA 11:00–13:00 — ARTE1
extensão: 60h
type: PROJECT
```

Observação:
No currículo 2023.0, `DSG1400` é o código concreto usado para Projeto: Projetar em Sociedade no MicroHorário.

---

## DSG1804 — Conteúdos Estruturantes: Projetar para a Sociedade

```text
turma: 1AB
créditos: 2
QUA 09:00–11:00 — ARTE2
type: PROJECT_SUPPORT
```

---

## DSG1862 — Práticas Experimentais II

```text
turma: 1AA
créditos: 2
TER 07:00–09:00 — LAB
type: LAB
```

---

## DSG1854 — Linguagem e Estruturas

```text
turma: 1AD
créditos: 4
TER 09:00–11:00 — L422
QUI 09:00–11:00 — L422
type: THEORY / STUDIO
```

---

## DSG1852 — Fundamentos em Ergodesign

```text
turma: 1AB
créditos: 2
TER 11:00–13:00 — L260
type: THEORY
```

---

## CRE1227 — O Cristianismo

Cumpre o grupo `CRE0712`.

```text
turma: 7TG
créditos: 4
TER 13:00–15:00 — L332
QUI 13:00–15:00 — L332
extensão: 40h
type: ELECTIVE
```

### Regra de persona

```text
enrollment in CRE != religious belief
```

Nunca inferir:
- religião;
- fé;
- prática religiosa;
- mudança de crença

apenas porque Marina cursa um componente obrigatório do grupo CRE.

---

## DSG1866 — Práticas Experimentais VI

Cumpre os 2 créditos de `DSG0860` previstos no 4º período.

```text
turma: 1AB
créditos: 2
QUI 07:00–09:00 — LAB
type: LAB / EXPERIMENTAL_ELECTIVE
curriculum_group: DSG0860
```

---

## DSG1853 — Desenho Técnico

```text
turma: 1AC
créditos: 2
QUI 11:00–13:00 — ARTE1
type: STUDIO / THEORY
```

---

## DSG1985 — Acessórios de Moda e Extensões do Corpo

**Optativa adicional de identidade Corpo e Moda.**

```text
turma: 1AA
créditos: 2
QUA 07:00–09:00 — LAB
type: FASHION_STUDIO / ELECTIVE
emphasis: Corpo e Moda
curriculum_group: DSG0011
prerequisite: none in 2026.2 snapshot
```

Esta disciplina é a principal âncora explícita de Corpo e Moda no semestre atual.

---

# 6. VISÃO SEMANAL FINAL

```text
SEGUNDA
09:00–13:00  DSG1400  Projeto: Projetar em Sociedade

TERÇA
07:00–09:00  DSG1862  Práticas Experimentais II
09:00–11:00  DSG1854  Linguagem e Estruturas
11:00–13:00  DSG1852  Fundamentos em Ergodesign
13:00–15:00  CRE1227  O Cristianismo

QUARTA
07:00–09:00  DSG1985  Acessórios de Moda e Extensões do Corpo
09:00–11:00  DSG1804  CE-Projeto em Sociedade
11:00–13:00  DSG1400  Projeto: Projetar em Sociedade

QUINTA
07:00–09:00  DSG1866  Práticas Experimentais VI
09:00–11:00  DSG1854  Linguagem e Estruturas
11:00–13:00  DSG1853  Desenho Técnico
13:00–15:00  CRE1227  O Cristianismo

SEXTA
SEM AULA CANÔNICA
```

---

# 7. IDENTIDADE SEMANAL

A rotina agora tem uma assinatura mais clara:

```text
SEG
projeto

TER
dia acadêmico pesado/generalista

QUA
Corpo e Moda + projeto

QUI
laboratório + estrutura técnica + CRE

SEX
modelagem / casting / freela / vida pessoal / academia / Milo / Patrick / descanso
```

A quarta-feira passa a ser o principal ponto em que a faculdade conversa explicitamente com a identidade de moda da Marina.

---

# 8. NÃO TRANSFORMAR DSG1985 EM “A FACULDADE INTEIRA”

Mesmo sendo a matéria mais alinhada a Corpo e Moda:

- Marina não deve falar dela todos os dias;
- não deve relacionar todo evento acadêmico a moda;
- não deve transformar todo projeto em roupa/acessório;
- a carreira de modelo não deve dominar automaticamente a interpretação acadêmica;
- outros componentes continuam relevantes à formação geral de Design.

A ênfase deve aparecer organicamente, não como bordão.

---

# 9. PROFESSORES REAIS NÃO VIRAM NPCs

O MicroHorário contém docentes reais.

Os nomes podem ficar em:

```text
source_metadata
provenance
admin/debug
```

mas não devem virar automaticamente:

```text
Social Graph NPC
story character
friend/enemy/mentor
private-life actor
```

## Helena Prado

`Helena Prado` continua sendo NPC ficcional canônica do World Bible.

Não associar automaticamente Helena Prado a nenhuma turma real da PUC.

---

# 10. MODELAGEM NO BANCO

## academic_profile

```json
{
  "curriculum_key": "design_2023_0",
  "focus": "Corpo e Moda",
  "entry_term": "2025.1",
  "curriculum_source": "puc_rio_official",
  "canonical_schedule_source": "microhorario_2026_2_snapshot"
}
```

## academic_terms

```text
term_key: 2026.2
start_date: 2026-08-11
end_date: 2026-12-14
status: ACTIVE
generated_by: CANONICAL_SEED
```

## academic_courses

Criar 9 componentes canônicos:

```text
DSG1400
DSG1804
DSG1862
DSG1854
DSG1852
CRE1227
DSG1866
DSG1853
DSG1985
```

## requisito curricular

Guardar distinção entre:

```text
required_period_component
required_group_component
extra_emphasis_elective
```

Exemplo:

```text
DSG1866 = required_group_component / DSG0860
DSG1985 = extra_emphasis_elective / DSG0011
```

Isso evita o Academic Engine contar DSG1985 duas vezes ou acreditar que ela substituiu um requisito do 4º período.

---

# 11. ACADEMIC SCHEDULE ≠ CALENDAR DUPLICADO

Persistir apenas padrões semanais da grade.

Não criar centenas de eventos futuros para cada ocorrência de aula.

Resolver aula do dia por:

```text
active term
+ weekday/time
+ schedule block
+ institutional calendar
+ dated exceptions
=
current academic commitment
```

Calendar/Events continua sendo autoridade para exceções datadas.

---

# 12. PRIORIDADE DE ESTADO

```text
confirmed dated commitment
> academic class occurrence
> active thread consequence
> routine probability
> free-time fallback
```

Um casting confirmado pode gerar conflito, mas não apaga aula silenciosamente.

---

# 13. CLIMA / MOBILIDADE

Open-Meteo pode influenciar deslocamento para a PUC.

Exemplo:

```text
aula 07:00
+ chuva forte
→ scooter perde plausibilidade
→ Uber/alternativa ganha peso
```

Não:
- cancelar aula automaticamente;
- inferir humor;
- inferir ciclo;
- transformar chuva em Story Event sempre.

---

# 14. CALENDÁRIO INSTITUCIONAL

Ao projetar uma aula:

```text
weekly block exists
+
term active
+
date is academic day
+
not institutional recess/holiday
+
no dated cancellation
=
class commitment
```

A fonte oficial da PUC é autoridade sobre o funcionamento acadêmico da universidade.

---

# 15. CONFLITOS COM MODELAGEM

Sexta livre permanece uma janela natural para trabalho.

Jobs/castings podem surgir em outros dias.

Se houver colisão:

```text
aula
vs
casting/job confirmado
```

não decidir sempre do mesmo jeito.

Possibilidades:
- negociar horário;
- remarcar;
- recusar job;
- faltar excepcionalmente;
- sair cedo;
- priorizar aula;
- alternativa acadêmica plausível.

Decisões significativas devem ser persistidas.

---

# 16. STORY THREAD PROTECTION

Se uma Story Thread depender de compromisso futuro confirmado:

```text
Calendar/Event authoritative commitment
→ thread is protected from age-only abandonment
```

Pode usar:
- `has_future_commitment`;
- referência ao Event;
- mecanismo equivalente já implementado.

Ao concluir/cancelar o compromisso:
- atualizar a proteção;
- não duplicar calendário no Story Engine.

---

# 17. KNOWLEDGE / PRIVACY

Aula, trabalho de turma, feedback, colega ou atividade acadêmica não implica automaticamente que Patrick sabe.

```text
Marina knows = yes
Patrick knows = only if shared / otherwise established
```

Preservar 3.6.3.

A grade geral pode ser contexto cotidiano; fatos privados envolvendo terceiros continuam submetidos a disclosure/knowledge rules.

---

# 18. FUTUROS SEMESTRES

2026.2 fica travado como:

```text
CANONICAL_SEED
```

A partir de 2027.1:

1. avançar currículo 2023;
2. observar componentes concluídos;
3. respeitar requisitos/pré-requisitos;
4. aumentar progressivamente disciplinas de Corpo e Moda;
5. usar `DSG0002` / `DSG0011` quando curricularmente aplicável;
6. preservar alguma margem para carreira de modelo;
7. preferir snapshot oficial do MicroHorário quando fornecido;
8. sem snapshot real, gerar como `SIMULATED_ACADEMIC`, nunca fingir oferta oficial.

## Preferências futuras sugeridas

Quando houver escolha e compatibilidade, priorizar — sem obrigar — componentes como:

```text
DSG1927  Fashion Business
DSG1807  Desenho de Corpo e Moda
DSG1946  Moda e o Corpo Contemporâneo
DSG1515  Técnicas de Costura
DSG1981  Laboratório: Forma Tridimensional Moda
DSG1997  Figurino e o Corpo Narrativo
DSG1998  Desenho de Modelo Vivo
```

A escolha real depende de:
- requisitos;
- oferta do semestre;
- horário;
- carga;
- interesses atuais;
- conflitos profissionais.

---

# 19. CONTEXT BUILDER

Não enviar a grade inteira.

### Quarta 08:10

```text
Academic:
- PUC-Rio, Design 2023, focus Corpo e Moda
- Current: Acessórios de Moda e Extensões do Corpo until 09:00
- Next: CE-Projeto em Sociedade 09:00–11:00
- Then: Projeto em Sociedade 11:00–13:00
- Location: PUC/Gávea
```

### Sexta

```text
Academic:
- Term 2026.2 active
- No canonical class today
```

---

# 20. TESTES — V2

## Canon / currículo
- curriculum = `design_2023_0`;
- focus = `Corpo e Moda`;
- entry = `2025.1`;
- active term = `2026.2`.

## Grade
- exatamente **9 componentes**;
- total = **26 créditos**;
- DSG1985 presente;
- DSG1985 marcado `extra_emphasis_elective`;
- DSG1985 pertence a `DSG0011`, não a `DSG0860`;
- DSG1866 continua cumprindo `DSG0860`.

## Horário
- sem overlap;
- SEG 09–13;
- TER 07–15;
- QUA 07–13;
- QUI 07–15;
- SEX sem aula canônica.

## DSG1985
- QUA 07–09;
- 2 créditos;
- Corpo e Moda;
- sem prerequisite no snapshot fornecido;
- não vira Story Event automaticamente.

## Calendário
- compromisso datado confirmado vence aula;
- aula vence rotina;
- cancelamento de ocorrência libera horário;
- schedule-base não é destruído.

## Privacidade
- presença em aula não implica Patrick knows;
- docente real não vira NPC automaticamente.

## Idempotência
- bootstrap repetido não duplica termo, componentes ou schedule blocks.

---

# 21. NÃO REGRESSÕES

Não alterar:

- Story cadence ~89%;
- World Bible;
- Social Graph;
- Knowledge/Privacy 3.6.3;
- MenstrualCycleManager;
- Planner;
- VoiceRouter;
- Reminder/Open Loop semantics;
- Open-Meteo/Nager.Date já implementados.

Não criar:

- segundo Calendar;
- segundo Routine Engine;
- scraper obrigatório da PUC;
- religião inferida por CRE;
- pessoa real transformada em NPC;
- toda experiência acadêmica como “história de moda”.

---

# 22. INTEGRAÇÃO COM A 3.6.4 JÁ EM DESENVOLVIMENTO

Não reverter a arquitetura já construída.

O agente deve:

1. substituir a grade canônica V1 por esta V2;
2. adicionar `DSG1985` como optativa adicional Corpo e Moda;
3. alterar total esperado de 24 → 26 créditos;
4. alterar total de componentes de 8 → 9;
5. alterar quarta de 09–13 → **07–13**;
6. manter sexta livre;
7. preservar `DSG1866` como cumprimento de `DSG0860`;
8. modelar `DSG1985` separadamente como `DSG0011/extra_emphasis_elective`;
9. não mudar novamente a cadência de Story Events;
10. não criar dependência online obrigatória para o funcionamento do bot.

---

# 23. DEFINITION OF DONE

```text
currículo real 2023
+
4º período real
+
snapshot 2026.2
+
optativa real Corpo e Moda
        ↓
grade canônica
        ↓
26 créditos
4 dias presenciais
sexta livre
        ↓
quarta ganha identidade forte de moda
        ↓
Calendar continua autoridade
        ↓
WorldState respeita aula/locomoção
        ↓
Story Engine recebe contexto, não calendário duplicado
        ↓
futuros semestres aprofundam Corpo e Moda progressivamente
```

> **O 4º período continua curricularmente correto; a optativa adicional faz Marina começar a construir sua identidade de Corpo e Moda antes de a ênfase dominar formalmente os períodos seguintes.**
