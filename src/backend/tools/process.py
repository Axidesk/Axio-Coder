import os
import re
import time
import socket
import shlex
import locale
import webbrowser
import subprocess
import threading

from src.backend.state import estado, emit_event
from src.backend.services.file_service import venv_projeto

def tool_executar_comando(comando: str):
    emit_event("executing", function=f"Executando: {comando}")
    comandos_proibidos = ['grep', 'sed', 'awk', 'cat', 'nano', 'vim', 'python', 'python3', 'py', 'powershell', 'pwsh', 'cmd', 'echo', 'mkdir', 'type']
    sugestoes = {
        'grep': 'tool_pesquisar_no_projeto',
        'sed': 'tool_substituir_texto',
        'awk': 'tool_substituir_texto',
        'cat': 'tool_ler_arquivo',
        'nano': 'tool_substituir_texto',
        'vim': 'tool_substituir_texto',
        'python': 'tool_validar_sintaxe (sintaxe) ou tool_executar_processo (venv/pip/servidor)',
        'python3': 'tool_validar_sintaxe (sintaxe) ou tool_executar_processo (venv/pip/servidor)',
        'py': 'tool_validar_sintaxe (sintaxe) ou tool_executar_processo (venv/pip/servidor)',
        'powershell': 'tool_executar_processo',
        'pwsh': 'tool_executar_processo',
        'cmd': 'tool_executar_processo',
        'echo': 'tool_salvar_arquivo ou tool_substituir_texto',
        'mkdir': 'tool_executar_processo',
        'type': 'tool_ler_arquivo',
    }
    cmd_base = comando.strip().split()[0].lower()
    if cmd_base in comandos_proibidos:
        sugestao = sugestoes.get(cmd_base, 'as ferramentas nativas correspondentes')
        return f"ERRO: O comando '{cmd_base}' é proibido. Motivo: existe ferramenta nativa mais segura e rastreável para isso. Use: {sugestao}."
    return tool_executar_processo(comando, modo="aguardar", timeout=30)

def id_processo():
    n = estado.setdefault("_contador_processo", 0) + 1
    estado["_contador_processo"] = n
    return f"proc_{n}"

def _tokenizar(comando):
    cmd = (comando or "").strip()
    if not cmd:
        return []
    try:
        partes = shlex.split(cmd, posix=False)
        if partes:
            return partes
    except ValueError:
        pass
    return cmd.split()

def _normalizar_exe(token):
    """Nome do executavel normalizado: sem caminho e sem sufixo .exe/.cmd/.bat."""
    exe = (token or "").replace("\\", "/").split("/")[-1].lower()
    for sufixo in (".exe", ".cmd", ".bat"):
        if exe.endswith(sufixo):
            exe = exe[: -len(sufixo)]
    return exe

def _validar_comando_processo(comando):
    cmd = (comando or "").strip()
    if not cmd:
        return False, "Comando vazio."
    partes = _tokenizar(cmd)
    exe = _normalizar_exe(partes[0])
    if not exe:
        return False, "Executável não identificado."

    if exe in ("python", "python3", "py"):
        if len(partes) >= 3 and partes[1] == "-m" and partes[2] in ("venv", "pip", "flask", "uvicorn"):
            return True, ""
        if len(partes) >= 2 and partes[1].endswith(".py"):
            return True, ""
        return False, f"Uso de '{exe}' não permitido. Permitido: {exe} -m venv/pip/flask/uvicorn ou {exe} app.py."

    if exe in ("pip", "pip3"):
        if len(partes) >= 2 and partes[1] == "install":
            return True, ""
        return False, "pip só é permitido com 'install'."

    if exe in ("npm", "npx"):
        if len(partes) >= 2 and partes[1] in ("install", "ci", "start", "run"):
            return True, ""
        return False, "npm/npx só são permitidos com install/ci/start/run."

    if exe == "node":
        return True, ""

    if exe == "flask":
        if len(partes) >= 2 and partes[1] == "run":
            return True, ""
        return False, "flask só é permitido com 'run'."

    if exe in ("supabase", "firebase", "gcloud", "docker", "mempalace", "git"):
        return True, ""

    if exe in ("cmake", "make", "mingw32-make", "ninja", "g++", "gcc", "clang", "clang++", "meson",
               "dotnet", "cargo", "rustc", "go", "javac", "tsc", "nmake", "msbuild", "cl"):
        return True, ""

    return False, f"Executável '{exe}' não está na lista permitida."

def _codepage_console_windows():
    if os.name != "nt":
        return None
    try:
        import ctypes
        cp = ctypes.windll.kernel32.GetConsoleOutputCP()
        if cp:
            return "cp%d" % cp
    except Exception:
        pass
    return None

