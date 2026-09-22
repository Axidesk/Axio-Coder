"""Visao do agente: olhar para o ecra e para as imagens do projeto.

Estas ferramentas nao devolvem texto: devolvem {'texto', 'imagem'}. O loop separa
as duas coisas - o texto vai na resposta da ferramenta e a imagem e entregue a
parte, como mensagem do UTILIZADOR no pedido seguinte. A API so aceita imagens em
mensagens do utilizador: dentro da resposta de uma ferramenta seriam recusadas.
"""
import base64
import ctypes
import io
import os
import tempfile
import time

from PIL import Image, ImageGrab

from src.backend.geometry.vista import EXTENSOES_MODELO, desenhar, desenho_do_ficheiro, vistas_do_pedido
from src.backend.state import caminho_estado_projeto, emit_event, estado
from src.backend.tools.registry import register
from src.backend.services.capturas import fins_do_conteudo, mapa_de_atividade, preparar_captura
from src.backend.services.file_service import resolver_caminho
from src.backend.services.imagem import (
    DPI_PDF,
    TOKENS_POR_IMAGEM,
    codificar_pedaco,
    codificar_para_envio,
    dimensoes_da_imagem,
    lado_a_lado,
    pagina_do_pdf_em_png,
    registar_imagem_olhada,
    retangulo_da_regiao,
    tiles_da_imagem,
)

PRINTS_A_GUARDAR = 50
MAX_TILES = 36
AMPLIACAO_MAXIMA = 8


