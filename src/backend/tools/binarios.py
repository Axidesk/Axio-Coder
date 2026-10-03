"""Bibliotecas que um programa do Windows pede e quais faltam ao lado dele.

Le a tabela de importacao do proprio ficheiro (formato PE), sem o executar e sem carregar
nada para dentro deste processo: diz o que ele pede, onde cada biblioteca foi encontrada
(pasta do programa, System32, SysWOW64, PATH) e o que nao existe em lado nenhum - que e' a
resposta ao codigo 0xc0000135, o "o programa nao arranca" de quem recebe um programa por
inteiro e sem as bibliotecas que ele pede emprestadas ao Windows.
"""
import os
import struct

from src.backend.services.file_service import resolver_caminho
from src.backend.state import emit_event
from src.backend.tools.registry import register

INDICE_DA_EXPORTACAO = 0
INDICE_DA_IMPORTACAO = 1
INDICE_DA_ATRASADA = 13
TAMANHO_DO_DESCRITOR = 20
TAMANHO_DO_DESCRITOR_ATRASADO = 32
LIMITE_DE_DLLS = 400
LIMITE_DE_FUNCOES = 600
LIMITE_DE_EXPORTADAS = 60000
MAXIMO_DE_LEITURA = 64 * 1024 * 1024
PREFIXOS_DE_CONJUNTO = ("api-ms-win-", "ext-ms-win-")


@register(
    "tool_dependencias_do_programa",
    "Diz que bibliotecas um programa do Windows pede e QUAIS FALTAM ao lado dele - a resposta "
    "para 'o programa nao arranca' (codigo 0xc0000135), 'faltam ficheiros' ou 'esta biblioteca "
    "serve?'. Le a tabela de importacao do proprio ficheiro (PE) sem o executar e sem carregar "
    "nada: diz o que ele pede, onde cada biblioteca existe (pasta do programa, System32, "
    "SysWOW64, PATH) e o que nao esta em lado nenhum. Com 'funcoes', diz tambem cada funcao "
    "pedida e quais dessas a biblioteca nao exporta.",
    {
        "caminho_relativo": {
            "tipo": "STRING",
            "obrig": True,
            "padrao": "",
            "desc": "O programa (.exe) ou a biblioteca (.dll) a ler, no projeto ou fora dele.",
        },
        "funcoes": {
            "tipo": "BOOLEAN",
            "desc": "Lista tambem as funcoes pedidas a cada biblioteca e acusa as que ela nao exporta.",
            "padrao": False,
        },
    },
)
def tool_dependencias_do_programa(caminho_relativo, funcoes=False):
    emit_event("executing", function=f"Dependencias de: {caminho_relativo}")
    alvo, erro = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro:
        return erro
    if not os.path.isfile(alvo):
        return f"ERRO: arquivo nao encontrado: {caminho_relativo}"
    try:
        with open(alvo, "rb") as ficheiro:
            bruto = ficheiro.read(MAXIMO_DE_LEITURA)
    except OSError as falha:
        return f"ERRO: nao consegui ler '{caminho_relativo}' ({falha})."
    try:
        bits, base_da_imagem, secoes, diretorios = _secoes_e_diretorios(bruto)
    except ValueError as falha:
        return f"ERRO: '{caminho_relativo}' nao e um programa do Windows ({falha})."
    pedidas = _pedidas(bruto, secoes, diretorios, base_da_imagem, bits)
    if not pedidas:
        return (
            f"'{caminho_relativo}' ({bits} bits) nao pede biblioteca nenhuma: nao ha tabela de"
            " importacao. Num programa do Windows isso e' estranho - confirme que o arquivo nao"
            " esta truncado."
        )
    pastas = _pastas_de_procura(alvo, bits)
    achadas = {}
    faltam = []
    conjuntos = {}
    for nome in sorted(pedidas, key=str.lower):
        caminho, rotulo = _onde_vive(nome, pastas)
        if caminho:
            achadas.setdefault(rotulo, []).append((nome, caminho))
        elif nome.lower().startswith(PREFIXOS_DE_CONJUNTO):
            conjuntos[nome] = pedidas[nome]
        else:
            faltam.append(nome)
    return _relato(caminho_relativo, bruto, bits, pedidas, achadas, faltam, conjuntos, funcoes)


