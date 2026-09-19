from . import modelo
from src.backend.geometry.catalogo import registrar

registrar(
    "arvore",
    {
        "descricao": "Arvore de Natal monumental giratoria de 30 m, em casca de aco facetada",
        "custo": "~2min20s medidos: 112s a recortar a pele chapa a chapa e 19s a gravar 49 MB",
        "parametros": modelo.Medidas,
        "variantes": modelo.VARIANTES,
        "construtor": modelo.construir,
    },
)
