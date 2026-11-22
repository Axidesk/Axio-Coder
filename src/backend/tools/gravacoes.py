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
VERSAO_DOS_ITENS = "7.4"
RECEITA_DA_LEITURA = """=== COMO LER A GRAVACAO (a receita .mon -> XML completa esta na descricao de tool_validar_monstro) ===
Nem o .mon, nem o video, nem a wiki sao a verdade sozinhos: cruzar sempre e dizer de onde veio cada facto.

LUGAR DO LOOT: ler o loot em DUAS tabelas - NO CORPO e DENTRO DO SACO - e somar corpo+saco antes de
comparar com o numero de entradas do .mon. A mochila do JOGADOR aberta logo depois do corpo NAO e a
bag do monstro (descartar). Bag vazia nao cai, logo a linha da bag no XML vai a chance="100000".
Ouro nunca se calibra pelo video (o jogador saqueia): serve para saber ONDE a pilha cai.

ITEM INVENTADO: item que aparece no XML e nao sai em centenas de corpos deixa de ser duvida de
amostra e passa a ser prova (legion helmet a 10% em 162 corpos = 1 em dez milhoes). E o caminho para
limpar o datapack 7.4, que tem loot a mais.

XP: so vale a gravacao em que o jogador mata SO aquele monstro - morte em area soma varios de uma vez
e falseia o salto. Quando o .mon e o video brigam, o video manda.

INTERVALO: nao existe no .mon. Mede-se por bicho: missil pela posicao de ORIGEM (o bicho parado mantem
o tile) e cura pelo id de criatura que a vida acompanha. Um ciclo de 2s nunca produz dois eventos a 1s
do mesmo bicho - se aparecerem, o ciclo e 1s. O motor tem contadores separados para ataque e defesa,
por isso o mesmo monstro pode atirar a 1s e curar a 2s.

NOME DO MONSTRO: usar o nome exato. Nomes que sao prefixo de outros (elf/elf scout/elf arcanist,
dragon/dragon lord, demon/demon skeleton) somam dois bichos numa tabela so quando casam por pedaco.

VERSAO DA GRAVACAO: as pastas TibiCAM/7.3 tem numeracao de ITEM diferente da 7.4. Ler uma 7.3 com a
tabela do 7.4 inventa item (saiu 'cot', 'counter', 'pool', 'teddy bear' em corpos de goblin). As 7.3
ficam fora de qualquer soma; numa gravacao 7.3 isolada o loot nem e lido.

ONDE ESTA CADA COISA: corpo = ContainerOpened com nome 'dead/slain/remains'. Saco do monstro = o
primeiro SACO DE LOOT (1987/1993) aberto depois do corpo, antes do proximo corpo, usado UMA vez.
Mochila do jogador e container de cenario (armario, cama, bau do depot, caixa) NUNCA sao saco - o
relatorio diz quantos foram ignorados. Item que o items.otb marca como FIXO e lixo de leitura e cai
fora com o nome dito."""
SACO_DE_LOOT = 1987
SACOS_DE_LOOT = frozenset({1987, 1993})
OURO = 2148
PREFIXOS_DE_CORPO = ("dead ", "slain ", "remains ")
MOCHILAS_DO_JOGADOR = frozenset(range(1988, 2005))
MEXER_NO_SACO = ("ContainerRemovedItem", "ContainerAddedItem", "ContainerTransformedItem")
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
    "efeito no mesmo tile, que e o que permite julgar isso.\n\n" + RECEITA_DA_LEITURA,
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
        "raca": {
            "tipo": "STRING",
            "desc": "Mede a RACE (o sangue) de um monstro na gravacao, atribuindo cada numero de dano "
            "e cada efeito a criatura que estava naquele tile. E a PROVA contra o campo Blood do .mon, "
            "que e quem manda quando nao ha gravacao. Como a ligacao e feita: o CreatureMoved vem com "
            "CreatureId=0 e NAO serve; quem traz id E posicao e o TileObjectAdded (Object.CreatureId + "
            "TilePosition), que sai so com terreno=true - por isso este pedido liga o terreno sozinho. "
            "O motor escolhe a cor do numero pela race (game.cpp:4251): TEXTCOLOR_RED=180 blood, "
            "TEXTCOLOR_LIGHTGREY=129 undead, TEXTCOLOR_LIGHTGREEN=30 venom, TEXTCOLOR_ORANGE=198 fire, "
            "TEXTCOLOR_LIGHTBLUE=35 energy, 215 experiencia. O EFEITO confirma e desempata: 9 hit_area = "
            "undead, 16 poison = venom, 0 draw_blood = blood OU fire (ai decide a cor, 180 vs 198). "
            "Licao medida: o beholder deu 9 numeros vermelhos em 11 e o vampire 4 efeitos 9 em 4 - o "
            "primeiro provou blood contra o VENOM do datapack, o segundo provou undead. Amostra pequena "
            "engana: rode em 2-3 gravacoes antes de mudar o XML, e lembre que numero laranja ou verde "
            "no tile do monstro pode ser dano elemental de outra fonte, nao a race dele.",
            "padrao": "",
        },
        "dano": {
            "tipo": "STRING",
            "desc": "Mede o dano que o JOGADOR LEVA, separado por AUTOR e por TIPO (a cor do numero), "
            "com os valores e o ritmo de cada um. E o caminho para saber o que um monstro faz de "
            "verdade sem escrever um leitor de log: com 'green djinn' responde de uma vez quais "
            "magias ele tem, de quanto e de quanto em quanto tempo. Nome do monstro filtra por "
            "autor; 'todos' mostra a gravacao inteira. O autor '(sem autor)' e o dano de CONDICAO "
            "(energia, veneno, fogo), que o cliente NAO atribui a ninguem - e onde a maioria dos "
            "enganos nasce. O numero e casado com a mensagem por VALOR EXATO e menos de 300ms: "
            "sem isso, dois numeros no mesmo instante (fogo + dreno) trocam-se e o tipo sai errado. "
            "As cores sao as do motor (game.cpp): 30 veneno, 35 energia, 198 fogo, 180 sangue/dreno, "
            "129 undead. Use 2-3 gravacoes antes de concluir: amostra pequena engana.",
            "padrao": "",
        },
        "area": {
            "tipo": "STRING",
            "desc": "Agrupa os numeros de dano pelo INSTANTE e responde 'esta magia sorteia o dano "
            "uma vez por conjuracao ou uma por alvo?': mostra cada instante com 2+ criaturas feridas "
            "ao mesmo tempo, os valores e se sao TODOS IGUAIS. Valor igual em todas as criaturas = "
            "sorteio unico por conjuracao (e o que o original faz: a magia do minotaur mage deu 62 em "
            "5 criaturas, a do demon 78 em 5); valores espalhados = sorteio por alvo. Aceita o id de "
            "um efeito grafico ('7' = fogo em area, '5' = explosion) para olhar so os instantes "
            "daquela magia, ou 'todos'. Ignora instantes com mais de uma cor, porque duas magias "
            "diferentes caindo no mesmo segundo nao se comparam.",
            "padrao": "",
        },
        "velocidade": {
            "tipo": "STRING",
            "desc": "Mede a velocidade REAL das criaturas pela serie de CreatureSpeedUpdated da "
            "gravacao - e o unico jeito de ver o speedchange a acontecer. Devolve, por criatura, a "
            "velocidade sem efeito (a mais frequente), o minimo e o maximo e a variacao em percentagem "
            "e por-mil. Nome do monstro filtra ('giant spider'); 'todos' mostra a gravacao inteira. "
            "MEDIDO a 2026-11-22 e provado contra o .mon: a velocidade sem efeito e exatamente "
            "2*GoStrength+80 (dragon 170, ghoul 144, cyclops 190, minotaur 168, gargoyle 200, "
            "bonebeast 218, rotworm 116) e a criatura que usa haste sobe em faixa - giant spider "
            "240 -> 336..352, behemoth 340 -> 444..470, scarab 160 -> 192..200. O valor da base "
            "NAO muda com o piso do mapa: o piso entra no passo, nao na velocidade. So aparece a "
            "criatura que o servidor mandou atualizar; sem leitura nao se conclui nada.",
            "padrao": "",
        },
        "terreno": {
            "tipo": "BOOLEAN",
            "desc": "Ler tambem o terreno do mapa (muito mais lento e o dobro do tamanho). Normalmente nao.",
            "padrao": False,
        },
    },
)
def tool_ler_rec(gravacao="", pasta="", inicio="", fim="", grupo="", evento="", limite=TETO_DE_LINHAS, terreno=False, loot="", varrer="", raca="", dano="", area="", velocidade=""):
    if str(varrer or "").strip():
        if str(loot or "").strip():
            emit_event("executing", function=f"Somando o loot de: {varrer}")
            return _loot_somado(str(varrer).strip())
        emit_event("executing", function=f"Varrendo as gravacoes por: {varrer}")
        return _varredura(str(varrer).strip())
    if str(raca or "").strip():
        terreno = True
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
    versao_da_gravacao = _normalizar_versao(usado) or _normalizar_versao(_versao_da_gravacao(caminho))
    if versao_da_gravacao and versao_da_gravacao != VERSAO_DOS_ITENS:
        linhas.append(
            f"  ATENCAO: gravacao do cliente {versao_da_gravacao} (lida com o cliente {usado}). "
            f"A numeracao dos itens dela NAO e "
            f"a do items.xml {VERSAO_DOS_ITENS}: lida com esta tabela, ela inventa item "
            f"(foi assim que apareceu mobilia dentro do loot). Nao serve para decidir item, "
            f"chance nem lugar."
        )
        if str(loot or "").strip():
            linhas.append("  O loot desta gravacao nao foi lido - use uma gravacao do 7.4, ou o "
                          "'varrer', que ja exclui as de 7.3.")
            return "\n".join(linhas)
    if alternativas:
        linhas.append("  OUTRAS COM ESSE NOME: " + " | ".join(alternativas))
    if str(raca or "").strip():
        linhas += _raca_das_criaturas(blocos, str(raca).strip().lower())
        return "\n".join(linhas)
    if str(dano or "").strip():
        emit_event("executing", function=f"Medindo o dano de: {dano}")
        linhas += _perfil_de_dano(blocos, str(dano).strip())
        return "\n".join(linhas)
    if str(velocidade or "").strip():
        emit_event("executing", function=f"Medindo a velocidade de: {velocidade}")
        linhas += _velocidade_das_criaturas(blocos, str(velocidade).strip().lower())
        return "\n".join(linhas)
    if str(area or "").strip():
        emit_event("executing", function="Agrupando o dano por instante")
        pedido = str(area).strip()
        linhas += _grupos_de_area(blocos, "" if pedido.lower() in ("todos", "todas") else pedido)
        return "\n".join(linhas)
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


