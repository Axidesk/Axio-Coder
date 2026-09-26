import codecs
import ctypes
import locale
import os
import re
import socket
import subprocess
import threading
import time
import webbrowser

from src.backend.services import arvore_processos
from src.backend.services.process_manager import montar_env_processo, tokenizar_linha
from src.backend.services.saida import recortar_linhas
from src.backend.services.sugestoes import detectar_url_na_saida
from src.backend.state import emit_event, estado
from src.backend.tools.registry import register

@register(
    "tool_executar_comando",
    'Executa COMPILAÇÃO real (cmake --build build, make, g++, etc.). PROIBIDO usar para ler/editar/buscar/validar sintaxe (Python, sed, awk, grep, cat, echo, mkdir, type, node --check) — para isso use as ferramentas nativas: tool_ler_arquivo, tool_substituir_texto, tool_pesquisar_no_projeto, tool_validar_sintaxe. Use apenas para compilação que não tenha ferramenta nativa correspondente.',
    {
        'comando': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'cwd': {"tipo": "STRING", "desc": "Pasta onde o comando corre. Vazio usa a pasta do projeto aberta.", "padrao": ""},
        'tempo': {"tipo": "INTEGER", "desc": "Segundos antes de abortar (padrao 30). Compilar um projeto inteiro pede varios minutos.", "padrao": None},
    },
)
def tool_executar_comando(comando: str, cwd: str = "", tempo=None):
    emit_event("executing", function=f"Executando: {comando}")
    partes = (comando or "").strip().split()
    if not partes:
        return "ERRO: comando vazio."
    cmd_base = _normalizar_exe(partes[0])
    if cmd_base in COMANDOS_PROIBIDOS:
        sugestao = FERRAMENTA_NATIVA.get(cmd_base, "as ferramentas nativas correspondentes")
        return f"ERRO: O comando '{cmd_base}' é proibido. Motivo: existe ferramenta nativa mais segura e rastreável para isso. Use: {sugestao}."
    return tool_executar_processo(comando, modo="aguardar", timeout=tempo or 30, cwd=cwd)

def id_processo():
    n = estado.setdefault("_contador_processo", 0) + 1
    estado["_contador_processo"] = n
    return f"proc_{n}"


SUFIXOS_DE_EXECUTAVEL = (".exe", ".cmd", ".bat")

ALIASES_DE_PYTHON = ("python", "python3", "py")

COMANDOS_PROIBIDOS = (
    "grep", "sed", "awk", "cat", "nano", "vim", "python", "python3", "py",
    "powershell", "pwsh", "cmd", "echo", "mkdir", "type",
)

FERRAMENTA_NATIVA = {
    "grep": "tool_pesquisar_no_projeto",
    "findstr": "tool_pesquisar_no_projeto",
    "find": "tool_pesquisar_no_projeto",
    "sed": "tool_substituir_texto",
    "awk": "tool_substituir_texto",
    "cat": "tool_ler_arquivo",
    "type": "tool_ler_arquivo",
    "more": "tool_ler_arquivo",
    "head": "tool_ler_trecho_arquivo",
    "tail": "tool_ler_trecho_arquivo",
    "nano": "tool_substituir_texto",
    "vim": "tool_substituir_texto",
    "vi": "tool_substituir_texto",
    "notepad": "tool_substituir_texto",
    "echo": "tool_salvar_arquivo ou tool_substituir_texto",
    "mkdir": "tool_executar_processo",
    "md": "tool_executar_processo",
    "rm": "tool_deletar_arquivo (passa pela lixeira)",
    "del": "tool_deletar_arquivo (passa pela lixeira)",
    "erase": "tool_deletar_arquivo (passa pela lixeira)",
    "rmdir": "tool_deletar_arquivo (passa pela lixeira)",
    "rd": "tool_deletar_arquivo (passa pela lixeira)",
    "cp": "tool_salvar_arquivo",
    "copy": "tool_salvar_arquivo",
    "xcopy": "tool_salvar_arquivo",
    "mv": "tool_mover_arquivo_binario",
    "move": "tool_mover_arquivo_binario",
    "ren": "tool_mover_arquivo_binario",
    "dir": "tool_listar_pasta ou tool_listar_arvore",
    "ls": "tool_listar_pasta ou tool_listar_arvore",
    "tree": "tool_listar_arvore",
    "python": "tool_validar_sintaxe (sintaxe) ou tool_executar_processo (venv/pip/servidor)",
    "python3": "tool_validar_sintaxe (sintaxe) ou tool_executar_processo (venv/pip/servidor)",
    "py": "tool_validar_sintaxe (sintaxe) ou tool_executar_processo (venv/pip/servidor)",
    "powershell": "tool_executar_processo",
    "pwsh": "tool_executar_processo",
    "cmd": "tool_executar_processo",
    "ruff": "tool_auditar_codigo",
    "eslint": "tool_auditar_codigo",
    "flake8": "tool_auditar_codigo",
    "pylint": "tool_auditar_codigo",
    "mypy": "tool_auditar_codigo",
    "jscpd": "tool_analisar_similaridade",
    "taskkill": "tool_parar_processo",
}

