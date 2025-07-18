FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    libmupdf-dev \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

EXPOSE 8080

ENV PORT=8080

# Aumenta el timeout y limita a 1 worker (ideal para contenedor chico/OCR)
CMD exec gunicorn app:app -b 0.0.0.0:${PORT} --timeout 180 --workers 1
