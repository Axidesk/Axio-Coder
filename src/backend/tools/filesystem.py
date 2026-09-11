import os
import re
import time
import json
import subprocess

from src.backend.state import MSG_SEM_PASTA, estado, emit_event, notificar_mudanca_arquivos
from src.backend.services.file_service import caminho_contido, resolver_caminho, entradas_diretorio, normalizar_unicode, registrar_edicao, desfazer_edicao, refazer_edicao, mover_para_lixeira
from src.backend.services.diff import gerar_diff
from src.backend.tools.syntax import aviso_estrutural_pos_edicao, validar_arquivo_apos_edicao

def _mapear_javascript(linhas):
    mapa = []
    for i, linha in enumerate(linhas):
        s = linha.strip()
        if re.match(r'^(?:async\s+)?function\s+[A-Za-z_$][\w$]*\s*\(', s):
            mapa.append(f"Linha {i+1}: {s}")
        elif re.match(r'^(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>', s):
            mapa.append(f"Linha {i+1}: {s}")
        elif re.match(r'^(?:async\s+)?[A-Za-z_$][\w$]*\s*\([^)]*\)\s*\{', s):
            nome = s.split('(')[0].strip().split()[-1]
            if nome not in ('if', 'for', 'while', 'switch', 'catch', 'return', 'typeof', 'delete', 'new'):
                mapa.append(f"Linha {i+1}: {s}")
    return mapa

def tool_mapear_codigo(caminho_relativo: str):
    emit_event("executing", function=f"Mapeando: {caminho_relativo}")
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro_caminho: return erro_caminho
    if not os.path.exists(caminho_absoluto): return f"ERRO: Arquivo não encontrado."
    try:
        mapa = []
        if caminho_relativo.endswith('.py'):
            import ast
            with open(caminho_absoluto, 'r', encoding='utf-8', errors='ignore') as f:
                conteudo = f.read()
            try:
                arvore = ast.parse(conteudo)
                for no in ast.walk(arvore):
                    if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        tipo = "Classe" if isinstance(no, ast.ClassDef) else "Função"
                        mapa.append(f"Linha {no.lineno}: {tipo} {no.name}")
                mapa.sort(key=lambda x: int(x.split(':')[0].replace('Linha ', '')))
            except SyntaxError:
                mapa.append("ERRO: Falha ao fazer parse do AST (erro de sintaxe no Python).")
        else:
            with open(caminho_absoluto, 'r', encoding='utf-8', errors='ignore') as f:
                linhas = f.readlines()
            if caminho_relativo.endswith(('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs')):
                mapa = _mapear_javascript(linhas)
            else:
                regex_cpp = r"^\s*(?:(?:inline|static|virtual|explicit|constexpr)\s+)*(?:[\w<>:]+\s+)*(?:[\w<>:]+::)?~?\w+\s*\([^)]*\)\s*(?:const|override|final|noexcept)*\s*\{?"
                for i, linha in enumerate(linhas):
                    if re.search(regex_cpp, linha) and not re.match(r"^\s*(if|for|while|switch|catch)\b", linha):
                        mapa.append(f"Linha {i+1}: {linha.strip()}")
        return "\\n".join(mapa) if mapa else "Nenhuma função identificada no formato padrão."
    except Exception as e: return f"ERRO: {str(e)}"

def _formato_tamanho(num):
    try:
        n = float(num)
    except (TypeError, ValueError):
        return "-"
    if n < 1024:
        return f"{n:.0f} B"
    for unidade in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024:
            return f"{n:.1f} {unidade}"
    return f"{n:.1f} PB"

