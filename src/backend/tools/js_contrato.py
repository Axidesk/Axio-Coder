"""Contrato ES modules: imports de modulos locais que nao resolvem no disco."""

import os

from src.backend.services.file_service import arquivos_recursivos
from src.backend.tools.graph import texto_no


def _arvores_esm(fontes):
    """Parseia cada fonte com tree-sitter e devolve {rel: (tree, bytes)}.

    A AST e quem separa codigo de comentario/string: um `import` dentro de um
    comentario nao vira no; e por isso que a verificacao nao usa regex. Sem
    tree-sitter devolve {} e quem chama nao bloqueia nada - o gate so recusa
    quando tem certeza.
    """
    try:
        import tree_sitter_javascript as tsjs
        from tree_sitter import Language, Parser
    except ImportError:
        return {}
    parser = Parser(Language(tsjs.language()))
    arvores = {}
    for rel, conteudo in fontes.items():
        try:
            carga = bytes(conteudo, "utf8")
            arvores[rel] = (parser.parse(carga).root_node, carga)
        except (UnicodeEncodeError, ValueError):
            continue
    return arvores

def _padroes_do_no(no, carga):
    """Nomes ligados por um padrao de declaracao (identifier ou destructuring)."""
    if no is None:
        return set()
    if no.type in ("identifier", "shorthand_property_identifier_pattern"):
        return {texto_no(carga, no)}
    nomes = set()
    for filho in no.children:
        nomes |= _padroes_do_no(filho, carga)
    return nomes

def _nomes_da_declaracao(no, carga):
    """Nomes que uma declaracao (function/class/var/const/let) introduz."""
    if no is None:
        return set()
    nome = no.child_by_field_name("name")
    if nome is not None:
        return _padroes_do_no(nome, carga)
    nomes = set()
    for filho in no.children:
        if filho.type == "variable_declarator":
            nomes |= _padroes_do_no(filho.child_by_field_name("name"), carga)
    return nomes

def _nomes_do_export_clause(no, carga):
    """Nomes que um 'export { ... }' disponibiliza (o alias, quando existe)."""
    nomes = set()
    for filho in no.children:
        if filho.type != "export_clause":
            continue
        for spec_no in filho.children:
            if spec_no.type != "export_specifier":
                continue
            alvo = spec_no.child_by_field_name("alias") or spec_no.child_by_field_name("name")
            if alvo is not None:
                nomes.add(texto_no(carga, alvo))
    return nomes

def _negociado_do_modulo(raiz_ast, carga):
    """(imports, exports) de um modulo.

    `imports` e uma lista de (linha, spec, nomes, pede_default) com os nomes
    EXIGIDOS do modulo alvo (o nome de origem, nunca o alias local; lista vazia
    quando o import nao exige nada - side-effect ou 'import * as ns').
    `exports` e (nomes, tem_default, tem_estrela); `tem_estrela` marca
    'export *' / 'export * from', que torna o modulo imprevisivel por desenho.
    """
    imports = []
    nomes_export = set()
    tem_default = False
    tem_estrela = False
    for no in raiz_ast.children:
        if no.type == "import_statement":
            fonte = no.child_by_field_name("source")
            if fonte is None:
                for filho in no.children:
                    if filho.type == "string":
                        fonte = filho
            if fonte is None:
                continue
            spec = texto_no(carga, fonte).strip("'\"")
            exigidos = set()
            pede_default = False
            for filho in no.children:
                if filho.type != "import_clause":
                    continue
                for item in filho.children:
                    if item.type == "identifier":
                        pede_default = True
                    elif item.type == "named_imports":
                        for spec_no in item.children:
                            if spec_no.type == "import_specifier":
                                origem = spec_no.child_by_field_name("name")
                                if origem is not None:
                                    exigidos.add(texto_no(carga, origem))
            imports.append((no.start_point[0] + 1, spec, exigidos, pede_default))
            continue
        if no.type != "export_statement":
            continue
        fonte = no.child_by_field_name("source")
        estrela = any(filho.type == "*" for filho in no.children)
        if estrela:
            tem_estrela = True
        if fonte is not None:
            nomes_export |= _nomes_do_export_clause(no, carga)
            continue
        if any(filho.type == "default" for filho in no.children) or no.child_by_field_name("value") is not None:
            tem_default = True
        nomes_export |= _nomes_da_declaracao(no.child_by_field_name("declaration"), carga)
        nomes_export |= _nomes_do_export_clause(no, carga)
    return imports, (nomes_export, tem_default, tem_estrela)

