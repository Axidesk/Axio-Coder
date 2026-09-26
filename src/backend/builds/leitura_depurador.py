import os
import re

_PROMPTS = re.compile(r"^(?:\d+:\d+[a-z0-9:]*>|\(Pdb\))\s*", re.IGNORECASE)
_PAROU_CDB = re.compile(r"^>\s*(?P<linha>\d+):\s?(?P<codigo>.*)$")
_QUADRO = re.compile(r"^\s*(?P<marca>>)?\s*(?P<ficheiro>[A-Za-z]:[\\/][^(]+?)\((?P<linha>\d+)\)")
_CODIGO_PDB = re.compile(r"^->\s*(?P<codigo>.*)$")
_MARCADA_PDB = re.compile(r"^\s*(?P<linha>\d+)\s+B->\s?(?P<codigo>.*)$")
_EXCECAO = re.compile(r"^\([0-9a-f.]+\):\s+(?P<nome>.+?)\s+-\s+code (?P<codigo>[0-9a-f]+)")
_NAO_TRATADA = re.compile(r"^Uncaught exception", re.IGNORECASE)
_PONTO = re.compile(r"^Breakpoint (?P<numero>\d+) hit")
_VARIAVEL = re.compile(r"^[0-9a-f`]{16,}\s+(?P<resto>.+)$")
_QUADRO_CDB = re.compile(r"\[(?P<ficheiro>[A-Za-z]:[^\]]*?)\s+@\s+(?P<linha>\d+)\]")
_FIM_DO_PROGRAMA = re.compile(r"^The program finished", re.IGNORECASE)
_RECUSA = re.compile(r"^\*\*\*\s*(?P<nome>[A-Za-z_.]*[Ee]rror|[A-Za-z_.]+):\s*(?P<texto>.*)$")
_TRACEBACK = re.compile(r"^Traceback \(most recent call last\):")
_QUADRO_DO_TRACEBACK = re.compile(r'^\s*File "(?P<ficheiro>[^"]+)", line (?P<linha>\d+), in (?P<nome>.*)$')
_QUADRO_SEM_FUNCAO = re.compile(r'^\s*File "(?P<ficheiro>[^"]+)", line (?P<linha>\d+)\s*$')
_MOTIVO_DO_TRACEBACK = re.compile(r"^(?P<nome>[A-Za-z_][A-Za-z0-9_.]*): ?(?P<texto>.*)$")

_FICHEIROS_DO_MOTOR = ("pdb.py", "bdb.py", "cmd.py", "code.py", "runpy.py", "<string>",
                       "<command-line>")

_CODIGO_DE_ARRANQUE = "80000003"
_PREFIXO_DE_QUEDA = "rebentou"
_MOTIVO_NAO_TRATADA = "rebentou: excecao nao tratada (o programa parou nesta linha)"
_ENCHIMENTO = "padrao repetido - enchimento de memoria por usar, nao um valor do programa"
_TRADUCOES = {
    "access violation": "o programa mexeu numa memoria que nao era dele",
}
_LIMITE_DE_VARIAVEIS = 8
_LIMITE_DE_QUADROS = 4


def leitura(texto, antes=None):
    """Le as linhas NOVAS de um depurador e acumula o retrato: onde parou, porque, o que se ve
    e quem chamou. So as linhas novas entram - e o que impede um motivo que ja passou (uma
    excecao que ficou escrita na janela do card) de voltar a valer a cada passo."""
    sobre = _retrato(antes)
    for linha in (texto or "").splitlines():
        _ler_linha(sobre, linha)
    _nomear_pelo_quadro(sobre)
    return sobre


def _retrato(antes):
    """O retrato que ja se tinha, pronto a receber as linhas novas."""
    if not antes:
        return {"parou": None, "motivo": "", "recusa": "", "variaveis": [], "quadros": [],
                "erro": None, "terminou": False, "pendente": False, "traceback": False,
                "motivo_novo": False}
    return {"parou": dict(antes["parou"]) if antes.get("parou") else None,
            "erro": dict(antes["erro"]) if antes.get("erro") else None,
            "motivo": antes.get("motivo", ""),
            "recusa": antes.get("recusa", ""),
            "variaveis": list(antes.get("variaveis") or []),
            "quadros": list(antes.get("quadros") or []),
            "terminou": bool(antes.get("terminou")),
            "pendente": bool(antes.get("pendente")),
            "traceback": bool(antes.get("traceback")),
            "motivo_novo": bool(antes.get("motivo_novo"))}


