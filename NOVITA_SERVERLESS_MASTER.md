# 📋 ARQUIVO MESTRE: INFRAESTRUTURA, CUSTOS & GESTÃO DA MARINA (FLUX.1 DEV + NOVITA)

Este arquivo centraliza a arquitetura, controle financeiro, endpoints, especificações técnicas e ciclo de vida da infraestrutura da **Marina Seltin (v2.5)**.

---

## 💰 1. Painel de Controle Financeiro & Ciclo de Vida da GPU

| Recurso | Tipo de Cobrança | Valor Unitário | Gestão de Créditos | Status Atual |
| :--- | :--- | :--- | :--- | :--- |
| **Instância GPU RTX 4090** | Por tempo ativo (PUT start/stop) | ~$0.39 / hora | Liga sob demanda, gera foto e pausa no `finally:` | Pausada quando ociosa ($0/h) |
| **Instância ID** | `e70d0a62c99c2402` | Região `us-ca-6` | ComfyUI oficial na porta 8188 | Operacional |
| **LoRA Storage** | Armazenamento local da instância | Incluso no container | 5 LoRAs persistidos em `/root/ComfyUI/models/loras/` | 100% Carregados |

> 🔒 **Regra de Ouro:** O bot NUNCA deixa a GPU ligada ociosa. O `sd_client.py` executa o método `_stop_instance` no bloco `finally:` de cada geração, garantindo zero queima acidental de créditos.

---

## 🖥️ 2. Stack de Modelos & LoRAs (FLUX.1 Dev Exclusivo)

* **UNET:** `flux1-dev-fp8.safetensors` (FLUX.1 Dev FP8 — **Nunca Schnell**)
* **DualCLIP:** `t5xxl_fp8_e4m3fn.safetensors` + `clip_l.safetensors`
* **VAE:** `flux_ae.safetensors`
* **LoRAs Calibrados:**
  1. `marina_flux.safetensors` (Peso 1.0) — Identidade facial/corporal da Marina Seltin.
  2. `NSFW_master.safetensors` (Peso 0.80) — Anatomia feminina sem censura (ativado em `is_nsfw=True`).
  3. `roundassv16_FLUX.safetensors` (Peso 0.65) — Ativado em fotos de costas / curvas.
  4. `FluxSideboob-E3.safetensors` (Peso 0.60) — Ativado em ângulos laterais.
  5. `Hand_v2.safetensors` (Peso 0.50) — Detalhamento anatômico de mãos e dedos.

---

## 🧠 3. Sistema de Personalidade & Conversação (Ultra-Humanóide)

* **LLM:** Llama 3.3 70B Instruct via OpenRouter.
* **Cadência de Mensagens:** `split_into_human_bubbles` divide respostas organicamente em 1 a 3 balões baseados em frases pontuadas com delay realista de digitação (`send_chat_action(TYPING)`).
* **Voz Autônoma:** Síntese de áudio ultrarrealista com ElevenLabs (fallback Gemini TTS), sem asteriscos ou rubricas teatrais.
* **Memória de Longo Prazo:** Banco SQLite relacional (`marin_memory.db`) com extração assíncrona de fatos, gostos, intimidade e histórico de conversas.
* **Foto de Perfil:** Atualização de avatar em 1 foto única 100% vestida e elegante, aplicada imediatamente via `set_my_profile_photo`.
