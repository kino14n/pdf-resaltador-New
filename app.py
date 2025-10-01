import fitz  # PyMuPDF
import re
from flask import Flask, request, make_response, render_template, flash, redirect, url_for
import os
import json
import logging

# Configuración de logging para que se vea en Railway
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

def highlight_codes_on_page(page, codes_to_find):
    """
    Busca y resalta códigos en una página de forma case-insensitive.
    """
    found_on_page = False
    page_text = page.get_text("text").lower() # Obtener todo el texto de la página en minúsculas

    # Log para ver el texto extraído (solo los primeros 300 caracteres)
    app.logger.info(f"--- Texto extraído de la página (primeros 300 chars): '{page_text[:300]}...'")

    # Si la página casi no tiene texto, probablemente es una imagen.
    if len(page_text.strip()) < 20:
        app.logger.warning(f"La página {page.number + 1} tiene muy poco texto. Puede que sea una imagen escaneada.")

    for code in codes_to_find:
        # Buscar el código (en minúsculas) dentro del texto de la página
        if code.lower() in page_text:
            app.logger.info(f"¡COINCIDENCIA ENCONTRADA! Buscando '{code}' en la página {page.number + 1}.")
            # Usar search_for para obtener las coordenadas exactas y resaltar
            text_instances = page.search_for(code, flags=re.IGNORECASE)
            
            if text_instances:
                found_on_page = True
                for inst in text_instances:
                    highlight = page.add_highlight_annot(inst)
                app.logger.info(f"Resaltadas {len(text_instances)} instancia(s) de '{code}'.")
        else:
            # Log si un código específico no se encuentra en el texto de la página
            app.logger.info(f"El código '{code}' no se encontró en la página {page.number + 1}.")
            
    return found_on_page

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        app.logger.info("="*50)
        app.logger.info("Nueva solicitud POST recibida para resaltar PDF.")

        if 'pdf_file' not in request.files:
            app.logger.error("No se encontró 'pdf_file' en la solicitud.")
            return "No se envió ningún archivo PDF.", 400
        
        file = request.files['pdf_file']
        specific_codes_str = request.form.get('specific_codes', '')

        if file.filename == '' or not specific_codes_str.strip():
            app.logger.error("Falta el archivo PDF o los códigos.")
            return "Falta el archivo PDF o los códigos.", 400

        if file and file.filename.lower().endswith('.pdf'):
            try:
                codes_to_find = set(filter(None, re.split(r'[\s,;\n]+', specific_codes_str.strip())))
                app.logger.info(f"Códigos recibidos para buscar: {list(codes_to_find)}")

                pdf_bytes = file.read()
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                app.logger.info(f"PDF '{file.filename}' abierto con {len(doc)} páginas.")
                
                pages_found = set()

                for page_num in range(len(doc)):
                    app.logger.info(f"Procesando página {page_num + 1}...")
                    page = doc.load_page(page_num)
                    if highlight_codes_on_page(page, codes_to_find):
                        pages_found.add(page_num + 1)
                
                output_pdf_bytes = doc.tobytes()
                doc.close()
                app.logger.info(f"Proceso finalizado. Páginas con coincidencias: {sorted(list(pages_found))}")

                response = make_response(output_pdf_bytes)
                response.headers.set('Content-Type', 'application/pdf')
                response.headers.set('Content-Disposition', 'inline', filename='resaltado.pdf')
                response.headers.set('X-Pages-Found', json.dumps(sorted(list(pages_found))))
                
                return response

            except Exception as e:
                app.logger.error(f"EXCEPCIÓN INESPERADA: {e}", exc_info=True)
                return f"Ocurrió un error interno: {e}", 500
        else:
            return "Formato de archivo no válido.", 400

    return render_template('index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
