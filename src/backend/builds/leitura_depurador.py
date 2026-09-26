import os
import re

_PROMPTS = re.compile(r"^(?:\d+:\d+[a-z0-9:]*>|\(Pdb\))\s*", re.IGNORECASE)
_PAROU_CDB = re.compile(r"^>\s*(?P<linha>\d+):\s?(?P<codigo>.*)$")
_QUADRO = re.compile(r"^\s*(?P<marca>>)?\s*(?P<ficheiro>[A-Za-z]:[\\/][^(]+?)\((?P<linha>\d+)\)")
_CODIGO_PDB = re.compile(r"^->\s*(?P<codigo>.*)$")
_MARCADA_PDB = re.compile(r"^\s*(?P<linha>\d+)\s+B->\s?(?P<codigo>.*)$")
_EXCECAO = re.compile(r"^\([0-9a-f.]+\):\s+(?P<nome>.+?)\s+-\s+code (?P<codigo>[0-9a-f]+)")
_PONTO = re.compile(r"^Breakpoint (?P<numero>\d+) hit")
_VARIAVEL = re.compile(r"^[0-9a-f`]{16,}\s+(?P<resto>.+)$")
_QUADRO_CDB = re.compile(r"\[(?P<ficheiro>[A-Za-z]:[^\]]*?)\s+@\s+(?P<linha>\d+)\]")

_CODIGO_DE_ARRANQUE = "80000003"
_ENCHIMENTO = "padrao repetido - enchimento de memoria por usar, nao um valor do programa"
_TRADUCOES = {
    "access violation": "o programa mexeu numa memoria que nao era dele",
}
_LIMITE_DE_VARIAVEIS = 8
_LIMITE_DE_QUADROS = 4


def leitura(texto, antes=None):
    """O que a saida de um depurador diz: onde parou, porque, o que se ve e quem chamou."""
    sobre = {"parou": None, "motivo": "", "variaveis": [], "quadros": []}
    for linha in (texto or "").splitlines():
        limpa = _PROMPTS.sub("", linha.rstrip())
        achado = _PAROU_CDB.match(limpa)
        if achado:
            _parou_em(sobre, "", int(achado.group("linha")), achado.group("codigo"))
            continue
        achado = _MARCADA_PDB.match(limpa)
        if achado:
            _parou_em(sobre, "", int(achado.group("linha")), achado.group("codigo"))
            continue
        achado = _QUADRO.match(limpa)
        if achado:
            if achado.group("marca"):
                _parou_em(sobre, achado.group("ficheiro"), int(achado.group("linha")), "")
            else:
                _juntar_quadro(sobre, achado.group("ficheiro"), achado.group("linha"))
            continue
        achado = _CODIGO_PDB.match(limpa)
        if achado:
            if sobre["parou"] and not sobre["parou"]["codigo"]:
                sobre["parou"]["codigo"] = achado.group("codigo").strip()
            continue
        achado = _EXCECAO.match(limpa)
        if achado:
            sobre["motivo"] = _motivo(achado.group("nome"), achado.group("codigo"))
            continue
        achado = _PONTO.match(limpa)
        if achado:
            sobre["motivo"] = f"ponto de paragem {achado.group('numero')}"
            continue
        achado = _QUADRO_CDB.search(limpa)
        if achado:
            _juntar_quadro(sobre, achado.group("ficheiro"), achado.group("linha"))
            continue
        achado = _VARIAVEL.match(limpa)
        if achado:
            variavel = _da_variavel(achado.group("resto"))
            if variavel:
                sobre["variaveis"].append(variavel)
    _nomear_pelo_quadro(sobre)
    return _com_o_que_ja_se_sabia(sobre, antes)


def linhas(sobre):
    """As linhas, em linguagem simples, que contam o que o depurador disse."""
    if not sobre:
        return []
    saida = []
    parou = sobre.get("parou") or {}
    if parou:
        onde = (f"{parou['ficheiro']}:{parou['linha']}" if parou["ficheiro"]
                else f"linha {parou['linha']}")
        codigo = parou.get("codigo") or ""
        saida.append(f"[axio] parou em {onde}" + (f"  ->  {codigo}" if codigo else ""))
    if sobre.get("motivo"):
        saida.append(f"[axio] porque: {sobre['motivo']}")
    variaveis = sobre.get("variaveis") or []
    if variaveis:
        mostradas = "  ·  ".join(_texto_da_variavel(v) for v in variaveis[:_LIMITE_DE_VARIAVEIS])
        resto = len(variaveis) - _LIMITE_DE_VARIAVEIS
        saida.append(f"[axio] valores: {mostradas}" + (f"  (+{resto} mais)" if resto > 0 else ""))
    quadros = sobre.get("quadros") or []
    if quadros:
        cadeia = " <- ".join(f"{q['nome']}:{q['linha']}" for q in quadros[:_LIMITE_DE_QUADROS])
        saida.append(f"[axio] quem chamou: {cadeia}")
    return saida


