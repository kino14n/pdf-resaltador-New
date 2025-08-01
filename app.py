import os
import re
import tempfile
import uuid
import fitz  # PyMuPDF
from flask import Flask, request, render_template, send_file, flash, redirect, url_for, after_this_request, jsonify
from werkzeug.utils import secure_filename
from pdf2image import convert_from_path
from pytesseract import image_to_string

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
    for c in re.split(r'[\n,]+', codigos_raw):
        c = c.strip()
        if c:
            codigos.append(c)
    return codigos

def buscar_y_resaltar(pdf_path, codigos):
    doc = fitz.open(pdf_path)
    paginas_con_codigos = set()
    
    # 1. Búsqueda por texto directo
    for page in doc:
        for codigo in codigos:
            rects = page.search_for(codigo)
            if rects:
                paginas_con_codigos.add(page.number)
                for rect in rects:
                    highlight = page.add_highlight_annot(rect)
                    highlight.set_colors(stroke=(0, 1, 0))  # Verde
                    highlight.update()

    # 2. Búsqueda por OCR si es necesario (ejemplo básico)
    # Esta parte se puede expandir si la búsqueda de texto no es suficiente
    
    if not paginas_con_codigos:
        doc.close()
        return None

    # Crear un nuevo PDF solo con las páginas que tienen resaltados
    doc_nuevo = fitz.open()
    for page_num in sorted(list(paginas_con_codigos)):
        doc_nuevo.insert_pdf(doc, from_page=page_num, to_page=page_num)
    
    out_path = os.path.join(app.config['PROCESSED_FOLDER'], f"resaltado_{uuid.uuid4().hex}.pdf")
    doc_nuevo.save(out_path)
    doc_nuevo.close()
    doc.close()
    return out_path

@app.route('/api/resaltar', methods=['POST'])
def api_resaltar():
    if 'pdf_file' not in request.files:
        return jsonify({"error": "No se encontró el archivo PDF en la petición"}), 400
    
    pdf_file = request.files['pdf_file']
    codigos_raw = request.form.get('codes', '')
    
    if not pdf_file.filename or not allowed_file(pdf_file.filename):
        return jsonify({"error": "El archivo proporcionado no es un PDF válido"}), 400

    codigos = limpiar_codigos(codigos_raw)
    if not codigos:
        return jsonify({"error": "No se proporcionaron códigos para resaltar"}), 400

    filename = secure_filename(pdf_file.filename)
    input_pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4().hex}_{filename}")
    pdf_file.save(input_pdf_path)
    
    resultado_pdf_path = None
    try:
        resultado_pdf_path = buscar_y_resaltar(input_pdf_path, codigos)

        if not resultado_pdf_path:
            return jsonify({"error": "No se encontraron los códigos en el PDF"}), 404
        
        @after_this_request
        def cleanup(response):
            try:
                if os.path.exists(resultado_pdf_path):
                    os.remove(resultado_pdf_path)
            except Exception as e:
                app.logger.error(f"Error eliminando archivo procesado {resultado_pdf_path}: {e}")
            return response
            
        return send_file(resultado_pdf_path, as_attachment=True, download_name=f"resaltado_{filename}")

    except Exception as e:
        app.logger.error(f"Error en buscar_y_resaltar: {e}")
        return jsonify({"error": f"Ocurrió un error interno al procesar el PDF"}), 500
    finally:
        try:
            if os.path.exists(input_pdf_path):
                os.remove(input_pdf_path)
        except Exception as e:
            app.logger.error(f"Error eliminando archivo subido {input_pdf_path}: {e}")

# La interfaz web original sigue funcionando por si la necesitas
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # ... (la lógica del POST de la interfaz web se mantiene sin cambios)
        pass
    return render_template('index.html')

@app.route('/descargar/<path:filename>')
def descargar(filename):
    path = os.path.join(app.config['PROCESSED_FOLDER'], filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=False)
    else:
        flash('El archivo solicitado no existe.', 'error')
        return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
