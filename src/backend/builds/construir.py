import os
import re

from src.backend.builds import cmake_api, detetar, kits, msbuild, presets

TIMEOUT_CONFIGURAR = 420
TIMEOUT_CONSTRUIR = 3000

_PASTAS_DE_SONDA = ("CMakeFiles", "CMakeScratch", "_deps", ".git")
_PASTAS_FORA_DO_CENSO = ("Release", "Debug", "RelWithDebInfo", "MinSizeRel", "obj", "bin", "x64")
_SUFIXOS_DE_FONTE = (".cpp", ".cxx", ".cc", ".c", ".m", ".mm")
_SUFIXOS_DE_CABECALHO = (".h", ".hpp", ".hxx", ".hh")
_PASSO_NO_LOG = re.compile(r"^\[(\d+)/(\d+)\]")


def preparar(pasta, configuracao="debug", plataforma=""):
    """Decide o que e preciso para construir: que projeto e, que kit o serve e que preset fica escrito.

    Nao executa nada - devolve os comandos ja formados. Quem os corre e quem tem o processo
    na mao, para o build ficar no painel do terminal e nao num canto invisivel.

    `plataforma` e a escolha do utilizador no menu C++ (x86/x64). Vazia, o projeto decide sozinho;
    preenchida e invalida para este projeto, o build recusa em vez de compilar outra coisa.
    """
    deteccao = detetar.detetar(pasta)
    if deteccao.get("erro"):
        return {"erro": deteccao["erro"]}
    recusa = _plataforma_recusada(deteccao, plataforma)
    if recusa:
        return {"deteccao": deteccao, "faltam": [recusa]}
    if deteccao["tipo"] == "msbuild":
        return _preparar_msbuild(deteccao, configuracao, plataforma)
    if deteccao["tipo"] != "cmake":
        return {"deteccao": deteccao, "faltam": [_sem_caminho(deteccao)]}
    escolha = kits.escolher_kit(deteccao, kits.kits_instalados(deteccao.get("prefixos", ())))
    if escolha["faltam"]:
        return {"deteccao": deteccao, "escolha": escolha, "faltam": escolha["faltam"]}
    _acrescentar_sanitizador(escolha, configuracao)
    escrita = presets.escrever(deteccao["pasta"], escolha, configuracao)
    if escrita.get("erro"):
        return {"deteccao": deteccao, "escolha": escolha, "faltam": [escrita["erro"]]}
    cmake_api.escrever_pedido(escrita["pasta_build"])
    return {
        "deteccao": deteccao,
        "escolha": escolha,
        "escrita": escrita,
        "configurar": f"cmake --preset {escrita['preset']}",
        "construir": f"cmake --build --preset {escrita['preset']}",
        "pasta_build": escrita["pasta_build"],
        "precisa_configurar": not os.path.isfile(
            os.path.join(escrita["pasta_build"], "CMakeCache.txt")
        ),
    }


def plataforma_do_build(pasta):
    """A plataforma com que este projeto vai ser compilado - o que o menu C++ mostra ANTES de carregar.

    Um projeto do Visual Studio traz a sua (a que tem as dependencias ligadas); um CMake e sempre x64,
    porque e o que o preset do Axio escreve. Sem projeto conhecido devolve vazio, para o menu nao
    escrever uma plataforma que nao sabe.
    """
    deteccao = detetar.detetar(pasta or "")
    if deteccao.get("erro"):
        return ""
    if deteccao["tipo"] == "msbuild":
        return _plataforma_do_msbuild(deteccao)
    if deteccao["tipo"] == "cmake":
        return "x64"
    return ""


def plataformas_do_build(pasta):
    """Entre que plataformas se pode escolher ao compilar este projeto - o que o menu C++ oferece.

    Manda o projeto: um do Visual Studio oferece as plataformas que ele tem LIGADAS, porque as
    dependencias costumam estar numa so, e so oferece as duas quando nao liga nenhuma (projeto
    recem-criado), onde a escolha e mesmo do utilizador. Um CMake do Axio e sempre x64, porque a
    plataforma sai do preset - oferecer x86 seria prometer o que ele nao faz. Sem projeto conhecido
    nao ha escolha nenhuma.
    """
    deteccao = detetar.detetar(pasta or "")
    if deteccao.get("erro"):
        return []
    return _plataformas_suportadas(deteccao)


