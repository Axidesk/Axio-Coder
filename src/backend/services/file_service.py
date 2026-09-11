import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata

from src.backend.state import estado, MAX_UNDO, caminho_estado_projeto, MSG_SEM_PASTA
from src.backend.config import APP_ROOT
from src.backend.services.file_watcher import notificar_gravacao

def dirs_leitura_extra():
    dirs = []
    raiz_app = APP_ROOT
    if raiz_app not in dirs:
        dirs.append(raiz_app)
    raw = os.getenv("DIRS_LEITURA_PERMITIDOS", "")
    if raw:
        for parte in re.split(r"[;,\n]", raw):
            parte = parte.strip().strip('"').strip("'")
            if parte:
                dirs.append(os.path.abspath(os.path.expanduser(parte)))
    raiz = estado.get("pasta_raiz")
    if raiz:
        candidatos = [
            os.path.join(raiz, "..", ".venv"),
            os.path.join(raiz, "..", "venv"),
            os.path.join(raiz, ".venv"),
            os.path.join(raiz, "venv"),
        ]
        for c in candidatos:
            c = os.path.abspath(c)
            if os.path.isdir(c) and c not in dirs:
                dirs.append(c)
    return dirs

def venv_projeto():
    raiz = estado.get("pasta_raiz")
    if not raiz:
        return None
    try:
        entradas = sorted(os.listdir(raiz))
    except OSError:
        entradas = []
    preferidos = [n for n in (".venv", "venv") if n in entradas]
    restante = [n for n in entradas if n not in preferidos]
    for nome in preferidos + restante:
        cand = os.path.join(raiz, nome)
        if not os.path.isdir(cand):
            continue
        if os.name == "nt":
            py = os.path.join(cand, "Scripts", "python.exe")
            scripts = os.path.join(cand, "Scripts")
        else:
            py = os.path.join(cand, "bin", "python")
            scripts = os.path.join(cand, "bin")
        if os.path.isfile(py):
            return {"dir": cand, "python": py, "scripts": scripts, "nome": nome}
    try:
        app_dir = APP_ROOT
        raiz_abs = os.path.abspath(raiz)
        if raiz_abs == app_dir or raiz_abs.startswith(app_dir + os.sep):
            if getattr(sys, "base_prefix", None) and sys.prefix != sys.base_prefix:
                if os.name == "nt":
                    scripts = os.path.join(sys.prefix, "Scripts")
                else:
                    scripts = os.path.join(sys.prefix, "bin")
                nome = os.path.basename(os.path.abspath(sys.prefix)) or ".venv"
                return {"dir": sys.prefix, "python": sys.executable, "scripts": scripts, "nome": nome}
    except Exception:
        pass
    return None

def _caminho_proibido(alvo):
    try:
        norm = os.path.normpath(alvo)
    except Exception:
        return False
    partes = [p for p in norm.replace("\\", "/").split("/") if p]
    return any(p == ".trash" for p in partes)

def caminho_contido(alvo, base):
    """Diz se `alvo` esta dentro de `base` (ou e igual a ela).

    normcase iguala 'D:\\Proj' e 'd:/proj' no Windows; drives diferentes fazem
    commonpath levantar ValueError, tratado como 'fora'.
    """
    try:
        a = os.path.normcase(os.path.abspath(alvo))
        b = os.path.normcase(os.path.abspath(base))
        return os.path.commonpath([a, b]) == b
    except ValueError:
        return False

def _validar_contencao(alvo, raiz_abs, permitir_extra, permitir_escrita):
    """Politica de contencao: dentro da raiz passa; fora depende do modo.

    Escrita fora da pasta do projeto e sempre recusada. Leitura fora so passa
    com permitir_extra, que e o que sustenta a navegacao do explorer (breadcrumb
    absoluto quando 'dentro_da_raiz' e falso).
    """
    if caminho_contido(alvo, raiz_abs):
        return None
    if permitir_escrita:
        return "ERRO: escrita fora da pasta do projeto e bloqueada."
    if not permitir_extra:
        return "ERRO: o caminho esta fora da pasta do projeto."
    return None

