import os
import time
import threading
import re
import base64
import logging

logging.getLogger("google.genai").setLevel(logging.ERROR)

from src.backend.state import estado, emit_event, set_turn_id, caminho_estado_projeto
from src.backend.tools.registry import register
from src.backend.memory.vector import wing_da_pasta, espelhar_notas_existentes, minerar_em_segundo_plano
from src.backend.services.session import carregar_checkpoint, formatar_checkpoint, salvar_checkpoint
from src.backend.ai.context import ErroContextoExcedido, compactar_historico, contar_tokens, texto_de_ferramentas, medir_contexto, podar_historico_global, truncar_mensagem_historico
from src.backend.ai.coleta import coletar_contexto
from src.backend.ai.atrito import registrar_uso_ferramenta, fechar_rodada
from src.backend.ai.base import chamar_api_com_retry
from src.backend.services.imagem import partes_da_imagem
from src.backend.ai.instructions import build_system_instructions
from src.backend.tools.bootstrap import tool_gerenciar_bootstrap
from src.backend.tools.web import tavily_configurada
from src.backend.tools.code_index import disparar_indexacao_background
from src.backend.tools import (
    browse,
    cofre,
    comments,
    computador,
    edit,
    environment,
    espera,
    graph,
    harness,
    janelas,
    js_auditoria,
    js_esm,
    js_imports,
    lint,
    memory_tools,
    modelagem,
    paint,
    plan,
    preferencias,
    preview,
    process,
    py_imports,
    read,
    refactor,
    rotas,
    selfcheck,
    similarity,
    structure,
    syntax,
    trash,
    undo,
    vision,
)
from src.backend.tools import bootstrap, code_index, pacotes, web
from src.backend.tools.registry import build_function_declarations, dispatch, register

from google.genai import types

@register(
    "tool_aprovar_plano",
    "Destrava as ferramentas de edição no modo semi-automático. Chame apenas quando perceber que o usuário aprovou/confirmou o plano (qualquer forma de 'sim', 'pode', 'aplica', etc.).",
    disponivel="semi",
)
def tool_aprovar_plano():
    """Destrava a edição no modo semi-automático após a IA perceber a aprovação do usuário."""
    emit_event("executing", function="Aprovação registrada: liberando edição")
    estado["bloquear_edicao"] = False
    return "APROVAÇÃO REGISTRADA: você está autorizado a editar os arquivos agora. Execute exatamente o plano aprovado."

def _formatar_edicoes_recentes():
    """Formata e limpa a lista de edições recentes (arquivo + linha) para injeção."""
    edicoes = estado.get("edicoes_rodada", [])
    if not edicoes:
        return ""
    linhas = []
    for e in edicoes:
        arquivo = e.get("arquivo", "")
        linha = e.get("linha")
        linhas.append(f"{arquivo}" + (f":{linha}" if linha else ""))
    estado["edicoes_rodada"] = []
    return "\n".join(linhas)

def _formatar_plano_pendente():
    plano = estado.get("plano_atual")
    if not plano:
        return ""
    linhas = []
    ha_pendente = False
    for etapa in plano:
        tarefas = etapa.get("tarefas", [])
        concluidas = set(etapa.get("tarefas_concluidas", []))
        pendentes = [t for t in tarefas if t not in concluidas]
        if pendentes:
            ha_pendente = True
        status = "pendente" if pendentes else "CONCLUIDA"
        linhas.append(f"Etapa '{etapa.get('id')}' - {etapa.get('titulo', '')} [{status}]")
        for t in tarefas:
            marcador = "[x]" if t in concluidas else "[ ]"
            linhas.append(f"  {marcador} {t}")
    if not ha_pendente:
        return ""
    return (
        "=== PLANO DE EXECUCAO EM ANDAMENTO (NAO PULE NENHUMA TAREFA) ===\n"
        + "\n".join(linhas)
        + "\n\nComplete TODAS as tarefas listadas, na ordem, e chame 'tool_atualizar_plano' IMEDIATAMENTE "
        "apos concluir CADA tarefa individual (com etapa_concluida=false nas intermediarias e true somente na ultima). "
        "NAO avance para a proxima etapa sem concluir todas as tarefas da etapa atual. "
        "NAO de a resposta final enquanto houver tarefa [ ] pendente. "
        "Se o pedido atual do usuario nao tiver relacao com este plano, ignore-o e atenda o pedido atual.\n"
    )