def _plataformas_suportadas(deteccao):
    if deteccao["tipo"] == "msbuild":
        return _plataformas_do_msbuild(deteccao)
    if deteccao["tipo"] == "cmake":
        return ["x64"]
    return []


def _plataformas_do_msbuild(deteccao):
    """As plataformas que o menu oferece num projeto do Visual Studio.

    As que o projeto tem LIGADAS: oferecer a plataforma sem dependencias e oferecer setenta erros de
    include que nao sao do codigo. Um projeto sem nenhuma ligada nao diz nada sobre plataformas - ai
    a escolha e do utilizador e oferecem-se as duas do Visual Studio.
    """
    ligadas = []
    for bruta in msbuild.plataformas_do_projeto(deteccao["pasta"]):
        normalizada = _normalizar_plataforma(bruta)
        if normalizada and normalizada not in ligadas:
            ligadas.append(normalizada)
    return ligadas or ["x86", "x64"]


def _normalizar_plataforma(valor):
    texto = str(valor or "").strip().lower()
    if texto in ("x86", "win32", "32"):
        return "x86"
    if texto in ("x64", "amd64", "64"):
        return "x64"
    return ""


def _plataforma_recusada(deteccao, plataforma):
    """A razao pela qual a plataforma pedida nao serve para este projeto - vazio quando serve.

    Uma plataforma pedida que nao se reconhece e RECUSADA, e nunca ignorada: cair em silencio na
    plataforma do projeto compilaria outra coisa que nao a pedida, sem ninguem dar por isso.
    """
    pedido = str(plataforma or "").strip()
    if not pedido:
        return ""
    pedida = _normalizar_plataforma(pedido)
    if not pedida:
        return f"Plataforma '{pedido}' desconhecida: use x86 ou x64."
    suportadas = [n for n in (_normalizar_plataforma(p) for p in _plataformas_suportadas(deteccao)) if n]
    if pedida in suportadas:
        return ""
    if not suportadas:
        return (f"Este projeto ({deteccao['rotulo']}) nao declara plataforma nenhuma: nao ha como "
                f"compilar para {pedida}.")
    return (f"Este projeto compila em {' e '.join(suportadas)}; foi pedido {pedida}. Escolha uma "
            f"plataforma do projeto.")


def _preparar_msbuild(deteccao, configuracao, plataforma=""):
    """O plano de um projeto do Visual Studio: que MSBuild, que plataforma e que configuracao."""
    escolha = kits.escolher_kit(deteccao, kits.kits_instalados(deteccao.get("prefixos", ())))
    if escolha["faltam"]:
        return {"deteccao": deteccao, "escolha": escolha, "faltam": escolha["faltam"]}
    if presets.e_sanitizador(configuracao):
        return {"deteccao": deteccao, "escolha": escolha, "faltam": [_sem_sanitizador_msbuild()]}
    alvo = _alvo_do_visual_studio(deteccao)
    if not alvo:
        return {"deteccao": deteccao, "escolha": escolha,
                "faltam": ["A pasta tem um projeto do Visual Studio e nao encontrei nem o .sln nem o "
                           ".vcxproj com as fontes declaradas."]}
    plataforma = _normalizar_plataforma(plataforma) or _plataforma_do_msbuild(deteccao) or "x64"
    nome = "Release" if configuracao == "release" else "Debug"
    escolha["gerador"] = ""
    escolha["arquitetura"] = plataforma
    escolha["cmake"] = None
    escolha.setdefault("notas", []).append(
        f"MSBuild: {escolha['msbuild']['caminho']} ({escolha['msbuild']['produto']})"
    )
    for toolset in msbuild.toolsets_do_projeto(deteccao["pasta"]):
        nota = _nota_do_toolset(toolset)
        if nota:
            escolha["notas"].append(nota)
    em_falta = msbuild.caminhos_de_dependencia(deteccao["pasta"])["em_falta"]
    if em_falta:
        escolha["notas"].append(_texto_caminhos_em_falta(em_falta))
    return {
        "deteccao": deteccao,
        "escolha": escolha,
        "pasta_build": deteccao["pasta"],
        "construir": (f'"{escolha["msbuild"]["caminho"]}" "{alvo}" /t:Build /m /nologo '
                      f"/p:Configuration={nome} /p:Platform={plataforma}"),
    }


