import os
import re
from urllib.parse import parse_qs, urlparse

import requests

BASE = "https://api.deepseek.com"
LIMITE_DO_RESUMO = 700
LIMITE_DO_TEXTO = 12000
TEMPO_DE_BUSCA = 20
TEMPO_DE_EXTRAIR = 35


class ErroDoProvedor(Exception):
    def __init__(self, mensagem, codigo=0):
        super().__init__(mensagem)
        self.codigo = codigo


def _chave():
    chave = ""
    try:
        from src.backend.services.settings import load_settings
        chave = (load_settings().get("deepseek") or {}).get("api_key", "")
    except Exception:
        chave = ""
    return (chave or os.getenv("DEEPSEEK_API_KEY", "")).strip()


def configurada():
    return bool(_chave())


def _mensagem_de_erro(resposta):
    try:
        dados = resposta.json()
    except ValueError:
        dados = {}
    erro = (dados or {}).get("error") or {}
    return erro.get("message") or f"HTTP {resposta.status_code}"


def _pedido(caminho, corpo, tempo):
    chave = _chave()
    if not chave:
        raise ErroDoProvedor("chave da DeepSeek ausente", 401)
    try:
        resposta = requests.post(
            BASE + caminho,
            headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
            json=corpo,
            timeout=tempo,
        )
    except requests.RequestException as erro:
        raise ErroDoProvedor(f"falha de rede ({type(erro).__name__})") from erro
    if resposta.status_code != 200:
        raise ErroDoProvedor(_mensagem_de_erro(resposta), resposta.status_code)
    try:
        return resposta.json() or {}
    except ValueError as erro:
        raise ErroDoProvedor("a resposta nao e JSON", resposta.status_code) from erro


def _consulta_com_dominios(query, dominios):
    if not dominios:
        return query
    return query + " " + " OR ".join(f"site:{dominio}" for dominio in dominios)


_DATA_SEM_MES = re.compile(r"\b(after|before):(\d{4})(?![\d-])")


def _normalizar_datas(query):
    """O after:2026 e lido como 'depois de 2026 inteiro' e devolve zero resultados."""
    def troca(achado):
        operador, ano = achado.group(1), achado.group(2)
        return f"{operador}:{ano}-01-01" if operador == "after" else f"{operador}:{ano}-12-31"

    return _DATA_SEM_MES.sub(troca, query)


_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")


def _na_frente_as_latinas(itens, query):
    """Uma query em alfabeto latino nao quer a pagina em chines a ocupar um dos cinco lugares."""
    if _CJK.search(query or ""):
        return itens
    latinas = [item for item in itens if not _CJK.search(item.get("title") or "")]
    outras = [item for item in itens if _CJK.search(item.get("title") or "")]
    return latinas + outras


_IDIOMAS_PREFERIDOS = ("en", "pt-br", "pt", "es", "fr", "de", "it")
_CODIGOS_DE_IDIOMA = frozenset((
    "af", "ar", "az", "be", "bg", "bn", "bs", "ca", "cs", "cy", "da", "de", "el", "en",
    "eo", "es", "et", "eu", "fa", "fi", "fr", "ga", "gl", "gu", "he", "hi", "hr", "hu",
    "hy", "id", "is", "it", "ja", "ka", "kk", "km", "kn", "ko", "lt", "lv", "mk", "ml",
    "mn", "mr", "ms", "mt", "nb", "ne", "nl", "nn", "no", "pa", "pl", "pt", "ro", "ru",
    "si", "sk", "sl", "sq", "sr", "sv", "sw", "ta", "te", "th", "tl", "tr", "uk", "ur",
    "uz", "vi", "zh", "zu",
))
_PARAMETROS_DE_IDIOMA = ("hl", "lang", "locale", "language")
_SEGMENTO_DE_IDIOMA = re.compile(r"^/([a-z]{2}(?:[-_][a-z]{2,4})?)(?=/|$)", re.I)
_EXTENSAO_NO_FIM = re.compile(r"\.(html?|php|aspx?)$", re.I)


