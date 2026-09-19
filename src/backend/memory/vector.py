import os
import re
import shutil
import sqlite3
import threading
import time

from src.backend.state import estado, emit_event, memoria_lock, mineracao_em_andamento, caminho_estado_projeto
from src.backend.memory.store import garantir_pasta_knowledge, nome_arquivo_seguro

_patch_mempalace_aplicado = False
_backfill_ai_memory_executado = False

MIN_SIMILARIDADE_MEMORIA = 0.45
VARREDURA_TIMEOUT = 120.0
PROPORCAO_MAX_ORFAOS = 0.4
ROOM_NOTAS = "ai_memory"
ROOMS_PROTEGIDAS = {ROOM_NOTAS, "_registry"}

def garantir_patch_mempalace():
    global _patch_mempalace_aplicado
    if _patch_mempalace_aplicado:
        return
    from src.backend.memory.mempalace_patch import aplicar_patch
    aplicar_patch()
    _patch_mempalace_aplicado = True

def wing_da_pasta(pasta_raiz):
    """Deriva um wing (namespace de memória) estável e único por projeto."""
    if not pasta_raiz:
        return None
    nome = os.path.basename(os.path.normpath(pasta_raiz)).strip().lower()
    if not nome:
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", nome).strip("-")
    return slug or None

def _contexto_vetor(titulo):
    """Devolve (palace_path, wing, source_file, erro) comuns as operacoes do vetor.

    Nao exige que o palace ja exista: a gravacao (create=True) o recria
    sob demanda, e a exclusao (create=False) devolve PalaceNotFoundError de
    forma graciosa se o diretorio foi apagado.
    """
    palace_path = os.path.expanduser("~/.mempalace/palace")
    wing = wing_da_pasta(estado.get("pasta_raiz")) or "general"
    source_file = os.path.join(garantir_pasta_knowledge(), f"{nome_arquivo_seguro(titulo)}.md")
    return palace_path, wing, source_file, None

_fila_vetor = []
_trava_fila_vetor = threading.Lock()

def _marcar_ocupacao(tipo):
    """Marca o vetor como ocupado e devolve a marca, para a poder limpar depois.

    A marca e a fonte de verdade da ocupacao (ver _ocupacao_atual): tanto as
    operacoes pesadas como o minerador a gravam. Devolver o proprio objeto e o
    que permite limpar apenas a marca de quem a pos: sem isso, o fim de uma
    operacao apagaria a marca de outra que continuasse a correr.
    """
    marca = {"tipo": tipo, "inicio": time.time()}
    estado["vetor_ocupado"] = marca
    return marca

def _limpar_ocupacao(marca):
    """Liberta o vetor, mas so se a marca em vigor ainda for esta."""
    if marca is not None and estado.get("vetor_ocupado") is marca:
        estado["vetor_ocupado"] = {}

def _enfileirar_no_vetor(operacao, titulo, conteudo=None):
    with _trava_fila_vetor:
        _fila_vetor.append((operacao, titulo, conteudo))

def esvaziar_fila_do_vetor():
    """Reaplica no vetor o que ficou adiado, se ele ja estiver livre.

    Corre no fim da mineracao, que e a unica ocupacao longa. Usa os nucleos
    _gravar/_excluir diretamente: chamar as funcoes publicas aqui so
    re-enfileiraria o que se acabou de tirar da fila.
    """
    with _trava_fila_vetor:
        if not _fila_vetor:
            return
        pendentes = list(_fila_vetor)
        _fila_vetor.clear()
    for indice, (operacao, titulo, conteudo) in enumerate(pendentes):
        if _ocupacao_atual():
            with _trava_fila_vetor:
                _fila_vetor[:0] = pendentes[indice:]
            return
        if operacao == "gravar":
            _gravar_no_vetor(titulo, conteudo)
        else:
            _excluir_do_vetor(titulo)

def _rodar_com_timeout(trabalho, timeout, ocupacao=None):
    """Roda `trabalho(resultado)` numa thread daemon sob memoria_lock.

    Ponto UNICO do padrao 'thread + join + memoria_lock' repetido por todas as
    operacoes do vetor (gravar, varrer, limpar, reparar, compactar). `trabalho`
    recebe um dict onde grava o que produzir; a excecao, se houver, fica em
    resultado["erro"]. Quando `ocupacao` e dado, marca estado["vetor_ocupado"]
    enquanto corre, para o acao='status' conseguir acompanhar a operacao mesmo
    depois de a tool devolver timeout.

    Devolve (resultado, expirou): expirou=True significa que o timeout estourou
    e a thread segue em background - NAO e falha.
    """
    resultado = {}
    ocupado = _marcar_ocupacao(ocupacao) if ocupacao else None

    def _executar():
        try:
            with memoria_lock:
                trabalho(resultado)
        except Exception as e:
            resultado["erro"] = str(e)
        finally:
            if ocupado:
                _limpar_ocupacao(ocupado)

    t = threading.Thread(target=_executar, daemon=True)
    t.start()
    t.join(timeout)
    return resultado, t.is_alive()

