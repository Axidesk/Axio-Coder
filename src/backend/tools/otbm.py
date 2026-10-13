import os
import re
import struct
import tempfile
import time
import xml.etree.ElementTree as ET

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
LIMITE_PORTAS = 200
TIPO_ITEM = 6
IDS_PORTA = (1223, 1225, 1241, 1243, 1255, 1257, 3542, 3551)
IDS_PORTA_NIVEL = (1227, 1229, 1245, 1247, 1259, 1261, 3540, 3549)
VOCACOES_DA_PORTA = {1: "sorcerer", 2: "druid", 3: "paladin", 4: "knight"}

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
    "leitura paga o custo, as seguintes saem do cache e milhares de coordenadas custam o mesmo que uma. "
    "'portas' lista os itens de porta (ou os ids pedidos em 'ids') dentro de 'regiao', com o action id de "
    "cada um - e como so o action id faz a porta selar e fechar depois de passar, a lista diz logo quais "
    "estao sem ele. 'spawns' le o ficheiro de spawn ao lado do mapa e conta os blocos, as criaturas, os "
    "blocos sem criatura nenhuma e as POSICOES REPETIDAS - que sao as que fazem o editor de mapa recusar a "
    "segunda e avisar 'Duplicate spawn on position', deixando um bloco grande e vazio no ecra.",
    {
        "caminho_relativo": {
            "tipo": "STRING",
            "desc": "Arquivo do mapa (.otbm), dentro do projeto.",
            "obrig": True,
            "padrao": "",
        },
        "acao": {
            "tipo": "STRING",
            "desc": "'ponto' (o tile de x,y,z), 'vazios' (tiles sem chao nem item), 'resumo' (contagens do mapa inteiro), 'portas' (itens de porta numa regiao, com o action id de cada um) ou 'spawns' (o ficheiro de spawn: blocos, criaturas e posicoes repetidas).",
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
        "ids": {
            "tipo": "STRING",
            "desc": "Para 'portas': os item ids a procurar, separados por virgula. Vazio usa as duas familias de porta: as 8 de quest (1223, 1225, 1241, 1243, 1255, 1257, 3542, 3551), em que o action id e a chave de storage da quest, e as 8 de nivel/vocacao (1227, 1229, 1245, 1247, 1259, 1261, 3540, 3549), em que o action id 1001-1999 e o nivel e o 2001-2008 a vocacao.",
            "padrao": "",
        },
        "regiao": {
            "tipo": "STRING",
            "desc": "Para 'portas': a caixa onde procurar, 'x1,y1,x2,y2' e opcionalmente o andar, 'x1,y1,x2,y2,z'. Vazio varre o mapa todo - sempre que possivel passe a caixa, que poupa a leitura das areas de fora.",
            "padrao": "",
        },
        "spawn": {
            "tipo": "STRING",
            "desc": "Para 'spawns': o ficheiro de spawn (spawn.xml do servidor). Vazio usa o 'spawn.xml' que estiver ao lado do mapa.",
            "padrao": "",
        },
        "detalhar_vazios": {
            "tipo": "BOOLEAN",
            "desc": "Para 'spawns': le o mapa inteiro (cerca de um minuto num mapa de 10 milhoes de tiles) e detalha cada bloco SEM criatura (posicao, raio, e os blocos povoados num raio de 40 no mesmo andar ou +-1) - e o que separa um bloco de lixo de um sitio de caçada - e diz quais dos blocos do ficheiro estao em posicao SEM TILE, que o editor de mapa larga no proximo save.",
            "padrao": False,
        },
    },
)
def tool_medir_mapa_otbm(
    caminho_relativo,
    acao="ponto",
    x=0,
    y=0,
    z=0,
    limite=LIMITE_VAZIOS,
    pontos="",
    ids="",
    regiao="",
    spawn="",
    detalhar_vazios=False,
):
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
        if escolha in ("ponto", "pontos"):
            lista = _pontos_pedidos(pontos, x, y, z)
            if not lista:
                return "ERRO: nenhuma coordenada valida em 'pontos' (escreve x,y,z por linha)."
            relatos = [_relato_ponto(dados, caminho_relativo, px, py, pz) for px, py, pz in lista]
            return relatos[0] if len(relatos) == 1 else "\n".join(relatos)
        if escolha == "vazios":
            return _relato_vazios(dados, caminho_relativo, _teto(limite))
        if escolha == "resumo":
            return _relato_resumo(dados, caminho_relativo)
        if escolha == "portas":
            return _relato_portas(dados, caminho_relativo, ids, regiao, _teto(limite, 5000, LIMITE_PORTAS))
        if escolha == "spawns":
            return _relato_spawns(caminho_relativo, alvo, spawn, _teto(limite), detalhar_vazios, dados)
    except ValueError as falha:
        return f"ERRO: o mapa '{caminho_relativo}' tem um no sem fecho ({falha})."
    return f"ERRO: acao desconhecida '{acao}' (usa 'ponto' ou 'pontos', 'vazios', 'resumo', 'portas' ou 'spawns')."


