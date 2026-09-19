import math

from src.backend.geometry import malhas as M
from gerados.arvore.desenho import _modelo

CATALOGO_FLOCOS = (
    ("Estrela de 6 raios finos", _modelo(niveis=0, largura=0.09), 1),
    ("Floco de 6 pontas com ramo curto", _modelo(niveis=1, largura=0.14, ramo_base=0.52,
                                                 ramo_comprimento=0.26, ramo_largura=0.50), 1),
    ("Floco de 6 pontas com dois niveis de ramos", _modelo(niveis=2, largura=0.15), 2),
    ("Floco denso de 6 pontas", _modelo(niveis=3, largura=0.12, ramo_base=0.28,
                                        ramo_passo=0.20, ramo_comprimento=0.24,
                                        abertura=1.15, ramo_largura=0.45), 3),
    ("Floco de 6 pontas com nucleo", _modelo(niveis=1, largura=0.16, ramo_base=0.45,
                                             ramo_comprimento=0.30, nucleo=0.20), 2),
    ("Estrela de 8 raios finos", _modelo(pontas=8, niveis=0, largura=0.09), 1),
    ("Floco de 8 pontas com ramos", _modelo(pontas=8, niveis=2, largura=0.13,
                                            ramo_base=0.40, abertura=0.95), 2),
    ("Roda de 12 raios finos", _modelo(pontas=12, niveis=0, largura=0.07), 1),
    ("Floco de 12 pontas com ramos curtos", _modelo(pontas=12, niveis=1, largura=0.08,
                                                    ramo_base=0.55, ramo_comprimento=0.22,
                                                    abertura=0.90, ramo_largura=0.45), 2),
    ("Floco de 6 pontas com 6 raios curtos", _modelo(niveis=0, largura=0.14, extras=6,
                                                     comprimento_extra=0.52), 1),
    ("Floco de 8 pontas com 8 raios curtos", _modelo(pontas=8, niveis=1, largura=0.11,
                                                     extras=8, comprimento_extra=0.48,
                                                     ramo_base=0.50, ramo_comprimento=0.24), 2),
    ("Floco de 6 pontas com pontas em losango", _modelo(niveis=2, largura=0.20,
                                                        ramo_base=0.30, ramo_passo=0.30,
                                                        ramo_comprimento=0.34, abertura=1.20), 3),
    ("Floco de 4 pontas em cruz", _modelo(pontas=4, niveis=2, largura=0.16, ramo_base=0.32,
                                          ramo_passo=0.28, ramo_comprimento=0.30, abertura=1.10), 2),
    ("Floco de 16 raios finos", _modelo(pontas=16, niveis=0, largura=0.06), 2),
    ("Floco de 6 pontas com tres niveis densos", _modelo(niveis=3, largura=0.11, ramo_base=0.34,
                                                         ramo_passo=0.22, ramo_comprimento=0.28,
                                                         abertura=0.85), 3),
)

_CACHE_FLOCOS = {}


def _hastes_do_floco(raio, modelo):
    meia = raio * modelo["largura"] * 0.5
    hastes = []
    for indice in range(modelo["pontas"]):
        angulo = math.tau * indice / modelo["pontas"]
        hastes.append(((0.0, 0.0), (math.cos(angulo), math.sin(angulo)), raio, meia))
    if modelo["extras"]:
        for indice in range(modelo["extras"]):
            angulo = math.tau * (indice + 0.5) / modelo["extras"]
            hastes.append((
                (0.0, 0.0), (math.cos(angulo), math.sin(angulo)),
                raio * modelo["comprimento_extra"], meia * 0.62,
            ))
    for nivel in range(modelo["niveis"]):
        fracao = modelo["ramo_base"] + modelo["ramo_passo"] * nivel
        comprimento = raio * modelo["ramo_comprimento"] * (1.0 - 0.15 * nivel)
        for indice in range(modelo["pontas"]):
            angulo = math.tau * indice / modelo["pontas"]
            origem = (math.cos(angulo) * raio * fracao, math.sin(angulo) * raio * fracao)
            for sinal in (-1.0, 1.0):
                abertura = angulo + sinal * modelo["abertura"]
                hastes.append((
                    origem, (math.cos(abertura), math.sin(abertura)),
                    comprimento, meia * modelo["ramo_largura"],
                ))
    return hastes


def _contorno_do_floco_2d(raio, nome, modelo):
    chave = (nome, round(raio, 5))
    guardado = _CACHE_FLOCOS.get(chave)
    if guardado is not None:
        return guardado
    pecas = [
        M.retangulo_2d(origem, direcao, comprimento, meia_largura)
        for origem, direcao, comprimento, meia_largura in _hastes_do_floco(raio, modelo)
    ]
    if modelo["nucleo"]:
        nucleo = raio * modelo["nucleo"]
        pecas.append([
            (nucleo * math.cos(math.tau * i / 6), nucleo * math.sin(math.tau * i / 6))
            for i in range(6)
        ])
    contorno = M.contorno_da_uniao(pecas)
    _CACHE_FLOCOS[chave] = contorno
    return contorno


def _semente(coluna, linha, sub):
    return (coluna * 7919 + linha * 104729 + sub * 1299709 + 31) % 2147483647


TONS_DO_ACO = (
    "Aco corten claro",
    "Aco corten dourado",
    "Aco corten medio",
    "Aco corten escuro",
)

TONS_DO_PAINEL = (
    "Painel de aco claro",
    "Painel de aco dourado",
    "Painel de aco medio",
)


def _tom_da_mancha(tons, coluna, linha):
    mistura = (coluna * 73856093) ^ (linha * 19349663)
    return tons[(mistura >> 3) % len(tons)]
