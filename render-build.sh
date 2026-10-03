#!/bin/bash
set -e
pip uninstall -y python-telegram-bot || true
pip cache purge || true
pip install --no-cache-dir python-telegram-bot==20.7
pip install --no-cache-dir -r requirements.txt
