import os
import time
import threading
import re
import base64
import logging

# Suprime avisos inofensivos do SDK do Google (como "AFC is disabled") no terminal
logging.getLogger("google.genai").setLevel(logging.ERROR)

from src.backend.state import estado, emit_event, set_turn_id, caminho_estado_projeto
from src.backend.memory.vector import wing_da_pasta, espelhar_notas_existentes, buscar_memorias_com_timeout, minerar_em_segundo_plano
from src.backend.memory.store import carregar_indice_knowledge, buscar_knowledge_textual
from src.backend.memory.glossary import tool_gerenciar_glossario
from src.backend.services.session import carregar_checkpoint, formatar_checkpoint, salvar_checkpoint
from src.backend.ai.context import ErroContextoExcedido, compactar_historico, contar_tokens, texto_de_ferramentas, medir_contexto, podar_historico_global, truncar_mensagem_historico
from src.backend.ai.base import chamar_api_com_retry
from src.backend.ai.instructions import build_system_instructions
from src.backend.tools.filesystem import tool_listar_pasta, tool_listar_arvore, tool_ler_arquivo, tool_ler_trecho_arquivo, tool_substituir_texto, tool_salvar_arquivo, tool_deletar_arquivo, tool_pesquisar_no_projeto, tool_mapear_codigo, tool_ler_assinaturas, tool_analisar_simbolo, tool_substituir_tudo, tool_desfazer, tool_refazer, tool_status_desfazer, tool_planejar_arquitetura, tool_iniciar_plano, tool_atualizar_plano, tool_adicionar_etapa_plano
from src.backend.tools.refactor import tool_mover_funcao_verbatim, tool_mover_bloco_verbatim, tool_verificar_integridade_refatoracao, tool_mover_arquivo_binario
from src.backend.tools.process import tool_executar_comando, tool_executar_processo, tool_parar_processo
from src.backend.tools.syntax import tool_validar_sintaxe
from src.backend.tools.environment import tool_info_ambiente
from src.backend.tools.bootstrap import tool_gerenciar_bootstrap
from src.backend.tools.web import tool_buscar_web, tavily_configurada
from src.backend.tools.memory_tools import tool_gerenciar_memoria, tool_gerenciar_banco_vetorial
from src.backend.tools.code_index import gerar_contexto_projeto, disparar_indexacao_background, buscar_codigo_relevante_para_contexto, tool_indexar_codigo, tool_buscar_codigo
from src.backend.tools.audit import tool_corrigir_imports_js, tool_auditar_codigo, tool_analisar_similaridade, tool_auditar_imports_js, tool_auditar_imports_py
from google.genai import types

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

