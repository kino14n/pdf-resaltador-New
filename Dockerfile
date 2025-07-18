FROM python:3.10-slim

# Instala dependencias del sistema necesarias para PyMuPDF y OCR
RUN apt-get update && apt-get install -y \
    build-essential \
    libmupdf-dev \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia los archivos del proyecto
COPY . /app

# Instala dependencias de Python
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expone el puerto
EXPOSE 10000

# Toma el puerto de la variable de entorno (Render y Railway lo configuran)
ENV PORT=10000

# Comando para iniciar Gunicorn usando la variable PORT
CMD exec gunicorn app:app -b 0.0.0.0:${PORT}