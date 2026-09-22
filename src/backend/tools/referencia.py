"""Medir uma referencia visual antes de modelar, e comparar o modelo com ela em numeros.

Nao desenha e nao julga: mede. A forma como o olho julga - proporcao, largura por faixas da
altura, onde estao as zonas acesas - sai daqui em percentagens do proprio objeto, para que
duas imagens de escalas diferentes possam ser comparadas lado a lado.
"""
import os
import tempfile

from src.backend.geometry import referencia as medicao
from src.backend.geometry.vista import (
    EXTENSOES_MODELO,
    desenhar,
    desenho_do_ficheiro,
    vistas_do_pedido,
)
from src.backend.services.file_service import resolver_caminho
from src.backend.services.imagem import codificar_para_envio, lado_a_lado
from src.backend.state import emit_event
from src.backend.tools.registry import register

FAIXAS = medicao.FAIXAS
MARCAS = medicao.MARCAS


@register(
    "tool_medir_referencia",
    "Mede uma imagem de referencia em NUMEROS, antes de modelar: separa o objeto do fundo, da a "
    "proporcao (largura/altura), o eixo mais longo, a inclinacao, a largura em cada faixa da "
    "altura (o que faz a silhueta), os vazios interiores e ONDE ESTAO AS ZONAS MAIS ACESAS - "
    "'o ponto mais brilhante esta a 60% da altura' e a resposta que faltava para saber a que "
    "altura poe os olhos. Tudo em percentagem do proprio objeto, logo serve para comparar "
    "imagens de escalas diferentes. Devolve tambem um desenho do diagnostico (contorno, faixas e "
    "marcas) para se ver se a medicao acertou - use-o SEMPRE antes de confiar nos numeros, e "
    "ele mesmo: se a separacao do fundo falhar, o relato avisa. Medir a referencia antes de "
    "modelar poupa rodadas inteiras: modelar por intuicao erra por dezenas de pontos percentuais. "
    "Quando a silhueta encosta a moldura (o relato avisa logo no inicio): OLHE para a imagem, diga "
    "onde esta o objeto em 'quadro' - a separacao passa a correr DENTRO desse quadro, por corte de "
    "grafos, e a forma sai medida (proporcao, largura por faixa, centro); as marcas acesas passam a "
    "ser relativas ao objeto, e e delas que saem as proporcoes (a que altura estao os olhos, o "
    "centro do rosto) para modelar. Sem quadro, uma imagem sem fundo separavel so da o desenho do "
    "diagnostico e as marcas.",
    {
        "imagem": {
            "tipo": "STRING",
            "desc": "Imagem de referencia (foto, render, prancha, captura) dentro do projeto.",
            "obrig": True,
            "padrao": "",
        },
        "faixas": {
            "tipo": "INTEGER",
            "desc": "Em quantas faixas horizontais dividir a altura para medir a largura (8 a 40).",
            "padrao": FAIXAS,
        },
        "marcas": {
            "tipo": "INTEGER",
            "desc": "Quantas zonas acesas listar, da mais clara para a menos.",
            "padrao": MARCAS,
        },
        "quadro": {
            "tipo": "STRING",
            "desc": "Para quando a separacao do fundo falha (o relato diz que a silhueta encosta a moldura): olhe para a imagem, diga onde esta o objeto. A partir daqui a ferramenta corta o objeto DENTRO desse quadro por corte de grafos (GrabCut) e mede a forma dele - proporcao, largura por faixa, centro - com as marcas acesas relativas ao objeto; so quando esse corte nao da resultado fiavel (quadro a cobrir quase toda a imagem) e que fica valendo o quadro indicado. Quatro numeros SEPARADOS POR VIRGULA, em porcentagem da imagem, no sentido x0,y0,x1,y1 a partir do canto superior esquerdo (ex: '15,6,86,93'). Sem ele, a imagem sem fundo separavel so da o desenho do diagnostico.",
            "padrao": "",
        },
        "destino": {
            "tipo": "STRING",
            "desc": "Caminho onde gravar o desenho do diagnostico (ex: gerados/x/medida_ref.png). Vazio so mede.",
            "padrao": "",
        },
        "mostrar": {
            "tipo": "BOOLEAN",
            "desc": "Entregar o desenho do diagnostico como imagem, alem do texto.",
            "padrao": True,
        },
    },
)
def tool_medir_referencia(imagem, faixas=FAIXAS, marcas=MARCAS, quadro="", destino="", mostrar=True):
    emit_event("executing", function=f"Medindo referencia: {imagem}")
    alvo, erro = resolver_caminho(imagem, permitir_extra=True)
    if erro:
        return erro
    if not os.path.isfile(alvo):
        return f"ERRO: ficheiro nao encontrado: {imagem}"
    try:
        medidas = medicao.medir(
            alvo, faixas=_teto(faixas, 8, 40), marcas=_teto(marcas, 1, 12), quadro=_quadro(quadro)
        )
    except ValueError as falha:
        return f"ERRO: {falha}."
    except Exception as falha:
        return f"ERRO: nao consegui medir '{imagem}' ({falha})."
    try:
        png = medicao.desenho(medidas)
    except Exception as falha:
        return medicao.relato(medidas, imagem) + f"\n\nAVISO: a medicao saiu, mas o desenho do diagnostico falhou ({falha})."
    return _resposta(medicao.relato(medidas, imagem), png, destino, f"medida de {imagem}", mostrar)


