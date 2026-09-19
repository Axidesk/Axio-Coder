import math

from src.backend.geometry.poligonos import pares_fechados, triangular_com_vaos


def somar(malhas):
    vertices = []
    faces = []
    for lista_vertices, lista_faces in malhas:
        deslocamento = len(vertices)
        vertices.extend(lista_vertices)
        faces.extend(tuple(indice + deslocamento for indice in face) for face in lista_faces)
    return vertices, faces


def volume_com_sinal(vertices, faces):
    total = 0.0
    for face in faces:
        a, b, c = vertices[face[0]], vertices[face[1]], vertices[face[2]]
        total += produto_escalar(a, produto_vetorial(b, c))
    return total / 6.0


def malha_fechada(vertices, faces, casas=6):
    contagem = {}
    for face in faces:
        anel = [vertices[indice] for indice in face]
        for inicio, fim in pares_fechados(anel):
            a = tuple(round(valor, casas) for valor in inicio)
            b = tuple(round(valor, casas) for valor in fim)
            chave = (a, b) if a <= b else (b, a)
            contagem[chave] = contagem.get(chave, 0) + 1
    soltas = sum(1 for vezes in contagem.values() if vezes != 2)
    return soltas == 0, soltas


def resumo(malhas):
    return (
        len(malhas),
        sum(len(faces) for _, faces in malhas),
        sum(len(vertices) for vertices, _ in malhas),
    )


def somar_pontos(*pontos):
    return tuple(sum(valores) for valores in zip(*pontos))


