import json
import os
import queue
import threading
import time

from src.backend.config import APP_ROOT

ARRANQUE = time.time()

estado = {
    "pasta_raiz": "",
    "stats": {"rpd": 0},
    "uso_minuto": [],
    "historico_chat": [],
    "file_history": {},
    "arquivos_tocados": set(),
    "edicoes_rodada": [],
    "session_id_atual": "",
    "bloquear_edicao": False,
    "processos": {},
    "compactacoes_contexto": 0,
    "cwd_terminal": "",
    "terminal_shell": "",
    "projeto_planejado": False,
    "urls_navegadas_turno": set(),
    "vetor_ocupado": {},
    "turno_ocupado": False,
    "etiquetando": False,
    "etiquetando_progresso": "",
    "traducao": {"estado": "livre", "texto": "", "erro": ""}
}

MSG_SEM_PASTA = "ERRO: Nenhuma pasta de projeto selecionada."

MAX_UNDO = 100

memoria_lock = threading.Lock()

mineracao_em_andamento = threading.Event()

_turn_local = threading.local()

_event_subscribers = set()
_subscribers_lock = threading.Lock()

def registrar_subscriber():
    """Cria e registra a fila de eventos de uma conexao SSE."""
    fila = queue.Queue()
    with _subscribers_lock:
        _event_subscribers.add(fila)
    return fila

def remover_subscriber(fila):
    """Desregistra a fila de uma conexao SSE encerrada (evita consumidor zumbi)."""
    with _subscribers_lock:
        _event_subscribers.discard(fila)

def limpar_eventos():
    """Descarta os eventos pendentes de todas as conexoes conectadas."""
    with _subscribers_lock:
        filas = list(_event_subscribers)
    for fila in filas:
        while not fila.empty():
            try:
                fila.get_nowait()
            except queue.Empty:
                break

def set_turn_id(turn_id):
    _turn_local.turn_id = turn_id

def silenciar_eventos_desta_thread(ativo=True):
    """Suspende os eventos emitidos por ESTA thread.

    A traducao das notas consulta o codigo com as ferramentas de leitura em
    segundo plano: os "executing"/"Pesquisando: ..." dessas chamadas nao podem
    chegar a barra de status, que pertence ao agente principal.
    """
    _turn_local.silencioso = bool(ativo)

def emit_event(event_type, **kwargs):
    if getattr(_turn_local, "silencioso", False):
        return
    data = {"type": event_type}
    data.update(kwargs)
    turn_id = getattr(_turn_local, "turn_id", None)
    if turn_id is not None:
        data["turn_id"] = turn_id
    msg = f"data: {json.dumps(data)}\n\n"
    with _subscribers_lock:
        filas = list(_event_subscribers)
    for fila in filas:
        fila.put(msg)

_avisos_de_mudanca = []

def registar_aviso_de_mudanca(fn):
    """Registra quem quer ser avisado quando o projeto muda ficheiros.

    Existe para nao criar ciclo de imports: quem precisa de reagir (ex: o indice
    de basenames da memoria, que fica em memory/manutencao.py e ja importa state)
    registra aqui a sua funcao em vez de a state a importar.
    """
    if fn not in _avisos_de_mudanca:
        _avisos_de_mudanca.append(fn)

def notificar_mudanca_arquivos():
    emit_event("files_changed")
    for aviso in list(_avisos_de_mudanca):
        try:
            aviso()
        except Exception:
            pass

def caminho_estado_projeto(*partes):
    """Caminho do estado por-projeto do Axio dentro de .axio/ (ou "" sem pasta)."""
    raiz = estado.get("pasta_raiz", "")
    if not raiz:
        return ""
    return os.path.join(raiz, ".axio", *partes)

def no_diretorio_do_axio():
    """True quando a pasta de projeto aberta e a raiz do proprio Axio.

    Gate da auto-melhoria (regra 26): as ferramentas do agente vivem em APP_ROOT.
    Quando o utilizador trabalha noutro projeto, elas ficam fora do alcance de
    escrita (resolver_caminho recusa caminhos fora da pasta do projeto), logo
    medir atrito ou prometer melhoria nas proprias ferramentas seria confundir o
    agente. Compara com normcase porque no Windows "D:\\Dropbox" e "d:\\dropbox"
    sao a mesma pasta.
    """
    raiz = estado.get("pasta_raiz", "")
    if not raiz:
        return False
    return os.path.normcase(os.path.normpath(os.path.abspath(raiz))) == os.path.normcase(
        os.path.normpath(os.path.abspath(APP_ROOT))
    )