def _executar_no_vetor(fn, timeout_msg):
    """Roda `fn` sob memoria_lock numa thread com timeout, devolvendo 'ok' ou erro."""
    resultado, expirou = _rodar_com_timeout(lambda _r: fn(), 6.0)
    if expirou:
        return timeout_msg
    if "erro" in resultado:
        return f"erro: {resultado['erro']}"
    return "ok"

def _room_protegida(room):
    """Rooms de memoria canonica do Axio/mempalace, que a limpeza NUNCA remove.

    ai_memory guarda as notas do usuario e _registry e o livro de registo do
    mempalace. Ambas podem ter source_file sintetico ou apontar para um
    caminho que mudou, o que as marcaria como 'orfas' e as apagaria por engano -
    perder memoria de verdade por causa de um path. As notas so saem do vetor
    por exclusao explicita (tool_gerenciar_memoria acao='excluir').
    """
    return (room or "") in ROOMS_PROTEGIDAS

def _gravar_no_vetor(titulo, conteudo):
    try:
        garantir_patch_mempalace()
        from mempalace.palace import get_collection
        from mempalace.miner import add_drawer
    except Exception as e:
        return f"falha ao importar mempalace: {e}"
    palace_path, wing, source_file, erro = _contexto_vetor(titulo)
    if erro:
        return erro

    def _trabalho():
        col = get_collection(palace_path, create=True)
        add_drawer(col, wing, ROOM_NOTAS, conteudo, source_file, 0, "axio")
    return _executar_no_vetor(_trabalho, "timeout ao gravar no vetor")

def salvar_memoria_no_vetor(titulo, conteudo):
    """Grava a nota no vetor, ou adia se houver operacao a correr.

    Durante o minerador (que segura o memoria_lock por minutos) gravar seria
    disputar o lock e acabar em timeout - e, pior, deixar a thread viva a
    escrever mais tarde, em paralelo com a mineracao. O caso real e este: a
    mineracao arranca no fim de cada resposta e ainda corre quando a rodada
    seguinte tenta gravar. Aqui a nota entra na fila e e indexada quando o
    vetor libertar.
    """
    ocupacao = _ocupacao_atual()
    if ocupacao:
        _enfileirar_no_vetor("gravar", titulo, conteudo)
        return f"adiado (vetor ocupado com {ocupacao})"
    return _gravar_no_vetor(titulo, conteudo)

def _excluir_do_vetor(titulo):
    try:
        garantir_patch_mempalace()
        from mempalace.palace import get_collection
        from mempalace.ids import make_drawer_id_from_chunk
    except Exception as e:
        return f"falha ao importar mempalace: {e}"
    palace_path, wing, source_file, erro = _contexto_vetor(titulo)
    if erro:
        return erro
    drawer_id = make_drawer_id_from_chunk(wing, ROOM_NOTAS, source_file, 0)

    def _trabalho():
        col = get_collection(palace_path, create=False)
        col.delete(ids=[drawer_id])
    return _executar_no_vetor(_trabalho, "timeout ao remover do vetor")

def excluir_memoria_do_vetor(titulo):
    """Remove a drawer do mempalace correspondente a uma nota de knowledge.

    O drawer_id segue exatamente a mesma formula de add_drawer (miner.py),
    que usa source_file + chunk_index. Como as notas de ai_memory sao salvas
    com chunk_index=0, recalculamos o id e deletamos apenas essa drawer.
    Se o vetor estiver ocupado, a exclusao entra na fila em vez de disputar
    o lock; e a fila e aplicada quando a mineracao terminar.
    """
    ocupacao = _ocupacao_atual()
    if ocupacao:
        _enfileirar_no_vetor("excluir", titulo)
        return f"adiado (vetor ocupado com {ocupacao})"
    return _excluir_do_vetor(titulo)

def preaquecer_mempalace():
    """Abre (ou cria) o ChromaDB em background no startup para a 1ª busca não dar timeout.

    A primeira abertura do PersistentClient carrega índices HNSW e é lenta.
    Sem pré-aquecimento, essa abertura acontece dentro da primeira busca
    semântica (que disputa o memoria_lock com o espelhamento de notas),
    estourando o timeout e degradando para "sem contexto". Aquecendo no
    startup, o client já fica cacheado e a primeira interação é rápida.

    create=True recria o palace e a collection 'mempalace_drawers' quando o
    diretório do mempalace foi apagado: sem isso, toda busca falha com
    "No palace found" até a primeira gravação, e a interface perde o contexto
    semântico.

    Abrir o client não chega: a materialização do índice HNSW só acontece na
    PRIMEIRA search_memories (medido a frio: 2,94s; quente: 0,5s). Só abrir a
    collection deixava esse custo para a primeira rodada, que estourava o
    timeout e caía no fallback textual. Aqui corre uma busca de aquecimento em
    background, para a primeira busca real já encontrar o índice quente.
    """
    def _trabalho():
        try:
            garantir_patch_mempalace()
            from mempalace.palace import get_collection
            from mempalace.searcher import search_memories
            palace_path = os.path.expanduser("~/.mempalace/palace")
            get_collection(palace_path, create=True)
            with memoria_lock:
                search_memories(
                    query="aquecimento do indice",
                    palace_path=palace_path,
                    wing=None,
                    n_results=1,
                )
        except Exception:
            pass

    threading.Thread(target=_trabalho, daemon=True).start()

