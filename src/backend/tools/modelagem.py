import os
from dataclasses import replace

from src.backend.geometry.catalogo import (
    MODELOS,
    PASTA_PADRAO,
    carregar,
    destino_padrao,
    nomes,
    pasta_existe,
)
from src.backend.geometry.exportador_ifc import escrever_ifc
from src.backend.geometry.exportador_step import (
    escrever_step,
    medir_step,
    motivo_de_recusa,
)
from src.backend.geometry.montagem import medir_ifc
from src.backend.geometry.montagem import validar as validar_ifc
from src.backend.services.file_service import resolver_caminho
from src.backend.state import emit_event
from src.backend.tools.registry import register

EXPORTADORES = {
    "ifc": {
        "extensao": ".ifc",
        "escrever": escrever_ifc,
        "medir": medir_ifc,
        "validar": validar_ifc,
        "abre_em": "Archicad, Revit, SketchUp Pro, Blender",
    },
    "step": {
        "extensao": ".step",
        "escrever": escrever_step,
        "medir": medir_step,
        "recusa": motivo_de_recusa,
        "abre_em": "SolidWorks, CATIA, NX, Inventor, FreeCAD",
    },
}

NOTA_VALIDADOR_OFICIAL = (
    "  schema conferido aqui; o buildingSMART publica validador oficial gratuito "
    "(STEP, schema e bSDD) em validate.buildingsmart.org"
)


@register(
    "tool_gerar_modelo",
    "Gera um modelo parametrico do catalogo do projeto e grava-o nos formatos pedidos, medindo cada ficheiro depois de o ler de volta. SEM 'modelo' devolve o catalogo: os modelos disponiveis, as variantes de cada um e todos os parametros com o valor de partida. COM 'modelo' aceita ajustes pontuais em 'parametros' (ex: 'altura_total=32; numero_costelas=24') e devolve, por familia de peca, o volume PREVISTO pela formula e o LIDO de volta do ficheiro gravado - a diferenca entre os dois e a prova de que a geometria saiu certa. 'nivel' escolhe o detalhe: 'estrutural' (o esqueleto que suporta carga e giro, para calculo) ou 'completo' (com pele e estrela, para o modelo visivel). Sem 'destino' grava em gerados/<modelo>/<modelo>.<formato>, criando a pasta se faltar - cada modelo gera dentro da sua propria pasta.",
    {
        "modelo": {"tipo": "STRING", "padrao": "", "desc": "Modelo do catalogo (ex: arvore). Vazio = lista o catalogo inteiro."},
        "destino": {"tipo": "STRING", "padrao": "", "desc": "Caminho relativo a gravar, sem extensao ou com ela (ex: gerados/arvore/arvore_30m.ifc). Passar uma pasta existente usa o nome do modelo como ficheiro. Vazio = gerados/<modelo>/<modelo>, com a pasta criada se faltar."},
        "formatos": {"tipo": "STRING", "padrao": "ifc", "desc": "Formatos separados por virgula: ifc, step ou ifc,step"},
        "variante": {"tipo": "STRING", "padrao": "", "desc": "Variante do modelo. Vazio = a de partida."},
        "parametros": {"tipo": "STRING", "padrao": "", "desc": "Ajustes 'nome=valor' separados por ';' (ex: 'nivel=estrutural; dentes_coroa=0')"},
    },
)
def tool_gerar_modelo(modelo="", destino="", formatos="ifc", variante="", parametros=""):
    falhas = _garantir_modelos()
    if not modelo:
        return _catalogo(falhas)
    ficha = MODELOS.get(modelo)
    if ficha is None:
        return f"ERRO: modelo '{modelo}' nao existe. Disponiveis: {', '.join(nomes())}"
    alvo, erro = resolver_caminho(
        destino or destino_padrao(modelo), permitir_extra=False, permitir_escrita=True
    )
    if erro:
        return erro if erro.startswith("ERRO") else f"ERRO: {erro}"
    alvo = _alvo_em_pasta(alvo, modelo, destino)
    os.makedirs(os.path.dirname(alvo), exist_ok=True)
    pedidos = _formatos_pedidos(formatos)
    if not pedidos:
        return f"ERRO: nenhum formato conhecido em '{formatos}'. Use: {', '.join(EXPORTADORES)}"
    try:
        escolhidos = _montar_parametros(ficha, variante, parametros)
    except ValueError as falha:
        return f"ERRO: {falha}"
    emit_event("executing", function=f"Gerando {modelo} ({escolhidos.nivel}) em {', '.join(pedidos)}")
    try:
        desenhado = ficha["construtor"](escolhidos)
    except (ValueError, KeyError) as falha:
        return f"ERRO: {modelo} recusou os parametros: {falha}"
    linhas = _cabecalho(modelo, ficha, escolhidos, len(desenhado.pecas))
    for formato in pedidos:
        dados = EXPORTADORES[formato]
        recusa = dados["recusa"](desenhado) if "recusa" in dados else ""
        if recusa:
            linhas.extend([f"[{formato.upper()}] nao gerado: {recusa}", ""])
            continue
        caminho = os.path.splitext(alvo)[0] + dados["extensao"]
        dados["escrever"](caminho, desenhado)
        linhas.extend(_relatorio_formato(formato, dados, caminho, desenhado))
    return "\n".join(linhas)


