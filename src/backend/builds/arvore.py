"""A arvore do projeto como o CMake a ve, para o explorer mostrar agrupado sem tocar no disco.

Os grupos saem da File API - os `sourceGroups` que o proprio CMake atribui - e nao de um palpite
pela extensao dos ficheiros. E a mesma fonte que o Qt Creator usa para desenhar a arvore dele, o
que permite mostrar a MESMA arrumacao sem mover um unico ficheiro do projeto.
"""

import os

from src.backend.builds import cmake_api

PREFIXO = "@arvore"
GRUPO_DE_OUTROS = "Outros"

_ROTULOS = {
    "Source Files": "Fontes",
    "Header Files": "Cabecalhos",
    "CMake Rules": "Regras do CMake",
}

_TIPOS = {
    "EXECUTABLE": "aplicacao",
    "STATIC_LIBRARY": "biblioteca estatica",
    "SHARED_LIBRARY": "biblioteca partilhada",
    "MODULE_LIBRARY": "modulo",
    "OBJECT_LIBRARY": "biblioteca de objetos",
    "INTERFACE_LIBRARY": "biblioteca de interface",
}

_cache = {}


def pasta_com_resposta(pasta):
    """Arvore de build, das que o Axio criou, que ja tem resposta da File API."""
    candidatos = []
    for nome in ("build", "out"):
        base = os.path.join(pasta, nome)
        if not os.path.isdir(base):
            continue
        for filho in sorted(os.listdir(base)):
            alvo = os.path.join(base, filho)
            if os.path.isdir(alvo) and cmake_api.ultimo_indice(alvo):
                candidatos.append(alvo)
    if not candidatos:
        return ""
    return max(candidatos, key=lambda c: _mtime(cmake_api.ultimo_indice(c)))


def grupos(pasta):
    """Os alvos do projeto com as fontes agrupadas, o executavel a frente."""
    pasta_build = pasta_com_resposta(pasta)
    if not pasta_build:
        return []
    marca = (pasta_build, _mtime(cmake_api.ultimo_indice(pasta_build)))
    if marca in _cache:
        return _cache[marca]
    alvos = [_alvo(a) for a in cmake_api.alvos(pasta_build)]
    alvos = _sem_alvos_repetidos([a for a in alvos if a["grupos"]])
    alvos.sort(key=lambda a: (a["tipo"] != "EXECUTABLE", a["nome"].lower()))
    _cache.clear()
    _cache[marca] = alvos
    return alvos


def e_no_virtual(chave):
    return (chave or "").startswith(PREFIXO)


def entradas_raiz(pasta):
    return [
        {
            "nome": alvo["nome"],
            "tipo": "grupo",
            "path": f"{PREFIXO}/{alvo['nome']}",
            "detalhe": alvo["detalhe"],
        }
        for alvo in grupos(pasta)
    ]


def entradas(pasta, chave):
    """Entradas de um no virtual da arvore: o alvo da os grupos, o grupo da os ficheiros."""
    partes = [p for p in (chave or "").split("/")[1:]]
    if not partes:
        return []
    alvos = grupos(pasta)
    alvo = next((a for a in alvos if a["nome"] == partes[0]), None)
    if alvo is None:
        return []
    if len(partes) == 1:
        return [
            {"nome": _rotulo(g["nome"]), "tipo": "grupo", "path": f"{chave}/{chave_do_grupo(g['nome'])}"}
            for g in alvo["grupos"]
        ]
    procurado = "/".join(partes[1:])
    grupo = next((g for g in alvo["grupos"] if chave_do_grupo(g["nome"]) == procurado), None)
    if grupo is None:
        return []
    return [
        {"nome": os.path.basename(f["relativo"]), "tipo": "file", "path": f["relativo"]}
        for f in grupo["ficheiros"]
    ]


def chave_do_grupo(nome):
    return nome or GRUPO_DE_OUTROS


def _rotulo(nome):
    return _ROTULOS.get(nome, nome or GRUPO_DE_OUTROS)


def _alvo(dados):
    """So ficam os ficheiros do projeto: fora a arvore de build e o que o CMake gerou."""
    grupos = [
        {
            "nome": g["nome"],
            "ficheiros": [f for f in g["ficheiros"] if not f["externo"] and not f["gerado"]],
        }
        for g in dados["grupos"]
    ]
    return {
        "nome": dados["nome"],
        "tipo": dados["tipo"],
        "detalhe": _TIPOS.get(dados["tipo"], "alvo"),
        "exe": dados["artefactos"][0] if dados["artefactos"] else "",
        "grupos": [g for g in grupos if g["ficheiros"]],
    }


def _sem_alvos_repetidos(alvos):
    """Um nome pode repetir-se na mesma configuracao; fica o que traz mais ficheiros."""
    melhores = {}
    for alvo in alvos:
        atual = melhores.get(alvo["nome"])
        if atual is None or _total(alvo) > _total(atual):
            melhores[alvo["nome"]] = alvo
    return list(melhores.values())


def _total(alvo):
    return sum(len(g["ficheiros"]) for g in alvo["grupos"])


def _mtime(caminho):
    try:
        return os.path.getmtime(caminho)
    except OSError:
        return 0.0
