import glob
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

WORKERS = 8
TIMEOUT_FICHEIRO = 240

_RX = re.compile(r"^(.+?)\((\d+)(?:,(\d+))?\)\s*:\s*(warning|error)\s+([A-Z]+\d+)\s*:\s*(.*)$")
_RX_CAUDA = re.compile(r"\s*\[[^\]]*\]\s*$")
_RX_PRAGMA = re.compile(r"^([ \t]*)#\s*pragma\s+warning\s*\(\s*disable\s*:[^)]*\)[^\r\n]*", re.M)

_PLATAFORMAS = {"Win32": "x86", "x64": "x64", "ARM64": "arm64"}

_NIVEL = {"Level1": "/W1", "Level2": "/W2", "Level3": "/W3", "Level4": "/W4", "TurnOffAllWarnings": "/w"}
_BIBLIOTECA = {
    "MultiThreaded": "/MT",
    "MultiThreadedDebug": "/MTd",
    "MultiThreadedDLL": "/MD",
    "MultiThreadedDebugDLL": "/MDd",
}


def censo(pasta, plataforma="", ficheiros=(), ao_progredir=None):
    """Compila os ficheiros de um projeto do Visual Studio com os avisos ligados e conta-os por codigo e por local."""
    projeto = _projeto(pasta)
    if not projeto:
        return {"erro": f"ERRO: nao encontrei nenhum .vcxproj em {pasta}. O censo de avisos so sabe ler "
                        "projetos do Visual Studio (o CMake teria de vir do compile_commands.json)."}
    opcoes = _opcoes(projeto)
    if not opcoes["fontes"]:
        return {"erro": f"ERRO: o {os.path.basename(projeto)} nao declara nenhum ficheiro para compilar."}
    vcvars = _vcvarsall()
    if not vcvars:
        return {"erro": "ERRO: nao encontrei o vcvarsall.bat - sem ele nao ha compilador para chamar."}
    escolhidos = _escolher(opcoes["fontes"], ficheiros)
    plataforma = plataforma or _plataforma(projeto)
    comando = _prefixo(vcvars, plataforma) + "cl /c /nologo " + _flags(opcoes)
    raiz, limpa = _arvore_sem_pragmas(os.path.dirname(projeto))
    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            pendentes = executor.map(
                lambda rel: (rel, _compilar(os.path.join(raiz, rel), comando)),
                escolhidos,
            )
            saidas = []
            for resultado in pendentes:
                saidas.append(resultado)
                if ao_progredir:
                    ao_progredir(len(saidas), len(escolhidos))
    finally:
        if limpa:
            shutil.rmtree(raiz, ignore_errors=True)
    dados = _somar(saidas, os.path.basename(projeto), plataforma)
    dados["pragmas_limpos"] = limpa
    return dados


def texto(dados):
    """Relatorio do censo de avisos, para ler de longe."""
    if dados.get("erro"):
        return dados["erro"]
    linhas = [f"CENSO DE AVISOS ({len(dados['compilados'])} ficheiros, {dados['plataforma']}):"]
    if dados.get("pragmas_limpos"):
        linhas.append("  (medido numa copia com os '#pragma warning(disable:...)' neutralizados: sao os avisos")
        linhas.append("   que os pragmas escondem, e o projeto no disco nao foi tocado)")
    if not dados["por_codigo"]:
        linhas.append("  nenhum aviso - compilou limpo")
        return "\n".join(linhas)
    linhas.append(f"  {dados['ocorrencias']} ocorrencias em {dados['distintos']} sitios distintos")
    for codigo, quantos in dados["por_codigo"]:
        linhas.append(f"  {codigo}: {quantos} ocorrencias | {len(dados['locais'][codigo])} sitios distintos")
    linhas.append("  sitios, por ficheiro, com o texto do aviso:")
    for ficheiro in sorted(dados["locais_por_ficheiro"]):
        for linha_local, codigo in dados["locais_por_ficheiro"][ficheiro]:
            mensagem = dados.get("mensagens", {}).get((ficheiro, linha_local), "")
            linhas.append(f"    {ficheiro}:{linha_local}: {codigo}: {mensagem}")
    if dados["sem_saida"]:
        linhas.append("  NAO COMPILARAM: " + ", ".join(dados["sem_saida"]))
    if dados.get("falhados"):
        linhas.append("  ERROS DE COMPILACAO (o censo destes ficheiros nao vale):")
        for ficheiro, lista in dados["falhados"].items():
            linhas.append(f"    {ficheiro}: " + "; ".join(lista[:3]))
    return "\n".join(linhas)


def _projeto(pasta):
    achados = sorted(glob.glob(os.path.join(pasta, "*.vcxproj")))
    return achados[0] if achados else ""


def _arvore_sem_pragmas(pasta):
    """Copia a pasta src para uma temporaria com os #pragma warning(disable) neutralizados, sem mexer no projeto."""
    origem = os.path.join(pasta, "src")
    if not os.path.isdir(origem):
        return pasta, False
    destino = tempfile.mkdtemp(prefix="axio_censo_")
    shutil.copytree(origem, os.path.join(destino, "src"))
    for raiz, _, ficheiros in os.walk(destino):
        for nome in ficheiros:
            if nome.endswith((".h", ".hpp", ".cpp", ".c", ".cc")):
                _neutralizar_pragmas(os.path.join(raiz, nome))
    return destino, True


def _neutralizar_pragmas(caminho):
    with open(caminho, "rb") as ficheiro:
        texto = ficheiro.read().decode("latin-1")
    limpo = _RX_PRAGMA.sub(r"\1", texto)
    if limpo == texto:
        return
    with open(caminho, "wb") as ficheiro:
        ficheiro.write(limpo.encode("latin-1"))


