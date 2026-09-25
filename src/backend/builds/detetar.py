import os
import re

_TIPOS = (
    ("cmake", "CMake", ("CMakeLists.txt",), ()),
    ("msbuild", "Visual Studio (MSBuild)", (), (".sln", ".vcxproj", ".csproj")),
    ("qmake", "qmake (Qt)", (), (".pro", ".pri")),
    ("python", "Python", ("pyproject.toml", "setup.py", "requirements.txt"), ()),
    ("npm", "Node (npm)", ("package.json",), ()),
    ("cargo", "Rust (Cargo)", ("Cargo.toml",), ()),
    ("go", "Go", ("go.mod",), ()),
    ("make", "Make", ("Makefile", "makefile", "GNUmakefile"), ()),
)

_RE_FIND_PACKAGE = re.compile(r"find_package\s*\(\s*([A-Za-z0-9_]+)([^)]*)\)", re.DOTALL)
_RE_FIND_PROGRAM = re.compile(r"find_program\s*\(\s*([A-Za-z0-9_]+)\s+([^)]*)\)", re.DOTALL)
_RE_PREFIX_PATH = re.compile(r"set\s*\(\s*CMAKE_PREFIX_PATH\s+([^)]*)\)", re.DOTALL)
_RE_CXX_STANDARD = re.compile(r"set\s*\(\s*CMAKE_CXX_STANDARD\s+([0-9]+)")
_RE_COMPONENTS = re.compile(
    r"\bCOMPONENTS\b(.*?)(?=\b(?:REQUIRED|QUIET|OPTIONAL_COMPONENTS|CONFIG|MODULE|PATHS|HINTS|NO_MODULE|EXACT|GLOBAL)\b|$)",
    re.DOTALL,
)
_RE_PROJECT = re.compile(r"project\s*\(\s*([A-Za-z0-9_]+)")
_RE_ADD_SUBDIRECTORY = re.compile(r"add_subdirectory\s*\(\s*([A-Za-z0-9_./\\-]+)")
_RE_PALAVRAS_IGNORADAS = re.compile(r"[()\s\"']+")

_MAX_CMAKELISTS = 12


def detetar(pasta):
    """Le o que a pasta diz de si propria: que projeto e, o que exige e onde ja foi construido."""
    caminho = os.path.abspath(pasta or "")
    if not os.path.isdir(caminho):
        return {"erro": f"'{pasta}' nao e uma pasta."}
    nomes = _nomes(caminho)
    achados = [
        {"tipo": tipo, "rotulo": rotulo, "ficheiros": _provas(nomes, fixos, extensoes)}
        for tipo, rotulo, fixos, extensoes in _TIPOS
    ]
    achados = [a for a in achados if a["ficheiros"]]
    if not achados:
        return {
            "pasta": caminho,
            "tipo": "desconhecido",
            "rotulo": "sem projeto conhecido",
            "ficheiros": [],
            "tambem": [],
            "vertentes": [],
            "pacotes": [],
            "programas": [],
            "prefixos": [],
            "pastas_de_build": [],
        }
    principal = achados[0]
    dados = {
        "pasta": caminho,
        "tipo": principal["tipo"],
        "rotulo": principal["rotulo"],
        "ficheiros": principal["ficheiros"],
        "tambem": [a["tipo"] for a in achados[1:]],
        "vertentes": [],
        "pacotes": [],
        "programas": [],
        "prefixos": [],
        "pastas_de_build": _pastas_de_build(caminho),
    }
    if principal["tipo"] == "cmake":
        dados.update(_leitura_cmake(caminho, nomes))
        dados["vertentes"] = _vertentes(nomes, dados["pacotes"], dados["programas"])
    return dados


def _nomes(caminho):
    try:
        return sorted(os.listdir(caminho))
    except OSError:
        return []


def _provas(nomes, fixos, extensoes):
    prova = [n for n in nomes if n in fixos]
    prova += [n for n in nomes if any(n.lower().endswith(e) for e in extensoes)]
    return prova


def _pastas_de_build(caminho):
    return [
        nome
        for nome in ("build", "out", "cmake-build-debug", "cmake-build-release")
        if os.path.isdir(os.path.join(caminho, nome))
    ]


