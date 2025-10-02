
<?php 
// api.php

// Manejo de solicitud OPTIONS para CORS
if ($_SERVER['REQUEST_METHOD'] == 'OPTIONS') {
    header("Access-Control-Allow-Origin: *");
    header("Access-Control-Allow-Methods: POST, GET, OPTIONS");
    header("Access-Control-Allow-Headers: Content-Type, Authorization");
    http_response_code(200);
    exit();
}

ini_set('display_errors', 1);
error_reporting(E_ALL);

require_once __DIR__ . '/config.php';

header('Content-Type: application/json');
$dsn = "mysql:host=" . DB_HOST . ";port=" . DB_PORT . ";dbname=" . DB_NAME . ";charset=utf8mb4";
try {
    $db = new PDO($dsn, DB_USER, DB_PASS, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(['error' => 'Error de conexión: '.$e->getMessage()]);
    exit;
}

$action = $_REQUEST['action'] ?? '';

switch ($action) {

  case 'get_config':
    echo json_encode([
      'headerTitle' => APP_HEADER_TITLE,
      'logoPath'    => APP_LOGO_PATH
    ]);
    break;
  
  case 'get_public_config':
    echo json_encode([
      'headerTitle' => PUBLIC_HEADER_TITLE,
      'logoPath'    => PUBLIC_LOGO_PATH
    ]);
    break;

  case 'suggest':
    $term = trim($_GET['term'] ?? '');
    if ($term === '') { echo json_encode([]); exit; }
    $stmt = $db->prepare("SELECT DISTINCT code FROM codes WHERE code LIKE ? ORDER BY code ASC LIMIT 10");
    $stmt->execute([$term . '%']);
    echo json_encode($stmt->fetchAll(PDO::FETCH_COLUMN));
    break;

  case 'upload':
    $name  = $_POST['name'] ?? '';
    $date  = $_POST['date'] ?? '';
    $codes = array_filter(array_map('trim', preg_split('/\\r?\\n/', $_POST['codes'] ?? '')));
    $file  = $_FILES['file'] ?? null;
    if (!$name || !$date || !$file || $file['error'] !== UPLOAD_ERR_OK) { http_response_code(400); echo json_encode(['error'=>'Faltan datos o hubo un error al subir el archivo.']); exit; }
    $filename = time().'_'.preg_replace("/[^a-zA-Z0-9\._-]/", "_", basename($file['name']));
    if (!move_uploaded_file($file['tmp_name'], __DIR__.'/uploads/'.$filename)) { http_response_code(500); echo json_encode(['error'=>'No se pudo guardar el archivo.']); exit; }
    $db->prepare('INSERT INTO documents (name,date,path) VALUES (?,?,?)')->execute([$name,$date,$filename]);
    $docId = $db->lastInsertId();
    $ins = $db->prepare('INSERT INTO codes (document_id,code) VALUES (?,?)');
    foreach (array_unique($codes) as $c) { $ins->execute([$docId,$c]); }
    echo json_encode(['message'=>'Documento guardado.']);
    break;

  case 'list':
    $stmt = $db->query("SELECT d.id,d.name,d.date,d.path, GROUP_CONCAT(c.code SEPARATOR '\\n') AS codes FROM documents d LEFT JOIN codes c ON d.id=c.document_id GROUP BY d.id ORDER BY d.date DESC");
    $rows = $stmt->fetchAll();
    $docs = array_map(function($r){ return ['id'=>(int)$r['id'], 'name'=>$r['name'], 'date'=>$r['date'], 'path'=>$r['path'], 'codes'=>$r['codes'] ? explode("\\n",$r['codes']) : []]; }, $rows);
    echo json_encode(['data'=>$docs]);
    break;

  case 'search':
    $codes_to_find = array_filter(array_unique(array_map('trim', preg_split('/[\\r\\n,]+/', $_POST['codes'] ?? ''))));
    if (empty($codes_to_find)) {
        echo json_encode([]);
        exit;
    }

    $placeholders = implode(',', array_fill(0, count($codes_to_find), '?'));
    $stmt = $db->prepare("
        SELECT d.id, d.name, d.date, d.path, GROUP_CONCAT(c.code SEPARATOR '|') AS codes
        FROM documents d
        JOIN codes c ON d.id = c.document_id
        WHERE c.code IN ($placeholders)
        GROUP BY d.id, d.name, d.date, d.path
        ORDER BY d.date DESC
    ");
    $stmt->execute($codes_to_find);
    $all_docs_raw = $stmt->fetchAll();

    $candidate_docs = [];
    foreach ($all_docs_raw as $doc) {
        $candidate_docs[$doc['id']] = [
            'id' => (int)$doc['id'],
            'name' => $doc['name'],
            'date' => $doc['date'],
            'path' => $doc['path'],
            'codes' => $doc['codes'] ? explode('|', $doc['codes']) : []
        ];
    }

    $remaining_codes = array_flip($codes_to_find);
    $selected_docs = [];

    while (!empty($remaining_codes) && !empty($candidate_docs)) {
        $best_doc_id = -1;
        $max_covered_count = -1;
        
        foreach ($candidate_docs as $doc_id => $doc) {
            $covered_codes = array_intersect_key(array_flip($doc['codes']), $remaining_codes);
            $covered_count = count($covered_codes);

            if ($covered_count > $max_covered_count) {
                $max_covered_count = $covered_count;
                $best_doc_id = $doc_id;
            }
        }
        
        if ($best_doc_id === -1 || $max_covered_count === 0) {
            break;
        }

        $best_doc = $candidate_docs[$best_doc_id];
        $selected_docs[$best_doc_id] = $best_doc;

        foreach ($best_doc['codes'] as $code) {
            unset($remaining_codes[$code]);
        }
        
        unset($candidate_docs[$best_doc_id]);
    }
    
    echo json_encode(array_values($selected_docs));
    break;

  case 'download_pdfs':
    $uploadsDir = __DIR__ . '/uploads';
    if (!is_dir($uploadsDir)) { http_response_code(500); echo json_encode(['error'=>'Carpeta uploads no encontrada']); exit; }
    $zip = new ZipArchive();
    $zipFileName = 'documentos_'.date('Ymd_His').'.zip';
    $zipFilePath = sys_get_temp_dir() . '/' . $zipFileName;
    if ($zip->open($zipFilePath, ZipArchive::CREATE | ZipArchive::OVERWRITE) !== TRUE) { http_response_code(500); echo json_encode(['error'=>'No se pudo crear el ZIP.']); exit; }
    $files = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($uploadsDir, RecursiveDirectoryIterator::SKIP_DOTS), RecursiveIteratorIterator::LEAVES_ONLY);
    foreach ($files as $file) {
        if (!$file->isDir()) {
            $filePath = $file->getRealPath();
            $relativePath = substr($filePath, strlen($uploadsDir) + 1);
            $zip->addFile($filePath, $relativePath);
        }
    }
    $zip->close();
    header('Content-Type: application/zip');
    header('Content-Disposition: attachment; filename="' . basename($zipFileName) . '"');
    header('Content-Length: ' . filesize($zipFilePath));
    readfile($zipFilePath);
    unlink($zipFilePath);
    exit;

  case 'edit':
    $id = (int)($_POST['id'] ?? 0);
    $name = $_POST['name'] ?? '';
    $date = $_POST['date'] ?? '';
    if (!$id || !$name || !$date) { http_response_code(400); echo json_encode(['error'=>'Faltan datos.']); exit; }
    $codes = array_filter(array_map('trim', preg_split('/\\r?\\n/', $_POST['codes'] ?? '')));
    if (!empty($_FILES['file']['tmp_name'])) {
      $old = $db->prepare('SELECT path FROM documents WHERE id=?');
      $old->execute([$id]);
      if ($path = $old->fetchColumn()) { @unlink(__DIR__.'/uploads/'.$path); }
      $fn = time().'_'.preg_replace("/[^a-zA-Z0-9\._-]/", "_", basename($_FILES['file']['name']));
      move_uploaded_file($_FILES['file']['tmp_name'], __DIR__.'/uploads/'.$fn);
      $db->prepare('UPDATE documents SET name=?,date=?,path=? WHERE id=?')->execute([$name,$date,$fn,$id]);
    } else {
      $db->prepare('UPDATE documents SET name=?,date=? WHERE id=?')->execute([$name,$date,$id]);
    }
    $db->prepare('DELETE FROM codes WHERE document_id=?')->execute([$id]);
    $ins = $db->prepare('INSERT INTO codes (document_id,code) VALUES (?,?)');
    foreach (array_unique($codes) as $c) { $ins->execute([$id,$c]); }
    echo json_encode(['message'=>'Documento actualizado.']);
    break;

  case 'delete':
    $id = (int)($_GET['id'] ?? 0);
    if (!$id) { http_response_code(400); echo json_encode(['error'=>'ID no válido.']); exit; }
    $old = $db->prepare('SELECT path FROM documents WHERE id=?');
    $old->execute([$id]);
    if ($pathToDelete = $old->fetchColumn()) { @unlink(__DIR__.'/uploads/'.$pathToDelete); }
    $db->prepare('DELETE FROM codes WHERE document_id=?')->execute([$id]);
    $db->prepare('DELETE FROM documents WHERE id=?')->execute([$id]);
    echo json_encode(['message'=>'Documento eliminado.']);
    break;

  case 'search_by_code':
    $code = trim($_POST['code'] ?? '');
    if (!$code) { echo json_encode([]); exit; }
    $stmt = $db->prepare("SELECT d.id, d.name, d.date, d.path, GROUP_CONCAT(c2.code SEPARATOR '\\n') AS codes FROM documents d JOIN codes c1 ON d.id = c1.document_id LEFT JOIN codes c2 ON d.id = c2.document_id WHERE c1.code = ? GROUP BY d.id");
    $stmt->execute([$code]);
    $rows = $stmt->fetchAll();
    $docs = array_map(function($r){ return ['id'=>(int)$r['id'], 'name'=>$r['name'], 'date'=>$r['date'], 'path'=>$r['path'], 'codes'=>$r['codes'] ? explode("\\n", $r['codes']) : []]; }, $rows);
    echo json_encode($docs);
    break;

  case 'highlight_pdf':
    header_remove('Content-Type');
    $docId = (int)($_POST['id'] ?? 0);
    $codesToHighlight = array_filter(array_map('trim', explode(',', $_POST['codes'] ?? '')));
    if (!$docId || empty($codesToHighlight)) { 
        http_response_code(400); 
        echo json_encode(['error' => 'Faltan parámetros.']); 
        exit; 
    }
    
    $stmt = $db->prepare('SELECT path FROM documents WHERE id = ?');
    $stmt->execute([$docId]);
    $path = $stmt->fetchColumn();

    $full_path_to_check = __DIR__ . '/uploads/' . $path;
    if (!$path || !file_exists($full_path_to_check)) {
        http_response_code(404);
        echo json_encode([
            'error' => 'Archivo no encontrado en el servidor.',
            'debug_info' => 'PHP no pudo encontrar el archivo en la ruta: ' . $full_path_to_check
        ]);
        exit;
    }
    
    $pdfFilePath = $full_path_to_check;

    $ch = curl_init();
    
    $postData = [
        'specific_codes' => implode("\n", $codesToHighlight), 
        'pdf_file'       => new CURLFile($pdfFilePath, 'application/pdf', basename($pdfFilePath))
    ];

    curl_setopt($ch, CURLOPT_URL, PDF_HIGHLIGHTER_URL);
    curl_setopt($ch, CURLOPT_POST, 1);
    curl_setopt($ch, CURLOPT_POSTFIELDS, $postData);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    
    $responseHeaders = [];
    curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, false);
    curl_setopt($ch, CURLOPT_HEADERFUNCTION, function($curl, $header) use (&$responseHeaders) {
        $len = strlen($header);
        $header = explode(':', $header, 2);
        if (count($header) < 2) return $len;
        $responseHeaders[strtolower(trim($header[0]))][] = trim($header[1]);
        return $len;
    });
    
    $highlightedPdf = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $error = curl_error($ch);
    curl_close($ch);

    if ($httpCode === 200 && $highlightedPdf) {
        header('Content-Type: application/pdf');
        header('Content-Disposition: attachment; filename="resaltado_' . basename($pdfFilePath) . '"');
        if (isset($responseHeaders['x-pages-found'])) {
            header('X-Pages-Found: ' . $responseHeaders['x-pages-found'][0]);
            header('Access-Control-Expose-Headers: X-Pages-Found');
        }
        echo $highlightedPdf;
    } else {
        http_response_code(500);
        header('Content-Type: application/json');
        echo json_encode(['error' => 'El servicio de resaltado falló.', 'details' => $error ? 'cURL error: ' . $error : 'HTTP status: ' . $httpCode]);
    }
    exit;

  default:
    http_response_code(400);
    echo json_encode(['error'=>'Acción inválida.']);
    break;
}
