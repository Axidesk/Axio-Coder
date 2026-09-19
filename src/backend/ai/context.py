import os
import json

from src.backend.state import estado, emit_event
from src.backend.ai.gemini import get_gemini_client
from src.backend.ai.deepseek import get_deepseek_client

LIMITE_TOKENS_HISTORICO_GLOBAL = int(os.getenv("LIMITE_TOKENS_HISTORICO", "200000"))
LIMITE_TOKENS_HISTORICO_MAX = int(os.getenv("LIMITE_TOKENS_HISTORICO_MAX", "1000000"))
MANTER_RECENTES_GLOBAL = 12
TETO_AUTOMATICO_LIMIAR = float(os.getenv("TETO_AUTOMATICO_LIMIAR", "85"))
TETO_AUTOMATICO_PASSOS = int(os.getenv("TETO_AUTOMATICO_PASSOS", "2"))

token_encoder = None
class ErroContextoExcedido(Exception):
    pass

def eh_erro_contexto_limite(msg):
    m = (msg or "").lower()
    return any(x in m for x in [
        "context length",
        "maximum context",
        "max context",
        "context window",
        "too many tokens",
        "maximum token",
        "max tokens",
        "input is too long",
        "prompt is too long",
        "exceeds the maximum",
        "token limit",
    ])

def eh_erro_transitorio(msg):
    return any(x in str(msg) for x in [
        "503",
        "504",
        "429",
        "500",
        "Quota",
        "timeout",
        "timed out",
        "connection error",
        "Connection",
        "rate limit",
        "RateLimit",
        "DEADLINE_EXCEEDED",
        "Deadline expired",
    ])

def limite_tokens():
    ajustado = estado.get("limite_tokens_contexto")
    if not ajustado:
        return LIMITE_TOKENS_HISTORICO_GLOBAL
    return max(1000, min(int(ajustado), LIMITE_TOKENS_HISTORICO_MAX))


def ajustar_teto_automatico(percent):
    """Sobe o teto quando a memoria da rodada se aproxima do limite, e diz por que.

    Sem isto o teto era 100% manual: a rodada chegava aos 200 mil tokens e a
    compactacao comecava a substituir conversa por resumo, mesmo com o modelo a
    aceitar um milhao. A subida e deliberada e escassa - limiar alto, dois passos
    por sessao no maximo, nunca abaixo do padrao do .env e cada passo anunciado
    com o motivo -, porque teto maior significa pedido maior em TODA chamada, ou
    seja custo real. Devolve True quando subiu.
    """
    teto = limite_tokens()
    if percent < TETO_AUTOMATICO_LIMIAR or teto >= LIMITE_TOKENS_HISTORICO_MAX:
        return False
    if teto < LIMITE_TOKENS_HISTORICO_GLOBAL:
        return False
    if estado.get("tetos_automaticos", 0) >= TETO_AUTOMATICO_PASSOS:
        return False
    novo = min(LIMITE_TOKENS_HISTORICO_MAX, teto * 2)
    estado["limite_tokens_contexto"] = novo
    estado["tetos_automaticos"] = estado.get("tetos_automaticos", 0) + 1
    motivo = f"a memoria da rodada chegou a {percent:.0f}% do teto"
    emit_event("context_limit", anterior=teto, limite=novo,
               maximo=LIMITE_TOKENS_HISTORICO_MAX, motivo=motivo)
    emit_event("status", message=f"Teto de contexto: {teto:,} -> {novo:,} tokens ({motivo}).")
    return True


def truncar_cabeca_cauda(texto, max_chars=3000):
    if len(texto) <= max_chars:
        return texto
    head = int(max_chars * 0.6)
    tail = int(max_chars * 0.4)
    removidos = len(texto) - max_chars
    return (
        texto[:head]
        + f"\n[...TRUNCADO: {removidos} caracteres no meio. Releia o trecho com tool_ler_trecho_arquivo se precisar.]\n"
        + texto[-tail:]
    )