def _ler_linha(sobre, linha):
    """Aplica a UMA linha da saida as regras do que ela quer dizer."""
    sobre["pendente"] = False
    limpa = _PROMPTS.sub("", linha.rstrip())
    achado = _FIM_DO_PROGRAMA.match(limpa)
    if achado:
        sobre["terminou"] = True
        sobre["recusa"] = ""
        return
    achado = _RECUSA.match(limpa)
    if achado:
        sobre["recusa"] = f"{achado.group('nome')}: {achado.group('texto')}".strip()
        return
    achado = _TRACEBACK.match(limpa)
    if achado:
        sobre["traceback"] = True
        sobre["erro"] = None
        return
    if sobre.get("traceback"):
        achado = _QUADRO_DO_TRACEBACK.match(limpa)
        if achado:
            _juntar_quadro(sobre, achado.group("ficheiro"), achado.group("linha"))
            _marcar_local_do_erro(sobre, achado.group("ficheiro"), achado.group("linha"))
            return
        achado = _QUADRO_SEM_FUNCAO.match(limpa)
        if achado:
            _marcar_local_do_erro(sobre, achado.group("ficheiro"), achado.group("linha"))
            return
        achado = _MOTIVO_DO_TRACEBACK.match(limpa)
        if achado:
            sobre["motivo"] = _motivo_da_excecao(achado.group("nome"), achado.group("texto"))
            sobre["motivo_novo"] = True
            sobre["traceback"] = False
            return
    achado = _PAROU_CDB.match(limpa)
    if achado:
        _parou_em(sobre, "", int(achado.group("linha")), achado.group("codigo"))
        return
    achado = _MARCADA_PDB.match(limpa)
    if achado:
        _parou_em(sobre, "", int(achado.group("linha")), achado.group("codigo"))
        return
    achado = _QUADRO.match(limpa)
    if achado:
        if achado.group("marca"):
            if _do_programa(achado.group("ficheiro")):
                _parou_em(sobre, achado.group("ficheiro"), int(achado.group("linha")), "")
        else:
            _juntar_quadro(sobre, achado.group("ficheiro"), achado.group("linha"))
        return
    achado = _CODIGO_PDB.match(limpa)
    if achado:
        parou = sobre.get("parou")
        if parou and not parou["codigo"]:
            parou["codigo"] = achado.group("codigo").strip()
        return
    achado = _NAO_TRATADA.match(limpa)
    if achado:
        sobre["motivo"] = sobre.get("motivo") or _MOTIVO_NAO_TRATADA
        sobre["motivo_novo"] = True
        return
    achado = _EXCECAO.match(limpa)
    if achado:
        sobre["motivo"] = _motivo(achado.group("nome"), achado.group("codigo"))
        sobre["motivo_novo"] = True
        return
    achado = _PONTO.match(limpa)
    if achado:
        sobre["motivo"] = f"ponto de paragem {achado.group('numero')}"
        sobre["motivo_novo"] = True
        return
    achado = _QUADRO_CDB.search(limpa)
    if achado:
        _juntar_quadro(sobre, achado.group("ficheiro"), achado.group("linha"))
        return
    achado = _VARIAVEL.match(limpa)
    if achado:
        variavel = _da_variavel(achado.group("resto"))
        if variavel:
            sobre["variaveis"].append(variavel)


def linhas(sobre):
    """As linhas, em linguagem simples, que contam o que o depurador disse."""
    if not sobre:
        return []
    saida = []
    parou = sobre.get("parou") or {}
    if parou and not sobre.get("pendente"):
        onde = (f"{parou['ficheiro']}:{parou['linha']}" if parou["ficheiro"]
                else f"linha {parou['linha']}")
        codigo = parou.get("codigo") or ""
        saida.append(f"[axio] parou em {onde}" + (f"  ->  {codigo}" if codigo else ""))
    if sobre.get("motivo"):
        saida.append(f"[axio] porque: {sobre['motivo']}")
        erro = sobre.get("erro") or {}
        if erro.get("linha") and parou.get("linha") and _e_outro_sitio(erro, parou):
            saida.append(f"[axio] o erro esta em {erro['ficheiro']}:{erro['linha']}")
    variaveis = sobre.get("variaveis") or []
    if variaveis:
        mostradas = "  ·  ".join(_texto_da_variavel(v) for v in variaveis[:_LIMITE_DE_VARIAVEIS])
        resto = len(variaveis) - _LIMITE_DE_VARIAVEIS
        saida.append(f"[axio] valores: {mostradas}" + (f"  (+{resto} mais)" if resto > 0 else ""))
    quadros = sobre.get("quadros") or []
    if quadros and not sobre.get("pendente") and not sobre.get("traceback"):
        cadeia = " <- ".join(f"{q['nome']}:{q['linha']}" for q in quadros[:_LIMITE_DE_QUADROS])
        saida.append(f"[axio] quem chamou: {cadeia}")
    if sobre.get("recusa"):
        saida.append(f"[axio] o depurador nao aceitou: {sobre['recusa']}")
    if sobre.get("terminou"):
        saida.append("[axio] o programa correu ate ao fim")
    return saida