@register(
    "tool_marcar_portas_otbm",
    "Escreve o action id (a chave de storage da quest) nos itens de porta de um mapa .otbm, POR POSICAO - "
    "e o que se faria a mao no editor de mapa, feito por codigo. E o caminho de raiz de uma porta de quest "
    "sem action id: o script da porta le o action id como chave e, sem ele, a porta abre para qualquer um e "
    "nao fecha depois de passar. Sem 'aplicar' apenas relata (o action id de cada porta, o que entraria e o "
    "que ja la esta); com 'aplicar' grava o mapa, guardando o original na pasta temporaria e conferindo o "
    "resultado por nova leitura. Nao toca em nenhum item fora das posicoes pedidas. Uma porta que JA tem "
    "action id nao se toca por omissao: para lhe corrigir a chave, 'trocar'=True troca o valor no proprio "
    "lugar (mesmo tamanho, sem mexer no resto do mapa).",
    {
        "caminho_relativo": {
            "tipo": "STRING",
            "desc": "Arquivo do mapa (.otbm), dentro do projeto.",
            "obrig": True,
            "padrao": "",
        },
        "posicoes": {
            "tipo": "STRING",
            "desc": "As portas a marcar, uma por linha no formato x,y,z. So entra a porta que existir mesmo nessa coordenada.",
            "padrao": "",
        },
        "actionid": {
            "tipo": "INTEGER",
            "desc": "O action id a escrever - que e a chave de storage da quest (a porta abre a quem tiver essa storage >= 1).",
            "padrao": 0,
        },
        "ids": {
            "tipo": "STRING",
            "desc": "Item ids considerados porta, separados por virgula. Vazio usa as duas familias de porta: as 8 de quest (1223, 1225, 1241, 1243, 1255, 1257, 3542, 3551) e as 8 de nivel/vocacao (1227, 1229, 1245, 1247, 1259, 1261, 3540, 3549).",
            "padrao": "",
        },
        "aplicar": {
            "tipo": "BOOLEAN",
            "desc": "False (padrao) so relata; True grava o mapa.",
            "padrao": False,
        },
        "trocar": {
            "tipo": "BOOLEAN",
            "desc": "False (padrao) recusa-se a tocar numa porta que ja tem action id. True troca a chave dessa porta no proprio lugar - a unica via para corrigir uma chave ja escrita, seja porque aponta para a quest errada, seja porque o portao passou a exigir outra storage.",
            "padrao": False,
        },
    },
)
def tool_marcar_portas_otbm(caminho_relativo, posicoes="", actionid=0, ids="", aplicar=False, trocar=False):
    emit_event("executing", function=f"Marcando portas no mapa: {caminho_relativo}")
    alvo, erro = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro:
        return erro
    if not os.path.isfile(alvo):
        return f"ERRO: arquivo nao encontrado: {caminho_relativo}"

    pedidas = _posicoes_pedidas(posicoes)
    if not pedidas:
        return "ERRO: nenhuma coordenada valida em 'posicoes' (escreve x,y,z por linha)."
    try:
        chave = int(actionid)
    except (TypeError, ValueError):
        return "ERRO: o action id tem de ser um numero."
    if not 0 < chave < 65536:
        return "ERRO: o action id tem de estar entre 1 e 65535."

    try:
        dados = _bytes_do_mapa(alvo)
    except OSError as falha:
        return f"ERRO: nao consegui ler '{caminho_relativo}' ({falha})."
    if len(dados) < 8 or (dados[0] != NODE_START and not (dados[:4] == bytes(4) and dados[4] == NODE_START)):
        return f"ERRO: '{caminho_relativo}' nao comeca com o cabecalho de um mapa OTBM."

    alvos = _ids_pedidos(ids)
    try:
        achados = _portas_com_offset(dados, alvos, pedidas)
    except ValueError as falha:
        return f"ERRO: o mapa '{caminho_relativo}' tem um no sem fecho ({falha})."

    if not achados:
        return (
            f"Nada a fazer: nenhuma das {len(pedidas)} posicao(oes) tem um item de porta "
            f"({'/'.join(str(i) for i in alvos)}) neste mapa."
        )

    linhas = [
        f"MAPA '{caminho_relativo}': action id {chave} em {len(achados)} porta(s).",
        "ANTES:",
    ]
    linhas += [f"  [{x}, {y}, {z}] {_linha_do_item(info)}" for x, y, z, info, _, _ in achados]
    faltam = pedidas - {(x, y, z) for x, y, z, _, _, _ in achados}
    if faltam:
        linhas.append("  SEM PORTA aqui: " + "; ".join(f"{x},{y},{z}" for x, y, z in sorted(faltam)))

    trocadas = [a for a in achados if a[3].get("acao") not in (None, chave)]
    if trocadas:
        linhas.append(
            "  ATENCAO: "
            + "; ".join(
                f"[{x}, {y}, {z}] ja tem action id {info.get('acao')}" for x, y, z, info, _, _ in trocadas
            )
        )
        if not trocar:
            return "\n".join(linhas) + (
                "\nNada foi gravado: porta que ja tem um action id nao se troca por cima (seria trocar a quest dela). "
                "Se a chave nova for mesmo a certa, repita com trocar=True."
            )

    insercoes = [offset for _, _, _, info, offset, _ in achados if info.get("acao") is None]
    if not insercoes and not trocadas:
        return "\n".join(linhas) + "\nNada a fazer: as portas ja tem esse action id."

    if not aplicar:
        return "\n".join(linhas) + (
            f"\nA GRAVAR: {len(insercoes)} porta(s) ganham o atributo de action id "
            f"({len(insercoes) * 3} byte(s) a mais) e {len(trocadas)} porta(s) tem a chave trocada no proprio lugar. "
            "Repita com aplicar=True para gravar."
        )

    novos = _com_action_id_trocado(dados, trocadas, chave) if trocadas else dados
    if isinstance(novos, str):
        return "\n".join(linhas) + "\n" + novos
    if insercoes:
        novos = _com_action_id_na_porta(novos, insercoes, chave)
    copia = _guardar_copia_do_mapa(alvo, dados)
    with open(alvo, "wb") as arquivo:
        arquivo.write(novos)
    _CACHE_DE_BYTES.clear()
    _CACHE_DE_AREAS.clear()

    confirmados = _portas_com_offset(_bytes_do_mapa(alvo), alvos, pedidas)
    lidas = [c for c in confirmados if c[3].get("acao") == chave]
    linhas.append(f"GRAVADO: {len(novos)} bytes (era {len(dados)}). Original guardado em {copia}")
    linhas.append(f"CONFERIDO POR NOVA LEITURA: {len(lidas)} de {len(achados)} porta(s) com action id {chave}.")
    linhas.append("DEPOIS:")
    linhas += [f"  [{x}, {y}, {z}] {_linha_do_item(info)}" for x, y, z, info, _, _ in confirmados]
    if len(lidas) != len(achados):
        linhas.append("ERRO: nem todas ficaram gravadas - reponha o original guardado acima e diga-me.")
    return "\n".join(linhas)


