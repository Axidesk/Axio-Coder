import glob
import json
import os
import re
import shutil
import string
import subprocess

from src.backend.builds.detetar import exigencia_de, versao_pedida

_RE_VISAO_QT = re.compile(r"^[0-9]+\.[0-9]+(\.[0-9]+)?$")
_RE_COMPILADOR_QT = re.compile(r"^(msvc|mingw|clang|android|ios|wasm)", re.IGNORECASE)

_CAMINHOS_PLAUSIVEIS = (
    "Qt",
    "Programas/Qt",
    "Program Files/Qt",
    "Program Files (x86)/Qt",
    "Dev/Qt",
)
_VSWHERE = "Microsoft Visual Studio/Installer/vswhere.exe"
_PREFERENCIA_COMPILADOR = {"msvc": 3, "clang": 2, "mingw": 1}


def kits_instalados(prefixos=()):
    """O que esta instalado NESTA maquina: Qt (por versao e kit), MSVC, CMake, Ninja, glslc, Vulkan, vcpkg."""
    raizes = _raizes_qt(prefixos)
    return {
        "qt": [kit for raiz in raizes for kit in _kits_qt(raiz)],
        "raizes_qt": raizes,
        "msvc": _visual_studio(),
        "cmake": _ferramentas_em_disco("cmake") + _ferramentas_da_qt(raizes, "CMake_64/bin/cmake.exe", "cmake"),
        "ninja": _ferramentas_em_disco("ninja") + _ferramentas_da_qt(raizes, "Ninja/ninja.exe", "ninja"),
        "glslc": _ferramentas_em_disco("glslc"),
        "vulkan": _vulkan(),
        "vcpkg": _vcpkg(raizes),
    }


def escolher_kit(deteccao, instalado):
    """Le as exigencias do projeto e devolve o kit que as serve, com o que falta nomeado.

    Nao pergunta nada ao utilizador: escolhe entre o que a maquina tem e, quando nao chega,
    diz exatamente o que falta e onde se instala.
    """
    faltam = []
    notas = []
    msvc = instalado["msvc"][0] if instalado["msvc"] else None
    cmake = _mais_recente(instalado["cmake"])
    ninja = _mais_recente(instalado["ninja"])
    glslc = instalado["glslc"][0] if instalado["glslc"] else None
    vulkan = instalado["vulkan"]
    if not cmake:
        faltam.append("CMake nao esta instalado - sem ele nao ha projeto para configurar.")
    exigencia_qt = exigencia_de(deteccao.get("pacotes", []), "qt")
    qt = None
    if exigencia_qt:
        qt = _melhor_qt(instalado["qt"], versao_pedida(exigencia_qt), msvc)
        if not qt:
            faltam.append(_falta_qt(exigencia_qt, instalado, msvc))
        else:
            faltam += _modulos_em_falta(qt, exigencia_qt)
    if deteccao.get("programas"):
        for programa in deteccao["programas"]:
            if any("glslc" in nome for nome in programa["nomes"]) and not glslc:
                faltam.append("O projeto compila shaders e o 'glslc' do Vulkan SDK nao esta no PATH.")
    if "Vulkan" in deteccao.get("vertentes", []) and not vulkan.get("lib"):
        faltam.append("O projeto pede Vulkan e nao encontrei a biblioteca do Vulkan SDK.")
    gerador, arquitetura = _gerador(qt, msvc, ninja)
    if qt and qt["compilador"] != "msvc" and not ninja:
        faltam.append(f"O kit de Qt '{qt['kit']}' e {qt['compilador']} e falta o Ninja para o compilar.")
    variaveis = {}
    if qt:
        variaveis["CMAKE_PREFIX_PATH"] = qt["caminho"]
    if msvc and not qt:
        notas.append(f"Compilador MSVC {msvc['ferramentas'][-1] if msvc['ferramentas'] else ''} de {msvc['produto']}.")
    if not msvc and not qt:
        faltam.append("Nao ha compilador C++ instalado (nem MSVC nem um kit de Qt com compilador).")
    return {
        "gerador": gerador,
        "arquitetura": arquitetura,
        "qt": qt,
        "cmake": cmake,
        "ninja": ninja,
        "glslc": glslc,
        "vulkan": vulkan,
        "variaveis": variaveis,
        "caminhos": _caminhos_para_correr(qt, vulkan),
        "satisfaz": not faltam,
        "faltam": faltam,
        "notas": notas,
    }


def _raizes_qt(prefixos):
    candidatos = []
    for prefixo in prefixos:
        candidatos.append(os.path.dirname(os.path.dirname(os.path.abspath(prefixo))))
    for var in ("QTDIR", "QT_DIR", "QT_ROOT"):
        if os.environ.get(var):
            candidatos.append(os.environ[var])
    qmake = shutil.which("qmake")
    if qmake:
        candidatos.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(qmake)))))
    for raiz in _raizes_do_disco():
        for relativo in _CAMINHOS_PLAUSIVEIS:
            candidatos.append(os.path.join(raiz, relativo.replace("/", os.sep)))
    vistas = []
    validas = []
    for candidato in candidatos:
        normal = os.path.normcase(os.path.abspath(candidato))
        if normal in vistas or not os.path.isdir(candidato):
            continue
        vistas.append(normal)
        if _tem_kit_qt(candidato):
            validas.append(os.path.abspath(candidato))
    return validas


