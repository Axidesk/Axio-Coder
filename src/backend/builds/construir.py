import os

from src.backend.builds import detetar, kits, presets

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
    if deteccao["tipo"] != "cmake":
        return {"deteccao": deteccao, "faltam": [_sem_caminho(deteccao)]}
    escolha = kits.escolher_kit(deteccao, kits.kits_instalados(deteccao.get("prefixos", ())))
    if escolha["faltam"]:
        return {"deteccao": deteccao, "escolha": escolha, "faltam": escolha["faltam"]}
    escrita = presets.escrever(deteccao["pasta"], escolha, configuracao)
    if escrita.get("erro"):
        return {"deteccao": deteccao, "escolha": escolha, "faltam": [escrita["erro"]]}
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


def _sem_caminho(deteccao):
    if deteccao["tipo"] == "desconhecido":
        return ("A pasta nao tem nenhum ficheiro de projeto conhecido (CMakeLists.txt, .sln, .pro, "
                "pyproject.toml...) - nao ha o que construir.")
    return (f"Projeto {deteccao['rotulo']} (identificado por {', '.join(deteccao['ficheiros'])}): "
            "nesta primeira versao o Axio configura e compila projetos CMake. Os outros ficam a seguir.")


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


