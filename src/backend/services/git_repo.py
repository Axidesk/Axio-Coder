"""Operacoes do git para o painel: estado, historico, commit por tarefa e restauro."""

import os
import re

from src.backend.services.file_service import git_saida, raiz_repositorio

_MANIFESTOS = ("requirements.txt", "package.json")
_LIMITE_HISTORICO = 200
_LIMITE_FICHEIROS = 80
_LIMITE_TAGS = 24
_LIMITE_POR_SUBIR = 200
_LIMITE_INTERVALO = 200
_LIMITE_HISTORIA = 500
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


def _sujos(raiz):
    retrato, erro = _retrato(raiz)
    if erro:
        return [], [], [], erro
    return retrato["em_stage"], retrato["fora"], retrato["novos"], ""


def _retrato(raiz):
    """Ramo, frente e ficheiros sujos numa so ida ao git: o `--branch` acrescenta a linha do ramo ao status."""
    texto, erro = git_saida(raiz, "status", "--porcelain", "--branch")
    if erro:
        return None, erro
    ramo, ahead, behind = "", None, None
    em_stage, fora, novos = [], [], []
    for linha in (texto or "").splitlines():
        if linha.startswith("## "):
            ramo, ahead, behind = _ramo_e_frente(linha)
            continue
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
    return {"ramo": ramo or "sem ramo", "ahead": ahead, "behind": behind,
            "em_stage": em_stage, "fora": fora, "novos": novos}, ""


def _ramo_atual(raiz):
    """Nome do ramo. O `rev-parse` falha num repositorio ainda sem commits, onde o symbolic-ref responde."""
    saida, erro = git_saida(raiz, "rev-parse", "--abbrev-ref", "HEAD")
    nome = (saida or "").strip()
    if not erro and nome and nome != "HEAD":
        return nome
    saida, erro = git_saida(raiz, "symbolic-ref", "--short", "HEAD")
    return (saida or "").strip() or "sem ramo"


def _ramo_e_frente(linha):
    """Separa a linha `## ramo...acima [ahead N, behind N]` que o `--branch` poe a frente do status."""
    resto = linha[3:].strip()
    if resto.startswith("No commits yet on "):
        return resto[len("No commits yet on "):].strip() or "sem ramo", None, None
    if resto.startswith("HEAD (no branch)"):
        return "sem ramo", None, None
    nome = resto
    marcas = ""
    if " [" in resto:
        nome, marcas = resto.split(" [", 1)
    ramo = nome.split("...")[0].strip() or "sem ramo"
    ahead = behind = None
    for parte in marcas.rstrip("]").split(","):
        parte = parte.strip()
        if parte.startswith("ahead ") and parte[6:].isdigit():
            ahead = int(parte[6:])
        elif parte.startswith("behind ") and parte[7:].isdigit():
            behind = int(parte[7:])
    if (ahead is None) != (behind is None):
        ahead = ahead or 0
        behind = behind or 0
    return ramo, ahead, behind


def _slug_do_remoto(url):
    """`Axidesk/Axio-Coder` a partir de https://github.com/Axidesk/Axio-Coder.git ou git@github.com:Axidesk/Axio-Coder.git."""
    texto = (url or "").strip()
    if not texto:
        return ""
    if "://" in texto:
        texto = texto.split("://", 1)[1]
        if "/" in texto:
            texto = texto.split("/", 1)[1]
    elif "@" in texto and ":" in texto:
        texto = texto.split(":", 1)[1]
    if texto.endswith(".git"):
        texto = texto[:-4]
    return texto.strip("/")


