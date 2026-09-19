"""Deteccao lexica de comentarios de codigo, por linguagem.

Camada de LEITURA do auditor de comentarios (`tools/comments.py`): descobre o
modo pela extensao e devolve cada comentario de um texto com a posicao exata.
A deteccao e LEXICA, nao regex solta: strings, template literals e regex
literais nunca sao confundidos com comentarios - era o defeito classico de
procurar "//" ou "#" no texto cru (ex: a URL "https://..." dentro de uma
string, ou um "#" dentro de aspas no shell).

Modos por extensao:
  python -> tokenize da stdlib (COMMENT) + docstrings pela AST
  c      -> // e /* */ (JS/TS/Java/C/C++/Go/Rust/PHP); regex literais no JS
  css    -> /* */ apenas
  html   -> <!-- --> (HTML/XML/Vue/Svelte/Markdown)
  hash   -> # ate ao fim da linha (YAML/TOML/shell/Ruby/INI)
  sql    -> -- e /* */

Modulo puro: nao le do disco, nao grava e nao emite eventos. Tudo o que a
ferramenta faz DEPOIS de ter os comentarios (filtrar, editar, reverter) fica em
`tools/comments.py`.
"""

import ast
import hashlib
import io
import os
import re
import tokenize

_EXTENSOES = {
    "python": (".py", ".pyw"),
    "javascript": (".js", ".mjs", ".cjs", ".jsx"),
    "typescript": (".ts", ".tsx"),
    "java": (".java",),
    "c": (".c", ".h"),
    "cpp": (".cpp", ".hpp", ".cc"),
    "csharp": (".cs",),
    "go": (".go",),
    "rust": (".rs",),
    "swift": (".swift",),
    "kotlin": (".kt",),
    "php": (".php",),
    "css": (".css", ".scss", ".less"),
    "html": (".html", ".htm", ".xml", ".svg", ".vue", ".svelte", ".md", ".markdown"),
    "yaml": (".yaml", ".yml", ".toml", ".sh", ".bash", ".zsh", ".ini", ".cfg",
             ".conf", ".ps1", ".rb", ".pl", ".r"),
    "sql": (".sql",),
}

_FAMILIA = {
    "python": "python", "javascript": "c", "typescript": "c", "java": "c", "c": "c",
    "cpp": "c", "csharp": "c", "go": "c", "rust": "c", "swift": "c", "kotlin": "c",
    "php": "c", "css": "css", "html": "html", "yaml": "hash", "sql": "sql",
}

_MODOS = {}
_LINGUAGEM = {}
for _ling, _exts in _EXTENSOES.items():
    for _ext in _exts:
        _MODOS[_ext] = _FAMILIA[_ling]
        _LINGUAGEM[_ext] = _ling

IGNORAR_PASTAS = {".git", "node_modules", "__pycache__", ".venv", "venv",
                   "dist", "build", "site-packages", ".mypy_cache",
                   ".ruff_cache", ".vs", "bin", "obj"}

_PALAVRAS_ANTES_DE_REGEX = {
    "return", "typeof", "case", "in", "of", "do", "else", "void", "delete",
    "throw", "new", "yield", "await", "instanceof",
}

TIPOS_DE_COMENTARIO = ("linha", "bloco", "html", "docstring")

def modo_de(caminho):
    return _MODOS.get(os.path.splitext(caminho)[1].lower(), "")

def linguagem_de(caminho):
    return _LINGUAGEM.get(os.path.splitext(caminho)[1].lower(), "desconhecida")

