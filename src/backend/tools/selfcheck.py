"""Checkup do registo de ferramentas (integridade depois de reiniciar o backend).

O registo (tools/registry.py) e a unica fonte de verdade das ferramentas do
agente, e ha tres falhas que NAO rebentam ao arrancar - so aparecem a meio de uma
rodada, quando a ferramenta ja devia estar a ser usada:

  * um modulo de tools/ que declara @register mas ficou fora do import do
    ai/loop.py: as ferramentas dele nunca chegam a existir (desaparecem caladas);
  * um handler cuja assinatura nao casa com o esquema declarado: o modelo ve a
    ferramenta, mas o despacho rebenta com TypeError;
  * uma declaracao mal formada ('required' a citar parametro inexistente, enum
    vazio, propriedade fora do esquema);
  * o processo esta a correr codigo ANTERIOR ao disco (backend nao reiniciado
    depois da ultima edicao): o registo parece saudavel, mas as ferramentas novas
    nao existem neste processo e quem responde sao os handlers velhos.

Este checkup cobre os quatro em segundos. Nao escreve nada, nao chama nenhuma
ferramenta real e nao usa o registo como cobaia: a resolucao dos argumentos e
provada na funcao PURA resolver_kwargs do registo e o nome desconhecido no
proprio dispatch, ambos sem efeitos colaterais.
"""

import ast
import inspect
import os

from src.backend.config import APP_ROOT
from src.backend.state import ARRANQUE, emit_event
from src.backend.tools.registry import (
    TOOL_REGISTRY,
    resolver_kwargs,
    build_function_declarations,
    collisions,
    dispatch,
    register,
)

_TIPOS_VALIDOS = ("STRING", "INTEGER", "NUMBER", "BOOLEAN")

_ESQUEMA_SONDA = {
    "texto": {"tipo": "STRING", "obrig": True, "padrao": ""},
    "booleano": {"tipo": "BOOLEAN", "obrig": False, "padrao": False},
    "inteiro": {"tipo": "INTEGER", "obrig": False, "padrao": 7},
    "derivado": {
        "tipo": "STRING",
        "obrig": False,
        "padrao": lambda args: f"eco:{args.get('texto', '')}",
    },
}


def _nome_decorador(decorador):
    if isinstance(decorador, ast.Call):
        decorador = decorador.func
    if isinstance(decorador, ast.Name):
        return decorador.id
    if isinstance(decorador, ast.Attribute):
        return decorador.attr
    return ""


def _modulos_com_registo():
    """(modulos, erros) dos ficheiros de tools/ que registam tools com @register.

    Olha para a AST (decorador real) e nao para o texto, para uma mencao em
    docstring ou comentario nao contar como registo.
    """
    pasta = os.path.join(APP_ROOT, "src", "backend", "tools")
    modulos = []
    erros = []
    for arquivo in sorted(os.listdir(pasta)):
        if not arquivo.endswith(".py") or arquivo in ("__init__.py", "registry.py"):
            continue
        try:
            with open(os.path.join(pasta, arquivo), "r", encoding="utf-8") as f:
                arvore = ast.parse(f.read())
        except (OSError, SyntaxError) as erro:
            erros.append(f"{arquivo}: {type(erro).__name__}: {erro}")
            continue
        for no in ast.walk(arvore):
            e_funcao = isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
            if e_funcao and any(_nome_decorador(d) == "register" for d in no.decorator_list):
                modulos.append(arquivo[:-3])
                break
    return modulos, erros