COMANDOS_DESTRUTIVOS = (
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard descarta alteracoes nao commitadas"),
    (r"\bgit\s+clean\s+-[a-z]*[fdx]", "git clean -f/-d/-x apaga ficheiros nao rastreados"),
    (r"\bgit\s+checkout\s+(--\s+)?\.(\s|$)", "git checkout . descarta alteracoes nao commitadas"),
    (r"\bgit\s+restore\s+(--staged\s+)?\.(\s|$)", "git restore . descarta alteracoes nao commitadas"),
    (r"\bgit\s+push\b[^|;&]*--force", "git push --force reescreve o historico remoto"),
    (r"\bgit\s+branch\s+-D\b", "git branch -D apaga uma branch sem confirmacao"),
    (r"\brm\s+[^|;&]*-[a-z]*[rf]", "rm -r/-f apaga sem passar pela lixeira"),
    (r"\b(del|erase)\s+[^|;&]*/[a-z]*[qs]", "del /s /q apaga sem passar pela lixeira"),
    (r"\b(rd|rmdir)\s+[^|;&]*/s\b", "rmdir /s apaga uma pasta inteira sem passar pela lixeira"),
    (r"\bformat\s+[a-z]:", "format apaga uma unidade inteira"),
    (r"\b(shutdown|reboot)\b", "desliga ou reinicia a maquina"),
    (r"\bdocker\s+(system|volume|image|builder)\s+prune\b", "docker prune apaga volumes e imagens"),
    (r"\btaskkill\s+[^|;&]*/f\b[^|;&]*/im\b", "taskkill /F /IM mata TODOS os processos com esse nome"),
)

MODULOS_PYTHON = (
    "venv", "pip", "flask", "uvicorn", "http.server", "pytest", "unittest",
    "ruff", "mypy", "black", "json.tool", "pipx", "ensurepip", "site", "compileall",
)

SUBCOMANDOS_DE_GESTOR_JS = (
    "install", "ci", "add", "remove", "uninstall", "update", "upgrade", "dedupe",
    "run", "test", "build", "dev", "start", "exec", "x", "dlx", "create", "init",
    "ls", "list", "why", "outdated", "audit", "view", "info", "pack", "prune",
    "cache", "config", "typecheck", "lint", "format", "check", "link",
)

SUBCOMANDOS_DE_GESTOR_PY = (
    "venv", "pip", "sync", "lock", "add", "remove", "uninstall", "run", "tree",
    "python", "tool", "cache", "self", "init", "export", "build", "install",
    "update", "upgrade", "show", "env", "new", "config", "check", "list",
    "inject", "reinstall", "download", "freeze", "wheel",
)

FERRAMENTAS_DE_CODIGO = (
    "pytest", "ruff", "mypy", "black", "pylint", "flake8", "isort", "tox", "nox",
    "hatch", "pre-commit", "alembic", "eslint", "prettier", "vite", "webpack",
    "rollup", "esbuild", "parcel", "tsc", "tsx", "jest", "vitest", "mocha",
    "playwright", "cypress", "electron", "electron-builder", "next", "nuxt",
    "astro", "nodemon", "pm2", "just", "task", "sass", "tailwindcss",
)

COMPILADORES = (
    "cmake", "make", "mingw32-make", "ninja", "g++", "gcc", "clang", "clang++",
    "meson", "dotnet", "cargo", "rustc", "go", "javac", "nmake", "msbuild", "cl",
)

INSTALADORES_DE_PACOTES = (
    "maintenancetool", "qt-unified-windows-x64", "qt-unified-linux-x64",
    "qt-unified-macos-x64", "qt-online-installer",
)

SUBCOMANDOS_DE_INSTALADOR = (
    "install", "in", "search", "se", "list", "check-updates", "ch", "update", "up",
)

SUBCOMANDOS_DE_INSTALADOR_PROIBIDOS = ("remove", "rm", "purge")

VERSIONAMENTO_E_NUVEM = (
    "git", "gh", "glab", "docker", "docker-compose", "kubectl", "helm", "supabase",
    "firebase", "gcloud", "aws", "az", "vercel", "netlify", "wrangler", "flyctl",
    "mempalace",
)

MIDIA = ("ffmpeg", "ffprobe", "magick", "sox", "scenedetect")

REDE_E_SISTEMA = (
    "curl", "wget", "ping", "netstat", "tasklist", "taskkill", "sqlite3",
    "tar", "unzip", "zip", "7z",
)

PACOTES_DE_CONSULTA_PIP = ("list", "freeze", "show", "check", "download", "wheel")

def _normalizar_exe(token):
    """Nome do executavel normalizado: sem caminho e sem sufixo .exe/.cmd/.bat."""
    exe = (token or "").replace("\\", "/").split("/")[-1].lower()
    for sufixo in SUFIXOS_DE_EXECUTAVEL:
        exe = exe.removesuffix(sufixo)
    return exe

def _subcomando_do_instalador(partes):
    """Primeiro argumento que nao e uma flag: nos instaladores da Qt o subcomando vem depois delas."""
    for token in partes[1:]:
        if not token.startswith("-"):
            return token.lower()
    return ""

def _pasta_de_trabalho(cwd):
    """Pasta onde o processo corre: a indicada, ou a do projeto aberto. Sem nenhuma, nao adivinha."""
    alvo = (cwd or "").strip() or estado.get("pasta_raiz") or ""
    if not alvo:
        return "", ""
    alvo = os.path.abspath(alvo)
    if not os.path.isdir(alvo):
        return "", f"ERRO: '{cwd}' nao e uma pasta - o comando nao corre num sitio que nao existe."
    return alvo, ""