def espelhar_notas_existentes():
    global _backfill_ai_memory_executado
    if _backfill_ai_memory_executado:
        return
    _backfill_ai_memory_executado = True
    pasta = caminho_estado_projeto("knowledge")
    if not os.path.isdir(pasta):
        return
    try:
        nomes = [f for f in os.listdir(pasta) if f.endswith(".md")]
    except OSError:
        return

    def _trabalho():
        for nome in nomes:
            titulo = nome[:-3]
            try:
                with open(os.path.join(pasta, nome), "r", encoding="utf-8") as f:
                    conteudo = f.read()
            except Exception:
                continue
            salvar_memoria_no_vetor(titulo, conteudo)

    threading.Thread(target=_trabalho, daemon=True).start()

def minerar_em_segundo_plano(pasta_chats, wing_atual):
    """Roda o minerador do mempalace em background, serializado.

    O minerador anteriormente rodava como subprocess separado (python -m
    mempalace mine). Isso abria um segundo PersistentClient no MESMO
    chroma.sqlite3 que o Flask ja mantinha aberto, e dois processos
    escrevendo/lendo o mesmo banco SQLite simultaneamente causavam crash
    nativo no binding Rust do ChromaDB (0xC0000005 / access violation).

    Agora a mineracao roda no proprio processo Flask, reutilizando o
    PersistentClient cacheado pelo patch e protegida pelo memoria_lock,
    que serializa com a busca semantica e a gravacao de memorias.

    Enquanto corre, o vetor fica marcado como OCUPADO: e o que impede uma tool
    de memoria de vir escrever por cima da mineracao (era assim que o banco se
    corrompia). A busca semantica usa o evento mineracao_em_andamento, que a
    dispensa antes sequer de tentar o lock.
    """
    garantir_patch_mempalace()
    from mempalace.convo_miner import mine_convos

    palace_path = os.path.expanduser("~/.mempalace/palace")
    mineracao_em_andamento.set()
    marca = _marcar_ocupacao("minerador de memorias")
    try:
        with memoria_lock:
            mine_convos(
                convo_dir=pasta_chats,
                palace_path=palace_path,
                wing=wing_atual,
                agent="axio",
            )
    except Exception as e:
        print(f"[miner] falha ao minerar conversas: {e}")
    finally:
        mineracao_em_andamento.clear()
        _limpar_ocupacao(marca)
        threading.Thread(target=esvaziar_fila_do_vetor, daemon=True).start()

def _filtrar_por_relevancia(data):
    if not data or "results" not in data:
        return data
    data = dict(data)
    hits = data.get("results") or []
    data["results"] = [h for h in hits if h.get("similarity", 0) >= MIN_SIMILARIDADE_MEMORIA]
    return data

