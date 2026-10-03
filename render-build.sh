#!/bin/bash
set -e
pip uninstall -y python-telegram-bot APScheduler || true
pip cache purge
pip install --no-cache-dir --force-reinstall python-telegram-bot==20.7
pip install --no-cache-dir -r requirements.txt
