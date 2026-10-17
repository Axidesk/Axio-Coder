import os
import re
import json
import subprocess
import xml.etree.ElementTree as ET

from html.parser import HTMLParser

from src.backend.state import emit_event, estado
from src.backend.services import executaveis
from src.backend.tools import cpp, rust
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
    ".php": "php",
    ".html": "html",
    ".htm": "html",
    ".rs": "rust",
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
    ".lua": "lua",
    ".xml": "html",
    ".xsd": "html",
    ".xsl": "html",
    ".svg": "html",
    ".xhtml": "html",
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
    relato = _validar_com_tree_sitter(conteudo, parser)
    if not relato:
        return relato
    sem_ancora = re.sub(r"url\(\s*#", "url(_", conteudo)
    if sem_ancora != conteudo and not _validar_com_tree_sitter(sem_ancora, parser):
        return None
    return relato

def _parser_rust():
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_rust
    except ImportError:
        return None, "ERRO: tree-sitter ou tree-sitter-rust nao instalados (necessarios para validar Rust)."
    try:
        return Parser(Language(tree_sitter_rust.language())), None
    except Exception as e:
        return None, f"ERRO: falha ao iniciar o parser de Rust (tree-sitter): {e}"

def _validar_rust(conteudo):
    parser, erro = _parser_rust()
    if erro:
        return erro
    return _validar_com_tree_sitter(conteudo, parser)

def _parser_lua():
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_lua
    except ImportError:
        return None, "ERRO: tree-sitter ou tree-sitter-lua nao instalados (necessarios para validar Lua)."
    try:
        return Parser(Language(tree_sitter_lua.language())), None
    except Exception as e:
        return None, f"ERRO: falha ao iniciar o parser de Lua (tree-sitter): {e}"

def _validar_lua(conteudo):
    parser, erro = _parser_lua()
    if erro:
        return erro
    return _validar_com_tree_sitter(conteudo, parser)

_RE_PREFIXO_DE_ERRO = re.compile(r"^linha (\d+), coluna \d+: ")


def _chave_do_erro(relato):
    relato = relato.strip()
    prefixo = _RE_PREFIXO_DE_ERRO.match(relato)
    if prefixo:
        return relato[prefixo.end():]
    return re.sub(r"\d+", "#", relato)


def _linha_do_erro(relato):
    achado = _RE_PREFIXO_DE_ERRO.match(relato.strip())
    return int(achado.group(1)) if achado else None


def _mais_perto(linhas, alvo):
    """Indice da linha mais proxima de 'alvo' (0 quando nao ha numeros que se comparem)."""
    if alvo is None or any(linha is None for linha in linhas):
        return 0
    return min(range(len(linhas)), key=lambda i: abs(linhas[i] - alvo))


def _erros_novos(agora, antes):
    """Separa dois relatos da arvore em (novos, ja existiam), comparando pelo TEXTO e nao pela linha."""
    fila = {}
    for relato in antes:
        fila.setdefault(_chave_do_erro(relato), []).append(_linha_do_erro(relato))
    novos, antigos = [], []
    for relato in agora:
        candidatas = fila.get(_chave_do_erro(relato))
        if not candidatas:
            novos.append(relato)
            continue
        candidatas.pop(_mais_perto(candidatas, _linha_do_erro(relato)))
        antigos.append(relato)
    return novos, antigos


def _problemas_de_antes(caminho_absoluto):
    """Problemas da versao do ficheiro ANTERIOR a ultima edicao gravada (None quando nao ha registo)."""
    hist = estado.get("file_history", {}).get(caminho_absoluto) or {}
    if not hist.get("undo"):
        return None
    antes = hist["undo"][-1].get("antes")
    if not isinstance(antes, str):
        return None
    return cpp.problemas_do_texto(antes, caminho_absoluto)


def _aviso_cpp(caminho_absoluto, antes=None):
    """Aviso pos-edicao de C++: a arvore nao e' o compilador, por isso so o NOVO interessa aqui."""
    problemas, erro = cpp.problemas_do_arquivo(caminho_absoluto)
    if erro or not problemas:
        return ""
    if antes is None:
        anteriores = _problemas_de_antes(caminho_absoluto)
    else:
        anteriores = cpp.problemas_do_texto(antes, caminho_absoluto)
    if anteriores is None:
        return (" | AVISO: a arvore de C++ nao leu o ficheiro (nao e' o compilador): "
                + "\n    ".join(problemas))
    novos, antigos = _erros_novos(problemas, anteriores)
    if not novos:
        return (f" | AVISO C++: nada de novo nesta edicao - a arvore ja acusava os mesmos "
                f"{len(antigos)} problema(s) antes da gravacao.")
    resto = f"\n    (e mais {len(antigos)} que ja existiam antes, fora desta lista)" if antigos else ""
    return " | AVISO C++ NOVO nesta edicao:\n    " + "\n    ".join(novos) + resto


