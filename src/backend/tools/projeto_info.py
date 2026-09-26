"""Retrato do projeto para o painel de informacoes e o contexto do prompt.

Arvore estruturada (com linhas por ficheiro e totais por pasta), stack, a
assinatura que invalida o retrato e a medicao em fio de fundo. O painel responde
sempre com o que tem em cache e mede so quando a assinatura do projeto muda -
medir abre cada ficheiro para contar linhas e extrair imports (0,6-0,9s).
"""
import os
import sys
import json
import time
import re
import hashlib
import threading

from src.backend.state import MSG_SEM_PASTA, estado
from src.backend.tools.dependencias import (
    dependencias_do_codigo,
    manifests_do_projeto,
    manifests_em_texto,
)
from src.backend.tools.projeto_comum import (
    PASTAS_IGNORADAS,
    arquivos_de_codigo,
    contar_linhas,
    eh_arquivo_de_codigo,
    eh_arquivo_texto,
    gravar_cache_projeto,
    ler_cache_projeto,
)

MAX_PROF_ARVORE = 4
MAX_NO_ARVORE = 1500
MAX_NO_ARVORE_OCULTOS = 4000
MAX_ARQUIVOS_CONTEXTO = 600
LIMITE_PODA_OCULTOS = 400
LIMITE_LINHAS_OCULTOS = 512000
_cache_contexto = {"texto": "", "ts": 0.0}
_estado_info = {"raiz": "", "correndo": False, "ts": 0.0, "assinatura": "",
                "dados": None, "erro": "", "assinatura_ocultos": "",
                "dados_ocultos": None}
_trava_info = threading.Lock()
_VERSAO_INFO_PROJETO = 3


_MARCADORES_STACK = (
    ("requirements.txt", "Python"),
    ("pyproject.toml", "Python"),
    ("Pipfile", "Python"),
    ("package.json", "JavaScript/Node"),
    ("tsconfig.json", "TypeScript"),
    ("Cargo.toml", "Rust"),
    ("go.mod", "Go"),
    ("CMakeLists.txt", "C++ (CMake)"),
    ("meson.build", "C/C++ (Meson)"),
    ("build.gradle", "Java (Gradle)"),
    ("pom.xml", "Java (Maven)"),
)
_EXTENSAO_STACK = (
    ((".cpp", ".cc", ".cxx", ".hpp", ".hh", ".h"), "C++"),
    ((".c",), "C"),
    ((".py",), "Python"),
    ((".ts", ".tsx"), "TypeScript"),
    ((".js", ".jsx", ".mjs", ".cjs"), "JavaScript"),
    ((".rs",), "Rust"),
    ((".go",), "Go"),
    ((".java",), "Java"),
    ((".cs",), "C#"),
    ((".rb",), "Ruby"),
    ((".php",), "PHP"),
)
_RE_QT = re.compile(r"find_package\s*\(\s*(Qt[56])")
_RE_CXX_STANDARD = re.compile(r"CXX_STANDARD\s+(\d+)|cxx_std_(\d+)")


def _linguagem_por_ficheiros():
    contagem = {}
    for caminho in arquivos_de_codigo(400):
        ext = os.path.splitext(caminho)[1].lower()
        for extensoes, nome in _EXTENSAO_STACK:
            if ext in extensoes:
                contagem[nome] = contagem.get(nome, 0) + 1
                break
    if not contagem:
        return ""
    return max(contagem.items(), key=lambda par: par[1])[0]


def _detalhes_nativos(raiz):
    """Versoes que o projeto declara fora do mundo Python (Qt, standard de C++, Node)."""
    partes = []
    cmake = os.path.join(raiz, "CMakeLists.txt")
    if os.path.exists(cmake):
        try:
            with open(cmake, "r", encoding="utf-8", errors="ignore") as f:
                texto = f.read()
        except OSError:
            texto = ""
        achado = _RE_QT.search(texto)
        if achado:
            partes.append(achado.group(1).replace("Qt", "Qt "))
        padrao = _RE_CXX_STANDARD.search(texto)
        if padrao:
            partes.append("C++" + (padrao.group(1) or padrao.group(2)))
    pkg_path = os.path.join(raiz, "package.json")
    if os.path.exists(pkg_path):
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                engines = (json.load(f).get("engines") or {})
            if engines.get("node"):
                partes.append(f"Node {engines['node']}")
        except (OSError, ValueError):
            pass
    for nome_arq in (".nvmrc", ".node-version"):
        caminho = os.path.join(raiz, nome_arq)
        if os.path.exists(caminho):
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    versao = f.read().strip()
            except OSError:
                versao = ""
            if versao:
                partes.append(f"Node {versao}")
                break
    return (", " + ", ".join(partes)) if partes else ""


