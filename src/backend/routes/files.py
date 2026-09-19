import os
import threading

from flask import Blueprint, request, jsonify

from src.backend.state import notificar_mudanca_arquivos
from src.backend.services.file_service import (
    resolver_caminho,
    raiz_abs,
    mover_para_lixeira,
    raiz_lixeira,
    listar_lixeira,
    listar_conteudo_lixeira,
    resolver_item_lixeira,
    restaurar_item_lixeira,
    limpar_dirs_vazios,
    limpar_item_lixeira_vazio,
    enviar_para_lixeira_sistema,
    limpar_lixeira,
)
from src.backend.services.session import propagar_rename_logs, marcar_deletado_logs

files_bp = Blueprint("files", __name__)

def _resolver_escrita(caminho):
    """Resolve o caminho para escrita, exigindo pasta de projeto.

    Devolve (alvo, erro_response). Quando erro_response nao e None, o chamador
    deve devolve-lo imediatamente (a exigencia de pasta vem de resolver_caminho).
    """
    alvo, erro = resolver_caminho(caminho, permitir_extra=False, permitir_escrita=True)
    if erro:
        return None, (jsonify({"error": erro}), 400)
    return alvo, None

def _resolver_item_editavel(caminho, acao):
    """Pre-condicao de fs_rename/fs_trash: resolve, exige que o item exista e
    que nao seja a pasta raiz. Devolve (alvo, erro_response)."""
    alvo, erro = _resolver_escrita(caminho)
    if erro:
        return None, erro
    if not os.path.exists(alvo):
        return None, (jsonify({"error": "ERRO: item não encontrado."}), 404)
    if alvo == raiz_abs():
        return None, (jsonify({"error": "ERRO: não é possível " + acao + " a pasta raiz."}), 400)
    return alvo, None

@files_bp.route('/api/fs_create', methods=['POST'])
def fs_create():
    dados = request.get_json(silent=True) or {}
    caminho = dados.get("caminho") or ""
    tipo = dados.get("tipo") or "file"
    alvo, erro = _resolver_escrita(caminho)
    if erro:
        return erro
    try:
        if os.path.exists(alvo):
            if tipo == "dir":
                base = alvo
                i = 2
                while os.path.exists(alvo):
                    alvo = base + "_" + str(i)
                    i += 1
            else:
                base, ext = os.path.splitext(alvo)
                i = 2
                while os.path.exists(alvo):
                    alvo = base + "_" + str(i) + ext
                    i += 1
        if tipo == "dir":
            os.makedirs(alvo, exist_ok=False)
        else:
            os.makedirs(os.path.dirname(alvo), exist_ok=True)
            with open(alvo, 'w', encoding='utf-8') as f:
                f.write('')
        rel = os.path.relpath(alvo, raiz_abs()).replace(os.sep, "/")
        return jsonify({"status": "criado", "caminho": rel, "absoluto": alvo})
    except OSError as e:
        return jsonify({"error": str(e)}), 500

@files_bp.route('/api/fs_rename', methods=['POST'])
def fs_rename():
    dados = request.get_json(silent=True) or {}
    caminho = dados.get("caminho") or ""
    novo_nome = (dados.get("novo_nome") or "").strip()
    if not novo_nome:
        return jsonify({"error": "ERRO: nome vazio."}), 400
    if "/" in novo_nome or "\\" in novo_nome:
        return jsonify({"error": "ERRO: o nome não pode conter barras."}), 400
    alvo, erro = _resolver_item_editavel(caminho, "renomear")
    if erro:
        return erro
    destino = os.path.join(os.path.dirname(alvo), novo_nome)
    if os.path.abspath(destino) == alvo:
        return jsonify({"status": "renomeado", "caminho": caminho})
    if os.path.exists(destino):
        return jsonify({"error": "ERRO: já existe um item com esse nome."}), 409
    try:
        rel_antigo = os.path.relpath(alvo, raiz_abs()).replace(os.sep, "/")
        os.rename(alvo, destino)
        rel = os.path.relpath(destino, raiz_abs()).replace(os.sep, "/")
        threading.Thread(target=propagar_rename_logs, args=(rel_antigo, rel), daemon=True).start()
        return jsonify({"status": "renomeado", "caminho": rel, "caminho_antigo": rel_antigo})
    except OSError as e:
        return jsonify({"error": str(e)}), 500

