#!/usr/bin/env python3
"""
CLI Oficial para Gestão da GPU Novita AI e ComfyUI da Marina Salles (v3.7.0).
Permite iniciar, pausar, verificar status, inspecionar modelos e sincronizar LoRAs da Civitai.

Uso:
  python gpu_manager.py status        # Exibe status da instância e ComfyUI
  python gpu_manager.py start         # Liga a GPU e aguarda o ComfyUI ficar online
  python gpu_manager.py stop          # Pausa a GPU imediatamente para poupar créditos
  python gpu_manager.py list-loras    # Lista todos os LoRAs no ComfyUI
  python gpu_manager.py sync-loras    # Baixa/sincroniza LoRAs faltantes da Civitai
"""
import os
import re
import sys
import time
import json
import argparse
import requests
import paramiko
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv(r"c:\Arquivos\GitHub\marin-telegram-bot\.env")

NOVITA_API_KEY = os.getenv("NOVITA_API_KEY", "").strip().strip('"')
CIVITAI_API_KEY = os.getenv("CIVITAI_API_KEY", "").strip().strip('"')
INSTANCE_ID = os.getenv("NOVITA_INSTANCE_ID", "e70d0a62c99c2402").strip().strip('"')

NOVITA_HEADERS = {
    "Authorization": f"Bearer {NOVITA_API_KEY}",
    "Content-Type": "application/json"
}

OFFICIAL_LORAS = [
    {
        "name": "marina_flux.safetensors",
        "desc": "Identidade Marina Salles (LoRA Principal)",
        "api_url": None
    },
    {
        "name": "NSFW_master.safetensors",
        "desc": "Anatomia Sem Censura (NSFW)",
        "api_url": None
    },
    {
        "name": "roundassv16_FLUX.safetensors",
        "desc": "Curvas / Poses de Costas",
        "api_url": None
    },
    {
        "name": "FluxSideboob-E3.safetensors",
        "desc": "Ângulos Laterais / Decote",
        "api_url": None
    },
    {
        "name": "Hand_v2.safetensors",
        "desc": "Detalhamento de Mãos e Dedos",
        "api_url": None
    },
    {
        "name": "iphone_photo_flux.safetensors",
        "desc": "iPhone Photo Booster (Realismo de Smartphone)",
        "api_url": "https://civitai.com/api/download/models/967140"
    },
    {
        "name": "mirror_selfie_flux.safetensors",
        "desc": "Mirror Selfie (Pose anatômica no espelho)",
        "api_url": "https://civitai.com/api/download/models/1816152?fileId=1716435"
    },
    {
        "name": "iphone16pro_flux.safetensors",
        "desc": "iPhone 14/15/16 Pro (Aparelho celular realista)",
        "api_url": "https://civitai.com/api/download/models/2047801?fileId=1956408"
    }
]


def get_instance_info():
    url = f"https://api.novita.ai/gpus/v2/instances/{INSTANCE_ID}"
    r = requests.get(url, headers=NOVITA_HEADERS, timeout=10)
    if r.status_code == 200:
        return r.json()
    raise RuntimeError(f"Erro ao consultar instância Novita ({r.status_code}): {r.text}")


def get_ssh_client(info=None):
    if not info:
        info = get_instance_info()
    ssh_info = info.get("tools", {}).get("ssh", {})
    cmd_str = ssh_info.get("command", "")
    password = ssh_info.get("password")

    port_m = re.search(r"-p\s+(\d+)", cmd_str)
    host_m = re.search(r"root@([\w\.\-]+)", cmd_str)
    if not port_m or not host_m:
        raise ValueError(f"Não foi possível extrair credenciais SSH de: {cmd_str}")

    port = int(port_m.group(1))
    host = host_m.group(1)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, port=port, username="root", password=password, timeout=15)
    return client


def cmd_status():
    print(f"=== STATUS DA INSTÂNCIA GPU NOVITA ({INSTANCE_ID}) ===")
    info = get_instance_info()
    st = info.get("status", {}).get("status")
    name = info.get("name")
    product = info.get("product_id")
    region = info.get("region")
    specs = info.get("resource_specs", {})
    ssh_cmd = info.get("tools", {}).get("ssh", {}).get("command")
    comfy_endpoint = f"https://{INSTANCE_ID}-8188.{region}.gpu-instance.novita.ai"

    print(f"Nome: {name} | Produto: {product} | Região: {region}")
    print(f"Status: {st.upper()}")
    print(f"GPU: {specs.get('gpu_num')}x ({specs.get('memory_gb')} GB RAM / {specs.get('cpu_num')} CPUs)")
    print(f"SSH: {ssh_cmd}")
    print(f"ComfyUI URL: {comfy_endpoint}")

    if st == "running":
        try:
            r = requests.get(f"{comfy_endpoint}/system_stats", timeout=3)
            if r.status_code == 200:
                print("ComfyUI API: ✅ ONLINE (Respondendo HTTP 200)")
            else:
                print(f"ComfyUI API: ⚠️ Status HTTP {r.status_code}")
        except Exception as e:
            print(f"ComfyUI API: ❌ Indisponível no momento ({e})")
    else:
        print("ComfyUI API: ⏸️ Instância pausada.")


