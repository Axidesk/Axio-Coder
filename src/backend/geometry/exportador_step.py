import math

import cadquery as cq

from src.backend.geometry.pecas import Extrusao, Malha, Revolucao


def escrever_step(caminho, modelo):
    motivo = motivo_de_recusa(modelo)
    if motivo:
        raise ValueError(motivo)
    solidos = [_solido(peca) for peca in modelo.pecas]
    conjunto = cq.Compound.makeCompound(solidos)
    cq.exporters.export(conjunto, caminho, cq.exporters.ExportTypes.STEP)
    return caminho


def motivo_de_recusa(modelo):
    malhas = [peca.nome for peca in modelo.pecas if isinstance(peca.operacao, Malha)]
    if not malhas:
        return ""
    return (
        f"este modelo tem {len(malhas)} peca(s) em malha facetada (ex: '{malhas[0]}') e o STEP "
        "e B-rep: a conversao perderia a forma. Gere so em ifc."
    )


def medir_step(caminho):
    importado = cq.importers.importStep(caminho)
    volumes = []
    for forma in importado.vals():
        solidos = forma.Solids()
        if solidos:
            volumes.extend(solido.Volume() for solido in solidos)
        else:
            volumes.append(forma.Volume())
    return volumes


def _solido(peca):
    plano = cq.Plane(origin=peca.origem, xDir=peca.eixo_x, normal=peca.eixo_z)
    contorno = cq.Workplane(plano).polyline(list(peca.perfil.pontos)).close()
    if isinstance(peca.operacao, Extrusao):
        return contorno.extrude(peca.operacao.profundidade).val()
    if isinstance(peca.operacao, Revolucao):
        return contorno.revolve(math.degrees(peca.operacao.angulo), (0, 0, 0), (1, 0, 0)).val()
    raise TypeError(f"operacao desconhecida em {peca.nome}: {type(peca.operacao).__name__}")
