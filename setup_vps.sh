#!/usr/bin/env bash
# Script para configurar e rodar o bot na VPS Linux (Ubuntu / Debian)

set -e

echo "=== Instalando dependências do sistema ==="
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git

echo "=== Criando ambiente virtual ==="
python3 -m venv venv
source venv/bin/activate

echo "=== Instalando bibliotecas Python ==="
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Instalação concluída! ==="
echo "Edite o arquivo .env com suas chaves e rode: python3 bot.py"
