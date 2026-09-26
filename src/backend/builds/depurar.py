import os
import sys
import threading

from src.backend.builds import leitura_depurador

_PASTA_DEPURADORES = ("Windows Kits/10/Debuggers", "Windows Kits/11/Debuggers")
_ARQUITETURAS = ("x64", "x86", "arm64", "arm")
_VENVS = (".venv", "venv", "env")
_EXTENSOES_CPP = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx")
_EXTENSOES_PY = (".py", ".pyw")

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

LINHA_DO_CARD = ("[axio] neste card: g continuar | p passo | t entrar | gu sair | "
                 "k pilha | dv /t /v variaveis | ?? expr | q sair")

COMANDOS_UTEIS_PY = (
    ("c", "continua ate ao proximo ponto de paragem"),
    ("n", "executa a linha seguinte, sem entrar nas funcoes"),
    ("s", "entra na funcao chamada e para na primeira linha dela"),
    ("r", "corre ate ao fim da funcao atual"),
    ("p expressao", "mostra o valor de uma variavel (ex: p total) - aqui o 'p' e IMPRIMIR"),
    ("pp expressao", "mostra uma lista ou um dicionario formatado"),
    ("w", "a pilha de chamadas, do sitio onde estas para tras"),
    ("l", "o codigo a volta da linha atual"),
    ("b ficheiro:linha", "marca um ponto de paragem novo, a quente"),
    ("cl numero", "tira um ponto de paragem"),
    ("q", "sai do depurador e fecha o programa"),
)

LINHA_DO_CARD_PY = ("[axio] neste card: c continuar | n proxima linha | s entrar na funcao | "
                    "p expr ver valor | w pilha | l codigo | q sair")

