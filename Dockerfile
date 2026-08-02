FROM python:3.12-slim

# Install system-level dependencies: Tesseract OCR, PostgreSQL client
# libraries, plus build tools needed to compile some Python packages
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    build-essential \
    pkg-config \
    libjpeg-dev \
    zlib1g-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD python manage.py migrate --noinput && gunicorn expense_tracker.wsgi:application --bind 0.0.0.0:$PORT