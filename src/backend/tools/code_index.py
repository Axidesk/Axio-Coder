"""Indice semantico do codigo do projeto no palace do mempalace.

Segmenta cada ficheiro (por AST no Python, por tree-sitter no resto), grava os
trechos com os embeddings e responde a busca por similaridade. O manifesto do
indice (hash, mtime, tamanho) vive em .axio/code_index.json e e ele que torna a
indexacao incremental - nao se reindexa o que nao mudou. tool_indexar_codigo e
tool_buscar_codigo sao a porta do agente para este indice.
"""
import ast
import hashlib
import json
import os
import threading
import time

from src.backend.memory.mempalace_patch import abrir_client
from src.backend.memory.vector import garantir_patch_mempalace, wing_da_pasta
from src.backend.state import caminho_estado_projeto, emit_event, estado, memoria_lock
from src.backend.tools.projeto_comum import arquivos_de_codigo, caminho_relativo
from src.backend.tools.registry import register

TAMANHO_CHUNK = 1600
CHUNKER_VERSION = 2
_COLLECTION_CODIGO = "axio_code"

_lock_index = threading.Lock()
TIMEOUT_INDEXACAO = 12.0
_identidade_embedder = {"status": "nao verificada"}
_erro_colecao = {"motivo": ""}

def _wing():
    return wing_da_pasta(estado.get("pasta_raiz")) or "general"

def _palace_path():
    return os.path.expanduser("~/.mempalace/palace")

def _colecao_codigo(create=True):
    """A colecao de codigo e NOSSA: abre pelo cliente do ChromaDB, nao pelo mempalace.

    O mempalace 3.10 recusa qualquer nome que nao seja as duas colecoes que ele
    proprio le (mempalace_drawers, mempalace_closets) e levanta
    CollectionNameMismatchError - a axio_code nunca foi dele, e um indice de codigo
    do Axio com marca 'wing' por projeto, pesquisado so pelo buscar_codigo_semantico.
    O palace continua a ser aberto pela via do mempalace (mempalace_patch.abrir_client),
    que e quem aplica as migracoes do chromadb; o que deixou de passar por ele foi a
    POLITICA DE NOMES, nao o acesso ao ficheiro.
    """
    garantir_patch_mempalace()
    if not create and not os.path.isdir(_palace_path()):
        _erro_colecao["motivo"] = f"palace inexistente em {_palace_path()}"
        return None
    try:
        cliente = abrir_client(_palace_path())
        col = cliente.get_or_create_collection(_COLLECTION_CODIGO) if create else cliente.get_collection(_COLLECTION_CODIGO)
    except Exception as exc:
        _erro_colecao["motivo"] = f"{type(exc).__name__}: {exc}"
        return None
    _erro_colecao["motivo"] = ""
    if create:
        _identidade_embedder["status"] = _gravar_identidade_embedder(col)
    return col

def _gravar_identidade_embedder(col):
    """Grava no metadata da colecao qual embedder a serve, uma vez so.

    A identidade gravada converte a suposicao num facto registado: se o modelo de
    embedding mudar, o valor que ficou aqui denuncia-o em vez de a busca degradar
    em silencio. O metadata do chromadb e SUBSTITUIDO por inteiro no modify, nunca
    fundido - sem o {**col.metadata} isto apagaria as chaves que la estiverem.
    Devolve o que aconteceu em vez de engolir a falha; sai no audit da indexacao.
    """
    try:
        atual = col.metadata or {}
        if atual.get("embedder"):
            return "ja registada"
        col.modify(metadata={**atual, "embedder": _nome_do_embedder(col)})
        return "registada agora"
    except Exception as exc:
        return f"falhou: {type(exc).__name__}: {exc}"


def _nome_do_embedder(col):
    nome = ""
    try:
        configuracao = getattr(col, "configuration", None) or {}
        ef = configuracao.get("embedding_function") if hasattr(configuracao, "get") else None
        nome = type(ef).__name__ if ef else ""
    except Exception:
        nome = ""
    try:
        vetores = col.peek(limit=1).get("embeddings")
        if vetores is not None and len(vetores):
            return f"{nome}/{len(vetores[0])}".lstrip("/")
    except Exception:
        pass
    return nome or "desconhecido"

