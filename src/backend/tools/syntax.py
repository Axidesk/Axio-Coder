import os
import re
import sys
import ast
import json
import subprocess

from html.parser import HTMLParser

from src.backend.state import emit_event
from src.backend.tools import cpp
from src.backend.tools.js_lexico import contar_simbolo, limpar
from src.backend.tools.registry import register
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
    ".html": "html",
    ".htm": "html",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c++": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".ipp": "cpp",
    ".tpp": "cpp",
    ".h": "cpp",
    ".c": "cpp",
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
        conteudo = _ler_texto(abs_path)
    except OSError as e:
        return f"ERRO ao ler o arquivo: {e}"
    modulo = _tem_sintaxe_de_modulo(conteudo)
    if modulo:
        comando = ["node", "--input-type=module", "--check"]
        entrada = conteudo
    else:
        comando = ["node", "--check", abs_path]
        entrada = None
    try:
        proc = subprocess.run(
            comando,
            input=entrada,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except FileNotFoundError:
        return "ERRO: 'node' não encontrado no PATH (necessário para validar JavaScript)."
    except subprocess.TimeoutExpired:
        return "ERRO: tempo limite excedido ao validar com node --check."
    if proc.returncode == 0:
        return None
    saida = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if modulo:
        saida = saida.replace("[stdin]", "(modulo)")
    return saida or f"node --check falhou (código {proc.returncode})."

def _tem_sintaxe_de_modulo(conteudo):
    return re.search(r"^\s*(import|export)\b", conteudo, re.M) is not None

def _validar_typescript(conteudo, abs_path):
    parser, erro = _parser_typescript(abs_path)
    if erro:
        return erro
    return _validar_com_tree_sitter(conteudo, parser)

def _validar_cpp(caminho_abs):
    return cpp.erros_de_sintaxe(caminho_abs)


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

def _parser_typescript(abs_path):
    """Parser de TypeScript/TSX via tree-sitter.

    Substitui o antigo 'npx tsc': no Windows, subprocess com LISTA nao aplica o
    PATHEXT, logo "npx" nunca casava com o npx.cmd real e a validacao de
    TypeScript falhava sempre. tree-sitter ja e dependencia do projeto, corre
    offline e responde a pergunta certa desta ferramenta - SINTAXE, nao tipos.
    """
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_typescript
    except ImportError:
        return None, "ERRO: tree-sitter ou tree-sitter-typescript não instalados (necessários para validar TypeScript)."
    try:
        fabrica = tree_sitter_typescript.language_tsx if abs_path.lower().endswith(".tsx") else tree_sitter_typescript.language_typescript
        return Parser(Language(fabrica())), None
    except Exception as e:
        return None, f"ERRO: falha ao iniciar o parser de TypeScript (tree-sitter): {e}"

def _parser_html():
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_html
    except ImportError:
        return None, "ERRO: tree-sitter ou tree-sitter-html nao instalados (necessarios para validar HTML)."
    try:
        return Parser(Language(tree_sitter_html.language())), None
    except Exception as e:
        return None, f"ERRO: falha ao iniciar o parser de HTML (tree-sitter): {e}"

def _coletar_erros(raiz, limite=5):
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

def _erros_como_texto(erros, total, conteudo):
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

def _validar_com_tree_sitter(conteudo, parser):
    try:
        arvore = parser.parse(conteudo.encode("utf-8"))
    except Exception as e:
        return f"ERRO: falha ao analisar o codigo: {e}"
    raiz = arvore.root_node
    if not raiz.has_error:
        return None
    erros, total = _coletar_erros(raiz)
    if not erros:
        return None
    return _erros_como_texto(erros, total, conteudo)

def _validar_css(conteudo):
    parser, erro = _parser_css()
    if erro:
        return erro
    return _validar_com_tree_sitter(conteudo, parser)

TAGS_VAZIAS_HTML = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
    "source", "track", "wbr", "path", "circle", "rect", "line", "polyline", "polygon",
    "ellipse", "stop", "use", "animate",
}