def resolver_caminho(caminho_relativo, permitir_extra=True, permitir_escrita=False):
    raiz = estado.get("pasta_raiz")
    if not raiz:
        return None, MSG_SEM_PASTA
    raiz_abs = os.path.abspath(raiz)
    alvo = os.path.abspath(os.path.join(raiz_abs, caminho_relativo))
    if _caminho_proibido(alvo):
        return None, "ERRO: caminho dentro da lixeira (área protegida)."
    erro_contencao = _validar_contencao(alvo, raiz_abs, permitir_extra, permitir_escrita)
    if erro_contencao:
        return None, erro_contencao
    return alvo, None

def resolver_caminho_arquivo(caminho):
    if not caminho:
        return None, "caminho não informado"
    if os.path.isabs(caminho) and not estado.get("pasta_raiz"):
        alvo = os.path.abspath(caminho)
        if _caminho_proibido(alvo):
            return None, "ERRO: caminho dentro da lixeira (área protegida)."
        return alvo, None
    return resolver_caminho(caminho, permitir_extra=True)

def versao_pacote(nome):
    try:
        from importlib import metadata
        return metadata.version(nome)
    except Exception:
        return "desconhecida"

def entradas_diretorio(caminho_alvo):
    ignorar = {'.git', 'node_modules', 'build', '__pycache__', '.vs', 'Intermediate', 'Binaries', 'Saved'}
    entradas = []
    for item in os.listdir(caminho_alvo):
        if item in ignorar or item.startswith('.'):
            continue
        caminho_item = os.path.join(caminho_alvo, item)
        if os.path.isdir(caminho_item):
            entradas.append({"nome": item, "tipo": "dir"})
        elif not item.endswith(('.exe', '.dll', '.obj', '.lib', '.o', '.so', '.a', '.dylib', '.png', '.jpg', '.pdb')):
            entradas.append({"nome": item, "tipo": "file"})
    return entradas

def normalizar_unicode(texto: str) -> str:
    """Normaliza para NFC e decodifica escapes Unicode literais (ex: 'ú' -> 'u').
    Resolve falha de match quando o arquivo grava acentos como 'ú' literal
    ou em mistura NFC/NFD."""
    def _decod(m):
        try:
            return chr(int(m.group(1), 16))
        except (ValueError, OverflowError):
            return m.group(0)
    texto = re.sub(r'\\u([0-9a-fA-F]{4})', _decod, texto)
    texto = re.sub(r'\\U([0-9a-fA-F]{8})', _decod, texto)
    return unicodedata.normalize('NFC', texto)

def aplicar_snapshot(entrada, reverso):
    """Aplica um snapshot de arquivo (usado por undo/redo).

    reverso=True  -> restaura o estado ANTES da edição
    reverso=False -> reaplica o estado DEPOIS da edição
    """
    caminho = entrada["caminho"]
    conteudo = entrada["antes"] if reverso else entrada["depois"]

    if conteudo is None:
        # O arquivo não existia antes da edição -> remove para desfazer a criação
        if os.path.exists(caminho):
            os.remove(caminho)
        return

    diretorio = os.path.dirname(caminho)
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(conteudo)

def _coletar_grupo_do_topo(grupo, pilha):
    """Remove do topo das pilhas de um grupo atômico as entradas correspondentes."""
    entradas = []
    for hist in estado["file_history"].values():
        if hist[pilha] and hist[pilha][-1].get("grupo") == grupo:
            entradas.append(hist[pilha].pop())
    return entradas

def _desfazer_ou_refazer(caminho, acao):
    """Executa undo ou redo para um arquivo, retornando um dict de resultado.

    acao == "undo"  -> restaura o estado ANTES da edição mais recente
    acao == "redo"  -> reaplica o estado DEPOIS da edição desfeita mais recente
    """
    origem = "undo" if acao == "undo" else "redo"
    destino = "redo" if acao == "undo" else "undo"
    reverso = acao == "undo"
    hist = estado["file_history"].get(caminho) if caminho else None
    if not hist or not hist[origem]:
        verbo = "desfazer" if acao == "undo" else "refazer"
        return {"status": "empty", "message": f"Nada para {verbo} neste arquivo."}

    entrada = hist[origem].pop()
    grupo = entrada.get("grupo")
    entradas = [entrada]
    if grupo:
        entradas.extend(_coletar_grupo_do_topo(grupo, origem))

    try:
        for e in reversed(entradas):
            aplicar_snapshot(e, reverso=reverso)
    except Exception as ex:
        for e in reversed(entradas):
            estado["file_history"].setdefault(e["caminho"], {"undo": [], "redo": []})[origem].append(e)
        return {"status": "error", "message": str(ex)}

    for e in entradas:
        estado["file_history"].setdefault(e["caminho"], {"undo": [], "redo": []})[destino].append(e)
    nome = os.path.basename(entrada["caminho"])
    verbo = "Desfeito" if acao == "undo" else "Refeito"
    return {"status": "ok", "message": f"{verbo}: {nome}", "entradas": entradas}