def sha(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()

def _hash_conteudo(texto):
    """Hash curto e estavel do CONTEUDO do comentario (espacos colapsados).

    Comentarios com o mesmo texto partilham o hash: remover por hash remove
    todas as repeticoes (ex: 20 linhas "// TODO: x"). Para um unico alvo use
    'linha_inicio'/'linha_fim'.
    """
    normalizado = re.sub(r"\s+", " ", (texto or "")).strip()
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()[:12]

def _col_ast_para_chars(linha, col_ast):
    """O col_offset do ast e em BYTES UTF-8; converte-o para colunas de caracteres.

    Sem esta conversao, qualquer linha com acento antes de uma docstring
    desalinharia o corte (o slicing trabalha em caracteres, nao em bytes).
    """
    if not linha or not col_ast:
        return 0
    try:
        return len(linha.encode("utf-8")[:col_ast].decode("utf-8", "ignore"))
    except Exception:
        return col_ast

def _inicia_regex(texto, i):
    """Heuristica de JSLint: decide se o '/' em `i` abre um regex literal.

    Os comentarios (// e /*) ja foram descartados antes desta chamada, logo a
    unica ambiguidade que resta e regex literal vs divisao.
    """
    j = i - 1
    while j >= 0 and texto[j] in " \t":
        j -= 1
    if j < 0:
        return True
    if texto[j] in ")]}":
        return False
    if texto[j] in "=,;:([!&|?+-*%^~<>{}":
        return True
    k = j
    while k >= 0 and (texto[k].isalnum() or texto[k] in "_$"):
        k -= 1
    return texto[k + 1:j + 1] in _PALAVRAS_ANTES_DE_REGEX

def _novo_avancador(texto, estado):
    """Devolve o 'avancar(n)' que move a posicao (i, linha, col) de um scanner.

    Ponto unico da contagem de linha/coluna partilhada pelos tres scanners: a
    copia local desta closure em cada um deles era duplicacao pura (o jscpd
    acusava 4 clones no proprio modulo).
    """
    n = len(texto)

    def avancar(quantidade):
        for _ in range(quantidade):
            if estado["i"] >= n:
                return
            if texto[estado["i"]] == "\n":
                estado["linha"] += 1
                estado["col"] = 0
            else:
                estado["col"] += 1
            estado["i"] += 1

    return avancar

def _consumir_string(texto, estado, avancar, aspa, escapa_todas):
    """Consome uma string a partir da aspa aberta (o estado aponta para ela).

    Ponto unico do consumo de strings partilhado pelos scanners: `escapa_todas`
    diz se todas as aspas aceitam '\\' como escape (JS/C) ou se so' a dupla o
    faz (shell/YAML/Ruby). Um backtick nunca quebra na linha (template literal);
    as restantes aspas param no fim da linha.
    """
    n = len(texto)
    avancar(1)
    while estado["i"] < n:
        ch = texto[estado["i"]]
        if ch == "\\" and (escapa_todas or aspa == '"'):
            avancar(2)
            continue
        if ch == aspa:
            avancar(1)
            break
        if ch == "\n" and aspa != "`":
            break
        avancar(1)

def _iniciar_scan(texto):
    """(n, estado, avancar) de um scanner novo.

    O estado e o MESMO dicionario que o avancar move (posicao viva), por isso os
    dois tem de nascer juntos. Ponto unico do arranque dos tres scanners, que
    repetiam estas quatro linhas.
    """
    estado = {"i": 0, "linha": 1, "col": 0}
    return len(texto), estado, _novo_avancador(texto, estado)

def _ler_ate_fim_da_linha(texto, estado, avancar):
    """Consome ate' ao fim da linha; devolve onde o comentario comecou."""
    n = len(texto)
    inicio = (estado["linha"], estado["col"])
    while estado["i"] < n and texto[estado["i"]] != "\n":
        avancar(1)
    return inicio

def _ler_bloco(texto, estado, avancar, abre="/*", fecha="*/"):
    """Consome um comentario de bloco delimitado; devolve onde comecou."""
    n = len(texto)
    inicio = (estado["linha"], estado["col"])
    avancar(len(abre))
    while estado["i"] < n and not texto.startswith(fecha, estado["i"]):
        avancar(1)
    avancar(len(fecha))
    return inicio

def _escanear_c(texto, permitir_linha=True, permitir_regex=True):
    """Comentarios // e /* */ fora de strings, templates e regex literais."""
    achados = []
    n, estado, avancar = _iniciar_scan(texto)

    while estado["i"] < n:
        c = texto[estado["i"]]
        if c in "'\"`":
            _consumir_string(texto, estado, avancar, c, escapa_todas=True)
            continue
        if c == "/" and estado["i"] + 1 < n:
            seguinte = texto[estado["i"] + 1]
            if seguinte == "/" and permitir_linha:
                inicio = _ler_ate_fim_da_linha(texto, estado, avancar)
                achados.append(inicio + (estado["linha"], estado["col"], "linha"))
                continue
            if seguinte == "*":
                inicio = _ler_bloco(texto, estado, avancar)
                achados.append(inicio + (estado["linha"], estado["col"], "bloco"))
                continue
            if permitir_regex and _inicia_regex(texto, estado["i"]):
                avancar(1)
                dentro_classe = False
                while estado["i"] < n:
                    ch = texto[estado["i"]]
                    if ch == "\\":
                        avancar(2)
                        continue
                    if ch == "[":
                        dentro_classe = True
                    elif ch == "]":
                        dentro_classe = False
                    elif ch == "/" and not dentro_classe:
                        avancar(1)
                        break
                    elif ch == "\n":
                        break
                    avancar(1)
                while estado["i"] < n and texto[estado["i"]].isalpha():
                    avancar(1)
                continue
        avancar(1)
    return achados

def _escanear_marcado(texto, marcador, com_bloco=False):
    """Comentarios de marcador simples ('#' ou '--'), fora de strings."""
    achados = []
    n, estado, avancar = _iniciar_scan(texto)

    while estado["i"] < n:
        c = texto[estado["i"]]
        if c in "'\"":
            _consumir_string(texto, estado, avancar, c, escapa_todas=False)
            continue
        if com_bloco and texto.startswith("/*", estado["i"]):
            inicio = _ler_bloco(texto, estado, avancar)
            achados.append(inicio + (estado["linha"], estado["col"], "bloco"))
            continue
        if texto.startswith(marcador, estado["i"]):
            inicio = _ler_ate_fim_da_linha(texto, estado, avancar)
            achados.append(inicio + (estado["linha"], estado["col"], "linha"))
            continue
        avancar(1)
    return achados

def _escanear_html(texto):
    """Comentarios <!-- --> (HTML/XML/Vue/Markdown)."""
    achados = []
    n, estado, avancar = _iniciar_scan(texto)

    while estado["i"] < n:
        if texto.startswith("<!--", estado["i"]):
            inicio = _ler_bloco(texto, estado, avancar, abre="<!--", fecha="-->")
            achados.append(inicio + (estado["linha"], estado["col"], "html"))
            continue
        avancar(1)
    return achados

def _escanear_python(texto, incluir_docstrings=True):
    """COMMENT do tokenize + docstrings da AST (posicoes convertidas p/ chars)."""
    achados = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(texto).readline):
            if tok.type == tokenize.COMMENT:
                achados.append((tok.start[0], tok.start[1], tok.end[0], tok.end[1], "linha"))
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        pass
    if not incluir_docstrings:
        return achados
    try:
        arvore = ast.parse(texto)
    except (SyntaxError, ValueError):
        return achados
    linhas = texto.splitlines(keepends=True)
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        corpo = getattr(no, "body", None) or []
        if not corpo:
            continue
        primeiro = corpo[0]
        if not (isinstance(primeiro, ast.Expr)
                and isinstance(primeiro.value, ast.Constant)
                and isinstance(primeiro.value.value, str)):
            continue
        valor = primeiro.value
        linha_ini = valor.lineno
        linha_fim = valor.end_lineno or valor.lineno
        col_ini = _col_ast_para_chars(linhas[linha_ini - 1] if linha_ini <= len(linhas) else "", valor.col_offset)
        col_fim = _col_ast_para_chars(linhas[linha_fim - 1] if linha_fim <= len(linhas) else "", valor.end_col_offset)
        achados.append((linha_ini, col_ini, linha_fim, col_fim, "docstring"))
    achados.sort()
    return achados