def _emitir_status_da_ferramenta(nome_func, args):
    """Emite no status o que a ferramenta despachada esta a fazer."""
    if nome_func == "tool_executar_comando":
        emit_event("status", message=" ")
    elif nome_func == "tool_executar_processo":
        emit_event("status", message=f"Executando processo: {args.get('comando', '')[:80]}")
    elif nome_func == "tool_buscar_web":
        url_esp = args.get("url_especifica", "") or ""
        query = args.get("query", "") or ""
        if url_esp:
            emit_event("status", message=f"Navegando: {url_esp}")
        elif query:
            emit_event("status", message=f"Navegando: pesquisando '{query[:60]}'...")
        else:
            emit_event("status", message="Navegando: ...")
    elif nome_func in ("tool_ler_trecho_arquivo", "tool_ler_arquivo") and args.get("caminho_relativo", "") in ("busca.txt", ".axio/busca.txt", "debug_tavily.txt"):
        alvo = args.get("caminho_relativo", "")
        emit_event("status", message=f"Extraindo informação: {alvo}")
    elif nome_func == "tool_info_ambiente":
        emit_event("status", message="Coletando informações do ambiente...")
    elif nome_func == "tool_capturar_print":
        emit_event("status", message="Capturando o ecrã...")
    elif nome_func == "tool_ver_imagem":
        emit_event("status", message=f"Abrindo a imagem: {args.get('caminho_relativo', '')}")
    elif nome_func == "tool_gerenciar_bootstrap":
        emit_event("status", message=f"Gerenciando estado de bootstrap ({args.get('acao', 'ler')})...")
    elif nome_func in ("tool_desfazer", "tool_refazer"):
        emit_event("status", message=f"{'Desfazendo' if nome_func == 'tool_desfazer' else 'Refazendo'}: {args.get('caminho_relativo', '')}")
    elif nome_func == "tool_status_desfazer":
        emit_event("status", message="Consultando histórico de desfazer/refazer...")
    elif nome_func in ("tool_planejar_arquitetura", "tool_iniciar_plano", "tool_atualizar_plano", "tool_adicionar_etapa_plano"):
        emit_event("status", message="Organizando plano de execução...")
    elif nome_func == "tool_observar_preview":
        emit_event("status", message=f"Olhando para o preview ({args.get('acao', 'estado')})...")
    elif nome_func == "tool_operar_preview":
        emit_event("status", message=f"Agindo no preview ({args.get('acao', '')})...")
    elif nome_func == "tool_computador":
        emit_event("status", message="Uso do computador: controlando o navegador...")
    else:
        alvo = args.get("caminho_relativo", "raiz do projeto")
        nome_limpo = nome_func.replace("tool_", "")
        msg_acao = f"Axio acionou {nome_limpo} em '{alvo}'..."
        emit_event("status", message=msg_acao)

def _registar_resumo_da_ferramenta(nome_func, args_dict, ferramentas_usadas_rodada):
    """Acrescenta ao resumo da rodada a ferramenta usada (e o trecho, se houver)."""
    resumo_acao = f"Usou {nome_func}"
    if "caminho_relativo" in args_dict:
        resumo_acao += f" em {args_dict['caminho_relativo']}"
    if "texto_novo" in args_dict:
        texto_novo = args_dict['texto_novo']
        if len(texto_novo) > 200:
            texto_novo = texto_novo[:200] + " [...]"
        resumo_acao += f". Trecho: '{texto_novo}'"
    ferramentas_usadas_rodada.append(resumo_acao)

