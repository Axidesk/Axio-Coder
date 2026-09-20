"""Operacoes do git para o painel: estado, historico, commit por tarefa e restauro."""

import os
import re

from src.backend.services.file_service import git_saida, raiz_repositorio

_MANIFESTOS = ("requirements.txt", "package.json")
_LIMITE_HISTORICO = 20
_LIMITE_FICHEIROS = 80
_SEPARADOR = "\x1f"


def curto(hash_completo):
    return (hash_completo or "").strip()[:7]


def pasta_do_repositorio(pasta):
    if not pasta:
        return "", "Nenhuma pasta selecionada"
    raiz = raiz_repositorio(pasta)
    if not raiz:
        return "", "A pasta do projeto nao e um repositorio git"
    return raiz, ""


def _ler_texto(caminho):
    if not caminho or not os.path.exists(caminho):
        return None
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def _sujos(raiz):
    texto, erro = git_saida(raiz, "status", "--porcelain")
    if erro:
        return [], [], [], erro
    em_stage, fora, novos = [], [], []
    for linha in (texto or "").splitlines():
        codigo, nome = linha[:2], linha[3:].strip()
        if not nome:
            continue
        if codigo == "??":
            fora.append(nome)
            novos.append(nome)
            continue
        if codigo[0] not in " ?":
            em_stage.append(nome)
        if codigo[1] not in " ?":
            fora.append(nome)
    return em_stage, fora, novos, ""


def _ramo_atual(raiz):
    """Nome do ramo. O `rev-parse` falha num repositorio ainda sem commits, onde o symbolic-ref responde."""
    saida, erro = git_saida(raiz, "rev-parse", "--abbrev-ref", "HEAD")
    nome = (saida or "").strip()
    if not erro and nome and nome != "HEAD":
        return nome
    saida, erro = git_saida(raiz, "symbolic-ref", "--short", "HEAD")
    return (saida or "").strip() or "sem ramo"


