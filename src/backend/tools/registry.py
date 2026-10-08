"""Registro central das ferramentas do agente (padrao Registry / Open-Closed).

Cada tool declara-se junto do proprio codigo, no modulo onde vive:

    @register(
        "tool_ler_arquivo",
        "Le o conteudo completo do arquivo.",
        {"caminho_relativo": {"tipo": "STRING", "obrig": True, "padrao": ""}},
    )
    def tool_ler_arquivo(caminho_relativo):
        ...

O decorador guarda handler + descricao + esquema em TOOL_REGISTRY, e dai saem as
duas pontas que antes viviam (e se desalinhavam) dentro do ai/loop.py:

  * build_function_declarations(types, ...) - a lista de FunctionDeclaration que o
    modelo ve, ja filtrada pela disponibilidade de cada tool;
  * dispatch(nome, args) - chama o handler com os parametros declarados, aplicando
    o 'padrao' de cada um quando o modelo o omite.

Chaves de cada parametro:
  tipo   -> STRING | INTEGER | NUMBER | BOOLEAN (coage o valor antes de chamar)
  desc   -> descricao mostrada ao modelo (opcional)
  enum   -> valores aceitos (opcional)
  obrig  -> entra no 'required' do esquema
  padrao -> valor, ou callable(args), usado quando o modelo omite o parametro

Disponibilidade ('disponivel'):
  sempre | edicao (todas as de edicao: modo != 'guided') | semi (so no modo
  semi-automatico) | web (exige Tavily configurada e DeepSeek).

Adicionar uma ferramenta passou a ser: 1 funcao no modulo dela + este decorador
acima dela.
"""
import difflib
import importlib
import threading
import time

from src.backend.services.transferencia import duracao_texto
from src.backend.state import emit_event, set_turn_id, turn_id_atual

TOOL_REGISTRY = {}

_DISPONIBILIDADES = ("sempre", "edicao", "semi", "web", "computer")

_VIGIA_SEGUNDOS = 15
_VIGIA_AVISO = 120

_COLISOES = []


def _origem(fn):
    return f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__qualname__', '?')}"


def register(nome, descricao, params=None, disponivel="sempre"):
    """Registra a ferramenta decorada. `params` None = declaracao sem parametros."""
    if disponivel not in _DISPONIBILIDADES:
        raise ValueError(f"disponibilidade invalida: {disponivel!r} (use {_DISPONIBILIDADES})")

    def decorator(fn):
        anterior = TOOL_REGISTRY.get(nome)
        if anterior is not None and anterior["handler"] is not fn:
            _COLISOES.append((nome, _origem(anterior["handler"]), _origem(fn)))
        TOOL_REGISTRY[nome] = {
            "handler": fn,
            "descricao": descricao,
            "params": params,
            "disponivel": disponivel,
        }
        return fn

    return decorator


def tool_names():
    return list(TOOL_REGISTRY.keys())


def collisions():
    """Nomes registados por dois handlers diferentes (o segundo sobrescreveu o primeiro)."""
    return list(_COLISOES)


def _disponivel_agora(disponivel, modo, use_deepseek, web_ok, ai_model):
    if disponivel == "sempre":
        return True
    if disponivel == "edicao":
        return modo != "guided"
    if disponivel == "semi":
        return modo == "semi"
    if disponivel == "computer":
        return bool(not use_deepseek and ai_model == "gemini-flash")
    return bool(use_deepseek and web_ok)


def _esquema_parametro(types, meta):
    campos = {"type": getattr(types.Type, meta.get("tipo") or "STRING")}
    if meta.get("desc"):
        campos["description"] = meta["desc"]
    if meta.get("enum"):
        campos["enum"] = list(meta["enum"])
    return types.Schema(**campos)


def build_function_declarations(types, modo="auto", use_deepseek=False, web_ok=False, ai_model="gemini"):
    """Declaracoes para o SDK, na ordem de registo, filtradas pela disponibilidade."""
    decls = []
    for nome, entry in TOOL_REGISTRY.items():
        if not _disponivel_agora(entry["disponivel"], modo, use_deepseek, web_ok, ai_model):
            continue
        params = entry["params"]
        if params is None:
            decls.append(types.FunctionDeclaration(name=nome, description=entry["descricao"]))
            continue
        propriedades = {
            pnome: _esquema_parametro(types, pmeta) for pnome, pmeta in params.items()
        }
        obrigatorios = [pnome for pnome, pmeta in params.items() if pmeta.get("obrig")]
        decls.append(
            types.FunctionDeclaration(
                name=nome,
                description=entry["descricao"],
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties=propriedades,
                    required=obrigatorios,
                ),
            )
        )
    return decls


