import os
import ast
import json
import time
import sys
import hashlib
import threading

from src.backend.state import estado, emit_event, caminho_estado_projeto, memoria_lock
from src.backend.memory.vector import garantir_patch_mempalace, wing_da_pasta

EXTENSOES_CODIGO = (
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".html", ".css", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".c",
    ".java", ".rs", ".go", ".rb", ".php", ".json", ".md",
    ".yaml", ".yml", ".toml", ".sh",
)
PASTAS_IGNORADAS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".axio", ".mempalace", "target", ".next",
    ".idea", ".vscode", "coverage", ".tox", ".nox", ".pytest_cache",
}
TAMANHO_CHUNK = 1600
MAX_ARQUIVOS_INDEX = 3000
MAX_ARQUIVOS_CONTEXTO = 600
CHUNKER_VERSION = 2
_COLLECTION_CODIGO = "axio_code"

_lock_index = threading.Lock()
TIMEOUT_INDEXACAO = 12.0
_cache_contexto = {"texto": "", "ts": 0.0}

def _wing():
    return wing_da_pasta(estado.get("pasta_raiz")) or "general"

def _palace_path():
    return os.path.expanduser("~/.mempalace/palace")

def _colecao_codigo(create=True):
    garantir_patch_mempalace()
    from mempalace.palace import get_collection
    if not create and not os.path.isdir(_palace_path()):
        return None
    try:
        return get_collection(_palace_path(), collection_name=_COLLECTION_CODIGO, create=create)
    except Exception:
        return None

def _caminho_indice():
    return caminho_estado_projeto("code_index.json")

def _carregar_indice():
    caminho = _caminho_indice()
    if not caminho or not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if isinstance(dados, dict) and isinstance(dados.get("arquivos"), dict):
            return dados["arquivos"]
    except Exception:
        pass
    return {}

def _salvar_indice(indice, auditoria=None):
    caminho = _caminho_indice()
    if not caminho:
        return
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        payload = {"arquivos": indice, "atualizado_em": time.time()}
        if auditoria:
            payload["ultima_indexacao"] = auditoria
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _relativo(caminho):
    raiz = estado.get("pasta_raiz", "")
    if not raiz:
        return caminho
    return os.path.relpath(caminho, raiz).replace("\\", "/")

def _arquivos_de_codigo(max_arquivos=MAX_ARQUIVOS_INDEX):
    raiz = estado.get("pasta_raiz", "")
    if not raiz or not os.path.isdir(raiz):
        return []
    arquivos = []
    for root, dirs, files in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in PASTAS_IGNORADAS and not d.startswith(".")]
        for name in files:
            if not name.lower().endswith(EXTENSOES_CODIGO):
                continue
            caminho = os.path.join(root, name)
            try:
                if os.path.getsize(caminho) > 512000:
                    continue
            except OSError:
                continue
            arquivos.append(caminho)
            if len(arquivos) >= max_arquivos:
                return arquivos
    return arquivos

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
        return {"erro": "falha ao abrir a coleção de código"}
    arquivos = _arquivos_de_codigo()
    wing = _wing()
    novos = 0
    alterados = 0
    removidos = 0
    total_chunks = 0
    vistos = set()
    total_arquivos = len(arquivos)
    for pos, caminho in enumerate(arquivos, 1):
        rel = _relativo(caminho)
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
        "timestamp": time.time(),
    }
    _salvar_indice(indice, auditoria)
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

def _detectar_stack():
    itens = [f"Python {sys.version.split()[0]}"]
    raiz = estado.get("pasta_raiz", "")
    if raiz:
        pkg_path = os.path.join(raiz, "package.json")
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                engines = pkg.get("engines") or {}
                if engines.get("node"):
                    itens.append(f"Node {engines['node']}")
            except Exception:
                pass
        for nome_arq in (".nvmrc", ".node-version"):
            caminho = os.path.join(raiz, nome_arq)
            if os.path.exists(caminho):
                try:
                    with open(caminho, "r", encoding="utf-8") as f:
                        versao = f.read().strip()
                    if versao:
                        itens.append(f"Node {versao}")
                        break
                except Exception:
                    pass
    return ", ".join(itens)

