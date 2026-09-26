import threading

from flask import Blueprint, jsonify, request

from src.backend.services.etiquetas import estado_etiquetagem, etiquetar_projeto
from src.backend.services.notas import gravar_notas, ler_notas
from src.backend.services.traducao import MAX_CHARS_TEXTO, estado_traducao, traduzir_texto
from src.backend.state import estado
from src.backend.tools.pacotes import pacotes_desatualizados
from src.backend.tools.projeto_info import dados_projeto

projeto_bp = Blueprint("projeto", __name__)


@projeto_bp.route('/api/projeto/info')
def projeto_info():
    return jsonify(dados_projeto(com_ocultos=request.args.get("ocultos") == "1"))


@projeto_bp.route('/api/projeto/outdated')
def projeto_outdated():
    return jsonify(pacotes_desatualizados())


@projeto_bp.route('/api/projeto/etiquetas')
def projeto_etiquetas():
    return jsonify(estado_etiquetagem())


@projeto_bp.route('/api/projeto/notas')
def projeto_notas():
    return jsonify(ler_notas())


@projeto_bp.route('/api/projeto/notas', methods=['POST'])
def projeto_notas_gravar():
    dados = request.json or {}
    if not isinstance(dados.get("abas"), list):
        return jsonify({"erro": "Falta a lista de abas."}), 400
    return jsonify(gravar_notas(dados))


@projeto_bp.route('/api/projeto/traduzir', methods=['POST'])
def projeto_traduzir():
    """Dispara a traducao de um trecho de nota numa thread.

    A traducao corre em paralelo com o chat (nao o bloqueia) e o resultado fica
    em `estado["traducao"]`, lido pela rota GET /api/projeto/traducao.
    """
    dados = request.json or {}
    texto = str(dados.get("texto") or "")
    if not texto.strip():
        return jsonify({"erro": "Nao ha texto para traduzir."}), 400
    if len(texto) > MAX_CHARS_TEXTO:
        return jsonify({"erro": f"O trecho tem {len(texto)} caracteres "
                       f"(limite {MAX_CHARS_TEXTO}): selecione a parte que quer traduzir."}), 413
    resultado = traduzir_texto(texto, bool(dados.get("use_deepseek")))
    if "erro" in resultado:
        return jsonify(resultado), 409
    return jsonify(resultado)


@projeto_bp.route('/api/projeto/traducao')
def projeto_traducao():
    return jsonify(estado_traducao())


@projeto_bp.route('/api/projeto/etiquetar', methods=['POST'])
def projeto_etiquetar():
    if estado.get("etiquetando"):
        return jsonify({"erro": "A etiquetagem ja esta em curso."}), 409
    if estado.get("turno_ocupado"):
        return jsonify({"erro": "Aguarde a conclusao da resposta atual."}), 409
    dados = request.json or {}
    threading.Thread(
        target=etiquetar_projeto,
        args=(bool(dados.get("use_deepseek")),),
        daemon=True,
    ).start()
    return jsonify({"estado": "a_etiquetar"})