def _nome_curto(caminho):
    """O nome do ficheiro, sem pastas."""
    return os.path.basename((caminho or "").replace("\\", "/"))


def _parou_em(sobre, ficheiro, linha, codigo):
    """Marca onde a execucao parou, e mantem o ficheiro e o codigo ja sabidos desta linha."""
    antes = sobre.get("parou") or {}
    mesma = antes.get("linha") == linha
    if not mesma:
        sobre["variaveis"] = []
        sobre["quadros"] = []
    sobre["parou"] = {
        "ficheiro": _nome_curto(ficheiro) or (antes.get("ficheiro", "") if mesma else ""),
        "linha": linha,
        "codigo": codigo.strip() or (antes.get("codigo", "") if mesma else ""),
    }


def _juntar_quadro(sobre, ficheiro, linha):
    """Anota um quadro da pilha, uma unica vez por ficheiro e linha."""
    quadro = {"nome": _nome_curto(ficheiro), "linha": int(linha)}
    if quadro not in sobre["quadros"]:
        sobre["quadros"].append(quadro)


def _nomear_pelo_quadro(sobre):
    """Da o nome do ficheiro ao sitio onde parou, lendo-o do quadro com a mesma linha."""
    parou = sobre.get("parou") or {}
    if not parou or parou.get("ficheiro"):
        return
    for quadro in sobre["quadros"]:
        if quadro["linha"] == parou["linha"]:
            parou["ficheiro"] = quadro["nome"]
            return


def _motivo(nome, codigo):
    """Nomeia a paragem em linguagem simples, sabendo que a de arranque nao e um erro."""
    if codigo == _CODIGO_DE_ARRANQUE:
        return "arranque do programa (o depurador para uma vez ao carregar)"
    traducao = _TRADUCOES.get((nome or "").strip().lower())
    return f"rebentou: {traducao or nome} ({nome}, code {codigo})"


def _da_variavel(resto):
    """Le uma variavel do 'dv': o tipo e o nome de um lado, o valor do outro."""
    nome_tipo, separador, valor = resto.partition(" = ")
    if not separador:
        return None
    pedacos = nome_tipo.split()
    if len(pedacos) < 2:
        return None
    valor, nota = _nota_do_valor(valor)
    return {"nome": pedacos[-1], "tipo": " ".join(pedacos[:-1]), "valor": valor, "nota": nota}


def _nota_do_valor(valor):
    """Separa o valor legivel da nota, quando o que esta la nao e um valor do programa."""
    bruto = (valor or "").replace("`", "").strip()
    if bruto[:2].lower() == "0n" and bruto[2:].isdigit():
        return bruto[2:], ""
    corpo = bruto[2:].lower() if bruto[:2].lower() == "0x" else ""
    if len(corpo) >= 8 and all(caractere in "0123456789abcdef" for caractere in corpo):
        pares = [corpo[i:i + 2] for i in range(0, len(corpo) - 1, 2)]
        if len(set(pares)) == 1:
            return bruto, _ENCHIMENTO
        if (len(set(pares[0::2])) == 1 and len(set(pares[1::2])) == 1
                and pares[0] != pares[1]):
            return bruto, _ENCHIMENTO
    return bruto, ""


def _texto_da_variavel(variavel):
    nota = f" ({variavel['nota']})" if variavel["nota"] else ""
    return f"{variavel['nome']} = {variavel['valor']}{nota}"


def _com_o_que_ja_se_sabia(sobre, antes):
    """Completa a leitura nova com o sitio onde ja se sabia que a execucao estava."""
    if not antes:
        return sobre
    if not sobre["parou"] and antes.get("parou"):
        sobre["parou"] = dict(antes["parou"])
    if not sobre["motivo"]:
        sobre["motivo"] = antes.get("motivo", "")
    return sobre
