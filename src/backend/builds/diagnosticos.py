import os
import re

_GRAVIDADE = (r"(?:fatal error|fatal erro|Error|Erro|error|erro|"
              r"Warning|Aviso|warning|aviso|Note|Nota|note|nota)")

_RE_COM_PARENTESES = re.compile(
    r"^(?P<ficheiro>[^()\r\n]+?)\((?P<linha>\d+)(?:,(?P<coluna>\d+))?\)\s*:\s*"
    r"(?P<gravidade>" + _GRAVIDADE + r")\s*(?P<codigo>[A-Z]{1,4}\d{2,6})?\s*:\s*(?P<mensagem>.*)$"
)
_RE_COM_DOIS_PONTOS = re.compile(
    r"^(?P<ficheiro>.+?):(?P<linha>\d+)(?::(?P<coluna>\d+))?:\s*"
    r"(?P<gravidade>" + _GRAVIDADE + r")\s*(?P<codigo>[A-Z]{1,4}\d{2,6})?\s*:\s*(?P<mensagem>.*)$"
)
_RE_CMAKE = re.compile(
    r"^CMake (?P<gravidade>Error|Warning) at (?P<ficheiro>.+?):(?P<linha>\d+) "
    r"\((?P<comando>[^)]*)\):\s*$"
)
_RE_SEM_LOCAL = re.compile(
    r"^\s*(?:\S+:\s*)?(?P<gravidade>" + _GRAVIDADE + r")\s+"
    r"(?P<codigo>[A-Z]{1,4}\d{3,6})\s*:\s*(?P<mensagem>.+)$"
)
_RE_PY_LOCAL = re.compile(r'^\s*File "(?P<ficheiro>.+?)", line (?P<linha>\d+)')
_RE_PY_EXCECAO = re.compile(r"^(?P<nome>SyntaxError|IndentationError|TabError):\s*(?P<mensagem>.*)$")

LIMITE_MENSAGEM = 300
_LINHAS_ATE_A_EXCECAO = 5


def analisar(texto, raiz=""):
    """Le a saida de um build e devolve os erros e avisos com ficheiro, linha e codigo."""
    linhas = _linhas(texto)
    itens = []
    for indice, linha in enumerate(linhas):
        item = _da_linha(linha, linhas, indice, raiz)
        if item:
            itens.append(item)
    return _sem_repetidos(itens)


def resumo(texto, raiz="", maximo=25):
    """Bloco de texto com os diagnosticos de um build, para quem le a saida de longe."""
    itens = analisar(texto, raiz)
    if not itens:
        return ""
    erros = sum(1 for i in itens if i["gravidade"] == "erro")
    avisos = sum(1 for i in itens if i["gravidade"] == "aviso")
    contagem = ", ".join(parte for parte in (
        f"{erros} erro(s)" if erros else "",
        f"{avisos} aviso(s)" if avisos else "",
        f"{len(itens) - erros - avisos} nota(s)" if len(itens) - erros - avisos else "",
    ) if parte)
    linhas = [f"DIAGNOSTICOS ({contagem}):"]
    for item in itens[:maximo]:
        linhas.append("  " + item["bruto"])
    if len(itens) > maximo:
        linhas.append(f"  ... e mais {len(itens) - maximo}")
    return "\n".join(linhas)


def _linhas(texto):
    return (texto or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _da_linha(linha, linhas, indice, raiz):
    if not linha.strip():
        return None
    achado = _python_sintaxe(linha, linhas, indice, raiz)
    if achado:
        return achado
    achado = _RE_CMAKE.match(linha)
    if achado:
        return _montar(achado, _mensagem_seguinte(linhas, indice), linha, raiz)
    achado = _RE_COM_PARENTESES.match(linha) or _RE_COM_DOIS_PONTOS.match(linha)
    if achado:
        return _montar(achado, achado.group("mensagem"), linha, raiz)
    achado = _RE_SEM_LOCAL.match(linha)
    if achado:
        return {
            "ficheiro": "",
            "caminho": "",
            "linha": 0,
            "coluna": 0,
            "gravidade": _gravidade(achado.group("gravidade")),
            "codigo": (achado.group("codigo") or "").upper(),
            "mensagem": achado.group("mensagem").strip()[:LIMITE_MENSAGEM],
            "bruto": linha.strip()[:LIMITE_MENSAGEM],
        }
    return None


def _python_sintaxe(linha, linhas, indice, raiz):
    """Le um erro de sintaxe do Python - so os de compilacao, que impedem o ficheiro de correr."""
    achado = _RE_PY_LOCAL.match(linha)
    if not achado:
        return None
    for seguinte in linhas[indice + 1:indice + _LINHAS_ATE_A_EXCECAO]:
        excecao = _RE_PY_EXCECAO.match(seguinte.strip())
        if not excecao:
            continue
        ficheiro = _limpar(achado.group("ficheiro"))
        return {
            "ficheiro": ficheiro,
            "caminho": _resolver(ficheiro, raiz),
            "linha": int(achado.group("linha")),
            "coluna": 0,
            "gravidade": "erro",
            "codigo": excecao.group("nome"),
            "mensagem": excecao.group("mensagem").strip()[:LIMITE_MENSAGEM],
            "bruto": linha.strip()[:LIMITE_MENSAGEM],
        }
    return None


def _mensagem_seguinte(linhas, indice):
    partes = []
    for seguinte in linhas[indice + 1:indice + 4]:
        if not seguinte.strip() or _filha_de_linha(seguinte):
            break
        partes.append(seguinte.strip())
    return " ".join(partes)


def _filha_de_linha(linha):
    return bool(_RE_COM_PARENTESES.match(linha) or _RE_COM_DOIS_PONTOS.match(linha)
                or _RE_CMAKE.match(linha) or _RE_SEM_LOCAL.match(linha))


def _montar(achado, mensagem, linha, raiz):
    ficheiro = _limpar(achado.group("ficheiro"))
    grupos = achado.groupdict()
    return {
        "ficheiro": ficheiro,
        "caminho": _resolver(ficheiro, raiz),
        "linha": int(grupos.get("linha") or 0),
        "coluna": int(grupos.get("coluna") or 0),
        "gravidade": _gravidade(achado.group("gravidade")),
        "codigo": (grupos.get("codigo") or "").upper(),
        "mensagem": (mensagem or "").strip()[:LIMITE_MENSAGEM],
        "bruto": linha.strip()[:LIMITE_MENSAGEM],
    }


def _limpar(ficheiro):
    return (ficheiro or "").strip().strip('"').strip("'")


def _resolver(ficheiro, raiz):
    if not ficheiro:
        return ""
    alvo = ficheiro if os.path.isabs(ficheiro) else os.path.join(raiz, ficheiro) if raiz else ""
    if not alvo:
        return ""
    alvo = os.path.abspath(alvo)
    return alvo.replace("\\", "/") if os.path.isfile(alvo) else ""


def _gravidade(palavra):
    texto = (palavra or "").strip().lower()
    if texto.startswith(("fatal", "error", "erro")):
        return "erro"
    if texto.startswith(("warning", "aviso")):
        return "aviso"
    return "nota"


def _sem_repetidos(itens):
    vistos = set()
    resultado = []
    for item in itens:
        chave = (item["caminho"] or item["ficheiro"], item["linha"], item["coluna"],
                 item["codigo"], item["mensagem"])
        if chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(item)
    return resultado
