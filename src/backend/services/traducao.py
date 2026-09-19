"""Traducao de notas do utilizador: um agente que consulta o codigo e reescreve.

Uma unica responsabilidade: receber um texto leigo, deixar o agente consultar o
projeto (arvore, funcoes, modulos, identificadores) com as ferramentas de leitura
e devolver o mesmo pedido reescrito no vocabulario tecnico do codigo. O agente
recebe de memoria o glossario (termo leigo -> codigo) e o retrato do projeto,
para precisar de pesquisar cada vez menos, e corre numa thread propria: nao
bloqueia o chat, e o resultado fica em `estado["traducao"]` ate o frontend o ler.
"""

import re
import threading

from src.backend.ai.base import chamar_api_com_retry
from src.backend.memory.glossary import load_glossary
from src.backend.state import estado, silenciar_eventos_desta_thread
from src.backend.tools.projeto_info import gerar_contexto_projeto
from src.backend.tools.registry import build_function_declarations, dispatch

MAX_CHARS_TEXTO = 20000
MAX_PASSOS = 6

AVISO = ("Reescrito pelo agente a partir da solicitação do usuário - pode conter erros; "
         "consulte o código caso seja necessário confirmar termos técnicos/funções.")

FERRAMENTAS_DE_LEITURA = {
    "tool_listar_pasta",
    "tool_listar_arvore",
    "tool_mapear_codigo",
    "tool_ler_arquivo",
    "tool_ler_trecho_arquivo",
    "tool_ler_assinaturas",
    "tool_pesquisar_no_projeto",
    "tool_buscar_codigo",
}

_INSTRUCAO = (
    "Es um tradutor de anotacoes de um utilizador LEIGO para o vocabulario tecnico "
    "do projeto. Recebes o texto do utilizador e devolves o MESMO pedido reescrito "
    "com os nomes reais do codigo (funcoes, modulos, ids, classes, ficheiros) no "
    "lugar das descricoes leigas. Consulta o codigo com as ferramentas quando "
    "precisares de descobrir o nome ou a localizacao exatos. Nao inventes nomes: se "
    "nao souberes, descreve o que se quer sem os inventar. Devolve APENAS o texto "
    "reescrito, sem preambulos, sem explicacoes e sem cercas de codigo."
)


def estado_traducao():
    """Estado atual da traducao para o frontend fazer polling."""
    return estado.get("traducao", {"estado": "livre", "texto": "", "erro": ""})


def traduzir_texto(texto, use_deepseek=False):
    """Dispara a traducao numa thread e devolve o estado imediatamente.

    O resultado fica em `estado["traducao"]` (lido pela rota GET), para a
    traducao correr em paralelo com o chat sem o bloquear.
    """
    atual = estado.get("traducao") or {}
    if atual.get("estado") == "a_traduzir":
        return {"erro": "Já há uma tradução em curso."}
    estado["traducao"] = {"estado": "a_traduzir", "texto": "", "erro": ""}
    threading.Thread(target=_correr, args=(texto, use_deepseek), daemon=True).start()
    return {"estado": "a_traduzir"}


def _correr(texto, use_deepseek):
    try:
        resultado = _traduzir_com_agente(texto, use_deepseek)
        if not resultado:
            estado["traducao"] = {"estado": "erro", "texto": "",
                                  "erro": "Não foi possível traduzir a nota."}
            return
        estado["traducao"] = {"estado": "pronto",
                              "texto": resultado + "\n\n" + AVISO, "erro": ""}
    except Exception as erro:
        estado["traducao"] = {"estado": "erro", "texto": "", "erro": str(erro)}


