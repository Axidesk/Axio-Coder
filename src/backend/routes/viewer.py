from flask import Blueprint, jsonify, request, send_file

from src.backend.services import cache_modelos
from src.backend.services.file_service import resolver_caminho

viewer_bp = Blueprint("viewer", __name__)


def _alvo():
    relativo = (request.args.get("caminho") or "").strip()
    if not relativo:
        return None, (jsonify({"error": "caminho em falta"}), 400)
    caminho, erro = resolver_caminho(relativo, permitir_extra=False)
    if erro or not caminho:
        return None, (jsonify({"error": erro or "caminho invalido"}), 403)
    return caminho, None


@viewer_bp.route('/api/modelo_convertido', methods=['GET'])
def modelo_convertido():
    caminho, falha = _alvo()
    if falha:
        return falha
    guardado = cache_modelos.ler(caminho)
    if not guardado:
        return '', 204
    resposta = send_file(guardado, mimetype='application/octet-stream')
    resposta.headers['Cache-Control'] = 'no-store'
    return resposta


@viewer_bp.route('/api/modelo_convertido', methods=['POST'])
def guardar_modelo_convertido():
    caminho, falha = _alvo()
    if falha:
        return falha
    conteudo = request.get_data()
    if not conteudo:
        return jsonify({"error": "corpo vazio"}), 400
    guardado = cache_modelos.gravar(caminho, conteudo)
    if not guardado:
        return jsonify({"error": "origem indisponivel"}), 409
    return jsonify({"ok": True, "bytes": len(conteudo), "removidos": cache_modelos.limpar_excedente()})
