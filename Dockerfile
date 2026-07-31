FROM python:3.12-slim

# Install system-level dependencies, including Tesseract OCR
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD gunicorn expense_tracker.wsgi:application --bind 0.0.0.0:$PORT
