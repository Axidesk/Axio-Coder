import os

from src.backend.geometry import inspecao
from src.backend.services.file_service import resolver_caminho
from src.backend.state import emit_event
from src.backend.tools.registry import register

MAX_PECAS = 20
EIXOS = ("x", "y", "z")


@register(
    "tool_medir_malha",
    "Le um ficheiro de malha (.obj, .glb, .gltf, .stl, .ply, .3mf, .off) e diz o que ele E, em "
    "numeros MEDIDOS: a caixa por eixo, qual o eixo mais longo, as pecas LIGADAS por arestas "
    "(cada pedaco separado, com tamanho, centro, volume e a fatia de faces que ocupa) e os eixos "
    "principais (PCA). E o caminho para responder 'o que e isto que aparece aceso?' num modelo "
    "desconhecido: um busto humano carregado do three.js tem 15 pecas ligadas, e as 'bolas' que "
    "se viam eram os globos oculares - sem esta medicao isso descobre-se a adivinhar por sombra. "
    "Com 'rodar' aplica uma rotacao e grava uma copia, medindo antes e depois - e assim que se "
    "poe a cara em +Z e o topo em +Y sem recarregar a aplicacao a cada tentativa. Nao confundir "
    "com olhar para o modelo: esta ferramenta so mede, quem julga a forma e tool_ver_imagem.",
    {
        "caminho_relativo": {
            "tipo": "STRING",
            "desc": "Ficheiro de malha a medir (.obj, .glb, .gltf, .stl, .ply, .3mf, .off), dentro do projeto.",
            "obrig": True,
            "padrao": "",
        },
        "maximo": {
            "tipo": "INTEGER",
            "desc": "Numero maximo de pecas a listar, das maiores para as menores; as restantes sao somadas numa linha.",
            "padrao": MAX_PECAS,
        },
        "rodar": {
            "tipo": "STRING",
            "desc": "Rotacao 'eixo:graus' a aplicar antes de medir e gravar (ex: 'x:-90' ou 'y:90'); aceita varias separadas por ';' (ex: 'x:-90;z:90'). Vazio = so mede, nao grava nada.",
            "padrao": "",
        },
        "destino": {
            "tipo": "STRING",
            "desc": "Caminho de destino da copia rodada, dentro do projeto. Vazio grava '<nome>_rodado.<ext>' ao lado da origem.",
            "padrao": "",
        },
    },
)
def tool_medir_malha(caminho_relativo, maximo=MAX_PECAS, rodar="", destino=""):
    emit_event("executing", function=f"Medindo malha: {caminho_relativo}")
    alvo, erro = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro:
        return erro
    if not os.path.isfile(alvo):
        return f"ERRO: ficheiro nao encontrado: {caminho_relativo}"
    try:
        vertices, faces = inspecao.carregar(alvo)
    except ValueError as falha:
        return f"ERRO: {falha}"
    except Exception as falha:
        return f"ERRO: nao consegui ler '{caminho_relativo}' ({falha})."

    linhas = _relato(caminho_relativo, vertices, faces, _teto(maximo))
    if not str(rodar or "").strip():
        return "\n".join(linhas)

    try:
        giradas = vertices
        for eixo, graus in _rotacoes(rodar):
            giradas = inspecao.rodar(giradas, eixo, graus)
    except ValueError as falha:
        return "\n".join(linhas + ["", f"ERRO: {falha}"])

    extensao = os.path.splitext(alvo)[1].lower()
    relativo_destino = _destino_da_copia(caminho_relativo, destino, extensao)
    caminho_destino, erro_destino = resolver_caminho(relativo_destino, permitir_extra=False, permitir_escrita=True)
    if erro_destino:
        return "\n".join(linhas + ["", erro_destino])
    try:
        inspecao.guardar(caminho_destino, giradas, faces)
    except Exception as falha:
        return "\n".join(linhas + ["", f"ERRO: nao consegui gravar '{relativo_destino}' ({falha})."])

    linhas += ["", f"GRAVADO: {relativo_destino} (rodado {rodar})", ""]
    linhas += _relato(relativo_destino, giradas, faces, _teto(maximo))
    return "\n".join(linhas)