def _detectar_stack():
    """Stack que o PROJETO aberto declara - nunca a do Axio.

    A versao do interprete que corre o Axio so entra quando o projeto e mesmo
    Python: antes disto o contexto anunciava 'Python 3.14' a um projeto CMake/Qt
    inteiro, ou seja, dava ao modelo uma stack falsa sobre o projeto aberto.
    """
    raiz = estado.get("pasta_raiz", "")
    if not raiz or not os.path.isdir(raiz):
        return f"Python {sys.version.split()[0]}"
    try:
        nomes = {n.lower() for n in os.listdir(raiz)}
    except OSError:
        nomes = set()
    itens = []
    for ficheiro, rotulo in _MARCADORES_STACK:
        if ficheiro.lower() in nomes and rotulo not in itens:
            itens.append("Python " + sys.version.split()[0] if rotulo == "Python" else rotulo)
    if any(n.endswith(".sln") for n in nomes) and "C++ (.sln)" not in itens:
        itens.append("C++ (.sln)")
    if any(n.endswith(".csproj") for n in nomes) and ".NET (MSBuild)" not in itens:
        itens.append(".NET (MSBuild)")
    detalhe = _detalhes_nativos(raiz)
    if itens:
        return ", ".join(itens) + detalhe
    predominante = _linguagem_por_ficheiros()
    if predominante:
        return f"{predominante} (pela extensao dos ficheiros)" + detalhe
    return "(nao identificada)"

def _arvore_resumida(raiz, max_prof=3, max_entradas=80):
    linhas = []
    contador = {"n": 0}
    limite_dir = 30

    def _walk(pasta, prefixo, prof):
        if prof > max_prof or contador["n"] >= max_entradas:
            return
        try:
            entradas = sorted(os.listdir(pasta), key=lambda n: n.lower())
        except OSError:
            return
        dirs = [e for e in entradas if os.path.isdir(os.path.join(pasta, e)) and e not in PASTAS_IGNORADAS and not e.startswith(".")]
        files = [e for e in entradas if os.path.isfile(os.path.join(pasta, e))]
        exibir = (dirs + files)[:limite_dir]
        for idx, e in enumerate(exibir):
            contador["n"] += 1
            if contador["n"] > max_entradas:
                linhas.append(prefixo + "... (truncado)")
                return
            eh_ultimo = idx == len(exibir) - 1
            ramo = "└── " if eh_ultimo else "├── "
            caminho = os.path.join(pasta, e)
            if os.path.isdir(caminho):
                linhas.append(prefixo + ramo + e + "/")
                _walk(caminho, prefixo + ("    " if eh_ultimo else "│   "), prof + 1)
            else:
                linhas.append(prefixo + ramo + e)
    _walk(raiz, "", 1)
    return "\n".join(linhas) if linhas else "(pasta vazia)"

def _stats_codigo(arquivos):
    por_ext = {}
    for caminho in arquivos:
        ext = os.path.splitext(caminho)[1].lower() or "(sem ext)"
        por_ext[ext] = por_ext.get(ext, 0) + 1
    resumo = f"{len(arquivos)} arquivos de código"
    if por_ext:
        topo = ", ".join(f"{k}:{v}" for k, v in sorted(por_ext.items(), key=lambda x: -x[1])[:10])
        resumo += f" | {topo}"
    return resumo

def _contar_ficheiros(pasta):
    """Quantos ficheiros existem dentro desta pasta, em qualquer nivel."""
    total = 0
    for _, _, ficheiros in os.walk(pasta):
        total += len(ficheiros)
    return total

def _tamanho(caminho):
    try:
        return os.path.getsize(caminho)
    except OSError:
        return 0

