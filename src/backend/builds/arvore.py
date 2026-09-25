"""A arvore do projeto como o sistema de build a ve, para o explorer mostrar agrupado.

Quem sabe onde cada ficheiro fica e o proprio projeto, nunca a extensao do nome: o CMake responde pela
File API (`sourceGroups`) e o Visual Studio escreve os filtros no `.vcxproj.filters`. Ler essa
declaracao permite mostrar a MESMA arrumacao que o Qt Creator e o Solution Explorer mostram, sem mover
um unico ficheiro do disco. Uma pasta de codigo sem projeto nenhum e agrupada pelo tipo, como o Visual
Studio faria ao criar um projeto la.

Nada aqui toca no disco: sao caminhos virtuais com o prefixo `@arvore`, resolvidos pela rota
`/api/explorer` (routes/editor.py).
"""

import os

from src.backend.builds import cmake_api, detetar, msbuild

PREFIXO = "@arvore"
MAX_FICHEIROS = 3000
PROFUNDIDADE_DA_MARCA = 3

_ROTULOS = {
    "Source Files": "Fontes",
    "Header Files": "Cabecalhos",
    "Resource Files": "Recursos",
    "CMake Rules": "Regras do CMake",
}

_TIPOS_CMAKE = {
    "EXECUTABLE": "aplicacao",
    "STATIC_LIBRARY": "biblioteca estatica",
    "SHARED_LIBRARY": "biblioteca partilhada",
    "MODULE_LIBRARY": "modulo",
    "OBJECT_LIBRARY": "biblioteca de objetos",
    "INTERFACE_LIBRARY": "biblioteca de interface",
    "LIBRARY": "biblioteca",
}

_cache = {}


def e_no_virtual(chave):
    return (chave or "").startswith(PREFIXO)


def entradas_raiz(pasta):
    """Nos de topo: um projeto (ou um grupo, quando a pasta nao tem projeto nenhum)."""
    return [_entrada(no, [no["nome"]]) for no in _nos(pasta)]


def entradas(pasta, chave):
    """Filhos de um no virtual: um projeto da os grupos, um grupo da os ficheiros."""
    partes = [p for p in (chave or "").split("/")[1:] if p]
    no = _descer(_nos(pasta), partes)
    if no is None:
        return []
    if no["filhos"]:
        return [_entrada(filho, partes + [filho["nome"]]) for filho in no["filhos"]]
    rotulos = _rotulos(no["ficheiros"])
    return [{"nome": rotulos[f], "tipo": "file", "path": f} for f in no["ficheiros"]]


def ficheiros_agrupados(pasta):
    """Ficheiros que a arvore mostra dentro de um grupo: saem da lista solta da raiz."""
    return {
        ficheiro
        for no in _nos(pasta)
        for ficheiro in _todos_os_ficheiros(no)
        if "/" not in ficheiro
    }


def _nos(pasta):
    caminho = os.path.abspath(pasta or "")
    chave = (caminho, _marca(caminho))
    if chave in _cache:
        return _cache[chave]
    nos = _montar(caminho)
    _cache.clear()
    _cache[chave] = nos
    return nos


def _montar(pasta):
    projetos = _projetos_cmake(pasta) + msbuild.projetos(pasta)
    if projetos:
        return [_do_projeto(p) for p in projetos]
    return [_do_grupo(g) for g in msbuild.grupos_soltos(pasta)]


def _projetos_cmake(pasta):
    """Alvos do CMake com as fontes agrupadas, pelo que o proprio CMake respondeu."""
    pasta_build = _pasta_com_resposta(pasta)
    if not pasta_build:
        return _projeto_por_texto(pasta)
    alvos = [_alvo_cmake(a) for a in cmake_api.alvos(pasta_build)]
    alvos = _sem_alvos_repetidos([a for a in alvos if a["grupos"]])
    alvos.sort(key=lambda a: (a["tipo"] != "EXECUTABLE", a["nome"].lower()))
    return alvos


def _alvo_cmake(dados):
    """So ficam os ficheiros do projeto: fora a arvore de build e o que o CMake gerou."""
    grupos = [
        {
            "nome": grupo["nome"],
            "ficheiros": [
                f["relativo"] for f in grupo["ficheiros"] if not f["externo"] and not f["gerado"]
            ],
        }
        for grupo in dados["grupos"]
    ]
    return {
        "nome": dados["nome"],
        "tipo": dados["tipo"],
        "detalhe": _TIPOS_CMAKE.get(dados["tipo"], "alvo"),
        "grupos": [g for g in grupos if g["ficheiros"]],
    }


def _projeto_por_texto(pasta):
    """O projeto como o CMakeLists o declara, para antes da primeira configuracao.

    So vale quando o CMakeLists declara UM alvo: com varios, os ficheiros de alvos
    diferentes apareceriam juntos e o no mentiria sobre a que alvo pertence cada um.
    Nesse caso nao ha no de projeto e a arvore fica como pasta, ate o CMake responder
    pela File API (que e quem sabe a pertenca real).
    """
    dados = detetar.detetar(pasta)
    if dados.get("tipo") != "cmake":
        return []
    alvos = dados.get("alvos") or []
    if len(alvos) != 1:
        return []
    ficheiros = _ficheiros_de_codigo(pasta, dados.get("pastas_de_build") or [])
    if not ficheiros:
        return []
    return [{
        "nome": dados.get("projeto") or alvos[0]["nome"],
        "tipo": alvos[0]["tipo"],
        "detalhe": _TIPOS_CMAKE.get(alvos[0]["tipo"], "projeto"),
        "grupos": msbuild.agrupar_por_tipo(ficheiros, {}, {}),
    }]