def _decodificar_linha_processo(raw):
    if isinstance(raw, str):
        return raw
    encs = ["utf-8"]
    if os.name == "nt":
        oem = _codepage_console_windows()
        if oem:
            encs.append(oem)
        for e in ("cp850", "cp437"):
            if e.lower() not in [x.lower() for x in encs]:
                encs.append(e)
    try:
        pref = locale.getpreferredencoding(False)
        if pref and pref.lower() not in [x.lower() for x in encs]:
            encs.append(pref)
    except Exception:
        pass
    for enc in encs + ["cp1252", "latin-1"]:
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")

def ler_saida_stream(pid, popen):
    try:
        stream = popen.stdout
        if not stream:
            return
        buffer = ""
        while True:
            bruto = stream.read1(4096) if hasattr(stream, "read1") else stream.read(4096)
            if not bruto:
                break
            texto = _decodificar_linha_processo(bruto)
            if not texto:
                continue
            emit_event("process_output", pid=pid, chunk=texto)
            buffer += texto
            while "\n" in buffer:
                linha, buffer = buffer.split("\n", 1)
                _anexar_log_processo(pid, linha.rstrip("\r"))
        if buffer:
            _anexar_log_processo(pid, buffer.rstrip("\r"))
    except Exception:
        pass

def _monitorar_processo_segundo_plano(pid, popen):
    try:
        popen.wait()
    except Exception:
        pass
    reg = estado.get("processos", {}).get(pid)
    if reg is None or reg.get("status") != "rodando":
        return
    rc = popen.returncode
    reg["status"] = "ok" if rc == 0 else "erro"
    emit_event("process_finished", pid=pid, exit_code=rc, status=reg["status"])

def matar_arvore(popen):
    if popen is None:
        return
    try:
        if popen.poll() is not None:
            return
    except Exception:
        pass
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(popen.pid)], capture_output=True)
        else:
            popen.terminate()
            try:
                popen.wait(timeout=5)
            except subprocess.TimeoutExpired:
                popen.kill()
    except Exception:
        try:
            popen.kill()
        except Exception:
            pass

def _porta_livre(preferida=5001):
    for porta in list(dict.fromkeys([preferida] + list(range(5001, 5201)))):
        if porta is None or porta == 5000:
            continue
        ocupada = False
        for familia, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::")):
            try:
                s = socket.socket(familia, socket.SOCK_STREAM)
            except OSError:
                continue
            try:
                s.bind((host, porta))
            except OSError:
                ocupada = True
            finally:
                try:
                    s.close()
                except Exception:
                    pass
            if ocupada:
                break
        if not ocupada:
            return porta
    return 5001

def _eh_comando_web(comando):
    cmd = (comando or "").strip()
    if not cmd:
        return False
    partes = _tokenizar(cmd)
    if not partes:
        return False
    exe = _normalizar_exe(partes[0])
    if exe in ("flask", "uvicorn"):
        return True
    if exe == "node":
        return bool(re.search(r"\S+\.(?:js|mjs|cjs)\b", cmd))
    if exe in ("python", "python3", "py"):
        return ("flask" in cmd) or ("uvicorn" in cmd) or bool(re.search(r"\S+\.py(?:\s|$)", cmd))
    if exe in ("npm", "npx"):
        return any(p in cmd for p in ("start", "run dev", "run serve", "run start"))
    return False

def _ajustar_porta_comando(comando):
    cmd = (comando or "").strip()
    if not cmd:
        return cmd, None
    m = re.search(r"(?<![\w])(--port[=\s]+|-p\s+)(\d+)", cmd)
    if m and m.group(2) == "5000":
        nova = _porta_livre()
        novo_cmd = re.sub(r"(?<![\w])(--port[=\s]+|-p\s+)5000", lambda mm: mm.group(1) + str(nova), cmd, count=1)
        return novo_cmd, nova
    if re.search(r"\bflask\s+run\b", cmd) and m is None:
        nova = _porta_livre()
        return f"{cmd} --port {nova}", nova
    return cmd, None

def _eh_servidor_http(comando):
    if not _eh_comando_web(comando):
        return False
    partes = _tokenizar(comando)
    if not partes:
        return False
    exe = _normalizar_exe(partes[0])
    return exe in ("flask", "uvicorn", "python", "python3", "py", "node", "npm", "npx")