def _validar_comando_processo(comando):
    cmd = (comando or "").strip()
    if not cmd:
        return False, "Comando vazio."
    partes = tokenizar_linha(cmd)
    exe = _normalizar_exe(partes[0])
    if not exe:
        return False, "Executável não identificado."

    irreversivel = comando_destrutivo(cmd)
    if irreversivel:
        return False, (
            f"Comando irreversivel recusado: {irreversivel}. Se e mesmo isto que queres, corre-o "
            "tu no painel do terminal - eu nao descarto trabalho sem uma pessoa a decidir."
        )

    if exe in ALIASES_DE_PYTHON:
        if len(partes) >= 3 and partes[1] == "-m" and partes[2] in MODULOS_PYTHON:
            return True, ""
        if len(partes) >= 2 and partes[1].endswith(".py"):
            return True, ""
        sugestao = ferramenta_nativa_do_comando(cmd)
        dica = f" Use: {sugestao}." if sugestao else ""
        return False, (f"Uso de '{exe}' não permitido. Permitido: {exe} -m <modulo> "
                       f"(venv/pip/flask/uvicorn/pytest/ruff/mypy/...) ou {exe} script.py.{dica}")

    if exe in ("pip", "pip3"):
        if len(partes) >= 2 and partes[1] in ("install",) + PACOTES_DE_CONSULTA_PIP:
            return True, ""
        return False, ("pip só é permitido com install/list/freeze/show/check/download/wheel "
                       "(os de consulta nao alteram nada).")

    if exe in ("uv", "poetry", "pipx"):
        if len(partes) >= 2 and partes[1] in SUBCOMANDOS_DE_GESTOR_PY:
            return True, ""
        return False, f"'{exe}' só é permitido com subcomandos de gestão de projeto ou pacotes."

    if exe in ("npx", "bunx"):
        return True, ""

    if exe in ("npm", "yarn", "pnpm", "bun", "deno"):
        if len(partes) >= 2 and partes[1] in SUBCOMANDOS_DE_GESTOR_JS:
            return True, ""
        return False, (f"'{exe}' só é permitido com subcomandos de instalação, execução de script "
                       "ou consulta (publicar nunca).")

    if exe == "node":
        return True, ""

    if exe == "flask":
        if len(partes) >= 2 and partes[1] == "run":
            return True, ""
        return False, "flask só é permitido com 'run'."

    if (exe in FERRAMENTAS_DE_CODIGO or exe in VERSIONAMENTO_E_NUVEM
            or exe in MIDIA or exe in REDE_E_SISTEMA):
        return True, ""

    if exe in COMPILADORES:
        return True, ""

    if exe in INSTALADORES_DE_PACOTES:
        sub = _subcomando_do_instalador(partes)
        if sub in SUBCOMANDOS_DE_INSTALADOR:
            return True, ""
        if sub in SUBCOMANDOS_DE_INSTALADOR_PROIBIDOS:
            return False, (
                f"'{exe} {sub}' desinstala componentes que ja estao instalados nesta maquina. "
                "Nao removo software instalado por iniciativa propria - se e mesmo isso que queres, "
                "corre-o tu no painel do terminal."
            )
        return False, (
            f"'{exe}' so e permitido com os subcomandos de consulta e instalacao "
            f"({', '.join(SUBCOMANDOS_DE_INSTALADOR)})."
        )

    if not re.search(r"\.(?:exe|cmd|bat)$", partes[0], re.IGNORECASE) and re.search(r"\.(?:exe|cmd|bat)\b", cmd, re.IGNORECASE):
        return False, (
            f"O executável não foi reconhecido (li '{exe}'). O caminho tem espaços sem aspas, "
            "por isso o cmd.exe também não o executaria assim. Repita com o caminho entre aspas: "
            "\"C:\\caminho com espacos\\python.exe\" script.py"
        )
    sugestao = ferramenta_nativa_do_comando(cmd)
    dica = f" Use: {sugestao}." if sugestao else ""
    return False, f"Executável '{exe}' não está na lista permitida.{dica}"


def ferramenta_nativa_do_comando(comando):
    """Ferramenta nativa que faz o mesmo que este comando, ou string vazia se nao houver."""
    partes = tokenizar_linha(comando or "")
    if not partes:
        return ""
    exe = _normalizar_exe(partes[0])
    sub = partes[1].lower() if len(partes) >= 2 else ""
    if exe in ALIASES_DE_PYTHON and sub == "-c":
        return "tool_executar_python"
    if exe == "node" and sub in ("-e", "--eval"):
        return "tool_executar_js"
    if exe == "node" and sub in ("--check", "-c"):
        return "tool_validar_sintaxe"
    return FERRAMENTA_NATIVA.get(exe, "")


def comando_destrutivo(comando):
    """Motivo pelo qual o comando e irreversivel, ou string vazia se nao for."""
    texto = (comando or "").strip()
    for padrao, motivo in COMANDOS_DESTRUTIVOS:
        if re.search(padrao, texto, re.IGNORECASE):
            return motivo
    return ""


def _codepage_console_windows():
    if os.name != "nt":
        return None
    try:
        cp = ctypes.windll.kernel32.GetConsoleOutputCP()
        if cp:
            return "cp%d" % cp
    except Exception:
        pass
    return None

