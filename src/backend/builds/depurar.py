import ast
import os
import sys
import threading

from src.backend.builds import leitura_depurador

_PASTA_DEPURADORES = ("Windows Kits/10/Debuggers", "Windows Kits/11/Debuggers")
_ARQUITETURAS = ("x64", "x86", "arm64", "arm")
_VENVS = (".venv", "venv", "env")
_EXTENSOES_CPP = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx")
_EXTENSOES_PY = (".py", ".pyw")
_PASTAS_A_FORA = ("venv", "env", "node_modules", "__pycache__", "build", "dist", "gerados")
_MARCAS_NATIVAS = ("cmakelists.txt", "meson.build", "makefile", "gnumakefile")
_SUFIXOS_NATIVOS = (".sln", ".vcxproj", ".pro", ".pri")
_NOMES_DE_ENTRADA = ("main.py", "app.py", "run.py", "__main__.py")
_MAX_FICHEIROS_PY = 200

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


def motor_do_alvo(breakpoints, alvo, raiz=""):
    """O depurador que sabe ler o que foi pedido: pelos pontos marcados, sem eles pelo ficheiro
    aberto no editor e, sem ficheiro nenhum, pelo que a pasta tem la dentro - e isto que faz o
    botao de depurar trabalhar com a janela do codigo fechada."""
    if _pedacos(breakpoints):
        return motor(breakpoints)
    if alvo:
        return "python" if _extensao_do_ponto(alvo) in _EXTENSOES_PY else "cpp"
    return "python" if _entrada_do_projeto(raiz) else "cpp"


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


def _tem_projeto_nativo(raiz):
    """Diz se a pasta tem um projeto nativo a vista: onde ele manda, o Python nao e o alvo."""
    try:
        nomes = [nome.lower() for nome in os.listdir(raiz)]
    except OSError:
        return False
    if any(nome in _MARCAS_NATIVAS for nome in nomes):
        return True
    return any(nome.endswith(_SUFIXOS_NATIVOS) for nome in nomes)


def _ficheiros_python(raiz):
    """Os .py da pasta, sem descer a venvs, pastas de build nem pastas escondidas."""
    achados = []
    for pasta, subpastas, ficheiros in os.walk(raiz):
        subpastas[:] = [s for s in subpastas
                        if not s.startswith(".") and s.lower() not in _PASTAS_A_FORA]
        achados += [os.path.join(pasta, f) for f in ficheiros
                    if f.lower().endswith(_EXTENSOES_PY) and f != "__init__.py"]
        if len(achados) > _MAX_FICHEIROS_PY:
            break
    return achados


def _importados_por(caminho):
    """Os nomes de modulo que um ficheiro importa, pelo primeiro pedaco de cada um."""
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as ficheiro:
            arvore = ast.parse(ficheiro.read())
    except (OSError, SyntaxError, ValueError):
        return set()
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes |= {apelido.name.split(".")[0].lower() for apelido in no.names}
        elif isinstance(no, ast.ImportFrom) and no.module and not no.level:
            nomes.add(no.module.split(".")[0].lower())
    return nomes


def _entrada_do_projeto(raiz):
    """O ficheiro Python por onde a pasta arranca quando ninguem abriu nenhum: um nome classico
    de entrada, ou o modulo que nenhum outro importa - quem importa os outros e o programa,
    quem e importado e biblioteca. Pasta com projeto nativo la dentro nao tem entrada Python."""
    if not raiz or not os.path.isdir(raiz) or _tem_projeto_nativo(raiz):
        return ""
    for nome in _NOMES_DE_ENTRADA:
        caminho = os.path.join(raiz, nome)
        if os.path.isfile(caminho):
            return os.path.realpath(caminho)
    ficheiros = _ficheiros_python(raiz)
    if not ficheiros:
        return ""
    importados = set()
    for caminho in ficheiros:
        importados |= _importados_por(caminho)
    livres = [caminho for caminho in ficheiros
              if os.path.splitext(os.path.basename(caminho))[0].lower() not in importados]
    if not livres:
        return ""
    livres.sort(key=lambda caminho: (caminho.count(os.sep), len(caminho)))
    return os.path.realpath(livres[0])


