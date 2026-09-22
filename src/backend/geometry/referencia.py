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
MINIMO_MARCA = 0.0015
MAXIMO_MARCA = 0.6
LIMIAR_COMPACTA = 0.15
PESO_LUZ = (0.299, 0.587, 0.114)


def carregar(caminho):
    """(rgb float32, alfa ou None) de um ficheiro de imagem, ja em RGBA."""
    with open(caminho, "rb") as ficheiro:
        return _dados_da_imagem(ficheiro.read())


def medir(caminho, faixas=FAIXAS, marcas=MARCAS):
    rgb, alfa = carregar(caminho)
    return medir_dados(rgb, alfa, faixas, marcas)


def medir_bytes(bruto, faixas=FAIXAS, marcas=MARCAS):
    """Como medir(), mas de bytes de imagem - um render em memoria nao passa pelo disco."""
    rgb, alfa = _dados_da_imagem(bruto)
    return medir_dados(rgb, alfa, faixas, marcas)


def medir_dados(rgb, alfa=None, faixas=FAIXAS, marcas=MARCAS):
    bruta, como = _mascara_do_objeto(rgb, alfa)
    furada, outras = _limpar(bruta)
    cheia = _preencher(furada)
    caixa = _caixa(cheia)
    if caixa is None:
        raise ValueError("nao encontrei objeto nenhum: a imagem parece vazia ou de uma cor so")
    x0, y0, x1, y1 = caixa
    largura = x1 - x0 + 1
    altura = y1 - y0 + 1
    if largura * altura < MINIMO_OBJETO * cheia.size:
        raise ValueError("o objeto encontrado e pequeno demais para medir (menos de 0,15% da imagem)")
    recorte = cheia[y0:y1 + 1, x0:x1 + 1]
    cinza = _cinza(rgb)[y0:y1 + 1, x0:x1 + 1]
    inclinacao, alongamento = _eixos(recorte)
    centro = _centro(recorte)
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
        "marcas": _marcas_acesas(cinza, recorte, marcas),
        "buracos": _buracos(furada[y0:y1 + 1, x0:x1 + 1], float(recorte.sum())),
        "outras_pecas": outras,
        "toca_a_moldura": _toca_a_moldura(cheia),
        "rgb": rgb,
        "mascara": cheia,
    }
    return medidas


