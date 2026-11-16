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
SACOS_DE_LOOT = frozenset({1987, 1993})
OURO = 2148
PREFIXOS_DE_CORPO = ("dead ", "slain ", "remains ")
MOCHILAS_DO_JOGADOR = frozenset(range(1988, 2005))
JANELA_DO_CORPO = 15.0
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
        "varrer": {
            "tipo": "STRING",
            "desc": "NAO abre uma gravacao: varre TODAS as gravacoes da pasta e diz quais tem "
            "corpos daquele monstro, com quantos cada uma. Aceita o nome ('demon') ou o id do "
            "corpo. Le cada ficheiro uma vez e guarda o resumo em cache (data/indice_recs.json), "
            "por isso a primeira chamada demora e as seguintes sao instantaneas. E o caminho "
            "para escolher QUAL gravacao abrir antes de analisar um monstro.",
            "padrao": "",
        },
        "gravacao": {
            "tipo": "STRING",
            "desc": "Nome da gravacao ('dlsolo.rec' ou so 'dlsolo') ou caminho completo. Sem 'pasta', "
            "procura nas pastas de gravacoes que o Painel de Controlo tem registadas. Nao e preciso "
            "quando se usa 'varrer'.",
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
def tool_ler_rec(gravacao="", pasta="", inicio="", fim="", grupo="", evento="", limite=TETO_DE_LINHAS, terreno=False, loot="", varrer=""):
    if str(varrer or "").strip():
        emit_event("executing", function=f"Varrendo as gravacoes por: {varrer}")
        return _varredura(str(varrer).strip())
    if not str(gravacao or "").strip():
        return "ERRO: diga qual gravacao abrir, ou use 'varrer' para procurar um monstro em todas."
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
        item = evento.get("ContainerItem") or {}
        identificador = item.get("ItemId") if isinstance(item, dict) else None
        nome = evento.get("ContainerName") or ""
        apelido = f" {nome}" if nome else ""
        return f"{tipo} item {identificador}{apelido} no contentor {evento.get('ContainerId')}"
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


def _lista_de_eventos(blocos):
    """Aceita blocos crus ou a lista de eventos ja achatada (com __t em segundos)."""
    if blocos and isinstance(blocos[0], dict) and "Event" in blocos[0]:
        return [dict(e, _quando=e.get("_quando") or (e.get("__t") or 0) * 1000) for e in blocos]
    return list(_eventos(blocos))


def _loot_dos_corpos(blocos, alvo):
    """Soma o conteudo dos corpos abertos: frequencia de cada item e pilhas de ouro."""
    nomes = _nomes_de_itens()
    procurado = alvo.lower()
    todos = procurado in ("todos", "*")
    por_id = procurado.isdigit()
    eventos = _lista_de_eventos(blocos)
    corpos = []
    conhecidos = collections.Counter()
    for evento in eventos:
        if evento.get("Event") != "ContainerOpened":
            continue
        nome = _nome_de_corpo(evento)
        if not nome:
            continue
        identificador = (evento.get("ContainerItem") or {}).get("ItemId")
        conhecidos[(nome, identificador)] += 1
        if todos:
            corpos.append(evento)
        elif por_id and str(identificador) == procurado:
            corpos.append(evento)
        elif not por_id and procurado in nome.lower():
            corpos.append(evento)
    nota = ""
    if not corpos and not todos and not por_id:
        corpo = _corpo_do_monstro(alvo)
        if corpo is not None:
            for evento in eventos:
                if evento.get("Event") != "ContainerOpened" or not evento.get("Items"):
                    continue
                if not _nome_de_corpo(evento):
                    continue
                if str((evento.get("ContainerItem") or {}).get("ItemId")) == str(corpo):
                    corpos.append(evento)
            if corpos:
                nota = f" (pelo corpo {corpo}, lido do XML do monstro)"
    corpo_id = None
    if por_id:
        corpo_id = int(alvo) if alvo.isdigit() else None
    elif not todos:
        corpo_id = _corpo_do_monstro(alvo)
    if not corpos:
        linhas = ["", f"LOOT: nenhum corpo aberto com '{alvo}' nesta gravacao."]
        if conhecidos:
            linhas.append("  corpos que existem (nome, id do corpo, vezes):")
            for (nome, identificador), vezes in conhecidos.most_common():
                linhas.append(f"    {nome} · id {identificador} · {vezes}")
        return linhas
    corpos = _sem_reaberturas(corpos)
    variados = collections.Counter((e.get("ContainerItem") or {}).get("ItemId") for e in corpos)
    if not por_id and len(variados) > 1:
        linhas = ["", f"LOOT: '{alvo}' tem {len(variados)} corpos diferentes na gravacao "
                  f"(o cliente da o mesmo nome a todos). Passe o id para escolher:"]
        for identificador, vezes in variados.most_common():
            linhas.append(f"    id {identificador} · {vezes} corpo(s) · {nomes.get(identificador, '?')}")
        return linhas

    separacao = []
    if corpo_id and not por_id:
        corpos, separacao = _separar_por_assinatura(corpos, alvo, corpo_id)
        if not corpos:
            return (["", f"LOOT: nenhum corpo de '{alvo}' sobrou depois de separar o corpo "
                         f"partilhado (id {corpo_id}) pela assinatura do loot (a separacao "
                         f"atribuiu-os a outros monstros ou a jogadores):"] + separacao)

    abertos = [e for e in eventos if e.get("Event") == "ContainerOpened"]
    posicoes = {id(e): i for i, e in enumerate(abertos)}

    def itens_de(evento):
        return [item for linha in (evento.get("Items") or []) for item in linha]

    def saco_depois(posicao, evento):
        abertura = (evento.get("_quando") or 0) / 1000.0
        for seguinte in abertos[posicao + 1:posicao + 8]:
            if _nome_de_corpo(seguinte):
                break
            if (seguinte.get("_quando") or 0) / 1000.0 - abertura > JANELA_DO_CORPO:
                break
            if (seguinte.get("ContainerItem") or {}).get("ItemId") in MOCHILAS_DO_JOGADOR:
                continue
            return seguinte
        return None

    no_corpo = collections.Counter()
    no_saco = collections.Counter()
    ouro_corpo = []
    ouro_saco = []
    com_saco = 0
    sacos_vazios = 0
    total_corpo = 0
    total_saco = 0
    com_ouro_corpo = 0
    com_ouro_saco = 0
    for evento in corpos:
        topos = itens_de(evento)
        if any(item.get("ItemId") == OURO for item in topos):
            com_ouro_corpo += 1
        tem_saco = any(item.get("ItemId") in SACOS_DE_LOOT for item in topos)
        for item in topos:
            if item.get("ItemId") in SACOS_DE_LOOT:
                continue
            if item.get("ItemId") == OURO:
                ouro_corpo.append(item.get("Count") or 1)
                continue
            no_corpo[item.get("ItemId")] += 1
            total_corpo += 1
        if not tem_saco:
            continue
        posicao = posicoes.get(id(evento), -1)
        saco = saco_depois(posicao, evento) if posicao >= 0 else None
        if saco is None:
            sacos_vazios += 1
            continue
        dentro = itens_de(saco)
        if not dentro:
            sacos_vazios += 1
            continue
        com_saco += 1
        if any(item.get("ItemId") == OURO for item in dentro):
            com_ouro_saco += 1
        for item in dentro:
            if item.get("ItemId") == OURO:
                ouro_saco.append(item.get("Count") or 1)
                continue
            no_saco[item.get("ItemId")] += 1
            total_saco += 1

    vazios = sum(1 for evento in corpos if not itens_de(evento))
    linhas = ["", f"LOOT: {len(corpos)} corpos de '{alvo}'{nota} · {com_saco} com saco "
              f"({100.0 * com_saco / len(corpos):.1f}%) · {sacos_vazios} saco(s) vazio(s) "
              f"· {vazios} corpo(s) sem nada"]
    linhas.extend(separacao)

    def tabela(titulo, contagem, base, ouro, extra="", absoluto=None, com_ouro=0):
        if not contagem and not ouro:
            return
        linhas.append("")
        linhas.append(f"  {titulo} (de {base}{extra}):")
        cabeca = f"    {'item':32s} {'vezes':>6s} {'%':>7s}"
        linhas.append(cabeca + (f" {'% por corpo':>12s}" if absoluto else ""))
        for identificador, vezes in contagem.most_common():
            nome = nomes.get(identificador, "?")
            linha = (f"    {nome[:30] + ' (' + str(identificador) + ')':32s} "
                     f"{vezes:6d} {100.0 * vezes / base:6.1f}%")
            if absoluto:
                linha += f" {100.0 * vezes / absoluto:11.1f}%"
            linhas.append(linha)
        if ouro:
            universo = absoluto or base
            linhas.append(f"    OURO: {len(ouro)} pilhas em {100.0 * com_ouro / universo:.1f}% dos "
                          f"corpos · media {sum(ouro) / len(ouro):.1f} · "
                          f"{sum(ouro) / universo:.2f} por corpo · maior {max(ouro)} "
                          f"· valores {sorted(ouro, reverse=True)[:12]}")

    tabela("NO CORPO", no_corpo, len(corpos), ouro_corpo, com_ouro=com_ouro_corpo)
    tabela("DENTRO DO SACO", no_saco, max(com_saco, 1), ouro_saco,
           f" {com_saco} com saco", len(corpos), com_ouro_saco)
    linhas.append("")
    linhas.append(f"  itens por corpo: {total_corpo / len(corpos):.2f} fora + "
                  f"{total_saco / len(corpos):.2f} no saco = "
                  f"{(total_corpo + total_saco) / len(corpos):.2f} (sem ouro) · "
                  f"ouro {len(ouro_corpo) / len(corpos):.2f} pilhas fora + "
                  f"{len(ouro_saco) / len(corpos):.2f} no saco")

    nome_do_monstro = alvo
    if por_id:
        nome_do_monstro = _monstro_do_corpo(int(alvo)) or ""
    if not todos and nome_do_monstro:
        declarado = _loot_do_monstro(nome_do_monstro)
        if declarado:
            vistos = set(no_corpo) | set(no_saco)
            if ouro_corpo or ouro_saco:
                vistos.add(OURO)
            faltam = sorted(i for i in declarado if i not in vistos and i not in SACOS_DE_LOOT)
            sobram = sorted(i for i in vistos if i not in declarado)
            linhas.append("")
            linhas.append("  CRUZAMENTO com o <loot> do XML do monstro:")
            if faltam:
                linhas.append("    no XML e NUNCA vistos nesta gravacao (NAO apagar so por isto):")
                for identificador in faltam:
                    linhas.append(f"      {(nomes.get(identificador) or '?')[:30]} "
                                  f"({identificador}) · {declarado[identificador]}")
            else:
                linhas.append("    todos os itens do XML apareceram")
            if sobram:
                linhas.append("    vistos e NAO estao no XML:")
                for identificador in sobram:
                    linhas.append(f"      {(nomes.get(identificador) or '?')[:30]} ({identificador})")
    return linhas


def _nome_de_corpo(evento):
    nome = str(evento.get("ContainerName") or "").strip()
    if not nome.lower().startswith(PREFIXOS_DE_CORPO):
        return ""
    return nome


def _assinatura_do_corpo(evento):
    return frozenset(
        (item.get("ItemId"), item.get("Count") or 1)
        for linha in (evento.get("Items") or [])
        for item in linha
    )


def _sem_reaberturas(corpos):
    limpos = []
    ultimo = {}
    for evento in corpos:
        chave = (evento.get("ContainerId"), (evento.get("ContainerItem") or {}).get("ItemId"))
        quando = (evento.get("_quando") or 0) / 1000.0
        agora = _assinatura_do_corpo(evento)
        anterior = ultimo.get(chave)
        if anterior is not None and quando - anterior[0] < JANELA_DO_CORPO:
            antes = _assinatura_do_corpo(anterior[1])
            if agora <= antes:
                continue
            limpos[anterior[2]] = evento
            ultimo[chave] = (quando, evento, anterior[2])
            continue
        ultimo[chave] = (quando, evento, len(limpos))
        limpos.append(evento)
    return limpos


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


def _ficheiro_do_monstro(nome):
    try:
        devolvido = resolver_caminho("docs/projetos/Tibia74/Server/data/monster")
    except Exception:
        return None
    pasta = devolvido[0] if isinstance(devolvido, tuple) else devolvido
    if not pasta or not os.path.isdir(pasta):
        return None
    procurado = re.sub(r"\s+", " ", nome.strip()).lower()
    direto = os.path.join(pasta, procurado + ".xml")
    if os.path.isfile(direto):
        return direto
    for ficheiro in sorted(os.listdir(pasta)):
        if not ficheiro.lower().endswith(".xml"):
            continue
        caminho = os.path.join(pasta, ficheiro)
        try:
            with open(caminho, encoding="utf-8", errors="replace") as fh:
                cabeca = fh.read(800)
        except OSError:
            continue
        achado = re.search(r'<monster\s+name="([^"]*)"', cabeca)
        if achado and re.sub(r"\s+", " ", achado.group(1)).lower() == procurado:
            return caminho
    return None


def _corpo_do_monstro(nome):
    caminho = _ficheiro_do_monstro(nome)
    if not caminho:
        return None
    try:
        with open(caminho, encoding="utf-8", errors="replace") as fh:
            texto = fh.read()
    except OSError:
        return None
    achado = re.search(r'corpse="(\d+)"', texto)
    return int(achado.group(1)) if achado else None


def _monstro_do_corpo(corpo):
    """Nome do monstro cujo corpse= e este id (o inverso de _corpo_do_monstro)."""
    try:
        devolvido = resolver_caminho("docs/projetos/Tibia74/Server/data/monster")
    except Exception:
        return None
    pasta = devolvido[0] if isinstance(devolvido, tuple) else devolvido
    if not pasta or not os.path.isdir(pasta):
        return None
    for ficheiro in sorted(os.listdir(pasta)):
        if not ficheiro.lower().endswith(".xml"):
            continue
        try:
            with open(os.path.join(pasta, ficheiro), encoding="utf-8", errors="replace") as fh:
                texto = fh.read(4000)
        except OSError:
            continue
        if re.search(r'corpse="%d"' % corpo, texto):
            achado = re.search(r'<monster\s+name="([^"]*)"', texto)
            if achado:
                return achado.group(1)
    return None


def _monstros_do_corpo(corpo):
    """Todos os monstros cujo corpse= e este id: o mesmo corpo serve a varios."""
    if "corpos" not in _CACHE:
        indice = {}
        try:
            devolvido = resolver_caminho("docs/projetos/Tibia74/Server/data/monster")
        except Exception:
            devolvido = None
        pasta = devolvido[0] if isinstance(devolvido, tuple) else devolvido
        if pasta and os.path.isdir(pasta):
            for ficheiro in sorted(os.listdir(pasta)):
                if not ficheiro.lower().endswith(".xml"):
                    continue
                try:
                    with open(os.path.join(pasta, ficheiro), encoding="utf-8", errors="replace") as fh:
                        texto = fh.read(4000)
                except OSError:
                    continue
                achado_corpo = re.search(r'corpse="(\d+)"', texto)
                achado_nome = re.search(r'<monster\s+name="([^"]*)"', texto)
                if not achado_corpo or not achado_nome:
                    continue
                nome = re.sub(r"\s+", " ", achado_nome.group(1)).strip().lower()
                indice.setdefault(int(achado_corpo.group(1)), []).append(nome)
        _CACHE["corpos"] = indice
    return list(_CACHE["corpos"].get(corpo) or [])


def _itens_sem_saco(evento):
    return frozenset(
        item.get("ItemId")
        for linha in (evento.get("Items") or [])
        for item in linha
        if item.get("ItemId") not in SACOS_DE_LOOT and item.get("ItemId") != OURO
    )


def _separar_por_assinatura(corpos, alvo, corpo):
    """Separa os corpos de um id partilhado pelo monstro, pela cara do loot.

    Cada corpo e comparado com o <loot> de cada monstro que usa aquele id; fica
    com o que explica mais itens. Devolve (corpos do alvo, linhas do relatorio).
    """
    inquilinos = _monstros_do_corpo(corpo)
    alvo_normal = re.sub(r"\s+", " ", str(alvo or "").strip()).lower()
    if len(inquilinos) < 2 or alvo_normal not in inquilinos:
        return corpos, []
    declarados = {nome: set(_loot_do_monstro(nome)) for nome in inquilinos}
    meus = declarados.get(alvo_normal) or set()
    if not meus:
        return corpos, []
    dos_outros = set()
    for nome, itens in declarados.items():
        if nome != alvo_normal:
            dos_outros |= itens
    marcadores = meus - dos_outros
    grupos = collections.Counter()
    ficam = []
    for evento in corpos:
        itens = _itens_sem_saco(evento)
        if not itens:
            grupos["so ouro (indefinido)"] += 1
            ficam.append(evento)
            continue
        if marcadores & itens:
            grupos[alvo_normal] += 1
            ficam.append(evento)
            continue
        melhor, nota = None, 0.0
        for nome, declarado in declarados.items():
            if not declarado:
                continue
            valor = len(itens & declarado) / len(itens)
            if valor > nota:
                melhor, nota = nome, valor
        if melhor == alvo_normal:
            grupos[alvo_normal] += 1
            ficam.append(evento)
        elif melhor:
            grupos[melhor] += 1
        else:
            grupos["sem assinatura (jogador/outro)"] += 1
    linhas = ["", f"  CORPO PARTILHADO (id {corpo}) com: {', '.join(inquilinos)}",
              f"    separado pela assinatura do loot · {len(ficam)} de {len(corpos)} corpos ficam:"]
    for nome, quantos in grupos.most_common():
        linhas.append(f"      {nome[:30]:30s} {quantos:5d}")
    if marcadores:
        linhas.append("    marcadores (so este monstro declara): "
                      + ", ".join(str(i) for i in sorted(marcadores)))
    return ficam, linhas


def _loot_do_monstro(nome):
    """id -> 'corpo' ou 'saco', lido do <loot> do XML do monstro."""
    caminho = _ficheiro_do_monstro(nome)
    if not caminho:
        return {}
    try:
        with open(caminho, encoding="utf-8", errors="replace") as fh:
            texto = fh.read()
    except OSError:
        return {}
    bloco = re.search(r"<loot\b.*?</loot>", texto, re.S)
    if not bloco:
        return {}
    declarado = {}
    profundidade = 0
    for achado in re.finditer(r"<inside\b|</inside\b|<item\s+id=\"(\d+)\"", bloco.group(0)):
        pedaco = achado.group(0)
        if pedaco.startswith("<inside"):
            profundidade += 1
            continue
        if pedaco.startswith("</inside"):
            profundidade = max(0, profundidade - 1)
            continue
        identificador = int(achado.group(1))
        onde = "saco" if profundidade else "corpo"
        if declarado.get(identificador) != "corpo":
            declarado[identificador] = onde
    return declarado


INDICE_DE_GRAVACOES = "data/indice_recs.json"


def _caminho_do_indice():
    raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    caminho = os.path.join(raiz, *INDICE_DE_GRAVACOES.split("/"))
    if not os.path.isdir(os.path.dirname(caminho)):
        return ""
    return caminho


def _gravacoes_no_disco():
    achadas = {}
    for pasta in _pastas_conhecidas():
        if not os.path.isdir(pasta):
            continue
        try:
            nomes = os.listdir(pasta)
        except OSError:
            continue
        for nome in nomes:
            if not nome.lower().endswith(".rec"):
                continue
            caminho = os.path.join(pasta, nome)
            chave = os.path.normcase(os.path.abspath(caminho))
            if chave not in achadas:
                achadas[chave] = caminho
    return achadas


def _corpos_resumidos(blocos):
    """id do corpo -> nome, quantos e o que caiu no corpo e no saco."""
    eventos = _lista_de_eventos(blocos)
    abertos = [e for e in eventos if e.get("Event") == "ContainerOpened"]
    posicoes = {id(e): i for i, e in enumerate(abertos)}

    def itens_de(evento):
        return [item for linha in (evento.get("Items") or []) for item in linha]

    def saco_depois(posicao):
        for seguinte in abertos[posicao + 1:posicao + 8]:
            if _nome_de_corpo(seguinte):
                break
            if (seguinte.get("ContainerItem") or {}).get("ItemId") in MOCHILAS_DO_JOGADOR:
                continue
            return seguinte
        return None

    corpos = _sem_reaberturas([e for e in abertos if _nome_de_corpo(e)])
    resumo = {}
    for evento in corpos:
        identificador = (evento.get("ContainerItem") or {}).get("ItemId")
        if identificador is None:
            continue
        registo = resumo.setdefault(
            str(identificador),
            {"nome": _nome_de_corpo(evento), "n": 0, "corpo": collections.Counter(),
             "saco": collections.Counter(), "pilhas": []},
        )
        registo["n"] += 1
        topos = itens_de(evento)
        pilhas = [item.get("Count") or 1 for item in topos if item.get("ItemId") == OURO]
        for item in topos:
            if item.get("ItemId") in SACOS_DE_LOOT or item.get("ItemId") == OURO:
                continue
            registo["corpo"][str(item.get("ItemId"))] += 1
        if any(item.get("ItemId") in SACOS_DE_LOOT for item in topos):
            saco = saco_depois(posicoes.get(id(evento), -1))
            if saco is not None:
                for item in itens_de(saco):
                    if item.get("ItemId") == OURO:
                        pilhas.append(item.get("Count") or 1)
                        continue
                    if item.get("ItemId") in SACOS_DE_LOOT:
                        continue
                    registo["saco"][str(item.get("ItemId"))] += 1
        if pilhas:
            registo["pilhas"].append(pilhas)
    return {
        chave: {"nome": r["nome"], "n": r["n"], "corpo": dict(r["corpo"]),
                "saco": dict(r["saco"]), "pilhas": r["pilhas"][:300]}
        for chave, r in resumo.items()
    }


def indexar_gravacoes(progresso=None, refazer=False):
    """Le o loot de todas as gravacoes e guarda o resumo em cache."""
    caminho_indice = _caminho_do_indice()
    if not caminho_indice:
        return {}, "nao consegui resolver o caminho do indice"
    indice = {}
    try:
        with open(caminho_indice, encoding="utf-8") as aberto:
            guardado = json.load(aberto)
        if isinstance(guardado, dict) and isinstance(guardado.get("gravacoes"), dict):
            indice = guardado["gravacoes"]
    except (OSError, ValueError):
        indice = {}

    miner = _achar_miner()
    if isinstance(miner, tuple):
        miner = miner[0]
    if not miner:
        return indice, "nao achei o miner.exe"
    clientes = _achar_clientes(miner)
    if not clientes:
        return indice, "nao achei os clientes do miner"

    por_ler = []
    for chave, caminho in sorted(_gravacoes_no_disco().items()):
        try:
            stat = os.stat(caminho)
        except OSError:
            continue
        anterior = indice.get(chave) or {}
        if not refazer and anterior.get("mtime") == stat.st_mtime and anterior.get("bytes") == stat.st_size:
            continue
        por_ler.append((chave, caminho, stat))

    lidos = 0
    falhados = 0
    for posicao, (chave, caminho, stat) in enumerate(por_ler, 1):
        if progresso:
            progresso(posicao, len(por_ler), os.path.basename(caminho))
        try:
            bruto, _ = _ler_bruto(caminho, miner, clientes, False)
        except RuntimeError:
            falhados += 1
            indice[chave] = {"mtime": stat.st_mtime, "bytes": stat.st_size,
                             "nome": os.path.basename(caminho), "erro": True}
            continue
        blocos = bruto if isinstance(bruto, list) else []
        indice[chave] = {
            "mtime": stat.st_mtime,
            "bytes": stat.st_size,
            "nome": os.path.basename(caminho),
            "segundos": round(_duracao(blocos), 1),
            "corpos": _corpos_resumidos(blocos),
        }
        lidos += 1
        if lidos % 25 == 0:
            _gravar_indice(indice, caminho_indice)

    if lidos or falhados:
        _gravar_indice(indice, caminho_indice)
    return indice, f"{lidos} lidas agora, {falhados} falharam, {len(indice)} no indice"


def _gravar_indice(indice, caminho):
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho + ".tmp", "w", encoding="utf-8") as saida:
            json.dump({"gravacoes": indice}, saida, ensure_ascii=False)
        os.replace(caminho + ".tmp", caminho)
    except OSError:
        pass