def _caminho_indice():
    return caminho_estado_projeto("code_index.json")

def _ler_indice_bruto():
    caminho = _caminho_indice()
    if not caminho or not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except Exception:
        return {}

def _carregar_indice():
    arquivos = _ler_indice_bruto().get("arquivos")
    return arquivos if isinstance(arquivos, dict) else {}

def _salvar_indice(indice, auditoria=None, colecao_id=""):
    caminho = _caminho_indice()
    if not caminho:
        return
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        payload = {"arquivos": indice, "atualizado_em": time.time()}
        if colecao_id:
            payload["colecao_id"] = colecao_id
        if auditoria:
            payload["ultima_indexacao"] = auditoria
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _colecao_foi_recriada(col, indice):
    """Deteta um palace apagado/recriado por baixo do cache de indexacao.

    O cache por hash (mtime/size/chunker_version) vive no PROJETO
    (.axio/code_index.json) mas os vetores vivem no palace do mempalace
    (~/.mempalace). Apagar ou reconstruir o palace nao toca no cache: ele
    continua a afirmar que os ficheiros estao indexados, o indexador salta-os
    todos e a busca semantica de codigo fica a servir em silencio apenas os
    ficheiros mexidos depois disso. Dois sinais denunciam-no: a colecao ganha
    um id novo quando e recriada, e o total de chunks cai abaixo do que o
    proprio cache promete.
    """
    guardado = _ler_indice_bruto().get("colecao_id")
    atual = getattr(col, "id", None) or getattr(col, "name", None)
    if guardado and atual and guardado != atual:
        return True
    prometidos = sum(int(info.get("chunks", 0) or 0) for info in indice.values())
    if not prometidos:
        return False
    try:
        return col.count() < prometidos
    except Exception:
        return False

def _chunkar_por_tamanho(conteudo):
    linhas = conteudo.splitlines()
    chunks = []
    atual = []
    inicio = 1
    tamanho = 0
    for i, linha in enumerate(linhas, 1):
        atual.append(linha)
        tamanho += len(linha) + 1
        if tamanho >= TAMANHO_CHUNK:
            chunks.append((inicio, "\n".join(atual)))
            atual = []
            inicio = i + 1
            tamanho = 0
    if atual:
        chunks.append((inicio, "\n".join(atual)))
    return chunks

def _agrupar_em_chunks(segmentos):
    """Agrupa segmentos (linha, texto) em blocos de ate TAMANHO_CHUNK caracteres."""
    chunks = []
    atual = []
    inicio = 1
    tamanho = 0
    for linha_no, seg in segmentos:
        if atual and tamanho + len(seg) > TAMANHO_CHUNK:
            chunks.append((inicio, "\n".join(atual)))
            atual = []
            inicio = linha_no
            tamanho = 0
        atual.append(seg)
        tamanho += len(seg) + 1
    if atual:
        chunks.append((inicio, "\n".join(atual)))
    return chunks

def _deletar_chunks_do_arquivo(col, rel):
    """Remove do vetor todos os chunks indexados de um arquivo (por source_file)."""
    try:
        with memoria_lock:
            existentes = col.get(where={"source_file": rel}, include=["metadatas"])
            ids = existentes.get("ids", []) if existentes else []
            if ids:
                col.delete(ids=ids)
    except Exception:
        pass

def _chunkar_python(conteudo):
    try:
        arvore = ast.parse(conteudo)
    except SyntaxError:
        return _chunkar_por_tamanho(conteudo)
    segmentos = []
    for no in arvore.body:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            try:
                seg = ast.get_source_segment(conteudo, no)
                if seg:
                    segmentos.append((no.lineno, seg))
            except Exception:
                pass
    if not segmentos:
        return _chunkar_por_tamanho(conteudo)
    return _agrupar_em_chunks(segmentos)

EXTENSAO_PARA_TS = {
    ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
    ".ts": "ts", ".tsx": "tsx",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
    ".c": "c", ".h": "c",
    ".css": "css",
    ".html": "html",
}

_cache_ts = None

