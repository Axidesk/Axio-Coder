"""Leitura de C/C++ por AST (tree-sitter): entidades, localizacao, includes e auditoria.

O motor verbatim do refactor nasceu para Python e JavaScript e, num .cpp a serio,
recusava ("Funcao 'applyPan' nao encontrada no JavaScript"). Aqui vive o leitor proprio
de C/C++, com a arvore do tree-sitter em vez de regex - a gramatica que o indice de codigo
(tools/code_index.py) ja usa para estes ficheiros, logo nao entra motor nem dependencia
novos. A arvore da o que a regex nao da: a assinatura real, o scope do metodo
(Classe::metodo) e a diferenca entre DECLARAR (prototipo, sem corpo) e DEFINIR - que e
exatamente o que decide se um movimento pode ser verbatim.
"""
import os
import re

from src.backend.tools.projeto_comum import varrer_por_extensao

EXTENSOES = (".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hh", ".hxx", ".ipp", ".tpp", ".h", ".c")
EXTENSOES_CABECALHO = (".h", ".hpp", ".hh", ".hxx")

_PARSERS = {}
_CAMADAS_NOME = ("function_declarator", "pointer_declarator", "reference_declarator",
                 "parenthesized_declarator", "array_declarator", "attributed_declarator")
_CAMADAS_DESCIDA = ("translation_unit", "declaration_list", "field_declaration_list",
                    "namespace_definition", "linkage_specification", "template_declaration")
_NOMES_SIMPLES = ("identifier", "field_identifier", "qualified_identifier", "destructor_name",
                  "operator_name", "type_identifier")
_TIPO_CLASSE = {"class_specifier": "classe", "struct_specifier": "struct", "union_specifier": "union"}
_RESERVADAS = {"public", "private", "protected", "signals", "slots", "friend", "virtual",
               "static", "inline", "template", "typedef", "using", "class", "struct", "union",
               "enum", "namespace", "operator", "explicit", "constexpr", "mutable"}
_MARCAS_DE_MACRO = {"explicit", "signals", "slots", "emit", "override", "final", "noexcept",
                    "public", "private", "protected", "tr", "foreach"}
_RE_NOME_VALIDO = re.compile(r"[A-Za-z_~][\w:~<>]*")
_RE_INCLUDE = re.compile(r"#[ \t]*include[ \t]*([<\"])([^>\"]+)[>\"]")
_MAX_CAMPOS = 12
_MAX_ERROS_SINTAXE = 5


def eh_cpp(caminho):
    return os.path.splitext(str(caminho))[1].lower() in EXTENSOES


def entidades(caminho_abs):
    """Classes, metodos, funcoes, campos e prototipos de um ficheiro C/C++, por linha."""
    src, arvore = partir(caminho_abs)
    if arvore is None:
        return []
    return colher(src, arvore)


def encontrar(caminho_abs, nome):
    """Ficha da definicao com corpo que casa com 'nome' (ou 'Classe::nome'). (ficha, erro)."""
    procurado_escopo, procurado_nome = _dividir_pedido(nome)
    if not procurado_nome:
        return None, f"ERRO: indique o nome da funcao (recebido '{nome}')."
    itens = [e for e in entidades(caminho_abs) if e["nome"] == procurado_nome]
    if not itens:
        return None, _recusa_por_ausencia(caminho_abs, procurado_nome)
    if procurado_escopo:
        itens = [e for e in itens if _escopo_casa(e["escopo"], procurado_escopo)]
    definicoes = [e for e in itens if e["corpo"]]
    if not definicoes:
        onde = itens[0]
        return None, (
            f"ERRO: '{nome}' esta apenas DECLARADA em '{os.path.basename(caminho_abs)}' "
            f"(linha {onde['linha']}): {onde['assinatura']} - nao tem corpo. Nao ha nada para mover "
            "nem apagar aqui: o corpo vive no .cpp. Aponte o ficheiro que o define."
        )
    if len(definicoes) > 1:
        lista = ", ".join(f"{_rotulo(e)} (linha {e['linha']})" for e in definicoes[:6])
        return None, (
            f"ERRO: '{nome}' tem {len(definicoes)} definicoes neste ficheiro ({lista}). "
            "Indique 'Classe::metodo' para escolher - mover a peca errada estragaria o ficheiro."
        )
    return definicoes[0], None


