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

# Color naranja para el resaltado (RGB en formato 0-1)
HIGHLIGHT_COLOR = (1, 0.75, 0)

def check_tesseract():
    """Verifica si Tesseract y el idioma español están disponibles."""
    try:
        pytesseract.get_tesseract_version()
        if 'spa' in pytesseract.get_languages():
            app.logger.info("Tesseract y 'spa' están listos.")
            return True
        else:
            app.logger.warning("Tesseract OK, pero falta el paquete de idioma 'spa'. OCR no funcionará.")
            return False
    except pytesseract.TesseractNotFoundError:
        app.logger.error("Tesseract no encontrado. El OCR está deshabilitado.")
        return False

TESSERACT_AVAILABLE = check_tesseract()

def highlight_codes_on_page(page, codes_to_find):
    """
    Busca y resalta códigos en una página usando múltiples estrategias.
    """
    found_on_page = False
    
    # --- ESTRATEGIA 1: BÚSQUEDA DE TEXTO NORMAL ---
    for code in codes_to_find:
        instances = page.search_for(code, flags=re.IGNORECASE)
        if instances:
            found_on_page = True
            for inst in instances:
                highlight = page.add_highlight_annot(inst)
                highlight.set_colors(stroke=HIGHLIGHT_COLOR) # Aplicar color naranja
                highlight.update()
    
    # --- ESTRATEGIA 2: BÚSQUEDA DE TEXTO CON ESPACIADO ---
    # Se ejecuta siempre para encontrar todas las coincidencias posibles
    for code in codes_to_find:
        spaced_out_code = " ".join(list(code))
        instances = page.search_for(spaced_out_code, flags=re.IGNORECASE)
        if instances:
            found_on_page = True
            for inst in instances:
                highlight = page.add_highlight_annot(inst)
                highlight.set_colors(stroke=HIGHLIGHT_COLOR) # Aplicar color naranja
                highlight.update()

    # --- ESTRATEGIA 3: RESPALDO CON OCR (Solo si Tesseract está disponible) ---
    if TESSERACT_AVAILABLE:
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
                    highlight = page.add_highlight_annot(rect)
                    highlight.set_colors(stroke=HIGHLIGHT_COLOR) # Aplicar color naranja
                    highlight.update()
        except Exception as e:
            app.logger.error(f"Error durante el proceso de OCR: {e}")
    
    return found_on_page

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        app.logger.info("="*50)
        app.logger.info("Nueva solicitud POST recibida.")

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
            
            # Si se encontraron coincidencias, crear un nuevo PDF solo con esas páginas
            if pages_with_highlights_indices:
                app.logger.info(f"Coincidencias encontradas. Creando PDF nuevo solo con páginas: {[p + 1 for p in pages_with_highlights_indices]}.")
                new_doc = fitz.open()
                # Usar la lista de índices para insertar las páginas correctas
                new_doc.insert_pdf(doc, from_page=pages_with_highlights_indices[0], to_pages=pages_with_highlights_indices)
                output_pdf_bytes = new_doc.tobytes(garbage=4, deflate=True, clean=True)
                new_doc.close()
            else:
                # Si no se encontró nada, devolver el documento original
                app.logger.info("No se encontraron coincidencias en ninguna página. Devolviendo el PDF original.")
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