def tool_listar_pasta(caminho_relativo=""):
    emit_event("executing", function=f"Listando: {caminho_relativo or 'Raiz'}")
    
    caminho_alvo, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro_caminho:
        return erro_caminho
    
    if not os.path.exists(caminho_alvo):
        return f"ERRO: O caminho '{caminho_relativo}' não existe."

    try:
        entradas = entradas_diretorio(caminho_alvo)
        entradas.sort(key=lambda e: (e["tipo"] != "dir", e["nome"].lower()))
        linhas = [f"Caminho: {caminho_relativo or os.path.basename(caminho_alvo.rstrip(os.sep)) or caminho_alvo}",
                  f"{len(entradas)} itens"]
        for e in entradas:
            nome = e["nome"] + "/" if e["tipo"] == "dir" else e["nome"]
            try:
                st = os.stat(os.path.join(caminho_alvo, e["nome"]))
                tam = _formato_tamanho(st.st_size)
                data = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
            except OSError:
                tam, data = "-", "-"
            linhas.append(f"{data}  {tam:>10}  {nome}")
        return "\n".join(linhas) if len(linhas) > 2 else "Pasta vazia."
    except Exception as e:
        return f"ERRO ao acessar pasta: {str(e)}"

def tool_listar_arvore(caminho_relativo="", profundidade_max=4, max_entradas=400):
    emit_event("executing", function=f"Mapeando árvore: {caminho_relativo or 'Raiz'}")
    caminho_alvo, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro_caminho:
        return erro_caminho
    if not os.path.isdir(caminho_alvo):
        return f"ERRO: O caminho '{caminho_relativo}' não é uma pasta."

    contador = {"n": 0}
    linhas = []
    limite_por_dir = 60

    def _arvore(pasta, prefixo, profundidade):
        if profundidade > profundidade_max:
            linhas.append(prefixo + "(...)")
            return False
        entradas = entradas_diretorio(pasta)
        entradas.sort(key=lambda e: (e["tipo"] != "dir", e["nome"].lower()))
        total = len(entradas)
        exibir = entradas[:limite_por_dir]
        for idx, e in enumerate(exibir):
            contador["n"] += 1
            if contador["n"] > max_entradas:
                linhas.append(prefixo + "... (limite de entradas atingido)")
                return True
            eh_ultimo = (idx == len(exibir) - 1) and (total <= limite_por_dir)
            ramo = "└── " if eh_ultimo else "├── "
            if e["tipo"] == "dir":
                linhas.append(prefixo + ramo + e["nome"] + "/")
                if _arvore(os.path.join(pasta, e["nome"]), prefixo + ("    " if eh_ultimo else "│   "), profundidade + 1):
                    return True
            else:
                linhas.append(prefixo + ramo + e["nome"])
        if total > limite_por_dir:
            linhas.append(prefixo + f"... (+{total - limite_por_dir} itens ocultos nesta pasta)")
        return False

    try:
        _arvore(caminho_alvo, "", 1)
        cabecalho = caminho_relativo if caminho_relativo else os.path.basename(caminho_alvo.rstrip(os.sep))
        resultado = cabecalho + "/\n" + "\n".join(linhas) if linhas else cabecalho + "/\n(pasta vazia)"
        return resultado
    except Exception as e:
        return f"ERRO ao mapear árvore: {str(e)}"

def _resolver_arquivo_existente(caminho_relativo):
    """Resolve o caminho e garante que o arquivo existe. Devolve (absoluto, erro_texto)."""
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro_caminho:
        return None, erro_caminho
    if not os.path.exists(caminho_absoluto):
        return None, f"ERRO: O arquivo '{caminho_relativo}' não existe."
    return caminho_absoluto, None

def tool_ler_arquivo(caminho_relativo: str):
    emit_event("executing", function=f"Lendo arquivo: {caminho_relativo}")
    caminho_absoluto, erro_caminho = _resolver_arquivo_existente(caminho_relativo)
    if erro_caminho: return erro_caminho
    try:
        with open(caminho_absoluto, 'r', encoding='utf-8', errors='ignore') as f:
            conteudo = f.read()
            num_linhas = conteudo.count("\n") + 1
            if len(conteudo) > 25000 or num_linhas > 600: return f"ERRO: Arquivo muito grande ({len(conteudo)} caracteres, {num_linhas} linhas). Use 'tool_mapear_codigo' e depois 'tool_ler_trecho_arquivo' para ler blocos específicos."
            return conteudo
    except Exception as e: return f"ERRO: {str(e)}"

