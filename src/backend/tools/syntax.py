import os
import re
import json
import subprocess

from src.backend.state import emit_event
from src.backend.services.file_service import resolver_caminho

EXTENSOES = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".css": "css",
}

def _detectar_linguagem(caminho, linguagem):
    if linguagem:
        return linguagem.strip().lower()
    ext = os.path.splitext(caminho)[1].lower()
    return EXTENSOES.get(ext, "")

def _ler_texto(abs_path):
    with open(abs_path, "r", encoding="utf-8") as f:
        return f.read()

def _validar_python(conteudo, caminho):
    try:
        compile(conteudo, caminho, "exec")
        return None
    except SyntaxError as e:
        linha = e.lineno or "?"
        coluna = e.offset or "?"
        detalhe = e.text.rstrip() if e.text else ""
        msg = f"linha {linha}, coluna {coluna}: {e.msg}"
        return msg + (f"\n    {detalhe}" if detalhe else "")

def _validar_javascript(abs_path):
    try:
        proc = subprocess.run(
            ["node", "--check", abs_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return "ERRO: 'node' não encontrado no PATH (necessário para validar JavaScript)."
    except subprocess.TimeoutExpired:
        return "ERRO: tempo limite excedido ao validar com node --check."
    if proc.returncode == 0:
        return None
    saida = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return saida or f"node --check falhou (código {proc.returncode})."

def _validar_typescript(abs_path):
    try:
        proc = subprocess.run(
            ["npx", "--no-install", "tsc", "--noEmit", "--pretty", "false", abs_path],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        return "ERRO: 'npx' não encontrado no PATH (necessário para validar TypeScript)."
    except subprocess.TimeoutExpired:
        return "ERRO: tempo limite excedido ao validar com tsc."
    if proc.returncode == 0:
        return None
    saida = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if "could not determine executable to run" in saida or "not found" in saida.lower():
        return "ERRO: TypeScript não instalado no projeto (instale typescript ou valide manualmente)."
    return saida or f"tsc falhou (código {proc.returncode})."

def _validar_json(conteudo):
    try:
        json.loads(conteudo)
        return None
    except json.JSONDecodeError as e:
        return f"linha {e.lineno}, coluna {e.colno}: {e.msg}"

def _parser_css():
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_css
    except ImportError:
        return None, "ERRO: tree-sitter ou tree-sitter-css não instalados (necessários para validar CSS)."
    try:
        return Parser(Language(tree_sitter_css.language())), None
    except Exception as e:
        return None, f"ERRO: falha ao iniciar o parser de CSS (tree-sitter): {e}"

def _coletar_erros_css(raiz, limite=5):
    achados = []
    total = 0
    pilha = [raiz]
    while pilha:
        no = pilha.pop()
        if no.is_error or no.is_missing:
            total += 1
            if len(achados) < limite:
                achados.append(no)
            continue
        if no.has_error:
            pilha.extend(no.children)
    achados.sort(key=lambda n: n.start_point)
    return achados, total

def _validar_css(conteudo):
    parser, erro = _parser_css()
    if erro:
        return erro
    try:
        arvore = parser.parse(conteudo.encode("utf-8"))
    except Exception as e:
        return f"ERRO: falha ao analisar o CSS: {e}"
    raiz = arvore.root_node
    if not raiz.has_error:
        return None
    erros, total = _coletar_erros_css(raiz)
    if not erros:
        return None
    linhas = conteudo.splitlines()
    partes = []
    for no in erros:
        linha = no.start_point[0] + 1
        coluna = no.start_point[1] + 1
        tipo = "faltando" if no.is_missing else "inesperado"
        detalhe = linhas[linha - 1].strip() if 0 < linha <= len(linhas) else ""
        if len(detalhe) > 120:
            detalhe = detalhe[:120] + "..."
        partes.append(f"linha {linha}, coluna {coluna}: token {tipo}" + (f"\n    {detalhe}" if detalhe else ""))
    if total > len(erros):
        partes.append(f"... e mais {total - len(erros)} erro(s) não listado(s).")
    return "\n".join(partes)

def tool_validar_sintaxe(caminho_relativo, linguagem=""):
    emit_event("executing", function=f"Validando sintaxe: {caminho_relativo}")
    if not caminho_relativo:
        return "ERRO: informe 'caminho_relativo'."
    abs_path, erro = resolver_caminho(caminho_relativo)
    if erro:
        return erro
    if not os.path.isfile(abs_path):
        return f"ERRO: arquivo '{caminho_relativo}' não encontrado."
    lang = _detectar_linguagem(caminho_relativo, linguagem)
    if not lang:
        return f"ERRO: extensão não suportada para validação automática. Passe 'linguagem' explícita ou valide manualmente. Extensões suportadas: {', '.join(sorted(EXTENSOES))}."
    if lang == "json":
        try:
            conteudo = _ler_texto(abs_path)
        except OSError as e:
            return f"ERRO ao ler o arquivo: {e}"
        erro_msg = _validar_json(conteudo)
    elif lang == "python":
        try:
            conteudo = _ler_texto(abs_path)
        except OSError as e:
            return f"ERRO ao ler o arquivo: {e}"
        erro_msg = _validar_python(conteudo, caminho_relativo)
    elif lang == "css":
        try:
            conteudo = _ler_texto(abs_path)
        except OSError as e:
            return f"ERRO ao ler o arquivo: {e}"
        erro_msg = _validar_css(conteudo)
    elif lang == "javascript":
        erro_msg = _validar_javascript(abs_path)
    elif lang == "typescript":
        erro_msg = _validar_typescript(abs_path)
    else:
        return f"ERRO: linguagem '{lang}' não suportada para validação."
    if erro_msg:
        return f"ERRO DE SINTAXE em '{caminho_relativo}' ({lang}):\n{erro_msg}"
    return f"SINTAXE OK: '{caminho_relativo}' ({lang})"

def validar_arquivo_apos_edicao(caminho_relativo, caminho_absoluto=None):
    lang = _detectar_linguagem(caminho_relativo, "")
    if lang not in ("python", "javascript", "json", "css"):
        return ""
    if caminho_absoluto is None:
        caminho_absoluto, erro = resolver_caminho(caminho_relativo)
        if erro:
            return ""
    try:
        if lang == "json":
            erro = _validar_json(_ler_texto(caminho_absoluto))
        elif lang == "python":
            erro = _validar_python(_ler_texto(caminho_absoluto), caminho_relativo)
        elif lang == "css":
            erro = _validar_css(_ler_texto(caminho_absoluto))
        else:
            erro = _validar_javascript(caminho_absoluto)
    except OSError:
        return ""
    if erro:
        return f" | AVISO SINTAXE {lang}: {erro}"
    return ""

_RE_FUNCAO_PY = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)
_RE_FUNCAO_JS = re.compile(r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", re.MULTILINE)

def _nomes_de_funcoes(caminho, texto):
    ext = os.path.splitext(caminho)[1].lower()
    if ext in (".py", ".pyw"):
        return set(_RE_FUNCAO_PY.findall(texto))
    if ext in (".js", ".mjs", ".cjs", ".ts", ".tsx"):
        return set(_RE_FUNCAO_JS.findall(texto))
    return set()

def aviso_estrutural_pos_edicao(caminho_relativo, texto_antigo, texto_novo):
    """Checklist automatico anexado ao retorno das ferramentas de edicao.

    Detalha as funcoes criadas/removidas pela edicao para obrigar (por leitura
    direta do retorno da ferramenta) a verificacao de duplicidade antes de criar
    e a verificacao de codigo morto depois de remover. Nao bloqueia a escrita.
    """
    if texto_novo is None:
        return ""
    antigas = _nomes_de_funcoes(caminho_relativo, texto_antigo or "")
    novas = _nomes_de_funcoes(caminho_relativo, texto_novo)
    criadas = sorted(novas - antigas)
    removidas = sorted(antigas - novas)
    partes = []
    if criadas:
        partes.append(
            "FUNCAO(OES) NOVA(S): " + ", ".join(criadas)
            + " -> ANTES de finalizar: tool_buscar_codigo + tool_pesquisar_no_projeto pelo nome/objetivo e tool_analisar_similaridade; se ja existir equivalente, MESCLAR em vez de duplicar."
        )
    if removidas:
        partes.append(
            "FUNCAO(OES) REMOVIDA(S): " + ", ".join(removidas)
            + " -> ANTES de finalizar: tool_pesquisar_no_projeto por cada nome (garantir que nada as chama) e tool_auditar_imports_py/js no arquivo (imports, variaveis e dead code orfaos)."
        )
    if not partes:
        return ""
    return " | CHECKLIST ESTRUTURAL: " + " | ".join(partes)