def _modulos_importados():
    """Modulos de tools/ que o ai/loop.py importa pelo efeito de registo."""
    caminho = os.path.join(APP_ROOT, "src", "backend", "ai", "loop.py")
    with open(caminho, "r", encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and no.module == "src.backend.tools":
            importados.update(alias.name for alias in no.names)
    return importados


def _problemas_modulos():
    problemas = []
    modulos, erros = _modulos_com_registo()
    problemas.extend(erros)
    orfaos = sorted(m for m in modulos if m not in _modulos_importados())
    if orfaos:
        problemas.append(
            "modulos com @register fora do import do ai/loop.py (nunca registam): "
            + ", ".join(orfaos)
        )
    return modulos, problemas


def _modulos_carregados():
    """Modulos de tools/ que registaram ferramentas NESTE processo (nome -> tools).

    Olha para o ficheiro de origem do handler, nao para o texto do import: um
    modulo apagado do disco mas ainda vivo em memoria (processo antigo) conta
    aqui como carregado, e e isso que denuncia o processo desatualizado.
    """
    pasta = os.path.join(APP_ROOT, "src", "backend", "tools")
    carregados = {}
    for nome, entry in TOOL_REGISTRY.items():
        handler = entry.get("handler")
        arquivo = getattr(getattr(handler, "__code__", None), "co_filename", "") or ""
        if os.path.dirname(os.path.abspath(arquivo)) != pasta:
            continue
        carregados.setdefault(os.path.basename(arquivo)[:-3], []).append(nome)
    return carregados


def _problemas_carregamento(modulos_disco):
    """Disco x processo: modulos que existem num lado e nao no outro."""
    carregados = set(_modulos_carregados())
    problemas = []
    faltam = sorted(set(modulos_disco) - carregados)
    sobram = sorted(carregados - set(modulos_disco))
    if faltam:
        problemas.append("modulo(s) no disco e nao carregados neste processo: " + ", ".join(faltam))
    if sobram:
        problemas.append("modulo(s) carregados que ja nao existem no disco: " + ", ".join(sobram))
    if problemas:
        problemas.append(
            "=> este processo corre codigo anterior ao disco: reinicie o backend (Ctrl+Shift+B)"
        )
    return problemas


def _arquivos_editados_desde_o_arranque():
    """Ficheiros .py do backend alterados depois de este processo arrancar."""
    pasta = os.path.join(APP_ROOT, "src", "backend")
    candidatos = [os.path.join(APP_ROOT, "app.py")]
    for raiz, subpastas, arquivos in os.walk(pasta):
        subpastas[:] = [s for s in subpastas if s != "__pycache__"]
        candidatos.extend(os.path.join(raiz, a) for a in arquivos if a.endswith(".py"))
    editados = []
    for caminho in candidatos:
        try:
            quando = os.path.getmtime(caminho)
        except OSError:
            continue
        if quando > ARRANQUE:
            editados.append((quando, os.path.relpath(caminho, APP_ROOT)))
    editados.sort(reverse=True)
    return [nome for _, nome in editados]


def _problemas_assinatura(nome, handler, params):
    """O handler tem de aceitar exatamente os nomes que o esquema promete ao modelo."""
    try:
        assinatura = inspect.signature(handler)
    except (TypeError, ValueError):
        return []
    parametros = list(assinatura.parameters.values())
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parametros):
        return []
    problemas = []
    faltam = sorted(set(params) - set(assinatura.parameters))
    if faltam:
        problemas.append(f"{nome}: o handler nao aceita {faltam}, declarado(s) no esquema")
    for pnome, p in assinatura.parameters.items():
        if pnome in params or p.default is not inspect.Parameter.empty:
            continue
        if p.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            problemas.append(f"{nome}: o handler exige {pnome!r}, ausente do esquema")
    return problemas


def _problemas_estrutura():
    problemas = []
    for nome, entry in TOOL_REGISTRY.items():
        if not nome.startswith("tool_"):
            problemas.append(f"{nome}: nome fora do padrao 'tool_*'")
        handler = entry.get("handler")
        if not callable(handler):
            problemas.append(f"{nome}: handler nao e chamavel")
            continue
        if not str(entry.get("descricao") or "").strip():
            problemas.append(f"{nome}: sem descricao (o modelo nao sabe quando a usar)")
        params = entry.get("params")
        if params is not None and not isinstance(params, dict):
            problemas.append(f"{nome}: 'params' devia ser dicionario ou None")
            continue
        for pnome, pmeta in (params or {}).items():
            if not isinstance(pmeta, dict):
                problemas.append(f"{nome}.{pnome}: metadados deviam ser dicionario")
                continue
            if (pmeta.get("tipo") or "STRING") not in _TIPOS_VALIDOS:
                problemas.append(f"{nome}.{pnome}: tipo {pmeta.get('tipo')!r} invalido")
            if pmeta.get("enum") is not None and not list(pmeta["enum"]):
                problemas.append(f"{nome}.{pnome}: 'enum' vazio")
        problemas.extend(_problemas_assinatura(nome, handler, params or {}))
    return problemas