def _frente(raiz):
    saida, erro = git_saida(raiz, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
    if erro:
        return None, None
    partes = (saida or "").split()
    if len(partes) != 2:
        return None, None
    try:
        return int(partes[0]), int(partes[1])
    except ValueError:
        return None, None


def _ultimo_commit(raiz):
    saida, erro = git_saida(
        raiz, "log", "-1", "--pretty=format:%H" + _SEPARADOR + "%s" + _SEPARADOR + "%cI"
    )
    if erro or not (saida or "").strip():
        return None
    partes = saida.split(_SEPARADOR)
    if len(partes) < 3:
        return None
    return {"hash": partes[0], "curto": curto(partes[0]), "mensagem": partes[1], "data": partes[2]}


def manifestos_diferentes(raiz, revisao):
    """Manifestos de dependencias que diferem entre o disco e a revisao indicada."""
    diferentes = []
    for rel in _MANIFESTOS:
        no_disco = _ler_texto(os.path.join(raiz, rel.replace("/", os.sep)))
        no_commit, erro = git_saida(raiz, "show", f"{revisao}:{rel}")
        if erro:
            no_commit = None
        if no_disco is None and no_commit is None:
            continue
        if (no_disco or "") != (no_commit or ""):
            diferentes.append(rel)
    return diferentes


def estado(pasta):
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return {"repo": False, "motivo": erro}
    em_stage, fora, novos, erro_status = _sujos(raiz)
    ahead, behind = _frente(raiz)
    remoto, _ = git_saida(raiz, "remote", "get-url", "origin")
    return {
        "repo": True,
        "raiz": raiz,
        "branch": _ramo_atual(raiz),
        "remoto": (remoto or "").strip(),
        "ahead": ahead,
        "behind": behind,
        "ultimo": _ultimo_commit(raiz),
        "em_stage": em_stage[:_LIMITE_FICHEIROS],
        "fora": fora[:_LIMITE_FICHEIROS],
        "novos": novos[:_LIMITE_FICHEIROS],
        "total_sujos": len({*em_stage, *fora}),
        "erro": erro_status,
    }


def historico(pasta, limite=_LIMITE_HISTORICO):
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return {"repo": False, "motivo": erro, "commits": [], "tags": []}
    formato = _SEPARADOR.join(["%H", "%h", "%s", "%cI", "%an", "%D"])
    saida, erro_log = git_saida(raiz, "log", f"--max-count={int(limite)}", "--decorate=short", f"--pretty=format:{formato}")
    commits = []
    for linha in (saida or "").splitlines():
        partes = linha.split(_SEPARADOR)
        if len(partes) < 6:
            continue
        marcas = [m.strip() for m in partes[5].split(",")]
        commits.append({
            "hash": partes[0],
            "curto": partes[1],
            "mensagem": partes[2],
            "data": partes[3],
            "autor": partes[4],
            "tags": [m[5:] for m in marcas if m.startswith("tag: ")],
            "head": "HEAD" in marcas,
        })
    tags_texto, _ = git_saida(raiz, "tag", "--list", "--sort=-creatordate")
    tags = [t.strip() for t in (tags_texto or "").splitlines() if t.strip()]
    return {"repo": True, "raiz": raiz, "commits": commits, "tags": tags, "erro": erro_log}


def _validar_caminhos(ficheiros):
    validos = []
    for rel in ficheiros or []:
        limpo = str(rel or "").replace("\\", "/").strip()
        if not limpo or limpo.startswith("/") or ".." in limpo.split("/"):
            continue
        if limpo not in validos:
            validos.append(limpo)
    return validos


def _caminhos_conhecidos(raiz, caminhos):
    """So o que o git consegue registar: o que ja esta rastreado ou existe no disco."""
    rastreados, _ = git_saida(raiz, "ls-files", "--", *caminhos)
    conhecidos = {l.strip() for l in (rastreados or "").splitlines() if l.strip()}
    escolhidos = []
    for rel in caminhos:
        if rel in conhecidos or os.path.exists(os.path.join(raiz, rel.replace("/", os.sep))):
            escolhidos.append(rel)
    return escolhidos


def commitar(pasta, mensagem, ficheiros=None):
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return {"status": "error", "message": erro}
    caminhos = []
    if ficheiros is not None:
        caminhos = _validar_caminhos(ficheiros)
        if not caminhos:
            return {"status": "error", "message": "Nenhum ficheiro para commitar nesta tarefa"}
        caminhos = _caminhos_conhecidos(raiz, caminhos)
        if not caminhos:
            return {"status": "error", "message": "Nenhum destes ficheiros pertence ao repositorio"}
    if caminhos:
        _, erro_add = git_saida(raiz, "add", "--", *caminhos)
    else:
        _, erro_add = git_saida(raiz, "add", "-A")
    if erro_add:
        return {"status": "error", "message": erro_add}
    prontos, _ = git_saida(raiz, "diff", "--cached", "--name-only")
    entrando = [l.strip() for l in (prontos or "").splitlines() if l.strip()]
    if not entrando:
        return {"status": "vazio", "message": "Nada por commitar nesta tarefa."}
    texto = (mensagem or "").strip() or "Tarefa sem titulo"
    _, erro_commit = git_saida(raiz, "commit", "-m", texto)
    if erro_commit:
        return {"status": "error", "message": erro_commit}
    hash_completo, erro_hash = git_saida(raiz, "rev-parse", "HEAD")
    if erro_hash:
        return {"status": "error", "message": erro_hash}
    hash_completo = (hash_completo or "").strip()
    return {
        "status": "ok",
        "hash": hash_completo,
        "curto": curto(hash_completo),
        "count": len(entrando),
        "ficheiros": entrando[:_LIMITE_FICHEIROS],
    }


def _nome_do_status(linha):
    partes = re.split(r"\t+", linha.strip())
    if len(partes) < 2:
        return "", ""
    return partes[0].strip(), partes[-1].strip()


def alteracoes_para_disco(pasta, revisao):
    """O que muda entre a revisao indicada e o disco, sem tocar em nada."""
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return {"repo": False, "motivo": erro, "restaurar": [], "remover": []}
    saida, erro_diff = git_saida(raiz, "diff", "--name-status", revisao, "--")
    if erro_diff:
        return {"repo": True, "erro": erro_diff, "restaurar": [], "remover": []}
    restaurar, remover = [], []
    for linha in (saida or "").splitlines():
        codigo, nome = _nome_do_status(linha)
        if not nome:
            continue
        if codigo.startswith("D"):
            restaurar.append({"caminho": nome, "acao": "recriado"})
        elif codigo.startswith("A"):
            remover.append(nome)
        else:
            restaurar.append({"caminho": nome, "acao": "restaurado"})
    _, _, novos, _ = _sujos(raiz)
    for rel in novos:
        if rel not in remover:
            remover.append(rel)
    return {"repo": True, "raiz": raiz, "restaurar": restaurar, "remover": remover}


def conteudo_na_revisao(pasta, revisao, caminhos):
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return {}, erro
    conteudos = {}
    for rel in _validar_caminhos(caminhos):
        texto, erro_show = git_saida(raiz, "show", f"{revisao}:{rel}")
        conteudos[rel] = None if erro_show else texto
    return conteudos, ""


def restaurar(pasta, revisao, caminhos):
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return {"status": "error", "message": erro}
    validos = _validar_caminhos(caminhos)
    if not validos:
        return {"status": "error", "message": "Nenhum ficheiro valido para restaurar"}
    _, erro_restore = git_saida(raiz, "restore", "--source", revisao, "--worktree", "--", *validos)
    if erro_restore:
        return {"status": "error", "message": erro_restore}
    return {"status": "ok", "count": len(validos), "ficheiros": validos}


def revisao_existe(pasta, revisao):
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return False
    _, erro_ver = git_saida(raiz, "rev-parse", "--verify", f"{revisao}^{{commit}}")
    return not erro_ver
