# 🌹 Marina Salles — Telegram AI Bot Autônomo & Humanoide (v3.7.0)

Bot interativo e exclusivo para Telegram com a personalidade autêntica, humana e desinibida de **Marina Salles** (jovem de 20 anos, modelo em início de carreira, namorada dedicada de Patrick Ramos).

O ecossistema integra LLM contextual avançada, geração visual ultra-realista via **FLUX.1 Dev** com pipeline de LoRAs de iPhone, síntese de voz clonada via **Novita MiniMax Speech 2.8 HD**, Smart Memory relacional persistente com **FTS5 e Consolidator assíncrono anti-falha**, ciclo biológico calculado em tempo real, espelhamento linguístico dinâmico e proatividade autônoma com agenda de rotina.

---

## 🏗️ Arquitetura do Sistema

### 🧠 Cérebro & Orquestração Conversacional
- **`bot.py`**: Orquestrador central do Telegram (PTB v21+), gerenciamento de comandos, envio em múltiplos balões orgânicos (`split_into_human_bubbles`), buffer inteligente de digitação (`MessageDebouncer`), reações emoji bidirecionais e lock de consolidação.
- **`planner.py`**: Planejador cognitivo interno que analisa previamente a mensagem, define intenção, tom, objetivo da fala, reações de emoji e agenda compromissos/follow-ups com normalização ISO rigorosa.
- **`context_builder.py`**: Montador estruturado de prompts que combina identidade nuclear, estado emocional com multiplicadores hormonais do ciclo, diretrizes do planner, preferências, sincronia de estilo e histórico dentro de um orçamento rígido de contexto (`MAX_TOTAL_CONTEXT_CHARS = 64000`).

### 💾 Smart Memory & Persistência (SQLite Relacional)
- **`db.py`**: Camada persistente exclusiva em SQLite (`marin_memory.db`) com WAL mode, busy timeout, foreign keys e framework de migrações (`migrations/`). Gerencia conexões seguras sem vazamentos de recursos.
- **`memory_retriever.py`**: Mecanismo de busca híbrida por Full-Text Search (FTS5) para recuperação seletiva de fatos, momentos marcantes e resumos temáticos de conversas passadas.
- **`memory_consolidator.py`**: Processador em segundo plano que extrai fatos permanentes sobre Patrick, resolve contradições, detecta momentos afetivos e sintetiza tópicos. Possui proteção contra falhas com retenção de cursor persistente e blindagem contra concorrência via `MEMORY_CONSOLIDATION_LOCK`.

### 📸 Câmera & Visão Computacional
- **`sd_client.py`**: Câmera fotográfica integrada à **Novita AI GPU (FLUX.1 Dev 4090/L40S)** com ComfyUI dedicado, acionamento sob demanda (`PUT start/stop`) para economia de créditos e suporte completo a fotos SFW e NSFW explícitas.
- **`visual_profile.py`**: DNA visual da Marina (rosto, corpo atlético proporcional, marquinha de biquíni sutil bronzeada, cabelo castanho ondulado com mechas douradas) e cadeia de LoRAs calibrada (Identidade Marina, iPhone Photo Realism Booster, Mirror Selfie Coherence e iPhone 16 Pro Preto).
- **`vision_service.py`**: Módulo multimodal que analisa imagens enviadas pelo usuário e gera comentários contextuais e afetuosos da Marina.

### 🎙️ Voz, Estilo & Biologia
- **`voice_engine.py`**: Síntese de áudio nativa (.ogg Opus com waveform) via **Novita MiniMax (speech-2.8-hd)** com clonagem de voz oficial, além de fallbacks configuráveis (ElevenLabs e Gemini TTS).
- **`style_engine.py`**: Motor de sincronia linguística que espelha padrões de risada (`kkkk`, `haha`), gírias do casal e cadência de digitação.
- **`cycle.py`**: Ciclo biológico autônomo calculado diariamente (28 dias, 4 fases: folicular, ovulatória, lútea e menstrual), modulando o afeto, a energia e a libido da Marina.
- **`proactivity_service.py`**: Motor autônomo que monitora a rotina, feriados, sono e eventos pendentes para iniciar conversas espontâneas e carinhosas no Telegram.

