from flask import Blueprint, jsonify, request

from src.backend.services import despertador

despertador_bp = Blueprint("despertador", __name__)


@despertador_bp.route('/api/despertador', methods=['GET'])
def ler_despertador():
    return jsonify({"ok": True, **despertador.retrato()})


@despertador_bp.route('/api/despertador', methods=['POST'])
def armar_despertador():
    dados = request.json or {}
    resultado = despertador.agendar(
        quando=dados.get("quando", ""),
        depois_de=dados.get("depois_de", ""),
        quando_processo=dados.get("quando_processo", ""),
        quando_ficheiro=dados.get("quando_ficheiro", ""),
        nota=dados.get("nota", ""),
    )
    if resultado.get("erro"):
        return jsonify({"ok": False, "error": resultado["erro"]}), 400
    return jsonify({"ok": True, **resultado})


@despertador_bp.route('/api/despertador', methods=['DELETE'])
def desarmar_despertador():
    return jsonify({"ok": True, **despertador.cancelar("cancelado pelo utilizador")})


@despertador_bp.route('/api/despertador/entregue', methods=['POST'])
def marcar_entregue():
    return jsonify(despertador.confirmar_entrega())
