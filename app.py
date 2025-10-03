import fitz  # PyMuPDF
import re
from flask import Flask, request, make_response, abort
import os
import json
import io

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

def search_and_highlight(pdf_bytes: bytes, codes_to_find: set) -> (bytes, list):
    """
    Abre un PDF desde bytes, busca cada código en todas las páginas y devuelve
    un nuevo PDF (en bytes) con SOLO las páginas que tuvieron coincidencias,
    resaltando el texto en naranja. También devuelve una lista de las páginas encontradas.
    """
    if not codes_to_find:
        raise ValueError("La lista de códigos a buscar está vacía.")

    src_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    pages_with_matches = []
    highlight_color = (1, 0.75, 0) # Color Naranja

    # Primer paso: Iterar y encontrar las páginas que tienen coincidencias
    for page in src_doc:
        found_on_page = False
        for code in codes_to_find:
            # Estrategia 1: Búsqueda normal (ignora mayúsculas/minúsculas)
            if page.search_for(code, flags=re.IGNORECASE):
                found_on_page = True
                break # Si ya encontramos un código, pasamos a la siguiente página
            
            # Estrategia 2: Búsqueda con espaciado (para tus PDFs especiales)
            spaced_out_code = " ".join(list(code))
            if page.search_for(spaced_out_code, flags=re.IGNORECASE):
                found_on_page = True
                break
        
        if found_on_page:
            pages_with_matches.append(page.number)

    if not pages_with_matches:
        src_doc.close()
        return None, []

    # Segundo paso: Crear un nuevo PDF y añadir solo las páginas encontradas
    new_doc = fitz.open()
    new_doc.insert_pdf(src_doc, from_page=pages_with_matches[0], to_pages=pages_with_matches)

    # Tercer paso: Aplicar el resaltado en el nuevo documento
    for page in new_doc:
        for code in codes_to_find:
            # Búsqueda normal
            instances = page.search_for(code, flags=re.IGNORECASE)
            for inst in instances:
                annot = page.add_highlight_annot(inst)
                annot.set_colors(stroke=highlight_color)
                annot.update()
            
            # Búsqueda con espaciado
            spaced_out_code = " ".join(list(code))
            instances_spaced = page.search_for(spaced_out_code, flags=re.IGNORECASE)
            for inst in instances_spaced:
                annot = page.add_highlight_annot(inst)
                annot.set_colors(stroke=highlight_color)
                annot.update()

    result_bytes = new_doc.tobytes(garbage=4, deflate=True)
    src_doc.close()
    new_doc.close()
    
    # Devolver el PDF en bytes y la lista de números de página (empezando en 1)
    return result_bytes, [p + 1 for p in pages_with_matches]

@app.route('/highlight', methods=['POST'])
def highlight():
    """
    Endpoint para recibir el PDF y los códigos.
    """
    # 1. Validar la entrada
    if 'pdf_file' not in request.files:
        abort(400, "Parámetro 'pdf_file' (archivo) no encontrado.")
    
    file = request.files['pdf_file']
    codes_str = request.form.get('codes', '')

    if file.filename == '' or not file.filename.lower().endswith('.pdf'):
        abort(400, "Es necesario un archivo con extensión .pdf.")
    if not codes_str.strip():
        abort(400, "Parámetro 'codes' (códigos a buscar) no encontrado o vacío.")

    try:
        # 2. Preparar los datos
        codes_to_find = set(filter(None, re.split(r'[\s,;\n]+', codes_str.strip())))
        pdf_bytes = file.read()

        # 3. Llamar a la función principal
        out_bytes, pages_found = search_and_highlight(pdf_bytes, codes_to_find)

        # 4. Manejar el resultado
        if not out_bytes:
            abort(404, f"No se encontraron los códigos en el documento.")

        response = make_response(out_bytes)
        response.headers.set('Content-Type', 'application/pdf')
        response.headers.set('Content-Disposition', 'inline', filename='resultado.pdf')
        response.headers.set('X-Pages-Found', json.dumps(sorted(pages_found)))
        
        return response

    except Exception as e:
        app.logger.error(f"EXCEPCIÓN INESPERADA: {e}", exc_info=True)
        abort(500, f"Error interno del servidor: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