def _linguagens_ts():
    global _cache_ts
    if _cache_ts is not None:
        return _cache_ts
    from tree_sitter import Language
    import tree_sitter_javascript as tsjs
    import tree_sitter_typescript as tsts
    import tree_sitter_cpp as tscpp
    import tree_sitter_c as tsc
    import tree_sitter_css as tscss
    import tree_sitter_html as tshtml

    tipos_js = {
        "function_declaration", "generator_function_declaration", "class_declaration",
        "method_definition", "lexical_declaration", "variable_declaration",
        "import_statement", "export_statement",
    }
    tipos_ts = tipos_js | {
        "interface_declaration", "type_alias_declaration", "enum_declaration",
        "namespace_declaration", "abstract_class_declaration",
    }
    tipos_cpp = {
        "function_definition", "class_specifier", "struct_specifier",
        "namespace_definition", "enum_specifier", "union_specifier",
        "template_declaration", "linkargs_definition",
    }
    tipos_c = {
        "function_definition", "struct_specifier", "enum_specifier",
        "union_specifier", "preproc_def", "declaration",
    }

    _cache_ts = {
        "js": (Language(tsjs.language()), tipos_js),
        "ts": (Language(tsts.language_typescript()), tipos_ts),
        "tsx": (Language(tsts.language_tsx()), tipos_ts),
        "cpp": (Language(tscpp.language()), tipos_cpp),
        "c": (Language(tsc.language()), tipos_c),
        "css": (Language(tscss.language()), {"rule_set", "at_rule"}),
        "html": (Language(tshtml.language()), {"element", "script_element", "style_element"}),
    }
    return _cache_ts

def _chunkar_ts(conteudo, nome):
    try:
        linguagens = _linguagens_ts()
    except ImportError:
        return _chunkar_por_tamanho(conteudo)
    entrada = linguagens.get(nome)
    if not entrada:
        return _chunkar_por_tamanho(conteudo)
    language, tipos = entrada
    from tree_sitter import Parser
    parser = Parser(language)
    conteudo_bytes = conteudo.encode("utf-8")
    try:
        tree = parser.parse(conteudo_bytes)
    except Exception:
        return _chunkar_por_tamanho(conteudo)

    def texto_no(no):
        return conteudo_bytes[no.start_byte:no.end_byte].decode("utf-8", "ignore")

    def fatiar(linha, texto):
        linhas = texto.splitlines()
        chunks = []
        atual = []
        tamanho = 0
        inicio = linha
        for i, l in enumerate(linhas):
            atual.append(l)
            tamanho += len(l) + 1
            if tamanho >= TAMANHO_CHUNK:
                chunks.append((inicio, "\n".join(atual)))
                atual = []
                tamanho = 0
                inicio = linha + i + 1
        if atual:
            chunks.append((inicio, "\n".join(atual)))
        return chunks

    segmentos = []

    def visitar(no):
        if no.type in tipos:
            seg = texto_no(no)
            if len(seg) <= TAMANHO_CHUNK * 2:
                segmentos.append((no.start_point[0] + 1, seg))
                return
            filhos = [c for c in no.named_children if c.type in tipos]
            if filhos:
                for f in filhos:
                    visitar(f)
                return
            segmentos.extend(fatiar(no.start_point[0] + 1, seg))
            return
        for c in no.named_children:
            visitar(c)

    for no in tree.root_node.named_children:
        visitar(no)

    if not segmentos:
        return _chunkar_por_tamanho(conteudo)
    return _agrupar_em_chunks(segmentos)

def _chunkar_conteudo(caminho, conteudo):
    ext = os.path.splitext(caminho)[1].lower()
    if ext == ".py":
        return _chunkar_python(conteudo)
    nome_ts = EXTENSAO_PARA_TS.get(ext)
    if nome_ts:
        try:
            return _chunkar_ts(conteudo, nome_ts)
        except Exception:
            return _chunkar_por_tamanho(conteudo)
    return _chunkar_por_tamanho(conteudo)