CONTROLES = (
    ("continuar", "Continuar", "g", "c", "segue ate ao proximo ponto de paragem"),
    ("passo", "Passo", "p", "n", "executa a linha seguinte, sem entrar nas funcoes"),
    ("entrar", "Entrar", "t", "s", "entra na funcao chamada e para na primeira linha dela"),
    ("sair", "Sair", "gu", "r", "sai da funcao onde estas e volta a quem a chamou"),
    ("pilha", "Pilha", "k", "w", "o caminho das chamadas ate aqui"),
    ("variaveis", "Variaveis", "dv /t /v", "p locals()", "os valores das variaveis deste momento"),
    ("terminar", "Terminar", "q", "q", "fecha a sessao de depuracao"),
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
    """Os comandos que abrem a sessao: fonte por linha, os pontos marcados, seguir e a pilha.

    O 'k' no fim nao e decoracao: o cdb diz a LINHA onde parou mas nao diz de que ficheiro ela
    e - so um 'k' traz os quadros com o caminho, e sem caminho o editor nao tem o que abrir.
    Vai ja escrito, porque a execucao so o consome depois de parar."""
    linhas = ["l+t", "l+s"]
    for ponto in breakpoints:
        linhas.append(f"bp `{ponto}`")
    linhas.append("g")
    linhas.append("k")
    return linhas


def _pedacos(texto):
    """Parte a lista de pontos ou de comandos: por linha ou por ';'."""
    return [p.strip() for p in (texto or "").replace("\r", "\n").replace(";", "\n").split("\n")
            if p.strip()]


def pontos(texto):
    """Le os pontos de paragem pedidos: 'ficheiro.cpp:12' por linha ou separados por ';'."""
    limpos = []
    for pedaco in _pedacos(texto):
        ponto = pedaco.strip('"').strip("'")
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


def _extensao_do_ponto(pedaco):
    """A extensao do ficheiro de um ponto, ja sem a linha e sem o 'modulo!' do cdb."""
    nome = pedaco.split("!")[-1]
    cabeca, _, cauda = nome.rpartition(":")
    if cabeca and cauda.strip().isdigit():
        nome = cabeca
    return os.path.splitext(nome)[1].lower()


def motor(breakpoints):
    """O depurador que sabe ler estes pontos, decidido pela linguagem do primeiro deles."""
    for pedaco in _pedacos(breakpoints):
        extensao = _extensao_do_ponto(pedaco)
        if extensao in _EXTENSOES_PY:
            return "python"
        if extensao in _EXTENSOES_CPP:
            return "cpp"
    return "cpp"


def motor_do_alvo(breakpoints, alvo):
    """O depurador que sabe ler o que foi pedido: pelos pontos marcados, e sem eles pelo
    ficheiro que esta aberto no editor (e o que decide o botao de depurar da barra)."""
    if _pedacos(breakpoints):
        return motor(breakpoints)
    return "python" if _extensao_do_ponto(alvo or "") in _EXTENSOES_PY else "cpp"


def pontos_de_outra_linguagem(breakpoints, escolhido):
    """Os pontos que o depurador escolhido nao sabe ler (ficaram de fora desta sessao)."""
    estranhas = _EXTENSOES_CPP if escolhido == "python" else _EXTENSOES_PY
    return [p for p in _pedacos(breakpoints) if _extensao_do_ponto(p) in estranhas]


def python_do_projeto(raiz):
    """O interpretador que corre o projeto: o venv dele, se tiver; senao o que corre o Axio."""
    for nome in _VENVS:
        for relativa in ("Scripts/python.exe", "bin/python"):
            alvo = os.path.join(raiz, nome, relativa.replace("/", os.sep))
            if os.path.isfile(alvo):
                return os.path.realpath(alvo)
    return sys.executable


def comando_python(script, raiz):
    """A linha que abre o pdb (o depurador que ja vem dentro do Python) sobre 'script'."""
    if not script or not os.path.isfile(script):
        return ""
    return " ".join([f'"{python_do_projeto(raiz)}"', "-u", "-m", "pdb", f'"{script}"'])


def _ficheiro_de(nome, raiz):
    """O ficheiro de um ponto: o caminho dado, o mesmo dentro do projeto, ou pelo nome."""
    if not nome:
        return ""
    dado = os.path.normpath(nome.replace("/", os.sep))
    if os.path.isfile(dado):
        return os.path.realpath(dado)
    dentro = os.path.normpath(os.path.join(raiz, dado))
    if os.path.isfile(dentro):
        return os.path.realpath(dentro)
    procurado = os.path.basename(dado).lower()
    achados = []
    for pasta, subpastas, ficheiros in os.walk(raiz):
        subpastas[:] = [s for s in subpastas
                        if not s.startswith(".") and s not in ("node_modules", "__pycache__")]
        achados += [os.path.join(pasta, f) for f in ficheiros if f.lower() == procurado]
        if len(achados) > 20:
            break
    if not achados:
        return ""
    achados.sort(key=lambda c: (c.count(os.sep), len(c)))
    return os.path.realpath(achados[0])


def script_de_arranque(alvo, raiz):
    """O ficheiro Python que a sessao corre quando nao ha nenhum ponto marcado."""
    if alvo:
        return _ficheiro_de(alvo, raiz)
    for nome in ("main.py", "app.py", "run.py", "__main__.py"):
        caminho = os.path.join(raiz, nome)
        if os.path.isfile(caminho):
            return os.path.realpath(caminho)
    return ""


def pontos_python(texto, raiz):
    """Le os pontos de paragem, resolvendo cada ficheiro dentro da pasta do projeto."""
    limpos = []
    for pedaco in _pedacos(texto):
        ficheiro, separador, linha = pedaco.rpartition(":")
        if not separador or not linha.strip().isdigit():
            continue
        caminho = _ficheiro_de(ficheiro.strip().strip('"').strip("'"), raiz)
        if caminho:
            limpos.append({"ficheiro": caminho, "linha": int(linha.strip())})
    return limpos


def preparacao_python(pontos, script):
    """Os comandos que abrem a sessao: os pontos marcados e seguir.

    No ficheiro que vai correr o ponto vai pelo NUMERO da linha - o pdb resolve-o contra o
    ficheiro aberto, sem caminho nenhum. Nos outros o caminho tem de ser o REAL: o pdb
    compara-o com o que a execucao reporta, e um nome curto do Windows (RODRIG~1) nunca
    casa com o nome longo, o que deixaria o ponto a nunca disparar.
    """
    alvo = os.path.normcase(os.path.realpath(script))
    linhas = []
    for ponto in pontos:
        caminho = os.path.realpath(ponto["ficheiro"])
        if os.path.normcase(caminho) == alvo:
            linhas.append(f"b {ponto['linha']}")
        else:
            linhas.append(f"b {caminho}:{ponto['linha']}")
    linhas.append("c")
    return linhas


SESSAO = {"id": "", "executavel": ""}
JANELA_DA_LEITURA = 80
_LEITURA = {"sobre": {}, "linhas": []}


def guardar_sessao(registo_id, executavel):
    """Anota a sessao aberta, para os comandos seguintes irem para o mesmo card."""
    SESSAO["id"] = registo_id
    SESSAO["executavel"] = executavel
    _LEITURA["sobre"] = {}
    _LEITURA["linhas"] = []


def esquecer_sessao():
    SESSAO["id"] = ""
    SESSAO["executavel"] = ""
    _LEITURA["sobre"] = {}
    _LEITURA["linhas"] = []


def sessao_aberta():
    """Diz se ha uma sessao anotada (se ainda corre, quem confirma e o processo)."""
    return bool(SESSAO["id"])


def card_da_sessao():
    """O card onde a sessao de depuracao esta aberta."""
    return SESSAO["id"]


_LEITURA_TRANCA = threading.Lock()


def leitura_nova(texto):
    """Le a saida do depurador e devolve, em linguagem simples, o que ela diz de NOVO: as
    linhas que ja foram escritas no card nao se repetem a cada passo da sessao."""
    with _LEITURA_TRANCA:
        _LEITURA["sobre"] = leitura_depurador.leitura(texto, _LEITURA["sobre"])
        atuais = leitura_depurador.linhas(_LEITURA["sobre"])
        anteriores = _LEITURA["linhas"]
        novas = [linha for linha in atuais if linha not in anteriores]
        _LEITURA["linhas"] = atuais
        return novas


def paragem_atual():
    """Onde a execucao esta, em ficheiro e linha - e isto que o editor abre quando ela para.

    'acontecimento' diz se houve algo que explique a paragem (um ponto de paragem apanhado ou
    uma queda). O sitio onde o depurador fica parado mal arranca nao conta como paragem: sem
    esta separacao o editor saltava para a primeira linha do ficheiro em todas as sessoes."""
    with _LEITURA_TRANCA:
        sobre = dict(_LEITURA["sobre"] or {})
    parou = dict(sobre.get("parou") or {})
    motivo = (sobre.get("motivo") or "").strip()
    caminho = (parou.get("caminho") or "").strip()
    linha = int(parou.get("linha") or 0)
    if not caminho or not linha:
        return {}
    return {"arquivo": os.path.realpath(caminho) if os.path.isfile(caminho) else caminho,
            "linha": linha,
            "queda": leitura_depurador.e_queda(motivo),
            "acontecimento": bool(motivo) and not motivo.startswith("arranque do programa")}


def texto_dos_comandos():
    return "\n".join(f"  {comando}  -  {para_que}" for comando, para_que in COMANDOS_UTEIS)


def texto_dos_comandos_py():
    return "\n".join(f"  {comando}  -  {para_que}" for comando, para_que in COMANDOS_UTEIS_PY)


def controles(motor_escolhido):
    """Os botoes que o card mostra, ja com o comando certo da linguagem desta sessao."""
    if motor_escolhido not in ("cpp", "python"):
        return []
    posicao = 2 if motor_escolhido == "cpp" else 3
    return [{"id": item[0], "rotulo": item[1], "comando": item[posicao], "dica": item[4]}
            for item in CONTROLES]


def comandos_do_pedido(texto):
    """Le os comandos a enviar na sessao: um por linha, ou separados por ';'."""
    linhas = []
    for pedaco in (texto or "").replace("\r", "\n").replace(";", "\n").split("\n"):
        comando = pedaco.strip()
        if comando:
            linhas.append(comando)
    return linhas
