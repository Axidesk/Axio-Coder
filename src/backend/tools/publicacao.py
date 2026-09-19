"""Divulgacao: publica o conteudo do projeto nos canais externos, com a chave lida do cofre."""

from src.backend.services import cofre, publicacao
from src.backend.tools.registry import register


def _lista_de_tags(texto):
    if isinstance(texto, list):
        return [t for t in texto if t][:4]
    if not texto:
        return []
    partes = [t.strip() for t in texto.replace(";", ",").split(",")]
    return [t for t in partes if t][:4]


@register(
    "tool_publicar_artigo",
    "Publica um artigo (Markdown) num canal externo de divulgacao, com a chave de API lida do cofre. "
    "Sem 'id_artigo' cria um artigo novo - exige 'titulo' e 'corpo'; com 'id_artigo' atualiza o que ja "
    "existe. Sai como RASCUNHO por omissao ('publicado'=false), para o utilizador rever e aprovar antes "
    "de ir para o ar: so com 'publicado'=true fica visivel no canal. Os 4 primeiros itens de 'tags' sao "
    "os que contam. As imagens tem de ser enderecos absolutos (o repositorio serve as do README pelo "
    "raw do GitHub).",
    {
        'canal': {"tipo": "STRING", "desc": "Canal de destino. Sem indicar, 'devto' (a DEV Community).", "padrao": "devto"},
        'titulo': {"tipo": "STRING", "desc": "Titulo do artigo (obrigatorio num artigo novo)", "padrao": ""},
        'corpo': {"tipo": "STRING", "desc": "Texto do artigo em Markdown (obrigatorio num artigo novo)", "padrao": ""},
        'tags': {"tipo": "STRING", "desc": "Etiquetas separadas por virgula - so as 4 primeiras contam (ex: 'ai, opensource, python, showdev')", "padrao": ""},
        'imagem': {"tipo": "STRING", "desc": "Endereco absoluto da imagem de capa", "padrao": ""},
        'url_canonica': {"tipo": "STRING", "desc": "Endereco de origem, quando o artigo ja vive noutro sitio", "padrao": ""},
        'descricao': {"tipo": "STRING", "desc": "Resumo curto, usado nas pre-visualizacoes e no SEO", "padrao": ""},
        'publicado': {"tipo": "BOOLEAN", "desc": "true publica de imediato; false guarda como rascunho", "padrao": False},
        'id_artigo': {"tipo": "STRING", "desc": "Id de um artigo ja publicado, para o atualizar em vez de criar outro", "padrao": ""},
    },
)
def tool_publicar_artigo(canal="devto", titulo="", corpo="", tags="", imagem="",
                         url_canonica="", descricao="", publicado=False, id_artigo=""):
    disponiveis = dict(publicacao.canais())
    if canal not in disponiveis:
        return (f"ERRO: canal '{canal}' nao existe. Disponiveis: "
                f"{', '.join(disponiveis) if disponiveis else 'nenhum'}.")
    if not id_artigo and not (titulo.strip() and corpo.strip()):
        return "ERRO: sem 'id_artigo' e um artigo novo - indique 'titulo' e 'corpo'."
    cartao = publicacao.cartao_do_canal(canal)
    token = cofre.obter(cartao, revelar=True, campo="chave")
    if not token:
        return (f"ERRO: falta a chave de API no cofre (Configuracoes -> Cofre, cartao '{cartao}', "
                f"campo 'chave'). No dev.to ela sai de Settings -> Extensions.")
    item = {"titulo": titulo, "corpo": corpo, "tags": _lista_de_tags(tags), "imagem": imagem,
            "url_canonica": url_canonica, "descricao": descricao, "publicado": publicado}
    dados, erro = publicacao.publicar(canal, item, token, id_artigo)
    if erro:
        return f"ERRO: o {disponiveis[canal]} recusou ({erro})."
    linhas = [f"ARTIGO {'atualizado' if id_artigo else 'criado'}: {dados.get('title') or titulo}",
              f"  canal: {disponiveis[canal]}",
              f"  id: {dados.get('id')}",
              f"  endereco: {dados.get('url')}"]
    if dados.get("published"):
        linhas.append("  estado: PUBLICADO - ja esta visivel para toda a gente.")
    else:
        linhas.append("  estado: RASCUNHO - so tu o ves ate o publicares "
                      "(o painel do canal tem o botao de publicar).")
    etiquetas = dados.get("tags") or dados.get("tag_list")
    if etiquetas:
        linhas.append(f"  tags: {', '.join(etiquetas) if isinstance(etiquetas, list) else etiquetas}")
    return "\n".join(linhas)