def buscar_memorias_com_timeout(query, palace_path, wing, n_results=5, timeout=8.0, room=None):
    """Roda search_memories com timeout para o ChromaDB nunca congelar a UI.

    O teto e 8s porque a PRIMEIRA busca do processo paga a materializacao do
    indice HNSW: medido a frio num palace de 150 MB, 2,94s; quente, ~0,5s.
    Com o teto antigo de 2,5s a primeira busca de cada arranque estourava
    SEMPRE, caia no fallback textual e a memoria da rodada vinha sem rotulo e
    sem passar pelo palace. preaquecer_mempalace aquece o indice no arranque;
    este teto e a rede de seguranca para o caso de o primeiro acesso real
    acontecer antes de o aquecimento terminar.

    `room` restringe a busca a um room e e o que separa as notas curadas das
    conversas mineradas: contadas no palace real, as notas sao 111 drawers
    (room ai_memory) contra 36.715 de transcricoes, repartidas pelos rooms
    tematicos do minerador (technical, planning, problems, general,
    architecture). A proporcao e de 331x, nao os 13x que a contagem de
    ficheiros sugere - por isso a busca sem filtro devolve quase so historico e
    as notas tem de ser pedidas explicitamente. O where do room tem o mesmo
    comportamento do wing, incluindo o fallback para busca sem filtro nos
    palaces antigos (issue #1035).

    O ChromaDB (PersistentClient) pode travar ao abrir um palace cujo
    chroma.sqlite3 ficou com lock pendente de um processo anterior morto de
    forma abrupta (ex.: minerador orfao apos fechar o app). Como a busca roda
    dentro da thread do loop de IA, um hang aqui congela a interface. Com
    timeout, degradamos para "sem contexto" e seguimos respondendo.

    Palaces antigos (construidos em chromadb 0.6.x e lidos por 1.5.x) quebram
    em consultas FILTRADAS por wing/room com "Error finding id" (issue #1035
    do MemPalace). Nesses casos, fazemos fallback para uma busca SEM filtro,
    que continua funcionando no indice HNSW antigo. Assim nao perdemos TODO o
    contexto de memoria por causa de um indice desatualizado; a filtragem fina
    pode ser recuperada depois com 'mempalace repair'.
    """
    if mineracao_em_andamento.is_set():
        return {"error": "minerador de memórias em andamento; contexto semântico indisponível nesta resposta"}

    def _executar(w):
        resultado = {}

        def _trabalho():
            try:
                garantir_patch_mempalace()
                from mempalace.searcher import search_memories
                with memoria_lock:
                    data = search_memories(
                        query=query,
                        palace_path=palace_path,
                        wing=w,
                        room=room,
                        n_results=n_results,
                    )
                    resultado["data"] = _filtrar_por_relevancia(data)
            except Exception as e:
                resultado["error"] = str(e)

        t = threading.Thread(target=_trabalho, daemon=True)
        t.start()
        t.join(timeout)

        if t.is_alive():
            return None, "timeout ao acessar banco de memorias"
        if "error" in resultado:
            return None, resultado["error"]
        return resultado.get("data"), None

    def _com_erro(data):
        return not data or data.get("error")

    data, erro = _executar(wing)
    if not erro and not _com_erro(data):
        return data

    if wing:
        data_sem_filtro, erro_sem_filtro = _executar(None)
        if not erro_sem_filtro and not _com_erro(data_sem_filtro):
            return data_sem_filtro
        primeiro = erro or (data or {}).get("error") or "erro desconhecido"
        segundo = erro_sem_filtro or (data_sem_filtro or {}).get("error") or "erro desconhecido"
        return {"error": f"{primeiro} | fallback sem wing: {segundo}"}

    return {"error": erro or (data or {}).get("error") or "erro desconhecido"}

def _basenames_fontes():
    """Nomes de arquivo existentes sob .axio/chats e .axio/knowledge, RECURSIVO.

    A busca tem de ser recursiva: os logs de sessao vivem em
    .axio/chats/session_logs/, uma subpasta. Checar apenas a raiz marcava
    todos esses logs como orfaos - um falso positivo que apontava dados VIVOS
    para exclusao. O conjunto e montado uma vez por varredura para a checagem
    ficar O(1) por drawer (ha mais de 100k drawers).
    """
    nomes = set()
    for base in (caminho_estado_projeto("chats"), garantir_pasta_knowledge()):
        if base and os.path.isdir(base):
            for _raiz, _dirs, arquivos in os.walk(base):
                nomes.update(arquivos)
    return nomes

def _source_file_existe(sf, basenames=None):
    """Indica se o arquivo de origem de uma drawer ainda existe.

    O source_file pode estar gravado com o caminho absoluto antigo (caso o
    projeto tenha sido movido de pasta). Nesse caso os.path.exists(sf) falha
    mesmo o arquivo existindo; reencontramos pelo basename em QUALQUER
    subpasta de .axio/chats e .axio/knowledge. So e orfa quando tanto o
    caminho exato como o basename em qualquer subpasta falham.
    """
    if not sf:
        return False
    if os.path.exists(sf):
        return True
    nome = os.path.basename(sf.replace("\\", "/"))
    if not nome:
        return False
    if basenames is None:
        basenames = _basenames_fontes()
    return nome in basenames

def _abrir_collection(palace_path):
    """Abre (ou reaproveita) a collection 'mempalace_drawers' do palace.

    Ponto UNICO de acesso ao vetor para as operacoes de manutencao: garante o
    patch do mempalace, reutiliza o PersistentClient cacheado (abrir um segundo
    cliente sobre o mesmo chroma.sqlite3 causa lock/crash nativo) e devolve o
    par (client, collection). Deve ser chamada com o memoria_lock ja adquirido,
    para que a operacao inteira fique serializada.
    """
    try:
        garantir_patch_mempalace()
        from src.backend.memory.mempalace_patch import abrir_client
    except Exception as e:
        raise RuntimeError(f"falha ao importar mempalace: {e}") from e
    client = abrir_client(palace_path)
    return client, client.get_collection("mempalace_drawers")