def tool_ler_trecho_arquivo(caminho_relativo: str, linha_inicio: int, linha_fim: int):
    emit_event("executing", function=f"Lendo trecho: {caminho_relativo}")
    caminho_absoluto, erro_caminho = _resolver_arquivo_existente(caminho_relativo)
    if erro_caminho: return erro_caminho
    try:
        with open(caminho_absoluto, 'r', encoding='utf-8', errors='ignore') as f:
            linhas = f.readlines()
        inicio = max(0, linha_inicio - 1)
        fim = min(len(linhas), linha_fim)
        if inicio >= fim: return "ERRO: Intervalo inválido."
        trecho = "".join(linhas[inicio:fim])
        return f"--- Trecho de {caminho_relativo} (Linhas {linha_inicio} a {linha_fim}) ---\\n{trecho}"
    except Exception as e: return f"ERRO: {str(e)}"

def _preparar_substituicao(caminho_relativo, rotulo, texto_antigo, texto_novo):
    """Valida o caminho, le o arquivo alvo e normaliza os textos (NFC).

    Devolve ((caminho_absoluto, conteudo, conteudo_nfc, texto_antigo_nfc,
    texto_novo_nfc, ocorrencias), erro). Quando `erro` nao for None, o chamador
    deve devolve-lo imediatamente.
    """
    if estado.get("bloquear_edicao"):
        return None, "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    emit_event("executing", function=f"{rotulo}: {caminho_relativo}")
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=False, permitir_escrita=True)
    if erro_caminho:
        return None, erro_caminho
    if not os.path.exists(caminho_absoluto):
        return None, f"ERRO: O arquivo '{caminho_relativo}' não existe."
    try:
        with open(caminho_absoluto, 'r', encoding='utf-8') as f:
            conteudo = f.read()
    except Exception as e:
        return None, f"ERRO: {str(e)}"
    # Normaliza NFC: acentos pré-compostos ('ú') e decompostos ('u'+combining) casam entre si.
    conteudo_nfc = normalizar_unicode(conteudo)
    texto_antigo_nfc = normalizar_unicode(texto_antigo)
    texto_novo_nfc = normalizar_unicode(texto_novo)
    return (caminho_absoluto, conteudo, conteudo_nfc, texto_antigo_nfc, texto_novo_nfc, conteudo_nfc.count(texto_antigo_nfc)), None

def _gravar_e_emitir_diff(caminho_relativo, caminho_absoluto, conteudo, novo_conteudo, action_name):
    """Grava o novo conteudo, registra no undo e emite o diff para a UI.

    Devolve o aviso de sintaxe (validar_arquivo_apos_edicao).
    """
    registrar_edicao(caminho_absoluto, conteudo, novo_conteudo)
    with open(caminho_absoluto, 'w', encoding='utf-8') as f:
        f.write(novo_conteudo)
    diff = gerar_diff(conteudo, novo_conteudo)
    emit_event("action_diff", actionName=action_name, diff=diff)
    notificar_mudanca_arquivos()
    return validar_arquivo_apos_edicao(caminho_relativo, caminho_absoluto) + aviso_estrutural_pos_edicao(caminho_relativo, conteudo, novo_conteudo)

def tool_substituir_texto(caminho_relativo: str, texto_antigo: str, texto_novo: str):
    dados, erro = _preparar_substituicao(caminho_relativo, "Substituindo texto", texto_antigo, texto_novo)
    if erro:
        return erro
    caminho_absoluto, conteudo, conteudo_nfc, texto_antigo_nfc, texto_novo_nfc, ocorrencias = dados
    try:
        if ocorrencias == 0: return "ERRO: O 'texto_antigo' não foi encontrado. Falha de indentação ou espaços. DICA: Não tente adivinhar os espaços. Use 'tool_ler_trecho_arquivo' novamente para copiar as linhas exatas, ou use uma âncora menor (ex: apenas 1 linha única) para garantir o match."
        elif ocorrencias > 1: return f"ERRO: O 'texto_antigo' ocorre {ocorrencias} vezes no arquivo. A âncora é ambígua. Forneça um trecho maior ou mais específico para garantir que apenas o local correto seja alterado."
        
        novo_conteudo = conteudo_nfc.replace(texto_antigo_nfc, texto_novo_nfc, 1)
        aviso = _gravar_e_emitir_diff(caminho_relativo, caminho_absoluto, conteudo, novo_conteudo, f"Modificado: {caminho_relativo}")
        return f"SUCESSO: Trecho substituído em '{caminho_relativo}'.{aviso}"
    except Exception as e: return f"ERRO: {str(e)}"

