"""Marcas de um frontend: o que o HTML nomeia, o que o JS procura e o que o CSS estiliza.

Le o HTML pelo parser do Python e o JS e o CSS pela arvore (tree-sitter), e devolve marcas
(id, classe, referencia, prefixo montado) ja com ficheiro e linha. Nao julga nada - quem cruza
os tres lados e decide o que e orfao e o auditor de ligacoes.
"""
import re
from html.parser import HTMLParser

EXT_HTML = (".html", ".htm")
EXT_JS = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx")
EXT_CSS = (".css",)

_METODOS_DE_ID = {"getelementbyid"}
_METODOS_DE_SELETOR = {"queryselector", "queryselectorall", "closest", "matches"}
_METODOS_DE_CLASSE = {"getelementsbyclassname"}
_METODOS_DE_CLASSLIST = {"add", "remove", "toggle", "contains", "replace"}
_MONTADOS = ("binary_expression", "template_string", "call_expression")
_ATRIBUTOS_DE_ID = (
    "for", "list", "form", "headers", "usemap",
    "aria-labelledby", "aria-describedby", "aria-controls", "aria-owns",
    "aria-activedescendant", "aria-flowto", "aria-details", "aria-errormessage",
)
_PADRAO_ID_NO_TEXTO = re.compile(r"""(?<![\w.$])id\s*=\s*["']([^"']+)["']""")
_PADRAO_CLASSE_NO_TEXTO = re.compile(r"""(?<![\w.$])class\s*=\s*["']([^"']*)["']""")
_PADRAO_ID_MONTADO = re.compile(r"""(?<![\w.$])id\s*=\s*["']([^"'$]*)\$\{""")
_PADRAO_CLASSE_MONTADA = re.compile(r"""(?<![\w.$])class\s*=\s*["']([^"'$]*)\$\{""")
_PADRAO_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")


def novo_cofre():
    """Acumulador das marcas de JS: procurados, criados, dinamicos e prefixos montados."""
    return {"ids": [], "classes": [], "dinamicos": [], "ids_novos": [], "classes_novas": [], "prefixos": set()}


def juntar(destino, origem):
    for chave in ("ids", "classes", "dinamicos", "ids_novos", "classes_novas"):
        destino[chave].extend(origem[chave])
    destino["prefixos"] |= origem["prefixos"]


def ler_texto(caminho):
    try:
        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return None


def _marca(valor, ficheiro, linha, via):
    return {"valor": valor, "ficheiro": ficheiro, "linha": linha, "via": via}


class _LeitorHtml(HTMLParser):
    def __init__(self, ficheiro):
        super().__init__(convert_charrefs=True)
        self.ficheiro = ficheiro
        self.ids = []
        self.classes = []
        self.referencias = []
        self.scripts = []
        self._bloco = None
        self._linha_do_script = 0

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self._linha_do_script = self.getpos()[0]
            self._bloco = []
        linha = self.getpos()[0]
        for nome, valor in attrs:
            if not valor:
                continue
            if nome == "id":
                self.ids.append(_marca(valor.strip(), self.ficheiro, linha, "id"))
            elif nome == "class":
                for parte in valor.split():
                    self.classes.append(_marca(parte, self.ficheiro, linha, "class"))
            elif nome in _ATRIBUTOS_DE_ID:
                for parte in valor.split():
                    self.referencias.append(_marca(parte, self.ficheiro, linha, nome))
            elif nome == "href" and valor.startswith("#") and len(valor) > 1:
                self.referencias.append(_marca(valor[1:], self.ficheiro, linha, "href"))

    def handle_endtag(self, tag):
        if tag == "script" and self._bloco is not None:
            if "".join(self._bloco).strip():
                self.scripts.append((self._linha_do_script, "".join(self._bloco)))
            self._bloco = None

    def handle_data(self, data):
        if self._bloco is not None:
            self._bloco.append(data)


