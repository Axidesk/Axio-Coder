import math

from src.backend.geometry import malhas as M
from src.backend.geometry.modelo import Documento, Grupo, Material, Modelo, Nivel
from gerados.arvore.chapas import _placas_do_revestimento
from gerados.arvore.conjuntos import (
    _aneis,
    _coroa_e_mastro,
    _estrutura,
    _mecanismo,
    _tambor,
)
from gerados.arvore.desenho import Medidas
from gerados.arvore.estrela import _estrela_da_ponta
from src.backend.geometry.pecas import Malha, Peca

NOME = "Arvore Giratoria de 30 m"
DESCRICAO = "Arvore de Natal monumental giratoria de 30 m - IFC4 para Archicad"
MEMORIAL = (
    "AV-30M-MEM-001",
    "Memorial Descritivo Preliminar",
    "Dimensoes e componentes derivados do memorial da Arvore Giratoria de 30 m",
)

CORES = {
    "Aco corten claro": ((1.00, 0.76, 0.32), 0.0, 0.48),
    "Aco corten dourado": ((0.95, 0.68, 0.26), 0.0, 0.44),
    "Aco corten medio": ((0.89, 0.60, 0.21), 0.0, 0.41),
    "Aco corten escuro": ((0.82, 0.52, 0.17), 0.0, 0.37),
    "Aco corten fundo": ((0.44, 0.25, 0.07), 0.0, 0.28),
    "Painel de aco claro": ((1.00, 0.88, 0.55), 0.0, 0.22),
    "Painel de aco dourado": ((0.99, 0.82, 0.46), 0.0, 0.20),
    "Painel de aco medio": ((0.96, 0.75, 0.38), 0.0, 0.18),
    "Cristal da estrela": ((1.00, 0.96, 0.82), 0.12, 0.62),
    "LED branco quente": ((1.00, 0.86, 0.56), 0.0, 0.60),
    "LED branco frio": ((0.90, 0.93, 1.00), 0.0, 0.60),
    "Aco estrutural": ((0.50, 0.36, 0.16), 0.0, 0.30),
    "Aco do mecanismo": ((0.42, 0.45, 0.50), 0.0, 0.45),
    "Concreto armado": ((0.70, 0.68, 0.63), 0.0, 0.05),
    "Vegetacao": ((0.11, 0.18, 0.08), 0.0, 0.05),
}

VARIANTES = {
    "base": Medidas(),
    "estrutural": Medidas(nivel="estrutural"),
}


