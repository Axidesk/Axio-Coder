import importlib
import os
import sys

from src.backend.state import estado

MODELOS = {}
PASTA_PADRAO = "gerados"


def registrar(nome, ficha):
    """Cada pasta de modelo chama isto ao ser importada."""
    MODELOS[nome] = ficha


def nomes():
    return sorted(MODELOS)


def pasta_existe(pasta=PASTA_PADRAO):
    raiz = estado.get("pasta_raiz", "")
    return bool(raiz) and os.path.isdir(os.path.join(raiz, pasta))


def destino_padrao(nome, pasta=PASTA_PADRAO):
    """Caminho relativo onde um modelo grava quando nao se indica destino."""
    return f"{pasta}/{nome}/{nome}"


def carregar(pasta=PASTA_PADRAO):
    """Importa cada pasta de modelo da pasta indicada e devolve (carregados, falhas)."""
    if not pasta_existe(pasta):
        return [], []
    raiz = estado.get("pasta_raiz", "")
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    caminho = os.path.join(raiz, pasta)
    prefixo = pasta.replace("\\", "/").strip("/").replace("/", ".")
    carregados, falhas = [], []
    for nome in sorted(os.listdir(caminho)):
        if not os.path.isfile(os.path.join(caminho, nome, "modelo.py")):
            continue
        pacote = f"{prefixo}.{nome}" if prefixo else nome
        _esquecer(pacote)
        try:
            importlib.import_module(pacote)
        except Exception as falha:
            falhas.append(f"{nome}: {falha}")
        else:
            carregados.append(nome)
    return carregados, falhas


def _esquecer(pacote):
    for chave in [c for c in sys.modules if c == pacote or c.startswith(pacote + ".")]:
        del sys.modules[chave]
