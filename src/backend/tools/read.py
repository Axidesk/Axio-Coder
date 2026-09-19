"""Leitura e inspecao de codigo: mapa, ficheiro, trecho, assinaturas e clangd.

Verbatim de tools/filesystem.py; importa-lo e o que regista as suas 5 tools de
leitura e de inspecao (mapa, ficheiro, trecho, assinaturas, clangd).
"""
import os
import re
import ast
import subprocess

from src.backend.state import emit_event
from src.backend.tools.registry import register
from src.backend.services.file_service import resolver_caminho, conteudo_de_revisao


def _mapear_javascript(linhas):
    mapa = []
    for i, linha in enumerate(linhas):
        s = linha.strip()
        if re.match(r'^(?:async\s+)?function\s+[A-Za-z_$][\w$]*\s*\(', s):
            mapa.append(f"Linha {i+1}: {s}")
        elif re.match(r'^(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>', s):
            mapa.append(f"Linha {i+1}: {s}")
        elif re.match(r'^(?:async\s+)?[A-Za-z_$][\w$]*\s*\([^)]*\)\s*\{', s):
            nome = s.split('(')[0].strip().split()[-1]
            if nome not in ('if', 'for', 'while', 'switch', 'catch', 'return', 'typeof', 'delete', 'new'):
                mapa.append(f"Linha {i+1}: {s}")
    return mapa