def _relato(caminho, bruto, bits, pedidas, achadas, faltam, conjuntos, com_funcoes):
    linhas = [
        f"'{caminho}' ({bits} bits, {len(bruto) / 1024 / 1024:.2f} MB) pede {len(pedidas)}"
        f" biblioteca(s): {len(pedidas) - len(faltam) - len(conjuntos)} encontrada(s) no disco,"
        f" {len(conjuntos)} do proprio Windows e {len(faltam)} EM FALTA."
    ]
    if faltam:
        linhas.append("")
        linhas.append("FALTAM (nao existem na pasta do programa, no Windows nem no PATH):")
        linhas.extend(f"  {nome}" for nome in faltam)
        linhas.append(
            "E' isto que faz o programa fechar-se no arranque com o codigo 0xc0000135. A cura e'"
            " pôr estas bibliotecas ao lado do programa (ou instalar o pacote do Visual C++"
            " Redistributable que as traz) - e nao procurar defeito no programa."
        )
    else:
        linhas.append("")
        linhas.append("Nenhuma em falta: o programa tem ao lado tudo o que pede ao Windows.")
    linhas.append("")
    linhas.append("ONDE CADA UMA FOI ENCONTRADA:")
    for rotulo in sorted(achadas, key=lambda chave: -len(achadas[chave])):
        linhas.append(f"  {rotulo}: {len(achadas[rotulo])} -> {_exemplos(achadas[rotulo])}")
    if conjuntos:
        linhas.append(
            f"  do proprio Windows, por conjunto de API (nao ha ficheiro): {len(conjuntos)}"
        )
    linhas.append(
        "A ordem de procura e' a do Windows: a pasta do programa, o System32, e so depois o"
        " PATH. Uma biblioteca que exista numa pasta ao lado mas nao na do programa nao serve:"
        " o programa nao a encontra."
    )
    if com_funcoes:
        linhas.extend(_relato_das_funcoes(pedidas, achadas))
    return "\n".join(linhas)


def _exemplos(achadas):
    """Os nomes encontrados naquela pasta, encurtados quando sao muitos."""
    nomes = [nome for nome, _ in achadas]
    if len(nomes) <= 6:
        return ", ".join(nomes)
    return ", ".join(nomes[:6]) + f" (+{len(nomes) - 6})"


def _relato_das_funcoes(pedidas, achadas):
    """As funcoes pedidas a cada biblioteca e as que ela nao exporta."""
    por_nome = {nome.lower(): caminho for lista in achadas.values() for nome, caminho in lista}
    linhas = ["", "FUNCOES PEDIDAS A CADA BIBLIOTECA:"]
    sem_exportacao = []
    for nome in sorted(pedidas, key=str.lower):
        funcoes = pedidas[nome]
        if not funcoes:
            continue
        caminho = por_nome.get(nome.lower())
        if not caminho:
            continue
        exportadas = _exportadas(caminho)
        conta = f"  {nome}: {len(funcoes)}"
        if exportadas is None:
            linhas.append(conta + " (nao consegui ler a tabela de exportacao)")
            continue
        faltam = [funcao for funcao in funcoes if not funcao.startswith("#") and funcao not in exportadas]
        linhas.append(conta + ("" if not faltam else f", NAO exporta {len(faltam)}"))
        if faltam:
            sem_exportacao.append((nome, faltam, caminho))
    if not sem_exportacao:
        linhas.append("Cada biblioteca encontrada exporta tudo o que o programa lhe pede.")
        return linhas
    linhas.append("")
    linhas.append("BIBLIOTECAS QUE NAO TEM O QUE LHE E' PEDIDO:")
    for nome, faltam, caminho in sem_exportacao:
        linhas.append(f"  {nome} ({caminho}):")
        linhas.extend(f"      {funcao}" for funcao in sorted(faltam)[:20])
    linhas.append(
        "Isto e' pista, nao prova: o Windows guarda versoes lado a lado da mesma biblioteca"
        " (pasta WinSxS) e o programa pode carregar outra que nao esta no caminho normal -"
        " o TaskDialogIndirect, por exemplo, so existe na versao 6 do comctl32. Uma funcao"
        " apontada aqui manda olhar, nao acusa sozinha."
    )
    return linhas