def _idioma_declarado(url):
    """O idioma que a propria pagina declara: no parametro (hl=, lang=) ou no inicio do caminho."""
    partes = urlparse(url or "")
    for nome in _PARAMETROS_DE_IDIOMA:
        valores = parse_qs(partes.query).get(nome)
        if valores and valores[0]:
            codigo = valores[0].lower().replace("_", "-")
            if codigo.split("-")[0] in _CODIGOS_DE_IDIOMA:
                return codigo
    achado = _SEGMENTO_DE_IDIOMA.match(partes.path or "")
    if achado:
        codigo = achado.group(1).lower().replace("_", "-")
        if codigo.split("-")[0] in _CODIGOS_DE_IDIOMA:
            return codigo
    return ""


def _idioma_preferido(codigo):
    if not codigo:
        return False
    base = codigo.split("-")[0]
    return any(base == preferido.split("-")[0] for preferido in _IDIOMAS_PREFERIDOS)


def _chave_de_variante(url):
    """Duas traducoes da mesma pagina caem no mesmo grupo quando o caminho e o mesmo."""
    partes = urlparse(url or "")
    caminho = _EXTENSAO_NO_FIM.sub("", (partes.path or "/").rstrip("/"))
    if _idioma_declarado(url) and caminho.count("/") >= 2:
        return "idioma:" + caminho
    chave = partes.netloc + caminho
    if partes.query:
        chave += "?" + partes.query
    return chave


def _sem_variantes_de_idioma(resultados):
    """Uma pagina traduzida em cinco idiomas ocupa cinco lugares; fica a melhor variante."""
    grupos, ordem = {}, []
    for indice, item in enumerate(resultados):
        chave = _chave_de_variante(item.get("url") or "")
        if chave not in grupos:
            grupos[chave] = []
            ordem.append(chave)
        grupos[chave].append((_idioma_declarado(item.get("url") or ""), indice, item))
    finais = []
    for chave in ordem:
        candidatos = grupos[chave]
        candidatos.sort(key=lambda t: (
            0 if _idioma_preferido(t[0]) else (1 if t[0] else 0.5),
            t[1],
        ))
        finais.append(candidatos[0][2])
    return finais


def _no_idioma_da_pergunta(resultados, query):
    """Uma pagina em polaco ou vietnamita nao tira o lugar a que esta no idioma da pergunta."""
    if _CJK.search(query or ""):
        return resultados

    def peso(item):
        codigo = _idioma_declarado(item.get("url") or "")
        return 0 if (not codigo or _idioma_preferido(codigo)) else 1

    return sorted(resultados, key=peso)


def _resultado(item, ler=False):
    titulo = (item.get("title") or "").strip()
    resumo = (item.get("summary") or item.get("snippet") or "").strip()
    if ler:
        inteiro = (item.get("content") or "").strip() or resumo
        conteudo = inteiro[:LIMITE_DO_TEXTO]
    else:
        inteiro = f"# {titulo}\n{resumo}" if titulo else resumo
        conteudo = inteiro[:LIMITE_DO_RESUMO]
    return {
        "url": item.get("url") or "",
        "title": titulo,
        "content": conteudo,
        "debug_content": inteiro,
        "authority": item.get("authority"),
        "date": item.get("date") or "",
        "site_name": item.get("site_name") or "",
        "rerank_score": item.get("rerank_score"),
    }


def pesquisar(query, count=5, dominios=None, ler=False):
    """Search da DeepSeek, devolvendo os resultados no formato dos da Tavily."""
    alvo = max(1, min(int(count or 5), 50))
    consulta = _normalizar_datas(_consulta_com_dominios(query, dominios or []))
    corpo = {
        "query": consulta,
        "count": min(alvo + 5, 50),
        "need_content": bool(ler),
    }
    dados = _pedido("/v1/tools/search", corpo, TEMPO_DE_BUSCA)
    itens = [_resultado(item, ler) for item in (dados.get("results") or []) if item.get("url")]
    itens = _sem_variantes_de_idioma(itens)
    itens = _no_idioma_da_pergunta(itens, consulta)
    itens = _na_frente_as_latinas(itens, consulta)
    return itens[:alvo]


def extrair(url):
    """Fetch da DeepSeek: devolve a pagina em Markdown."""
    dados = _pedido("/v1/tools/fetch", {"url": url}, TEMPO_DE_EXTRAIR)
    conteudo = (dados.get("content") or "").strip()
    if not conteudo:
        raise ErroDoProvedor("a pagina nao devolveu conteudo", 404)
    return {
        "url": url,
        "title": (dados.get("title") or "").strip(),
        "content": conteudo,
        "debug_content": conteudo,
    }