def desfazer_edicao(caminho):
    return _desfazer_ou_refazer(caminho, "undo")

def refazer_edicao(caminho):
    return _desfazer_ou_refazer(caminho, "redo")

def _primeira_linha_alterada(antes, depois):
    """Retorna a 1ª linha efetivamente alterada entre dois conteúdos (1-based)."""
    if antes is None:
        return 1
    if depois is None:
        return None
    linhas_a = antes.splitlines()
    linhas_b = depois.splitlines()
    n = min(len(linhas_a), len(linhas_b))
    for i in range(n):
        if linhas_a[i] != linhas_b[i]:
            return i + 1
    if len(linhas_a) != len(linhas_b):
        return n + 1
    return None

def registrar_edicao_para_contexto(caminho_absoluto, antes, depois):
    """Registra (arquivo + linha) para injetar no contexto do próximo turno.

    Não mexe no histórico de desfazer/refazer nem em arquivos_tocados; apenas
    alimenta a lista que informa ao modelo "o que foi editado recentemente",
    incluindo edições manuais feitas pelo usuário no editor (estilo Cursor).
    """
    if antes is not None and antes == depois:
        return
    linha = _primeira_linha_alterada(antes, depois)
    pasta_raiz = estado.get("pasta_raiz", "")
    try:
        rel = os.path.relpath(caminho_absoluto, pasta_raiz).replace("\\", "/") if pasta_raiz else caminho_absoluto.replace("\\", "/")
    except ValueError:
        rel = caminho_absoluto.replace("\\", "/")
    edicoes = estado.setdefault("edicoes_rodada", [])
    edicoes[:] = [e for e in edicoes if e["arquivo"] != rel]
    edicoes.append({"arquivo": rel, "linha": linha})
    notificar_gravacao(caminho_absoluto, depois)

def registrar_edicao(caminho_absoluto, antes, depois, grupo=None):
    """Registra uma edição no histórico de desfazer/refazer.

    'antes' é None quando o arquivo não existia antes da edição.
    'grupo' agrupa edições atômicas (ex: mover origem+destino) para desfazer/refazer juntas.
    """
    if antes is not None and antes == depois:
        return  # Sem mudança efetiva, não registra

    registrar_edicao_para_contexto(caminho_absoluto, antes, depois)

    # Marca o arquivo como tocado nesta sessão para que ele entre no checkpoint
    # de código persistido junto com o log da sessão (Fase 1 de restauração).
    estado["arquivos_tocados"].add(caminho_absoluto)

    hist = estado["file_history"].setdefault(caminho_absoluto, {"undo": [], "redo": []})

    entrada = {
        "caminho": caminho_absoluto,
        "antes": antes,
        "depois": depois,
    }
    if grupo:
        entrada["grupo"] = grupo
    hist["undo"].append(entrada)

    # Mantém apenas as MAX_UNDO edições mais recentes
    if len(hist["undo"]) > MAX_UNDO:
        hist["undo"] = hist["undo"][-MAX_UNDO:]

    # Uma nova edição invalida o histórico de redo
    hist["redo"].clear()