def _pastas_de_procura(programa, bits):
    """[(rotulo, pasta)] na ordem em que o Windows procura as bibliotecas desta largura."""
    raiz = os.environ.get("SystemRoot") or r"C:\Windows"
    rotulo = "SysWOW64" if bits == 32 else "System32"
    do_windows = os.path.join(raiz, rotulo)
    pastas = [(os.path.dirname(os.path.abspath(programa)), "pasta do programa"),
              (do_windows, rotulo)]
    do_sistema = {
        os.path.normcase(os.path.abspath(do_windows)),
        os.path.normcase(os.path.join(raiz, "System32")),
        os.path.normcase(os.path.join(raiz, "SysWOW64")),
    }
    for item in (os.environ.get("PATH") or "").split(os.pathsep):
        limpo = item.strip().strip('"')
        if not limpo or not os.path.isdir(limpo):
            continue
        if os.path.normcase(os.path.abspath(limpo)) in do_sistema:
            continue
        pastas.append((limpo, "PATH"))
    return pastas


def _onde_vive(nome, pastas):
    for pasta, rotulo in pastas:
        caminho = os.path.join(pasta, nome)
        if os.path.isfile(caminho):
            return caminho, rotulo
    return "", ""


def _secoes_e_diretorios(bruto):
    """(bits, base da imagem, seccoes, diretorios) de um PE; ValueError se nao for um."""
    if len(bruto) < 64 or bruto[:2] != b"MZ":
        raise ValueError("nao tem a assinatura MZ")
    assinatura = struct.unpack_from("<I", bruto, 0x3C)[0]
    if assinatura + 24 > len(bruto) or bruto[assinatura:assinatura + 4] != b"PE\0\0":
        raise ValueError("nao tem o cabecalho PE")
    secoes_pedidas = struct.unpack_from("<H", bruto, assinatura + 6)[0]
    tamanho_opcional = struct.unpack_from("<H", bruto, assinatura + 20)[0]
    inicio = assinatura + 24
    if inicio + tamanho_opcional > len(bruto):
        raise ValueError("o cabecalho esta cortado")
    magia = struct.unpack_from("<H", bruto, inicio)[0]
    if magia == 0x20B:
        bits = 64
        base_da_imagem = struct.unpack_from("<Q", bruto, inicio + 24)[0]
        inicio_diretorios = inicio + 112
    elif magia == 0x10B:
        bits = 32
        base_da_imagem = struct.unpack_from("<I", bruto, inicio + 28)[0]
        inicio_diretorios = inicio + 96
    else:
        raise ValueError(f"cabecalho de formato desconhecido (0x{magia:x})")
    diretorios = {}
    for indice in range(16):
        posicao = inicio_diretorios + indice * 8
        if posicao + 8 > inicio + tamanho_opcional:
            break
        rva = struct.unpack_from("<I", bruto, posicao)[0]
        if rva:
            diretorios[indice] = rva
    secoes = []
    for numero in range(secoes_pedidas):
        posicao = inicio + tamanho_opcional + numero * 40
        if posicao + 40 > len(bruto):
            break
        tamanho_virtual, virtual = struct.unpack_from("<II", bruto, posicao + 8)
        tamanho_bruto, bruto_em = struct.unpack_from("<II", bruto, posicao + 16)
        if virtual and tamanho_virtual and bruto_em:
            secoes.append((virtual, max(tamanho_virtual, tamanho_bruto), bruto_em))
    return bits, base_da_imagem, secoes, diretorios


def _deslocamento(rva, secoes):
    """Onde cai um endereco relativo dentro do arquivo, ou None se ele sair das seccoes."""
    for virtual, tamanho, bruto_em in secoes:
        if virtual <= rva < virtual + tamanho:
            return bruto_em + (rva - virtual)
    return None


