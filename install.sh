#!/bin/bash
set -e

# Install system dependencies (picamera2 must be installed via apt on Raspberry Pi OS)
sudo apt update
sudo apt install -y python3-dev python3-venv build-essential libcap-dev libcamera-dev python3-picamera2

# Create virtual environment with system site packages to access libcamera and picamera2
if [ ! -d ".venv" ]; then
    python3 -m venv --system-site-packages .venv
fi

# Install Python dependencies
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Build Cython extension
.venv/bin/python setup.py build_ext --inplace

echo "Setup complete! Run the program with: .venv/bin/python record.py"