def _plataforma_do_msbuild(deteccao):
    """A plataforma do projeto no nome que o utilizador reconhece: 'Win32' e 'x86' sao a mesma coisa.

    Vazio quando o projeto nao declara nenhuma: o menu nao promete uma plataforma que o projeto nao diz.
    """
    return _normalizar_plataforma(msbuild.plataforma_do_projeto(deteccao["pasta"]))


def _acrescentar_sanitizador(escolha, configuracao):
    """Poe o runtime do AddressSanitizer no PATH dos cards quando a configuracao o pede."""
    if not presets.e_sanitizador(configuracao):
        return
    runtime = kits.pasta_do_runtime_asan()
    if not runtime:
        escolha.setdefault("notas", []).append(
            "Foi pedido o AddressSanitizer e o runtime dele nao esta nesta maquina (vem com o "
            "compilador do Visual Studio 2019 16.9 ou mais recente): o programa compila, mas "
            "morre no arranque sem dizer nada."
        )
        return
    escolha["caminhos"] = list(escolha.get("caminhos") or []) + [runtime]


def _sem_caminho(deteccao):
    if deteccao["tipo"] == "desconhecido":
        return ("A pasta nao tem nenhum ficheiro de projeto conhecido (CMakeLists.txt, .sln, .pro, "
                "pyproject.toml...) - nao ha o que construir.")
    if deteccao["tipo"] == "tauri":
        return ("Projeto Tauri (Rust + webview): quem o constroi e o cargo, pela CLI do Tauri "
                "('tauri dev' / 'tauri build'), nao o motor CMake/MSBuild. Iterar no visual faz-se "
                "em modo dev - o frontend e lido do disco e recarrega sem recompilar, e o Rust so "
                "recompila quando ele proprio muda. O build release, com LTO, e so para o "
                "artefacto final.")
    if deteccao["tipo"] == "cargo":
        return ("Projeto Rust (Cargo): quem o constroi e o cargo ('cargo build'), nao o motor "
                "CMake/MSBuild. Para iterar use 'cargo run' - o perfil de debug nao tem LTO e so "
                "recompila o que mudou; o 'cargo build --release' e para o artefacto final.")
    return (f"Projeto {deteccao['rotulo']} (identificado por {', '.join(deteccao['ficheiros'])}): "
            "nesta primeira versao o Axio configura e compila projetos CMake e do Visual Studio. "
            "Os outros ficam a seguir.")


def _alvo_do_visual_studio(deteccao):
    ficheiros = deteccao.get("ficheiros") or []
    for extensao in (".sln", ".vcxproj"):
        achado = next((f for f in ficheiros if f.lower().endswith(extensao)), "")
        if achado:
            return os.path.join(deteccao["pasta"], achado)
    return ""


def _sem_sanitizador_msbuild():
    return ("O AddressSanitizer esta ligado para projetos CMake (e uma opcao do preset). Num projeto "
            "do Visual Studio a flag '/fsanitize=address' teria de ser escrita no proprio projeto, "
            "por isso aqui o que ha para pedir e 'debug' ou 'release'.")


def _texto_caminhos_em_falta(em_falta):
    raiz = _raiz_comum(em_falta)
    onde = f" Todas debaixo de '{raiz}'." if raiz else f" A primeira e '{em_falta[0]}'."
    return (f"ATENCAO: {len(em_falta)} pasta(s) de dependencias que este projeto declara nao existem "
            f"nesta maquina - a compilacao para com 'cannot open include file'."
            f"{onde} Sao caminhos que ficaram no computador onde o projeto foi criado.")


def _nota_do_toolset(pedido):
    """O que dizer sobre o toolset que o projeto pede: com que compilador sai, ou que ele nao esta aqui.

    Cala-se quando o nome nao e de uma familia conhecida - melhor nao dizer nada do que afirmar que falta.
    """
    achado = kits.toolset_instalado(pedido)
    if not achado:
        return ""
    if achado["pasta"]:
        return (f"Toolset {pedido}: compila com o compilador de {achado['produto']} "
                f"({achado['versao']}) em {achado['pasta']}.")
    return (f"ATENCAO: o projeto pede o toolset {pedido} e nao encontrei esse conjunto de ferramentas "
            f"nesta maquina - o MSBuild para antes de compilar, a dizer que nao o encontra. Resolve-se "
            f"instalando-o pelo Visual Studio Installer (separador 'Componentes individuais') ou mudando "
            f"o toolset do projeto.")


