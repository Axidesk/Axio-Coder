"""A arvore do projeto como o Visual Studio a ve: o .sln, o .vcxproj e o .vcxproj.filters.

O proprio Visual Studio escreve a arrumacao da arvore dele em texto: o `.vcxproj` diz QUE ficheiros
pertencem ao projeto e o `.vcxproj.filters` diz em que pasta virtual cada um fica (Source Files,
Header Files, Resource Files). Ler os dois e a mesma ideia da File API do CMake: a arrumacao vem do
projeto, nao de um palpite pela extensao dos ficheiros, e no disco nao se toca.
https://learn.microsoft.com/en-us/cpp/build/reference/vcxproj-filters-files
https://learn.microsoft.com/en-us/visualstudio/msbuild/msbuild-project-file-schema-reference

Nao confundir com a File API do MSBuild (`msbuild -getItem`), que le os itens DEPOIS de avaliar as
condicoes do projeto: aqui le-se o texto, que chega para a arrumacao e nao exige o Visual Studio
instalado nem uma compilacao previa.
"""

import os
import xml.etree.ElementTree as ET

GRUPOS_DE_OMISSAO = (
    ("Source Files", (
        "cpp", "c", "cc", "cxx", "def", "odl", "idl", "hpj", "bat", "asm", "asmx",
    )),
    ("Header Files", ("h", "hh", "hpp", "hxx", "hm", "inl", "inc", "xsd")),
    ("Resource Files", (
        "rc", "ico", "cur", "bmp", "dlg", "rc2", "rct", "bin", "rgs", "gif", "jpg",
        "jpeg", "jpe", "resx", "tiff", "tif", "png", "wav", "mfcribbon-ms",
    )),
)

EXTENSOES_DE_CODIGO = (
    "c", "cc", "cpp", "cxx", "h", "hh", "hpp", "hxx", "inl", "ipp", "tpp", "m", "mm",
)

_ELEMENTOS = (
    "ClCompile", "ClInclude", "ResourceCompile", "None", "Text", "Image", "Natvis",
    "Manifest", "Midl", "CustomBuild",
)

_TIPOS = {
    "Application": "aplicacao",
    "StaticLibrary": "biblioteca estatica",
    "DynamicLibrary": "biblioteca partilhada",
    "Makefile": "makefile",
    "Utility": "utilitario",
}


def projetos(pasta):
    """Projetos do Visual Studio nesta pasta, com as fontes arrumadas como o proprio VS arruma."""
    saida = []
    for caminho in _vcxprojs(pasta):
        projeto = _projeto(caminho)
        if projeto and projeto["grupos"]:
            saida.append(projeto)
    return saida


def grupos_soltos(pasta):
    """Pasta de codigo sem projeto nenhum: agrupa pelo tipo, como o VS faria ao criar um projeto la."""
    try:
        nomes = sorted(os.listdir(pasta))
    except OSError:
        return []
    ficheiros = [
        n for n in nomes
        if os.path.isfile(os.path.join(pasta, n))
        and _grupo_por_extensao(n, {}) != "Outros"
    ]
    if not ficheiros:
        return []
    return agrupar_por_tipo(ficheiros, {}, {})


def _vcxprojs(pasta):
    """Os .vcxproj que compoem a solucao; sem solucao, o .vcxproj solto da propria pasta."""
    try:
        nomes = sorted(os.listdir(pasta))
    except OSError:
        return []
    alvos = []
    for nome in nomes:
        if nome.lower().endswith(".sln"):
            alvos += _do_sln(os.path.join(pasta, nome))
    if not alvos:
        alvos = [os.path.join(pasta, n) for n in nomes if n.lower().endswith(".vcxproj")]
    return [a for a in _unicos(alvos) if os.path.isfile(a)]


def _do_sln(caminho):
    """Os caminhos dos .vcxproj declarados na solucao (linhas `Project(...) = "Nome", "Ficheiro"`)."""
    base = os.path.dirname(caminho)
    alvos = []
    for linha in _linhas(caminho):
        if not linha.lstrip().startswith("Project("):
            continue
        pedacos = linha.split('"')
        if len(pedacos) > 5 and pedacos[5].lower().endswith(".vcxproj"):
            alvos.append(os.path.normpath(os.path.join(base, pedacos[5])))
    return alvos