def _guardar_copia_do_mapa(alvo, dados):
    marca = time.strftime("%Y%m%d-%H%M%S")
    destino = os.path.join(tempfile.gettempdir(), f"{os.path.basename(alvo)}.{marca}.bak")
    with open(destino, "wb") as arquivo:
        arquivo.write(dados)
    return destino


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


def _monstros_do_datapack(caminho_mapa):
    caminho = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(caminho_mapa))), "monster", "monsters.xml"
    )
    if not os.path.isfile(caminho):
        return set()
    try:
        raiz = ET.parse(caminho).getroot()
    except (ET.ParseError, OSError):
        return set()
    return {(no.get("name") or "").lower() for no in raiz if no.tag == "monster"}


def _relato_spawns(rotulo, caminho_mapa, caminho_spawn, limite, detalhar=False, dados=None):
    if not str(caminho_spawn or "").strip():
        caminho_spawn = os.path.join(os.path.dirname(caminho_mapa), "spawn.xml")
    else:
        alvo, erro = resolver_caminho(caminho_spawn, permitir_extra=True)
        if erro:
            return erro
        caminho_spawn = alvo
    if not os.path.isfile(caminho_spawn):
        return (
            f"ERRO: nao encontrei o ficheiro de spawn '{caminho_spawn}'.\n"
            "O TFS guarda-o ao lado do mapa com o nome 'spawn.xml' - se tiver outro nome, passe o caminho em 'spawn'."
        )
    try:
        with open(caminho_spawn, encoding="utf-8", errors="replace") as arquivo:
            texto = arquivo.read()
    except OSError as falha:
        return f"ERRO: nao consegui ler '{caminho_spawn}' ({falha})."
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError as falha:
        return f"ERRO: '{caminho_spawn}' nao e um XML valido ({falha})."
    if raiz.tag != "spawns":
        return f"ERRO: '{caminho_spawn}' tem <{raiz.tag}> na raiz; o TFS espera <spawns>."

    blocos = raiz.findall("spawn")
    sem_criatura = len(re.findall(r"<spawn[^>]*/>", texto))
    monstros = npcs = 0
    monstros_do_datapack = _monstros_do_datapack(caminho_mapa)
    npcs_com_nome_de_monstro = []
    fora = []
    quantos = {}
    vazios = []
    povoados = []
    nascem_em = {}
    for bloco in blocos:
        centro = (
            int(bloco.get("centerx") or 0),
            int(bloco.get("centery") or 0),
            int(bloco.get("centerz") or 0),
        )
        raio = int(bloco.get("radius") or 0)
        quantos[centro] = quantos.get(centro, 0) + 1
        nomes_do_bloco = [c.get("name") or "?" for c in bloco if c.tag in ("monster", "npc")]
        if nomes_do_bloco:
            povoados.append((centro, nomes_do_bloco))
        else:
            vazios.append((centro, raio))
        for criatura in bloco:
            if criatura.tag == "monster":
                monstros += 1
            elif criatura.tag == "npc":
                npcs += 1
                if (criatura.get("name") or "").lower() in monstros_do_datapack:
                    npcs_com_nome_de_monstro.append(criatura.get("name") or "?")
            else:
                continue
            deslocamento = (int(criatura.get("x") or 0), int(criatura.get("y") or 0))
            nascem_em.setdefault(
                (centro[0] + deslocamento[0], centro[1] + deslocamento[1], centro[2]), []
            ).append(criatura.get("name") or "?")
            if abs(deslocamento[0]) > raio or abs(deslocamento[1]) > raio:
                fora.append(
                    (centro, raio, criatura.tag, criatura.get("name") or "?", deslocamento)
                )

    repetidas = sorted(posicao for posicao, total in quantos.items() if total > 1)
    linhas = [
        f"SPAWNS '{os.path.basename(caminho_spawn)}' (o de '{rotulo}'):",
        f"  blocos <spawn>: {len(blocos)} | criaturas: {monstros + npcs} ({monstros} monstros + {npcs} NPCs)",
        f"  blocos sem criatura nenhuma: {sem_criatura}",
        f"  posicoes repetidas: {len(repetidas)}",
    ]
    if repetidas:
        linhas.append("  REPETIDAS (o editor recusa a segunda e avisa 'Duplicate spawn'):")
        linhas += [f"    {x}, {y}, {z} - {quantos[(x, y, z)]} blocos" for x, y, z in repetidas[:limite]]
    linhas.append(f"  criaturas fora do raio do bloco: {len(fora)}")
    if fora:
        linhas += [
            f"    [{x}, {y}, {z}] raio {raio}: {tag} '{nome}' em {dx:+d},{dy:+d}"
            for (x, y, z), raio, tag, nome, (dx, dy) in fora[:limite]
        ]
    if npcs_com_nome_de_monstro:
        linhas.append(
            f"  NPC COM NOME DE MONSTRO ({len(npcs_com_nome_de_monstro)}): {', '.join(sorted(set(npcs_com_nome_de_monstro)))}"
        )
        linhas.append(
            "    o editor de mapa procura a criatura pelo NOME, encontra o monstro homonimo e grava-o como monstro - o NPC desaparece no proximo save."
        )
    if detalhar and dados is not None:
        centros = {centro for centro, _ in vazios} | {centro for centro, _ in povoados}
        if centros:
            com_tile = set()
            for tx, ty, tz, _, _, _ in _tiles(dados):
                chave = (tx, ty, tz)
                if chave in centros:
                    com_tile.add(chave)
            sem_tile = sorted(centros - com_tile)
            if sem_tile:
                linhas.append(
                    f"  BLOCOS EM POSICAO SEM TILE ({len(sem_tile)}) - o editor larga-os no save, nao ha tile onde guardar o bloco:"
                )
                linhas += [f"    {x}, {y}, {z}" for x, y, z in sem_tile[:limite]]
    if detalhar and vazios:
        cascas = sum(1 for centro, _ in vazios if centro in nascem_em)
        linhas.append(
            f"  BLOCOS SEM CRIATURA ({len(vazios)}) - posicao, raio, e os blocos povoados num raio de 40:"
        )
        if cascas:
            linhas.append(
                f"    ({cascas} deles sao CASCA: o centro e o tile onde nasce uma criatura de OUTRO"
                " bloco - nao falta bicho nenhum ali)"
            )
        for (vx, vy, vz), raio in vazios:
            perto = []
            for (px, py, pz), nomes_do_bloco in povoados:
                distancia = max(abs(px - vx), abs(py - vy))
                if distancia <= 40 and abs(pz - vz) <= 1:
                    perto.append((distancia, (px, py, pz), nomes_do_bloco))
            perto.sort()
            if not perto:
                linhas.append(
                    f"    [{vx}, {vy}, {vz}] raio {raio}: NENHUM bloco povoado num raio de 40 - "
                    "nenhuma caçada por perto, o mais provavel e lixo do ficheiro."
                )
                continue
            amostra = "; ".join(
                f"a {distancia} em {px},{py},{pz}: {', '.join(nomes_do_bloco[:4])}"
                for distancia, (px, py, pz), nomes_do_bloco in perto[:3]
            )
            marca = ""
            if (vx, vy, vz) in nascem_em:
                marca = (
                    f" | CASCA: nasce {', '.join(nascem_em[(vx, vy, vz)][:4])} neste tile por OUTRO bloco"
                )
            linhas.append(
                f"    [{vx}, {vy}, {vz}] raio {raio}: {len(perto)} vizinho(s) - {amostra}{marca}"
            )
    return "\n".join(linhas)


