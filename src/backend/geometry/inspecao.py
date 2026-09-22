import math
import os

import numpy as np

CASAS = 6
CONVENCAO_POR_EXTENSAO = {".glb": "y", ".gltf": "y"}
CONVENCAO_PADRAO = "z"


def carregar(caminho):
    """Vertices (N,3) e faces (M,3) de um ficheiro de malha, em unidades do ficheiro."""
    import trimesh

    carregado = trimesh.load(caminho, force="mesh")
    vertices = np.asarray(carregado.vertices, dtype=float)
    faces = np.asarray(carregado.faces, dtype=int)
    if not len(faces):
        raise ValueError("o ficheiro nao tem faces (e um conjunto de pontos?)")
    return vertices, faces


def guardar(caminho, vertices, faces):
    """Grava a malha no formato pedido pela extensao do caminho."""
    import trimesh

    trimesh.Trimesh(vertices=np.asarray(vertices, dtype=float), faces=np.asarray(faces, dtype=int)).export(caminho)


def grupos(vertices, faces, casas=CASAS):
    """Indices das faces de cada peca LIGADA por arestas, da maior para a menor.

    A uniao e feita sobre vertices SOLDADOS por coordenada arredondada: sem soldar, um
    ficheiro que repete o vertice em cada triangulo daria uma peca por face.
    """
    ident = _identidades(vertices, casas)
    pai = list(range(int(ident.max()) + 1))

    def achar(x):
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    for face in faces:
        i = int(ident[int(face[0])])
        for outro in (int(ident[int(face[1])]), int(ident[int(face[2])])):
            raiz_i, raiz_outro = achar(i), achar(outro)
            if raiz_i != raiz_outro:
                pai[raiz_outro] = raiz_i

    por_raiz = {}
    for posicao, face in enumerate(faces):
        por_raiz.setdefault(achar(int(ident[int(face[0])])), []).append(posicao)
    return sorted(por_raiz.values(), key=len, reverse=True)


def caixa(vertices):
    """(minimo, maximo, tamanho) por eixo."""
    minimo = np.asarray(vertices).min(axis=0)
    maximo = np.asarray(vertices).max(axis=0)
    return minimo, maximo, maximo - minimo


def volume(vertices, faces):
    """Volume da malha pela soma dos tetraedros com o vertice na origem."""
    a = vertices[faces[:, 0]]
    b = vertices[faces[:, 1]]
    c = vertices[faces[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def eixos_principais(vertices):
    """Direcoes principais (PCA) com o comprimento da malha medido ao longo de cada uma."""
    centrados = np.asarray(vertices) - np.asarray(vertices).mean(axis=0)
    _, _, vetores = np.linalg.svd(centrados, full_matrices=False)
    projecoes = centrados @ vetores.T
    extensao = projecoes.max(axis=0) - projecoes.min(axis=0)
    ordem = np.argsort(-extensao)
    return [(vetores[i], float(extensao[i])) for i in ordem]


def rodar(vertices, eixo, graus):
    """Vertices rodados em torno de um dos eixos, com o centro na origem."""
    angulo = math.radians(graus)
    cosseno, seno = math.cos(angulo), math.sin(angulo)
    if eixo == "x":
        matriz = ((1.0, 0.0, 0.0), (0.0, cosseno, -seno), (0.0, seno, cosseno))
    elif eixo == "y":
        matriz = ((cosseno, 0.0, seno), (0.0, 1.0, 0.0), (-seno, 0.0, cosseno))
    elif eixo == "z":
        matriz = ((cosseno, -seno, 0.0), (seno, cosseno, 0.0), (0.0, 0.0, 1.0))
    else:
        raise ValueError(f"eixo '{eixo}' desconhecido. Use x, y ou z")
    return np.asarray(vertices, dtype=float) @ np.asarray(matriz, dtype=float).T


def de_y_para_z(vertices):
    """Leva a convencao Y-para-cima (glTF/GLB, three.js) para Z-para-cima (IFC, CAD)."""
    vertices = np.asarray(vertices, dtype=float)
    return np.column_stack((vertices[:, 0], -vertices[:, 2], vertices[:, 1]))


def convencao_do_ficheiro(caminho, cima=None):
    """(convencao, motivo) dos eixos ao desenhar: 'y' para Y-para-cima, 'z' para Z-para-cima."""
    extensao = os.path.splitext(str(caminho))[1].lower()
    pedida = str(cima or "").strip().lower()
    if pedida and pedida not in ("y", "z"):
        raise ValueError(f"convencao '{cima}' desconhecida. Use 'y' (Y para cima: glTF, three.js) ou 'z' (Z para cima: IFC, CAD)")
    if pedida:
        return pedida, "declarada por si"
    assumida = CONVENCAO_POR_EXTENSAO.get(extensao, CONVENCAO_PADRAO)
    if assumida == "y":
        return "y", f"assumida pela extensao {extensao} (glTF/GLB e Y para cima)"
    return "z", "padrao do desenhador (Z para cima: IFC, CAD, STL)"


def _identidades(vertices, casas):
    chaves = np.round(np.asarray(vertices, dtype=float), casas)
    _, ident = np.unique(chaves, axis=0, return_inverse=True)
    return np.asarray(ident).reshape(-1)
