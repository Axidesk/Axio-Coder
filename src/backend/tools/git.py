"""Retrato do repositorio git numa so chamada: onde esta, como esta e o que falta commitar."""

import os
import tempfile

from src.backend.config import APP_ROOT
from src.backend.services.file_service import git_saida, raiz_repositorio
from src.backend.state import estado
from src.backend.tools.registry import register

_TAGS_POR_OMISSAO = 6
_MAX_ITENS_LISTADOS = 40
_SEGREDOS = (
    ".env",
    ".axio/",
    "data/settings.json",
    "data/cofre.json",
    "data/vertex_credentials.json",
    "entities.json",
    "mempalace.yaml",
)


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


def _e_segredo(nome):
    limpo = nome.replace("\\", "/")
    if limpo.startswith("./"):
        limpo = limpo[2:]
    for segredo in _SEGREDOS:
        if segredo.endswith("/"):
            if limpo.startswith(segredo):
                return True
        elif limpo == segredo or limpo.startswith(segredo + "."):
            return True
    return False


def _nomes_do_status(raiz):
    texto, erro = git_saida(raiz, "status", "--short")
    if erro:
        return [], erro
    nomes = []
    for linha in (texto or "").splitlines():
        if len(linha) > 3:
            nomes.append(linha[3:].strip().strip('"'))
    return nomes, ""


def _lista_de_ficheiros(raiz, ficheiros):
    texto = (ficheiros or "").strip()
    if not texto:
        return []
    if "," in texto:
        return [p.strip() for p in texto.split(",") if p.strip()]
    pedacos = texto.split()
    if len(pedacos) > 1 and os.path.exists(os.path.join(raiz, texto)):
        return [texto]
    return pedacos


def _ficheiro_da_mensagem(mensagem):
    caminho = os.path.join(tempfile.gettempdir(), f"axio_git_msg_{os.getpid()}.txt")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(mensagem)
    return caminho


def _ficheiros_em_stage(raiz):
    saida, _ = git_saida(raiz, "diff", "--cached", "--name-only")
    return [n.strip().strip('"') for n in (saida or "").splitlines() if n.strip()]


def _recusa_de_publicacao(segredos):
    return ("RECUSADO: entre o que iria para o commit aparece " + ", ".join(segredos) +
            ". Nada foi commitado - tira esses caminhos do pedido ou poe-os no .gitignore.")


