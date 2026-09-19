"""Auditor de imports e escopo de modulos Python (AST + symtable)."""

import os
import ast
import symtable
import builtins
from src.backend.tools.registry import register
from src.backend.services.file_service import arquivos_recursivos, caminho_contido, resolver_caminho, raiz_abs
from src.backend.config import APP_ROOT
from src.backend.state import emit_event
PY_EXTRA_GLOBALS = {
    '__name__', '__file__', '__doc__', '__package__', '__spec__', '__loader__',
    '__builtins__', '__debug__', '__dict__', '__class__', '__all__',
    '__annotations__', '__qualname__', '__module__'
}


def _py_arquivos(pasta):
    """Lista recursivamente os .py de uma pasta, ignorando venv/caches/build."""
    return arquivos_recursivos(pasta, ".py")


def _py_ler(caminho):
    """Le e analisa um .py. Devolve (arvore, symtable_mod, erro)."""
    try:
        with open(caminho, "r", encoding="utf-8") as fh:
            src = fh.read()
    except Exception as e:
        return None, None, f"erro de leitura: {e}"
    try:
        arvore = ast.parse(src, caminho)
    except SyntaxError as e:
        return None, None, f"erro de sintaxe na linha {e.lineno}: {e.msg}"
    try:
        return arvore, symtable.symtable(src, caminho, "exec"), None
    except Exception as e:
        return None, None, f"erro ao montar symtable: {e}"


def _py_escopos(st):
    """Achata a arvore de escopos do symtable (modulo, funcoes, classes, comprehensions)."""
    saida = [st]
    for filho in st.get_children():
        saida.extend(_py_escopos(filho))
    return saida


def _py_nomes_carregados(arvore):
    """Nomes lidos (ctx Load) do arquivo. Ignora atribuicoes, que nao sao usos."""
    return {no.id for no in ast.walk(arvore) if isinstance(no, ast.Name) and isinstance(no.ctx, ast.Load)}


def _py_modulos_por_alias(arvore):
    """Nome local -> caminho do modulo que ele carrega, para seguir 'alias.simbolo'."""
    alias = {}
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for al in no.names:
                alias[al.asname or al.name.split(".")[0]] = al.name
        elif isinstance(no, ast.ImportFrom) and no.module and no.module != "__future__":
            for al in no.names:
                if al.name != "*":
                    alias[al.asname or al.name] = f"{no.module}.{al.name}"
    return alias


def _py_atributos_de_modulo(arvore):
    """Pares (modulo, simbolo) acedidos por atributo - e o que um 'import x as M' esconde."""
    alias = _py_modulos_por_alias(arvore)
    usados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Attribute) and isinstance(no.value, ast.Name):
            modulo = alias.get(no.value.id)
            if modulo:
                usados.add((modulo.split(".")[-1], no.attr))
    return usados


def _py_imports(arvore):
    """Nomes introduzidos por import/from-import (descontando __future__ e import *)."""
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for al in no.names:
                nomes.add((al.asname or al.name).split(".")[0])
        elif isinstance(no, ast.ImportFrom) and no.module != "__future__":
            for al in no.names:
                if al.name != "*":
                    nomes.add(al.asname or al.name)
    return nomes


def _py_imports_ignorados(caminho, arvore):
    """Nomes de import que o proprio autor marcou com '# noqa' na mesma instrucao.

    Existe por causa dos imports POR EFEITO DE REGISTO (o bloco do ai/loop.py):
    eles nunca sao referenciados no arquivo, logo cairiam sempre em 'IMPORT NAO
    USADO' - e o aviso 'confirme antes de remover' e fraco de mais quando apagar
    a linha desliga todas as ferramentas do modulo.
    """
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            linhas = f.read().splitlines()
    except OSError:
        return set()
    ignorados = set()
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.Import, ast.ImportFrom)):
            continue
        fim = getattr(no, "end_lineno", no.lineno) or no.lineno
        if "noqa" not in "\n".join(linhas[no.lineno - 1:fim]):
            continue
        for al in no.names:
            if al.name == "*":
                continue
            if isinstance(no, ast.Import):
                ignorados.add((al.asname or al.name).split(".")[0])
            else:
                ignorados.add(al.asname or al.name)
    return ignorados