def _dependencias(raiz):
    linhas = []
    req = os.path.join(raiz, "requirements.txt")
    if os.path.exists(req):
        try:
            with open(req, "r", encoding="utf-8", errors="ignore") as f:
                nomes = []
                for l in f:
                    l = l.strip()
                    if not l or l.startswith("#") or l.startswith("-"):
                        continue
                    nome = l.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split("[")[0].strip()
                    if nome:
                        nomes.append(nome)
            if nomes:
                nomes_unicos = sorted(set(nomes), key=str.lower)
                linhas.append(f"requirements.txt ({len(nomes_unicos)} pacotes): " + ", ".join(nomes_unicos))
        except Exception:
            pass
    pkg_path = os.path.join(raiz, "package.json")
    if os.path.exists(pkg_path):
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            deps = list((pkg.get("dependencies") or {}).keys()) + list((pkg.get("devDependencies") or {}).keys())
            if deps:
                linhas.append(f"package.json ({len(deps)} dependências): " + ", ".join(sorted(set(deps), key=str.lower)))
        except Exception:
            pass
    pyproject = os.path.join(raiz, "pyproject.toml")
    if os.path.exists(pyproject):
        try:
            with open(pyproject, "r", encoding="utf-8", errors="ignore") as f:
                nlinhas = sum(1 for _ in f)
            linhas.append(f"pyproject.toml presente ({nlinhas} linhas)")
        except Exception:
            pass
    return "\n".join(linhas) if linhas else "(sem manifestos de dependências detectados)"

def _arvore_resumida(raiz, max_prof=3, max_entradas=80):
    linhas = []
    contador = {"n": 0}
    limite_dir = 30

    def _walk(pasta, prefixo, prof):
        if prof > max_prof or contador["n"] >= max_entradas:
            return
        try:
            entradas = sorted(os.listdir(pasta), key=lambda n: n.lower())
        except OSError:
            return
        dirs = [e for e in entradas if os.path.isdir(os.path.join(pasta, e)) and e not in PASTAS_IGNORADAS and not e.startswith(".")]
        files = [e for e in entradas if os.path.isfile(os.path.join(pasta, e))]
        exibir = (dirs + files)[:limite_dir]
        for idx, e in enumerate(exibir):
            contador["n"] += 1
            if contador["n"] > max_entradas:
                linhas.append(prefixo + "... (truncado)")
                return
            eh_ultimo = idx == len(exibir) - 1
            ramo = "└── " if eh_ultimo else "├── "
            caminho = os.path.join(pasta, e)
            if os.path.isdir(caminho):
                linhas.append(prefixo + ramo + e + "/")
                _walk(caminho, prefixo + ("    " if eh_ultimo else "│   "), prof + 1)
            else:
                linhas.append(prefixo + ramo + e)
    _walk(raiz, "", 1)
    return "\n".join(linhas) if linhas else "(pasta vazia)"

def _stats_codigo(arquivos):
    por_ext = {}
    for caminho in arquivos:
        ext = os.path.splitext(caminho)[1].lower() or "(sem ext)"
        por_ext[ext] = por_ext.get(ext, 0) + 1
    resumo = f"{len(arquivos)} arquivos de código"
    if por_ext:
        topo = ", ".join(f"{k}:{v}" for k, v in sorted(por_ext.items(), key=lambda x: -x[1])[:10])
        resumo += f" | {topo}"
    return resumo

def gerar_contexto_projeto():
    raiz = estado.get("pasta_raiz", "")
    if not raiz:
        return "(nenhuma pasta de projeto selecionada)"
    agora = time.time()
    if _cache_contexto["texto"] and (agora - _cache_contexto["ts"]) < 120:
        return _cache_contexto["texto"]
    arquivos = _arquivos_de_codigo(MAX_ARQUIVOS_CONTEXTO)
    stack = _detectar_stack()
    partes = [
        f"Raiz: {raiz}",
        f"Stack: {stack}",
        f"Arquivos: {_stats_codigo(arquivos)}",
        f"Dependências:\n{_dependencias(raiz)}",
        f"Estrutura:\n{_arvore_resumida(raiz)}",
    ]
    texto = "\n".join(partes)
    _cache_contexto["texto"] = texto
    _cache_contexto["ts"] = agora
    return texto

def disparar_indexacao_background():
    def _trabalho():
        if not _lock_index.acquire(blocking=False):
            return
        try:
            indexar_codigo_incremental()
        finally:
            _lock_index.release()

    threading.Thread(target=_trabalho, daemon=True).start()

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

def tool_buscar_codigo(query):
    emit_event("executing", function=f"Buscando no código: {query}")
    resultados = buscar_codigo_semantico(query, n_results=6)
    if not resultados:
        return ("Nenhum trecho de código relevante encontrado. O índice de código pode "
                "ainda não ter sido construído (a primeira indexação roda em background).")
    linhas = []
    for r in resultados:
        linhas.append(f"[{r['arquivo']}:{r['linha']}] (similaridade {r['similaridade']})\n{r['texto']}")
    return "Trechos de código mais relevantes:\n\n" + "\n\n".join(linhas)
