import math

from shapely.geometry import Polygon
from shapely.ops import triangulate


def _area_2d(contorno):
    area = 0.0
    for (x1, y1), (x2, y2) in pares_fechados(contorno):
        area += x1 * y2 - x2 * y1
    return area * 0.5


def _cruz_2d(u, v, w):
    return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])


def _estritamente_dentro(ponto, a, b, c):
    return (
        _cruz_2d(a, b, ponto) > 1e-9
        and _cruz_2d(b, c, ponto) > 1e-9
        and _cruz_2d(c, a, ponto) > 1e-9
    )


def _no_segmento(a, b, ponto):
    return (
        min(a[0], b[0]) - 1e-9 <= ponto[0] <= max(a[0], b[0]) + 1e-9
        and min(a[1], b[1]) - 1e-9 <= ponto[1] <= max(a[1], b[1]) + 1e-9
    )


def _bloqueia(a, b, c, d):
    d1, d2 = _cruz_2d(a, b, c), _cruz_2d(a, b, d)
    d3, d4 = _cruz_2d(c, d, a), _cruz_2d(c, d, b)
    if ((d1 > 1e-9) != (d2 > 1e-9)) and ((d3 > 1e-9) != (d4 > 1e-9)):
        return True
    if abs(d1) <= 1e-9 and _no_segmento(a, b, c):
        return True
    if abs(d2) <= 1e-9 and _no_segmento(a, b, d):
        return True
    if abs(d3) <= 1e-9 and _no_segmento(c, d, a):
        return True
    if abs(d4) <= 1e-9 and _no_segmento(c, d, b):
        return True
    return False


def _ponte_livre(contorno, buraco, indice_buraco, indice_contorno):
    a = buraco[indice_buraco]
    b = contorno[indice_contorno]
    total_buraco = len(buraco)
    for indice in range(total_buraco):
        seguinte = (indice + 1) % total_buraco
        if indice == indice_buraco or seguinte == indice_buraco:
            continue
        if _bloqueia(a, b, buraco[indice], buraco[seguinte]):
            return False
    total = len(contorno)
    for indice in range(total):
        seguinte = (indice + 1) % total
        if indice == indice_contorno or seguinte == indice_contorno:
            continue
        if _bloqueia(a, b, contorno[indice], contorno[seguinte]):
            return False
    return True


def _ponte(contorno, buraco, etiquetas):
    candidatos = sorted(
        (
            (buraco[indice_buraco][0] - contorno[indice_contorno][0]) ** 2
            + (buraco[indice_buraco][1] - contorno[indice_contorno][1]) ** 2,
            indice_buraco,
            indice_contorno,
        )
        for indice_buraco in range(len(buraco))
        for indice_contorno in range(len(contorno))
        if etiquetas[indice_contorno] == "externo"
    )
    for _, indice_buraco, indice_contorno in candidatos:
        if _ponte_livre(contorno, buraco, indice_buraco, indice_contorno):
            return indice_buraco, indice_contorno
    raise ValueError("nao ha ponte livre entre o buraco e o contorno externo")


def _sem_repetidos(contorno, tolerancia=1e-9):
    unicos = []
    for ponto in contorno:
        if not unicos or math.dist(ponto, unicos[-1]) > tolerancia:
            unicos.append(ponto)
    while len(unicos) > 1 and math.dist(unicos[0], unicos[-1]) <= tolerancia:
        unicos.pop()
    return unicos


def _sem_colineares(contorno, tolerancia=1e-12):
    atual = list(contorno)
    for _ in range(len(atual)):
        if len(atual) < 3:
            break
        total = len(atual)
        limpos = [
            atual[posicao]
            for posicao in range(total)
            if abs(_cruz_2d(atual[posicao - 1], atual[posicao], atual[(posicao + 1) % total])) > tolerancia
        ]
        if len(limpos) == len(atual) or len(limpos) < 3:
            break
        atual = limpos
    return atual


def _reflexos(contorno, indices):
    return [
        indices[lugar]
        for lugar in range(len(indices))
        if _cruz_2d(
            contorno[indices[lugar - 1]],
            contorno[indices[lugar]],
            contorno[indices[(lugar + 1) % len(indices)]],
        ) < -1e-12
    ]


def _convexo(contorno):
    viragens = set()
    total = len(contorno)
    for posicao in range(total):
        cruz = _cruz_2d(
            contorno[posicao - 1], contorno[posicao], contorno[(posicao + 1) % total]
        )
        if abs(cruz) > 1e-12:
            viragens.add(cruz > 0.0)
    return len(viragens) < 2


def _aneis_das_etiquetas(etiquetas):
    aneis = [[indice for indice, rotulo in enumerate(etiquetas) if rotulo == "externo"]]
    vaos = sorted(
        {rotulo for rotulo in etiquetas if rotulo.startswith("vao")},
        key=lambda rotulo: int(rotulo[3:]),
    )
    for rotulo in vaos:
        aneis.append([indice for indice, atual in enumerate(etiquetas) if atual == rotulo])
    return aneis