def _traduzir_com_agente(texto, use_deepseek):
    """Uma conversa modelo -> ferramentas -> modelo, ate o pedido tecnico sair.

    O ultimo passo corre SEM ferramentas e com um pedido explicito do texto
    final: era o que faltava quando o agente gastava os passos todos a consultar
    o codigo e nao devolvia traducao nenhuma.
    """
    from google.genai import types

    instrucao = _INSTRUCAO + "\n\n" + _contexto_de_memoria()
    decls = build_function_declarations(types, modo="auto", use_deepseek=use_deepseek)
    decls_leitura = [d for d in decls if d.name in FERRAMENTAS_DE_LEITURA]
    historico = [types.Content(role="user", parts=[types.Part.from_text(text=texto)])]
    silenciar_eventos_desta_thread(True)
    try:
        for passo in range(MAX_PASSOS):
            ultimo = passo == MAX_PASSOS - 1
            if ultimo:
                historico.append(types.Content(role="user", parts=[types.Part.from_text(
                    text="Devolve agora o texto reescrito, sem mais consultas.")]))
            config = _configuracao(types, instrucao, [] if ultimo else decls_leitura)
            resposta = chamar_api_com_retry(historico, config, use_deepseek=use_deepseek)
            if resposta is None:
                return ""
            if resposta.function_calls and not ultimo:
                historico.append(resposta.candidates[0].content)
                historico.append(types.Content(
                    role="user", parts=_respostas_das_ferramentas(types, resposta.function_calls)))
                continue
            final = _texto_da_resposta(resposta)
            if final:
                return final
        return ""
    finally:
        silenciar_eventos_desta_thread(False)


def _configuracao(types, instrucao, decls):
    """Configuracao da conversa; sem declaracoes o passo e so de escrita."""
    return types.GenerateContentConfig(
        system_instruction=instrucao,
        tools=[types.Tool(function_declarations=decls)] if decls else None,
        temperature=0.2,
        thinking_config=types.ThinkingConfig(include_thoughts=False),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def _respostas_das_ferramentas(types, chamadas):
    """O resultado de cada ferramenta, na parte que volta ao historico do modelo."""
    partes = []
    for call in chamadas:
        resultado, _ = dispatch(call.name, call.args or {})
        partes.append(types.Part(
            function_response=types.FunctionResponse(
                name=call.name,
                response={"result": resultado},
                id=getattr(call, "id", None),
            )
        ))
    return partes


def _texto_da_resposta(resposta):
    """Texto final, sem pensamento e sem chamadas de ferramenta escritas como texto.

    Alguns modelos emitem as chamadas no proprio corpo do texto (em vez do campo
    nativo): nunca podem chegar ao resultado como se fossem a traducao.
    """
    if not resposta.candidates or not resposta.candidates[0].content.parts:
        return ""
    trechos = []
    for p in resposta.candidates[0].content.parts:
        if getattr(p, "reasoning_content", None):
            continue
        if getattr(p, "thought", False) or getattr(p, "is_thought", False):
            continue
        texto = getattr(p, "text", "") or ""
        texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL)
        texto = re.sub(r"<tool_calls>.*?</tool_calls>", "", texto, flags=re.DOTALL)
        texto = re.sub(r"<invoke\b[^>]*>.*?</invoke>", "", texto, flags=re.DOTALL)
        texto = texto.strip()
        if texto:
            trechos.append(texto)
    return "\n".join(trechos).strip()


def _contexto_de_memoria():
    """O que o agente ja sabe antes de consultar: glossario e retrato do projeto."""
    partes = []
    dados = load_glossary()
    termos = dados.get("termos") if isinstance(dados, dict) else []
    if termos:
        linhas = ["GLOSSARIO (termo leigo -> codigo, ja conhecido):"]
        for item in termos:
            if not isinstance(item, dict) or not item.get("identificador"):
                continue
            local = item.get("localizacao") or {}
            onde = f"{local.get('arquivo')}:{local.get('linha')}" if local.get("arquivo") else ""
            aliases = ", ".join(item.get("aliases") or [])
            linha = f'- "{item.get("termo")}"' + (f" [{aliases}]" if aliases else "")
            linha += f" -> {item.get('identificador')}"
            if onde:
                linha += f" ({onde})"
            linhas.append(linha)
        partes.append("\n".join(linhas))
    try:
        contexto_projeto = gerar_contexto_projeto()
        if contexto_projeto:
            partes.append(contexto_projeto)
    except Exception:
        pass
    return "\n\n".join(partes)