def tool_planejar_arquitetura(stack: str, urls_pesquisadas: str, estrutura_pastas: str, etapas_planejamento: str):
    urls_declaradas = [u.rstrip('/').rstrip('.,;') for u in re.findall(r'https?://[^\s,;]+', urls_pesquisadas or "")]
    navegadas = {u.rstrip('/') for u in estado.get("urls_navegadas_turno", set())}

    if not navegadas:
        return (
            "⚠️ VALIDAÇÃO DE FONTES FALHOU: você ainda não pesquisou na web neste turno.\n"
            "Antes de planejar a arquitetura, PESQUISE (tool_buscar_web) a stack e as melhores práticas "
            "na documentação OFICIAL (docs.*, developer.mozilla.org, site oficial ou GitHub oficial).\n"
            "Só então liste no campo 'urls_pesquisadas' APENAS as URLs que realmente abriu."
        )

    if not urls_declaradas:
        return (
            "⚠️ VALIDAÇÃO DE FONTES FALHOU: o campo 'urls_pesquisadas' está vazio ou sem URLs.\n"
            "Liste UMA por linha as URLs que você REALMENTE abriu neste turno (as que apareceram no status 'Navegando:')."
        )

    inventadas = [u for u in urls_declaradas if u not in navegadas]
    if inventadas:
        return (
            "⚠️ VALIDAÇÃO DE FONTES FALHOU: as URLs abaixo NÃO correspondem a nenhuma navegação real deste turno "
            "(não as invente nem troque blog por MDN):\n" +
            "\n".join(f"  - {u}" for u in inventadas) +
            "\n\nURLs realmente navegadas neste turno:\n" +
            "\n".join(f"  - {u}" for u in sorted(navegadas)) +
            "\n\nRefaça a pesquisa em documentação oficial e cite apenas o que abriu de verdade."
        )

    estado["projeto_planejado"] = True
    estado["plano_stack"] = {
        "stack": stack,
        "urls_pesquisadas": urls_pesquisadas,
        "estrutura_pastas": estrutura_pastas,
    }
    emit_event("executing", function="Planejamento de Arquitetura Concluído")
    return f"SUCESSO: Arquitetura planejada e validada. Trava de segurança liberada. Você pode começar a criar os arquivos.\nStack: {stack}\nEtapas: {etapas_planejamento}"

def tool_iniciar_plano(plano_json: str):
    try:
        plano = json.loads(plano_json)
        for i, etapa in enumerate(plano):
            etapa["tarefas_concluidas"] = []
            etapa["revelada"] = (i == 0)
        estado["plano_atual"] = plano
        primeira = plano[0] if plano else None
        emit_event("executing", function="Iniciando plano de execução")
        emit_event("plan_started", plan=[primeira] if primeira else [], stack=estado.get("plano_stack"))
        return "SUCESSO: Plano iniciado e exibido na interface."
    except Exception as e:
        return f"ERRO ao iniciar plano: {str(e)}"

def tool_atualizar_plano(id_etapa: str, tarefa_concluida: str, etapa_concluida: bool):
    plano = estado.get("plano_atual")
    proxima = None
    if plano:
        for i, etapa in enumerate(plano):
            if etapa.get("id") == id_etapa:
                concluidas = etapa.setdefault("tarefas_concluidas", [])
                if etapa_concluida:
                    concluidas = list(etapa.get("tarefas", []))
                elif tarefa_concluida and tarefa_concluida not in concluidas:
                    concluidas.append(tarefa_concluida)
                etapa["tarefas_concluidas"] = concluidas
                if etapa_concluida and i + 1 < len(plano):
                    prox = plano[i + 1]
                    if not prox.get("revelada"):
                        prox["revelada"] = True
                        proxima = prox
                break
    emit_event("executing", function="Concluindo etapa do plano" if etapa_concluida else f"Atualizando plano: {tarefa_concluida}")
    emit_event("plan_updated", id_etapa=id_etapa, tarefa_concluida=tarefa_concluida, etapa_concluida=etapa_concluida)
    if proxima:
        emit_event("plan_step_added", step=proxima)
    return "SUCESSO: Plano atualizado na interface."

