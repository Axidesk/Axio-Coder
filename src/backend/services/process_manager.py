from collections import deque
import os
import re
import shlex
import shutil
import threading
import time

from flask import request

from src.backend.state import estado
from src.backend.extensions import socketio
from src.backend.services.file_service import venv_projeto


def comando_inicia_axio(cmd):
    c = re.sub(r"\s+", " ", (cmd or "").strip().lower())
    if re.match(r"^npm\s+(start|run\b)", c):
        return True
    if re.match(r"^(npx\s+)?electron(\s|$)", c):
        return True
    if re.match(r"^flask\s+run", c) or re.match(r"^(python|python3|py)\s+-m\s+flask\s+run", c):
        return True
    if re.match(r"^(python|python3|py)\s+(app\.py|ax\.py)(\s|$)", c):
        return True
    return False

def tokenizar_linha(comando):
    """Divide o comando em tokens, limpando as aspas que o shlex preserva.

    Com posix=False o token fica com as aspas coladas (ex: "C:/x/python.exe"),
    o que estragava _normalizar_exe: sobrava um python.exe\" que nao casava com
    nenhuma regra da allowlist e a mensagem devolvida nao dizia o verdadeiro
    motivo. O strip alinha com o que config.py e file_service.py ja fazem.
    """
    cmd = (comando or "").strip()
    if not cmd:
        return []
    try:
        partes = shlex.split(cmd, posix=False)
        if partes:
            return [p.strip('"').strip("'") for p in partes]
    except ValueError:
        pass
    return [p.strip('"').strip("'") for p in cmd.split()]

