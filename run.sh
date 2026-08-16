#!/usr/bin/env bash
# Chạy ứng dụng (Linux / WSL). Tự tạo venv + cài dependencies lần đầu.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Tạo môi trường ảo và cài dependencies (lần đầu)..."
  python3 -m venv .venv
  .venv/bin/python -m pip install -U pip
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python main.py
