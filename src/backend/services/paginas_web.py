import re
from urllib.parse import urljoin, urlparse

import requests

TEMPO_DE_LEITURA = 15
CABECALHOS = {"User-Agent": "Mozilla/5.0 (compatible; Axio Coder)"}

_META_CHARSET = re.compile(r'<meta[^>]+charset=["\']?([\w.:-]+)', re.I)
_ANCORA = re.compile(r'<a\b[^>]*?href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_TAGS = re.compile(r'<[^>]+>')
_SEM_TEXTO = frozenset(("none", "null", "here", "click here", "link", "aqui", "saiba mais", "veja mais"))


def _decodificar(resposta):
    bruto = resposta.content
    charset = (resposta.encoding or "").lower()
    if charset in ("", "iso-8859-1"):
        achado = _META_CHARSET.search(bruto[:4096].decode("ascii", "ignore"))
        charset = (achado.group(1) if achado else "") or resposta.apparent_encoding or "utf-8"
    try:
        return bruto.decode(charset, "replace")
    except LookupError:
        return bruto.decode("utf-8", "replace")


def _limpar_texto(trecho):
    return " ".join(_TAGS.sub(" ", trecho).split())


def _segmentos(caminho):
    return [p for p in caminho.split("/") if p]


def _em_comum_ate(url, referencia):
    meu, outro = _segmentos(urlparse(url).path), _segmentos(urlparse(referencia).path)
    comuns = 0
    for a, b in zip(meu, outro):
        if a != b:
            break
        comuns += 1
    return comuns


def _chave_de_ordem(url, referencia):
    return (-_em_comum_ate(url, referencia), len(_segmentos(urlparse(url).path)), url)


def ligacoes(url, limite=20):
    """Ligações da propria pagina (menu e navegacao), da mesma area primeiro."""
    try:
        resposta = requests.get(url, timeout=TEMPO_DE_LEITURA, headers=CABECALHOS)
    except requests.RequestException as erro:
        return [], f"falha de rede ({type(erro).__name__})"
    if resposta.status_code != 200:
        return [], f"HTTP {resposta.status_code}"

    html = _decodificar(resposta)
    alvo = urlparse(url)
    vistos, textos, achadas = set(), set(), []
    for casamento in _ANCORA.finditer(html):
        texto = _limpar_texto(casamento.group(2))
        if not texto or len(texto) > 90 or texto.lower() in textos or texto.lower() in _SEM_TEXTO:
            continue
        destino = urljoin(url, casamento.group(1)).split("#")[0]
        partes = urlparse(destino)
        if partes.scheme not in ("http", "https") or partes.netloc != alvo.netloc:
            continue
        if destino.rstrip("/") == url.rstrip("/") or destino in vistos:
            continue
        mesma_area = _em_comum_ate(destino, url) >= 2
        vistos.add(destino)
        textos.add(texto.lower())
        achadas.append({"texto": texto, "url": destino, "mesma_area": mesma_area})
    achadas.sort(key=lambda item: _chave_de_ordem(item["url"], url))
    return achadas[:max(1, int(limite or 20))], ""
