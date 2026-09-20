import os
import re
import ast
import hashlib
import shutil
import uuid

from src.backend.state import estado, emit_event, notificar_mudanca_arquivos
from src.backend.tools.registry import register
from src.backend.services.file_service import resolver_caminho, registrar_edicao
from src.backend.services.diff import gerar_diff

def _localizar_funcao_py(linhas, nome_funcao):
    conteudo = "".join(linhas)
    try:
        arvore = ast.parse(conteudo)
    except SyntaxError as e:
        return f"ERRO: Falha ao parsear Python (AST): {e}"
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and no.name == nome_funcao:
            fim = no.end_lineno or no.lineno
            return (no.lineno, fim)
    return f"ERRO: Função ou classe '{nome_funcao}' não encontrada no Python."

def _range_com_decoradores_py(linhas, nome_funcao):
    """Estende o range da funcao para cima, ate aos decoradores dela (@rota, @register)."""
    r = _localizar_funcao_py(linhas, nome_funcao)
    if isinstance(r, str):
        return r
    inicio, fim = r
    idx = inicio - 2
    while idx >= 0 and linhas[idx].lstrip().startswith("@"):
        idx -= 1
    return (idx + 2, fim)

def _fim_funcao_js(linhas, inicio):
    texto = "".join(linhas)
    offsets = [0]
    for ln in linhas:
        offsets.append(offsets[-1] + len(ln))
    n = len(texto)

    def _linha_de(pos):
        lo, hi = 0, len(offsets) - 1
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if offsets[mid] <= pos:
                lo = mid
            else:
                hi = mid
        return lo

    def _pular_string_comentario(i):
        while i < n:
            ch = texto[i]
            if ch == "/" and i + 1 < n and texto[i + 1] == "/":
                while i < n and texto[i] != "\n":
                    i += 1
                return i
            if ch == "/" and i + 1 < n and texto[i + 1] == "*":
                i += 2
                while i + 1 < n and not (texto[i] == "*" and texto[i + 1] == "/"):
                    i += 1
                i += 2
                continue
            if ch in ('"', "'", "`"):
                aspas = ch
                i += 1
                while i < n and texto[i] != aspas:
                    if texto[i] == "\\":
                        i += 1
                    i += 1
                i += 1
                continue
            return i
        return i

    i = offsets[inicio]
    paren = 0
    bracket = 0
    abertura = None
    while i < n:
        i = _pular_string_comentario(i)
        if i >= n:
            break
        ch = texto[i]
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket -= 1
        elif ch == "{" and paren == 0 and bracket == 0:
            abertura = i
            break
        i += 1

    if abertura is None:
        j = offsets[inicio]
        while j < n:
            if texto[j] == "\n":
                break
            if texto[j:j + 2] == "=>":
                return _linha_de(j) + 1
            j += 1
        return None

    profundidade = 0
    i = abertura
    while i < n:
        i = _pular_string_comentario(i)
        if i >= n:
            break
        ch = texto[i]
        if ch == "{":
            profundidade += 1
        elif ch == "}":
            profundidade -= 1
            if profundidade == 0:
                return _linha_de(i) + 1
        i += 1
    return None

def _localizar_funcao_js(linhas, nome_funcao):
    inicio = None
    for i, linha in enumerate(linhas):
        s = linha.strip()
        if re.match(r"^(?:export\s+)?(?:async\s+)?function\s+" + re.escape(nome_funcao) + r"\s*\(", s):
            inicio = i
            break
        if re.match(r"^(?:export\s+)?(?:const|let|var)\s+" + re.escape(nome_funcao) + r"\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", s):
            inicio = i
            break
        if re.match(r"^(?:export\s+)?(?:async\s+)?" + re.escape(nome_funcao) + r"\s*\([^)]*\)\s*\{", s):
            inicio = i
            break
    if inicio is None:
        return f"ERRO: Função '{nome_funcao}' não encontrada no JavaScript."
    fim = _fim_funcao_js(linhas, inicio)
    if fim is None:
        return f"ERRO: Não foi possível determinar o fim da função '{nome_funcao}' (chaves desbalanceadas)."
    return (inicio + 1, fim)