class _BalancoHtml(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pilha = []
        self.ids = {}
        self.erros = []

    def handle_starttag(self, tag, attrs):
        ident = dict(attrs).get("id")
        if ident:
            anterior = self.ids.get(ident)
            if anterior:
                self.erros.append(f'linha {self.getpos()[0]}: id "{ident}" repetido (ja usado na linha {anterior})')
            else:
                self.ids[ident] = self.getpos()[0]
        if tag in TAGS_VAZIAS_HTML:
            return
        self.pilha.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in TAGS_VAZIAS_HTML:
            return
        if self.pilha and self.pilha[-1][0] == tag:
            self.pilha.pop()
            return
        for i in range(len(self.pilha) - 1, -1, -1):
            if self.pilha[i][0] == tag:
                if i + 1 < len(self.pilha):
                    fora = self.pilha[i + 1]
                    self.erros.append(f'linha {self.getpos()[0]}: </{tag}> fecha antes de </{fora[0]}> (aberto na linha {fora[1]})')
                del self.pilha[i:]
                return
        self.erros.append(f"linha {self.getpos()[0]}: </{tag}> sem abertura correspondente")

def _erros_de_estrutura_html(conteudo):
    balanco = _BalancoHtml()
    balanco.feed(conteudo)
    balanco.close()
    erros = list(balanco.erros)
    if balanco.pilha:
        tag, linha = balanco.pilha[-1]
        erros.append(f"linha {linha}: <{tag}> ficou por fechar")
    return erros

def _erros_finos_html(conteudo):
    parser, erro = _parser_html()
    if erro:
        return []
    try:
        arvore = parser.parse(conteudo.encode("utf-8"))
    except Exception:
        return []
    raiz = arvore.root_node
    if not raiz.has_error:
        return []
    erros, _ = _coletar_erros(raiz)
    erros = [no for no in erros if no.text.strip() != b">"]
    if not erros:
        return []
    return _erros_como_texto(erros, len(erros), conteudo).splitlines()

def _validar_html(conteudo):
    erros = _erros_de_estrutura_html(conteudo) + _erros_finos_html(conteudo)
    if not erros:
        return None
    if len(erros) > 8:
        return "\n".join(erros[:8]) + f"\n... e mais {len(erros) - 8} erro(s) nao listado(s)."
    return "\n".join(erros)

@register(
    "tool_validar_sintaxe",
    'Valida a sintaxe de um arquivo (Python, JavaScript, TypeScript, C/C++, JSON, CSS ou HTML) após editar/mover código. Use SEMPRE após edições para confirmar que não quebrou sintaxe — NÃO use comandos proibidos (python, py_compile, node --check, grep, sed, cat, echo) para isso. No HTML confere o balanceamento das tags, os ids repetidos e os tokens mal formados. Em C/C++ a leitura e pela arvore (tree-sitter): palavras que so o pre-processador conhece (Q_OBJECT, signals:, emit) nao contam como erro. Retorna OK ou o erro com linha/coluna.',
    {
        'caminho_relativo': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'linguagem': {"tipo": "STRING", "enum": ['python', 'javascript', 'typescript', 'cpp', 'json', 'css', 'html'], "padrao": ""},
    },
)
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
    elif lang == "html":
        try:
            conteudo = _ler_texto(abs_path)
        except OSError as e:
            return f"ERRO ao ler o arquivo: {e}"
        erro_msg = _validar_html(conteudo)
    elif lang == "javascript":
        erro_msg = _validar_javascript(abs_path)
    elif lang == "typescript":
        try:
            conteudo = _ler_texto(abs_path)
        except OSError as e:
            return f"ERRO ao ler o arquivo: {e}"
        erro_msg = _validar_typescript(conteudo, abs_path)
    elif lang == "cpp":
        erro_msg = _validar_cpp(abs_path)
    else:
        return f"ERRO: linguagem '{lang}' não suportada para validação."
    if erro_msg:
        return f"ERRO DE SINTAXE em '{caminho_relativo}' ({lang}):\n{erro_msg}"
    return f"SINTAXE OK: '{caminho_relativo}' ({lang})"

def validar_texto(caminho_relativo, conteudo):
    """Valida a sintaxe de um conteudo EM MEMORIA, sem gravar nada.

    Cobre python, css, json e html - as linguagens cujo validador nao depende de
    um interpretador externo. Devolve a mensagem de erro ou None (ok / nao
    aplicavel). JS e TS devolvem None: nao sao validaveis em memoria, logo quem
    edita deve validar DEPOIS de gravar com
    `validar_arquivo_apos_edicao` e reverter se houver erro.
    """
    lang = _detectar_linguagem(caminho_relativo, "")
    try:
        if lang == "python":
            return _validar_python(conteudo, caminho_relativo)
        if lang == "css":
            return _validar_css(conteudo)
        if lang == "json":
            return _validar_json(conteudo)
        if lang == "html":
            return _validar_html(conteudo)
        if lang == "cpp":
            return cpp.erros_de_texto(conteudo, caminho_relativo)
    except Exception as e:
        return f"falha ao validar: {e}"
    return None

def validar_arquivo_apos_edicao(caminho_relativo, caminho_absoluto=None):
    lang = _detectar_linguagem(caminho_relativo, "")
    if lang not in ("python", "javascript", "json", "css", "html", "cpp"):
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
        elif lang == "html":
            erro = _validar_html(_ler_texto(caminho_absoluto))
        elif lang == "cpp":
            erro = _validar_cpp(caminho_absoluto)
        else:
            erro = _validar_javascript(caminho_absoluto)
    except OSError:
        return ""
    if erro:
        return f" | AVISO SINTAXE {lang}: {erro}"
    return ""

_RE_FUNCAO_PY = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)
_RE_FUNCAO_JS = re.compile(r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", re.MULTILINE)
_TOKENS_DO_NOME = re.compile(r"[A-Za-z0-9]+")

def _funcoes_py(texto):
    """Funcoes Python com a linha onde comecam, lidas pela AST, nao por regex.

    A regex encontrava 'def' escrito dentro de docstrings e de strings que geram
    codigo (ex: o script embutido de tools/rotas.py) e anunciava funcoes novas que
    nao existem - o mesmo motivo que levou _imports_locais a usar a AST. Se o texto
    estiver com sintaxe invalida (edicao a meio), cai na regex para nao perder o aviso.
    A LINHA faz falta a regra 7: para dizer "poe a funcao abaixo desta" e preciso saber
    onde esta esta.
    """
    if not texto:
        return []
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return [(nome, 0) for nome in _RE_FUNCAO_PY.findall(texto)]
    return [(no.name, no.lineno) for no in ast.walk(arvore)
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))]

