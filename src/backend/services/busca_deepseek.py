import os
import re
from urllib.parse import parse_qs, urlparse

import requests

BASE = "https://api.deepseek.com"
LIMITE_DO_RESUMO = 700
LIMITE_DO_TEXTO = 12000
TEMPO_DE_BUSCA = 20
TEMPO_DE_EXTRAIR = 35
_ULTIMA_NOTA = ""


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


_PALAVRAS_EM_PORTUGUES = frozenset((
    "nao", "não", "para", "como", "erro", "esta", "está", "fazer", "instalar", "baixar",
    "preciso", "quero", "qual", "onde", "porque", "tambem", "também", "arquivo", "usando",
    "funciona", "exemplo", "servidor", "versao", "versão",
))
_PALAVRA_SIMPLES = re.compile(r"[a-zà-ÿ]+")
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


def _idioma_preferido(codigo, aceitos=("en", "pt")):
    if not codigo:
        return False
    base = codigo.split("-")[0]
    return any(base == preferido.split("-")[0] for preferido in aceitos)


_SEGMENTO_DE_VERSAO = re.compile(
    r"^(v?\d+(?:[._]\d+)*|latest|stable|current|dev|master|main|head|pr-\d+)$", re.I
)


def _sufixo_do_caminho(url, quantos=2):
    """O fim do caminho sem o prefixo de idioma nem a versao: /pt-br/3.16/library/x -> library/x."""
    segmentos = [s for s in (urlparse(url or "").path or "/").split("/") if s]
    uteis = []
    for segmento in segmentos:
        limpo = _EXTENSAO_NO_FIM.sub("", segmento)
        if not limpo or _SEGMENTO_DE_VERSAO.match(limpo):
            continue
        if limpo.lower() in _CODIGOS_DE_IDIOMA:
            continue
        uteis.append(limpo)
    return "/".join(uteis[-quantos:])


def _chave_de_variante(url, idioma=""):
    """Duas traducoes da mesma pagina caem no mesmo grupo quando o fim do caminho e o mesmo."""
    sufixo = _sufixo_do_caminho(url)
    if idioma and sufixo:
        return "idioma:" + sufixo
    partes = urlparse(url or "")
    caminho = _EXTENSAO_NO_FIM.sub("", (partes.path or "/").rstrip("/"))
    chave = partes.netloc + caminho
    if partes.query:
        chave += "?" + partes.query
    return chave


def _sem_variantes_de_idioma(resultados, query=""):
    """Uma pagina traduzida em cinco idiomas ocupa cinco lugares; fica a melhor variante."""
    aceitos = _idiomas_da_query(query)
    grupos, ordem = {}, []
    for indice, item in enumerate(resultados):
        url = item.get("url") or ""
        idioma = _idioma_declarado(url) or _idioma_do_texto(item.get("title") or "")
        chave = _chave_de_variante(url, idioma)
        if chave not in grupos:
            grupos[chave] = []
            ordem.append(chave)
        grupos[chave].append((idioma, indice, item))
    finais = []
    for chave in ordem:
        candidatos = grupos[chave]
        candidatos.sort(key=lambda t: (
            0 if _idioma_preferido(t[0], aceitos) else (1 if t[0] else 0.5),
            t[1],
        ))
        finais.append(candidatos[0][2])
    return finais


def _no_idioma_da_pergunta(resultados, query):
    """Uma pagina em polaco ou vietnamita nao tira o lugar a que esta no idioma da pergunta."""
    if _CJK.search(query or ""):
        return resultados

    aceitos = _idiomas_da_query(query)

    def peso(item):
        codigo = _idioma_declarado(item.get("url") or "") or _idioma_do_texto(item.get("title") or "")
        return 0 if (not codigo or _idioma_preferido(codigo, aceitos)) else 1

    return sorted(resultados, key=peso)


_TERMOS_VAZIOS = frozenset((
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas",
    "para", "pra", "por", "com", "um", "uma", "que", "se", "ao", "aos", "como", "mais", "sobre",
    "the", "and", "for", "with", "how", "what", "who", "why", "when", "where", "of", "to", "in",
    "on", "at", "is", "are", "be", "it", "this", "that", "from", "by", "or", "not",
    "el", "la", "los", "las", "del", "y", "en", "con", "una", "uno", "les", "des", "du", "et",
    "une", "der", "die", "das", "und", "mit", "fur", "von",
    "site", "lang", "after", "before",
))