def _no_oculto(nome, caminho):
    """No de um ficheiro que o painel esconde: linhas quando e texto, peso quando nao.

    Contar linhas de um binario daria um numero sem sentido e ler um ficheiro
    enorme so para o contar atrasa a medicao: nesses dois casos o que se mostra e
    o tamanho, que e a informacao verdadeira que existe.
    """
    no = {"nome": nome, "tipo": "ficheiro", "oculto": True,
          "ext": os.path.splitext(nome)[1].lower() if eh_arquivo_de_codigo(nome) else "",
          "linhas": 0}
    tamanho = _tamanho(caminho)
    if eh_arquivo_texto(nome) and tamanho <= LIMITE_LINHAS_OCULTOS:
        no["linhas"] = contar_linhas(caminho)
    else:
        no["tamanho"] = tamanho
    return no

def _arvore_estruturada(raiz, com_ocultos=False, max_prof=MAX_PROF_ARVORE, max_nos=None):
    """Arvore de pastas e ficheiros com linhas e totais por pasta.

    Devolve DADOS (nao texto) porque o painel de informacoes do workspace precisa
    de recolher e expandir cada no; `_arvore_resumida` continua a ser a versao em
    texto injetada no contexto do prompt.

    Com `com_ocultos` (o olho do explorer) entram tambem os ficheiros que o painel
    esconde - pastas de build e de cache, nomes com ponto inicial, binarios e o que
    nao e codigo -, todos marcados com `oculto`. Uma pasta oculta com milhares de
    ficheiros dentro (node_modules, .git, .axio) entra fechada, com o numero de
    ficheiros que tem: o que interessa e saber que la esta e quanto ocupa, nao
    abrir a tripa de meio projeto nem ler ficheiros que ninguem vai ler.
    """
    contador = {"nos": 0}
    if max_nos is None:
        max_nos = MAX_NO_ARVORE_OCULTOS if com_ocultos else MAX_NO_ARVORE

    def _no_pasta(caminho, prof):
        try:
            nomes = sorted(os.listdir(caminho), key=str.lower)
        except OSError:
            return None
        pastas, ficheiros = [], []
        for nome in nomes:
            lista = pastas if os.path.isdir(os.path.join(caminho, nome)) else ficheiros
            lista.append(nome)
        filhos = []
        for nome in ficheiros + pastas:
            if contador["nos"] >= max_nos:
                break
            completo = os.path.join(caminho, nome)
            escondido = nome in PASTAS_IGNORADAS or nome.startswith(".")
            if os.path.isdir(completo):
                if prof >= max_prof or (escondido and not com_ocultos):
                    continue
                if escondido:
                    total = _contar_ficheiros(completo)
                    if total > LIMITE_PODA_OCULTOS:
                        contador["nos"] += 1
                        filhos.append({"nome": nome, "tipo": "pasta", "linhas": 0,
                                       "oculto": True, "omitidos": total, "filhos": []})
                        continue
                filho = _no_pasta(completo, prof + 1)
                if filho and (filho["filhos"] or escondido):
                    if escondido:
                        filho["oculto"] = True
                    filhos.append(filho)
            elif eh_arquivo_de_codigo(nome):
                contador["nos"] += 1
                filhos.append({"nome": nome, "tipo": "ficheiro",
                               "ext": os.path.splitext(nome)[1].lower(),
                               "linhas": contar_linhas(completo)})
            elif com_ocultos:
                contador["nos"] += 1
                filhos.append(_no_oculto(nome, completo))
        return {"nome": os.path.basename(caminho) or caminho, "tipo": "pasta",
                "linhas": sum(f["linhas"] for f in filhos), "filhos": filhos}

    return _no_pasta(raiz, 0) or {"nome": os.path.basename(raiz), "tipo": "pasta",
                                  "linhas": 0, "filhos": []}

def _agregar_arvore(no, acc):
    """Acumula arquivos, linhas, pastas e a quebra por extensao de um no."""
    for f in no.get("filhos", []):
        if f["tipo"] == "pasta":
            acc["pastas"] += 1
            _agregar_arvore(f, acc)
        else:
            acc["arquivos"] += 1
            acc["linhas"] += f["linhas"]
            ext = f.get("ext") or ""
            if not ext:
                continue
            item = acc["extensoes"].setdefault(ext, {"arquivos": 0, "linhas": 0})
            item["arquivos"] += 1
            item["linhas"] += f["linhas"]