def _extrair_pensamentos_e_textos(partes, tem_calls):
    """Separa as partes da resposta em pensamentos e texto final."""
    pensamentos = []
    textos_finais = []
    for i, p in enumerate(partes):
        rc = getattr(p, 'reasoning_content', None)
        if rc:
            pensamentos.append(rc.strip())
            continue
        if not (hasattr(p, 'text') and p.text):
            continue
        texto = p.text
        if getattr(p, 'thought', False) or getattr(p, 'is_thought', False):
            pensamentos.append(texto)
        elif '<think>' in texto:
            match = re.search(r'<think>(.*?)</think>', texto, re.DOTALL)
            if match:
                pensamentos.append(match.group(1).strip())
                texto_sem_think = re.sub(r'<think>.*?</think>', '', texto, flags=re.DOTALL).strip()
                if texto_sem_think:
                    textos_finais.append(texto_sem_think)
            else:
                partes_think = texto.split('<think>')
                if len(partes_think) > 1:
                    pensamentos.append(partes_think[1].strip())
                if partes_think[0].strip():
                    textos_finais.append(partes_think[0].strip())
        elif len(partes) > 1 and i == 0 and not tem_calls:
            tem_outro_texto = any(hasattr(p_next, 'text') and p_next.text for p_next in partes[i+1:])
            if tem_outro_texto:
                pensamentos.append(texto)
            else:
                textos_finais.append(texto)
        elif len(partes) > 1 and i == 0 and tem_calls:
            pensamentos.append(texto)
        else:
            textos_finais.append(texto)
    return pensamentos, textos_finais

def _extrair_citacoes_grounding(response, textos_finais):
    """Citacoes inline (trecho -> URL) devolvidas pelo grounding do Gemini.

    O grounding marca trechos do texto bruto com start/end_index. Alinhamos os
    offsets com o texto final (que passa por strip) para marcar os trechos na
    resposta exibida.
    """
    if not (response.candidates and response.candidates[0].content.parts):
        return []
    metadata = getattr(response.candidates[0], 'grounding_metadata', None)
    if not metadata:
        return []
    supports = getattr(metadata, 'grounding_supports', None) or []
    chunks = getattr(metadata, 'grounding_chunks', None) or []
    if not supports:
        return []
    bruto = "\n".join(textos_finais)
    desvio = len(bruto) - len(bruto.lstrip())
    citacoes = []
    for sup in supports:
        segmento = getattr(sup, 'segment', None)
        if not segmento:
            continue
        inicio = getattr(segmento, 'start_index', None)
        fim = getattr(segmento, 'end_index', None)
        if inicio is None or fim is None or fim <= inicio:
            continue
        url = titulo = None
        for idx in (getattr(sup, 'grounding_chunk_indices', None) or []):
            if 0 <= idx < len(chunks):
                web = getattr(chunks[idx], 'web', None)
                if web and getattr(web, 'uri', None):
                    url = web.uri
                    titulo = getattr(web, 'title', None) or url
                    break
        if not url:
            continue
        citacoes.append({
            "inicio": inicio - desvio,
            "fim": fim - desvio,
            "url": url,
            "titulo": titulo,
        })
    return citacoes


def _injetar_citacoes_inline(texto, citacoes):
    """Marca os trechos citados com [^n](url) e monta o bloco Fontes."""
    if not citacoes:
        return texto, ""
    validas = [c for c in citacoes if 0 <= c["inicio"] < c["fim"] <= len(texto)]
    if not validas:
        return texto, ""
    validas.sort(key=lambda c: (c["inicio"], c["fim"]))
    numeradas = [(i + 1, c) for i, c in enumerate(validas)]
    for num, c in reversed(numeradas):
        marcador = f" [^{num}]({c['url']})"
        texto = texto[:c["fim"]] + marcador + texto[c["fim"]:]
    linhas = ["**Fontes:**"]
    for num, c in numeradas:
        linhas.append(f"[^{num}] [{c['titulo']}]({c['url']})")
    return texto, "\n\n" + "\n".join(linhas)

