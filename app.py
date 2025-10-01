import fitz  # PyMuPDF
import re
from flask import Flask, request, make_response, render_template, flash, redirect, url_for
import os
import json

app = Flask(__name__)
# Es una buena práctica usar una clave secreta desde las variables de entorno para producción.
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

def highlight_codes_on_page(page, codes_to_find):
    """
    Busca y resalta códigos en una página de forma case-insensitive (ignorando mayúsculas/minúsculas).
    Esta función es más robusta porque busca el texto completo en lugar de palabra por palabra.
    """
    found_on_page = False
    
    # Iterar sobre cada código que necesitamos encontrar
    for code in codes_to_find:
        # Usar la función search_for con la bandera re.IGNORECASE para la búsqueda
        # El flag re.IGNORECASE hace que la búsqueda no distinga entre mayúsculas y minúsculas.
        text_instances = page.search_for(code, flags=re.IGNORECASE)
        
        # Si se encontraron instancias de este código, resaltarlas
        if text_instances:
            found_on_page = True
            for inst in text_instances:
                # Crear un rectángulo sobre el texto encontrado y añadir el resaltado
                highlight = page.add_highlight_annot(inst)
    
    return found_on_page

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Validar que el archivo y los códigos fueron enviados
        if 'pdf_file' not in request.files:
            flash('No se envió ningún archivo PDF.', 'error')
            return redirect(request.url)
        
        file = request.files['pdf_file']
        specific_codes_str = request.form.get('specific_codes', '')

        if file.filename == '' or not specific_codes_str.strip():
            flash('Es necesario seleccionar un archivo PDF y proporcionar al menos un código.', 'error')
            return redirect(request.url)

        if file and file.filename.lower().endswith('.pdf'):
            try:
                # Procesar la lista de códigos, eliminando vacíos y duplicados
                codes_to_find = set(filter(None, re.split(r'[\s,;\n]+', specific_codes_str.strip())))
                
                # Cargar el PDF desde los bytes recibidos
                pdf_bytes = file.read()
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                
                pages_found = set()

                # Recorrer cada página del documento
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    # Usar la nueva función de resaltado mejorada
                    if highlight_codes_on_page(page, codes_to_find):
                        pages_found.add(page_num + 1)
                
                # Guardar el PDF modificado en memoria para enviarlo como respuesta
                output_pdf_bytes = doc.tobytes()
                doc.close()

                # Preparar la respuesta que se enviará de vuelta al navegador
                response = make_response(output_pdf_bytes)
                response.headers.set('Content-Type', 'application/pdf')
                response.headers.set('Content-Disposition', 'inline', filename='resaltado.pdf')
                # Enviar la lista de páginas encontradas en una cabecera personalizada
                response.headers.set('X-Pages-Found', json.dumps(sorted(list(pages_found))))
                
                return response

            except Exception as e:
                # Capturar cualquier error inesperado durante el procesamiento
                flash(f'Ocurrió un error al procesar el PDF: {e}', 'error')
                app.logger.error(f"Error procesando PDF: {e}")
                return redirect(request.url)
        else:
            flash('Formato de archivo no válido. Por favor, sube un PDF.', 'error')
            return redirect(request.url)

    # Si la solicitud es GET, simplemente mostrar el formulario de subida
    return render_template('index.html')

if __name__ == '__main__':
    # Configuración para que funcione tanto localmente como en Railway
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