def localizar(caminho_abs, nome):
    """(inicio, fim) em linhas 1-based da definicao com corpo, ou mensagem de erro."""
    ficha, erro = encontrar(caminho_abs, nome)
    if erro:
        return erro
    return (ficha["linha"], ficha["fim"])


def escopo_de(caminho_abs, nome):
    """Nome da classe dona da funcao ('CameraManager') ou '' quando e funcao livre."""
    ficha, erro = encontrar(caminho_abs, nome)
    if erro or not ficha["escopo"]:
        return ""
    return sem_qualificadores(ficha["escopo"])


def includes(caminho_abs):
    """[(delimitador, destino)] na ordem em que aparecem, com '<' ou '\"' no delimitador."""
    try:
        with open(caminho_abs, "r", encoding="utf-8", errors="ignore") as f:
            texto = f.read()
    except OSError:
        return []
    return [(m.group(1), m.group(2).strip()) for m in _RE_INCLUDE.finditer(texto)]


def header_da_classe(nome, pastas):
    """Primeiro cabecalho das pastas dadas que DECLARA a classe 'nome' (AST, nao regex).

    A pista textual e so um filtro barato antes de parsear: quem confirma e a arvore,
    porque 'class CameraManager' tambem aparece dentro de um comentario ou de uma string.
    """
    if not nome:
        return ""
    pista = re.compile(r"\b(?:class|struct)\s+" + re.escape(nome) + r"\b")
    for pasta in pastas:
        if not pasta or not os.path.isdir(pasta):
            continue
        for ficheiro in varrer_por_extensao(pasta, EXTENSOES_CABECALHO):
            try:
                with open(ficheiro, "r", encoding="utf-8", errors="ignore") as f:
                    if not pista.search(f.read()):
                        continue
            except OSError:
                continue
            for item in entidades(ficheiro):
                if item["tipo"] in ("classe", "struct") and item["nome"] == nome:
                    return ficheiro
    return ""


def erros_de_sintaxe(caminho_abs):
    """Mensagem com os erros que a arvore acusa (ou None, que e tambem 'nao validavel')."""
    try:
        with open(caminho_abs, "rb") as f:
            texto = f.read()
    except OSError as e:
        return f"ERRO ao ler o ficheiro: {e}"
    return _erros_do_texto(texto, caminho_abs)


def erros_de_texto(texto, rotulo):
    """Mesma validacao sobre conteudo EM MEMORIA (validar_texto/comments). None = ok."""
    return _erros_do_texto(str(texto or "").encode("utf-8", "replace"), rotulo)