def html_do_ficheiro(caminho, relativo):
    """(ids, classes, referencias internas, blocos de <script>) declarados num HTML."""
    texto = ler_texto(caminho)
    if texto is None:
        return [], [], [], []
    leitor = _LeitorHtml(relativo)
    try:
        leitor.feed(texto)
        leitor.close()
    except Exception:
        pass
    return leitor.ids, leitor.classes, leitor.referencias, leitor.scripts


def _linha_do_indice(texto, indice):
    return texto.count("\n", 0, indice) + 1


def _tokens_do_atributo(valor):
    return [parte for parte in valor.split() if _PADRAO_TOKEN.match(parte)]


def declaracoes_em_texto(texto, relativo):
    """Id, classe e prefixo montado escritos em texto (markup despachado dentro de uma string)."""
    ids = [_marca(achado.group(1).strip(), relativo, _linha_do_indice(texto, achado.start()), "id no texto")
           for achado in _PADRAO_ID_NO_TEXTO.finditer(texto)
           if _PADRAO_TOKEN.match(achado.group(1).strip())]
    classes = [_marca(parte, relativo, _linha_do_indice(texto, achado.start()), "class no texto")
               for achado in _PADRAO_CLASSE_NO_TEXTO.finditer(texto)
               for parte in _tokens_do_atributo(achado.group(1))]
    prefixos = set()
    for achado in _PADRAO_ID_MONTADO.finditer(texto):
        linha = _linha_do_indice(texto, achado.start())
        for parte in _tokens_do_atributo(achado.group(1)):
            ids.append(_marca(parte, relativo, linha, "id montado no texto"))
        cabeca = achado.group(1).strip()
        if len(cabeca) >= 2:
            prefixos.add(cabeca)
    for achado in _PADRAO_CLASSE_MONTADA.finditer(texto):
        linha = _linha_do_indice(texto, achado.start())
        for parte in _tokens_do_atributo(achado.group(1)):
            classes.append(_marca(parte, relativo, linha, "class montada no texto"))
        cabeca = achado.group(1).strip()
        if len(cabeca) >= 2:
            prefixos.add(cabeca)
    return ids, classes, prefixos


def _texto(no, dados):
    return dados[no.start_byte:no.end_byte].decode("utf-8", "ignore")


def _ler_string(no, dados):
    if no.type == "string":
        texto = _texto(no, dados)
        if len(texto) >= 2 and texto[0] in "\"'":
            return texto[1:-1]
        return texto
    if no.type == "template_string":
        if any(filho.type == "template_substitution" for filho in no.children):
            return None
        texto = _texto(no, dados)
        return texto[1:-1] if len(texto) >= 2 else texto
    return None


def _membros(no, dados):
    partes = []
    while no is not None and no.type == "member_expression":
        propriedade = no.child_by_field_name("property")
        if propriedade is not None:
            partes.insert(0, _texto(propriedade, dados))
        no = no.child_by_field_name("object")
    if no is not None and no.type in ("identifier", "this"):
        partes.insert(0, _texto(no, dados))
    return partes


def _fim_do_intervalo(texto, i, abre, fecha):
    i += 1
    while i < len(texto):
        if texto[i] == "\\":
            i += 2
            continue
        if texto[i] == fecha:
            return i + 1
        if abre != fecha and texto[i] == abre:
            i = _fim_do_intervalo(texto, i, abre, fecha)
            continue
        i += 1
    return i


def _alvos_do_seletor(seletor):
    """Ids e classes citados num seletor CSS, sem olhar para dentro de [atributo] nem de aspas."""
    ids, classes = set(), set()
    i, n = 0, len(seletor)
    while i < n:
        ch = seletor[i]
        if ch == "[":
            i = _fim_do_intervalo(seletor, i, "[", "]")
            continue
        if ch in "\"'":
            i = _fim_do_intervalo(seletor, i, ch, ch)
            continue
        if ch in "#.":
            j = i + 1
            while j < n and (seletor[j].isalnum() or seletor[j] in "_-\\"):
                j += 1
            nome = seletor[i + 1:j].replace("\\", "")
            if nome:
                (ids if ch == "#" else classes).add(nome)
            i = j
            continue
        i += 1
    return ids, classes


