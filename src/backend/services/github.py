"""Fala com a API do GitHub: pedidos autenticados, Releases e a vitrine do repositorio."""

import json
import urllib.error
import urllib.request

API = "https://api.github.com"


def _leitor():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def pedido_api(url, token="", metodo="GET", corpo=None):
    """Faz um pedido a API e devolve (dados, erro) - nunca levanta por resposta HTTP de erro."""
    cabecalhos = {"Accept": "application/vnd.github+json", "User-Agent": "axio"}
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    carga = None
    if corpo is not None:
        carga = json.dumps(corpo).encode("utf-8")
        cabecalhos["Content-Type"] = "application/json"
    pedido = urllib.request.Request(url, data=carga, headers=cabecalhos, method=metodo)
    try:
        with _leitor().open(pedido, timeout=25) as resposta:
            return json.loads(resposta.read().decode("utf-8", "replace")), ""
    except urllib.error.HTTPError as falha:
        texto = falha.read().decode("utf-8", "replace")
        try:
            return None, (json.loads(texto).get("message") or texto[:200])
        except ValueError:
            return None, texto[:200]
    except Exception as falha:
        return None, str(falha)


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