def _coagir(tipo, valor):
    if valor is None:
        return None
    if tipo == "BOOLEAN":
        if isinstance(valor, bool):
            return valor
        return str(valor).strip().lower() in ("true", "1", "sim", "yes")
    if tipo in ("INTEGER", "NUMBER"):
        try:
            return int(valor) if tipo == "INTEGER" else float(valor)
        except (TypeError, ValueError):
            return valor
    return valor if isinstance(valor, str) else str(valor)


def resolver_kwargs(params, args):
    """kwargs finais de uma chamada: valor do modelo ou o 'padrao', ja coagido.

    Puro (nao toca no registo) para poder ser provado sem despachar nada.
    """
    kwargs = {}
    for pnome, pmeta in (params or {}).items():
        padrao = pmeta.get("padrao")
        if pnome in args:
            valor = args[pnome]
        elif callable(padrao):
            valor = padrao(args)
        else:
            valor = padrao
        kwargs[pnome] = _coagir(pmeta.get("tipo"), valor)
    return kwargs


def argumentos_desconhecidos(params, args):
    """Nomes recebidos que o esquema nao declara, cada um com o parente mais proximo."""
    conhecidos = list((params or {}).keys())
    estranhos = []
    for nome in (args or {}):
        if nome in conhecidos:
            continue
        proximo = difflib.get_close_matches(nome, conhecidos, n=1)
        estranhos.append((nome, proximo[0] if proximo else None))
    return estranhos


def _aviso_dos_desconhecidos(params, args):
    estranhos = argumentos_desconhecidos(params, args)
    if not estranhos:
        return ""
    conhecidos = list((params or {}).keys())
    lista = ", ".join(conhecidos[:10]) + ("..." if len(conhecidos) > 10 else "")
    partes = [
        f"'{nome}'" + (f" (querias '{proximo}'?)" if proximo else "")
        for nome, proximo in estranhos
    ]
    return (
        "[AVISO] A ferramenta nao aceita "
        + ", ".join(partes)
        + f". Aceita: {lista}."
    )


def dispatch(nome, args):
    """Chama o handler registado. Devolve (resultado, conhecida)."""
    entry = TOOL_REGISTRY.get(nome)
    if entry is None:
        return None, False
    resultado = _com_vigia(nome, entry["handler"], resolver_kwargs(entry["params"], args or {}))
    aviso = _aviso_dos_desconhecidos(entry["params"], args or {})
    if aviso and isinstance(resultado, str):
        resultado = f"{aviso}\n\n{resultado}"
    return resultado, True


def _com_vigia(nome, handler, kwargs):
    """Corre a ferramenta com um vigia que republica o tempo decorrido na barra.

    Uma ferramenta pesada corre na linha do turno e nao devolve nada enquanto trabalha:
    sem isto a barra fica presa na frase do inicio e o turno parece congelado. O vigia
    nao interrompe a ferramenta - diz quanto tempo ela ja leva e, passado o aviso, que o
    turno pode ser parado.
    """
    parar = threading.Event()
    turno = turn_id_atual()
    inicio = time.monotonic()

    def bater():
        set_turn_id(turno)
        while not parar.wait(_VIGIA_SEGUNDOS):
            segundos = time.monotonic() - inicio
            recado = f"{nome}: ainda a trabalhar ({duracao_texto(segundos)})"
            if segundos >= _VIGIA_AVISO:
                recado += " - se nao valer a pena esperar, pare o turno"
            emit_event("executing", function=recado)

    vigia = threading.Thread(target=bater, daemon=True, name=f"vigia-{nome}")
    vigia.start()
    try:
        return handler(**kwargs)
    finally:
        parar.set()


def carregar_ferramentas_em_segundo_plano(porta=5000):
    """Importa o motor da IA - que arrasta o registo inteiro de ferramentas - so depois de o
    servidor atender. Sao ~550 modulos e ~1s de importacao que nao tem de atrasar a janela:
    quem despacha uma ferramenta e o proprio motor, logo o registo esta completo quando ele
    corre, e o primeiro turno nao paga a espera."""
    from src.backend.services.aquecimento import depois_do_arranque  # import-local: o registo nao pode depender de services no arranque

    def carregar():
        importlib.import_module("src.backend.ai.loop")

    return depois_do_arranque(porta, carregar, nome="ferramentas")