def indexar_codigo_incremental(force=False):
    indice = _carregar_indice()
    raiz = estado.get("pasta_raiz", "")
    if not raiz:
        return {"erro": "nenhuma pasta de projeto selecionada"}
    col = _colecao_codigo(create=True)
    if col is None:
        return {"erro": f"falha ao abrir a coleção de código: {_erro_colecao['motivo'] or 'causa desconhecida'}"}
    recriada = False
    if not force and _colecao_foi_recriada(col, indice):
        force = True
        recriada = True
    arquivos = arquivos_de_codigo()
    wing = _wing()
    novos = 0
    alterados = 0
    removidos = 0
    total_chunks = 0
    vistos = set()
    total_arquivos = len(arquivos)
    for pos, caminho in enumerate(arquivos, 1):
        rel = caminho_relativo(caminho)
        vistos.add(rel)
        try:
            st = os.stat(caminho)
        except OSError:
            continue
        mtime = st.st_mtime
        size = st.st_size
        antigo = indice.get(rel)
        if not force and antigo and antigo.get("mtime") == mtime and antigo.get("size") == size and antigo.get("chunker_version") == CHUNKER_VERSION:
            total_chunks += antigo.get("chunks", 0)
            continue
        try:
            with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
                conteudo = f.read()
        except Exception:
            continue
        h = hashlib.sha256(conteudo.encode("utf-8", "ignore")).hexdigest()
        if not force and antigo and antigo.get("hash") == h and antigo.get("chunker_version") == CHUNKER_VERSION:
            indice[rel] = {"hash": h, "mtime": mtime, "size": size, "chunks": antigo.get("chunks", 0), "chunker_version": CHUNKER_VERSION}
            total_chunks += antigo.get("chunks", 0)
            continue
        _deletar_chunks_do_arquivo(col, rel)
        chunks = _chunkar_conteudo(caminho, conteudo)
        docs = []
        ids = []
        metas = []
        for idx, (linha_inicio, texto) in enumerate(chunks):
            did = "code_" + hashlib.sha256((rel + ":" + str(linha_inicio)).encode()).hexdigest()[:24]
            docs.append(texto)
            ids.append(did)
            metas.append({
                "wing": wing,
                "room": "code",
                "source_file": rel,
                "chunk_index": idx,
                "line_start": linha_inicio,
                "added_by": "axio",
                "source_mtime": mtime,
            })
        try:
            with memoria_lock:
                col.upsert(documents=docs, ids=ids, metadatas=metas)
        except Exception:
            continue
        indice[rel] = {"hash": h, "mtime": mtime, "size": size, "chunks": len(chunks), "chunker_version": CHUNKER_VERSION}
        if antigo:
            alterados += 1
        else:
            novos += 1
        total_chunks += len(chunks)
        if (novos + alterados) % 5 == 0:
            emit_event("executing", function=f"Indexando código ({pos}/{total_arquivos})")
    for rel in list(indice.keys()):
        if rel not in vistos:
            _deletar_chunks_do_arquivo(col, rel)
            indice.pop(rel, None)
            removidos += 1
    auditoria = {
        "novos": novos,
        "alterados": alterados,
        "removidos": removidos,
        "total_chunks": total_chunks,
        "total_arquivos": len(vistos),
        "colecao_recriada": recriada,
        "identidade_embedder": _identidade_embedder["status"],
        "timestamp": time.time(),
    }
    _salvar_indice(indice, auditoria, getattr(col, "id", ""))
    return {"novos": novos, "alterados": alterados, "removidos": removidos, "total_chunks": total_chunks}

def buscar_codigo_semantico(query, n_results=5):
    if not query or not query.strip():
        return []
    col = _colecao_codigo(create=False)
    if col is None:
        return []
    wing = _wing()
    kwargs = {
        "query_texts": [query],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }
    if wing:
        kwargs["where"] = {"wing": wing}
    try:
        with memoria_lock:
            res = col.query(**kwargs)
    except Exception:
        if wing:
            kwargs.pop("where", None)
            try:
                with memoria_lock:
                    res = col.query(**kwargs)
            except Exception:
                return []
        else:
            return []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    out = []
    for doc, meta, dist in zip(docs, metas, dists):
        meta = meta or {}
        out.append({
            "texto": doc,
            "arquivo": meta.get("source_file", "?"),
            "linha": meta.get("line_start", 1),
            "similaridade": round(max(0.0, 1 - dist), 3),
        })
    return out