def _delaunay(pontos, aneis):
    """Triangulos de Delaunay inteiramente dentro da face; None quando sobra area por cobrir.

    Decide por centroide, e por isso perde os triangulos que atravessam uma fronteira
    concava: a soma das areas aceites e conferida contra a area da face antes de o
    resultado ser aceite, e uma lacuna faz cair no ear clipping.
    """
    face = Polygon(
        [pontos[indice] for indice in aneis[0]],
        [[pontos[indice] for indice in anel] for anel in aneis[1:]],
    )
    indice_do_ponto = {}
    for indice, ponto in enumerate(pontos):
        indice_do_ponto[(round(ponto[0], 9), round(ponto[1], 9))] = indice
    escolhidos = []
    coberto = 0.0
    for triangulo in triangulate(face):
        if not face.contains(triangulo.representative_point()):
            continue
        cantos = list(triangulo.exterior.coords)[:3]
        indices = [indice_do_ponto.get((round(x, 9), round(y, 9))) for x, y in cantos]
        if None in indices or len(set(indices)) < 3:
            continue
        if _cruz_2d(pontos[indices[0]], pontos[indices[1]], pontos[indices[2]]) < 0.0:
            indices[1], indices[2] = indices[2], indices[1]
        escolhidos.append(tuple(indices))
        coberto += triangulo.area
    if abs(coberto - face.area) > 1e-9 * max(1.0, face.area):
        return None
    return escolhidos


def triangular(contorno):
    indices = list(range(len(contorno)))
    if _area_2d(contorno) < 0.0:
        indices.reverse()
    triangulos = []
    while len(indices) > 3:
        reflexos = _reflexos(contorno, indices)
        for posicao in range(len(indices)):
            anterior = indices[posicao - 1]
            atual = indices[posicao]
            seguinte = indices[(posicao + 1) % len(indices)]
            a, b, c = contorno[anterior], contorno[atual], contorno[seguinte]
            cruz = _cruz_2d(a, b, c)
            if cruz <= 1e-12:
                continue
            if any(
                _estritamente_dentro(contorno[outro], a, b, c)
                for outro in reflexos
                if outro not in (anterior, atual, seguinte)
            ):
                continue
            triangulos.append((anterior, atual, seguinte))
            indices.pop(posicao)
            break
        else:
            raise ValueError(
                f"o ear clipping travou com {len(indices)} vertices por fechar: cada vao liga-se "
                "a borda por uma fenda de largura zero, e vaos cujas fendas se cruzam esgotam as "
                "orelhas. Use uma placa por vao, afaste os vaos, ou um contorno externo convexo "
                "(esse triangula pela Delaunay e aguenta qualquer numero de vaos)."
            )
    triangulos.append((indices[0], indices[1], indices[2]))
    return triangulos


def _vaos_validos(externo, buracos):
    contorno = Polygon(externo)
    caixas = [Polygon(buraco) for buraco in buracos]
    for numero, caixa in enumerate(caixas):
        if not contorno.contains(caixa):
            raise ValueError(f"o vao {numero} nao cabe dentro do contorno externo")
        for anterior in range(numero):
            if caixa.intersects(caixas[anterior]):
                raise ValueError(
                    f"os vaos {anterior} e {numero} tocam-se ou sobrepoem-se: "
                    "a ponte entre o vao e a borda nao encontra caminho. "
                    "Use um vao por placa, ou afaste-os."
                )


def contorno_com_vaos(externo_2d, buracos_2d):
    externo = _sem_colineares(_sem_repetidos(externo_2d))
    if _area_2d(externo) < 0.0:
        externo.reverse()
    limpos = []
    for buraco in buracos_2d:
        pontos = _sem_colineares(_sem_repetidos(buraco))
        if _area_2d(pontos) > 0.0:
            pontos.reverse()
        limpos.append(pontos)
    _vaos_validos(externo, limpos)
    contorno = list(externo)
    etiquetas = ["externo"] * len(externo)
    for numero, buraco in enumerate(limpos):
        indice_buraco, indice_contorno = _ponte(contorno, buraco, etiquetas)
        ciclo = buraco[indice_buraco:] + buraco[:indice_buraco]
        inicio = indice_contorno + 1
        rotulo = "vao%d" % numero
        contorno = contorno[:inicio] + ciclo + [ciclo[0]] + contorno[indice_contorno:]
        etiquetas = (
            etiquetas[:inicio]
            + [rotulo] * len(ciclo)
            + ["fecho", "fecho"]
            + etiquetas[inicio:]
        )
    return contorno, etiquetas


def triangular_com_vaos(externo_2d, buracos_2d):
    """(pontos, aneis, triangulos) de uma face plana com vaos.

    aneis[0] e o contorno externo (CCW) e os restantes os vaos (CW); os triangulos
    indexam a lista de pontos devolvida. O externo convexo usa a Delaunay filtrada,
    que aguenta qualquer numero de vaos; o concavo usa o ear clipping com pontes, que
    e mais geral mas trava a partir de tres vaos.
    """
    externo = _sem_colineares(_sem_repetidos(externo_2d))
    if _area_2d(externo) < 0.0:
        externo.reverse()
    vaos = []
    for buraco in buracos_2d:
        limpo = _sem_colineares(_sem_repetidos(buraco))
        if _area_2d(limpo) > 0.0:
            limpo.reverse()
        vaos.append(limpo)
    _vaos_validos(externo, vaos)
    if not vaos:
        return externo, [list(range(len(externo)))], triangular(externo)
    aneis = []
    inicio = 0
    for anel in [externo] + vaos:
        aneis.append(list(range(inicio, inicio + len(anel))))
        inicio += len(anel)
    pontos = [ponto for anel in [externo] + vaos for ponto in anel]
    if _convexo(externo):
        triangulos = _delaunay(pontos, aneis)
        if triangulos is not None:
            return pontos, aneis, triangulos
    contorno, etiquetas = contorno_com_vaos(externo, vaos)
    return contorno, _aneis_das_etiquetas(etiquetas), triangular(contorno)


def pares_fechados(contorno):
    return list(zip(contorno, list(contorno[1:]) + [contorno[0]]))
