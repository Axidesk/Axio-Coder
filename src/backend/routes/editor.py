import os
import base64

from flask import Blueprint, request, jsonify
from src.backend.state import estado, MSG_SEM_PASTA
from src.backend.services.file_service import (
    resolver_caminho,
    resolver_caminho_arquivo,
    entradas_diretorio,
    raiz_abs,
    calcular_posicao_relativa,
    desfazer_edicao,
    refazer_edicao,
    registrar_edicao_para_contexto,
)

editor_bp = Blueprint("editor", __name__)
@editor_bp.route('/api/undo_redo_status', methods=['GET'])
def undo_redo_status():
    files = []
    pasta_raiz = estado.get("pasta_raiz", "")
    for caminho, hist in estado["file_history"].items():
        if hist["undo"] or hist["redo"]:
            files.append({
                "caminho": caminho,
                "nome": os.path.basename(caminho),
                "caminho_relativo": (os.path.relpath(caminho, pasta_raiz).replace("\\", "/") if pasta_raiz else caminho.replace("\\", "/")),
                "can_undo": len(hist["undo"]) > 0,
                "can_redo": len(hist["redo"]) > 0,
                "undo_count": len(hist["undo"]),
                "redo_count": len(hist["redo"]),
            })
    # Ordena pelo nome para facilitar a localização
    files.sort(key=lambda f: f["nome"].lower())
    return jsonify({"files": files})

@editor_bp.route('/api/undo', methods=['POST'])
def undo():
    data = request.json or {}
    caminho = data.get("caminho")
    resultado = desfazer_edicao(caminho)
    if resultado.get("status") == "error":
        return jsonify(resultado), 500
    return jsonify(resultado)

@editor_bp.route('/api/redo', methods=['POST'])
def redo():
    data = request.json or {}
    caminho = data.get("caminho")
    resultado = refazer_edicao(caminho)
    if resultado.get("status") == "error":
        return jsonify(resultado), 500
    return jsonify(resultado)

@editor_bp.route('/api/explorer', methods=['GET'])
def explorer():
    caminho_rel = request.args.get("path", "") or ""
    if not estado.get("pasta_raiz"):
        return jsonify({
            "root": "",
            "path": caminho_rel,
            "cwd": "",
            "relativo": "",
            "dentro_da_raiz": False,
            "raiz_nome": "",
            "entries": [],
            "sem_raiz": True
        })
    caminho_alvo, erro = resolver_caminho(caminho_rel, permitir_extra=True)
    if erro:
        return jsonify({"error": erro}), 400
    if not os.path.isdir(caminho_alvo):
        return jsonify({"error": "não é uma pasta"}), 404
    items = []
    for e in entradas_diretorio(caminho_alvo):
        item = {
            "nome": e["nome"],
            "tipo": e["tipo"],
            "path": (caminho_rel + "/" + e["nome"]) if caminho_rel else e["nome"],
        }
        if e["tipo"] == "file":
            item["ext"] = os.path.splitext(e["nome"])[1].lstrip('.').lower()
        items.append(item)
    items.sort(key=lambda x: (x["tipo"] != "dir", x["nome"].lower()))
    raiz = estado.get("pasta_raiz", "")
    raiz_absoluta = raiz_abs()
    cwd = caminho_alvo
    relativo, dentro = calcular_posicao_relativa(cwd, raiz_absoluta)
    return jsonify({
        "root": raiz,
        "path": caminho_rel,
        "cwd": cwd,
        "relativo": relativo,
        "dentro_da_raiz": dentro,
        "raiz_nome": os.path.basename(raiz_absoluta) if raiz_absoluta else "",
        "entries": items
    })

@editor_bp.route('/api/file_content', methods=['GET'])
def file_content():
    caminho = request.args.get("caminho")
    alvo, erro = resolver_caminho_arquivo(caminho)
    if erro:
        return jsonify({"error": erro}), 400
    try:
        with open(alvo, 'rb') as f:
            raw = f.read()
    except Exception as e:
        return jsonify({"error": str(e)}), 404

    ext = os.path.splitext(alvo)[1].lower()
    img_exts = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico'}
    if ext in img_exts:
        mime = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.bmp': 'image/bmp',
            '.ico': 'image/x-icon',
        }.get(ext, 'application/octet-stream')
        return jsonify({
            "caminho": alvo,
            "tipo": "imagem",
            "mime": mime,
            "data": base64.b64encode(raw).decode('ascii'),
        })

    try:
        conteudo = raw.decode('utf-8')
        return jsonify({"caminho": alvo, "conteudo": conteudo, "tipo": "texto"})
    except UnicodeDecodeError:
        return jsonify({
            "caminho": alvo,
            "tipo": "binario",
            "mensagem": "Arquivo binário (não textual) — não é possível exibi-lo como código.",
        })

