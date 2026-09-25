"""A API de ficheiros do CMake: os alvos, as fontes e as flags reais do projeto.

O CMake responde por JSON a um pedido deixado em <build>/.cmake/api/v1/query/client-axio/query.json
e escreve a resposta em <build>/.cmake/api/v1/reply/. E a MESMA fonte que o Qt Creator usa para
desenhar a arvore dele, por isso os alvos e o agrupamento das fontes saem do projeto e nao de um
palpite pela extensao dos ficheiros.
https://cmake.org/cmake/help/latest/manual/cmake-file-api.7.html

Forma real medida no CMake 4.0.2 (nao vem de memoria): o objeto `codemodel` guarda os `projects`,
`directories` e `targets` DENTRO de cada configuracao, e cada alvo tem um ficheiro proprio com
`sources`, `sourceGroups` e `compileGroups`.
"""

import json
import os

CLIENTE = "client-axio"
PASTA_QUERY = os.path.join(".cmake", "api", "v1", "query")
PASTA_REPLY = os.path.join(".cmake", "api", "v1", "reply")

_OBJETOS = (
    {"kind": "codemodel", "version": 2},
    {"kind": "cmakeFiles", "version": 1},
    {"kind": "toolchains", "version": 1},
)

_CLIENTE_JSON = {"name": "axio", "version": "1.0"}

_PREFERIDAS = ("Debug", "RelWithDebInfo", "Release", "MinSizeRel")


def escrever_pedido(pasta_build):
    """Deixa o pedido na arvore de build: a proxima geracao do CMake responde-lhe."""
    destino = os.path.join(pasta_build, PASTA_QUERY, CLIENTE)
    try:
        os.makedirs(destino, exist_ok=True)
        with open(os.path.join(destino, "query.json"), "w", encoding="utf-8") as f:
            json.dump({"requests": list(_OBJETOS), "client": _CLIENTE_JSON}, f, indent=2)
    except OSError as e:
        return {"erro": f"nao consegui escrever o pedido da File API: {e}"}
    return {"arquivo": os.path.join(destino, "query.json").replace("\\", "/")}


def ultimo_indice(pasta_build):
    """Indice mais recente da resposta, ou vazio. O CMake apaga os antigos; vence o maior nome."""
    pasta = os.path.join(pasta_build, PASTA_REPLY)
    if not os.path.isdir(pasta):
        return ""
    indices = sorted(
        n for n in os.listdir(pasta) if n.startswith("index-") and n.endswith(".json")
    )
    return os.path.join(pasta, indices[-1]) if indices else ""


def resposta(pasta_build):
    """A resposta mais recente do CMake por tipo de objeto, ou vazio se ainda nao ha nenhuma."""
    indice = ultimo_indice(pasta_build)
    if not indice:
        return {}
    pasta = os.path.join(pasta_build, PASTA_REPLY)
    dados = _ler_json(pasta, os.path.basename(indice))
    if not isinstance(dados, dict):
        return {}
    saida = {"cmake": dados.get("cmake") or {}}
    for objeto in dados.get("objects") or []:
        nome = objeto.get("jsonFile")
        if nome and objeto.get("kind"):
            saida[objeto["kind"]] = _ler_json(pasta, os.path.basename(nome))
    return saida


def alvos(pasta_build, configuracao=""):
    """Alvos do projeto com as fontes agrupadas e as flags, tal como o CMake os modela."""
    modelo = resposta(pasta_build).get("codemodel") or {}
    if not isinstance(modelo, dict):
        return []
    configuracao = configuracao or _configuracao_preferida(modelo)
    pasta = os.path.join(pasta_build, PASTA_REPLY)
    caminhos = modelo.get("paths") or {}
    for conf in modelo.get("configurations") or []:
        if conf.get("name") != configuracao:
            continue
        return [_alvo(pasta, item, caminhos) for item in conf.get("targets") or []]
    return []


def _configuracao_preferida(modelo):
    nomes = [c.get("name") for c in modelo.get("configurations") or []]
    for preferida in _PREFERIDAS:
        if preferida in nomes:
            return preferida
    return nomes[0] if nomes else ""


def _alvo(pasta_reply, item, caminhos):
    dados = _ler_json(pasta_reply, os.path.basename(item.get("jsonFile") or ""))
    if not isinstance(dados, dict):
        dados = {}
    origem = caminhos.get("source") or ""
    build = caminhos.get("build") or ""
    grupos_compile = dados.get("compileGroups") or []
    nomes = [g.get("name") or "" for g in dados.get("sourceGroups") or []]
    fontes = _fontes(dados.get("sources") or [], nomes, origem, build)
    return {
        "nome": dados.get("name") or item.get("name") or "",
        "id": dados.get("id") or item.get("id") or "",
        "tipo": dados.get("type") or "",
        "artefactos": [_absoluto(a.get("path"), build) for a in dados.get("artifacts") or []],
        "grupos": _grupos(fontes, nomes),
        "includes": _unicos(i.get("path") for g in grupos_compile for i in g.get("includes") or []),
        "defines": _unicos(d.get("define") for g in grupos_compile for d in g.get("defines") or []),
        "linguagens": _unicos(g.get("language") for g in grupos_compile),
        "fontes": [f["relativo"] for f in fontes],
    }


def _grupos(fontes, nomes):
    """Agrupa as fontes pelo nome que o proprio CMake lhes deu, mantendo a ordem dele."""
    por_nome = {}
    for fonte in fontes:
        por_nome.setdefault(fonte["grupo"], []).append(fonte)
    ordenados = [{"nome": nome, "ficheiros": por_nome.pop(nome, [])} for nome in nomes]
    ordenados += [{"nome": nome, "ficheiros": do_grupo} for nome, do_grupo in por_nome.items()]
    return [g for g in ordenados if g["ficheiros"]]


def _fontes(fontes, nomes_de_grupo, origem, build):
    saida = []
    for fonte in fontes:
        relativo = fonte.get("path") or ""
        if not relativo:
            continue
        absoluto = _absoluto(relativo, origem)
        dentro = _dentro_de(absoluto, origem)
        if not dentro:
            absoluto = _absoluto(relativo, build)
            dentro = _dentro_de(absoluto, origem)
        indice = fonte.get("sourceGroupIndex")
        grupo = nomes_de_grupo[indice] if isinstance(indice, int) and indice < len(nomes_de_grupo) else ""
        saida.append({
            "relativo": _relativo(absoluto, origem) if dentro else absoluto,
            "absoluto": absoluto,
            "grupo": grupo,
            "gerado": bool(fonte.get("isGenerated")) or _dentro_de(absoluto, build),
            "externo": not dentro,
        })
    return saida


def _absoluto(caminho, base):
    if not caminho:
        return ""
    if os.path.isabs(caminho):
        return os.path.normpath(caminho).replace("\\", "/")
    return os.path.normpath(os.path.join(base, caminho)).replace("\\", "/")


def _relativo(absoluto, origem):
    try:
        return os.path.relpath(absoluto, origem).replace("\\", "/")
    except ValueError:
        return absoluto


def _dentro_de(absoluto, origem):
    if not absoluto or not origem:
        return False
    normal_abs = os.path.normcase(os.path.normpath(absoluto))
    normal_origem = os.path.normcase(os.path.normpath(origem))
    return normal_abs == normal_origem or normal_abs.startswith(normal_origem + os.sep)


def _unicos(itens):
    return sorted({i for i in itens if i})


def _ler_json(pasta, nome):
    if not nome:
        return {}
    try:
        with open(os.path.join(pasta, nome), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}