---

## ⚡ Instalação e Execução

### 1. Clonar o Repositório e Criar Ambiente Virtual

```powershell
git clone https://github.com/ptkramos/marina-telegram-bot.git
cd marina-telegram-bot
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar Variáveis de Ambiente (`.env`)

Copie o arquivo `.env.example` para `.env` e preencha com suas credenciais:

```powershell
Copy-Item .env.example .env
```

Principais variáveis:
- `TELEGRAM_BOT_TOKEN`: Token gerado pelo @BotFather.
- `TARGET_CHAT_ID`: Seu ID numérico no Telegram (segurança de acesso restrito).
- `LLM_API_KEY` & `LLM_MODEL`: Chave do OpenRouter ou OpenAI (ex: `meta-llama/llama-3.3-70b-instruct`).
- `NOVITA_API_KEY`: Chave da Novita AI para a câmera ComfyUI e voz MiniMax.
- `NOVITA_VOICE_ID`: Identificador da voz clonada da Marina.
- `NOVITA_INSTANCE_ID`: ID da instância GPU na Novita.

### 3. Diagnóstico de Saúde do Sistema

Antes de iniciar, execute o diagnósticador autônomo para validar sintaxe, banco SQLite, ciclo biológico e dependências:

```powershell
python healthcheck.py
```

### 4. Rodando o Bot

```powershell
python bot.py
```

---

## 🧪 Testes Automatizados

O projeto conta com uma suíte abrangente de **56 testes unitários e de integração offline**:

```powershell
python -W error::ResourceWarning -m unittest discover tests -v
```

Módulos testados:
- `test_context_builder.py`: Limites de contexto, injeção de emoções e diretrizes do planner.
- `test_memory_cursor.py`: Persistência de cursor no SQLite, anti-falha e lock de concorrência.
- `test_planner.py`: Planejamento heurístico, parser temporal e ordenação cronológica de eventos.
- `test_proactivity_service.py`: Disparos espontâneos, checagem de rotina e eventos pendentes.
- `test_style_engine.py`: Espelhamento de risadas, gírias e pontuação.
- `test_vision_service.py`: Redimensionamento de fotos e análise afetiva.
- `test_visual_profile.py`: Prompts SFW/NSFW, continuidade de look/ambiente e LoRAs.
- `test_wiring_auditoria.py`: Integração completa do pipeline de texto, fotos e banco de dados.

---

## 💬 Comandos Principais no Telegram

| Comando | Descrição |
| :--- | :--- |
| `/status` | Exibe status em tempo real (versão, dia do ciclo biológico, LLM, câmera, memória e histórico). Auto-limpeza em 15s. |
| `/foto [tema]` | Marina gera e envia uma foto em alta definição renderizada no FLUX.1 Dev com LoRAs de iPhone. |
| `/avatar` | Marina gera e atualiza sua foto de perfil oficial no Telegram de forma autônoma. |
| `/audio` ou `/voz` | Recebe uma mensagem de voz com síntese ultra-realista via Novita MiniMax. |
| `/memorias` | Visualiza os fatos, preferências e lembranças que a Marina registrou sobre você. |
| `/feedback [nota]` | Registra instruções, correções de comportamento e alinhamentos no SQLite. |

---

## 📄 Licença & Privacidade

Projeto privado e de uso pessoal desenvolvido exclusivamente para o casal Patrick Ramos & Marina Salles. Todos os dados de conversas, memórias e credenciais permanecem protegidos localmente em SQLite e variáveis de ambiente isoladas.

## 🎬 Créditos

Os dados de filmes, séries, animes e doramas (títulos, episódios, recomendações e onde assistir no Brasil) vêm do [TMDB](https://www.themoviedb.org/) (logo e regras de atribuição: https://www.themoviedb.org/about/logos-attribution).

*This product uses the TMDB API but is not endorsed or certified by TMDB.*