@files_bp.route('/api/fs_trash', methods=['POST'])
def fs_trash():
    dados = request.get_json(silent=True) or {}
    caminho = dados.get("caminho") or ""
    alvo, erro = _resolver_item_editavel(caminho, "excluir")
    if erro:
        return erro
    rel = os.path.relpath(alvo, raiz_abs()).replace(os.sep, "/")
    mover_para_lixeira(alvo)
    threading.Thread(target=marcar_deletado_logs, args=(rel,), daemon=True).start()
    notificar_mudanca_arquivos()
    return jsonify({"status": "movido", "caminho": rel})

@files_bp.route('/api/fs_existem', methods=['POST'])
def fs_existem():
    """Caminhos recebidos que ja nao existem: sem pasta de projeto devolve lista vazia."""
    dados = request.get_json(silent=True) or {}
    caminhos = dados.get("caminhos")
    if not isinstance(caminhos, list):
        return jsonify({"error": "ERRO: 'caminhos' tem de ser uma lista."}), 400
    if not raiz_abs():
        return jsonify({"ausentes": []})
    ausentes = []
    for caminho in caminhos:
        if not isinstance(caminho, str) or not caminho:
            continue
        alvo, erro = resolver_caminho(caminho, permitir_extra=False)
        if erro or not os.path.exists(alvo):
            ausentes.append(caminho)
    return jsonify({"ausentes": ausentes})

@files_bp.route('/api/trash', methods=['GET'])
def trash_list():
    return jsonify({"items": listar_lixeira()})

@files_bp.route('/api/trash_tree', methods=['GET'])
def trash_tree():
    return jsonify({"items": listar_conteudo_lixeira(request.args.get("id") or "")})

def _resolver_item_lixeira():
    """Valida e resolve um item da lixeira a partir do JSON do pedido.

    Devolve (lixeira_raiz, item_id, origem, erro_response). Quando erro_response
    nao e None, o chamador deve devolve-lo imediatamente. O item pode ser um
    arquivo ou um diretorio. A validacao em si vive em services/file_service,
    para ser a MESMA que as ferramentas de lixeira usam.
    """
    dados = request.get_json(silent=True) or {}
    item_id = (dados.get("id") or "").strip()
    origem, erro = resolver_item_lixeira(item_id)
    if erro:
        return None, item_id, None, (jsonify({"error": erro}), 400)
    return raiz_lixeira(), item_id, origem, None

@files_bp.route('/api/trash_restore', methods=['POST'])
def trash_restore():
    dados = request.get_json(silent=True) or {}
    rel_original, erro = restaurar_item_lixeira((dados.get("id") or "").strip())
    if erro:
        return jsonify({"error": erro}), 400
    notificar_mudanca_arquivos()
    return jsonify({"status": "restaurado", "caminho": rel_original})

@files_bp.route('/api/trash_delete', methods=['POST'])
def trash_delete():
    lixeira_raiz, item_id, origem, erro = _resolver_item_lixeira()
    if erro:
        return erro
    ts_dir = item_id.split("/")[0]
    ts_path = os.path.join(lixeira_raiz, ts_dir)
    def _excluir_em_segundo_plano():
        try:
            if enviar_para_lixeira_sistema(origem):
                limpar_dirs_vazios(os.path.dirname(origem), ts_path)
                limpar_item_lixeira_vazio(lixeira_raiz, ts_dir)
                notificar_mudanca_arquivos()
        except OSError:
            pass
    threading.Thread(target=_excluir_em_segundo_plano, daemon=True).start()
    return jsonify({"status": "excluido"})

@files_bp.route('/api/trash_purge', methods=['POST'])
def trash_purge():
    """Esvazia a lixeira do projeto (manda tudo para a Lixeira do Windows)."""
    try:
        total = limpar_lixeira()
    except OSError as e:
        return jsonify({"error": str(e)}), 500
    notificar_mudanca_arquivos()
    return jsonify({"status": "limpo", "total": total})
