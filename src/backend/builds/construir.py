import os

from src.backend.builds import cmake_api, detetar, kits, msbuild, presets

TIMEOUT_CONFIGURAR = 420
TIMEOUT_CONSTRUIR = 3000

_PASTAS_DE_SONDA = ("CMakeFiles", "CMakeScratch", "_deps", ".git")


def preparar(pasta, configuracao="debug"):
    """Decide o que e preciso para construir: que projeto e, que kit o serve e que preset fica escrito.

    Nao executa nada - devolve os comandos ja formados. Quem os corre e quem tem o processo
    na mao, para o build ficar no painel do terminal e nao num canto invisivel.
    """
    deteccao = detetar.detetar(pasta)
    if deteccao.get("erro"):
        return {"erro": deteccao["erro"]}
    if deteccao["tipo"] == "msbuild":
        return _preparar_msbuild(deteccao, configuracao)
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


def _preparar_msbuild(deteccao, configuracao):
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
    plataforma = msbuild.plataforma_do_projeto(deteccao["pasta"]) or "x64"
    if alvo.lower().endswith(".sln") and plataforma.lower() == "win32":
        plataforma = "x86"
    nome = "Release" if configuracao == "release" else "Debug"
    escolha["gerador"] = ""
    escolha["arquitetura"] = plataforma
    escolha["cmake"] = None
    escolha.setdefault("notas", []).append(
        f"MSBuild: {escolha['msbuild']['caminho']} ({escolha['msbuild']['produto']})"
    )
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
    return (f"ATENCAO: {len(em_falta)} pasta(s) de dependencias que este projeto declara nao existem "
            f"nesta maquina - a compilacao para com 'cannot open include file'. A primeira e "
            f"'{em_falta[0]}'. Sao caminhos que ficaram no computador onde o projeto foi criado.")


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


