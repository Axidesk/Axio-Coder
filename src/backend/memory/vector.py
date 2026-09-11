import hashlib
import os
import re
import threading

from src.backend.state import estado, memoria_lock, mineracao_em_andamento, caminho_estado_projeto
from src.backend.memory.store import garantir_pasta_knowledge, nome_arquivo_seguro

_patch_mempalace_aplicado = False
_backfill_ai_memory_executado = False

MIN_SIMILARIDADE_MEMORIA = 0.45

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
    """Devolve (palace_path, wing, source_file, erro) comuns as operacoes do vetor."""
    palace_path = os.path.expanduser("~/.mempalace/palace")
    if not os.path.isdir(palace_path):
        return None, None, None, "palace do mempalace não encontrado"
    wing = wing_da_pasta(estado.get("pasta_raiz")) or "general"
    source_file = os.path.join(garantir_pasta_knowledge(), f"{nome_arquivo_seguro(titulo)}.md")
    return palace_path, wing, source_file, None

def _executar_no_vetor(fn, timeout_msg):
    """Roda `fn` sob memoria_lock numa thread com timeout, devolvendo 'ok' ou erro."""
    resultado = {}
    def _trabalho():
        try:
            with memoria_lock:
                fn()
            resultado["ok"] = True
        except Exception as e:
            resultado["erro"] = str(e)
    t = threading.Thread(target=_trabalho, daemon=True)
    t.start()
    t.join(6.0)
    if t.is_alive():
        return timeout_msg
    if "erro" in resultado:
        return f"erro: {resultado['erro']}"
    return "ok"

def salvar_memoria_no_vetor(titulo, conteudo):
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
        add_drawer(col, wing, "ai_memory", conteudo, source_file, 0, "axio")
    return _executar_no_vetor(_trabalho, "timeout ao gravar no vetor")

def excluir_memoria_do_vetor(titulo):
    """Remove a drawer do mempalace correspondente a uma nota de knowledge.

    O drawer_id segue exatamente a mesma fórmula de add_drawer (miner.py),
    que usa source_file + chunk_index. Como as notas de ai_memory são salvas
    com chunk_index=0, recalculamos o id e deletamos apenas essa drawer.
    """
    try:
        garantir_patch_mempalace()
        from mempalace.palace import get_collection
    except Exception as e:
        return f"falha ao importar mempalace: {e}"
    palace_path, wing, source_file, erro = _contexto_vetor(titulo)
    if erro:
        return erro
    drawer_id = f"drawer_{wing}_ai_memory_{hashlib.sha256((source_file + str(0)).encode()).hexdigest()[:24]}"

    def _trabalho():
        col = get_collection(palace_path, create=False)
        col.delete(ids=[drawer_id])
    return _executar_no_vetor(_trabalho, "timeout ao remover do vetor")

def preaquecer_mempalace():
    """Abre o ChromaDB em background no startup para a 1ª busca não dar timeout.

    A primeira abertura do PersistentClient carrega índices HNSW e é lenta.
    Sem pré-aquecimento, essa abertura acontece dentro da primeira busca
    semântica (que disputa o memoria_lock com o espelhamento de notas),
    estourando o timeout e degradando para "sem contexto". Aquecendo no
    startup, o client já fica cacheado e a primeira interação é rápida.
    """
    def _trabalho():
        try:
            garantir_patch_mempalace()
            from mempalace.palace import get_collection
            palace_path = os.path.expanduser("~/.mempalace/palace")
            if not os.path.isdir(palace_path):
                return
            get_collection(palace_path, create=False)
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
    """
    garantir_patch_mempalace()
    from mempalace.convo_miner import mine_convos

    palace_path = os.path.expanduser("~/.mempalace/palace")
    mineracao_em_andamento.set()
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

def _filtrar_por_relevancia(data):
    if not data or "results" not in data:
        return data
    data = dict(data)
    hits = data.get("results") or []
    data["results"] = [h for h in hits if h.get("similarity", 0) >= MIN_SIMILARIDADE_MEMORIA]
    return data

def buscar_memorias_com_timeout(query, palace_path, wing, n_results=5, timeout=2.5):
    """Roda search_memories com timeout para o ChromaDB nunca congelar a UI.

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

def _source_file_existe(sf):
    """Indica se o arquivo de origem de uma drawer ainda existe.

    O source_file pode estar gravado com o caminho absoluto antigo (caso o
    projeto tenha sido movido de pasta). Nesse caso os.path.exists(sf) falha
    mesmo o arquivo existindo; reencontramos pelo basename nos diretórios
    onde as fontes vivem (.axio/chats e .axio/knowledge) para não gerar
    falso positivo de órfã a cada mudança de raiz.
    """
    if not sf:
        return False
    if os.path.exists(sf):
        return True
    nome = os.path.basename(sf)
    if not nome:
        return False
    for base in (caminho_estado_projeto("chats"), garantir_pasta_knowledge()):
        if base and os.path.exists(os.path.join(base, nome)):
            return True
    return False

