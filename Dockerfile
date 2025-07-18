# Usa imagen oficial de Python ligera
FROM python:3.10-slim

# Instala dependencias del sistema necesarias para PyMuPDF y OCR
RUN apt-get update && apt-get install -y \
    build-essential \
    libmupdf-dev \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Establece directorio de trabajo
WORKDIR /app

# Copia los archivos del proyecto
COPY . /app

# Instala las dependencias de Python
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expone el puerto
EXPOSE 5000

# Define el comando por defecto para correr la app
CMD ["python", "app.py"]
