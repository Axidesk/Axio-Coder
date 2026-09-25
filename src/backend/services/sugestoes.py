import ast
import json
import os
import re

from src.backend.builds import construir, presets
from src.backend.config import APP_ROOT
from src.backend.services.process_manager import comando_inicia_axio

LIMITE_SUGESTOES = 6
LIMITE_CANDIDATOS_PY = 12

_NOMES_PY_PRIORITARIOS = ("main.py", "app.py", "run.py", "server.py", "manage.py")
_SERVIDORES = ("app", "uvicorn", "socketio")
_SCRIPTS_NPM = (("start", "npm start"), ("dev", "npm run dev"), ("serve", "npm run serve"))
_URL_LOCAL = re.compile(
    r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(?::\d{2,5})?(?:/[^\s\"'<>\x1b]*)?(?![\w-]|\.\w)",
    re.IGNORECASE,
)
_MARCADORES_PROJETO = (
    (("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"), "docker compose up", "Docker Compose"),
    (("Makefile", "makefile"), "make", "Makefile"),
    (("Cargo.toml",), "cargo run", "Rust"),
    (("go.mod",), "go run .", "Go"),
)


def detectar_sugestoes(pasta):
    """Comandos de arranque plausiveis para uma pasta do explorador, por ordem de prioridade."""
    if not pasta or not os.path.isdir(pasta):
        return []
    try:
        ficheiros = sorted(n for n in os.listdir(pasta) if os.path.isfile(os.path.join(pasta, n)))
    except OSError:
        return []
    sugestoes = (_sugestoes_npm(pasta) + _sugestoes_python(pasta, ficheiros)
                 + _sugestoes_cmake(pasta, ficheiros) + _sugestoes_projeto(ficheiros))
    return _sem_repetidos(_sem_recusados(sugestoes, pasta))


def detectar_url_na_saida(texto):
    """URL local anunciada pela saida de um processo: a prova de que ele abriu um servidor."""
    if not texto or "://" not in texto:
        return ""
    achado = _URL_LOCAL.search(texto)
    if not achado:
        return ""
    url = achado.group(0).rstrip(".,;:)]}'\"")
    return re.sub(r"^http://0\.0\.0\.0", "http://localhost", url, count=1, flags=re.IGNORECASE)


def _sugestoes_npm(pasta):
    alvo = os.path.join(pasta, "package.json")
    if not os.path.isfile(alvo):
        return []
    try:
        with open(alvo, "r", encoding="utf-8", errors="replace") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return []
    scripts = dados.get("scripts") if isinstance(dados, dict) else None
    if not isinstance(scripts, dict):
        return []
    return [
        {"comando": comando, "origem": "package.json", "dica": "scripts." + chave}
        for chave, comando in _SCRIPTS_NPM
        if chave in scripts
    ]


def _sugestoes_python(pasta, ficheiros):
    py = [n for n in ficheiros if n.lower().endswith(".py")]
    prioritarios = [n for n in _NOMES_PY_PRIORITARIOS if n in py]
    restantes = [n for n in py if n not in prioritarios][:LIMITE_CANDIDATOS_PY]
    return [
        {"comando": "python " + nome, "origem": nome, "dica": "ponto de entrada"}
        for nome in prioritarios + restantes
        if _tem_ponto_de_entrada(os.path.join(pasta, nome))
    ]


def _tem_ponto_de_entrada(caminho):
    """Verdadeiro se o modulo tem a guarda `if __name__ == '__main__'` ou arranca um servidor no topo."""
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            arvore = ast.parse(f.read())
    except (OSError, SyntaxError, ValueError):
        return False
    for no in ast.walk(arvore):
        if isinstance(no, ast.If) and _e_guarda_de_main(no.test):
            return True
        if isinstance(no, ast.Call) and _e_arranque_de_servidor(no.func):
            return True
    return False


def _e_guarda_de_main(teste):
    return (
        isinstance(teste, ast.Compare)
        and isinstance(teste.left, ast.Name)
        and teste.left.id == "__name__"
        and len(teste.comparators) == 1
        and isinstance(teste.comparators[0], ast.Constant)
        and teste.comparators[0].value == "__main__"
    )


def _e_arranque_de_servidor(func):
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "run"
        and isinstance(func.value, ast.Name)
        and func.value.id in _SERVIDORES
    )


def _sugestoes_projeto(ficheiros):
    saida = [
        {"comando": comando, "origem": nomes[0], "dica": dica}
        for nomes, comando, dica in _MARCADORES_PROJETO
        if any(n in ficheiros for n in nomes)
    ]
    for nome in ficheiros:
        if nome.lower().endswith(".bat"):
            saida.append({"comando": nome, "origem": nome, "dica": "script"})
    return saida


def _sugestoes_cmake(pasta, ficheiros):
    """A cadeia configurar/compilar/executar de um projeto CMake ja preparado pelo Axio."""
    if "CMakeLists.txt" not in ficheiros:
        return []
    preset = _preset_do_axio(pasta)
    if not preset:
        return []
    sugestoes = [
        {"comando": f"cmake --preset {preset}", "origem": presets.ARQUIVO, "dica": "configurar"},
        {"comando": f"cmake --build --preset {preset}", "origem": presets.ARQUIVO, "dica": "compilar"},
    ]
    executavel = _executavel_do_build(pasta, preset)
    if executavel:
        sugestoes.append({"comando": f'"{executavel}"', "origem": "build", "dica": "executar"})
    return sugestoes


def _preset_do_axio(pasta):
    """O primeiro preset que o Axio escreveu neste projeto (nome com o prefixo do Axio)."""
    caminho = os.path.join(pasta, presets.ARQUIVO)
    if not os.path.isfile(caminho):
        return ""
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return ""
    for preset in dados.get("configurePresets") or []:
        nome = preset.get("name") if isinstance(preset, dict) else None
        if isinstance(nome, str) and nome.startswith(presets.PREFIXO_PRESET):
            return nome
    return ""


def _executavel_do_build(pasta, preset):
    achados = construir.exe_produzido(os.path.join(pasta, "build", preset),
                                      nome=os.path.basename(os.path.normpath(pasta)))
    return achados[0]["caminho"] if achados else ""


def _sem_repetidos(sugestoes):
    vistos = set()
    saida = []
    for sugestao in sugestoes:
        if sugestao["comando"] in vistos:
            continue
        vistos.add(sugestao["comando"])
        saida.append(sugestao)
        if len(saida) >= LIMITE_SUGESTOES:
            break
    return saida


def _sem_recusados(sugestoes, pasta):
    """Na raiz do Axio a rota recusa o que arrancaria o proprio Axio: sugerir isso e um card que nunca arranca."""
    if os.path.normcase(os.path.abspath(pasta)) != os.path.normcase(APP_ROOT):
        return sugestoes
    return [s for s in sugestoes if not comando_inicia_axio(s["comando"])]
