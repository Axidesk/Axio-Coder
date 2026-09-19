import os
import re
from urllib.parse import urlparse

from src.backend.state import caminho_estado_projeto, emit_event, estado
from src.backend.tools.registry import register

_tavily_client = None
_tavily_client_key = None

def _get_tavily_api_key():
    try:
        from src.backend.services.settings import load_settings
        return (load_settings().get("tavily") or {}).get("api_key", "") or os.getenv("TAVILY_API_KEY", "")
    except Exception:
        return os.getenv("TAVILY_API_KEY", "")

def tavily_configurada():
    if not _get_tavily_api_key():
        return False
    try:
        from src.backend.services.settings import load_settings
        tv = (load_settings().get("tavily") or {})
    except Exception:
        tv = {}
    if "enabled" in tv:
        return bool(tv.get("enabled"))
    return True

def _get_tavily_client():
    global _tavily_client, _tavily_client_key
    api_key = _get_tavily_api_key()
    if not api_key:
        _tavily_client = None
        _tavily_client_key = None
        return None
    if _tavily_client is not None and _tavily_client_key == api_key:
        return _tavily_client
    from tavily import TavilyClient
    _tavily_client = TavilyClient(api_key=api_key)
    _tavily_client_key = api_key
    return _tavily_client
DOMINIOS_OFICIAIS = (
    "developer.mozilla.org", "docs.python.org", "nodejs.org", "pypi.org", "npmjs.com",
    "learn.microsoft.com", "developer.apple.com", "developer.android.com", "w3.org",
    "ietf.org", "rfc-editor.org", "sqlite.org", "kubernetes.io", "git-scm.com",
    "kernel.org", "rust-lang.org", "go.dev", "php.net", "ruby-lang.org", "docker.com",
    "postgresql.org", "mysql.com", "mongodb.com", "redis.io", "readthedocs.io",
    "buildingsmart.org", "iso.org", "iec.ch", "arxiv.org", "doi.org",
)

DOMINIOS_DE_CODIGO = ("github.com", "gitlab.com", "bitbucket.org")

DOMINIOS_FRACOS = (
    "linkedin.com", "medium.com", "dev.to", "blogspot.", "wordpress.com", "quora.com",
    "reddit.com", "csdn.net", "juejin.cn", "zhihu.com", "qiita.com", "zenn.dev",
    "cnblogs.com", "segmentfault.com", "tutorialspoint.com", "javatpoint.com",
    "geeksforgeeks.org", "w3schools.com", "programiz.com", "bilibili.com", "scribd.com",
    "slideshare.net",
)

ETIQUETAS_DE_FONTE = {
    "oficial": "OFICIAL",
    "codigo": "REPOSITORIO",
    "comunidade": "COMUNIDADE",
    "blog": "BLOG (fonte fraca)",
    "outra": "NAO CLASSIFICADA (verificar origem)",
}

def _dominio(url):
    return (urlparse(url or "").netloc or "").lower().removeprefix("www.")

def _nivel_da_fonte(url):
    """Confianca da fonte: oficial, codigo, comunidade, blog ou outra (nao classificada)."""
    dominio = _dominio(url)
    if not dominio:
        return "outra"
    if dominio.startswith(("docs.", "developer.", "learn.")):
        return "oficial"
    if dominio.startswith("blog."):
        return "blog"
    if any(d in dominio for d in DOMINIOS_OFICIAIS):
        return "oficial"
    if any(d in dominio for d in DOMINIOS_DE_CODIGO):
        return "codigo"
    if "stackexchange" in dominio or dominio.startswith("stackoverflow."):
        return "comunidade"
    if any(d in dominio for d in DOMINIOS_FRACOS):
        return "blog"
    return "outra"

def _lista_de_dominios(texto):
    limpos = []
    for bruto in re.split(r"[,;\s]+", texto or ""):
        bruto = bruto.strip().lower()
        if not bruto:
            continue
        dominio = (urlparse(bruto if "//" in bruto else "//" + bruto).netloc or bruto).strip("/")
        dominio = dominio.removeprefix("www.")
        if dominio and dominio not in limpos:
            limpos.append(dominio)
    return limpos

def _aviso_de_fontes(niveis):
    """Aviso quando NENHUMA fonte e oficial ou repositorio: refazer na fonte primaria.

    Fonte nao classificada conta como fraca: cair fora das tabelas nao e atestado de
    confianca, e um blog aleatorio nao se distingue de um site serio sem a etiqueta.
    """
    if not niveis or any(n in ("oficial", "codigo") for n in niveis):
        return ""
    return (
        "\n⚠️ NENHUMA fonte oficial ou repositorio entre as encontradas.\n"
        "Nao afirme facto tecnico a partir destas fontes: repita a pesquisa com 'dominios' apontado\n"
        "a documentacao oficial (ex: dominios=\"docs.python.org\") ou use 'url_especifica' na pagina oficial.\n"
    )