def cmd_start():
    print(f"⚡ Solicitando início da instância GPU ({INSTANCE_ID})...")
    url = f"https://api.novita.ai/gpus/v2/instances/{INSTANCE_ID}/start"
    r = requests.put(url, headers=NOVITA_HEADERS, json={}, timeout=10)
    print(f"Resposta API Start: {r.status_code}")

    print("Aguardando inicialização e inicialização do ComfyUI...")
    comfy_endpoint = f"https://{INSTANCE_ID}-8188.us-ca-6.gpu-instance.novita.ai"
    for i in range(35):
        time.sleep(3)
        try:
            info = get_instance_info()
            st = info.get("status", {}).get("status")
            print(f"[{i*3}s] Status da Instância: {st}")
            if st == "running":
                try:
                    cs = requests.get(f"{comfy_endpoint}/system_stats", timeout=3)
                    if cs.status_code == 200:
                        print("🎉 INSTÂNCIA ONLINE E COMFYUI OPERACIONAL!")
                        return True
                except Exception:
                    pass
        except Exception as e:
            print(f"Aviso na checagem: {e}")

    print("⚠️ Timeout aguardando o ComfyUI responder.")
    return False


def cmd_stop():
    print(f"⏸️ Solicitando pausa da instância GPU ({INSTANCE_ID}) para economizar créditos...")
    url = f"https://api.novita.ai/gpus/v2/instances/{INSTANCE_ID}/stop"
    r = requests.put(url, headers=NOVITA_HEADERS, json={}, timeout=10)
    if r.status_code in (200, 204):
        print("✅ Instância pausada com sucesso! Créditos protegidos.")
    else:
        print(f"Aviso ({r.status_code}): {r.text}")


def cmd_list_loras():
    info = get_instance_info()
    st = info.get("status", {}).get("status")
    if st != "running":
        print("Aviso: A instância está pausada. Ligando temporariamente para consulta ou listando via SSH...")
        choice = input("Deseja ligar a instância para listar os modelos? (s/n): ").strip().lower()
        if choice != "s":
            return
        cmd_start()

    print("\n--- Conectando via SSH para inspecionar /root/ComfyUI/models/loras/ ---")
    client = get_ssh_client(info)
    try:
        stdin, stdout, stderr = client.exec_command("ls -lh /root/ComfyUI/models/loras/")
        print(stdout.read().decode())
    finally:
        client.close()


def cmd_sync_loras():
    info = get_instance_info()
    st = info.get("status", {}).get("status")
    if st != "running":
        print("A instância está pausada. Iniciando para sincronização...")
        if not cmd_start():
            print("Não foi possível iniciar a instância. Abortando sincronização.")
            return

    if not CIVITAI_API_KEY:
        print("❌ CIVITAI_API_KEY não configurada no .env. Impossível baixar LoRAs.")
        return

    client = get_ssh_client(info)
    sftp = client.open_sftp()
    remote_dir = "/root/ComfyUI/models/loras"

    print("\nVerificando arquivos existentes no servidor...")
    stdin, stdout, stderr = client.exec_command(f"ls {remote_dir}")
    existing_files = stdout.read().decode().splitlines()

    civ_headers = {"Authorization": f"Bearer {CIVITAI_API_KEY}"}

    try:
        for item in OFFICIAL_LORAS:
            name = item["name"]
            api_url = item["api_url"]
            if name in existing_files:
                print(f"✅ {name} já está instalado.")
                continue

            if not api_url:
                print(f"⚠️ {name} não possui URL de download público cadastrada. Envio manual necessário.")
                continue

            print(f"\n📥 Sincronizando {item['desc']} ({name})...")
            r = requests.get(api_url, headers=civ_headers, allow_redirects=False)
            if r.status_code not in (301, 302, 307):
                print(f"❌ Falha ao obter link de download para {name}: {r.status_code}")
                continue

            direct_url = r.headers.get("Location")
            temp_local = os.path.join(os.getcwd(), f"temp_{name}")

            print(f"Baixando localmente da Civitai...")
            with requests.get(direct_url, stream=True) as resp:
                resp.raise_for_status()
                with open(temp_local, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024*1024):
                        if chunk:
                            f.write(chunk)

            size_mb = os.path.getsize(temp_local) / 1024 / 1024
            print(f"Upload via SFTP para {remote_dir}/{name} ({size_mb:.2f} MB)...")
            sftp.put(temp_local, f"{remote_dir}/{name}")
            print(f"✅ {name} sincronizado com sucesso!")

            try:
                os.remove(temp_local)
            except:
                pass

        print("\n=== LISTAGEM FINAL ATUALIZADA ===")
        stdin, stdout, stderr = client.exec_command(f"ls -lh {remote_dir}")
        print(stdout.read().decode())

    finally:
        sftp.close()
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Gestor Oficial da GPU Novita AI / ComfyUI (Marina Salles)")
    parser.add_argument("command", choices=["status", "start", "stop", "list-loras", "sync-loras"], help="Comando a executar")
    args = parser.parse_args()

    if args.command == "status":
        cmd_status()
    elif args.command == "start":
        cmd_start()
    elif args.command == "stop":
        cmd_stop()
    elif args.command == "list-loras":
        cmd_list_loras()
    elif args.command == "sync-loras":
        cmd_sync_loras()


if __name__ == "__main__":
    main()
