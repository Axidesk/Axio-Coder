"""Pedido JSON por HTTP com os cabecalhos de cada servico - nunca levanta por resposta de erro."""

import json
import urllib.error
import urllib.request


def _leitor():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _mensagem_do_erro(texto):
    try:
        dados = json.loads(texto)
    except ValueError:
        return texto[:200]
    if isinstance(dados, dict):
        return str(dados.get("error") or dados.get("message") or texto[:200])[:300]
    return texto[:200]


def pedido_json(url, cabecalhos=None, corpo=None, metodo="GET", timeout=30):
    """Faz o pedido e devolve (dados, erro); a mensagem que o servico mandar vem no erro."""
    cabecalhos = dict(cabecalhos or {})
    cabecalhos.setdefault("User-Agent", "axio")
    carga = None
    if corpo is not None:
        carga = json.dumps(corpo).encode("utf-8")
        cabecalhos["Content-Type"] = "application/json"
    pedido = urllib.request.Request(url, data=carga, headers=cabecalhos, method=metodo)
    try:
        with _leitor().open(pedido, timeout=timeout) as resposta:
            texto = resposta.read().decode("utf-8", "replace")
        return (json.loads(texto) if texto.strip() else {}), ""
    except urllib.error.HTTPError as falha:
        return None, _mensagem_do_erro(falha.read().decode("utf-8", "replace"))
    except Exception as falha:
        return None, str(falha)
