"""Medicao de uma imagem de referencia: silhueta, proporcoes por faixas e marcas acesas.

Responde ao que se julga numa referencia ANTES de modelar: onde comeca e acaba a
forma, a que altura estao as zonas que mandam (os olhos, um emblema, a base) e
quanto a silhueta enche a sua propria caixa. Tudo o que sai daqui e relativo ao
OBJETO (0 a 1 dentro da sua caixa), nunca a imagem - e o que permite comparar duas
imagens de escalas e enquadramentos diferentes.
"""
import io
import math

import numpy as np

FAIXAS = 16
MARCAS = 4
ALFA_OBJETO = 24
LIMIAR_DISTANCIA = 26.0
LIMIAR_FUNDO_LISO = 34.0
LIMIAR_ACIMA = 0.85
LIMIAR_MINIMO = 12.0
MINIMO_BURACO = 0.004
MINIMO_OBJETO = 0.0015
MINIMO_PECA = 0.02
MINIMO_PIXEIS_MARCA = 4.0
LIMIAR_COMPACTA = 0.15
LIMIAR_PECA_SOLTA = 0.5
PESO_LUZ = (0.299, 0.587, 0.114)


def carregar(caminho):
    """(rgb float32, alfa ou None) de um ficheiro de imagem, ja em RGBA."""
    with open(caminho, "rb") as ficheiro:
        return _dados_da_imagem(ficheiro.read())


def medir(caminho, faixas=FAIXAS, marcas=MARCAS, quadro=None):
    rgb, alfa = carregar(caminho)
    return medir_dados(rgb, alfa, faixas, marcas, quadro)


def medir_bytes(bruto, faixas=FAIXAS, marcas=MARCAS, quadro=None):
    """Como medir(), mas de bytes de imagem - um render em memoria nao passa pelo disco."""
    rgb, alfa = _dados_da_imagem(bruto)
    return medir_dados(rgb, alfa, faixas, marcas, quadro)


def medir_dados(rgb, alfa=None, faixas=FAIXAS, marcas=MARCAS, quadro=None):
    """quadro: (x0, y0, x1, y1) em fraccao da imagem, declarado por quem olhou onde esta o objeto."""
    bruta, como = _mascara_do_objeto(rgb, alfa)
    furada, outras = _limpar(bruta)
    cheia = _preencher(furada)
    declarada = _quadro_em_pixeis(quadro, cheia.shape)
    silhueta = True
    if declarada is not None and (_toca_a_moldura(cheia) or _compactacao(cheia) < LIMIAR_COMPACTA):
        separada = _por_grabcut(rgb, declarada)
        limpa, _soltas = _limpar(separada)
        medida = _preencher(limpa)
        if _compactacao(medida) >= LIMIAR_COMPACTA and not _toca_a_moldura(medida):
            furada, cheia, outras = limpa, medida, []
            como = "corte de grafos (GrabCut) dentro do quadro que indicaste"
        else:
            silhueta = False
    caixa = _caixa(cheia) if silhueta else declarada
    if caixa is None:
        raise ValueError("nao encontrei objeto nenhum: a imagem parece vazia ou de uma cor so")
    x0, y0, x1, y1 = caixa
    largura = x1 - x0 + 1
    altura = y1 - y0 + 1
    if largura * altura < MINIMO_OBJETO * cheia.size:
        raise ValueError("o objeto encontrado e pequeno demais para medir (menos de 0,15% da imagem)")
    recorte = cheia[y0:y1 + 1, x0:x1 + 1]
    cinza_da_imagem = _cinza(rgb)
    cinza = cinza_da_imagem[y0:y1 + 1, x0:x1 + 1]
    inclinacao, alongamento = _eixos(recorte)
    centro = _centro(recorte)
    achados = _marcas_acesas(
        cinza_da_imagem, (x0, y0, largura, altura), marcas * 3 if declarada else marcas
    )
    marcas_do_relato, marcas_fora = _marcas_no_quadro(achados, declarada, marcas)
    medidas = {
        "imagem": (int(cheia.shape[1]), int(cheia.shape[0])),
        "como": como,
        "caixa": (int(x0), int(y0), int(x1), int(y1)),
        "objeto": (int(largura), int(altura)),
        "proporcao": largura / altura,
        "area": int(recorte.sum()),
        "area_relativa": float(recorte.mean()),
        "area_da_imagem": float(cheia.sum()) / cheia.size,
        "centro": centro,
        "inclinacao": inclinacao,
        "alongamento": alongamento,
        "eixo": "vertical" if altura >= largura else "horizontal",
        "perfil": _perfil(recorte, faixas),
        "brilho": _brilho_por_faixa(cinza, recorte, faixas),
        "marcas": marcas_do_relato,
        "marcas_fora": marcas_fora,
        "buracos": _buracos(furada[y0:y1 + 1, x0:x1 + 1], float(recorte.sum())),
        "outras_pecas": outras,
        "toca_a_moldura": _toca_a_moldura(cheia),
        "quadro": declarada,
        "silhueta": silhueta,
        "rgb": rgb,
        "mascara": cheia,
    }
    return medidas


