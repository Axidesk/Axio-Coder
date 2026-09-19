"""Retrato do repositorio git numa so chamada: onde esta, como esta e o que falta commitar."""

import io
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image

from src.backend.config import APP_ROOT
from src.backend.services import cofre, github
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


def _nomes_das_tags(pasta):
    saida, erro = git_saida(pasta, "tag", "--list", "--sort=-creatordate")
    if erro:
        return [], erro
    return [n.strip() for n in (saida or "").splitlines() if n.strip()], ""


def _linhas_das_tags(pasta, quantas):
    nomes, erro = _nomes_das_tags(pasta)
    if erro:
        return [f"TAGS: nao foi possivel listar ({erro})"]
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


def _notas_da_etiqueta(pasta, etiqueta):
    nomes, _ = _nomes_das_tags(pasta)
    posicao = nomes.index(etiqueta) if etiqueta in nomes else -1
    tem_anterior = 0 <= posicao + 1 < len(nomes)
    intervalo = f"{nomes[posicao + 1]}..{etiqueta}" if tem_anterior else etiqueta
    saida, erro = git_saida(pasta, "log", "--no-merges", "--pretty=- %s", "--max-count=30", intervalo)
    if erro:
        return ""
    return "\n".join(linha for linha in (saida or "").splitlines() if linha.strip())


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
    for separador in (",", ";", "\n"):
        if separador in texto:
            return [p.strip() for p in texto.split(separador) if p.strip()]
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
    "origin' pelo tool_executar_processo. Le tambem a VITRINE do remoto pela API do GitHub quando o "
    "origin e um repositorio publico: descricao, topics, licenca, estrelas, discussions e quantos "
    "RELEASES existem - e a diferenca entre a tag (que so leva o codigo) e o Release (que notifica "
    "quem segue o repositorio). Nao escreve nada no repositorio: so le."
    ,
    {
        'caminho': {"tipo": "STRING", "desc": "Pasta dentro do repositorio (padrao: a pasta do projeto aberto)", "padrao": ""},
        'tags': {"tipo": "INTEGER", "desc": "Quantas tags mostrar, das mais recentes", "padrao": _TAGS_POR_OMISSAO},
        'vitrine': {"tipo": "BOOLEAN", "desc": "Ler tambem a vitrine do repositorio remoto pela API do GitHub (descricao, topics, licenca, Releases)", "padrao": True},
    },
)
def tool_estado_git(caminho="", tags=_TAGS_POR_OMISSAO, vitrine=True):
    base = caminho or estado.get("pasta_raiz") or APP_ROOT
    raiz = raiz_repositorio(base)
    if not raiz:
        return (f"ERRO: '{base}' nao esta dentro de um repositorio git "
                "(nenhuma pasta .git a subir a partir dai).")
    linhas = _linhas_do_repositorio(raiz, tags)
    if vitrine:
        linhas = linhas + _linhas_da_vitrine(raiz)
    return "\n".join(linhas)


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
        'ficheiros': {"tipo": "STRING", "desc": "Caminhos a publicar, separados por espaco (ou por virgula/ponto-e-virgula quando o caminho tiver espacos) - padrao: tudo o que mudou", "padrao": ""},
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