def mapa(caminho_abs):
    """Mapa do ficheiro no formato dos outros mapeadores: linha, tipo, nome, corpo."""
    src, arvore = partir(caminho_abs)
    if arvore is None:
        return ""
    itens = colher(src, arvore)
    if not itens:
        return ""
    total = src.count(b"\n") + 1
    linguagem = "C" if os.path.splitext(caminho_abs)[1].lower() == ".c" else "C++"
    classes = [e for e in itens if e["tipo"] in ("classe", "struct", "union")]
    funcoes = [e for e in itens if e["tipo"] in ("metodo", "funcao", "prototipo")]
    campos = [e for e in itens if e["tipo"] == "campo"]
    linhas = [(f"[{total} linhas | {len(classes)} classe(s) | {len(funcoes)} funcao(oes) | "
               f"{len(campos)} campo(s) | {linguagem}]")]
    for item in itens:
        if item["tipo"] == "campo":
            continue
        if item["tipo"] in ("classe", "struct", "union"):
            membros = [e for e in funcoes if _escopo_casa(e["escopo"], item["nome"])]
            meus_campos = [e for e in campos if _escopo_casa(e["escopo"], item["nome"])]
            linhas.append(f"Linha {item['linha']}-{item['fim']} ({item['fim'] - item['linha'] + 1}l): "
                          f"{item['tipo'].capitalize()} {item['nome']} "
                          f"({len(membros)} funcao(oes), {len(meus_campos)} campo(s))")
        elif item["corpo"]:
            linhas.append(f"Linha {item['linha']}-{item['fim']} "
                          f"({item['fim'] - item['linha'] + 1}l): {_rotulo(item)}")
        else:
            linhas.append(f"Linha {item['linha']}: (decl) {_rotulo(item)}")
    for item in classes:
        meus_campos = [e for e in campos if _escopo_casa(e["escopo"], item["nome"])]
        if not meus_campos:
            continue
        nomes = ", ".join(f"{c['nome']} (L{c['linha']})" for c in meus_campos[:_MAX_CAMPOS])
        resto = f" +{len(meus_campos) - _MAX_CAMPOS}" if len(meus_campos) > _MAX_CAMPOS else ""
        linhas.append(f"Campos de {item['nome']}: {nomes}{resto}")
    return "\n".join(linhas)


def partir(caminho_abs):
    """(bytes, arvore) do ficheiro, ou (None, None) quando nao ha tree-sitter ou nao da para ler."""
    parser = _parser(caminho_abs)
    if parser is None:
        return None, None
    try:
        with open(caminho_abs, "rb") as f:
            src = f.read()
    except OSError:
        return None, None
    try:
        return src, parser.parse(src)
    except Exception:
        return None, None


def _parser(caminho_abs):
    chave = "c" if os.path.splitext(caminho_abs)[1].lower() == ".c" else "cpp"
    if chave not in _PARSERS:
        try:
            from tree_sitter import Language, Parser
            if chave == "c":
                import tree_sitter_c as gramatica
            else:
                import tree_sitter_cpp as gramatica
            _PARSERS[chave] = Parser(Language(gramatica.language()))
        except Exception:
            _PARSERS[chave] = None
    return _PARSERS[chave]


def colher(src, arvore):
    """Entidades de topo de uma arvore ja parseada (evita ler o ficheiro outra vez)."""
    def texto(no):
        if no is None:
            return ""
        return src[no.start_byte:no.end_byte].decode("utf-8", "replace")

    saida = []

    def anda(no, classe, escopo, template=False, sinais=False):
        marcado = sinais
        for filho in no.children:
            tipo = filho.type
            if _desativado(filho, texto):
                continue
            if _e_marca_de_sinal(tipo, texto(filho)):
                marcado = True
                continue
            if tipo == "access_specifier":
                marcado = False
                continue
            if tipo == "template_declaration":
                anda(filho, classe, escopo, True, marcado)
            elif tipo in _CAMADAS_DESCIDA or tipo.startswith("preproc"):
                anda(filho, classe, escopo, template, marcado)
            elif tipo in _TIPO_CLASSE:
                nome = texto(filho.child_by_field_name("name"))
                if not nome:
                    continue
                escopo_filho = _juntar(escopo, nome)
                saida.append(_ficha(_TIPO_CLASSE[tipo], nome, escopo, filho, texto,
                                    corpo=True, classe=classe, template=template))
                anda(filho, nome, escopo_filho, template)
            elif tipo == "function_definition":
                declarador = filho.child_by_field_name("declarator")
                escopo_fn, nome = _dividir_nome(declarador, texto)
                if not nome:
                    continue
                corpo = filho.child_by_field_name("body")
                saida.append(_ficha("metodo" if classe else "funcao", nome,
                                    _juntar(escopo, escopo_fn) if escopo_fn else escopo,
                                    filho, texto, corpo=True, classe=classe, template=template,
                                    parametros=_quantos_parametros(declarador),
                                    sinal=marcado, assinatura=_assinatura(filho, corpo, texto)))
            elif tipo == "field_declaration":
                if classe:
                    saida.extend(_membros(filho, classe, escopo, texto, marcado))
            elif tipo == "declaration":
                if classe:
                    saida.extend(_membros(filho, classe, escopo, texto, marcado))
                    continue
                if _descendente(filho, "class_specifier") or _descendente(filho, "struct_specifier"):
                    anda(filho, classe, escopo, template, marcado)
                    continue
                declarador = filho.child_by_field_name("declarator")
                escopo_fn, nome = _dividir_nome(declarador, texto)
                if not nome or nome in _RESERVADAS:
                    continue
                saida.append(_ficha("prototipo", nome,
                                    _juntar(escopo, escopo_fn) if escopo_fn else escopo,
                                    filho, texto, corpo=False, classe=classe, template=template,
                                    parametros=_quantos_parametros(declarador)))

    anda(arvore.root_node, "", "")
    return sorted(saida, key=lambda e: (e["linha"], e["fim"]))


