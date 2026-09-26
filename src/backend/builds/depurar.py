import os

_PASTA_DEPURADORES = ("Windows Kits/10/Debuggers", "Windows Kits/11/Debuggers")
_ARQUITETURAS = ("x64", "x86", "arm64", "arm")

COMANDOS_UTEIS = (
    ("g", "continuar ate ao proximo ponto de paragem"),
    ("p", "passo a passo por linha, sem entrar em funcoes"),
    ("t", "passo a passo por linha, entrando em funcoes"),
    ("gu", "sair da funcao atual"),
    ("k", "a pilha de chamadas (quem chamou quem)"),
    ("dv", "as variaveis locais deste quadro"),
    ("dv /t /v", "as variaveis locais com o tipo e os valores"),
    ("lm", "os modulos carregados"),
    ("q", "sair do depurador"),
)


def cdb():
    """O depurador de consola do Windows SDK (cdb.exe), preferindo o x64."""
    for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
        if not base:
            continue
        for relativa in _PASTA_DEPURADORES:
            raiz = os.path.join(base, relativa.replace("/", os.sep))
            for arquitetura in _ARQUITETURAS:
                alvo = os.path.join(raiz, arquitetura, "cdb.exe")
                if os.path.isfile(alvo):
                    return alvo.replace("\\", "/")
    return ""


def comando(exe, pastas=()):
    """A linha que abre o depurador sobre 'exe', com os simbolos e as fontes do projeto."""
    depurador = cdb()
    if not depurador:
        return ""
    caminhos = [os.path.dirname(exe)]
    for pasta in pastas:
        if pasta and os.path.isdir(pasta):
            caminhos.append(os.path.abspath(pasta))
    caminhos = [c.replace("\\", "/") for c in dict.fromkeys(caminhos)]
    juntos = ";".join(caminhos)
    return " ".join([
        f'"{depurador}"',
        "-y", f'"{juntos}"',
        "-srcpath", f'"{juntos}"',
        f'"{exe}"',
    ])


def preparacao(breakpoints):
    """Os comandos que abrem a sessao: carregar as linhas, marcar os pontos e seguir."""
    linhas = [".lines"]
    for ponto in breakpoints:
        linhas.append(f"bp `{ponto}`")
    linhas.append("g")
    return linhas


def pontos(texto):
    """Le os pontos de paragem pedidos: 'ficheiro.cpp:12' por linha ou separados por ';'."""
    limpos = []
    for pedaco in (texto or "").replace("\r", "\n").replace(";", "\n").split("\n"):
        ponto = pedaco.strip().strip('"').strip("'")
        if not ponto:
            continue
        if "!" in ponto:
            limpos.append(ponto)
            continue
        ficheiro, separador, linha = ponto.rpartition(":")
        if not separador or not linha.strip().isdigit():
            continue
        limpos.append(f"{os.path.basename(ficheiro.replace(chr(92), '/'))}:{linha.strip()}")
    return limpos


def texto_dos_comandos():
    return "\n".join(f"  {comando}  -  {para_que}" for comando, para_que in COMANDOS_UTEIS)