@register(
    "tool_publicar_release",
    "Publica no GitHub o Release de uma etiqueta que ja existe no repositorio. E o Release que "
    "notifica quem segue o repositorio e aparece na aba /releases - a etiqueta empurrada sozinha "
    "fica invisivel para quem nao usa a linha de comandos. A chave do GitHub vive no cofre, no "
    "cartao 'github' campo 'chave' (classic token com o escopo 'repo'). Sem 'notas', o corpo sai "
    "das mensagens dos commits desde a etiqueta anterior. Correr duas vezes na mesma etiqueta "
    "atualiza o Release em vez de falhar.",
    {
        'etiqueta': {"tipo": "STRING", "desc": "Etiqueta ja empurrada para o remoto (ex: 'v3.1.3')"},
        'titulo': {"tipo": "STRING", "desc": "Titulo do Release (padrao: a propria etiqueta)", "padrao": ""},
        'notas': {"tipo": "STRING", "desc": "Corpo do Release em Markdown (padrao: gerado das mensagens dos commits)", "padrao": ""},
        'rascunho': {"tipo": "BOOLEAN", "desc": "Guardar como rascunho em vez de publicar", "padrao": False},
        'caminho': {"tipo": "STRING", "desc": "Pasta dentro do repositorio (padrao: a pasta do projeto aberto)", "padrao": ""},
    },
)
def tool_publicar_release(etiqueta, titulo="", notas="", rascunho=False, caminho=""):
    if not etiqueta:
        return "ERRO: indique a etiqueta do Release (ex: 'v3.1.3')."
    base = caminho or estado.get("pasta_raiz") or APP_ROOT
    raiz = raiz_repositorio(base)
    if not raiz:
        return f"ERRO: '{base}' nao esta dentro de um repositorio git."
    host, slug = _slug_do_remoto(raiz)
    if "github" not in host:
        return (f"ERRO: o remoto 'origin' aponta para '{host or '?'}' - so o GitHub tem o objeto "
                "Release que esta ferramenta publica.")
    nomes, _ = _nomes_das_tags(raiz)
    if etiqueta not in nomes:
        return (f"ERRO: a etiqueta '{etiqueta}' nao existe neste repositorio. "
                f"Existentes: {', '.join(nomes) if nomes else 'nenhuma'}.")
    token = cofre.obter("github", revelar=True, campo="chave")
    if not token:
        return ("ERRO: falta a chave do GitHub no cofre (Configuracoes -> Cofre, cartao 'github', "
                "campo 'chave'; classic token com o escopo 'repo'). Sem ela o GitHub recusa criar Releases.")
    corpo = notas or _notas_da_etiqueta(raiz, etiqueta)
    dados, erro, acao = github.publicar_release(slug, etiqueta, titulo or etiqueta, corpo, rascunho, token)
    if erro:
        return f"ERRO: o GitHub recusou ({erro})."
    linhas = [f"RELEASE {acao}: {etiqueta}",
              f"  titulo: {dados.get('name')}",
              f"  endereco: {dados.get('html_url')}",
              f"  notas: {len(corpo)} caracteres" + ("" if notas else " (geradas das mensagens dos commits)")]
    if dados.get("draft"):
        linhas.append("  AVISO: ficou como rascunho - so tu o ves ate o publicares.")
    return "\n".join(linhas)


def _slug_do_remoto(raiz):
    saida, erro = git_saida(raiz, "remote", "get-url", "origin")
    url = (saida or "").strip()
    if erro or not url:
        return "", ""
    if url.startswith("git@"):
        _, _, resto = url.partition("git@")
        host, _, caminho = resto.partition(":")
    else:
        partes = urllib.parse.urlparse(url)
        host, caminho = partes.netloc or partes.path, partes.path
    host = host.split("@")[-1].strip("/")
    caminho = caminho.strip("/")
    if caminho.endswith(".git"):
        caminho = caminho[:-4]
    if not host or "/" not in caminho:
        return "", ""
    return host, caminho


def _base_do_remoto(raiz, ramo):
    host, caminho = _slug_do_remoto(raiz)
    if not host:
        return ""
    if not ramo:
        nome, _ = git_saida(raiz, "rev-parse", "--abbrev-ref", "HEAD")
        ramo = (nome or "").strip() or "main"
    if "github.com" in host:
        return f"https://raw.githubusercontent.com/{caminho}/{ramo}"
    return f"https://{host}/{caminho}/raw/{ramo}"


def _leitor_sem_proxy():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _ler_remoto(leitor, url):
    with leitor.open(url, timeout=30) as resposta:
        return resposta.read()


def _pedido_json(url):
    dados, erro = github.pedido_api(url)
    if erro:
        raise urllib.error.URLError(erro)
    return dados


