import os
import re
import sys
import ast

from src.backend.tools.js_lexico import contar_simbolo, limpar

_RE_FUNCAO_PY = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)
_RE_FUNCAO_JS = re.compile(r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", re.MULTILINE)
_TOKENS_DO_NOME = re.compile(r"[A-Za-z0-9]+")

def _funcoes_py(texto):
    """Funcoes Python com a linha onde comecam, lidas pela AST, nao por regex.

    A regex encontrava 'def' escrito dentro de docstrings e de strings que geram
    codigo (ex: o script embutido de tools/rotas.py) e anunciava funcoes novas que
    nao existem - o mesmo motivo que levou _imports_locais a usar a AST. Se o texto
    estiver com sintaxe invalida (edicao a meio), cai na regex para nao perder o aviso.
    A LINHA faz falta a regra 7: para dizer "poe a funcao abaixo desta" e preciso saber
    onde esta esta.
    """
    if not texto:
        return []
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return [(nome, 0) for nome in _RE_FUNCAO_PY.findall(texto)]
    return [(no.name, no.lineno) for no in ast.walk(arvore)
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))]

def _funcoes_com_linha(caminho, texto):
    """[(nome, linha)] das funcoes declaradas no texto, por tipo de ficheiro."""
    ext = os.path.splitext(caminho)[1].lower()
    if ext in (".py", ".pyw"):
        return sorted(_funcoes_py(texto), key=lambda par: par[1])
    if ext in (".js", ".mjs", ".cjs", ".ts", ".tsx"):
        return [(nome, numero)
                for numero, linha in enumerate((texto or "").splitlines(), start=1)
                for nome in _RE_FUNCAO_JS.findall(linha)]
    return []

def _tokens_do_nome(nome):
    """Palavras de um nome: 'achar_linha_identificador' -> {achar, linha, identificador}."""
    partes = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(nome or ""))
    return {pedaco.lower() for pedaco in _TOKENS_DO_NOME.findall(partes) if len(pedaco) >= 3}

def _aviso_de_posicao(criadas, antes, depois):
    """Onde a funcao nova deve ficar: abaixo da correlacionada, nunca no fim por habito.

    A regra 7 ("posicione a funcao nova abaixo da ultima funcao correlacionada do
    ficheiro") deixa de ser uma instrucao generica e passa a trazer o NOME e a LINHA da
    vizinha, lidos do proprio texto editado. Fala so quando ha mesmo o que corrigir -
    uma funcao colocada ACIMA de todas as suas correlacionadas, ou atirada para o fim
    com outras funcoes pelo meio - e fica calada quando ela ja ficou logo abaixo da que
    lhe pertence, para o aviso nao virar ruido que se aprende a ignorar.
    """
    linhas = {}
    for nome, linha in depois:
        linhas[nome] = max(linhas.get(nome, 0), linha)
    if not linhas:
        return ""
    anteriores = {nome for nome, _ in antes}
    ultima = max(linhas.values())
    partes = []
    for nome in criadas:
        minha = linhas.get(nome)
        if minha is None:
            continue
        meus = _tokens_do_nome(nome)
        parentes = [(outro, linha) for outro, linha in linhas.items()
                    if outro != nome and outro in anteriores and _tokens_do_nome(outro) & meus]
        if not parentes:
            continue
        vizinha, linha_vizinha = min(parentes, key=lambda par: (abs(par[1] - minha), par[1]))
        if minha < linha_vizinha:
            partes.append(
                f"'{nome}' ficou ACIMA de '{vizinha}' (linha {linha_vizinha}), que e correlacionada"
                f" -> move-a para ABAIXO dela, nao a deixes fora do grupo das semelhantes"
            )
        elif minha == ultima and any(linha_vizinha < linha < minha for outro, linha in linhas.items() if outro != nome):
            partes.append(
                f"'{nome}' ficou no FIM do ficheiro, longe de '{vizinha}' (linha {linha_vizinha}),"
                f" que e correlacionada -> coloca-a logo ABAIXO de '{vizinha}' (regra 7),"
                f" nao no fim do ficheiro nem em qualquer lugar"
            )
    if not partes:
        return ""
    return "POSICAO DA FUNCAO NOVA: " + " | ".join(partes)

