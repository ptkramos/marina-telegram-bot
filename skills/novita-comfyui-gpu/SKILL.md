---
name: novita-comfyui-gpu
description: Gestão de ciclo de vida e renderização de FLUX.1 Dev em GPU dedicada na Novita AI com ComfyUI
---

# Novita ComfyUI GPU Instance Lifecycle

## Endpoints da API Novita (v2)
- **Status da Instância:** `GET https://api.novita.ai/gpus/v2/instances/{instance_id}`
- **Iniciar Instância:** `PUT https://api.novita.ai/gpus/v2/instances/{instance_id}/start` (Body vazio `b''` ou `{}`)
- **Pausar Instância:** `PUT https://api.novita.ai/gpus/v2/instances/{instance_id}/stop` (Body vazio `b''` ou `{}`)
- **Header:** `Authorization: Bearer <NOVITA_API_KEY>` e `Content-Type: application/json`

## Ciclo Seguro
1. `_ensure_instance_running`: Verifica status. Se `stopped` ou `exited`, dispara `PUT /start`.
2. Aguarda status `running` e faz ping em `https://{instance_id}-8188.us-ca-6.gpu-instance.novita.ai/system_stats`.
3. Submete o workflow no `/prompt`.
4. Faz polling no `/history/{prompt_id}` até obter as imagens prontas.
5. Baixa o binário pelo `/view?filename={filename}&type=output`.
6. **Sempre (no `finally:`)** executa `PUT /stop` para pausar a GPU e não queimar créditos.