def _consciencia_de_dpi():
    """Declara o processo consciente de DPI (Windows).

    Sem isto o Windows virtualiza o ecra: num monitor a 125% a captura sai
    esticada e desfocada. Uma segunda chamada devolve E_ACCESSDENIED, sem efeito.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


class _CaixaMonitor(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _monitores():
    """(esquerda, topo, direita, base) de cada monitor, da esquerda para a direita.

    A enumeracao depende da consciencia de DPI: antes dela o Windows devolve a area ja
    escalada (um 4K a 125% chega como 3072x1728) e o recorte do monitor sairia errado.
    """
    _consciencia_de_dpi()
    encontrados = []

    def _recolher(hmonitor, hdc, caixa, dados):
        retangulo = caixa.contents
        encontrados.append((retangulo.left, retangulo.top, retangulo.right, retangulo.bottom))
        return 1

    try:
        ctypes.windll.user32.EnumDisplayMonitors(
            0, 0,
            ctypes.WINFUNCTYPE(
                ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                ctypes.POINTER(_CaixaMonitor), ctypes.c_double,
            )(_recolher),
            0,
        )
    except Exception:
        return []
    return sorted(encontrados)


def _texto_monitores():
    """Mapa dos ecras: sem ele a captura de todos paga em faixas pretas o ecra pequeno."""
    monitores = _monitores()
    if len(monitores) < 2:
        return ""
    partes = []
    for indice, (esquerda, topo, direita, base) in enumerate(monitores, 1):
        marca = " (principal)" if (esquerda, topo) == (0, 0) else ""
        partes.append(f"{indice}: {direita - esquerda}x{base - topo} em ({esquerda},{topo}){marca}")
    return "Monitores, da esquerda para a direita: " + "; ".join(partes) + "."


def _capturar(regiao, ecra):
    """(imagem, nota) do pedido; (None, motivo) quando 'ecra' nao identifica um monitor.

    'nota' e o rotulo do monitor no sucesso, e o motivo da recusa quando a imagem e None.
    'ecra' aceita 'principal' (ou vazio), 'todos' e o numero de um monitor, pela ordem da
    lista: um valor desconhecido e RECUSADO - capturar outro ecra em silencio e pior do que falhar.
    """
    _consciencia_de_dpi()
    monitores = _monitores()
    escolha = str(ecra).strip().lower()
    if escolha in ("", "principal"):
        return ImageGrab.grab(bbox=retangulo_da_regiao(regiao), all_screens=bool(regiao)), ""
    if escolha == "todos":
        return ImageGrab.grab(bbox=retangulo_da_regiao(regiao), all_screens=True), ""
    if not (escolha.isdigit() and 1 <= int(escolha) <= len(monitores)):
        return None, (
            f"'{ecra}' nao e um ecra valido: use 'principal', 'todos' ou o numero de um monitor"
            f" ({_texto_monitores() or 'este PC tem um unico ecra'})"
        )
    numero = int(escolha)
    origem_x, origem_y = min(m[0] for m in monitores), min(m[1] for m in monitores)
    area = (
        max(m[2] for m in monitores) - origem_x,
        max(m[3] for m in monitores) - origem_y,
    )
    completa = ImageGrab.grab(all_screens=True)
    if completa.size != area:
        return None, (
            f"a area dos monitores ({area[0]}x{area[1]}) nao casa com a captura"
            f" ({completa.size[0]}x{completa.size[1]}): peca o retangulo em 'regiao'"
        )
    esquerda, topo, direita, base = monitores[numero - 1]
    recorte = (esquerda - origem_x, topo - origem_y, direita - origem_x, base - origem_y)
    return completa.crop(recorte), f" (monitor {numero})"


def _pasta_destino():
    return caminho_estado_projeto("prints") or os.path.join(tempfile.gettempdir(), "axio_prints")


def _guardar(bruto, pasta):
    """Grava o print sem nunca sobrepor o de outro print do mesmo segundo."""
    os.makedirs(pasta, exist_ok=True)
    base = "print_" + time.strftime("%Y%m%d_%H%M%S")
    caminho = os.path.join(pasta, base + ".png")
    sufixo = 2
    while os.path.exists(caminho):
        caminho = os.path.join(pasta, f"{base}_{sufixo}.png")
        sufixo += 1
    with open(caminho, "wb") as f:
        f.write(bruto)
    return caminho


def _limpar_prints_antigos(pasta, manter=PRINTS_A_GUARDAR):
    """Mantem apenas os ultimos prints: a pasta nao pode crescer sem fim."""
    try:
        entradas = [
            os.path.join(pasta, nome)
            for nome in os.listdir(pasta)
            if nome.startswith("print_") and nome.endswith(".png")
        ]
    except OSError:
        return
    if len(entradas) <= manter:
        return
    entradas.sort(key=lambda c: os.path.getmtime(c), reverse=True)
    for antigo in entradas[manter:]:
        try:
            os.remove(antigo)
        except OSError:
            pass


def _caminho_legivel(caminho):
    raiz = estado.get("pasta_raiz")
    if raiz:
        try:
            return os.path.relpath(caminho, raiz)
        except ValueError:
            pass
    return caminho


def _resumo_entrega(original, entregue):
    """O que vai para o modelo, dito em tamanho: a reducao nao pode ser invisivel.

    O numero que importa e o que SAI daqui - e esse que o modelo ve, porque a API
    reduziria qualquer imagem ao mesmo teto de ~800x800 equivalentes.
    """
    if not entregue:
        return ""
    largura, altura = original
    largura_envio, altura_envio = entregue
    if (largura_envio, altura_envio) == (largura, altura):
        return f"Vai para o modelo em tamanho original ({largura}x{altura} px)."
    return (
        f"Vai para o modelo com {largura_envio}x{altura_envio} px (a captura tem {largura}x{altura}):"
        " a API reduz toda a imagem a ~800x800 equivalentes, por isso nada se perdeu no pedido - o"
        " detalhe que falta e o que ela propria descartaria. Para ler texto fino, capture um"
        " retangulo estreito ou use detalhe='tiles'."
    )


def _imagens_em_pedacos(imagem, relativo, caixas):
    """Imagens do print partido em pedacos que chegam em tamanho original (uma por caixa)."""
    total = len(caixas)
    imagens = []
    for indice, caixa in enumerate(caixas, 1):
        bruto, mime = codificar_pedaco(imagem.crop(caixa), "image/png")
        imagens.append({
            "base64": base64.b64encode(bruto).decode("ascii"),
            "mime": mime,
            "rotulo": f"[Print do ecra: {relativo} - pedaco {indice}/{total}]",
        })
    return imagens


@register(
    "tool_capturar_print",
    "Tira um print do ecra e entrega-o a VOCE como imagem, para olhar para o que esta "
    "desenhado (a interface do Axio, uma janela, um erro visual, uma pagina). A imagem "
    "chega no pedido seguinte, como se o utilizador a tivesse enviado. Captura apenas o "
    "que estiver VISIVEL: se a janela que interessa estiver tapada ou minimizada, o print "
    "nao a mostra - diga isso ao utilizador em vez de concluir a partir do que faltou. "
    "TETO POR IMAGEM: a API reduz toda a imagem a ~800x800 pixels equivalentes (384 tokens), "
    "logo um ecra inteiro chega esbatido e texto pequeno desaparece, por muito que se aumente "
    "a captura. Para ler bem ha dois caminhos: (a) capture um RETANGULO ESTREITO em volta do "
    "que quer ler - abaixo de ~640 000 px (ex: 1200x520) chega em tamanho original; (b) passe "
    "detalhe='tiles' para partir a captura em pedacos, cada um dentro do teto e por isso em "
    "tamanho original - e o unico caminho para ler um ecra inteiro de uma vez, ao custo de "
    "384 tokens por pedaco. O retorno declara sempre o tamanho que chegou ao modelo e, havendo "
    "mais do que um monitor, o mapa dos ecras (numero, tamanho e posicao): use esse numero em "
    "'ecra' para capturar so o que interessa. PARA OLHAR PARA UMA JANELA ESPECIFICA use a outra "
    "ferramenta: 'tool_operar_janela' com acao='print' e 'janela' por um trecho do titulo (ex: "
    "'Axio Coder') - ela le a janela pela composicao do sistema, logo funciona mesmo com a janela "
    "tapada, e o 'regiao' dela e relativo a janela (0,0 = canto superior esquerdo dela).",
    {
        "regiao": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Retangulo a capturar, 'x,y,largura,altura' em pixeis, nas coordenadas da area total dos monitores (podem ser negativas, quando ha um ecra a esquerda do principal). Vazio captura o ecra inteiro. Quanto menor a regiao, mais nitida ela chega ao modelo: abaixo de ~640 000 px chega em tamanho original - use uma tira estreita para ler texto fino.",
        },
        "ecra": {
            "tipo": "STRING", "obrig": False, "padrao": "principal",
            "desc": "'principal' captura o monitor principal; 'todos' captura a area dos monitores juntos; o NUMERO de um monitor (1, 2...) captura so esse, na ordem que o retorno da captura lista. Escolha o monitor que interessa: num ecra pequeno as faixas em volta vem pretas e pagam-se em pedacos vazios.",
        },
        "detalhe": {
            "tipo": "STRING", "obrig": False, "padrao": "unico",
            "enum": ["unico", "tiles"],
            "desc": "'unico' entrega uma imagem (barato). 'tiles' parte a captura em pedacos que chegam em tamanho original - use para ler um ecra inteiro, ao custo de 384 tokens por pedaco.",
        },
    },
)
def tool_capturar_print(regiao="", ecra="principal", detalhe="unico"):
    emit_event("executing", function="Capturando o ecrã")
    try:
        _consciencia_de_dpi()
        imagem, nota = _capturar(regiao, ecra)
    except Exception as e:
        return f"ERRO: nao foi possivel capturar o ecra ({e})."
    if imagem is None:
        return f"ERRO: {nota}."

    largura, altura = imagem.size
    if not largura or not altura:
        return (
            "ERRO: o ecra foi lido mas a captura saiu VAZIA (0x0 px) - nao ha imagem nenhuma"
            " para mostrar nem para guardar."
            + (f" A regiao {regiao!r} cai toda fora do ecra: confira as coordenadas"
               " (x,y,largura,altura, em pixeis, a partir do canto superior esquerdo) ou"
               " capture sem 'regiao'." if str(regiao).strip() else
               " Confirme que a area de trabalho esta desbloqueada antes de capturar.")
        )

    buffer = io.BytesIO()
    try:
        imagem.save(buffer, format="PNG")
    except (ValueError, OSError) as e:
        return f"ERRO: a captura veio com {largura}x{altura} px e nao a consegui codificar ({e})."
    bruto = buffer.getvalue()

    pasta = _pasta_destino()
    try:
        caminho = _guardar(bruto, pasta)
    except OSError as e:
        return f"ERRO: o ecra foi capturado mas nao foi possivel guardar o print ({e})."
    _limpar_prints_antigos(pasta)

    relativo = _caminho_legivel(caminho)
    mapa = _texto_monitores()
    sufixo_mapa = f" {mapa}" if mapa else ""
    if str(detalhe).lower() == "tiles":
        caixas = tiles_da_imagem(largura, altura)
        if len(caixas) > MAX_TILES:
            return (
                f"ERRO: esta captura daria {len(caixas)} pedacos (maximo {MAX_TILES}). "
                "Reduza a regiao ou capture um monitor em vez de todos."
            )
        imagens = _imagens_em_pedacos(imagem, relativo, caixas)
        largura_pedaco = caixas[0][2] - caixas[0][0]
        altura_pedaco = caixas[0][3] - caixas[0][1]
        return {
            "texto": (
                f"Print do ecra capturado{nota}: {largura}x{altura} px, guardado em {relativo}. "
                f"Entregue em {len(imagens)} pedacos de ate {largura_pedaco}x{altura_pedaco} px,"
                " cada um em tamanho original (um unico pedaco chegaria esbatido)."
                f" Custa cerca de {len(imagens) * TOKENS_POR_IMAGEM} tokens de imagem."
                " As imagens seguem com esta resposta - olhe para TODAS antes de concluir."
                f"{sufixo_mapa}"
            ),
            "imagens": imagens,
        }

    base64_img, mime, entregue = codificar_para_envio(bruto)
    return {
        "texto": (
            f"Print do ecra capturado{nota}: {largura}x{altura} px, guardado em {relativo}. "
            f"{_resumo_entrega((largura, altura), entregue)} "
            "A imagem segue com esta resposta - olhe para ela antes de concluir."
            f"{sufixo_mapa}"
        ),
        "imagem": {"base64": base64_img, "mime": mime, "rotulo": f"[Print do ecra: {relativo}]"},
    }


@register(
    "tool_ver_imagem",
    "Entrega a VOCE como imagem um ficheiro do projeto, seja ele uma imagem (png, jpg, gif, webp, "
    "bmp, ico), uma PAGINA de um PDF ('pagina') ou um MODELO 3D (.ifc, ou malha stl/obj/ply/glb) "
    "desenhado dos angulos que pedir em 'vista'. Use-a para olhar para um icone, um esquema, uma "
    "prancha ou um desenho de referencia, e para CONFERIR com os olhos o modelo que acabou de gerar: "
    "a medicao prova que a geometria saiu como pediu, so o olho prova que era a geometria certa. "
    "Num modelo 3D, 'focar' isola as pecas cujo nome ou classe contenham um texto (ex: 'estrela').",
    {
        "caminho_relativo": {"tipo": "STRING", "obrig": True, "padrao": ""},
        "pagina": {"tipo": "INTEGER", "desc": "Pagina do PDF a mostrar (1 = a primeira).", "padrao": 1},
        "vista": {
            "tipo": "STRING",
            "desc": "Angulo de um modelo 3D: frente, lado, costas, 3q, topo, ou 'azimute,elevacao'. Varios separados por ';' (ex: 'frente;3q'), ate 4 - cada um custa uma imagem.",
            "padrao": "3q",
        },
        "focar": {
            "tipo": "STRING",
            "desc": "Isola, num modelo 3D, as pecas cujo nome ou classe contenham este texto (ex: 'estrela', 'IfcPlate').",
            "padrao": "",
        },
        "cima": {
            "tipo": "STRING",
            "desc": "Para modelos 3D: qual o eixo que aponta para CIMA no ficheiro - 'y' ou 'z'. O desenhador e Z-para-cima (IFC, CAD) e o three.js/glTF e Y-para-cima: sem isto um busto .glb sai DEITADO e o julgamento sai ao contrario do verdadeiro. Vazio decide pela extensao (.glb/.gltf -> y) e a legenda diz sempre qual foi usada - se o desenho aparecer deitado, repita com o outro valor.",
            "padrao": "",
        },
        "comparar_com": {
            "tipo": "STRING",
            "desc": "Caminho de uma imagem de referencia (foto, render, prancha). Cada vista sai LADO A LADO com ela, a referencia a esquerda - e a forma de julgar semelhanca sem alternar entre duas imagens. Use sempre que estiver a modelar a partir de uma referencia visual.",
            "padrao": "",
        },
        "regiao": {
            "tipo": "STRING",
            "desc": "Olha so para um recorte: 'x,y,largura,altura' em pixels da imagem (ex: '590,330,220,80'). E o caminho para LER letra pequena: a imagem inteira chega ao modelo dentro de um teto de ~800x800 px equivalentes e um texto de 8 px de altura desaparece la dentro, enquanto o mesmo texto recortado e ampliado fica legivel. Vale para imagem e para pagina de PDF; num modelo 3D e ignorado.",
            "padrao": "",
        },
        "ampliar": {
            "tipo": "INTEGER",
            "desc": "Quantas vezes ampliar o recorte (1 a 8). A ampliacao nao inventa detalhe nenhum: torna grande o que ja la esta.",
            "padrao": 1,
        },
    },
)
def tool_ver_imagem(caminho_relativo, pagina=1, vista="3q", focar="", comparar_com="", cima="",
                    regiao="", ampliar=1):
    emit_event("executing", function=f"Abrindo: {caminho_relativo}")
    alvo, erro = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro:
        return erro
    if not os.path.isfile(alvo):
        return f"ERRO: ficheiro nao encontrado: {caminho_relativo}"
    extensao = os.path.splitext(alvo)[1].lower()
    try:
        desenhos = _desenhos_do_ficheiro(alvo, extensao, pagina, vista, focar, cima)
    except ValueError as falha:
        return f"ERRO: {falha}"
    except Exception as falha:
        return f"ERRO: nao foi possivel ler '{caminho_relativo}' ({falha})."

    if extensao not in EXTENSOES_MODELO and (regiao or int(ampliar or 1) > 1):
        try:
            desenhos = [
                (_recorte_ampliado(bruto, regiao, ampliar),
                 f"{legenda} (recorte ampliado {max(1, min(AMPLIACAO_MAXIMA, int(ampliar or 1)))}x)")
                for bruto, legenda in desenhos
            ]
        except ValueError as falha:
            return f"ERRO: {falha}"

    juntas = ""
    if comparar_com:
        referencia, erro_ref = resolver_caminho(comparar_com, permitir_extra=True)
        if erro_ref:
            return erro_ref
        if not os.path.isfile(referencia):
            return f"ERRO: referencia nao encontrada: {comparar_com}"
        with open(referencia, "rb") as ficheiro:
            bytes_referencia = ficheiro.read()
        desenhos = [
            (lado_a_lado(bytes_referencia, bruto), f"{legenda} ao lado de {comparar_com}")
            for bruto, legenda in desenhos
        ]
        juntas = f" Cada vista saiu lado a lado com '{comparar_com}' (a esquerda)."

    registar_imagem_olhada(alvo)

    imagens = []
    partes = []
    for bruto, legenda in desenhos:
        base64_img, mime, entregue = codificar_para_envio(bruto)
        imagens.append({
            "base64": base64_img,
            "mime": mime,
            "rotulo": f"[{caminho_relativo}{legenda}]",
        })
        tamanho = dimensoes_da_imagem(bruto)
        partes.append(f"{legenda or 'imagem'}: {_resumo_entrega(tamanho, entregue) if tamanho else ''}")

    resultado = {
        "texto": (
            f"'{caminho_relativo}' entregue a voce em {len(imagens)} imagem(ns). "
            + " ".join(partes)
            + juntas
            + " Olhe para TODAS antes de concluir."
        )
    }
    if len(imagens) == 1:
        resultado["imagem"] = imagens[0]
    else:
        resultado["imagens"] = imagens
    return resultado


@register(
    "tool_preparar_captura",
    "Prepara uma captura de ecra para publicar (README, documentacao, repositorio): diz ONDE esta o "
    "conteudo da imagem e grava a versao final, recortada e reduzida. Sem 'destino' so mede - e esse "
    "o primeiro passo, porque o mapa de atividade mostra o que esta aceso e o que e espaco vazio, em "
    "vez de se recortar as cegas. Com 'destino' recorta por 'caixa' e grava. So ESCREVE dentro do "
    "projeto: a origem pode estar fora (ex: a pasta institucional), o destino nao.",
    {
        "origem": {
            "tipo": "STRING",
            "obrig": True,
            "padrao": "",
            "desc": "Imagem de partida (png, jpg), no projeto ou fora dele.",
        },
        "destino": {
            "tipo": "STRING",
            "desc": "Caminho de destino DENTRO do projeto (ex: docs/interface/preview.jpg). Vazio = so medir, nao grava nada.",
            "padrao": "",
        },
        "caixa": {
            "tipo": "STRING",
            "desc": "Recorte 'x,y,largura,altura' em pixels da ORIGEM (ex: '900,0,2931,1000'). Vazio = a imagem inteira. Com 'caixa', a ferramenta mede tambem a faixa do recorte: os blocos de conteudo por eixo, se a linha de corte passa a meio de um deles e a que distancia esta o conteudo seguinte.",
            "padrao": "",
        },
        "largura": {
            "tipo": "INTEGER",
            "desc": "Largura maxima do ficheiro gravado: so reduz, nunca aumenta.",
            "padrao": 1920,
        },
        "qualidade": {
            "tipo": "INTEGER",
            "desc": "Qualidade do JPEG (1-95); ignorada quando o destino e .png.",
            "padrao": 86,
        },
    },
)
def tool_preparar_captura(origem, destino="", caixa="", largura=1920, qualidade=86):
    emit_event("executing", function=f"Preparando captura: {origem}")
    caminho_origem, erro = resolver_caminho(origem, permitir_extra=True)
    if erro:
        return erro
    if not os.path.isfile(caminho_origem):
        return f"ERRO: ficheiro nao encontrado: {origem}"
    with open(caminho_origem, "rb") as ficheiro:
        bruto = ficheiro.read()
    try:
        mapa = mapa_de_atividade(bruto)
    except Exception as falha:
        return f"ERRO: nao foi possivel ler '{origem}' ({falha})."
    partes = [
        f"Mapa de atividade de '{origem}': grelha de {mapa['celula']} px, "
        f"{mapa['colunas']} colunas x {mapa['linhas']} linhas, do liso ao aceso.",
        mapa["texto"],
        "Legenda: ' ' e zona lisa (fundo vazio), '@' e a zona com mais conteudo.",
    ]
    recorte = retangulo_da_regiao(caixa) if caixa else None
    if caixa and not recorte:
        return "ERRO: 'caixa' tem de ser 'x,y,largura,altura' em pixels (ex: '0,0,2200,520')."
    if recorte:
        try:
            partes.append(_texto_do_conteudo(fins_do_conteudo(bruto, recorte)))
        except Exception as falha:
            partes.append(f"AVISO: nao foi possivel medir o conteudo do recorte ({falha}).")
    if not destino:
        return "\n".join(partes + ["Nada foi gravado: sem 'destino', a ferramenta so mede."])
    caminho_destino, erro_destino = resolver_caminho(destino, permitir_extra=False,
                                                     permitir_escrita=True)
    if erro_destino:
        return erro_destino
    try:
        resultado = preparar_captura(caminho_origem, caminho_destino, recorte, largura, qualidade)
    except ValueError as fora:
        return f"ERRO: {fora}."
    except Exception as falha:
        return f"ERRO: nao foi possivel gravar '{destino}' ({falha})."
    largura_origem, altura_origem = resultado["original"]
    largura_final, altura_final = resultado["final"]
    resumo = (f"Gravado em {_caminho_legivel(caminho_destino)}: "
              f"{largura_origem}x{altura_origem} px -> {largura_final}x{altura_final} px, "
              f"{resultado['bytes'] // 1024} KB.")
    if recorte:
        largura_recorte, altura_recorte = resultado["recortada"]
        resumo += (f" Recorte ({recorte[0]},{recorte[1]})-({recorte[2]},{recorte[3]}) da origem:"
                   f" ficou com {largura_recorte}x{altura_recorte} px antes da reducao.")
    else:
        resumo += " Sem recorte: a imagem inteira."
    largura_antes_da_reducao = resultado["recortada"][0] if recorte else largura_origem
    if largura_final == largura_antes_da_reducao:
        resumo += " A largura pedida nao era menor: ficou no tamanho que tinha."
    return "\n".join(partes + ["", resumo])


def _texto_do_conteudo(medida):
    faixa = medida["faixa"]
    linhas = medida["linhas"]
    colunas = medida["colunas"]
    if not linhas or not colunas:
        return (f"Faixa ({faixa[0]},{faixa[1]})-({faixa[2]},{faixa[3]}): uniforme, "
                f"sem conteudo a localizar.")
    partes = [
        f"Conteudo na faixa do recorte ({faixa[0]},{faixa[1]})-({faixa[2]},{faixa[3]}):",
        f"  na vertical (colunas {faixa[0]}-{faixa[2]}): {_descricao_dos_blocos(linhas)}",
        f"  na horizontal (linhas {faixa[1]}-{faixa[3]}): {_descricao_dos_blocos(colunas)}",
    ]
    corta_base = _bloco_com(linhas, faixa[3] - 1)
    corta_direita = _bloco_com(colunas, faixa[2] - 1)
    if corta_base:
        partes.append(f"A base do recorte (linha {faixa[3] - 1}) cai dentro do bloco "
                      f"{corta_base[0]}-{corta_base[1]}: o corte passa a meio. Estende a base "
                      f"ate {corta_base[1] + 1} ou corta em {corta_base[0]}.")
    if corta_direita:
        partes.append(f"A direita do recorte (coluna {faixa[2] - 1}) cai dentro do bloco "
                      f"{corta_direita[0]}-{corta_direita[1]}: o corte passa a meio.")
    proximo_abaixo = _bloco_depois(linhas, faixa[3] - 1)
    if proximo_abaixo:
        partes.append(f"A base e a linha {faixa[3] - 1}: o conteudo mais proximo por baixo "
                      f"comeca na linha {proximo_abaixo[0]}, "
                      f"{proximo_abaixo[0] - faixa[3] + 1} px depois "
                      f"(vai ate {proximo_abaixo[1]}).")
    proximo_a_direita = _bloco_depois(colunas, faixa[2] - 1)
    if proximo_a_direita:
        partes.append(f"A direita e a coluna {faixa[2] - 1}: o conteudo mais proximo comeca na "
                      f"coluna {proximo_a_direita[0]}, "
                      f"{proximo_a_direita[0] - faixa[2] + 1} px depois "
                      f"(vai ate {proximo_a_direita[1]}).")
    return "\n".join(partes)


def _descricao_dos_blocos(blocos):
    return "; ".join(f"{inicio}-{fim}" for inicio, fim in blocos)


def _bloco_com(blocos, ponto):
    for bloco in blocos:
        if bloco[0] <= ponto <= bloco[1]:
            return bloco
    return None


def _bloco_depois(blocos, ponto):
    for bloco in blocos:
        if bloco[0] > ponto:
            return bloco
    return None


def _recorte_ampliado(bruto, regiao, ampliar):
    """Bytes do recorte pedido, ampliado - a via para ler letra pequena na imagem inteira."""
    fator = max(1, min(AMPLIACAO_MAXIMA, int(ampliar or 1)))
    with Image.open(io.BytesIO(bruto)) as imagem:
        imagem.load()
        caixa = retangulo_da_regiao(regiao) if regiao else (0, 0, imagem.width, imagem.height)
        if not caixa:
            raise ValueError("'regiao' tem de ser 'x,y,largura,altura' em pixels (ex: '590,330,220,80').")
        if caixa[0] < 0 or caixa[1] < 0 or caixa[2] > imagem.width or caixa[3] > imagem.height:
            raise ValueError(f"a regiao {caixa} sai fora da imagem, que tem {imagem.width}x{imagem.height} px.")
        recorte = imagem.crop(caixa).convert("RGB")
        if fator > 1:
            recorte = recorte.resize((recorte.width * fator, recorte.height * fator),
                                     Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        recorte.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()


def _desenhos_do_ficheiro(alvo, extensao, pagina, vista, focar, cima=""):
    if extensao == ".pdf":
        return [pagina_do_pdf_em_png(alvo, pagina, DPI_PDF)]
    if extensao in EXTENSOES_MODELO:
        return _vistas_do_modelo(alvo, vista, focar, cima)
    with open(alvo, "rb") as ficheiro:
        return [(ficheiro.read(), "")]



def _vistas_do_modelo(alvo, vista, focar, cima=""):
    triangulos, rodape = desenho_do_ficheiro(alvo, focar or None, cima or None)
    desenhos = []
    for nome, azimute, elevacao in vistas_do_pedido(vista):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as ficheiro:
            saida = ficheiro.name
        try:
            resultado = desenhar(triangulos, saida, azimute=azimute, elevacao=elevacao)
            with open(saida, "rb") as ficheiro:
                bruto = ficheiro.read()
        finally:
            try:
                os.remove(saida)
            except OSError:
                pass
        filtro = f", filtro '{focar}'" if focar else ""
        escondidas = resultado.get("escondidas") or []
        oclusao = (
            f"; {len(resultado['pecas'])} pecas, nenhuma escondida"
            if not escondidas
            else f"; {len(escondidas)} peca(s) 100% escondida(s) nesta vista: {', '.join(escondidas[:6])}"
        )
        tapadas = resultado.get("tapadas") or []
        if tapadas:
            oclusao += "; mais tapadas: " + ", ".join(
                f"{nome} {visivel:.0%} a vista" for nome, visivel in tapadas[:4]
            )
        legenda = (
            f" (vista {nome}: azimute {azimute:g}, elevacao {elevacao:g};"
            f" {resultado['triangulos_pintados']} de {resultado['triangulos_lidos']} triangulos{filtro}{oclusao}{rodape})"
        )
        desenhos.append((bruto, legenda))
    return desenhos
