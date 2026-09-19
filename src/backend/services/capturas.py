"""Captura pronta a publicar: onde esta o conteudo, o recorte e o tamanho final.

Uma captura de ecra chega maior do que o que se quer mostrar e com zonas lisas a
volta - num ecra largo, a janela inteira deixa metade da imagem vazia, e no README
isso le-se como espaco morto. `mapa_de_atividade` diz ONDE esta o conteudo (grelha
de desvio por celula) antes de se escolher o recorte, e `preparar_captura` recorta,
reduz a largura maxima e grava, devolvendo as medidas do antes e do depois.
"""
import io
import os

from PIL import Image, ImageStat

LADO_DA_CELULA = 64
ESCALA_DO_DESVIO = 8
_NIVEIS = " .:-=+*#%@"


def mapa_de_atividade(bruto, celula=LADO_DA_CELULA):
    """Grelha de atividade da imagem: onde ha conteudo aceso e onde a zona e lisa."""
    with Image.open(io.BytesIO(bruto)) as imagem:
        cinza = imagem.convert("L")
        largura, altura = cinza.size
        colunas = max(1, largura // celula)
        linhas = max(1, altura // celula)
        fundo = ImageStat.Stat(cinza).median[0]
        grelha = []
        maior = 0.0
        for i in range(linhas):
            topo = round(i * altura / linhas)
            base = round((i + 1) * altura / linhas)
            linha = []
            for j in range(colunas):
                esquerda = round(j * largura / colunas)
                direita = round((j + 1) * largura / colunas)
                celula_estatistica = ImageStat.Stat(cinza.crop((esquerda, topo, direita, base)))
                atividade = max(celula_estatistica.stddev[0],
                                abs(celula_estatistica.mean[0] - fundo))
                maior = max(maior, atividade)
                linha.append(_NIVEIS[min(len(_NIVEIS) - 1, int(atividade / ESCALA_DO_DESVIO))])
            grelha.append("".join(linha))
    return {
        "texto": "\n".join(grelha),
        "colunas": colunas,
        "linhas": linhas,
        "celula": celula,
        "maior_atividade": round(maior, 1),
    }


def preparar_captura(origem, destino, caixa=None, largura=1920, qualidade=86):
    """Recorta, reduz e grava a captura; devolve o original, o recorte e o ficheiro gravado.

    Levanta ValueError quando a caixa nao toca a imagem: um recorte fora de escala
    nao pode sair daqui como um ficheiro de 1 px, que e o que a parece um defeito.
    """
    with open(origem, "rb") as ficheiro:
        bruto = ficheiro.read()
    with Image.open(io.BytesIO(bruto)) as imagem:
        original = imagem.size
        imagem = imagem.convert("RGB")
        recortada = None
        if caixa:
            esquerda, topo, direita, base = (int(v) for v in caixa)
            if direita <= 0 or base <= 0 or esquerda >= imagem.width or topo >= imagem.height:
                raise ValueError(
                    f"a caixa ({esquerda},{topo})-({direita},{base}) nao toca a imagem "
                    f"de {imagem.width}x{imagem.height} px"
                )
            esquerda = max(0, min(esquerda, imagem.width - 1))
            topo = max(0, min(topo, imagem.height - 1))
            direita = max(esquerda + 1, min(direita, imagem.width))
            base = max(topo + 1, min(base, imagem.height))
            imagem = imagem.crop((esquerda, topo, direita, base))
            recortada = imagem.size
        escala = min(1.0, float(largura) / imagem.width)
        if escala < 1:
            imagem = imagem.resize(
                (max(1, round(imagem.width * escala)), max(1, round(imagem.height * escala))),
                Image.Resampling.LANCZOS,
            )
        pasta = os.path.dirname(destino)
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        if destino.lower().endswith(".png"):
            imagem.save(destino, format="PNG", optimize=True)
        else:
            imagem.save(destino, format="JPEG", quality=int(qualidade), optimize=True,
                        subsampling=1)
        final = imagem.size
    return {
        "original": original,
        "recortada": recortada,
        "final": final,
        "bytes": os.path.getsize(destino),
    }