def detetar(abs_path, texto, incluir_docstrings=True):
    """(modo, [(linha, col, fim_linha, fim_col, tipo)]) do ficheiro."""
    modo = modo_de(abs_path)
    if modo == "python":
        return modo, _escanear_python(texto, incluir_docstrings)
    if modo == "c":
        return modo, _escanear_c(texto, permitir_linha=True, permitir_regex=True)
    if modo == "css":
        return modo, _escanear_c(texto, permitir_linha=False, permitir_regex=False)
    if modo == "html":
        return modo, _escanear_html(texto)
    if modo == "hash":
        return modo, _escanear_marcado(texto, "#")
    if modo == "sql":
        return modo, _escanear_marcado(texto, "--", com_bloco=True)
    return "", []

def _delimitadores(tipo, modo, bruto):
    """(abre, fecha) do comentario - o fecha vazio significa 'ate fim da linha'."""
    if tipo == "bloco":
        return "/*", "*/"
    if tipo == "html":
        return "<!--", "-->"
    if tipo == "docstring":
        for marca in ('"""', "'''", '"', "'"):
            if bruto.startswith(marca):
                return marca, marca
        return '"""', '"""'
    if modo == "c":
        return "//", ""
    if modo == "sql":
        return "--", ""
    return "#", ""

def _bruto(linhas, alvo):
    linha_ini, col, linha_fim, fim_col = alvo[:4]
    if linha_ini == linha_fim:
        return linhas[linha_ini - 1][col:fim_col]
    partes = [linhas[linha_ini - 1][col:]]
    partes.extend(linhas[linha_ini:linha_fim - 1])
    partes.append(linhas[linha_fim - 1][:fim_col])
    return "".join(partes)

def resumo(texto):
    colapsado = re.sub(r"\s+", " ", texto or "").strip()
    return colapsado if len(colapsado) <= 110 else colapsado[:107] + "..."

def montar_comentarios(linhas, achados, modo):
    """Converte as posicoes cruas em registos ricos (tipo, texto, hash)."""
    registos = []
    for alvo in achados:
        linha_ini, col, linha_fim, fim_col, tipo = alvo
        if linha_ini < 1 or linha_fim > len(linhas):
            continue
        bruto = _bruto(linhas, alvo)
        abre, fecha = _delimitadores(tipo, modo, bruto)
        interior = bruto[len(abre):]
        if fecha and interior.endswith(fecha):
            interior = interior[:-len(fecha)]
        registos.append({
            "espaco_abre": bool(interior[:1].isspace()),
            "espaco_fecha": bool(interior[-1:].isspace()),
            "linha": linha_ini,
            "col": col,
            "fim_linha": linha_fim,
            "fim_col": fim_col,
            "tipo": tipo,
            "abre": abre,
            "fecha": fecha,
            "texto": interior.strip(),
            "resumo": resumo(interior),
            "hash": _hash_conteudo(interior),
        })
    return registos