_RE_IMPORT_JS = re.compile(r"import\s*\{([^}]*)\}", re.MULTILINE)
_RE_IMPORT_JS_NOME = re.compile(r"^\s*import\s+([A-Za-z_$][\w$]*)\s*(?:,|from\s)", re.MULTILINE)
_RE_IMPORT_JS_NAMESPACE = re.compile(r"import\s*\*\s*as\s+([A-Za-z_$][\w$]*)")
_RE_IMPORT_PY = re.compile(r"^\s*from\s+[\w.]+\s+import\s+(?:\(([^)]*)\)|([^\n#]+))", re.MULTILINE)

def _nomes_importados(texto, caminho_relativo):
    """Nomes que o modulo trouxe para dentro de si por import (JS/TS e Python)."""
    ext = os.path.splitext(caminho_relativo or "")[1].lower()
    if ext in (".js", ".mjs", ".cjs", ".ts", ".tsx"):
        blocos = [m.group(1) for m in _RE_IMPORT_JS.finditer(texto or "")]
    elif ext in (".py", ".pyw"):
        blocos = [(m.group(1) if m.group(1) is not None else m.group(2))
                  for m in _RE_IMPORT_PY.finditer(texto or "")]
    else:
        return set()
    nomes = set()
    for bloco in blocos:
        for item in bloco.replace("\\", " ").split(","):
            item = item.split("#")[0].strip()
            if not item or item.startswith("*"):
                continue
            nomes.add(item.split(" as ")[-1].strip())
    if ext in (".js", ".mjs", ".cjs", ".ts", ".tsx"):
        nomes.update(m.group(1) for m in _RE_IMPORT_JS_NOME.finditer(texto or ""))
        nomes.update(m.group(1) for m in _RE_IMPORT_JS_NAMESPACE.finditer(texto or ""))
    return {n for n in nomes if n}

def _aviso_referencias_orfas(caminho_relativo, texto_antigo, texto_novo):
    """Nome que saiu do import nesta edicao e continua a ser usado: quebra em execucao.

    O caso real (renderer.js, lixeira do historico): a edicao tirou
    'confirmDeletePopup' do import e deixou o uso na linha seguinte. A auditoria de
    imports nao ve (js_auditoria.py:_faltantes so olha para 'nome(' e so acusa quando o
    simbolo ainda e exportado por alguem) e o lint so acusa quem o correr depois. Aqui
    os dois textos da edicao ja estao em maos: o caso e apanhado quando nasce.
    """
    if not texto_novo:
        return ""
    saiu = _nomes_importados(texto_antigo, caminho_relativo) - _nomes_importados(texto_novo, caminho_relativo)
    if not saiu:
        return ""
    ext = os.path.splitext(caminho_relativo or "")[1].lower()
    limpo = limpar(texto_novo) if ext in (".js", ".mjs", ".cjs", ".ts", ".tsx") else texto_novo
    orfaos = []
    for nome in sorted(saiu):
        if not re.fullmatch(r"[A-Za-z_$][\w$]*", nome):
            continue
        if re.search(r"\b(?:function|class|const|let|var)\s+" + re.escape(nome) + r"\b", limpo):
            continue
        usos = contar_simbolo(nome, limpo)
        if usos:
            orfaos.append(f"{nome} ({usos}x)")
    if not orfaos:
        return ""
    return ("REFERENCIA ORFA: " + ", ".join(orfaos)
            + " saiu do import nesta edicao e continua a ser usado -> quebra em execucao;"
              " corrige o uso ou repoe o import antes de finalizar.")

def _decoradores_de_registo(texto):
    """[(nome declarado no @register, nome da funcao decorada, linha)] do topo do modulo."""
    if not texto:
        return []
    try:
        arvore = ast.parse(texto)
    except (SyntaxError, ValueError):
        return []
    achados = []
    for no in arvore.body:
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for decorador in no.decorator_list:
            if not isinstance(decorador, ast.Call) or not decorador.args:
                continue
            alvo = decorador.func
            nome_decorador = alvo.id if isinstance(alvo, ast.Name) else getattr(alvo, "attr", "")
            if nome_decorador != "register":
                continue
            primeiro = decorador.args[0]
            if not (isinstance(primeiro, ast.Constant) and isinstance(primeiro.value, str)):
                continue
            achados.append((primeiro.value, no.name, no.lineno))
    return achados