def capturar_snapshot():
    """Captura o estado atual (conteúdo) de todos os arquivos tocados na sessão.

    Retorna um dicionário {caminho_relativo: {"conteudo": str|None}}. Quando o
    arquivo não existe mais no disco (foi criado e depois removido), `conteudo`
    é None, indicando que a restauração deve remover o arquivo.
    """
    pasta_raiz = estado.get("pasta_raiz", "")
    snapshot = {}
    for caminho in sorted(estado.get("arquivos_tocados", set())):
        try:
            rel = os.path.relpath(caminho, pasta_raiz).replace("\\", "/") if pasta_raiz else caminho.replace("\\", "/")
        except ValueError:
            rel = caminho.replace("\\", "/")

        if os.path.exists(caminho):
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    conteudo = f.read()
            except (OSError, UnicodeDecodeError):
                continue  # Ignora arquivos ilegíveis/binários (não editáveis por texto).
            snapshot[rel] = {"conteudo": conteudo}
        else:
            # Foi tocado nesta sessão, mas não existe mais no disco.
            snapshot[rel] = {"conteudo": None}
    return snapshot

def raiz_abs():
    raiz = estado.get("pasta_raiz", "")
    return os.path.abspath(raiz) if raiz else ""

def calcular_posicao_relativa(cwd, raiz_abs):
    """Devolve (relativo, dentro) de um caminho em relacao a raiz do projeto.

    `relativo` usa sempre '/' como separador. `dentro` indica se o caminho esta
    contido na raiz (ou e igual a ela).
    """
    relativo = ""
    dentro = False
    if raiz_abs:
        try:
            relativo = os.path.relpath(cwd, raiz_abs).replace("\\", "/")
        except ValueError:
            relativo = ""
        dentro = caminho_contido(cwd, raiz_abs)
    return relativo, dentro

def raiz_lixeira():
    raiz = estado.get("pasta_raiz", "")
    if not raiz:
        return ""
    return caminho_estado_projeto("chats", "session_logs", ".trash")

def _meta_lixeira_path(lixeira_raiz, ts_dir):
    """Caminho do manifesto de uma operacao da lixeira (irmao do diretorio).

    O manifesto guarda o caminho original e o tipo do item apagado. Fica FORA do
    diretorio do item para nao ser restaurado junto com ele.
    """
    return os.path.join(lixeira_raiz, "." + ts_dir + ".json")

def _gravar_meta_lixeira(lixeira_raiz, ts_dir, rel, tipo):
    """Registra o caminho original de um item movido para a lixeira."""
    try:
        with open(_meta_lixeira_path(lixeira_raiz, ts_dir), "w", encoding="utf-8") as f:
            json.dump({"caminho": rel.replace(os.sep, "/"), "tipo": tipo}, f, ensure_ascii=False)
    except OSError as e:
        print(f"Erro ao gravar manifesto da lixeira {ts_dir}: {e}")

def _ler_meta_lixeira(lixeira_raiz, ts_dir):
    """Le o manifesto de uma operacao da lixeira (None quando nao existe)."""
    try:
        with open(_meta_lixeira_path(lixeira_raiz, ts_dir), "r", encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) else None

def _dirs_vazios_lixeira(ts_path):
    """Diretorios da lixeira cuja subarvore nao contem nenhum arquivo.

    Devolve apenas os mais externos (se 'a' e 'a/b' estiverem vazios, devolve
    so 'a'), para nao listar pastas aninhadas como itens separados.
    """
    vazios = set()
    for root, dirs, files in os.walk(ts_path, topdown=False):
        if root == ts_path:
            continue
        if not files and all(os.path.join(root, d) in vazios for d in dirs):
            vazios.add(root)
    return sorted(d for d in vazios if os.path.dirname(d) not in vazios)

