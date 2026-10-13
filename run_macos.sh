#!/usr/bin/env bash
# Meteora 全池扫描与筛选器 V3.1  (macOS / Linux)
set -e
cd "$(dirname "$0")"

echo "============================================================"
echo "  Meteora 全池扫描与筛选器 V3.1  (macOS / Linux)"
echo "============================================================"

if [ ! -d ".venv" ]; then
  echo "[1/3] 创建虚拟环境 .venv ..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "[2/3] 检查依赖 ..."
if ! python -c "import streamlit, requests, pandas, dotenv" 2>/dev/null; then
  echo "正在安装依赖 ..."
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
fi

if [ ! -f ".env" ]; then
  echo "提示：未找到 .env，飞书报警不可用。可复制 .env.example 为 .env 后填写。"
fi

echo "[3/3] 启动应用（浏览器将自动打开 http://localhost:8501）..."
streamlit run app.py
