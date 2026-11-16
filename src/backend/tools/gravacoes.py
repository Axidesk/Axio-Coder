import collections
import json
import os
import re
import shutil
import subprocess
import tempfile

from src.backend.services.file_service import resolver_caminho
from src.backend.state import emit_event
from src.backend.tools.registry import register

VERSAO_PADRAO = "7.40"
SACO_DE_LOOT = 1987
OURO = 2148
TETO_DE_LINHAS = 60
SEGUNDOS_PADRAO = 300
PROFUNDIDADE_DA_BUSCA = 7
PASTAS_FORA = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "build",
        "dist",
        "obj",
        "Release",
        "Debug",
        "libs",
        "vendor",
        "gerados",
        "cache_modelos",
    }
)
GRUPOS = {
    "dano": ("NumberEffectPopped",),
    "efeito": ("GraphicalEffectPopped",),
    "vida": ("CreatureHealthUpdated", "PlayerDataUpdated"),
    "chat": ("StatusMessageReceived", "CreatureSpoke", "CreatureSpokeOnMap", "PrivateConversationOpened"),
    "loot": ("ContainerAddedItem", "ContainerRemovedItem", "ContainerTransformedItem", "ContainerOpened", "ContainerClosed"),
    "magia": ("MissileFired",),
    "movimento": ("CreatureMoved", "PlayerMoved"),
    "velocidade": ("CreatureSpeedUpdated",),
    "criatura": ("CreatureSeen", "CreatureRemoved", "CreatureHeadingUpdated"),
}
_CACHE = {}
_MINER = {}
_CLIENTES = {}