def listar_lixeira():
    lixeira_raiz = raiz_lixeira()
    if not lixeira_raiz or not os.path.isdir(lixeira_raiz):
        return []
    itens = []
    for ts_dir in sorted(os.listdir(lixeira_raiz), reverse=True):
        ts_path = os.path.join(lixeira_raiz, ts_dir)
        if not os.path.isdir(ts_path):
            continue
        try:
            ts = int(ts_dir)
        except ValueError:
            ts = 0
        rel_meta = ""
        tipo_meta = ""
        meta = _ler_meta_lixeira(lixeira_raiz, ts_dir)
        if meta:
            rel_meta = (meta.get("caminho") or "").replace(os.sep, "/")
            tipo_meta = meta.get("tipo") or ""
        if rel_meta:
            nome = os.path.basename(rel_meta.rstrip("/"))
            if os.path.exists(os.path.join(ts_path, nome)):
                itens.append({
                    "id": ts_dir + "/" + nome,
                    "nome": nome,
                    "original": rel_meta,
                    "ts": ts,
                    "tipo": tipo_meta or ("dir" if os.path.isdir(os.path.join(ts_path, nome)) else "file"),
                })
            continue
        for root, _dirs, files in os.walk(ts_path):
            for nome in files:
                full = os.path.join(root, nome)
                rel_lixeira = os.path.relpath(full, lixeira_raiz)
                rel_original = os.path.relpath(full, ts_path)
                itens.append({
                    "id": rel_lixeira.replace(os.sep, "/"),
                    "nome": nome,
                    "original": rel_original.replace(os.sep, "/"),
                    "ts": ts,
                    "tipo": "file",
                })
        for pasta in _dirs_vazios_lixeira(ts_path):
            rel_lixeira = os.path.relpath(pasta, lixeira_raiz)
            rel_original = os.path.relpath(pasta, ts_path)
            itens.append({
                "id": rel_lixeira.replace(os.sep, "/"),
                "nome": os.path.basename(pasta),
                "original": rel_original.replace(os.sep, "/"),
                "ts": ts,
                "tipo": "dir",
            })
    itens.sort(key=lambda x: (x["ts"], x["id"]), reverse=True)
    return itens

def caminho_original_lixeira(lixeira_raiz, item_id, origem):
    """Caminho original (relativo a raiz do projeto) de um item da lixeira.

    Com manifesto, o item de topo devolve o caminho exato que foi apagado e um
    descendente devolve caminho_original + subcaminho. Sem manifesto (operacoes
    antigas) cai no calculo pelo layout achatado.
    """
    ts_dir = item_id.split("/")[0]
    ts_path = os.path.join(lixeira_raiz, ts_dir)
    meta = _ler_meta_lixeira(lixeira_raiz, ts_dir)
    if not meta:
        return os.path.relpath(origem, ts_path).replace(os.sep, "/")
    base = (meta.get("caminho") or "").replace(os.sep, "/").rstrip("/")
    if not base:
        return os.path.relpath(origem, ts_path).replace(os.sep, "/")
    raiz_item = os.path.join(ts_path, os.path.basename(base))
    if not caminho_contido(origem, raiz_item):
        return base
    resto = os.path.relpath(origem, raiz_item).replace(os.sep, "/")
    if resto in (".", ""):
        return base
    return base + "/" + resto

def listar_conteudo_lixeira(rel):
    """Lista o conteudo de uma pasta dentro da lixeira (navegacao na interface)."""
    lixeira_raiz = raiz_lixeira()
    if not lixeira_raiz or not rel:
        return []
    alvo = os.path.abspath(os.path.join(lixeira_raiz, rel.replace("/", os.sep)))
    if not caminho_contido(alvo, lixeira_raiz) or not os.path.isdir(alvo):
        return []
    itens = []
    for nome in os.listdir(alvo):
        full = os.path.join(alvo, nome)
        e_dir = os.path.isdir(full)
        itens.append({
            "id": os.path.relpath(full, lixeira_raiz).replace(os.sep, "/"),
            "nome": nome,
            "original": nome,
            "tipo": "dir" if e_dir else "file",
        })
    itens.sort(key=lambda x: (not x["tipo"] == "dir", x["nome"].lower()))
    return itens

def limpar_dirs_vazios(caminho, limite):
    while caminho and caminho != limite and os.path.isdir(caminho) and not os.listdir(caminho):
        os.rmdir(caminho)
        caminho = os.path.dirname(caminho)

def limpar_item_lixeira_vazio(lixeira_raiz, ts_dir):
    """Remove o diretorio de uma operacao da lixeira quando fica sem conteudo.

    Chamada apos restaurar ou excluir definitivamente o ultimo item de uma
    operacao: apaga tambem o manifesto, que deixaria de ter dono.
    """
    ts_path = os.path.join(lixeira_raiz, ts_dir)
    if os.path.isdir(ts_path):
        if os.listdir(ts_path):
            return
        try:
            os.rmdir(ts_path)
        except OSError:
            return
    meta = _meta_lixeira_path(lixeira_raiz, ts_dir)
    if os.path.isfile(meta):
        try:
            os.remove(meta)
        except OSError:
            pass