def _parece_utf8(bruto):
    """Verdadeiro para UTF-8 valido e para a cauda de uma sequencia cortada a meio."""
    try:
        bruto.decode("utf-8")
        return True
    except UnicodeDecodeError as e:
        return e.reason == "unexpected end of data"

def _escolher_encoding_saida(bruto):
    if _parece_utf8(bruto):
        return "utf-8"
    candidatos = []
    oem = _codepage_console_windows()
    if oem:
        candidatos.append(oem)
    candidatos.extend(["cp850", "cp437", "cp1252"])
    for enc in candidatos:
        try:
            bruto.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return "utf-8"

class _DecodificadorSaida:
    """Fixa a pagina do stream quando aparece o primeiro byte nao-ASCII e guarda a
    cauda de uma sequencia cortada, para um bloco de 4096 bytes nao virar lixo."""

    def __init__(self):
        self.decoder = None
        self.pendente = b""

    def alimentar(self, bruto):
        if self.decoder is not None:
            return self.decoder.decode(bruto)
        self.pendente += bruto
        if self.pendente.isascii():
            texto = self.pendente.decode("ascii")
            self.pendente = b""
            return texto
        self.decoder = codecs.getincrementaldecoder(_escolher_encoding_saida(self.pendente))(errors="replace")
        texto = self.decoder.decode(self.pendente)
        self.pendente = b""
        return texto

    def fechar(self):
        if self.decoder is None:
            texto = self.pendente.decode("ascii", "replace")
            self.pendente = b""
            return texto
        return self.decoder.decode(b"", True)

def _texto_de_saida(bruto):
    """Descodifica a saida ja capturada de um subprocesso, sem nunca rebentar.

    Em modo texto e o proprio subprocesso que descodifica dentro da sua thread
    leitora: um byte fora do UTF-8 (o cp1252 de um comando do Windows) mata essa
    thread, imprime um traceback no terminal do Axio, a saida do comando perde-se
    INTEIRA e o stdout chega ao chamador como None (nao vazio). Aqui a leitura e
    binaria e a pagina sai do mesmo criterio que o stream usa.
    """
    if not bruto:
        return ""
    decodificador = _DecodificadorSaida()
    return decodificador.alimentar(bruto) + decodificador.fechar()

def _codificar_entrada_processo(texto):
    """UTF-8 primeiro: os subprocessos arrancam com PYTHONIOENCODING=utf-8, logo e
    UTF-8 que esperam na entrada; a pagina OEM so fica como recurso."""
    linha = str(texto) + "\r\n"
    candidatos = ["utf-8"]
    if os.name == "nt":
        candidatos.append(_codepage_console_windows())
        try:
            candidatos.append(locale.getpreferredencoding(False))
        except Exception:
            pass
    for enc in candidatos:
        if not enc:
            continue
        try:
            return linha.encode(enc)
        except (UnicodeEncodeError, LookupError):
            continue
    return linha.encode("utf-8", "replace")

def _emitir_saida_processo(pid, texto):
    dados = {"pid": pid, "chunk": texto}
    url = detectar_url_na_saida(texto)
    if url:
        dados["url"] = url
    emit_event("process_output", **dados)

def ler_saida_stream(pid, popen):
    try:
        stream = popen.stdout
        if not stream:
            return
        decodificador = _DecodificadorSaida()
        buffer = ""
        while True:
            bruto = stream.read1(4096) if hasattr(stream, "read1") else stream.read(4096)
            if not bruto:
                break
            texto = decodificador.alimentar(bruto)
            if not texto:
                continue
            _emitir_saida_processo(pid, texto)
            buffer += texto
            while "\n" in buffer:
                linha, buffer = buffer.split("\n", 1)
                _anexar_log_processo(pid, linha.rstrip("\r"))
        cauda = decodificador.fechar()
        if cauda:
            _emitir_saida_processo(pid, cauda)
            buffer += cauda
        if buffer:
            _anexar_log_processo(pid, buffer.rstrip("\r"))
    except Exception:
        pass

def _monitorar_processo_segundo_plano(pid, popen):
    try:
        codigo = popen.wait()
    except Exception:
        return
    reg = estado.get("processos", {}).get(pid)
    if reg is None or reg.get("status") != "rodando":
        return
    reg["status"] = "ok" if codigo == 0 else "erro"
    emit_event("process_finished", pid=pid, exit_code=codigo, status=reg["status"])

_JUNTAS_PROCESSO = {}


def _juntar_ao_job(popen):
    """Poe o processo novo numa junta (Job Object) do Windows, com ordem de morrer com ela.

    O Windows nao guarda a relacao pai-filho: o 'taskkill /T' percorre uma fotografia feita
    na hora e falha quando o pai ja saiu, deixando o neto vivo - foi assim que o Electron
    sobrevivia ao 'npm start' e ficava a segurar a camara. A junta agrupa-os pelo lado do
    sistema e morre com o Axio, que e o que impede os fantasmas entre reinicios.
    """
    if os.name != "nt":
        return None
    try:
        import win32api
        import win32con
        import win32job
    except ImportError:
        return None
    try:
        junta = win32job.CreateJobObject(None, "")
        info = win32job.QueryInformationJobObject(junta, win32job.JobObjectExtendedLimitInformation)
        info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(junta, win32job.JobObjectExtendedLimitInformation, info)
        alca = win32api.OpenProcess(
            win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, popen.pid
        )
        win32job.AssignProcessToJobObject(junta, alca)
    except Exception:
        return None
    _JUNTAS_PROCESSO[getattr(popen, "pid", None)] = junta
    return junta


