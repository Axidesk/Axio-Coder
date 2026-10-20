import hashlib
import html as html_lib
import os
import re
from urllib.parse import urljoin, urlparse

import requests

TEMPO_DE_LEITURA = 15
TEMPO_DA_IMAGEM = 20
CABECALHOS = {"User-Agent": "Mozilla/5.0 (compatible; Axio Coder)"}
SUFIXOS_DE_IMAGEM = (".png", ".jpg", ".jpeg", ".webp", ".gif")
NOMES_DECORATIVOS = ("logo", "icon", "favicon", "sprite", "avatar", "badge", "pixel")
TETO_DA_IMAGEM = 8 * 1024 * 1024

_META_CHARSET = re.compile(r'<meta[^>]+charset=["\']?([\w.:-]+)', re.I)
_ANCORA = re.compile(r'<a\b[^>]*?href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_TITULO = re.compile(r'<h([1-6])\b[^>]*\bid="([^"]+)"[^>]*>(.*?)</h\1>', re.S | re.I)
_IMAGEM = re.compile(r"<img\b[^>]*>", re.I)
_ATRIBUTO = re.compile(r'\b([\w-]+)\s*=\s*"([^"]*)"')
_TAGS = re.compile(r'<[^>]+>')
_COMENTARIO = re.compile(r"<!--.*?-->", re.S)
_RUIDO = re.compile(r"<(script|style|noscript|svg|canvas|template)\b.*?</\1\s*>", re.S | re.I)
_BLOCO = re.compile(
    r"</?(p|div|br|tr|li|h[1-6]|table|thead|tbody|section|article|header|footer|ul|ol|dl|dd|dt)\b[^>]*>",
    re.I,
)
_BLOCO_DE_NAVEGACAO = re.compile(
    r"<(ul|nav|aside|div)\b[^>]*\b(?:class|id)\s*=\s*\"[^\"]*(menu|nav|sidebar|breadcrumb)[^\"]*\"[^>]*>",
    re.I,
)
_TABELA = re.compile(r"<table\b.*?</table\s*>", re.S | re.I)
_LINHA_DA_TABELA = re.compile(r"<tr\b.*?</tr\s*>", re.S | re.I)
_CELULA = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]\s*>", re.S | re.I)
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


def _baixar(url):
    try:
        resposta = requests.get(url, timeout=TEMPO_DE_LEITURA, headers=CABECALHOS)
    except requests.RequestException as erro:
        return "", f"falha de rede ({type(erro).__name__})"
    if resposta.status_code != 200:
        return "", f"HTTP {resposta.status_code}"
    return _decodificar(resposta), ""


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


def _pasta(url, quantos=None):
    pedacos = _segmentos(urlparse(url).path)
    if os.path.splitext(pedacos[-1] if pedacos else "")[1]:
        pedacos = pedacos[:-1]
    if quantos is not None:
        pedacos = pedacos[quantos:]
    return "/".join(pedacos)


def _atributos(tag):
    return {nome.lower(): valor for nome, valor in _ATRIBUTO.findall(tag)}


def _secoes(html):
    vistas, achadas = set(), []
    for casamento in _TITULO.finditer(html):
        nivel, ident, bruto = int(casamento.group(1)), casamento.group(2), casamento.group(3)
        texto = _limpar_texto(bruto).strip("¶# ")
        if not texto or ident in vistas:
            continue
        vistas.add(ident)
        achadas.append({"nivel": nivel, "id": ident, "texto": texto})
    return achadas


def _imagens(html, url):
    alvo = urlparse(url)
    vistas, achadas = set(), []
    for tag in _IMAGEM.finditer(html):
        atributos = _atributos(tag.group(0))
        origem = atributos.get("src") or atributos.get("data-src") or ""
        if not origem:
            continue
        destino = urljoin(url, html_lib.unescape(origem)).split("?")[0]
        partes = urlparse(destino)
        if partes.scheme not in ("http", "https"):
            continue
        nome = os.path.basename(partes.path).lower()
        if partes.netloc != alvo.netloc and not nome.endswith(SUFIXOS_DE_IMAGEM):
            continue
        if not nome.endswith(SUFIXOS_DE_IMAGEM):
            continue
        if any(marca in nome for marca in NOMES_DECORATIVOS):
            continue
        if destino in vistas:
            continue
        vistas.add(destino)
        achadas.append({"texto": (atributos.get("alt") or atributos.get("title") or nome).strip(), "url": destino})
    return achadas


def _rotulos(html):
    """Todo texto de ligacao da pagina - tambem os de fora - para tirar o menu do corpo."""
    rotulos = []
    for casamento in _ANCORA.finditer(html):
        texto = _limpar_texto(casamento.group(2))
        if texto and len(texto) <= 90:
            rotulos.append(texto)
    return rotulos


def _titulo_da_pagina(html):
    """Texto do <title>: o nome do site repetido no topo nao acrescenta nada ao corpo."""
    casamento = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.IGNORECASE | re.DOTALL)
    return _limpar_texto(casamento.group(1)) if casamento else ""


def _ligacoes(html, url):
    alvo = urlparse(url)
    vistos, textos, achadas = set(), set(), []
    for casamento in _ANCORA.finditer(html):
        texto = _limpar_texto(casamento.group(2))
        if not texto or len(texto) > 90 or texto.lower() in textos or texto.lower() in _SEM_TEXTO:
            continue
        destino = urljoin(url, html_lib.unescape(casamento.group(1))).split("#")[0]
        partes = urlparse(destino)
        if partes.scheme not in ("http", "https") or partes.netloc != alvo.netloc:
            continue
        if destino.rstrip("/") == url.rstrip("/") or destino in vistos:
            continue
        vistos.add(destino)
        textos.add(texto.lower())
        achadas.append({
            "texto": texto,
            "url": destino,
            "comum": _em_comum_ate(destino, url),
            "pasta": _pasta(destino),
        })
    achadas.sort(key=lambda item: (-item["comum"], len(_segmentos(urlparse(item["url"]).path)), item["url"]))
    return achadas


