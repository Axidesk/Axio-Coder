import os
import struct

from src.backend.services.file_service import resolver_caminho
from src.backend.state import emit_event
from src.backend.tools.registry import register

NODE_START = 0xFE
NODE_END = 0xFF
ESCAPE = 0xFD

TIPO_TILE_AREA = 4
TIPO_TILE = 5
TIPO_HOUSE_TILE = 14

ATTR_FLAGS = 3
ATTR_ACAO = 4
ATTR_UNICO = 5
ATTR_TELEPORTE = 8
ATTR_CHAO = 9

LADO_DA_AREA = 256
LIMITE_VAZIOS = 200
LIMITE_ITENS = 20

_CACHE_DE_BYTES = {}
_CACHE_DE_AREAS = {}


@register(
    "tool_medir_mapa_otbm",
    "Le um mapa de Tibia no formato OTBM (.otbm) e responde por MEDICAO, sem o abrir no editor. "
    "'ponto' diz o que existe numa coordenada: se ha tile, qual o chao e que itens estao em cima, "
    "com action id, unique id e destino de teleporte. 'vazios' lista os tiles sem chao NENHUM - os "
    "que fazem um monstro ou um NPC nascer sobre o nada. 'resumo' conta os tiles do mapa e da a caixa "
    "onde existe chao. A armadilha que este leitor ja resolve: um tile COM chao pode nao ter o "
    "atributo 9 - quando o chao tem atributos (um dirt com action id, por exemplo), o editor grava-o "
    "como no filho. Logo, tile sem atributo 9 mas com filho NAO e tile vazio; vazio e so o que nao "
    "tem chao nem filho. Um mapa grande (88 MB, ~10 milhoes de tiles) faz 'ponto' responder na hora, "
    "mas 'resumo' e 'vazios' leem o mapa inteiro. Varrer a vizinhanca de um ponto nao se faz com uma "
    "chamada por coordenada: passa-se a lista inteira em 'pontos' (uma por linha, x,y,z) - a primeira "
    "leitura paga o custo, as seguintes saem do cache e milhares de coordenadas custam o mesmo que uma.",
    {
        "caminho_relativo": {
            "tipo": "STRING",
            "desc": "Arquivo do mapa (.otbm), dentro do projeto.",
            "obrig": True,
            "padrao": "",
        },
        "acao": {
            "tipo": "STRING",
            "desc": "'ponto' (o tile de x,y,z), 'vazios' (tiles sem chao nem item) ou 'resumo' (contagens do mapa inteiro).",
            "padrao": "ponto",
        },
        "x": {
            "tipo": "INTEGER",
            "desc": "Coordenada x para 'ponto'.",
            "padrao": 0,
        },
        "y": {
            "tipo": "INTEGER",
            "desc": "Coordenada y para 'ponto'.",
            "padrao": 0,
        },
        "z": {
            "tipo": "INTEGER",
            "desc": "Andar para 'ponto'.",
            "padrao": 0,
        },
        "pontos": {
            "tipo": "STRING",
            "desc": "Varias coordenadas numa so chamada para 'ponto', uma por linha no formato x,y,z - poupa uma chamada por coordenada.",
            "padrao": "",
        },
        "limite": {
            "tipo": "INTEGER",
            "desc": "Quantos tiles sem chao listar em 'vazios'.",
            "padrao": LIMITE_VAZIOS,
        },
    },
)
def tool_medir_mapa_otbm(caminho_relativo, acao="ponto", x=0, y=0, z=0, limite=LIMITE_VAZIOS, pontos=""):
    emit_event("executing", function=f"Medindo mapa OTBM: {caminho_relativo}")
    alvo, erro = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro:
        return erro
    if not os.path.isfile(alvo):
        return f"ERRO: arquivo nao encontrado: {caminho_relativo}"
    try:
        dados = _bytes_do_mapa(alvo)
    except OSError as falha:
        return f"ERRO: nao consegui ler '{caminho_relativo}' ({falha})."
    if len(dados) < 8:
        return f"ERRO: '{caminho_relativo}' e pequeno demais para ser um mapa OTBM."
    if dados[0] != NODE_START and not (dados[:4] == bytes(4) and dados[4] == NODE_START):
        return (
            f"ERRO: '{caminho_relativo}' nao comeca com o cabecalho de um mapa OTBM "
            "(4 bytes zerados e o no, ou o no direto na primeira posicao)."
        )

    escolha = str(acao or "ponto").strip().lower()
    try:
        if escolha == "ponto":
            lista = _pontos_pedidos(pontos, x, y, z)
            if not lista:
                return "ERRO: nenhuma coordenada valida em 'pontos' (escreve x,y,z por linha)."
            relatos = [_relato_ponto(dados, caminho_relativo, px, py, pz) for px, py, pz in lista]
            return relatos[0] if len(relatos) == 1 else "\n".join(relatos)
        if escolha == "vazios":
            return _relato_vazios(dados, caminho_relativo, _teto(limite))
        if escolha == "resumo":
            return _relato_resumo(dados, caminho_relativo)
    except ValueError as falha:
        return f"ERRO: o mapa '{caminho_relativo}' tem um no sem fecho ({falha})."
    return f"ERRO: acao desconhecida '{acao}' (usa 'ponto', 'vazios' ou 'resumo')."


