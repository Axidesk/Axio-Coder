import math

import numpy as np

try:
    from numba import njit

    _COMPILADO = True
except ImportError:
    _COMPILADO = False

    def njit(**configuracao):
        def envolver(funcao):
            return funcao

        return envolver


TOLERANCIA_BORDA = 1e-6


@njit(cache=True)
def _rasterizar_compilado(pixels, profundidades, cores, buffer_z, buffer_cor, dono):
    pintados = 0
    for t in range(pixels.shape[0]):
        x0 = pixels[t, 0, 0]
        y0 = pixels[t, 0, 1]
        x1 = pixels[t, 1, 0]
        y1 = pixels[t, 1, 1]
        x2 = pixels[t, 2, 0]
        y2 = pixels[t, 2, 1]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-12:
            continue
        esquerda = int(math.floor(min(x0, x1, x2)))
        direita = int(math.ceil(max(x0, x1, x2)))
        topo = int(math.floor(min(y0, y1, y2)))
        base = int(math.ceil(max(y0, y1, y2)))
        if esquerda < 0:
            esquerda = 0
        if topo < 0:
            topo = 0
        if direita > buffer_z.shape[1] - 1:
            direita = buffer_z.shape[1] - 1
        if base > buffer_z.shape[0] - 1:
            base = buffer_z.shape[0] - 1
        if esquerda > direita or topo > base:
            continue

        z0 = profundidades[t, 0]
        z1 = profundidades[t, 1]
        z2 = profundidades[t, 2]
        vermelho = cores[t, 0]
        verde = cores[t, 1]
        azul = cores[t, 2]
        inverso = 1.0 / area
        ganhou = False
        for py in range(topo, base + 1):
            fy = py + 0.5
            for px in range(esquerda, direita + 1):
                fx = px + 0.5
                peso0 = ((x1 - fx) * (y2 - fy) - (x2 - fx) * (y1 - fy)) * inverso
                if peso0 < -TOLERANCIA_BORDA:
                    continue
                peso1 = ((x2 - fx) * (y0 - fy) - (x0 - fx) * (y2 - fy)) * inverso
                if peso1 < -TOLERANCIA_BORDA:
                    continue
                peso2 = 1.0 - peso0 - peso1
                if peso2 < -TOLERANCIA_BORDA:
                    continue
                profundidade = peso0 * z0 + peso1 * z1 + peso2 * z2
                if profundidade < buffer_z[py, px]:
                    buffer_z[py, px] = profundidade
                    buffer_cor[py, px, 0] = vermelho
                    buffer_cor[py, px, 1] = verde
                    buffer_cor[py, px, 2] = azul
                    dono[py, px] = t
                    ganhou = True
        if ganhou:
            pintados += 1
    return pintados


def _rasterizar_vetorizado(pixels, profundidades, cores, buffer_z, buffer_cor, dono):
    pintados = 0
    for t in range(pixels.shape[0]):
        (x0, y0), (x1, y1), (x2, y2) = pixels[t]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-12:
            continue
        esquerda = max(0, int(math.floor(min(x0, x1, x2))))
        direita = min(buffer_z.shape[1] - 1, int(math.ceil(max(x0, x1, x2))))
        topo = max(0, int(math.floor(min(y0, y1, y2))))
        base = min(buffer_z.shape[0] - 1, int(math.ceil(max(y0, y1, y2))))
        if esquerda > direita or topo > base:
            continue
        grelha_x, grelha_y = np.meshgrid(
            np.arange(esquerda, direita + 1, dtype=np.float64) + 0.5,
            np.arange(topo, base + 1, dtype=np.float64) + 0.5,
        )
        peso0 = ((x1 - grelha_x) * (y2 - grelha_y) - (x2 - grelha_x) * (y1 - grelha_y)) / area
        peso1 = ((x2 - grelha_x) * (y0 - grelha_y) - (x0 - grelha_x) * (y2 - grelha_y)) / area
        peso2 = 1.0 - peso0 - peso1
        dentro = (
            (peso0 >= -TOLERANCIA_BORDA)
            & (peso1 >= -TOLERANCIA_BORDA)
            & (peso2 >= -TOLERANCIA_BORDA)
        )
        if not dentro.any():
            continue
        profundidade = (
            peso0 * profundidades[t, 0] + peso1 * profundidades[t, 1] + peso2 * profundidades[t, 2]
        )
        janela_z = buffer_z[topo:base + 1, esquerda:direita + 1]
        ganha = dentro & (profundidade < janela_z)
        if not ganha.any():
            continue
        janela_z[ganha] = profundidade[ganha]
        buffer_cor[topo:base + 1, esquerda:direita + 1][ganha] = cores[t]
        dono[topo:base + 1, esquerda:direita + 1][ganha] = t
        pintados += 1
    return pintados


class Rasterizador:
    def __init__(self, largura, altura, fundo):
        self.largura = int(largura)
        self.altura = int(altura)
        self.profundidade = np.full((self.altura, self.largura), math.inf, dtype=np.float64)
        self.cor = np.zeros((self.altura, self.largura, 3), dtype=np.uint8)
        self.cor[:, :] = fundo
        self.dono = np.full((self.altura, self.largura), -1, dtype=np.int32)
        self.pintados = 0

    def rasterizar(self, pixels, profundidades, cores):
        pixels = np.ascontiguousarray(pixels, dtype=np.float64)
        profundidades = np.ascontiguousarray(profundidades, dtype=np.float64)
        cores = np.ascontiguousarray(cores, dtype=np.uint8)
        if not len(pixels):
            return 0
        motor = _rasterizar_compilado if _COMPILADO else _rasterizar_vetorizado
        self.pintados = motor(pixels, profundidades, cores, self.profundidade, self.cor, self.dono)
        return self.pintados

    def pixels_por_triangulo(self, quantidade):
        if quantidade <= 0:
            return np.zeros(0, dtype=np.int64)
        usados = self.dono[self.dono >= 0].ravel()
        return np.bincount(usados, minlength=quantidade)[:quantidade]

    def cobertura(self):
        return int(np.count_nonzero(self.dono >= 0))