def _veredicto_cpp(caminho_relativo, caminho_absoluto):
    """Veredicto do validador de C++: o que apareceu agora fica separado do que ja la estava."""
    problemas, erro = cpp.problemas_do_arquivo(caminho_absoluto)
    if erro:
        return (f"NAO FOI POSSIVEL LER '{caminho_relativo}' (cpp, a arvore nao substitui o "
                f"compilador):\n    {erro}")
    if not problemas:
        return f"SINTAXE OK: '{caminho_relativo}' (cpp)"
    cabeca = (f"NAO FOI POSSIVEL LER '{caminho_relativo}' (cpp, a arvore nao substitui o "
              f"compilador):")
    anteriores = _problemas_de_antes(caminho_absoluto)
    if anteriores is None:
        return cabeca + "\n    " + "\n    ".join(problemas)
    novos, antigos = _erros_novos(problemas, anteriores)
    blocos = [cabeca]
    if novos:
        blocos.append("NOVO nesta edicao:\n    " + "\n    ".join(novos))
    if antigos:
        blocos.append(f"JA existia antes desta edicao ({len(antigos)}):\n    " + "\n    ".join(antigos))
    if not novos:
        blocos.append("Nenhum problema novo: esta lista ja estava toda no ficheiro antes da sua edicao.")
    return "\n".join(blocos)


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
    if _PROLOGO_XML.match(conteudo):
        return _validar_xml(conteudo)
    erros = _erros_de_estrutura_html(conteudo) + _erros_finos_html(conteudo)
    if not erros:
        return None
    if len(erros) > 8:
        return "\n".join(erros[:8]) + f"\n... e mais {len(erros) - 8} erro(s) nao listado(s)."
    return "\n".join(erros)

_PROLOGO_XML = re.compile(r"^[^\S\n]*<\?xml\b", re.IGNORECASE)

def _validar_xml(conteudo):
    try:
        ET.fromstring(conteudo.encode("utf-8"))
        return None
    except ET.ParseError as e:
        return str(e)

def _limpar_saida_php(texto):
    limpo = texto.strip()
    primeira = limpo.splitlines()[0] if limpo else ""
    linha = re.search(r"on line (\d+)", texto)
    corpo = re.sub(r"\s+in\s+.*$", "", re.sub(r"^.*?error:\s*", "", primeira)).strip()
    if linha:
        return f"linha {linha.group(1)}: {corpo}"
    return corpo or primeira

def _erros_php(abs_path):
    """Erro de sintaxe do php, ou None (ficheiro bom OU php ausente - quem chama decide)."""
    php = executaveis.php()
    if not php:
        return None
    try:
        saida = subprocess.run([php, "-l", abs_path], capture_output=True, timeout=30)
    except subprocess.TimeoutExpired:
        return "o php nao respondeu em 30s"
    except OSError:
        return None
    if saida.returncode == 0:
        return None
    texto = (saida.stdout or b"").decode("utf-8", "replace") + (saida.stderr or b"").decode("utf-8", "replace")
    if not texto.strip():
        return "o php recusou o ficheiro e nao disse por que"
    return _limpar_saida_php(texto)

