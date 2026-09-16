# 📋 GUIA MESTRE: INFRAESTRUTURA GPU, COMFYUI & LORAS DA MARINA SELTIN

Este documento é o **caminho das pedras definitivo** para qualquer desenvolvedor, agente ou conversa futura que precise gerenciar, sincronizar ou debugar a geração de imagens da Marina Seltin.

---

## ⚡ 1. Visão Geral da Arquitetura

* **Modelo Base:** FLUX.1 Dev FP8 (`flux1-dev-fp8.safetensors` — **NUNCA Schnell**)
* **CLIP:** DualCLIP com `t5xxl_fp8_e4m3fn.safetensors` + `clip_l.safetensors`
* **Serviço de Render:** ComfyUI oficial (porta `8188`) rodando sob supervisor em container Linux
* **Cloud Provider:** **Novita AI GPU Instances**
* **ID da Instância Dedicada:** `e70d0a62c99c2402` (Nome: `test-4090`, Cluster: `us-ca-6`)
* **Endpoint ComfyUI:** `https://e70d0a62c99c2402-8188.us-ca-6.gpu-instance.novita.ai`
* **Diretório de LoRAs no Servidor:** `/root/ComfyUI/models/loras/`
* **Diretório de UNETs no Servidor:** `/root/ComfyUI/models/unet/`

---

## 💰 2. Gestão Financeira & Ciclo de Vida da GPU

| Recurso | Modelo de Cobrança | Custo Aprox. | Como Funciona |
| :--- | :--- | :--- | :--- |
| **RTX 4090 (16 vCPU, 62GB RAM)** | Postpaid (por tempo ativo) | ~$0.33 - $0.39 / hora | **On-Demand Automático:** O `sd_client.py` liga a instância via API (`PUT /start`), renderiza a foto e pausa imediatamente (`PUT /stop`) no bloco `finally:`. |
| **Persistência de Disco** | Rootfs 60GB (`auto_migrate: true`) | Incluso | Os modelos salvos em `/root/ComfyUI/models/` persistem automaticamente entre pausas e migrações. |

> 🔒 **Regra de Ouro:** NUNCA deixe a instância ligada ociosa se não for gerar fotos ou transferir arquivos. Sempre pause usando `python gpu_manager.py stop` ou deixe o bot gerenciar o ciclo de vida.

---

## 🎨 3. Tabela Canônica de LoRAs Instalados

Todos os 8 LoRAs abaixo estão baixados e ativos em `/root/ComfyUI/models/loras/`:

| LoRA (.safetensors) | Tamanho | Função e Gatilho | Origem / Download |
| :--- | :--- | :--- | :--- |
| **`marina_flux.safetensors`** | 328 MB | **Identidade Facial e Corporal** da Marina (Peso 1.0) | Modelo proprietário treinado |
| **`NSFW_master.safetensors`** | 165 MB | **Anatomia Sem Censura** (mamilos, genitália, aréolas). Ativado quando `is_nsfw=True` | Civitai |
| **`roundassv16_FLUX.safetensors`** | 74 MB | **Curvas e Poses Traseiras**. Ativado em fotos de costas (`focus_angle='behind'`) | Civitai |
| **`FluxSideboob-E3.safetensors`** | 19 MB | **Decote Lateral / Ângulo Lateral**. Ativado em `focus_angle='side'` | Civitai |
| **`Hand_v2.safetensors`** | 328 MB | **Anatomia de Mãos e Dedos** | Civitai |
| **`iphone_photo_flux.safetensors`** | 11 MB | **iPhone Photo Realism Booster**. Ativado em todas as fotos quando `IPHONE_LORAS_ENABLED=true` | [Civitai 967140](https://civitai.com/api/download/models/967140) |
| **`mirror_selfie_flux.safetensors`** | 18.4 MB | **Mirror Selfie**. Poses naturais na frente do espelho | [Civitai 1816152](https://civitai.com/api/download/models/1816152?fileId=1716435) |
| **`iphone16pro_flux.safetensors`** | 18.4 MB | **Aparelho iPhone Realista** segurado na mão (3 lentes de safira) | [Civitai 2047801](https://civitai.com/api/download/models/2047801?fileId=1956408) |

---

## 🛠️ 4. CLI de Gestão Rápida (`gpu_manager.py`)

No repositório existe o utilitário [gpu_manager.py](file:///c:/Arquivos/GitHub/marin-telegram-bot/gpu_manager.py), que automatiza 100% das tarefas operacionais:

```powershell
# 1. Verificar se a GPU e o ComfyUI estão online
.\venv\Scripts\python.exe gpu_manager.py status

# 2. Iniciar a GPU (aguarda até ComfyUI responder HTTP 200)
.\venv\Scripts\python.exe gpu_manager.py start

# 3. Pausar a GPU imediatamente para proteger os créditos
.\venv\Scripts\python.exe gpu_manager.py stop

# 4. Listar arquivos LoRA diretamente do servidor remoto
.\venv\Scripts\python.exe gpu_manager.py list-loras

# 5. Baixar e sincronizar LoRAs faltantes automaticamente da Civitai
.\venv\Scripts\python.exe gpu_manager.py sync-loras
```

---

## 🔑 5. Detalhes Cruciais de Conexão & Gotchas

Se precisar conectar manualmente via script ou SSH:

1. **Credenciais SSH Dinâmicas:**
   A Novita AI gera porta e senha SSH dinamicamente para cada instância. NUNCA hardcode porta/host fixos em scripts persistentes.
   Sempre consulte via API:
   ```python
   import requests
   r = requests.get(f"https://api.novita.ai/gpus/v2/instances/{INSTANCE_ID}", headers={"Authorization": f"Bearer {NOVITA_API_KEY}"})
   ssh_info = r.json()["tools"]["ssh"]
   # Exemplo: command: "ssh -p 32787 root@proxy.us-ca-6.gpu-instance.novita.ai", password: "..."
   ```

2. **Download de LoRAs da Civitai (Erro 401 vs HTTP 307):**
   * **Gotcha:** Passar `?token=...` na query string de downloads da Civitai pode falhar com **HTTP 401** quando `fileId` ou outros parâmetros estão presentes.
   * **Solução:** Use o header de autenticação:
     `headers = {"Authorization": f"Bearer {CIVITAI_API_KEY}"}`
     A Civitai responderá com **HTTP 307 Temporary Redirect** contendo no header `Location` o link direto pré-assinado da Backblaze B2 (`https://b2.civitai.com/...`), que não requer autenticação adicional.
   * Em seguida, envie para o servidor via SFTP (`sftp.put`) ou `curl -L "<url_presigned>"`.

3. **Verificação dos LoRAs no ComfyUI:**
   Para testar se o ComfyUI detectou novos arquivos sem reiniciar o processo:
   ```bash
   curl -s http://127.0.0.1:8188/object_info/LoraLoader
   ```
   O ComfyUI lê automaticamente o diretório a cada chamada.

4. **Variáveis de Ambiente no `.env`:**
   ```env
   NOVITA_API_KEY="sk_..."
   NOVITA_INSTANCE_ID="e70d0a62c99c2402"
   CIVITAI_API_KEY="..."
   IMAGE_ENGINE="novita"
   IPHONE_LORAS_ENABLED=true
   ```
