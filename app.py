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
    Busca y resalta códigos en una página usando tres estrategias:
    1. Búsqueda de texto normal.
    2. Búsqueda de texto con espaciado.
    3. Búsqueda con OCR como último recurso.
    """
    found_on_page = False
    
    # --- ESTRATEGIA 1: BÚSQUEDA DE TEXTO NORMAL ---
    app.logger.info(f"Página {page.number + 1}: Iniciando Estrategia 1 (Búsqueda Normal).")
    for code in codes_to_find:
        instances = page.search_for(code, flags=re.IGNORECASE)
        if instances:
            found_on_page = True
            for inst in instances:
                page.add_highlight_annot(inst)
            app.logger.info(f"ÉXITO (Normal): Código '{code}' encontrado en la página {page.number + 1}.")
    if found_on_page:
        return True

    # --- ESTRATEGIA 2: BÚSQUEDA DE TEXTO CON ESPACIADO ---
    app.logger.info(f"Página {page.number + 1}: Estrategia 1 falló. Iniciando Estrategia 2 (Búsqueda con Espaciado).")
    for code in codes_to_find:
        # Crear una versión del código con espacios (ej: "C-O-D-E")
        spaced_out_code = " ".join(code)
        instances = page.search_for(spaced_out_code, flags=re.IGNORECASE)
        if instances:
            found_on_page = True
            for inst in instances:
                page.add_highlight_annot(inst)
            app.logger.info(f"ÉXITO (Espaciado): Código '{code}' encontrado en la página {page.number + 1}.")
    if found_on_page:
        return True

    # --- ESTRATEGIA 3: RESPALDO CON OCR ---
    app.logger.warning(f"Página {page.number + 1}: Estrategias 1 y 2 fallaron. Iniciando Estrategia 3 (OCR).")
    try:
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))
        ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, lang='spa')
        
        n_boxes = len(ocr_data['level'])
        codes_to_find_lower = {c.lower() for c in codes_to_find}
        for i in range(n_boxes):
            word_text = ocr_data['text'][i].strip()
            # Limpiar la palabra leída por el OCR
            cleaned_word = re.sub(r'[^a-zA-Z0-9-]', '', word_text)
            
            if cleaned_word and cleaned_word.lower() in codes_to_find_lower:
                found_on_page = True
                app.logger.info(f"ÉXITO (OCR): Código '{cleaned_word}' encontrado en la página {page.number + 1}.")
                (x, y, w, h) = (ocr_data['left'][i], ocr_data['top'][i], ocr_data['width'][i], ocr_data['height'][i])
                
                zoom_x = pix.width / page.rect.width
                zoom_y = pix.height / page.rect.height
                
                rect = fitz.Rect(x / zoom_x, y / zoom_y, (x + w) / zoom_x, (y + h) / zoom_y)
                page.add_highlight_annot(rect)
    except Exception as e:
        app.logger.error(f"Error durante el proceso de OCR en la página {page.number + 1}: {e}")

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
                app.logger.info(f"Coincidencias encontradas. Creando PDF nuevo solo con páginas: {[p + 1 for p in pages_with_highlights_indices]}.")
                new_doc = fitz.open()
                new_doc.insert_pdf(doc, from_page=pages_with_highlights_indices[0], to_pages=pages_with_highlights_indices)
                output_pdf_bytes = new_doc.tobytes(garbage=4, deflate=True, clean=True)
                new_doc.close()
            else:
                app.logger.info("No se encontraron coincidencias en ninguna página. Devolviendo el PDF original.")
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