def _achar_gravacao(pedido, pasta=""):
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


def _pastas_de_gravacoes(pasta=""):
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

_TETO_DA_CADEIA = 24


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


SANGUE_POR_EFEITO = {0: ('blood ou fire', 'draw_blood'), 9: ('undead', 'hit_area'), 16: ('venom', 'poison')}
SANGUE_POR_COR = {180: 'blood', 129: 'undead', 30: 'venom', 198: 'fire'}


def _raca_das_criaturas(blocos, pedido):
    """Atribui cada numero e cada efeito a criatura do tile e vota na race pelo que o motor pinta."""
    nomes, posicao, ocupante = {}, {}, {}
    efeitos = collections.defaultdict(collections.Counter)
    cores = collections.defaultdict(collections.Counter)
    for bloco in blocos:
        for evento in bloco.get("Events", []):
            tipo = evento.get("Event")
            if tipo == "CreatureSeen":
                nomes[evento.get("CreatureId")] = str(evento.get("Name") or "").lower()
            elif tipo == "TileObjectAdded":
                objeto = evento.get("Object") or {}
                criatura = objeto.get("CreatureId")
                if criatura is None:
                    continue
                ponto = _ponto(evento.get("TilePosition"))
                anterior = posicao.get(criatura)
                if anterior is not None and ocupante.get(anterior) == criatura:
                    ocupante.pop(anterior, None)
                posicao[criatura] = ponto
                ocupante[ponto] = criatura
            elif tipo in ("GraphicalEffectPopped", "NumberEffectPopped"):
                criatura = ocupante.get(_ponto(evento.get("Position")))
                if criatura is None:
                    continue
                nome = nomes.get(criatura, "")
                if not nome or (pedido and pedido not in nome):
                    continue
                if tipo == "GraphicalEffectPopped":
                    efeitos[nome][evento.get("Id")] += 1
                else:
                    cores[nome][evento.get("Color")] += 1

    if not efeitos and not cores:
        return [
            "",
            f"  Nenhum numero nem efeito atribuido a '{pedido}' nesta gravacao.",
            "  Confirme o nome exato do monstro (elf, elf scout e elf arcanist sao bichos diferentes)",
            "  e que a gravacao tem mesmo uma luta com ele.",
        ]
    linhas = ["", "  RACE PELA COR DO DANO E PELO EFEITO (game.cpp:4251)"]
    for nome in sorted(set(efeitos) | set(cores)):
        linhas.append(f"  {nome}:")
        if cores[nome]:
            total = sum(cores[nome].values())
            linhas.append("    numeros: " + ", ".join(
                f"cor {cor} {SANGUE_POR_COR.get(cor, '?')}={quantos} ({100 * quantos / total:.0f}%)"
                for cor, quantos in cores[nome].most_common(4)))
        if efeitos[nome]:
            linhas.append("    efeitos: " + ", ".join(
                f"{identificador} {SANGUE_POR_EFEITO.get(identificador, ('', 'outro'))[1]}={quantos}"
                for identificador, quantos in efeitos[nome].most_common(4)))
        linhas.append("    veredito: " + _veredito_da_raca(efeitos[nome], cores[nome]))
    linhas.append("  O .mon manda quando nao ha gravacao; com gravacao, e este veredito que vale.")
    return linhas


