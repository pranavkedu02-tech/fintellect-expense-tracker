#!/usr/bin/env bash
# Exit immediately if any command fails
set -o errexit

# Install Tesseract OCR at the system level (Render's Linux environment)
apt-get update
apt-get install -y tesseract-ocr

# Install Python dependencies
pip install -r requirements.txt

# Collect all static files (CSS/JS) into one production-ready folder
python manage.py collectstatic --noinput

# Apply any pending database migrations (for SQLite/auth tables)
python manage.py migrate