def _fechar_junta(pid):
    """Encerra a junta do processo: mata tudo o que ela agrupa, filhos desligados incluidos."""
    junta = _JUNTAS_PROCESSO.pop(pid, None)
    if junta is None:
        return False
    try:
        import win32job
        win32job.TerminateJobObject(junta, 0)
    except Exception:
        pass
    try:
        junta.Close()
    except Exception:
        pass
    return True


def matar_arvore(popen):
    if popen is None:
        return
    _fechar_junta(getattr(popen, "pid", None))
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
    partes = tokenizar_linha(cmd)
    if not partes:
        return False
    exe = _normalizar_exe(partes[0])
    if exe in ("flask", "uvicorn"):
        return True
    if exe == "node":
        return bool(re.search(r"\S+\.(?:js|mjs|cjs)\b", cmd))
    if exe in ("python", "python3", "py"):
        return ("flask" in cmd) or ("uvicorn" in cmd) or bool(re.search(r"\S+\.py(?:\s|$)", cmd))
    if exe in ("npm", "npx", "yarn", "pnpm", "bun", "deno"):
        return any(p in cmd for p in ("start", "run dev", "run serve", "run start", "dev", "serve"))
    if exe in ("vite", "next", "nuxt", "astro", "nodemon"):
        return True
    if exe in ("uv", "poetry"):
        return "run" in cmd and any(p in cmd for p in ("flask", "uvicorn", "dev", "serve", "start"))
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
    partes = tokenizar_linha(comando)
    if not partes:
        return False
    exe = _normalizar_exe(partes[0])
    if exe in ALIASES_DE_PYTHON:
        return True
    return exe in ("flask", "uvicorn", "node", "npm", "npx", "yarn", "pnpm", "bun", "deno",
                   "vite", "next", "nuxt", "astro", "nodemon")

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
    if len(reg["log"]) > 2000:
        reg["log"] = reg["log"][-2000:]

def registrar_linha_processo(pid, linha):
    emit_event("process_output", pid=pid, line=linha)
    _anexar_log_processo(pid, linha)

def _abrir_quando_pronto(pid, porta):
    url = f"http://127.0.0.1:{porta}"
    if not _porta_responde(porta, timeout=30):
        registrar_linha_processo(pid, f"[axio] servidor não respondeu em 30s; abra manualmente: {url}")
        return
    if _abrir_navegador(url):
        registrar_linha_processo(pid, f"[axio] navegador aberto em {url}")
    else:
        registrar_linha_processo(pid, f"[axio] não consegui abrir o navegador; abra manualmente: {url}")


@register(
    "tool_executar_processo",
    "Executa processos longos ou de bootstrap: criar venv, instalar dependências (pip/npm) e rodar servidores. Use modo='aguardar' (padrão) para venv/instalações e modo='segundo_plano' para servidores que não terminam (npm start, flask run). Para subir um SERVIDOR FLASK use 'python -m flask --app app run --port N' (a allowlist recusa 'python -c'). ATENÇÃO AO LEVANTAR UMA SEGUNDA INSTÂNCIA DO PRÓPRIO AXIO para testar o código do disco: ela arranca com o estado VAZIO (sem pasta de projeto), logo /preview/<p> responde 403 e tudo o que depende da pasta recusa — quem restaura a pasta no arranque é o frontend, e um servidor sem frontend não o faz. Nesse caso fixe a pasta de dentro da própria página, com um fetch relativo a POST /api/set_folder e {\"folder\":\"<raiz>\"}.",
    {
        'comando': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'modo': {"tipo": "STRING", "enum": ['aguardar', 'segundo_plano'], "padrao": "aguardar"},
        'timeout': {"tipo": "INTEGER", "padrao": None},
        'cwd': {"tipo": "STRING", "desc": "Pasta onde o processo corre. Vazio usa a pasta do projeto aberta.", "padrao": ""},
    },
    disponivel="edicao",
)
def tool_executar_processo(comando: str, modo: str = "aguardar", timeout=None, cwd: str = ""):
    pasta_de_trabalho, erro_pasta = _pasta_de_trabalho(cwd)
    if erro_pasta:
        return erro_pasta
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
    try:
        reg = iniciar_processo(comando, cwd=pasta_de_trabalho, porta_env=porta_env, modo=modo,
                               acompanhar=(modo == "segundo_plano"))
    except OSError as e:
        return f"ERRO: nao consegui iniciar o processo ({e})."
    pid = reg["id"]
    popen = reg["popen"]
    leitor = reg["_leitor"]

    try:
        if modo == "segundo_plano":
            if _eh_servidor_http(comando) and porta_env:
                threading.Thread(target=_abrir_quando_pronto, args=(pid, porta_env), daemon=True).start()
            return f"PROCESSO INICIADO EM SEGUNDO PLANO (pid={pid}){nota_porta}. Acompanhe em /api/processos e encerre com /api/processo/{pid}/parar."

        if not _esperar_com_progresso(popen, pid, timeout):
            matar_arvore(popen)
            reg["status"] = "timeout"
            emit_event("process_finished", pid=pid, exit_code=None, status="timeout")
            return f"ERRO: o processo excedeu {timeout}s e foi abortado."

        leitor.join(timeout=5)
        reg["status"] = "ok" if popen.returncode == 0 else "erro"
        emit_event("process_finished", pid=pid, exit_code=popen.returncode, status=reg["status"])
        saida = recortar_linhas(reg["log"])
        if reg["status"] == "ok":
            base = saida if saida.strip() else "SUCESSO: processo concluído sem saída."
            return base + nota_porta
        return f"ERRO (exit code {popen.returncode}):\n{saida}"
    except Exception as e:
        reg["status"] = "erro"
        emit_event("process_finished", pid=pid, exit_code=None, status="erro")
        return f"ERRO: {e}"