def buscar_codigo_relevante_para_contexto(query, n_results=3, min_similaridade=0.5):
    resultado = {"data": None}

    def _trabalho():
        resultado["data"] = buscar_codigo_semantico(query, n_results=n_results)

    t = threading.Thread(target=_trabalho, daemon=True)
    t.start()
    t.join(6.0)
    if t.is_alive():
        return ""
    hits = resultado["data"] or []
    relevantes = [h for h in hits if h.get("similaridade", 0) >= min_similaridade]
    if not relevantes:
        return ""
    linhas = []
    for h in relevantes:
        linhas.append(f"[{h['arquivo']}:{h['linha']}] (similaridade {h['similaridade']})\n{h['texto']}")
    return "Trechos de código potencialmente relevantes (use tool_buscar_codigo para busca mais ampla):\n\n" + "\n\n".join(linhas)

def disparar_indexacao_background():
    def _trabalho():
        if not _lock_index.acquire(blocking=False):
            return
        try:
            indexar_codigo_incremental()
        finally:
            _lock_index.release()

    threading.Thread(target=_trabalho, daemon=True).start()

@register(
    "tool_indexar_codigo",
    'Atualiza o índice semântico de código do projeto (embeddings dos trechos de código no ChromaDB). É INCREMENTAL: só reprocessa os arquivos que mudaram desde a última indexação, então normalmente termina em segundos. A indexação também roda automaticamente no início de cada rodada.',
    {
        'forcar': {"tipo": "BOOLEAN", "desc": 'Reconstrói o índice do zero, ignorando o cache por hash. Use raramente e só se o índice estiver corrompido — em projetos grandes isso demora minutos.', "padrao": False},
    },
)
def tool_indexar_codigo(forcar=False):
    emit_event("executing", function="Indexando código do projeto")
    if not _lock_index.acquire(blocking=False):
        return ("AVISO: já existe uma indexação de código em andamento (ela roda "
                "automaticamente no início de cada rodada). Nada foi feito para não "
                "duplicar trabalho — tente novamente em alguns instantes.")
    resultado = {}

    def _trabalho():
        try:
            resultado["res"] = indexar_codigo_incremental(force=forcar)
        except Exception as e:
            resultado["erro"] = str(e)
        finally:
            _lock_index.release()

    t = threading.Thread(target=_trabalho, daemon=True)
    t.start()
    t.join(TIMEOUT_INDEXACAO)
    if t.is_alive():
        return (f"Indexação iniciada: ainda em andamento em background (ultrapassou "
                f"{int(TIMEOUT_INDEXACAO)}s). O índice continua sendo atualizado sem bloquear "
                f"a interface — use tool_buscar_codigo quando terminar.")
    if "erro" in resultado:
        return f"ERRO: {resultado['erro']}"
    res = resultado.get("res") or {}
    if "erro" in res:
        return f"ERRO: {res['erro']}"
    return (f"SUCESSO: índice de código atualizado (incremental). {res.get('novos', 0)} novos, "
            f"{res.get('alterados', 0)} alterados, {res.get('removidos', 0)} removidos, "
            f"{res.get('total_chunks', 0)} chunks no total.")

@register(
    "tool_buscar_codigo",
    'Busca trechos de código relevantes por similaridade semântica no índice de código do projeto (codebase indexing, como o Cursor). Use para localizar código por descrição/contexto, não por termo exato.',
    {
        'query': {"tipo": "STRING", "desc": 'Descrição ou contexto do que procura no código', "obrig": True, "padrao": ""},
    },
)
def tool_buscar_codigo(query):
    emit_event("executing", function=f"Buscando no código: {query}")
    resultados = buscar_codigo_semantico(query, n_results=6)
    if not resultados:
        if _erro_colecao["motivo"]:
            return f"ERRO: não consegui abrir o índice de código: {_erro_colecao['motivo']}"
        return ("Nenhum trecho de código relevante encontrado. O índice de código pode "
                "ainda não ter sido construído (a primeira indexação roda em background).")
    linhas = []
    for r in resultados:
        linhas.append(f"[{r['arquivo']}:{r['linha']}] (similaridade {r['similaridade']})\n{r['texto']}")
    return "Trechos de código mais relevantes:\n\n" + "\n\n".join(linhas)

