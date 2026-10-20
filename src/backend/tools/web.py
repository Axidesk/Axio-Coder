import json
import os
import re
from urllib.parse import urlparse

from src.backend.config import caminho_data
from src.backend.services import busca_deepseek
from src.backend.state import emit_event, estado
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

_NOMES_DOS_PROVEDORES = {"tavily": "Tavily", "deepseek": "DeepSeek"}

def busca_configurada():
    """Existe pelo menos um provedor de busca pronto a usar."""
    return tavily_configurada() or busca_deepseek.configurada()

def _ordem_dos_provedores():
    """Provedores a tentar, com o preferido em primeiro e o outro como rede."""
    from src.backend.services.settings import provedor_de_busca
    prontos = []
    if tavily_configurada():
        prontos.append("tavily")
    if busca_deepseek.configurada():
        prontos.append("deepseek")
    preferido = provedor_de_busca()
    if preferido in prontos:
        return [preferido] + [p for p in prontos if p != preferido]
    return prontos

def _nomes_dos_provedores(lista):
    return ", ".join(_NOMES_DOS_PROVEDORES.get(p, p) for p in lista if p)

DOMINIOS_OFICIAIS = (
    "developer.mozilla.org", "docs.python.org", "nodejs.org", "pypi.org", "npmjs.com",
    "learn.microsoft.com", "developer.apple.com", "developer.android.com", "w3.org",
    "ietf.org", "rfc-editor.org", "sqlite.org", "kubernetes.io", "git-scm.com",
    "kernel.org", "rust-lang.org", "go.dev", "php.net", "ruby-lang.org", "docker.com",
    "postgresql.org", "mysql.com", "mongodb.com", "redis.io", "readthedocs.io",
    "buildingsmart.org", "iso.org", "iec.ch", "arxiv.org", "doi.org",
)

DOMINIOS_DE_CODIGO = (
    "github.com", "githubusercontent.com", "github.io", "gist.github.com",
    "gitlab.com", "bitbucket.org", "codeberg.org", "gitea.com", "sourceforge.net",
    "sr.ht", "gitee.com",
)

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

def _motivo_da_falha(resultado):
    """Diz PORQUE uma extracao nao trouxe nada, em vez de responder so 'nenhum resultado'."""
    if not resultado:
        return "a API nao devolveu resposta"
    falhas = resultado.get("failed_results") or []
    if falhas:
        return "; ".join(
            f"{f.get('url', '?')}: {f.get('error', 'erro nao informado')}" for f in falhas
        )
    return "a API respondeu sem resultados e sem motivo declarado"

_BLOCOS_DE_NAVEGACAO = (
    ("Skip to content", "Repository files navigation"),
    ("Skip to content", "File metadata and controls"),
    ("Skip to content", "Footer"),
)

def _sem_navegacao_do_repositorio(conteudo):
    """Tira o menu do GitHub que vem agarrado ao README de qualquer repositorio.

    Medido a 2026-10-18: o README do GaussianSplats3D chegou precedido de metade da
    navegacao da pagina, e o conteudo util ficou escondido no meio disso. O corte so
    acontece quando o bloco e grande: numa pagina que apenas MENCIONE o texto, nada
    e removido.
    """
    texto = conteudo or ""
    for inicio, fim in _BLOCOS_DE_NAVEGACAO:
        abertura = texto.find(inicio)
        if abertura < 0:
            continue
        fecho = texto.find(fim, abertura)
        if fecho < 0 or fecho - abertura < 1500:
            continue
        texto = texto[:abertura] + texto[fecho:]
    return texto

def _conteudo_ilegivel(conteudo):
    """Detecta se o conteúdo extraído está ilegível/garbled (ex: Shiki, JS toggles).
    Retorna (bool, str): (é_ilegivel, motivo)"""
    if not conteudo or len(conteudo) < 50:
        return False, ""

    texto = conteudo.strip()
    if texto[:1] in "{[":
        try:
            json.loads(texto)
            return False, ""
        except (ValueError, TypeError):
            pass
    
    chars = len(conteudo)
    sem_urls = re.sub(r'https?://\S+', '', conteudo)
    base_espacos = len(sem_urls)
    densidade_espacos = sem_urls.count(' ') / base_espacos if base_espacos > 0 else 0
    
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