def _projeto(caminho):
    arvore = _ler(caminho)
    if arvore is None:
        return None
    ficheiros = _ficheiros(arvore)
    atribuicao, extensoes = _filtros(os.path.isfile(caminho + ".filters") and caminho + ".filters")
    grupos = agrupar_por_tipo(ficheiros, atribuicao, extensoes)
    nome = (
        _texto(arvore, "ProjectName")
        or _texto(arvore, "RootNamespace")
        or os.path.splitext(os.path.basename(caminho))[0]
    )
    tipo = _texto(arvore, "ConfigurationType")
    return {"nome": nome, "tipo": tipo, "detalhe": _TIPOS.get(tipo, "projeto"), "grupos": grupos}


def _ficheiros(arvore):
    """Os ficheiros do projeto, pela ordem em que o .vcxproj os declara."""
    saida = []
    for elemento in arvore.iter():
        if _local(elemento.tag) not in _ELEMENTOS:
            continue
        caminho = elemento.get("Include")
        if caminho:
            saida.append(_normalizar(caminho))
    return _unicos(saida)


def _filtros(caminho):
    """Onde cada ficheiro fica (pelo .vcxproj.filters) e que extensoes cada filtro leva."""
    arvore = _ler(caminho) if caminho else None
    if arvore is None:
        return {}, {}
    atribuicao = {}
    extensoes = {}
    for elemento in arvore.iter():
        nome = _local(elemento.tag)
        if nome == "Filter" and elemento.get("Include"):
            extensoes[elemento.get("Include")] = _extensoes_do_filtro(elemento)
        elif nome in _ELEMENTOS and elemento.get("Include"):
            filtro = _filho_texto(elemento, "Filter")
            if filtro:
                atribuicao[_normalizar(elemento.get("Include"))] = filtro
    return atribuicao, extensoes


def _extensoes_do_filtro(elemento):
    texto = _filho_texto(elemento, "Extensions")
    return {e.strip().lower() for e in texto.split(";") if e.strip()}


_ORDEM = {"Source Files": 0, "Header Files": 1, "Resource Files": 2, "Outros": 3}


def _grupo_por_extensao(ficheiro, extensoes):
    extensao = _extensao(ficheiro)
    for grupo, declaradas in extensoes.items():
        if extensao in declaradas:
            return grupo
    for grupo, declaradas in GRUPOS_DE_OMISSAO:
        if extensao in declaradas:
            return grupo
    return "Outros"


def agrupar_por_tipo(ficheiros, atribuicao, extensoes):
    """Grupos por filtro declarado; sem filtro, pela extensao. 'Outros' fecha a lista.

    Os filtros que o projeto DECLARA entram mesmo sem ficheiros: o Solution Explorer
    mostra o no vazio (o Tibia74 declara 'Resource Files' e nao tem la nada), e esconder
    um no que o projeto pediu dava uma arvore que nao bate com a do Visual Studio.

    Serve tambem quem agrupa sem projeto nenhum (arvore.py, no CMake ainda nao
    configurado): nesse caso `atribuicao` e `extensoes` vao vazios e a extensao decide.
    """
    por_grupo = {}
    for ficheiro in ficheiros:
        grupo = atribuicao.get(ficheiro) or _grupo_por_extensao(ficheiro, extensoes)
        por_grupo.setdefault(grupo, []).append(ficheiro)
    for declarado in extensoes:
        por_grupo.setdefault(declarado, [])
    nomes = sorted(por_grupo, key=lambda g: (_ORDEM.get(g, 1), g.lower()))
    return [{"nome": nome, "ficheiros": por_grupo[nome]} for nome in nomes]


def _texto(arvore, nome):
    for elemento in arvore.iter():
        if _local(elemento.tag) == nome and (elemento.text or "").strip():
            return elemento.text.strip()
    return ""


def _filho_texto(elemento, nome):
    for filho in elemento:
        if _local(filho.tag) == nome and (filho.text or "").strip():
            return filho.text.strip()
    return ""


def _local(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def _normalizar(caminho):
    trocado = (caminho or "").replace("\\", "/")
    return os.path.normpath(trocado).replace("\\", "/") if trocado else ""


def _extensao(nome):
    return os.path.splitext(nome)[1].lstrip(".").lower()


def _linhas(caminho):
    try:
        with open(caminho, "r", encoding="utf-8-sig", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


def _ler(caminho):
    if not caminho or not os.path.isfile(caminho):
        return None
    try:
        return ET.parse(caminho).getroot()
    except (OSError, ET.ParseError):
        return None


def _unicos(itens):
    vistos = set()
    saida = []
    for item in itens:
        if item in vistos:
            continue
        vistos.add(item)
        saida.append(item)
    return saida