def _iterar_drawers(col, incluir, tamanho=5000):
    """Percorre a collection em lotes, devolvendo (processados, total, lote).

    Ponto UNICO de paginacao do vetor, reutilizado pela varredura, pela limpeza
    e pelo reparo. Ler em lotes evita carregar as 100k drawers de uma vez, o que
    estouraria a memoria do processo Flask.
    """
    total = col.count()
    offset = 0
    while offset < total:
        lote = col.get(limit=tamanho, offset=offset, include=incluir)
        offset += tamanho
        yield min(offset, total), total, lote

def _ids_e_metadados(palace_path, col, collection_name="mempalace_drawers"):
    """ids e metadados de TODAS as drawers, por SQL direto sempre que possivel.

    Caminho rapido (mempalace >= 3.8, PR #2314): sqlite_list_id_metadata le a
    tabela embedding_metadata do chroma.sqlite3 e devolve os pares sem abrir o
    indice HNSW. O ganho foi medido pelo proprio release numa palace de 165k
    drawers: 2.31s e 1148 MB -> 0.01s e 86 MB. A varredura, a limpeza de orfaos
    e a limpeza de logs descartados consultam SO metadados, logo carregar o
    indice vetorial inteiro era custo puro - era isso que podia estourar o
    VARREDURA_TIMEOUT e inflar a RAM do processo Flask sem necessidade.

    Caminho de recuo: se o SQLite nao puder ser lido (outro backend, banco com
    problema) a funcao devolve None e paginamos pela collection, como antes. O
    reparo NAO passa por aqui de proposito: ele re-embeda os DOCUMENTOS, que
    este caminho evita materializar (o texto do palace inteiro sao centenas de
    MB numa palace grande).
    """
    try:
        from mempalace.backends.chroma import sqlite_list_id_metadata
        via_sql = sqlite_list_id_metadata(palace_path, collection_name)
    except Exception:
        via_sql = None
    if via_sql is not None:
        ids, metas = via_sql
        return list(ids), list(metas)
    ids = []
    metas = []
    for feito, total, lote in _iterar_drawers(col, ["metadatas"]):
        ids.extend(lote["ids"])
        metas.extend(lote["metadatas"])
        _marcar_progresso(f"{feito}/{total} drawers")
    return ids, metas

def _marcar_progresso(texto):
    """Grava o progresso da operacao vetorial em curso (visivel em acao='status').

    A tool perde o resultado quando estoura o timeout, mas a marca de ocupacao
    continua em RAM: e ela que permite acompanhar a operacao ate ao fim.
    """
    marca = estado.get("vetor_ocupado")
    if marca:
        marca["progresso"] = texto

def _ocupacao_atual():
    """Descricao da operacao vetorial pesada em curso, ou '' se o vetor estiver livre."""
    marca = estado.get("vetor_ocupado") or {}
    if not marca:
        return ""
    tipo = marca.get("tipo", "operacao")
    try:
        decorrido = int(time.time() - marca.get("inicio", time.time()))
    except (TypeError, ValueError):
        decorrido = 0
    progresso = marca.get("progresso")
    sufixo = f", {progresso}" if progresso else ""
    return f"{tipo} (em curso ha {decorrido}s{sufixo})"

def _bloqueio_vetor_ocupado():
    """Texto de recusa quando ja ha uma operacao pesada a correr, senao ''.

    Duas operacoes simultaneas disputariam o mesmo chroma.sqlite3; pior: se a
    primeira tiver estourado o timeout e continuar em background, a segunda
    ficaria presa no memoria_lock sem forma de sair ate a primeira terminar.
    """
    atual = _ocupacao_atual()
    if not atual:
        return ""
    return (f"ERRO: o vetor ja esta ocupado com {atual}. Aguarde terminar "
            "(consulte acao='status'); duas operacoes ao mesmo tempo podem travar o banco.")

def vetor_status():
    """Estado atual do vetor: livre ou operacao pesada em curso, com a duracao."""
    atual = _ocupacao_atual()
    if not atual:
        return "vetor livre (nenhuma operacao pesada em curso)."
    return (f"vetor OCUPADO: {atual}. Nao feche o app nem reinicie o backend antes de terminar, "
            "senao a operacao fica a meio.")