@register(
    "tool_validar_sintaxe",
    'Valida a sintaxe de um arquivo (Python, JavaScript, TypeScript, C/C++, Rust, Lua, JSON, CSS, HTML, XML ou PHP) após editar/mover código. Use SEMPRE após edições para confirmar que não quebrou sintaxe — NÃO use comandos proibidos (python, py_compile, node --check, grep, sed, cat, echo) para isso. No HTML confere o balanceamento das tags, os ids repetidos e os tokens mal formados. Num XML com prologo <?xml faz o parse a serio (tag desalinhada, atributo mal fechado); o XML sem prologo continua a ser lido como HTML, para nao acusar ficheiros de terceiros que nunca foram nossos. Em C/C++ a leitura e pela arvore (tree-sitter): palavras que so o pre-processador conhece (Q_OBJECT, signals:, emit) nao contam como erro. Em Rust e em Lua a leitura tambem e pela arvore (tree-sitter), onde os atributos #[...] contam como parte do item. Aceita VARIOS arquivos de uma vez, um por linha no proprio caminho_relativo, e responde num relatorio unico com o total - e o caminho rapido depois de editar em lote. Retorna OK ou o erro com linha/coluna.',
    {
        'caminho_relativo': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'linguagem': {"tipo": "STRING", "enum": ['python', 'javascript', 'typescript', 'cpp', 'rust', 'lua', 'json', 'css', 'html', 'xml', 'php'], "padrao": ""},
    },
)
def tool_validar_sintaxe(caminho_relativo, linguagem=""):
    emit_event("executing", function=f"Validando sintaxe: {caminho_relativo}")
    caminhos = [c.strip() for c in (caminho_relativo or "").splitlines() if c.strip()]
    if not caminhos:
        return "ERRO: informe 'caminho_relativo'."
    if len(caminhos) == 1:
        return _validar_um(caminhos[0], linguagem)
    resultados = [_validar_um(c, linguagem) for c in caminhos]
    falhas = [r for r in resultados if not r.startswith("SINTAXE OK")]
    cabecalho = f"VALIDACAO EM LOTE ({len(caminhos)} arquivo(s)): {len(caminhos) - len(falhas)} OK, {len(falhas)} com problema"
    return "\n\n".join([cabecalho] + resultados)

def _validar_um(caminho_relativo, linguagem=""):
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
    elif lang in ("html", "xml"):
        try:
            conteudo = _ler_texto(abs_path)
        except OSError as e:
            return f"ERRO ao ler o arquivo: {e}"
        if lang == "xml" or _PROLOGO_XML.match(conteudo):
            lang = "xml"
            erro_msg = _validar_xml(conteudo)
        else:
            erro_msg = _validar_html(conteudo)
    elif lang == "javascript":
        erro_msg = _validar_javascript(abs_path)
    elif lang == "typescript":
        try:
            conteudo = _ler_texto(abs_path)
        except OSError as e:
            return f"ERRO ao ler o arquivo: {e}"
        erro_msg = _validar_typescript(conteudo, abs_path)
    elif lang == "rust":
        try:
            conteudo = _ler_texto(abs_path)
        except OSError as e:
            return f"ERRO ao ler o arquivo: {e}"
        erro_msg = _validar_rust(conteudo)
    elif lang == "lua":
        try:
            conteudo = _ler_texto(abs_path)
        except OSError as e:
            return f"ERRO ao ler o arquivo: {e}"
        erro_msg = _validar_lua(conteudo)
    elif lang == "cpp":
        return _veredicto_cpp(caminho_relativo, abs_path)
    elif lang == "php":
        if not executaveis.php():
            return ("ERRO: nao encontrei o php.exe para validar sintaxe php. "
                    "Ponha o caminho dele em PHP_EXE ou instale o php.")
        erro_msg = _erros_php(abs_path)
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
        if lang == "rust":
            return rust.erros_de_texto(conteudo)
        if lang == "lua":
            return _validar_lua(conteudo)
    except Exception as e:
        return f"falha ao validar: {e}"
    return None

def validar_arquivo_apos_edicao(caminho_relativo, caminho_absoluto=None, antes=None):
    """Em C++ vale por 'antes' o TEXTO anterior completo (None = ir busca-lo ao historico de edicoes)."""
    lang = _detectar_linguagem(caminho_relativo, "")
    if lang not in ("python", "javascript", "json", "css", "html", "cpp", "rust", "php", "lua"):
        return ""
    if caminho_absoluto is None:
        caminho_absoluto, erro = resolver_caminho(caminho_relativo)
        if erro:
            return ""
    if lang == "cpp":
        return _aviso_cpp(caminho_absoluto, antes)
    try:
        if lang == "json":
            erro = _validar_json(_ler_texto(caminho_absoluto))
        elif lang == "python":
            erro = _validar_python(_ler_texto(caminho_absoluto), caminho_relativo)
        elif lang == "css":
            erro = _validar_css(_ler_texto(caminho_absoluto))
        elif lang == "html":
            erro = _validar_html(_ler_texto(caminho_absoluto))
        elif lang == "php":
            erro = _erros_php(caminho_absoluto)
        elif lang == "rust":
            erro = _validar_rust(_ler_texto(caminho_absoluto))
        elif lang == "lua":
            erro = _validar_lua(_ler_texto(caminho_absoluto))
        else:
            erro = _validar_javascript(caminho_absoluto)
    except OSError:
        return ""
    if erro:
        return f" | AVISO SINTAXE {lang}: {erro}"
    return ""

