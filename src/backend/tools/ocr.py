"""Texto escrito dentro de uma imagem: print, prancha, planta, documento fotografado.

O motor e o RapidOCR sobre o onnxruntime que ja esta instalado, com os modelos do
proprio pacote - nao descarrega nada e nao precisa de binario externo. Cada trecho
sai com a caixa e a confianca: numa prancha, a POSICAO do numero e o que diz a que
parede ele pertence, e a confianca e o que separa uma cota de uma letra inventada.
"""
import io
import os
import tempfile

from PIL import Image

from src.backend.services.file_service import resolver_caminho
from src.backend.services.imagem import pagina_do_pdf_em_png, retangulo_da_regiao
from src.backend.state import emit_event
from src.backend.tools.registry import register

DPI_LEITURA = 200
CONFIANCA_BAIXA = 60
MAX_TRECHOS = 80
_motor = None


@register(
    "tool_ler_texto_imagem",
    "Le o TEXTO escrito numa imagem ou numa pagina de PDF - print, prancha, planta, documento "
    "fotografado, painel de interface - e devolve cada trecho com a caixa (em % da imagem) e a "
    "confianca. E o caminho para tirar as COTAS de uma prancha ou o texto de um print em vez de "
    "adivinhar pela forma das letras. Nao descreve cenas nem mede geometria: para isso use "
    "tool_ver_imagem e tool_medir_referencia.",
    {
        "caminho_relativo": {
            "tipo": "STRING",
            "obrig": True,
            "padrao": "",
            "desc": "Imagem (png, jpg, webp, bmp, tif) ou PDF, no projeto ou fora dele.",
        },
        "pagina": {
            "tipo": "INTEGER",
            "desc": "Pagina do PDF a ler (1 = a primeira).",
            "padrao": 1,
        },
        "regiao": {
            "tipo": "STRING",
            "desc": "Le so 'x,y,largura,altura' em pixels da imagem (ex: '0,570,300,120'). Vazio = a imagem inteira, que e o caminho normal: o motor localiza sozinho toda a escrita. Use 'regiao' para isolar uma zona carregada, e com folga - medido, recortes apertados em cima do texto podem nao devolver nada.",
            "padrao": "",
        },
    },
)
def tool_ler_texto_imagem(caminho_relativo, pagina=1, regiao=""):
    emit_event("executing", function=f"Lendo texto em: {caminho_relativo}")
    alvo, erro = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro:
        return erro
    if not os.path.isfile(alvo):
        return f"ERRO: ficheiro nao encontrado: {caminho_relativo}"
    temporario = ""
    try:
        caminho, temporario, largura, altura, deslocamento = _imagem_a_ler(alvo, pagina, regiao)
        leitura = _motor_de_leitura()(caminho)
    except ValueError as falha:
        return f"ERRO: {falha}"
    except Exception as falha:
        return f"ERRO: nao foi possivel ler '{caminho_relativo}' ({falha})."
    finally:
        if temporario:
            try:
                os.remove(temporario)
            except OSError:
                pass
    return _relato(caminho_relativo, leitura, largura, altura, deslocamento, bool(regiao))


def _motor_de_leitura():
    global _motor
    if _motor is None:
        from rapidocr import RapidOCR

        _motor = RapidOCR()
    return _motor