def varrer_memoria_vetor():
    """Lista todas as drawers do palace e cruza com os arquivos de origem.

    Retorna um diagnóstico legível: total de drawers, contagem por room e as
    drawers órfãs (cujo source_file não existe mais no disco), que são as
    candidatas seguras a exclusão por terem ficado obsoletas.
    """
    bloqueio = _bloqueio_vetor_ocupado()
    if bloqueio:
        return bloqueio
    palace_path = os.path.expanduser("~/.mempalace/palace")
    if not os.path.isdir(palace_path):
        return "palace do mempalace não encontrado"

    emit_event("status", message="Varredura vetorial iniciada...")

    def _trabalho(r):
        _client, col = _abrir_collection(palace_path)
        ids, metas = _ids_e_metadados(palace_path, col)
        r["total"] = len(ids)
        r["ids"] = ids
        r["metas"] = metas

    resultado, expirou = _rodar_com_timeout(_trabalho, VARREDURA_TIMEOUT, ocupacao="varredura")
    if expirou:
        emit_event("status", message="Varredura vetorial: ainda em background...")
        return (f"timeout ao varrer o vetor ({int(VARREDURA_TIMEOUT)}s). O vetor pode ter muitos drawers - "
                "rode a limpeza de orfaos (acao='limpar_orfaos') para reduzir o volume.")
    if "erro" in resultado:
        return f"erro ao varrer: {resultado['erro']}"
    ids = resultado["ids"]
    metas = resultado["metas"]
    basenames = _basenames_fontes()
    wing_atual = wing_da_pasta(estado.get("pasta_raiz")) or "general"
    por_room = {}
    por_wing = {}
    orfas = []
    orfas_por_wing = {}
    orfas_por_room = {}
    for i, did in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        if not meta:
            continue
        room = meta.get("room", "?")
        wing = meta.get("wing", "?")
        por_room[room] = por_room.get(room, 0) + 1
        por_wing[wing] = por_wing.get(wing, 0) + 1
        sf = meta.get("source_file", "")
        if sf and not _room_protegida(room) and not _source_file_existe(sf, basenames):
            orfas.append((did, room, sf))
            orfas_por_wing[wing] = orfas_por_wing.get(wing, 0) + 1
            orfas_por_room[room] = orfas_por_room.get(room, 0) + 1
    linhas = [f"Total de drawers: {len(ids)}"]
    if not estado.get("pasta_raiz"):
        linhas.append("AVISO: sem pasta de projeto selecionada o detector nao ve .axio/chats/.axio/knowledge, "
                      "por isso a contagem de orfas abaixo e INVALIDA (falso positivo em massa). "
                      "NAO rode limpar_orfaos neste estado.")
    if por_room:
        linhas.append("Por room: " + ", ".join(f"{r}={c}" for r, c in sorted(por_room.items(), key=lambda x: -x[1])))
    if por_wing:
        linhas.append("Por projeto (wing): " + ", ".join(f"{w}={c}" for w, c in sorted(por_wing.items(), key=lambda x: -x[1])))
    linhas.append(f"Órfãs removíveis (source_file fora de .axio/chats e .axio/knowledge): {len(orfas)}")
    if orfas_por_room:
        linhas.append("  Órfãs por room: " + ", ".join(f"{r}={c}" for r, c in sorted(orfas_por_room.items(), key=lambda x: -x[1])))
    linhas.append("  (rooms " + ", ".join(sorted(ROOMS_PROTEGIDAS)) + " nunca sao removidas pela limpeza)")
    if orfas_por_wing:
        linhas.append("  Órfãs por projeto: " + ", ".join(f"{w}={c}" for w, c in sorted(orfas_por_wing.items(), key=lambda x: -x[1])))
        outros = [w for w in orfas_por_wing if w != wing_atual]
        if outros:
            linhas.append(f"  ATENCAO: a limpeza tambem afeta projetos alem do atual (atual: {wing_atual}): {', '.join(outros)}")
    for did, room, sf in orfas[:80]:
        linhas.append(f"  - [{room}] {os.path.basename(sf)}  id={did}")
    if len(orfas) > 80:
        linhas.append(f"  ... e mais {len(orfas) - 80} órfãs omitidas")
    return "\n".join(linhas)