def _funcoes_com_linha(caminho, texto):
    """[(nome, linha)] das funcoes declaradas no texto, por tipo de ficheiro."""
    ext = os.path.splitext(caminho)[1].lower()
    if ext in (".py", ".pyw"):
        return sorted(_funcoes_py(texto), key=lambda par: par[1])
    if ext in (".js", ".mjs", ".cjs", ".ts", ".tsx"):
        return [(nome, numero)
                for numero, linha in enumerate((texto or "").splitlines(), start=1)
                for nome in _RE_FUNCAO_JS.findall(linha)]
    return []

def _tokens_do_nome(nome):
    """Palavras de um nome: 'achar_linha_identificador' -> {achar, linha, identificador}."""
    partes = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(nome or ""))
    return {pedaco.lower() for pedaco in _TOKENS_DO_NOME.findall(partes) if len(pedaco) >= 3}

def _aviso_de_posicao(criadas, antes, depois):
    """Onde a funcao nova deve ficar: abaixo da correlacionada, nunca no fim por habito.

    A regra 7 ("posicione a funcao nova abaixo da ultima funcao correlacionada do
    ficheiro") deixa de ser uma instrucao generica e passa a trazer o NOME e a LINHA da
    vizinha, lidos do proprio texto editado. Fala so quando ha mesmo o que corrigir -
    uma funcao colocada ACIMA de todas as suas correlacionadas, ou atirada para o fim
    com outras funcoes pelo meio - e fica calada quando ela ja ficou logo abaixo da que
    lhe pertence, para o aviso nao virar ruido que se aprende a ignorar.
    """
    linhas = {}
    for nome, linha in depois:
        linhas[nome] = max(linhas.get(nome, 0), linha)
    if not linhas:
        return ""
    anteriores = {nome for nome, _ in antes}
    ultima = max(linhas.values())
    partes = []
    for nome in criadas:
        minha = linhas.get(nome)
        if minha is None:
            continue
        meus = _tokens_do_nome(nome)
        parentes = [(outro, linha) for outro, linha in linhas.items()
                    if outro != nome and outro in anteriores and _tokens_do_nome(outro) & meus]
        if not parentes:
            continue
        vizinha, linha_vizinha = min(parentes, key=lambda par: (abs(par[1] - minha), par[1]))
        if minha < linha_vizinha:
            partes.append(
                f"'{nome}' ficou ACIMA de '{vizinha}' (linha {linha_vizinha}), que e correlacionada"
                f" -> move-a para ABAIXO dela, nao a deixes fora do grupo das semelhantes"
            )
        elif minha == ultima and any(linha_vizinha < linha < minha for outro, linha in linhas.items() if outro != nome):
            partes.append(
                f"'{nome}' ficou no FIM do ficheiro, longe de '{vizinha}' (linha {linha_vizinha}),"
                f" que e correlacionada -> coloca-a logo ABAIXO de '{vizinha}' (regra 7),"
                f" nao no fim do ficheiro nem em qualquer lugar"
            )
    if not partes:
        return ""
    return "POSICAO DA FUNCAO NOVA: " + " | ".join(partes)

