"""Imagem que vai para o modelo: formato real, teto de pixels, codificacao e pedacos.

O formato e decidido pelo CONTEUDO (assinatura de bytes), nunca pela extensao nem
pelo mime que o cliente declarou - um nome errado nao pode decidir o que vai no
pedido. Quando a imagem ja cabe no teto E esta num formato que a API aceita, os
bytes originais seguem intactos: recomprimir o que ja serve so perde qualidade.

O TETO NAO E NOSSO: antes da inferencia a API reduz toda a imagem a ~800x800
pixels equivalentes (384 tokens por imagem, no maximo). Enviar o ecra maior nao
acrescenta detalhe nenhum - o que sai daqui ja e o que o modelo ve. Para passar
esse teto o caminho e PARTIR a imagem (tiles_da_imagem): cada pedaco tem o seu
proprio teto e chega em tamanho original.
"""
import base64
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.request

from PIL import Image

from src.backend.config import APP_ROOT
from src.backend.services.persistencia import gravar_json_atomico
from src.backend.state import caminho_estado_projeto, estado

PIXELS_MODELO = 800 * 800
TOKENS_POR_IMAGEM = 384
LADO_TILE = 1024
SOBREPOSICAO_TILE = 32
MAX_PEDACOS = 16
LIMITE_IMAGEM_REDE = 12 * 1024 * 1024
LIMITE_VISTAS = 400

FORMATOS_ACEITOS = ("image/jpeg", "image/png", "image/gif", "image/webp")

_ASSINATURAS = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"\x00\x00\x01\x00", "image/x-icon"),
)


def detectar_mime(bruto):
    """Mime do formato REAL da imagem, lido da assinatura de bytes (None se nao reconhecer)."""
    if not bruto:
        return None
    for assinatura, mime in _ASSINATURAS:
        if bruto.startswith(assinatura):
            return mime
    if bruto[:4] == b"RIFF" and bruto[8:12] == b"WEBP":
        return "image/webp"
    return None


def preparar_imagem(bruto, pixels_max=PIXELS_MODELO):
    """(bytes, mime) prontos a enviar. Os bytes originais saem intactos quando ja servem."""
    mime = detectar_mime(bruto)
    if mime in FORMATOS_ACEITOS and _cabe_no_orcamento(bruto, pixels_max):
        return bruto, mime
    return _reduzir(bruto, pixels_max, mime)


def codificar_para_envio(bruto, pixels_max=PIXELS_MODELO):
    """(base64, mime, dimensoes) do que entra no pedido ao modelo."""
    final, mime = preparar_imagem(bruto, pixels_max)
    return base64.b64encode(final).decode("ascii"), mime, dimensoes_da_imagem(final)


def partes_da_imagem(bruto, max_pedacos=MAX_PEDACOS, pixels_max=PIXELS_MODELO):
    """(bytes, mime) de cada parte em que uma imagem segue para o modelo, em tamanho original.

    Dentro do orcamento de pixels a imagem sai inteira e intacta; acima dele e CORTADA
    em pedacos, porque reduzir-la ao teto apagaria o texto fino de um print. A imagem e
    reduzida quando os pedacos passariam de `max_pedacos`, para o custo nao crescer sem limite.
    """
    mime = detectar_mime(bruto)
    if mime in FORMATOS_ACEITOS and _cabe_no_orcamento(bruto, pixels_max):
        return [(bruto, mime)]
    with Image.open(io.BytesIO(bruto)) as imagem:
        imagem.load()
        imagem, caixas = _imagem_e_caixas(imagem, max_pedacos, pixels_max)
        return [codificar_pedaco(imagem.crop(caixa), mime) for caixa in caixas]


def codificar_pedaco(imagem, mime_origem):
    """(bytes, mime) de um pedaco recortado, no formato da origem (JPEG em foto, PNG no resto)."""
    buffer = io.BytesIO()
    if mime_origem == "image/jpeg":
        imagem.convert("RGB").save(buffer, format="JPEG", quality=90)
        return buffer.getvalue(), "image/jpeg"
    imagem.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), "image/png"