def _porta_responde(porta, timeout=30):
    inicio = time.time()
    while time.time() - inicio < timeout:
        try:
            with socket.create_connection(("127.0.0.1", porta), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False

def _abrir_navegador(url):
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False

def _anexar_log_processo(pid, linha):
    reg = estado.get("processos", {}).get(pid)
    if reg is None:
        return
    reg["log"].append(linha)
    if len(reg["log"]) > 500:
        reg["log"] = reg["log"][-500:]

def _registrar_linha_processo(pid, linha):
    emit_event("process_output", pid=pid, line=linha)
    _anexar_log_processo(pid, linha)

def _abrir_quando_pronto(pid, porta):
    url = f"http://127.0.0.1:{porta}"
    if not _porta_responde(porta, timeout=30):
        _registrar_linha_processo(pid, f"[axio] servidor não respondeu em 30s; abra manualmente: {url}")
        return
    if _abrir_navegador(url):
        _registrar_linha_processo(pid, f"[axio] navegador aberto em {url}")
    else:
        _registrar_linha_processo(pid, f"[axio] não consegui abrir o navegador; abra manualmente: {url}")

def montar_env_processo(comando, porta_env=None):
    env = os.environ.copy()
    if porta_env:
        env["PORT"] = str(porta_env)
        env["FLASK_RUN_PORT"] = str(porta_env)
    venv = venv_projeto()
    if venv:
        scripts = venv["scripts"]
        path_atual = env.get("PATH", "")
        env["PATH"] = scripts + os.pathsep + path_atual if path_atual else scripts
        env["VIRTUAL_ENV"] = venv["dir"]
    return env

def tool_executar_processo(comando: str, modo: str = "aguardar", timeout=None):
    try:
        timeout = int(timeout) if timeout is not None else 300
    except (TypeError, ValueError):
        timeout = 300
    if timeout < 5:
        timeout = 5

    ok, motivo = _validar_comando_processo(comando)
    if not ok:
        return f"ERRO: {motivo}"

    comando, porta_ajustada = _ajustar_porta_comando(comando)
    eh_web = _eh_comando_web(comando)
    porta_env = porta_ajustada
    if eh_web and porta_env is None:
        porta_env = _porta_livre()

    nota_porta = ""
    if porta_ajustada:
        nota_porta = f" (porta HTTP ajustada: {porta_ajustada})"
    elif eh_web and porta_env:
        nota_porta = f" (porta sugerida via env PORT/FLASK_RUN_PORT: {porta_env})"

    emit_event("executing", function=f"Executando: {comando}")
    pid = id_processo()
    reg = {"id": pid, "comando": comando, "status": "rodando", "log": [], "cwd": estado.get("pasta_raiz", ""), "popen": None}
    estado["processos"][pid] = reg

    try:
        kwargs = {
            "shell": True,
            "cwd": estado.get("pasta_raiz", ""),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        kwargs["env"] = montar_env_processo(comando, porta_env)
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        popen = subprocess.Popen(comando, **kwargs)
        reg["popen"] = popen
        emit_event("process_started", pid=pid, comando=comando, modo=modo)
        leitor = threading.Thread(target=ler_saida_stream, args=(pid, popen), daemon=True)
        leitor.start()

        if modo == "segundo_plano":
            threading.Thread(target=_monitorar_processo_segundo_plano, args=(pid, popen), daemon=True).start()
            if _eh_servidor_http(comando) and porta_env:
                threading.Thread(target=_abrir_quando_pronto, args=(pid, porta_env), daemon=True).start()
            return f"PROCESSO INICIADO EM SEGUNDO PLANO (pid={pid}){nota_porta}. Acompanhe em /api/processos e encerre com /api/processo/{pid}/parar."

        try:
            popen.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            matar_arvore(popen)
            reg["status"] = "timeout"
            emit_event("process_finished", pid=pid, exit_code=None, status="timeout")
            return f"ERRO: o processo excedeu {timeout}s e foi abortado."

        leitor.join(timeout=5)
        reg["status"] = "ok" if popen.returncode == 0 else "erro"
        emit_event("process_finished", pid=pid, exit_code=popen.returncode, status=reg["status"])
        tail = "\n".join(reg["log"][-50:])
        if reg["status"] == "ok":
            base = tail if tail.strip() else "SUCESSO: processo concluído sem saída."
            return base + nota_porta
        return f"ERRO (exit code {popen.returncode}):\n{tail}"
    except Exception as e:
        reg["status"] = "erro"
        emit_event("process_finished", pid=pid, exit_code=None, status="erro")
        return f"ERRO: {e}"

def parar_processo_reg(pid, reg):
    """Marca o processo como parado e encerra sua arvore, se ainda estiver ativa."""
    reg["status"] = "parado"
    popen = reg.get("popen")
    if popen is not None:
        try:
            if popen.poll() is None:
                matar_arvore(popen)
        except Exception:
            pass
    emit_event("process_finished", pid=pid, exit_code=None, status="parado")

def tool_parar_processo(pid: str):
    emit_event("executing", function="Parando processo")
    pid = (pid or "").strip()
    if not pid:
        return "ERRO: informe o pid do processo a parar."
    reg = estado.get("processos", {}).get(pid)
    if reg is None:
        return f"ERRO: processo '{pid}' nao encontrado. Liste os pids em /api/processos."
    parar_processo_reg(pid, reg)
    return f"Processo {pid} parado."