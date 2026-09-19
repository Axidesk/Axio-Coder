import math
from dataclasses import dataclass
from typing import Callable

from src.backend.geometry.malhas import polar

RAIO_MINIMO = 0.001


def raio_em_z(raio_base, raio_topo, z_base, z_topo, z):
    """Raio de um cone na altura z, limitado as duas extremidades."""
    altura = z_topo - z_base
    if not altura:
        raise ValueError("o cone precisa de altura")
    fracao = min(max((z - z_base) / altura, 0.0), 1.0)
    return raio_base + (raio_topo - raio_base) * fracao


def largura_do_sector(raio, colunas, fracao_painel=1.0):
    """Largura do arco do painel de um par (painel e costela) a um dado raio."""
    return sector(colunas) * fracao_painel * raio


def angulo_do_sector(colunas, s, fracao_painel=1.0):
    """Angulo da posicao continua s, com as colunas a alternar painel e costela.

    As colunas contam-se uma a uma (s de 0 a colunas) e cada par ocupa um sector; dentro do
    par, fracao_painel e a fatia do painel. O conjunto tila o circulo sem sobreposicao nem folga.
    """
    if not 0.0 < fracao_painel < 1.0:
        raise ValueError("fracao_painel tem de estar entre 0 e 1")
    abertura = sector(colunas)
    coluna = int(math.floor(s))
    fracao = s - coluna
    base = abertura * (coluna // 2)
    if coluna % 2 == 0:
        return base + abertura * fracao * fracao_painel
    return base + abertura * (fracao_painel + fracao * (1.0 - fracao_painel))


def sector(colunas):
    """Abertura angular de um par - um painel e a costela que se lhe segue."""
    if colunas < 2 or colunas % 2:
        raise ValueError("a alternancia de painel e costela precisa de um numero par de colunas")
    return 2.0 * math.tau / colunas


def deslocamento_do_perfil(perfil, amplitude, s, raio, raio_base):
    """Deslocamento radial A(z)*p(s) com A proporcional ao raio - a unica lei que mantem a chapa plana."""
    return amplitude * (raio / raio_base) * perfil(s)


def alturas_dos_aneis(raio_base, raio_topo, z_base, z_topo, aneis):
    """Alturas das fronteiras dos aneis, em progressao geometrica pelo raio."""
    if aneis < 1:
        raise ValueError("a casca precisa de pelo menos um anel")
    if raio_base <= 0.0 or raio_topo <= 0.0:
        raise ValueError("os raios da casca tem de ser positivos")
    if not (z_topo - z_base):
        raise ValueError("o cone precisa de altura")
    if abs(raio_topo - raio_base) < 1e-12:
        return [z_base + (z_topo - z_base) * indice / aneis for indice in range(aneis + 1)]
    razao = (raio_topo / raio_base) ** (1.0 / aneis)
    declive = (raio_base - raio_topo) / (z_topo - z_base)
    alturas = []
    raio = raio_base
    for _ in range(aneis + 1):
        alturas.append(z_base + (raio_base - raio) / declive)
        raio *= razao
    alturas[-1] = z_topo
    return alturas


@dataclass(frozen=True)
class Casca:
    """Cone dividido em sectores alternados e aneis, com um perfil de relevo opcional."""

    raio_base: float
    raio_topo: float
    z_base: float
    z_topo: float
    colunas: int
    aneis: int = 30
    fracao_painel: float = 1.0
    perfil: Callable | None = None
    amplitude: float = 0.0

    def raio_em(self, z):
        return raio_em_z(self.raio_base, self.raio_topo, self.z_base, self.z_topo, z)

    def alturas(self):
        return alturas_dos_aneis(
            self.raio_base, self.raio_topo, self.z_base, self.z_topo, self.aneis
        )

    def largura_do_sector(self, z):
        return largura_do_sector(self.raio_em(z), self.colunas, self.fracao_painel)

    def ponto(self, s, z):
        raio = self.raio_em(z)
        if self.perfil is not None and self.amplitude:
            raio += deslocamento_do_perfil(self.perfil, self.amplitude, s, raio, self.raio_base)
        return polar(
            max(raio, RAIO_MINIMO), angulo_do_sector(self.colunas, s, self.fracao_painel), z
        )

    def cantos(self, s_esquerdo, s_direito, z_baixo, z_alto):
        return [
            self.ponto(s_esquerdo, z_alto),
            self.ponto(s_direito, z_alto),
            self.ponto(s_direito, z_baixo),
            self.ponto(s_esquerdo, z_baixo),
        ]