def tool_adicionar_etapa_plano(nova_etapa_json: str):
    try:
        etapa = json.loads(nova_etapa_json)
        emit_event("executing", function="Adicionando etapa ao plano")
        emit_event("plan_step_added", step=etapa)
        return "SUCESSO: Nova etapa adicionada ao plano na interface."
    except Exception as e:
        return f"ERRO ao adicionar etapa: {str(e)}"

def _eh_projeto_novo():
    raiz = estado.get("pasta_raiz", "")
    if not raiz or not os.path.isdir(raiz):
        return False
    src = os.path.join(raiz, "src")
    if os.path.isdir(src):
        if os.path.isdir(os.path.join(src, "backend")) or os.path.isdir(os.path.join(src, "frontend")):
            return False
    ignorados = {".axio", ".git", "__pycache__", "node_modules", ".venv", "venv"}
    dirs_codigo = {"src", "app", "backend", "frontend", "lib", "packages"}
    ext_codigo = (".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json", ".vue", ".toml", ".yaml", ".yml")
    try:
        itens = os.listdir(raiz)
    except OSError:
        return False
    for item in itens:
        if item in ignorados or item.startswith("."):
            continue
        caminho = os.path.join(raiz, item)
        if os.path.isdir(caminho) and item.lower() in dirs_codigo:
            return False
        if os.path.isfile(caminho) and item.lower().endswith(ext_codigo):
            return False
    return True

def tool_salvar_arquivo(caminho_relativo: str, conteudo: str):
    if estado.get("bloquear_edicao"):
        return "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=False, permitir_escrita=True)
    if not erro_caminho and not os.path.exists(caminho_absoluto):
        if not estado.get("projeto_planejado") and _eh_projeto_novo():
            return (
                "⚠️ TRAVA DE SEGURANÇA DO SISTEMA: Acesso negado.\n"
                "Você tentou criar um arquivo de um projeto NOVO sem concluir as etapas obrigatórias de preparação. "
                "Esta ação foi BLOQUEADA pelo backend.\n\n"
                "Para destravar, siga EXATAMENTE nesta ordem:\n"
                "1. PESQUISE NA WEB (tool_buscar_web) a stack, a documentação atualizada e as melhores práticas/modernas.\n"
                "2. Monte a LISTA DE ETAPAS DE PLANEJAMENTO (criação de pastas, criação de módulos, validação, finalização...).\n"
                "3. Chame 'tool_planejar_arquitetura' (stack, urls_pesquisadas, estrutura_pastas, etapas_planejamento) para liberar a trava.\n"
                "4. Chame 'tool_iniciar_plano' para exibir as etapas visualmente na interface (coluna 3).\n"
                "5. Só então comece a criar os arquivos, atualizando o plano com 'tool_atualizar_plano' a cada tarefa concluída.\n\n"
                "DIRETRIZES DE CRIAÇÃO DE CÓDIGO (obrigatórias):\n"
                "- Raiz limpa: apenas arquivos de configuração essenciais.\n"
                "- Código em src/, dividido em backend/ e frontend/.\n"
                "- No máximo UMA subpasta por domínio dentro de backend/ e frontend/.\n"
                "- Modular: 1-2 arquivos para adicionar/remover uma feature sem quebrar o resto.\n"
                "- Nomes curtos, ES Modules para JS, stacks mais modernas e justificadas.\n"
            )

    emit_event("executing", function=f"Salvando Arquivo: {caminho_relativo}")
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=False, permitir_escrita=True)
    if erro_caminho: return erro_caminho
    try:
        texto_antigo = None
        if os.path.exists(caminho_absoluto):
            with open(caminho_absoluto, 'r', encoding='utf-8') as f:
                texto_antigo = f.read()
                
        os.makedirs(os.path.dirname(caminho_absoluto), exist_ok=True)
        with open(caminho_absoluto, 'w', encoding='utf-8') as f:
            f.write(conteudo)

        registrar_edicao(caminho_absoluto, texto_antigo, conteudo)
            
        if texto_antigo:
            diff = gerar_diff(texto_antigo, conteudo)
            emit_event("action_diff", actionName=f"Salvo/Sobrescrito: {caminho_relativo}", diff=diff)
        else:
            diff = [{"type": "added", "text": conteudo}]
            emit_event("action_diff", actionName=f"Criado: {caminho_relativo}", actionType="created", diff=diff)
        notificar_mudanca_arquivos()
        
        aviso = validar_arquivo_apos_edicao(caminho_relativo, caminho_absoluto) + aviso_estrutural_pos_edicao(caminho_relativo, texto_antigo, conteudo)
        return f"SUCESSO: Arquivo '{caminho_relativo}' salvo.{aviso}"
    except Exception as e: return f"ERRO: {str(e)}"