def _conteudo_ilegivel(conteudo):
    """Detecta se o conteúdo extraído está ilegível/garbled (ex: Shiki, JS toggles).
    Retorna (bool, str): (é_ilegivel, motivo)"""
    if not conteudo or len(conteudo) < 50:
        return False, ""
    
    chars = len(conteudo)
    espacos = conteudo.count(' ')
    densidade_espacos = espacos / chars if chars > 0 else 0
    
    tem_view_code = 'View Code' in conteudo or 'View Format' in conteudo
    tem_copy = 'Copy' in conteudo
    
    tags_html = conteudo.count('<span') + conteudo.count('<div') + conteudo.count('<code') + conteudo.count('</span>') + conteudo.count('</div>')
    densidade_tags = tags_html / (chars / 1000) if chars > 0 else 0
    
    trechos = conteudo[:5000]
    coladas = re.findall(r'[A-Za-z]{20,}', trechos)
    palavras_coladas = len(coladas)
    
    linhas = conteudo.split('\n')
    imports_duplicados = 0
    for linha in linhas:
        imports_na_linha = re.findall(r'import\s+\{[^}]+\}\s+from\s+["\'][^"\']+["\']', linha)
        if len(imports_na_linha) >= 3:
            imports_duplicados += 1
    
    jsx_garbled = len(re.findall(r'<\s+[A-Z][a-zA-Z]*\s*>?\s*[A-Z]', conteudo[:10000]))
    
    tags_duplicadas = len(re.findall(r'</?(\w+)\s*>?\s*</?\s*\1\s*>', conteudo[:10000]))
    
    motivos = []
    sinais_fortes = 0

    if densidade_espacos < 0.05:
        sinais_fortes += 1
        motivos.append(f"densidade de espaços muito baixa ({densidade_espacos:.1%})")

    if tem_view_code and tem_copy and densidade_espacos < 0.08:
        sinais_fortes += 1
        motivos.append("código colapsado atrás de toggle JS (View Code/Copy)")

    if densidade_tags > 15:
        sinais_fortes += 1
        motivos.append(f"alta densidade de tags HTML ({densidade_tags:.0f}/1k chars) — provável Shiki/syntax highlighter")

    if imports_duplicados >= 1:
        sinais_fortes += 1
        motivos.append(f"imports duplicados/colados ({imports_duplicados} linhas com 3+ imports) — Shiki garbled")

    if jsx_garbled >= 3:
        sinais_fortes += 1
        motivos.append(f"JSX corrompido ({jsx_garbled} tags com espaço após '<') — artefato Shiki")

    if tags_duplicadas >= 4:
        sinais_fortes += 1
        motivos.append(f"tags React duplicadas consecutivas ({tags_duplicadas} ocorrências) — Shiki garbled")

    tokens_analise = trechos.split() or [""]
    fracao_coladas = palavras_coladas / len(tokens_analise)
    if fracao_coladas >= 0.3:
        sinais_fortes += 1
        motivos.append(f"muitas palavras coladas ({palavras_coladas} sequências, {fracao_coladas:.0%} dos tokens)")

    if sinais_fortes > 0:
        return True, "; ".join(motivos)
    return False, ""