@register(
    "tool_ler_rec",
    "Le uma gravacao do Tibia (.rec do TibiaCAM, 7.3 ou 7.4) e devolve o que aconteceu la dentro, em "
    "texto: o resumo por tipo de evento, os nomes das criaturas, o jogador, e - com 'inicio'/'fim' ou "
    "'grupo' - a lista de eventos do momento que interessa. E o caminho para responder 'o que aconteceu "
    "no 3:10 daquela gravacao' sem abrir o Painel de Controlo: dano (valor, cor e tile), efeito grafico "
    "(id e tile), vida, fala, loot e magia, todos com hora ao milesimo. O motor e o miner.exe do "
    "TibiaCAM que o painel ja usa, mas chamado pelo caminho certo: a gravacao e copiada para uma pasta "
    "temporaria sem acentos, porque textos como '2. Utilitarios' no caminho fazem o miner responder "
    "'IO failure'. Nao serve para concluir o tipo de dano sozinha - ela mostra a cor do numero e o id do "
    "efeito no mesmo tile, que e o que permite julgar isso.",
    {
        "gravacao": {
            "tipo": "STRING",
            "desc": "Nome da gravacao ('dlsolo.rec' ou so 'dlsolo') ou caminho completo. Sem 'pasta', "
            "procura nas pastas de gravacoes que o Painel de Controlo tem registadas.",
            "obrig": True,
            "padrao": "",
        },
        "pasta": {
            "tipo": "STRING",
            "desc": "Pasta onde estao as gravacoes .rec. Vazio = as pastas registadas no painel e a raiz do projeto.",
            "padrao": "",
        },
        "inicio": {
            "tipo": "STRING",
            "desc": "Instante de partida, em 'm:ss' ('3:10'), 'm:ss.cc' ('3:10.28') ou segundos ('190'). Vazio = desde o principio.",
            "padrao": "",
        },
        "fim": {
            "tipo": "STRING",
            "desc": "Instante de chegada, no mesmo formato de 'inicio'. Vazio = ate ao fim da gravacao.",
            "padrao": "",
        },
        "grupo": {
            "tipo": "STRING",
            "desc": "Familia de eventos: dano, efeito, vida, chat, loot, magia, movimento, velocidade, criatura. Vazio = resumo geral.",
            "padrao": "",
        },
        "evento": {
            "tipo": "STRING",
            "desc": "Nome exato de um evento do miner (ex: 'NumberEffectPopped'), quando o grupo nao chega.",
            "padrao": "",
        },
        "limite": {
            "tipo": "INTEGER",
            "desc": "Numero maximo de linhas a listar.",
            "padrao": TETO_DE_LINHAS,
        },
        "loot": {
            "tipo": "STRING",
            "desc": "Soma o loot dos corpos abertos na gravacao e devolve DUAS tabelas: o que caiu "
            "NO CORPO e o que caiu DENTRO DO SACO, cada uma com a frequencia dos itens e as pilhas "
            "de ouro. Separa-as porque o saco so aparece numa parte dos corpos - a taxa que o "
            "servidor aplica e a do saco multiplicada por essa fracao. Nome do monstro "
            "('dragon lord') filtra pelos corpos dele; um numero escolhe o id do corpo; 'todos' "
            "soma tudo.",
            "padrao": "",
        },
        "terreno": {
            "tipo": "BOOLEAN",
            "desc": "Ler tambem o terreno do mapa (muito mais lento e o dobro do tamanho). Normalmente nao.",
            "padrao": False,
        },
    },
)
def tool_ler_rec(gravacao, pasta="", inicio="", fim="", grupo="", evento="", limite=TETO_DE_LINHAS, terreno=False, loot=""):
    emit_event("executing", function=f"Lendo a gravacao: {gravacao}")
    caminho, alternativas = _achar_gravacao(gravacao, pasta)
    if not caminho:
        return f"ERRO: nao achei a gravacao '{gravacao}'. Passe 'pasta' com a pasta onde ela esta."

    miner = _achar_miner()
    if not miner:
        return (
            "ERRO: nao achei o miner.exe no projeto. Ele vem com o Painel de Controlo "
            "(bin/miner.exe) ou pode ser apontado em MINER_TIBIACAM."
        )
    clientes = _achar_clientes(miner)
    if not clientes:
        return (
            f"ERRO: achei o miner em {miner} mas nao achei nenhuma pasta 'clientes/<versao>' com "
            "Tibia.dat ao lado dele - sem os dados do cliente o miner nao abre a gravacao."
        )

    try:
        bruto, usado = _ler_bruto(caminho, miner, clientes, bool(terreno))
    except RuntimeError as falha:
        return f"ERRO: {falha}"

    blocos = bruto if isinstance(bruto, list) else []
    linhas = _cabecalho(caminho, blocos, usado)
    if alternativas:
        linhas.append("  OUTRAS COM ESSE NOME: " + " | ".join(alternativas))
    if str(loot or "").strip():
        linhas += _loot_dos_corpos(blocos, str(loot).strip())
        return "\n".join(linhas)
    filtro = _filtro(grupo, evento)
    de, ate = _janela(inicio, fim)
    if not filtro and de is None and ate is None:
        linhas += _resumo(blocos)
        return "\n".join(linhas)
    linhas += _listar(blocos, filtro, de, ate, _teto(limite))
    return "\n".join(linhas)


def eventos_da_gravacao(gravacao, pasta="", terreno=False):
    """Devolve a lista de eventos da gravacao, cada um com '__t' em segundos."""
    caminho, _ = _achar_gravacao(gravacao, pasta)
    if not caminho:
        raise RuntimeError(f"nao achei a gravacao '{gravacao}'")
    miner = _achar_miner()
    if isinstance(miner, tuple):
        miner = miner[0]
    if not miner:
        raise RuntimeError("nao achei o miner.exe no projeto")
    bruto, _ = _ler_bruto(caminho, miner, _achar_clientes(miner), bool(terreno))
    blocos = bruto if isinstance(bruto, list) else []
    eventos = []
    for bloco in blocos:
        quando = float(bloco.get("Timestamp", 0)) / 1000.0
        for evento in bloco.get("Events", []):
            linha = dict(evento)
            linha["__t"] = quando
            eventos.append(linha)
    return eventos