def _membros(no, classe, escopo, texto, sinais=False):
    """Metodos e campos de UMA field_declaration.

    Desce ao interior do no porque um macro sem ';' (Q_OBJECT) cola a declaracao seguinte
    dentro dele: sem isto, o construtor desaparecia da classe e a auditoria acusava uma
    definicao sem declaracao que existe. O no embaralhado traz um ERROR dentro, e e por
    esse sinal que se ignora - um campo a serio (mesmo um bitfield) nao tem ERROR nenhum.
    """
    if _tem_erro(no):
        return []
    declarador = no.child_by_field_name("declarator")
    funcao = declarador if declarador is not None and declarador.type == "function_declarator" \
        else _descendente(no, "function_declarator")
    if funcao is not None:
        _, nome = _dividir_nome(funcao, texto)
        if not nome or nome in _RESERVADAS:
            return []
        bruto = texto(no)
        abstrato = re.search(r"=\s*(?:0|default|delete)\s*;", bruto) is not None
        return [_ficha("metodo", nome, escopo, no, texto, corpo=False, classe=classe,
                       abstrato=abstrato, sinal=sinais,
                       parametros=_quantos_parametros(funcao),
                       assinatura=_uma_linha(bruto.split("{")[0]))]
    nome = _nome_do_declarador(declarador, texto)
    if not nome or nome in _RESERVADAS or not _e_nome_de_funcao(nome):
        return []
    return [_ficha("campo", nome, escopo, no, texto, corpo=False, classe=classe)]


def _ficha(tipo, nome, escopo, no, texto, corpo=False, classe="", template=False,
           assinatura=None, abstrato=False, parametros=0, sinal=False):
    return {
        "tipo": tipo,
        "nome": nome,
        "escopo": escopo or "",
        "classe": classe,
        "linha": no.start_point[0] + 1,
        "fim": no.end_point[0] + 1,
        "corpo": corpo,
        "template": template,
        "abstrato": abstrato,
        "parametros": parametros,
        "sinal": sinal,
        "assinatura": assinatura if assinatura is not None else _uma_linha(texto(no)),
    }


def _assinatura(no, corpo, texto):
    if corpo is None:
        return _uma_linha(texto(no))
    return _uma_linha(texto(no)[: corpo.start_byte - no.start_byte])


def _dividir_nome(declarador, texto):
    """(escopo, nome) do declarador: 'CameraManager::applyPan' -> ('CameraManager', 'applyPan')."""
    no = _descer_declarador(declarador)
    if no is None:
        return "", ""
    if no.type == "qualified_identifier":
        return texto(no.child_by_field_name("scope")), texto(no.child_by_field_name("name"))
    return "", texto(no)


def _descer_declarador(no):
    """Atravessa os invólucros do declarador ate ao nome.

    O campo 'declarator' NEM SEMPRE existe: em 'MaterialManager& MaterialManager::instance()'
    o reference_declarator traz o '&' anonimo e o function_declarator como filho, sem campo
    nenhum. Seguir so o campo perdia TODA a funcao que devolve referencia ou ponteiro - e a
    auditoria acusava uma declaracao sem definicao que estava no ficheiro ao lado.
    """
    while no is not None and no.type in _CAMADAS_NOME:
        proximo = no.child_by_field_name("declarator")
        if proximo is None:
            candidatos = [c for c in no.named_children
                          if c.type in _CAMADAS_NOME or c.type in _NOMES_SIMPLES]
            proximo = candidatos[-1] if candidatos else None
        no = proximo
    return no