def _aviso_registo_em_funcao_errada(caminho_relativo, texto_novo):
    """@register declarado para um nome que nao e o da funcao logo abaixo dele.

    Um decorador cola-se SEMPRE a funcao imediatamente a seguir: inserir uma
    auxiliar privada entre o `@register("tool_x", ...)` e o `def tool_x` registra a
    auxiliar no lugar do handler, e a ferramenta morre em execucao com um TypeError
    de argumento inesperado - sem a sintaxe acusar nada, porque o ficheiro continua
    valido. A prova de que esta certo e tool_verificar_ferramentas.
    """
    if not str(caminho_relativo or "").endswith(".py"):
        return ""
    errados = [
        f'@register("{declarado}") decora {funcao} (linha {linha})'
        for declarado, funcao, linha in _decoradores_de_registo(texto_novo)
        if declarado != funcao
    ]
    if not errados:
        return ""
    return ("REGISTO NA FUNCAO ERRADA: " + "; ".join(errados)
            + " -> o decorador cola-se a funcao imediatamente a seguir, logo o handler registado e o errado"
              " e a ferramenta morre em execucao (a sintaxe passa): a auxiliar privada vai ANTES do @register"
              " ou DEPOIS da funcao registada. Confirma com tool_verificar_ferramentas.")

def aviso_estrutural_pos_edicao(caminho_relativo, texto_antigo, texto_novo):
    """Checklist automatico anexado ao retorno das ferramentas de edicao.

    Detalha as funcoes criadas/removidas pela edicao para obrigar (por leitura
    direta do retorno da ferramenta) a verificacao de duplicidade antes de criar
    e a verificacao de codigo morto depois de remover. Nao bloqueia a escrita.
    """
    if texto_novo is None:
        return ""
    antes = _funcoes_com_linha(caminho_relativo, texto_antigo or "")
    depois = _funcoes_com_linha(caminho_relativo, texto_novo)
    nomes_antes = {nome for nome, _ in antes}
    nomes_depois = {nome for nome, _ in depois}
    criadas = sorted(nomes_depois - nomes_antes)
    removidas = sorted(nomes_antes - nomes_depois)
    partes = []
    registo = _aviso_registo_em_funcao_errada(caminho_relativo, texto_novo)
    if registo:
        partes.append(registo)
    chamada = _aviso_chamada_sem_parametro(caminho_relativo, texto_novo)
    if chamada:
        partes.append(chamada)
    if criadas:
        partes.append(
            "FUNCAO(OES) NOVA(S): " + ", ".join(criadas)
            + " -> POSICAO: abaixo da ultima funcao correlacionada do modulo, nunca no fim do ficheiro nem em qualquer lugar. ANTES de finalizar: tool_buscar_codigo + tool_pesquisar_no_projeto pelo nome/objetivo e tool_analisar_similaridade; se ja existir equivalente, MESCLAR em vez de duplicar."
        )
        posicao = _aviso_de_posicao(criadas, antes, depois)
        if posicao:
            partes.append(posicao)
    if removidas:
        partes.append(
            "FUNCAO(OES) REMOVIDA(S): " + ", ".join(removidas)
            + " -> ANTES de finalizar: tool_pesquisar_no_projeto por cada nome (garantir que nada as chama) e tool_auditar_imports_py/js no arquivo (imports, variaveis e dead code orfaos)."
        )
    orfas = _aviso_referencias_orfas(caminho_relativo, texto_antigo, texto_novo)
    if orfas:
        partes.append(orfas)
    if not partes:
        return ""
    return " | CHECKLIST ESTRUTURAL: " + " | ".join(partes)

def _assinaturas_do_topo(arvore):
    assinaturas = {}
    repetidos = set()
    for no in arvore.body:
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if no.name in assinaturas:
            repetidos.add(no.name)
            continue
        argumentos = no.args
        aceitos = [a.arg for a in (*argumentos.posonlyargs, *argumentos.args, *argumentos.kwonlyargs)]
        assinaturas[no.name] = (aceitos, argumentos.kwarg is not None)
    for nome in repetidos:
        assinaturas.pop(nome, None)
    return assinaturas

def _chamadas_com_palavra_inexistente(arvore, assinaturas):
    achados = set()
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Name):
            continue
        alvo = assinaturas.get(no.func.id)
        if alvo is None:
            continue
        aceitos, tem_kwargs = alvo
        if tem_kwargs:
            continue
        for palavra in no.keywords:
            if palavra.arg is not None and palavra.arg not in aceitos:
                achados.add((no.lineno, no.func.id, palavra.arg, ", ".join(aceitos)))
    return sorted(achados)