def _leitura_cmake(caminho, nomes):
    textos = _textos_cmake(caminho, nomes)
    pacotes = []
    programas = []
    prefixos = []
    padrao = ""
    projeto = ""
    for texto in textos:
        pacotes += _pacotes_do_texto(texto)
        programas += _programas_do_texto(texto)
        prefixos += _prefixos_do_texto(texto)
        if not projeto:
            achado = _RE_PROJECT.search(texto)
            if achado:
                projeto = achado.group(1)
        if not padrao:
            achado = _RE_CXX_STANDARD.search(texto)
            if achado:
                padrao = achado.group(1)
    return {
        "projeto": projeto,
        "pacotes": _sem_repetidos(pacotes, "nome"),
        "programas": _sem_repetidos(programas, "variavel"),
        "prefixos": _sem_repetidos(prefixos),
        "padrao_cxx": padrao,
        "cmakelists_lidos": len(textos),
        "tem_presets": "CMakePresets.json" in nomes,
    }


def _textos_cmake(caminho, nomes):
    alvos = [os.path.join(caminho, "CMakeLists.txt")]
    for nome in nomes:
        if len(alvos) >= _MAX_CMAKELISTS:
            break
        sub = os.path.join(caminho, nome)
        if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "CMakeLists.txt")):
            alvos.append(os.path.join(sub, "CMakeLists.txt"))
    textos = []
    for alvo in alvos:
        try:
            with open(alvo, "r", encoding="utf-8", errors="replace") as f:
                textos.append(f.read())
        except OSError:
            continue
    return textos


def _pacotes_do_texto(texto):
    pacotes = []
    for achado in _RE_FIND_PACKAGE.finditer(texto):
        nome = achado.group(1)
        if nome.lower() in ("python", "pkgconfig"):
            continue
        argumentos = achado.group(2)
        componentes = _RE_COMPONENTS.search(argumentos)
        nomes_componentes = []
        if componentes:
            nomes_componentes = [c for c in _RE_PALAVRAS_IGNORADAS.split(componentes.group(1)) if c.isidentifier()]
        pacotes.append({
            "nome": nome,
            "componentes": nomes_componentes,
            "obrigatorio": "REQUIRED" in argumentos.upper(),
        })
    return pacotes


def _programas_do_texto(texto):
    programas = []
    for achado in _RE_FIND_PROGRAM.finditer(texto):
        corpo = achado.group(2)
        nomes = []
        if "NAMES" in corpo.upper():
            depois = re.split(r"\bNAMES\b", corpo, flags=re.IGNORECASE)[1]
            antes = re.split(r"\b(?:DOC|PATHS|HINTS|REQUIRED)\b", depois, flags=re.IGNORECASE)[0]
            nomes = [n for n in _RE_PALAVRAS_IGNORADAS.split(antes) if n]
        programas.append({"variavel": achado.group(1), "nomes": nomes})
    return programas


def _prefixos_do_texto(texto):
    prefixos = []
    for achado in _RE_PREFIX_PATH.finditer(texto):
        for bruto in achado.group(1).split():
            limpo = bruto.strip("\"'")
            if limpo and not limpo.startswith("${") and limpo != "${CMAKE_PREFIX_PATH}":
                prefixos.append(limpo.replace("\\", "/").rstrip("/"))
    return prefixos


def _vertentes(nomes, pacotes, programas):
    vertentes = []
    for pacote in pacotes:
        nome = pacote["nome"]
        if re.match(r"^Qt[0-9]$", nome):
            vertentes.append(f"Qt {nome[2:]}")
        elif nome.lower() == "vulkan":
            vertentes.append("Vulkan")
    if any(n.lower().endswith(".qml") for n in nomes) or "qml.qrc" in nomes:
        vertentes.append("QML")
    if any(p["nomes"] and "glslc" in p["nomes"] for p in programas) or any(
        n.lower().endswith((".vert", ".frag", ".comp")) for n in nomes
    ):
        vertentes.append("shaders")
    return vertentes


def _sem_repetidos(itens, chave=None):
    vistos = set()
    saida = []
    for item in itens:
        marca = item[chave] if chave else item
        if marca in vistos:
            continue
        vistos.add(marca)
        saida.append(item)
    return saida


def exigencia_de(pacotes, prefixo):
    """Primeiro pacote cujo nome comeca por 'prefixo' (Qt6 -> Qt), ou None."""
    for pacote in pacotes:
        if pacote["nome"].lower().startswith(prefixo.lower()):
            return pacote
    return None


def versao_pedida(pacote):
    """Numero do major pedido no nome do pacote (Qt6 -> 6, Vulkan -> 0)."""
    achado = re.search(r"([0-9]+)$", pacote.get("nome", ""))
    return int(achado.group(1)) if achado else 0