_falhas_de_modelos = []


def _garantir_modelos():
    """Carrega as pastas de modelo do projeto; guarda as falhas de importacao."""
    global _falhas_de_modelos
    if not MODELOS and not _falhas_de_modelos:
        _, _falhas_de_modelos = carregar()
    return _falhas_de_modelos


def _catalogo(falhas=()):
    linhas = ["MODELOS DISPONIVEIS", ""]
    if not MODELOS:
        if pasta_existe():
            linhas.extend([f"Nenhum modelo registado: nao ha subpasta com modelo.py em {PASTA_PADRAO}/.", ""])
        else:
            linhas.extend([f"Nao existe a pasta {PASTA_PADRAO}/ neste projeto - nenhum modelo registado.", ""])
    for chave in nomes():
        ficha = MODELOS[chave]
        partida = ficha["variantes"].get("base") or ficha["parametros"]()
        linhas.append(f"[{chave}] {ficha['descricao']}")
        if ficha.get("custo"):
            linhas.append(f"  custo medido: {ficha['custo']}")
        if ficha["variantes"]:
            linhas.append(f"  variantes: {', '.join(ficha['variantes'])}")
        linhas.append("  parametros (valor de partida):")
        for campo in ficha["parametros"].__dataclass_fields__:
            linhas.append(f"    {campo}={getattr(partida, campo)!r}")
        linhas.append("")
    linhas.append(f"Formatos: {', '.join(EXPORTADORES)}")
    for chave, dados in EXPORTADORES.items():
        linhas.append(f"  {chave:5s} -> abre em: {dados['abre_em']}")
    if falhas:
        linhas.append("")
        linhas.append("Pastas de modelo nao carregadas:")
        linhas.extend(f"  {falha}" for falha in falhas)
    return "\n".join(linhas)


def _alvo_em_pasta(alvo, modelo, indicado=""):
    if indicado.endswith(("/", "\\")) or os.path.isdir(alvo):
        return os.path.join(alvo, modelo)
    return alvo


def _montar_parametros(ficha, variante, texto):
    escolhidos = ficha["variantes"] or {}
    base = escolhidos.get(variante) if variante else None
    if variante and base is None:
        raise ValueError(f"variante '{variante}' nao existe. Disponiveis: {', '.join(escolhidos) or 'nenhuma'}")
    base = base or escolhidos.get("base") or ficha["parametros"]()
    ajustes = _ler_ajustes(ficha["parametros"], texto)
    return replace(base, **ajustes) if ajustes else base


def _ler_ajustes(classe, texto):
    if not texto or not texto.strip():
        return {}
    campos = {nome: campo.type for nome, campo in classe.__dataclass_fields__.items()}
    ajustes = {}
    for pedaco in texto.replace("\n", ";").split(";"):
        pedaco = pedaco.strip()
        if not pedaco:
            continue
        if "=" not in pedaco:
            raise ValueError(f"ajuste sem '=': '{pedaco}'. Formato: nome=valor; nome=valor")
        chave, valor = (parte.strip() for parte in pedaco.split("=", 1))
        if chave not in campos:
            raise ValueError(f"parametro desconhecido: '{chave}'. Validos: {', '.join(sorted(campos))}")
        ajustes[chave] = _converter(campos[chave], chave, valor)
    return ajustes


