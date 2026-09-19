import math
import os

import numpy as np

from src.backend.geometry.malhas import diferenca, norma, produto_vetorial, unitario
from src.backend.geometry.raster import Rasterizador

VISTAS = {
    "frente": (0.0, 0.0),
    "lado": (90.0, 0.0),
    "costas": (180.0, 0.0),
    "3q": (35.0, 18.0),
    "topo": (0.0, 88.0),
}

EXTENSOES_MALHA = (".stl", ".obj", ".ply", ".glb", ".gltf", ".3mf", ".off")
EXTENSOES_MODELO = (".ifc",) + EXTENSOES_MALHA

LUZ = (-0.45, -0.60, 0.66)
RECHECIO = (-0.75, 0.35, 0.30)
FUNDO = (10, 12, 18)
AMBIENTE = 0.30
DIFUSA = 0.62
ESPECULAR = 0.28
TETO_INTENSIDADE = 1.35
MARGEM = 0.06
TETO_VISTAS = 4
PIXELS_VISTA = 800 * 800


def vistas_do_pedido(texto):
    escolhidas = [parte.strip() for parte in str(texto or "").split(";") if parte.strip()] or ["3q"]
    if len(escolhidas) > TETO_VISTAS:
        raise ValueError(f"no maximo {TETO_VISTAS} vistas por pedido (pediu {len(escolhidas)})")
    return [(nome, *_angulos(nome)) for nome in escolhidas]


def de_ficheiro(caminho, focar=None):
    extensao = os.path.splitext(caminho)[1].lower()
    if extensao == ".ifc":
        return _de_ifc(caminho, focar)
    if extensao in EXTENSOES_MALHA:
        return _de_malha(caminho)
    raise ValueError(f"nao sei desenhar '{extensao}'. Aceito: .ifc, {', '.join(EXTENSOES_MALHA)}")


def desenhar(triangulos, saida, azimute=0.0, elevacao=0.0, largura=0, altura=0, margem=MARGEM):
    from PIL import Image

    olhar, direita, cima = _base_camera(azimute, elevacao)
    projetados = []
    caixa = [float("inf"), float("inf"), float("-inf"), float("-inf")]
    for entrada in triangulos:
        pontos, cor = entrada[0], entrada[1]
        etiqueta = entrada[2] if len(entrada) > 2 else ""
        plano = [
            (
                ponto[0] * direita[0] + ponto[1] * direita[1] + ponto[2] * direita[2],
                ponto[0] * cima[0] + ponto[1] * cima[1] + ponto[2] * cima[2],
                ponto[0] * olhar[0] + ponto[1] * olhar[1] + ponto[2] * olhar[2],
            )
            for ponto in pontos
        ]
        for x, y, _ in plano:
            caixa[0] = min(caixa[0], x)
            caixa[1] = min(caixa[1], y)
            caixa[2] = max(caixa[2], x)
            caixa[3] = max(caixa[3], y)
        projetados.append((plano, cor, etiqueta, pontos))

    largura_util = max(caixa[2] - caixa[0], 1e-6)
    altura_util = max(caixa[3] - caixa[1], 1e-6)
    largura, altura = _tamanho_que_cabe(largura, altura, largura_util / altura_util)
    escala = min(
        (largura * (1 - 2 * margem)) / largura_util,
        (altura * (1 - 2 * margem)) / altura_util,
    )
    deslocamento_x = largura / 2 - (caixa[0] + largura_util / 2) * escala
    deslocamento_y = altura / 2 + (caixa[1] + altura_util / 2) * escala

    luz = unitario(LUZ)
    recheio = unitario(RECHECIO)
    fundo = tuple(canal / 255 for canal in FUNDO)
    pixels = []
    profundidades = []
    cores = []
    numeros = []
    areas = []
    indice_por_peca = {}
    descartados = 0
    for plano, cor, etiqueta, pontos in projetados:
        normal = produto_vetorial(diferenca(pontos[1], pontos[0]), diferenca(pontos[2], pontos[0]))
        if norma(normal) < 1e-12:
            continue
        normal = unitario(normal)
        if sum(componente * vista for componente, vista in zip(normal, olhar)) >= -1e-9:
            descartados += 1
            continue
        tom, transparencia = _material(cor)
        intensidade = (
            AMBIENTE
            + DIFUSA * abs(sum(n * l for n, l in zip(normal, luz)))
            + ESPECULAR * abs(sum(n * l for n, l in zip(normal, recheio)))
        )
        if transparencia > 0.0:
            tom = tuple(
                canal * (1.0 - transparencia) + base * transparencia
                for canal, base in zip(tom, fundo)
            )
        desenhados = [(p[0] * escala + deslocamento_x, deslocamento_y - p[1] * escala) for p in plano]
        pixels.append(desenhados)
        profundidades.append([p[2] for p in plano])
        cores.append(_rgb(tom, min(intensidade, TETO_INTENSIDADE)))
        areas.append(
            abs(
                (desenhados[1][0] - desenhados[0][0]) * (desenhados[2][1] - desenhados[0][1])
                - (desenhados[2][0] - desenhados[0][0]) * (desenhados[1][1] - desenhados[0][1])
            )
            * 0.5
        )
        if etiqueta not in indice_por_peca:
            indice_por_peca[etiqueta] = len(indice_por_peca)
        numeros.append(indice_por_peca[etiqueta])

    tela = Rasterizador(largura, altura, FUNDO)
    tela.rasterizar(pixels, profundidades, cores)
    Image.fromarray(tela.cor).save(saida)
    return {
        "ficheiro": saida,
        "triangulos_lidos": len(triangulos),
        "triangulos_pintados": tela.pintados,
        "descartados": descartados,
        "tamanho": f"{largura}x{altura}",
        "enquadramento": f"{largura_util:.2f} x {altura_util:.2f}",
        **_visibilidade(tela, numeros, areas, indice_por_peca),
    }


