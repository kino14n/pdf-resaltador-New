# PDF Extractor y Resaltador de Códigos

Proyecto Flask para subir un PDF, buscar códigos exactos, resaltarlos en verde y devolver un PDF solo con las páginas que contienen los códigos encontrados.

Incluye fallback OCR para buscar códigos en imágenes si no se encuentran directamente.

## Requisitos

- Python 3.8+
- Tesseract OCR instalado (https://github.com/tesseract-ocr/tesseract)

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

```bash
python app.py
```

Abrir navegador en http://localhost:5000, subir PDF y poner códigos separados por coma o salto de línea.

## Deploy

Se puede desplegar en Render, Railway, Heroku, etc.