def _texto_da_celula(bruto):
    base = " ".join(html_lib.unescape(_TAGS.sub(" ", bruto)).split())
    if base:
        return base
    alternativas = []
    for tag in _IMAGEM.finditer(bruto):
        atributos = _atributos(tag.group(0))
        rotulo = " ".join((atributos.get("alt") or atributos.get("title") or "").split())
        if rotulo and rotulo not in alternativas:
            alternativas.append(rotulo)
    return " ".join(alternativas)


def tabelas(html):
    """Tabelas do HTML cru: o conversor de markdown descarta celulas com imagem."""
    achadas = []
    for bruto in _TABELA.findall(_COMENTARIO.sub(" ", html)):
        linhas = []
        for linha_bruta in _LINHA_DA_TABELA.findall(bruto):
            celulas = [_texto_da_celula(celula) for celula in _CELULA.findall(linha_bruta)]
            if any(celulas):
                linhas.append(celulas)
        if sum(1 for linha in linhas for celula in linha if celula) >= 2:
            achadas.append(linhas)
    return achadas


def _fim_do_bloco(html, inicio, tag):
    padrao = re.compile(rf"</?{tag}\b[^>]*>", re.I)
    profundidade = 1
    for casamento in padrao.finditer(html, inicio):
        if casamento.group(0).startswith("</"):
            profundidade -= 1
            if profundidade == 0:
                return casamento.end()
        else:
            profundidade += 1
    return -1


def _sem_navegacao(html):
    """Tira os blocos de menu/sidebar: o que sobra e o miolo da pagina."""
    cortes = []
    for casamento in _BLOCO_DE_NAVEGACAO.finditer(html):
        if any(inicio <= casamento.start() < fim for inicio, fim in cortes):
            continue
        fim = _fim_do_bloco(html, casamento.end(), casamento.group(1).lower())
        if fim != -1:
            cortes.append((casamento.start(), fim))
    for inicio, fim in reversed(cortes):
        html = html[:inicio] + " " + html[fim:]
    return html


def texto(html):
    """Texto visivel da pagina, linha a linha, sem scripts, estilos e menus."""
    sem_ruido = _RUIDO.sub(" ", _COMENTARIO.sub(" ", _sem_navegacao(html)))
    linhas = []
    for linha in _BLOCO.sub("\n", sem_ruido).splitlines():
        juntada = " ".join(html_lib.unescape(_TAGS.sub(" ", linha)).split())
        if juntada:
            linhas.append(juntada)
    return "\n".join(linhas)


def mapa(url):
    """Menu, secoes, imagens, texto e tabelas da pagina, de um so pedido."""
    html, erro = _baixar(url)
    if erro:
        return {"ligacoes": [], "secoes": [], "imagens": [], "texto": "", "tabelas": [],
                "rotulos": [], "titulo": "", "erro": erro}
    return {
        "titulo": _titulo_da_pagina(html),
        "ligacoes": _ligacoes(html, url),
        "secoes": _secoes(html),
        "imagens": _imagens(html, url),
        "texto": texto(html),
        "tabelas": tabelas(html),
        "rotulos": _rotulos(html),
        "erro": "",
    }


def _nome_do_ficheiro(url):
    nome = os.path.basename(urlparse(url).path) or "imagem.png"
    limpo = re.sub(r"[^\w.-]+", "-", nome).strip("-.") or "imagem.png"
    return hashlib.sha1(url.encode("utf-8", "ignore")).hexdigest()[:10] + "-" + limpo


def _podar(destino, manter=40):
    try:
        ficheiros = [
            os.path.join(destino, nome)
            for nome in os.listdir(destino)
            if nome.lower().endswith(SUFIXOS_DE_IMAGEM)
        ]
    except OSError:
        return
    if len(ficheiros) <= manter:
        return
    ficheiros.sort(key=lambda caminho: os.path.getmtime(caminho))
    for antigo in ficheiros[: len(ficheiros) - manter]:
        try:
            os.remove(antigo)
        except OSError:
            pass


def gravar_imagens(imagens, destino, maximo=6):
    """Baixa as imagens da pagina para o disco, para poderem ser olhadas com tool_ver_imagem."""
    os.makedirs(destino, exist_ok=True)
    _podar(destino)
    gravadas, falhadas = [], []
    for item in imagens[:maximo]:
        caminho = os.path.join(destino, _nome_do_ficheiro(item["url"]))
        try:
            resposta = requests.get(item["url"], timeout=TEMPO_DA_IMAGEM, headers=CABECALHOS, stream=True)
            if resposta.status_code != 200:
                falhadas.append({"texto": item["texto"], "erro": f"HTTP {resposta.status_code}"})
                continue
            pedacos, total = [], 0
            for pedaco in resposta.iter_content(65536):
                pedacos.append(pedaco)
                total += len(pedaco)
                if total > TETO_DA_IMAGEM:
                    break
            if not pedacos:
                falhadas.append({"texto": item["texto"], "erro": "imagem vazia"})
                continue
            with open(caminho, "wb") as ficheiro:
                ficheiro.write(b"".join(pedacos))
        except requests.RequestException as erro:
            falhadas.append({"texto": item["texto"], "erro": type(erro).__name__})
            continue
        gravadas.append({"texto": item["texto"], "url": item["url"], "caminho": caminho, "bytes": total})
    return gravadas, falhadas