def _achar_gravacao(pedido, pasta):
    texto = str(pedido or "").strip().strip('"')
    if not texto:
        return "", []
    if os.path.isabs(texto) and os.path.isfile(texto):
        return texto, []
    alvo, erro = resolver_caminho(texto, permitir_extra=True)
    if not erro and os.path.isfile(alvo):
        return alvo, []
    nome = texto if texto.lower().endswith(".rec") else f"{texto}.rec"
    achadas = []
    vistos = set()
    for candidata in _pastas_de_gravacoes(pasta):
        caminho = os.path.join(candidata, nome)
        chave = os.path.normcase(os.path.abspath(caminho))
        if chave in vistos or not os.path.isfile(caminho):
            continue
        vistos.add(chave)
        achadas.append(caminho)
    if not achadas:
        return "", []
    return achadas[0], achadas[1:]


def _pastas_de_gravacoes(pasta):
    vistas = _pastas_conhecidas()
    if str(pasta or "").strip():
        vistas.insert(0, str(pasta).strip().strip('"'))
    return vistas


def _pastas_conhecidas():
    if _CACHE.get("pastas"):
        return list(_CACHE["pastas"])
    achadas = []
    raiz = os.getcwd()
    achadas.append(raiz)
    for pasta, dirs, ficheiros in os.walk(raiz):
        dirs[:] = [
            d for d in dirs if d not in PASTAS_FORA and not d.startswith(".")
        ]
        if os.path.relpath(pasta, raiz).count(os.sep) >= PROFUNDIDADE_DA_BUSCA:
            dirs[:] = []
            continue
        if "video.json" in ficheiros:
            for registada in _pastas_do_estado(os.path.join(pasta, "video.json")):
                if registada and registada not in achadas:
                    achadas.append(registada)
    _CACHE["pastas"] = achadas
    return list(achadas)


def _pastas_do_estado(ficheiro):
    try:
        with open(ficheiro, encoding="utf-8") as aberto:
            dados = json.load(aberto)
    except (OSError, ValueError):
        return []
    if not isinstance(dados, dict):
        return []
    mapa = dados.get("pastas")
    if isinstance(mapa, dict):
        return [str(mapa[chave]) for chave in sorted(mapa, reverse=True) if isinstance(mapa[chave], str)]
    alvo = dados.get("pasta")
    return [alvo] if isinstance(alvo, str) else []


def _achar_miner():
    if _MINER.get("caminho") is not None:
        return _MINER["caminho"]
    ambiente = os.environ.get("MINER_TIBIACAM", "")
    achado = ambiente if ambiente and os.path.isfile(ambiente) else ""
    if not achado:
        raiz = os.getcwd()
        for pasta, dirs, ficheiros in os.walk(raiz):
            dirs[:] = [d for d in dirs if d not in PASTAS_FORA and not d.startswith(".")]
            if os.path.relpath(pasta, raiz).count(os.sep) >= PROFUNDIDADE_DA_BUSCA:
                dirs[:] = []
                continue
            if "miner.exe" in ficheiros:
                achado = os.path.join(pasta, "miner.exe")
                break
    _MINER["caminho"] = achado
    return achado


def _achar_clientes(miner):
    if _CLIENTES.get("mapa"):
        return dict(_CLIENTES["mapa"])
    pasta = os.path.dirname(miner)
    mapa = {}
    for _ in range(4):
        candidata = os.path.join(pasta, "clientes")
        if os.path.isdir(candidata):
            for nome in sorted(os.listdir(candidata)):
                dados = os.path.join(candidata, nome)
                if os.path.isfile(os.path.join(dados, "Tibia.dat")):
                    mapa[_versao_do_miner(nome)] = dados
        if mapa:
            break
        pasta = os.path.dirname(pasta)
    _CLIENTES["mapa"] = mapa
    return dict(mapa)


def _versao_do_miner(nome):
    return f"{nome}0" if nome.count(".") == 1 else nome