def _veredito_da_raca(efeitos, cores):
    """O efeito 9/16 vale o dobro da cor: so a race o produz, enquanto a cor de dano elemental engana."""
    votos = collections.Counter()
    for identificador, quantos in efeitos.items():
        if identificador == 9:
            votos['undead'] += 2 * quantos
        elif identificador == 16:
            votos['venom'] += 2 * quantos
    for cor, quantos in cores.items():
        if cor in SANGUE_POR_COR:
            votos[SANGUE_POR_COR[cor]] += quantos
    if not votos:
        return "sem sinal de acerto fisico (so dano elemental) - nao da para concluir a race"
    raca, peso = votos.most_common(1)[0]
    total = sum(votos.values())
    detalhe = (
        f"{peso} de {total} pontos, {100 * peso / total:.0f}%"
        f" - efeito 9/16 pesa o dobro da cor, porque so a race o produz"
    )
    if peso < 3:
        return (
            f"{raca} com amostra pequena ({detalhe}): rode noutra gravacao antes de mexer no XML"
        )
    return f"{raca} ({detalhe})"


def _velocidade_das_criaturas(blocos, pedido):
    """A velocidade que o servidor enviou, por criatura: a de base e a faixa que os feitiços abrem."""
    nomes, tipos = {}, {}
    for evento in _eventos(blocos):
        if evento.get("Event") == "CreatureSeen":
            nomes[evento.get("CreatureId")] = str(evento.get("Name") or "").strip().lower()
            tipos[evento.get("CreatureId")] = evento.get("Type") or ""
    series = collections.defaultdict(list)
    for evento in _eventos(blocos):
        if evento.get("Event") != "CreatureSpeedUpdated":
            continue
        valor = evento.get("Speed")
        if isinstance(valor, int):
            series[evento.get("CreatureId")].append(valor)
    if not series:
        return [
            "",
            f"  Nenhuma criatura teve a velocidade atualizada nesta gravacao ({pedido} pedido). "
            "O cliente so recebe CreatureSpeedUpdated quando o servidor muda a velocidade - "
            "numa gravacao curta ou parada isso pode nao acontecer nenhuma vez.",
        ] + _paralisias_do_jogador(blocos) + _alcance_da_paralisia(blocos)

    medidas = collections.defaultdict(list)
    for chave, valores in series.items():
        nome = nomes.get(chave)
        if not nome:
            continue
        if pedido not in ("todos", "todas") and pedido not in nome:
            continue
        medidas[nome].extend(valores)
    if not medidas:
        vistos = sorted({nome for nome in nomes.values() if nome})
        com_leitura = sorted({nomes.get(chave) for chave in series if nomes.get(chave)})
        return [
            "",
            f"  Nenhuma leitura de velocidade para '{pedido}'. Criaturas com nome nesta gravacao: "
            + (", ".join(vistos[:20]) if vistos else "nenhuma"),
            "  ATENCAO: o cliente so recebe CreatureSpeedUpdated quando a velocidade MUDA, logo um bicho"
            " que nao levou haste nem paralyze nesta gravacao NUNCA aparece aqui - a ausencia nao quer"
            " dizer que ele nao estava la.",
            "  Quem teve leitura: "
            + (", ".join(com_leitura[:12]) if com_leitura else "ninguem (a gravacao nao mudou velocidade de criatura nenhuma)"),
        ] + _paralisias_do_jogador(blocos) + _alcance_da_paralisia(blocos)

    linhas = [
        "",
        "VELOCIDADE MEDIDA (o numero que o servidor enviou em CreatureSpeedUpdated):",
        f"  {'criatura':22s} {'base':>5s} {'min':>5s} {'max':>5s} {'origem':6s} variacao            leituras",
    ]
    for nome in sorted(medidas, key=lambda n: -len(medidas[n])):
        valores = medidas[nome]
        menor, maior = min(valores), max(valores)
        base, origem = _base_da_velocidade(nome), ".mon"
        if not base:
            base = collections.Counter(valores).most_common(1)[0][0]
            origem = "vista"
        if maior == menor:
            variacao = "sem variacao (nunca levou haste nem paralyze nesta gravacao)"
        else:
            baixo = 100.0 * (menor - base) / base
            alto = 100.0 * (maior - base) / base
            variacao = (
                f"{baixo:+.1f}% a {alto:+.1f}% "
                f"({int(round((menor - base) * 1000 / base))} a {int(round((maior - base) * 1000 / base))} por mil)"
            )
        linhas.append(
            f"  {nome[:22]:22s} {base:5d} {menor:5d} {maior:5d} {origem:6s} {variacao}  ({len(valores)})"
        )
    linhas.append(
        "  'base' pelo .mon = 2*GoStrength+80 (provado ao digito em 7 monstros); 'vista' = a velocidade "
        "mais frequente, quando o .mon nao esta ao alcance. O per-mil e o que o XML escreve em "
        "speedchange/speedchange_max."
    )
    linhas.extend(_paralisias_do_jogador(blocos))
    linhas.extend(_alcance_da_paralisia(blocos))
    return linhas


def _quedas_de_velocidade(serie):
    """Episodios de queda e a velocidade de repouso do jogador.

    A percentagem de cada queda mede-se contra a velocidade do instante ANTERIOR a ela, nunca
    contra um repouso unico da gravacao: quem calca umas botas de haste muda de velocidade a meio.
    Medido no vampireswithnator: o jogador alterna entre 266 e 320 (266 x 1.2, as botas) e medir
    contra o maior valor da gravacao dava -88% onde o original fez -50%. O repouso, esse, e a
    velocidade a que ele volta - a mais frequente entre as leituras que nao sao um tombo.
    """
    calmos = [
        valor
        for indice, (_, valor) in enumerate(serie)
        if indice == 0 or valor >= serie[indice - 1][1] * 0.97
    ]
    repouso = collections.Counter(calmos).most_common(1)[0][0] if calmos else 0
    episodios = []
    antes = pior = inicio = None
    anterior = None
    for instante, valor in serie:
        if anterior is not None:
            if valor < anterior * 0.97:
                if antes is None:
                    antes, inicio, pior = anterior, instante, valor
                else:
                    pior = min(pior, valor)
            elif antes is not None:
                episodios.append((inicio, instante, antes, pior))
                antes = None
        anterior = valor
    if antes is not None:
        episodios.append((inicio, None, antes, pior))
    return repouso, episodios