def _nomes_dos_ramos(raiz):
    saida, erro = git_saida(raiz, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    if erro:
        return []
    return [l.strip() for l in (saida or "").splitlines() if l.strip()]


def _ultimo_commit(raiz, caminhos=None):
    """Commit mais recente do ramo, ou o mais recente que tocou nestes caminhos."""
    formato = "--pretty=format:%H" + _SEPARADOR + "%s" + _SEPARADOR + "%cI"
    so_estes = ["--", *caminhos] if caminhos else []
    saida, erro = git_saida(raiz, "log", "-1", formato, *so_estes)
    if erro or not (saida or "").strip():
        return None
    partes = saida.split(_SEPARADOR)
    if len(partes) < 3:
        return None
    return {"hash": partes[0], "curto": curto(partes[0]), "mensagem": partes[1], "data": partes[2]}


def estado(pasta):
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return {"repo": False, "motivo": erro}
    retrato, erro_status = _retrato(raiz)
    if erro_status:
        retrato = {"ramo": _ramo_atual(raiz), "ahead": None, "behind": None,
                   "em_stage": [], "fora": [], "novos": []}
    sujos = {*retrato["em_stage"], *retrato["fora"]}
    remoto, _ = git_saida(raiz, "remote", "get-url", "origin")
    remoto = (remoto or "").strip()
    return {
        "repo": True,
        "raiz": raiz,
        "branch": retrato["ramo"],
        "ramos": _nomes_dos_ramos(raiz),
        "remoto": remoto,
        "slug": _slug_do_remoto(remoto),
        "ahead": retrato["ahead"],
        "behind": retrato["behind"],
        "ultimo": _ultimo_commit(raiz),
        "em_stage": retrato["em_stage"][:_LIMITE_FICHEIROS],
        "fora": retrato["fora"][:_LIMITE_FICHEIROS],
        "novos": retrato["novos"][:_LIMITE_FICHEIROS],
        "total_sujos": len(sujos),
        "manifestos": [m for m in _MANIFESTOS if m in sujos],
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
    return {"repo": True, "raiz": raiz, "commits": commits, "erro": erro_log}


def _tags_com_ponto(raiz):
    """Cada etiqueta com o commit exato a que aponta. Numa etiqueta anotada o alvo esta em *objectname."""
    formato = _SEPARADOR.join([
        "%(refname:short)", "%(objecttype)", "%(objectname)", "%(*objectname)",
        "%(creatordate:iso-strict)", "%(subject)", "%(*subject)",
    ])
    saida, erro = git_saida(raiz, "for-each-ref", "--sort=-creatordate", f"--format={formato}", "refs/tags")
    if erro:
        return [], erro
    tags = []
    for linha in (saida or "").splitlines():
        if not linha.strip():
            continue
        campos = linha.split(_SEPARADOR)
        if len(campos) < 7:
            continue
        anotada = campos[1] == "tag"
        ponto = campos[3] if anotada else campos[2]
        mensagem = campos[6] if anotada else campos[5]
        tags.append({
            "nome": campos[0],
            "ponto": ponto,
            "curto": curto(ponto),
            "data": campos[4],
            "mensagem": (mensagem or "").strip(),
        })
    return tags[:_LIMITE_TAGS], ""


def tags_com_ponto(pasta):
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return []
    return _tags_com_ponto(raiz)[0]


def _tags_relacionadas(raiz, revisao, relacao):
    """Etiquetas que contem a revisao (`--contains`) ou que ja vivem na historia dela (`--merged`)."""
    saida, erro = git_saida(raiz, "tag", relacao, revisao)
    if erro:
        return [], erro
    return [l.strip() for l in (saida or "").splitlines() if l.strip()], ""


def versao_da_revisao(pasta, revisao):
    """A etiqueta vigente nesta revisao: a que o `git describe` elege, ou seja a ultima versionada que ja a leva dentro."""
    if not revisao:
        return ""
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return ""
    saida, erro_tag = git_saida(raiz, "describe", "--tags", "--abbrev=0", revisao)
    if erro_tag:
        return ""
    return (saida or "").strip()


def _commits_do_intervalo(raiz, ponta, base):
    argumentos = ["rev-list", f"--max-count={_LIMITE_INTERVALO}", ponta]
    if base:
        argumentos.extend(["--not", base])
    saida, erro = git_saida(raiz, *argumentos)
    if erro:
        return [], erro
    return [l.strip() for l in (saida or "").splitlines() if l.strip()], ""


def _preencher_intervalos(raiz, tags):
    """Commits de cada intervalo e quantos vieram depois, de UMA leitura do log (sem uma chamada por etiqueta)."""
    formato = "%H" + _SEPARADOR + "%D"
    saida, erro = git_saida(raiz, "log", f"--max-count={_LIMITE_HISTORIA}", f"--pretty=format:{formato}")
    hashes = []
    if not erro:
        hashes = [l.split(_SEPARADOR)[0].strip() for l in (saida or "").splitlines() if l.strip()]
    indice = {h: i for i, h in enumerate(hashes)}
    cortado = len(hashes) >= _LIMITE_HISTORIA
    conhecidas = []
    for tag in tags:
        tag["commits"] = []
        tag["truncado"] = False
        tag["fora"] = False
        tag["depois"] = 0
        posicao = indice.get(tag["ponto"])
        if posicao is None:
            tag["fora"] = True
            continue
        tag["depois"] = posicao
        conhecidas.append((posicao, tag))
    conhecidas.sort(key=lambda par: par[0])
    for ordem, (posicao, tag) in enumerate(conhecidas):
        ultima = ordem + 1 >= len(conhecidas)
        fim = len(hashes) if ultima else conhecidas[ordem + 1][0]
        tag["commits"] = hashes[posicao:fim]
        tag["truncado"] = bool(ultima and cortado)


def _ramo_principal(raiz):
    for nome in ("main", "master"):
        if not git_saida(raiz, "rev-parse", "--verify", f"refs/heads/{nome}")[1]:
            return nome
    return ""


def _base_do_ramo(raiz, nome, upstream, principal):
    if upstream:
        return upstream
    remoto = f"origin/{nome}"
    if not git_saida(raiz, "rev-parse", "--verify", f"refs/remotes/{remoto}")[1]:
        return remoto
    return principal if nome != principal else ""


def _ramos_com_ponto(raiz):
    principal = _ramo_principal(raiz)
    formato = _SEPARADOR.join([
        "%(refname:short)", "%(objectname)", "%(HEAD)", "%(upstream:short)",
        "%(committerdate:iso-strict)", "%(subject)",
    ])
    saida, erro = git_saida(raiz, "for-each-ref", "--sort=-committerdate", f"--format={formato}", "refs/heads")
    if erro:
        return [], erro
    ramos = []
    for linha in (saida or "").splitlines():
        campos = linha.split(_SEPARADOR)
        if len(campos) < 6:
            continue
        nome = campos[0]
        base = _base_do_ramo(raiz, nome, campos[3].strip(), principal)
        commits, _ = _commits_do_intervalo(raiz, nome, base) if base else ([], "")
        todos, _ = _commits_do_intervalo(raiz, nome, "")
        ramos.append({
            "nome": nome,
            "ponto": campos[1],
            "curto": curto(campos[1]),
            "atual": campos[2].strip() == "*",
            "base": base,
            "por_publicar": len(commits),
            "commits": commits,
            "todos": todos,
            "data": campos[4],
            "mensagem": (campos[5] or "").strip(),
        })
    return ramos, ""


def versoes(pasta):
    """Etiquetas e ramos com o ponto exato de cada um e os commits do intervalo de cada etiqueta."""
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return {"repo": False, "motivo": erro, "tags": [], "ramos": []}
    tags, erro_tags = _tags_com_ponto(raiz)
    _preencher_intervalos(raiz, tags)
    ramos, erro_ramos = _ramos_com_ponto(raiz)
    return {"repo": True, "raiz": raiz, "tags": tags, "ramos": ramos, "erro": erro_tags or erro_ramos}


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


def caminhos_do_repo(pasta, caminhos):
    """Converte caminhos relativos a pasta do projeto em relativos a raiz do repositorio."""
    raiz, _ = pasta_do_repositorio(pasta)
    if not raiz:
        return list(caminhos or [])
    return _converter_caminhos(pasta, raiz, caminhos)


def _converter_caminhos(pasta, raiz, caminhos):
    """Caminhos relativos a pasta do projeto vistos desde a raiz do repositorio."""
    convertidos = []
    for rel in caminhos or []:
        alvo = os.path.abspath(os.path.join(pasta, str(rel).replace("/", os.sep)))
        convertidos.append(os.path.relpath(alvo, raiz).replace(os.sep, "/"))
    return convertidos


def pendentes(pasta, caminhos):
    """Subconjunto destes caminhos (relativos a raiz do repositorio) com alteracoes por commitar."""
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return {"repo": False, "motivo": erro}
    if not caminhos:
        return {"repo": True, "pendentes": [], "count": 0}
    texto, erro_status = git_saida(raiz, "status", "--porcelain", "--", *caminhos)
    if erro_status:
        return {"repo": True, "pendentes": [], "count": 0, "erro": erro_status}
    nomes = []
    for linha in (texto or "").splitlines():
        if len(linha) < 4:
            continue
        nome = linha[3:].strip().strip('"')
        if " -> " in nome:
            nome = nome.split(" -> ")[-1]
        if nome and nome not in nomes:
            nomes.append(nome)
    if not nomes:
        return {"repo": True, "pendentes": [], "count": 0, "levou": _ultimo_commit(raiz, caminhos)}
    return {"repo": True, "pendentes": nomes, "count": len(nomes)}


def por_subir(pasta, limite=_LIMITE_POR_SUBIR, remoto=None):
    """Commits locais que ainda nao chegaram a nenhum ramo remoto; 'truncado' avisa que a lista saiu cortada."""
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return {"repo": False, "motivo": erro, "remoto": "", "commits": [], "count": 0}
    if remoto is None:
        remoto, _ = git_saida(raiz, "remote", "get-url", "origin")
    remoto = (remoto or "").strip()
    if not remoto:
        return {"repo": True, "raiz": raiz, "remoto": "", "commits": [], "count": 0}
    formato = _SEPARADOR.join(["%H", "%h", "%s", "%cI"])
    saida, erro_log = git_saida(
        raiz, "log", f"--max-count={int(limite) + 1}", "HEAD", "--not", "--remotes", f"--pretty=format:{formato}"
    )
    commits = []
    for linha in (saida or "").splitlines():
        partes = linha.split(_SEPARADOR)
        if len(partes) < 4:
            continue
        commits.append({"hash": partes[0], "curto": partes[1], "mensagem": partes[2], "data": partes[3]})
    truncado = len(commits) > int(limite)
    return {
        "repo": True,
        "raiz": raiz,
        "remoto": remoto,
        "commits": commits[:int(limite)],
        "count": min(len(commits), int(limite)),
        "truncado": truncado,
        "erro": erro_log,
    }


def empurrar(pasta):
    """Envia o ramo atual para o remoto. Nunca reescreve historia: nao usa force."""
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return {"status": "error", "message": erro}
    remoto, _ = git_saida(raiz, "remote", "get-url", "origin")
    if not (remoto or "").strip():
        return {"status": "error", "message": "Este projeto nao tem remoto (origin): nao ha para onde enviar."}
    antes = por_subir(raiz).get("count", 0)
    ramo = _ramo_atual(raiz)
    _, sem_upstream = git_saida(raiz, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if sem_upstream:
        saida, erro_push = git_saida(raiz, "push", "--set-upstream", "origin", ramo)
    else:
        saida, erro_push = git_saida(raiz, "push")
    if erro_push:
        return {"status": "error", "message": erro_push}
    depois = por_subir(raiz).get("count", 0)
    return {
        "status": "ok",
        "ramo": ramo,
        "enviados": max(0, antes - depois),
        "restantes": depois,
        "saida": (saida or "").strip()[-400:],
    }


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
    so_os_da_tarefa = ["--", *caminhos] if caminhos else []
    prontos, _ = git_saida(raiz, "diff", "--cached", "--name-only", *so_os_da_tarefa)
    entrando = [l.strip() for l in (prontos or "").splitlines() if l.strip()]
    if not entrando:
        return {"status": "vazio", "message": "Nada por commitar nesta tarefa."}
    texto = (mensagem or "").strip() or "Tarefa sem titulo"
    _, erro_commit = git_saida(raiz, "commit", "-m", texto, *so_os_da_tarefa)
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


def emendar(pasta, mensagem, revisao=""):
    """Reescreve a mensagem do ultimo commit, so quando isso nao reescreve historia publicada.

    Exige tres condicoes: nada em stage (senao o amend levaria ficheiros que nao sao
    desta tarefa), o commit da tarefa ser a ponta do ramo (senao apagaria o que veio
    depois) e ainda nao estar no remoto nem levar etiqueta (senao a etiqueta e os
    hashes ja gravados apontariam para um commit que deixa de existir).
    """
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return {"status": "error", "message": erro}
    texto = (mensagem or "").strip()
    if not texto:
        return {"status": "error", "message": "Escreve a mensagem que queres dar a este commit."}
    em_stage, _, _, _ = _sujos(raiz)
    if em_stage:
        return {"status": "error", "message": "Ha ficheiros em stage: emendar levaria coisas que nao sao desta tarefa."}
    ponta, _ = git_saida(raiz, "rev-parse", "HEAD")
    ponta = (ponta or "").strip()
    if revisao and revisao != ponta:
        return {"status": "error", "message": "Ja ha commits depois deste: emendar apagaria o que veio a seguir."}
    info = por_subir(pasta)
    if info.get("remoto") and ponta not in [c["hash"] for c in info.get("commits", [])]:
        return {"status": "error", "message": "Este commit ja esta no GitHub: mudar-lhe a mensagem so por reescrita de historia."}
    etiquetas, _ = _tags_relacionadas(raiz, ponta, "--contains")
    if etiquetas:
        return {"status": "error", "message": f"O commit ja leva a etiqueta {etiquetas[0]}: a etiqueta ficaria pendurada."}
    _, erro_commit = git_saida(raiz, "commit", "--amend", "-m", texto)
    if erro_commit:
        return {"status": "error", "message": erro_commit}
    novo, _ = git_saida(raiz, "rev-parse", "HEAD")
    novo = (novo or "").strip()
    return {"status": "ok", "hash": novo, "curto": curto(novo), "emendado": True}


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


def registrar_restauro(pasta, caminhos, titulo, detalhe=""):
    """Grava um ponto com o estado que acabou de ser restaurado, por cima do ramo.

    O restauro mexe so no disco: sem este ponto o ramo continua a apontar para o
    codigo que foi desfeito e o envio para a nuvem levaria essa versao. O commit
    entra no topo, com hash novo, sem reescrever nenhum commit anterior.
    """
    limpos = _validar_caminhos(caminhos)
    if not limpos:
        return {"status": "vazio", "message": "Nada para gravar neste restauro."}
    if not pasta_do_repositorio(pasta)[0]:
        return {"status": "sem_repo", "message": "A pasta do projeto nao e um repositorio git."}
    mensagem = (titulo or "").strip() or "Volta ao ponto anterior"
    if (detalhe or "").strip():
        mensagem += "\n\n" + detalhe.strip()
    return commitar(pasta, mensagem, limpos)


def revisao_existe(pasta, revisao):
    raiz, erro = pasta_do_repositorio(pasta)
    if erro:
        return False
    _, erro_ver = git_saida(raiz, "rev-parse", "--verify", f"{revisao}^{{commit}}")
    return not erro_ver