_RE_IMPORT_JS = re.compile(r"import\s*\{([^}]*)\}", re.MULTILINE)
_RE_IMPORT_JS_NOME = re.compile(r"^\s*import\s+([A-Za-z_$][\w$]*)\s*(?:,|from\s)", re.MULTILINE)
_RE_IMPORT_JS_NAMESPACE = re.compile(r"import\s*\*\s*as\s+([A-Za-z_$][\w$]*)")
_RE_IMPORT_PY = re.compile(r"^\s*from\s+[\w.]+\s+import\s+(?:\(([^)]*)\)|([^\n#]+))", re.MULTILINE)

def _nomes_importados(texto, caminho_relativo):
    """Nomes que o modulo trouxe para dentro de si por import (JS/TS e Python)."""
    ext = os.path.splitext(caminho_relativo or "")[1].lower()
    if ext in (".js", ".mjs", ".cjs", ".ts", ".tsx"):
        blocos = [m.group(1) for m in _RE_IMPORT_JS.finditer(texto or "")]
    elif ext in (".py", ".pyw"):
        blocos = [(m.group(1) if m.group(1) is not None else m.group(2))
                  for m in _RE_IMPORT_PY.finditer(texto or "")]
    else:
        return set()
    nomes = set()
    for bloco in blocos:
        for item in bloco.replace("\\", " ").split(","):
            item = item.split("#")[0].strip()
            if not item or item.startswith("*"):
                continue
            nomes.add(item.split(" as ")[-1].strip())
    if ext in (".js", ".mjs", ".cjs", ".ts", ".tsx"):
        nomes.update(m.group(1) for m in _RE_IMPORT_JS_NOME.finditer(texto or ""))
        nomes.update(m.group(1) for m in _RE_IMPORT_JS_NAMESPACE.finditer(texto or ""))
    return {n for n in nomes if n}

def _aviso_referencias_orfas(caminho_relativo, texto_antigo, texto_novo):
    """Nome que saiu do import nesta edicao e continua a ser usado: quebra em execucao.

    O caso real (renderer.js, lixeira do historico): a edicao tirou
    'confirmDeletePopup' do import e deixou o uso na linha seguinte. A auditoria de
    imports nao ve (js_auditoria.py:_faltantes so olha para 'nome(' e so acusa quando o
    simbolo ainda e exportado por alguem) e o lint so acusa quem o correr depois. Aqui
    os dois textos da edicao ja estao em maos: o caso e apanhado quando nasce.
    """
    if not texto_novo:
        return ""
    saiu = _nomes_importados(texto_antigo, caminho_relativo) - _nomes_importados(texto_novo, caminho_relativo)
    if not saiu:
        return ""
    ext = os.path.splitext(caminho_relativo or "")[1].lower()
    limpo = limpar(texto_novo) if ext in (".js", ".mjs", ".cjs", ".ts", ".tsx") else texto_novo
    orfaos = []
    for nome in sorted(saiu):
        if not re.fullmatch(r"[A-Za-z_$][\w$]*", nome):
            continue
        if re.search(r"\b(?:function|class|const|let|var)\s+" + re.escape(nome) + r"\b", limpo):
            continue
        usos = contar_simbolo(nome, limpo)
        if usos:
            orfaos.append(f"{nome} ({usos}x)")
    if not orfaos:
        return ""
    return ("REFERENCIA ORFA: " + ", ".join(orfaos)
            + " saiu do import nesta edicao e continua a ser usado -> quebra em execucao;"
              " corrige o uso ou repoe o import antes de finalizar.")