def _paralisias_do_jogador(blocos):
    """As quedas de velocidade do jogador: quanto, por quanto tempo e o provavel autor de cada uma."""
    eventos = list(_eventos(blocos))
    jogador = None
    for evento in eventos:
        if evento.get("Event") == "WorldInitialized":
            jogador = evento.get("PlayerId")
            break
    if not jogador:
        return []
    serie = sorted(
        (evento.get("_quando") or 0, evento.get("Speed"))
        for evento in eventos
        if evento.get("Event") == "CreatureSpeedUpdated"
        and evento.get("CreatureId") == jogador
        and isinstance(evento.get("Speed"), int)
    )
    if len(serie) < 2:
        return ["", "PARALISIA: a velocidade do jogador nao foi enviada nesta gravacao."]
    repouso, episodios = _quedas_de_velocidade(serie)
    if repouso <= 0:
        return []
    ataques = []
    for evento in eventos:
        if evento.get("Event") != "StatusMessageReceived":
            continue
        casou = re.search(r"due to an attack by (?:an? )?(.+?)\.?$", (evento.get("Message") or "").strip())
        if casou:
            ataques.append((evento.get("_quando") or 0, casou.group(1).strip()))
    ataques.sort()
    if not episodios:
        return ["", f"PARALISIA: base do jogador = {repouso}; nenhuma queda de velocidade nesta gravacao."]
    por_autor = collections.defaultdict(list)
    duracoes = []
    sem_recuperacao = 0
    for inicio, fim, antes, pior in episodios:
        recentes = [a for a in ataques if 0 <= inicio - a[0] <= 3000]
        quem = recentes[-1][1] if recentes else "(sem dano antes)"
        por_autor[quem].append(round(100.0 * (pior - antes) / antes))
        if fim is None:
            sem_recuperacao += 1
        else:
            duracoes.append((fim - inicio) / 1000.0)
    todas = [pct for pcts in por_autor.values() for pct in pcts]
    duracoes.sort()
    menor = min(valor for _, valor in serie)
    if duracoes:
        quanto_durou = (
            f"duracao mediana ~{int(duracoes[len(duracoes) // 2])}s"
            f" (a mais longa {int(duracoes[-1])}s)"
        )
    else:
        quanto_durou = "nenhuma recuperacao observada, logo a duracao nao se mede"
    linhas = [
        "",
        f"PARALISIA (quedas de velocidade do jogador; repouso = {repouso}, a velocidade a que ele"
        " volta - contada so nas leituras que NAO sao um tombo, porque quem calca umas botas de"
        " haste muda de velocidade a meio da gravacao):",
        f"  {len(episodios)} episodio(s); quedas de {min(todas)}% a {max(todas)}%; {quanto_durou}",
        f"  a velocidade mais baixa atingida foi {menor} ({100.0 * (menor - repouso) / repouso:+.0f}%"
        " do repouso). Cada queda e medida contra a velocidade do instante ANTERIOR a ela, e a"
        " percentagem do .mon incide sobre a velocidade INTEIRA do alvo: -40% deixa 60%, -100%"
        " leva a zero.",
    ]
    if sem_recuperacao:
        linhas.append(
            f"  {sem_recuperacao} episodio(s) acabaram sem o servidor enviar a recuperacao: a queda"
            " e real, a duracao desses nao se mede."
        )
    pequenas = sum(1 for pct in todas if -20 < pct <= 0)
    if pequenas:
        linhas.append(
            f"  {pequenas} de {len(todas)} queda(s) tiram menos de 20%: as botas de haste dao +20% e"
            " sair delas tira ~17%, logo estas podem ser troca de equipamento e nao feitiço -"
            " cruzar com o mínimo que o .mon declara."
        )
    for quem in sorted(por_autor, key=lambda nome: -len(por_autor[nome])):
        pcts = por_autor[quem]
        linhas.append(f"    {quem[:22]:22s} n={len(pcts):3d}  {min(pcts):+d}% a {max(pcts):+d}%")
    linhas.append(
        "  atribuicao pelo ultimo dano nomeado nos 3s antes da queda: e INDICATIVA (uma criatura pode "
        "paralisar sem causar dano no mesmo instante). Cruza-la com as criaturas que o .mon declara ter "
        "feitiço de speed."
    )
    return linhas


def _alcance_da_paralisia(blocos):
    """Diz se as quedas de velocidade pegam UMA pessoa de cada vez ou varias no mesmo instante.

    O .mon separa os dois casos pela origem da linha: `Victim` e de ALVO UNICO (o numero e o
    alcance) e `Origin` e EM AREA (o numero e o raio). Aqui a prova vem do proprio servidor: numa
    magia de area os jogadores que estao ao lado caem no MESMO milesimo; numa de alvo unico nunca
    caem juntos. Medido a 2026-11-22: no AncientScarabs dois jogadores caem juntos 42 vezes
    (scarab, Origin (4,...)) e no goethidipthrah nenhuma das 6x5 quedas coincide (farao, Victim).
    """
    eventos = list(_eventos(blocos))
    tipo = {}
    nome_de = {}
    for evento in eventos:
        if evento.get("Event") == "CreatureSeen":
            tipo[evento.get("CreatureId")] = evento.get("Type")
            nome_de[evento.get("CreatureId")] = evento.get("Name")
    jogadores = {cid for cid, marca in tipo.items() if marca == "Player"}
    if len(jogadores) < 2:
        return []
    series = collections.defaultdict(list)
    for evento in eventos:
        if (
            evento.get("Event") == "CreatureSpeedUpdated"
            and evento.get("CreatureId") in jogadores
            and isinstance(evento.get("Speed"), int)
        ):
            series[evento.get("CreatureId")].append((evento.get("_quando") or 0, evento["Speed"]))
    quedas = {}
    for cid, serie in series.items():
        serie.sort()
        anterior = None
        lista = []
        for instante, valor in serie:
            if anterior is not None and valor < anterior - 2:
                lista.append(instante)
            anterior = valor
        if lista:
            quedas[nome_de.get(cid, str(cid))] = lista
    if len(quedas) < 2:
        return [""]
    por_instante = collections.defaultdict(set)
    for quem, lista in quedas.items():
        for instante in lista:
            por_instante[round(instante / 100.0)].add(quem)
    juntos = {chave: quem for chave, quem in por_instante.items() if len(quem) >= 2}
    todas = sum(len(lista) for lista in quedas.values())
    linhas = [
        "",
        "ALCANCE DA PARALISIA (jogadores que perdem velocidade no MESMO instante):",
        f"  {len(quedas)} jogador(es) com queda, {todas} queda(s) no total, "
        f"{len(juntos)} instante(s) com dois ou mais a cair juntos",
    ]
    if juntos:
        pares = collections.Counter()
        for quem in juntos.values():
            ordenados = sorted(quem)
            for i, um in enumerate(ordenados):
                for outro in ordenados[i + 1:]:
                    pares[(um, outro)] += 1
        linhas.append(
            "  => EM AREA: ha quedas simultaneas, e so uma magia centrada no monstro (Origin do "
            ".mon) atinge quem esta em volta ao mesmo tempo."
        )
        for (um, outro), quantas in pares.most_common(4):
            linhas.append(
                f"    {um[:20]:20s} + {outro[:20]:20s} {quantas} vez(es) juntos"
            )
    else:
        linhas.append(
            "  => ALVO UNICO: nenhuma queda coincidiu com a de outro jogador, e uma magia em area "
            "obrigaria a cair dois ao mesmo tempo. Bate com `Victim (alcance, ...)` do .mon."
        )
    linhas.append(
        "  A janela e de 100ms: o servidor manda a velocidade de cada um no mesmo pacote, logo uma "
        "magia em area cai no mesmo milesimo e duas conjuracoes separadas caem a segundos de "
        "distancia."
    )
    return linhas


