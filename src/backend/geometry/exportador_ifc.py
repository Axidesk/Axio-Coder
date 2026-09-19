from src.backend.geometry.montagem import Montador
from src.backend.geometry.pecas import Malha


NIVEL_PADRAO = "Nivel unico"


def escrever_ifc(caminho, modelo):
    montador = Montador(modelo.nome, autor=modelo.autor, descricao=modelo.descricao)
    niveis = _niveis(montador, modelo)
    materiais = {
        material.nome: montador.material(
            material.nome, material.cor, material.transparencia, material.brilho
        )
        for material in modelo.materiais
    }
    produtos = {}
    for peca in modelo.pecas:
        produtos.setdefault(peca.nome, _escrever_peca(montador, peca, niveis, materiais))
    for grupo in modelo.grupos:
        montador.grupo(
            grupo.nome, grupo.descricao,
            [produtos[nome] for nome in grupo.pecas if nome in produtos],
        )
    for documento in modelo.documentos:
        montador.documento(
            documento.identificacao, documento.nome, documento.descricao,
            [produtos[nome] for nome in documento.pecas if nome in produtos],
        )
    montador.escrever(caminho)
    return caminho


def _niveis(montador, modelo):
    niveis = {
        nivel.nome: montador.nivel(nivel.nome, nivel.elevacao, nivel.descricao)
        for nivel in modelo.niveis
    }
    if not niveis:
        niveis[""] = montador.nivel(NIVEL_PADRAO, 0.0)
    return niveis


def _escrever_peca(montador, peca, niveis, materiais):
    nivel = niveis.get(peca.nivel)
    if nivel is None:
        nivel = next(iter(niveis.values()))
    material = materiais.get(peca.material)
    if isinstance(peca.operacao, Malha):
        return montador.peca(
            peca.tipo_ifc, peca.nome, peca.operacao.corpos,
            nivel, material, peca.descricao, peca.tipo, dict(peca.propriedades) or None,
        )
    return montador.solido(peca, nivel, material)