def _raiz_comum(caminhos):
    """A pasta mais funda por onde TODOS os caminhos em falta passam - o que ficou para tras.

    Um projeto copiado de outro computador costuma ter as dependencias todas debaixo de uma so pasta
    que nao veio; dize-la numa linha poupa a leitura das N.
    """
    partes = [os.path.normpath(c).split(os.sep) for c in (caminhos or [])]
    if not partes:
        return ""
    comum = []
    for i in range(min(len(p) for p in partes)):
        if len({p[i].lower() for p in partes}) != 1:
            break
        comum.append(partes[0][i])
    return os.sep.join(comum) if len(comum) > 1 else ""


def exe_produzido(pasta_build, desde=None, nome=""):
    """Executaveis deixados pelo build, sem as sondas do proprio CMake e com o do projeto a frente."""
    achados = []
    for raiz, pastas, ficheiros in os.walk(pasta_build):
        pastas[:] = [p for p in pastas if p not in _PASTAS_DE_SONDA]
        for ficheiro in ficheiros:
            if not ficheiro.lower().endswith(".exe"):
                continue
            caminho = os.path.join(raiz, ficheiro)
            try:
                mtime = os.path.getmtime(caminho)
                tamanho = os.path.getsize(caminho)
            except OSError:
                continue
            if desde and mtime < desde:
                continue
            achados.append({
                "caminho": caminho.replace("\\", "/"),
                "nome": ficheiro,
                "mb": round(tamanho / 1048576, 2),
                "mtime": mtime,
            })
    alvo = (nome or "").lower() + ".exe"
    achados.sort(key=lambda a: (a["nome"].lower() != alvo, -a["mtime"]))
    return achados


def fontes_compiladas(saida):
    """As fontes que este build recompilou, lidas da saida do compilador.

    O MSBuild imprime cada fonte numa linha indentada ('  item.cpp'); o Ninja e o Make escrevem
    '[12/72]' e sao contados por passos_do_build. Ler a saida e o unico caminho que nao adivinha:
    quem decide o que esta velho e o compilador, nao o Axio.
    """
    nomes = []
    vistas = set()
    for linha in (saida or "").splitlines():
        texto = linha.strip()
        if " " in texto or not texto.lower().endswith(_SUFIXOS_DE_FONTE):
            continue
        if texto not in vistas:
            vistas.add(texto)
            nomes.append(texto)
    return nomes


def passos_do_build(saida):
    """O par (feito, total) que o Ninja e o Make escrevem como '[12/72]'; (0, 0) sem eles."""
    feito = total = 0
    for linha in (saida or "").splitlines():
        casado = _PASSO_NO_LOG.match(linha.strip())
        if casado:
            feito = max(feito, int(casado.group(1)))
            total = max(total, int(casado.group(2)))
    return feito, total


def cabecalho_mais_recente(pasta, desde):
    """O cabecalho tocado depois de 'desde' (o mtime do executavel anterior), do mais novo.

    Um cabecalho mexido obriga o compilador a refazer tudo o que o inclui - e e isso que
    transforma um build de segundos num build de minutos.
    """
    melhor, quando = "", 0.0
    for raiz, pastas, ficheiros in os.walk(pasta or ""):
        pastas[:] = [p for p in pastas if p not in _PASTAS_DE_SONDA
                     and p not in _PASTAS_FORA_DO_CENSO and not p.startswith(".")]
        for ficheiro in ficheiros:
            if not ficheiro.lower().endswith(_SUFIXOS_DE_CABECALHO):
                continue
            caminho = os.path.join(raiz, ficheiro)
            try:
                mtime = os.path.getmtime(caminho)
            except OSError:
                continue
            if mtime > desde and mtime > quando:
                melhor, quando = os.path.relpath(caminho, pasta).replace("\\", "/"), mtime
    return melhor, quando


