import os
import sys

from flask import Blueprint, request, jsonify
from src.backend.config import APP_ROOT
from src.backend.state import estado
from src.backend.services.file_service import venv_projeto, calcular_posicao_relativa, raiz_abs, resolver_caminho
from src.backend.services.settings import atualizar_settings, load_settings
from src.backend.services.sugestoes import detectar_sugestoes
from src.backend.services.process_manager import (
    pty_lock,
    pty_kill_locked,
    cwd_atual,
    detectar_shell,
    shell_caminho,
    comando_inicia_axio,
)
from src.backend.tools.process import (
    escrever_stdin_processo,
    iniciar_processo,
    parar_processo_reg,
)

terminal_bp = Blueprint("terminal", __name__)
@terminal_bp.route('/api/processos', methods=['GET'])
def processos():
    lista = []
    for pid, reg in estado.get("processos", {}).items():
        popen = reg.get("popen")
        rodando = popen is not None
        if popen is not None:
            try:
                rodando = popen.poll() is None
            except Exception:
                rodando = False
        lista.append({
            "id": pid,
            "comando": reg.get("comando", ""),
            "status": reg.get("status", "rodando"),
            "log": reg.get("log", [])[-200:],
            "rodando": rodando,
            "cwd": reg.get("cwd", ""),
            "rotulo": reg.get("rotulo", ""),
            "controles": reg.get("controles", []),
        })
    return jsonify({"processos": lista})

@terminal_bp.route('/api/processo/<pid>/parar', methods=['POST'])
def processo_parar(pid):
    reg = estado.get("processos", {}).get(pid)
    if not reg:
        return jsonify({"error": "processo não encontrado"}), 404
    parar_processo_reg(pid, reg)
    return jsonify({"status": "parado", "id": pid})

@terminal_bp.route('/api/processo/<pid>/input', methods=['POST'])
def processo_input(pid):
    """Escreve uma linha no stdin de um processo gerido (a resposta a um prompt do card)."""
    if pid not in estado.get("processos", {}):
        return jsonify({"error": "processo não encontrado"}), 404
    data = request.json or {}
    texto = data.get("texto")
    if texto is None:
        return jsonify({"error": "texto vazio"}), 400
    ok, motivo = escrever_stdin_processo(pid, texto)
    if not ok:
        return jsonify({"error": motivo}), 409
    return jsonify({"status": "enviado", "id": pid})

@terminal_bp.route('/api/env_info', methods=['GET'])
def env_info():
    venv = venv_projeto()
    if venv:
        nome_venv = venv["nome"]
        venv_path = venv["dir"]
    else:
        nome_venv = ".venv não detectado"
        venv_path = ""
    return jsonify({
        "venv_name": nome_venv,
        "venv_path": venv_path,
        "has_project_venv": bool(venv),
        "python": sys.version.split()[0],
        "folder": estado.get("pasta_raiz", ""),
        "ultima_pasta": (load_settings().get("projeto") or {}).get("ultima_pasta", ""),
        "shell": detectar_shell().get("nome", "cmd")
    })

@terminal_bp.route('/api/terminal/cwd', methods=['GET'])
def terminal_cwd():
    cwd = cwd_atual()
    raiz = estado.get("pasta_raiz") or ""
    raiz_absoluta = raiz_abs()
    relativo, dentro = calcular_posicao_relativa(cwd, raiz_absoluta)
    return jsonify({
        "cwd": cwd,
        "relativo": relativo,
        "dentro_da_raiz": dentro,
        "raiz": raiz,
        "raiz_nome": os.path.basename(raiz_absoluta) if raiz_absoluta else ""
    })

@terminal_bp.route('/api/terminal/cwd', methods=['POST'])
def terminal_set_cwd():
    data = request.json or {}
    path = (data.get("path") or "").strip()
    cwd = cwd_atual()
    if not path or path == ".":
        novo = cwd
    elif path == "~":
        novo = os.path.expanduser("~")
    else:
        if path.startswith("~" + os.sep) or path.startswith("~/"):
            path = os.path.join(os.path.expanduser("~"), path[2:].lstrip("\\/"))
        if os.path.isabs(path):
            novo = os.path.abspath(path)
        else:
            novo = os.path.abspath(os.path.join(cwd, path))
    if not os.path.isdir(novo):
        return jsonify({"error": f"pasta não encontrada: {novo}"}), 404
    estado["cwd_terminal"] = novo
    return terminal_cwd()

@terminal_bp.route('/api/terminal/shells', methods=['GET'])
def terminal_shells():
    atuais = []
    nomes = ("cmd", "powershell", "pwsh") if os.name == "nt" else ("bash", "zsh", "sh")
    for nome in nomes:
        if shell_caminho(nome):
            atuais.append({"nome": nome})
    return jsonify({"shells": atuais, "atual": detectar_shell().get("nome", "cmd")})

@terminal_bp.route('/api/terminal/shell', methods=['POST'])
def terminal_set_shell():
    data = request.json or {}
    shell = (data.get("shell") or "").strip().lower()
    if shell in ("auto", ""):
        estado["terminal_shell"] = ""
        shell = ""
    else:
        if not shell_caminho(shell):
            return jsonify({"error": f"shell indisponível: {shell}"}), 400
        estado["terminal_shell"] = shell
    try:
        atualizar_settings({"terminal": {"shell": shell}})
    except Exception:
        pass
    with pty_lock:
        pty_kill_locked()
    return jsonify({"atual": detectar_shell().get("nome", "cmd")})

@terminal_bp.route('/api/terminal/exec', methods=['POST'])
def terminal_exec():
    """Arranca um comando como processo gerido (card no terminal) e devolve o pid logo;
    a saida chega por SSE e o fim por process_finished. Nao espera pela conclusao."""
    data = request.json or {}
    cmd = (data.get("cmd") or "").strip()
    if not cmd:
        return jsonify({"error": "comando vazio"}), 400
    cwd = data.get("cwd") or estado.get("pasta_raiz", "")
    if not cwd or not os.path.isdir(cwd):
        cwd = estado.get("pasta_raiz", "") or os.getcwd()
    if os.path.normcase(os.path.abspath(cwd)) == os.path.normcase(APP_ROOT) and comando_inicia_axio(cmd):
        return jsonify({"error": "Este comando iniciaria o proprio Axio (porta 5000 ja em uso)."}), 400
    try:
        reg = iniciar_processo(cmd, cwd=cwd, modo="terminal", acompanhar=True, stdin_pipe=True)
    except OSError as e:
        return jsonify({"error": f"nao consegui iniciar: {e}"}), 500
    return jsonify({"id": reg["id"], "comando": cmd, "status": reg["status"], "rodando": True})

@terminal_bp.route('/api/terminal/sugestoes', methods=['GET'])
def terminal_sugestoes():
    """Comandos de arranque plausiveis para a pasta aberta no explorador (cards prontos a dar play)."""
    caminho_rel = request.args.get("path", "") or ""
    if not estado.get("pasta_raiz"):
        return jsonify({"sugestoes": [], "path": caminho_rel})
    caminho_alvo, erro = resolver_caminho(caminho_rel, permitir_extra=True)
    if erro:
        return jsonify({"error": erro}), 400
    return jsonify({"sugestoes": detectar_sugestoes(caminho_alvo), "path": caminho_rel})
