"""Dependencias externas que o codigo usa e as que os manifestos declaram.

Le requirements.txt, package.json e pyproject.toml e cruza-os com os imports
reais do projeto (.py por AST, .js por import/require) para responder ao painel
de informacoes e ao contexto do prompt. O casamento com o manifesto e por nome
normalizado, porque o nome importado quase nunca e o nome publicado
(`import tavily` -> pacote `tavily-python`).
"""
import os
import re
import ast
import json
import sys

from src.backend.tools.projeto_comum import (
    EXTENSOES_JS,
    EXTENSOES_PY,
    PASTAS_IGNORADAS,
    arquivos_de_codigo,
)

BUILTINS_NODE = {
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
    "crypto", "dgram", "diagnostics_channel", "dns", "domain", "events", "fs",
    "http", "http2", "https", "inspector", "module", "net", "os", "path",
    "perf_hooks", "process", "punycode", "querystring", "readline", "repl",
    "stream", "string_decoder", "timers", "tls", "trace_events", "tty", "url",
    "util", "v8", "vm", "wasi", "worker_threads", "zlib",
}
MAX_ARQUIVOS_DEPENDENCIAS = 800
_RE_IMPORT_JS = re.compile(r"""import\s+(?:[\w${}*,\s]+\s+from\s+)?['"]([^'"]+)['"]""")
_RE_REQUIRE_JS = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]""")


def manifests_do_projeto(raiz):
    """Manifestos de dependencias com os nomes reais dos pacotes (dados, nao texto).

    Nucleo unico desta informacao: `_dependencias` formata-o para o contexto do
    prompt e o painel de informacoes (`dados_projeto`) serve-o em JSON. Sem isto
    haveria duas leituras do mesmo manifesto, que divergem no primeiro dia.
    """
    saida = []
    req = os.path.join(raiz, "requirements.txt")
    if os.path.exists(req):
        nomes = []
        try:
            with open(req, "r", encoding="utf-8", errors="ignore") as f:
                for l in f:
                    l = l.strip()
                    if not l or l.startswith("#") or l.startswith("-"):
                        continue
                    nome = l.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split("[")[0].strip()
                    if nome:
                        nomes.append(nome)
        except OSError:
            nomes = []
        if nomes:
            saida.append({"manifesto": "requirements.txt", "rotulo": "pacotes",
                          "pacotes": sorted(set(nomes), key=str.lower)})
    pkg_path = os.path.join(raiz, "package.json")
    if os.path.exists(pkg_path):
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            deps = list((pkg.get("dependencies") or {}).keys()) + list((pkg.get("devDependencies") or {}).keys())
        except Exception:
            deps = []
        if deps:
            saida.append({"manifesto": "package.json", "rotulo": "dependências",
                          "pacotes": sorted(set(deps), key=str.lower)})
    pyproject = os.path.join(raiz, "pyproject.toml")
    if os.path.exists(pyproject):
        try:
            with open(pyproject, "r", encoding="utf-8", errors="ignore") as f:
                nlinhas = sum(1 for _ in f)
        except OSError:
            nlinhas = 0
        saida.append({"manifesto": "pyproject.toml", "rotulo": "linhas",
                      "pacotes": [], "linhas": nlinhas})
    return saida

def manifests_em_texto(raiz):
    linhas = []
    for m in manifests_do_projeto(raiz):
        if m["pacotes"]:
            linhas.append(f"{m['manifesto']} ({len(m['pacotes'])} {m['rotulo']}): " + ", ".join(m["pacotes"]))
        else:
            linhas.append(f"{m['manifesto']} presente ({m.get('linhas', 0)} linhas)")
    return "\n".join(linhas) if linhas else "(sem manifestos de dependências detectados)"

def _modulos_locais(raiz, arquivos):
    """Nomes que o codigo do projeto importa de si mesmo (nao sao dependencias)."""
    nomes = set()
    for caminho in arquivos:
        nomes.add(os.path.splitext(os.path.basename(caminho))[0])
    try:
        for nome in os.listdir(raiz):
            if os.path.isdir(os.path.join(raiz, nome)) and nome not in PASTAS_IGNORADAS:
                nomes.add(nome)
    except OSError:
        pass
    return nomes

def _imports_python(caminho):
    """Modulos de TOPO importados por um ficheiro .py (stdlib incluida, filtrada depois).

    Nao confundir com `_py_imports` (tools/py_imports.py): aquele devolve os NOMES
    que entraram no escopo (`from flask import Flask` -> 'Flask'), o que serve a
    auditoria de dead code. Aqui a pergunta e outra - QUE PACOTE foi usado - logo
    devolve-se 'flask'. Sao responsabilidades diferentes, nao duplicacao.
    """
    try:
        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
            arvore = ast.parse(f.read())
    except (OSError, SyntaxError, ValueError):
        return set()
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for alias in no.names:
                nomes.add(alias.name.split(".")[0])
        elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
            nomes.add(no.module.split(".")[0])
    return nomes

def _imports_js(caminho):
    """Especificadores EXTERNOS importados/dados a require por um ficheiro JS."""
    try:
        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
            conteudo = f.read()
    except OSError:
        return set()
    nomes = set()
    for esp in _RE_IMPORT_JS.findall(conteudo) + _RE_REQUIRE_JS.findall(conteudo):
        if not esp or esp.startswith(".") or esp.startswith("/") or "://" in esp:
            continue
        if esp.startswith("node:"):
            continue
        partes = esp.split("/")
        nome = "/".join(partes[:2]) if esp.startswith("@") and len(partes) >= 2 else partes[0]
        if nome and nome not in BUILTINS_NODE:
            nomes.add(nome)
    return nomes

def normalizar_pacote(nome):
    """Forma comparavel de um nome de pacote (sem hifens, underscores ou pontos)."""
    return re.sub(r"[-_.]", "", str(nome or "")).lower()

def _esta_declarado(nome, normalizados):
    """O pacote importado consta do manifesto, tolerando nomes diferentes.

    `import tavily` (pacote tavily-python), `import dotenv` (python-dotenv) e
    `import socketio` (python-socketio) sao o MESMO pacote com nomes diferentes:
    sem esta tolerancia o painel enchia-se de falsos "por declarar". Compara-se a
    forma normalizada por igualdade ou por continencia, o que erra por omissao
    (nao marca) e nunca por ruido.
    """
    alvo = normalizar_pacote(nome)
    if not alvo:
        return False
    return any(alvo == d or alvo in d or d in alvo for d in normalizados)

def dependencias_do_codigo(raiz):
    """Dependencias externas USADAS no codigo, mesmo sem manifesto gerado.

    O painel de informacoes precisa de listar dependencias quando o
    requirements.txt ainda nao existe, por isso os imports reais sao a fonte:
    .py por AST, .js por import/require. A stdlib e os modulos do proprio projeto
    ficam de fora. O casamento com o manifesto e por nome normalizado (ver
    `_esta_declarado`), porque o nome importado quase nunca e o nome publicado.
    """
    arquivos = [c for c in arquivos_de_codigo(MAX_ARQUIVOS_DEPENDENCIAS)
                if os.path.splitext(c)[1].lower() in EXTENSOES_PY + EXTENSOES_JS]
    locais = _modulos_locais(raiz, arquivos)
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    usados = set()
    for caminho in arquivos:
        ext = os.path.splitext(caminho)[1].lower()
        nomes = _imports_python(caminho) if ext in EXTENSOES_PY else _imports_js(caminho)
        for nome in nomes:
            if nome not in locais and nome not in stdlib:
                usados.add(nome)
    declarados = set()
    for m in manifests_do_projeto(raiz):
        declarados.update(normalizar_pacote(p) for p in m.get("pacotes", []))
    return {
        "usadas": sorted(usados, key=str.lower),
        "nao_declaradas": sorted((n for n in usados if not _esta_declarado(n, declarados)), key=str.lower),
        "declaradas": len(declarados),
    }