def relato(medidas, caminho=""):
    largura_imagem, altura_imagem = medidas["imagem"]
    largura_objeto, altura_objeto = medidas["objeto"]
    declarado = medidas.get("quadro")
    medida_de_verdade = bool(medidas.get("silhueta", True)) and not _sem_objeto(medidas)
    linhas = [
        f"=== MEDIDA DENTRO DE UM QUADRO QUE TU INDICASTE: {caminho or 'imagem'} ===" if declarado
        else f"=== SILHUETA DE {caminho or 'imagem'} ===",
    ]
    linhas += _aviso_de_confianca(medidas)
    if declarado:
        linhas += _bloco_do_quadro(medidas)
    linhas += [
        f"Imagem: {largura_imagem}x{altura_imagem} px. "
        + (f"Separacao do fundo tentada por: {medidas['como']} - sem resultado fiavel, vale o quadro "
           f"que indicaste." if declarado and not medida_de_verdade
           else f"Objeto separado do fundo por: {medidas['como']}."),
        f"Objeto: {largura_objeto}x{altura_objeto} px"
        + (" (o quadro declarado)" if declarado and not medida_de_verdade else "")
        + f", caixa em x {medidas['caixa'][0]}..{medidas['caixa'][2]} "
        f"e y {medidas['caixa'][1]}..{medidas['caixa'][3]}.",
    ]
    if not declarado or medida_de_verdade:
        linhas += [
            f"Proporcao (largura/altura): {medidas['proporcao']:.3f} - {_leitura_da_proporcao(medidas['proporcao'])}.",
            f"Eixo mais longo: {medidas['eixo']} ({_texto_do_eixo(medidas)}).",
            f"Inclinacao do eixo principal: {medidas['inclinacao']:.1f} graus a partir da vertical; "
            f"alongamento {_texto_do_alongamento(medidas['alongamento'])}.",
            f"Area: {medidas['area_relativa']:.0%} da caixa (o quanto a forma a enche) e "
            f"{medidas['area_da_imagem']:.1%} da imagem.",
            f"Centro de massa: x {medidas['centro'][0]:.1%}, y {medidas['centro'][1]:.1%} (relativo ao objeto).",
        ]
    if medidas["outras_pecas"] and not declarado:
        mostradas = medidas["outras_pecas"][:5]
        texto = ", ".join(f"{area:.1%} da maior" for area in mostradas)
        restantes = len(medidas["outras_pecas"]) - len(mostradas)
        if restantes > 0:
            texto += f", e mais {restantes} peca(s) menores"
        linhas.append("Outras pecas soltas, ignoradas (a medicao e a maior): " + texto + ".")
    if medidas["buracos"] and not declarado:
        linhas.append(
            "Vazios interiores (o objeto tem "
            + ", ".join(
                f"{buraco['area']:.1%} da area em x {buraco['x']:.0%}/y {buraco['y']:.0%}"
                for buraco in medidas["buracos"]
            )
            + "): zonas interiores com a cor do fundo - vaos, cavidades, ou um detalhe "
            "claro que por acaso tem a cor do fundo (pela cor, os tres sao indistinguiveis; "
            "o desenho do diagnostico marca-os e mostra qual e)."
        )
    linhas += ["", "=== PROPORCOES POR FAIXAS (do topo para a base) ==="]
    if (declarado and not medida_de_verdade) or _sem_objeto(medidas):
        linhas.append(_texto_sem_silhueta(declarado and not medida_de_verdade))
    else:
        linhas.append("y (altura)   largura   centro-x   brilho")
        for (y_pct, largura_pct, x_centro, densidade), brilho in zip(medidas["perfil"], medidas["brilho"]):
            linhas.append(
                f"{y_pct:8.1%}   {largura_pct:7.1%}   {x_centro:8.1%}   {brilho:6.0%}"
                + ("   <- faixa vazia" if densidade <= 0.0 else "")
            )
        linhas.append(_leitura_do_perfil(medidas))
    linhas += ["", f"=== ZONAS MAIS ACESAS ({len(medidas['marcas'])}) ==="]
    if not medidas["marcas"]:
        linhas.append(
            "Nada na imagem passa o limiar de brilho (85% do pico): e de brilho uniforme, "
            "logo nao ha marcas a medir."
        )
    for indice, marca in enumerate(medidas["marcas"], start=1):
        linhas.append(
            f"{indice}. x {marca['x']:.1%}, y {marca['y']:.1%} da caixa do objeto - "
            f"{marca['area']:.0f} px, brilho medio {marca['brilho']:.0%} "
            f"(pico {marca['pico']:.0%}), cheia a {marca['compacidade']:.0%}."
        )
    if medidas["marcas"]:
        maior = medidas["marcas"][0]
        linhas.append(
            f"A maior mancha acesa esta a {maior['y']:.0%} da altura do objeto (a partir do "
            f"topo) e a {maior['x']:.0%} da largura. Ordenadas por MASSA: as particulas de "
            f"fundo ficam para o fim e uma mancha grande e vazia (uma rede de fios) le-se "
            f"pela coluna 'cheia a'."
        )
        if medidas["toca_a_moldura"]:
            linhas.append(
                "Estas marcas foram medidas na IMAGEM inteira, sem depender da silhueta - "
                "continuam a valer quando a separacao do fundo falha."
            )
        if declarado and not medida_de_verdade:
            linhas.append(
                "As posicoes acima sao relativas ao QUADRO que indicaste, nao a imagem: usa-as como "
                "proporcao do objeto que vais modelar."
            )
        if declarado and medida_de_verdade:
            linhas.append(
                "As posicoes acima sao relativas ao OBJETO, que separei do fundo dentro do quadro que "
                "indicaste: usa-as como proporcao do objeto que vais modelar."
            )
        if medidas.get("marcas_fora"):
            linhas.append(
                f"{medidas['marcas_fora']} mancha(s) acesa(s) cai(em) fora do quadro declarado "
                f"(paineis, particulas do fundo) e nao entram na lista."
            )
    return "\n".join(linhas)


