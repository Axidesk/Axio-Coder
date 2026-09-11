import os
import threading

from src.backend.state import estado

try:
    from watchfiles import Change, watch
except ImportError:
    Change = None
    watch = None

EXTENSOES_TEXTO = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".md",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".txt", ".sh", ".bat", ".ps1",
    ".cpp", ".h", ".hpp", ".cc", ".c", ".java", ".go", ".rs", ".rb", ".php",
    ".sql", ".xml", ".csv", ".vue", ".svelte", ".env", ".gitignore",
}

ARQUIVOS_SEM_EXT = {
    "Dockerfile", "Makefile", "LICENSE", "README",
    ".env", ".gitignore", ".dockerignore", ".editorconfig",
}

PASTAS_IGNORADAS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".axio",
    "dist", "build", ".idea", ".vscode", ".next", ".nuxt", "target",
}

ARQUIVOS_IGNORADOS = {"busca.txt"}

TAMANHO_MAX = 2 * 1024 * 1024
LIMITE_PRE_CACHE = 2000

_cache = {}
_lock = threading.Lock()
_stop_event = None
_thread = None


def _rel(caminho):
    raiz = estado.get("pasta_raiz", "")
    if not raiz:
        return caminho.replace("\\", "/")
    try:
        return os.path.relpath(caminho, raiz).replace("\\", "/")
    except ValueError:
        return caminho.replace("\\", "/")

def _deve_monitorar(caminho):
    nome = os.path.basename(caminho)
    if nome in ARQUIVOS_IGNORADOS:
        return False
    if nome.endswith(("~", ".swp", ".tmp", ".bak", ".orig")):
        return False
    rel = _rel(caminho)
    partes = rel.replace("\\", "/").split("/")
    if any(p in PASTAS_IGNORADAS for p in partes):
        return False
    if nome in ARQUIVOS_SEM_EXT:
        return True
    return os.path.splitext(caminho)[1].lower() in EXTENSOES_TEXTO

def notificar_gravacao(caminho, conteudo):
    """Sincroniza o cache do watcher ap\u00f3s grava\u00e7\u00f5es feitas pelo backend/editor.

    Mant\u00e9m o \"antes\" do watcher sempre alinhado ao \u00faltimo conte\u00fado conhecido,
    para que edi\u00e7\u00f5es externas (VS Code etc.) sejam detectadas com a linha correta
    e edi\u00e7\u00f5es internas n\u00e3o gerem falso positivo.
    """
    with _lock:
        if conteudo is None:
            _cache.pop(caminho, None)
        else:
            _cache[caminho] = conteudo

def _ler(caminho):
    try:
        st = os.stat(caminho)
    except OSError:
        return None
    if st.st_size > TAMANHO_MAX:
        return None
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None

def _preencher_cache(raiz):
    contador = 0
    with _lock:
        _cache.clear()
    for root, dirs, files in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in PASTAS_IGNORADAS]
        for nome in files:
            if contador >= LIMITE_PRE_CACHE:
                return
            caminho = os.path.join(root, nome)
            if not _deve_monitorar(caminho):
                continue
            conteudo = _ler(caminho)
            if conteudo is not None:
                with _lock:
                    _cache[caminho] = conteudo
                contador += 1

def _processar(changes):
    from src.backend.services.file_service import registrar_edicao_para_contexto

    for change, caminho in changes:
        if not _deve_monitorar(caminho):
            continue
        if change == Change.deleted:
            with _lock:
                antes = _cache.pop(caminho, None)
            if antes is None:
                continue
            registrar_edicao_para_contexto(caminho, antes, None)
            continue
        atual = _ler(caminho)
        if atual is None:
            continue
        with _lock:
            antes = _cache.get(caminho)
        if antes == atual:
            with _lock:
                _cache[caminho] = atual
            continue
        registrar_edicao_para_contexto(caminho, antes, atual)
        with _lock:
            _cache[caminho] = atual

def _loop(raiz):
    try:
        for changes in watch(
            raiz,
            watch_filter=None,
            debounce=800,
            step=50,
            stop_event=_stop_event,
            recursive=True,
            raise_interrupt=False,
        ):
            if _stop_event is not None and _stop_event.is_set():
                break
            _processar(changes)
    except Exception:
        pass

def iniciar_watcher():
    global _stop_event, _thread
    if watch is None:
        return
    parar_watcher()
    raiz = estado.get("pasta_raiz", "")
    if not raiz or not os.path.isdir(raiz):
        return
    _preencher_cache(raiz)
    _stop_event = threading.Event()
    _thread = threading.Thread(target=_loop, args=(raiz,), daemon=True)
    _thread.start()

def parar_watcher():
    global _stop_event, _thread
    if _stop_event is not None:
        _stop_event.set()
        _stop_event = None
    if _thread is not None:
        _thread.join(timeout=2)
        _thread = None