def _quantos_parametros(declarador):
    """Numero de parametros declarados - e o que separa 'BoundingBox()' de 'BoundingBox(a,b)'."""
    no = declarador
    if no is not None and no.type != "function_declarator":
        no = _descendente(no, "function_declarator")
    if no is None:
        return 0
    lista = no.child_by_field_name("parameters")
    if lista is None:
        return 0
    return len([c for c in lista.named_children if c.type != "comment"])


def _nome_do_declarador(declarador, texto):
    if declarador is None:
        return ""
    if declarador.type not in _CAMADAS_NOME:
        return texto(declarador)
    _, nome = _dividir_nome(declarador, texto)
    return nome


def _descendente(no, tipo):
    """Primeiro no do tipo pedido dentro da subarvore (procura em largura)."""
    fila = list(no.children)
    while fila:
        atual = fila.pop(0)
        if atual.type == tipo:
            return atual
        fila += list(atual.children)
    return None


def _tem_erro(no):
    fila = [no]
    while fila:
        atual = fila.pop()
        if atual.type == "ERROR" or atual.is_missing:
            return True
        fila += list(atual.children)
    return False


def mencoes_por_classe(src, arvore):
    """{classe: nomes de funcao escritos no corpo dela}, por leitura solta.

    Serve SO para calar um aviso, nunca para o dar: quando um macro sem ';' (Q_OBJECT)
    embaralha a arvore, a lista estrita de membros fica incompleta e um metodo declarado
    apareceria como 'definido sem declaracao'. Desce a tudo menos ao corpo das funcoes -
    uma chamada la dentro nao declara nada na classe.
    """
    saida = {}

    def anda(no, classe):
        for filho in no.children:
            tipo = filho.type
            if tipo in ("class_specifier", "struct_specifier", "union_specifier"):
                nome_no = filho.child_by_field_name("name")
                nome = src[nome_no.start_byte:nome_no.end_byte].decode("utf-8", "replace") \
                    if nome_no is not None else ""
                if nome:
                    saida.setdefault(nome, set())
                    anda(filho, nome)
            elif tipo in ("function_definition", "compound_statement", "lambda_expression"):
                continue
            elif tipo in ("function_declarator", "call_expression") and classe:
                alvo = filho.child_by_field_name("function") or _descendente(filho, "field_identifier") \
                    or _descendente(filho, "identifier")
                if alvo is not None:
                    nome = src[alvo.start_byte:alvo.end_byte].decode("utf-8", "replace")
                    saida[classe].add(sem_qualificadores(nome))
                anda(filho, classe)
            elif not filho.is_named:
                continue
            else:
                anda(filho, classe)

    anda(arvore.root_node, "")
    return saida


def _erros_do_texto(src_bytes, rotulo):
    parser = _parser(rotulo)
    if parser is None:
        return None
    try:
        arvore = parser.parse(src_bytes)
    except Exception:
        return None
    problemas = []

    def anda(no):
        if len(problemas) >= _MAX_ERROS_SINTAXE:
            return
        if no.type == "ERROR" or no.is_missing:
            trecho = src_bytes[no.start_byte:no.end_byte].decode("utf-8", "replace")
            if _e_marca_de_macro(trecho):
                return
            problemas.append(f"linha {no.start_point[0] + 1}, coluna {no.start_point[1] + 1}: "
                             f"{_uma_linha(trecho, 60) or '(falta token)'}")
            return
        for filho in no.children:
            anda(filho)

    anda(arvore.root_node)
    return "\n    ".join(problemas) if problemas else None


