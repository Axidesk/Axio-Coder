"""Fala com a API do GitHub: pedidos autenticados, Releases e a vitrine do repositorio."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from src.backend.services.http_json import pedido_json

API = "https://api.github.com"

_TIPOS_DE_ANEXO = {
    ".zip": "application/zip",
    ".7z": "application/x-7z-compressed",
    ".rar": "application/vnd.rar",
    ".exe": "application/vnd.microsoft.portable-executable",
    ".msi": "application/x-msi",
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".json": "application/json",
}


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


def anexar_ficheiro(slug, release_id, caminho, token):
    """Sobe um ficheiro como anexo do Release; devolve (dados, erro).

    O GitHub aceita o binario inteiro num pedido so (sem blocos) ate 2 GB - o que
    faltava nao era protocolo, era o parametro na ferramenta.
    """
    nome = os.path.basename(caminho)
    try:
        with open(caminho, "rb") as f:
            dados = f.read()
    except OSError as falha:
        return None, f"nao consegui ler o ficheiro ({falha})"
    cabecalhos = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "axio",
        "Content-Type": _tipo_do_anexo(nome),
    }
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    url = f"{API}/repos/{slug}/releases/{release_id}/assets?name={urllib.parse.quote(nome)}"
    pedido = urllib.request.Request(url, data=dados, headers=cabecalhos, method="POST")
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(pedido, timeout=600) as resposta:
            texto = resposta.read().decode("utf-8", "replace")
        return (json.loads(texto) if texto.strip() else {}), ""
    except urllib.error.HTTPError as falha:
        corpo = falha.read().decode("utf-8", "replace")
        if falha.code == 422 and "already_exists" in corpo:
            return None, "ja existe um anexo com esse nome neste Release"
        try:
            motivo = json.loads(corpo).get("errors") or json.loads(corpo).get("message") or corpo
        except ValueError:
            motivo = corpo
        return None, f"HTTP {falha.code}: {str(motivo)[:200]}"
    except Exception as falha:
        return None, str(falha)


def _tipo_do_anexo(nome):
    return _TIPOS_DE_ANEXO.get(os.path.splitext(nome)[1].lower(), "application/octet-stream")