def _corpos_do_nome(procurado):
    """Ids de corpo cujo monstro casa com o nome - o 'varrer' aceita o monstro, nao so o corpo."""
    _monstros_do_corpo(0)
    return {
        corpo
        for corpo, nomes in (_CACHE.get("corpos") or {}).items()
        if any(procurado in nome for nome in nomes)
    }


def _varredura(termo):
    """Todas as gravacoes que tem um corpo cujo nome casa com o termo."""
    indice, nota = indexar_gravacoes()
    procurado = termo.lower()
    por_id = procurado.isdigit()
    ids_do_monstro = set() if por_id else _corpos_do_nome(procurado)
    achados = []
    for chave, dados in indice.items():
        if dados.get("erro"):
            continue
        for identificador, corpo in (dados.get("corpos") or {}).items():
            nome = str(corpo.get("nome") or "").lower()
            if (identificador if por_id else nome).find(procurado) < 0:
                try:
                    if int(identificador) not in ids_do_monstro:
                        continue
                except (TypeError, ValueError):
                    continue
            achados.append((dados.get("nome") or os.path.basename(chave), nome,
                            corpo.get("n") or 0, dados.get("segundos") or 0, identificador))
    achados.sort(key=lambda x: -x[2])
    if not achados:
        linhas = ["", f"VARREDURA: nenhuma gravacao com '{termo}' no indice ({nota})."]
        nomes = collections.Counter(
            str(c.get("nome")) for d in indice.values() if not d.get("erro")
            for c in (d.get("corpos") or {}).values()
        )
        if nomes:
            linhas.append("  corpos que o indice conhece:")
            for nome, vezes in nomes.most_common(40):
                linhas.append(f"    {nome[:44]:44s} {vezes:5d} gravacao(oes)")
        return "\n".join(linhas)
    total = sum(a[2] for a in achados)
    via = ""
    if ids_do_monstro:
        via = " · casou pelo MONSTRO, corpo(s) %s" % sorted(ids_do_monstro)
    linhas = ["", f"VARREDURA: '{termo}' em {len(achados)} gravacao(oes) · {total} corpo(s)"
                  f"{via} · {nota}", ""]
    linhas.append(f"    {'corpos':>6s} {'min':>8s}  arquivo")
    for nome_arquivo, _nome_corpo, quantos, segundos, _ident in achados[:60]:
        linhas.append(f"    {quantos:6d} {segundos / 60:7.1f}  {nome_arquivo}")
    if len(achados) > 60:
        linhas.append(f"    ... e mais {len(achados) - 60}")
    vistos = set()
    for achado in achados:
        try:
            vistos.add(int(achado[4]))
        except (TypeError, ValueError):
            continue
    partilhados = {c: _monstros_do_corpo(c) for c in vistos}
    partilhados = {c: m for c, m in partilhados.items() if len(m) > 1}
    if partilhados:
        linhas.append("")
        linhas.append("  CORPO PARTILHADO (a contagem mistura estes monstros) - use loot=<monstro> numa")
        linhas.append("  gravacao para separar pela assinatura:")
        for corpo, nomes in sorted(partilhados.items()):
            linhas.append(f"    {corpo}: {', '.join(nomes)}")
    return "\n".join(linhas)


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


if __name__ == "__main__":
    def _progresso(posicao, total, nome):
        if posicao % 25 == 0 or posicao == total:
            print(f"[{posicao}/{total}] {nome}", flush=True)

    _, relato = indexar_gravacoes(progresso=_progresso, refazer="--refazer" in os.sys.argv)
    print(relato)