def _assinatura_projeto(raiz):
    """Impressao digital do projeto: caminho, mtime e tamanho de cada ficheiro.

    Percorre a arvore sem abrir um unico ficheiro. O que custa na medicao completa
    nao e listar pastas, e LER o conteudo (contar linhas, extrair imports): medido
    neste projeto, o retrato custa 0,6-0,9s e esta varredura 0,014s. E o que permite
    perguntar \"mudou alguma coisa?\" a cada abertura do painel em vez de escolher
    entre aceitar um retrato velho e pagar a medicao outra vez.
    """
    partes = []
    for base, pastas, arquivos in os.walk(raiz):
        pastas[:] = [p for p in pastas if p not in PASTAS_IGNORADAS and not p.startswith(".")]
        for nome in arquivos:
            if not eh_arquivo_de_codigo(nome):
                continue
            caminho = os.path.join(base, nome)
            try:
                st = os.stat(caminho)
            except OSError:
                continue
            partes.append(f"{os.path.relpath(caminho, raiz)}|{st.st_mtime_ns}|{st.st_size}")
    partes.sort()
    return hashlib.sha1("\n".join(partes).encode("utf-8")).hexdigest()

def _retrato_projeto(raiz, com_ocultos=False):
    """Mede o projeto inteiro: arvore, linguagens, stack, manifests e dependencias.

    Reusa as mesmas medicoes do contexto do prompt (`_detectar_stack` e
    `manifests_do_projeto`) e mede aqui o que so o painel precisa: arvore de
    codigo com linhas por ficheiro e por pasta.
    """
    arvore = _arvore_estruturada(raiz, com_ocultos)
    acc = {"arquivos": 0, "linhas": 0, "pastas": 0, "extensoes": {}}
    _agregar_arvore(arvore, acc)
    linguagens = [{"ext": ext, "arquivos": v["arquivos"], "linhas": v["linhas"]}
                  for ext, v in sorted(acc["extensoes"].items(), key=lambda x: -x[1]["linhas"])]
    return {
        "raiz": raiz,
        "stack": _detectar_stack(),
        "linguagens": linguagens,
        "manifests": manifests_do_projeto(raiz),
        "dependencias_codigo": dependencias_do_codigo(raiz),
        "totais": {"arquivos": acc["arquivos"], "linhas": acc["linhas"],
                   "pastas": acc["pastas"], "linguagens": len(linguagens)},
        "arvore": arvore,
        "com_ocultos": bool(com_ocultos),
    }

def _medir_info_projeto(raiz, assinatura, com_ocultos=False):
    dados = _retrato_projeto(raiz, com_ocultos)
    with _trava_info:
        if com_ocultos:
            _estado_info.update({"assinatura_ocultos": assinatura,
                                 "dados_ocultos": dados, "erro": ""})
        else:
            _estado_info.update({"ts": time.time(), "assinatura": assinatura,
                                 "dados": dados, "erro": ""})
    if not com_ocultos:
        gravar_cache_projeto("projeto_info.json",
                              {"versao": _VERSAO_INFO_PROJETO, "assinatura": assinatura,
                               "dados": dados})

def _medir_info_em_fundo(raiz, assinatura, com_ocultos=False):
    try:
        _medir_info_projeto(raiz, assinatura, com_ocultos)
    except Exception as e:
        with _trava_info:
            _estado_info["erro"] = str(e)
    finally:
        with _trava_info:
            _estado_info["correndo"] = False

