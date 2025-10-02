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

def highlight_codes_on_page(page, codes_to_find):
    """
    Busca y resalta códigos en una página.
    Primero intenta leer el texto palabra por palabra y limpiarlo.
    Si eso falla, usa OCR como respaldo.
    """
    found_on_page = False
    
    # --- ESTRATEGIA 1: BÚSQUEDA DE TEXTO INTELIGENTE ---
    app.logger.info(f"Iniciando búsqueda de texto inteligente en la página {page.number + 1}.")
    
    words = page.get_text("words")
    codes_to_find_lower = {c.lower() for c in codes_to_find}

    for word_tuple in words:
        # La tupla es (x0, y0, x1, y1, "texto", ...)
        word_text_original = word_tuple[4]
        
        # Limpiar la palabra extraída eliminando todos los espacios y caracteres no alfanuméricos (excepto guiones)
        cleaned_word = re.sub(r'[^a-zA-Z0-9-]', '', word_text_original)
        
        if cleaned_word and cleaned_word.lower() in codes_to_find_lower:
            found_on_page = True
            rect = fitz.Rect(word_tuple[0], word_tuple[1], word_tuple[2], word_tuple[3])
            page.add_highlight_annot(rect)
            app.logger.info(f"¡COINCIDENCIA DE TEXTO! Código '{cleaned_word}' encontrado en la página {page.number + 1}.")
            
    if found_on_page:
        return True

    # --- ESTRATEGIA 2: RESPALDO CON OCR (para PDFs que son imágenes) ---
    app.logger.warning(f"La búsqueda de texto normal falló. Intentando con OCR en la página {page.number + 1}.")
    try:
        pix = page.get_pixmap(dpi=200) # Usamos 200 DPI para un buen balance entre velocidad y precisión
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))
        
        ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, lang='spa') # 'spa' para español
        
        n_boxes = len(ocr_data['level'])
        for i in range(n_boxes):
            word_text = ocr_data['text'][i].strip()
            cleaned_word = re.sub(r'[^a-zA-Z0-9-]', '', word_text)
            
            if cleaned_word and cleaned_word.lower() in codes_to_find_lower:
                found_on_page = True
                app.logger.info(f"¡COINCIDENCIA CON OCR! Código '{cleaned_word}' encontrado.")
                (x, y, w, h) = (ocr_data['left'][i], ocr_data['top'][i], ocr_data['width'][i], ocr_data['height'][i])
                
                # Convertir coordenadas de imagen a coordenadas de PDF
                zoom_x = pix.width / page.rect.width
                zoom_y = pix.height / page.rect.height
                
                rect = fitz.Rect(x / zoom_x, y / zoom_y, (x + w) / zoom_x, (y + h) / zoom_y)
                page.add_highlight_annot(rect)
                
    except Exception as e:
        app.logger.error(f"Error durante el proceso de OCR: {e}")

    return found_on_page

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        app.logger.info("="*50)
        app.logger.info("Nueva solicitud POST recibida.")

        if 'pdf_file' not in request.files or 'specific_codes' not in request.form:
             app.logger.error("Solicitud inválida: Faltan 'pdf_file' o 'specific_codes'.")
             return "Faltan datos", 400
        
        file = request.files['pdf_file']
        specific_codes_str = request.form.get('specific_codes', '')

        if file.filename == '' or not specific_codes_str.strip():
            app.logger.error("Archivo PDF o códigos no proporcionados.")
            return "Archivo o códigos no proporcionados", 400

        try:
            codes_to_find = set(filter(None, re.split(r'[\s,;\n]+', specific_codes_str.strip())))
            app.logger.info(f"Buscando los siguientes códigos: {list(codes_to_find)}")

            pdf_bytes = file.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            app.logger.info(f"PDF '{file.filename}' abierto con {len(doc)} páginas.")
            
            pages_with_highlights_indices = []

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                if highlight_codes_on_page(page, codes_to_find):
                    pages_with_highlights_indices.append(page_num)
            
            if pages_with_highlights_indices:
                app.logger.info(f"Coincidencias encontradas en las páginas (índice 0): {pages_with_highlights_indices}. Creando PDF nuevo.")
                new_doc = fitz.open()
                new_doc.insert_pdf(doc, from_page=pages_with_highlights_indices[0], to_pages=pages_with_highlights_indices)
                output_pdf_bytes = new_doc.tobytes(garbage=4, deflate=True, clean=True)
                new_doc.close()
            else:
                app.logger.info("No se encontraron coincidencias. Devolviendo el PDF original.")
                output_pdf_bytes = doc.tobytes()

            doc.close()
            
            pages_found_user_friendly = [p + 1 for p in pages_with_highlights_indices]
            app.logger.info(f"Proceso finalizado. Páginas con coincidencias: {pages_found_user_friendly}")

            response = make_response(output_pdf_bytes)
            response.headers.set('Content-Type', 'application/pdf')
            response.headers.set('Content-Disposition', 'inline', filename='resultado.pdf')
            response.headers.set('X-Pages-Found', json.dumps(sorted(pages_found_user_friendly)))
            
            return response

        except Exception as e:
            app.logger.error(f"EXCEPCIÓN INESPERADA: {e}", exc_info=True)
            return f"Error interno: {e}", 500

    return render_template('index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