_OPERADOR_NA_QUERY = re.compile(r"\b(?:site|after|before|lang):\S+", re.I)
_TERMO_NA_QUERY = re.compile(r"[0-9a-zA-ZÀ-ÿ][0-9a-zA-ZÀ-ÿ+#._-]{2,}")


def _distintivos(query):
    """O que a pergunta quer dizer sobre o assunto: fora os operadores e as palavras vazias."""
    texto = _OPERADOR_NA_QUERY.sub(" ", query or "")
    termos = []
    for bruto in _TERMO_NA_QUERY.findall(texto.lower()):
        limpo = bruto.strip("._-")
        if len(limpo) >= 3 and limpo not in _TERMOS_VAZIOS and limpo not in termos:
            termos.append(limpo)
    return termos


def _dominio(url):
    return (urlparse(url or "").netloc or "").lower().removeprefix("www.")


def _cobertura(item, termos):
    alvo = " ".join((
        item.get("title") or "", item.get("content") or "", item.get("url") or ""
    )).lower()
    return sum(1 for termo in termos if termo in alvo)


_CAMINHOS_DE_FORUM = (
    "/answers/", "/questions/", "/forum", "/forums/", "/community/", "/threads/",
    "/discussion", "/topic/", "stackoverflow.com/questions", "/issues/", "/comments/",
)
_PALAVRAS_DE_PROBLEMA = (
    "erro", "error", "falha", "fail", "corrigir", "crash", "exception", "traceback",
    "problema", "issue", "bug", "nao funciona", "not working", "dll", "exit code",
)


def _e_forum(item):
    endereco = (item.get("url") or "").lower()
    return any(caminho in endereco for caminho in _CAMINHOS_DE_FORUM)


def _pede_ajuda_com_problema(query):
    alvo = (query or "").lower()
    return any(palavra in alvo for palavra in _PALAVRAS_DE_PROBLEMA)


def _da_fonte_do_projeto(item, termos):
    """O dominio que carrega o nome do proprio projeto (docs.vulkan.org para 'vulkan')."""
    dominio = _dominio(item.get("url") or "")
    return bool(dominio) and any(termo in dominio for termo in termos)