def _prefixo_do_montado(no, dados):
    """Parte literal do nome que o codigo constroi (`` `painel-${x}` `` -> 'painel-')."""
    if no.type == "template_string":
        texto = _texto(no, dados)
        corte = texto.find("${")
        if corte < 0:
            return ""
        literal = texto[1:corte].lstrip("#.").strip()
        return literal if len(literal) >= 2 else ""
    if no.type == "binary_expression":
        esquerda = no.child_by_field_name("left")
        if esquerda is None or esquerda.type != "string":
            return ""
        literal = (_ler_string(esquerda, dados) or "").lstrip("#.").strip()
        return literal if len(literal) >= 2 else ""
    return ""


def _strings_internas(no, dados):
    """Literais de texto dentro de uma expressao (`` `a${x ? ' b' : ''}` `` -> [' b'])."""
    literais = []
    pilha = [no]
    while pilha:
        atual = pilha.pop()
        if atual.type == "string":
            texto = _ler_string(atual, dados)
            if texto:
                literais.append(texto)
            continue
        pilha.extend(atual.children)
    return literais


def _dinamico(argumento, dados, ficheiro, linha, via, cofre):
    if argumento.type not in _MONTADOS:
        return
    cofre["dinamicos"].append(_marca(_texto(argumento, dados)[:48], ficheiro, linha, via))
    prefixo = _prefixo_do_montado(argumento, dados)
    if prefixo:
        cofre["prefixos"].add(prefixo)


def _da_chamada(no, dados, ficheiro, cofre):
    funcao = no.child_by_field_name("function")
    argumentos = no.child_by_field_name("arguments")
    if funcao is None or argumentos is None or funcao.type != "member_expression":
        return
    partes = _membros(funcao, dados)
    if len(partes) < 2:
        return
    metodo, baixo = partes[-1], partes[-1].lower()
    dono = partes[-2].lower()
    linha = no.start_point[0] + 1
    argumentos = list(argumentos.named_children)
    if dono == "classlist" and baixo in _METODOS_DE_CLASSLIST:
        for argumento in argumentos:
            valor = _ler_string(argumento, dados)
            if valor is None:
                _dinamico(argumento, dados, ficheiro, linha, f"classList.{metodo}", cofre)
                continue
            for parte in valor.split():
                cofre["classes"].append(_marca(parte, ficheiro, linha, f"classList.{metodo}"))
        return
    if baixo in _METODOS_DE_ID:
        for argumento in argumentos:
            valor = _ler_string(argumento, dados)
            if valor is None:
                _dinamico(argumento, dados, ficheiro, linha, metodo, cofre)
                continue
            cofre["ids"].append(_marca(valor, ficheiro, linha, metodo))
        return
    if baixo in _METODOS_DE_CLASSE:
        for argumento in argumentos:
            valor = _ler_string(argumento, dados)
            if valor is None:
                _dinamico(argumento, dados, ficheiro, linha, metodo, cofre)
                continue
            for parte in valor.split():
                cofre["classes"].append(_marca(parte, ficheiro, linha, metodo))
        return
    if baixo in _METODOS_DE_SELETOR:
        for argumento in argumentos:
            valor = _ler_string(argumento, dados)
            if valor is None:
                _dinamico(argumento, dados, ficheiro, linha, metodo, cofre)
                continue
            achados_ids, achados_classes = _alvos_do_seletor(valor)
            for nome in achados_ids:
                cofre["ids"].append(_marca(nome, ficheiro, linha, f"{metodo}('{valor}')"))
            for nome in achados_classes:
                cofre["classes"].append(_marca(nome, ficheiro, linha, f"{metodo}('{valor}')"))
        return
    if baixo == "setattribute" and len(argumentos) >= 2:
        nome = _ler_string(argumentos[0], dados)
        valor = _ler_string(argumentos[1], dados) or ""
        if nome == "id" and valor:
            cofre["ids_novos"].append(_marca(valor, ficheiro, linha, "setAttribute('id')"))
        elif nome == "class":
            for parte in valor.split():
                cofre["classes_novas"].append(_marca(parte, ficheiro, linha, "setAttribute('class')"))


