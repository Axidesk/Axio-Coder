import os
import sys
import subprocess
import threading

from flask import Blueprint, request, jsonify
from src.backend.config import APP_ROOT
from src.backend.state import estado, emit_event
from src.backend.services.file_service import venv_projeto, calcular_posicao_relativa, raiz_abs
from src.backend.services.settings import atualizar_settings
from src.backend.services.process_manager import (
    pty_lock,
    pty_kill_locked,
    cwd_atual,
    detectar_shell,
    shell_caminho,
    comando_inicia_axio,
)
from src.backend.tools.process import (
    id_processo,
    matar_arvore,
    parar_processo_reg,
    ler_saida_stream,
    montar_env_processo,
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
        })
    return jsonify({"processos": lista})

@terminal_bp.route('/api/processo/<pid>/parar', methods=['POST'])
def processo_parar(pid):
    reg = estado.get("processos", {}).get(pid)
    if not reg:
        return jsonify({"error": "processo não encontrado"}), 404
    parar_processo_reg(pid, reg)
    return jsonify({"status": "parado", "id": pid})

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
    data = request.json or {}
    cmd = (data.get("cmd") or "").strip()
    if not cmd:
        return jsonify({"error": "comando vazio"}), 400
    cwd = data.get("cwd") or estado.get("pasta_raiz", "")
    if not cwd or not os.path.isdir(cwd):
        cwd = estado.get("pasta_raiz", "") or os.getcwd()
    raiz_app = APP_ROOT
    if os.path.normcase(os.path.abspath(cwd)) == os.path.normcase(raiz_app) and comando_inicia_axio(cmd):
        return jsonify({
            "exit_code": 1,
            "status": "bloqueado",
            "output": "[bloqueado] Este comando iniciaria o proprio Axio (porta 5000 ja em uso).\nUse o terminal externo para subir o Axio, ou troque para a pasta de outro projeto."
        })
    pid = id_processo()
    reg = {"id": pid, "comando": cmd, "status": "rodando", "log": [], "cwd": cwd, "popen": None}
    estado["processos"][pid] = reg
    emit_event("process_started", pid=pid, comando=cmd, modo="terminal")
    try:
        kwargs = {
            "shell": True,
            "cwd": cwd,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
            "env": montar_env_processo(cmd),
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        popen = subprocess.Popen(cmd, **kwargs)
        reg["popen"] = popen
        leitor = threading.Thread(target=ler_saida_stream, args=(pid, popen), daemon=True)
        leitor.start()
        try:
            popen.wait(timeout=60)
        except subprocess.TimeoutExpired:
            matar_arvore(popen)
            reg["status"] = "timeout"
            emit_event("process_finished", pid=pid, exit_code=None, status="timeout")
            return jsonify({"exit_code": None, "status": "timeout", "output": "\n".join(reg["log"][-200:])})
        leitor.join(timeout=5)
        reg["status"] = "ok" if popen.returncode == 0 else "erro"
        emit_event("process_finished", pid=pid, exit_code=popen.returncode, status=reg["status"])
        return jsonify({"exit_code": popen.returncode, "status": reg["status"], "output": "\n".join(reg["log"][-200:])})
    except Exception as e:
        reg["status"] = "erro"
        emit_event("process_finished", pid=pid, exit_code=None, status="erro")
        return jsonify({"exit_code": None, "status": "erro", "output": str(e)})