def _converter(tipo, chave, valor):
    try:
        if tipo is int:
            return int(float(valor))
        if tipo is float:
            return float(valor)
        if tipo is bool:
            return str(valor).strip().lower() in ("true", "1", "sim", "yes")
    except ValueError:
        raise ValueError(f"'{valor}' nao serve para '{chave}' (esperado {tipo.__name__})")
    return valor


def _formatos_pedidos(formatos):
    limpos = (formatos or "").lower().replace(" ", "").split(",")
    return [nome for nome in limpos if nome in EXPORTADORES]


def _cabecalho(modelo, ficha, escolhidos, total):
    partida = ficha["variantes"].get("base") or ficha["parametros"]()
    mudados = [
        f"{campo}={_valor(getattr(escolhidos, campo))}"
        for campo in escolhidos.__dataclass_fields__
        if getattr(escolhidos, campo) != getattr(partida, campo)
    ]
    return [
        f"MODELO '{modelo}' GERADO ({total} pecas) - nivel {escolhidos.nivel}",
        "diferencas da variante de partida: " + (" | ".join(mudados) or "nenhuma"),
        "",
    ]


def _valor(valor):
    return f"{valor:g}" if isinstance(valor, (int, float)) else str(valor)


def _relatorio_formato(formato, dados, caminho, modelo):
    previstos = modelo.volumes_previstos()
    medidos = _medir(dados, caminho, modelo.pecas)
    linhas = [
        f"[{formato.upper()}] {caminho} - abre em: {dados['abre_em']}",
        "Familia    Pecas   Volume total   Erro maximo",
    ]
    for familia, familia_dados in _por_familia(previstos, medidos).items():
        linhas.append(f"{familia:10s} {familia_dados['pecas']:5d} {familia_dados['total']:14.6f} {familia_dados['erro']:12.4f}%")
    total_previsto = sum(previstos.values())
    total_medido = sum(medidos.values())
    linhas.append(
        f"{'TOTAL':10s} {len(previstos):5d} {total_medido:14.6f} "
        f"{abs(total_medido - total_previsto) / total_previsto * 100:12.4f}%"
    )
    if dados.get("validar"):
        linhas.extend(_linhas_validacao(dados["validar"](caminho)))
    linhas.append("")
    return linhas


def _linhas_validacao(achados, limite=8):
    if not achados:
        return ["Validacao do schema IFC: sem erros nem avisos.", NOTA_VALIDADOR_OFICIAL]
    linhas = [f"Validacao do schema IFC: {len(achados)} achado(s)."]
    for item in achados[:limite]:
        local = item.get("attribute") or item.get("type") or ""
        instancia = str(item.get("instance") or "")
        if len(instancia) > 90:
            instancia = instancia[:90] + "..."
        linhas.append(f"  [{item.get('level', '?')}] {item.get('message', '')} ({local}) {instancia}")
    if len(achados) > limite:
        linhas.append(f"  ... e mais {len(achados) - limite} achado(s).")
    linhas.append(NOTA_VALIDADOR_OFICIAL)
    return linhas


def _medir(dados, caminho, pecas):
    resultado = dados["medir"](caminho)
    if isinstance(resultado, dict):
        return resultado
    if len(resultado) == len(pecas):
        return {peca.nome: volume for peca, volume in zip(pecas, resultado)}
    return {f"corpo_{indice + 1:03d}": volume for indice, volume in enumerate(resultado)}


def _por_familia(previstos, medidos):
    grupos = {}
    for nome, previsto in previstos.items():
        familia = nome.split("_")[0]
        dado = grupos.setdefault(familia, {"pecas": 0, "total": 0.0, "erro": 0.0})
        lido = medidos.get(nome)
        dado["pecas"] += 1
        dado["total"] += lido if lido is not None else 0.0
        if lido is not None and previsto:
            dado["erro"] = max(dado["erro"], abs(lido - previsto) / previsto * 100)
    return grupos