def _declaracoes():
    """(declaracoes, erro): a uniao dos cenarios de escopo, porque nenhum sozinho cobre o registo.

    O escopo 'computer' (ai_model='gemini-flash' sem DeepSeek) e o UNICO que liga
    tool_computador e o unico que desliga as de escopo 'web': comparar o registo
    com um so cenario acusava uma falha que nao existe.
    """
    try:
        # import-local: SDK pesado e opcional (o checkup degrada em vez de rebentar)
        from google.genai import types
    except ImportError as erro:
        return None, f"google.genai indisponivel: {erro}"
    try:
        comuns = build_function_declarations(types, modo="semi", use_deepseek=True, web_ok=True)
        do_computador = build_function_declarations(
            types, modo="semi", use_deepseek=False, web_ok=True, ai_model="gemini-flash"
        )
        vistos = {d.name for d in comuns}
        return comuns + [d for d in do_computador if d.name not in vistos], None
    except Exception as erro:
        return None, f"build_function_declarations rebentou: {type(erro).__name__}: {erro}"


def _problemas_declaracoes(decls):
    problemas = []
    if decls is None:
        return problemas
    nomes = [d.name for d in decls]
    if len(decls) != len(TOOL_REGISTRY):
        problemas.append(
            f"declaracoes ({len(decls)}) != registo ({len(TOOL_REGISTRY)}) com tudo disponivel"
        )
    if len(set(nomes)) != len(nomes):
        problemas.append("declaracao repetida na lista enviada ao modelo")
    for decl in decls:
        if not str(decl.description or "").strip():
            problemas.append(f"{decl.name}: declaracao sem descricao")
        params = (TOOL_REGISTRY.get(decl.name) or {}).get("params") or {}
        if not params:
            continue
        props = set(getattr(decl.parameters, "properties", None) or {})
        obrig = list(getattr(decl.parameters, "required", None) or [])
        if props != set(params):
            problemas.append(
                f"{decl.name}: propriedades {sorted(props)} != esquema {sorted(params)}"
            )
        fora = sorted(o for o in obrig if o not in props)
        if fora:
            problemas.append(f"{decl.name}: 'required' cita parametro inexistente {fora}")
        esperados = sorted(p for p, m in params.items() if m.get("obrig"))
        if sorted(obrig) != esperados:
            problemas.append(
                f"{decl.name}: 'required' {sorted(obrig)} != obrigatorios do esquema {esperados}"
            )
    return problemas


def _problemas_despacho():
    problemas = []
    casos = (
        (
            "valor do modelo e padrao simples",
            {"texto": "abc", "booleano": "false", "derivado": "escolhido"},
            {"texto": "abc", "booleano": False, "inteiro": 7, "derivado": "escolhido"},
        ),
        (
            "padrao callable e coercao numerica",
            {"texto": 5, "inteiro": "12"},
            {"texto": "5", "booleano": False, "inteiro": 12, "derivado": "eco:5"},
        ),
    )
    for rotulo, entrada, esperado in casos:
        obtido = resolver_kwargs(_ESQUEMA_SONDA, entrada)
        if obtido != esperado:
            problemas.append(f"despacho ({rotulo}): esperado {esperado}, obtido {obtido}")
    resultado, conhecida = dispatch("__ferramenta_inexistente__", {})
    if conhecida or resultado is not None:
        problemas.append("despacho: nome desconhecido devia devolver (None, False)")
    return problemas


def _listar_por_modulo():
    por_modulo = {}
    for nome, entry in TOOL_REGISTRY.items():
        modulo = getattr(entry["handler"], "__module__", "?").rsplit(".", 1)[-1]
        por_modulo.setdefault(modulo, []).append(nome)
    return [
        f"  {modulo} ({len(por_modulo[modulo])}): " + ", ".join(sorted(por_modulo[modulo]))
        for modulo in sorted(por_modulo)
    ]


