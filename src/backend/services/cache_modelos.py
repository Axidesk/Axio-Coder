import hashlib
import json
import os
import threading

from src.backend.config import caminho_data

PASTA = caminho_data("cache_modelos")
LIMITE_BYTES = 512 * 1024 * 1024
_trava = threading.Lock()


def _chave(caminho):
    alvo = os.path.normcase(os.path.abspath(caminho))
    return hashlib.sha1(alvo.encode("utf-8")).hexdigest()


def _marca(caminho):
    try:
        estado = os.stat(caminho)
    except OSError:
        return None
    return {"mtime_ns": int(estado.st_mtime_ns), "tamanho": int(estado.st_size)}


def _ficheiros(chave):
    return os.path.join(PASTA, chave + ".frag"), os.path.join(PASTA, chave + ".json")


def ler(caminho):
    """Modelo convertido guardado, ou None quando nao ha cache da versao atual do ficheiro."""
    marca = _marca(caminho)
    if not marca:
        return None
    convertido, meta = _ficheiros(_chave(caminho))
    try:
        with open(meta, "r", encoding="utf-8") as f:
            guardada = json.load(f)
    except (OSError, ValueError):
        return None
    if guardada.get("mtime_ns") != marca["mtime_ns"] or guardada.get("tamanho") != marca["tamanho"]:
        return None
    return convertido if os.path.isfile(convertido) else None


def gravar(caminho, conteudo):
    marca = _marca(caminho)
    if not marca or not conteudo:
        return None
    os.makedirs(PASTA, exist_ok=True)
    convertido, meta = _ficheiros(_chave(caminho))
    parcial = convertido + ".parcial"
    with _trava:
        if not _gravar_bytes(parcial, convertido, conteudo):
            return None
        with open(meta, "w", encoding="utf-8") as f:
            json.dump({"origem": caminho, "bytes": len(conteudo), **marca}, f)
    return convertido


def _gravar_bytes(parcial, destino, conteudo):
    """Escreve o convertido; o os.replace cede a escrita no lugar quando o Windows recusa o destino aberto."""
    try:
        with open(parcial, "wb") as f:
            f.write(conteudo)
        os.replace(parcial, destino)
        return True
    except OSError:
        pass
    try:
        os.remove(parcial)
    except OSError:
        pass
    try:
        with open(destino, "wb") as f:
            f.write(conteudo)
        return True
    except OSError:
        return False


def limpar_excedente():
    """Apaga os modelos convertidos mais antigos ate o conjunto caber no limite. Devolve quantos sairam."""
    try:
        itens = []
        for nome in os.listdir(PASTA):
            if not nome.endswith(".frag"):
                continue
            alvo = os.path.join(PASTA, nome)
            try:
                estado = os.stat(alvo)
            except OSError:
                continue
            itens.append((estado.st_mtime, estado.st_size, alvo))
    except OSError:
        return 0
    total = sum(item[1] for item in itens)
    if total <= LIMITE_BYTES:
        return 0
    removidos = 0
    for _, tamanho, alvo in sorted(itens):
        if total <= LIMITE_BYTES:
            break
        try:
            os.remove(alvo)
            os.remove(alvo[:-5] + ".json")
        except OSError:
            continue
        total -= tamanho
        removidos += 1
    return removidos