@register(
    "tool_comparar_com_referencia",
    "Poe o MODELO ao lado da REFERENCIA em numeros, os dois medidos pelo mesmo instrumento: "
    "proporcao, centro de massa, inclinacao e a largura faixa a faixa da altura, com a diferenca "
    "de cada uma e um veredicto. E o que faltava para julgar forma: olhar cinco rodadas para uma "
    "imagem de cada vez nao mostra o desvio - as duas ao mesmo tempo, em numeros, mostram. "
    "Entrega tambem as duas imagens lado a lado com as medicoes desenhadas por cima. O brilho do "
    "modelo NAO entra na comparacao (depende da luz do desenho, nao da forma), logo compare "
    "silhueta, nunca iluminacao. Use a MESMA vista que a referencia mostra.",
    {
        "modelo": {
            "tipo": "STRING",
            "desc": "Ficheiro do modelo a comparar (.ifc, .obj, .glb, .stl, .ply, .3mf, .off), dentro do projeto.",
            "obrig": True,
            "padrao": "",
        },
        "referencia": {
            "tipo": "STRING",
            "desc": "Imagem de referencia com a qual comparar.",
            "obrig": True,
            "padrao": "",
        },
        "vista": {
            "tipo": "STRING",
            "desc": "Vista do modelo a desenhar e medir: frente, lado, costas, 3q, topo (a primeira e a que conta).",
            "padrao": "frente",
        },
        "cima": {
            "tipo": "STRING",
            "desc": "Eixo que e para cima no ficheiro: 'z' (IFC/CAD/STL) ou 'y' (glTF/three.js). Vazio decide pela extensao. Se a comparacao disser que a inclinacao saiu 90 graus e a referencia e de pe, e este o parametro a trocar.",
            "padrao": "",
        },
        "faixas": {
            "tipo": "INTEGER",
            "desc": "Em quantas faixas horizontais a altura e dividida na comparacao (8 a 40).",
            "padrao": FAIXAS,
        },
        "quadro": {
            "tipo": "STRING",
            "desc": "Retangulo do objeto DENTRO da referencia, em porcentagem dela no sentido x0,y0,x1,y1 (ex: '15,6,86,93') - use quando o fundo da referencia nao se separa. O modelo continua a ser medido pela silhueta do desenho.",
            "padrao": "",
        },
        "destino": {
            "tipo": "STRING",
            "desc": "Caminho onde gravar a imagem das duas lado a lado (ex: gerados/x/comparacao.png). Vazio nao grava.",
            "padrao": "",
        },
        "mostrar": {
            "tipo": "BOOLEAN",
            "desc": "Entregar a imagem das duas lado a lado, alem do texto.",
            "padrao": True,
        },
    },
)
def tool_comparar_com_referencia(modelo, referencia, vista="frente", cima="", faixas=FAIXAS,
                                 quadro="", destino="", mostrar=True):
    emit_event("executing", function=f"Comparando {modelo} com {referencia}")
    caminho_modelo, erro = resolver_caminho(modelo, permitir_extra=True)
    if erro:
        return erro
    caminho_referencia, erro = resolver_caminho(referencia, permitir_extra=True)
    if erro:
        return erro
    if not os.path.isfile(caminho_modelo):
        return f"ERRO: ficheiro nao encontrado: {modelo}"
    if not os.path.isfile(caminho_referencia):
        return f"ERRO: ficheiro nao encontrado: {referencia}"
    if os.path.splitext(caminho_modelo)[1].lower() not in EXTENSOES_MODELO:
        return (f"ERRO: '{modelo}' nao e um modelo que eu saiba desenhar. Aceito: "
                f"{', '.join(EXTENSOES_MODELO)}.")
    quantas = _teto(faixas, 8, 40)
    try:
        nome, azimute, elevacao = vistas_do_pedido(vista)[0]
    except ValueError as falha:
        return f"ERRO: {falha}."
    try:
        triangulos, rodape = desenho_do_ficheiro(caminho_modelo, None, cima or None)
    except ValueError as falha:
        return f"ERRO: {falha}."
    try:
        medidas_referencia = medicao.medir(
            caminho_referencia, faixas=quantas, quadro=_quadro(quadro)
        )
    except ValueError as falha:
        return f"ERRO na referencia '{referencia}': {falha}."
    except Exception as falha:
        return f"ERRO: nao consegui medir a referencia '{referencia}' ({falha})."
    try:
        bruto_modelo = _png_do_modelo(triangulos, azimute, elevacao)
        medidas_modelo = medicao.medir_bytes(bruto_modelo, faixas=quantas)
    except ValueError as falha:
        return f"ERRO no modelo '{modelo}': {falha}."
    except Exception as falha:
        return f"ERRO: nao consegui medir o modelo '{modelo}' ({falha})."

    texto = medicao.comparar(medidas_referencia, medidas_modelo, referencia, f"{modelo} na vista {nome}")
    texto += f"\nVista do modelo: {nome} (azimute {azimute:g}, elevacao {elevacao:g}){rodape}."
    if medidas_referencia["toca_a_moldura"]:
        texto += ("\nAVISO: na referencia a silhueta encosta a moldura - confirme no desenho "
                  "lado a lado se a separacao do fundo ficou com o objeto. Se o fundo nao se "
                  "separa, passe 'quadro' com o retangulo do objeto (x0,y0,x1,y1 em % da imagem): "
                  "a comparacao passa a ser relativa a ele.")
        if medidas_referencia.get("quadro") and not medidas_referencia.get("silhueta", True):
            texto += ("\nAVISO: na referencia vale o quadro declarado, nao a silhueta - o modelo "
                      "do outro lado e medido pela silhueta do desenho.")
        if medidas_referencia.get("quadro") and medidas_referencia.get("silhueta", True):
            texto += ("\nAVISO: na referencia o objeto foi separado DENTRO do quadro que indicaste, "
                      "por corte de grafos, e a comparacao ja e entre as duas silhuetas.")
    try:
        juntas = lado_a_lado(
            medicao.desenho(medidas_referencia),
            medicao.desenho(medidas_modelo),
        )
    except Exception as falha:
        return texto + f"\n\nAVISO: os numeros sairam, mas a imagem lado a lado falhou ({falha})."
    return _resposta(texto, juntas, destino, f"{modelo} vs {referencia}", mostrar)


