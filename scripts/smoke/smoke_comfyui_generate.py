import os
import json
import time
import requests
import random
from dotenv import load_dotenv

load_dotenv(r"C:\Arquivos\GitHub\marin-telegram-bot\.env")
api_key = os.getenv("NOVITA_API_KEY")
base_url = "https://45ca1e01a436df7d-comfyui.runsync.novita.dev"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

prompt_text = (
    "candid amateur smartphone photo of marina_reference, 22yo woman, gorgeous feminine face, "
    "expressive luminous honey-amber eyes, delicate nose, full plump lips, full cheeks, "
    "voluminous dark chocolate brown wavy hair with sun-kissed golden blonde tips. "
    "She is completely naked in bedroom, smiling playfully at camera, legs open, uncensored, "
    "fit athletic feminine silhouette, perky medium-to-large natural breasts, firm upright high-set bust, "
    "erect pink nipples with natural areolas, slim waist, natural proportional hips, "
    "round bubble butt projecting backward, detailed explicit female anatomy, pink labia, shaved pussy, "
    "natural skin texture with visible pores and subtle imperfections, authentic indoor lighting, flash photography"
)

def create_flux_workflow():
    seed = random.randint(1, 999999999)
    workflow = {
        # 1. UNET Loader (FLUX Schnell FP8)
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "flux1-schnell-fp8.safetensors",
                "weight_dtype": "default"
            }
        },
        # 2. Dual CLIP Loader (T5 + CLIP_L para FLUX)
        "2": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": "t5xxl_fp8_e4m3fn.safetensors",
                "clip_name2": "clip_l.safetensors",
                "type": "flux"
            }
        },
        # 3. VAE Loader
        "3": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": "flux_ae.safetensors"
            }
        },
        # 4. LoRA 1: Identidade da Marina (Marina Sweet)
        "4": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0],
                "clip": ["2", 0],
                "lora_name": "marina_flux.safetensors",
                "strength_model": 0.85,
                "strength_clip": 0.85
            }
        },
        # 5. LoRA 2: Anatomia Sem Censura (NSFW Master)
        "5": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["4", 0],
                "clip": ["4", 1],
                "lora_name": "NSFW_master.safetensors",
                "strength_model": 0.80,
                "strength_clip": 0.80
            }
        },
        # 6. Prompt Positivo
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["5", 1],
                "text": prompt_text
            }
        },
        # 7. Prompt Negativo (Vazio para FLUX Schnell)
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["5", 1],
                "text": ""
            }
        },
        # 8. Latent Image (832 x 1216)
        "8": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": 832,
                "height": 1216,
                "batch_size": 1
            }
        },
        # 9. KSampler (Euler / Simple, 4 passos rápidos!)
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["5", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["8", 0],
                "seed": seed,
                "steps": 4,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0
            }
        },
        # 10. VAE Decode
        "10": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["9", 0],
                "vae": ["3", 0]
            }
        },
        # 11. Salvar Imagem
        "11": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "marina_official_nsfw",
                "images": ["10", 0]
            }
        }
    }
    return workflow

def run():
    print("Montando workflow oficial FLUX ComfyUI (UNETLoader + DualCLIP + 2x LoRAs)...")
    wf = create_flux_workflow()
    payload = {"prompt": wf}

    print(f"Enviando para {base_url}/prompt ...")
    try:
        res = requests.post(f"{base_url}/prompt", headers=headers, json=payload, timeout=60)
        print("Status HTTP:", res.status_code)
        if res.status_code != 200:
            print("Erro:", res.text)
            return False

        prompt_id = res.json().get("prompt_id")
        print(f"Prompt aceito e validado! ID: {prompt_id}")
        print("Aguardando geração (4 passos no Schnell leva ~3 segundos!)...")

        for i in range(40):
            time.sleep(2)
            hist_res = requests.get(f"{base_url}/history/{prompt_id}", headers=headers, timeout=15)
            if hist_res.status_code == 200:
                hist_data = hist_res.json().get(prompt_id, {})
                outputs = hist_data.get("outputs", {})
                if "11" in outputs:
                    images = outputs["11"].get("images", [])
                    if images:
                        img_info = images[0]
                        filename = img_info.get("filename")
                        print(f"\nRenderização concluída com sucesso! Imagem: {filename}")
                        view_url = f"{base_url}/view?filename={filename}&type=output"
                        img_res = requests.get(view_url, headers=headers, timeout=30)
                        if img_res.status_code == 200:
                            save_path = r"C:\Arquivos\GitHub\marin-telegram-bot\marina_primeira_foto_oficial.png"
                            with open(save_path, "wb") as f:
                                f.write(img_res.content)
                            print(f"SALVA COM SUCESSO EM: {save_path} ({len(img_res.content)/1024:.1f} KB)!")
                            return True
            print(f"Aguardando... ({i*2}s)")
    except Exception as e:
        print("Erro de requisição:", e)
    return False

if __name__ == "__main__":
    run()
