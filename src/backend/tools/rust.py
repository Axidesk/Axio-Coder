"""Leitura de Rust por AST (tree-sitter): onde comeca e acaba um item do modulo.

O motor verbatim do refactor cobria Python, JavaScript e C/C++ (tools/cpp.py) e num .rs
recusava ("a extensao '.rs' nao tem localizador de funcao"). Aqui vive o leitor proprio de
Rust, com a gramatica tree-sitter-rust - a mesma familia que o cpp.py e o validador de
sintaxe ja usam, logo nao entra motor nem conceito novos. A arvore nao e luxo neste
ficheiro: em Rust o apostrofo de um lifetime ('a) le-se como abertura de char literal e
engole o resto do ficheiro, e os atributos (#[tauri::command]) sao nos IRMAOS do item que
decoram - apagar o item sem eles deixa um #[...] orfao, que nem sintaxe valida e.
"""
import os

_PARSERS = {}
_ITENS_COM_NOME = {
    "function_item": "funcao",
    "struct_item": "struct",
    "enum_item": "enum",
    "union_item": "union",
    "trait_item": "trait",
    "const_item": "const",
    "static_item": "static",
    "type_item": "tipo",
    "mod_item": "modulo",
    "macro_definition": "macro",
}
_LIMITE_DE_ERROS = 5
_LIMITE_DE_CANDIDATOS = 8


def eh_rust(caminho):
    return os.path.splitext(str(caminho))[1].lower() == ".rs"


def localizar(caminho_abs, nome):
    """(linha inicial, linha final) do item 'nome', ja com os atributos e a doc acima dele."""
    dados, arvore = partir(caminho_abs)
    if arvore is None:
        return f"ERRO: nao consegui ler '{os.path.basename(caminho_abs)}' como Rust."
    achados = _procurar(arvore.root_node, dados, nome)
    if not achados:
        return (f"ERRO: '{nome}' nao existe em '{os.path.basename(caminho_abs)}'. Neste ficheiro o "
                "localizador cobre funcao, struct, enum, union, trait, const, static, type, mod, "
                "macro e impl (pelo tipo).")
    if len(achados) > 1:
        linhas = ", ".join(str(_inicio_em_linhas(no, dados)) for no in achados[:_LIMITE_DE_CANDIDATOS])
        return (f"ERRO: ha {len(achados)} itens com o nome '{nome}' neste ficheiro (linhas {linhas}). "
                "Cortar um so cortaria o errado - use tool_mover_bloco_verbatim com as linhas exatas.")
    item = achados[0]
    com_marcas = _com_as_marcas_acima(item, dados)
    return (_inicio_em_linhas(com_marcas, dados), _fim_em_linhas(item, dados))


def erros_de_texto(texto):
    """Erro (ou None) da arvore de um conteudo EM MEMORIA, com a linha e o que nao encaixa."""
    problemas = problemas_do_texto(texto)
    return "\n    ".join(problemas) if problemas else None


def problemas_do_texto(texto):
    """Lista dos erros da arvore de um conteudo EM MEMORIA (vazia = ok ou sem parser)."""
    arvore = _parsear(str(texto or "").encode("utf-8", "replace"))
    if arvore is None:
        return []
    dados = str(texto or "").encode("utf-8", "replace")
    return [f"linha {no.start_point[0] + 1}, coluna {no.start_point[1] + 1}: {_o_que_nao_encaixa(no, dados)}"
            for no in _erros_da_arvore(arvore.root_node)]


def partir(caminho_abs):
    """(bytes, arvore) do ficheiro, ou (None, None) se nao houver parser ou a leitura falhar."""
    try:
        with open(caminho_abs, "rb") as f:
            dados = f.read()
    except OSError:
        return None, None
    arvore = _parsear(dados)
    if arvore is None:
        return None, None
    return dados, arvore


def _parser():
    if "rust" not in _PARSERS:
        try:
            import tree_sitter_rust as gramatica
            from tree_sitter import Language, Parser
            _PARSERS["rust"] = Parser(Language(gramatica.language()))
        except (ImportError, AttributeError, TypeError, ValueError):
            _PARSERS["rust"] = None
    return _PARSERS["rust"]


def _parsear(dados):
    parser = _parser()
    if parser is None:
        return None
    try:
        return parser.parse(dados)
    except (TypeError, ValueError):
        return None


def _procurar(no, dados, nome):
    """Itens com esse nome, em qualquer nivel - em Rust o metodo vive dentro de um 'impl'."""
    achados = []

    def anda(atual):
        for filho in atual.children:
            if filho.type in _ITENS_COM_NOME:
                if _nome_do_item(filho, dados) == nome:
                    achados.append(filho)
            elif filho.type == "impl_item" and _tipo_do_impl(filho, dados) == nome:
                achados.append(filho)
            anda(filho)

    anda(no)
    return achados


def _nome_do_item(no, dados):
    return _texto_do_campo(no, "name", dados)


def _tipo_do_impl(no, dados):
    return _texto_do_campo(no, "type", dados).strip()


def _texto_do_campo(no, campo, dados):
    alvo = no.child_by_field_name(campo)
    if alvo is None:
        return ""
    return dados[alvo.start_byte:alvo.end_byte].decode("utf-8", "replace")


def _com_as_marcas_acima(no, dados):
    """Sobe do item para os atributos (#[...]) e a doc (///) colados por cima dele."""
    pai = no.parent
    if pai is None:
        return no
    irmaos = pai.children
    posicao = irmaos.index(no)
    atual = no
    while posicao > 0:
        anterior = irmaos[posicao - 1]
        if not _e_marca_do_item(anterior, atual, dados):
            break
        atual = anterior
        posicao -= 1
    return atual


def _e_marca_do_item(anterior, seguinte, dados):
    if anterior.type == "attribute_item":
        return _linhas_coladas(anterior, seguinte, dados)
    if anterior.type != "line_comment":
        return False
    marcadores = {filho.type for filho in anterior.children}
    if "outer_doc_comment_marker" not in marcadores:
        return False
    return _linhas_coladas(anterior, seguinte, dados)


def _linhas_coladas(anterior, seguinte, dados):
    return _fim_em_linhas(anterior, dados) + 1 == _inicio_em_linhas(seguinte, dados)


def _inicio_em_linhas(no, dados):
    return dados[:no.start_byte].count(b"\n") + 1


def _fim_em_linhas(no, dados):
    novas = dados[:no.end_byte].count(b"\n")
    return novas if dados[no.end_byte - 1:no.end_byte] == b"\n" else novas + 1


def _erros_da_arvore(raiz, limite=_LIMITE_DE_ERROS):
    achados = []
    pilha = [raiz]
    while pilha:
        no = pilha.pop()
        if no.type == "token_tree":
            continue
        if no.is_error or no.is_missing:
            achados.append(no)
            continue
        if no.has_error:
            pilha.extend(no.children)
    achados.sort(key=lambda item: item.start_point)
    return achados[:limite]


def _o_que_nao_encaixa(no, dados):
    trecho = ""
    if no.end_byte > no.start_byte:
        trecho = dados[no.start_byte:no.end_byte].decode("utf-8", "replace").splitlines()[0].strip()
    if len(trecho) > 60:
        trecho = trecho[:60] + "..."
    return ("falta" if no.is_missing else "nao entendi") + f" '{trecho or 'nada'}'"
