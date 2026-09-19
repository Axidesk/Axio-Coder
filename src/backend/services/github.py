"""Fala com a API do GitHub: pedidos autenticados, Releases e a vitrine do repositorio."""

from src.backend.services.http_json import pedido_json

API = "https://api.github.com"


def pedido_api(url, token="", metodo="GET", corpo=None):
    """Faz um pedido a API do GitHub e devolve (dados, erro)."""
    cabecalhos = {"Accept": "application/vnd.github+json", "User-Agent": "axio"}
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    return pedido_json(url, cabecalhos, corpo, metodo, timeout=25)


def release_da_etiqueta(slug, etiqueta, token):
    dados, erro = pedido_api(f"{API}/repos/{slug}/releases/tags/{etiqueta}", token)
    return None if erro else dados


def publicar_release(slug, etiqueta, titulo, corpo, rascunho, token):
    """Cria o Release da etiqueta ou atualiza o que ja existe; devolve (dados, erro, acao)."""
    pedido = {"tag_name": etiqueta, "name": titulo or etiqueta, "body": corpo,
              "draft": bool(rascunho), "prerelease": False}
    existente = release_da_etiqueta(slug, etiqueta, token)
    if isinstance(existente, dict) and existente.get("id"):
        dados, erro = pedido_api(f"{API}/repos/{slug}/releases/{existente['id']}", token, "PATCH", pedido)
        return dados, erro, "atualizado"
    dados, erro = pedido_api(f"{API}/repos/{slug}/releases", token, "POST", pedido)
    return dados, erro, "publicado"
