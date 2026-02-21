#!/bin/bash
set -e

# Install system dependencies
# Note: libcamera and its Python bindings come pre-installed on Raspberry Pi OS
sudo apt update
sudo apt install -y python3-dev python3-venv build-essential libcap-dev libjpeg-dev

# Create virtual environment with system site packages to access libcamera
if [ ! -d ".venv" ]; then
    python3 -m venv --system-site-packages .venv
fi

# Activate virtual environment and install packages
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "Setup complete! Run the program with: .venv/bin/python record.py"