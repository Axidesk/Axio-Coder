import math

from src.backend.geometry import casca as C
from src.backend.geometry import malhas as M
from gerados.arvore.desenho import _quadro_da_placa


def _ponto_do_tambor(medidas, angulo, z):
    raio = C.raio_em_z(
        medidas.raio_tambor_base, medidas.raio_tambor_topo,
        medidas.z_base_tambor, medidas.z_topo_tambor, z,
    )
    return M.polar(raio, angulo, z)


CURVA_DA_AGULHA = 2.6
LARGURA_DA_AGULHA = 0.075
FRACAO_DA_ROSETA = 0.62
TRACOS_DA_ROSETA = 4


def _roseta_do_tambor(raio):
    agulha = M.agulha_2d(raio * 2.0, raio * LARGURA_DA_AGULHA, CURVA_DA_AGULHA)
    laminas = [
        M.rodar_2d(agulha, math.tau * indice / (TRACOS_DA_ROSETA * 2))
        for indice in range(TRACOS_DA_ROSETA)
    ]
    return M.contorno_da_uniao(laminas)


def _painel_do_tambor(medidas, indice):
    inicio = C.angulo_do_sector(medidas.colunas, float(indice), medidas.fracao_painel)
    fim = C.angulo_do_sector(medidas.colunas, float(indice + 1), medidas.fracao_painel)
    z0, z1 = medidas.z_base_tambor + 0.20, medidas.z_topo_tambor - 0.25
    cantos = [
        _ponto_do_tambor(medidas, fim, z1),
        _ponto_do_tambor(medidas, inicio, z1),
        _ponto_do_tambor(medidas, inicio, z0),
        _ponto_do_tambor(medidas, fim, z0),
    ]
    quadro = _quadro_da_placa(cantos)
    externo = M.orientar_contorno(M.expandir_contorno(cantos, 0.010), quadro.normal)
    espessura = 0.06
    if indice % 2:
        interior = [
            M.somar_pontos(ponto, M.escalar(quadro.normal, -espessura)) for ponto in externo
        ]
        return M.prisma_entre(externo, interior)
    raio = min(quadro.meia_largura, quadro.meia_altura) * FRACAO_DA_ROSETA
    vao = M.contorno_no_plano(_roseta_do_tambor(raio), quadro.centro, quadro.normal)
    return M.placa_vazada(externo, [vao], espessura)


def _juncao_do_tambor(medidas, angulo):
    inicio = _ponto_do_tambor(medidas, angulo, medidas.z_base_tambor + 0.10)
    fim = _ponto_do_tambor(medidas, angulo, medidas.z_topo_tambor - 0.10)
    radial = M.unitario((inicio[0], inicio[1], 0.0))
    eixo = M.diferenca(fim, inicio)
    centro = M.somar_pontos(
        M.escalar(M.somar_pontos(inicio, fim), 0.5), M.escalar(radial, 0.035)
    )
    return M.caixa_orientada(
        centro,
        M.escalar(radial, 0.055),
        M.escalar(M.unitario(M.produto_vetorial(radial, (0.0, 0.0, 1.0))), 0.085),
        M.escalar(eixo, 0.5),
    )


def _tambor(medidas):
    paineis = [_painel_do_tambor(medidas, indice) for indice in range(medidas.colunas)]
    juncoes = [
        _juncao_do_tambor(
            medidas, C.angulo_do_sector(medidas.colunas, float(indice), medidas.fracao_painel)
        )
        for indice in range(medidas.colunas)
    ]
    interior = M.tronco(
        medidas.raio_tambor_base - 0.30, medidas.raio_tambor_topo - 0.30,
        medidas.z_base_tambor, medidas.z_topo_tambor, medidas.colunas * 2,
    )
    return paineis, juncoes, interior


def _estrutura(medidas):
    segmentos = 12
    costelas = []
    for indice in range(medidas.colunas):
        angulo = C.angulo_do_sector(medidas.colunas, float(indice), medidas.fracao_painel)
        radial = M.unitario((math.cos(angulo), math.sin(angulo), 0.0))
        tangential = M.unitario(M.produto_vetorial(radial, (0.0, 0.0, 1.0)))
        malhas = []
        for passo in range(segmentos):
            z0 = medidas.z_base_cone + (medidas.z_topo_cone - medidas.z_base_cone) * passo / segmentos
            z1 = medidas.z_base_cone + (medidas.z_topo_cone - medidas.z_base_cone) * (passo + 1) / segmentos
            p0 = M.polar(max(medidas.casca.raio_em(z0) - medidas.recuo_do_esqueleto, 0.05), angulo, z0)
            p1 = M.polar(max(medidas.casca.raio_em(z1) - medidas.recuo_do_esqueleto, 0.05), angulo, z1)
            centro = M.escalar(M.somar_pontos(p0, p1), 0.5)
            direcao = M.diferenca(p1, p0)
            malhas.append(M.caixa_orientada(
                centro,
                M.escalar(tangential, 0.16),
                M.escalar(radial, 0.16),
                M.escalar(M.unitario(direcao), M.norma(direcao) * 1.04),
            ))
        costelas.append(M.somar(malhas))
    return costelas


def _aneis(medidas):
    malhas = []
    z = medidas.z_base_cone + 2.80
    while z < medidas.z_topo_cone - 1.20:
        raio = medidas.casca.raio_em(z) - medidas.recuo_do_esqueleto + 0.04
        malhas.append(M.anel(raio - 0.09, raio, z - 0.06, z + 0.06, lados=medidas.colunas * 2))
        z += 2.80
    return malhas


def _mecanismo(medidas):
    return {
        "fundacao": M.tronco(9.80, 9.40, -1.60, -0.45, 48),
        "radier": M.tronco(9.95, 9.95, -0.45, 0.12, 48),
        "chapa": M.anel(0.6, 5.60, 0.12, 0.32, 48),
        "rolamento": M.toro(4.90, 0.24, 64, 10, 0.70),
        "coroa": M.somar([_dente_de_coroa(4.46, 0.30, math.tau * i / 72) for i in range(72)]),
        "pinhao": M.tubo((5.10, 0.0, 0.72), (5.10, 0.0, 1.22), 0.34, 16),
        "motor": M.caixa_orientada((6.55, 0.0, 0.97), (1.6, 0.0, 0.0), (0.0, 1.4, 0.0), (0.0, 0.0, 1.0)),
        "anel_coletor": M.tubo((0.0, 0.0, 0.32), (0.0, 0.0, 1.32), 0.42, 16),
        "plataforma": M.tronco(5.30, 5.30, 1.32, 1.92, 48),
    }


def _dente_de_coroa(raio, altura, angulo):
    largura = math.tau * raio / 72 * 0.52
    radial = (math.cos(angulo), math.sin(angulo), 0.0)
    tangential = (-math.sin(angulo), math.cos(angulo), 0.0)
    return M.caixa_orientada(
        M.polar(raio, angulo, 0.60),
        M.escalar(tangential, largura),
        M.escalar(radial, 0.34),
        (0.0, 0.0, altura),
    )


def _coroa_e_mastro(medidas):
    z = medidas.z_topo_cone
    raio = max(medidas.casca.raio_em(z), 0.30)
    return [
        M.anel(max(raio - 0.14, 0.10), raio + 0.10, z - 0.18, z + 0.06, 24),
        M.tubo((0.0, 0.0, z - 0.10), (0.0, 0.0, medidas.z_centro_estrela), 0.20, 12),
        M.toro(0.30, 0.13, 24, 10, medidas.z_centro_estrela - medidas.raio_estrela * 0.42),
    ]