_PASTAS_PROTEGIDAS = {".git", ".axio"}

def _validar_alvo_exclusao(caminho_relativo, caminho_absoluto):
    """Bloqueia exclusoes perigosas antes de tocar no disco.

    Recusa a propria raiz do projeto, qualquer caminho fora dela (defesa em
    profundidade: resolver_caminho ja bloqueia escrita fora, mas a exclusao e
    irreversivel) e as pastas estruturalmente protegidas: o .axio guarda a
    lixeira usada para recuperar o que foi apagado.
    """
    raiz = estado.get("pasta_raiz", "")
    if not raiz:
        return MSG_SEM_PASTA
    raiz_abs = os.path.abspath(raiz)
    alvo = os.path.abspath(caminho_absoluto)
    if not caminho_contido(alvo, raiz_abs):
        return f"ERRO: '{caminho_relativo}' esta fora da pasta do projeto (exclusao bloqueada)."
    if alvo == raiz_abs:
        return "ERRO: nao e possivel excluir a pasta raiz do projeto."
    nome = os.path.basename(alvo).lower()
    if nome in _PASTAS_PROTEGIDAS:
        return f"ERRO: a pasta '{nome}' e protegida (contem o controle de versao ou o estado do projeto, incluindo a propria lixeira)."
    return None

def _deletar_pasta(caminho_relativo, caminho_absoluto):
    """Move uma pasta (vazia ou com conteudo) para a lixeira.

    A pasta vazia tambem vai para a lixeira: listar_lixeira lista esse
    diretorio como item proprio (tipo 'dir') e restaura-lo recria a pasta.
    Sem isso a estrutura apagada desaparecia sem qualquer forma de recuperacao.
    """
    try:
        total = sum(len(arquivos) for _raiz, _dirs, arquivos in os.walk(caminho_absoluto))
        mover_para_lixeira(caminho_absoluto)
        if os.path.exists(caminho_absoluto):
            return f"ERRO: nao foi possivel mover a pasta '{caminho_relativo}' para a lixeira."
        notificar_mudanca_arquivos()
        if total == 0:
            return f"SUCESSO: Pasta vazia '{caminho_relativo}' movida para a lixeira."
        return f"SUCESSO: Pasta '{caminho_relativo}' movida para a lixeira ({total} arquivo(s) recuperaveis na interface)."
    except OSError as e:
        return f"ERRO: {e}"