def _py_tem_star_import(arvore):
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and any(al.name == "*" for al in no.names):
            return True
    return False


def _py_exports(arvore):
    """Nomes declarados em __all__ = [...] (reexports explicitos)."""
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Assign) and any(isinstance(a, ast.Name) and a.id == "__all__" for a in no.targets):
            if isinstance(no.value, (ast.List, ast.Tuple)):
                for el in no.value.elts:
                    if isinstance(el, ast.Constant) and isinstance(el.value, str):
                        nomes.add(el.value)
    return nomes


def _py_definicoes_topo(arvore):
    """Funcoes/classes de topo sem decorador (decoradas sao usadas por registro implicito)."""
    return [no.name for no in arvore.body
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not no.decorator_list]


def _py_nome_modulo(caminho, raiz):
    """Converte caminho absoluto no nome dotted do modulo (relativo a raiz)."""
    try:
        rel = os.path.relpath(caminho, raiz).replace(os.sep, "/")
    except Exception:
        return ""
    if rel.endswith(".py"):
        rel = rel[:-3]
    if rel.endswith("/__init__"):
        rel = rel[:-9]
    return rel.replace("/", ".")


def _py_raiz_varredura(abs_path):
    """Escolhe a raiz para a varredura cross-file: o ancestral mais proximo que seja raiz de projeto."""
    alvo = os.path.abspath(abs_path)
    candidatos = []
    selecionada = raiz_abs()
    if selecionada:
        candidatos.append(os.path.abspath(selecionada))
    candidatos.append(APP_ROOT)
    for cand in candidatos:
        if caminho_contido(alvo, cand):
            return cand
    return os.path.dirname(alvo) if os.path.isfile(alvo) else alvo