def truncar_mensagem_historico(texto, max_linhas=200, max_chars=25000):
    if not texto:
        return ""
    if len(texto) <= max_chars and texto.count("\n") + 1 <= max_linhas:
        return texto
    linhas = texto.split("\n")
    total = len(linhas)
    head_n = max(1, max_linhas // 2)
    tail_n = max(1, max_linhas - head_n)
    head = "\n".join(linhas[:head_n])
    tail = "\n".join(linhas[-tail_n:]) if total > head_n else ""
    removidas = max(0, total - head_n - tail_n)
    removidos = max(0, len(texto) - len(head) - len(tail))
    marcador = (
        f"\n[...TRUNCADO: {removidas} linhas / {removidos} caracteres removidos do histórico "
        f"para não estourar o contexto. O texto completo segue salvo em disco; peça ao usuário "
        f"para reenviar o trecho específico se precisar.]\n"
    )
    return head + marcador + tail

def compactar_historico(historico, max_chars=3000):
    compactou = False
    for content in historico:
        for part in getattr(content, "parts", []) or []:
            fr = getattr(part, "function_response", None)
            if not fr:
                continue
            try:
                resp = fr.response
                if isinstance(resp, dict) and isinstance(resp.get("result"), str):
                    resultado = resp["result"]
                    if len(resultado) > max_chars:
                        resp["result"] = truncar_cabeca_cauda(resultado, max_chars)
                        compactou = True
                elif isinstance(resp, str) and len(resp) > max_chars:
                    fr.response = truncar_cabeca_cauda(resp, max_chars)
                    compactou = True
            except Exception:
                continue
    return compactou

def texto_de_content(content):
    textos = []
    for part in getattr(content, "parts", []) or []:
        t = getattr(part, "text", None)
        if t:
            textos.append(t)
    return "\n".join(textos)

def texto_completo_de_content(content):
    partes = []
    for part in getattr(content, "parts", []) or []:
        t = getattr(part, "text", None)
        if t:
            partes.append(t)
            continue
        fc = getattr(part, "function_call", None)
        if fc is not None:
            try:
                partes.append(json.dumps({"name": getattr(fc, "name", ""), "args": getattr(fc, "args", {})}, ensure_ascii=False))
            except Exception:
                partes.append(str(fc))
            continue
        fr = getattr(part, "function_response", None)
        if fr is not None:
            try:
                partes.append(json.dumps({"name": getattr(fr, "name", ""), "response": getattr(fr, "response", {})}, ensure_ascii=False))
            except Exception:
                partes.append(str(fr))
    return "\n".join(partes)

def tokens_historico(historico):
    return sum(contar_tokens(texto_completo_de_content(c)) for c in historico)

def obter_encoder_tokens():
    global token_encoder
    if token_encoder is None:
        try:
            import tiktoken
            token_encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            token_encoder = False
    return token_encoder if token_encoder is not False else None

def contar_tokens(texto):
    if not texto:
        return 0
    enc = obter_encoder_tokens()
    if enc is not None:
        try:
            return len(enc.encode(texto))
        except Exception:
            pass
    return max(1, len(texto) // 4)

def resumir_com_llm(texto, use_deepseek=False):
    from google.genai import types
    prompt = (
        "Resuma a conversa abaixo em um único parágrafo técnico e conciso, preservando TODAS as "
        "decisões, fatos, números, nomes de arquivos, caminhos, funções e conclusões importantes. "
        "Não omita detalhes técnicos relevantes. Responda apenas com o resumo, sem introdução.\n\n"
        f"{texto}"
    )
    try:
        if use_deepseek:
            resp = get_deepseek_client().chat.completions.create(
                model="deepseek-flash",
                messages=[
                    {"role": "system", "content": "Você é um resumidor de conversas técnicas de desenvolvimento."},
                    {"role": "user", "content": prompt},
                ],
            )
            return (resp.choices[0].message.content or "").strip() or None
        resp = get_gemini_client().models.generate_content(
            model='gemini-3.1-pro-preview-customtools', #gemini-3.8-flash (compute use)
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0.2),
        )
        return (resp.text or "").strip() or None
    except Exception:
        return None

def podar_historico_global(use_deepseek=False):
    from google.genai import types
    hist = estado.get("historico_chat", [])
    if not hist:
        return
    total = sum(contar_tokens(texto_de_content(c)) for c in hist)
    if total <= limite_tokens():
        return
    antigas = hist[:-MANTER_RECENTES_GLOBAL]
    recentes = hist[-MANTER_RECENTES_GLOBAL:]
    texto_antigas = "\n".join(
        f"[{getattr(c, 'role', '?')}]: {texto_de_content(c).strip()}"
        for c in antigas
        if texto_de_content(c).strip()
    )
    if not texto_antigas:
        return
    resumo_texto = resumir_com_llm(texto_antigas, use_deepseek)
    if resumo_texto:
        bloco_resumo = (
            "=== RESUMO DA CONVERSA ANTERIOR (gerado por IA para liberar contexto) ===\n"
            f"{resumo_texto}"
        )
        estado["historico_chat"] = [types.Content(role="model", parts=[types.Part.from_text(text=bloco_resumo)])] + recentes
    else:
        estado["historico_chat"] = recentes
    estado["compactacoes_contexto"] = estado.get("compactacoes_contexto", 0) + 1

def texto_de_ferramentas(ferramentas):
    if not ferramentas:
        return ""
    partes = []
    for f in ferramentas:
        dados = None
        for metodo in ("model_dump", "to_json_dict"):
            m = getattr(f, metodo, None)
            if callable(m):
                try:
                    dados = m()
                    if dados is not None:
                        break
                except Exception:
                    continue
        if dados is None:
            dados = {
                "name": getattr(f, "name", ""),
                "description": getattr(f, "description", ""),
            }
        try:
            partes.append(json.dumps(dados, ensure_ascii=False))
        except Exception:
            partes.append(str(dados))
    return "\n".join(partes)

def medir_contexto(extra_texto="", system_text="", ferramentas=None, historico=None, tokens_base=0, fase="acumulado"):
    if historico is None:
        historico = estado.get("historico_chat", [])
    usado = tokens_base + tokens_historico(historico)
    if system_text:
        usado += contar_tokens(system_text)
    if ferramentas:
        usado += contar_tokens(texto_de_ferramentas(ferramentas))
    if extra_texto:
        usado += contar_tokens(extra_texto)
    limite = limite_tokens()
    percent = (usado / limite) * 100 if limite else 0.0
    acumulado = tokens_historico(estado.get("historico_chat", []))
    percent_acumulado = (acumulado / limite) * 100 if limite else 0.0
    if ajustar_teto_automatico(percent):
        limite = limite_tokens()
        percent = (usado / limite) * 100 if limite else 0.0
        percent_acumulado = (acumulado / limite) * 100 if limite else 0.0
    emit_event(
        "context_usage",
        usado=usado,
        limite=limite,
        percent=round(min(100.0, percent), 1),
        compactacoes=estado.get("compactacoes_contexto", 0),
        fase=fase,
        usado_sessao=usado,
        percent_sessao=round(min(100.0, percent), 1),
        usado_acumulado=acumulado,
        percent_acumulado=round(min(100.0, percent_acumulado), 1),
    )