def _aviso_chamada_sem_parametro(caminho_relativo, texto_novo):
    """Chamada a uma funcao do proprio modulo com palavra-chave que a assinatura nao tem."""
    if not str(caminho_relativo or "").endswith(".py") or not texto_novo:
        return ""
    try:
        arvore = ast.parse(texto_novo)
    except (SyntaxError, ValueError):
        return ""
    achados = _chamadas_com_palavra_inexistente(arvore, _assinaturas_do_topo(arvore))
    if not achados:
        return ""
    detalhe = "; ".join(f"linha {linha}: {nome}({palavra}=...) mas a assinatura tem ({aceitos})"
                        for linha, nome, palavra, aceitos in achados)
    return ("CHAMADA COM PARAMETRO INEXISTENTE: " + detalhe
            + " -> a sintaxe passa e so rebenta em execucao, com TypeError a meio da ferramenta:"
              " acerte a chamada ou a assinatura.")

_MARCADOR_IMPORT_LOCAL = "# import-local"

def _imports_locais(texto):
    """Imports dentro de blocos (col_offset > 0), lidos pela AST.

    Ler a AST em vez de regex evita falso positivo com exemplos de codigo
    escritos em docstrings. Devolve [(linha, modulo)] ordenado.
    """
    if not texto:
        return []
    try:
        arvore = ast.parse(texto)
    except (SyntaxError, ValueError):
        return []
    achados = []
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.Import, ast.ImportFrom)) or no.col_offset <= 0:
            continue
        if isinstance(no, ast.Import):
            nomes = [alias.name.split(".")[0] for alias in no.names]
        else:
            nomes = [(no.module or "").split(".")[0]]
        achados.extend((no.lineno, nome) for nome in nomes if nome)
    return sorted(achados)

def _import_local_marcado(texto, linha):
    linhas = texto.splitlines()
    for alvo in (linha, linha - 1):
        if 1 <= alvo <= len(linhas) and _MARCADOR_IMPORT_LOCAL in linhas[alvo - 1]:
            return True
    return False

def _novos_imports_locais(caminho_relativo, texto_antigo, texto_novo):
    """[(linha, modulo)] dos imports locais introduzidos pela edicao."""
    if not texto_novo or not str(caminho_relativo).endswith(".py"):
        return []
    anteriores = {nome for _, nome in _imports_locais(texto_antigo or "")}
    return [
        (linha, nome)
        for linha, nome in _imports_locais(texto_novo)
        if nome not in anteriores and not _import_local_marcado(texto_novo, linha)
    ]

def bloquear_import_local(caminho_relativo, texto_antigo, texto_novo):
    """Trava de escrita: recusa import local novo de biblioteca padrao.

    Import da stdlib nunca tem motivo para ficar dentro de uma funcao: nao ha
    ciclo de importacao, custo de carregamento nem dependencia opcional. Ja as
    dependencias externas e os modulos do proprio projeto continuam livres: ai a
    importacao dentro da funcao costuma ser deliberada (ciclo, ordem de patch ou
    carga tardia), por isso recebem apenas aviso. Excecao explicita: a propria
    linha do import (ou a
    anterior) pode conter '# import-local: <motivo>'.
    """
    ofensores = [
        (linha, nome)
        for linha, nome in _novos_imports_locais(caminho_relativo, texto_antigo, texto_novo)
        if nome in sys.stdlib_module_names
    ]
    if not ofensores:
        return ""
    detalhe = ", ".join(f"linha {linha}: '{nome}'" for linha, nome in ofensores)
    return (
        "IMPORT LOCAL DE BIBLIOTECA PADRAO: " + detalhe
        + ". Import da stdlib vai SEMPRE no bloco de imports do topo do arquivo. "
        "Mova o import para o topo e repita a edicao; se houver motivo tecnico real, "
        "marque a linha com '" + _MARCADOR_IMPORT_LOCAL + ": <motivo>'."
    )

def aviso_import_local(caminho_relativo, texto_antigo, texto_novo):
    """Aviso (nao bloqueia) para import local novo de dependencia externa/projeto."""
    novos = [
        (linha, nome)
        for linha, nome in _novos_imports_locais(caminho_relativo, texto_antigo, texto_novo)
        if nome not in sys.stdlib_module_names
    ]
    if not novos:
        return ""
    detalhe = ", ".join(f"linha {linha}: '{nome}'" for linha, nome in novos)
    return (
        " | IMPORT LOCAL NOVO: " + detalhe
        + " -> confirme que e deliberado (ciclo, ordem de patch ou carga tardia); "
        "caso contrario mova para o topo do arquivo."
    )