def _relato_portas(dados, rotulo, ids, regiao, limite):
    alvos = _ids_pedidos(ids)
    caixa = _caixa_pedida(regiao)
    sinais = [bytes((NODE_START, TIPO_ITEM, i & 0xFF, (i >> 8) & 0xFF)) for i in alvos]
    achados = []
    for base, inicio, fim, ultimo in _areas_com_sinal(dados, sinais, caixa):
        indice = inicio
        while dados[indice] == NODE_START and indice <= ultimo and len(achados) < limite:
            x, y, z, _, tem_filho, seguinte = _tile_curto(dados, indice, base)
            if tem_filho and _dentro_da_caixa(caixa, x, y, z) and _tem_sinal(dados, indice, seguinte, sinais):
                for item in _tile(dados, indice, base)["itens"]:
                    if item.get("id") in alvos:
                        achados.append((x, y, z, item))
            indice = seguinte
    return "\n".join(_linhas_das_portas(rotulo, alvos, caixa, achados, limite))


def _posicoes_pedidas(posicoes):
    achadas = set()
    for linha in str(posicoes or "").replace(";", "\n").splitlines():
        campos = [c.strip() for c in linha.split(",") if c.strip()]
        if len(campos) < 3:
            continue
        try:
            x, y, z = int(campos[0]), int(campos[1]), int(campos[2])
        except ValueError:
            continue
        achadas.add((x, y, z))
    return achadas


