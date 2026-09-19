"""Publica conteudo nos canais externos: um adaptador fino por canal, sobre a mesma interface."""

from src.backend.services.http_json import pedido_json

API_DEVTO = "https://dev.to/api/articles"


def _artigo_devto(item, novo=True):
    artigo = {}
    if item.get("titulo"):
        artigo["title"] = item["titulo"]
    if item.get("corpo"):
        artigo["body_markdown"] = item["corpo"]
    if novo or item.get("publicado"):
        artigo["published"] = bool(item.get("publicado"))
    etiquetas = item.get("tags")
    if etiquetas:
        artigo["tags"] = list(etiquetas)
    for chave, campo in (("main_image", "imagem"), ("canonical_url", "url_canonica"),
                         ("description", "descricao"), ("series", "serie")):
        valor = item.get(campo)
        if valor:
            artigo[chave] = valor
    return {"article": artigo}


CANAIS = {
    "devto": {
        "titulo": "DEV Community (dev.to)",
        "cartao": "devto",
        "endereco": API_DEVTO,
        "cabecalho": "api-key",
        "aceita": "application/json",
        "prepara": _artigo_devto,
    },
}


def canais():
    return [(nome, dados["titulo"]) for nome, dados in CANAIS.items()]


def cartao_do_canal(canal):
    dados = CANAIS.get(canal)
    return dados["cartao"] if dados else ""


def publicar(canal, item, token, id_artigo=""):
    """Cria o item no canal - ou atualiza, com 'id_artigo'; devolve (dados, erro)."""
    dados = CANAIS.get(canal)
    if not dados:
        return None, f"canal desconhecido: {canal}"
    endereco = f"{dados['endereco']}/{id_artigo}" if id_artigo else dados["endereco"]
    cabecalhos = {dados["cabecalho"]: token, "Accept": dados["aceita"]}
    return pedido_json(endereco, cabecalhos, dados["prepara"](item, not id_artigo),
                       "PUT" if id_artigo else "POST")