def _bytes_do_mapa(alvo):
    marca = os.path.getmtime(alvo), os.path.getsize(alvo)
    guardado = _CACHE_DE_BYTES.get(alvo)
    if guardado is not None and guardado[0] == marca:
        return guardado[1]
    with open(alvo, "rb") as arquivo:
        dados = arquivo.read()
    _CACHE_DE_BYTES.clear()
    _CACHE_DE_BYTES[alvo] = (marca, dados)
    return dados


def _pontos_pedidos(pontos, x, y, z):
    if not str(pontos or "").strip():
        return [(int(x), int(y), int(z))]
    lista = []
    for linha in str(pontos).splitlines():
        campos = [c.strip() for c in linha.replace(";", ",").split(",") if c.strip()]
        if len(campos) != 3:
            continue
        try:
            lista.append(tuple(int(c) for c in campos))
        except ValueError:
            continue
    return lista


def _relato_ponto(dados, rotulo, x, y, z):
    for base, inicio in _areas(dados):
        x0, y0, z0 = base
        if z0 != z or not (x0 <= x < x0 + LADO_DA_AREA and y0 <= y < y0 + LADO_DA_AREA):
            continue
        indice = inicio
        while dados[indice] == NODE_START:
            tile = _tile(dados, indice, base)
            if tile["x"] == x and tile["y"] == y:
                return "\n".join(_linhas_do_tile(rotulo, tile))
            indice = tile["fim"]
    return (
        f"MAPA '{rotulo}': nao existe tile em {x}, {y}, {z}.\n"
        "Um ponto sem tile nenhum e o que faz a criatura nascer sobre o nada."
    )


def _relato_vazios(dados, rotulo, limite):
    total = 0
    caixa = [None, None, None, None]
    listados = []
    for x, y, z, tem_chao, tem_filho, _ in _tiles(dados):
        if tem_chao:
            _esticar(caixa, x, y)
            continue
        if tem_filho:
            continue
        total += 1
        if len(listados) < limite:
            listados.append((x, y, z))
    if caixa[0] is None:
        return (
            f"MAPA '{rotulo}': {total} tile(s) sem chao nenhum e sem item.\n"
            "Nenhum tile deste mapa tem o atributo de chao - a caixa do chao nao pode ser medida."
        )
    dentro = sum(1 for x, y, _ in listados if caixa[0] <= x <= caixa[1] and caixa[2] <= y <= caixa[3])
    fora = len(listados) - dentro
    linhas = [
        f"MAPA '{rotulo}': {total} tile(s) sem chao nenhum (sem atributo de chao e sem item filho).",
        f"CAIXA DO CHAO: x {caixa[0]}..{caixa[1]}, y {caixa[2]}..{caixa[3]} - fora dela nao existe chao.",
    ]
    if listados:
        linhas.append(f"NA LISTA ({len(listados)} de {total}): {dentro} dentro da caixa, {fora} fora.")
        linhas.append("POSICOES:")
        linhas += [f"  {x}, {y}, {z}" for x, y, z in listados]
    return "\n".join(linhas)


def _relato_resumo(dados, rotulo):
    total = 0
    com_chao = 0
    com_filho = 0
    vazios = []
    caixa = [None, None, None, None]
    for x, y, z, tem_chao, tem_filho, _ in _tiles(dados):
        total += 1
        if tem_chao:
            com_chao += 1
            _esticar(caixa, x, y)
            continue
        if tem_filho:
            com_filho += 1
            continue
        vazios.append((x, y, z))
    if caixa[0] is None:
        return f"MAPA '{rotulo}': {total} tiles, nenhum com atributo de chao."
    dentro = sum(1 for x, y, _ in vazios if caixa[0] <= x <= caixa[1] and caixa[2] <= y <= caixa[3])
    return "\n".join(
        [
            f"MAPA '{rotulo}': {total} tiles.",
            f"  com chao no atributo 9: {com_chao}",
            f"  sem atributo 9 mas com itens (inclui chao com atributos): {com_filho}",
            f"  sem chao nenhum e sem item: {len(vazios)} ({dentro} dentro da caixa do chao, {len(vazios) - dentro} fora)",
            f"CAIXA DO CHAO: x {caixa[0]}..{caixa[1]}, y {caixa[2]}..{caixa[3]}",
        ]
    )