def _linhas_da_vitrine(raiz):
    host, caminho = _slug_do_remoto(raiz)
    if "github.com" not in host:
        return [f"VITRINE: o remoto nao e GitHub ('{host or 'sem origin'}') - sem leitura da vitrine."]
    try:
        dados = _pedido_json(f"https://api.github.com/repos/{caminho}")
        releases = _pedido_json(f"https://api.github.com/repos/{caminho}/releases")
    except urllib.error.HTTPError as fora:
        if fora.code == 404:
            return ["VITRINE: a API do GitHub devolveu 404 - o repositorio remoto nao e publico."]
        return [f"VITRINE: a API do GitHub recusou a consulta ({fora.code})."]
    except Exception as falha:
        return [f"VITRINE: nao consegui consultar a API do GitHub ({falha})."]

    partes = [f"VITRINE de {caminho} (o que o GitHub mostra a quem chega):"]
    em_falta = []
    descricao = (dados.get("description") or "").strip()
    if descricao:
        partes.append(f"  descricao: {descricao}")
    else:
        em_falta.append("descricao (a frase que aparece na busca e ao lado do nome)")
    topics = dados.get("topics") or []
    if topics:
        partes.append(f"  topics ({len(topics)}): {', '.join(topics)}")
    else:
        em_falta.append("topics (e por eles que o repositorio aparece nas buscas e nas paginas de assunto)")
    licenca = (dados.get("license") or {}).get("spdx_id")
    if licenca:
        partes.append(f"  licenca: {licenca}")
    else:
        em_falta.append("licenca (sem ela ninguem pode usar nem distribuir o teu codigo)")
    if dados.get("homepage"):
        partes.append(f"  homepage: {dados['homepage']}")
    partes.append(f"  estrelas: {dados.get('stargazers_count', 0)} | "
                  f"quem segue: {dados.get('subscribers_count', 0)} | "
                  f"forkes: {dados.get('forks_count', 0)}")
    if not dados.get("has_discussions"):
        partes.append("  discussions: desligado (e onde as perguntas ficam em publico)")

    nomes = [r.get("tag_name") for r in releases]
    partes.append(f"RELEASES publicados: {len(nomes)}" + (f" ({', '.join(nomes)})" if nomes else ""))
    locais, erro = _nomes_das_tags(raiz)
    sem_release = [t for t in locais if t not in nomes] if not erro else []
    if sem_release:
        partes.append(f"  TAGS SEM RELEASE: {', '.join(sem_release)} - a tag leva o codigo ao remoto, "
                      "mas e o Release que notifica quem segue o repositorio e aparece em /releases")
    if em_falta:
        partes.append("EM FALTA NA VITRINE: " + "; ".join(em_falta))
    return partes


def _tamanho_da_imagem(bruto):
    try:
        with Image.open(io.BytesIO(bruto)) as imagem:
            return f"{imagem.width}x{imagem.height}"
    except Exception:
        return ""


def _caminhos_de_imagem(texto):
    return re.findall(r"!\[[^\]]*\]\(([^)\s]+)", texto)