def loop_raciocinio_ia(prompt_usuario, modo="auto", imagens_b64=None, use_deepseek=False, turn_id=None):
    # Marca todos os eventos emitidos nesta thread com o turn_id, para o frontend
    # descartar eventos atrasados de um turno cancelado.
    set_turn_id(turn_id)
    # Modo semi: cada turno começa com a edição bloqueada. Só é liberada se a IA
    # chamar 'tool_aprovar_plano' após perceber a aprovação do usuário (FASE 2).
    estado["bloquear_edicao"] = (modo == "semi")
    estado["urls_navegadas_turno"] = set()

    emit_event("status", message="Coletando memória...")

    disparar_indexacao_background()
    espelhar_notas_existentes()
    wing_atual = wing_da_pasta(estado["pasta_raiz"])
    palace_path = os.path.expanduser("~/.mempalace/palace")

    def _buscar_memoria():
        if not os.path.exists(palace_path):
            return "Nenhuma memória encontrada. Esta é a primeira interação."
        resultados = buscar_memorias_com_timeout(
            query=prompt_usuario,
            palace_path=palace_path,
            wing=wing_atual,
            n_results=8,
        )
        if resultados.get("error"):
            print(f"Erro no mempalace: {resultados['error']}")
            return buscar_knowledge_textual(prompt_usuario)
        hits = resultados.get("results", [])
        return "\n".join([hit['text'] for hit in hits]) if hits else "(nenhuma memória relevante para esta consulta)"

    contexto = {}

    def _coletar(nome, fn):
        try:
            contexto[nome] = fn()
        except Exception as e:
            contexto[nome] = f"[falha ao carregar contexto de {nome}: {e}]"

    tarefas = [
        ("projeto", gerar_contexto_projeto),
        ("memoria", _buscar_memoria),
        ("ai_memory", lambda: carregar_indice_knowledge(prompt_usuario)),
        ("codigo", lambda: buscar_codigo_relevante_para_contexto(prompt_usuario)),
    ]
    threads = [threading.Thread(target=_coletar, args=(n, f), daemon=True) for n, f in tarefas]
    for t in threads:
        t.start()

    fases = ["Coletando memória", "Indexado", "Processando..."]
    INTERVALO_FASE = 1.0
    idx_fase = 0
    ultimo_avanco = time.time()

    while True:
        todas_concluidas = not any(t.is_alive() for t in threads)
        agora = time.time()
        if idx_fase < len(fases) - 1 and (agora - ultimo_avanco) >= INTERVALO_FASE:
            idx_fase += 1
            emit_event("status", message=f"{fases[idx_fase]}...")
            ultimo_avanco = agora
        if todas_concluidas and idx_fase >= len(fases) - 1 and (agora - ultimo_avanco) >= INTERVALO_FASE:
            break
        time.sleep(0.04)

    for t in threads:
        t.join()

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

    instrucao = build_system_instructions(modo, contexto_memoria, contexto_ai_memory, bloco_continuidade, contexto_projeto, contexto_codigo, contexto_edicoes, tem_web_search=tavily_configurada(), use_deepseek=use_deepseek)

    ferramentas_base = [
        types.FunctionDeclaration(
    name="tool_listar_pasta", 
    description="Lista o conteúdo de uma pasta. Use sem argumentos para a raiz ou passe 'caminho_relativo' para explorar subpastas.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "caminho_relativo": types.Schema(type=types.Type.STRING, description="Subpasta opcional")
        }
    )

),
        types.FunctionDeclaration(
    name="tool_listar_arvore", 
    description="Mapeia recursivamente a árvore/estrutura de pastas e arquivos do projeto em formato de árvore (com ramos e indentação), já ignorando pastas inúteis (node_modules, .git, __pycache__, binários etc.). USE ESTA ferramenta (não tool_listar_pasta) quando precisar descobrir a estrutura geral do projeto ou localizar onde um arquivo/pasta está, sem navegar pasta a pasta. Pastas muito grandes são truncadas com aviso explícito '( +N itens ocultos)' — nada é ocultado sem aviso.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "caminho_relativo": types.Schema(type=types.Type.STRING, description="Pasta inicial (padrão: raiz do projeto)"),
            "profundidade_max": types.Schema(type=types.Type.INTEGER, description="Profundidade máxima (padrão 4)"),
            "max_entradas": types.Schema(type=types.Type.INTEGER, description="Teto de entradas exibidas no total (padrão 400)")
        }
    )

),
        types.FunctionDeclaration(name="tool_ler_arquivo", description="Lê o conteúdo completo. USE APENAS para arquivos pequenos (até ~600 linhas ou ~25k caracteres). Para arquivos grandes como .cpp, use obrigatoriamente 'tool_mapear_codigo' primeiro e depois 'tool_ler_trecho_arquivo'.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING")}, required=["caminho_relativo"])),
        types.FunctionDeclaration(name="tool_ler_trecho_arquivo", description="Lê linhas específicas de um arquivo.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING"), "linha_inicio": types.Schema(type="INTEGER"), "linha_fim": types.Schema(type="INTEGER")}, required=["caminho_relativo", "linha_inicio", "linha_fim"])),
        
        types.FunctionDeclaration(name="tool_executar_comando", description="Executa COMPILAÇÃO real (cmake --build build, make, g++, etc.). PROIBIDO usar para ler/editar/buscar/validar sintaxe (Python, sed, awk, grep, cat, echo, mkdir, type, node --check) — para isso use as ferramentas nativas: tool_ler_arquivo, tool_substituir_texto, tool_pesquisar_no_projeto, tool_validar_sintaxe. Use apenas para compilação que não tenha ferramenta nativa correspondente.", parameters=types.Schema(type="OBJECT", properties={"comando": types.Schema(type="STRING")}, required=["comando"])),
        types.FunctionDeclaration(
            name="tool_pesquisar_no_projeto", 
            description="Busca ocorrências de string no código (compara com normalização Unicode NFC — acentos compostos e decompostos casam automaticamente). PROIBIDO pesquisar termos de leigo passados pelo humano (Ex: porta, alisar, camera, parede etc). Se o usuário citar, primeiro mapeie o código ou leia as assinaturas para descobrir o nome correto e evitar perder tempo.", 
            parameters=types.Schema(type="OBJECT", properties={"termo": types.Schema(type="STRING")}, required=["termo"])
        ),
        types.FunctionDeclaration(name="tool_mapear_codigo", description="Lista as funções e classes de um arquivo para você saber onde alterar.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING")}, required=["caminho_relativo"])),
        types.FunctionDeclaration(name="tool_ler_assinaturas", description="Lê apenas as assinaturas de funções de um arquivo grande.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING")}, required=["caminho_relativo"])),
        types.FunctionDeclaration(name="tool_indexar_codigo", description="Atualiza o índice semântico de código do projeto (embeddings dos trechos de código no ChromaDB). É INCREMENTAL: só reprocessa os arquivos que mudaram desde a última indexação, então normalmente termina em segundos. A indexação também roda automaticamente no início de cada rodada.", parameters=types.Schema(type="OBJECT", properties={"forcar": types.Schema(type="BOOLEAN", description="Reconstrói o índice do zero, ignorando o cache por hash. Use raramente e só se o índice estiver corrompido — em projetos grandes isso demora minutos.")})),
        types.FunctionDeclaration(name="tool_buscar_codigo", description="Busca trechos de código relevantes por similaridade semântica no índice de código do projeto (codebase indexing, como o Cursor). Use para localizar código por descrição/contexto, não por termo exato.", parameters=types.Schema(type="OBJECT", properties={"query": types.Schema(type="STRING", description="Descrição ou contexto do que procura no código")}, required=["query"])),
        types.FunctionDeclaration(name="tool_analisar_simbolo", description="Usa o clangd para verificar erros de sintaxe após você fazer uma edição.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING"), "termo": types.Schema(type="STRING")}, required=["caminho_relativo", "termo"])),
        types.FunctionDeclaration(name="tool_validar_sintaxe", description="Valida a sintaxe de um arquivo (Python, JavaScript, TypeScript, JSON ou CSS) após editar/mover código. Use SEMPRE após edições para confirmar que não quebrou sintaxe — NÃO use comandos proibidos (python, py_compile, node --check, grep, sed, cat, echo) para isso. Retorna OK ou o erro com linha/coluna.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING"), "linguagem": types.Schema(type="STRING", enum=["python", "javascript", "typescript", "json", "css"])}, required=["caminho_relativo"])),
        types.FunctionDeclaration(name="tool_gerenciar_memoria", description="Acessa memória persistente.", parameters=types.Schema(type="OBJECT", properties={"acao": types.Schema(type="STRING", enum=["ler", "escrever", "listar", "excluir"]), "titulo": types.Schema(type="STRING"), "conteudo": types.Schema(type="STRING")}, required=["acao"])),
        types.FunctionDeclaration(name="tool_gerenciar_banco_vetorial", description="Gerencia o banco de dados vetorial do mempalace. Use acao='varredura' para listar as drawers e identificar órfãs/obsoletas e acao='reparar' para reconstruir o índice HNSW (equivale a 'mempalace repair', rodando dentro do Flask sem risco de lock).", parameters=types.Schema(type="OBJECT", properties={"acao": types.Schema(type="STRING", enum=["ler", "escrever", "listar", "deletar", "varredura", "reparar"]), "caminho_relativo": types.Schema(type="STRING"), "conteudo": types.Schema(type="STRING")}, required=["acao"])),
        types.FunctionDeclaration(name="tool_gerenciar_glossario", description="Gerencia o glossario de termos leigos -> codigo (data/glossary.json). Use quando descobrir um termo leigo do usuario mapeado para um identificador real (ex: 'icone do editor' -> '#btn-editor'). acao='escrever' grava com filtro critico + dedup no backend; acao='listar' mostra os termos; acao='remover' apaga. Use com criterio: so salve termos concretos e verificados no codigo, para nao poluir o glossario (ele e injetado no seu contexto toda rodada).", parameters=types.Schema(type="OBJECT", properties={"acao": types.Schema(type="STRING", enum=["listar", "escrever", "remover"]), "termo": types.Schema(type="STRING", description="Termo leigo do usuario (ex: 'icone do editor')"), "aliases": types.Schema(type="STRING", description="Sinonimos separados por virgula"), "identificador": types.Schema(type="STRING", description="Identificador real no codigo (ex: '#btn-editor', '#editor-host', nome de funcao)"), "descricao": types.Schema(type="STRING"), "localizacao_arquivo": types.Schema(type="STRING", description="Arquivo onde o identificador vive"), "localizacao_linha": types.Schema(type="INTEGER", description="Linha aproximada")}, required=["acao"])),
        types.FunctionDeclaration(name="tool_gerenciar_bootstrap", description="Gerencia o estado de um bootstrap de projeto (Supabase/Firebase/serviço) para retomada segura. Use acao='gravar' para registrar progresso ou parar aguardando uma credencial, acao='ler' para retomar de onde parou e acao='limpar' ao concluir o bootstrap. Ao concluir definitivamente, chame gravar com concluido=true (ou acao='limpar') para que o estado pare de ser injetado.", parameters=types.Schema(type="OBJECT", properties={"acao": types.Schema(type="STRING", enum=["ler", "gravar", "limpar"]), "servico": types.Schema(type="STRING", description="Nome do serviço (ex: supabase, firebase, gcloud)"), "etapa_atual": types.Schema(type="STRING", description="Descrição da etapa atual em andamento"), "etapa_concluida": types.Schema(type="STRING", description="Etapa concluída para adicionar à lista acumulada"), "aguardando": types.Schema(type="STRING", description="O que está aguardando do usuário (ex: credencial/token)"), "concluido": types.Schema(type="BOOLEAN", description="Marque true quando o bootstrap estiver definitivamente concluído, para não ser mais injetado no contexto")}, required=["acao"])),
        types.FunctionDeclaration(name="tool_info_ambiente", description="Retorna metadados do ambiente: caminho do venv em uso, versões de Python, Mempalace e ChromaDB, diretórios de leitura permitidos e estado do palace do mempalace.", parameters=types.Schema(type="OBJECT", properties={})),
        types.FunctionDeclaration(name="tool_verificar_integridade_refatoracao", description="Verifica se uma função movida por refatoração permaneceu idêntica (verbatim) ao original, comparando hash e byte a byte. Use após tool_mover_funcao_verbatim para provar que o movimento não alterou nada.", parameters=types.Schema(type="OBJECT", properties={"arquivo_origem": types.Schema(type="STRING"), "nome_funcao": types.Schema(type="STRING"), "arquivo_destino": types.Schema(type="STRING"), "hash_esperado": types.Schema(type="STRING")}, required=["arquivo_destino", "nome_funcao"])),
    ]

    if modo != "guided":
        ferramentas_base.extend([
            types.FunctionDeclaration(name="tool_mover_funcao_verbatim", description="Move uma função/classe inteira de um arquivo para outro copiando os bytes exatos do disco (verbatim, sem redigitar, sem simplificar). Detecta o range completo da função (início e fim) por AST no Python e por balanceamento de chaves no JavaScript. Opcionalmente remove a função do arquivo de origem. Use preview=true para dry-run (mostra linhas + SHA-256 sem escrever/remover nada). Retorna o SHA-256 do corpo movido para verificação.", parameters=types.Schema(type="OBJECT", properties={"arquivo_origem": types.Schema(type="STRING"), "nome_funcao": types.Schema(type="STRING"), "arquivo_destino": types.Schema(type="STRING"), "remover_origem": types.Schema(type="BOOLEAN"), "preview": types.Schema(type="BOOLEAN")}, required=["arquivo_origem", "nome_funcao", "arquivo_destino"])),
            types.FunctionDeclaration(name="tool_mover_bloco_verbatim", description="Move um bloco/range de linhas (ou um bloco delimitado por tags, ex: '<style>...</style>') de um arquivo para outro copiando os bytes exatos do disco (verbatim, sem redigitar). Use OU linha_inicio/linha_fim OU tag_abertura/tag_fechamento (com 'ocorrencia' para escolher qual bloco quando houver mais de um). Remove o bloco da origem e verifica por SHA-256 e por presença/ausência que saiu inteiro da origem e entrou idêntico no destino. Ideal para CSS/HTML/blocos de texto que tool_mover_funcao_verbatim não cobre. Use SEMPRE para mover blocos grandes em vez de fatiar manualmente.", parameters=types.Schema(type="OBJECT", properties={"arquivo_origem": types.Schema(type="STRING"), "arquivo_destino": types.Schema(type="STRING"), "linha_inicio": types.Schema(type="INTEGER"), "linha_fim": types.Schema(type="INTEGER"), "tag_abertura": types.Schema(type="STRING"), "tag_fechamento": types.Schema(type="STRING"), "remover_origem": types.Schema(type="BOOLEAN"), "ocorrencia": types.Schema(type="INTEGER")}, required=["arquivo_origem", "arquivo_destino"])),
            types.FunctionDeclaration(name="tool_substituir_texto", description="Substitui texto (compara com normalização Unicode NFC — acentos compostos e decompostos casam automaticamente). NUNCA substitua caractere acentuado isolado; use âncoras longas e únicas.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING"), "texto_antigo": types.Schema(type="STRING"), "texto_novo": types.Schema(type="STRING")}, required=["caminho_relativo", "texto_antigo", "texto_novo"])),
            types.FunctionDeclaration(name="tool_salvar_arquivo", description="Salva arquivo.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING"), "conteudo": types.Schema(type="STRING")}, required=["caminho_relativo", "conteudo"])),
            types.FunctionDeclaration(name="tool_deletar_arquivo", description="Move um arquivo ou uma pasta do projeto para a lixeira (recuperável pela interface, inclusive pasta vazia). Não exclui a raiz do projeto nem as pastas .git e .axio.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING")}, required=["caminho_relativo"])),
            types.FunctionDeclaration(name="tool_substituir_tudo", description="Substitui todas as ocorrências (compara com normalização Unicode NFC). PERIGO: nunca use para caractere acentuado isolado (ex: 'ó'->'o') — corrompe o arquivo; use apenas com palavras/âncoras completas.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING"), "texto_antigo": types.Schema(type="STRING"), "texto_novo": types.Schema(type="STRING")}, required=["caminho_relativo", "texto_antigo", "texto_novo"])),
            types.FunctionDeclaration(name="tool_executar_processo", description="Executa processos longos ou de bootstrap: criar venv, instalar dependências (pip/npm) e rodar servidores. Use modo='aguardar' (padrão) para venv/instalações e modo='segundo_plano' para servidores que não terminam (npm start, flask run).", parameters=types.Schema(type="OBJECT", properties={"comando": types.Schema(type="STRING"), "modo": types.Schema(type="STRING", enum=["aguardar", "segundo_plano"]), "timeout": types.Schema(type="INTEGER")}, required=["comando"])),
            types.FunctionDeclaration(name="tool_parar_processo", description="Para (mata) um processo em segundo plano pelo pid. Use para encerrar servidores e processos longos antes de reinicia-los. Obtenha os pids em /api/processos.", parameters=types.Schema(type="OBJECT", properties={"pid": types.Schema(type="STRING", description="Identificador do processo (ex: proc_1)")}, required=["pid"])),
            types.FunctionDeclaration(name="tool_mover_arquivo_binario", description="Move um arquivo binário ou uma pasta inteira (ícones, imagens, fontes, binários) de um lugar para outro byte a byte usando shutil.move. Use para mover .ico, .png, .exe ou pastas inteiras que tool_mover_bloco_verbatim não consegue (só lida com texto). Retorna o SHA-256 do arquivo movido e verifica que a origem sumiu e o destino apareceu.", parameters=types.Schema(type="OBJECT", properties={"origem": types.Schema(type="STRING", description="Caminho relativo do arquivo ou pasta a mover"), "destino": types.Schema(type="STRING", description="Caminho relativo de destino (arquivo ou pasta)"), "sobrescrever": types.Schema(type="BOOLEAN", description="Se True, substitui o destino caso já exista")}, required=["origem", "destino"])),
            types.FunctionDeclaration(name="tool_desfazer", description="Desfaz (undo) a edição mais recente de um arquivo, restaurando o conteúdo de ANTES daquela edição. Use quando uma edição recém-feita quebrou a sintaxe ou a lógica e corrigir manualmente não vale a pena. Funciona também para edições atômicas em grupo (ex: mover função restaura origem+destino juntos). Receba o caminho_relativo do arquivo. Para saber o que pode ser desfeito, chame antes 'tool_status_desfazer'.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING", description="Caminho relativo do arquivo a desfazer (ex: src/backend/app.py)")}, required=["caminho_relativo"])),
            types.FunctionDeclaration(name="tool_refazer", description="Refaz (redo) a edição desfeita mais recente de um arquivo, reaplicando o conteúdo de DEPOIS daquela edição. Use para reverter um 'tool_desfazer' feito por engano.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING", description="Caminho relativo do arquivo a refazer (ex: src/backend/app.py)")}, required=["caminho_relativo"])),
            types.FunctionDeclaration(name="tool_status_desfazer", description="Lista, por arquivo, quantas edições estão disponíveis para desfazer e refazer nesta sessão. Use para decidir qual arquivo desfazer/refazer e em quantos passos.", parameters=types.Schema(type="OBJECT", properties={})),
            types.FunctionDeclaration(name="tool_corrigir_imports_js", description="Varre os módulos JS de uma pasta, identifica dependências cruzadas (exports usados em outros arquivos) e injeta os imports corretos no topo de cada arquivo automaticamente.", parameters=types.Schema(type="OBJECT", properties={"pasta_js": types.Schema(type="STRING", description="Caminho da pasta contendo os arquivos JS (ex: src/frontend/js/chat)")}, required=["pasta_js"])),
            types.FunctionDeclaration(name="tool_auditar_codigo", description="Executa um linter (ESLint para JS/TS, Ruff para Python) e reporta variáveis não declaradas (no-undef) e código não usado (no-unused-vars). Exige 'linguagem'.", parameters=types.Schema(type="OBJECT",properties={"caminho_relativo": types.Schema(type="STRING", description="Caminho do arquivo a ser auditado"),"linguagem": types.Schema(type="STRING", description="Linguagem do código (ex: javascript, python etc)")},required=["caminho_relativo", "linguagem"])),
            types.FunctionDeclaration(name="tool_analisar_similaridade", description="Analisa a similaridade de código em um arquivo ou pasta usando jscpd.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING", description="Caminho do arquivo ou pasta a ser analisado"), "min_linhas": types.Schema(type="INTEGER", description="Número mínimo de linhas para considerar como duplicado (padrão: 5)")}, required=["caminho_relativo"])),
            types.FunctionDeclaration(name="tool_auditar_imports_js", description="Audita módulos JavaScript (imports, destructuring e declarações) e cruza os dados entre os módulos da pasta para classificar cada símbolo não usado como: ÓRFÃO LOCAL (usado em outro módulo, remover só do import daqui), DEAD CODE GLOBAL (não usado em lugar nenhum, candidato a apagar a definição) ou FALTANTE (usado mas não importado, risco de ReferenceError). NÃO edita nada, apenas reporta. Use para auditar uma pasta ou arquivo .js específico.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING", description="Arquivo .js ou pasta contendo os módulos (ex: src/frontend/js/chat)")}, required=["caminho_relativo"])),
            types.FunctionDeclaration(name="tool_auditar_imports_py", description="Audita modulos Python (AST + symtable, com escopos reais) e classifica: FALTANTE (nome usado como global mas nao importado/definido no modulo -> risco de NameError), IMPORT NAO USADO (candidato a remover, ja descontando reexports e __all__) e DEAD CODE GLOBAL (funcao/classe de topo nunca referenciada no projeto). NAO edita nada, apenas reporta.", parameters=types.Schema(type="OBJECT", properties={"caminho_relativo": types.Schema(type="STRING", description="Arquivo .py ou pasta contendo os modulos (ex: src/backend/routes)")}, required=["caminho_relativo"])),
            types.FunctionDeclaration(name="tool_analisar_dependencias_globais_js", description="Analisa scripts JS clássicos em uma pasta usando AST (tree-sitter) para descobrir quais variáveis/funções globais cada arquivo declara e quais ele consome de outros arquivos. Essencial para planejar migração para ESM.", parameters=types.Schema(type="OBJECT", properties={"pasta": types.Schema(type="STRING", description="Pasta contendo os scripts (ex: src/frontend/js/editor)")}, required=["pasta"])),
            types.FunctionDeclaration(name="tool_migrar_para_esm", description="Migra scripts JS clássicos para ES Modules (ESM) injetando 'export' nas declarações globais e 'import' para as dependências externas, baseado na análise AST.", parameters=types.Schema(type="OBJECT", properties={"pasta": types.Schema(type="STRING", description="Pasta contendo os scripts (ex: src/frontend/js/editor)")}, required=["pasta"])),
            types.FunctionDeclaration(name="tool_planejar_arquitetura", description="Obrigatório antes de criar projetos novos. Fluxo PESQUISA-PRIMEIRO: pesquise a stack na documentação oficial ANTES e decida com base no que leu; o backend valida que as URLs citadas foram realmente navegadas neste turno (inventou = rejeitado). Valida a stack e libera a trava de segurança para salvar arquivos. No campo 'stack' preencha uma LISTA técnica COM RÓTULO: UMA linha POR categoria, agrupando itens da MESMA categoria separados por vírgula (padrão 'Categoria: Nome versão_real', ex: 'Linguagem: Python 3.14', 'Framework: Flask 3.1.3', 'Estilo: CSS', 'Linguagem: HTML5, JavaScript (ES Modules)'). NUNCA repita a mesma categoria em duas linhas. Categorias NESTA ordem: Linguagem, Runtime, Framework, Dependências, API externa, Build, CI/CD, Banco de dados, Estilo. OMITA 'Formato de saída' e 'Ambiente' quando triviais (site estático não precisa deles). Versão só quando houver versão real (HTML/CSS/JS vanilla não têm). PROIBIDO escrever 'sem framework', 'sem build step', 'sem dependências' (omita o item inexistente) e adjetivos vagos ('CSS3 moderno'/'HTML5 semântico' -> use só 'CSS'/'HTML5'). Nunca invente versões. Em 'urls_pesquisadas' PESQUISE antes (mesmo projeto estático, ao menos MDN) e cite APENAS as URLs que realmente abriu (as do status 'Navegando:'), UMA por linha; nunca escreva 'Nenhuma' nem invente/troque blog por MDN; se a fonte não for oficial, refaça a pesquisa em documentação oficial ou GitHub oficial. No campo 'estrutura_pastas' descreva a árvore de diretórios completa.", parameters=types.Schema(type="OBJECT", properties={"stack": types.Schema(type="STRING"), "urls_pesquisadas": types.Schema(type="STRING"), "estrutura_pastas": types.Schema(type="STRING"), "etapas_planejamento": types.Schema(type="STRING")}, required=["stack", "urls_pesquisadas", "estrutura_pastas", "etapas_planejamento"])),
            types.FunctionDeclaration(name="tool_iniciar_plano", description="Inicia a exibição visual de um plano de execução na interface (coluna 3). Use antes de começar tarefas complexas ou projetos novos. O plano_json deve ser uma string JSON com a estrutura: [{'id': 'etapa1', 'titulo': 'Validando Stack', 'tarefas': ['Pesquisar', 'Definir']}]", parameters=types.Schema(type="OBJECT", properties={"plano_json": types.Schema(type="STRING")}, required=["plano_json"])),
            types.FunctionDeclaration(name="tool_atualizar_plano", description="Atualiza o status de uma tarefa no plano visual. Risca a tarefa concluída e, se etapa_concluida=true, marca a etapa inteira como concluída.", parameters=types.Schema(type="OBJECT", properties={"id_etapa": types.Schema(type="STRING"), "tarefa_concluida": types.Schema(type="STRING"), "etapa_concluida": types.Schema(type="BOOLEAN")}, required=["id_etapa", "tarefa_concluida", "etapa_concluida"])),
            types.FunctionDeclaration(name="tool_adicionar_etapa_plano", description="Adiciona uma nova etapa ao plano visual em andamento. nova_etapa_json deve ser uma string JSON: {'id': 'etapa_extra', 'titulo': 'Nova Etapa', 'tarefas': ['Tarefa 1']}", parameters=types.Schema(type="OBJECT", properties={"nova_etapa_json": types.Schema(type="STRING")}, required=["nova_etapa_json"])),
            types.FunctionDeclaration(name="tool_gerar_wiring_dom_state", description="Gera o código de wiring (ligação) entre elementos do DOM e o estado global.", parameters=types.Schema(type="OBJECT", properties={"caminho_arquivo": types.Schema(type="STRING")}, required=["caminho_arquivo"]))
        ])

    if modo == "semi":
        ferramentas_base.append(
            types.FunctionDeclaration(
                name="tool_aprovar_plano",
                description="Destrava as ferramentas de edição no modo semi-automático. Chame apenas quando perceber que o usuário aprovou/confirmou o plano (qualquer forma de 'sim', 'pode', 'aplica', etc.)."
            )
        )

    if tavily_configurada() and use_deepseek:
        ferramentas_base.append(
            types.FunctionDeclaration(name="tool_buscar_web", description="Pesquisa na internet ou extrai conteúdo de uma URL específica. Use 'query' para buscar por termo ou 'url_especifica' para extrair uma página. O conteúdo bruto completo fica em 'busca.txt'. Priorize documentações de apis dos sites oficiais caso o scrap esteja disponível.", parameters=types.Schema(type="OBJECT", properties={"query": types.Schema(type="STRING", description="Termo de busca na web"), "url_especifica": types.Schema(type="STRING", description="URL específica para extrair conteúdo")}))
        )

    if use_deepseek:
        lista_tools = [types.Tool(function_declarations=ferramentas_base)]
    else:
        lista_tools = [
            types.Tool(function_declarations=ferramentas_base),
            types.Tool(google_search=types.GoogleSearch())
        ]

    config = types.GenerateContentConfig(
        system_instruction=instrucao,
        tools=lista_tools,
        temperature=0.1,
        thinking_config=types.ThinkingConfig(include_thoughts=True),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
    )
    
    partes_usuario = [types.Part.from_text(text=prompt_usuario)]
    if imagens_b64:
        for img_data in imagens_b64:
            if isinstance(img_data, dict):
                img_b64 = img_data.get("base64")
                img_name = img_data.get("name", "imagem")
                partes_usuario.append(types.Part.from_text(text=f"[Imagem anexada: {img_name}]"))
                partes_usuario.append(types.Part.from_bytes(data=base64.b64decode(img_b64), mime_type="image/jpeg"))
            else:
                partes_usuario.append(types.Part.from_bytes(data=base64.b64decode(img_data), mime_type="image/jpeg"))
        
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
            response = chamar_api_com_retry(historico_sessao, config, use_deepseek=use_deepseek)
            
            if response is None:
                emit_event("error", message="Erro: A API não retornou uma resposta válida.")
                break
                
            if estado.get("cancel_requested"):
                estado["cancel_requested"] = False
                emit_event("status", message=" ")
                emit_event("cancel")
                return
                
            # Captura dos links consultados pelo Gemini (Grounding)
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
            
            if response.candidates and response.candidates[0].content.parts:
                partes = response.candidates[0].content.parts
                for i, p in enumerate(partes):
                    # 1. Raciocínio explícito preservado (DeepSeek): campo próprio, nunca vai pro texto final.
                    rc = getattr(p, 'reasoning_content', None)
                    if rc:
                        pensamentos.append(rc.strip())
                        continue
                    if not (hasattr(p, 'text') and p.text):
                        continue
                    texto = p.text
                    # 2. Parte marcada como pensamento (Gemini).
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
                    elif len(partes) > 1 and i == 0 and not response.function_calls:
                        # Se tem mais de uma parte, não é chamada de função, e é a primeira parte
                        # Verifica se a próxima parte também é texto. Se for, a primeira é pensamento.
                        tem_outro_texto = any(hasattr(p_next, 'text') and p_next.text for p_next in partes[i+1:])
                        if tem_outro_texto:
                            pensamentos.append(texto)
                        else:
                            textos_finais.append(texto)
                    elif len(partes) > 1 and i == 0 and response.function_calls:
                        # Se tem chamada de função, a primeira parte de texto geralmente é o pensamento
                        pensamentos.append(texto)
                    else:
                        textos_finais.append(texto)
                            
            if pensamentos:
                emit_event("ai_thought", text="\n\n".join(pensamentos))

            if response.function_calls:
                historico_sessao.append(response.candidates[0].content)
                partes_resposta = []
                medir_contexto(historico=historico_sessao, tokens_base=_tokens_fixos, fase="execucao")
                
                for call in response.function_calls:
                    if estado.get("cancel_requested"):
                        estado["cancel_requested"] = False
                        emit_event("status", message=" ")
                        emit_event("cancel")
                        return
                        
                    nome_func = call.name
                    args = call.args if call.args else {}
                    
                    # LOG PARA A INTERFACE
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
                    elif nome_func in ("tool_ler_trecho_arquivo", "tool_ler_arquivo") and args.get("caminho_relativo", "") in ("busca.txt", "debug_tavily.txt"):
                        alvo = args.get("caminho_relativo", "")
                        emit_event("status", message=f"Extraindo informação: {alvo}")
                    elif nome_func == "tool_info_ambiente":
                        emit_event("status", message="Coletando informações do ambiente...")
                    elif nome_func == "tool_gerenciar_bootstrap":
                        emit_event("status", message=f"Gerenciando estado de bootstrap ({args.get('acao', 'ler')})...")
                    elif nome_func in ("tool_desfazer", "tool_refazer"):
                        emit_event("status", message=f"{'Desfazendo' if nome_func == 'tool_desfazer' else 'Refazendo'}: {args.get('caminho_relativo', '')}")
                    elif nome_func == "tool_status_desfazer":
                        emit_event("status", message="Consultando histórico de desfazer/refazer...")
                    elif nome_func in ("tool_planejar_arquitetura", "tool_iniciar_plano", "tool_atualizar_plano", "tool_adicionar_etapa_plano"):
                        emit_event("status", message="Organizando plano de execução...")
                    else:
                        alvo = args.get("caminho_relativo", "raiz do projeto")
                        nome_limpo = nome_func.replace("tool_", "")
                        msg_acao = f"Axio acionou {nome_limpo} em '{alvo}'..."
                        emit_event("status", message=msg_acao)
                    
                    # ENVIAR EVENTO DE FERRAMENTA USADA
                    args_dict = {k: v for k, v in args.items()} if hasattr(args, 'items') else args
                    emit_event("tool_used", name=nome_func, args=args_dict)
                    
                    # REGISTRAR PARA O HISTÓRICO RESUMIDO
                    resumo_acao = f"Usou {nome_func}"
                    if "caminho_relativo" in args_dict:
                        resumo_acao += f" em {args_dict['caminho_relativo']}"
                    if "texto_novo" in args_dict:
                        texto_novo = args_dict['texto_novo']
                        if len(texto_novo) > 200:
                            texto_novo = texto_novo[:200] + " [...]"
                        resumo_acao += f". Trecho: '{texto_novo}'"
                    ferramentas_usadas_rodada.append(resumo_acao)
                    
                    caminho = args.get("caminho_relativo") if args.get("caminho_relativo") else ""
                    if nome_func == "tool_listar_pasta": resultado = tool_listar_pasta(caminho)
                    elif nome_func == "tool_listar_arvore": resultado = tool_listar_arvore(caminho, int(args.get("profundidade_max", 4)), int(args.get("max_entradas", 400)))
                    elif nome_func == "tool_ler_arquivo": resultado = tool_ler_arquivo(caminho)
                    elif nome_func == "tool_ler_trecho_arquivo": resultado = tool_ler_trecho_arquivo(caminho, int(args.get("linha_inicio", 1)), int(args.get("linha_fim", int(args.get("linha_inicio", 1)) + 400)))
                    elif nome_func == "tool_substituir_texto": resultado = tool_substituir_texto(caminho, args.get("texto_antigo", ""), args.get("texto_novo", ""))
                    elif nome_func == "tool_planejar_arquitetura": resultado = tool_planejar_arquitetura(args.get("stack", ""), args.get("urls_pesquisadas", ""), args.get("estrutura_pastas", ""), args.get("etapas_planejamento", ""))
                    elif nome_func == "tool_iniciar_plano": resultado = tool_iniciar_plano(args.get("plano_json", ""))
                    elif nome_func == "tool_atualizar_plano": resultado = tool_atualizar_plano(args.get("id_etapa", ""), args.get("tarefa_concluida", ""), args.get("etapa_concluida", False))
                    elif nome_func == "tool_adicionar_etapa_plano": resultado = tool_adicionar_etapa_plano(args.get("nova_etapa_json", ""))
                    elif nome_func == "tool_salvar_arquivo": resultado = tool_salvar_arquivo(caminho, args.get("conteudo", ""))
                    elif nome_func == "tool_deletar_arquivo": resultado = tool_deletar_arquivo(caminho)
                    elif nome_func == "tool_executar_comando": resultado = tool_executar_comando(args.get("comando", ""))
                    elif nome_func == "tool_executar_processo": resultado = tool_executar_processo(args.get("comando", ""), args.get("modo", "aguardar"), args.get("timeout"))
                    elif nome_func == "tool_parar_processo": resultado = tool_parar_processo(args.get("pid", ""))
                    elif nome_func == "tool_pesquisar_no_projeto": resultado = tool_pesquisar_no_projeto(args.get("termo", ""))
                    elif nome_func == "tool_mapear_codigo": resultado = tool_mapear_codigo(caminho)
                    elif nome_func == "tool_ler_assinaturas": resultado = tool_ler_assinaturas(caminho)
                    elif nome_func == "tool_indexar_codigo": resultado = tool_indexar_codigo(args.get("forcar", False))
                    elif nome_func == "tool_buscar_codigo": resultado = tool_buscar_codigo(args.get("query", ""))
                    elif nome_func == "tool_analisar_simbolo": resultado = tool_analisar_simbolo(caminho, args.get("termo", ""))
                    elif nome_func == "tool_validar_sintaxe": resultado = tool_validar_sintaxe(caminho, args.get("linguagem", ""))
                    elif nome_func == "tool_substituir_tudo": resultado = tool_substituir_tudo(caminho, args.get("texto_antigo", ""), args.get("texto_novo", ""))
                    elif nome_func == "tool_aprovar_plano": resultado = tool_aprovar_plano()
                    elif nome_func == "tool_gerenciar_memoria": resultado = tool_gerenciar_memoria(args.get("acao"), args.get("titulo"), args.get("conteudo"))
                    elif nome_func == "tool_gerenciar_banco_vetorial": resultado = tool_gerenciar_banco_vetorial(args.get("acao"), args.get("caminho_relativo", ""), args.get("conteudo"))
                    elif nome_func == "tool_gerenciar_glossario": resultado = tool_gerenciar_glossario(args.get("acao"), args.get("termo"), args.get("aliases"), args.get("identificador"), args.get("descricao"), args.get("localizacao_arquivo"), args.get("localizacao_linha"))
                    elif nome_func == "tool_gerenciar_bootstrap": resultado = tool_gerenciar_bootstrap(args.get("acao", "ler"), args.get("servico", ""), args.get("etapa_atual", ""), args.get("etapa_concluida", ""), args.get("aguardando", ""), False, args.get("concluido", False))
                    elif nome_func == "tool_buscar_web": resultado = tool_buscar_web(args.get("query", ""), args.get("url_especifica", ""))
                    elif nome_func == "tool_mover_funcao_verbatim": resultado = tool_mover_funcao_verbatim(args.get("arquivo_origem", ""), args.get("nome_funcao", ""), args.get("arquivo_destino", ""), args.get("remover_origem", True), args.get("preview", False))
                    elif nome_func == "tool_mover_bloco_verbatim": resultado = tool_mover_bloco_verbatim(args.get("arquivo_origem", ""), args.get("arquivo_destino", ""), args.get("linha_inicio", 0), args.get("linha_fim", 0), args.get("tag_abertura", ""), args.get("tag_fechamento", ""), args.get("remover_origem", True), args.get("ocorrencia", 1))
                    elif nome_func == "tool_verificar_integridade_refatoracao": resultado = tool_verificar_integridade_refatoracao(args.get("arquivo_origem", ""), args.get("nome_funcao", ""), args.get("arquivo_destino", ""), args.get("hash_esperado", ""))
                    elif nome_func == "tool_corrigir_imports_js": resultado = tool_corrigir_imports_js(args.get("pasta_js", ""))
                    elif nome_func == "tool_auditar_codigo": resultado = tool_auditar_codigo(args.get("caminho_relativo", ""), args.get("linguagem", "javascript"))
                    elif nome_func == "tool_analisar_similaridade": resultado = tool_analisar_similaridade(args.get("caminho_relativo", ""), args.get("min_linhas", 5))
                    elif nome_func == "tool_auditar_imports_js": resultado = tool_auditar_imports_js(args.get("caminho_relativo", ""))
                    elif nome_func == "tool_auditar_imports_py": resultado = tool_auditar_imports_py(args.get("caminho_relativo", ""))
                    elif nome_func == "tool_analisar_dependencias_globais_js":
                        from src.backend.tools.audit import tool_analisar_dependencias_globais_js
                        resultado = tool_analisar_dependencias_globais_js(args.get("pasta", ""))
                    elif nome_func == "tool_migrar_para_esm":
                        from src.backend.tools.audit import tool_migrar_para_esm
                        resultado = tool_migrar_para_esm(args.get("pasta", ""))

                    elif nome_func == "tool_mover_arquivo_binario": resultado = tool_mover_arquivo_binario(args.get("origem", ""), args.get("destino", ""), args.get("sobrescrever", False))
                    elif nome_func == "tool_desfazer": resultado = tool_desfazer(args.get("caminho_relativo", ""))
                    elif nome_func == "tool_refazer": resultado = tool_refazer(args.get("caminho_relativo", ""))
                    elif nome_func == "tool_status_desfazer": resultado = tool_status_desfazer()
                    elif nome_func == "tool_info_ambiente": resultado = tool_info_ambiente()
                    else: resultado = "Ferramenta desconhecida."
                    
                    call_id = getattr(call, 'id', None)
                    partes_resposta.append(types.Part(
                        function_response=types.FunctionResponse(
                            name=nome_func,
                            response={"result": resultado},
                            id=call_id,
                        )
                    ))
                
                historico_sessao.append(types.Content(role="user", parts=partes_resposta))
                emit_event("status")
                medir_contexto(historico=historico_sessao, tokens_base=_tokens_fixos, fase="execucao")
                
            else:
                # 1. Captura o texto com segurança (usa a lista textos_finais extraída acima)
                texto_final = "\n".join(textos_finais).strip()
                
                # Limpar mensagem efêmera se existir
                texto_final = re.sub(r"The following is an ephemeral message.*?</EPHEMERAL_MESSAGE>", "", texto_final, flags=re.DOTALL).strip()
                
                # Limpar prefixos de identidade que o modelo pode ter gerado por engano
                # (o frontend já adiciona o prefixo visual correto)
                texto_final = re.sub(r'^\s*\[Axio (Coder|Counselor)\]:\s*', '', texto_final)
                texto_final = re.sub(r'^\s*Axio (Coder|Counselor)\s*:?\s*', '', texto_final)
                
                # 2. Se a IA só pensou e não respondeu nada no final, evita travar a interface
                if not texto_final:
                    texto_final = "⚠️ [Aviso do Sistema] O processamento foi concluído, mas o agente esqueceu de escrever a mensagem final."

                # 3. Salva a interação no histórico global para evitar a amnésia
                # Extrai o resumo semântico obrigatório da rodada (opção C).
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
                
                # 4. Grava o arquivo de sessão para o mempalace
                timestamp = str(int(time.time()))
                pasta_chats = caminho_estado_projeto("chats")
                os.makedirs(pasta_chats, exist_ok=True)
                caminho_memo = os.path.join(pasta_chats, f"sessao_{timestamp}.txt")
                
                memo_humano = truncar_mensagem_historico(texto_usuario_final)
                memo_ia = truncar_mensagem_historico(texto_final)
                with open(caminho_memo, "w", encoding="utf-8") as f:
                    f.write(f"Humano: {memo_humano}\nIA: [{nome_agente_atual}]: {memo_ia}\n")
                
                emit_event("ai_response", message=texto_final)
                # Registra a pergunta enviada pelo usuário no log da sessão, para o
                # ícone de "pergunta do usuário" na aba de Arquivos (e no histórico).
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
