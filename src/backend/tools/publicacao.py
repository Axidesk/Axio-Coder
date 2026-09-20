"""Divulgacao: publica o conteudo do projeto nos canais externos, com as chaves lidas do cofre."""

import re

from src.backend.services import cofre, imagem, publicacao
from src.backend.tools.registry import register

_FIGURA = re.compile(r"!\[[^\]]*\]\(\s*([^)\s]+)|<img[^>]+?src=[\"']([^\"']+)[\"']", re.IGNORECASE)


def _lista_de_tags(texto):
    if isinstance(texto, list):
        return [t for t in texto if t][:4]
    if not texto:
        return []
    partes = [t.strip() for t in texto.replace(";", ",").split(",")]
    return [t for t in partes if t][:4]


def _credenciais_do_canal(ficha):
    """Le do cofre os campos que o canal declara precisar; devolve (credenciais, erro)."""
    cartao = ficha["cartao"]
    credenciais = {campo: cofre.obter(cartao, revelar=True, campo=campo) or ""
                   for campo in ficha["credenciais"]}
    faltam = [campo for campo, valor in credenciais.items() if not valor]
    if faltam:
        return None, (f"ERRO: falta no cofre o campo '{faltam[0]}' do cartao '{cartao}' "
                      f"(Configuracoes -> Cofre). {ficha.get('ajuda_chave', '')}")
    return credenciais, ""


def _enderecos_de_imagem(item):
    """A capa e as imagens que o corpo mostra - o que vai mesmo aparecer na publicacao."""
    achados = [item.get("imagem") or ""]
    for achado in _FIGURA.finditer(item.get("corpo") or ""):
        achados.append(achado.group(1) or achado.group(2) or "")
    return [alvo for alvo in achados if alvo]


def _texto_de_recusa(ficha, titulo, corpo, imagem, publicado):
    """O que impede o gesto antes de sair para a rede - dito antes, nunca depois."""
    if not ficha["rascunho"] and not publicado:
        return (f"ERRO: o {ficha['titulo']} nao tem rascunho - o que se publica fica visivel na hora. "
                f"Confirme com publicado=true para publicar, ou nao publique agora.")
    if not corpo.strip():
        return "ERRO: indique 'corpo' com o texto a publicar."
    if ficha["precisa_titulo"] and not titulo.strip():
        return "ERRO: este canal precisa de 'titulo'."
    limite = ficha.get("limite") or 0
    if limite and len(corpo.strip()) > limite:
        return (f"ERRO: o corpo tem {len(corpo.strip())} caracteres e o {ficha['titulo']} corta nos "
                f"{limite}. Encurte o texto - num post nao se escreve um artigo.")
    if imagem and not ficha["recebe_imagem"]:
        return f"ERRO: o {ficha['titulo']} ainda nao recebe imagem por esta ferramenta - so texto."
    return ""


def _recusa_de_imagem(item):
    """Recusa publicar uma imagem que eu nunca olhei ou que nao carrega - ver antes de postar."""
    problemas = imagem.conferir_imagens(_enderecos_de_imagem(item))
    if not problemas:
        return ""
    linhas = [f"ERRO: {len(problemas)} imagem(ns) do que ia ser publicado nao passaram na conferencia:"]
    linhas += [f"  - {endereco} ({motivo})" for endereco, motivo in problemas]
    linhas.append("Abra cada uma com tool_ver_imagem antes de publicar. A marca e o CONTEUDO do "
                  "ficheiro: corrigir a imagem obriga a olhar para ela outra vez.")
    return "\n".join(linhas)


@register(
    "tool_publicar_artigo",
    "Publica um artigo ou um post num canal externo de divulgacao, com a chave de API lida do cofre. "
    "Sem 'id_artigo' cria (exige 'corpo'; 'titulo' so nos canais que o pedem); com 'id_artigo' atualiza "
    "o que ja existe. Cada canal diz o que aceita: o dev.to aceita rascunho - sai como RASCUNHO por "
    "omissao ('publicado'=false) para o utilizador rever antes de ir para o ar - e o Bluesky nao tem "
    "rascunho, logo exige 'publicado'=true e fica visivel no momento. Os 4 primeiros itens de 'tags' "
    "sao os que contam no dev.to; no Bluesky as etiquetas vao no texto do proprio post como hashtags. "
    "As imagens tem de ser enderecos absolutos (o repositorio serve as do README pelo raw do GitHub). "
    "Antes de sair para a rede, cada imagem - a capa e as que o corpo mostra - e CONFERIDA pelo conteudo: "
    "tem de carregar e de ja ter sido OLHADA por mim com tool_ver_imagem; publicar uma imagem que nunca vi, "
    "ou que responde 404, fica recusado.",
    {
        'canal': {"tipo": "STRING", "desc": "Canal de destino. Sem indicar, 'devto' (a DEV Community).", "padrao": "devto"},
        'titulo': {"tipo": "STRING", "desc": "Titulo do artigo (so nos canais que o pedem, como o dev.to)", "padrao": ""},
        'corpo': {"tipo": "STRING", "desc": "Texto a publicar: Markdown no dev.to, texto simples no Bluesky (maximo 300 caracteres)", "padrao": ""},
        'tags': {"tipo": "STRING", "desc": "Etiquetas separadas por virgula - so as 4 primeiras contam (ex: 'ai, opensource, python, showdev')", "padrao": ""},
        'imagem': {"tipo": "STRING", "desc": "Endereco absoluto da imagem de capa (so nos canais que a aceitam)", "padrao": ""},
        'url_canonica': {"tipo": "STRING", "desc": "Endereco de origem, quando o artigo ja vive noutro sitio", "padrao": ""},
        'descricao': {"tipo": "STRING", "desc": "Resumo curto, usado nas pre-visualizacoes e no SEO", "padrao": ""},
        'publicado': {"tipo": "BOOLEAN", "desc": "true publica de imediato; false guarda como rascunho nos canais que o tenham", "padrao": False},
        'id_artigo': {"tipo": "STRING", "desc": "Id de um artigo ja publicado, para o atualizar em vez de criar outro", "padrao": ""},
    },
)
def tool_publicar_artigo(canal="devto", titulo="", corpo="", tags="", imagem="",
                         url_canonica="", descricao="", publicado=False, id_artigo=""):
    disponiveis = dict(publicacao.canais())
    if canal not in disponiveis:
        return (f"ERRO: canal '{canal}' nao existe. Disponiveis: "
                f"{', '.join(disponiveis) if disponiveis else 'nenhum'}.")
    ficha = publicacao.ficha_do_canal(canal)
    if not id_artigo:
        recusa = _texto_de_recusa(ficha, titulo, corpo, imagem, publicado)
        if recusa:
            return recusa
    item = {"titulo": titulo, "corpo": corpo, "tags": _lista_de_tags(tags), "imagem": imagem,
            "url_canonica": url_canonica, "descricao": descricao, "publicado": publicado}
    recusa = _recusa_de_imagem(item)
    if recusa:
        return recusa
    credenciais, erro = _credenciais_do_canal(ficha)
    if erro:
        return erro
    dados, erro = publicacao.publicar(canal, item, credenciais, id_artigo)
    if erro:
        return f"ERRO: o {disponiveis[canal]} recusou ({erro})."
    linhas = [f"{ficha['tipo'].upper()} {'atualizado' if id_artigo else 'criado'}: "
              f"{dados.get('title') or titulo or corpo.strip()[:60]}",
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