def _imagem_a_ler(alvo, pagina, regiao):
    """(caminho para o motor, temporario a apagar, largura, altura, canto do recorte)."""
    if alvo.lower().endswith(".pdf"):
        bruto, _ = pagina_do_pdf_em_png(alvo, pagina, DPI_LEITURA)
        temporario = _em_temporario(bruto)
        largura, altura = _dimensoes_do_bruto(bruto)
        return temporario, temporario, largura, altura, (0, 0)
    largura, altura = _dimensoes_do_ficheiro(alvo)
    if not regiao:
        return alvo, "", largura, altura, (0, 0)
    caixa = retangulo_da_regiao(regiao)
    if not caixa:
        raise ValueError("'regiao' tem de ser 'x,y,largura,altura' em pixels (ex: '30,540,300,90').")
    if caixa[0] < 0 or caixa[1] < 0 or caixa[2] > largura or caixa[3] > altura:
        raise ValueError(f"a regiao {caixa} sai fora da imagem, que tem {largura}x{altura} px.")
    with Image.open(alvo) as imagem:
        imagem.load()
        recorte = imagem.crop(caixa).convert("RGB")
    buffer = io.BytesIO()
    recorte.save(buffer, format="PNG", optimize=True)
    temporario = _em_temporario(buffer.getvalue())
    return temporario, temporario, largura, altura, (caixa[0], caixa[1])


def _em_temporario(bruto):
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as ficheiro:
        ficheiro.write(bruto)
        return ficheiro.name


def _dimensoes_do_ficheiro(alvo):
    with Image.open(alvo) as imagem:
        return imagem.size


def _dimensoes_do_bruto(bruto):
    with Image.open(io.BytesIO(bruto)) as imagem:
        return imagem.size


def _lista(valor):
    """Lista de um campo do motor de leitura: None, tuplo ou array do numpy."""
    return [] if valor is None else list(valor)


def _relato(caminho, leitura, largura, altura, deslocamento, recortada):
    textos = [str(texto) for texto in _lista(getattr(leitura, "txts", None))]
    caixas = _lista(getattr(leitura, "boxes", None))
    notas = [float(nota) for nota in _lista(getattr(leitura, "scores", None))]
    onde = "no recorte" if recortada else "na imagem"
    if not textos:
        return (
            f"Nenhum texto encontrado {onde} de '{caminho}' ({largura}x{altura} px). Pode nao "
            "haver escrita nenhuma (um desenho puro, uma foto sem letras), a letra ser pequena "
            "demais para o motor, ou o recorte ter ficado apertado em cima do texto. Com 'regiao', "
            "isole a zona com folga - e, em duvida, leia a imagem inteira: sem 'regiao' o motor "
            "localiza sozinho toda a escrita."
        )
    medidas = [_caixa_em_percentagem(caixa, largura, altura, deslocamento) for caixa in caixas]
    trechos = list(zip(textos, medidas, notas))
    linhas = [
        f"  {nota * 100:5.1f}%  x {medida[0]:3.0f}..{medida[2]:3.0f}%  y {medida[1]:3.0f}..{medida[3]:3.0f}%"
        f"  {texto.strip()}"
        for texto, medida, nota in trechos[:MAX_TRECHOS]
    ]
    media = 100 * sum(notas) / len(notas)
    relato = [
        f"Texto lido {onde} de '{caminho}' ({largura}x{altura} px): {len(textos)} trecho(s).",
        "  conf.   caixa (em % da imagem)                                  escrita",
        *linhas,
    ]
    if len(trechos) > MAX_TRECHOS:
        relato.append(f"  (mais {len(trechos) - MAX_TRECHOS} trecho(s) nao mostrados)")
    relato.append(f"Confianca media: {media:.0f}%.")
    if media < CONFIANCA_BAIXA:
        relato.append(
            f"AVISO: confianca media de {media:.0f}% - leitura insegura. Confirme o texto na "
            "imagem antes de o usar: numa imagem gerada por IA (render, concept art) a escrita "
            "pode ser pseudo-texto, letras plausiveis que nao formam palavra nenhuma."
        )
    return "\n".join(relato)


def _caixa_em_percentagem(caixa, largura, altura, deslocamento):
    xs = [float(ponto[0]) + deslocamento[0] for ponto in caixa]
    ys = [float(ponto[1]) + deslocamento[1] for ponto in caixa]
    return (100 * min(xs) / largura, 100 * min(ys) / altura,
            100 * max(xs) / largura, 100 * max(ys) / altura)
