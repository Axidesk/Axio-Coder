import os
import re

from src.backend.state import estado, emit_event

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
def _conteudo_ilegivel(conteudo):
    """Detecta se o conteúdo extraído está ilegível/garbled (ex: Shiki, JS toggles).
    Retorna (bool, str): (é_ilegivel, motivo)"""
    if not conteudo or len(conteudo) < 50:
        return False, ""
    
    # 1. Densidade de espaços: texto normal tem ~15-20%, garbled tem < 5%
    chars = len(conteudo)
    espacos = conteudo.count(' ')
    densidade_espacos = espacos / chars if chars > 0 else 0
    
    # 2. Indicadores de toggle JS (código colapsado)
    tem_view_code = 'View Code' in conteudo or 'View Format' in conteudo
    tem_copy = 'Copy' in conteudo
    
    # 3. Densidade de tags HTML (Shiki gera muitos <span>)
    tags_html = conteudo.count('<span') + conteudo.count('<div') + conteudo.count('<code') + conteudo.count('</span>') + conteudo.count('</div>')
    densidade_tags = tags_html / (chars / 1000) if chars > 0 else 0  # tags por 1000 chars
    
    # 4. Palavras coladas (ex: "ViewFormatCopyimport") - 3+ palavras sem espaço
    trechos = conteudo[:5000]  # analisa primeiros 5000 chars
    # Procura sequências de camelCase/PascalCase com 20+ caracteres sem espaço (reduzido de 30)
    coladas = re.findall(r'[A-Za-z]{20,}', trechos)
    palavras_coladas = len(coladas)
    
    # 5. Duplicação de imports na mesma linha (Shiki garbled: cada token duplicado e colado)
    # Ex: import { Button } from "@/components/ui/button" import { Button } from "@/components/ui/button"
    linhas = conteudo.split('\n')
    imports_duplicados = 0
    for linha in linhas:
        imports_na_linha = re.findall(r'import\s+\{[^}]+\}\s+from\s+["\'][^"\']+["\']', linha)
        if len(imports_na_linha) >= 3:  # 3+ imports idênticos colados = garbled
            imports_duplicados += 1
    
    # 6. JSX com espaço após < (ex: "< Popover>", "< Button") — artefato Shiki
    jsx_garbled = len(re.findall(r'<\s+[A-Z][a-zA-Z]*\s*>?\s*[A-Z]', conteudo[:10000]))
    
    # 7. Tags React duplicadas consecutivas (ex: "<Popover>< Popover>")
    tags_duplicadas = len(re.findall(r'</?(\w+)\s*>?\s*</?\s*\1\s*>', conteudo[:10000]))
    
    motivos = []
    ilegivel = False
    
    if densidade_espacos < 0.05:
        ilegivel = True
        motivos.append(f"densidade de espaços muito baixa ({densidade_espacos:.1%})")
    
    if tem_view_code and tem_copy and densidade_espacos < 0.08:
        ilegivel = True
        motivos.append("código colapsado atrás de toggle JS (View Code/Copy)")
    
    if densidade_tags > 15:
        ilegivel = True
        motivos.append(f"alta densidade de tags HTML ({densidade_tags:.0f}/1k chars) — provável Shiki/syntax highlighter")
    
    if palavras_coladas >= 5:
        ilegivel = True
        motivos.append(f"muitas palavras coladas ({palavras_coladas} sequências) — texto não parseável")
    
    if imports_duplicados >= 1:
        ilegivel = True
        motivos.append(f"imports duplicados/colados ({imports_duplicados} linhas com 3+ imports) — Shiki garbled")
    
    if jsx_garbled >= 3:
        ilegivel = True
        motivos.append(f"JSX corrompido ({jsx_garbled} tags com espaço após '<') — artefato Shiki")
    
    if tags_duplicadas >= 4:
        ilegivel = True
        motivos.append(f"tags React duplicadas consecutivas ({tags_duplicadas} ocorrências) — Shiki garbled")
    
    if ilegivel:
        return True, "; ".join(motivos)
    return False, ""