def relato(medidas, caminho=""):
    largura_imagem, altura_imagem = medidas["imagem"]
    largura_objeto, altura_objeto = medidas["objeto"]
    linhas = [
        f"=== SILHUETA DE {caminho or 'imagem'} ===",
        f"Imagem: {largura_imagem}x{altura_imagem} px. Objeto separado do fundo por: {medidas['como']}.",
        f"Objeto: {largura_objeto}x{altura_objeto} px, caixa em x {medidas['caixa'][0]}..{medidas['caixa'][2]} "
        f"e y {medidas['caixa'][1]}..{medidas['caixa'][3]}.",
        f"Proporcao (largura/altura): {medidas['proporcao']:.3f} - {_leitura_da_proporcao(medidas['proporcao'])}.",
        f"Eixo mais longo: {medidas['eixo']} ({_texto_do_eixo(medidas)}).",
        f"Inclinacao do eixo principal: {medidas['inclinacao']:.1f} graus a partir da vertical; "
        f"alongamento {_texto_do_alongamento(medidas['alongamento'])}.",
        f"Area: {medidas['area_relativa']:.0%} da caixa (o quanto a forma a enche) e "
        f"{medidas['area_da_imagem']:.1%} da imagem.",
        f"Centro de massa: x {medidas['centro'][0]:.1%}, y {medidas['centro'][1]:.1%} (relativo ao objeto).",
    ]
    if medidas["outras_pecas"]:
        linhas.append(
            "Outras pecas soltas, ignoradas (a medicao e a maior): "
            + ", ".join(f"{area:.1%} da maior" for area in medidas["outras_pecas"])
            + "."
        )
    if medidas["toca_a_moldura"]:
        linhas.append(
            "AVISO: a silhueta encosta a moldura da imagem - ou o objeto sai do enquadramento, "
            "ou a separacao do fundo ficou com o fundo em vez do objeto. Confirme no desenho "
            "do diagnostico antes de usar estas medidas."
        )
    if medidas["area_relativa"] < LIMIAR_COMPACTA:
        linhas.append(
            f"AVISO: a silhueta enche so {medidas['area_relativa']:.0%} da sua propria caixa - "
            "pouco para uma forma cheia. A separacao do fundo pode ter falhado: olhe para o "
            "desenho do diagnostico antes de confiar nestas medidas."
        )
    if medidas["buracos"]:
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
    linhas.append("y (altura)   largura   centro-x   brilho")
    for (y_pct, largura_pct, x_centro, densidade), brilho in zip(medidas["perfil"], medidas["brilho"]):
        linhas.append(
            f"{y_pct:8.1%}   {largura_pct:7.1%}   {x_centro:8.1%}   {brilho:6.0%}"
            + ("   <- faixa vazia" if densidade <= 0.0 else "")
        )
    linhas.append(_leitura_do_perfil(medidas))
    linhas += ["", f"=== ZONAS MAIS ACESAS ({len(medidas['marcas'])}) ==="]
    if not medidas["marcas"]:
        linhas.append("Nenhuma zona acesa por cima das outras: a imagem e de brilho uniforme.")
    for indice, marca in enumerate(medidas["marcas"], start=1):
        linhas.append(
            f"{indice}. x {marca['x']:.1%}, y {marca['y']:.1%} da caixa do objeto, "
            f"brilho medio {marca['brilho']:.0%} (pico {marca['pico']:.0%})."
        )
    if medidas["marcas"]:
        mais_acesa = medidas["marcas"][0]
        linhas.append(
            f"A zona mais acesa esta a {mais_acesa['y']:.0%} da altura do objeto "
            f"(a partir do topo) e a {mais_acesa['x']:.0%} da largura."
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
        raio = max(5, int(min(largura, altura) * 0.02))
        tinta.ellipse(
            [centro_x - raio, centro_y - raio, centro_x + raio, centro_y + raio],
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


def _marcas_acesas(cinza, recorte, quantas):
    """Regioes ACESAS de verdade: o que passa do limiar, agrupado - nunca a media de um bloco.

    A media de um bloco dilui uma marca pequena no escuro a volta (um disco branco de 25 px
    num bloco de 17x10 saia a 32% de brilho e a 10 pontos percentuais do sitio certo), por
    isso a marca e a regiao acima do limiar, medida pelo seu proprio centro.
    """
    import cv2

    dentro = cinza[recorte]
    if dentro.size == 0:
        return []
    limiar = max(float(dentro.max()) * LIMIAR_ACIMA, LIMIAR_MINIMO)
    acima = ((cinza >= limiar) & recorte).astype(np.uint8)
    if not acima.any():
        return []
    quantos, rotulos, estatisticas, _ = cv2.connectedComponentsWithStats(acima, 8)
    area_objeto = float(recorte.sum()) or 1.0
    altura, largura = recorte.shape
    achados = []
    for indice in range(1, quantos):
        area = float(estatisticas[indice, cv2.CC_STAT_AREA])
        if area / area_objeto < MINIMO_MARCA or area / area_objeto > MAXIMO_MARCA:
            continue
        marca = rotulos == indice
        ys, xs = np.nonzero(marca)
        valores = cinza[marca]
        achados.append({
            "brilho": float(valores.mean()) / 255.0,
            "pico": float(valores.max()) / 255.0,
            "x": float(xs.mean()) / largura,
            "y": float(ys.mean()) / altura,
            "area": area / area_objeto,
        })
    achados.sort(key=lambda achado: -achado["brilho"])
    return achados[:max(1, quantas)]


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


def _veredicto_do_desvio(desvio):
    if desvio <= 0.03:
        return "As duas silhuetas praticamente coincidem faixa a faixa."
    if desvio <= 0.08:
        return "As silhuetas sao parecidas; corrige as faixas marcadas acima."
    if desvio <= 0.18:
        return "Diferenca clara de forma: a proporcao geral ainda nao bate com a referencia."
    return "A forma ainda e outra coisa: trata a geometria antes de afinar detalhe."
