import fitz  # PyMuPDF
import re
from flask import Flask, request, make_response, render_template
import os
import json
import logging
import pytesseract
from PIL import Image
import io

# Configuración de logging para que se vea en Railway
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

def check_tesseract():
    """Verifica si Tesseract está instalado y es ejecutable."""
    try:
        pytesseract.get_tesseract_version()
        languages = pytesseract.get_languages()
        app.logger.info(f"Tesseract encontrado. Idiomas disponibles: {languages}")
        if 'spa' in languages:
            app.logger.info("El paquete de idioma español ('spa') está instalado.")
            return True
        else:
            app.logger.warning("ADVERTENCIA: Tesseract está instalado, pero falta el paquete de idioma español ('spa').")
            return False
    except pytesseract.TesseractNotFoundError:
        app.logger.error("ERROR CRÍTICO: El ejecutable de Tesseract no se encontró. El OCR estará deshabilitado.")
        return False
    except Exception as e:
        app.logger.error(f"Error inesperado al verificar Tesseract: {e}")
        return False

# Verificar Tesseract una sola vez al iniciar la aplicación
TESSERACT_AVAILABLE = check_tesseract()

def highlight_codes_on_page(page, codes_to_find):
    """
    Busca y resalta códigos usando múltiples estrategias.
    """
    found_on_page = False
    
    # Estrategia 1: Búsqueda de texto normal (rápida)
    for code in codes_to_find:
        instances = page.search_for(code, flags=re.IGNORECASE)
        if instances:
            found_on_page = True
            for inst in instances:
                page.add_highlight_annot(inst)
    if found_on_page:
        app.logger.info(f"ÉXITO (Estrategia 1 - Normal) en página {page.number + 1}.")
        return True

    # Estrategia 2: Búsqueda de texto con espaciado
    for code in codes_to_find:
        spaced_out_code = " ".join(list(code))
        instances = page.search_for(spaced_out_code, flags=re.IGNORECASE)
        if instances:
            found_on_page = True
            for inst in instances:
                page.add_highlight_annot(inst)
    if found_on_page:
        app.logger.info(f"ÉXITO (Estrategia 2 - Espaciado) en página {page.number + 1}.")
        return True

    # Estrategia 3: Respaldo con OCR (solo si Tesseract está bien configurado)
    if TESSERACT_AVAILABLE:
        app.logger.warning(f"Estrategias de texto fallaron. Ejecutando Estrategia 3 (OCR) en la página {page.number + 1}.")
        try:
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            ocr_data = pytesseract.image_to_data(img, lang='spa', output_type=pytesseract.Output.DICT)
            
            n_boxes = len(ocr_data['level'])
            codes_to_find_lower = {c.lower() for c in codes_to_find}
            for i in range(n_boxes):
                word_text = ocr_data['text'][i].strip()
                cleaned_word = re.sub(r'[^a-zA-Z0-9-]', '', word_text)
                
                if cleaned_word and cleaned_word.lower() in codes_to_find_lower:
                    found_on_page = True
                    (x, y, w, h) = (ocr_data['left'][i], ocr_data['top'][i], ocr_data['width'][i], ocr_data['height'][i])
                    zoom_x = pix.width / page.rect.width
                    zoom_y = pix.height / page.rect.height
                    rect = fitz.Rect(x / zoom_x, y / zoom_y, (x + w) / zoom_x, (y + h) / zoom_y)
                    page.add_highlight_annot(rect)
            if found_on_page:
                app.logger.info(f"ÉXITO (OCR) en página {page.number + 1}.")
        except Exception as e:
            app.logger.error(f"Error durante el proceso de OCR: {e}")
    else:
        app.logger.warning(f"OCR no disponible o mal configurado. Saltando Estrategia 3.")

    return found_on_page

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'pdf_file' not in request.files or 'specific_codes' not in request.form:
             return "Solicitud inválida: Faltan 'pdf_file' o 'specific_codes'.", 400
        
        file = request.files['pdf_file']
        specific_codes_str = request.form.get('specific_codes', '')

        if file.filename == '' or not specific_codes_str.strip():
            return "Archivo PDF o códigos no proporcionados.", 400

        try:
            codes_to_find = set(filter(None, re.split(r'[\s,;\n]+', specific_codes_str.strip())))
            pdf_bytes = file.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            pages_with_highlights_indices = []

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                if highlight_codes_on_page(page, codes_to_find):
                    pages_with_highlights_indices.append(page_num)
            
            if pages_with_highlights_indices:
                new_doc = fitz.open()
                new_doc.insert_pdf(doc, from_page_p=pages_with_highlights_indices)
                output_pdf_bytes = new_doc.tobytes(garbage=4, deflate=True, clean=True)
                new_doc.close()
            else:
                output_pdf_bytes = doc.tobytes()

            doc.close()
            
            pages_found_user_friendly = [p + 1 for p in pages_with_highlights_indices]
            response = make_response(output_pdf_bytes)
            response.headers.set('Content-Type', 'application/pdf')
            response.headers.set('Content-Disposition', 'inline', filename='resultado.pdf')
            response.headers.set('X-Pages-Found', json.dumps(sorted(pages_found_user_friendly)))
            
            return response
        except Exception as e:
            app.logger.error(f"EXCEPCIÓN INESPERADA: {e}", exc_info=True)
            return f"Error interno del servidor: {e}", 500

    return render_template('index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