def _portas_com_offset(dados, alvos, posicoes):
    xs = [p[0] for p in posicoes]
    ys = [p[1] for p in posicoes]
    caixa = (min(xs), min(ys), max(xs), max(ys), {p[2] for p in posicoes})
    sinais = [bytes((NODE_START, TIPO_ITEM, i & 0xFF, (i >> 8) & 0xFF)) for i in alvos]
    achados = []
    for base, inicio, _, ultimo in _areas_com_sinal(dados, sinais, caixa):
        indice = inicio
        while dados[indice] == NODE_START and indice <= ultimo:
            x, y, z, _, tem_filho, seguinte = _tile_curto(dados, indice, base)
            if tem_filho and (x, y, z) in posicoes and _tem_sinal(dados, indice, seguinte, sinais):
                ponteiro = _ate_marcador(dados, indice + 2)[1]
                while dados[ponteiro] == NODE_START:
                    props, fim_props = _ate_marcador(dados, ponteiro + 2)
                    info = _item(_sem_escape(props))
                    if info.get("id") in alvos:
                        achados.append((x, y, z, info, fim_props, ponteiro + 2))
                    ponteiro = _fim_do_no(dados, ponteiro)
            indice = seguinte
    return achados


def _com_action_id_na_porta(dados, insercoes, chave):
    acrescento = bytearray()
    for byte in bytes((ATTR_ACAO,)) + struct.pack("<H", chave):
        if byte in (NODE_START, NODE_END, ESCAPE):
            acrescento.append(ESCAPE)
        acrescento.append(byte)
    saida = bytearray()
    anterior = 0
    for offset in sorted(insercoes):
        saida += dados[anterior:offset]
        saida += acrescento
        anterior = offset
    saida += dados[anterior:]
    return bytes(saida)