def _ler_fonte(caminho):
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None

def defeitos_contrato_imports(raiz, alteracoes=None):
    """Imports de modulos locais que nao resolvem no estado projetado do projeto.

    `alteracoes` mapeia caminho relativo (com '/') -> conteudo posterior; None
    significa que o ficheiro deixa de existir. O resto do projeto e lido do
    disco. Devolve uma lista de {arquivo, linha, simbolo, modulo, motivo} - o
    que deixaria de resolver depois de aplicar `alteracoes`.

    Um import nomeado que aponta para um export inexistente (ou para um modulo
    que deixou de existir) e fatal em ES modules: o modulo inteiro falha ao
    carregar e leva atras quem o importa. E a classe de erro que deixa a
    interface muda, sem um unico erro visivel no ecra.
    """
    if not raiz or not os.path.isdir(raiz):
        return []
    abs_raiz = os.path.abspath(raiz)
    alteracoes = alteracoes or {}
    fontes = {}
    for caminho in arquivos_recursivos(abs_raiz, ".js"):
        rel = os.path.relpath(caminho, abs_raiz).replace(os.sep, "/")
        conteudo = alteracoes[rel] if rel in alteracoes else _ler_fonte(caminho)
        if conteudo is not None:
            fontes[rel] = conteudo
    for rel, conteudo in alteracoes.items():
        if rel.endswith(".js") and rel not in fontes and conteudo is not None:
            fontes[rel] = conteudo

    arvores = _arvores_esm(fontes)
    if not arvores:
        return []

    contratos = {}
    for rel, (raiz_ast, carga) in arvores.items():
        contratos[rel] = _negociado_do_modulo(raiz_ast, carga)

    defeitos = []
    for rel, (imports, _exports) in contratos.items():
        for linha, spec, exigidos, pede_default in imports:
            if not spec.startswith("."):
                continue
            alvo = os.path.normpath(os.path.join(os.path.dirname(rel), spec)).replace(os.sep, "/")
            if alvo not in fontes:
                removido = alvo.endswith(".js") and alvo in alteracoes and alteracoes[alvo] is None
                if removido:
                    defeitos.append({
                        "arquivo": rel, "linha": linha, "simbolo": "*",
                        "modulo": alvo, "motivo": "o modulo deixa de existir",
                    })
                continue
            nomes_export, tem_default, tem_estrela = contratos[alvo][1]
            if tem_estrela:
                continue
            if pede_default and not tem_default:
                defeitos.append({
                    "arquivo": rel, "linha": linha, "simbolo": "default",
                    "modulo": alvo, "motivo": "o modulo nao tem export default",
                })
            for nome in sorted(exigidos - nomes_export):
                defeitos.append({
                    "arquivo": rel, "linha": linha, "simbolo": nome,
                    "modulo": alvo, "motivo": "o modulo nao exporta este nome",
                })
    return defeitos

def quebras_introduzidas(raiz, alteracoes):
    """Defeitos de contrato que `alteracoes` INTRODUZ no projeto.

    O que ja estava quebrado antes nao conta: a medicao e por diferenca, para
    que uma restauracao legitima nao seja recusada por um defeito que ela nao
    criou.
    """
    chave = lambda d: (d["arquivo"], d["modulo"], d["simbolo"], d["motivo"])
    antes = {chave(d) for d in defeitos_contrato_imports(raiz, {})}
    return [d for d in defeitos_contrato_imports(raiz, alteracoes) if chave(d) not in antes]