def _base_da_velocidade(nome):
    """2*GoStrength+80 lido do .mon da CipSoft - a velocidade sem feitiço."""
    chave = ("velocidade", nome)
    if chave in _CACHE:
        return _CACHE[chave]
    base = 0
    try:
        devolvido = resolver_caminho("docs/projetos/Tibia74/gerados/monstros/cipsoft")
    except Exception:
        devolvido = None
    pasta = (devolvido[0] if isinstance(devolvido, tuple) else devolvido) if devolvido else None
    if pasta and os.path.isdir(pasta):
        direto = os.path.join(pasta, re.sub(r"\s+", "", nome) + ".mon")
        caminho = direto if os.path.isfile(direto) else ""
        if not caminho:
            for ficheiro in sorted(os.listdir(pasta)):
                if not ficheiro.lower().endswith(".mon"):
                    continue
                try:
                    with open(os.path.join(pasta, ficheiro), encoding="latin-1") as fh:
                        texto = fh.read(2000)
                except OSError:
                    continue
                achado = re.search(r'Name\s*=\s*"([^"]+)"', texto)
                if achado and achado.group(1).strip().lower() == nome:
                    caminho = os.path.join(pasta, ficheiro)
                    break
        if caminho:
            try:
                with open(caminho, encoding="latin-1") as fh:
                    forca = re.search(r"\(GoStrength,\s*(-?\d+)", fh.read())
            except OSError:
                forca = None
            if forca:
                base = 2 * int(forca.group(1)) + 80
    _CACHE[chave] = base
    return base


def _perfil_de_dano(blocos, alvo=""):
    """Dano que o jogador leva, por autor e por cor, casando a mensagem com o numero de MESMO valor."""
    eventos = list(_eventos(blocos))
    numeros = [
        (evento.get("_quando") or 0, evento.get("Color"), evento.get("Value"))
        for evento in eventos
        if evento.get("Event") == "NumberEffectPopped" and evento.get("Color") != 215
    ]
    pedido = (alvo or "").strip().lower()
    if pedido in ("todos", "todas", "tudo"):
        pedido = ""
    autores = {}
    sem_numero = 0
    for evento in eventos:
        if evento.get("Event") != "StatusMessageReceived":
            continue
        casou = re.match(
            r"You lose (\d+) hitpoints?(?: due to an attack by (?:an? )?(.+?))?\.?$",
            (evento.get("Message") or "").strip(),
        )
        if not casou:
            continue
        valor = int(casou.group(1))
        autor = (casou.group(2) or "").strip().lower() or "(sem autor)"
        quando = evento.get("_quando") or 0
        cor = None
        for instante, cor_do_numero, valor_do_numero in numeros:
            if valor_do_numero == valor and abs(instante - quando) < 300:
                cor = cor_do_numero
                break
        if cor is None:
            sem_numero += 1
            continue
        autores.setdefault(autor, {}).setdefault(cor, []).append((quando / 1000.0, valor))

    if not autores:
        return ["  nenhum dano com numero casado nesta gravacao"]

    linhas = []
    for autor in sorted(autores, key=lambda nome: -sum(len(v) for v in autores[nome].values())):
        if pedido and pedido not in autor and autor != "(sem autor)":
            continue
        golpes = autores[autor]
        total = sum(len(lista) for lista in golpes.values())
        linhas.append(f"  {autor} - {total} golpe(s)")
        for cor in sorted(golpes, key=lambda tom: -len(golpes[tom])):
            lista = sorted(golpes[cor])
            valores = [v for _, v in lista]
            tipo = CORES_DE_NUMERO.get(cor, f"cor {cor}")
            distintos = sorted(set(valores))
            if len(distintos) <= 8:
                amostra = ", ".join(str(v) for v in distintos)
            else:
                amostra = f"{distintos[0]}..{distintos[-1]} ({len(distintos)} valores)"
            razoes = [round(lista[i + 1][0] - lista[i][0], 1) for i in range(len(lista) - 1)]
            curtos = collections.Counter(d for d in razoes if 0.5 < d < 25)
            ritmo = ""
            cadeias = ""
            if curtos:
                intervalo, quantos = curtos.most_common(1)[0]
                ritmo = f" | ritmo {intervalo}s ({quantos}x)"
                resumo = _resumo_das_cadeias(lista, intervalo)
                if resumo:
                    cadeias = " | " + resumo
            linhas.append(
                f"      {tipo:18s} x{len(valores):3d}  valores {amostra}"
                f"  media {sum(valores) / len(valores):.1f}{ritmo}{cadeias}"
            )
            mostrados = lista if len(lista) <= _TETO_DA_CADEIA else lista[:_TETO_DA_CADEIA]
            anterior = None
            for quando, valor in mostrados:
                salto = "" if anterior is None else f"  (+{quando - anterior:.1f}s)"
                linhas.append(f"        {quando:8.1f}s  valor {valor}{salto}")
                anterior = quando
            if len(lista) > len(mostrados):
                linhas.append(
                    f"        ... +{len(lista) - len(mostrados)} golpe(s); o ultimo aos {lista[-1][0]:.1f}s"
                )
    if not linhas:
        return [f"  nenhum dano de '{alvo}' nesta gravacao - os autores sao: " + ", ".join(sorted(autores))]
    if sem_numero:
        linhas.append(f"  ({sem_numero} dano(s) sem numero casado - fora da janela de 300ms)")
    linhas.append(
        "  '(sem autor)' e o dano de CONDICAO (energia, veneno, fogo): o cliente nao o atribui a ninguem."
    )
    return linhas


def _resumo_das_cadeias(lista, intervalo):
    """Quantos numeros seguidos uma condicao aplica, contando os passos do ritmo dela."""
    tolerancia = max(0.5, intervalo * 0.25)
    tamanhos, atual = [], 1
    for indice in range(len(lista) - 1):
        passo = lista[indice + 1][0] - lista[indice][0]
        if abs(passo - intervalo) <= tolerancia:
            atual += 1
        else:
            tamanhos.append(atual)
            atual = 1
    tamanhos.append(atual)
    corridas = [n for n in tamanhos if n >= 2]
    if not corridas:
        return ""
    contagem = collections.Counter(corridas)
    detalhe = ", ".join(f"{n} x{v}" for n, v in sorted(contagem.items()))
    return f"cadeias: {detalhe} (media {sum(corridas) / len(corridas):.2f} ticks)"