def varrer_memoria_vetor():
    """Lista todas as drawers do palace e cruza com os arquivos de origem.

    Retorna um diagnóstico legível: total de drawers, contagem por room e as
    drawers órfãs (cujo source_file não existe mais no disco), que são as
    candidatas seguras a exclusão por terem ficado obsoletas.
    """
    try:
        garantir_patch_mempalace()
        from src.backend.memory.mempalace_patch import _client_cache, _client_lock
        import chromadb
    except Exception as e:
        return f"falha ao importar mempalace: {e}"
    palace_path = os.path.expanduser("~/.mempalace/palace")
    if not os.path.isdir(palace_path):
        return "palace do mempalace não encontrado"

    resultado = {}

    def _trabalho():
        try:
            with memoria_lock:
                with _client_lock:
                    client = _client_cache.get(palace_path)
                    if client is None:
                        client = chromadb.PersistentClient(path=palace_path)
                        _client_cache[palace_path] = client
                    col = client.get_collection("mempalace_drawers")
                    total = col.count()
                    batch_size = 2000
                    ids = []
                    metas = []
                    offset = 0
                    while offset < total:
                        batch = col.get(limit=batch_size, offset=offset, include=["metadatas"])
                        ids.extend(batch["ids"])
                        metas.extend(batch["metadatas"])
                        offset += batch_size
                    resultado["total"] = total
                    resultado["ids"] = ids
                    resultado["metas"] = metas
        except Exception as e:
            resultado["erro"] = str(e)

    t = threading.Thread(target=_trabalho, daemon=True)
    t.start()
    t.join(30.0)
    if t.is_alive():
        return "timeout ao varrer o vetor"
    if "erro" in resultado:
        return f"erro ao varrer: {resultado['erro']}"
    ids = resultado["ids"]
    metas = resultado["metas"]
    por_room = {}
    orfas = []
    for i, did in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        if not meta:
            continue
        room = meta.get("room", "?")
        por_room[room] = por_room.get(room, 0) + 1
        sf = meta.get("source_file", "")
        if sf and not _source_file_existe(sf):
            orfas.append((did, room, sf))
    linhas = [f"Total de drawers: {len(ids)}"]
    if por_room:
        linhas.append("Por room: " + ", ".join(f"{r}={c}" for r, c in sorted(por_room.items(), key=lambda x: -x[1])))
    linhas.append(f"Órfãs (source_file não existe mais): {len(orfas)}")
    for did, room, sf in orfas[:80]:
        linhas.append(f"  - [{room}] {os.path.basename(sf)}  id={did}")
    if len(orfas) > 80:
        linhas.append(f"  ... e mais {len(orfas) - 80} órfãs omitidas")
    return "\n".join(linhas)

def reparar_memoria_vetor():
    """Reconstrói o índice HNSW do palace a partir dos metadados já gravados.

    Equivalente ao 'mempalace repair', porém roda DENTRO do processo Flask,
    reutilizando o PersistentClient cacheado pelo patch. Isso evita o crash
    nativo (0xC0000005) que ocorre quando um segundo processo abre o mesmo
    chroma.sqlite3 simultaneamente. O índice é reconstruído ao deletar e
    recriar a collection, re-adicionando as drawers extraídas em memória.
    """
    try:
        garantir_patch_mempalace()
        from src.backend.memory.mempalace_patch import _client_cache, _client_lock
        import shutil
    except Exception as e:
        return f"falha ao importar: {e}"
    palace_path = os.path.expanduser("~/.mempalace/palace")
    if not os.path.isdir(palace_path):
        return "palace do mempalace não encontrado"

    resultado = {}

    def _trabalho():
        print("[memoria] repair iniciado: lendo drawers existentes...")
        try:
            with memoria_lock:
                with _client_lock:
                    client = _client_cache.get(palace_path)
                    if client is None:
                        import chromadb
                        client = chromadb.PersistentClient(path=palace_path)
                        _client_cache[palace_path] = client
                    col = client.get_collection("mempalace_drawers")
                    total = col.count()
                    print(f"[memoria] repair: {total} drawers encontradas")
                    if total == 0:
                        resultado["msg"] = "nada a reparar (0 drawers)"
                        print("[memoria] repair: nada a reparar (0 drawers)")
                        return
                    batch_size = 5000
                    all_ids = []
                    all_docs = []
                    all_metas = []
                    offset = 0
                    while offset < total:
                        batch = col.get(limit=batch_size, offset=offset, include=["documents", "metadatas"])
                        all_ids.extend(batch["ids"])
                        all_docs.extend(batch["documents"])
                        all_metas.extend(batch["metadatas"])
                        offset += batch_size
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
                    resultado["msg"] = f"repair concluído: {filed} drawers reconstruídas. backup em {backup_path}"
                    print(f"[memoria] {resultado['msg']}")
        except Exception as e:
            resultado["erro"] = str(e)
            print(f"[memoria] erro no repair: {e}")

    t = threading.Thread(target=_trabalho, daemon=True)
    t.start()
    t.join(180.0)
    if t.is_alive():
        print("[memoria] repair: timeout de 180s, ainda em background")
        return "repair em andamento em background (timeout de 180s atingido)"
    if "erro" in resultado:
        print(f"[memoria] erro ao reparar: {resultado['erro']}")
        return f"erro ao reparar: {resultado['erro']}"
    print("[memoria] repair finalizado")
    return resultado.get("msg", "repair concluído")

