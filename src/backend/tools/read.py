"""Leitura e inspecao de codigo: mapa, ficheiro, trecho, assinaturas e clangd.

Verbatim de tools/filesystem.py; importa-lo e o que regista as suas 5 tools de
leitura e de inspecao (mapa, ficheiro, trecho, assinaturas, clangd).
"""
import os
import re
import ast
import subprocess

from src.backend.state import emit_event
from src.backend.tools import cpp
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
            elif cpp.eh_cpp(caminho_relativo):
                mapa = cpp.mapa(caminho_absoluto).splitlines()
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


def _intervalos_pedidos(texto, total):
    intervalos = []
    for pedaco in re.split(r"[;,]", texto or ""):
        pedaco = pedaco.strip()
        if not pedaco:
            continue
        partes = re.split(r"\s*[-:]\s*", pedaco, 1)
        try:
            inicio = int(partes[0])
            fim = int(partes[1]) if len(partes) > 1 else inicio
        except ValueError:
            return [], f"ERRO: intervalo invalido em 'trechos': {pedaco}"
        if inicio < 1 or inicio > total:
            return [], f"ERRO: intervalo fora do ficheiro (tem {total} linhas): {pedaco}"
        intervalos.append((inicio, min(total, max(inicio, fim))))
    return intervalos, ""


_PADROES_DE_DEFINICAO = {
    ".py": r"^\s*(?:async\s+)?(?:def|class)\s+\w+",
    ".pyi": r"^\s*(?:async\s+)?(?:def|class)\s+\w+",
    ".rs": r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:fn|struct|enum|trait|impl|mod)\s+\w+",
    ".js": r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class)\s+\w+|^\s*(?:export\s+)?const\s+\w+\s*=\s*(?:async\s*)?\(",
    ".php": r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|abstract\s+|final\s+)*function\s+\w+",
    ".lua": r"^\s*(?:local\s+)?function\s+[\w.:]+",
    ".c": r"^\s*(?:template\s*<[^>]*>\s*)?(?:class|struct|namespace)\s+\w+|^[A-Za-z_][\w:<>,*&\s]*\s+\w+\s*\([^;]*\)\s*(?:const\s*)?\{?\s*$",
}
for _extra in (".jsx", ".mjs", ".cjs", ".ts", ".tsx"):
    _PADROES_DE_DEFINICAO[_extra] = _PADROES_DE_DEFINICAO[".js"]
for _extra in (".cc", ".cxx", ".cpp", ".h", ".hh", ".hpp", ".hxx", ".ino"):
    _PADROES_DE_DEFINICAO[_extra] = _PADROES_DE_DEFINICAO[".c"]

_PALAVRAS_DE_CONTROLE = frozenset(
    {"if", "for", "while", "switch", "catch", "else", "return", "match", "loop", "do"}
)


def _definicao_acima(caminho, linhas, inicio):
    """A definicao mais proxima acima do trecho, so para orientar quem le (nunca decide nada)."""
    achado = re.search(r"(\.[A-Za-z0-9_]+)$", caminho.split(" [")[0])
    padrao = _PADROES_DE_DEFINICAO.get(achado.group(1).lower() if achado else "")
    if not padrao:
        return ""
    for indice in range(inicio - 2, max(-1, inicio - 402), -1):
        linha = linhas[indice]
        if not re.search(padrao, linha):
            continue
        primeira = re.match(r"\s*(?:pub\s+)?(?:async\s+)?(\w+)", linha)
        if primeira and primeira.group(1) in _PALAVRAS_DE_CONTROLE:
            continue
        return f" · dentro de: {linha.strip()[:90]} (linha {indice + 1})"
    return ""


def _ler_varios_trechos(caminho_relativo, linhas, trechos):
    intervalos, erro = _intervalos_pedidos(trechos, len(linhas))
    if erro:
        return erro
    if not intervalos:
        return "ERRO: nenhum intervalo utilizavel em 'trechos'."
    blocos = []
    for inicio, fim in intervalos:
        onde = _definicao_acima(caminho_relativo, linhas, inicio)
        blocos.append(f"--- Trecho de {caminho_relativo} (Linhas {inicio} a {fim}){onde} ---\n" + "".join(linhas[inicio - 1:fim]))
    return "\n\n".join(blocos)


@register(
    "tool_ler_trecho_arquivo",
    'Lê linhas específicas de um arquivo. Aceita VARIOS intervalos numa so chamada no campo trechos (ex: "12-60;210-320;1180-1240"): o ficheiro e lido uma vez e cada intervalo sai com o seu cabecalho - use-o em vez de repetir a chamada por bloco. Cada cabecalho diz tambem a definicao mais proxima acima do trecho ("dentro de: ..."), para nao confundir a funcao onde o trecho vive com a que vem antes dele. Passa o parametro revisao (ex: HEAD) para ler a versao do git em vez do disco.',
    {
        'caminho_relativo': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'linha_inicio': {"tipo": "INTEGER", "padrao": 1},
        'linha_fim': {"tipo": "INTEGER", "padrao": lambda a: int(a.get("linha_inicio", 1)) + 400},
        'revisao': {"tipo": "STRING", "padrao": ""},
        'trechos': {"tipo": "STRING", "padrao": ""},
    },
)
def tool_ler_trecho_arquivo(caminho_relativo: str, linha_inicio: int = 1, linha_fim: int = 0, revisao: str = "", trechos: str = ""):
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
    if trechos:
        return _ler_varios_trechos(caminho_relativo, linhas, trechos)
    if not linha_fim: linha_fim = linha_inicio + 400
    inicio = max(0, linha_inicio - 1)
    fim = min(len(linhas), linha_fim)
    if inicio >= fim: return "ERRO: Intervalo inválido."
    trecho = "".join(linhas[inicio:fim])
    onde = _definicao_acima(caminho_relativo, linhas, linha_inicio)
    return f"--- Trecho de {caminho_relativo} (Linhas {linha_inicio} a {linha_fim}){onde} ---\n{trecho}"


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