def _grupos_de_area(blocos, efeito="", minimo=2):
    """Agrupa os numeros de dano pelo INSTANTE: quantas criaturas levaram dano ao
    mesmo tempo e se o valor e o mesmo. Numero igual em todas = a magia sorteia
    UMA vez por conjuracao; numeros espalhados = sorteia por alvo."""
    eventos = _lista_de_eventos(blocos)
    marcas = collections.Counter()
    numeros = collections.defaultdict(list)
    for evento in eventos:
        quando = round((evento.get("_quando") or 0) / 1000.0, 2)
        tipo = evento.get("Event")
        if tipo == "NumberEffectPopped":
            posicao = evento.get("Position") or {}
            numeros[quando].append((posicao.get("X"), posicao.get("Y"),
                                    evento.get("Value"), evento.get("Color")))
        elif tipo == "GraphicalEffectPopped" and (not efeito or str(evento.get("Id")) == str(efeito)):
            marcas[quando] += 1

    linhas = ["", "  DANO EM AREA - uma tiragem por conjuracao ou uma por alvo?"]
    if efeito:
        linhas.append(f"  (so os instantes em que o efeito {efeito} apareceu)")
    iguais = diferentes = 0
    for quando in sorted(numeros):
        if efeito and not marcas.get(quando):
            continue
        por_posicao = collections.defaultdict(list)
        for x, y, valor, cor in numeros[quando]:
            por_posicao[(x, y)].append((valor, cor))
        if len(por_posicao) < minimo or any(len(v) > 1 for v in por_posicao.values()):
            continue
        valores = [v[0][0] for v in por_posicao.values()]
        cores = {v[0][1] for v in por_posicao.values()}
        if len(cores) > 1:
            continue
        mesmo = len(set(valores)) == 1
        if mesmo:
            iguais += 1
        else:
            diferentes += 1
        veredito = "TODOS IGUAIS" if mesmo else f"espalhados, {max(valores) - min(valores)} de diferenca"
        linhas.append(
            f"    {int(quando // 60)}:{quando % 60:05.2f}  {len(por_posicao)} criatura(s)"
            f"  {sorted(valores)}  cor {cores.pop()}  {veredito}"
        )
    if not iguais and not diferentes:
        linhas.append("    nenhum instante com 2+ criaturas levando dano ao mesmo tempo"
                      " (sem 'efeito', isto olha a gravacao inteira)")
    else:
        linhas.append(f"    -> {iguais} conjuracao(oes) em que TODAS as criaturas levaram o MESMO valor"
                      f" | {diferentes} com valores diferentes")
        linhas.append("    valor igual em todas = sorteio unico por conjuracao;"
                      " valores diferentes com o mesmo efeito no instante = sorteio por alvo.")
    return linhas


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
    em_eventos = {id(e): i for i, e in enumerate(eventos)}

    fixos = _itens_que_nao_se_pegam()
    descartados = collections.Counter()
    sacos_usados = set()
    cenario = collections.Counter()
    for abertura in abertos:
        nome_aberto = str(abertura.get("ContainerName") or "").strip()
        if not nome_aberto or _nome_de_corpo(abertura):
            continue
        que_item = (abertura.get("ContainerItem") or {}).get("ItemId")
        if que_item in SACOS_DE_LOOT or que_item in MOCHILAS_DO_JOGADOR:
            continue
        cenario[nome_aberto.lower()] += 1

    def itens_de(evento):
        limpos = []
        for linha in (evento.get("Items") or []):
            for item in linha:
                if fixos and item.get("ItemId") in fixos:
                    descartados[item.get("ItemId")] += 1
                    continue
                limpos.append(item)
        return limpos



    nome_do_monstro = alvo
    if por_id:
        nome_do_monstro = _monstro_do_corpo(int(alvo)) or ""
    declarado_ids = set(_loot_do_monstro(nome_do_monstro) or {}) if nome_do_monstro else set()

    no_corpo = collections.Counter()
    no_saco = collections.Counter()
    ouro_corpo = []
    ouro_saco = []
    com_saco = 0
    sacos_vazios = 0
    sacos_alheios = 0
    sacos_fora = 0
    total_corpo = 0
    total_saco = 0
    com_ouro_corpo = 0
    com_ouro_saco = 0
    nos_dois = collections.Counter()
    nos_dois_limpos = collections.Counter()
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
        saco, onde_do_saco = _achar_saco(abertos, posicao, evento.get("ContainerId"),
                                         _segundos(evento), sacos_usados, declarado_ids)
        if onde_do_saco.startswith("aberto fora"):
            sacos_fora += 1
        if saco is None:
            sacos_vazios += 1
            continue
        dentro = itens_de(saco)
        if not dentro:
            sacos_vazios += 1
            continue
        dentro_ids = {item.get("ItemId") for item in dentro} - {OURO}
        if declarado_ids and dentro_ids and not (dentro_ids & declarado_ids):
            sacos_alheios += 1
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
        fora_agora = {item.get("ItemId") for item in topos}
        dentro_agora = {item.get("ItemId") for item in dentro}
        inicio = em_eventos.get(id(evento), -1)
        fim = em_eventos.get(id(saco), -1)
        mexeu = inicio >= 0 and fim > inicio and any(
            x.get("Event") in MEXER_NO_SACO for x in eventos[inicio + 1:fim]
        )
        for identificador in (fora_agora & dentro_agora) - SACOS_DE_LOOT:
            nos_dois[identificador] += 1
            if not mexeu:
                nos_dois_limpos[identificador] += 1

    vazios = sum(1 for evento in corpos if not itens_de(evento))
    linhas = ["", f"LOOT: {len(corpos)} corpos de '{alvo}'{nota} · {com_saco} com saco "
              f"({100.0 * com_saco / len(corpos):.1f}%) · {sacos_vazios} saco(s) vazio(s) "
              f"· {vazios} corpo(s) sem nada"]
    if sacos_fora:
        linhas.append(f"  ({sacos_fora} saco(s) contados porque estavam abertos noutra janela mas "
                      f"traziam item que o monstro declara - bag guardada e aberta na mochila)")
    if sacos_alheios:
        linhas.append(f"  (descartados {sacos_alheios} saco(s) sem NENHUM item do monstro - "
                      f"e a mochila de loot do jogador aberta logo depois do corpo, nao a do monstro)")
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
           " que tinham saco", len(corpos), com_ouro_saco)
    linhas.append("")
    linhas.append(f"  itens por corpo: {total_corpo / len(corpos):.2f} fora + "
                  f"{total_saco / len(corpos):.2f} no saco = "
                  f"{(total_corpo + total_saco) / len(corpos):.2f} (sem ouro) · "
                  f"ouro {len(ouro_corpo) / len(corpos):.2f} pilhas fora + "
                  f"{len(ouro_saco) / len(corpos):.2f} no saco")
    if cenario:
        linhas.append("")
        linhas.append("  IGNORADO (containers que NAO sao loot de monstro - movel, armario, bau do "
                      "depot, caixa; o que estava la dentro nao entra em tabela nenhuma):")
        linhas.append("    " + ", ".join(f"{nome} x{vezes}" for nome, vezes in cenario.most_common(8)))
    if descartados:
        linhas.append("")
        linhas.append("  DESCARTADO (o items.otb marca como FIXO, logo nao pode estar dentro de um "
                      "corpo nem de um saco - e lixo de leitura):")
        for identificador, vezes in descartados.most_common(8):
            linhas.append(f"    {(nomes.get(identificador) or '?')[:30]} ({identificador}) · {vezes}")

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
            trocados = []
            for identificador, sitio_no_xml in sorted(declarado.items()):
                if identificador in SACOS_DE_LOOT:
                    continue
                fora = no_corpo.get(identificador, 0)
                dentro = no_saco.get(identificador, 0)
                if fora and dentro:
                    trocados.append((identificador, min(fora, dentro),
                                     f"cai nos DOIS sitios em corpos diferentes ({fora} no corpo, "
                                     f"{dentro} no saco) - o XML tem uma entrada so: dividir a chance "
                                     f"entre corpo e saco"))
                elif sitio_no_xml == "corpo" and dentro:
                    trocados.append((identificador, dentro,
                                     f"o XML poe no corpo e caiu {dentro} vez(es) no saco - "
                                     f"acrescentar uma entrada dentro da bag"))
                elif sitio_no_xml == "saco" and fora:
                    trocados.append((identificador, fora,
                                     f"o XML poe no saco e caiu {fora} vez(es) no corpo"))
            if trocados:
                linhas.append("    POSICAO a corrigir (o saco lido e o do monstro, nao a mochila do jogador):")
                for identificador, _, que in sorted(trocados, key=lambda t: -t[1]):
                    linhas.append(f"      {(nomes.get(identificador) or '?')[:30]} "
                                  f"({identificador}) · {que}")
            if nos_dois:
                linhas.append("    MESMO ITEM no corpo E no saco do MESMO corpo:")
                for identificador, vezes in nos_dois.most_common(8):
                    provados = nos_dois_limpos.get(identificador, 0)
                    nota = (f"{provados} sem o jogador mexer (posto pelo proprio monstro)"
                            if provados else
                            "todos com o jogador a mexer antes - pode ser a mochila dele")
                    linhas.append(f"      {(nomes.get(identificador) or '?')[:30]} "
                                  f"({identificador}) · {vezes} corpo(s) · {nota}")
            if sobram:
                linhas.append("    NAO estao no <loot> (lixo do saque ou mochila do jogador - nao acrescentar):")
                for identificador in sobram[:12]:
                    onde = []
                    if no_corpo.get(identificador):
                        onde.append(f"{no_corpo[identificador]} no corpo")
                    if no_saco.get(identificador):
                        onde.append(f"{no_saco[identificador]} no saco")
                    linhas.append(f"      {(nomes.get(identificador) or '?')[:30]} "
                                  f"({identificador}) · {', '.join(onde)}")
    return linhas