def _extrair_cru(tavily_client, endereco):
    if "?" in endereco:
        return None
    try:
        resposta = tavily_client.extract(urls=[endereco + "?action=raw"], extract_depth="advanced")
    except Exception:
        return None
    achados = (resposta or {}).get('results') or []
    if not achados:
        return None
    for item in achados:
        item['url'] = endereco
    return {"results": achados}


def _extrair_tavily(endereco):
    cliente = _get_tavily_client()
    if not cliente:
        raise RuntimeError("cliente Tavily nao inicializado")
    resultado = cliente.extract(urls=[endereco], extract_depth="advanced")
    achados = (resultado or {}).get("results") or []
    if achados:
        return achados[0]
    cru = _extrair_cru(cliente, endereco)
    achados = (cru or {}).get("results") or []
    if achados:
        return achados[0]
    raise RuntimeError(_motivo_da_falha(resultado))


def _extrair_uma(endereco):
    ultimo = ""
    for provedor in _ordem_dos_provedores():
        try:
            if provedor == "tavily":
                item = _extrair_tavily(endereco)
            else:
                item = busca_deepseek.extrair(endereco)
        except Exception as erro:
            ultimo = str(erro)
            continue
        if item and item.get("content"):
            return item, provedor, ""
        ultimo = "o extrator nao devolveu conteudo"
    return None, "", ultimo or "nenhum provedor de busca configurado"


def _extrair_paginas(enderecos):
    itens, falhados, origens = [], [], []
    for endereco in enderecos:
        item, provedor, erro = _extrair_uma(endereco)
        if item:
            itens.append(item)
            if provedor and provedor not in origens:
                origens.append(provedor)
        else:
            falhados.append({"url": endereco, "error": erro})
    return {"results": itens, "failed_results": falhados}, origens, falhados


def _pesquisar_tavily(query, dominios):
    cliente = _get_tavily_client()
    if not cliente:
        raise RuntimeError("cliente Tavily nao inicializado")
    opcoes = {"query": query, "max_results": 3, "search_depth": "advanced"}
    preferidos = _lista_de_dominios(dominios)
    if preferidos:
        opcoes["include_domains"] = preferidos
        opcoes["include_domains_mode"] = "prefer"
        emit_event("status", message=f"Navegando: privilegiando {', '.join(preferidos)}")
    busca = cliente.search(**opcoes)
    urls = [r["url"] for r in busca.get("results", []) if r.get("url")]
    if not urls:
        return {"results": []}
    emit_event("status", message=f"Navegando: {', '.join(urls)}")
    return cliente.extract(urls=urls, extract_depth="advanced") or {"results": []}


def _pesquisar(query, dominios):
    falhas = []
    for provedor in _ordem_dos_provedores():
        nome = _NOMES_DOS_PROVEDORES.get(provedor, provedor)
        emit_event("status", message=f"Navegando: pesquisando '{query[:60]}' pelo {nome}")
        try:
            if provedor == "tavily":
                resultado = _pesquisar_tavily(query, dominios)
            else:
                resultado = {
                    "results": busca_deepseek.pesquisar(
                        query, count=5, dominios=_lista_de_dominios(dominios)
                    )
                }
        except Exception as erro:
            falhas.append((provedor, str(erro)))
            continue
        if resultado.get("results"):
            return resultado, [provedor], falhas
        falhas.append((provedor, "nenhum resultado"))
    return {"results": []}, [], falhas


def _texto_das_falhas(falhas):
    linhas = ["Nenhum resultado encontrado na web."]
    for provedor, motivo in falhas:
        linhas.append(f"  {_NOMES_DOS_PROVEDORES.get(provedor, provedor)}: {motivo}")
    linhas.append(
        "Se o Tavily ficou sem cota, escolha a busca da DeepSeek em Configuracoes -> APIs -> Busca na web."
    )
    return "\n".join(linhas)


def _termos(filtro):
    return [p.strip().lower() for linha in (filtro or "").splitlines() for p in linha.split("|") if p.strip()]


def _nivel_do_resultado(res):
    autoridade = res.get("authority")
    if isinstance(autoridade, int) and autoridade >= 3:
        return "oficial"
    return _nivel_da_fonte(res.get("url", ""))