def script_de_arranque(alvo, raiz):
    """O ficheiro Python que a sessao corre: o indicado, ou o que a pasta tem por entrada."""
    if alvo:
        return _ficheiro_de(alvo, raiz)
    return _entrada_do_projeto(raiz)


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
_LIMITE_DE_ESCRITAS = 5000
_LEITURA = {"sobre": {}, "escritas": set()}


def guardar_sessao(registo_id, executavel):
    """Anota a sessao aberta, para os comandos seguintes irem para o mesmo card."""
    SESSAO["id"] = registo_id
    SESSAO["executavel"] = executavel
    _limpar_leitura()


def esquecer_sessao():
    SESSAO["id"] = ""
    SESSAO["executavel"] = ""
    _limpar_leitura()


def _limpar_leitura():
    """Comeca um retrato novo: o que ja foi dito pertence a sessao que acabou."""
    _LEITURA["sobre"] = {}
    _LEITURA["escritas"] = set()


def sessao_aberta():
    """Diz se ha uma sessao anotada (se ainda corre, quem confirma e o processo)."""
    return bool(SESSAO["id"])


def card_da_sessao():
    """O card onde a sessao de depuracao esta aberta."""
    return SESSAO["id"]


_LEITURA_TRANCA = threading.Lock()


def leitura_nova(texto):
    """Le a saida NOVA do depurador e devolve, em linguagem simples, o que ainda nao foi dito
    nesta sessao. O que ja saiu uma vez nao volta a sair: uma linha que reaparece (o reinicio
    do pdb, um motivo ja lido) fica calada em vez de encher o card."""
    with _LEITURA_TRANCA:
        _LEITURA["sobre"] = leitura_depurador.leitura(texto, _LEITURA["sobre"])
        atuais = leitura_depurador.linhas(_LEITURA["sobre"])
        escritas = _LEITURA["escritas"]
        if len(escritas) > _LIMITE_DE_ESCRITAS:
            escritas.clear()
        novas = [linha for linha in atuais if linha not in escritas]
        escritas.update(novas)
        return novas


def programa_terminou():
    """Diz se o programa depurado ja correu ate ao fim."""
    with _LEITURA_TRANCA:
        return bool((_LEITURA["sobre"] or {}).get("terminou"))


def paragem_atual():
    """Onde a execucao esta, em ficheiro e linha - e isto que o editor abre quando ela para.

    'acontecimento' diz se houve algo que explique a paragem (um ponto de paragem apanhado ou
    uma queda). O sitio onde o depurador fica parado mal arranca nao conta como paragem: sem
    esta separacao o editor saltava para a primeira linha do ficheiro em todas as sessoes.
    Numa queda o sitio do ERRO ganha ao sitio da paragem: o pdb fica no import que chamou o
    modulo que nao compila, e editar esse import nao resolve nada."""
    with _LEITURA_TRANCA:
        sobre = dict(_LEITURA["sobre"] or {})
    parou = dict(sobre.get("parou") or {})
    motivo = (sobre.get("motivo") or "").strip()
    caminho = (parou.get("caminho") or "").strip()
    linha = int(parou.get("linha") or 0)
    if not caminho or not linha:
        return {}
    queda = leitura_depurador.e_queda(motivo)
    if queda:
        erro = dict(sobre.get("erro") or {})
        if erro.get("caminho") and erro.get("linha"):
            caminho = erro["caminho"].strip()
            linha = int(erro["linha"])
    return {"arquivo": os.path.realpath(caminho) if os.path.isfile(caminho) else caminho,
            "linha": linha,
            "queda": queda,
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
