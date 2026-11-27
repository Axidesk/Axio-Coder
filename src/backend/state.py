import json
import os
import queue
import threading
import time

from src.backend.config import APP_ROOT

ARRANQUE = time.time()

CHAVE_DO_PRINCIPAL = "principal"


def _estado_novo():
    """Um estado de trabalho em branco - a copia de partida de cada workspace."""
    return {
        "pasta_raiz": "",
        "stats": {"rpd": 0},
        "uso_minuto": [],
        "historico_chat": [],
        "file_history": {},
        "arquivos_tocados": set(),
        "edicoes_rodada": [],
        "memorias_injetadas": {},
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
        "traducao": {"estado": "livre", "texto": "", "erro": ""},
    }


class Workspace:
    """Uma area de trabalho: a pasta do projeto e a conversa DELA.

    Duas areas abertas ao mesmo tempo nao se veem: o que muda de uma para outra
    e a pasta, o historico do chat, a sessao, os processos e o cwd do terminal.
    """

    def __init__(self, chave, nome=""):
        self.chave = chave
        self.nome = nome
        self.dados = _estado_novo()

    def retrato(self):
        return {
            "chave": self.chave,
            "nome": self.nome or os.path.basename(os.path.normpath(self.dados.get("pasta_raiz") or "")) or "",
            "pasta": self.dados.get("pasta_raiz") or "",
            "ocupado": bool(self.dados.get("turno_ocupado")),
        }


_workspaces = {}
_workspaces_lock = threading.Lock()
_ws_local = threading.local()


def _criar_workspace(chave, nome=""):
    ws = Workspace(chave, nome)
    with _workspaces_lock:
        _workspaces[chave] = ws
    return ws


_criar_workspace(CHAVE_DO_PRINCIPAL)


def ligar_workspace(chave):
    """Prende esta thread a um workspace - tudo o que ela ler/escrever e dele.

    Um turno corre na propria thread e chama isto ao comecar. Sem isto, dois
    pedidos simultaneos de projetos diferentes escreviam no mesmo estado (a
    pasta, o historico e a sessao de um atropelavam os do outro).
    """
    chave = chave or CHAVE_DO_PRINCIPAL
    with _workspaces_lock:
        ws = _workspaces.get(chave)
    if ws is None:
        ws = _criar_workspace(chave)
    _ws_local.workspace = ws
    return ws


def desligar_workspace():
    _ws_local.workspace = None


def workspace_atual():
    """O workspace preso a esta thread, ou o principal quando nao ha nenhum."""
    ws = getattr(_ws_local, "workspace", None)
    if ws is not None:
        return ws
    with _workspaces_lock:
        return _workspaces.get(CHAVE_DO_PRINCIPAL)


def chave_do_workspace():
    return workspace_atual().chave


def nomear_workspace(chave, nome):
    with _workspaces_lock:
        ws = _workspaces.get(chave)
    if ws is not None:
        ws.nome = nome or ""
    return ws


def listar_workspaces():
    with _workspaces_lock:
        return [ws.retrato() for ws in _workspaces.values()]


def fechar_workspace(chave):
    """Descarta um workspace. O principal fica sempre - e para onde tudo volta."""
    if not chave or chave == CHAVE_DO_PRINCIPAL:
        return False
    with _workspaces_lock:
        return _workspaces.pop(chave, None) is not None


class _Estado:
    """O `estado` de sempre, agora resolvido para o workspace desta thread.

    A interface e a de um dicionario (leitura, escrita, get, setdefault, pop,
    update, items...) e por isso as centenas de chamadas espalhadas pelo
    backend nao mudam: quem decide de que projeto e o estado e a thread.
    """

    @staticmethod
    def _alvo():
        return workspace_atual().dados

    def __getitem__(self, chave):
        return self._alvo()[chave]

    def __setitem__(self, chave, valor):
        self._alvo()[chave] = valor

    def __delitem__(self, chave):
        del self._alvo()[chave]

    def __contains__(self, chave):
        return chave in self._alvo()

    def __len__(self):
        return len(self._alvo())

    def __iter__(self):
        return iter(self._alvo())

    def get(self, chave, padrao=None):
        return self._alvo().get(chave, padrao)

    def setdefault(self, chave, padrao=None):
        return self._alvo().setdefault(chave, padrao)

    def pop(self, chave, *args):
        return self._alvo().pop(chave, *args)

    def update(self, *args, **kwargs):
        return self._alvo().update(*args, **kwargs)

    def clear(self):
        return self._alvo().clear()

    def keys(self):
        return self._alvo().keys()

    def values(self):
        return self._alvo().values()

    def items(self):
        return self._alvo().items()


estado = _Estado()

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

def turn_id_atual():
    """O turno desta thread - o vigia das ferramentas corre noutra e precisa dele."""
    return getattr(_turn_local, "turn_id", None)

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
    ws = getattr(_ws_local, "workspace", None)
    if ws is not None:
        data["workspace"] = ws.chave
    msg = f"data: {json.dumps(data)}\n\n"
    with _subscribers_lock:
        filas = list(_event_subscribers)
    for fila in filas:
        fila.put(msg)

_pedido_de_reinicio = False
_lock_do_reinicio = threading.Lock()

def pedir_reinicio_da_interface():
    """Marca que a janela e o servidor devem reiniciar no FIM da rodada.

    O pedido nunca se executa a meio: quem reinicia e a janela, quando a rodada
    ja acabou e a resposta esta entregue - por isso o sinal vai agarrado ao
    evento 'done' e nao a uma accao imediata.
    """
    global _pedido_de_reinicio
    with _lock_do_reinicio:
        _pedido_de_reinicio = True

def consumir_pedido_de_reinicio():
    """Devolve se houve pedido e limpa-o - cada pedido vale por uma rodada so."""
    global _pedido_de_reinicio
    with _lock_do_reinicio:
        pedido = _pedido_de_reinicio
        _pedido_de_reinicio = False
    return pedido

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

def _ficheiro_de_projetos():
    return os.path.join(APP_ROOT, "data", "projetos_abertos.json")

def projetos_ja_abertos():
    """As pastas de projeto que o Axio ja abriu, da mais recente para a mais antiga.

    Existe porque o material de um projeto vive no .axio DELE: com outro projeto
    aberto, o Axio precisa de saber onde estao as conversas e as notas do
    primeiro para nao as tomar por orfas e para as alcancar a partir daqui.
    So devolve pastas que ainda existem no disco.
    """
    try:
        with open(_ficheiro_de_projetos(), encoding="utf-8") as fh:
            guardadas = json.load(fh)
    except (OSError, ValueError):
        return []
    if not isinstance(guardadas, list):
        return []
    vistas = []
    for pasta in guardadas:
        if isinstance(pasta, str) and pasta and os.path.isdir(pasta):
            if os.path.normcase(pasta) not in [os.path.normcase(v) for v in vistas]:
                vistas.append(pasta)
    return vistas

def registar_projeto_aberto(pasta):
    """Guarda a pasta de projeto aberta, para o Axio a recordar quando correr noutra."""
    if not pasta:
        return
    alvo = os.path.abspath(pasta)
    lista = [p for p in projetos_ja_abertos()
             if os.path.normcase(os.path.abspath(p)) != os.path.normcase(alvo)]
    lista.insert(0, alvo)
    try:
        with open(_ficheiro_de_projetos(), "w", encoding="utf-8") as fh:
            json.dump(lista[:20], fh, ensure_ascii=False, indent=2)
    except OSError:
        pass

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