def _montar_bloco_continuidade():
    """Bloco de continuidade: checkpoint pendente + bootstrap em andamento."""
    contexto_continuidade = ""
    bloco_continuidade = ""
    checkpoint = carregar_checkpoint()
    if checkpoint:
        contexto_continuidade = formatar_checkpoint(checkpoint)
        bloco_continuidade = (
            "=== ESTADO DE CONTINUIDADE PENDENTE ===\n"
            f"{contexto_continuidade}\n"
            "Use este contexto SOMENTE se o pedido atual do usuário indicar que ele quer retomar a tarefa interrompida. "
            "Caso contrário, ignore este bloco e atenda o pedido atual.\n"
        )
    bootstrap = tool_gerenciar_bootstrap(acao="ler", silencioso=True)
    if bootstrap and not bootstrap.startswith("Nenhum estado") and not bootstrap.startswith("ERRO"):
        bloco_continuidade += (
            "=== ESTADO DE BOOTSTRAP EM ANDAMENTO ===\n"
            f"{bootstrap}\n"
            "Retome o bootstrap de onde parou se o pedido atual estiver relacionado a ele. Se o campo 'aguardando' "
            "estiver preenchido, verifique se o usuário já forneceu a credencial/valor nesta mensagem antes de continuar. "
            "Se o pedido não tiver relação com o bootstrap, ignore este bloco.\n"
        )
    return contexto_continuidade, bloco_continuidade

def _montar_config_do_turno(instrucao, modo, use_deepseek, ai_model):
    """Declaracoes das ferramentas disponiveis + config de geracao do turno."""
    ferramentas_base = build_function_declarations(
        types, modo=modo, use_deepseek=use_deepseek, web_ok=tavily_configurada(), ai_model=ai_model
    )
    if use_deepseek:
        lista_tools = [types.Tool(function_declarations=ferramentas_base)]
    else:
        lista_tools = [
            types.Tool(function_declarations=ferramentas_base),
            types.Tool(google_search=types.GoogleSearch()),
        ]

    config = types.GenerateContentConfig(
        system_instruction=instrucao,
        tools=lista_tools,
        temperature=0.1,
        thinking_config=types.ThinkingConfig(include_thoughts=True),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
    )
    return ferramentas_base, config

def _bruto_da_imagem_anexada(img_data):
    """(bytes, nome) de um anexo do frontend: o dict {base64, name, mime} ou a propria string base64."""
    if isinstance(img_data, dict):
        codificado = img_data.get("base64")
        nome = img_data.get("name") or "imagem"
    else:
        codificado, nome = img_data, "imagem"
    if not codificado:
        return None, nome
    try:
        return base64.b64decode(codificado), nome
    except Exception:
        return None, nome

def _separar_imagem_do_resultado(resultado):
    """(texto, imagens) de um resultado de ferramenta.

    Uma ferramenta de visao devolve {'texto', 'imagem'} ou {'texto', 'imagens'};
    as restantes devolvem texto. As imagens NAO podem seguir no corpo da resposta
    da ferramenta (a API so aceita imagens em mensagens do utilizador), por isso
    saem daqui e sao entregues a parte, no pedido seguinte.
    """
    if not isinstance(resultado, dict):
        return resultado, []
    if "imagens" in resultado:
        return str(resultado.get("texto", "")), [i for i in (resultado.get("imagens") or []) if i]
    if "imagem" in resultado:
        imagem = resultado.get("imagem")
        return str(resultado.get("texto", "")), [imagem] if imagem else []
    if "texto" in resultado:
        return str(resultado["texto"]), []
    return resultado, []

def _partes_das_imagens(imagens):
    """Partes de uma mensagem do utilizador com as imagens que as ferramentas entregaram."""
    partes = []
    for imagem in imagens:
        dados = (imagem or {}).get("base64")
        if not dados:
            continue
        partes.append(types.Part.from_text(text=imagem.get("rotulo") or "[Imagem entregue pela ferramenta]"))
        partes.append(types.Part.from_bytes(
            data=base64.b64decode(dados),
            mime_type=imagem.get("mime") or "image/png",
        ))
    return partes