@register(
    "tool_buscar_web",
    "Pesquisa na internet (Tavily ou DeepSeek) ou extrai uma URL específica. 'query' busca por termo e 'url_especifica' extrai uma página. Cada fonte volta etiquetada por confiança (OFICIAL, REPOSITORIO, COMUNIDADE, BLOG): sem nenhuma OFICIAL, repita a busca com 'dominios' apontado à documentação do projeto. Na busca da DeepSeek o resultado vem em resumos: para o texto completo de uma página, peça-a em 'url_especifica' (o Fetch devolve Markdown). O conteúdo bruto fica em data/busca.txt. Com 'filtro' (um termo por linha, ex: Sigurd|Sells) o conteúdo devolvido fica reduzido às linhas que contêm algum desses termos, com a contagem — o texto integral continua no ficheiro. Use-o sempre que só lhe interessar uma parte da página. Aceita VÁRIOS pedidos numa só chamada: um termo por linha em 'query' (uma busca por linha) ou uma URL por linha em 'url_especifica' (uma única extração para todas) — o resultado vem agrupado por pedido.",
    {
        'query': {"tipo": "STRING", "desc": 'Termo de busca na web. Vários assuntos? um por linha: faz uma busca para cada e agrupa o resultado.', "padrao": ""},
        'url_especifica': {"tipo": "STRING", "desc": 'URL específica para extrair conteúdo. Várias páginas? uma por linha, numa só extração.', "padrao": ""},
        'dominios': {"tipo": "STRING", "desc": 'Domínios a privilegiar, separados por vírgula (ex: docs.python.org,mozilla.org). Use para refazer a busca quando as fontes vierem de blogs.', "padrao": ""},
        'filtro': {"tipo": "STRING", "desc": 'Mostra só as linhas do conteúdo extraído que contêm algum destes termos (um por linha, sem distinguir maiúsculas). O texto integral fica em data/busca.txt — use o filtro para não encher o contexto com uma página inteira.', "padrao": ""},
    },
    disponivel="web",
)
def tool_buscar_web(query="", url_especifica="", dominios="", filtro=""):
    """Busca na web pelo provedor escolhido e extrai paginas por URL."""
    if not busca_configurada():
        return ("ERRO: navegacao web desativada. Ative a chave do DeepSeek ou da Tavily em "
                "Configuracoes -> APIs e escolha o provedor em 'Busca na web'.")

    pedidos = [linha.strip() for linha in query.splitlines() if linha.strip()]
    if len(pedidos) > 1 and not url_especifica:
        partes = []
        for indice, termo in enumerate(pedidos, 1):
            partes.append(f"===== BUSCA {indice}/{len(pedidos)}: {termo} =====")
            partes.append(tool_buscar_web(query=termo, dominios=dominios, filtro=filtro))
        return "\n\n".join(partes)

    termos = _termos(filtro)

    try:
        origem_servida = []
        aviso_do_provedor = ""
        if url_especifica:
            pedidas = [linha.strip() for linha in url_especifica.splitlines() if linha.strip()]
            emit_event("status", message=f"Navegando: {', '.join(pedidas)[:120]}")
            resultado, origem_servida, _ = _extrair_paginas(pedidas)
        elif query:
            resultado, origem_servida, falhas = _pesquisar(query, dominios)
            if not resultado.get("results") and falhas:
                return _texto_das_falhas(falhas)
            if falhas:
                motivos = "; ".join(
                    f"{_NOMES_DOS_PROVEDORES.get(p, p)}: {m}" for p, m in falhas
                )
                aviso_do_provedor = (
                    f"⚠️ {motivos} — usei {_nomes_dos_provedores(origem_servida)}.\n"
                )
        else:
            return "ERRO: Forneça 'query' ou 'url_especifica'."

        if not resultado or not resultado.get('results'):
            if url_especifica:
                abertas = [u.strip() for u in url_especifica.splitlines() if u.strip()]
                estado["urls_navegadas_turno"].update(abertas)
            return "Nenhum resultado encontrado na web."

        contexto = ""
        contexto_debug = ""
        fontes = []
        fontes_ilegiveis = []
        
        for idx, res in enumerate(resultado.get('results', []), 1):
            url = res.get('url', '')
            fontes.append(url)
            conteudo = _sem_navegacao_do_repositorio(res.get('raw_content', '') or res.get('content', ''))
            
            ilegivel, motivo = _conteudo_ilegivel(conteudo)
            
            contexto_debug += f"--- FONTE {idx}: {url} ---\n"
            if ilegivel:
                contexto_debug += f"⚠️ CONTEÚDO ILEGÍVEL DETECTADO: {motivo}\n"
                fontes_ilegiveis.append((idx, url, motivo))
            contexto_debug += f"{res.get('debug_content') or conteudo}\n\n"
            
            contexto += f"--- FONTE {idx}: {url} ---\n"
            if ilegivel:
                contexto += f"⚠️ CONTEÚDO ILEGÍVEL ({motivo}). NÃO INVENTE CÓDIGO — avise o usuário que esta fonte não pôde ser extraída corretamente.\n"
            if termos:
                linhas = conteudo.splitlines()
                achadas = [linha for linha in linhas if any(t in linha.lower() for t in termos)]
                contexto += f"   [filtro: {len(achadas)} linha(s) de {len(linhas)}]\n"
                if achadas:
                    contexto += "\n".join(achadas)[:12000] + "\n\n"
                else:
                    inicio = [linha for linha in linhas if linha.strip()][:15]
                    contexto += ("   O filtro NAO casou nenhuma linha, mas a pagina TEM conteudo. "
                                 "O texto completo ficou em data/busca.txt (tool_ler_trecho_arquivo). "
                                 "Comeco da pagina:\n")
                    contexto += "\n".join(inicio)[:12000] + "\n\n"
            else:
                contexto += f"{conteudo[:30000]}\n\n"
        
        estado["urls_navegadas_turno"].update(fontes)

        emit_event("tool_sources", urls=fontes)
        
        debug_path = caminho_data("busca.txt")
        try:
            os.makedirs(os.path.dirname(debug_path), exist_ok=True)
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(contexto_debug)
        except OSError:
            debug_path = ""
        
        total = len(fontes)
        total_ilegiveis = len(fontes_ilegiveis)
        total_legiveis = total - total_ilegiveis
        
        resumo = f"✅ Busca concluída! {total} fonte(s) encontrada(s)"
        if total_ilegiveis > 0:
            resumo += f" — ⚠️ {total_ilegiveis} ILEGÍVEL(is)"
        resumo += ":\n"
        if origem_servida:
            resumo += f"🔎 provedor: {_nomes_dos_provedores(origem_servida)}\n"
        if aviso_do_provedor:
            resumo += aviso_do_provedor

        niveis = [_nivel_do_resultado(res) for res in resultado.get("results", [])]

        for i, (res, url) in enumerate(zip(resultado.get("results", []), fontes), 1):
            status_fonte = ""
            for fi, fu, fm in fontes_ilegiveis:
                if fi == i:
                    status_fonte = f" ⚠️ ILEGÍVEL: {fm}"
                    break
            etiqueta = ETIQUETAS_DE_FONTE.get(niveis[i - 1], "")
            marca = f" — {etiqueta}" if etiqueta else ""
            autoridade = res.get("authority")
            if isinstance(autoridade, int) and autoridade >= 0:
                marca += f" (autoridade {autoridade}/4)"
            data = res.get("date") or ""
            if data:
                marca += f" · {data[:10]}"
            resumo += f"  [{i}] {url}{marca}{status_fonte}\n"

        resumo += _aviso_de_fontes(niveis)

        falhados = resultado.get("failed_results") or []
        if falhados:
            resumo += "\n⚠️ PÁGINA(S) NÃO EXTRAÍDA(S):\n"
            for falhou in falhados:
                resumo += f"  ⚠️ {falhou.get('url', '?')} — {falhou.get('error') or 'o extrator nao devolveu conteudo'}\n"

        resumo += f"\n📄 Log COMPLETO salvo em '{debug_path or 'busca.txt'}'.\n"
        
        if total_ilegiveis > 0:
            resumo += f"\n⚠️ ATENÇÃO: {total_ilegiveis} de {total} fonte(s) tiveram conteúdo ILEGÍVEL.\n"
            resumo += f"Isso acontece em sites com renderização client-side pesada (Shiki, JS toggles).\n"
            resumo += f"O conteúdo dessas fontes NÃO pode ser usado para extrair código.\n"
            if total_legiveis == 0:
                resumo += f"🚫 NENHUMA fonte legível. NÃO INVENTE CÓDIGO — informe o usuário honestamente.\n"
            resumo += f"\n"
        
        if termos:
            resumo += f"=== CONTEÚDO FILTRADO por {', '.join(termos)} (o integral está no log) ===\n" + contexto
        else:
            resumo += "=== CONTEÚDO EXTRAÍDO (primeiros 30000 chars por fonte) ===\n" + contexto
        
        return resumo
        
    except Exception as e:
        return f"ERRO na busca web: {str(e)}"