def _falta_qt(exigencia, instalado, msvc):
    """Nomeia o que falta para servir um projeto que pede Qt, sem inventar o componente a instalar."""
    pedido = versao_pedida(exigencia)
    disponiveis = sorted({k["versao"] for k in instalado["qt"]})
    modulos = ", ".join(exigencia.get("componentes", [])) or "sem modulos nomeados"
    if disponiveis:
        estado = f"o que esta instalado e o Qt {', '.join(disponiveis)}, que nao serve"
    else:
        estado = "nao ha nenhum kit de Qt instalado"
    frase = f"O projeto pede Qt {pedido} ({modulos}) e {estado}."
    instalador = _instalador_do_qt(instalado)
    if instalador:
        familia = "win64_msvc2022_64" if msvc else "win64_mingw"
        frase += (f" Instala-se pelo instalador que ja esta na maquina ({instalador}), com o componente "
                  f"do Qt {pedido} para {familia} - o id exato do componente e lido do proprio instalador "
                  "antes de instalar, nunca escrito de memoria.")
    else:
        frase += " Nao encontrei o instalador da Qt nesta maquina: sem ele, esse Qt tem de ser instalado a mao."
    return frase


def _raizes_do_disco():
    raizes = []
    for letra in string.ascii_uppercase:
        raiz = f"{letra}:{os.sep}"
        if os.path.isdir(raiz):
            raizes.append(raiz)
    return raizes


def _tem_kit_qt(candidato):
    for versao in sorted(glob.glob(os.path.join(candidato, "[0-9]*"))) or []:
        if _RE_VISAO_QT.match(os.path.basename(versao)) and _kits_qt(versao):
            return True
    return False


def _kits_qt(versao_ou_raiz):
    versoes = []
    if _RE_VISAO_QT.match(os.path.basename(versao_ou_raiz)):
        versoes = [versao_ou_raiz]
    else:
        versoes = [v for v in sorted(glob.glob(os.path.join(versao_ou_raiz, "[0-9]*"))) if _RE_VISAO_QT.match(os.path.basename(v))]
    kits = []
    for versao in versoes:
        for kit in sorted(os.listdir(versao)) if os.path.isdir(versao) else []:
            caminho = os.path.join(versao, kit)
            if not os.path.isfile(os.path.join(caminho, "bin", "qmake.exe")):
                continue
            compilador = _RE_COMPILADOR_QT.match(kit)
            kits.append({
                "versao": os.path.basename(versao),
                "kit": kit,
                "caminho": caminho.replace("\\", "/"),
                "compilador": (compilador.group(1).lower() if compilador else "desconhecido"),
                "raiz": os.path.dirname(versao).replace("\\", "/"),
                "instalador": _instalador_da_raiz(os.path.dirname(versao)),
            })
    return kits


def _instalador_da_raiz(raiz_qt):
    alvo = os.path.join(raiz_qt, "MaintenanceTool.exe")
    return alvo.replace("\\", "/") if os.path.isfile(alvo) else ""


def _instalador_do_qt(instalado):
    for kit in instalado["qt"]:
        if kit["instalador"]:
            return kit["instalador"]
    for raiz in instalado["raizes_qt"]:
        alvo = os.path.join(raiz, "MaintenanceTool.exe")
        if os.path.isfile(alvo):
            return alvo.replace("\\", "/")
    return ""


