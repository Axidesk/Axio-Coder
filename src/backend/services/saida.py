"""Recorte de saidas compridas: preserva as duas pontas e diz o que ficou de fora."""

TETO_CABECA_LINHAS = 12
TETO_CAUDA_LINHAS = 50
TETO_CABECA_TEXTO = 2800
TETO_CAUDA_TEXTO = 1200


def recortar_linhas(linhas, teto_cabeca=TETO_CABECA_LINHAS, teto_cauda=TETO_CAUDA_LINHAS):
    """Preserva as duas pontas de um log; a cauda sozinha escondia o resumo escrito no topo."""
    linhas = list(linhas or [])
    if len(linhas) <= teto_cabeca + teto_cauda:
        return "\n".join(linhas)
    omitidas = len(linhas) - teto_cabeca - teto_cauda
    aviso = f"... ({omitidas} de {len(linhas)} linhas registadas omitidas entre as duas pontas)"
    return "\n".join(linhas[:teto_cabeca] + [aviso] + linhas[-teto_cauda:])


def repartir_teto(teto):
    """As duas pontas de um teto pedido pela chamada: 3/4 na cabeca, o resto na cauda."""
    teto = max(0, int(teto or 0))
    cabeca = int(teto * 0.75)
    return cabeca, teto - cabeca


def recortar_texto(texto, teto_cabeca=TETO_CABECA_TEXTO, teto_cauda=TETO_CAUDA_TEXTO):
    """Preserva as duas pontas de uma saida comprida; a cabeca sozinha perdia a excecao do fim.

    O aviso diz quanto ficou de fora E o 'teto_saida' exato que traz o texto inteiro: sem essa
    conta, uma saida cortada a meio so se resolvia repetindo o trecho para ver a outra ponta.
    """
    texto = (texto or "").strip()
    if len(texto) <= teto_cabeca + teto_cauda:
        return texto
    omitidos = len(texto) - teto_cabeca - teto_cauda
    aviso = (f"\n... (saida cortada: {omitidos} de {len(texto)} caracteres ficaram de fora entre as "
             f"duas pontas; repita com teto_saida={len(texto)} para ver tudo)\n")
    return texto[:teto_cabeca] + aviso + texto[-teto_cauda:]


def linhas_com_termo(texto, termos, com_numero=False):
    """As linhas de 'texto' que contem algum dos termos, sem diferenciar maiusculas.

    E a primitiva partilhada de quem precisa de ver so um pedaco de uma saida ou de uma
    fonte comprida: o filtro do harness (saida de um processo) e o da consulta de API
    (declaracao de um pacote) contam com ela, em vez de cada um casar linhas a sua maneira.
    Com 'com_numero', cada linha vem precedida do numero dela no texto.
    """
    if isinstance(termos, str):
        termos = [termos]
    chaves = [str(t).strip().lower() for t in (termos or []) if str(t or "").strip()]
    if not chaves:
        return []
    guardadas = []
    for numero, linha in enumerate((texto or "").splitlines(), 1):
        if any(chave in linha.lower() for chave in chaves):
            guardadas.append(f"{numero}: {linha}" if com_numero else linha)
    return guardadas