def _ler_bruto(caminho, miner, clientes, terreno):
    stat = os.stat(caminho)
    chave = (os.path.abspath(caminho), stat.st_mtime, stat.st_size, terreno)
    if chave in _CACHE:
        return _CACHE[chave]

    ordens = [VERSAO_PADRAO] if VERSAO_PADRAO in clientes else []
    ordens += [v for v in sorted(clientes, reverse=True) if v not in ordens]
    problemas = []
    temporaria = tempfile.mkdtemp(prefix="axio_rec")
    copia = os.path.join(temporaria, "gravacao.rec")
    try:
        shutil.copy2(caminho, copia)
        for versao in ordens:
            comando = [miner, clientes[versao], copia, "--input-format", "rec", "--input-version", versao]
            if not terreno:
                comando.append("--skip-terrain")
            try:
                saida = subprocess.run(comando, capture_output=True, timeout=SEGUNDOS_PADRAO)
            except subprocess.TimeoutExpired:
                problemas.append(f"{versao}: passou de {SEGUNDOS_PADRAO}s")
                continue
            if saida.returncode != 0:
                motivo = saida.stderr.decode("utf-8", "replace").strip() or "sem mensagem"
                problemas.append(f"{versao}: {motivo[:160]}")
                continue
            try:
                bruto = json.loads(saida.stdout)
            except ValueError:
                problemas.append(f"{versao}: a saida nao e JSON")
                continue
            if not isinstance(bruto, list) or not bruto:
                problemas.append(f"{versao}: gravacao sem eventos")
                continue
            _CACHE[chave] = (bruto, versao)
            return bruto, versao
    finally:
        shutil.rmtree(temporaria, ignore_errors=True)
    raise RuntimeError(
        "o miner nao abriu esta gravacao"
        + (": " + " | ".join(problemas) if problemas else "")
    )


def _cabecalho(caminho, blocos, versao):
    segundos = _duracao(blocos)
    linhas = [
        f"GRAVACAO: {os.path.basename(caminho)} ({_bytes(os.path.getsize(caminho))})",
        f"  pasta: {os.path.dirname(caminho)}",
        f"  versao {versao} | {_hora(segundos * 1000)} de duracao | {len(blocos)} blocos",
    ]
    jogador = _quem_grave(blocos)
    if jogador:
        linhas.append(f"  quem gravou: {jogador}")
    return linhas


CORES_DE_NUMERO = {
    5: "azul",
    30: "verde (veneno)",
    35: "azul (energia)",
    129: "cinza (fisico em undead)",
    180: "vermelho (sangue/dreno)",
    198: "laranja (fogo)",
    215: "experiencia (nao e dano)",
}


def _resumo(blocos):
    contagem = collections.Counter()
    cores = collections.Counter()
    efeitos = collections.Counter()
    nomes = _nomes(blocos)
    for evento in _eventos(blocos):
        tipo = evento.get("Event", "")
        contagem[tipo] += 1
        if tipo == "NumberEffectPopped":
            cores[evento.get("Color")] += 1
        elif tipo == "GraphicalEffectPopped":
            efeitos[evento.get("Id")] += 1
    linhas = ["", "EVENTOS (por tipo):"]
    linhas += [f"  {tipo}: {quantos}" for tipo, quantos in contagem.most_common()]
    if cores:
        linhas.append("CORES DOS NUMEROS (cor do cliente -> o que acende -> quantas vezes):")
        linhas.append("  " + " | ".join(
            f"{cor} {CORES_DE_NUMERO.get(cor, '?')} -> {quantos}x"
            for cor, quantos in cores.most_common(12)))
    if efeitos:
        linhas.append("EFEITOS GRAFICOS (id -> quantas vezes):")
        linhas.append("  " + " | ".join(f"{i} -> {q}x" for i, q in efeitos.most_common(12)))
    if nomes:
        linhas.append(f"CRIATURAS ({len(nomes)} com nome):")
        linhas.append("  " + ", ".join(sorted(set(nomes.values()))[:40]))
    return linhas


def _listar(blocos, filtro, de, ate, limite):
    nomes = _nomes(blocos)
    jogador = _quem_grave(blocos)
    linhas = []
    total = 0
    for evento in _eventos(blocos):
        quando = evento.get("_quando", 0) / 1000.0
        if de is not None and quando < de:
            continue
        if ate is not None and quando > ate:
            continue
        tipo = evento.get("Event", "")
        if filtro and tipo not in filtro:
            continue
        total += 1
        if len(linhas) < limite:
            linhas.append(f"  {_hora(evento.get('_quando', 0))} {_descrever(evento, nomes, jogador)}")
    if not total:
        return ["", _motivo_do_vazio(blocos, filtro, de, ate)]
    if total > len(linhas):
        linhas.append(f"  ... e mais {total - len(linhas)} evento(s) fora do 'limite'.")
    return [""] + linhas


