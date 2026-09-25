import json
import os

PREFIXO_PRESET = "axio-"
ARQUIVO = "CMakeUserPresets.json"

_VISAO = 6
_GERADORES_MULTI_CONFIG = ("Visual Studio", "Xcode", "Multi-Config")
_CONFIGURACOES = {"debug": "Debug", "release": "Release", "relwithdebinfo": "RelWithDebInfo", "minsizerel": "MinSizeRel"}


def nome_do_preset(configuracao):
    return PREFIXO_PRESET + configuracao


def escrever(pasta, escolha, configuracao="debug"):
    """Grava no CMakeUserPresets.json o configure+build que o Axio escolheu, sem tocar no do projeto.

    O CMakeUserPresets e o ficheiro LOCAL do CMake (nunca vai para o git) e inclui sozinho o
    CMakePresets.json do projeto - por isso acrescentar presets aqui nunca colide com quem os
    escreveu. Presets de outro dono no mesmo ficheiro ficam intactos.
    """
    if escolha.get("faltam") or not escolha.get("gerador"):
        return {"erro": "sem kit escolhido", "faltam": escolha.get("faltam", [])}
    nome = nome_do_preset(configuracao)
    dados, erro = _ler(pasta)
    if erro:
        return {"erro": erro}
    configuracao_cmake = _CONFIGURACOES.get(configuracao.lower(), "Debug")
    multi_config = any(g in escolha["gerador"] for g in _GERADORES_MULTI_CONFIG)
    configure = _configure(nome, escolha, configuracao_cmake, multi_config)
    build = _build(nome, configuracao_cmake, multi_config)
    dados["configurePresets"] = _sem_nome(dados.get("configurePresets"), nome) + [configure]
    dados["buildPresets"] = _sem_nome(dados.get("buildPresets"), nome) + [build]
    pasta_build = os.path.join(pasta, "build", nome)
    try:
        os.makedirs(pasta_build, exist_ok=True)
        with open(os.path.join(pasta_build, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("*\n")
        with open(os.path.join(pasta, ARQUIVO), "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except OSError as e:
        return {"erro": f"nao consegui gravar o {ARQUIVO}: {e}"}
    return {
        "arquivo": os.path.join(pasta, ARQUIVO).replace("\\", "/"),
        "preset": nome,
        "pasta_build": pasta_build.replace("\\", "/"),
        "configurePreset": nome,
        "buildPreset": nome,
    }


def ler_presets(pasta):
    """Nomes dos presets de configure que existem hoje no projeto (do Axio e de outros)."""
    dados, _ = _ler(pasta)
    return [p.get("name") for p in dados.get("configurePresets") or [] if p.get("name")]


def _configure(nome, escolha, configuracao, multi_config):
    preset = {
        "name": nome,
        "displayName": f"Axio - {configuracao}",
        "description": _descricao(escolha),
        "generator": escolha["gerador"],
        "binaryDir": "${sourceDir}/build/" + nome,
    }
    if escolha.get("arquitetura"):
        preset["architecture"] = {"value": escolha["arquitetura"], "strategy": "set"}
    variaveis = dict(escolha.get("variaveis") or {})
    if not multi_config:
        variaveis["CMAKE_BUILD_TYPE"] = configuracao
    if variaveis:
        preset["cacheVariables"] = variaveis
    return preset


def _build(nome, configuracao, multi_config):
    preset = {"name": nome, "configurePreset": nome}
    if multi_config:
        preset["configuration"] = configuracao
    return preset


def _descricao(escolha):
    partes = []
    if escolha.get("qt"):
        partes.append(f"Qt {escolha['qt']['versao']} {escolha['qt']['kit']}")
    if escolha.get("cmake"):
        partes.append(f"CMake {escolha['cmake'].get('versao') or 'instalado'}")
    if escolha.get("glslc"):
        partes.append("glslc")
    return "Escolhido pelo Axio: " + ", ".join(partes) if partes else "Escolhido pelo Axio"


def _sem_nome(lista, nome):
    return [p for p in (lista or []) if isinstance(p, dict) and p.get("name") != nome]


def _ler(pasta):
    caminho = os.path.join(pasta, ARQUIVO)
    if not os.path.isfile(caminho):
        return {"version": _VISAO}, ""
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError) as e:
        return {}, f"o {ARQUIVO} que ja existe nao e JSON valido ({e}) - nao lhe toquei."
    if not isinstance(dados, dict):
        return {}, f"o {ARQUIVO} que ja existe nao tem um objeto na raiz - nao lhe toquei."
    dados.setdefault("version", _VISAO)
    return dados, ""