def _e_marca_de_sinal(tipo, bruto):
    """True quando a linha e a marca 'signals:' (ou Q_SIGNALS) de dentro de uma classe.

    Metodo sob 'signals:' nao tem corpo escrito por ninguem: quem o gera e o moc, no build.
    Sem esta marca, todo sinal de Qt aparecia como 'declarado sem definicao' e o aviso - que
    existe para o erro de linker - perdia o valor.
    """
    if tipo not in ("access_specifier", "ERROR", "labeled_statement", "identifier"):
        return False
    return _palavra_limpa(bruto) in ("signals", "q_signals")


def _palavra_limpa(bruto):
    primeira = str(bruto or "").split("\n")[0].strip().rstrip(":").strip().lower()
    return primeira


def _desativado(no, texto):
    """Bloco dentro de '#if 0': nao existe para o compilador, logo nao conta como definicao.

    Um 'int main' que vive num #if 0 de uma biblioteca de ficheiro unico (stb_*) aparecia
    como definicao duplicada do main do projeto - ruido que esconde a duplicacao a serio.
    """
    if no.type not in ("preproc_if", "preproc_ifdef", "preproc_elif"):
        return False
    primeira = str(texto(no)).split("\n")[0].strip()
    return re.match(r"#\s*(?:if|elif)\s+0\b", primeira) is not None


def _e_marca_de_macro(trecho):
    """Palavra que o C++ padrao nao conhece e o pre-processador come.

    Qt e companhia definem 'signals', 'slots' e 'emit' por macro (#define signals public) -
    o parser ve a palavra crua e acusa ERROR onde nao ha erro nenhum. O mesmo vale para
    'Q_OBJECT' e afins, que so o moc entende. Sem esta trava, todo cabecalho Qt sairia
    marcado como quebrado e o aviso deixava de valer - alarme falso que se aprende a ignorar.
    """
    limpo = str(trecho or "").strip().rstrip(":").strip()
    if not limpo:
        return False
    if limpo in _MARCAS_DE_MACRO:
        return True
    return bool(re.fullmatch(r"[A-Z_][A-Z0-9_]*", limpo)) and "_" in limpo


def sem_qualificadores(nome):
    """Ultimo pedaco de um nome qualificado: 'App::Foo::bar' -> 'bar' (sem <template>)."""
    return str(nome or "").split("::")[-1].split("<")[0].strip()


def _e_nome_de_funcao(nome):
    return bool(nome) and _RE_NOME_VALIDO.fullmatch(nome) is not None


def _uma_linha(texto, limite=200):
    limpo = re.sub(r"\s+", " ", str(texto or "")).strip()
    return limpo if len(limpo) <= limite else limpo[:limite] + "..."


def _rotulo(item):
    escopo = f"{item['escopo']}::" if item.get("escopo") else ""
    return f"{item['tipo'].capitalize()} {escopo}{item['nome']}"


def _juntar(escopo, nome):
    return f"{escopo}::{nome}" if escopo else nome


def _escopo_casa(escopo, procurado):
    if not procurado:
        return True
    partes = [sem_qualificadores(p) for p in str(escopo).split("::") if p.strip()]
    return bool(partes) and partes[-1] == sem_qualificadores(procurado)


def _dividir_pedido(nome):
    bruto = str(nome or "").strip()
    if "::" in bruto:
        escopo, _, limpo = bruto.rpartition("::")
        return escopo.strip(), limpo.strip()
    return "", bruto


def _recusa_por_ausencia(caminho_abs, nome):
    conhecidos = [e["nome"] for e in entidades(caminho_abs) if e["tipo"] in ("metodo", "funcao")]
    parecidos = sorted({k for k in conhecidos if nome.lower() in k.lower() or k.lower() in nome.lower()})
    dica = f" Nomes parecidos no ficheiro: {', '.join(parecidos[:6])}." if parecidos else ""
    return (f"ERRO: '{nome}' nao existe em '{os.path.basename(caminho_abs)}' "
            f"({len(conhecidos)} funcao(oes) lida(s) pela arvore).{dica}")