ESPERA_MORTE = 0.25
TENTATIVAS_MORTE = 4


def parar_processo_reg(pid, reg):
    """Marca o processo como parado, encerra a arvore e devolve quem morreu e quem escapou."""
    popen = reg.get("popen")
    alvos = []
    if popen is not None and _processo_vivo(reg):
        alvos = arvore_processos.arvore(getattr(popen, "pid", 0))
    reg["status"] = "parado"
    if popen is not None:
        matar_arvore(popen)
    sobraram = _encerrar_sobreviventes(alvos)
    emit_event("process_finished", pid=pid, exit_code=None, status="parado")
    return {"alvos": alvos, "sobraram": sobraram}


def _esperar_morrer(pids):
    """Reconta os pids ao longo de um curto intervalo: a morte de um processo nao e instantanea."""
    restantes = arvore_processos.vivos(pids)
    for _ in range(TENTATIVAS_MORTE):
        if not restantes:
            return []
        time.sleep(ESPERA_MORTE / TENTATIVAS_MORTE)
        restantes = arvore_processos.vivos(pids)
    return restantes


def _matar_pid(pid):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=10)
        else:
            os.kill(int(pid), 9)
    except Exception:
        pass


def _encerrar_sobreviventes(alvos):
    """Segunda passagem pelos que escaparam a junta, um a um pelo pid, e reconta."""
    pids = [item["pid"] for item in alvos if item.get("existe")]
    if not pids:
        return []
    sobraram = _esperar_morrer(pids)
    if not sobraram:
        return []
    for item in sobraram:
        _matar_pid(item["pid"])
    return _esperar_morrer([item["pid"] for item in sobraram])