def _decoradores_de_registo(texto):
    """[(nome declarado no @register, nome da funcao decorada, linha)] do topo do modulo."""
    if not texto:
        return []
    try:
        arvore = ast.parse(texto)
    except (SyntaxError, ValueError):
        return []
    achados = []
    for no in arvore.body:
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for decorador in no.decorator_list:
            if not isinstance(decorador, ast.Call) or not decorador.args:
                continue
            alvo = decorador.func
            nome_decorador = alvo.id if isinstance(alvo, ast.Name) else getattr(alvo, "attr", "")
            if nome_decorador != "register":
                continue
            primeiro = decorador.args[0]
            if not (isinstance(primeiro, ast.Constant) and isinstance(primeiro.value, str)):
                continue
            achados.append((primeiro.value, no.name, no.lineno))
    return achados

def _aviso_registo_em_funcao_errada(caminho_relativo, texto_novo):
    """@register declarado para um nome que nao e o da funcao logo abaixo dele.

    Um decorador cola-se SEMPRE a funcao imediatamente a seguir: inserir uma
    auxiliar privada entre o `@register("tool_x", ...)` e o `def tool_x` registra a
    auxiliar no lugar do handler, e a ferramenta morre em execucao com um TypeError
    de argumento inesperado - sem a sintaxe acusar nada, porque o ficheiro continua
    valido. A prova de que esta certo e tool_verificar_ferramentas.
    """
    if not str(caminho_relativo or "").endswith(".py"):
        return ""
    errados = [
        f'@register("{declarado}") decora {funcao} (linha {linha})'
        for declarado, funcao, linha in _decoradores_de_registo(texto_novo)
        if declarado != funcao
    ]
    if not errados:
        return ""
    return ("REGISTO NA FUNCAO ERRADA: " + "; ".join(errados)
            + " -> o decorador cola-se a funcao imediatamente a seguir, logo o handler registado e o errado"
              " e a ferramenta morre em execucao (a sintaxe passa): a auxiliar privada vai ANTES do @register"
              " ou DEPOIS da funcao registada. Confirma com tool_verificar_ferramentas.")

def aviso_estrutural_pos_edicao(caminho_relativo, texto_antigo, texto_novo):
    """Checklist automatico anexado ao retorno das ferramentas de edicao.

    Detalha as funcoes criadas/removidas pela edicao para obrigar (por leitura
    direta do retorno da ferramenta) a verificacao de duplicidade antes de criar
    e a verificacao de codigo morto depois de remover. Nao bloqueia a escrita.
    """
    if texto_novo is None:
        return ""
    antes = _funcoes_com_linha(caminho_relativo, texto_antigo or "")
    depois = _funcoes_com_linha(caminho_relativo, texto_novo)
    nomes_antes = {nome for nome, _ in antes}
    nomes_depois = {nome for nome, _ in depois}
    criadas = sorted(nomes_depois - nomes_antes)
    removidas = sorted(nomes_antes - nomes_depois)
    partes = []
    registo = _aviso_registo_em_funcao_errada(caminho_relativo, texto_novo)
    if registo:
        partes.append(registo)
    if criadas:
        partes.append(
            "FUNCAO(OES) NOVA(S): " + ", ".join(criadas)
            + " -> POSICAO: abaixo da ultima funcao correlacionada do modulo, nunca no fim do ficheiro nem em qualquer lugar. ANTES de finalizar: tool_buscar_codigo + tool_pesquisar_no_projeto pelo nome/objetivo e tool_analisar_similaridade; se ja existir equivalente, MESCLAR em vez de duplicar."
        )
        posicao = _aviso_de_posicao(criadas, antes, depois)
        if posicao:
            partes.append(posicao)
    if removidas:
        partes.append(
            "FUNCAO(OES) REMOVIDA(S): " + ", ".join(removidas)
            + " -> ANTES de finalizar: tool_pesquisar_no_projeto por cada nome (garantir que nada as chama) e tool_auditar_imports_py/js no arquivo (imports, variaveis e dead code orfaos)."
        )
    orfas = _aviso_referencias_orfas(caminho_relativo, texto_antigo, texto_novo)
    if orfas:
        partes.append(orfas)
    if not partes:
        return ""
    return " | CHECKLIST ESTRUTURAL: " + " | ".join(partes)

