import os

_PASTA_DEPURADORES = ("Windows Kits/10/Debuggers", "Windows Kits/11/Debuggers")
_ARQUITETURAS = ("x64", "x86", "arm64", "arm")

COMANDOS_UTEIS = (
    ("l+s", "a linha de origem onde a execucao parou"),
    ("k", "a pilha de chamadas, com ficheiro e linha"),
    ("dv /t /v", "as variaveis locais deste quadro, com o tipo e o valor"),
    ("?? expressao", "avalia uma expressao ou variavel C++ (ex: ?? argc)"),
    ("x modulo!simbolo", "procura um simbolo pelo nome"),
    ("p", "salta para a linha seguinte, sem entrar em funcoes"),
    ("t", "entra na funcao chamada e para na primeira linha dela"),
    ("gu", "sai da funcao atual"),
    ("g", "continua ate ao proximo ponto de paragem"),
    ("bp ficheiro:linha", "marca um ponto de paragem novo, a quente"),
    ("bl", "lista os pontos de paragem marcados"),
    ("r", "os registos do processador"),
    ("u", "o assembly a volta da linha atual"),
    ("l-t", "passa a andar por instrucao de assembly em vez de linha"),
    ("l+t", "volta a andar por linha de origem"),
    ("lm", "os modulos carregados"),
    ("q", "sai do depurador e fecha o programa"),
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
        "-lines",
        "-y", f'"{juntos}"',
        "-srcpath", f'"{juntos}"',
        f'"{exe}"',
    ])


def preparacao(breakpoints):
    """Os comandos que abrem a sessao: fonte por linha, os pontos marcados e seguir."""
    linhas = ["l+t", "l+s"]
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


SESSAO = {"id": "", "executavel": ""}


def guardar_sessao(registo_id, executavel):
    """Anota a sessao aberta, para os comandos seguintes irem para o mesmo card."""
    SESSAO["id"] = registo_id
    SESSAO["executavel"] = executavel


def esquecer_sessao():
    SESSAO["id"] = ""
    SESSAO["executavel"] = ""


def sessao_aberta():
    """Diz se ha uma sessao anotada (se ainda corre, quem confirma e o processo)."""
    return bool(SESSAO["id"])


def card_da_sessao():
    """O card onde a sessao de depuracao esta aberta."""
    return SESSAO["id"]


def texto_dos_comandos():
    return "\n".join(f"  {comando}  -  {para_que}" for comando, para_que in COMANDOS_UTEIS)


def comandos_do_pedido(texto):
    """Le os comandos a enviar na sessao: um por linha, ou separados por ';'."""
    linhas = []
    for pedaco in (texto or "").replace("\r", "\n").replace(";", "\n").split("\n"):
        comando = pedaco.strip()
        if comando:
            linhas.append(comando)
    return linhas