def _com_action_id_trocado(dados, achados, chave):
    if any(byte in (NODE_START, NODE_END, ESCAPE) for byte in struct.pack("<H", chave)):
        return (
            f"ERRO: o action id {chave} tem um byte que precisa de escape e a troca no proprio "
            "lugar mudaria o tamanho do no. Nada foi gravado."
        )
    saida = bytearray(dados)
    for x, y, z, info, fim, inicio in achados:
        antigo = int(info.get("acao") or 0)
        bruto = dados[inicio:fim]
        par = bytes((ATTR_ACAO,)) + struct.pack("<H", antigo)
        quantas = bruto.count(par)
        if quantas != 1:
            return (
                f"ERRO: nas propriedades da porta [{x}, {y}, {z}] o par do action id {antigo} aparece "
                f"{quantas} vez(es) - nao troco as cegas. Nada foi gravado."
            )
        posicao = inicio + bruto.index(par) + 1
        saida[posicao : posicao + 2] = struct.pack("<H", chave)
    return bytes(saida)


def _ids_pedidos(ids):
    if not str(ids or "").strip():
        return list(IDS_PORTA) + list(IDS_PORTA_NIVEL)
    lista = []
    for pedaco in str(ids).replace(";", ",").split(","):
        pedaco = pedaco.strip()
        if pedaco.isdigit() and int(pedaco) not in lista:
            lista.append(int(pedaco))
    return lista


def _caixa_pedida(regiao):
    campos = [c.strip() for c in str(regiao or "").replace(";", ",").split(",") if c.strip()]
    if len(campos) < 4:
        return None
    try:
        numeros = [int(c) for c in campos]
    except ValueError:
        return None
    return (
        min(numeros[0], numeros[2]),
        min(numeros[1], numeros[3]),
        max(numeros[0], numeros[2]),
        max(numeros[1], numeros[3]),
        set(numeros[4:]) or None,
    )


def _dentro_da_caixa(caixa, x, y, z):
    if caixa is None:
        return True
    if not (caixa[0] <= x <= caixa[2] and caixa[1] <= y <= caixa[3]):
        return False
    return caixa[4] is None or z in caixa[4]


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