def _nome_no_rva(bruto, rva, secoes):
    posicao = _deslocamento(rva, secoes)
    if posicao is None or posicao >= len(bruto):
        return ""
    fim = bruto.find(b"\0", posicao)
    if fim < 0:
        fim = min(posicao + 300, len(bruto))
    return bruto[posicao:fim].decode("latin-1")


def _funcoes(bruto, rva, secoes, bits):
    """Os nomes pedidos numa tabela de importacao: '#n' quando o pedido e' por numero."""
    nomes = []
    posicao = _deslocamento(rva, secoes)
    if posicao is None:
        return nomes
    passo = 8 if bits == 64 else 4
    formato = "<Q" if bits == 64 else "<I"
    mais_alto = 1 << (63 if bits == 64 else 31)
    for numero in range(LIMITE_DE_FUNCOES):
        sitio = posicao + numero * passo
        if sitio + passo > len(bruto):
            break
        valor = struct.unpack_from(formato, bruto, sitio)[0]
        if not valor:
            break
        if valor & mais_alto:
            nomes.append(f"#{valor & 0xFFFF}")
            continue
        nome = _nome_no_rva(bruto, valor + 2, secoes)
        if nome:
            nomes.append(nome)
    return nomes


def _pedidas(bruto, secoes, diretorios, base_da_imagem, bits):
    """{biblioteca: [funcoes]} do que o programa pede, na importacao e nas atrasadas."""
    pedidas = {}
    for indice, atrasado in ((INDICE_DA_IMPORTACAO, False), (INDICE_DA_ATRASADA, True)):
        rva = diretorios.get(indice)
        if not rva:
            continue
        base = _deslocamento(rva, secoes)
        if base is None:
            continue
        passo = TAMANHO_DO_DESCRITOR_ATRASADO if atrasado else TAMANHO_DO_DESCRITOR
        for numero in range(LIMITE_DE_DLLS):
            posicao = base + numero * passo
            if posicao + passo > len(bruto) or not any(bruto[posicao:posicao + passo]):
                break
            if atrasado:
                atributos, nome_em, _, tabela, olhar_em = struct.unpack_from("<IIIII", bruto, posicao)
                olhar_em = olhar_em or tabela
                if not atributos & 1:
                    nome_em = max(nome_em - base_da_imagem, 0)
                    olhar_em = max(olhar_em - base_da_imagem, 0)
            else:
                olhar_em, _, _, nome_em, _ = struct.unpack_from("<IIIII", bruto, posicao)
            nome = _nome_no_rva(bruto, nome_em, secoes)
            if not nome:
                continue
            lista = pedidas.setdefault(nome, [])
            for funcao in _funcoes(bruto, olhar_em, secoes, bits):
                if funcao not in lista:
                    lista.append(funcao)
    return pedidas


def _exportadas(caminho):
    """O que a biblioteca exporta, ou None se a tabela nao puder ser lida."""
    try:
        with open(caminho, "rb") as ficheiro:
            bruto = ficheiro.read(MAXIMO_DE_LEITURA)
    except OSError:
        return None
    try:
        _, _, secoes, diretorios = _secoes_e_diretorios(bruto)
    except ValueError:
        return None
    rva = diretorios.get(INDICE_DA_EXPORTACAO)
    if not rva:
        return set()
    base = _deslocamento(rva, secoes)
    if base is None or base + 40 > len(bruto):
        return None
    quantos = struct.unpack_from("<I", bruto, base + 24)[0]
    lista = struct.unpack_from("<I", bruto, base + 32)[0]
    inicio = _deslocamento(lista, secoes)
    if inicio is None:
        return None
    nomes = set()
    for numero in range(min(quantos, LIMITE_DE_EXPORTADAS)):
        sitio = inicio + numero * 4
        if sitio + 4 > len(bruto):
            break
        nome = _nome_no_rva(bruto, struct.unpack_from("<I", bruto, sitio)[0], secoes)
        if nome:
            nomes.add(nome)
    return nomes
