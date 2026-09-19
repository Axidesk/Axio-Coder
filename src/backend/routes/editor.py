import os
import codecs
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
from src.backend.services.busca_texto import buscar_no_projeto

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
    files.sort(key=lambda f: f["nome"].lower())
    return jsonify({"files": files})

def _undo_redo(aplicar):
    """Corpo unico de /api/undo e /api/redo: aplica a acao ao caminho do pedido."""
    caminho = (request.json or {}).get("caminho")
    resultado = aplicar(caminho)
    if resultado.get("status") == "error":
        return jsonify(resultado), 500
    return jsonify(resultado)


@editor_bp.route('/api/undo', methods=['POST'])
def undo():
    return _undo_redo(desfazer_edicao)


@editor_bp.route('/api/redo', methods=['POST'])
def redo():
    return _undo_redo(refazer_edicao)

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

TETO_TEXTO_BYTES = 4 * 1024 * 1024
AMOSTRA_TEXTO_BYTES = 65536
MIME_POR_EXTENSAO = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.bmp': 'image/bmp',
    '.ico': 'image/x-icon',
}

def _parece_texto(caminho):
    with open(caminho, 'rb') as f:
        amostra = f.read(AMOSTRA_TEXTO_BYTES)
    decodificador = codecs.getincrementaldecoder('utf-8')()
    try:
        decodificador.decode(amostra, False)
        return True
    except UnicodeDecodeError:
        return False

def _aviso_nao_textual(alvo):
    """Por que o arquivo nao pode ser mostrado como codigo; None quando e texto."""
    if os.path.splitext(alvo)[1].lower() in MIME_POR_EXTENSAO:
        return {"tipo": "imagem", "mensagem": "Isto e uma imagem.\nClique-a no explorador para a ver no editor."}
    try:
        tamanho = os.path.getsize(alvo)
    except OSError:
        return None
    if tamanho > TETO_TEXTO_BYTES:
        return {"tipo": "binario", "mensagem": f"Arquivo com {tamanho / 1048576:.1f} MB.\nDemasiado grande para exibir como codigo."}
    try:
        if _parece_texto(alvo):
            return None
    except OSError:
        return None
    return {"tipo": "binario", "mensagem": "Arquivo binario.\nNao e possivel exibi-lo como codigo."}

@editor_bp.route('/api/file_content', methods=['GET'])
def file_content():
    caminho = request.args.get("caminho")
    alvo, erro = resolver_caminho_arquivo(caminho)
    if erro:
        return jsonify({"error": erro}), 400
    try:
        tamanho = os.path.getsize(alvo)
    except Exception as e:
        return jsonify({"error": str(e)}), 404

    ext = os.path.splitext(alvo)[1].lower()
    if ext in MIME_POR_EXTENSAO:
        try:
            with open(alvo, 'rb') as f:
                raw = f.read()
        except Exception as e:
            return jsonify({"error": str(e)}), 404
        mime = MIME_POR_EXTENSAO[ext]
        return jsonify({
            "caminho": alvo,
            "tipo": "imagem",
            "mime": mime,
            "data": base64.b64encode(raw).decode('ascii'),
        })

    if tamanho > TETO_TEXTO_BYTES:
        return jsonify({
            "caminho": alvo,
            "tipo": "binario",
            "mensagem": f"Arquivo com {tamanho / 1048576:.1f} MB.\nDemasiado grande para exibir como código.",
        })

    if not _parece_texto(alvo):
        return jsonify({
            "caminho": alvo,
            "tipo": "binario",
            "mensagem": "Arquivo binário.\nNão é possível exibi-lo como código.",
        })

    try:
        with open(alvo, 'rb') as f:
            raw = f.read()
        conteudo = raw.decode('utf-8')
    except (OSError, UnicodeDecodeError):
        return jsonify({
            "caminho": alvo,
            "tipo": "binario",
            "mensagem": "Arquivo binário.\nNão é possível exibi-lo como código.",
        })
    return jsonify({"caminho": alvo, "conteudo": conteudo, "tipo": "texto"})

@editor_bp.route('/api/search_files', methods=['GET'])
def search_files():
    termo = (request.args.get("termo") or "").strip()
    raiz = raiz_abs()
    if not raiz:
        return jsonify({"error": MSG_SEM_PASTA}), 400
    if not termo:
        return jsonify({"results": []})
    return jsonify({"results": buscar_no_projeto(raiz, termo), "termo": termo})

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
        primeira = hist["redo"][-1]
        original = primeira.get("antes")
        criado = original is None

    if original is None:
        if criado:
            original = ""
        else:
            try:
                with open(alvo, 'r', encoding='utf-8') as f:
                    original = f.read()
            except (OSError, UnicodeDecodeError):
                aviso = _aviso_nao_textual(alvo)
                if aviso:
                    return jsonify({"caminho": alvo, "conteudo": "", "criado": False, **aviso})
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
