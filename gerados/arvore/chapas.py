import math
from dataclasses import dataclass

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from src.backend.geometry import malhas as M
from gerados.arvore.desenho import _quadro_da_placa
from gerados.arvore.flocos import (
    CATALOGO_FLOCOS,
    TONS_DO_ACO,
    TONS_DO_PAINEL,
    _contorno_do_floco_2d,
    _semente,
    _tom_da_mancha,
)

LADO_DO_ENTALHE = 0.80
DESVIO_DO_ENTALHE = 0.44
RAIO_DO_ENTALHE = (0.20, 0.42)
FRACAO_MINIMA_DA_CHAPA = 0.05
LARGURA_MINIMA_DA_CHAPA = 0.06
ALCANCE_DO_ENTALHE = 2


@dataclass(frozen=True)
class Desenho:
    """O desenho recortado na casca, em coordenadas de celula (uma chapa por quadrado unitario).

    Um floco de duas celulas atravessa quatro chapas e cada uma recebe o pedaco que lhe cabe -
    pecas de um piso hidraulico, que so fazem sentido juntas. A malha fecha em u (o desenho da a
    volta a casca) e nao em v.
    """

    flocos: dict
    colunas: int
    passo_u: float
    passo_v: float
    nomes: tuple

    def da_celula(self, celula, linha):
        coluna = int(celula // self.passo_u)
        fila = int(linha // self.passo_v)
        return [
            self.flocos[(coluna + desvio_coluna) % self.colunas, fila + desvio_fila]
            for desvio_coluna in range(-ALCANCE_DO_ENTALHE, ALCANCE_DO_ENTALHE + 1)
            for desvio_fila in range(-ALCANCE_DO_ENTALHE, ALCANCE_DO_ENTALHE + 1)
            if ((coluna + desvio_coluna) % self.colunas, fila + desvio_fila) in self.flocos
        ]


def _entalhes_da_casca(medidas):
    largura = medidas.colunas * 2
    colunas = max(1, int(round(largura / LADO_DO_ENTALHE)))
    filas = max(1, int(round(medidas.linhas / LADO_DO_ENTALHE)))
    passo_u = largura / colunas
    passo_v = medidas.linhas / filas
    flocos = {}
    nomes = []
    for fila in range(filas):
        for coluna in range(colunas):
            semente = _semente(coluna, fila, 5)
            nome, modelo, _ = CATALOGO_FLOCOS[semente % len(CATALOGO_FLOCOS)]
            raio = RAIO_DO_ENTALHE[0] + (RAIO_DO_ENTALHE[1] - RAIO_DO_ENTALHE[0]) * (
                ((semente // 977) % 2039) / 2038.0
            )
            contorno = M.rodar_2d(
                _contorno_do_floco_2d(raio, nome, modelo),
                math.tau * (((semente // 3571) % 1489) / 1489.0),
            )
            aqui = (
                (coluna + 0.5 + DESVIO_DO_ENTALHE * (((semente // 131) % 2003) / 2002.0 - 0.5))
                * passo_u,
                (fila + 0.5 + DESVIO_DO_ENTALHE * (((semente // 7919) % 2011) / 2010.0 - 0.5))
                * passo_v,
            )
            flocos[(coluna, fila)] = Polygon(
                [(x + aqui[0], y + aqui[1]) for x, y in contorno]
            )
            nomes.append(nome)
    return Desenho(flocos, colunas, passo_u, passo_v, tuple(nomes))


def _poligonos(geometria):
    if geometria.is_empty:
        return []
    if geometria.geom_type == "Polygon":
        return [geometria]
    return [parte for parte in geometria.geoms if parte.geom_type == "Polygon"]


def _contorno_3d(quadro, contorno_2d, celula, linha):
    """Leva o contorno das coordenadas de celula para o plano da chapa, em metros.

    A passagem e directa - uma celula e um quadrado do plano da chapa - e por isso o que esta
    dentro fica dentro: uma chapa de aco e plana, quem acompanha a casca sao os seus cantos.
    """
    return [
        quadro.para_espaco((
            ((u - celula) * 2.0 - 1.0) * quadro.meia_largura,
            ((v - linha) * 2.0 - 1.0) * quadro.meia_altura,
        ))
        for u, v in contorno_2d
    ]


def _chapas_da_celula(quadro, desenho, celula, linha, medidas):
    """As chapas que sobram de uma celula depois de lhe tirar o pedaco do desenho que lhe cabe.

    A folga entra no quadrado antes do corte: as chapas vizinhas sobrepoem-se um pouco e a junta
    fecha sem deixar ver a estrutura por tras. Nao se repoe a apara: nem o pedaco abaixo de
    FRACAO_MINIMA_DA_CHAPA da chapa, nem o que fica com menos de LARGURA_MINIMA_DA_CHAPA de lado -
    nenhum deles e uma chapa.
    """
    folga = medidas.folga_da_placa / (min(quadro.meia_largura, quadro.meia_altura) * 2.0)
    quadrado = box(float(celula), float(linha), celula + 1.0, linha + 1.0).buffer(folga)
    cheia = quadrado.area
    dentro = [floco for floco in desenho.da_celula(celula, linha) if floco.intersects(quadrado)]
    if dentro:
        quadrado = quadrado.difference(unary_union(dentro))
    chapas = []
    for parte in _poligonos(quadrado):
        largura = (parte.bounds[2] - parte.bounds[0]) * quadro.meia_largura * 2.0
        altura = (parte.bounds[3] - parte.bounds[1]) * quadro.meia_altura * 2.0
        if (parte.area < cheia * FRACAO_MINIMA_DA_CHAPA
                or min(largura, altura) < LARGURA_MINIMA_DA_CHAPA):
            continue
        externo = _contorno_3d(quadro, parte.exterior.coords[:-1], celula, linha)
        buracos = [
            _contorno_3d(quadro, anel.coords[:-1], celula, linha) for anel in parte.interiors
        ]
        chapas.append(
            M.placa_vazada(
                M.orientar_contorno(externo, quadro.normal), buracos, medidas.espessura_placa
            )
        )
    return chapas


def _placas_do_revestimento(medidas):
    """Recorta a casca chapa a chapa e devolve as malhas agrupadas por tom de aco."""
    casca = medidas.casca
    alturas = casca.alturas()
    desenho = _entalhes_da_casca(medidas)
    por_tom = {}
    vazadas = []
    for coluna in range(medidas.colunas):
        tons = TONS_DO_PAINEL if coluna % 2 == 0 else TONS_DO_ACO
        for linha in range(medidas.linhas):
            z0, z1 = alturas[linha], alturas[linha + 1]
            tom = _tom_da_mancha(tons, coluna, linha)
            for sub in range(2):
                celula = coluna * 2 + sub
                quadro = _quadro_da_placa(
                    casca.cantos(celula * 0.5, (celula + 1) * 0.5, z0, z1)
                )
                for malha in _chapas_da_celula(quadro, desenho, celula, linha, medidas):
                    por_tom.setdefault(tom, []).append(malha)
                    vazadas.append(malha)
    abertas = [indice for indice, malha in enumerate(vazadas) if not M.malha_fechada(*malha)]
    if abertas:
        raise ValueError(f"chapas vazadas com a malha aberta: {abertas[:8]}")
    return por_tom, desenho.nomes