def _motivo_do_vazio(blocos, filtro, de, ate):
    if not filtro:
        return "Nada nesse intervalo."
    tipos = collections.Counter(evento.get("Event", "") for evento in _eventos(blocos))
    existentes = [nome for nome in filtro if tipos.get(nome)]
    if existentes:
        quantos = sum(tipos[nome] for nome in existentes)
        return (f"O filtro '{', '.join(existentes)}' existe nesta gravacao ({quantos} evento(s)), "
                f"mas nenhum cai dentro do intervalo pedido.")
    pedidos = ", ".join(filtro)
    parecidos = [tipo for tipo in tipos if any(p.lower() in tipo.lower() for p in filtro)]
    sugestao = ", ".join(parecidos[:6]) or ", ".join(tipo for tipo, _ in tipos.most_common(6))
    return (f"'{pedidos}' nao e nome de evento desta gravacao - em 'evento' o nome tem de ser exato "
            f"(ex: NumberEffectPopped). Para familias use 'grupo' (dano, efeito, vida, chat, loot, "
            f"magia, movimento, velocidade, criatura). Nomes desta gravacao que existem: {sugestao}.")


def _descrever(evento, nomes, jogador):
    tipo = evento.get("Event", "?")
    if tipo == "NumberEffectPopped":
        onde = _ponto(evento.get("Position"))
        return f"numero {evento.get('Value')} cor {evento.get('Color')} em {onde}"
    if tipo == "GraphicalEffectPopped":
        return f"efeito id {evento.get('Id')} em {_ponto(evento.get('Position'))}"
    if tipo == "CreatureHealthUpdated":
        return f"vida {_nome(nomes, evento.get('CreatureId'))}: {evento.get('Health')}%"
    if tipo == "PlayerDataUpdated":
        return (
            f"jogador vida {evento.get('Health')}/{evento.get('MaxHealth')} "
            f"mana {evento.get('Mana')}/{evento.get('MaxMana')} exp {evento.get('Experience')} "
            f"nivel {evento.get('Level')} ml {evento.get('MagicLevel')}"
        )
    if tipo == "MissileFired":
        return f"missil id {evento.get('Id')} de {_ponto(evento.get('Origin'))} a {_ponto(evento.get('Target'))}"
    if tipo in ("CreatureSpoke", "CreatureSpokeOnMap"):
        autor = evento.get("AuthorName") or _nome(nomes, evento.get("CreatureId"))
        marca = "" if autor == jogador else f" [{autor}]"
        return f"fala ({evento.get('Mode')}){marca}: {evento.get('Message')}"
    if tipo == "StatusMessageReceived":
        return f"aviso ({evento.get('Mode')}): {evento.get('Message')}"
    if tipo in ("CreatureSeen", "CreatureRemoved"):
        return f"{tipo} {evento.get('Name') or _nome(nomes, evento.get('CreatureId'))}"
    if tipo in ("CreatureMoved", "PlayerMoved"):
        alvo = evento.get("To") if tipo == "CreatureMoved" else evento.get("Position")
        return f"{tipo} para {_ponto(alvo)}"
    if tipo.startswith("Container"):
        item = evento.get("Item") or {}
        identificador = item.get("ItemId") if isinstance(item, dict) else None
        return f"{tipo} item {identificador} no contentor {evento.get('ContainerId')}"
    return f"{tipo} {json.dumps(evento, ensure_ascii=False)[:180]}"


def _eventos(blocos):
    for bloco in blocos:
        quando = bloco.get("Timestamp", 0)
        for evento in bloco.get("Events", []) or []:
            if isinstance(evento, dict):
                evento["_quando"] = quando
                yield evento


