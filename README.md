# 🎀 Marin Kitagawa - Telegram AI Bot Híbrido

Bot interativo para Telegram com a personalidade gyaru e energética da **Marin Kitagawa** (*My Dress-Up Darling*), unindo a inteligência conversacional da OpenAI com geração de fotos locais na sua GPU AMD Radeon RX 570 via Stable Diffusion (Automatic1111).

---

## 📂 Estrutura dos Arquivos

- `bot.py`: Código principal do bot Telegram, comandos (`/start`, `/status`, `/foto`), respostas e agendador de iniciativa própria.
- `prompts.py`: Definições da personalidade gyaru da Marin e construtor de prompts fotográficos com tags da Marin Kitagawa.
- `sd_client.py`: Cliente assíncrono para a API do Stable Diffusion com semáforo de GPU (evita sobrecarga de VRAM).
- `config.py`: Gerenciador de configurações e variáveis de ambiente.
- `requirements.txt`: Dependências Python necessárias.
- `.env.example`: Modelo de configuração das credenciais.

---

## 🚀 Passo a Passo de Configuração

### 1. Preparando o Ambiente Python

```powershell
cd C:\Users\conta\.gemini\antigravity-ide\scratch\marin-telegram-bot
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

Copie o arquivo `.env.example` para `.env` e preencha suas chaves:
- `TELEGRAM_BOT_TOKEN`: Pegue com o [@BotFather](https://t.me/BotFather) no Telegram.
- `OPENAI_API_KEY`: Sua chave de API da OpenAI.
- `TARGET_CHAT_ID`: Seu ID de usuário no Telegram (consulte enviando `/start` para [@userinfobot](https://t.me/userinfobot)).
- `SD_API_URL`: A URL do túnel público (ex: Ngrok) que aponta para o seu Stable Diffusion.

---

### 2. Configurando o PC Local (RX 570 com Automatic1111 DirectML)

Na sua placa de vídeo AMD RX 570 (8GB), o Automatic1111 deve ser executado com a versão **DirectML**:

1. **Ativar o modo API**:
   No diretório do seu Stable Diffusion WebUI, edite o arquivo `webui-user.bat`:
   ```bat
   set COMMANDLINE_ARGS=--api --medvram --opt-sub-quad-attention --no-half
   ```
   *(A flag `--api` é obrigatória para liberar a porta para o bot).*

2. **Modelos Recomendados (SD 1.5 no Civitai)**:
   - **Checkpoint Base**: [CyberRealistic](https://civitai.com/models/15003/cyberrealistic) ou [Realistic Vision V5.1](https://civitai.com/models/4201/realistic-vision-v51) (coloque em `models/Stable-diffusion/`).
   - **LoRA da Marin Kitagawa**: Procure por *"Marin Kitagawa"* no Civitai compatível com SD 1.5 (coloque o arquivo `.safetensors` na pasta `models/Lora/`).
   *(O prompt base no `prompts.py` já usa o nome canônico e tags da Marin!)*

3. **Iniciar o WebUI**:
   Dê dois cliques em `webui-user.bat`. O servidor ficará disponível localmente em:
   `http://127.0.0.1:7860`

---

### 3. Expondo a Porta para a Nuvem / VPS (Túnel)

Para que o bot (rodando na VPS ou em outro local) converse com a sua RX 570:

#### Opção A: Ngrok (Muito Simples)
```powershell
ngrok http 7860
```
Copie a URL HTTPS gerada (ex: `https://abc1-23.ngrok-free.app/`) e coloque na variável `SD_API_URL` do `.env`.

#### Opção B: Pinggy (Não requer instalação)
```powershell
ssh -p 443 -R0:localhost:7860 a.pinggy.io
```

---

### 4. Rodando o Bot

```powershell
python bot.py
```

No Telegram:
1. Envie `/start` para a Marin.
2. Envie `/status` para checar se a sua GPU e o bot estão conectados.
3. Peça fotos naturalmente na conversa (*"Marin, manda uma selfie!"*) ou use o comando `/foto`.