def _linhas_da_publicacao(raiz, mensagem, ficheiros, tag, empurrar):
    if not (mensagem or "").strip():
        return ["ERRO: sem mensagem nao ha commit - escreve o que mudou."]
    nomes, erro = _nomes_do_status(raiz)
    if erro:
        return [f"ERRO: git recusou o estado do repositorio: {erro}"]
    if not nomes:
        return ["NADA A PUBLICAR: o repositorio esta limpo."]
    segredos = [n for n in nomes if _e_segredo(n)]
    if segredos:
        return [_recusa_de_publicacao(segredos) + " Nada foi posto em stage."]

    antes = _ficheiros_em_stage(raiz)
    linhas = []
    lista = _lista_de_ficheiros(raiz, ficheiros)
    if lista:
        _, erro = git_saida(raiz, "add", "--", *lista)
        linhas.append("git add " + " ".join(lista) + ": " + (f"ERRO: {erro}" if erro else "ok"))
    else:
        _, erro = git_saida(raiz, "add", "-A")
        linhas.append("git add -A: " + (f"ERRO: {erro}" if erro else "ok"))
    if erro:
        return linhas

    entrada, _ = git_saida(raiz, "diff", "--cached", "--name-status")
    itens = [l for l in (entrada or "").splitlines() if l.strip()]
    if not itens:
        return linhas + ["NADA EM STAGE depois do add: nao ha o que commitar."]
    segredos = [n for n in _ficheiros_em_stage(raiz) if _e_segredo(n)]
    if segredos:
        nota = " O stage ficou como estava antes."
        if git_saida(raiz, "reset")[1]:
            git_saida(raiz, "rm", "--cached", "--quiet", "--", *segredos)
            nota = " Tirei esses caminhos do stage; o resto ficou la."
        elif antes:
            git_saida(raiz, "add", "--", *antes)
        return linhas + [_recusa_de_publicacao(segredos) + nota]
    linhas += _linhas_do_estado("ENTRA NO COMMIT", itens)

    caminho_msg = _ficheiro_da_mensagem(mensagem)
    try:
        saida, erro = git_saida(raiz, "commit", "-F", caminho_msg)
        if erro:
            return linhas + [f"ERRO no commit: {erro}"]
        linhas.append("COMMIT: " + " ".join((saida or "").split()))

        etiqueta = (tag or "").strip()
        if etiqueta:
            _, erro = git_saida(raiz, "tag", "-a", etiqueta, "-F", caminho_msg)
            linhas.append(f"ETIQUETA {etiqueta}: " + (f"ERRO: {erro}" if erro else "criada"))
    finally:
        try:
            os.remove(caminho_msg)
        except OSError:
            pass

    if not empurrar:
        linhas.append("SEM PUSH (empurrar=false): o commit ficou so no disco local.")
        return linhas

    ramo, _ = git_saida(raiz, "rev-parse", "--abbrev-ref", "HEAD")
    ramo = (ramo or "").strip() or "main"
    _, erro = git_saida(raiz, "push", "origin", ramo)
    linhas.append(f"PUSH {ramo}: " + (f"ERRO: {erro}" if erro else "aceite pelo remoto"))
    etiqueta = (tag or "").strip()
    if etiqueta:
        _, erro = git_saida(raiz, "push", "origin", etiqueta)
        linhas.append(f"PUSH da etiqueta {etiqueta}: " + (f"ERRO: {erro}" if erro else "aceite pelo remoto"))
    sincronia, _ = git_saida(raiz, "status", "--short", "--branch")
    cabecalho = (sincronia or "").splitlines()
    if cabecalho:
        linhas.append("ESTADO FINAL: " + cabecalho[0].lstrip("#").strip())
    return linhas


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


@register(
    "tool_publicar_git",
    "Publica no repositorio o que esta no disco: poe em stage (tudo o que mudou, ou so os caminhos "
    "indicados), grava o commit, cria a etiqueta anotada quando pedida e empurra para o remoto, "
    "terminando com a sincronia entre o ramo local e o remoto. Leva a mensagem por ficheiro, por isso "
    "acentos e varias linhas passam intactos. RECUSA-SE a publicar quando entre os ficheiros aparece "
    "algum de credencial ou de estado local (.env, data/settings.json, data/cofre.json, "
    "data/vertex_credentials.json, entities.json, mempalace.yaml, .axio/) - e nesse caso nao toca em "
    "nada, nem no stage. ESCREVE no repositorio: ve o que vai entrar com 'tool_estado_git' antes.",
    {
        'mensagem': {"tipo": "STRING", "desc": "Mensagem do commit (a mesma serve de mensagem a etiqueta)"},
        'ficheiros': {"tipo": "STRING", "desc": "Caminhos a publicar, separados por espaco - ou por virgula quando o caminho tiver espacos (padrao: tudo o que mudou)", "padrao": ""},
        'tag': {"tipo": "STRING", "desc": "Etiqueta anotada a criar neste commit (padrao: nenhuma)", "padrao": ""},
        'empurrar': {"tipo": "BOOLEAN", "desc": "Empurrar o commit (e a etiqueta) para o remoto", "padrao": True},
        'caminho': {"tipo": "STRING", "desc": "Pasta dentro do repositorio (padrao: a pasta do projeto aberto)", "padrao": ""},
    },
)
def tool_publicar_git(mensagem, ficheiros="", tag="", empurrar=True, caminho=""):
    base = caminho or estado.get("pasta_raiz") or APP_ROOT
    raiz = raiz_repositorio(base)
    if not raiz:
        return (f"ERRO: '{base}' nao esta dentro de um repositorio git "
                "(nenhuma pasta .git a subir a partir dai).")
    return "\n".join(_linhas_da_publicacao(raiz, mensagem, ficheiros, tag, empurrar))