def limpar_memoria_orfaos(limite_proporcao=None):
    """Remove do vetor as drawers orfas (cujo source_file ja nao existe no disco).

    As drawers orfas referem chats/knowledge antigos ja apagados; remove-las
    liberta espaco e acelera tanto as buscas como a propria varredura. Reutiliza
    o PersistentClient cacheado (mesmo memoria_lock das outras operacoes do
    vetor) para nao abrir um segundo processo sobre o chroma.sqlite3.

    limite_proporcao e a guarda de seguranca: se a fracao marcada como orfa
    ultrapassar esse valor, NADA e apagado (uma proporcao tao alta costuma ser
    bug no detector, nao lixo real). Passe um valor explicito (ex: 1.0) apenas
    depois de CONFERIR os nomes em acao='varredura' - a exclusao e irreversivel
    e nao tem undo.
    """
    bloqueio = _bloqueio_vetor_ocupado()
    if bloqueio:
        return bloqueio
    limite = PROPORCAO_MAX_ORFAOS
    if limite_proporcao is not None:
        try:
            limite = float(limite_proporcao)
        except (TypeError, ValueError):
            return f"ERRO: limite_orfaos invalido ('{limite_proporcao}'). Use um numero entre 0 e 1."
        if not 0 < limite <= 1:
            return f"ERRO: limite_orfaos deve estar entre 0 e 1 (recebido {limite})."
    if not estado.get("pasta_raiz"):
        return ("ERRO: nenhuma pasta de projeto esta selecionada. Sem ela o detector nao ve os arquivos "
                "em .axio/chats e .axio/knowledge e marcaria milhares de drawers VALIDAS como orfas "
                "(o caminho gravado no vetor e absoluto e nao bate). Selecione a pasta do projeto e repita.")
    palace_path = os.path.expanduser("~/.mempalace/palace")
    if not os.path.isdir(palace_path):
        return "palace do mempalace nao encontrado"

    emit_event("status", message="Limpeza de orfaos iniciada...")

    def _trabalho(r):
        _client, col = _abrir_collection(palace_path)
        basenames = _basenames_fontes()
        ids, metas = _ids_e_metadados(palace_path, col)
        total = len(ids)
        orfaos = []
        for did, meta in zip(ids, metas):
            meta = meta or {}
            sf = meta.get("source_file", "")
            if sf and not _room_protegida(meta.get("room")) and not _source_file_existe(sf, basenames):
                orfaos.append(did)
        _marcar_progresso(f"fase 1/2 deteccao concluida, {len(orfaos)} orfaos de {total}")
        emit_event("status", message=f"Limpeza vetorial: {total} drawers varridas, {len(orfaos)} orfaos...")
        if total > 100 and len(orfaos) > total * limite:
            r["abortado"] = (
                f"deteccao suspeita - {len(orfaos)} de {total} drawers ({len(orfaos) / total:.0%}) "
                f"marcadas como orfas, acima do limite de {limite:.0%}. Uma proporcao tao alta "
                "costuma ser bug no detector, nao lixo real, por isso NADA foi apagado. Confirme os "
                "nomes em acao='varredura' e, se forem mesmo lixo, repita a limpeza com "
                "limite_orfaos=1.0 para autorizar."
            )
            return
        removidos = 0
        for i in range(0, len(orfaos), 1000):
            lote = orfaos[i:i + 1000]
            col.delete(ids=lote)
            removidos += len(lote)
            _marcar_progresso(f"fase 2/2 exclusao {removidos}/{len(orfaos)} drawers")
            emit_event("status", message=f"Limpeza vetorial: removidos {removidos}/{len(orfaos)} orfaos...")
        r["total"] = total
        r["removidos"] = removidos

    resultado, expirou = _rodar_com_timeout(_trabalho, VARREDURA_TIMEOUT, ocupacao="limpeza de orfaos")
    if expirou:
        return (f"timeout na limpeza (>{int(VARREDURA_TIMEOUT)}s). O processo continua em background "
                "- NAO feche o app; use acao='status' para acompanhar ate terminar.")
    if "erro" in resultado:
        return f"erro na limpeza: {resultado['erro']}"
    if "abortado" in resultado:
        return f"ABORTADO: {resultado['abortado']}"
    return f"SUCESSO: {resultado.get('removidos', 0)} drawers orfas removidas (de {resultado.get('total', 0)} no total)."

def limpar_drawers_de_sources(nomes):
    """Remove do vetor as drawers mineradas de arquivos ja descartados do disco.

    Chamada quando o historico de sessoes descarta logs antigos (prune): sem
    isto, as drawers daqueles logs ficariam orfas no banco a poluir a busca
    semantica com trabalho antigo. Recebe NOMES de arquivo, nao caminhos: o
    source_file gravado guarda o caminho absoluto de quando o projeto foi
    minerado, que deixa de valer se o projeto for movido de pasta.
    """
    alvos = {os.path.basename(n.replace("\\", "/")) for n in (nomes or []) if n}
    if not alvos:
        return "nada a remover"
    palace_path = os.path.expanduser("~/.mempalace/palace")
    if not os.path.isdir(palace_path):
        return "palace do mempalace nao encontrado"
    def _trabalho(r):
        _client, col = _abrir_collection(palace_path)
        ids_lidos, metas = _ids_e_metadados(palace_path, col)
        ids = []
        for did, meta in zip(ids_lidos, metas):
            meta = meta or {}
            sf = meta.get("source_file", "")
            if sf and not _room_protegida(meta.get("room")) and os.path.basename(sf.replace("\\", "/")) in alvos:
                ids.append(did)
        for i in range(0, len(ids), 1000):
            col.delete(ids=ids[i:i + 1000])
        r["removidos"] = len(ids)

    resultado, expirou = _rodar_com_timeout(_trabalho, VARREDURA_TIMEOUT)
    if expirou:
        return "limpeza das drawers de logs descartados continua em background"
    if "erro" in resultado:
        return f"erro ao limpar drawers de logs descartados: {resultado['erro']}"
    return f"{resultado.get('removidos', 0)} drawers de logs descartados removidas do vetor."

