"""Mapa das dependencias internas de um modulo (base para dividir god objects).

Mostra, por simbolo de topo (funcao/classe/constante), quem ele usa DENTRO do
mesmo ficheiro, e agrupa tudo em componentes conexas: cada componente e um
candidato natural a virar modulo proprio. Sem isto, dividir um ficheiro grande e
adivinhacao - foi assim que o audit.py (4 dominios, 22 simbolos) virou 6 modulos.

Suporta Python (AST da stdlib, exato no que toca a nomes) e JavaScript/ESM
(tree-sitter). Limite honesto: as arestas sao por NOME dentro do span do simbolo,
logo uma variavel local com o mesmo nome de uma funcao de topo pode criar uma
aresta falsa (no Python isso e raro; no JS, um parametro homonimo).
"""

import ast
import os

from src.backend.services.file_service import resolver_caminho
from src.backend.state import emit_event
from src.backend.tools.registry import register


def _componentes(arestas, nomes):
    vistos = set()
    grupos = []
    for nome in nomes:
        if nome in vistos:
            continue
        pilha = [nome]
        grupo = set()
        while pilha:
            atual = pilha.pop()
            if atual in grupo:
                continue
            grupo.add(atual)
            for outro in nomes:
                if outro in grupo:
                    continue
                if outro in arestas.get(atual, set()) or atual in arestas.get(outro, set()):
                    pilha.append(outro)
        vistos |= grupo
        grupos.append(grupo)
    return sorted(grupos, key=len, reverse=True)


def _simbolos_py(caminho):
    with open(caminho, "r", encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    nos = {}
    for no in arvore.body:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nos[no.name] = no
        elif isinstance(no, ast.Assign):
            for alvo in no.targets:
                if isinstance(alvo, ast.Name):
                    nos[alvo.id] = no
    spans = {nome: (no.lineno, no.end_lineno) for nome, no in nos.items()}
    arestas = {
        nome: {s.id for s in ast.walk(no) if isinstance(s, ast.Name) and s.id in nos and s.id != nome}
        for nome, no in nos.items()
    }
    return spans, arestas, "Python"


def texto_no(fonte, no):
    return fonte[no.start_byte:no.end_byte].decode("utf8")


def _nomes_do_alvo(fonte, alvo):
    """Nomes declarados por um alvo JS: simples ou destructuring ({ a, b: c })."""
    if alvo.type not in ("object_pattern", "array_pattern"):
        return [texto_no(fonte, alvo)]
    pilha = [alvo]
    nomes = []
    while pilha:
        atual = pilha.pop()
        if atual.type in ("identifier", "shorthand_property_identifier_pattern"):
            nomes.append(texto_no(fonte, atual))
            continue
        pilha.extend(atual.children)
    return nomes


def _simbolos_js(caminho):
    try:
        import tree_sitter_javascript as tsjs
        from tree_sitter import Language, Parser
    except ImportError:
        return None, None, "ERRO: tree_sitter ou tree_sitter_javascript nao instalados."

    with open(caminho, "r", encoding="utf-8") as f:
        fonte = bytes(f.read(), "utf8")
    parser = Parser(Language(tsjs.language()))
    raiz = parser.parse(fonte).root_node

    nos = {}
    for filho in raiz.children:
        alvos = []
        if filho.type in ("function_declaration", "class_declaration"):
            alvos.append(filho.child_by_field_name("name"))
        elif filho.type in ("variable_declaration", "lexical_declaration"):
            alvos.extend(
                decl.child_by_field_name("name") for decl in filho.children if decl.type == "variable_declarator"
            )
        for alvo in alvos:
            if alvo is not None:
                for nome in _nomes_do_alvo(fonte, alvo):
                    nos[nome] = filho

    spans = {nome: (no.start_point[0] + 1, no.end_point[0] + 1) for nome, no in nos.items()}
    arestas = {}
    for nome, no in nos.items():
        referencias = set()

        def visitar(atual, nome_raiz=nome):
            if atual.type == "identifier":
                pai = atual.parent
                e_propriedade = pai is not None and pai.type == "member_expression" and pai.child_by_field_name("property") is atual
                e_chave = pai is not None and pai.type == "pair" and pai.child_by_field_name("key") is atual
                texto = texto_no(fonte, atual)
                if not e_propriedade and not e_chave and texto in nos and texto != nome_raiz:
                    referencias.add(texto)
            for filho in atual.children:
                visitar(filho, nome_raiz)

        visitar(no)
        arestas[nome] = referencias
    return spans, arestas, "JavaScript"


def _relatorio(caminho_relativo, linguagem, spans, arestas):
    nomes = list(spans)
    if not nomes:
        return f"{caminho_relativo} [{linguagem}]: nenhum simbolo de topo encontrado."
    grupos = _componentes(arestas, nomes)
    linhas = [f"{caminho_relativo} [{linguagem}]: {len(nomes)} simbolo(s) de topo, {len(grupos)} componente(s)"]
    for indice, grupo in enumerate(grupos, 1):
        linhas.append(f"\n-- componente {indice} ({len(grupo)} simbolo(s)) --")
        for nome in sorted(grupo):
            inicio, fim = spans[nome]
            usados = ", ".join(sorted(arestas.get(nome, set()) & grupo)) or "-"
            linhas.append(f"  {nome} (l.{inicio}-{fim}, {fim - inicio + 1} linhas) usa: {usados}")
    if len(grupos) > 1:
        linhas.append("\nCada componente acima e candidato a modulo proprio (tool_mover_funcao_verbatim).")
    return "\n".join(linhas)


@register(
    "tool_mapa_dependencias",
    "Mapeia as dependencias internas de um modulo (Python ou JavaScript): por simbolo de topo, quem ele usa dentro do mesmo ficheiro, agrupado em componentes conexas. Use ANTES de dividir um ficheiro grande (god object) para saber exatamente o que move junto.",
    {
        "caminho_relativo": {"tipo": "STRING", "desc": "Arquivo .py, .js ou .mjs (ex: src/backend/ai/loop.py)", "obrig": True, "padrao": ""},
    },
    disponivel="sempre",
)
def tool_mapa_dependencias(caminho_relativo):
    emit_event("executing", function=f"Mapeando dependencias: {caminho_relativo}")
    abs_path, erro = resolver_caminho(caminho_relativo)
    if erro:
        return erro
    if os.path.isdir(abs_path):
        return "ERRO: informe um arquivo (nao uma pasta)."
    extensao = os.path.splitext(abs_path)[1].lower()
    if extensao == ".py":
        spans, arestas, linguagem = _simbolos_py(abs_path)
    elif extensao in (".js", ".mjs"):
        spans, arestas, linguagem = _simbolos_js(abs_path)
    else:
        return "ERRO: extensao nao suportada (use .py, .js ou .mjs)."
    if spans is None:
        return arestas
    return _relatorio(caminho_relativo, linguagem, spans, arestas)