def iniciar_processo(comando, cwd=None, porta_env=None, modo="aguardar", acompanhar=False, stdin_pipe=False,
                     caminhos_extra=None):
    """Abre o comando, registra-o em estado['processos'] e liga o leitor da saida.
    Devolve o registo (com a thread leitora em '_leitor'). Com 'acompanhar' liga tambem o
    monitor que fecha o processo nos eventos quando ele terminar sozinho; quem espera pela
    conclusao (modo 'aguardar') passa False e trata o fim por si, para nao haver dois fim.
    Com 'stdin_pipe' a entrada fica aberta para escrever_stdin_processo (cards do terminal)."""
    cwd = cwd or estado.get("pasta_raiz", "") or os.getcwd()
    pid = id_processo()
    reg = {"id": pid, "comando": comando, "status": "rodando", "log": [], "cwd": cwd,
           "popen": None, "stdin": None, "modo": modo, "nascimento": time.time()}
    estado["processos"][pid] = reg
    emit_event("process_started", pid=pid, comando=comando, modo=modo, cwd=cwd)
    kwargs = {
        "shell": True,
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.PIPE if stdin_pipe else subprocess.DEVNULL,
        "env": montar_env_processo(comando, porta_env, caminhos_extra),
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        popen = subprocess.Popen(comando, **kwargs)
    except OSError:
        reg["status"] = "erro"
        emit_event("process_finished", pid=pid, exit_code=None, status="erro")
        raise
    reg["popen"] = popen
    reg["stdin"] = popen.stdin
    reg["junta"] = _juntar_ao_job(popen)
    reg["_leitor"] = threading.Thread(target=ler_saida_stream, args=(pid, popen), daemon=True)
    reg["_leitor"].start()
    if acompanhar:
        threading.Thread(target=_monitorar_processo_segundo_plano, args=(pid, popen), daemon=True).start()
    return reg

def escrever_stdin_processo(pid, texto, timeout=2.0):
    """Escreve uma linha no stdin de um processo gerido aberto com 'stdin_pipe'.
    Devolve (ok, motivo). A linha vai com CRLF porque o cmd.exe so a da por completa assim;
    a escrita corre numa thread com limite porque um processo que nao le o pipe o enche
    (~64KB) e a escrita bloqueia para sempre."""
    reg = estado.get("processos", {}).get(pid)
    if reg is None:
        return False, "processo nao encontrado"
    popen = reg.get("popen")
    entrada = reg.get("stdin")
    if popen is None or entrada is None:
        return False, "este processo nao aceita entrada"
    try:
        if popen.poll() is not None:
            return False, "o processo ja terminou"
    except Exception:
        return False, "o processo ja terminou"
    bruto = _codificar_entrada_processo(texto)
    pronto = threading.Event()
    resultado = {"erro": ""}

    def _gravar():
        try:
            entrada.write(bruto)
            entrada.flush()
        except (OSError, ValueError) as e:
            resultado["erro"] = str(e)
        finally:
            pronto.set()

    threading.Thread(target=_gravar, daemon=True).start()
    if not pronto.wait(timeout):
        return False, "o processo nao esta a ler a entrada"
    if resultado["erro"]:
        return False, f"nao consegui escrever: {resultado['erro']}"
    return True, ""

@register(
    "tool_parar_processo",
    'Para (mata) um processo em segundo plano pelo pid, com a arvore inteira. Use para encerrar servidores e processos longos antes de reinicia-los. Obtenha os pids em /api/processos. A resposta PROVA o que aconteceu: diz quantos processos a arvore tinha, quais morreram e se algum sobreviveu (com pid e nome) - sao os que seguram a porta que voce acha livre.',
    {
        'pid': {"tipo": "STRING", "desc": 'Identificador do processo (ex: proc_1)', "obrig": True, "padrao": ""},
    },
    disponivel="edicao",
)
def tool_parar_processo(pid: str):
    emit_event("executing", function="Parando processo")
    pid = (pid or "").strip()
    if not pid:
        return "ERRO: informe o pid do processo a parar."
    reg = estado.get("processos", {}).get(pid)
    if reg is None:
        return f"ERRO: processo '{pid}' nao encontrado. Liste os pids em /api/processos."
    return _texto_da_paragem(pid, parar_processo_reg(pid, reg))


def _texto_da_paragem(pid, relato):
    """A prova da paragem: a arvore que existia, o que morreu e o que ficou de pe."""
    vivos = [item for item in (relato.get("alvos") or []) if item.get("existe")]
    sobraram = relato.get("sobraram") or []
    escaparam = {item["pid"] for item in sobraram}
    if not vivos:
        return f"Processo {pid} parado: a arvore ja estava morta quando o pedido chegou."
    linhas = [
        f"Processo {pid} parado: a arvore tinha {len(vivos)} processo(s), "
        f"morreram {len(vivos) - len(escaparam)}."
    ]
    for item in sorted(vivos, key=lambda i: (i["nivel"], i["pid"])):
        marca = "SOBREVIVEU" if item["pid"] in escaparam else "morto"
        linhas.append(f"  {'  ' * item['nivel']}{item['pid']} {item['nome'] or '?'} [{marca}]")
    if sobraram:
        quem = ", ".join(f"{item['pid']} {item['nome'] or '?'}" for item in sobraram)
        linhas.append(
            f"AVISO: {quem} continua(m) vivo(s) - sem permissao para matar ou fora do alcance da "
            "junta. Confirme com tool_listar_processos antes de arrancar outro igual."
        )
    return "\n".join(linhas)

@register(
    "tool_listar_processos",
    'Lista os processos em segundo plano iniciados pelo Axio (pid, comando, estado). Use para saber o que esta a correr antes de parar ou reiniciar algo. Com saida>0 mostra tambem as ultimas linhas que cada processo escreveu - o caminho para ler a resposta de um processo que continua a correr (um depurador, um servidor) sem o parar.',
    {
        "saida": {
            "tipo": "INTEGER",
            "desc": "Quantas linhas do fim da saida de cada processo mostrar (0 = so o estado).",
            "padrao": 0,
        },
    },
    disponivel="edicao",
)
def tool_listar_processos(saida=0):
    """Lista os processos em segundo plano iniciados pelo Axio (pid, comando, estado).

    Permite saber o que esta a correr (servidores, watchers) sem ter de decorar
    os pids nem consultar /api/processos manualmente. Com 'saida' traz tambem o fim
    do que cada um escreveu, que e a unica forma de ler um processo que nao terminou.
    """
    emit_event("executing", function="Listando processos em segundo plano")
    registros = estado.get("processos", {})
    if not registros:
        return "Nenhum processo em segundo plano nesta sessao."
    linhas = []
    for pid, reg in registros.items():
        estado_txt = "rodando" if _processo_vivo(reg) else reg.get("status", "parado")
        bloco = f"{pid}: {reg.get('comando', '(desconhecido)')} [{estado_txt}]"
        if saida and saida > 0:
            cauda = [str(linha) for linha in (reg.get("log") or [])[-int(saida):]]
            if cauda:
                bloco += "\n" + "\n".join("    " + linha for linha in cauda)
        linhas.append(bloco)
    return "Processos em segundo plano:\n" + "\n".join(linhas)


IDADE_PROCESSO_ANTIGO = 30 * 60
LIMITE_BLOCO_PROCESSOS = 12


def _processo_vivo(reg):
    """O processo do registo ainda corre? Um popen ja fechado da False, sem levantar."""
    popen = (reg or {}).get("popen")
    if popen is None:
        return False
    try:
        return popen.poll() is None
    except Exception:
        return False


def _idade_texto(segundos):
    if segundos < 60:
        return f"{int(segundos)}s"
    if segundos < 3600:
        return f"{int(segundos // 60)}min"
    return f"{segundos / 3600:.1f}h"


def limpar_processos_encerrados():
    """Tira do registo o que ja terminou: a lista e uma so e nao pode crescer a cada rodada."""
    registros = estado.get("processos", {})
    mortos = [pid for pid, reg in list(registros.items()) if not _processo_vivo(reg)]
    for pid in mortos:
        registros.pop(pid, None)
        _fechar_junta(pid)
    return len(mortos)


def bloco_processos():
    """O que continua a correr de rodadas anteriores, dito ao agente no inicio de cada rodada.

    Um servidor esquecido segura portas, ficheiros e a placa de video, e volta como erro que
    ninguem liga ao processo que o deixou de pe. Com isto o agente sabe o que ficou antes de
    comecar e limpa o que ja nao serve antes de arrancar outro igual.
    """
    limpar_processos_encerrados()
    agora = time.time()
    vivos = [(pid, reg) for pid, reg in estado.get("processos", {}).items() if _processo_vivo(reg)]
    if not vivos:
        return ""
    linhas = []
    antigos = 0
    for pid, reg in vivos[:LIMITE_BLOCO_PROCESSOS]:
        idade = agora - float(reg.get("nascimento") or agora)
        velho = idade > IDADE_PROCESSO_ANTIGO
        antigos += 1 if velho else 0
        linhas.append(f"- {pid}: {str(reg.get('comando'))[:90]} "
                      f"[{reg.get('modo') or '?'}, {_idade_texto(idade)}"
                      f"{', ANTIGO' if velho else ''}]")
    if len(vivos) > LIMITE_BLOCO_PROCESSOS:
        linhas.append(f"- (+{len(vivos) - LIMITE_BLOCO_PROCESSOS} processos; a lista completa esta "
                      "em /api/processos)")
    aviso = (
        f" {antigos} dele(s) corre(m) ha mais de meia hora: pare o que ja nao serve com"
        " tool_parar_processo ANTES de arrancar outro igual - dois servidores na mesma porta sao"
        " a origem dos erros que ninguem liga ao processo."
        if antigos else ""
    )
    return (
        "=== PROCESSOS AINDA A CORRER (de rodadas anteriores) ===\n"
        f"{len(vivos)} processo(s) em segundo plano continuam vivos nesta sessao.{aviso}\n"
        + "\n".join(linhas)
        + "\nIsto e estado, nao instrucao: a tarefa pedida vem primeiro e um processo que serve o"
        " trabalho em curso nao se para.\n"
    )


def run_com_timeout(cmd, timeout=60, cwd=None):
    """Executa um comando externo com timeout que realmente funciona no Windows.

    subprocess.run(..., shell=True, timeout=...) mata apenas o shell; o processo
    neto (ex: node via npx) herda os pipes de stdout/stderr e o communicate()
    nunca retorna, ignorando o timeout. Aqui usamos Popen + communicate(timeout)
    e, ao estourar, encerramos a arvore inteira com matar_arvore antes de relancar
    subprocess.TimeoutExpired para o chamador tratar.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=isinstance(cmd, str),
        cwd=cwd or None,
    )
    _juntar_ao_job(proc)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        matar_arvore(proc)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        raise
    return subprocess.CompletedProcess(proc.args, proc.returncode,
                                       _texto_de_saida(out), _texto_de_saida(err))


FATIA_PROGRESSO_PROCESSO = 10.0


def _texto_de_progresso(pid, decorrido, timeout):
    reg = estado.get("processos", {}).get(pid) or {}
    comando = str(reg.get("comando") or "processo")[:60]
    log = reg.get("log") or []
    cauda = f" | ultima linha: {log[-1][:100]}" if log else ""
    return f"{comando} - {int(decorrido)}s de {int(timeout)}s{cauda}"


def _esperar_com_progresso(popen, pid, timeout, fatia=FATIA_PROGRESSO_PROCESSO):
    """Espera pelo fim em fatias, avisando o ecra do que ja corre.

    Sem isto um passo longo (um pip install de gigabytes, um build) fica minutos calado e
    nao se sabe se anda ou morreu. Devolve False quando o tempo acaba.
    """
    restante = float(timeout)
    decorrido = 0.0
    while restante > 0:
        passo = min(fatia, restante)
        try:
            popen.wait(timeout=passo)
            return True
        except subprocess.TimeoutExpired:
            decorrido += passo
            restante -= passo
            if restante <= 0:
                return False
            emit_event("executing", function=_texto_de_progresso(pid, decorrido, timeout))
    return False


def correr_como_card(comando, cwd=None, timeout=300, caminhos_extra=None):
    """Corre o comando como card do terminal (visivel, com parar) e espera pelo fim."""
    reg = iniciar_processo(comando, cwd=cwd, modo="card", acompanhar=True,
                           caminhos_extra=caminhos_extra)
    return _esperar_card(reg, timeout)


def _esperar_card(reg, timeout):
    pid = reg["id"]
    restante = float(timeout)
    decorrido = 0.0
    while restante > 0:
        passo = min(FATIA_PROGRESSO_PROCESSO, restante)
        fim = time.time() + passo
        while time.time() < fim:
            if reg.get("status") != "rodando":
                return _resultado_do_card(reg)
            time.sleep(0.2)
        decorrido += passo
        restante -= passo
        if restante > 0:
            emit_event("executing", function=_texto_de_progresso(pid, decorrido, timeout))
    popen = reg.get("popen")
    if popen is not None:
        matar_arvore(popen)
    reg["status"] = "timeout"
    emit_event("process_finished", pid=pid, exit_code=None, status="timeout")
    return _resultado_do_card(reg)


def _resultado_do_card(reg):
    leitor = reg.get("_leitor")
    if leitor is not None:
        leitor.join(timeout=5)
    popen = reg.get("popen")
    codigo = None
    if popen is not None:
        try:
            codigo = popen.returncode if popen.returncode is not None else popen.poll()
        except Exception:
            codigo = None
    resultado = subprocess.CompletedProcess(reg.get("comando"), codigo,
                                            "\n".join(reg.get("log") or []), "")
    resultado.status = reg.get("status")
    resultado.pid = reg.get("id")
    return resultado