@register(
    "tool_auditar_imports_py",
    'Audita modulos Python (AST + symtable, com escopos reais) e classifica: FALTANTE (nome usado como global mas nao importado/definido no modulo -> risco de NameError), IMPORT NAO USADO (candidato a remover, ja descontando reexports e __all__) e DEAD CODE GLOBAL (funcao/classe de topo nunca referenciada no projeto). NAO edita nada, apenas reporta.',
    {
        'caminho_relativo': {"tipo": "STRING", "desc": 'Arquivo .py ou pasta contendo os modulos (ex: src/backend/routes)', "obrig": True, "padrao": ""},
    },
    disponivel="edicao",
)
def tool_auditar_imports_py(caminho_relativo):
    emit_event("executing", function=f"Auditando imports/dead code (Python): {caminho_relativo}")
    abs_path, erro = resolver_caminho(caminho_relativo)
    if erro:
        return erro

    if os.path.isdir(abs_path):
        arquivos = _py_arquivos(abs_path)
        report_only = None
    else:
        arquivos = [abs_path]
        report_only = os.path.basename(abs_path)

    if not arquivos:
        return "Nenhum arquivo .py encontrado."

    raiz = _py_raiz_varredura(abs_path)
    cache = {}
    for caminho in _py_arquivos(raiz):
        arvore, st, _err = _py_ler(caminho)
        cache[caminho] = (arvore, st)

    usados_no_projeto = set()
    usados_por_atributo = set()
    importados_entre_modulos = set()
    for _caminho, (arvore, _st) in cache.items():
        if arvore is None:
            continue
        usados_no_projeto |= _py_nomes_carregados(arvore)
        usados_por_atributo |= _py_atributos_de_modulo(arvore)
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and no.module:
                for al in no.names:
                    importados_entre_modulos.add((no.module, al.asname or al.name))

    builtins_set = set(dir(builtins)) | PY_EXTRA_GLOBALS
    linhas = ["=== AUDITORIA DE IMPORTS E DEAD CODE (PYTHON) ===",
              f"Escopo da varredura: {raiz}",
              f"Analisados {len(arquivos)} arquivo(s).", ""]
    total = 0

    for caminho in arquivos:
        fname = os.path.basename(caminho)
        if report_only and fname != report_only:
            continue

        arvore, st = cache.get(caminho, (None, None))
        if arvore is None or st is None:
            _a, _s, err = _py_ler(caminho)
            linhas.append(f"ARQUIVO: {fname}")
            linhas.append(f"  [NAO ANALISADO] {err}")
            linhas.append("")
            total += 1
            continue

        modulo_names = set(st.get_identifiers())
        carregados_aqui = _py_nomes_carregados(arvore)
        exports = _py_exports(arvore)
        dotted = _py_nome_modulo(caminho, raiz)

        faltantes = set()
        if not _py_tem_star_import(arvore):
            for escopo in _py_escopos(st):
                for simb in escopo.get_symbols():
                    nome = simb.get_name()
                    if not simb.is_global():
                        continue
                    if nome in modulo_names or nome in builtins_set:
                        continue
                    faltantes.add(nome)

        candidatos = set()
        for nome in _py_imports(arvore):
            if nome in carregados_aqui or nome in exports:
                continue
            if (dotted, nome) in importados_entre_modulos:
                continue
            candidatos.add(nome)
        respeitados = candidatos & _py_imports_ignorados(caminho, arvore)
        nao_usados = candidatos - respeitados

        chave_do_modulo = os.path.splitext(fname)[0]
        deads = set()
        for nome in _py_definicoes_topo(arvore):
            if nome in usados_no_projeto or nome in exports:
                continue
            if (chave_do_modulo, nome) in usados_por_atributo:
                continue
            deads.add(nome)

        blocos = []
        if respeitados:
            blocos.append(f"  [{len(respeitados)} import(s) com '# noqa' - respeitado(s) de proposito]")
        if faltantes:
            blocos.append("  [FALTANTE (usado mas nao importado -> risco de NameError)]")
            blocos.extend(f"    - {n} -> usado como global, mas nao importado/definido neste modulo" for n in sorted(faltantes))
        if nao_usados:
            blocos.append("  [IMPORT NAO USADO (confirmar antes de remover)]")
            blocos.extend(f"    - {n} -> importado e nunca referenciado no arquivo" for n in sorted(nao_usados))
        if deads:
            blocos.append("  [DEAD CODE GLOBAL (candidatos a apagar)]")
            blocos.extend(f"    - {n}() -> definido no topo e nunca referenciado no projeto" for n in sorted(deads))

        if blocos:
            linhas.append(f"ARQUIVO: {fname}")
            linhas.extend(blocos)
            linhas.append("")
            total += len(faltantes) + len(nao_usados) + len(deads)

    if total == 0:
        linhas.append("Nenhum import faltante, import nao usado ou dead code de topo encontrado.")
    else:
        linhas.append(f"Total de itens sinalizados: {total}")
        linhas.append("IMPORTANTE: relatorio apenas informativo. Nada foi editado. Revise antes de remover/mover.")
    linhas.append("")
    linhas.append("NOTA: FALTANTE e o achado mais grave (NameError real em runtime) e tem baixo falso")
    linhas.append("positivo, pois usa AST + symtable (escopos reais). IMPORT NAO USADO ja desconta reexports,")
    linhas.append("__all__ e o que o autor marcou com '# noqa' (imports por efeito de registo, que so")
    linhas.append("existem para registar ferramentas); o resto, confirme antes de remover. DEAD CODE ignora")
    linhas.append("funcoes decoradas (usadas via registro/decorador), logo so apanha o que e mesmo orfao.")
    return "\n".join(linhas)
