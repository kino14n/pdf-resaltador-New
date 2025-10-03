import fitz  # PyMuPDF
import re
from flask import Flask, request, make_response, render_template
import os
import json
import logging

# Configuración de logging para que se vea en Railway
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

def highlight_codes_on_page(page, codes_to_find):
    """
    Busca y resalta códigos usando una estrategia de texto limpio y robusto.
    """
    found_on_page = False
    
    # Obtener el texto completo de la página una sola vez
    page_text = page.get_text("text")
    if not page_text.strip():
        app.logger.info(f"Página {page.number + 1} no contiene texto extraíble.")
        return False
        
    # Crear una versión "limpia" del texto de la página: sin espacios y en minúsculas
    cleaned_page_text = re.sub(r'\s+', '', page_text).lower()

    for code in codes_to_find:
        # Limpiar también el código a buscar
        cleaned_code = re.sub(r'\s+', '', code).lower()

        # 1. VERIFICAR SI EXISTE: Comprobar si el código limpio está en el texto limpio.
        if cleaned_code in cleaned_page_text:
            app.logger.info(f"Coincidencia encontrada para '{code}' en la página {page.number + 1}. Buscando área para resaltar.")
            
            # 2. ENCONTRAR PARA RESALTAR: Ahora que sabemos que existe, buscamos el texto original para obtener las coordenadas.
            # Intentamos buscar la versión normal y la versión con espacios.
            
            # Intento 1: Búsqueda Normal
            instances = page.search_for(code, flags=re.IGNORECASE)
            if instances:
                found_on_page = True
                for inst in instances:
                    page.add_highlight_annot(inst)
                app.logger.info(f"Resaltado con búsqueda normal para '{code}'.")

            # Intento 2: Búsqueda con Espaciado
            spaced_out_code = " ".join(list(code))
            instances_spaced = page.search_for(spaced_out_code, flags=re.IGNORECASE)
            if instances_spaced:
                found_on_page = True
                for inst in instances_spaced:
                    page.add_highlight_annot(inst)
                app.logger.info(f"Resaltado con búsqueda espaciada para '{code}'.")
            
            # Si se encontró en el texto limpio pero no se pudo resaltar, dejar un aviso.
            if not found_on_page:
                 app.logger.warning(f"Se encontró una coincidencia para '{code}', pero no se pudo localizar el área exacta en el PDF para resaltar.")

    return found_on_page

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        app.logger.info("="*50)
        app.logger.info("Nueva solicitud POST recibida.")

        if 'pdf_file' not in request.files or 'specific_codes' not in request.form:
             app.logger.error("Solicitud inválida: Faltan 'pdf_file' o 'specific_codes'.")
             return "Solicitud inválida: Faltan 'pdf_file' o 'specific_codes'.", 400
        
        file = request.files['pdf_file']
        specific_codes_str = request.form.get('specific_codes', '')

        if file.filename == '' or not specific_codes_str.strip():
            app.logger.error("Archivo PDF o códigos no proporcionados.")
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
                new_doc.insert_pdf(doc, from_page=pages_with_highlights_indices[0], to_pages=pages_with_highlights_indices)
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