@editor_bp.route('/api/search_files', methods=['GET'])
def search_files():
    termo = (request.args.get("termo") or "").strip()
    raiz = raiz_abs()
    if not raiz:
        return jsonify({"error": MSG_SEM_PASTA}), 400
    if not termo:
        return jsonify({"results": []})
    termo_lower = termo.lower()
    ignorar_dirs = {'.git', 'node_modules', 'build', '__pycache__', '.vs', 'Intermediate', 'Binaries', 'Saved', 'dist', '.next', 'venv', '.venv'}
    exts_bin = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.exe', '.dll', '.obj', '.lib', '.pdb', '.so', '.dylib', '.zip', '.pdf', '.pyc'}
    exts_texto = {'.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.html', '.htm', '.css', '.scss', '.less', '.json', '.md', '.cpp', '.cc', '.h', '.hpp', '.c', '.sh', '.bash', '.sql', '.yaml', '.yml', '.xml', '.java', '.cs', '.go', '.rs', '.php', '.rb', '.swift', '.kt', '.lua', '.r', '.txt', '.toml', '.ini', '.cfg', '.env'}
    resultados = []
    for dirpath, dirnames, filenames in os.walk(raiz):
        dirnames[:] = [d for d in dirnames if d not in ignorar_dirs and not d.startswith('.')]
        for fn in filenames:
            if fn.startswith('.'):
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext in exts_bin:
                continue
            if ext and ext not in exts_texto:
                continue
            caminho = os.path.join(dirpath, fn)
            try:
                with open(caminho, 'r', encoding='utf-8', errors='ignore') as f:
                    linhas = f.readlines()
            except Exception:
                continue
            ocorrencias = []
            total = 0
            for i, linha in enumerate(linhas, 1):
                if termo_lower in linha.lower():
                    total += 1
                    if len(ocorrencias) < 100:
                        trecho = linha.strip()
                        if len(trecho) > 160:
                            trecho = trecho[:160] + '…'
                        ocorrencias.append({"linha": i, "trecho": trecho})
            if total > 0:
                rel = os.path.relpath(caminho, raiz)
                resultados.append({"arquivo": rel, "total": total, "ocorrencias": ocorrencias})
            if len(resultados) >= 300:
                break
    return jsonify({"results": resultados, "termo": termo})

@editor_bp.route('/api/file_original', methods=['GET'])
def file_original():
    """Retorna o conteúdo original (antes da primeira edição registrada) do arquivo.

    Usado pela coluna 3 para exibir o estado inicial na ordem cronológica das
    edições da pilha. Se o arquivo foi criado na sessão, retorna criado=True.
    """
    caminho = request.args.get("caminho")
    alvo, erro = resolver_caminho_arquivo(caminho)
    if erro:
        return jsonify({"error": erro}), 400

    hist = estado["file_history"].get(alvo)
    original = None
    criado = False

    if hist and hist["undo"]:
        primeira = hist["undo"][0]
        original = primeira.get("antes")
        criado = original is None
    elif hist and hist["redo"]:
        # Arquivo desfeito até o estado original: a edição mais antiga é a última
        # desfeita (topo invertido da pilha de redo), então usamos hist["redo"][-1].
        primeira = hist["redo"][-1]
        original = primeira.get("antes")
        criado = original is None

    if original is None:
        if criado:
            original = ""
        else:
            # Sem registro de criação, tenta ler o conteúdo atual do disco.
            try:
                with open(alvo, 'r', encoding='utf-8') as f:
                    original = f.read()
            except Exception:
                original = ""

    return jsonify({"caminho": alvo, "conteudo": original, "criado": criado})

@editor_bp.route('/api/file_save', methods=['POST'])
def file_save():
    dados = request.get_json(silent=True) or {}
    caminho = dados.get("caminho") or ""
    conteudo = dados.get("conteudo") or ""
    alvo, erro = resolver_caminho(caminho, permitir_extra=False, permitir_escrita=True)
    if erro:
        return jsonify({"error": erro}), 400
    try:
        eol = "\n"
        try:
            with open(alvo, 'rb') as f_orig:
                amostra = f_orig.read(8192)
            idx = amostra.find(b"\n")
            if idx > 0 and amostra[idx - 1:idx] == b"\r":
                eol = "\r\n"
        except Exception:
            pass
        texto_antigo = None
        try:
            with open(alvo, 'r', encoding='utf-8') as f_antes:
                texto_antigo = f_antes.read()
        except Exception:
            texto_antigo = None
        texto = (conteudo or "").replace("\r\n", "\n").replace("\r", "\n")
        if eol == "\r\n":
            texto = texto.replace("\n", "\r\n")
        with open(alvo, 'w', encoding='utf-8', newline='') as f:
            f.write(texto)
        registrar_edicao_para_contexto(alvo, texto_antigo, texto)
        return jsonify({"caminho": alvo, "status": "salvo"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
