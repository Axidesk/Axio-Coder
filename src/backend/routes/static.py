import os
import re

from flask import Blueprint, jsonify, request, send_from_directory
from src.backend.config import APP_ROOT
from src.backend.memory.glossary import load_glossary, save_glossary

static_bp = Blueprint("static", __name__)

@static_bp.route('/editor/<path:p>')
def serve_editor_module(p):
    return send_from_directory(
        os.path.join(APP_ROOT, 'src', 'frontend', 'js', 'editor'), p,
        mimetype='application/javascript')

@static_bp.route('/vendor/socket.io.js')
def serve_socketio_client():
    return send_from_directory(
        os.path.join(APP_ROOT, 'node_modules', 'socket.io-client', 'dist'),
        'socket.io.min.js', mimetype='application/javascript')

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
    return send_from_directory(os.path.join(APP_ROOT, 'src', 'frontend'), 'index.html')

@static_bp.route('/chat/<path:p>')
def serve_chat_module(p):
    return send_from_directory(
        os.path.join(APP_ROOT, 'src', 'frontend', 'js', 'chat'), p,
        mimetype='application/javascript')

@static_bp.route('/style.css')
def serve_style_css():
    return send_from_directory(os.path.join(APP_ROOT, 'src', 'frontend'), 'style.css')

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
