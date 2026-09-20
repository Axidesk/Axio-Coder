import os
import re

from flask import Blueprint, jsonify, request, send_file, send_from_directory
from src.backend.config import APP_ROOT
from src.backend.memory.glossary import load_glossary, save_glossary
from src.backend.services.file_service import resolver_caminho
from src.backend.tools.js_contrato import defeitos_contrato_imports

static_bp = Blueprint("static", __name__)


def _servir_pasta(subpasta, alvo, mimetype):
    """Corpo unico das rotas estaticas: serve um ficheiro de uma pasta do projeto."""
    return send_from_directory(os.path.join(APP_ROOT, *subpasta), alvo, mimetype=mimetype)


@static_bp.route('/editor/<path:p>')
def serve_editor_module(p):
    return _servir_pasta(('src', 'frontend', 'js', 'editor'), p, 'application/javascript')


@static_bp.route('/vendor/socket.io.js')
def serve_socketio_client():
    return _servir_pasta(('node_modules', 'socket.io-client', 'dist'), 'socket.io.min.js', 'application/javascript')

@static_bp.route('/vendor/<path:p>')
def serve_vendor(p):
    return _servir_pasta(('src', 'frontend', 'vendor'), p, None)


@static_bp.route('/monaco/<path:p>')
def serve_monaco(p):
    fname = p.rsplit('/', 1)[-1]
    immutable = bool(re.search(r'-[A-Za-z0-9_-]{8,}\.js$', fname))
    max_age = 31536000 if immutable else 86400
    resp = send_from_directory(os.path.join(APP_ROOT, 'node_modules', 'monaco-editor', 'min'), p, max_age=max_age)
    if immutable:
        resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return resp

@static_bp.route('/xterm/<path:p>')
def serve_xterm(p):
    raiz = os.path.join(APP_ROOT, 'node_modules', '@xterm')
    if p.endswith('.css'):
        mimetype = 'text/css'
    elif p.endswith(('.js', '.mjs')):
        mimetype = 'application/javascript'
    else:
        mimetype = None
    return send_from_directory(raiz, p, mimetype=mimetype)

@static_bp.route('/')
def serve_index():
    return _servir_pasta(('src', 'frontend'), 'index.html', None)


@static_bp.route('/raciocinio')
def serve_raciocinio():
    return _servir_pasta(('src', 'frontend'), 'raciocinio.html', None)


@static_bp.route('/chat/<path:p>')
def serve_chat_module(p):
    return _servir_pasta(('src', 'frontend', 'js', 'chat'), p, 'application/javascript')


@static_bp.route('/boot-guard.js')
def serve_boot_guard():
    """Guard de arranque: script CLASSICO de proposito.

    Todo o resto do frontend sao ES modules, e um modulo so corre depois de
    resolver os seus imports - que e exatamente o que pode estar partido. Um
    guard que tem de sobreviver a modulos mortos nao pode ser um deles.
    """
    return _servir_pasta(('src', 'frontend', 'js'), 'boot-guard.js', 'application/javascript')


@static_bp.route('/api/diagnostico_frontend', methods=['GET'])
def diagnostico_frontend():
    """Imports de modulos locais do frontend que NAO resolvem no disco.

    E a mesma analise (tree-sitter) que trava a restauracao de checkpoint, mas
    sobre o estado ATUAL e sem alteracoes projetadas. O guard de arranque
    consulta-a porque ha avarias que o browser nao reporta de forma apanhável
    (modulo que deixou de existir aborta o fetch antes de qualquer execucao).
    """
    raiz = os.path.join(APP_ROOT, 'src', 'frontend', 'js')
    return jsonify({"defeitos": defeitos_contrato_imports(raiz, {})})


@static_bp.route('/style.css')
def serve_style_css():
    return _servir_pasta(('src', 'frontend'), 'style.css', None)


@static_bp.route('/css/<path:p>')
def serve_css_module(p):
    return _servir_pasta(('src', 'frontend', 'css'), p, 'text/css')


@static_bp.route('/js/<path:p>')
def serve_js_module(p):
    return _servir_pasta(('src', 'frontend', 'js'), p, 'application/javascript')


@static_bp.route('/icons/<path:p>')
def serve_icone(p):
    return _servir_pasta(('data', 'icons'), p, None)


_MIME_EXTRA = {
    '.mjs': 'application/javascript',
    '.jsx': 'application/javascript'
}


@static_bp.route('/preview/<path:p>')
def serve_ficheiro_do_projeto(p):
    """Serve um ficheiro da pasta do projeto para a janela de preview.

    Existe porque por file:// um HTML do projeto nao carrega nada: os caminhos
    absolutos do documento (/css/x.css, /editor/y.js) resolvem contra a raiz do
    disco. Servido daqui, o mesmo documento resolve-os contra o servidor e as
    paginas do proprio Axio funcionam inteiras dentro do preview.
    """
    caminho, erro = resolver_caminho(p, permitir_extra=False)
    if erro or not caminho:
        return jsonify({"error": erro or "caminho invalido"}), 403
    if not os.path.isfile(caminho):
        return jsonify({"error": "ficheiro nao encontrado: " + p}), 404
    extra = _MIME_EXTRA.get(os.path.splitext(caminho)[1].lower())
    resposta = send_file(caminho, mimetype=extra) if extra else send_file(caminho)
    resposta.headers['Cache-Control'] = 'no-store'
    return resposta

@static_bp.route('/api/glossary', methods=['GET'])
def glossary_list():
    return jsonify(load_glossary())

@static_bp.route('/api/glossary', methods=['POST'])
def glossary_add():
    dados = request.json or {}
    termo = (dados.get("termo") or "").strip()
    identificador = (dados.get("identificador") or "").strip()
    if not termo or not identificador:
        return jsonify({"error": "termo e identificador sao obrigatorios"}), 400
    glossary = load_glossary()
    termos = glossary.get("termos", [])
    existente = next((t for t in termos if t.get("identificador") == identificador), None)
    nova_entrada = {
        "termo": termo,
        "aliases": dados.get("aliases") or [],
        "identificador": identificador,
        "descricao": dados.get("descricao") or "",
        "localizacao": dados.get("localizacao") or {}
    }
    if existente:
        existente.update(nova_entrada)
    else:
        termos.append(nova_entrada)
    glossary["termos"] = termos
    save_glossary(glossary)
    return jsonify({"ok": True, "entrada": nova_entrada})

@static_bp.route('/api/glossary/validate', methods=['GET'])
def glossary_validate():
    glossary = load_glossary()
    termos = glossary.get("termos", [])
    base = APP_ROOT
    resultado = []
    for t in termos:
        identificador = (t.get("identificador") or "").strip()
        loc = t.get("localizacao") or {}
        arquivo = (loc.get("arquivo") or "").strip()
        valido = False
        motivo = "arquivo nao especificado"
        if arquivo:
            caminho = os.path.join(base, arquivo)
            if os.path.exists(caminho):
                try:
                    with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
                        conteudo = f.read()
                    if identificador.startswith(("#", ".")):
                        alvo = identificador[1:]
                    else:
                        alvo = identificador
                    valido = alvo in conteudo
                    motivo = "ok" if valido else "identificador nao encontrado no arquivo"
                except Exception as e:
                    motivo = "erro ao ler: %s" % e
            else:
                motivo = "arquivo nao encontrado"
        resultado.append({
            "termo": t.get("termo"),
            "identificador": identificador,
            "arquivo": arquivo,
            "valido": valido,
            "motivo": motivo
        })
    return jsonify({"resultado": resultado})
