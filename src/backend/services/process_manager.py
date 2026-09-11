import os
import re
import shutil
import threading
import time

from src.backend.state import estado
from src.backend.extensions import socketio
from src.backend.tools.process import montar_env_processo
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

# Marca se a preferencia de shell ja foi lida do disco neste processo. Evita
# pagar I/O a cada chamada de detectar_shell.
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

# --- Terminal interativo (shell persistente via ConPTY) + Socket.IO ---
_pty_proc = None
pty_lock = threading.Lock()
_pty_pump_started = False
_pty_dims = (24, 120)

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