def _tem_assinatura_funcao_js(linhas, nome_funcao):
    for linha in linhas:
        s = linha.strip()
        if re.match(r"^(?:export\s+)?(?:async\s+)?function\s+" + re.escape(nome_funcao) + r"\s*\(", s):
            return True
        if re.match(r"^(?:export\s+)?(?:const|let|var)\s+" + re.escape(nome_funcao) + r"\s*=\s*", s):
            return True
    return False

def _corpo_com_chaves_balanceadas(corpo):
    profundidade = 0
    i = 0
    n = len(corpo)
    while i < n:
        ch = corpo[i]
        if ch == "/" and i + 1 < n and corpo[i + 1] == "/":
            while i < n and corpo[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and corpo[i + 1] == "*":
            i += 2
            while i + 1 < n and not (corpo[i] == "*" and corpo[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if ch in ('"', "'", "`"):
            aspas = ch
            i += 1
            while i < n and corpo[i] != aspas:
                if corpo[i] == "\\":
                    i += 1
                i += 1
            i += 1
            continue
        if ch == "{":
            profundidade += 1
        elif ch == "}":
            profundidade -= 1
            if profundidade < 0:
                return False
        i += 1
    return profundidade == 0

def _extrair_corpo_funcao(caminho_absoluto, nome_funcao):
    with open(caminho_absoluto, "r", encoding="utf-8", errors="ignore") as f:
        linhas = f.readlines()
    if caminho_absoluto.endswith(".py"):
        r = _localizar_funcao_py(linhas, nome_funcao)
    else:
        r = _localizar_funcao_js(linhas, nome_funcao)
    if isinstance(r, str):
        return None, r
    inicio, fim = r
    corpo = "".join(linhas[inicio - 1:fim])
    return corpo, (inicio, fim)

def _colapsar_linhas_vazias(linhas):
    resultado = []
    vazias = 0
    for linha in linhas:
        if linha.strip() == "":
            vazias += 1
            if vazias > 2:
                continue
        else:
            vazias = 0
        resultado.append(linha)
    return resultado

def _gravar_destino_com_corpo(dest_abs, dest_existia, conteudo_dest, corpo, remover_origem, errors=None):
    """Anexa `corpo` ao destino, registra no undo e grava. Devolve (diff_dest, grupo_mover)."""
    novo_dest = conteudo_dest
    if novo_dest and not novo_dest.endswith("\n"):
        novo_dest += "\n"
    novo_dest += corpo
    if not novo_dest.endswith("\n"):
        novo_dest += "\n"
    grupo_mover = f"mover-{uuid.uuid4().hex[:12]}" if remover_origem else None
    registrar_edicao(dest_abs, None if not dest_existia else conteudo_dest, novo_dest, grupo=grupo_mover)
    with open(dest_abs, "w", encoding="utf-8", errors=errors) as f:
        f.write(novo_dest)
    return gerar_diff(conteudo_dest, novo_dest), grupo_mover

def _emitir_diff_movido(arquivo_origem, arquivo_destino, conteudo_orig, novo_orig, diff_dest):
    """Gera o diff da origem e o diff combinado (removido + adicionado) e emite o evento 'moved'."""
    diff_orig = gerar_diff(conteudo_orig, novo_orig)
    partes_deletadas = [p for p in diff_orig if p.get("type") in ("deleted", "modified")]
    partes_adicionadas = [p for p in diff_dest if p.get("type") == "added"]
    emit_event("action_diff", actionName=arquivo_destino, actionType="moved", origem=arquivo_origem, destino=arquivo_destino, diff=partes_deletadas + partes_adicionadas)

@register(
    "tool_mover_funcao_verbatim",
    'Move uma função/classe inteira de um arquivo para outro copiando os bytes exatos do disco (verbatim, sem redigitar, sem simplificar). Detecta o range completo da função (início e fim) por AST no Python e por balanceamento de chaves no JavaScript. Recusa funções aninhadas, porque o destino recebe o corpo no topo do módulo e a indentação herdada o invalidaria. Opcionalmente remove a função do arquivo de origem. Use preview=true para dry-run (mostra linhas + SHA-256 sem escrever/remover nada). Retorna o SHA-256 do corpo movido para verificação.',
    {
        'arquivo_origem': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'nome_funcao': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'arquivo_destino': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'remover_origem': {"tipo": "BOOLEAN", "padrao": True},
        'preview': {"tipo": "BOOLEAN", "padrao": False},
    },
    disponivel="edicao",
)
def tool_mover_funcao_verbatim(arquivo_origem, nome_funcao, arquivo_destino, remover_origem=True, preview=False):
    if estado.get("bloquear_edicao"):
        return "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    emit_event("executing", function=f"Movendo função verbatim: {nome_funcao}")
    if isinstance(remover_origem, str):
        remover_origem = remover_origem.strip().lower() in ("1", "true", "sim", "yes", "s")
    if isinstance(preview, str):
        preview = preview.strip().lower() in ("1", "true", "sim", "yes", "s")
    origem_abs, erro = resolver_caminho(arquivo_origem, permitir_extra=True)
    if erro:
        return erro
    if not os.path.exists(origem_abs):
        return f"ERRO: Arquivo origem '{arquivo_origem}' não existe."
    corpo, info = _extrair_corpo_funcao(origem_abs, nome_funcao)
    if corpo is None:
        return info
    inicio, fim = info
    if corpo[:1].isspace():
        return (
            f"ERRO: '{nome_funcao}' esta ANINHADA dentro de outra funcao (linha {inicio} indentada). O destino "
            "recebe o corpo no topo do modulo, logo move-la assim gravaria um ficheiro invalido. Aninhada nao e "
            "peca solta: o que ela fecha por cima tem de virar parametro, e essa decisao nao e mecanica. Extraia "
            "por faixas de linha, dedentando com prova de ida-e-volta (repôr a indentacao removida tem de "
            "reproduzir os bytes originais) e ajuste a assinatura. Nada foi movido."
        )
    if not _corpo_com_chaves_balanceadas(corpo):
        return f"ERRO: O corpo extraído da função '{nome_funcao}' está com chaves desbalanceadas (possível corte incorreto). Nada foi movido. Verifique o arquivo origem manualmente."
    hash_corpo = hashlib.sha256(corpo.encode("utf-8")).hexdigest()
    if preview:
        primeira_linha = corpo.splitlines()[0].strip() if corpo else ""
        return (
            f"PREVIEW (dry-run): Função '{nome_funcao}' localizada em '{arquivo_origem}'.\n"
            f"Linhas: {inicio}-{fim} ({fim - inicio + 1} linha(s))\n"
            f"SHA-256 do corpo: {hash_corpo}\n"
            f"Primeira linha: {primeira_linha}\n"
            f"Nada foi escrito ou removido."
        )
    dest_abs, erro_dest = resolver_caminho(arquivo_destino, permitir_extra=False, permitir_escrita=True)
    if erro_dest:
        return erro_dest
    os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
    dest_existia = os.path.exists(dest_abs)
    if dest_existia and os.path.getsize(dest_abs) > 0:
        corpo_dest, _ = _extrair_corpo_funcao(dest_abs, nome_funcao)
        if corpo_dest is not None:
            return f"ERRO: Já existe uma função '{nome_funcao}' no destino '{arquivo_destino}'. Mover novamente causaria duplicação."
        with open(dest_abs, "r", encoding="utf-8", errors="ignore") as f:
            linhas_dest = f.readlines()
        if _tem_assinatura_funcao_js(linhas_dest, nome_funcao):
            return f"ERRO: Já existe a assinatura da função '{nome_funcao}' no destino '{arquivo_destino}' (mesmo que truncada/duplicada). Corrija o destino manualmente antes de mover novamente."
    if dest_existia:
        with open(dest_abs, "r", encoding="utf-8") as f:
            conteudo_dest = f.read()
    else:
        conteudo_dest = ""
    diff_dest, grupo_mover = _gravar_destino_com_corpo(dest_abs, dest_existia, conteudo_dest, corpo, remover_origem)
    if remover_origem:
        with open(origem_abs, "r", encoding="utf-8") as f:
            conteudo_orig = f.read()
        linhas_orig = conteudo_orig.replace("\r\n", "\n").splitlines(keepends=True)
        del linhas_orig[inicio - 1:fim]
        novo_orig = "".join(_colapsar_linhas_vazias(linhas_orig))
        registrar_edicao(origem_abs, conteudo_orig, novo_orig, grupo=grupo_mover)
        with open(origem_abs, "w", encoding="utf-8") as f:
            f.write(novo_orig)
        _emitir_diff_movido(arquivo_origem, arquivo_destino, conteudo_orig, novo_orig, diff_dest)
    else:
        emit_event("action_diff", actionName=arquivo_destino, diff=diff_dest)
    notificar_mudanca_arquivos()
    return (
        f"SUCESSO: Função '{nome_funcao}' movida verbatim.\n"
        f"Origem: {arquivo_origem} (linhas {inicio}-{fim})\n"
        f"Destino: {arquivo_destino}\n"
        f"Linhas movidas: {fim - inicio + 1}\n"
        f"SHA-256 do corpo: {hash_corpo}\n"
        f"Removida da origem: {'sim' if remover_origem else 'não'}"
    )

@register(
    "tool_verificar_integridade_refatoracao",
    'Verifica se uma função movida por refatoração permaneceu idêntica (verbatim) ao original, comparando hash e byte a byte. Use após tool_mover_funcao_verbatim para provar que o movimento não alterou nada.',
    {
        'arquivo_origem': {"tipo": "STRING", "padrao": ""},
        'nome_funcao': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'arquivo_destino': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'hash_esperado': {"tipo": "STRING", "padrao": ""},
    },
)
def tool_verificar_integridade_refatoracao(arquivo_origem, nome_funcao, arquivo_destino, hash_esperado=""):
    emit_event("executing", function=f"Verificando integridade: {nome_funcao}")
    def _hash(texto):
        return hashlib.sha256(texto.encode("utf-8")).hexdigest()
    origem_abs, erro = resolver_caminho(arquivo_origem, permitir_extra=True)
    if erro:
        return erro
    dest_abs, erro_dest = resolver_caminho(arquivo_destino, permitir_extra=True)
    if erro_dest:
        return erro_dest
    if not os.path.exists(dest_abs):
        return f"ERRO: Arquivo destino '{arquivo_destino}' não existe."
    corpo_dest, info_dest = _extrair_corpo_funcao(dest_abs, nome_funcao)
    if corpo_dest is None:
        return f"ERRO no destino: {info_dest}"
    hash_dest = _hash(corpo_dest)
    linhas = []
    linhas.append(f"Função '{nome_funcao}' no destino '{arquivo_destino}':")
    linhas.append(f"  SHA-256: {hash_dest}")
    linhas.append(f"  Linhas: {info_dest[0]}-{info_dest[1]}")
    if hash_esperado:
        hash_esperado = hash_esperado.strip()
        if hash_dest == hash_esperado:
            linhas.append("  RESULTADO: INTEGRO (hash bate com o esperado). Nenhuma alteração detectada.")
            return "\n".join(linhas)
        linhas.append("  RESULTADO: DIVERGENTE (hash NÃO bate com o esperado).")
        return "\n".join(linhas)
    if not os.path.exists(origem_abs):
        linhas.append("  AVISO: arquivo origem não existe mais para comparação byte a byte; use 'hash_esperado' para validar.")
        return "\n".join(linhas)
    corpo_orig, info_orig = _extrair_corpo_funcao(origem_abs, nome_funcao)
    if corpo_orig is None:
        linhas.append(f"  AVISO: função não encontrada na origem ({info_orig}); use 'hash_esperado' para validar.")
        return "\n".join(linhas)
    hash_orig = _hash(corpo_orig)
    linhas.append(f"  Origem '{arquivo_origem}' SHA-256: {hash_orig}")
    if corpo_orig == corpo_dest:
        linhas.append("  RESULTADO: INTEGRO (origem e destino são idênticos byte a byte).")
    else:
        linhas.append("  RESULTADO: DIVERGENTE (origem e destino diferem).")
        linhas.append("  Diferenças (linha por linha):")
        diff = gerar_diff(corpo_orig, corpo_dest)
        for parte in diff:
            if parte["type"] != "unmodified":
                texto = parte["text"].rstrip("\n")
                if parte["type"] == "deleted":
                    linhas.append(f"    - [origem] {texto}")
                elif parte["type"] == "added":
                    linhas.append(f"    + [destino] {texto}")
    return "\n".join(linhas)

@register(
    "tool_remover_funcao",
    'Remove uma funcao, classe ou rota inteira de um ficheiro, por nome, sem redigitar nada: o range sai do AST no Python (ja com os decoradores @ incluidos, que de outro modo ficariam orfaos) ou do balanceamento de chaves no JavaScript. A gravacao entra na pilha de undo. RECUSA quando o nome ainda e usado noutro ponto do MESMO ficheiro e lista as linhas - o uso no projeto inteiro confirma-se com tool_pesquisar_no_projeto. Em Python volta a parsear o ficheiro depois de cortar e NAO apaga se o corte quebrar a sintaxe (ex: o corpo ficava so com a funcao removida). Use preview=true para ver as linhas e o SHA-256 sem tocar em nada. E o caminho para apagar codigo morto (regra 17) sem citar o corpo inteiro no tool_substituir_texto.',
    {
        'arquivo': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'nome_funcao': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'preview': {"tipo": "BOOLEAN", "padrao": False},
    },
    disponivel="edicao",
)
def tool_remover_funcao(arquivo, nome_funcao, preview=False):
    if estado.get("bloquear_edicao"):
        return "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    emit_event("executing", function=f"Apagando funcao: {nome_funcao}")
    if isinstance(preview, str):
        preview = preview.strip().lower() in ("1", "true", "sim", "yes", "s")
    alvo_abs, erro = resolver_caminho(arquivo, permitir_escrita=True)
    if erro:
        return erro
    if not os.path.exists(alvo_abs):
        return f"ERRO: Arquivo '{arquivo}' não existe."
    with open(alvo_abs, "r", encoding="utf-8", errors="ignore") as f:
        conteudo_orig = f.read()
    linhas = conteudo_orig.replace("\r\n", "\n").splitlines(keepends=True)
    r = _range_com_decoradores_py(linhas, nome_funcao) if alvo_abs.endswith(".py") else _localizar_funcao_js(linhas, nome_funcao)
    if isinstance(r, str):
        return r
    inicio, fim = r
    if inicio < 1 or fim < inicio or fim > len(linhas):
        return f"ERRO: range inválido ({inicio}-{fim}) para '{nome_funcao}'. Nada foi apagado."
    corpo = "".join(linhas[inicio - 1:fim])
    hash_corpo = hashlib.sha256(corpo.encode("utf-8")).hexdigest()
    padrao = re.compile(r"\b" + re.escape(nome_funcao) + r"\b")
    usos = [i + 1 for i, linha in enumerate(linhas) if not (inicio - 1 <= i < fim) and padrao.search(linha)]
    if preview:
        if usos:
            amostra = ", ".join(str(n) for n in usos[:8])
            aviso = f"AVISO: ainda ha {len(usos)} referencia(s) no mesmo ficheiro (linhas {amostra}{'...' if len(usos) > 8 else ''}) - a remocao seria recusada."
        else:
            aviso = "Sem referencias no mesmo ficheiro."
        return (
            f"PREVIEW (dry-run): '{nome_funcao}' localizada em '{arquivo}'.\n"
            f"Linhas: {inicio}-{fim} ({fim - inicio + 1} linha(s))\n"
            f"SHA-256 do corpo: {hash_corpo}\n"
            f"Primeira linha: {corpo.splitlines()[0].strip() if corpo else ''}\n"
            f"{aviso}\n"
            f"Nada foi apagado."
        )
    if usos:
        amostra = ", ".join(str(n) for n in usos[:8])
        resto = "..." if len(usos) > 8 else ""
        return (
            f"ERRO: '{nome_funcao}' ainda é usada em {len(usos)} ponto(s) deste ficheiro (linhas {amostra}{resto}). "
            "Apagar agora deixaria essas referências penduradas. Trate primeiro quem a chama (ou apague os dois lados "
            "na mesma edição com tool_substituir_texto). Nada foi apagado."
        )
    del linhas[inicio - 1:fim]
    corte = inicio - 1
    while 0 < corte < len(linhas) and not linhas[corte].strip() and not linhas[corte - 1].strip():
        del linhas[corte]
    novo = "".join(linhas)
    if alvo_abs.endswith(".py"):
        try:
            ast.parse(novo)
        except SyntaxError as e:
            return (
                f"ERRO: apagar '{nome_funcao}' quebraria a sintaxe do ficheiro (linha {e.lineno}: {e.msg}). "
                "Costuma ser um corpo que ficava só com esta função. Nada foi apagado - apague pelo bloco com "
                "tool_substituir_texto e ajuste o que fica à mão."
            )
    registrar_edicao(alvo_abs, conteudo_orig, novo)
    with open(alvo_abs, "w", encoding="utf-8", errors="ignore") as f:
        f.write(novo)
    emit_event("action_diff", actionName=arquivo, diff=gerar_diff(conteudo_orig, novo))
    notificar_mudanca_arquivos()
    return (
        f"SUCESSO: '{nome_funcao}' removida de '{arquivo}'.\n"
        f"Linhas apagadas: {inicio}-{fim} ({fim - inicio + 1} linha(s))\n"
        f"SHA-256 do corpo: {hash_corpo}\n"
        "Desfazível com tool_desfazer; confirme a sintaxe com tool_validar_sintaxe."
    )

@register(
    "tool_mover_bloco_verbatim",
    "Move um bloco/range de linhas (ou um bloco delimitado por tags, ex: '<style>...</style>') de um arquivo para outro copiando os bytes exatos do disco (verbatim, sem redigitar). Use OU linha_inicio/linha_fim OU tag_abertura/tag_fechamento (com 'ocorrencia' para escolher qual bloco quando houver mais de um). Remove o bloco da origem e verifica por SHA-256 e por presença/ausência que saiu inteiro da origem e entrou idêntico no destino. Ideal para CSS/HTML/blocos de texto que tool_mover_funcao_verbatim não cobre. Use SEMPRE para mover blocos grandes em vez de fatiar manualmente.",
    {
        'arquivo_origem': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'arquivo_destino': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'linha_inicio': {"tipo": "INTEGER", "padrao": 0},
        'linha_fim': {"tipo": "INTEGER", "padrao": 0},
        'tag_abertura': {"tipo": "STRING", "padrao": ""},
        'tag_fechamento': {"tipo": "STRING", "padrao": ""},
        'remover_origem': {"tipo": "BOOLEAN", "padrao": True},
        'ocorrencia': {"tipo": "INTEGER", "padrao": 1},
    },
    disponivel="edicao",
)
def tool_mover_bloco_verbatim(arquivo_origem, arquivo_destino, linha_inicio=0, linha_fim=0, tag_abertura="", tag_fechamento="", remover_origem=True, ocorrencia=1):
    if estado.get("bloquear_edicao"):
        return "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    emit_event("executing", function="Movendo bloco verbatim")
    if isinstance(remover_origem, str):
        remover_origem = remover_origem.strip().lower() in ("1", "true", "sim", "yes", "s")
    try:
        ocorrencia = int(ocorrencia) if str(ocorrencia).strip().isdigit() else 1
    except Exception:
        ocorrencia = 1
    if ocorrencia < 1:
        ocorrencia = 1

    origem_abs, erro = resolver_caminho(arquivo_origem, permitir_extra=True)
    if erro:
        return erro
    if not os.path.exists(origem_abs):
        return f"ERRO: Arquivo origem '{arquivo_origem}' não existe."

    with open(origem_abs, "r", encoding="utf-8", errors="ignore") as f:
        conteudo_orig = f.read()
    linhas_orig = conteudo_orig.replace("\r\n", "\n").splitlines(keepends=True)

    inicio = None
    fim = None
    modo = ""

    if tag_abertura:
        modo = "tags"
        tag_ab = tag_abertura
        fecho = tag_fechamento
        if not fecho:
            m = re.match(r'^</?([A-Za-z][\w-]*)', tag_ab.strip())
            if m:
                fecho = "</" + m.group(1) + ">"
            else:
                fecho = tag_ab
        achados = [i for i, l in enumerate(linhas_orig) if tag_ab in l]
        if not achados:
            return f"ERRO: Tag de abertura '{tag_ab}' não encontrada no arquivo origem."
        if len(achados) < ocorrencia:
            return f"ERRO: Tag de abertura '{tag_ab}' tem {len(achados)} ocorrência(s), mas foi pedida a ocorrência {ocorrencia}."
        idx_abertura = achados[ocorrencia - 1]
        idx_fechamento = None
        for i in range(idx_abertura, len(linhas_orig)):
            if fecho in linhas_orig[i]:
                idx_fechamento = i
                break
        if idx_fechamento is None:
            return f"ERRO: Tag de fechamento '{fecho}' não encontrada após a abertura (ocorrência {ocorrencia})."
        inicio = idx_abertura + 1
        fim = idx_fechamento + 1
    else:
        modo = "linhas"
        try:
            inicio = int(linha_inicio)
            fim = int(linha_fim)
        except (TypeError, ValueError):
            return "ERRO: Informe um range de linhas (linha_inicio/linha_fim) ou tags (tag_abertura/tag_fechamento)."

    if not inicio or not fim or inicio < 1 or fim < inicio:
        return f"ERRO: Range inválido (inicio={inicio}, fim={fim}). As linhas são 1-based e inclusivas."
    if fim > len(linhas_orig):
        return f"ERRO: linha_fim={fim} ultrapassa o total de linhas do arquivo ({len(linhas_orig)})."

    corpo = "".join(linhas_orig[inicio - 1:fim])
    if not corpo.strip():
        return "ERRO: O bloco selecionado está vazio."

    hash_corpo = hashlib.sha256(corpo.encode("utf-8")).hexdigest()

    dest_abs, erro_dest = resolver_caminho(arquivo_destino, permitir_extra=False, permitir_escrita=True)
    if erro_dest:
        return erro_dest
    os.makedirs(os.path.dirname(dest_abs), exist_ok=True)

    dest_existia = os.path.exists(dest_abs)
    conteudo_dest = ""
    if dest_existia:
        with open(dest_abs, "r", encoding="utf-8", errors="ignore") as f:
            conteudo_dest = f.read()
        if corpo in conteudo_dest.replace("\r\n", "\n"):
            return f"ERRO: O bloco já existe no destino '{arquivo_destino}'. Mover novamente causaria duplicação."

    diff_dest, grupo_mover = _gravar_destino_com_corpo(dest_abs, dest_existia, conteudo_dest, corpo, remover_origem, errors="ignore")

    verificacoes = []
    with open(dest_abs, "r", encoding="utf-8", errors="ignore") as f:
        conteudo_dest_final = f.read()
    if corpo in conteudo_dest_final.replace("\r\n", "\n"):
        verificacoes.append("DESTINO: OK (bloco copiado verbatim, hash confere)")
    else:
        verificacoes.append("DESTINO: FALHOU (bloco não encontrado no destino após a escrita)")

    if remover_origem:
        del linhas_orig[inicio - 1:fim]
        novo_orig = "".join(linhas_orig)
        registrar_edicao(origem_abs, conteudo_orig, novo_orig, grupo=grupo_mover)
        with open(origem_abs, "w", encoding="utf-8", errors="ignore") as f:
            f.write(novo_orig)
        _emitir_diff_movido(arquivo_origem, arquivo_destino, conteudo_orig, novo_orig, diff_dest)
        with open(origem_abs, "r", encoding="utf-8", errors="ignore") as f:
            conteudo_orig_final = f.read()
        if corpo not in conteudo_orig_final.replace("\r\n", "\n"):
            verificacoes.append("ORIGEM: OK (bloco totalmente removido, zero resíduo)")
        else:
            verificacoes.append("ORIGEM: FALHOU (bloco ainda presente na origem após a remoção)")
    else:
        emit_event("action_diff", actionName=arquivo_destino, diff=diff_dest)

    notificar_mudanca_arquivos()
    n_linhas = fim - inicio + 1
    return (
        f"SUCESSO: Bloco movido verbatim (modo={modo}).\n"
        f"Origem: {arquivo_origem} (linhas {inicio}-{fim})\n"
        f"Destino: {arquivo_destino}\n"
        f"Linhas movidas: {n_linhas}\n"
        f"SHA-256 do bloco: {hash_corpo}\n"
        f"Removido da origem: {'sim' if remover_origem else 'não'}\n"
        f"Verificações:\n" + "\n".join(f"  - {v}" for v in verificacoes)
    )

@register(
    "tool_mover_arquivo_binario",
    'Move um arquivo binário ou uma pasta inteira (ícones, imagens, fontes, binários) de um lugar para outro byte a byte usando shutil.move. Use para mover .ico, .png, .exe ou pastas inteiras que tool_mover_bloco_verbatim não consegue (só lida com texto). Retorna o SHA-256 do arquivo movido e verifica que a origem sumiu e o destino apareceu.',
    {
        'origem': {"tipo": "STRING", "desc": 'Caminho relativo do arquivo ou pasta a mover', "obrig": True, "padrao": ""},
        'destino': {"tipo": "STRING", "desc": 'Caminho relativo de destino (arquivo ou pasta)', "obrig": True, "padrao": ""},
        'sobrescrever': {"tipo": "BOOLEAN", "desc": 'Se True, substitui o destino caso já exista', "padrao": False},
    },
    disponivel="edicao",
)
def tool_mover_arquivo_binario(origem, destino, sobrescrever=False):
    if estado.get("bloquear_edicao"):
        return "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    emit_event("executing", function=f"Movendo arquivo/pasta (binário): {origem}")
    if isinstance(sobrescrever, str):
        sobrescrever = sobrescrever.strip().lower() in ("1", "true", "sim", "yes", "s")
    origem_abs, erro = resolver_caminho(origem, permitir_extra=True)
    if erro:
        return erro
    if not os.path.exists(origem_abs):
        return f"ERRO: Origem '{origem}' não existe."
    dest_abs, erro_dest = resolver_caminho(destino, permitir_extra=False, permitir_escrita=True)
    if erro_dest:
        return erro_dest
    if os.path.exists(dest_abs) and not sobrescrever:
        return f"ERRO: Destino '{destino}' já existe. Use sobrescrever=True para substituí-lo."
    os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
    hash_orig = None
    if os.path.isfile(origem_abs):
        try:
            with open(origem_abs, "rb") as f:
                hash_orig = hashlib.sha256(f.read()).hexdigest()
        except OSError as e:
            return f"ERRO ao ler a origem para calcular o hash: {e}"
    try:
        if sobrescrever and os.path.isdir(dest_abs):
            shutil.rmtree(dest_abs)
        shutil.move(origem_abs, dest_abs)
    except OSError as e:
        return f"ERRO ao mover '{origem}' para '{destino}': {e}"
    verificacoes = []
    verificacoes.append("ORIGEM: OK (removida após o move)" if not os.path.exists(origem_abs) else "ORIGEM: FALHOU (ainda existe após o move)")
    verificacoes.append("DESTINO: OK (presente após o move)" if os.path.exists(dest_abs) else "DESTINO: FALHOU (não encontrado após o move)")
    if hash_orig and os.path.isfile(dest_abs):
        try:
            with open(dest_abs, "rb") as f:
                hash_dest = hashlib.sha256(f.read()).hexdigest()
            verificacoes.append("HASH: OK (byte a byte idêntico)" if hash_dest == hash_orig else "HASH: FALHOU (hash do destino difere da origem)")
        except OSError:
            verificacoes.append("HASH: INDETERMINADO (não foi possível reler o destino)")
    emit_event("action_diff", actionName=destino, actionType="moved", origem=origem, destino=destino, diff=[])
    notificar_mudanca_arquivos()
    return (
        f"SUCESSO: '{origem}' movido para '{destino}' (shutil.move byte a byte).\n"
        + "\n".join(f"  - {v}" for v in verificacoes)
        + (f"\n  - SHA-256: {hash_orig}" if hash_orig else "")
    )