def _tem_sinal(dados, indice, seguinte, sinais):
    return any(dados.find(sinal, indice, seguinte) >= 0 for sinal in sinais)


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


def _areas_com_sinal(dados, sinais, caixa):
    areas = _areas(dados)
    for posicao, (base, inicio) in enumerate(areas):
        fim = areas[posicao + 1][1] if posicao + 1 < len(areas) else len(dados)
        if caixa is not None:
            x0, y0, z0 = base
            if (
                x0 + LADO_DA_AREA - 1 < caixa[0]
                or x0 > caixa[2]
                or y0 + LADO_DA_AREA - 1 < caixa[1]
                or y0 > caixa[3]
            ):
                continue
            if caixa[4] is not None and z0 not in caixa[4]:
                continue
        ultimo = -1
        for sinal in sinais:
            encontrado = dados.rfind(sinal, inicio, fim)
            if encontrado > ultimo:
                ultimo = encontrado
        if ultimo >= 0:
            yield base, inicio, fim, ultimo


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


def _linhas_das_portas(rotulo, alvos, caixa, achados, limite):
    onde = "o mapa todo" if caixa is None else f"a caixa {caixa[0]}..{caixa[2]} x {caixa[1]}..{caixa[3]}"
    com_acao = [a for a in achados if a[3].get("acao")]
    sem_acao = [a for a in achados if not a[3].get("acao")]
    sem_acao_quest = [a for a in sem_acao if a[3].get("id") in IDS_PORTA]
    sem_acao_nivel = [a for a in sem_acao if a[3].get("id") in IDS_PORTA_NIVEL]
    linhas = [
        f"MAPA '{rotulo}': {len(achados)} item(ns) de {'/'.join(str(i) for i in alvos)} em {onde}.",
        f"  COM action id: {len(com_acao)}",
        f"  SEM action id: {len(sem_acao)}",
    ]
    if sem_acao_quest:
        linhas.append(
            "  Porta de quest sem action id no mapa nao sela nem fecha apos a passagem: "
            "o script so sabe qual e a chave pelo action id."
        )
    if sem_acao_nivel:
        linhas.append(
            "  Gate of expertise sem action id nao pede nivel nem vocacao: abre a qualquer um "
            "(o action id dessas portas e o nivel, 1001-1999, ou a vocacao, 2001-2008)."
        )
    if len(achados) >= limite:
        linhas.append(f"  (lista cortada em {limite} - passe 'regiao' ou suba 'limite')")
    contagem = {}
    for _, _, _, item in achados:
        contagem[item.get("id")] = contagem.get(item.get("id"), 0) + 1
    if contagem:
        linhas.append("POR ID:")
        linhas += [f"  {identificador}: {quantos}" for identificador, quantos in sorted(contagem.items())]
    if achados:
        linhas.append("POSICOES:")
        linhas += [f"  [{x}, {y}, {z}] {_linha_do_item(item)}" for x, y, z, item in achados]
    return linhas


def _linha_do_item(info):
    partes = [f"item {info.get('id')}"]
    if "acao" in info:
        partes.append(f"action id {info['acao']}")
        sentido = _sentido_da_porta(info)
        if sentido:
            partes.append(sentido)
    if "unico" in info:
        partes.append(f"unique id {info['unico']}")
    if "teleporte" in info:
        destino = info["teleporte"]
        partes.append(f"teleporte para {destino[0]}, {destino[1]}, {destino[2]}")
    if "resto" in info:
        partes.append(f"resto {info['resto']}")
    return " | ".join(partes)


def _sentido_da_porta(info):
    acao = info.get("acao")
    if info.get("id") not in IDS_PORTA_NIVEL or not acao:
        return None
    if 1001 <= acao <= 1999:
        return f"pede nivel {acao - 1000}"
    if 2001 <= acao <= 2008:
        return f"so {VOCACOES_DA_PORTA.get(acao - 2000, 'vocation desconhecida')}"
    return None


def _teto(valor, maximo=1000, padrao=LIMITE_VAZIOS):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return padrao
    return max(1, min(maximo, numero))