def _nome_de_corpo(evento):
    nome = str(evento.get("ContainerName") or "").strip()
    if not nome.lower().startswith(PREFIXOS_DE_CORPO):
        return ""
    return nome


def _versao_da_gravacao(caminho):
    """Versao do cliente pela pasta (TibiCAM/7.3, 7.4): o id de item muda de uma para a outra."""
    for parte in reversed(os.path.normpath(os.path.abspath(str(caminho))).split(os.sep)[:-1]):
        texto = parte.strip().lower()
        if re.fullmatch(r"7\.\d+", texto):
            return texto
    return ""


def _normalizar_versao(texto):
    """'7.40' e '7.4' sao a mesma versao; '7.30' e '7.3' tambem."""
    limpo = str(texto or "").strip()
    if re.fullmatch(r"7\.\d0", limpo):
        return limpo[:-1]
    return limpo


def _itens_que_nao_se_pegam():
    """Ids que o items.otb deixa fixos: nao podem estar dentro de um corpo nem de um saco."""
    if "nao_pega" in _CACHE:
        return _CACHE["nao_pega"]
    fixos = frozenset()
    try:
        from src.backend.tools.otbm import _itens_do_otb
        for alvo in ("docs/projetos/Tibia74/Server/data/items/items.otb",
                     "Server/data/items/items.otb"):
            try:
                devolvido = resolver_caminho(alvo)
            except Exception:
                continue
            caminho = devolvido[0] if isinstance(devolvido, tuple) else devolvido
            if not caminho or not os.path.isfile(caminho):
                continue
            with open(caminho, "rb") as fh:
                itens = _itens_do_otb(fh.read())
            if itens:
                fixos = frozenset(i for i, (_cliente, flags) in itens.items() if not flags & 0x20)
                break
    except Exception:
        fixos = frozenset()
    _CACHE["nao_pega"] = fixos
    return fixos


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


def _segundos(evento):
    if evento.get("__t") is not None:
        return float(evento["__t"])
    return (evento.get("_quando") or 0) / 1000.0


def _achar_saco(abertos, posicao, cid_do_corpo, quando, usados, declarados):
    """O saco de loot que pertence a um corpo aberto, e de mais ninguem.

    Primeiro o que tem o MESMO ContainerId do corpo - e assim que o cliente abre a bag que
    esta dentro dele. So se nao houver nenhum, aceita uma bag aberta noutra janela quando o
    conteudo dela traz item que o monstro declara (o caso de a bag ter sido guardada e aberta
    na mochila). Devolve (evento, onde) ou (None, motivo).
    """
    if posicao < 0:
        return None, ""
    candidata = None
    viu_outra = False
    for indice, seguinte in enumerate(abertos[posicao + 1:posicao + 12], posicao + 1):
        if _nome_de_corpo(seguinte):
            break
        if _segundos(seguinte) - quando > JANELA_DO_CORPO:
            break
        if indice in usados:
            continue
        if (seguinte.get("ContainerItem") or {}).get("ItemId") not in SACOS_DE_LOOT:
            continue
        if seguinte.get("ContainerId") == cid_do_corpo:
            usados.add(indice)
            return seguinte, "dentro do corpo"
        viu_outra = True
        if candidata is None and declarados:
            dentro = {item.get("ItemId") for linha in (seguinte.get("Items") or [])
                      for item in linha}
            if dentro & declarados:
                candidata = (indice, seguinte)
    if candidata is not None:
        usados.add(candidata[0])
        return candidata[1], "aberto fora do corpo (tinha item do monstro)"
    if viu_outra:
        return None, "havia saco aberto noutra janela sem item do monstro"
    return None, ""