def tool_deletar_arquivo(caminho_relativo: str):
    if estado.get("bloquear_edicao"):
        return "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    emit_event("executing", function=f"Excluindo: {caminho_relativo}")
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=False, permitir_escrita=True)
    if erro_caminho: return erro_caminho
    if not os.path.exists(caminho_absoluto): return f"ERRO: O arquivo '{caminho_relativo}' não existe."
    erro_alvo = _validar_alvo_exclusao(caminho_relativo, caminho_absoluto)
    if erro_alvo: return erro_alvo
    if os.path.isdir(caminho_absoluto): return _deletar_pasta(caminho_relativo, caminho_absoluto)
    try:
        with open(caminho_absoluto, 'r', encoding='utf-8', errors='ignore') as f:
            texto_antigo = f.read()
        mover_para_lixeira(caminho_absoluto)
        if os.path.exists(caminho_absoluto):
            return f"ERRO: não foi possível mover '{caminho_relativo}' para a lixeira."
        registrar_edicao(caminho_absoluto, texto_antigo, None)
        emit_event("action_diff", actionName=f"Excluído: {caminho_relativo}", diff=[{"type": "deleted", "text": texto_antigo}])
        notificar_mudanca_arquivos()
        return f"SUCESSO: Arquivo '{caminho_relativo}' movido para a lixeira."
    except Exception as e: return f"ERRO: {str(e)}"

def tool_pesquisar_no_projeto(termo: str):
    emit_event("executing", function=f"Pesquisando: {termo}")
    termo_norm = normalizar_unicode(termo)
    resultados = []
    tempo_inicio = time.time()
    pastas_ignoradas = {'.git', '__pycache__', 'node_modules', 'build'}
    extensoes_ignoradas = ('.exe', '.dll', '.obj', '.o', '.a', '.lib', '.so', '.pyc', '.spv', '.pdb', '.ilk', '.png', '.jpg', '.jpeg', '.ttf', '.bin', '.zip', '.tar')

    for root, dirs, files in os.walk(estado["pasta_raiz"]):
        dirs[:] = [d for d in dirs if d not in pastas_ignoradas and not d.startswith('.')]
        
        for name in files:
            if time.time() - tempo_inicio > 10:
                resultados.append("[AVISO] Timeout de 10s atingido. Resultados parciais.")
                saida = "\\n".join(resultados)
                return saida[:10000] + "\\n... [RESULTADO TRUNCADO]" if len(saida) > 10000 else saida

            if name.endswith(extensoes_ignoradas): continue
            caminho_absoluto = os.path.join(root, name)
            
            try:
                if os.path.getsize(caminho_absoluto) > 512000: continue
                caminho_relativo = os.path.relpath(caminho_absoluto, estado["pasta_raiz"])
                
                with open(caminho_absoluto, 'r', encoding='utf-8', errors='ignore') as f:
                    for i, linha in enumerate(f):
                        if termo_norm in normalizar_unicode(linha):
                            resultados.append(f"{caminho_relativo} (Linha {i+1}): {linha.strip()}")
            except: pass
            
    if not resultados: return f"Nenhuma ocorrência encontrada para o termo '{termo}'."
    saida = "\\n".join(resultados)
    if len(saida) > 10000: return saida[:10000] + "\\n... [RESULTADO TRUNCADO]"
    return saida

def tool_ler_assinaturas(caminho_relativo: str):
    emit_event("executing", function=f"Lendo assinaturas: {caminho_relativo}")
    caminho_absoluto, erro_caminho = _resolver_arquivo_existente(caminho_relativo)
    if erro_caminho: return erro_caminho
    try:
        with open(caminho_absoluto, 'r', encoding='utf-8', errors='ignore') as f:
            linhas = f.readlines()
    except Exception as e:
        return f"ERRO: {str(e)}"
    if caminho_relativo.endswith(('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs')):
        resultado = _mapear_javascript(linhas)
        return "\n".join(resultado) if resultado else "Nenhuma assinatura clara encontrada."
    resultado = []
    padrao = r"^\s*(?:(?:inline|static|virtual|explicit|constexpr)\s+)*(?:[\w<>:]+\s+)*(?:[\w<>:]+::)?~?\w+\s*\([^)]*\)\s*(?:const|override|final|noexcept)*"
    for i, linha in enumerate(linhas):
        if re.search(padrao, linha) and not re.match(r"^\s*(if|for|while|switch|catch)\b", linha):
            resultado.append(f"Linha {i+1}: {linha.strip()};")
        elif "class " in linha or "struct " in linha:
            resultado.append(f"Linha {i+1}: {linha.strip()}")
    return "\n".join(resultado) if resultado else "Nenhuma assinatura clara encontrada."

