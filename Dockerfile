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

# Exponer el puerto (opcional, Render lo detecta, pero ayuda a clarity)
EXPOSE 8080

# Usa la variable de entorno PORT si existe, si no 8080
ENV PORT=8080

# Comando para iniciar Gunicorn usando la variable PORT
CMD exec gunicorn app:app -b 0.0.0.0:${PORT}