def _resumo_python(arvore, conteudo):
    """Diz quanto de um modulo Python e codigo e quanto e dado.

    Um ficheiro de 2000 linhas pode ter 900 de logica e 1100 de uma unica string:
    so o numero de linhas nao distingue um god object de um ficheiro com dados
    dentro (foi o caso de tools/process.py, com 1151 linhas em constantes de texto
    e 902 de logica). Conta as linhas ocupadas por literais de string atribuidos a
    um nome de topo e da-as como dado; o resto e codigo.
    """
    total = len(conteudo.splitlines())
    dado = 0
    chars = 0
    quantas = 0
    for no in arvore.body:
        if isinstance(no, (ast.Assign, ast.AnnAssign)):
            valor = no.value
            if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
                dado += no.end_lineno - no.lineno + 1
                chars += len(valor.value)
                quantas += 1
    defs = sum(1 for no in arvore.body
               if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
    base = f"{total} linhas | {defs} definicao(oes) de topo"
    if not dado:
        return base
    return (f"{base} | {dado} linhas ({100 * dado // total}%) em {quantas} constante(s) "
            f"de texto de {chars} chars - o resto ({total - dado}) e codigo")


@register(
    "tool_mapear_codigo",
    'Lista as funções e classes de um arquivo para você saber onde alterar.',
    {
        'caminho_relativo': {"tipo": "STRING", "obrig": True, "padrao": ""},
    },
)
def tool_mapear_codigo(caminho_relativo: str):
    emit_event("executing", function=f"Mapeando: {caminho_relativo}")
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro_caminho: return erro_caminho
    if not os.path.exists(caminho_absoluto): return f"ERRO: Arquivo não encontrado."
    try:
        mapa = []
        if caminho_relativo.endswith('.py'):
            with open(caminho_absoluto, 'r', encoding='utf-8', errors='ignore') as f:
                conteudo = f.read()
            try:
                arvore = ast.parse(conteudo)
                itens = []
                for no in ast.walk(arvore):
                    if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        tipo = "Classe" if isinstance(no, ast.ClassDef) else "Função"
                        tamanho = no.end_lineno - no.lineno + 1
                        itens.append((no.lineno,
                                      f"Linha {no.lineno}-{no.end_lineno} ({tamanho}l): {tipo} {no.name}"))
                itens.sort(key=lambda par: par[0])
                mapa = [f"[{_resumo_python(arvore, conteudo)}]"] + [texto for _, texto in itens]
            except SyntaxError:
                mapa.append("ERRO: Falha ao fazer parse do AST (erro de sintaxe no Python).")
        else:
            with open(caminho_absoluto, 'r', encoding='utf-8', errors='ignore') as f:
                linhas = f.readlines()
            if caminho_relativo.endswith(('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs')):
                mapa = _mapear_javascript(linhas)
            else:
                regex_cpp = r"^\s*(?:(?:inline|static|virtual|explicit|constexpr)\s+)*(?:[\w<>:]+\s+)*(?:[\w<>:]+::)?~?\w+\s*\([^)]*\)\s*(?:const|override|final|noexcept)*\s*\{?"
                for i, linha in enumerate(linhas):
                    if re.search(regex_cpp, linha) and not re.match(r"^\s*(if|for|while|switch|catch)\b", linha):
                        mapa.append(f"Linha {i+1}: {linha.strip()}")
        return "\n".join(mapa) if mapa else "Nenhuma função identificada no formato padrão."
    except Exception as e: return f"ERRO: {str(e)}"


def _resolver_arquivo_existente(caminho_relativo):
    """Resolve o caminho e garante que o arquivo existe. Devolve (absoluto, erro_texto)."""
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro_caminho:
        return None, erro_caminho
    if not os.path.exists(caminho_absoluto):
        return None, f"ERRO: O arquivo '{caminho_relativo}' não existe."
    return caminho_absoluto, None


@register(
    "tool_ler_arquivo",
    "Lê o conteúdo completo. USE APENAS para arquivos pequenos (até ~600 linhas ou ~25k caracteres). Para arquivos grandes como .cpp, use obrigatoriamente 'tool_mapear_codigo' primeiro e depois 'tool_ler_trecho_arquivo'.",
    {
        'caminho_relativo': {"tipo": "STRING", "obrig": True, "padrao": ""},
    },
)
def tool_ler_arquivo(caminho_relativo: str):
    emit_event("executing", function=f"Lendo arquivo: {caminho_relativo}")
    caminho_absoluto, erro_caminho = _resolver_arquivo_existente(caminho_relativo)
    if erro_caminho: return erro_caminho
    try:
        with open(caminho_absoluto, 'r', encoding='utf-8', errors='ignore') as f:
            conteudo = f.read()
            num_linhas = conteudo.count("\n") + 1
            if len(conteudo) > 25000 or num_linhas > 600: return f"ERRO: Arquivo muito grande ({len(conteudo)} caracteres, {num_linhas} linhas). Use 'tool_mapear_codigo' e depois 'tool_ler_trecho_arquivo' para ler blocos específicos."
            return conteudo
    except Exception as e: return f"ERRO: {str(e)}"


@register(
    "tool_ler_trecho_arquivo",
    'Lê linhas específicas de um arquivo. Passa o parametro revisao (ex: HEAD) para ler a versao do git em vez do disco.',
    {
        'caminho_relativo': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'linha_inicio': {"tipo": "INTEGER", "obrig": True, "padrao": 1},
        'linha_fim': {"tipo": "INTEGER", "obrig": True, "padrao": lambda a: int(a.get("linha_inicio", 1)) + 400},
        'revisao': {"tipo": "STRING", "padrao": ""},
    },
)
def tool_ler_trecho_arquivo(caminho_relativo: str, linha_inicio: int, linha_fim: int, revisao: str = ""):
    emit_event("executing", function=f"Lendo trecho: {caminho_relativo}")
    if revisao:
        conteudo, erro = conteudo_de_revisao(caminho_relativo, revisao)
        if erro: return erro
        caminho_relativo = f"{caminho_relativo} [{revisao}]"
        linhas = conteudo.splitlines(keepends=True)
    else:
        caminho_absoluto, erro_caminho = _resolver_arquivo_existente(caminho_relativo)
        if erro_caminho: return erro_caminho
        try:
            with open(caminho_absoluto, 'r', encoding='utf-8', errors='ignore') as f:
                linhas = f.readlines()
        except Exception as e: return f"ERRO: {str(e)}"
    inicio = max(0, linha_inicio - 1)
    fim = min(len(linhas), linha_fim)
    if inicio >= fim: return "ERRO: Intervalo inválido."
    trecho = "".join(linhas[inicio:fim])
    return f"--- Trecho de {caminho_relativo} (Linhas {linha_inicio} a {linha_fim}) ---\\n{trecho}"


@register(
    "tool_ler_assinaturas",
    'Lê apenas as assinaturas de funções de um arquivo grande.',
    {
        'caminho_relativo': {"tipo": "STRING", "obrig": True, "padrao": ""},
    },
)
def tool_ler_assinaturas(caminho_relativo: str):
    emit_event("executing", function=f"Lendo assinaturas: {caminho_relativo}")
    caminho_absoluto, erro_caminho = _resolver_arquivo_existente(caminho_relativo)
    if erro_caminho: return erro_caminho
    try:
        with open(caminho_absoluto, 'r', encoding='utf-8', errors='ignore') as f:
            linhas = f.readlines()
    except Exception as e:
        return f"ERRO: {str(e)}"
    if caminho_relativo.endswith(('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs')):
        resultado = _mapear_javascript(linhas)
        return "\n".join(resultado) if resultado else "Nenhuma assinatura clara encontrada."
    resultado = []
    padrao = r"^\s*(?:(?:inline|static|virtual|explicit|constexpr)\s+)*(?:[\w<>:]+\s+)*(?:[\w<>:]+::)?~?\w+\s*\([^)]*\)\s*(?:const|override|final|noexcept)*"
    for i, linha in enumerate(linhas):
        if re.search(padrao, linha) and not re.match(r"^\s*(if|for|while|switch|catch)\b", linha):
            resultado.append(f"Linha {i+1}: {linha.strip()};")
        elif "class " in linha or "struct " in linha:
            resultado.append(f"Linha {i+1}: {linha.strip()}")
    return "\n".join(resultado) if resultado else "Nenhuma assinatura clara encontrada."


@register(
    "tool_analisar_simbolo",
    'Usa o clangd para verificar erros de sintaxe após você fazer uma edição.',
    {
        'caminho_relativo': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'termo': {"tipo": "STRING", "obrig": True, "padrao": ""},
    },
)
def tool_analisar_simbolo(caminho_relativo: str, termo: str):
    emit_event("executing", function=f"Analisando símbolo: {termo} em {caminho_relativo}")
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro_caminho: return erro_caminho
    try:
        resultado_clang = subprocess.run(f"clangd --check={caminho_absoluto}", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
        saida = resultado_clang.stderr
        erros = [l for l in saida.splitlines() if "error:" in l]
        aviso_erro = "\\n".join(erros[:5]) if erros else "Nenhum erro de sintaxe detectado."
        return f"Análise Semântica de '{termo}':\\n{aviso_erro}\\n\\nUse 'tool_pesquisar_no_projeto' para localizar referências cruzadas."
    except Exception:
        return f"Clangd não respondeu. Use tool_pesquisar_no_projeto para busca textual de '{termo}'."
