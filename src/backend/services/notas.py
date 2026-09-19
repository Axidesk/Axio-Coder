"""Notas do projeto: o caderno do utilizador na janela de informacoes.

Nao confundir com as notas de knowledge (memory/store.py), que sao memoria do
agente curada por ele. O que vive aqui e o caderno DO UTILIZADOR: o que ele
escreve e guardado tal e qual, sem interpretacao nenhuma, e volta a estar la na
proxima vez que abrir o programa.

O ficheiro e um por projeto, em `.axio/notas.json` - dentro do estado por-projeto
(como as etiquetas), nunca no codigo: nota nao e codigo, logo fica fora da arvore
do editor e fora do registo de restauro das sessoes. O documento tem as varias
notas (abas, cada uma com titulo e texto) e qual delas estava aberta.

Grava-se o documento INTEIRO, de forma atomica: quem grava manda o estado completo
e nao um remendo, para o ficheiro nunca poder ficar com metade das abas de uma
versao e metade de outra.
"""

import json
import os
import time

from src.backend.services.persistencia import gravar_json_atomico
from src.backend.state import caminho_estado_projeto

NOME_FICHEIRO = "notas.json"

NOME_ANTIGO = "notas.md"

TITULO_PADRAO = "Nota 1"
MAX_TITULO = 60
MAX_ABAS = 60
MAX_CHARS_ABA = 500000


def _caminho():
    return caminho_estado_projeto(NOME_FICHEIRO)


def _caminho_antigo():
    return caminho_estado_projeto(NOME_ANTIGO)


def _id_novo(usados):
    """Id livre para uma aba que chegou sem id (ou com um id ja usado)."""
    base = "n" + format(int(time.time() * 1000), "x")
    ident = base
    contador = 1
    while ident in usados:
        ident = f"{base}_{contador}"
        contador += 1
    return ident


def _titulo(valor, indice):
    titulo = " ".join(str(valor or "").split())[:MAX_TITULO]
    return titulo or f"Nota {indice}"


def _normalizar(dados):
    """Documento valido sempre: uma aba pelo menos, ids unicos, `ativa` a existir.

    Nao confia no que chega (vem do browser) mas tambem nao recusa nada: o TEXTO e
    a unica coisa aqui que nao se pode perder, logo um campo em falta nunca o leva
    com ele - e substituido por um valor por omissao.
    """
    dados = dados if isinstance(dados, dict) else {}
    bruto = dados.get("abas") if isinstance(dados.get("abas"), list) else []
    abas = []
    usados = set()
    for item in bruto[:MAX_ABAS]:
        if not isinstance(item, dict):
            continue
        ident = str(item.get("id") or "").strip()
        if not ident or ident in usados:
            ident = _id_novo(usados)
        usados.add(ident)
        abas.append({
            "id": ident,
            "titulo": _titulo(item.get("titulo"), len(abas) + 1),
            "texto": str(item.get("texto") or "")[:MAX_CHARS_ABA],
        })
    if not abas:
        ident = _id_novo(usados)
        abas = [{"id": ident, "titulo": TITULO_PADRAO, "texto": ""}]
    ativa = str(dados.get("ativa") or "").strip()
    if ativa not in {aba["id"] for aba in abas}:
        ativa = abas[0]["id"]
    return {"abas": abas, "ativa": ativa}


def _ler_do_disco():
    """Documento gravado, ou None quando nao existe (ou nao se consegue ler)."""
    caminho = _caminho()
    if not caminho or not os.path.exists(caminho):
        return None
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return _normalizar(json.load(f))
    except (OSError, json.JSONDecodeError):
        return None


def _nota_antiga():
    """Texto da nota unica da versao anterior ("" se nao houver nada)."""
    caminho = _caminho_antigo()
    if not caminho or not os.path.exists(caminho):
        return ""
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def gravar_notas(dados):
    """Grava o documento do projeto aberto e devolve-o normalizado."""
    documento = _normalizar(dados)
    caminho = _caminho()
    if not caminho:
        return documento
    gravar_json_atomico(caminho, documento)
    return documento


def ler_notas():
    """Documento das notas do projeto aberto: as abas e a que estava aberta."""
    documento = _ler_do_disco()
    if documento is not None:
        return documento
    return gravar_notas({"abas": [{"titulo": TITULO_PADRAO, "texto": _nota_antiga()}]})
