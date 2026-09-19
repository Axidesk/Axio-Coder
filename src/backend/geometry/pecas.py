import math
from dataclasses import dataclass

from src.backend.geometry.malhas import volume_com_sinal


@dataclass(frozen=True)
class Perfil:
    pontos: tuple

    def area(self):
        return _area_poligono(self.pontos)


@dataclass(frozen=True)
class Extrusao:
    profundidade: float
    direcao: tuple = (0.0, 0.0, 1.0)


@dataclass(frozen=True)
class Revolucao:
    angulo: float = math.tau


@dataclass(frozen=True)
class Malha:
    corpos: tuple

    def volume(self):
        return sum(abs(volume_com_sinal(vertices, faces)) for vertices, faces in self.corpos)


@dataclass(frozen=True)
class Peca:
    nome: str
    tipo_ifc: str
    operacao: object
    perfil: Perfil = None
    origem: tuple = (0.0, 0.0, 0.0)
    eixo_x: tuple = (1.0, 0.0, 0.0)
    eixo_z: tuple = (0.0, 0.0, 1.0)
    material: str = ""
    nivel: str = ""
    descricao: str = ""
    tipo: str = ""
    propriedades: tuple = ()


def _area_poligono(pontos):
    soma = 0.0
    for (x1, y1), (x2, y2) in zip(pontos, pontos[1:] + pontos[:1]):
        soma += x1 * y2 - x2 * y1
    return abs(soma) / 2.0


def _centroide_y(pontos):
    dobro_area = 0.0
    acumulado = 0.0
    for (x1, y1), (x2, y2) in zip(pontos, pontos[1:] + pontos[:1]):
        cruz = x1 * y2 - x2 * y1
        dobro_area += cruz
        acumulado += (y1 + y2) * cruz
    if abs(dobro_area) < 1e-15:
        return 0.0
    return acumulado / (3.0 * dobro_area)


def volume_previsto(peca):
    if isinstance(peca.operacao, Malha):
        return peca.operacao.volume()
    if isinstance(peca.operacao, Extrusao):
        return peca.perfil.area() * peca.operacao.profundidade
    if isinstance(peca.operacao, Revolucao):
        voltas = peca.operacao.angulo / math.tau
        return math.tau * abs(_centroide_y(peca.perfil.pontos)) * peca.perfil.area() * voltas
    raise TypeError(f"operacao desconhecida: {type(peca.operacao).__name__}")