def shell_caminho(nome):
    nome = (nome or "").strip().lower()
    if not nome:
        return None
    caminho = shutil.which(nome)
    if caminho:
        return caminho
    if os.path.isfile(nome):
        return nome
    if os.name == "nt":
        if nome == "cmd":
            return os.environ.get("COMSPEC") or "cmd.exe"
        sysroot = os.environ.get("SystemRoot") or r"C:\Windows"
        pf = os.environ.get("ProgramFiles") or r"C:\Program Files"
        extras = {
            "powershell": [os.path.join(sysroot, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")],
            "pwsh": [os.path.join(pf, "PowerShell", "7", "pwsh.exe")],
        }
        for extra in extras.get(nome, []):
            if os.path.isfile(extra):
                return extra
    return None

def detectar_shell():
    if not (estado.get("terminal_shell") or "").strip():
        carregar_shell_persistido()
    preferido = (estado.get("terminal_shell") or "").strip() or os.environ.get("AXIO_TERM_SHELL", "").strip()
    if preferido:
        caminho = shell_caminho(preferido)
        if caminho:
            nome = os.path.splitext(os.path.basename(preferido))[0].lower()
            return {"cmd": caminho, "nome": nome}
    if os.name == "nt":
        for nome in ("pwsh", "powershell", "cmd"):
            caminho = shell_caminho(nome)
            if caminho:
                return {"cmd": caminho, "nome": nome}
        return {"cmd": os.environ.get("COMSPEC") or "cmd.exe", "nome": "cmd"}
    for nome in ("bash", "zsh", "sh"):
        caminho = shell_caminho(nome)
        if caminho:
            return {"cmd": caminho, "nome": nome}
    return {"cmd": "sh", "nome": "sh"}

_shell_persistido_lido = False

def carregar_shell_persistido():
    """Restaura no boot o shell escolhido pelo usuario (data/settings.json).

    Le o disco uma unica vez por processo: o estado em RAM e reiniciado a cada
    Ctrl+Shift+B, e sem isto a escolha do dropdown voltaria sempre para 'auto'."""
    global _shell_persistido_lido
    if _shell_persistido_lido:
        return estado.get("terminal_shell", "") or ""
    _shell_persistido_lido = True
    if (estado.get("terminal_shell") or "").strip():
        return estado["terminal_shell"]
    from src.backend.services.settings import load_settings
    try:
        shell = ((load_settings().get("terminal") or {}).get("shell") or "").strip().lower()
    except Exception:
        shell = ""
    if shell and shell_caminho(shell):
        estado["terminal_shell"] = shell
    return shell

_pty_proc = None
pty_lock = threading.Lock()
_pty_pump_started = False
_pty_dims = (24, 120)
_pty_hist = deque()
_pty_hist_len = 0
_pty_hist_aparado = False
_LIMITE_HIST_PTY = 200000

def _pty_env():
    return montar_env_processo(detectar_shell()["cmd"])

def cwd_atual():
    cwd = estado.get("cwd_terminal") or estado.get("pasta_raiz") or os.getcwd()
    if not os.path.isdir(cwd):
        cwd = estado.get("pasta_raiz") or os.getcwd()
    return os.path.abspath(cwd)

def _pty_spawn_locked():
    global _pty_proc
    from winpty import PtyProcess
    shell = detectar_shell()
    cwd = cwd_atual()
    args = [shell["cmd"]]
    if shell["nome"] in ("powershell", "pwsh"):
        args += ["-NoLogo", "-NoProfile"]
    elif shell["nome"] == "cmd":
        args += ["/Q", "/D"]
    _pty_proc = PtyProcess.spawn(args, cwd=cwd, env=_pty_env(), dimensions=_pty_dims)
    _pty_hist_limpar()
    socketio.emit('pty:session', {'shell': shell['nome']})
    return _pty_proc

def pty_kill_locked():
    global _pty_proc
    proc = _pty_proc
    _pty_proc = None
    if proc is not None:
        try:
            proc.terminate(force=True)
        except Exception:
            pass
        try:
            proc.close(force=True)
        except Exception:
            pass

def _pty_pump():
    global _pty_proc
    while True:
        with pty_lock:
            proc = _pty_proc
            if proc is None or not proc.isalive():
                pty_kill_locked()
                try:
                    proc = _pty_spawn_locked()
                except Exception as e:
                    socketio.emit('pty:output', {'data': '\r\n\x1b[31m[erro ao iniciar shell: %s]\x1b[0m\r\n' % e})
                    time.sleep(1.0)
                    continue
        try:
            data = proc.read(2048)
            if isinstance(data, bytes):
                data = data.decode('utf-8', errors='replace')
            if data:
                with pty_lock:
                    _pty_hist_append(data)
                socketio.emit('pty:output', {'data': data})
        except EOFError:
            with pty_lock:
                pty_kill_locked()
            time.sleep(0.3)
        except Exception:
            time.sleep(0.2)

def _pty_ensure_pump():
    global _pty_pump_started
    if _pty_pump_started:
        return
    _pty_pump_started = True
    threading.Thread(target=_pty_pump, daemon=True).start()

def _pty_hist_limpar():
    global _pty_hist_len, _pty_hist_aparado
    _pty_hist.clear()
    _pty_hist_len = 0
    _pty_hist_aparado = False

def _pty_hist_append(data):
    global _pty_hist_len, _pty_hist_aparado
    _pty_hist.append(data)
    _pty_hist_len += len(data)
    while _pty_hist_len > _LIMITE_HIST_PTY and len(_pty_hist) > 1:
        _pty_hist_len -= len(_pty_hist.popleft())
        _pty_hist_aparado = True

def _pty_hist_texto():
    if not _pty_hist:
        return ''
    texto = ''.join(_pty_hist)
    if _pty_hist_aparado:
        corte = texto.find('\n')
        if corte != -1:
            texto = texto[corte + 1:]
    return texto

@socketio.on('connect')
def _pty_on_connect():
    _pty_ensure_pump()

@socketio.on('pty:input')
def _pty_on_input(data):
    d = (data or {}).get('data') if isinstance(data, dict) else data
    if not d:
        return
    _pty_ensure_pump()
    if os.name == 'nt':
        d = d.replace('\n', '\r')
    with pty_lock:
        proc = _pty_proc
    if proc is not None:
        try:
            proc.write(d)
        except Exception:
            pass

@socketio.on('pty:resize')
def _pty_on_resize(data):
    global _pty_dims
    d = data if isinstance(data, dict) else {}
    try:
        cols = int(d.get('cols') or 0)
        rows = int(d.get('rows') or 0)
    except (TypeError, ValueError):
        return
    if not (20 <= cols <= 1000 and 2 <= rows <= 500):
        return
    _pty_dims = (rows, cols)
    with pty_lock:
        proc = _pty_proc
    if proc is None:
        return
    try:
        proc.setwinsize(rows, cols)
    except Exception as e:
        print(f"[pty] setwinsize falhou: {e}")

@socketio.on('pty:restart')
def _pty_on_restart():
    _pty_ensure_pump()
    with pty_lock:
        pty_kill_locked()

@socketio.on('pty:replay')
def _pty_on_replay():
    _pty_ensure_pump()
    with pty_lock:
        texto = _pty_hist_texto()
    socketio.emit('pty:replay', {'data': texto}, to=request.sid)
def montar_env_processo(comando, porta_env=None, caminhos_extra=None):
    """Ambiente do processo: o venv do projeto mais as pastas que tenham de vir a frente.

    'caminhos_extra' existe para programas FORA do Python que precisam das suas proprias
    bibliotecas no PATH para arrancar (um executavel de Qt precisa do <kit>/bin).
    """
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if porta_env:
        env["PORT"] = str(porta_env)
        env["FLASK_RUN_PORT"] = str(porta_env)
    venv = venv_projeto()
    if venv:
        env["VIRTUAL_ENV"] = venv["dir"]
    caminhos = [c for c in (caminhos_extra or []) if c and os.path.isdir(c)]
    if venv:
        caminhos.append(venv["scripts"])
    if caminhos:
        atual = env.get("PATH", "")
        novo = os.pathsep.join(caminhos)
        env["PATH"] = novo + os.pathsep + atual if atual else novo
    return env
