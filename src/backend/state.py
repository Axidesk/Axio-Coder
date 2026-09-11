import json
import os
import queue
import threading

# Estado global
estado = {
    "pasta_raiz": "",
    "stats": {"rpd": 0},
    "uso_minuto": [],
    "event_queue": queue.Queue(),
    "historico_chat": [],
    # Histórico de desfazer/refazer por arquivo: {caminho: {"undo": [...], "redo": [...]}}
    # Cada arquivo tem a própria pilha, permitindo desfazer/refazer de forma independente.
    "file_history": {},
    # Arquivos tocados na sessão atual (edição/criação), usados para montar o
    # checkpoint de código persistido junto com o log da sessão (Fase 1 de restauração).
    "arquivos_tocados": set(),
    # Edições (arquivo + linha) registradas desde o último turno, para injeção no
    # contexto da próxima mensagem (equivale ao "último arquivo editado" do Cursor).
    "edicoes_rodada": [],
    # Identificador da sessão atual de logs (gerado ao selecionar a pasta).
    # Todas as edições feitas enquanto o programa está aberto no mesmo projeto
    # são acumuladas neste mesmo id, formando UMA sessão no histórico.
    "session_id_atual": "",
    # Modo semi-automático: bloqueia as ferramentas de edição na FASE 1 até que
    # a IA chame 'tool_aprovar_plano' após perceber a aprovação do usuário.
    "bloquear_edicao": False,
    # Processos longos em segundo plano (venv/pip/npm install/servidores).
    # Cada entrada: {id: {"popen", "status", "log", "cwd", "comando"}}.
    "processos": {},
    # Número de compactações de contexto disparadas nesta sessão (exibido na barra de uso).
    "compactacoes_contexto": 0,
    # Pasta de trabalho atual do terminal (compartilhada com o explorer).
    # Vazio = usar a pasta raiz do projeto. Persiste só em RAM durante a sessão.
    "cwd_terminal": "",
    # Shell escolhido pelo usuário no dropdown do terminal ("cmd"/"powershell"/"pwsh"/...).
    # Vazio = detecção automática (AXIO_TERM_SHELL ou pwsh>powershell>cmd).
    "terminal_shell": "",
    # Trava de segurança para projetos novos
    "projeto_planejado": False,
    # URLs realmente navegadas (tool_buscar_web) no turno atual, usadas no
    # cross-check do tool_planejar_arquitetura para impedir fontes inventadas.
    "urls_navegadas_turno": set()
}

# Mensagem padrao compartilhada por rotas e servicos quando nenhuma pasta de
# projeto foi selecionada. Centralizada para evitar literais repetidos.
MSG_SEM_PASTA = "ERRO: Nenhuma pasta de projeto selecionada."

# Limite de edições mantidas no histórico de desfazer/refazer
MAX_UNDO = 100

# Serializa o acesso in-process ao ChromaDB do mempalace. O espelho de notas
# (espelhar_notas_existentes) roda em thread de background e disputa a abertura
# do PersistentClient com a busca semantica, causando "Could not connect to
# tenant default_tenant" / "RustBindingsAPI object has no attribute 'bindings'"
# na primeira interacao apos reabrir o app.
memoria_lock = threading.Lock()

# Indica que o minerador do mempalace esta rodando (mine_convos segura o
# memoria_lock durante toda a mineracao). A busca semantica espera este
# evento em vez de disputar o lock e estourar timeout na primeira interacao.
mineracao_em_andamento = threading.Event()

# Identificador do turno ativo na thread atual (thread-local). Permite que o
# frontend descarte eventos de um turno antigo/cancelado e nunca interfira no novo.
_turn_local = threading.local()

def set_turn_id(turn_id):
    _turn_local.turn_id = turn_id

def emit_event(event_type, **kwargs):
    data = {"type": event_type}
    data.update(kwargs)
    turn_id = getattr(_turn_local, "turn_id", None)
    if turn_id is not None:
        data["turn_id"] = turn_id
    estado["event_queue"].put(f"data: {json.dumps(data)}\n\n")

def notificar_mudanca_arquivos():
    emit_event("files_changed")

def caminho_estado_projeto(*partes):
    """Caminho do estado por-projeto do Axio dentro de .axio/ (ou "" sem pasta)."""
    raiz = estado.get("pasta_raiz", "")
    if not raiz:
        return ""
    return os.path.join(raiz, ".axio", *partes)