def _relato(rotulo, vertices, faces, maximo):
    minimo, maximo_caixa, tamanho = inspecao.caixa(vertices)
    eixo_longo = EIXOS[int(tamanho.argmax())]
    grupos = inspecao.grupos(vertices, faces)
    linhas = [
        f"MALHA '{rotulo}': {len(vertices)} vertices, {len(faces)} faces, "
        f"{len(grupos)} peca(s) ligada(s) por arestas",
        "CAIXA (x, y, z): "
        + " x ".join(f"{valor:.4f}" for valor in tamanho)
        + f"  |  eixo mais longo: {eixo_longo} ({tamanho.max():.4f})",
        "CENTRO DA CAIXA: " + ", ".join(f"{valor:.4f}" for valor in (minimo + tamanho / 2)),
        "EIXOS PRINCIPAIS (PCA - a direcao e o comprimento medido nela):",
    ]
    for posicao, (vetor, extensao) in enumerate(inspecao.eixos_principais(vertices), start=1):
        linhas.append(
            f"  {posicao}) ({vetor[0]:+.3f}, {vetor[1]:+.3f}, {vetor[2]:+.3f}) - {extensao:.4f}"
        )
    linhas.append(f"PECAS (por numero de faces, {len(grupos)} no total):")
    restantes = 0
    faces_restantes = 0
    for posicao, do_grupo in enumerate(grupos, start=1):
        if posicao > maximo:
            restantes += 1
            faces_restantes += len(do_grupo)
            continue
        indices = [int(valor) for face in faces[do_grupo] for valor in face]
        usados = sorted(set(indices))
        pontos = vertices[usados]
        _, _, medida = inspecao.caixa(pontos)
        volume = abs(inspecao.volume(vertices, faces[do_grupo]))
        linhas.append(
            f"  {posicao}) {len(do_grupo)} faces ({len(do_grupo) / len(faces):.1%}), "
            f"{len(usados)} vertices, caixa " + "x".join(f"{valor:.3f}" for valor in medida)
            + ", centro (" + ", ".join(f"{valor:.3f}" for valor in pontos.mean(axis=0)) + ")"
            + f", volume {volume:.5f}"
        )
    if restantes:
        linhas.append(f"  ... e {restantes} peca(s) menor(es), {faces_restantes} faces no total")
    if len(grupos) == 1:
        linhas.append("NOTA: uma so peca ligada - o ficheiro e uma malha unica, nao um conjunto.")
    linhas.append(
        "AVISO: nada nesta medicao diz qual eixo e a ALTURA do objeto - o eixo mais longo pode ser "
        "os ombros. Decida pela anatomia/forma e confirme com tool_ver_imagem (que aceita "
        "cima='y' ou 'z' e diz na legenda qual usou)."
    )
    return linhas


def _rotacoes(texto):
    pedacos = [parte.strip() for parte in str(texto).split(";") if parte.strip()]
    if not pedacos:
        raise ValueError("'rodar' vazio. Escreva 'eixo:graus' (ex: 'x:-90')")
    rotacoes = []
    for pedaco in pedacos:
        eixo, _, graus = pedaco.partition(":")
        eixo = eixo.strip().lower()
        if eixo not in EIXOS:
            raise ValueError(f"eixo '{eixo}' desconhecido em '{pedaco}'. Use x, y ou z")
        try:
            rotacoes.append((eixo, float(graus)))
        except ValueError:
            raise ValueError(f"graus invalidos em '{pedaco}'. Escreva 'eixo:graus' (ex: 'x:-90')") from None
    return rotacoes


def _destino_da_copia(caminho_relativo, destino, extensao):
    if str(destino or "").strip():
        return destino
    raiz, _ = os.path.splitext(str(caminho_relativo))
    return f"{raiz}_rodado{extensao or '.obj'}"


def _teto(maximo):
    try:
        return max(1, int(maximo))
    except (TypeError, ValueError):
        return MAX_PECAS
