#!/bin/bash
set -e

echo "=== 进入项目目录 ==="
cd /opt/render/project/src

echo "=== 清理 venv 内的旧版本 ==="
.venv/bin/pip uninstall -y python-telegram-bot 2>/dev/null || true
.venv/bin/pip cache purge 2>/dev/null || true

echo "=== 强制安装纯净版 20.7 ==="
.venv/bin/pip install --no-cache-dir --force-reinstall python-telegram-bot==20.7
.venv/bin/pip install --no-cache-dir -r requirements.txt

echo "=== 验证版本 ==="
.venv/bin/python -c "import telegram; print('✅ 安装版本:', telegram.__version__)"