def tiles_da_imagem(largura, altura, pixels_max=PIXELS_MODELO, sobreposicao=SOBREPOSICAO_TILE):
    """Caixas (esquerda, topo, direita, base) que partem a imagem em pedacos dentro do teto da API.

    Os pedacos sobrepoem-se para uma linha de texto cortada na fronteira aparecer
    inteira no pedaco vizinho.
    """
    lado = min(LADO_TILE, largura)
    altura_tile = min(max(1, pixels_max // lado), altura)
    passo_x = max(1, lado - sobreposicao)
    passo_y = max(1, altura_tile - sobreposicao)
    return [
        (x, y, x + lado, y + altura_tile)
        for y in _inicios(altura, altura_tile, passo_y)
        for x in _inicios(largura, lado, passo_x)
    ]


def _na_altura(imagem, altura):
    largura = max(1, round(imagem.width * altura / imagem.height))
    return imagem.convert("RGB").resize((largura, altura), Image.Resampling.LANCZOS)


def lado_a_lado(esquerda, direita, altura=640, faixa=8):
    """Junta duas imagens numa so, na mesma altura, com a esquerda primeiro.

    Comparar um modelo com a referencia a olho obriga a alternar entre duas imagens,
    e a memoria do que se viu duas chamadas antes nao serve para julgar forma. Numa
    imagem so, as diferencas saltam. A faixa escura marca a fronteira.
    """
    with Image.open(io.BytesIO(esquerda)) as uma:
        primeira = _na_altura(uma, altura)
    with Image.open(io.BytesIO(direita)) as outra:
        segunda = _na_altura(outra, altura)
    junta = Image.new("RGB", (primeira.width + faixa + segunda.width, altura), (32, 32, 32))
    junta.paste(primeira, (0, 0))
    junta.paste(segunda, (primeira.width + faixa, 0))
    buffer = io.BytesIO()
    junta.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def dimensoes_da_imagem(bruto):
    """(largura, altura) de bytes de imagem; None quando nao sao uma imagem legivel."""
    try:
        with Image.open(io.BytesIO(bruto)) as imagem:
            return imagem.size
    except Exception:
        return None


def retangulo_da_regiao(regiao):
    """(esquerda, topo, direita, base) de 'x,y,largura,altura'; None se vazio ou invalido."""
    partes = [p.strip() for p in str(regiao or "").replace("x", ",").replace("X", ",").split(",") if p.strip()]
    if len(partes) != 4:
        return None
    try:
        x, y, largura, altura = (int(float(p)) for p in partes)
    except ValueError:
        return None
    return (x, y, x + max(1, largura), y + max(1, altura))


def _cabe_no_orcamento(bruto, pixels_max):
    dimensoes = dimensoes_da_imagem(bruto)
    return bool(dimensoes) and dimensoes[0] * dimensoes[1] <= pixels_max


def _imagem_e_caixas(imagem, max_pedacos, pixels_max):
    """(imagem a recortar, caixas dos pedacos), encolhendo-a enquanto passarem de max_pedacos.

    A contagem de pedacos nao acompanha a area ao certo (a ultima fila e a ultima coluna
    apanham o que sobra), por isso a reducao e verificada e repetida em vez de calculada.
    """
    caixas = tiles_da_imagem(imagem.width, imagem.height, pixels_max)
    for _ in range(5):
        if len(caixas) <= max_pedacos:
            break
        escala = (max_pedacos / len(caixas)) ** 0.5 * 0.97
        reduzida = imagem.resize(
            (max(1, round(imagem.width * escala)), max(1, round(imagem.height * escala))),
            Image.Resampling.LANCZOS,
        )
        if reduzida.size == imagem.size:
            break
        imagem = reduzida
        caixas = tiles_da_imagem(imagem.width, imagem.height, pixels_max)
    return imagem, caixas


def _reduzir(bruto, pixels_max, mime_origem):
    """Reduz ao teto de pixels e converte para um formato aceito (PNG para o que tem transparencia)."""
    with Image.open(io.BytesIO(bruto)) as imagem:
        imagem.load()
        total = imagem.width * imagem.height
        if total > pixels_max:
            escala = (pixels_max / total) ** 0.5
            tamanho = (max(1, int(imagem.width * escala)), max(1, int(imagem.height * escala)))
            imagem = imagem.resize(tamanho, Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        if mime_origem == "image/jpeg":
            imagem.convert("RGB").save(buffer, format="JPEG", quality=88)
            return buffer.getvalue(), "image/jpeg"
        imagem.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue(), "image/png"


def _inicios(tamanho, lado, passo):
    """Posicoes iniciais que cobrem [0, tamanho) com pedacos de comprimento 'lado'."""
    if tamanho <= lado:
        return [0]
    inicios = [0]
    while inicios[-1] + lado < tamanho:
        proximo = min(inicios[-1] + passo, tamanho - lado)
        if proximo <= inicios[-1]:
            break
        inicios.append(proximo)
    return inicios


def _registo_das_vistas():
    return caminho_estado_projeto("imagens_vistas.json") or os.path.join(APP_ROOT, ".axio", "imagens_vistas.json")


def _vistas_guardadas():
    caminho = _registo_das_vistas()
    if not os.path.isfile(caminho):
        return {}
    try:
        with open(caminho, "r", encoding="utf-8") as ficheiro:
            dados = json.load(ficheiro)
        return dados if isinstance(dados, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def registar_imagem_olhada(caminho):
    """Grava o sha256 do que acabou de ser olhado: e a prova de que ESTA imagem foi vista."""
    if not caminho or not os.path.isfile(caminho):
        return ""
    with open(caminho, "rb") as ficheiro:
        marca = hashlib.sha256(ficheiro.read()).hexdigest()
    vistas = _vistas_guardadas()
    vistas[marca] = {"nome": os.path.basename(caminho), "visto": time.strftime("%Y-%m-%d %H:%M:%S")}
    if len(vistas) > LIMITE_VISTAS:
        recentes = sorted(vistas.items(), key=lambda item: item[1].get("visto", ""))
        vistas = dict(recentes[-LIMITE_VISTAS:])
    gravar_json_atomico(_registo_das_vistas(), vistas)
    return marca


def _bytes_do_endereco(endereco):
    if endereco.lower().startswith(("http://", "https://")):
        pedido = urllib.request.Request(endereco, headers={"User-Agent": "axio"})
        try:
            with urllib.request.urlopen(pedido, timeout=25) as resposta:
                return resposta.read(LIMITE_IMAGEM_REDE + 1), ""
        except urllib.error.HTTPError as falha:
            return None, f"respondeu {falha.code}"
        except Exception as falha:
            return None, str(falha)[:120]
    raiz = estado.get("pasta_raiz") or APP_ROOT
    caminho = endereco if os.path.isabs(endereco) else os.path.join(raiz, endereco)
    if not os.path.isfile(caminho):
        return None, "ficheiro nao encontrado"
    try:
        with open(caminho, "rb") as ficheiro:
            return ficheiro.read(LIMITE_IMAGEM_REDE + 1), ""
    except OSError as falha:
        return None, str(falha)[:120]


def conferir_imagens(enderecos):
    """Confere cada imagem antes de sair para a rede: carrega mesmo, e ja foi olhada?

    A identidade e o CONTEUDO (sha256 dos bytes), nunca o caminho: a imagem servida
    pelo raw do GitHub e a do disco dao a mesma marca, e uma imagem que mudou deixa
    de passar - e e isso que impede publicar as cegas.
    """
    vistas = _vistas_guardadas()
    problemas = []
    for endereco in dict.fromkeys(alvo for alvo in enderecos if alvo):
        bruto, erro = _bytes_do_endereco(endereco)
        if erro:
            problemas.append((endereco, f"nao carrega ({erro})"))
            continue
        if len(bruto) > LIMITE_IMAGEM_REDE:
            problemas.append((endereco, "maior do que o limite de leitura"))
            continue
        if hashlib.sha256(bruto).hexdigest() not in vistas:
            problemas.append((endereco, "nunca foi olhada por mim"))
    return problemas