def loop_raciocinio_ia(prompt_usuario, modo="auto", imagens_b64=None, use_deepseek=False, turn_id=None, ai_model="gemini"):
    set_turn_id(turn_id)
    estado["bloquear_edicao"] = (modo == "semi")
    estado["urls_navegadas_turno"] = set()

    emit_event("status", message="Coletando memória...")

    disparar_indexacao_background()
    espelhar_notas_existentes()
    wing_atual = wing_da_pasta(estado["pasta_raiz"])
    palace_path = os.path.expanduser("~/.mempalace/palace")


    contexto = coletar_contexto(prompt_usuario, wing_atual, palace_path)

    contexto_projeto = contexto.get("projeto", "")
    contexto_memoria = contexto.get("memoria", "")
    contexto_ai_memory = contexto.get("ai_memory", "")
    contexto_codigo = contexto.get("codigo", "")

    contexto_edicoes = _formatar_edicoes_recentes()

    if estado.get("cancel_requested"):
        estado["cancel_requested"] = False
        emit_event("status", message=" ")
        emit_event("cancel")
        return

    contexto_continuidade, bloco_continuidade = _montar_bloco_continuidade()

    instrucao = build_system_instructions(modo, contexto_memoria, contexto_ai_memory, bloco_continuidade, contexto_projeto, contexto_codigo, contexto_edicoes, tem_web_search=tavily_configurada(), use_deepseek=use_deepseek, mensagem_usuario=prompt_usuario, ai_model=ai_model)

    ferramentas_base, config = _montar_config_do_turno(instrucao, modo, use_deepseek, ai_model)
    
    partes_usuario = [types.Part.from_text(text=prompt_usuario)]
    for img_data in imagens_b64 or []:
        bruto, nome = _bruto_da_imagem_anexada(img_data)
        try:
            partes_imagem = partes_da_imagem(bruto) if bruto else []
        except Exception:
            partes_imagem = []
        if not partes_imagem:
            emit_event("status", message=f"Aviso: a imagem '{nome}' nao pode ser lida e foi ignorada.")
            continue
        partes_usuario.append(types.Part.from_text(text=f"[Imagem anexada: {nome}]"))
        if len(partes_imagem) > 1:
            emit_event("status", message=(
                f"A imagem '{nome}' e grande: segue em {len(partes_imagem)} pedacos, cada um em"
                " tamanho original, para o texto fino chegar legivel."
            ))
        for indice, (bytes_envio, mime_anexo) in enumerate(partes_imagem, 1):
            if len(partes_imagem) > 1:
                partes_usuario.append(types.Part.from_text(
                    text=f"[Parte {indice}/{len(partes_imagem)} da imagem '{nome}': em tamanho original,"
                         " olhe para TODAS antes de concluir]"
                ))
            partes_usuario.append(types.Part.from_bytes(data=bytes_envio, mime_type=mime_anexo))
        
    podar_historico_global(use_deepseek=use_deepseek)
    lista_historico = estado["historico_chat"]
    historico_sessao = list(lista_historico) + [types.Content(role="user", parts=partes_usuario)]
    _tokens_fixos = contar_tokens(instrucao) + contar_tokens(texto_de_ferramentas(ferramentas_base))
    medir_contexto(historico=historico_sessao, tokens_base=_tokens_fixos, fase="execucao")
    
    ferramentas_usadas_rodada = []
    contador_chamadas_api = 0
    tempo_inicio_rodada = time.time()
    
    while True:
        if estado.get("cancel_requested"):
            estado["cancel_requested"] = False
            emit_event("status", message=" ")
            emit_event("cancel")
            return
            
        try:
            contador_chamadas_api += 1
            decorrido_s = int(time.time() - tempo_inicio_rodada)
            aviso_relogio = (
                f"[SISTEMA-RELÓGIO] Chamada de API nº {contador_chamadas_api} desta rodada | "
                f"Hora atual: {time.strftime('%H:%M:%S')} | Tempo decorrido desde o início da tarefa: "
                f"{decorrido_s // 60}min {decorrido_s % 60}s. "
                "Se já tentou a MESMA estAguardando resposta...ratégia 2+ vezes sem progresso, PARE de insistir: "
                "troque de abordagem, use tool_buscar_web ou seja honesto com o usuário. "
                "15 minutos é tempo mais que suficiente para resolver algo simples."
            )
            texto_aviso = aviso_relogio
            plano_pendente = _formatar_plano_pendente()
            if plano_pendente:
                texto_aviso += "\n\n" + plano_pendente
            historico_sessao.append(types.Content(role="user", parts=[types.Part.from_text(text=texto_aviso)]))
            if contador_chamadas_api == 1:
                emit_event("status", message="Enviando...")
            else:
                emit_event("status")
            response = chamar_api_com_retry(historico_sessao, config, use_deepseek=use_deepseek, ai_model=ai_model)
            
            if response is None:
                emit_event("error", message="Erro: A API não retornou uma resposta válida.")
                break
                
            if estado.get("cancel_requested"):
                estado["cancel_requested"] = False
                emit_event("status", message=" ")
                emit_event("cancel")
                return
                
            if response.candidates and hasattr(response.candidates[0], 'grounding_metadata') and response.candidates[0].grounding_metadata:
                metadata = response.candidates[0].grounding_metadata
                if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                    urls = []
                    for chunk in metadata.grounding_chunks:
                        if hasattr(chunk, 'web') and chunk.web and hasattr(chunk.web, 'uri'):
                            urls.append(chunk.web.uri)
                    if urls:
                        urls_formatadas = ", ".join(urls)
                        emit_event("status", message=f"Grounding: {urls_formatadas}")
                        emit_event("tool_used", name="Google Grounding", args={"urls_visitadas": urls})
                        ferramentas_usadas_rodada.append(f"Usou Google Grounding. Links: {urls_formatadas}")
                
            pensamentos = []
            textos_finais = []
            citacoes_grounding = []
            
            if response.candidates and response.candidates[0].content.parts:
                partes = response.candidates[0].content.parts
                pensamentos, textos_finais = _extrair_pensamentos_e_textos(partes, bool(response.function_calls))
                citacoes_grounding = _extrair_citacoes_grounding(response, textos_finais)
                            
            if pensamentos:
                emit_event("ai_thought", text="\n\n".join(pensamentos))

            if response.function_calls:
                historico_sessao.append(response.candidates[0].content)
                partes_resposta = []
                imagens_das_ferramentas = []
                medir_contexto(historico=historico_sessao, tokens_base=_tokens_fixos, fase="execucao")
                
                for call in response.function_calls:
                    if estado.get("cancel_requested"):
                        estado["cancel_requested"] = False
                        emit_event("status", message=" ")
                        emit_event("cancel")
                        return
                        
                    nome_func = call.name
                    args = call.args if call.args else {}
                    
                    _emitir_status_da_ferramenta(nome_func, args)
                    
                    args_dict = {k: v for k, v in args.items()} if hasattr(args, 'items') else args
                    emit_event("tool_used", name=nome_func, args=args_dict)
                    registrar_uso_ferramenta(nome_func, args_dict)
                    
                    _registar_resumo_da_ferramenta(nome_func, args_dict, ferramentas_usadas_rodada)
                    
                    resultado, conhecida = dispatch(nome_func, args)
                    if not conhecida:
                        resultado = "Ferramenta desconhecida."
                    texto_resultado, imagens_resultado = _separar_imagem_do_resultado(resultado)
                    imagens_das_ferramentas.extend(imagens_resultado)
                    
                    call_id = getattr(call, 'id', None)
                    partes_resposta.append(types.Part(
                        function_response=types.FunctionResponse(
                            name=nome_func,
                            response={"result": texto_resultado},
                            id=call_id,
                        )
                    ))
                
                historico_sessao.append(types.Content(role="user", parts=partes_resposta))
                if imagens_das_ferramentas:
                    partes_visao = _partes_das_imagens(imagens_das_ferramentas)
                    if partes_visao:
                        historico_sessao.append(types.Content(role="user", parts=partes_visao))
                emit_event("status")
                medir_contexto(historico=historico_sessao, tokens_base=_tokens_fixos, fase="execucao")
                
            else:
                texto_final = "\n".join(textos_finais).strip()
                
                texto_final = re.sub(r"The following is an ephemeral message.*?</EPHEMERAL_MESSAGE>", "", texto_final, flags=re.DOTALL).strip()
                
                texto_final = re.sub(r'^\s*\[Axio (Coder|Counselor)\]:\s*', '', texto_final)
                texto_final = re.sub(r'^\s*Axio (Coder|Counselor)\s*:?\s*', '', texto_final)
                
                if not texto_final:
                    texto_final = "⚠️ [Aviso do Sistema] O processamento foi concluído, mas o agente esqueceu de escrever a mensagem final."

                resumo_semantico = ""
                m_resumo = re.search(r"\[RESUMO_RODADA\]\s*(.*)$", texto_final, flags=re.DOTALL)
                if m_resumo:
                    resumo_semantico = m_resumo.group(1).strip()
                    texto_final = re.sub(r"\s*\[RESUMO_RODADA\].*$", "", texto_final, flags=re.DOTALL).strip()
                    if not texto_final:
                        texto_final = "Processamento concluído."

                texto_usuario_final = prompt_usuario
                linhas_sistema = []
                if ferramentas_usadas_rodada:
                    linhas_sistema.append("[SISTEMA] Ferramentas usadas na rodada anterior: " + " | ".join(ferramentas_usadas_rodada))
                if resumo_semantico:
                    linhas_sistema.append("[SISTEMA] Resumo da rodada: " + resumo_semantico)
                elif any(f in (" | ".join(ferramentas_usadas_rodada)) for f in ("tool_salvar_arquivo", "tool_substituir_texto", "tool_substituir_tudo", "tool_deletar_arquivo", "tool_mover_funcao_verbatim", "tool_mover_bloco_verbatim")):
                    linhas_sistema.append("[SISTEMA] ⚠️ Resumo obrigatório ausente nesta rodada (houve edição).")
                if linhas_sistema:
                    texto_usuario_final = f"{prompt_usuario}\n\n" + "\n".join(linhas_sistema)

                lista_historico.append(types.Content(role="user", parts=[types.Part.from_text(text=texto_usuario_final)]))
                
                nome_agente_atual = "Axio Coder"
                texto_historico = f"[{nome_agente_atual}]: {texto_final}"
                lista_historico.append(types.Content(role="model", parts=[types.Part.from_text(text=texto_historico)]))
                medir_contexto()
                
                timestamp = str(int(time.time()))
                pasta_chats = caminho_estado_projeto("chats")
                os.makedirs(pasta_chats, exist_ok=True)
                caminho_memo = os.path.join(pasta_chats, f"sessao_{timestamp}.txt")
                
                memo_humano = truncar_mensagem_historico(texto_usuario_final)
                memo_ia = truncar_mensagem_historico(texto_final)
                with open(caminho_memo, "w", encoding="utf-8") as f:
                    f.write(f"Humano: {memo_humano}\nIA: [{nome_agente_atual}]: {memo_ia}\n")
                
                texto_exibicao = texto_final
                if citacoes_grounding:
                    texto_exibicao, bloco_fontes = _injetar_citacoes_inline(texto_final, citacoes_grounding)
                    if bloco_fontes:
                        texto_exibicao += bloco_fontes
                emit_event("ai_response", message=texto_exibicao)
                emit_event("ai_question", text=prompt_usuario)
                emit_event("done")

                threading.Thread(
                    target=minerar_em_segundo_plano,
                    args=(pasta_chats, wing_atual),
                    daemon=True,
                ).start()
                break
                
        except ErroContextoExcedido as e:
            if compactar_historico(historico_sessao):
                emit_event("status", message="Limite de contexto atingido. Compactando histórico e continuando...")
                continue
            salvar_checkpoint(prompt_usuario, use_deepseek, e, ferramentas_usadas_rodada, historico_sessao)
            emit_event("status", message=f"Erro (contexto excedido): {str(e)}")
            emit_event("done")
            break
        except Exception as e:
            salvar_checkpoint(prompt_usuario, use_deepseek, e, ferramentas_usadas_rodada, historico_sessao)
            emit_event("status", message=f"Erro: {str(e)}")
            emit_event("done")
            break

    fechar_rodada()