def _plataforma(projeto):
    for elemento in ET.parse(projeto).getroot().iter():
        if elemento.tag.rsplit("}", 1)[-1] != "ProjectConfiguration":
            continue
        escolhida = _PLATAFORMAS.get(elemento.get("Include", "").rsplit("|", 1)[-1].strip())
        if escolhida:
            return escolhida
    return "x86"


def _opcoes(projeto):
    raiz = ET.parse(projeto).getroot()
    definicoes, includes, fontes = {}, set(), []
    for elemento in raiz.iter():
        etiqueta = elemento.tag.rsplit("}", 1)[-1]
        if etiqueta == "IncludePath":
            includes.update(_listar(elemento.text))
            continue
        if etiqueta != "ClCompile":
            continue
        if elemento.get("Include"):
            fontes.append(elemento.get("Include"))
            continue
        for filho in elemento:
            nome = filho.tag.rsplit("}", 1)[-1]
            if nome == "AdditionalIncludeDirectories":
                includes.update(_listar(filho.text))
            elif nome == "PreprocessorDefinitions":
                definicoes.setdefault("defines", set()).update(_listar(filho.text))
            elif nome in ("WarningLevel", "SDLCheck", "RuntimeLibrary") and (filho.text or "").strip():
                if nome != "RuntimeLibrary" or "Release" in elemento.get("Condition", "") \
                        or "RuntimeLibrary" not in definicoes:
                    definicoes[nome] = filho.text.strip()
    return {"fontes": fontes, "includes": sorted(includes), "defines": sorted(definicoes.get("defines", ())),
            "nivel": _NIVEL.get(definicoes.get("WarningLevel", ""), "/W3"),
            "sdl": definicoes.get("SDLCheck", "").lower() == "true",
            "biblioteca": _BIBLIOTECA.get(definicoes.get("RuntimeLibrary", ""), "/MD")}


def _listar(texto):
    return [p.strip() for p in (texto or "").split(";")
            if p.strip() and "%(" not in p and "$(" not in p]


def _escolher(fontes, pedidos):
    if not pedidos:
        return fontes
    queridos = {os.path.basename(p).lower() for p in pedidos if p.strip()}
    return [f for f in fontes if os.path.basename(f).lower() in queridos]


def _vcvarsall():
    raizes = [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")]
    for raiz in filter(None, raizes):
        achados = glob.glob(os.path.join(raiz, "Microsoft Visual Studio", "*", "*",
                                         "VC", "Auxiliary", "Build", "vcvarsall.bat"))
        if achados:
            return sorted(achados)[-1]
    return ""


def _prefixo(vcvars, plataforma):
    return 'call "' + vcvars + '" ' + (plataforma or "x86") + " >nul && "


def _flags(opcoes):
    partes = [opcoes["nivel"], opcoes["biblioteca"], "/EHsc", "/GS"]
    if opcoes["sdl"]:
        partes.append("/sdl")
    partes += ["/D " + d for d in opcoes["defines"]]
    partes += ['/I "' + i + '"' for i in opcoes["includes"]]
    return " ".join(partes)


def _compilar(origem, comando):
    temporaria = tempfile.mkdtemp(prefix="axio_avisos_")
    try:
        resultado = subprocess.run(comando + ' "' + origem + '"', shell=True, cwd=temporaria,
                                   capture_output=True, timeout=TIMEOUT_FICHEIRO)
        saida = (resultado.stdout or b"").decode("cp1252", "replace")
        return saida + (resultado.stderr or b"").decode("cp1252", "replace")
    except (OSError, subprocess.SubprocessError):
        return ""
    finally:
        shutil.rmtree(temporaria, ignore_errors=True)


def _somar(saidas, projeto, plataforma):
    por_codigo, locais, mensagens, compilados, sem_saida, falhados = {}, {}, {}, [], [], {}
    for rel, saida in saidas:
        if not saida.strip():
            sem_saida.append(rel)
            continue
        compilados.append(rel)
        for linha in saida.splitlines():
            achado = _RX.match(linha.strip())
            if not achado:
                continue
            ficheiro = os.path.basename(achado.group(1))
            if achado.group(4) == "error":
                falhados.setdefault(rel, []).append(f"{ficheiro}:{achado.group(2)} {achado.group(5)}")
                continue
            codigo = achado.group(5)
            local = (ficheiro, int(achado.group(2)))
            por_codigo[codigo] = por_codigo.get(codigo, 0) + 1
            locais.setdefault(codigo, set()).add(local)
            mensagens.setdefault(local, _RX_CAUDA.sub("", achado.group(6)).strip())
    juncao = set()
    for conjunto in locais.values():
        juncao |= conjunto
    por_ficheiro = {}
    for ficheiro, linha in juncao:
        por_ficheiro.setdefault(ficheiro, []).append((linha, _codigo_de(ficheiro, linha, locais)))
    for ficheiro in por_ficheiro:
        por_ficheiro[ficheiro].sort()
    return {
        "projeto": projeto,
        "plataforma": plataforma,
        "compilados": compilados,
        "sem_saida": sem_saida,
        "falhados": falhados,
        "ocorrencias": sum(por_codigo.values()),
        "distintos": len(juncao),
        "por_codigo": sorted(por_codigo.items(), key=lambda par: (-par[1], par[0])),
        "locais": locais,
        "mensagens": mensagens,
        "locais_por_ficheiro": por_ficheiro,
    }


def _codigo_de(ficheiro, linha, locais):
    for codigo, conjunto in locais.items():
        if (ficheiro, linha) in conjunto:
            return codigo
    return ""
