import fitz  # PyMuPDF
import re
from flask import Flask, request, make_response, abort, jsonify
import os
import json
import io
import logging

# Configuración de logging para que se vea en Railway
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

def search_and_highlight(pdf_bytes: bytes, codes_to_find: set) -> (bytes, list):
    """
    Abre un PDF desde bytes, busca cada código usando dos estrategias de texto,
    y devuelve un nuevo PDF (en bytes) con SOLO las páginas que tuvieron coincidencias,
    resaltando el texto en naranja. También devuelve una lista de las páginas encontradas.
    """
    if not codes_to_find:
        raise ValueError("La lista de códigos a buscar está vacía.")

    src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    pages_with_matches_indices = []
    orange_color = (1, 0.75, 0) # Naranja (RGB en formato 0-1)

    # Paso 1: Identificar todas las páginas que tienen al menos una coincidencia
    for page in src_doc:
        found_on_page = False
        for code in codes_to_find:
            # Estrategia 1: Búsqueda de texto normal (ignora mayúsculas/minúsculas)
            if page.search_for(code, flags=re.IGNORECASE):
                found_on_page = True
                break  # Si se encuentra, no es necesario seguir buscando en esta página
            
            # Estrategia 2: Búsqueda de texto con espaciado (para tus PDFs especiales)
            spaced_out_code = " ".join(list(code))
            if page.search_for(spaced_out_code, flags=re.IGNORECASE):
                found_on_page = True
                break
        
        if found_on_page:
            pages_with_matches_indices.append(page.number)

    # Si no se encontró ninguna coincidencia en todo el documento, devolvemos None
    if not pages_with_matches_indices:
        src_doc.close()
        return None, []

    # Paso 2: Crear un nuevo documento y copiar solo las páginas con coincidencias
    app.logger.info(f"Coincidencias encontradas en las páginas (índice 0): {pages_with_matches_indices}.")
    new_doc = fitz.open()
    new_doc.insert_pdf(src_doc, from_page=pages_with_matches_indices[0], to_pages=pages_with_matches_indices)

    # Paso 3: Aplicar el resaltado en el NUEVO documento
    for page in new_doc:
        for code in codes_to_find:
            # Búsqueda normal
            instances = page.search_for(code, flags=re.IGNORECASE)
            for inst in instances:
                annot = page.add_highlight_annot(inst)
                annot.set_colors(stroke=orange_color)
                annot.update()
            
            # Búsqueda con espaciado
            spaced_out_code = " ".join(list(code))
            instances_spaced = page.search_for(spaced_out_code, flags=re.IGNORECASE)
            for inst in instances_spaced:
                annot = page.add_highlight_annot(inst)
                annot.set_colors(stroke=orange_color)
                annot.update()

    result_bytes = new_doc.tobytes(garbage=4, deflate=True)
    src_doc.close()
    new_doc.close()
    
    # Devolver el PDF en bytes y la lista de números de página (empezando en 1)
    return result_bytes, [p + 1 for p in pages_with_matches_indices]

@app.route('/highlight', methods=['POST'])
def highlight():
    """
    Endpoint para recibir el PDF y los códigos.
    Espera los campos 'pdf_file' y 'codes'.
    """
    app.logger.info("="*50)
    app.logger.info("Nueva solicitud POST en /highlight.")

    if 'pdf_file' not in request.files:
        abort(400, "Parámetro 'pdf_file' (archivo) no encontrado.")
    
    file = request.files['pdf_file']
    codes_str = request.form.get('codes', '')

    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        abort(400, "Es necesario un archivo con extensión .pdf.")
    if not codes_str.strip():
        abort(400, "Parámetro 'codes' (códigos a buscar) no encontrado o vacío.")

    try:
        codes_to_find = set(filter(None, re.split(r'[\s,;\n]+', codes_str.strip())))
        pdf_bytes = file.read()

        out_bytes, pages_found = search_and_highlight(pdf_bytes, codes_to_find)

        if not out_bytes:
            abort(404, "No se encontraron los códigos en el documento.")

        response = make_response(out_bytes)
        response.headers.set('Content-Type', 'application/pdf')
        response.headers.set('Content-Disposition', 'inline', filename='resultado.pdf')
        response.headers.set('X-Pages-Found', json.dumps(sorted(pages_found)))
        
        return response

    except Exception as e:
        app.logger.error(f"EXCEPCIÓN INESPERADA: {e}", exc_info=True)
        abort(500, f"Error interno del servidor: {e}")

# Añadimos una ruta raíz para verificar que el servicio está funcionando
@app.route('/', methods=['GET'])
def root():
    return jsonify({"status": "ok", "message": "Servicio de Resaltado de PDF está en línea. Usa el endpoint POST /highlight para procesar archivos."})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