def _corpos_resumidos(blocos):
    """id do corpo -> nome, quantos e o que caiu no corpo e no saco.

    O saco do monstro e o primeiro SACO DE LOOT aberto depois do corpo, antes do proximo
    corpo e sem repetir um saco ja usado. Container de cenario (armario, cama, bau do
    depot, caixote) NUNCA conta - era o que metia mobilia dentro do loot.
    """
    eventos = _lista_de_eventos(blocos)
    abertos = [e for e in eventos if e.get("Event") == "ContainerOpened"]
    posicoes = {id(e): i for i, e in enumerate(abertos)}
    fixos = _itens_que_nao_se_pegam()

    def itens_de(evento):
        return [item for linha in (evento.get("Items") or []) for item in linha
                if not (fixos and item.get("ItemId") in fixos)]

    declarados = {}

    def declarado_de(nome_corpo):
        simples = _nome_simples(nome_corpo)
        if simples not in declarados:
            try:
                declarados[simples] = set((_loot_do_monstro(simples) or {}))
            except Exception:
                declarados[simples] = set()
        return declarados[simples]

    corpos = _sem_reaberturas([e for e in abertos if _nome_de_corpo(e)])
    usados = set()
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
            saco, _onde = _achar_saco(abertos, posicoes.get(id(evento), -1),
                                      evento.get("ContainerId"), _segundos(evento),
                                      usados, declarado_de(_nome_de_corpo(evento)))
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
            bruto, cliente = _ler_bruto(caminho, miner, clientes, False)
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
            "cliente": cliente,
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


def _nome_simples(nome):
    """Nome do corpo sem o prefixo de estado: 'remains of a ghost' -> 'ghost'."""
    texto = re.sub(r"\s+", " ", str(nome or "").strip().lower())
    if texto.startswith(PREFIXOS_DE_CORPO):
        texto = texto.split(" ", 1)[1]
        if texto.startswith("of "):
            texto = texto[3:]
        for artigo in ("a ", "an ", "the "):
            if texto.startswith(artigo):
                return texto[len(artigo):]
    return texto


def _corpos_do_nome(procurado):
    """Ids de corpo cujo monstro casa com o nome - o 'varrer' aceita o monstro, nao so o corpo.

    O nome exato ganha ao pedaco de nome: 'elf' e 'elf scout' sao monstros diferentes e
    partilham tres letras, por isso procurar por 'elf' arrastava o scout e o arcanista e
    somava loots de tres bichos numa tabela so. So se NENHUM corpo tiver o nome exato e
    que se aceita quem apenas o contem - e o que permite pedir 'elf scout' e 'beholder'.
    """
    _monstros_do_corpo(0)
    exatos, parecidos = set(), set()
    for corpo, nomes in (_CACHE.get("corpos") or {}).items():
        for nome in nomes:
            simples = _nome_simples(nome)
            if simples == procurado:
                exatos.add(corpo)
            elif procurado in simples:
                parecidos.add(corpo)
    indice, _nota = indexar_gravacoes()
    for dados in indice.values():
        if dados.get("erro"):
            continue
        for identificador, achado in (dados.get("corpos") or {}).items():
            simples = _nome_simples(str(achado.get("nome") or ""))
            try:
                corpo = int(identificador)
            except (TypeError, ValueError):
                continue
            if simples == procurado:
                exatos.add(corpo)
            elif procurado in simples:
                parecidos.add(corpo)
    return exatos or parecidos


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


def _contagens_do_loot(procurado):
    """Soma em TODAS as gravacoes do indice quanto caiu no corpo e quanto caiu no saco."""
    indice, nota = indexar_gravacoes()
    termo = procurado.lower()
    ids = {int(termo)} if termo.isdigit() else _corpos_do_nome(termo)
    corpo = collections.Counter()
    saco = collections.Counter()
    pilhas = []
    corpos = 0
    fora = 0
    for chave, dados in indice.items():
        if dados.get("erro"):
            continue
        if _normalizar_versao(dados.get("cliente") or _versao_da_gravacao(chave)) != VERSAO_DOS_ITENS:
            fora += 1
            continue
        for identificador, achado in (dados.get("corpos") or {}).items():
            try:
                if int(identificador) not in ids:
                    continue
            except (TypeError, ValueError):
                continue
            corpos += achado.get("n") or 0
            corpo.update(achado.get("corpo") or {})
            saco.update(achado.get("saco") or {})
            pilhas.extend(achado.get("pilhas") or [])
    if fora:
        nota = f"{nota}; {fora} gravacao(oes) de outro cliente (7.3) ficaram de fora"
    return corpo, saco, corpos, pilhas, nota


def posicoes_do_loot(procurado):
    """Onde cada item caiu DE FACTO nas gravacoes: {id: 'corpo'|'saco'} pelo sitio onde aparece mais."""
    corpo, saco, corpos, _pilhas, _nota = _contagens_do_loot(procurado)
    if not corpos:
        return {}
    sitio = {}
    for contagem, rotulo in ((corpo, "corpo"), (saco, "saco")):
        for identificador, vezes in contagem.items():
            try:
                numero = int(identificador)
            except (TypeError, ValueError):
                continue
            antes = sitio.get(numero)
            if not antes or vezes > antes[1]:
                sitio[numero] = (rotulo, vezes)
    return {numero: lugar for numero, (lugar, _vezes) in sitio.items()}


def _loot_somado(procurado):
    """Loot de um monstro somado em TODAS as gravacoes do indice, com a posicao que o XML declara."""
    corpo, saco, corpos, pilhas, nota = _contagens_do_loot(procurado)
    nomes = _nomes_de_itens()
    if not corpos:
        return f"\nLOOT SOMADO: nenhum corpo de '{procurado}' no indice ({nota})."

    declarado = _loot_do_monstro(procurado) or {}
    linhas = ["", f"LOOT SOMADO: '{procurado}' em todas as gravacoes · {corpos} corpo(s) · {nota}"]
    for rotulo, contagem in (("CORPO", corpo), ("SACO", saco)):
        if not contagem:
            continue
        linhas.append(f"  {rotulo}:")
        for identificador, vezes in contagem.most_common():
            try:
                numero = int(identificador)
            except (TypeError, ValueError):
                continue
            sitio = declarado.get(numero) or declarado.get(identificador)
            if sitio and sitio != rotulo.lower():
                marca = f"   (o XML poe no {sitio})"
            elif not sitio:
                marca = "   (nao declarado no XML)"
            else:
                marca = ""
            etiqueta = f"{nomes.get(numero) or 'item'} ({numero})"
            linhas.append(f"    {etiqueta[:32]:<32} {vezes:5d}  {100 * vezes / corpos:6.2f}%{marca}")
    if pilhas:
        totais = [sum(p) for p in pilhas]
        linhas.append(f"  OURO: {len(pilhas)} de {corpos} corpos = {100 * len(pilhas) / corpos:.1f}%"
                      f" · medio {sum(totais) / len(totais):.1f} · min {min(totais)} · max {max(totais)}")
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
