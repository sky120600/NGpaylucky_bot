#!/bin/bash
set -e
echo "=== 清理旧版本 ==="
pip uninstall -y python-telegram-bot python-telegram-bot-job-queue 2>/dev/null || true
pip cache purge 2>/dev/null || true

echo "=== 安装纯净版 v20.7 ==="
pip install --no-cache-dir --force-reinstall python-telegram-bot==20.7
pip install --no-cache-dir --force-reinstall python-telegram-bot[job-queue]==20.7

echo "=== 验证版本 ==="
python -c "import telegram; print('✅ 当前版本:', telegram.__version__)"