def _garantir_info_projeto(raiz, com_ocultos=False):
    """Hidrata a cache (memoria -> disco) e remede em fundo se algo mudou.

    A cache e validada pela ASSINATURA do projeto e nao por tempo: um retrato de
    ontem continua bom se nenhum ficheiro mudou, e um de agora mesmo esta velho se
    um ficheiro acabou de ser gravado (o agente edita este projeto o tempo todo).

    Sao DUAS medicoes independentes guardadas lado a lado: a normal (so o projeto)
    e a do olho (`com_ocultos`). A pesada nunca e paga sem alguem a pedir, e nunca
    passa por cima da normal - quem abre o painel sem o olho recebe sempre a leve,
    mesmo que a outra esteja a ser medida naquele instante.
    """
    with _trava_info:
        if _estado_info["raiz"] != raiz:
            _estado_info.update({"raiz": raiz, "correndo": False, "ts": 0.0,
                                 "assinatura": "", "dados": None, "erro": "",
                                 "assinatura_ocultos": "", "dados_ocultos": None})
        if not _estado_info["assinatura"]:
            disco = ler_cache_projeto("projeto_info.json", ("assinatura", "dados"),
                                       versao=_VERSAO_INFO_PROJETO)
            if disco:
                _estado_info.update({"ts": disco.get("ts") or 0.0,
                                     "assinatura": disco["assinatura"],
                                     "dados": disco["dados"]})
        if _estado_info["correndo"]:
            return
    assinatura = _assinatura_projeto(raiz)
    with _trava_info:
        if _estado_info["correndo"]:
            return
        chave = "assinatura_ocultos" if com_ocultos else "assinatura"
        guardado = "dados_ocultos" if com_ocultos else "dados"
        if assinatura == _estado_info[chave] and _estado_info[guardado]:
            return
        _estado_info["correndo"] = True
    threading.Thread(target=_medir_info_em_fundo, args=(raiz, assinatura, com_ocultos),
                     daemon=True).start()

def dados_projeto(com_ocultos=False):
    """Retrato estruturado do projeto para o painel de informacoes (JSON).

    Responde SEMPRE com o que tem em cache e mede o resto num fio de fundo: o
    retrato completo custa 0,6-0,9s (abre cada ficheiro para contar linhas e
    extrair imports), o que fazia o painel abrir em \"A medir o projeto...\" a cada
    consulta. A cache so e invalidada quando um ficheiro de codigo muda.

    `com_ocultos` serve o olho do explorer: devolve a arvore COM o que o painel
    esconde (e os totais a contar isso), que e uma medicao a parte e mais cara.
    """
    raiz = estado.get("pasta_raiz", "")
    if not raiz or not os.path.isdir(raiz):
        return {"erro": MSG_SEM_PASTA}
    _garantir_info_projeto(raiz, com_ocultos)
    with _trava_info:
        dados = _estado_info["dados_ocultos" if com_ocultos else "dados"]
        correndo = _estado_info["correndo"]
        erro = _estado_info["erro"]
    if dados is None:
        if erro:
            return {"erro": "Nao foi possivel medir o projeto: " + erro}
        return {"estado": "a_medir"}
    resposta = dict(dados)
    resposta.update({"estado": "a_medir" if correndo else "pronto", "erro": erro})
    return resposta

def preaquecer_info_projeto(raiz=None):
    """Mede o projeto em fundo mal a pasta e fixada, antes de o painel ser aberto.

    Sem isto a primeira abertura de cada sessao pagaria os 0,6s da medicao com o
    painel nas maos do utilizador; com isto, quando ele abre, ja esta em cache.
    """
    raiz = raiz or estado.get("pasta_raiz", "")
    if raiz and os.path.isdir(raiz):
        _garantir_info_projeto(raiz)

def gerar_contexto_projeto():
    raiz = estado.get("pasta_raiz", "")
    if not raiz:
        return "(nenhuma pasta de projeto selecionada)"
    agora = time.time()
    if _cache_contexto["texto"] and (agora - _cache_contexto["ts"]) < 120:
        return _cache_contexto["texto"]
    arquivos = arquivos_de_codigo(MAX_ARQUIVOS_CONTEXTO)
    stack = _detectar_stack()
    partes = [
        f"Raiz: {raiz}",
        f"Stack: {stack}",
        f"Arquivos: {_stats_codigo(arquivos)}",
        f"Dependências:\n{manifests_em_texto(raiz)}",
        f"Estrutura:\n{_arvore_resumida(raiz)}",
    ]
    texto = "\n".join(partes)
    _cache_contexto["texto"] = texto
    _cache_contexto["ts"] = agora
    return texto

