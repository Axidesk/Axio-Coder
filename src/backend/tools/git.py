"""Retrato do repositorio git numa so chamada: onde esta, como esta e o que falta commitar."""

from src.backend.config import APP_ROOT
from src.backend.services.file_service import git_saida, raiz_repositorio
from src.backend.state import estado
from src.backend.tools.registry import register

_TAGS_POR_OMISSAO = 6
_MAX_ITENS_LISTADOS = 40


def _curto(pasta, revisao):
    saida, erro = git_saida(pasta, "rev-parse", "--short", f"{revisao}^{{commit}}")
    if erro:
        saida, _ = git_saida(pasta, "rev-parse", "--short", revisao)
    return (saida or "").strip() or "?"


def _commits_por_cima(pasta, revisao):
    saida, erro = git_saida(pasta, "rev-list", "--count", f"{revisao}..HEAD")
    return (saida or "").strip() if not erro else "?"


def _linhas_das_tags(pasta, quantas):
    saida, erro = git_saida(pasta, "tag", "--list", "--sort=-creatordate")
    if erro:
        return [f"TAGS: nao foi possivel listar ({erro})"]
    nomes = [n.strip() for n in (saida or "").splitlines() if n.strip()]
    if not nomes:
        return ["TAGS: nenhuma"]
    try:
        limite = max(1, int(quantas))
    except (TypeError, ValueError):
        limite = _TAGS_POR_OMISSAO
    itens = []
    for nome in nomes[:limite]:
        atras = _commits_por_cima(pasta, nome)
        marca = "no HEAD" if atras == "0" else f"{atras} commit(s) por cima"
        itens.append(f"{nome} -> {_curto(pasta, nome)} ({marca})")
    return [f"TAGS mostradas {len(itens)} de {len(nomes)}, da mais recente: " + " | ".join(itens)]


def _separar_estado(linhas):
    em_stage, fora = [], []
    for linha in linhas:
        codigo, nome = linha[:2], linha[3:].strip()
        if codigo == "??":
            fora.append(f"?? {nome}")
            continue
        if codigo[0] not in " ?":
            em_stage.append(f"{codigo[0]} {nome}")
        if codigo[1] not in " ?":
            fora.append(f"{codigo[1]} {nome}")
    return em_stage, fora


def _linhas_do_estado(rotulo, itens):
    if not itens:
        return [f"{rotulo}: nada"]
    mostrados = " | ".join(itens[:_MAX_ITENS_LISTADOS])
    if len(itens) <= _MAX_ITENS_LISTADOS:
        return [f"{rotulo} ({len(itens)}): {mostrados}"]
    restantes = len(itens) - _MAX_ITENS_LISTADOS
    return [f"{rotulo} ({len(itens)}): {mostrados} | ... e mais {restantes} ficheiro(s)"]


def _veredito_do_estado(em_stage, fora):
    if em_stage and fora:
        return f"{len(em_stage)} em stage e {len(fora)} fora dele - nada sera commitado sem 'git add'"
    if em_stage:
        return f"{len(em_stage)} ficheiro(s) em stage - pronto a commitar"
    if fora:
        return f"{len(fora)} alteracao(oes) fora do stage - falta 'git add'"
    return "nada por commitar"


def _linhas_do_repositorio(raiz, tags):
    texto, erro = git_saida(raiz, "status", "--short", "--branch")
    if erro:
        return [f"ERRO: git recusou o pedido em '{raiz}': {erro}"]
    linhas = [l for l in (texto or "").splitlines() if l.strip()]
    cabecalho = (linhas[0] if linhas else "").lstrip("#").strip()
    em_stage, fora = _separar_estado(linhas[1:])
    ultimo, _ = git_saida(raiz, "log", "-1", "--format=%h %ad %s", "--date=short")
    partes = [
        f"REPOSITORIO: {raiz}",
        f"BRANCH: {cabecalho}",
        f"ULTIMO COMMIT: {(ultimo or '').strip()}",
    ]
    partes += _linhas_das_tags(raiz, tags)
    partes += _linhas_do_estado("EM STAGE", em_stage)
    partes += _linhas_do_estado("FORA DO STAGE", fora)
    partes.append(f"VEREDITO: {_veredito_do_estado(em_stage, fora)}")
    return partes


@register(
    "tool_estado_git",
    "Retrato do repositorio git numa so chamada: raiz, branch e relacao com o remoto, ultimo commit, "
    "as tags com o commit que apontam e quantos commits ficaram por cima, o que esta em stage e o que "
    "mudou fora dele. Use ANTES de commitar (ver o que entra) e ao escolher o nome de uma tag: o "
    "'git tag --list' local nao diz se o nome ja foi publicado, para isso use 'git ls-remote --tags "
    "origin' pelo tool_executar_processo. Nao escreve nada no repositorio: so le."
    ,
    {
        'caminho': {"tipo": "STRING", "desc": "Pasta dentro do repositorio (padrao: a pasta do projeto aberto)", "padrao": ""},
        'tags': {"tipo": "INTEGER", "desc": "Quantas tags mostrar, das mais recentes", "padrao": _TAGS_POR_OMISSAO},
    },
)
def tool_estado_git(caminho="", tags=_TAGS_POR_OMISSAO):
    base = caminho or estado.get("pasta_raiz") or APP_ROOT
    raiz = raiz_repositorio(base)
    if not raiz:
        return (f"ERRO: '{base}' nao esta dentro de um repositorio git "
                "(nenhuma pasta .git a subir a partir dai).")
    return "\n".join(_linhas_do_repositorio(raiz, tags))
