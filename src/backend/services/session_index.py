import json
import os
import threading
import time

from src.backend.services.session import ler_log_sessao, pasta_session_logs, ts_de_arquivo_log

CAMPOS_LEVES = ("id", "name", "title", "timestamp", "duration", "salvo", "commit", "commit_nome", "questions", "aiResponse")
VERSAO_INDICE = 3

_guarda_dos_bloqueios = threading.Lock()
_bloqueios = {}
_aquecendo = threading.Event()


def pasta_indices_sessao():
    pasta_logs = pasta_session_logs()
    if not pasta_logs:
        return ""
    return os.path.join(os.path.dirname(pasta_logs), "session_index")


def _caminho_indice(caminho_log):
    pasta_logs = os.path.dirname(caminho_log)
    return os.path.join(os.path.dirname(pasta_logs), "session_index", os.path.basename(caminho_log) + ".idx.json")


def _marca_do_log(caminho_log):
    info = os.stat(caminho_log)
    return [int(info.st_size), int(info.st_mtime)]


def _bloqueio_de(caminho):
    with _guarda_dos_bloqueios:
        return _bloqueios.setdefault(caminho, threading.Lock())


def projetar_rodada(grupo):
    """Reduz uma rodada ao que a lista e a busca precisam, sem o diff renderizado."""
    leve = {campo: grupo.get(campo) for campo in CAMPOS_LEVES}
    leve["questions"] = list(leve.get("questions") or [])
    leve["aiResponse"] = leve.get("aiResponse") or ""
    leve["salvo"] = bool(leve.get("salvo"))
    leve["files"] = [{"name": f.get("name"), "deleted": bool(f.get("deleted"))} for f in (grupo.get("files") or [])]
    leve["nFerramentas"] = len(grupo.get("tools") or [])
    return leve


def construir_indice_de_log(caminho_log, dados=None):
    dados = dados if dados is not None else ler_log_sessao(caminho_log)
    indice = {
        "versao": VERSAO_INDICE,
        "marca": _marca_do_log(caminho_log),
        "datetime": dados.get("datetime", ""),
        "rounds": [projetar_rodada(g) for g in (dados.get("logs") or [])],
    }
    caminho_indice = _caminho_indice(caminho_log)
    os.makedirs(os.path.dirname(caminho_indice), exist_ok=True)
    temporario = caminho_indice + ".tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(indice, f, ensure_ascii=False)
    os.replace(temporario, caminho_indice)
    return indice


def _indice_valido(caminho_log):
    caminho_indice = _caminho_indice(caminho_log)
    if not os.path.exists(caminho_indice):
        return None
    try:
        with open(caminho_indice, "r", encoding="utf-8") as f:
            indice = json.load(f)
        marca = _marca_do_log(caminho_log)
    except (OSError, ValueError):
        return None
    if indice.get("marca") != marca or indice.get("versao") != VERSAO_INDICE:
        return None
    return indice


def indice_de_log(caminho_log):
    """Indice leve da sessao: vem do cache em disco e so e reconstruido quando o log muda."""
    with _bloqueio_de(caminho_log):
        indice = _indice_valido(caminho_log)
        if indice is not None:
            return indice
        try:
            return construir_indice_de_log(caminho_log)
        except (OSError, ValueError):
            return None


def atualizar_indice_de_payload(caminho_log, dados):
    """Reescreve o indice com o payload que acabou de ser gravado, sem voltar a ler o log."""
    try:
        construir_indice_de_log(caminho_log, dados)
    except (OSError, ValueError):
        pass


def rodada_completa_de_log(pasta_logs, nome_log, turn_id):
    caminho_log = os.path.join(pasta_logs, os.path.basename(nome_log))
    dados = ler_log_sessao(caminho_log)
    snapshot_raiz = dados.get("snapshot") or {}
    for grupo in (dados.get("logs") or []):
        if str(grupo.get("id")) != str(turn_id):
            continue
        return {
            "id": grupo.get("id"),
            "files": grupo.get("files") or [],
            "snapshot": grupo.get("snapshot") or snapshot_raiz,
            "tools": grupo.get("tools") or [],
            "thoughts": grupo.get("thoughts") or [],
            "questions": grupo.get("questions") or [],
            "aiResponse": grupo.get("aiResponse") or "",
            "commit": grupo.get("commit") or "",
        }
    return None


def descartar_indices_orfaos():
    pasta_indices = pasta_indices_sessao()
    pasta_logs = pasta_session_logs()
    if not pasta_indices or not os.path.isdir(pasta_indices) or not pasta_logs:
        return 0
    try:
        nomes = [f for f in os.listdir(pasta_logs) if f.startswith("sessionlog_") and f.endswith(".json")]
    except OSError:
        return 0
    vivos = {nome + ".idx.json" for nome in nomes}
    removidos = 0
    try:
        indices = os.listdir(pasta_indices)
    except OSError:
        return 0
    for nome in indices:
        if nome in vivos:
            continue
        try:
            os.remove(os.path.join(pasta_indices, nome))
            removidos += 1
        except OSError:
            pass
    return removidos


def preaquecer_indices_de_sessao(intervalo=0.05):
    """Constroi em background os indices em falta, do log mais recente para o mais antigo."""
    if _aquecendo.is_set():
        return

    def _trabalho():
        try:
            pasta_logs = pasta_session_logs()
            if not pasta_logs or not os.path.isdir(pasta_logs):
                return
            descartar_indices_orfaos()
            try:
                arquivos = [f for f in os.listdir(pasta_logs) if f.startswith("sessionlog_") and f.endswith(".json")]
            except OSError:
                return
            arquivos.sort(key=ts_de_arquivo_log, reverse=True)
            for nome in arquivos:
                indice_de_log(os.path.join(pasta_logs, nome))
                time.sleep(intervalo)
        finally:
            _aquecendo.clear()

    _aquecendo.set()
    threading.Thread(target=_trabalho, daemon=True).start()
