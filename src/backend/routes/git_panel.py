"""Rotas do painel de git: retrato do repositorio, commit por tarefa e restauro."""

import os

from flask import Blueprint, jsonify, request

from src.backend.services import git_repo
from src.backend.services.git_sugestao import sugerir_mensagem
from src.backend.services.file_service import mover_para_lixeira, registrar_edicao
from src.backend.services.session import marcar_commit_no_log
from src.backend.state import estado
from src.backend.tools.js_contrato import quebras_introduzidas

git_bp = Blueprint("git_panel", __name__)


def _pasta():
    return estado.get("pasta_raiz", "")


def _revisao_pedida(dados):
    revisao = str((dados or {}).get("revisao") or "").strip()
    if not revisao:
        return "", (jsonify({"status": "error", "message": "Revisao obrigatoria"}), 400)
    if not git_repo.revisao_existe(_pasta(), revisao):
        return "", (jsonify({"status": "error", "message": f"Revisao desconhecida: {revisao}"}), 400)
    return revisao, None


def _quebras_do_restauro(raiz, revisao, restaurar, remover):
    caminhos = [r.get("caminho") for r in restaurar if isinstance(r, dict) and r.get("caminho")]
    caminhos.extend([r for r in restaurar if isinstance(r, str)])
    conteudos, _ = git_repo.conteudo_na_revisao(raiz, revisao, caminhos)
    projecao = dict(conteudos)
    for rel in remover or []:
        projecao[str(rel)] = None
    if not projecao:
        return []
    return quebras_introduzidas(raiz, projecao)


@git_bp.route("/api/git/estado", methods=["GET"])
def git_estado():
    pasta = _pasta()
    info = git_repo.estado(pasta)
    if not info.get("repo"):
        return jsonify({"status": "sem_repo", "message": info.get("motivo", ""), "estado": info})
    arvore = git_repo.historico(pasta)
    info["commits"] = arvore.get("commits", [])
    info["tags"] = git_repo.tags_com_ponto(pasta)
    info["erro_historico"] = arvore.get("erro", "")
    info["manifestos"] = git_repo.manifestos_diferentes(info.get("raiz", ""), "HEAD")
    return jsonify({"status": "ok", "estado": info})


@git_bp.route("/api/git/versoes", methods=["GET"])
def git_versoes():
    info = git_repo.versoes(_pasta())
    if not info.get("repo"):
        return jsonify({
            "status": "sem_repo",
            "message": info.get("motivo", ""),
            "tags": [],
            "ramos": [],
        })
    return jsonify({
        "status": "ok",
        "tags": info.get("tags", []),
        "ramos": info.get("ramos", []),
        "erro": info.get("erro", ""),
    })


@git_bp.route("/api/git/commit", methods=["POST"])
def git_commit():
    dados = request.json or {}
    ficheiros = git_repo.caminhos_do_repo(_pasta(), dados.get("ficheiros") or [])
    resultado = git_repo.commitar(_pasta(), dados.get("mensagem") or "", ficheiros)
    if resultado.get("status") == "error":
        return jsonify(resultado), 400
    if resultado.get("status") != "ok":
        return jsonify(resultado)
    filename = os.path.basename(dados.get("filename") or "")
    round_id = str(dados.get("round_id") or "")
    if filename and round_id:
        resultado["gravado"] = marcar_commit_no_log(filename, round_id, resultado.get("hash") or "")
    return jsonify(resultado)


@git_bp.route("/api/git/pendentes", methods=["POST"])
def git_pendentes():
    dados = request.json or {}
    ficheiros = git_repo.caminhos_do_repo(_pasta(), dados.get("ficheiros") or [])
    info = git_repo.pendentes(_pasta(), ficheiros)
    if not info.get("repo"):
        return jsonify({
            "status": "sem_repo",
            "message": info.get("motivo", ""),
            "pendentes": [],
            "count": 0,
        })
    return jsonify({
        "status": "ok",
        "pendentes": info.get("pendentes", []),
        "count": info.get("count", 0),
    })


@git_bp.route("/api/git/restauro_preview", methods=["POST"])
def git_restauro_preview():
    revisao, erro = _revisao_pedida(request.json or {})
    if erro:
        return erro
    alteracoes = git_repo.alteracoes_para_disco(_pasta(), revisao)
    if not alteracoes.get("repo"):
        return jsonify({"status": "sem_repo", "message": alteracoes.get("motivo", "")})
    quebras = _quebras_do_restauro(
        alteracoes.get("raiz", ""), revisao, alteracoes.get("restaurar") or [], alteracoes.get("remover") or []
    )
    return jsonify({
        "status": "ok",
        "restaurar": alteracoes.get("restaurar") or [],
        "remover": alteracoes.get("remover") or [],
        "quebras": quebras[:40],
        "vazio": not alteracoes.get("restaurar") and not alteracoes.get("remover"),
    })


@git_bp.route("/api/git/restauro", methods=["POST"])
def git_restauro():
    dados = request.json or {}
    revisao, erro = _revisao_pedida(dados)
    if erro:
        return erro
    restaurar = dados.get("restaurar") or []
    remover = [str(r) for r in (dados.get("remover") or [])]
    raiz = git_repo.pasta_do_repositorio(_pasta())[0]
    quebras = _quebras_do_restauro(raiz, revisao, restaurar, remover)
    if quebras:
        return jsonify({
            "status": "blocked",
            "message": "Restauracao cancelada: nada foi alterado.",
            "quebras": quebras[:40],
        }), 409
    caminhos = [r.get("caminho") if isinstance(r, dict) else r for r in restaurar]
    caminhos = [c for c in caminhos if c]
    alterados = []
    if caminhos:
        resultado = git_repo.restaurar(_pasta(), revisao, caminhos)
        if resultado.get("status") != "ok":
            return jsonify(resultado), 500
        alterados = [{"nome": c, "acao": "restaurado"} for c in caminhos]
    for rel in remover:
        alvo = os.path.abspath(os.path.join(raiz, rel.replace("/", os.sep)))
        if not os.path.exists(alvo):
            continue
        try:
            with open(alvo, "r", encoding="utf-8") as f:
                atual = f.read()
        except (OSError, UnicodeDecodeError):
            atual = None
        registrar_edicao(alvo, atual, None)
        try:
            mover_para_lixeira(alvo)
        except OSError as e:
            return jsonify({"status": "error", "message": str(e)}), 500
        alterados.append({"nome": rel, "acao": "removido"})
    return jsonify({"status": "ok", "altered": alterados, "count": len(alterados)})


@git_bp.route("/api/git/sugestao", methods=["POST"])
def git_sugestao():
    dados = request.json or {}
    mensagem, erro = sugerir_mensagem(dados.get("contexto") or "", dados.get("ficheiros") or [])
    if erro:
        return jsonify({"status": "error", "message": erro}), 400
    return jsonify({"status": "ok", "mensagem": mensagem})