def _tiles(dados):
    for base, inicio in _areas(dados):
        indice = inicio
        while dados[indice] == NODE_START:
            x, y, z, tem_chao, tem_filho, seguinte = _tile_curto(dados, indice, base)
            yield x, y, z, tem_chao, tem_filho, seguinte
            indice = seguinte


def _tile(dados, i, base):
    tipo = dados[i + 1]
    props, marcador = _ate_marcador(dados, i + 2)
    limpos = _sem_escape(props)
    casa = None
    if tipo == TIPO_HOUSE_TILE and len(limpos) >= 6:
        deslocamento = (limpos[0], limpos[1])
        casa = struct.unpack_from("<I", limpos, 2)[0]
        atributos = _atributos(limpos, 6)
    else:
        deslocamento = (limpos[0], limpos[1]) if len(limpos) >= 2 else (0, 0)
        atributos = _atributos(limpos, 2)
    itens = []
    indice = marcador
    while dados[indice] == NODE_START:
        item_props, _ = _ate_marcador(dados, indice + 2)
        itens.append(_item(_sem_escape(item_props)))
        indice = _fim_do_no(dados, indice)
    return {
        "x": base[0] + deslocamento[0],
        "y": base[1] + deslocamento[1],
        "z": base[2],
        "casa": casa,
        "atributos": atributos,
        "itens": itens,
        "fim": indice + 1,
    }


def _tile_curto(dados, i, base):
    tipo = dados[i + 1]
    props, marcador = _ate_marcador(dados, i + 2)
    limpos = _sem_escape(props)
    deslocamento = (limpos[0], limpos[1]) if len(limpos) >= 2 else (0, 0)
    inicio = 6 if tipo == TIPO_HOUSE_TILE else 2
    tem_chao = _tem_atributo(limpos, inicio, ATTR_CHAO)
    indice = marcador
    tem_filho = dados[indice] == NODE_START
    while dados[indice] == NODE_START:
        indice = _fim_do_no(dados, indice)
    return base[0] + deslocamento[0], base[1] + deslocamento[1], base[2], tem_chao, tem_filho, indice + 1


def _item(limpos):
    if len(limpos) < 2:
        return {"id": None, "bruto": limpos.hex()}
    info = {"id": struct.unpack_from("<H", limpos, 0)[0]}
    info.update(_atributos(limpos, 2))
    return info


def _tem_atributo(limpos, i, alvo):
    tamanho = len(limpos)
    while i < tamanho:
        chave = limpos[i]
        i += 1
        if chave == ATTR_FLAGS and i + 4 <= tamanho:
            i += 4
            continue
        if chave == ATTR_CHAO and i + 2 <= tamanho:
            if chave == alvo:
                return True
            i += 2
            continue
        return False
    return False


def _atributos(limpos, i):
    achados = {}
    tamanho = len(limpos)
    while i < tamanho:
        chave = limpos[i]
        i += 1
        if chave == ATTR_FLAGS and i + 4 <= tamanho:
            achados["flags"] = struct.unpack_from("<I", limpos, i)[0]
            i += 4
        elif chave == ATTR_ACAO and i + 2 <= tamanho:
            achados["acao"] = struct.unpack_from("<H", limpos, i)[0]
            i += 2
        elif chave == ATTR_UNICO and i + 2 <= tamanho:
            achados["unico"] = struct.unpack_from("<H", limpos, i)[0]
            i += 2
        elif chave == ATTR_TELEPORTE and i + 5 <= tamanho:
            achados["teleporte"] = struct.unpack_from("<HHB", limpos, i)
            i += 5
        elif chave == ATTR_CHAO and i + 2 <= tamanho:
            achados["chao"] = struct.unpack_from("<H", limpos, i)[0]
            i += 2
        else:
            achados["resto"] = limpos[i - 1 :].hex()
            break
    return achados


