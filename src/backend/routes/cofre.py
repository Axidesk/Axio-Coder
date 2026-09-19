from flask import Blueprint, jsonify, request

from src.backend.services import cofre

cofre_bp = Blueprint("cofre", __name__)


@cofre_bp.route('/api/cofre', methods=['GET'])
def ler_cofre():
    revelar = (request.args.get("revelar") or "").lower() in ("1", "true", "sim")
    return jsonify({
        "ok": True,
        "entradas": cofre.listar(revelar=revelar),
        "categorias": cofre.categorias(),
    })


@cofre_bp.route('/api/cofre', methods=['POST'])
def gravar_cofre():
    try:
        entrada = cofre.definir(request.json or {})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "entrada": entrada})


@cofre_bp.route('/api/cofre/<entrada_id>', methods=['DELETE'])
def apagar_cofre(entrada_id):
    return jsonify({"ok": cofre.remover(entrada_id)})