def reparar_memoria_vetor():
    """Reconstrói o índice HNSW do palace a partir dos metadados já gravados.

    Equivalente ao 'mempalace repair', porém roda DENTRO do processo Flask,
    reutilizando o PersistentClient cacheado pelo patch. Isso evita o crash
    nativo (0xC0000005) que ocorre quando um segundo processo abre o mesmo
    chroma.sqlite3 simultaneamente. O índice é reconstruído ao deletar e
    recriar a collection, re-adicionando as drawers extraídas em memória.
    """
    palace_path = os.path.expanduser("~/.mempalace/palace")
    if not os.path.isdir(palace_path):
        return "palace do mempalace não encontrado"

    bloqueio = _bloqueio_vetor_ocupado()
    if bloqueio:
        return bloqueio
    emit_event("status", message="Reparo do indice vetorial iniciado...")

    def _trabalho(r):
        print("[memoria] repair iniciado: lendo drawers existentes...")
        client, col = _abrir_collection(palace_path)
        total = col.count()
        print(f"[memoria] repair: {total} drawers encontradas")
        if total == 0:
            r["msg"] = "nada a reparar (0 drawers)"
            print("[memoria] repair: nada a reparar (0 drawers)")
            return
        batch_size = 5000
        all_ids = []
        all_docs = []
        all_metas = []
        for _feito, _total, lote in _iterar_drawers(col, ["documents", "metadatas"]):
            all_ids.extend(lote["ids"])
            all_docs.extend(lote["documents"])
            all_metas.extend(lote["metadatas"])
        backup_path = palace_path + ".backup"
        if os.path.exists(backup_path):
            shutil.rmtree(backup_path)
        shutil.copytree(palace_path, backup_path)
        client.delete_collection("mempalace_drawers")
        nova = client.create_collection("mempalace_drawers", metadata={"hnsw:space": "cosine"})
        filed = 0
        for i in range(0, len(all_ids), batch_size):
            b_ids = all_ids[i:i + batch_size]
            b_docs = all_docs[i:i + batch_size]
            b_metas = all_metas[i:i + batch_size]
            nova.add(documents=b_docs, ids=b_ids, metadatas=b_metas)
            filed += len(b_ids)
        r["msg"] = f"repair concluído: {filed} drawers reconstruídas. backup em {backup_path}"
        print(f"[memoria] {r['msg']}")

    resultado, expirou = _rodar_com_timeout(_trabalho, 180.0, ocupacao="reparo do indice")
    if expirou:
        print("[memoria] repair: timeout de 180s, ainda em background")
        return "repair em andamento em background (timeout de 180s atingido)"
    if "erro" in resultado:
        print(f"[memoria] erro ao reparar: {resultado['erro']}")
        return f"erro ao reparar: {resultado['erro']}"
    print("[memoria] repair finalizado")
    return resultado.get("msg", "repair concluído")

def compactar_memoria_vetor():
    """Compacta o chroma.sqlite3, devolvendo ao disco o espaco das drawers apagadas.

    O SQLite marca as paginas dos dados apagados como livres mas NAO encolhe o
    ficheiro; so o VACUUM reconstroi o banco num tamanho minimo. Sem isto, um
    chroma.sqlite3 de varios GB continua exatamente do mesmo tamanho depois de a
    limpeza remover dezenas de milhares de drawers. O VACUUM precisa de ate 2x o
    tamanho do ficheiro em espaco livre e de lock de escrita exclusivo, por isso
    roda em background sob memoria_lock, com progresso visivel em acao='status'.
    """
    bloqueio = _bloqueio_vetor_ocupado()
    if bloqueio:
        return bloqueio
    palace_path = os.path.expanduser("~/.mempalace/palace")
    db_path = os.path.join(palace_path, "chroma.sqlite3")
    if not os.path.isfile(db_path):
        return "chroma.sqlite3 nao encontrado"
    antes = os.path.getsize(db_path)
    emit_event("status", message="Compactando o banco vetorial (VACUUM)...")

    def _trabalho(r):
        con = sqlite3.connect(db_path, timeout=30.0)
        try:
            con.execute("VACUUM")
            con.commit()
        finally:
            con.close()
        r["depois"] = os.path.getsize(db_path)

    resultado, expirou = _rodar_com_timeout(_trabalho, 900.0, ocupacao="compactacao do banco")
    if expirou:
        return ("compactacao em andamento em background (VACUUM de um banco grande). "
                "NAO feche o app; acompanhe com acao='status' ate concluir.")
    if "erro" in resultado:
        print(f"[memoria] erro na compactacao: {resultado['erro']}")
        return (f"erro ao compactar: {resultado['erro']}. Se a mensagem for 'database is locked', "
                "feche o app e rode o VACUUM com ele parado.")
    depois = resultado.get("depois", antes)
    mb = 1048576
    return (f"banco compactado: {antes / mb:.0f} MB -> {depois / mb:.0f} MB "
            f"({(antes - depois) / mb:.0f} MB devolvidos ao disco).")

