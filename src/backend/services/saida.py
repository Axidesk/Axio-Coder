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


def recortar_texto(texto, teto_cabeca=TETO_CABECA_TEXTO, teto_cauda=TETO_CAUDA_TEXTO):
    """Preserva as duas pontas de uma saida comprida; a cabeca sozinha perdia a excecao do fim."""
    texto = (texto or "").strip()
    if len(texto) <= teto_cabeca + teto_cauda:
        return texto
    omitidos = len(texto) - teto_cabeca - teto_cauda
    aviso = f"\n... (saida cortada; {omitidos} caracteres omitidos entre as duas pontas)\n"
    return texto[:teto_cabeca] + aviso + texto[-teto_cauda:]