def _por_utilidade(resultados, query):
    """A fonte do proprio projeto sobe, o resultado fora do assunto desce, e o forum idem.

    So reordena: a ordem relativa de quem tem o mesmo peso fica a da API, que e a que
    conhece o ranking. Nada e apagado aqui.
    """
    termos = _distintivos(query)
    if not termos:
        return resultados
    minimo = max(1, (len(termos) + 1) // 2)
    aceita_forum = _pede_ajuda_com_problema(query)

    def peso(par):
        indice, item = par
        cobertura = _cobertura(item, termos)
        ponto = 0
        if cobertura >= minimo:
            ponto += 2
        elif cobertura == 0:
            ponto -= 2
        if _da_fonte_do_projeto(item, termos):
            ponto += 1
        if not aceita_forum and _e_forum(item):
            ponto -= 1
        return (-ponto, indice)

    return [item for _, item in sorted(enumerate(resultados), key=peso)]


_LANG_NA_QUERY = re.compile(r"\blang:([a-z]{2}(?:[-_][a-z]{2,4})?)", re.I)

_ESCRITAS = (
    ("ja", re.compile(r"[぀-ヿ]")),
    ("ko", re.compile(r"[가-힯]")),
    ("zh", re.compile(r"[㐀-䶿一-鿿]")),
    ("ru", re.compile(r"[Ѐ-ӿ]")),
    ("ar", re.compile(r"[؀-ۿ]")),
    ("he", re.compile(r"[֐-׿]")),
    ("el", re.compile(r"[Ͱ-Ͽ]")),
    ("th", re.compile(r"[฀-๿]")),
)


_MARCAS_EM_INGLES = frozenset((
    "the", "and", "of", "to", "is", "are", "with", "for", "this", "that", "from", "you",
    "your", "will", "can", "not", "how", "what", "when", "have", "has", "been", "which",
))
_MARCAS_EM_PORTUGUES = frozenset((
    "que", "para", "como", "nao", "não", "uma", "dos", "das", "com", "esta", "está", "seu",
    "sua", "pelo", "pela", "voce", "você", "mais", "sem", "aos", "foi", "sao", "são", "tem",
))


def _idiomas_pedidos(query):
    return [m.group(1).lower().replace("_", "-") for m in _LANG_NA_QUERY.finditer(query or "")]


def _idiomas_da_query(query):
    """Uma pergunta em portugues quer portugues ou ingles; uma em ingles nao quer alemao."""
    palavras = set(_PALAVRA_SIMPLES.findall((query or "").lower()))
    if palavras & _PALAVRAS_EM_PORTUGUES:
        return ("pt", "en")
    return ("en", "pt")


def _idioma_latino(texto):
    """Portugues ou ingles pelo peso das palavras funcionais: um titulo curto nao decide."""
    palavras = _PALAVRA_SIMPLES.findall((texto or "").lower())
    if len(palavras) < 12:
        return ""
    portugues = sum(1 for p in palavras if p in _MARCAS_EM_PORTUGUES)
    ingles = sum(1 for p in palavras if p in _MARCAS_EM_INGLES)
    if max(portugues, ingles) < 3:
        return ""
    return "pt" if portugues > ingles else "en"


def _idioma_do_texto(texto):
    """O idioma que se ve na escrita (para quem nao declara idioma no endereco)."""
    for codigo, padrao in _ESCRITAS:
        if padrao.search(texto or ""):
            return codigo
    return _idioma_latino(texto)


def _mesmo_idioma(um, outro):
    if not um or not outro:
        return False
    return um.split("-")[0] == outro.split("-")[0]


def _por_idioma_pedido(resultados, query):
    """A API ignora o lang:: quem filtra e este codigo, pelo idioma que a pagina declara."""
    pedidos = _idiomas_pedidos(query)
    if not pedidos:
        return resultados, ""

    certos, sem_idioma, outros = [], [], []
    for item in resultados:
        amostra = (item.get("title") or "") + " " + (item.get("content") or "")[:400]
        codigo = _idioma_declarado(item.get("url") or "") or _idioma_do_texto(amostra)
        if any(_mesmo_idioma(codigo, pedido) for pedido in pedidos):
            certos.append(item)
        elif not codigo:
            sem_idioma.append(item)
        else:
            outros.append(item)

    alvo = ", ".join(pedidos)
    if not certos:
        if sem_idioma:
            return sem_idioma, (
                f"lang:{alvo}: nenhuma destas fontes declara idioma no endereco, logo o filtro "
                f"nao pode ser verificado (a API ignora o operador) — ficaram so as que nao declaram."
            )
        return resultados, (
            f"lang:{alvo} nao pode ser cumprido: todas as fontes vieram noutro idioma "
            f"(a API ignora o operador)."
        )
    nota = f"lang:{alvo} aplicado localmente: {len(certos)} no idioma pedido"
    if sem_idioma:
        nota += f", {len(sem_idioma)} sem idioma declarado"
    if outros:
        nota += f", {len(outros)} fora do idioma descartado(s)"
    return certos + sem_idioma, nota + "."


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
        "count": min(alvo + 10, 50),
        "need_content": bool(ler),
    }
    dados = _pedido("/v1/tools/search", corpo, TEMPO_DE_BUSCA)
    itens = [_resultado(item, ler) for item in (dados.get("results") or []) if item.get("url")]
    itens = _sem_variantes_de_idioma(itens, consulta)
    itens = _no_idioma_da_pergunta(itens, consulta)
    itens = _na_frente_as_latinas(itens, consulta)
    itens, nota = _por_idioma_pedido(itens, consulta)
    itens = _por_utilidade(itens, consulta)
    global _ULTIMA_NOTA
    _ULTIMA_NOTA = nota
    return itens[:alvo]


def ultima_nota():
    """O que os filtros locais fizeram na ultima busca (idioma pedido, fonte descartada)."""
    return _ULTIMA_NOTA


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