def _nomes(blocos):
    nomes = {}
    for evento in _eventos(blocos):
        if evento.get("Event") == "CreatureSeen" and evento.get("Name"):
            nomes[evento.get("CreatureId")] = evento["Name"]
    return nomes


def _loot_dos_corpos(blocos, alvo):
    """Soma o conteudo dos corpos abertos: frequencia de cada item e pilhas de ouro."""
    nomes = _nomes_de_itens()
    procurado = alvo.lower()
    todos = procurado in ("todos", "*")
    por_id = procurado.isdigit()
    corpos = []
    conhecidos = collections.Counter()
    for evento in _eventos(blocos):
        if evento.get("Event") != "ContainerOpened" or not evento.get("Items"):
            continue
        nome = str(evento.get("ContainerName") or "")
        if not nome.lower().startswith("dead"):
            continue
        identificador = (evento.get("ContainerItem") or {}).get("ItemId")
        conhecidos[(nome, identificador)] += 1
        if todos:
            corpos.append(evento)
        elif por_id and str(identificador) == procurado:
            corpos.append(evento)
        elif not por_id and procurado in nome.lower():
            corpos.append(evento)
    if not corpos:
        linhas = ["", f"LOOT: nenhum corpo aberto com '{alvo}' nesta gravacao."]
        if conhecidos:
            linhas.append("  corpos que existem (nome, id do corpo, vezes):")
            for (nome, identificador), vezes in conhecidos.most_common():
                linhas.append(f"    {nome} · id {identificador} · {vezes}")
        return linhas
    variados = collections.Counter((e.get("ContainerItem") or {}).get("ItemId") for e in corpos)
    if not por_id and len(variados) > 1:
        linhas = ["", f"LOOT: '{alvo}' tem {len(variados)} corpos diferentes na gravacao "
                  f"(o cliente da o mesmo nome a todos). Passe o id para escolher:"]
        for identificador, vezes in variados.most_common():
            linhas.append(f"    id {identificador} · {vezes} corpo(s) · {nomes.get(identificador, '?')}")
        return linhas

    abertos = [e for e in _eventos(blocos) if e.get("Event") == "ContainerOpened"]

    def itens_de(evento):
        return [item for linha in (evento.get("Items") or []) for item in linha]

    def eh_saco(evento):
        return (evento.get("ContainerItem") or {}).get("ItemId") == SACO_DE_LOOT

    no_corpo = collections.Counter()
    no_saco = collections.Counter()
    ouro_corpo = []
    ouro_saco = []
    com_saco = 0
    sacos_vazios = 0
    total_corpo = 0
    total_saco = 0
    for evento in corpos:
        topos = itens_de(evento)
        tem_saco = any(item.get("ItemId") == SACO_DE_LOOT for item in topos)
        for item in topos:
            if item.get("ItemId") == SACO_DE_LOOT:
                continue
            no_corpo[item.get("ItemId")] += 1
            total_corpo += 1
            if item.get("ItemId") == OURO:
                ouro_corpo.append(item.get("Count") or 1)
        if not tem_saco:
            continue
        posicao = abertos.index(evento)
        saco = next((x for x in abertos[posicao + 1:posicao + 8] if eh_saco(x)), None)
        if saco is None:
            sacos_vazios += 1
            continue
        dentro = itens_de(saco)
        if not dentro:
            sacos_vazios += 1
            continue
        com_saco += 1
        for item in dentro:
            no_saco[item.get("ItemId")] += 1
            total_saco += 1
            if item.get("ItemId") == OURO:
                ouro_saco.append(item.get("Count") or 1)

    linhas = ["", f"LOOT: {len(corpos)} corpos de '{alvo}' · {com_saco} com saco "
              f"({100.0 * com_saco / len(corpos):.1f}%) · {sacos_vazios} saco(s) vazio(s)"]

    def tabela(titulo, contagem, base, ouro, extra=""):
        if not contagem and not ouro:
            return
        linhas.append("")
        linhas.append(f"  {titulo} (de {base}{extra}):")
        linhas.append(f"    {'item':32s} {'vezes':>6s} {'%':>7s}")
        for identificador, vezes in contagem.most_common():
            nome = nomes.get(identificador, "?")
            linhas.append(f"    {nome[:30] + ' (' + str(identificador) + ')':32s} "
                          f"{vezes:6d} {100.0 * vezes / base:6.1f}%")
        if ouro:
            linhas.append(f"    OURO: {len(ouro)} pilhas · media {sum(ouro) / len(ouro):.1f} "
                          f"· {sum(ouro) / base:.2f} por corpo · maior {max(ouro)} "
                          f"· valores {sorted(ouro, reverse=True)[:12]}")

    tabela("NO CORPO", no_corpo, len(corpos), ouro_corpo)
    tabela("DENTRO DO SACO", no_saco, max(com_saco, 1), ouro_saco, f" {com_saco} com saco")
    linhas.append("")
    linhas.append(f"  itens por corpo: {total_corpo / len(corpos):.2f} fora + "
                  f"{total_saco / len(corpos):.2f} no saco = "
                  f"{(total_corpo + total_saco) / len(corpos):.2f}")
    return linhas