def tool_analisar_simbolo(caminho_relativo: str, termo: str):
    emit_event("executing", function=f"Analisando símbolo: {termo} em {caminho_relativo}")
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro_caminho: return erro_caminho
    try:
        resultado_clang = subprocess.run(f"clangd --check={caminho_absoluto}", shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
        saida = resultado_clang.stderr
        erros = [l for l in saida.splitlines() if "error:" in l]
        aviso_erro = "\\n".join(erros[:5]) if erros else "Nenhum erro de sintaxe detectado."
        return f"Análise Semântica de '{termo}':\\n{aviso_erro}\\n\\nUse 'tool_pesquisar_no_projeto' para localizar referências cruzadas."
    except:
        return f"Clangd não respondeu. Use tool_pesquisar_no_projeto para busca textual de '{termo}'."

def tool_substituir_tudo(caminho_relativo: str, texto_antigo: str, texto_novo: str):
    dados, erro = _preparar_substituicao(caminho_relativo, "Substituindo tudo em", texto_antigo, texto_novo)
    if erro:
        return erro
    caminho_absoluto, conteudo, conteudo_nfc, texto_antigo_nfc, texto_novo_nfc, ocorrencias = dados
    try:
        if ocorrencias == 0: return "ERRO: O 'texto_antigo' não foi encontrado. Nenhuma substituição feita."
        novo_conteudo = conteudo_nfc.replace(texto_antigo_nfc, texto_novo_nfc)
        aviso = _gravar_e_emitir_diff(caminho_relativo, caminho_absoluto, conteudo, novo_conteudo, f"Substituição Global: {caminho_relativo}")
        return f"SUCESSO: Substituição global realizada. {ocorrencias} ocorrências de '{texto_antigo}' foram substituídas no arquivo '{caminho_relativo}'.{aviso}"
    except Exception as e: return f"ERRO ao realizar substituição global: {str(e)}"

def tool_desfazer(caminho_relativo: str):
    if estado.get("bloquear_edicao"):
        return "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    emit_event("executing", function=f"Desfazendo: {caminho_relativo}")
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=False, permitir_escrita=True)
    if erro_caminho: return erro_caminho
    resultado = desfazer_edicao(caminho_absoluto)
    if resultado.get("status") == "ok":
        emit_event("undo_changed", acao="undo", caminho=caminho_absoluto, nome=os.path.basename(caminho_absoluto))
        notificar_mudanca_arquivos()
    return resultado.get("message", "Operação concluída.")

def tool_refazer(caminho_relativo: str):
    if estado.get("bloquear_edicao"):
        return "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    emit_event("executing", function=f"Refazendo: {caminho_relativo}")
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=False, permitir_escrita=True)
    if erro_caminho: return erro_caminho
    resultado = refazer_edicao(caminho_absoluto)
    if resultado.get("status") == "ok":
        emit_event("undo_changed", acao="redo", caminho=caminho_absoluto, nome=os.path.basename(caminho_absoluto))
        notificar_mudanca_arquivos()
    return resultado.get("message", "Operação concluída.")

def tool_status_desfazer():
    emit_event("executing", function="Consultando histórico de desfazer/refazer")
    pasta_raiz = estado.get("pasta_raiz", "")
    arquivos = []
    for caminho, hist in estado["file_history"].items():
        if not (hist["undo"] or hist["redo"]):
            continue
        try:
            rel = os.path.relpath(caminho, pasta_raiz).replace("\\", "/") if pasta_raiz else caminho.replace("\\", "/")
        except ValueError:
            rel = caminho.replace("\\", "/")
        arquivos.append(f"{rel}: {len(hist['undo'])} para desfazer, {len(hist['redo'])} para refazer")
    if not arquivos:
        return "Nenhuma edição registrada para desfazer/refazer nesta sessão."
    return "\n".join(sorted(arquivos))