def _areas(dados):
    guardado = _CACHE_DE_AREAS.get(id(dados))
    if guardado is not None and guardado[0] is dados:
        return guardado[1]
    lista = list(_areas_do_ficheiro(dados))
    _CACHE_DE_AREAS.clear()
    _CACHE_DE_AREAS[id(dados)] = (dados, lista)
    return lista


def _areas_do_ficheiro(dados):
    alvo = bytes((NODE_START, TIPO_TILE_AREA))
    procura = 0
    while True:
        posicao = dados.find(alvo, procura)
        if posicao < 0:
            return
        procura = posicao + 1
        if not _eh_marcador(dados, posicao):
            continue
        props, marcador = _ate_marcador(dados, posicao + 2)
        limpos = _sem_escape(props)
        if len(limpos) < 5:
            continue
        base = (struct.unpack_from("<H", limpos, 0)[0], struct.unpack_from("<H", limpos, 2)[0], limpos[4])
        yield base, marcador


def _eh_marcador(dados, posicao):
    corrida = 0
    i = posicao - 1
    while i >= 0 and dados[i] == ESCAPE:
        corrida += 1
        i -= 1
    return corrida % 2 == 0


def _ate_marcador(dados, i):
    inicio = i
    tamanho = len(dados)
    while i < tamanho:
        byte = dados[i]
        if byte == ESCAPE:
            i += 2
            continue
        if byte == NODE_START or byte == NODE_END:
            return dados[inicio:i], i
        i += 1
    raise ValueError("propriedades sem marcador de fim")


def _fim_do_no(dados, i):
    profundidade = 0
    tamanho = len(dados)
    while i < tamanho:
        byte = dados[i]
        if byte == ESCAPE:
            i += 2
            continue
        if byte == NODE_START:
            profundidade += 1
            i += 1
            continue
        if byte == NODE_END:
            profundidade -= 1
            i += 1
            if profundidade == 0:
                return i
            continue
        i += 1
    raise ValueError("no sem fecho")


def _sem_escape(bruto):
    saida = bytearray()
    i = 0
    tamanho = len(bruto)
    while i < tamanho:
        byte = bruto[i]
        if byte == ESCAPE:
            if i + 1 < tamanho:
                saida.append(bruto[i + 1])
            i += 2
            continue
        saida.append(byte)
        i += 1
    return bytes(saida)


def _esticar(caixa, x, y):
    if caixa[0] is None or x < caixa[0]:
        caixa[0] = x
    if caixa[1] is None or x > caixa[1]:
        caixa[1] = x
    if caixa[2] is None or y < caixa[2]:
        caixa[2] = y
    if caixa[3] is None or y > caixa[3]:
        caixa[3] = y


def _linhas_do_tile(rotulo, tile):
    atributos = tile["atributos"]
    itens = tile["itens"]
    titulo = f"MAPA '{rotulo}': tile em {tile['x']}, {tile['y']}, {tile['z']}"
    if tile["casa"] is not None:
        titulo += f" (casa {tile['casa']})"
    linhas = [titulo]
    chao = atributos.get("chao")
    if chao is not None:
        linhas.append(f"  chao: item {chao} (atributo 9)")
    elif itens:
        linhas.append(
            f"  chao: nao esta no atributo 9 - o primeiro filho e o item {itens[0].get('id')} "
            "(chao com atributos, gravado como filho)"
        )
    else:
        linhas.append("  chao: NENHUM e nenhum item - tile vazio, a criatura aqui nasce sobre o nada")
    if "flags" in atributos:
        linhas.append(f"  flags: {atributos['flags']}")
    if "resto" in atributos:
        linhas.append(f"  atributos nao lidos: {atributos['resto']}")
    if itens:
        linhas.append(f"  itens ({len(itens)}):")
        for item in itens[:LIMITE_ITENS]:
            linhas.append("    " + _linha_do_item(item))
        if len(itens) > LIMITE_ITENS:
            linhas.append(f"    ... e mais {len(itens) - LIMITE_ITENS}")
    return linhas


def _linha_do_item(info):
    partes = [f"item {info.get('id')}"]
    if "acao" in info:
        partes.append(f"action id {info['acao']}")
    if "unico" in info:
        partes.append(f"unique id {info['unico']}")
    if "teleporte" in info:
        destino = info["teleporte"]
        partes.append(f"teleporte para {destino[0]}, {destino[1]}, {destino[2]}")
    if "resto" in info:
        partes.append(f"resto {info['resto']}")
    return " | ".join(partes)


def _teto(valor, maximo=1000, padrao=LIMITE_VAZIOS):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return padrao
    return max(1, min(maximo, numero))