def _png_do_modelo(triangulos, azimute, elevacao):
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as ficheiro:
        saida = ficheiro.name
    try:
        desenhar(triangulos, saida, azimute=azimute, elevacao=elevacao)
        with open(saida, "rb") as ficheiro:
            return ficheiro.read()
    finally:
        try:
            os.remove(saida)
        except OSError:
            pass


def _resposta(texto, png, destino, rotulo, mostrar):
    gravado = ""
    if destino:
        caminho, erro = resolver_caminho(destino, permitir_extra=False, permitir_escrita=True)
        if erro:
            gravado = "\n" + erro
        else:
            pasta = os.path.dirname(caminho)
            if pasta:
                os.makedirs(pasta, exist_ok=True)
            with open(caminho, "wb") as ficheiro:
                ficheiro.write(png)
            gravado = f"\nDesenho gravado em '{destino}'."
    if not mostrar:
        return texto + gravado
    base64_img, mime, entregue = codificar_para_envio(png)
    return {
        "texto": texto + gravado + " Olhe para o desenho antes de concluir: os numeros dizem o que mediu, o desenho diz se mediu o que julgava.",
        "imagem": {"base64": base64_img, "mime": mime, "rotulo": f"[{rotulo}]"},
    }


def _teto(valor, minimo, maximo):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return minimo
    return max(minimo, min(maximo, numero))


def _quadro(declarado):
    if not str(declarado).strip():
        return None
    partes = [parte for parte in str(declarado).replace(";", ",").split(",") if parte.strip()]
    if len(partes) != 4:
        raise ValueError(
            f"o quadro precisa de 4 numeros (x0,y0,x1,y1 em % da imagem) e chegaram {len(partes)}"
        )
    try:
        return tuple(float(parte) / 100.0 for parte in partes)
    except ValueError:
        raise ValueError(f"o quadro tem um valor que nao e numero: '{declarado}'")