def comparar(referencia, modelo, nome_referencia="referencia", nome_modelo="modelo"):
    linhas = [
        "=== REFERENCIA AO LADO DO MODELO (numeros, ambos relativos ao proprio objeto) ===",
        f"{'':22} {'referencia':>12} {'modelo':>12} {'diferenca':>12}",
    ]
    pares = [
        ("proporcao (L/A)", referencia["proporcao"], modelo["proporcao"], "{:.3f}", "{:+.3f}"),
        ("altura (px da foto)", float(referencia["objeto"][1]), float(modelo["objeto"][1]), "{:.0f}", "{:+.0f}"),
        ("area da caixa", referencia["area_relativa"], modelo["area_relativa"], "{:.1%}", "{:+.1%}"),
        ("centro-x", referencia["centro"][0], modelo["centro"][0], "{:.1%}", "{:+.1%}"),
        ("centro-y", referencia["centro"][1], modelo["centro"][1], "{:.1%}", "{:+.1%}"),
        ("inclinacao (graus)", referencia["inclinacao"], modelo["inclinacao"], "{:.1f}", "{:+.1f}"),
    ]
    for rotulo, valor_a, valor_b, formato, formato_da_diferenca in pares:
        linhas.append(
            f"{rotulo:22} {formato.format(valor_a):>12} {formato.format(valor_b):>12} "
            f"{_texto_da_diferenca(valor_a, valor_b, formato_da_diferenca)}"
        )
    linhas += ["", "=== LARGURA POR FAIXA DA ALTURA (o que faz a silhueta) ==="]
    linhas.append("y (altura)   referencia   modelo   diferenca")
    desvios = []
    for (y_pct, largura_ref, centro_ref, _), (_, largura_mod, centro_mod, _) in zip(
        referencia["perfil"], modelo["perfil"]
    ):
        diferenca = largura_mod - largura_ref
        desvios.append(abs(diferenca))
        faixa = f"{y_pct:8.1%}   {largura_ref:9.1%}   {largura_mod:6.1%}   {diferenca:+8.1%}"
        if abs(diferenca) >= 0.10:
            faixa += "   <== aqui divergem"
        linhas.append(faixa)
    if desvios:
        pior = int(np.argmax(desvios))
        linhas += [
            "",
            f"Desvio medio: {np.mean(desvios):.1%} da largura do objeto. "
            f"Pior faixa: y {referencia['perfil'][pior][0]:.1%} "
            f"(referencia {referencia['perfil'][pior][1]:.1%}, modelo {modelo['perfil'][pior][1]:.1%}).",
            _veredicto_do_desvio(float(np.mean(desvios))),
        ]
    linhas += [
        "",
        f"Nota: a silhueta do modelo e a da vista desenhada de '{nome_modelo}'; "
        "o brilho do modelo nao entra na comparacao (depende da luz do desenho, nao da forma).",
    ]
    return "\n".join(linhas)