def mover_para_lixeira(alvo):
    """Move um item removido para a lixeira do projeto em vez de apaga-lo.

    Cada exclusao ganha um diretorio proprio (timestamp) com apenas o item
    apagado, sob o nome original, e um manifesto com o caminho de origem. Assim
    uma pasta apagada continua a ser UMA pasta recuperavel na interface, em vez
    de aparecer como os seus arquivos soltos.
    """
    pasta_raiz = estado.get("pasta_raiz", "")
    if not pasta_raiz:
        return
    try:
        alvo = os.path.abspath(alvo)
        if not os.path.exists(alvo):
            return
        lixeira_raiz = raiz_lixeira()
        if not lixeira_raiz:
            return
        rel = os.path.relpath(alvo, pasta_raiz).replace(os.sep, "/")
        ts_dir = str(int(time.time() * 1000))
        while os.path.exists(os.path.join(lixeira_raiz, ts_dir)):
            ts_dir = str(int(ts_dir) + 1)
        tipo = "dir" if os.path.isdir(alvo) else "file"
        destino = os.path.join(lixeira_raiz, ts_dir, os.path.basename(rel))
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.move(alvo, destino)
        _gravar_meta_lixeira(lixeira_raiz, ts_dir, rel, tipo)
    except OSError as e:
        print(f"Erro ao mover para lixeira {alvo}: {e}")

def _enviar_lote_lixeira_sistema(caminhos):
    """Envia uma lista de caminhos para a Lixeira do sistema numa so chamada.

    No Windows monta um unico script PowerShell com uma remocao por item, para
    nao arrancar um processo por ficheiro; em outros sistemas remove
    diretamente. Retorna True quando todos os caminhos deixaram de existir.
    """
    caminhos = [os.path.abspath(c) for c in caminhos if os.path.exists(c)]
    if not caminhos:
        return True
    if sys.platform == "win32":
        try:
            partes = ["Add-Type -AssemblyName Microsoft.VisualBasic;"]
            for caminho in caminhos:
                metodo = "DeleteDirectory" if os.path.isdir(caminho) else "DeleteFile"
                partes.append(
                    "[Microsoft.VisualBasic.FileIO.FileSystem]::{metodo}('{p}',"
                    "'OnlyErrorDialogs','SendToRecycleBin');".format(
                        metodo=metodo, p=caminho.replace("'", "''")
                    )
                )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", "".join(partes)],
                check=False,
                timeout=180,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return all(not os.path.exists(c) for c in caminhos)
        except Exception as e:
            print(f"Erro ao enviar para lixeira do sistema: {e}")
            return False
    ok = True
    for caminho in caminhos:
        try:
            if os.path.isdir(caminho):
                shutil.rmtree(caminho)
            else:
                os.remove(caminho)
        except OSError as e:
            print(f"Erro ao remover {caminho}: {e}")
            ok = False
    return ok

def enviar_para_lixeira_sistema(caminho):
    """Envia um item da lixeira do projeto para a Lixeira do sistema operacional.

    No Windows usa a API do VisualBasic (Shell) via PowerShell; em outros
    sistemas remove diretamente (fallback). Retorna True se o item sumiu.
    """
    return _enviar_lote_lixeira_sistema([caminho])

def limpar_lixeira():
    """Esvazia a lixeira do projeto enviando tudo para a Lixeira do sistema.

    Cada operacao guarda os seus itens de topo; uma so invocacao do PowerShell
    trata de todos. Devolve a quantidade de operacoes processadas.
    """
    lixeira_raiz = raiz_lixeira()
    if not lixeira_raiz or not os.path.isdir(lixeira_raiz):
        return 0
    operacoes = []
    alvos = []
    for ts_dir in sorted(os.listdir(lixeira_raiz)):
        ts_path = os.path.join(lixeira_raiz, ts_dir)
        if not os.path.isdir(ts_path):
            continue
        operacoes.append(ts_dir)
        alvos.extend(os.path.join(ts_path, nome) for nome in sorted(os.listdir(ts_path)))
    if alvos:
        _enviar_lote_lixeira_sistema(alvos)
    for ts_dir in operacoes:
        limpar_item_lixeira_vazio(lixeira_raiz, ts_dir)
    return len(operacoes)
