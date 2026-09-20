from flask import Blueprint, jsonify, request
from src.backend.services.settings import atualizar_settings, load_settings, save_settings

settings_bp = Blueprint("settings", __name__)

@settings_bp.route('/api/settings', methods=['GET'])
def obter_settings():
    return jsonify(load_settings())

@settings_bp.route('/api/settings', methods=['POST'])
def gravar_settings():
    dados = request.json or {}
    try:
        gravado = save_settings(dados)
        return jsonify({"ok": True, "settings": gravado})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@settings_bp.route('/api/settings/parcial', methods=['POST'])
def gravar_settings_parcial():
    try:
        return jsonify({"ok": True, "settings": atualizar_settings(request.json or {})})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