def _contrato_da_ferramenta(nome):
    """O contrato EXATO de uma ferramenta, lido do registo vivo.

    Recorrer a isto custa uma chamada; procurar o modulo no projeto para lembrar
    o nome de um parametro custa uma busca a varrer dezenas de ficheiros (e foi
    assim que se perdeu uma rodada a tentar lembrar-se de 'espera' dentro de
    'passos'). Diz o que o modelo realmente recebe, nao o que o ficheiro parece
    dizer: e a declaracao do registo que decide.
    """
    chave = (nome or "").strip()
    entry = TOOL_REGISTRY.get(chave)
    if entry is None:
        return [
            f"ERRO: nao ha ferramenta '{chave}' neste registo.",
            "Veja os nomes com tool_verificar_ferramentas(detalhado=true) ou procure por assunto com tool_buscar_codigo.",
        ]
    handler = entry["handler"]
    onde = getattr(handler, "__module__", "?")
    try:
        ficheiro = inspect.getsourcefile(handler) or ""
        if ficheiro:
            onde = f"{os.path.relpath(ficheiro, APP_ROOT)}:{inspect.getsourcelines(handler)[1]}"
    except (OSError, TypeError):
        pass
    linhas = [
        f"{chave}  ({onde})",
        f"  disponibilidade: {entry['disponivel']}",
        f"  descricao: {entry['descricao']}",
    ]
    params = entry["params"] or {}
    if not params:
        linhas.append("  parametros: nenhum")
        return linhas
    linhas.append(f"  parametros ({len(params)}):")
    for pnome, meta in params.items():
        tipos = meta.get("tipo") or "STRING"
        if meta.get("enum"):
            tipos += " -> " + " | ".join(str(v) for v in meta["enum"])
        padrao = meta.get("padrao")
        if callable(padrao):
            padrao = "(calculado)"
        marca = "OBRIGATORIO" if meta.get("obrig") else f"opcional, padrao={padrao!r}"
        linhas.append(f"    {pnome} [{tipos}] ({marca})")
        if meta.get("desc"):
            linhas.append(f"      {meta['desc']}")
    return linhas


@register(
    "tool_verificar_ferramentas",
    "Checkup do proprio registo de ferramentas (use logo depois de reiniciar o backend): confirma que todos os modulos com @register estao a ser importados pelo loop, que a assinatura de cada handler casa com o esquema declarado, que as declaracoes enviadas ao modelo saem coerentes e prova o mecanismo de despacho com uma sonda pura. Nao escreve nada nem chama ferramentas reais. Com 'ferramenta', mostra o CONTRATO de uma so (descricao, cada parametro com tipo, obrigatoriedade e padrao, e o ficheiro:linha onde vive) - use em vez de procurar o modulo no projeto para lembrar-se de um parametro.",
    {
        "detalhado": {
            "tipo": "BOOLEAN",
            "desc": "True lista as ferramentas agrupadas por modulo",
            "obrig": False,
            "padrao": False,
        },
        "ferramenta": {
            "tipo": "STRING",
            "desc": "Nome de UMA ferramenta (ex: 'tool_operar_preview') para ver o contrato dela em detalhe, em vez do checkup geral.",
            "obrig": False,
            "padrao": "",
        },
    },
)
def tool_verificar_ferramentas(detalhado=False, ferramenta=""):
    if (ferramenta or "").strip():
        emit_event("executing", function=f"Lendo o contrato de {(ferramenta or '').strip()}")
        return "\n".join(_contrato_da_ferramenta(ferramenta))
    emit_event("executing", function="Verificando o registo de ferramentas")
    modulos, problemas = _problemas_modulos()
    problemas.extend(_problemas_carregamento(modulos))
    editados = _arquivos_editados_desde_o_arranque()
    if editados:
        problemas.append(
            f"{len(editados)} ficheiro(s) .py editados depois do arranque deste processo "
            f"(mais recente: {editados[0]}) - ainda nao carregados"
        )
    problemas.extend(_problemas_estrutura())
    decls, erro_decl = _declaracoes()
    if erro_decl:
        problemas.append(erro_decl)
    problemas.extend(_problemas_declaracoes(decls))
    problemas.extend(_problemas_despacho())
    colisoes = collisions()
    for nome, antes, depois in colisoes:
        problemas.append(f"{nome}: registado por dois handlers ({antes} e {depois})")

    linhas = [
        f"Ferramentas registadas: {len(TOOL_REGISTRY)}",
        f"Modulos de tools/ com @register: {len(modulos)}",
        f"Modulos de tools/ carregados neste processo: {len(_modulos_carregados())}",
        f"Ficheiros .py editados desde o arranque do processo: {len(editados)}",
        "Declaracoes para o modelo (todos os escopos): " + (str(len(decls)) if decls else "indisponivel"),
        f"Colisoes de nome no registo: {len(colisoes)}",
        "Sonda de despacho (resolucao de argumentos): executada",
    ]
    if detalhado:
        linhas.append("")
        linhas.extend(_listar_por_modulo())
    linhas.append("")
    if problemas:
        linhas.append(f"FALHAS ({len(problemas)}):")
        linhas.extend(f"  - {p}" for p in problemas)
        linhas.append("")
        linhas.append(
            f"VEREDITO: {len(problemas)} PROBLEMA(S) no registo ou no carregamento do processo."
        )
    else:
        linhas.append("VEREDITO: REGISTO SAUDAVEL (estrutura, assinaturas, declaracoes e despacho).")
    return "\n".join(linhas)