def desenho(medidas, cor=(255, 104, 72), fundo=None):
    """PNG do diagnostico: contorno, faixas medidas e marcas - o que prova se a medicao acertou."""
    from PIL import Image, ImageDraw

    rgb = medidas["rgb"].astype(np.uint8) if fundo is None else np.full_like(medidas["rgb"], fundo, dtype=np.uint8)
    imagem = Image.fromarray(rgb, "RGB")
    tinta = ImageDraw.Draw(imagem)
    x0, y0, x1, y1 = medidas["caixa"]
    largura = x1 - x0 + 1
    altura = y1 - y0 + 1
    tinta.rectangle([x0, y0, x1, y1], outline=(90, 210, 130), width=2)
    for y_pct, largura_pct, x_centro, _ in medidas["perfil"]:
        y = y0 + y_pct * altura
        tinta.line([x0, y, x1, y], fill=(70, 74, 86), width=1)
        meio = x0 + x_centro * largura
        metade = largura_pct * largura / 2
        tinta.line([meio - metade, y, meio + metade, y], fill=cor, width=3)
    for marca in medidas["marcas"]:
        centro_x = x0 + marca["x"] * largura
        centro_y = y0 + marca["y"] * altura
        meia_largura = max(5.0, marca["caixa"][0] * largura / 2)
        meia_altura = max(5.0, marca["caixa"][1] * altura / 2)
        tinta.ellipse(
            [centro_x - meia_largura, centro_y - meia_altura,
             centro_x + meia_largura, centro_y + meia_altura],
            outline=(255, 214, 84),
            width=2,
        )
    for buraco in medidas["buracos"]:
        centro_x = x0 + buraco["x"] * largura
        centro_y = y0 + buraco["y"] * altura
        tinta.line([centro_x - 4, centro_y - 4, centro_x + 4, centro_y + 4], fill=(120, 200, 255), width=2)
        tinta.line([centro_x - 4, centro_y + 4, centro_x + 4, centro_y - 4], fill=(120, 200, 255), width=2)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _dados_da_imagem(bruto):
    from PIL import Image

    with Image.open(io.BytesIO(bruto)) as bruta:
        tem_alfa = bruta.mode in ("RGBA", "LA", "PA") or "transparency" in bruta.info
        imagem = bruta.convert("RGBA")
    dados = np.asarray(imagem).astype(np.float32)
    return dados[:, :, :3], (dados[:, :, 3] if tem_alfa else None)


def _cinza(rgb):
    return rgb[:, :, 0] * PESO_LUZ[0] + rgb[:, :, 1] * PESO_LUZ[1] + rgb[:, :, 2] * PESO_LUZ[2]


def _mascara_do_objeto(rgb, alfa):
    if alfa is not None and float(alfa.min()) < ALFA_OBJETO:
        return alfa >= ALFA_OBJETO, "canal alfa da imagem"
    fundo, espalhamento = _cor_do_fundo(rgb)
    if espalhamento <= LIMIAR_FUNDO_LISO:
        distancia = np.abs(rgb - fundo).max(axis=2)
        return distancia > LIMIAR_DISTANCIA, (
            f"diferenca para a cor de fundo da borda ({fundo[0]:.0f},{fundo[1]:.0f},{fundo[2]:.0f})"
        )
    return _por_otsu(rgb), "luminancia por Otsu (a borda nao tem cor unica)"


