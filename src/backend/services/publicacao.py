"""Publica conteudo nos canais externos: um adaptador fino por canal, sobre a mesma interface."""

import re
import time

from src.backend.services.http_json import pedido_json

API_DEVTO = "https://dev.to/api/articles"
API_BLUESKY = "https://bsky.social/xrpc"
LIMITE_BLUESKY = 300
COLECAO_POST = "app.bsky.feed.post"

_LINK = rb"[$|\W](https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*[-a-zA-Z0-9@%_\+~#//=])?)"
_TAG = rb"(?:^|\s)(#[^\d\s]\S*)"


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


def _facetas(texto):
    """Enderecos e hashtags do post, indexados em bytes UTF-8 - e a unidade do Bluesky."""
    corpo = texto.encode("utf-8")
    facetas = []
    for achado in re.finditer(_LINK, corpo):
        inicio, fim = achado.start(1), achado.end(1)
        while fim > inicio and corpo[fim - 1:fim] in b".,;!?":
            fim -= 1
        facetas.append({"index": {"byteStart": inicio, "byteEnd": fim},
                        "features": [{"$type": "app.bsky.richtext.facet#link",
                                      "uri": corpo[inicio:fim].decode("utf-8")}]})
    for achado in re.finditer(_TAG, corpo):
        inicio, fim = achado.start(1), achado.end(1)
        while fim > inicio + 1 and corpo[fim - 1:fim] in b".,;!?":
            fim -= 1
        facetas.append({"index": {"byteStart": inicio, "byteEnd": fim},
                        "features": [{"$type": "app.bsky.richtext.facet#tag",
                                      "tag": corpo[inicio + 1:fim].decode("utf-8")}]})
    facetas.sort(key=lambda faceta: faceta["index"]["byteStart"])
    return facetas or None


def _post_bluesky(item, novo=True):
    texto = (item.get("corpo") or "").strip()
    registo = {"$type": COLECAO_POST, "text": texto,
               "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())}
    facetas = _facetas(texto)
    if facetas:
        registo["facets"] = facetas
    return registo


def _publica_generico(ficha, item, credenciais, id_artigo=""):
    endereco = f"{ficha['endereco']}/{id_artigo}" if id_artigo else ficha["endereco"]
    cabecalhos = {ficha["cabecalho"]: credenciais[ficha["credenciais"][0]], "Accept": ficha["aceita"]}
    return pedido_json(endereco, cabecalhos, ficha["prepara"](item, not id_artigo),
                       "PUT" if id_artigo else "POST")


def _publica_bluesky(ficha, item, credenciais, id_artigo=""):
    if id_artigo:
        return None, "o Bluesky nao atualiza um post - cada um e um registo proprio e nao se edita"
    sessao, erro = pedido_json(f"{ficha['endereco']}/com.atproto.server.createSession",
                               {"Accept": "application/json"},
                               {"identifier": credenciais["usuario"], "password": credenciais["chave"]},
                               "POST")
    if erro:
        return None, f"o login foi recusado ({erro})"
    publicado, erro = pedido_json(f"{ficha['endereco']}/com.atproto.repo.createRecord",
                                  {"Authorization": "Bearer " + sessao["accessJwt"],
                                   "Accept": "application/json"},
                                  {"repo": sessao["did"], "collection": COLECAO_POST,
                                   "record": ficha["prepara"](item)}, "POST")
    if erro:
        return None, erro
    chave = publicado["uri"].rsplit("/", 1)[-1]
    return {"id": chave, "uri": publicado["uri"], "published": True,
            "url": f"https://bsky.app/profile/{sessao['handle']}/post/{chave}"}, ""


CANAIS = {
    "devto": {
        "titulo": "DEV Community (dev.to)",
        "cartao": "devto",
        "tipo": "artigo",
        "credenciais": ("chave",),
        "ajuda_chave": "No dev.to ela sai de Settings -> Extensions.",
        "endereco": API_DEVTO,
        "cabecalho": "api-key",
        "aceita": "application/json",
        "prepara": _artigo_devto,
        "rascunho": True,
        "precisa_titulo": True,
        "recebe_imagem": True,
    },
    "bluesky": {
        "titulo": "Bluesky",
        "cartao": "bluesky",
        "tipo": "post",
        "credenciais": ("usuario", "chave"),
        "ajuda_chave": ("No Bluesky ela sai de Settings -> App Passwords (e o campo 'usuario' e o handle, "
                        "ex: axidesk.bsky.social)."),
        "endereco": API_BLUESKY,
        "prepara": _post_bluesky,
        "publica": _publica_bluesky,
        "rascunho": False,
        "precisa_titulo": False,
        "recebe_imagem": False,
        "limite": LIMITE_BLUESKY,
    },
}


def canais():
    return [(nome, dados["titulo"]) for nome, dados in CANAIS.items()]


def ficha_do_canal(canal):
    return dict(CANAIS.get(canal) or {})


def publicar(canal, item, credenciais, id_artigo=""):
    """Cria o item no canal - ou atualiza, com 'id_artigo'; devolve (dados, erro)."""
    ficha = CANAIS.get(canal)
    if not ficha:
        return None, f"canal desconhecido: {canal}"
    proprio = ficha.get("publica")
    if proprio:
        return proprio(ficha, item, credenciais, id_artigo)
    return _publica_generico(ficha, item, credenciais, id_artigo)