def _sem_marcacao(texto):
    texto = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", texto)
    texto = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", texto)
    texto = re.sub(r"[*`_#>|]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _blocos_em_falta(disco, publicado, maximo):
    limpo = _sem_marcacao(publicado)
    faltam = []
    for bruto in re.split(r"\n\s*\n", disco):
        frase = _sem_marcacao(bruto)
        if len(frase) < 40 or frase in limpo:
            continue
        faltam.append(frase[:200])
    return faltam[:maximo]


def _linhas_da_conferencia(raiz, ficheiro, ramo, max_frases):
    caminho_local = os.path.join(raiz, ficheiro)
    try:
        with open(caminho_local, "r", encoding="utf-8") as f:
            disco = f.read()
    except OSError as falha:
        return [f"ERRO: nao consegui ler '{caminho_local}' ({falha})."]
    base = _base_do_remoto(raiz, ramo)
    if not base:
        return ["ERRO: o remoto 'origin' nao deu um endereco de leitura (esperado: GitHub ou um host com '/raw/')."]
    leitor = _leitor_sem_proxy()
    url = f"{base}/{ficheiro}"
    try:
        publicado = _ler_remoto(leitor, url).decode("utf-8", errors="replace")
    except Exception as falha:
        return [f"ERRO: nao consegui ler '{url}' ({falha})."]

    partes = [f"PUBLICADO: {url}", f"  {len(publicado)} chars no remoto | {len(disco)} chars no disco"]

    caminhos = _caminhos_de_imagem(publicado)
    partes.append(f"IMAGENS no publicado: {len(caminhos)}")
    falhas = 0
    for caminho_img in caminhos:
        alvo = f"{base}/{caminho_img.lstrip('./')}"
        try:
            bruto = _ler_remoto(leitor, alvo)
            partes.append(f"  OK   {_tamanho_da_imagem(bruto):<11} {len(bruto)/1024:7.1f} KB  {caminho_img}")
        except urllib.error.HTTPError as falha:
            falhas += 1
            partes.append(f"  {falha.code}  FALHA                    {caminho_img}")
        except Exception as falha:
            falhas += 1
            partes.append(f"  ?    FALHA ({falha})  {caminho_img}")

    try:
        limite = max(1, int(max_frases))
    except (TypeError, ValueError):
        limite = 12
    faltam = _blocos_em_falta(disco, publicado, limite)
    if faltam:
        partes.append(f"BLOCO(S) DO DISCO QUE NAO APARECEM INTEIROS NO PUBLICADO: {len(faltam)}")
        for frase in faltam:
            partes.append(f"  - {frase}")
    else:
        partes.append("BLOCO(S) DO DISCO QUE NAO APARECEM INTEIROS NO PUBLICADO: nenhum")

    veredito = ("o publicado bate com o disco" if not falhas and not faltam
                else f"o publicado DIVERGE do disco ({falhas} imagem(ns) em falta, {len(faltam)} bloco(s) por publicar)")
    partes.append(f"VEREDITO: {veredito}")
    return partes


@register(
    "tool_conferir_publicacao",
    "Le o que esta PUBLICADO no remoto e confere-o contra o disco, sem depender dos olhos de ninguem: "
    "pede o ficheiro de texto no endereco de leitura do remoto, pede CADA imagem que ele referencia "
    "(com o status HTTP e as dimensoes reais, que denunciam a imagem servida por um endereco em cache) e "
    "lista os blocos que existem no disco e ainda nao aparecem inteiros no publicado. Use DEPOIS de "
    "publicar e antes de dizer que a pagina esta pronta: foi o que provou que uma imagem tida como "
    "'desatualizada' no GitHub era, afinal, cache da URL - o ficheiro publicado era byte a byte o do disco."
    ,
    {
        'ficheiro': {"tipo": "STRING", "desc": "Ficheiro de texto a conferir no remoto (padrao: README.md)", "padrao": "README.md"},
        'ramo': {"tipo": "STRING", "desc": "Ramo do remoto (padrao: o ramo atual do repositorio)", "padrao": ""},
        'caminho': {"tipo": "STRING", "desc": "Pasta dentro do repositorio (padrao: a pasta do projeto aberto)", "padrao": ""},
        'max_frases': {"tipo": "INTEGER", "desc": "Quantos blocos em falta listar", "padrao": 12},
    },
)
def tool_conferir_publicacao(ficheiro="README.md", ramo="", caminho="", max_frases=12):
    base = caminho or estado.get("pasta_raiz") or APP_ROOT
    raiz = raiz_repositorio(base)
    if not raiz:
        return (f"ERRO: '{base}' nao esta dentro de um repositorio git "
                "(nenhuma pasta .git a subir a partir dai).")
    return "\n".join(_linhas_da_conferencia(raiz, ficheiro, ramo, max_frases))