def _da_atribuicao(no, dados, ficheiro, cofre):
    esquerda = no.child_by_field_name("left")
    direita = no.child_by_field_name("right")
    if esquerda is None or direita is None or esquerda.type != "member_expression":
        return
    partes = _membros(esquerda, dados)
    if not partes or partes[-1] not in ("id", "className"):
        return
    linha = no.start_point[0] + 1
    valor = _ler_string(direita, dados)
    if valor is not None:
        if partes[-1] == "id":
            cofre["ids_novos"].append(_marca(valor, ficheiro, linha, "atribuicao de id"))
            return
        for parte in valor.split():
            cofre["classes_novas"].append(_marca(parte, ficheiro, linha, "atribuicao de className"))
        return
    if partes[-1] != "className":
        return
    prefixo = _prefixo_do_montado(direita, dados)
    if prefixo:
        cofre["prefixos"].add(prefixo)
        for parte in prefixo.split():
            if not parte.endswith(("-", "_")):
                cofre["classes_novas"].append(_marca(parte, ficheiro, linha, "class montada em className"))
    for literal in _strings_internas(direita, dados):
        for parte in literal.split():
            cofre["classes_novas"].append(_marca(parte, ficheiro, linha, "class montada em className"))


def _alvos_do_js(ficheiro, dados, arvore):
    cofre = novo_cofre()
    pilha = [arvore.root_node]
    while pilha:
        no = pilha.pop()
        if no.type == "call_expression":
            _da_chamada(no, dados, ficheiro, cofre)
        elif no.type == "assignment_expression":
            _da_atribuicao(no, dados, ficheiro, cofre)
        pilha.extend(no.children)
    return cofre


def javascript_do_texto(ficheiro, texto, leitor, base=0):
    """Marcas de um trecho de JS: o ficheiro inteiro ou um <script> dentro do HTML."""
    dados = texto.encode("utf-8")
    cofre = _alvos_do_js(ficheiro, dados, leitor.parse(dados))
    if base:
        for chave in ("ids", "classes", "dinamicos", "ids_novos", "classes_novas"):
            for marca in cofre[chave]:
                marca["linha"] += base
    return cofre


def alvos_do_css(ficheiro, texto, leitor):
    """(ids, classes) citados nos seletores de um CSS."""
    dados = texto.encode("utf-8")
    ids, classes = [], []
    pilha = [leitor.parse(dados).root_node]
    while pilha:
        no = pilha.pop()
        if no.type in ("id_selector", "class_selector"):
            filho = next((c for c in no.children if c.type in ("id_name", "class_name")), None)
            if filho is not None:
                nome = _texto(filho, dados).lstrip("#.").strip()
                if nome:
                    destino = ids if no.type == "id_selector" else classes
                    destino.append(_marca(nome, ficheiro, no.start_point[0] + 1, no.type))
        pilha.extend(no.children)
    return ids, classes


def leitor_js(caminho):
    try:
        from tree_sitter import Language, Parser
        if caminho.lower().endswith((".ts", ".tsx")):
            import tree_sitter_typescript
            fabrica = (tree_sitter_typescript.language_tsx
                       if caminho.lower().endswith(".tsx") else tree_sitter_typescript.language_typescript)
            return Parser(Language(fabrica())), None
        import tree_sitter_javascript
        return Parser(Language(tree_sitter_javascript.language())), None
    except ImportError:
        return None, "tree-sitter-javascript/typescript nao instalado"
    except Exception as e:
        return None, f"falha ao iniciar o parser de JS ({e})"


def leitor_css():
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_css
        return Parser(Language(tree_sitter_css.language())), None
    except ImportError:
        return None, "tree-sitter-css nao instalado"
    except Exception as e:
        return None, f"falha ao iniciar o parser de CSS ({e})"