def _visual_studio():
    vswhere = ""
    for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
        candidato = os.path.join(base, _VSWHERE.replace("/", os.sep)) if base else ""
        if candidato and os.path.isfile(candidato):
            vswhere = candidato
            break
    if not vswhere:
        return []
    try:
        saida = subprocess.run(
            [vswhere, "-all", "-products", "*", "-format", "json", "-utf8"],
            capture_output=True, text=True, timeout=60, check=False,
        ).stdout
        instalacoes = json.loads(saida or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    resultado = []
    for instalacao in instalacoes:
        caminho = instalacao.get("installationPath") or ""
        ferramentas = sorted(
            os.path.basename(p) for p in glob.glob(os.path.join(caminho, "VC", "Tools", "MSVC", "*"))
        )
        if not ferramentas:
            continue
        resultado.append({
            "produto": instalacao.get("displayName") or "",
            "versao": instalacao.get("installationVersion") or "",
            "caminho": caminho.replace("\\", "/"),
            "ferramentas": ferramentas,
        })
    return sorted(resultado, key=lambda v: _versao_tupla(v["versao"]), reverse=True)


def _ferramentas_em_disco(nome):
    achado = shutil.which(nome)
    if not achado:
        return []
    return [{"caminho": achado.replace("\\", "/"), "versao": _versao_da_ferramenta(achado)}]


def _ferramentas_da_qt(raizes, relativo, nome):
    resultado = []
    for raiz in raizes:
        alvo = os.path.join(raiz, relativo.replace("/", os.sep))
        if os.path.isfile(alvo):
            resultado.append({"caminho": alvo.replace("\\", "/"), "versao": _versao_da_ferramenta(alvo)})
    return resultado


def _versao_da_ferramenta(caminho):
    for argumento in ("--version", "-version", "/?"):
        try:
            saida = subprocess.run([caminho, argumento], capture_output=True, text=True, timeout=30,
                                   check=False)
        except (OSError, subprocess.SubprocessError):
            continue
        texto = (saida.stdout or "") + (saida.stderr or "")
        achado = re.search(r"([0-9]+\.[0-9]+(\.[0-9]+)?)", texto)
        if achado:
            return achado.group(1)
    return ""


def _vulkan():
    for var in ("VULKAN_SDK", "VK_SDK_PATH"):
        raiz = os.environ.get(var)
        if not raiz or not os.path.isdir(raiz):
            continue
        libs = glob.glob(os.path.join(raiz, "Lib", "vulkan-1.lib"))
        executaveis = glob.glob(os.path.join(raiz, "Bin", "glslc.exe"))
        return {
            "raiz": raiz.replace("\\", "/"),
            "lib": libs[0].replace("\\", "/") if libs else "",
            "glslc": executaveis[0].replace("\\", "/") if executaveis else "",
        }
    return {"raiz": "", "lib": "", "glslc": ""}


def _vcpkg(raizes):
    candidatos = []
    if os.environ.get("VCPKG_ROOT"):
        candidatos.append(os.environ["VCPKG_ROOT"])
    candidatos += [os.path.join(raiz, "vcpkg") for raiz in raizes]
    return [c.replace("\\", "/") for c in candidatos if os.path.isfile(os.path.join(c, "vcpkg.exe"))]


def _versao_tupla(texto):
    return tuple(int(p) for p in re.findall(r"[0-9]+", texto or "")[:4])


def _mais_recente(lista):
    if not lista:
        return None
    return max(lista, key=lambda f: _versao_tupla(f.get("versao", "")))


def _melhor_qt(kits, major, msvc):
    candidatos = [k for k in kits if not major or k["versao"].startswith(f"{major}.")]
    if not candidatos:
        return None
    def ordem(kit):
        tem_compilador = 1 if (kit["compilador"] == "msvc" and msvc) or kit["compilador"] != "msvc" else 0
        return (tem_compilador, _PREFERENCIA_COMPILADOR.get(kit["compilador"], 0), _versao_tupla(kit["versao"]))
    return max(candidatos, key=ordem)


def _caminhos_para_correr(qt, vulkan):
    """Pastas que tem de estar no PATH para o programa COMPILADO arrancar (as DLLs do kit)."""
    caminhos = []
    if qt:
        caminhos.append(os.path.join(qt["caminho"], "bin"))
    if vulkan.get("raiz"):
        caminhos.append(os.path.join(vulkan["raiz"], "Bin"))
    return [os.path.normpath(c) for c in caminhos if os.path.isdir(c)]


def _modulos_em_falta(kit, exigencia):
    """Modulos que o find_package pede e que o kit escolhido nao traz (a pasta do modulo e a prova)."""
    pedidos = exigencia.get("componentes") or []
    major = kit["versao"].split(".")[0]
    ausentes = [
        modulo
        for modulo in pedidos
        if not os.path.isdir(os.path.join(kit["caminho"], "lib", "cmake", f"Qt{major}{modulo}"))
    ]
    if not ausentes:
        return []
    onde = f" Instala-se pelo instalador que ja esta na maquina ({kit['instalador']})." if kit["instalador"] else ""
    return [
        (
            f"O kit de Qt {kit['versao']} {kit['kit']} nao traz os modulos {', '.join(ausentes)} "
            f"que o projeto pede (dos {len(pedidos)} pedidos).{onde}"
        )
    ]


def _gerador(qt, msvc, ninja):
    if qt and qt["compilador"] == "msvc" and msvc:
        return _gerador_visual_studio(msvc), "x64"
    if qt and qt["compilador"] == "mingw" and ninja:
        return "Ninja", ""
    if not qt and msvc:
        return _gerador_visual_studio(msvc), "x64"
    if ninja:
        return "Ninja", ""
    return "", ""


def _gerador_visual_studio(msvc):
    major = _versao_tupla(msvc["versao"])
    if major and major[0] >= 17:
        return "Visual Studio 17 2022"
    if major and major[0] == 16:
        return "Visual Studio 16 2019"
    return "Visual Studio 17 2022"
