import math

from src.backend.geometry import malhas as M


def _estrela_da_ponta(medidas):
    centro = (0.0, 0.0, medidas.z_centro_estrela)
    raio = medidas.raio_estrela
    eixo_n = (0.0, 1.0, 0.0)
    eixo_u = (1.0, 0.0, 0.0)
    eixo_v = (0.0, 0.0, 1.0)
    pontas = 8
    malhas = []
    anel = []
    for indice in range(pontas):
        direcao, lado = _raio_do_plano(math.tau * indice / pontas, eixo_u, eixo_v, eixo_n)
        interno = M.somar_pontos(centro, M.escalar(direcao, raio * 0.30))
        anel.append(interno)
        meio = M.somar_pontos(centro, M.escalar(direcao, raio * 0.40))
        largura = M.escalar(lado, raio * 0.105)
        crista = M.unitario(M.produto_vetorial(direcao, lado))
        malhas.append(_lamina(
            interno, M.somar_pontos(meio, largura), M.somar_pontos(centro, M.escalar(direcao, raio)),
            M.somar_pontos(meio, M.escalar(largura, -1.0)), crista, raio * 0.080,
        ))
    for indice in range(pontas):
        direcao, lado = _raio_do_plano(
            math.tau * (indice + 0.5) / pontas, eixo_u, eixo_v, eixo_n
        )
        interno = M.somar_pontos(centro, M.escalar(direcao, raio * 0.26))
        meio = M.somar_pontos(centro, M.escalar(direcao, raio * 0.28))
        largura = M.escalar(lado, raio * 0.062)
        crista = M.unitario(M.produto_vetorial(direcao, lado))
        malhas.append(_lamina(interno, M.somar_pontos(meio, largura),
                              M.somar_pontos(centro, M.escalar(direcao, raio * 0.44)),
                              M.somar_pontos(meio, M.escalar(largura, -1.0)), crista, raio * 0.050))
    malhas.append(_nucleo_da_estrela(centro, anel, eixo_n, raio))
    return M.somar(malhas)


def _raio_do_plano(angulo, eixo_u, eixo_v, eixo_n):
    direcao = M.somar_pontos(
        M.escalar(eixo_u, math.cos(angulo)), M.escalar(eixo_v, math.sin(angulo))
    )
    return direcao, M.unitario(M.produto_vetorial(eixo_n, direcao))


def _lamina(interno, lado_a, ponta, lado_b, crista, altura):
    frente = M.somar_pontos(
        M.escalar(M.somar_pontos(interno, ponta), 0.5), M.escalar(crista, altura)
    )
    tras = M.somar_pontos(
        M.escalar(M.somar_pontos(interno, ponta), 0.5), M.escalar(crista, -altura)
    )
    vertices = [interno, lado_a, ponta, lado_b, frente, tras]
    faces = [
        (4, 0, 1), (4, 1, 2), (4, 2, 3), (4, 3, 0),
        (5, 1, 0), (5, 2, 1), (5, 3, 2), (5, 0, 3),
    ]
    return vertices, faces


def _nucleo_da_estrela(centro, anel, eixo_n, raio):
    vertices = list(anel)
    vertices.append(M.somar_pontos(centro, M.escalar(eixo_n, raio * 0.22)))
    frente = len(vertices) - 1
    vertices.append(M.somar_pontos(centro, M.escalar(eixo_n, -raio * 0.22)))
    tras = len(vertices) - 1
    total = len(anel)
    faces = []
    for indice in range(total):
        seguinte = (indice + 1) % total
        faces += [(frente, indice, seguinte), (tras, seguinte, indice)]
    return vertices, faces