def _cor_do_fundo(rgb):
    altura, largura = rgb.shape[:2]
    faixa = max(1, min(altura, largura) // 12)
    bordas = np.concatenate([
        rgb[:faixa].reshape(-1, 3),
        rgb[-faixa:].reshape(-1, 3),
        rgb[:, :faixa].reshape(-1, 3),
        rgb[:, -faixa:].reshape(-1, 3),
    ])
    fundo = np.median(bordas, axis=0)
    espalhamento = float(np.percentile(np.abs(bordas - fundo).max(axis=1), 85))
    return fundo, espalhamento


def _por_otsu(rgb):
    """Dos dois lados do limiar de Otsu, fica o que se comportar como OBJETO.

    Dois sinais, nesta ordem: o objeto nao encosta a moldura da imagem (o fundo encosta, por
    definicao) e, entre os que nao encostam, e o mais compacto. Cada sinal sozinho engana -
    num fundo com textura a limpeza liga os pontos soltos numa teia que cobre tudo (compacta,
    mas encostada a moldura) e o fundo tem tanta area como o objeto (encostado, mas nem sempre
    o mais compacto). Medido, nao adivinhado.
    """
    import cv2

    cinza = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    _, clara = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    candidatas = [(clara > 0), (cv2.bitwise_not(clara) > 0)]
    limpas = [_limpar(candidata)[0] for candidata in candidatas]
    soltas = [mascara for mascara in limpas if not _toca_a_moldura(mascara)]
    return max(soltas or limpas, key=_compactacao)


LIMITE_DO_QUADRO_NA_IMAGEM = 0.70
LADO_PARA_MEIA_ESCALA = 360


def _por_grabcut(rgb, caixa):
    """Silhueta do objeto DENTRO do quadro, por corte de grafos sobre a cor (GrabCut do OpenCV).

    E o passo que resolve o caso em que objeto e fundo partilham a cor: nenhum limiar separa
    uma malha de pontos do fundo que tem a mesma familia de cor, mas a mistura de cores com a
    vizinhanca separa. O que fica de fora do quadro conta como fundo garantido, por isso o
    quadro tem de deixar moldura a volta (com o quadro a cobrir a imagem toda nao ha fundo e o
    resultado e um borrao).
    """
    import cv2

    x0, y0, x1, y1 = caixa
    largura_imagem, altura_imagem = rgb.shape[1], rgb.shape[0]
    dentro_da_imagem = (x1 - x0 + 1) * (y1 - y0 + 1) / float(largura_imagem * altura_imagem)
    if dentro_da_imagem > LIMITE_DO_QUADRO_NA_IMAGEM:
        return np.zeros(rgb.shape[:2], bool)
    recorte = np.ascontiguousarray(rgb[y0:y1 + 1, x0:x1 + 1].astype(np.uint8))
    if min(recorte.shape[:2]) < 8:
        return np.zeros(rgb.shape[:2], bool)
    escala = 1.0
    if max(recorte.shape[:2]) > LADO_PARA_MEIA_ESCALA:
        escala = 0.5
        recorte = cv2.resize(
            recorte,
            (max(8, int(recorte.shape[1] * escala)), max(8, int(recorte.shape[0] * escala))),
            interpolation=cv2.INTER_AREA,
        )
    bgr = cv2.cvtColor(recorte, cv2.COLOR_RGB2BGR)
    mascara = np.zeros(bgr.shape[:2], np.uint8)
    fundo = np.zeros((1, 65), np.float64)
    frente = np.zeros((1, 65), np.float64)
    retangulo = (1, 1, bgr.shape[1] - 2, bgr.shape[0] - 2)
    cv2.grabCut(bgr, mascara, retangulo, fundo, frente, 5, cv2.GC_INIT_WITH_RECT)
    dentro = ((mascara == cv2.GC_FGD) | (mascara == cv2.GC_PR_FGD)).astype(np.uint8)
    if escala != 1.0:
        dentro = cv2.resize(dentro, (x1 - x0 + 1, y1 - y0 + 1), interpolation=cv2.INTER_NEAREST)
    achado = np.zeros(rgb.shape[:2], bool)
    achado[y0:y1 + 1, x0:x1 + 1] = dentro > 0
    return achado


def _toca_a_moldura(mascara):
    return bool(mascara[0].any() or mascara[-1].any() or mascara[:, 0].any() or mascara[:, -1].any())


def _compactacao(mascara):
    caixa = _caixa(mascara)
    if caixa is None:
        return 0.0
    x0, y0, x1, y1 = caixa
    return float(mascara.sum()) / float((x1 - x0 + 1) * (y1 - y0 + 1))


def _limpar(mascara):
    """Maior peca ligada, sem os pontos soltos; devolve tambem a area das pecas descartadas."""
    import cv2

    nucleo = np.ones((3, 3), np.uint8)
    tinta = mascara.astype(np.uint8) * 255
    tinta = cv2.morphologyEx(tinta, cv2.MORPH_CLOSE, nucleo, iterations=2)
    quantos, rotulos, estatisticas, _ = cv2.connectedComponentsWithStats(tinta, 8)
    if quantos <= 1:
        return tinta > 0, []
    areas = estatisticas[1:, cv2.CC_STAT_AREA]
    maior = 1 + int(np.argmax(areas))
    descartadas = [
        float(area) / float(areas.max())
        for indice, area in enumerate(areas, start=1)
        if indice != maior and float(area) / float(areas.max()) >= MINIMO_PECA
    ]
    return rotulos == maior, sorted(descartadas, reverse=True)


def _preencher(mascara):
    """Silhueta sem furos: o detalhe claro dentro do objeto nao pode furar o contorno."""
    import cv2

    tinta = mascara.astype(np.uint8) * 255
    contornos, _ = cv2.findContours(tinta, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cheia = np.zeros_like(tinta)
    cv2.drawContours(cheia, contornos, -1, 255, thickness=cv2.FILLED)
    return cheia > 0


def _caixa(mascara):
    linhas = np.flatnonzero(mascara.any(axis=1))
    colunas = np.flatnonzero(mascara.any(axis=0))
    if linhas.size == 0 or colunas.size == 0:
        return None
    return int(colunas[0]), int(linhas[0]), int(colunas[-1]), int(linhas[-1])


def _quadro_em_pixeis(quadro, forma):
    if not quadro:
        return None
    altura, largura = forma[:2]
    valores = [float(valor) for valor in quadro]
    if len(valores) != 4:
        raise ValueError("o quadro precisa de 4 numeros: x0, y0, x1, y1")
    x0, y0, x1, y1 = valores
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        raise ValueError(
            "o quadro tem de caber na imagem e ter area: x0 < x1 e y0 < y1, os quatro entre 0% e 100%"
        )
    caixa = (
        int(round(x0 * largura)),
        int(round(y0 * altura)),
        min(largura - 1, int(round(x1 * largura)) - 1),
        min(altura - 1, int(round(y1 * altura)) - 1),
    )
    if (caixa[2] - caixa[0] + 1) * (caixa[3] - caixa[1] + 1) < MINIMO_OBJETO * largura * altura:
        raise ValueError("o quadro declarado e pequeno demais para medir (menos de 0,15% da imagem)")
    return caixa


def _centro(recorte):
    ys, xs = np.nonzero(recorte)
    if xs.size == 0:
        return 0.5, 0.5
    return float(xs.mean()) / recorte.shape[1], float(ys.mean()) / recorte.shape[0]


def _eixos(recorte):
    ys, xs = np.nonzero(recorte)
    if xs.size < 3:
        return 0.0, 1.0
    pontos = np.stack([xs - xs.mean(), ys - ys.mean()], axis=1).astype(np.float64)
    valores, vetores = np.linalg.eigh(pontos.T @ pontos / len(pontos))
    ordem = np.argsort(valores)[::-1]
    maior, menor = float(valores[ordem[0]]), float(valores[ordem[1]])
    alongamento = math.sqrt(maior / menor) if menor > 1e-9 else 99.0
    vetor = vetores[:, ordem[0]]
    inclinacao = math.degrees(math.atan2(abs(float(vetor[0])), abs(float(vetor[1]))))
    return inclinacao, alongamento


def _perfil(recorte, faixas):
    altura, largura = recorte.shape
    linhas = []
    for indice in range(max(1, faixas)):
        topo, base = _limites_da_faixa(indice, altura, faixas)
        fatia = recorte[topo:base]
        colunas = np.flatnonzero(fatia.any(axis=0))
        if colunas.size == 0:
            linhas.append(((indice + 0.5) / faixas, 0.0, 0.5, 0.0))
            continue
        linhas.append((
            (indice + 0.5) / faixas,
            (colunas[-1] - colunas[0] + 1) / largura,
            float(colunas.mean()) / largura,
            float(fatia.mean()),
        ))
    return linhas


def _brilho_por_faixa(cinza, recorte, faixas):
    altura = recorte.shape[0]
    valores = []
    for indice in range(max(1, faixas)):
        topo, base = _limites_da_faixa(indice, altura, faixas)
        fatia = recorte[topo:base]
        if not fatia.any():
            valores.append(0.0)
            continue
        valores.append(float(cinza[topo:base][fatia].mean()) / 255.0)
    return valores


def _limites_da_faixa(indice, altura, faixas):
    topo = min(altura - 1, int(round(indice * altura / faixas)))
    base = max(topo + 1, min(altura, int(round((indice + 1) * altura / faixas))))
    return topo, base


def _marcas_acesas(cinza, caixa, quantas):
    """Regioes ACESAS medidas na IMAGEM, por MASSA - nunca presas a mascara do objeto.

    Dois defeitos medidos na mesma imagem (rosto de malha de pontos sobre fundo salpicado
    de particulas acesas), os dois aqui:
    1. A procura era DENTRO da mascara do objeto, e a mascara sai errada exactamente quando
    objeto e fundo partilham a cor - nessa imagem deixava de fora 98% dos pixeis acesos
    (984 de 47631) e o resultado era ZERO marcas, no momento em que elas mais precisavam de
    sair. A marca (um olho, um emblema) e um sinal de brilho proprio: nao depende da silhueta.
    2. A ordem era por BRILHO MEDIO, e num fundo salpicado o mais brilhante e um ponto
    minusculo e puro, enquanto a marca de verdade e uma mancha com MASSA. Passa a ordenar-se
    por area - as particulas caem para o fim sozinhas - e cada mancha leva a area e o quanto
    enche a propria caixa: uma rede de fios enche 5%, um olho cheio enche 30%.
    """
    import cv2

    if cinza.size == 0:
        return []
    limiar = max(float(cinza.max()) * LIMIAR_ACIMA, LIMIAR_MINIMO)
    acima = (cinza >= limiar).astype(np.uint8)
    if not acima.any():
        return []
    quantos, rotulos, estatisticas, _ = cv2.connectedComponentsWithStats(acima, 8)
    x0, y0, largura_caixa, altura_caixa = caixa
    achados = []
    for indice in range(1, quantos):
        area = float(estatisticas[indice, cv2.CC_STAT_AREA])
        if area < MINIMO_PIXEIS_MARCA:
            continue
        marca = rotulos == indice
        ys, xs = np.nonzero(marca)
        valores = cinza[marca]
        largura_marca = float(estatisticas[indice, cv2.CC_STAT_WIDTH])
        altura_marca = float(estatisticas[indice, cv2.CC_STAT_HEIGHT])
        achados.append({
            "brilho": float(valores.mean()) / 255.0,
            "pico": float(valores.max()) / 255.0,
            "x": (float(xs.mean()) - x0) / largura_caixa,
            "y": (float(ys.mean()) - y0) / altura_caixa,
            "area": area,
            "caixa": (largura_marca / largura_caixa, altura_marca / altura_caixa),
            "compacidade": area / max(1.0, largura_marca * altura_marca),
        })
    achados.sort(key=lambda achado: -achado["area"])
    return achados[:max(1, quantas)]


def _marcas_no_quadro(achados, declarada, quantas):
    if not declarada:
        return achados[:quantas], 0
    dentro = [
        achado for achado in achados
        if 0.0 <= achado["x"] <= 1.0 and 0.0 <= achado["y"] <= 1.0
    ]
    return dentro[:quantas], len(achados) - len(dentro)


def _buracos(recorte, area_objeto):
    import cv2

    contornos, hierarquia = cv2.findContours(
        recorte.astype(np.uint8) * 255, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
    )
    if hierarquia is None:
        return []
    area_objeto = area_objeto or 1.0
    altura, largura = recorte.shape
    achados = []
    for indice, contorno in enumerate(contornos):
        if hierarquia[0][indice][3] == -1:
            continue
        area = float(cv2.contourArea(contorno))
        if area / area_objeto < MINIMO_BURACO:
            continue
        instantes = contorno.reshape(-1, 2).astype(np.float64)
        centro = instantes.mean(axis=0)
        achados.append({
            "area": area / area_objeto,
            "x": float(centro[0]) / largura,
            "y": float(centro[1]) / altura,
        })
    return sorted(achados, key=lambda buraco: -buraco["area"])


def _leitura_da_proporcao(proporcao):
    if proporcao > 1.35:
        return "muito mais larga que alta"
    if proporcao > 1.08:
        return "mais larga que alta"
    if proporcao >= 0.92:
        return "quase quadrada"
    if proporcao >= 0.72:
        return "mais alta que larga"
    return "muito mais alta que larga"


def _texto_do_eixo(medidas):
    largura, altura = medidas["objeto"]
    vezes = max(largura, altura) / max(1, min(largura, altura))
    return f"{vezes:.2f}x o outro lado"


def _texto_do_alongamento(valor):
    if valor >= 4.0:
        return f"{valor:.1f} (forma muito esticada num sentido)"
    if valor >= 2.0:
        return f"{valor:.1f} (claramente esticada)"
    return f"{valor:.1f} (forma cheia, sem direcao dominante)"


def _leitura_do_perfil(medidas):
    perfil = medidas["perfil"]
    if not perfil:
        return ""
    larguras = [(y, largura) for y, largura, _, densidade in perfil if densidade > 0.0]
    if not larguras:
        return "Todas as faixas saem vazias: a medicao nao apanhou o objeto."
    mais_larga = max(larguras, key=lambda par: par[1])
    mais_estreita = min(larguras, key=lambda par: par[1])
    vazias = [y for y, _, _, densidade in perfil if densidade <= 0.0]
    texto = (
        f"Leitura: o ponto mais largo esta a {mais_larga[0]:.0%} da altura ({mais_larga[1]:.0%} de largura) "
        f"e o mais estreito a {mais_estreita[0]:.0%} ({mais_estreita[1]:.0%})."
    )
    if vazias:
        texto += f" Ha {len(vazias)} faixa(s) sem nenhum pixel do objeto."
    return texto


def _texto_da_diferenca(valor_a, valor_b, formato):
    if abs(valor_a) < 1e-9 and abs(valor_b) < 1e-9:
        return ""
    return formato.format(valor_b - valor_a)


def _texto_sem_silhueta(declarado):
    if declarado:
        return (
            "Largura por faixa nao medida: ela sairia da silhueta, que nao se separa do fundo nesta "
            "imagem. Deste relato aproveitam-se o quadro acima e as marcas acesas abaixo."
        )
    return (
        "Nao ha largura por faixa a relatar: nada foi separado do fundo e a caixa do objeto e a "
        "imagem inteira, logo cada faixa mediria a largura da propria imagem. O que vale deste "
        "relato sao as marcas acesas abaixo - e um quadro, se o indicares."
    )


def _veredicto_do_desvio(desvio):
    if desvio <= 0.03:
        return "As duas silhuetas praticamente coincidem faixa a faixa."
    if desvio <= 0.08:
        return "As silhuetas sao parecidas; corrige as faixas marcadas acima."
    if desvio <= 0.18:
        return "Diferenca clara de forma: a proporcao geral ainda nao bate com a referencia."
    return "A forma ainda e outra coisa: trata a geometria antes de afinar detalhe."


def _aviso_de_confianca(medidas):
    """Bloco de aviso quando a separacao do fundo nao sustenta as medidas (vazio quando sustenta)."""
    motivos = []
    if medidas["toca_a_moldura"]:
        motivos.append("a silhueta encosta a moldura da imagem")
    if medidas["area_relativa"] < LIMIAR_COMPACTA:
        motivos.append(f"a silhueta enche so {medidas['area_relativa']:.0%} da sua propria caixa")
    soltas = [area for area in medidas["outras_pecas"] if area >= LIMIAR_PECA_SOLTA]
    if soltas:
        motivos.append(
            f"ha {len(soltas)} peca(s) solta(s), a maior com {soltas[0]:.0%} do tamanho da principal"
        )
    if not motivos:
        return []
    return [
        "",
        "=== ATENCAO: NAO HA SILHUETA DE CONFIANCA ===",
        "As medidas abaixo NAO descrevem a forma do objeto. Motivo: " + "; ".join(motivos) + ".",
        "Acontece quando objeto e fundo partilham a cor ou a luminosidade (malha de pontos, "
        "wireframe, holograma, fundo texturizado) - pela cor nao ha como separa-los, e nenhum "
        "limiar resolve isso. O que resolve: recortar a imagem ao objeto sobre fundo liso, ou "
        "fotografar em contraluz. Sem isso, deste relato valem as marcas acesas (nao dependem da "
        "silhueta) e o quadro, quando o indicas: a forma, essa, nao sai daqui.",
        "",
    ]


def _bloco_do_quadro(medidas):
    largura_imagem, altura_imagem = medidas["imagem"]
    x0, y0, x1, y1 = medidas["caixa"]
    largura_objeto, altura_objeto = medidas["objeto"]
    return [
        "=== QUADRO DECLARADO (indicado por quem olhou, nao medido) ===",
        f"Quadro: x {x0 / max(1, largura_imagem - 1):.1%} a {x1 / max(1, largura_imagem - 1):.1%} e "
        f"y {y0 / max(1, altura_imagem - 1):.1%} a {y1 / max(1, altura_imagem - 1):.1%} da imagem "
        f"(em px: x {x0}..{x1}, y {y0}..{y1} - {largura_objeto}x{altura_objeto} px, "
        f"proporcao {medidas['proporcao']:.3f}).",
        ("O quadro foi o ponto de partida: a separacao do fundo correu DENTRO dele e o objeto saiu de "
         "la medido, nao indicado." if medidas.get("silhueta", True) else
         "A separacao do fundo nao encontrou o objeto nesta imagem, por isso a caixa do objeto e ESTA - "
         "indicada, nao medida.")
        + " Todas as percentagens abaixo sao relativas a ela e nao a imagem: e o "
        "que torna a medida utilizavel para modelar.",
        "",
    ]


def _sem_objeto(medidas):
    """True quando a 'caixa do objeto' e a imagem inteira: nada foi separado do fundo."""
    largura, altura = medidas["imagem"]
    return tuple(medidas["caixa"]) == (0, 0, largura - 1, altura - 1)