def _material(cor):
    """(tom, transparencia) que aceita tanto a cor simples como o material do IFC."""
    if len(cor) > 3:
        return tuple(cor[:3]), max(0.0, min(1.0, float(cor[3])))
    return tuple(cor), 0.0


def _visibilidade(tela, numeros, areas, indice_por_peca):
    """Pixels ganhos por peca contra os que ela cobriria se nada estivesse a frente.

    A area projetada de cada triangulo (em pixels) e o que ele cobriria; o raster
    diz quantos sobreviveram ao teste de profundidade. A razao entre os dois separa
    o que esta escondido do que esta apenas tapado.
    """
    contagem = tela.pixels_por_triangulo(len(numeros))
    indices = np.array(numeros, dtype=np.int64)
    pintados = np.bincount(indices, weights=contagem, minlength=len(indice_por_peca))
    previstos = np.bincount(
        indices, weights=np.array(areas, dtype=np.float64), minlength=len(indice_por_peca)
    )
    pecas = sorted(
        ((nome, int(pintados[numero])) for nome, numero in indice_por_peca.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    tapadas = sorted(
        (
            (nome, round(float(pintados[numero]) / float(previstos[numero]), 3))
            for nome, numero in indice_por_peca.items()
            if previstos[numero] > 1.0 and 0 < pintados[numero] < previstos[numero] * 0.99
        ),
        key=lambda item: item[1],
    )
    return {
        "pixels": tela.cobertura(),
        "pecas": pecas,
        "escondidas": [nome for nome, valor in pecas if valor == 0 and nome],
        "tapadas": tapadas,
    }


def _angulos(nome):
    chave = nome.strip().lower()
    if chave in VISTAS:
        return VISTAS[chave]
    partes = [parte.strip() for parte in chave.split(",")]
    if len(partes) == 2:
        try:
            return (float(partes[0]), float(partes[1]))
        except ValueError:
            pass
    raise ValueError(f"vista '{nome}' desconhecida. Use: {', '.join(VISTAS)} ou 'azimute,elevacao'")


def _base_camera(azimute_graus, elevacao_graus):
    azimute = math.radians(azimute_graus)
    elevacao = math.radians(-elevacao_graus)
    olhar = (
        math.cos(elevacao) * math.sin(azimute),
        -math.cos(elevacao) * math.cos(azimute),
        math.sin(elevacao),
    )
    direita = (math.cos(azimute), math.sin(azimute), 0.0)
    cima = (
        -math.sin(elevacao) * math.sin(azimute),
        math.sin(elevacao) * math.cos(azimute),
        math.cos(elevacao),
    )
    return olhar, direita, cima


def _tamanho_que_cabe(largura, altura, proporcao):
    if largura and altura:
        return int(largura), int(altura)
    if proporcao >= 1.0:
        altura = int((PIXELS_VISTA / proporcao) ** 0.5)
        return max(1, int(altura * proporcao)), max(1, altura)
    largura = int((PIXELS_VISTA * proporcao) ** 0.5)
    return max(1, largura), max(1, int(largura / proporcao))


def _rgb(cor, intensidade):
    return tuple(max(0, min(255, int(255 * canal * intensidade))) for canal in cor)


def _tom(nome):
    if not nome:
        return (0.62, 0.64, 0.68)
    semente = 0
    for letra in nome:
        semente = (semente * 131 + ord(letra)) % 1000003
    matiz = (semente % 997) / 997.0
    onda = (
        abs(matiz * 6 - 3) - 1,
        2 - abs(matiz * 6 - 2),
        2 - abs(matiz * 6 - 4),
    )
    return tuple(min(0.94, max(0.30, canal * 0.62 + 0.26)) for canal in onda)


def _cor_do_estilo(estilo):
    """(R, G, B, transparencia) da superficie do estilo; None quando nao declara cor.

    A transparencia do IfcSurfaceStyleRendering e o que separa o acabamento dourado
    do painel translucido: sem ela as duas superficies saem com o mesmo tom.
    """
    for superficie in getattr(estilo, "Styles", None) or []:
        for alvo in getattr(superficie, "Styles", None) or []:
            cor = getattr(alvo, "SurfaceColour", None)
            if cor is not None:
                transparencia = getattr(alvo, "Transparency", None)
                return (
                    float(cor.Red),
                    float(cor.Green),
                    float(cor.Blue),
                    float(transparencia or 0.0),
                )
    return None


def _cores_por_produto(modelo):
    do_item = {}
    for estilo in modelo.by_type("IfcStyledItem"):
        cor = _cor_do_estilo(estilo)
        if cor is not None and estilo.Item is not None:
            do_item[estilo.Item.id()] = cor
    por_produto = {}
    for produto in modelo.by_type("IfcProduct"):
        representacao = getattr(produto, "Representation", None)
        if representacao is None:
            continue
        for forma in representacao.Representations or []:
            for item in forma.Items or []:
                cor = do_item.get(item.id())
                if cor is not None:
                    por_produto[produto.id()] = cor
                    break
            if produto.id() in por_produto:
                break
    return por_produto


def _passa_no_filtro(produto, focar):
    if not focar:
        return True
    alvo = str(focar).lower()
    return alvo in (getattr(produto, "Name", None) or "").lower() or alvo in produto.is_a().lower()


def _de_ifc(caminho, focar):
    import ifcopenshell
    import ifcopenshell.geom

    modelo = ifcopenshell.open(caminho)
    cores = _cores_por_produto(modelo)
    configuracao = ifcopenshell.geom.settings()
    configuracao.set(configuracao.USE_WORLD_COORDS, True)
    configuracao.set(configuracao.APPLY_DEFAULT_MATERIALS, False)
    configuracao.set("weld-vertices", False)
    iterador = ifcopenshell.geom.iterator(configuracao, modelo, min(8, os.cpu_count() or 1))
    if not iterador.initialize():
        raise ValueError("o modelo nao devolveu geometria")
    triangulos = []
    while True:
        forma = iterador.get()
        produto = modelo.by_id(forma.id)
        if _passa_no_filtro(produto, focar):
            verts = list(forma.geometry.verts)
            faces = list(forma.geometry.faces)
            pontos = [(verts[i], verts[i + 1], verts[i + 2]) for i in range(0, len(verts), 3)]
            nome = getattr(produto, "Name", None) or produto.is_a()
            cor = cores.get(produto.id()) or _tom(nome)
            for i in range(0, len(faces), 3):
                triangulos.append(((pontos[faces[i]], pontos[faces[i + 1]], pontos[faces[i + 2]]), cor, nome))
        if not iterador.next():
            break
    if not triangulos:
        raise ValueError(f"nenhuma peca passou no filtro '{focar}'" if focar else "o modelo nao tem triangulos")
    return triangulos


def _de_malha(caminho):
    import trimesh

    carregado = trimesh.load(caminho, force="mesh")
    vertices = [tuple(float(coordenada) for coordenada in ponto) for ponto in carregado.vertices]
    if not len(carregado.faces):
        raise ValueError("o ficheiro nao tem faces (e um conjunto de pontos?)")
    nome = os.path.basename(caminho)
    cor = _tom(nome)
    return [((vertices[a], vertices[b], vertices[c]), cor, nome) for a, b, c in carregado.faces]