_MARCADOR_IMPORT_LOCAL = "# import-local"

def _imports_locais(texto):
    """Imports dentro de blocos (col_offset > 0), lidos pela AST.

    Ler a AST em vez de regex evita falso positivo com exemplos de codigo
    escritos em docstrings. Devolve [(linha, modulo)] ordenado.
    """
    if not texto:
        return []
    try:
        arvore = ast.parse(texto)
    except (SyntaxError, ValueError):
        return []
    achados = []
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.Import, ast.ImportFrom)) or no.col_offset <= 0:
            continue
        if isinstance(no, ast.Import):
            nomes = [alias.name.split(".")[0] for alias in no.names]
        else:
            nomes = [(no.module or "").split(".")[0]]
        achados.extend((no.lineno, nome) for nome in nomes if nome)
    return sorted(achados)

def _import_local_marcado(texto, linha):
    linhas = texto.splitlines()
    for alvo in (linha, linha - 1):
        if 1 <= alvo <= len(linhas) and _MARCADOR_IMPORT_LOCAL in linhas[alvo - 1]:
            return True
    return False

def _novos_imports_locais(caminho_relativo, texto_antigo, texto_novo):
    """[(linha, modulo)] dos imports locais introduzidos pela edicao."""
    if not texto_novo or not str(caminho_relativo).endswith(".py"):
        return []
    anteriores = {nome for _, nome in _imports_locais(texto_antigo or "")}
    return [
        (linha, nome)
        for linha, nome in _imports_locais(texto_novo)
        if nome not in anteriores and not _import_local_marcado(texto_novo, linha)
    ]

def bloquear_import_local(caminho_relativo, texto_antigo, texto_novo):
    """Trava de escrita: recusa import local novo de biblioteca padrao.

    Import da stdlib nunca tem motivo para ficar dentro de uma funcao: nao ha
    ciclo de importacao, custo de carregamento nem dependencia opcional. Ja as
    dependencias externas e os modulos do proprio projeto continuam livres: ai a
    importacao dentro da funcao costuma ser deliberada (ciclo, ordem de patch ou
    carga tardia), por isso recebem apenas aviso. Excecao explicita: a propria
    linha do import (ou a
    anterior) pode conter '# import-local: <motivo>'.
    """
    ofensores = [
        (linha, nome)
        for linha, nome in _novos_imports_locais(caminho_relativo, texto_antigo, texto_novo)
        if nome in sys.stdlib_module_names
    ]
    if not ofensores:
        return ""
    detalhe = ", ".join(f"linha {linha}: '{nome}'" for linha, nome in ofensores)
    return (
        "IMPORT LOCAL DE BIBLIOTECA PADRAO: " + detalhe
        + ". Import da stdlib vai SEMPRE no bloco de imports do topo do arquivo. "
        "Mova o import para o topo e repita a edicao; se houver motivo tecnico real, "
        "marque a linha com '" + _MARCADOR_IMPORT_LOCAL + ": <motivo>'."
    )

def aviso_import_local(caminho_relativo, texto_antigo, texto_novo):
    """Aviso (nao bloqueia) para import local novo de dependencia externa/projeto."""
    novos = [
        (linha, nome)
        for linha, nome in _novos_imports_locais(caminho_relativo, texto_antigo, texto_novo)
        if nome not in sys.stdlib_module_names
    ]
    if not novos:
        return ""
    detalhe = ", ".join(f"linha {linha}: '{nome}'" for linha, nome in novos)
    return (
        " | IMPORT LOCAL NOVO: " + detalhe
        + " -> confirme que e deliberado (ciclo, ordem de patch ou carga tardia); "
        "caso contrario mova para o topo do arquivo."
    )
