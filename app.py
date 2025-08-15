import os
import re
import tempfile
import uuid
import fitz  # PyMuPDF
from flask import Flask, request, render_template, send_file, flash, redirect, url_for, after_this_request
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'clave-secreta-para-desarrollo')

UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'uploads')
PROCESSED_FOLDER = os.path.join(tempfile.gettempdir(), 'processed')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def limpiar_codigos(codigos_raw):
    codigos = []
    if not codigos_raw:
        return codigos
    # Se usa re.split para manejar comas y saltos de línea como separadores
    for c in re.split(r'[\\n,]+', codigos_raw):
        c = c.strip()
        if c:
            codigos.append(c)
    return list(set(codigos)) # Devuelve códigos únicos

def buscar_y_resaltar(pdf_path, codigos):
    doc = fitz.open(pdf_path)
    paginas_con_codigos = set()
    
    encontrados = {} # {'codigo': [página1, página2]}
    
    # Búsqueda por texto directo
    for page in doc:
        for codigo in codigos:
            rects = page.search_for(codigo, quads=True) # Búsqueda exacta
            if rects:
                paginas_con_codigos.add(page.number)
                highlight = page.add_highlight_annot(rects)
                
                # --- LÍNEA MODIFICADA ---
                # Cambiado de (0, 1, 0) a (0, 0.5, 0) para un verde más oscuro
                highlight.set_colors(stroke=(0, 0.5, 0)) 
                
                highlight.update()
                
                # Guardar en qué página se encontró
                if codigo not in encontrados:
                    encontrados[codigo] = []
                # Añadir número de página real (page.number + 1)
                if page.number + 1 not in encontrados[codigo]:
                    encontrados[codigo].append(page.number + 1)

    # Determinar qué códigos no se encontraron
    codigos_encontrados = set(encontrados.keys())
    no_encontrados = [c for c in codigos if c not in codigos_encontrados]

    if not paginas_con_codigos:
        doc.close()
        # Devuelve que no se creó archivo, los encontrados (vacío) y los no encontrados (todos)
        return None, encontrados, no_encontrados

    # Crear un nuevo PDF solo con las páginas que tienen resaltados
    doc_nuevo = fitz.open()
    for page_num in sorted(list(paginas_con_codigos)):
        doc_nuevo.insert_pdf(doc, from_page=page_num, to_page=page_num)
    
    out_filename = f"resaltado_{uuid.uuid4().hex}.pdf"
    out_path = os.path.join(app.config['PROCESSED_FOLDER'], out_filename)
    doc_nuevo.save(out_path, garbage=4, deflate=True, clean=True)
    doc_nuevo.close()
    doc.close()
    
    # Devuelve la ruta del archivo, los códigos encontrados y los no encontrados
    return out_path, encontrados, no_encontrados

@app.route('/', methods=['GET', 'POST'])
def index():
    # Inicializa las variables para pasarlas siempre al template
    render_context = {
        'encontrados': None,
        'no_encontrados': None,
        'resultado_pdf': None
    }

    if request.method == 'POST':
        if 'pdf_file' not in request.files:
            flash('No se seleccionó ningún archivo.', 'error')
            return redirect(request.url)
        
        pdf_file = request.files['pdf_file']
        codigos_raw = request.form.get('specific_codes', '')

        if pdf_file.filename == '':
            flash('No se seleccionó ningún archivo.', 'error')
            return redirect(request.url)

        if not allowed_file(pdf_file.filename):
            flash('El archivo proporcionado no es un PDF válido.', 'error')
            return redirect(request.url)
        
        codigos = limpiar_codigos(codigos_raw)
        if not codigos:
            flash('No se proporcionaron códigos para resaltar.', 'error')
            return redirect(request.url)

        filename = secure_filename(pdf_file.filename)
        input_pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4().hex}_{filename}")
        pdf_file.save(input_pdf_path)
        
        try:
            # La función ahora devuelve tres valores
            resultado_pdf_path, encontrados, no_encontrados = buscar_y_resaltar(input_pdf_path, codigos)
            
            # Actualiza el contexto con los resultados
            render_context['encontrados'] = encontrados
            render_context['no_encontrados'] = no_encontrados

            if resultado_pdf_path:
                render_context['resultado_pdf'] = os.path.basename(resultado_pdf_path)
                flash('Procesamiento completado.', 'success')
            else:
                flash('No se encontró ninguno de los códigos en el documento.', 'error')

            @after_this_request
            def cleanup(response):
                try:
                    if os.path.exists(input_pdf_path):
                        os.remove(input_pdf_path)
                except Exception as e:
                    app.logger.error(f"Error limpiando archivo subido: {e}")
                return response
            
        except Exception as e:
            app.logger.error(f"Error crítico en el procesamiento del PDF: {e}")
            flash(f'Ocurrió un error inesperado al procesar el PDF: {e}', 'error')
        
        # Renderiza la misma página pero con los resultados
        return render_template('index.html', **render_context)

    # Para el método GET, simplemente muestra la página inicial
    return render_template('index.html', **render_context)

@app.route('/descargar/<path:filename>')
def descargar(filename):
    path = os.path.join(app.config['PROCESSED_FOLDER'], filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=False)
    else:
        flash('El archivo solicitado no existe o ya ha sido eliminado.', 'error')
        return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)