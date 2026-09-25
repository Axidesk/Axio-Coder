"""A arvore do projeto como o sistema de build a ve, para o explorer mostrar agrupado.

Quem sabe onde cada ficheiro fica e o proprio projeto, nunca a extensao do nome: o CMake responde pela
File API (`sourceGroups`, os `directories` e o `cmakeFiles`) e o Visual Studio escreve os filtros no
`.vcxproj.filters`. Ler essa declaracao permite mostrar a MESMA arrumacao que o Qt Creator e o Solution
Explorer mostram, sem mover um unico ficheiro do disco: o projeto na raiz, as pastas pelo caminho que
ele proprio declara, cada alvo com os seus grupos de fontes e, quando o CMake os leu, os scripts do
projeto num no a parte. Uma pasta de codigo sem projeto nenhum e agrupada pelo tipo, como o Visual
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
    return [_entrada(no, [str(i)]) for i, no in enumerate(_nos(pasta))]


def tem_projeto(pasta):
    """Verdadeiro quando a arrumacao vem de um projeto: nesse caso a raiz mostra SO ele.

    E o que o Qt Creator e o Solution Explorer fazem: a vista de projeto mostra o que o
    projeto declara, e os ficheiros que vivem na pasta sem pertencer a nenhum alvo
    (logs, .VC.db, ficheiros de build) ficam de fora. Sem projeto, a raiz continua a
    mostrar as pastas e a lista solta.
    """
    return any(no.get("projeto") for no in _nos(pasta))


def entradas(pasta, chave):
    """Filhos de um no virtual: os sub-nos e, nos grupos, os ficheiros que ele mostra."""
    partes = [p for p in (chave or "").split("/")[1:] if p]
    no = _descer(_nos(pasta), partes)
    if no is None:
        return []
    rotulos = _rotulos(no["ficheiros"])
    return [{"nome": rotulos[f], "tipo": "file", "path": f} for f in no["ficheiros"]] + [
        _entrada(filho, partes + [str(i)]) for i, filho in enumerate(no["filhos"])
    ]


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
    nos = _projetos_cmake(pasta) + _projetos_msbuild(pasta)
    if nos:
        return nos
    return [_no_grupo(g) for g in msbuild.grupos_soltos(pasta)]


def _projetos_cmake(pasta):
    """O projeto como o CMake o declara: a arvore de pastas com os alvos dentro de cada uma."""
    pasta_build = _pasta_com_resposta(pasta)
    estrutura = cmake_api.estrutura(pasta_build) if pasta_build else {}
    if not estrutura:
        return _projeto_por_texto(pasta)
    return [_no_cmake(pasta, estrutura, pasta_build)]


def _no_cmake(pasta, estrutura, pasta_build):
    origem = estrutura["origem"]
    pastas = {}
    _pasta_virtual(pastas, "")
    for diretorio in estrutura["directorios"]:
        no = _pasta_virtual(pastas, diretorio["pasta"])
        alvos = _sem_alvos_repetidos([a for a in diretorio["alvos"] if a["grupos"]])
        alvos.sort(key=lambda a: (a["tipo"] != "EXECUTABLE", a["nome"].lower()))
        no["alvos"].extend(alvos)
    raiz = _fechar_no(pastas[""], pasta, origem)
    modulos = _no_dos_modulos(pasta_build, pasta, origem)
    if modulos:
        raiz["filhos"].append(modulos)
    return {
        "nome": estrutura.get("nome") or os.path.basename(pasta),
        "detalhe": "projeto",
        "projeto": True,
        "filhos": raiz["filhos"],
        "ficheiros": raiz["ficheiros"],
    }


def _pasta_virtual(pastas, caminho):
    """No da pasta `caminho` (relativa, com `/`), criando as maes que faltarem.

    A File API so lista as pastas que tem `CMakeLists.txt`; as que so existem no caminho
    de outra (`libs`, acima de `libs/libdxfrw`) entram por aqui, ou a arvore ficava plana.
    """
    if "" not in pastas:
        pastas[""] = {
            "nome": "", "detalhe": "", "filhos": [], "alvos": [], "ficheiros": [], "_rel": ""
        }
    atual = pastas[""]
    acumulado = ""
    for parte in _partes_do_caminho(caminho):
        acumulado = f"{acumulado}/{parte}" if acumulado else parte
        if acumulado not in pastas:
            filho = {
                "nome": parte,
                "detalhe": acumulado,
                "pasta": True,
                "filhos": [],
                "alvos": [],
                "ficheiros": [],
                "_rel": acumulado,
            }
            pastas[acumulado] = filho
            atual["filhos"].append(filho)
        atual = pastas[acumulado]
    return atual


def _partes_do_caminho(caminho):
    return [p for p in (caminho or "").replace("\\", "/").split("/") if p and p != "."]


def _fechar_no(no, pasta, origem):
    """Fecha o no: alvos e subpastas como filhos, o CMakeLists da pasta como ficheiro."""
    rel = no.pop("_rel", "")
    alvos = [a for a in (_no_do_alvo(alvo, pasta, origem) for alvo in no.pop("alvos", [])) if a]
    no["filhos"] = alvos + [_fechar_no(filho, pasta, origem) for filho in no["filhos"]]
    manifesto = _manifesto_da_pasta(pasta, origem, rel)
    no["ficheiros"] = [manifesto] if manifesto else []
    return no


def _no_do_alvo(alvo, pasta, origem):
    """Um alvo do CMake com os grupos de fontes que ele declara, fora o que o CMake gerou."""
    grupos = [
        _no_grupo({
            "nome": grupo["nome"],
            "ficheiros": [
                _relativo_ao_projeto(f["relativo"], pasta, origem)
                for f in grupo["ficheiros"]
                if not f["externo"] and not f["gerado"]
            ],
        })
        for grupo in alvo["grupos"]
    ]
    grupos = [g for g in grupos if _todos_os_ficheiros(g)]
    if not grupos:
        return None
    return {
        "nome": alvo["nome"],
        "detalhe": _TIPOS_CMAKE.get(alvo["tipo"], "alvo"),
        "alvo": True,
        "filhos": grupos,
        "ficheiros": [],
    }


def _no_dos_modulos(pasta_build, pasta, origem):
    """Os scripts do CMake do projeto, agrupados pelas pastas onde vivem."""
    ficheiros = [
        _relativo_ao_projeto(m, pasta, origem) for m in cmake_api.modulos_do_projeto(pasta_build)
    ]
    if not ficheiros:
        return None
    pastas = {}
    _pasta_virtual(pastas, "")
    raiz = pastas[""]
    for ficheiro in ficheiros:
        mae = ficheiro.rsplit("/", 1)[0] if "/" in ficheiro else ""
        _pasta_virtual(pastas, mae)["ficheiros"].append(ficheiro)
    raiz["nome"] = "Modulos do CMake"
    raiz["detalhe"] = "scripts do projeto"
    return _podar(raiz)


def _podar(no):
    no.pop("alvos", None)
    no.pop("_rel", None)
    no["filhos"] = [_podar(filho) for filho in no["filhos"]]
    return no


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
    manifesto = "CMakeLists.txt" if os.path.isfile(os.path.join(pasta, "CMakeLists.txt")) else ""
    return [{
        "nome": dados.get("projeto") or alvos[0]["nome"],
        "detalhe": "projeto",
        "projeto": True,
        "ficheiros": [manifesto] if manifesto else [],
        "filhos": [{
            "nome": alvos[0]["nome"],
            "detalhe": _TIPOS_CMAKE.get(alvos[0]["tipo"], "alvo"),
            "alvo": True,
            "filhos": [_no_grupo(g) for g in msbuild.agrupar_por_tipo(ficheiros, {}, {})],
            "ficheiros": [],
        }],
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


def _relativo_ao_projeto(relativo, pasta, origem):
    """O caminho do ficheiro visto da pasta aberta: e por ele que a arvore o abre."""
    if not origem or not relativo:
        return relativo
    absoluto = os.path.join(origem, relativo)
    return _relativo(absoluto, pasta) if _caminho_dentro(absoluto, pasta) else relativo


def _caminho_dentro(caminho, raiz):
    absoluto = os.path.normcase(os.path.abspath(caminho))
    base = os.path.normcase(os.path.abspath(raiz))
    return absoluto == base or absoluto.startswith(base + os.sep)


def _manifesto_da_pasta(pasta, origem, rel):
    """O CMakeLists.txt daquela pasta, quando existe: o Qt Creator mostra-o ao lado dos alvos."""
    if not origem:
        return ""
    absoluto = os.path.join(origem, rel, "CMakeLists.txt") if rel else os.path.join(
        origem, "CMakeLists.txt"
    )
    if not os.path.isfile(absoluto) or not _caminho_dentro(absoluto, pasta):
        return ""
    return _relativo(absoluto, pasta)


def _projetos_msbuild(pasta):
    return [
        {
            "nome": projeto["nome"],
            "detalhe": projeto.get("detalhe") or "projeto",
            "projeto": True,
            "filhos": [_no_grupo(grupo) for grupo in projeto["grupos"]],
            "ficheiros": [],
        }
        for projeto in msbuild.projetos(pasta)
    ]


def _no_grupo(grupo):
    """Um grupo do projeto; um filtro aninhado ('Source Files\\nucleo') vira pastas."""
    partes = [p for p in (grupo["nome"] or "").replace("/", "\\").split("\\") if p] or ["Outros"]
    partes[0] = _rotulo(partes[0])
    no = {"nome": partes[-1], "detalhe": "", "filhos": [], "ficheiros": list(grupo["ficheiros"])}
    for parte in reversed(partes[:-1]):
        no = {"nome": parte, "detalhe": "", "filhos": [no], "ficheiros": []}
    return no


def _entrada(no, caminho):
    return {
        "nome": no["nome"],
        "tipo": "grupo",
        "path": f"{PREFIXO}/{'/'.join(caminho)}",
        "detalhe": no["detalhe"],
        "nivel": _nivel(no),
    }


def _nivel(no):
    for marca in ("projeto", "alvo", "pasta"):
        if no.get(marca):
            return marca
    return "grupo"


def _descer(nos, partes):
    atual = None
    candidatos = nos
    for parte in partes:
        if not parte.isdigit() or int(parte) >= len(candidatos):
            return None
        atual = candidatos[int(parte)]
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
