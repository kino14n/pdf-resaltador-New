import os
import re
import tempfile
import uuid

import fitz
from flask import Flask, request, render_template, send_file, flash, redirect, url_for
from werkzeug.utils import secure_filename
from pdf2image import convert_from_path
from pytesseract import image_to_string

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'clave-secreta-para-dev')

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
    for c in re.split(r'[\n,]+', codigos_raw):
        c = c.strip()
        if c:
            c = re.sub(r'[\s\r]+', '', c)
            codigos.append(c)
    return codigos

def buscar_y_resaltar(pdf_path, codigos):
    doc = fitz.open(pdf_path)
    paginas_resaltadas = set()
    codigos_encontrados = {}
    codigos_no_encontrados = set(codigos)

    # Búsqueda texto directo
    for page_num in range(len(doc)):
        pagina = doc[page_num]
        for codigo in list(codigos_no_encontrados):
            rects = pagina.search_for(codigo)
            if rects:
                for r in rects:
                    highlight = pagina.add_highlight_annot(r)
                    highlight.set_colors(stroke=(0,1,0))
                    highlight.update()
                paginas_resaltadas.add(page_num)
                codigos_encontrados.setdefault(codigo, []).append(page_num + 1)
                codigos_no_encontrados.remove(codigo)

    # Fallback OCR
    if codigos_no_encontrados:
       images = convert_from_path(pdf_path, dpi=120)  # menor DPI, menos RAM, más rápido
        for page_num, image in enumerate(images):
            if not codigos_no_encontrados:
                break
            texto_ocr = image_to_string(image)
            pagina = doc[page_num]
            for codigo in list(codigos_no_encontrados):
                if codigo in texto_ocr:
                    rects = pagina.search_for(codigo)
                    for r in rects:
                        highlight = pagina.add_highlight_annot(r)
                        highlight.set_colors(stroke=(0,1,0))
                        highlight.update()
                    paginas_resaltadas.add(page_num)
                    codigos_encontrados.setdefault(codigo, []).append(page_num + 1)
                    codigos_no_encontrados.remove(codigo)

    if not paginas_resaltadas:
        doc.close()
        return None, codigos_encontrados, codigos_no_encontrados

    doc_nuevo = fitz.open()
    for p in sorted(paginas_resaltadas):
        doc_nuevo.insert_pdf(doc, from_page=p, to_page=p)

    out_path = os.path.join(app.config['PROCESSED_FOLDER'], f"resaltado_{uuid.uuid4().hex}.pdf")
    doc_nuevo.save(out_path)
    doc_nuevo.close()
    doc.close()
    return out_path, codigos_encontrados, codigos_no_encontrados

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    encontrados = {}
    no_encontrados = set()
    resultado_pdf = None

    if request.method == 'POST':
        pdf_file = request.files.get('pdf_file')
        codigos_raw = request.form.get('specific_codes', '')

        if not pdf_file or not allowed_file(pdf_file.filename):
            flash('Debes subir un archivo PDF válido.', 'error')
            return redirect(url_for('index'))

        codigos = limpiar_codigos(codigos_raw)
        if not codigos:
            flash('Debes ingresar al menos un código para buscar.', 'error')
            return redirect(url_for('index'))

        filename = secure_filename(pdf_file.filename)
        input_pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4().hex}_{filename}")
        pdf_file.save(input_pdf_path)

        try:
            resultado_pdf, encontrados, no_encontrados = buscar_y_resaltar(input_pdf_path, codigos)
        except Exception as e:
            flash(f"Error procesando el PDF: {e}", 'error')
            return redirect(url_for('index'))
        finally:
            try:
                os.remove(input_pdf_path)
            except Exception:
                pass

        if not resultado_pdf:
            flash('No se encontraron códigos en el PDF.', 'error')

    return render_template(
        'index.html',
        error=error,
        encontrados=encontrados,
        no_encontrados=no_encontrados,
        resultado_pdf=resultado_pdf
    )

@app.route('/descargar/<path:filename>')
def descargar(filename):
    path = os.path.join(app.config['PROCESSED_FOLDER'], filename)
    if not os.path.exists(path):
        flash('Archivo no encontrado para descargar.', 'error')
        return redirect(url_for('index'))
    return send_file(path, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)