@register(
    "tool_buscar_web",
    "Pesquisa na internet (Tavily) ou extrai uma URL específica. 'query' busca por termo e 'url_especifica' extrai uma página. Cada fonte volta etiquetada por confiança (OFICIAL, REPOSITORIO, COMUNIDADE, BLOG): sem nenhuma OFICIAL, repita a busca com 'dominios' apontado à documentação do projeto. O conteúdo bruto fica em .axio/busca.txt.",
    {
        'query': {"tipo": "STRING", "desc": 'Termo de busca na web', "padrao": ""},
        'url_especifica': {"tipo": "STRING", "desc": 'URL específica para extrair conteúdo', "padrao": ""},
        'dominios': {"tipo": "STRING", "desc": 'Domínios a privilegiar, separados por vírgula (ex: docs.python.org,mozilla.org). Use para refazer a busca quando as fontes vierem de blogs.', "padrao": ""},
    },
    disponivel="web",
)
def tool_buscar_web(query="", url_especifica="", dominios=""):
    """Busca na web usando Tavily. Usa workflow 2 passos: Search → Extract (advanced) para maior fidelidade."""
    if not tavily_configurada():
        return "ERRO: navegação web desativada. Ative o globo em Configurações → APIs (ao lado do DeepSeek) e informe a chave Tavily."
    
    tavily_client = _get_tavily_client()
    if not tavily_client:
        return "ERRO: Cliente Tavily não inicializado."
    
    try:
        if url_especifica:
            emit_event("status", message=f"Navegando: {url_especifica}")
            resultado = tavily_client.extract(
                urls=[url_especifica],
                extract_depth="advanced"
            )
        elif query:
            emit_event("status", message=f"Navegando: pesquisando '{query[:60]}'...")
            opcoes = {"query": query, "max_results": 3, "search_depth": "advanced"}
            preferidos = _lista_de_dominios(dominios)
            if preferidos:
                opcoes["include_domains"] = preferidos
                opcoes["include_domains_mode"] = "prefer"
                emit_event("status", message=f"Navegando: privilegiando {', '.join(preferidos)}")
            search_resp = tavily_client.search(**opcoes)
            urls = [r['url'] for r in search_resp.get('results', []) if r.get('url')]
            if not urls:
                return "Nenhum resultado encontrado na web."
            
            emit_event("status", message=f"Navegando: {', '.join(urls)}")
            resultado = tavily_client.extract(
                urls=urls,
                extract_depth="advanced"
            )
        else:
            return "ERRO: Forneça 'query' ou 'url_especifica'."

        if not resultado or not resultado.get('results'):
            return "Nenhum resultado encontrado na web."

        contexto = ""
        contexto_debug = ""
        fontes = []
        fontes_ilegiveis = []
        
        for idx, res in enumerate(resultado.get('results', []), 1):
            url = res.get('url', '')
            fontes.append(url)
            conteudo = res.get('raw_content', '') or res.get('content', '')
            
            ilegivel, motivo = _conteudo_ilegivel(conteudo)
            
            contexto_debug += f"--- FONTE {idx}: {url} ---\n"
            if ilegivel:
                contexto_debug += f"⚠️ CONTEÚDO ILEGÍVEL DETECTADO: {motivo}\n"
                fontes_ilegiveis.append((idx, url, motivo))
            contexto_debug += f"{conteudo}\n\n"
            
            contexto += f"--- FONTE {idx}: {url} ---\n"
            if ilegivel:
                contexto += f"⚠️ CONTEÚDO ILEGÍVEL ({motivo}). NÃO INVENTE CÓDIGO — avise o usuário que esta fonte não pôde ser extraída corretamente.\n"
            contexto += f"{conteudo[:30000]}\n\n"
        
        estado["urls_navegadas_turno"].update(fontes)

        emit_event("tool_sources", urls=fontes)
        
        debug_path = caminho_estado_projeto("busca.txt")
        if debug_path:
            os.makedirs(os.path.dirname(debug_path), exist_ok=True)
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(contexto_debug)
        
        total = len(fontes)
        total_ilegiveis = len(fontes_ilegiveis)
        total_legiveis = total - total_ilegiveis
        
        resumo = f"✅ Busca concluída! {total} fonte(s) encontrada(s)"
        if total_ilegiveis > 0:
            resumo += f" — ⚠️ {total_ilegiveis} ILEGÍVEL(is)"
        resumo += ":\n"
        
        niveis = [_nivel_da_fonte(url) for url in fontes]

        for i, url in enumerate(fontes, 1):
            status_fonte = ""
            for fi, fu, fm in fontes_ilegiveis:
                if fi == i:
                    status_fonte = f" ⚠️ ILEGÍVEL: {fm}"
                    break
            etiqueta = ETIQUETAS_DE_FONTE.get(niveis[i - 1], "")
            marca = f" — {etiqueta}" if etiqueta else ""
            resumo += f"  [{i}] {url}{marca}{status_fonte}\n"

        resumo += _aviso_de_fontes(niveis)
        
        resumo += f"\n📄 Log COMPLETO salvo em '{debug_path or 'busca.txt'}'.\n"
        
        if total_ilegiveis > 0:
            resumo += f"\n⚠️ ATENÇÃO: {total_ilegiveis} de {total} fonte(s) tiveram conteúdo ILEGÍVEL.\n"
            resumo += f"Isso acontece em sites com renderização client-side pesada (Shiki, JS toggles).\n"
            resumo += f"O conteúdo dessas fontes NÃO pode ser usado para extrair código.\n"
            if total_legiveis == 0:
                resumo += f"🚫 NENHUMA fonte legível. NÃO INVENTE CÓDIGO — informe o usuário honestamente.\n"
            resumo += f"\n"
        
        resumo += "=== CONTEÚDO EXTRAÍDO (primeiros 30000 chars por fonte) ===\n" + contexto
        
        return resumo
        
    except Exception as e:
        return f"ERRO na busca web: {str(e)}"
