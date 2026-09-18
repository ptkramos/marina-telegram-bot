# Cobertura da biblioteca abstrata — release 3.6.2, antes da etapa 10

A biblioteca contém **26 estruturas** em **19 categorias** e **7 formas causais**. O núcleo curado tem 13 seeds, incluindo um para cada lacuna da taxonomia (`romantic`, `family`, `self_care`); outras 13 estruturas passaram no critério de apoio de pelo menos duas famílias aprovadas. `unexpected_message` foi excluído por apoio cruzado insuficiente. Nenhum par de estruturas finais tem a mesma assinatura de categoria, forma causal, papéis, pré-condições e consequências possíveis.

## Categorias

- 3: amizade;
- 2 cada: acadêmico, sucesso pequeno, mal-entendido, profissional, conflito de agenda;
- 1 cada: situação prática diária, constrangimento, família, casa, convite, lazer, mobilidade, pet, romântico, autocuidado, compra, pequeno inconveniente, social leve.

## Famílias de origem

- ROCStories apoia 23 estruturas;
- DailyDialog apoia 21;
- EmpatheticDialogues apoia 21;
- Gutenberg Dialogue apoia 4;
- 13 estruturas pertencem ao núcleo curado da Marina; as três novas têm apenas `marina_curated` como origem.

Uma estrutura pode ter apoio de várias famílias; esses totais **não são pesos de sorteio**. O detalhe de apoio por seed está em `coverage_report.v1.json` e a atribuição/licença de cada corpus em `../external/story_datasets/manifests/` e `../external/story_datasets/licenses/`.

## Formas causais

- 5: revisão de plano;
- 5: interrupção da rotina;
- 4: esforço seguido de resultado;
- 4: reparo social;
- 4: apoio social;
- 3: oferta seguida de decisão;
- 1: esforço seguido de recuperação.

As formas descrevem **possibilidades**, não roteiros completos. Consequências dependem de evidência posterior; os novos tipos exigem um sinal observado no contexto antes de serem elegíveis no motor.

## Simulação longa

O agente externo executou três cenários de **1.095 dias** em SQLite descartável: `baseline` sem sinais, `realistic_context` com observações esparsas e rotina plausível, e `contextual_stress` com todos os sinais. Cada cenário teve **86 eventos**, **92,1% de dias sem evento novo** e **zero evento grave**. O baseline selecionou 4 tipos; o cenário realista, 17; o estresse, 22. A exposição a contexto observado foi de 0, 555 e 1.095 dias, respectivamente. O cenário intermediário modela, de forma determinística e explicitamente hipotética, período letivo, trabalho ocasional, contatos com Henrique, gestos de Patrick e necessidade de descanso. Ele não deriva descanso do ciclo. O detalhamento por marcos de 30, 90, 365 e 1.095 dias está em `simulation_report.v1.json`.

O cenário de estresse é deliberadamente artificial para exercitar elegibilidade; não presume que tantos acontecimentos tenham sido observados na vida da Marina. Os textos de origem continuam apenas no processamento offline ignorado pelo Git; o runtime lê somente a biblioteca abstrata e permanece com a flag desligada por padrão.

A validação externa está registrada em `validation_results.v1.json`: **241 testes aprovados, zero falhas, zero pulados**, 26 seeds abstratos validados e quatro verificações da simulação aprovadas. Não é necessário repetir a execução para revisar esses resultados.