def construir(medidas=None):
    medidas = medidas or Medidas()
    estrutural = medidas.nivel == "estrutural"
    niveis = [Nivel(f"Nivel {indice:02d}", z) for indice, z in enumerate(medidas.niveis_em_z())]

    def em(z):
        return niveis[min(int(z // 3.0), len(niveis) - 1)].nome

    def peca(nome, tipo_ifc, corpos, z, material, descricao="", tipo=""):
        return Peca(
            nome=nome, tipo_ifc=tipo_ifc, operacao=Malha(_corpo(corpos)),
            material=material, nivel=em(z), descricao=descricao, tipo=tipo,
        )

    mecanismo = _mecanismo(medidas)
    base = [
        peca("Fundacao circular e radier", "IfcFooting", mecanismo["fundacao"], -1.0,
             "Concreto armado", "Bloco e radier de fundacao", "Fundacao"),
        peca("Rolamento de giro", "IfcMechanicalFastener", mecanismo["rolamento"], 0.7,
             "Aco do mecanismo", "Rolamento axial de esferas", "Rolamento"),
        peca("Coroa dentada de 72 dentes", "IfcMechanicalFastener", mecanismo["coroa"], 0.6,
             "Aco do mecanismo", "Coroa de accionamento do giro", "Coroa"),
        peca("Pinhao e motorredutor", "IfcMechanicalFastener",
             [mecanismo["pinhao"], mecanismo["motor"]], 0.9,
             "Aco do mecanismo", "Conjunto motriz do giro", "Motriz"),
        peca("Anel coletor", "IfcMechanicalFastener", mecanismo["anel_coletor"], 0.8,
             "Aco do mecanismo", "Slip ring de alimentacao eletrica", "Coletor"),
        peca("Plataforma giratoria", "IfcSlab",
             [mecanismo["plataforma"], mecanismo["chapa"]], 1.2,
             "Aco estrutural", "Plataforma que recebe a arvore", "Plataforma"),
    ]

    paineis, juncoes, fundo = _tambor(medidas)
    tambor = [
        peca(f"Revestimento do tambor - {len(paineis)} paineis, metade com roseta", "IfcPlate",
             paineis, 2.0, "Aco corten dourado",
             "Paineis alternados: roseta de 4 agulhas recortada na chapa em coluna par",
             "Painel do tambor"),
        peca("Forro interior do tambor", "IfcPlate", [fundo], 2.0,
             "Aco corten fundo", "Chapa de fundo opaca que veda o tambor", "Forro"),
        peca("Perfis iluminados das juntas do tambor", "IfcMember", juncoes, 2.5,
             "LED branco quente", "Perfis verticais iluminados que acompanham o cone",
             "Iluminacao"),
        peca("Cornija do tambor", "IfcPlate",
             [M.anel(8.90, 9.46, medidas.z_topo_tambor - 0.12, medidas.z_topo_tambor + 0.16,
                     medidas.colunas * 2)], 4.0,
             "Aco corten claro", "Cornija de remate do tambor", "Cornija"),
        peca("Saia do tambor", "IfcPlate",
             [M.anel(10.35, 10.92, medidas.z_base_tambor - 0.14, medidas.z_base_tambor + 0.34,
                     medidas.colunas * 2)], 1.0,
             "Aco corten fundo", "Saia de remate inferior do tambor", "Saia"),
        peca("Patamar do canteiro", "IfcSlab",
             [M.anel(10.55, 11.10, -0.16, 0.04, 64)], 0.5,
             "Concreto armado", "Patamar onde assenta o canteiro", "Patamar"),
        peca("Canteiro verde", "IfcBuildingElementProxy",
             [M.anel(10.85, 11.70, 0.04, 0.30, 64)], 0.5,
             "Vegetacao", "Macico vegetal em anel no pe do tambor", "Canteiro"),
        peca("Balizas do canteiro", "IfcDiscreteAccessory",
             [M.tubo((10.95 * math.cos(math.tau * i / 16), 10.95 * math.sin(math.tau * i / 16),
                      0.06),
                     (10.95 * math.cos(math.tau * i / 16), 10.95 * math.sin(math.tau * i / 16),
                      0.80), 0.075, 10) for i in range(16)], 0.5,
             "LED branco quente", "Balizas de iluminacao do canteiro", "Baliza"),
    ]

    costelas = _estrutura(medidas)
    estrutura = [
        peca(f"Costelas verticais - {len(costelas)} unidades", "IfcMember",
             M.somar(costelas), medidas.z_base_cone,
             "Aco estrutural", "Costelas principais em aco, no interior", "Costela"),
        peca("Aneis estruturais", "IfcMember", _aneis(medidas), medidas.z_base_cone,
             "Aco estrutural", "Aneis horizontais de travamento", "Anel"),
    ]

    revestimento = []
    if not estrutural:
        por_tom, _ = _placas_do_revestimento(medidas)
        revestimento = [
            peca(f"{tom} - {len(malhas)} chapas", "IfcPlate", malhas, 12.0,
                 tom, f"Chapas do revestimento em {tom.lower()}", tom)
            for tom, malhas in por_tom.items()
        ]

    topo = [
        peca("Coroa de fecho e mastro", "IfcMember", _coroa_e_mastro(medidas),
             medidas.z_topo_cone, "Aco corten claro",
             "Remate do cone e mastro de suporte da estrela", "Coroa"),
    ]
    if not estrutural:
        topo.append(
            peca("Estrela tridimensional do topo", "IfcBuildingElementProxy",
                 _estrela_da_ponta(medidas), medidas.z_centro_estrela,
                 "Cristal da estrela", "Estrela de 8 pontas em cristal facetado", "Estrela")
        )

    tudo = base + tambor + estrutura + revestimento + topo
    grupos = [
        Grupo("Base, giro e tambor", "Fundacao, mecanismo, tambor e canteiro",
              _nomes(base + tambor)),
        Grupo("Estrutura principal", "Costelas e aneis no interior da casca",
              _nomes(estrutura)),
    ]
    if revestimento:
        grupos.append(Grupo("Pele cenografica", "Chapas dobradas e paineis vazados",
                            _nomes(revestimento)))
    grupos.append(Grupo("Topo e estrela", "Coroa, mastro e estrela", _nomes(topo)))

    return Modelo(
        nome=NOME,
        pecas=tuple(tudo),
        descricao=DESCRICAO,
        niveis=tuple(niveis),
        materiais=tuple(
            Material(nome, cor, transparencia, brilho)
            for nome, (cor, transparencia, brilho) in CORES.items()
        ),
        grupos=tuple(grupos),
        documentos=(Documento(*MEMORIAL, _nomes(tudo)),),
    )


def _corpo(corpos):
    return (corpos,) if isinstance(corpos, tuple) else tuple(corpos)


def _nomes(pecas):
    return tuple(peca.nome for peca in pecas)