def tool_buscar_web(query="", url_especifica=""):
    """Busca na web usando Tavily. Usa workflow 2 passos: Search → Extract (advanced) para maior fidelidade."""
    if not tavily_configurada():
        return "ERRO: navegação web desativada. Ative o globo em Configurações → APIs (ao lado do DeepSeek) e informe a chave Tavily."
    
    tavily_client = _get_tavily_client()
    if not tavily_client:
        return "ERRO: Cliente Tavily não inicializado."
    
    try:
        if url_especifica:
            # URL direta: Extract com advanced depth (traz tabelas, listas, conteúdo estruturado)
            emit_event("status", message=f"Navegando: {url_especifica}")
            resultado = tavily_client.extract(
                urls=[url_especifica],
                extract_depth="advanced"
            )
        elif query:
            # Workflow 2 passos (recomendado pela doc Tavily):
            # Passo 1: Search para descobrir URLs relevantes
            emit_event("status", message=f"Navegando: pesquisando '{query[:60]}'...")
            search_resp = tavily_client.search(
                query=query,
                max_results=3,
                search_depth="advanced"
            )
            urls = [r['url'] for r in search_resp.get('results', []) if r.get('url')]
            if not urls:
                return "Nenhum resultado encontrado na web."
            
            # Passo 2: Extract em cada URL com advanced depth (tabelas, listas preservadas)
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
        contexto_debug = ""  # Versão COMPLETA para o log, sem truncar
        fontes = []
        fontes_ilegiveis = []
        
        for idx, res in enumerate(resultado.get('results', []), 1):
            url = res.get('url', '')
            fontes.append(url)
            conteudo = res.get('raw_content', '') or res.get('content', '')
            
            # Detecta conteúdo ilegível
            ilegivel, motivo = _conteudo_ilegivel(conteudo)
            
            # Log COMPLETO (sem truncar) para debug
            contexto_debug += f"--- FONTE {idx}: {url} ---\n"
            if ilegivel:
                contexto_debug += f"⚠️ CONTEÚDO ILEGÍVEL DETECTADO: {motivo}\n"
                fontes_ilegiveis.append((idx, url, motivo))
            contexto_debug += f"{conteudo}\n\n"
            
            # Resposta para o LLM: truncada a 30000 chars por fonte para não estourar tokens
            contexto += f"--- FONTE {idx}: {url} ---\n"
            if ilegivel:
                contexto += f"⚠️ CONTEÚDO ILEGÍVEL ({motivo}). NÃO INVENTE CÓDIGO — avise o usuário que esta fonte não pôde ser extraída corretamente.\n"
            contexto += f"{conteudo[:30000]}\n\n"
        
        # Registra as URLs realmente navegadas para o cross-check do planejamento
        estado["urls_navegadas_turno"].update(fontes)

        # Emite as URLs visitadas para o log de ferramentas da interface
        emit_event("tool_sources", urls=fontes)
        
        # Salva log COMPLETO (raw_content integral) para debug
        debug_path = os.path.join(estado["pasta_raiz"], "busca.txt")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(contexto_debug)
        
        # Monta resumo
        total = len(fontes)
        total_ilegiveis = len(fontes_ilegiveis)
        total_legiveis = total - total_ilegiveis
        
        resumo = f"✅ Busca concluída! {total} fonte(s) encontrada(s)"
        if total_ilegiveis > 0:
            resumo += f" — ⚠️ {total_ilegiveis} ILEGÍVEL(is)"
        resumo += ":\n"
        
        for i, url in enumerate(fontes, 1):
            status_fonte = ""
            for fi, fu, fm in fontes_ilegiveis:
                if fi == i:
                    status_fonte = f" ⚠️ ILEGÍVEL: {fm}"
                    break
            resumo += f"  [{i}] {url}{status_fonte}\n"
        
        resumo += f"\n📄 Log COMPLETO salvo em 'busca.txt'.\n"
        
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