def _nomes_de_itens():
    """id -> nome, lido do items.xml mais proximo da raiz do projeto."""
    if "itens" in _CACHE:
        return _CACHE["itens"]
    nomes = {}
    for alvo in ("docs/projetos/Tibia74/Server/data/items/items.xml",
                 "Server/data/items/items.xml"):
        try:
            devolvido = resolver_caminho(alvo)
        except Exception:
            continue
        caminho = devolvido[0] if isinstance(devolvido, tuple) else devolvido
        if not caminho or not os.path.isfile(caminho):
            continue
        try:
            with open(caminho, encoding="utf-8", errors="replace") as fh:
                texto = fh.read()
        except OSError:
            continue
        for achado in re.finditer(r'<item\s+id="(\d+)"[^>]*?\bname="([^"]*)"', texto):
            nomes[int(achado.group(1))] = achado.group(2)
        if nomes:
            break
    _CACHE["itens"] = nomes
    return nomes


def _quem_grave(blocos):
    jogador = None
    nomes = {}
    for evento in _eventos(blocos):
        if evento.get("Event") == "WorldInitialized":
            jogador = evento.get("PlayerId")
        elif evento.get("Event") == "CreatureSeen" and evento.get("Name"):
            nomes[evento.get("CreatureId")] = evento["Name"]
    return nomes.get(jogador, "")


def _nome(nomes, identificador):
    if identificador is None:
        return "?"
    return nomes.get(identificador) or f"id {identificador}"


def _ponto(posicao):
    if not isinstance(posicao, dict):
        return "(?)"
    return f"({posicao.get('X')},{posicao.get('Y')},{posicao.get('Z')})"


def _duracao(blocos):
    if not blocos:
        return 0.0
    return float(blocos[-1].get("Timestamp", 0)) / 1000.0


def _hora(milissegundos):
    total = float(milissegundos) / 1000.0
    minutos = int(total // 60)
    return f"{minutos}:{total - minutos * 60:05.2f}"


def _bytes(tamanho):
    if tamanho < 1024:
        return f"{tamanho} B"
    if tamanho < 1024 * 1024:
        return f"{tamanho / 1024:.0f} KB"
    return f"{tamanho / (1024 * 1024):.1f} MB"


def _filtro(grupo, evento):
    if str(evento or "").strip():
        return (str(evento).strip(),)
    nome = str(grupo or "").strip().lower()
    return GRUPOS.get(nome, ())


def _janela(inicio, fim):
    return _instante(inicio), _instante(fim)


def _instante(texto):
    valor = str(texto or "").strip()
    if not valor:
        return None
    if ":" in valor:
        minutos, _, segundos = valor.partition(":")
        try:
            return float(minutos) * 60 + float(segundos)
        except ValueError:
            return None
    try:
        return float(valor.replace(",", "."))
    except ValueError:
        return None


def _teto(limite):
    try:
        return max(1, min(1000, int(limite)))
    except (TypeError, ValueError):
        return TETO_DE_LINHAS