def e_queda(motivo):
    """Diz se um motivo desta leitura e uma queda: o programa rebentou a correr."""
    return (motivo or "").strip().lower().startswith(_PREFIXO_DE_QUEDA)


def _nome_curto(caminho):
    """O nome do ficheiro, sem pastas."""
    return os.path.basename((caminho or "").replace("\\", "/"))


def _parou_em(sobre, ficheiro, linha, codigo):
    """Marca onde a execucao parou, e mantem o ficheiro e o codigo ja sabidos desta linha.

    Um programa que ja correu ate ao fim nao volta a andar so porque o pdb reiniciou: a posicao
    que chega depois disso e ignorada, e o editor fica onde a execucao terminou de facto.

    O codigo da linha chega numa linha seguinte do depurador, por isso a paragem nasce PENDENTE
    e o card so a mostra quando a linha fica completa - era isto que fazia sair cada paragem
    duas vezes, uma sem o codigo e outra com ele."""
    if sobre.get("terminou"):
        return
    antes = sobre.get("parou") or {}
    mesma = antes.get("linha") == linha and _mesmo_sitio(antes.get("caminho"), ficheiro)
    if not mesma:
        sobre["variaveis"] = []
        sobre["quadros"] = []
        if not sobre.pop("motivo_novo", False):
            sobre["motivo"] = ""
        sobre["recusa"] = ""
    sobre["pendente"] = not codigo
    sobre["parou"] = {
        "ficheiro": _nome_curto(ficheiro) or (antes.get("ficheiro", "") if mesma else ""),
        "caminho": (ficheiro or "").strip() or (antes.get("caminho", "") if mesma else ""),
        "linha": linha,
        "codigo": codigo.strip() or (antes.get("codigo", "") if mesma else ""),
    }


def _juntar_quadro(sobre, ficheiro, linha):
    """Anota um quadro da pilha, uma unica vez por ficheiro e linha."""
    if not _do_programa(ficheiro):
        return
    quadro = {"nome": _nome_curto(ficheiro), "caminho": (ficheiro or "").strip(), "linha": int(linha)}
    if quadro not in sobre["quadros"]:
        sobre["quadros"].append(quadro)
        sobre["pendente"] = True


def _marcar_local_do_erro(sobre, ficheiro, linha):
    """Guarda o ULTIMO quadro do traceback - e ali que o erro esta."""
    if not _do_programa(ficheiro):
        return
    sobre["erro"] = {"ficheiro": _nome_curto(ficheiro), "caminho": (ficheiro or "").strip(),
                     "linha": int(linha)}


def _do_programa(caminho):
    """Diz se o ficheiro e do programa que esta a ser depurado, e nao do motor do depurador nem
    da biblioteca do Python - a pilha do pdb, do bdb e do codecs nao e a pilha do utilizador."""
    if not caminho:
        return True
    if _nome_curto(caminho).lower() in _FICHEIROS_DO_MOTOR:
        return False
    normalizado = "/" + caminho.replace("\\", "/").lower().strip("/") + "/"
    return "/lib/" not in normalizado and "/lib64/" not in normalizado


def _mesmo_sitio(antes, agora):
    """Diz se dois caminhos sao o mesmo ficheiro (um deles pode vir sem caminho nenhum)."""
    if not antes or not agora:
        return True
    return _nome_curto(antes).lower() == _nome_curto(agora).lower()


def _e_outro_sitio(erro, parou):
    """Diz se o sitio do erro e diferente de onde o depurador ficou parado."""
    if _nome_curto(erro.get("ficheiro")).lower() != _nome_curto(parou.get("ficheiro")).lower():
        return True
    return int(erro.get("linha") or 0) != int(parou.get("linha") or 0)


def _nomear_pelo_quadro(sobre):
    """Da o ficheiro ao sitio onde parou, lendo-o do quadro da pilha com a mesma linha."""
    parou = sobre.get("parou") or {}
    if not parou or parou.get("caminho"):
        return
    for quadro in sobre["quadros"]:
        if quadro["linha"] == parou["linha"]:
            parou["ficheiro"] = quadro["nome"]
            parou["caminho"] = quadro.get("caminho", "")
            return


def _motivo_da_excecao(nome, texto):
    """Nomeia a excecao do fim de um traceback do Python, em linguagem simples."""
    return f"rebentou: {nome}: {texto}".rstrip(": ")


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

