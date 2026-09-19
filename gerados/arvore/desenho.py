import math
from dataclasses import dataclass

from src.backend.geometry import casca as C
from src.backend.geometry import malhas as M


@dataclass(frozen=True)
class Medidas:
    nivel: str = "completo"
    altura_total: float = 30.04
    colunas: int = 24
    fracao_painel: float = 0.72
    linhas: int = 30
    raio_base_cone: float = 8.90
    z_base_cone: float = 4.40
    raio_topo_cone: float = 0.90
    z_topo_cone: float = 25.60
    espessura_placa: float = 0.045
    folga_da_placa: float = 0.014
    inclinacao_relevo: float = 14.0
    recuo_do_esqueleto: float = 0.42
    raio_tambor_topo: float = 8.90
    raio_tambor_base: float = 10.35
    z_base_tambor: float = 0.30
    z_topo_tambor: float = 4.45
    raio_estrela: float = 1.85
    z_centro_estrela: float = 28.10

    @property
    def declive(self):
        return (self.raio_base_cone - self.raio_topo_cone) / (self.z_topo_cone - self.z_base_cone)

    @property
    def largura_do_painel_na_base(self):
        return C.largura_do_sector(self.raio_base_cone, self.colunas, self.fracao_painel)

    @property
    def meia_largura_da_chapa(self):
        return self.largura_do_painel_na_base * 0.5

    @property
    def amplitude_relevo(self):
        return self.meia_largura_da_chapa * math.tan(math.radians(self.inclinacao_relevo))

    @property
    def casca(self):
        if len(PASSOS_DO_RELEVO) != self.colunas * 2:
            raise ValueError("o desenho do relevo precisa de um passo por chapa, duas por coluna")
        return C.Casca(
            self.raio_base_cone, self.raio_topo_cone, self.z_base_cone, self.z_topo_cone,
            self.colunas, self.linhas, self.fracao_painel, Relevo(PASSOS_DO_RELEVO),
            self.amplitude_relevo,
        )

    def niveis_em_z(self):
        return [indice * 3.0 for indice in range(10)]


SIMBOLOS_DO_RELEVO = {"\\": -1.0, "/": 1.0, "-": 0.0}

DESENHO_DO_RELEVO = (
    "\\/ /\\ -- /\\ \\/ /\\ \\/ -- \\- -/ -- -- /\\ \\/ /\\ -- \\/ /\\ \\- -/ -- /\\ \\/ /\\"
)


def _passos_do_relevo(desenho):
    """Le o desenho do perfil: cada simbolo e o passo de uma chapa - entra, sai ou segue reto."""
    simbolos = [caractere for caractere in desenho if not caractere.isspace()]
    return tuple(SIMBOLOS_DO_RELEVO[caractere] for caractere in simbolos)


PASSOS_DO_RELEVO = _passos_do_relevo(DESENHO_DO_RELEVO)


@dataclass(frozen=True)
class Relevo:
    """Perfil radial com um no em cada fronteira de chapa, reto entre nos.

    Um passo por chapa, e nao por coluna: a dobra cai sempre na aresta entre duas chapas, que e
    o unico lugar onde ela aparece - a chapa tem quatro cantos e so mostra relevo se eles
    estiverem em nos diferentes.
    """

    passos: tuple

    @property
    def nos(self):
        valores = [0.0]
        for passo in self.passos:
            valores.append(valores[-1] + passo)
        media = sum(valores) / len(valores)
        return [valor - media for valor in valores]

    def __call__(self, s):
        nos = self.nos
        ultimo = len(nos) - 1
        posicao = min(max(s * 2.0, 0.0), float(ultimo))
        base = int(math.floor(posicao))
        if base >= ultimo:
            return nos[ultimo]
        return nos[base] + (nos[base + 1] - nos[base]) * (posicao - base)


@dataclass(frozen=True)
class Quadro:
    """Sistema local de uma chapa: centro, eixos em metros e meias medidas.

    Os eixos saem dos proprios cantos medidos na casca, por isso um ponto vizinho projecta-se no
    mesmo (x, y) visto de uma chapa ou da sua vizinha: e o que faz o desenho continuar de uma
    chapa para a outra.
    """

    centro: tuple
    eixo_u: tuple
    eixo_v: tuple
    normal: tuple
    meia_largura: float
    meia_altura: float

    def para_espaco(self, ponto_2d):
        return M.somar_pontos(
            self.centro, M.escalar(self.eixo_u, ponto_2d[0]), M.escalar(self.eixo_v, ponto_2d[1])
        )


def _quadro_da_placa(cantos):
    alto_esquerdo, alto_direito, baixo_direito, baixo_esquerdo = cantos
    centro = M.escalar(M.somar_pontos(*cantos), 0.25)
    eixo_u = M.unitario(M.diferenca(baixo_direito, baixo_esquerdo))
    acima = M.diferenca(alto_esquerdo, baixo_esquerdo)
    eixo_v = M.unitario(M.diferenca(acima, M.escalar(eixo_u, M.produto_escalar(acima, eixo_u))))
    normal = M.unitario(M.produto_vetorial(eixo_u, eixo_v))
    meia_largura = (
        M.norma(M.diferenca(baixo_direito, baixo_esquerdo))
        + M.norma(M.diferenca(alto_direito, alto_esquerdo))
    ) * 0.25
    meia_altura = (
        M.norma(M.diferenca(alto_esquerdo, baixo_esquerdo))
        + M.norma(M.diferenca(alto_direito, baixo_direito))
    ) * 0.25
    return Quadro(centro, eixo_u, eixo_v, normal, meia_largura, meia_altura)


def _modelo(pontas=6, niveis=1, largura=0.15, ramo_base=0.40, ramo_passo=0.26,
            ramo_comprimento=0.28, abertura=1.05, ramo_largura=0.55, extras=0,
            comprimento_extra=0.0, nucleo=0.0):
    return {
        "pontas": pontas, "niveis": niveis, "largura": largura, "ramo_base": ramo_base,
        "ramo_passo": ramo_passo, "ramo_comprimento": ramo_comprimento, "abertura": abertura,
        "ramo_largura": ramo_largura, "extras": extras, "comprimento_extra": comprimento_extra,
        "nucleo": nucleo,
    }