def _ficheiros_de_codigo(pasta, pastas_de_build):
    """Ficheiros de codigo sob a pasta, fora das pastas de build e das escondidas."""
    ignorar = {nome.lower() for nome in pastas_de_build}
    achados = []
    for raiz, pastas, ficheiros in os.walk(pasta):
        pastas[:] = [p for p in pastas if not p.startswith(".") and p.lower() not in ignorar]
        for nome in ficheiros:
            if os.path.splitext(nome)[1].lstrip(".").lower() in msbuild.EXTENSOES_DE_CODIGO:
                achados.append(_relativo(os.path.join(raiz, nome), pasta))
                if len(achados) >= MAX_FICHEIROS:
                    return sorted(achados)
    return sorted(achados)


def _relativo(caminho, base):
    return os.path.relpath(caminho, base).replace("\\", "/")


def _do_projeto(projeto):
    return {
        "nome": projeto["nome"],
        "detalhe": projeto.get("detalhe") or "projeto",
        "filhos": [
            {
                "nome": _rotulo(grupo["nome"]),
                "detalhe": "",
                "filhos": [],
                "ficheiros": list(grupo["ficheiros"]),
            }
            for grupo in projeto["grupos"]
        ],
        "ficheiros": [],
    }


def _do_grupo(grupo):
    return {
        "nome": _rotulo(grupo["nome"]),
        "detalhe": "",
        "filhos": [],
        "ficheiros": list(grupo["ficheiros"]),
    }


def _entrada(no, caminho):
    return {
        "nome": no["nome"],
        "tipo": "grupo",
        "path": f"{PREFIXO}/{'/'.join(caminho)}",
        "detalhe": no["detalhe"],
        "nivel": "projeto" if no["filhos"] else "grupo",
    }


def _descer(nos, partes):
    atual = None
    candidatos = nos
    for parte in partes:
        atual = next((n for n in candidatos if n["nome"] == parte), None)
        if atual is None:
            return None
        candidatos = atual["filhos"]
    return atual


def _rotulo(nome):
    return _ROTULOS.get(nome, nome or "Outros")


def _rotulos(ficheiros):
    """Nome curto, ou o caminho quando dois ficheiros do mesmo grupo tem o mesmo nome."""
    contagem = {}
    for ficheiro in ficheiros:
        nome = os.path.basename(ficheiro)
        contagem[nome] = contagem.get(nome, 0) + 1
    return {
        ficheiro: (os.path.basename(ficheiro) if contagem[os.path.basename(ficheiro)] == 1 else ficheiro)
        for ficheiro in ficheiros
    }


def _todos_os_ficheiros(no):
    return list(no["ficheiros"]) + [
        ficheiro for filho in no["filhos"] for ficheiro in _todos_os_ficheiros(filho)
    ]


def _sem_alvos_repetidos(alvos):
    """Um nome pode repetir-se na mesma configuracao; fica o que traz mais ficheiros."""
    melhores = {}
    for alvo in alvos:
        atual = melhores.get(alvo["nome"])
        if atual is None or _total(alvo) > _total(atual):
            melhores[alvo["nome"]] = alvo
    return list(melhores.values())


def _total(alvo):
    return sum(len(grupo["ficheiros"]) for grupo in alvo["grupos"])


def _pasta_com_resposta(pasta):
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


def _marca(pasta):
    """Tudo o que muda a arrumacao: os ficheiros de projeto, o indice do CMake e as pastas.

    As pastas entram ate `PROFUNDIDADE_DA_MARCA` niveis porque a arrumacao sem File API
    e montada a partir dos ficheiros que estao la dentro: sem elas, criar um ficheiro
    numa subpasta nao invalidava o cache e a arvore so mudava ao navegar para fora e voltar.
    """
    alvos = []
    try:
        alvos = [
            os.path.join(pasta, nome)
            for nome in os.listdir(pasta)
            if nome.lower().endswith((".sln", ".vcxproj", ".vcxproj.filters", ".pro", ".pri",
                                      "cmakelists.txt"))
        ]
    except OSError:
        pass
    pasta_build = _pasta_com_resposta(pasta)
    if pasta_build:
        alvos.append(cmake_api.ultimo_indice(pasta_build))
    marcas = [_mtime(caminho) for caminho in alvos]
    marcas.extend(_mtime(p) for p in _pastas_ate(pasta, PROFUNDIDADE_DA_MARCA))
    return tuple(sorted(marcas))


def _pastas_ate(pasta, profundidade):
    """A pasta e as subpastas ate N niveis, sem descer ao que nao interessa."""
    niveis = [pasta]
    atual = [pasta]
    for _ in range(max(0, profundidade)):
        seguinte = []
        for pai in atual:
            try:
                seguinte.extend(
                    os.path.join(pai, nome)
                    for nome in os.listdir(pai)
                    if not nome.startswith(".") and os.path.isdir(os.path.join(pai, nome))
                )
            except OSError:
                continue
        if not seguinte:
            break
        niveis.extend(seguinte)
        atual = seguinte
    return niveis


def _mtime(caminho):
    try:
        return os.path.getmtime(caminho)
    except OSError:
        return 0.0