def diferenca(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def escalar(vetor, fator):
    return (vetor[0] * fator, vetor[1] * fator, vetor[2] * fator)


def produto_vetorial(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def produto_escalar(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def norma(vetor):
    return math.sqrt(vetor[0] ** 2 + vetor[1] ** 2 + vetor[2] ** 2)


def unitario(vetor):
    tamanho = norma(vetor)
    if tamanho < 1e-12:
        raise ValueError("nao e possivel normalizar um vetor nulo")
    return (vetor[0] / tamanho, vetor[1] / tamanho, vetor[2] / tamanho)


def base_local(normal):
    eixo = unitario(normal)
    apoio = (0.0, 0.0, 1.0) if abs(eixo[2]) < 0.9 else (0.0, 1.0, 0.0)
    eixo_u = unitario(produto_vetorial(apoio, eixo))
    eixo_v = produto_vetorial(eixo, eixo_u)
    return eixo_u, eixo_v


def rodar_2d(pontos, angulo, origem=(0.0, 0.0)):
    """Roda pontos no plano em torno de uma origem."""
    cosseno, seno = math.cos(angulo), math.sin(angulo)
    rodados = []
    for x, y in pontos:
        braco_x, braco_y = x - origem[0], y - origem[1]
        rodados.append((
            origem[0] + braco_x * cosseno - braco_y * seno,
            origem[1] + braco_x * seno + braco_y * cosseno,
        ))
    return rodados


def polar(raio, angulo, z):
    return (raio * math.cos(angulo), raio * math.sin(angulo), z)


def tronco(raio_base, raio_topo, z_base, z_topo, lados=48, tampas=True):
    vertices = [polar(raio_base, math.tau * i / lados, z_base) for i in range(lados)]
    vertices += [polar(raio_topo, math.tau * i / lados, z_topo) for i in range(lados)]
    faces = []
    for indice in range(lados):
        seguinte = (indice + 1) % lados
        faces.append((indice, seguinte, lados + seguinte))
        faces.append((indice, lados + seguinte, lados + indice))
    if tampas:
        baixo = len(vertices)
        vertices.append((0.0, 0.0, z_base))
        topo = len(vertices)
        vertices.append((0.0, 0.0, z_topo))
        for indice in range(lados):
            seguinte = (indice + 1) % lados
            faces.append((baixo, seguinte, indice))
            faces.append((topo, lados + indice, lados + seguinte))
    return vertices, faces


def anel(raio_interno, raio_externo, z_base, z_topo, lados=64):
    vertices = []
    for z in (z_base, z_topo):
        for raio in (raio_externo, raio_interno):
            vertices += [polar(raio, math.tau * i / lados, z) for i in range(lados)]
    externo_baixo, interno_baixo, externo_topo, interno_topo = 0, lados, 2 * lados, 3 * lados
    faces = []
    for indice in range(lados):
        seguinte = (indice + 1) % lados
        faces += [
            (externo_baixo + indice, externo_baixo + seguinte, externo_topo + seguinte),
            (externo_baixo + indice, externo_topo + seguinte, externo_topo + indice),
            (interno_baixo + indice, interno_topo + seguinte, interno_baixo + seguinte),
            (interno_baixo + indice, interno_topo + indice, interno_topo + seguinte),
            (externo_baixo + indice, interno_baixo + indice, interno_baixo + seguinte),
            (externo_baixo + indice, interno_baixo + seguinte, externo_baixo + seguinte),
            (externo_topo + indice, externo_topo + seguinte, interno_topo + seguinte),
            (externo_topo + indice, interno_topo + seguinte, interno_topo + indice),
        ]
    return vertices, faces


def toro(raio_maior, raio_tubo, segmentos_maiores=48, segmentos_tubo=8, z=0.0, achatamento=1.0):
    vertices = []
    for indice in range(segmentos_maiores):
        theta = math.tau * indice / segmentos_maiores
        for outro in range(segmentos_tubo):
            phi = math.tau * outro / segmentos_tubo
            radial = raio_maior + raio_tubo * math.cos(phi)
            vertices.append(
                (radial * math.cos(theta), radial * math.sin(theta), z + achatamento * raio_tubo * math.sin(phi))
            )
    faces = []
    for indice in range(segmentos_maiores):
        proximo = (indice + 1) % segmentos_maiores
        for outro in range(segmentos_tubo):
            seguinte = (outro + 1) % segmentos_tubo
            a = indice * segmentos_tubo + outro
            b = proximo * segmentos_tubo + outro
            c = proximo * segmentos_tubo + seguinte
            d = indice * segmentos_tubo + seguinte
            faces += [(a, b, c), (a, c, d)]
    return vertices, faces


def tubo(ponto_a, ponto_b, raio, lados=8):
    direcao = unitario(diferenca(ponto_b, ponto_a))
    eixo_u, eixo_v = base_local(direcao)
    vertices = []
    for ponto in (ponto_a, ponto_b):
        for indice in range(lados):
            angulo = math.tau * indice / lados
            deslocamento = somar_pontos(
                escalar(eixo_u, raio * math.cos(angulo)),
                escalar(eixo_v, raio * math.sin(angulo)),
            )
            vertices.append(somar_pontos(ponto, deslocamento))
    faces = []
    for indice in range(lados):
        seguinte = (indice + 1) % lados
        faces += [
            (indice, seguinte, lados + seguinte),
            (indice, lados + seguinte, lados + indice),
            (0, seguinte, indice),
            (lados, lados + indice, lados + seguinte),
        ]
    return vertices, faces


def prisma_entre(quad_externo, quad_interno):
    vertices = list(quad_externo) + list(quad_interno)
    n = len(quad_externo)
    faces = []
    for indice in range(n):
        seguinte = (indice + 1) % n
        faces.append((indice, seguinte, n + seguinte))
        faces.append((indice, n + seguinte, n + indice))
    for indice in range(1, n - 1):
        faces.append((0, indice + 1, indice))
        faces.append((n, n + indice, n + indice + 1))
    if volume_com_sinal(vertices, faces) < 0.0:
        faces = [tuple(reversed(face)) for face in faces]
    return vertices, faces


def normal_do_contorno(contorno):
    acumulado = (0.0, 0.0, 0.0)
    for atual, seguinte in pares_fechados(contorno):
        acumulado = somar_pontos(
            acumulado,
            (
                (atual[1] - seguinte[1]) * (atual[2] + seguinte[2]),
                (atual[2] - seguinte[2]) * (atual[0] + seguinte[0]),
                (atual[0] - seguinte[0]) * (atual[1] + seguinte[1]),
            ),
        )
    return unitario(acumulado)


def orientar_contorno(contorno, eixo):
    if produto_escalar(normal_do_contorno(contorno), eixo) < 0.0:
        return list(reversed(contorno))
    return list(contorno)


def centro_do_contorno(contorno):
    total = len(contorno)
    return tuple(sum(ponto[eixo] for ponto in contorno) / total for eixo in range(3))


def expandir_contorno(contorno, folga):
    """Afasta cada vertice do centro do contorno, abrindo folga sem lhe mudar a forma."""
    centro = centro_do_contorno(contorno)
    expandido = []
    for ponto in contorno:
        braco = diferenca(ponto, centro)
        distancia = norma(braco)
        if distancia < 1e-12:
            expandido.append(ponto)
        else:
            expandido.append(somar_pontos(ponto, escalar(braco, folga / distancia)))
    return expandido


def plano_do_contorno(contorno):
    origem = centro_do_contorno(contorno)
    eixo_u, eixo_v = base_local(normal_do_contorno(contorno))
    return origem, eixo_u, eixo_v


def para_plano(ponto, origem, eixo_u, eixo_v):
    deslocamento = diferenca(ponto, origem)
    return produto_escalar(deslocamento, eixo_u), produto_escalar(deslocamento, eixo_v)


def contorno_no_plano(contorno_2d, centro, normal):
    eixo_u, eixo_v = base_local(normal)
    return [
        somar_pontos(centro, escalar(eixo_u, x), escalar(eixo_v, y))
        for x, y in contorno_2d
    ]


def placa_vazada(externo, buracos, espessura):
    origem, eixo_u, eixo_v = plano_do_contorno(externo)
    normal = normal_do_contorno(externo)
    pontos, aneis, triangulos = triangular_com_vaos(
        [para_plano(ponto, origem, eixo_u, eixo_v) for ponto in externo],
        [[para_plano(ponto, origem, eixo_u, eixo_v) for ponto in buraco] for buraco in buracos],
    )
    vertices = []
    for recuo in (0.0, -espessura):
        base = somar_pontos(origem, escalar(normal, recuo))
        for x, y in pontos:
            vertices.append(somar_pontos(base, escalar(eixo_u, x), escalar(eixo_v, y)))
    total = len(pontos)
    faces = []
    for primeiro, segundo, terceiro in triangulos:
        faces.append((primeiro, segundo, terceiro))
        faces.append((total + primeiro, total + terceiro, total + segundo))
    for anel in aneis:
        for posicao, indice in enumerate(anel):
            seguinte = anel[(posicao + 1) % len(anel)]
            faces += [(indice, total + indice, total + seguinte), (indice, total + seguinte, seguinte)]
    return vertices, faces


def faixa(aresta_direita, aresta_esquerda, interior_direita, interior_esquerda):
    n = len(aresta_direita)
    aneis = (aresta_esquerda, interior_direita, interior_esquerda)
    if n < 2 or any(len(lista) != n for lista in aneis):
        raise ValueError("faixa precisa de quatro aneis com o mesmo numero de pontos (>= 2)")
    vertices = (
        list(aresta_direita) + list(aresta_esquerda)
        + list(interior_direita) + list(interior_esquerda)
    )
    faces = []
    for k in range(n - 1):
        a, a2 = k, k + 1
        b, b2 = n + k, n + k + 1
        ia, ia2 = 2 * n + k, 2 * n + k + 1
        ib, ib2 = 3 * n + k, 3 * n + k + 1
        faces += [(a, a2, b2), (a, b2, b), (ia, ib, ib2), (ia, ib2, ia2)]
        faces += [(a, ia, ia2), (a, ia2, a2), (b, b2, ib2), (b, ib2, ib)]
    for k in (0, n - 1):
        a, b, ia, ib = k, n + k, 2 * n + k, 3 * n + k
        if k == 0:
            faces += [(a, b, ib), (a, ib, ia)]
        else:
            faces += [(a, ib, b), (a, ia, ib)]
    return vertices, [tuple(reversed(face)) for face in faces]


_FACES_DA_CAIXA = (
    (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
    (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
    (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
)


def caixa(centro, largura, profundidade, altura):
    cx, cy, cz = centro
    meia_l, meia_p, meia_a = largura / 2, profundidade / 2, altura / 2
    vertices = [
        (cx - meia_l, cy - meia_p, cz - meia_a), (cx + meia_l, cy - meia_p, cz - meia_a),
        (cx + meia_l, cy + meia_p, cz - meia_a), (cx - meia_l, cy + meia_p, cz - meia_a),
        (cx - meia_l, cy - meia_p, cz + meia_a), (cx + meia_l, cy - meia_p, cz + meia_a),
        (cx + meia_l, cy + meia_p, cz + meia_a), (cx - meia_l, cy + meia_p, cz + meia_a),
    ]
    return vertices, list(_FACES_DA_CAIXA)


def caixa_orientada(centro, eixo_a, eixo_b, eixo_c):
    meios = [escalar(eixo, 0.5) for eixo in (eixo_a, eixo_b, eixo_c)]
    vertices = []
    for sinal_a, sinal_b, sinal_c in (
        (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
        (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
    ):
        vertices.append(somar_pontos(
            centro,
            escalar(meios[0], sinal_a),
            escalar(meios[1], sinal_b),
            escalar(meios[2], sinal_c),
        ))
    return vertices, list(_FACES_DA_CAIXA)


def estrela(centro, normal, raio_externo, raio_interno, espessura, pontas=6, saliencia=1.0):
    eixo = unitario(normal)
    eixo_u, eixo_v = base_local(eixo)
    contorno = []
    for indice in range(pontas * 2):
        angulo = math.pi / 2 + math.tau * indice / (pontas * 2)
        raio = raio_externo if indice % 2 == 0 else raio_interno
        contorno.append(somar_pontos(
            centro, escalar(eixo_u, raio * math.cos(angulo)), escalar(eixo_v, raio * math.sin(angulo))
        ))
    vertices = []
    for ponto in contorno:
        saliente = saliencia * espessura * 0.5 * (norma(diferenca(ponto, centro)) / raio_externo)
        vertices.append(somar_pontos(ponto, escalar(eixo, saliente)))
    for ponto in contorno:
        saliente = saliencia * espessura * 0.5 * (norma(diferenca(ponto, centro)) / raio_externo)
        vertices.append(somar_pontos(ponto, escalar(eixo, -saliente)))
    nucleo = espessura * 0.5 * (1.0 - saliencia) if saliencia < 1.0 else espessura * 0.12
    vertices.append(somar_pontos(centro, escalar(eixo, nucleo)))
    centro_frente = len(vertices) - 1
    vertices.append(somar_pontos(centro, escalar(eixo, -nucleo)))
    centro_tras = len(vertices) - 1
    total = pontas * 2
    faces = []
    for indice in range(total):
        seguinte = (indice + 1) % total
        faces += [
            (centro_frente, indice, seguinte),
            (centro_tras, total + seguinte, total + indice),
            (indice, total + indice, total + seguinte),
            (indice, total + seguinte, seguinte),
        ]
    return vertices, faces


def retangulo_2d(origem, direcao, comprimento, meia_largura):
    perpendicular = (-direcao[1], direcao[0])
    ponta = (
        origem[0] + direcao[0] * comprimento,
        origem[1] + direcao[1] * comprimento,
    )
    return [
        origem,
        ponta,
        (ponta[0] + perpendicular[0] * meia_largura, ponta[1] + perpendicular[1] * meia_largura),
        (origem[0] + perpendicular[0] * meia_largura, origem[1] + perpendicular[1] * meia_largura),
    ]


def agulha_2d(comprimento, meia_largura, curva=2.6, amostras=12):
    """Contorno de uma agulha de duas pontas afiadas, ao longo do eixo x, centrada na origem.

    A meia largura segue sin(pi*t)**curva: com curva=2 os lados saem retos (losango), e acima de
    2 entram para dentro, que e o corte em agulha.
    """
    if comprimento <= 0.0 or meia_largura <= 0.0:
        raise ValueError("a agulha precisa de comprimento e meia largura positivos")
    if curva < 1.0:
        raise ValueError("a curva da agulha tem de ser pelo menos 1")
    superior = []
    inferior = []
    for passo in range(amostras + 1):
        t = passo / amostras
        x = (t - 0.5) * comprimento
        meia = meia_largura * math.sin(math.pi * t) ** curva
        superior.append((x, meia))
        inferior.append((x, -meia))
    return superior + inferior[-2:0:-1]


def contorno_da_uniao(pecas):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    uniao = unary_union([Polygon(peca).buffer(0) for peca in pecas]).buffer(0)
    if uniao.geom_type == "MultiPolygon":
        uniao = max(uniao.geoms, key=lambda parte: parte.area)
    return list(uniao.exterior.coords[:-1])


