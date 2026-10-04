"""Janelas nativas do Windows: ver e operar qualquer app por UI Automation."""

import ctypes
import io
import json
import os
import re
import struct
import subprocess
import time
import unicodedata

from ctypes import wintypes
from PIL import Image, ImageDraw, ImageGrab

from src.backend.services import cofre, executaveis
from src.backend.services.imagem import codificar_para_envio, retangulo_da_regiao
from src.backend.services.process_manager import tokenizar_linha
from src.backend.state import emit_event
from src.backend.tools.registry import register

TIPOS_INTERATIVOS = frozenset({
    "Button", "CheckBox", "ComboBox", "Document", "Edit", "Hyperlink", "ListItem", "MenuItem",
    "RadioButton", "Slider", "Spinner", "SplitButton", "TabItem", "TreeItem", "DataItem",
})
TIPOS_SEM_NOME = frozenset({"Edit", "Document"})
PADROES = ("invoke", "toggle", "selection_item", "expand_collapse", "value", "scroll", "text", "range_value")
LIMITE_MAPA = 300
LIMITE_VARREDURA = 6000
ARVORE_POBRE = 40
LIMITE_TRACO = 64
PAUSA_TRACO = 0.02
LIMITE_PASSOS_ROTEIRO = 40
ESPERA_MAX_PASSO = 30000
ESPERA_JANELA_PADRAO = 15.0
CARACTERES_DE_TECLA = "+^%~(){}"
ACOES_NO_ROTEIRO = frozenset({
    "mapa", "elemento", "clicar", "escrever", "teclas", "arrastar", "fechar", "print", "mover", "esperar",
})
VALIDADE_DO_CENSO = 1.0
SEM_PROGRAMA = (
    "nao encontrei '{0}'. Use o nome do executavel (ex: 'notepad', 'mspaint') ou o caminho"
    " completo do ficheiro (ex: C:\\Program Files\\App\\app.exe) - com espacos, sem aspas."
)
SEM_BIBLIOTECA = (
    "o pywinauto nao esta instalado no ambiente que corre o Axio. Instale-o no venv do projeto"
    " (\"python -m pip install pywinauto\") e reinicie o backend"
)
SEM_JANELA = (
    "nao encontrei essa janela. Use acao='janelas' para ver o que esta aberto: 'janela' aceita"
    " o numero do hwnd, 'pid:<numero>' (para escolher pelo processo) ou um trecho do titulo"
    " (ex: 'Bloco de notas')"
)
ORCAMENTO_MAPA = 10.0
PAUSA_ESTAVEL = 1.5
ESPERA_JANELA = 30.0
ESPERA_DELEGADA = 6.0
LIMITE_SUPERFICIES = 4
ESPERA_FECHO = 6.0
LIMITE_LEITURAS_DE_AVISO = 3
ORCAMENTO_AVISO = 3.0
PAUSA_ATE_O_AVISO = 0.7
PAUSA_DEPOIS_DO_AVISO = 0.7
RESPOSTAS_DE_AVISO = (
    (("nao", "salvar"), ("dont", "save"), ("no", "save"), ("nicht", "speichern")),
    (("nao",), ("no",), ("nein",)),
    (("cancelar",), ("cancel",), ("abbrechen",), ("annuler",)),
    (("ok",), ("aceitar",), ("sim",), ("yes",)),
)


_MODULO = None
_RATO = None
_TECLADO = None


_CLIPBOARD = None


def _area_de_transferencia():
    """Os modulos da area de transferencia, com o import adiado (pywin32)."""
    global _CLIPBOARD
    if _CLIPBOARD is None:
        import win32clipboard
        import win32con

        _CLIPBOARD = (win32clipboard, win32con)
    return _CLIPBOARD


def _desktop():
    """Desktop UIA do pywinauto, com o import adiado: carrega-lo custa o comtypes e inicia MTA."""
    global _MODULO
    if _MODULO is None:
        from pywinauto import Desktop
        _MODULO = Desktop
    return _MODULO(backend="uia")


def _mouse():
    """Modulo de rato do pywinauto, com o mesmo import adiado do _desktop."""
    global _RATO
    if _RATO is None:
        from pywinauto import mouse
        _RATO = mouse
    return _RATO


def _teclado():
    """Modulo de teclado do pywinauto, com o mesmo import adiado do _mouse."""
    global _TECLADO
    if _TECLADO is None:
        from pywinauto import keyboard
        _TECLADO = keyboard
    return _TECLADO


def _texto(elemento):
    try:
        return (elemento.window_text() or "").strip()
    except Exception:
        return ""


def _auto_id(elemento):
    try:
        return (elemento.automation_id() or "").strip()
    except Exception:
        return ""


def _tipo(elemento):
    try:
        return str(elemento.element_info.control_type)
    except Exception:
        return "?"


def _caixa(elemento):
    try:
        retangulo = elemento.rectangle()
        return f"({retangulo.left},{retangulo.top} {retangulo.width()}x{retangulo.height()})"
    except Exception:
        return "(sem caixa)"


def _chave(elemento):
    """Identidade estavel entre duas leituras da mesma janela: tipo, nome, automacao e caixa."""
    return (_tipo(elemento), _texto(elemento), _auto_id(elemento), _caixa(elemento))


def _prazo_esgotado(prazo):
    return prazo is not None and time.monotonic() >= prazo


def _visivel(elemento):
    try:
        return elemento.is_visible()
    except Exception:
        return True


def _interface(elemento, nome):
    """Padrao UIA do elemento, ou None: os iface_* do pywinauto LEVANTAM quando nao existem."""
    try:
        return getattr(elemento, "iface_" + nome, None)
    except Exception:
        return None


def _padroes(elemento):
    return [nome for nome in PADROES if _interface(elemento, nome) is not None]


def _valor(elemento):
    """Texto atual do campo pelo padrao de valor; vazio quando o elemento nao o tem."""
    interface = _interface(elemento, "value")
    if interface is None:
        return ""
    try:
        return interface.CurrentValue or ""
    except Exception:
        return ""


SUFIXO_DE_INDICE = re.compile(r"#(\d+)\s*$")


def _separar_indice(pedido):
    """('titulo', n): 'jogo#2' pede a 2a janela que casa com esse titulo."""
    achado = SUFIXO_DE_INDICE.search(pedido)
    if not achado:
        return pedido, 1
    return pedido[:achado.start()].strip(), int(achado.group(1))


def _por_posicao(janelas):
    """Da esquerda para a direita - a ordem com que o olho as distingue, com as minimizadas no fim.

    Uma janela minimizada vive em x=-32000: ordenada so pela posicao ela seria a '#1', e o gesto
    cairia justamente na unica que nao da para operar. Medido a 2026-10-02, com quatro blocos de
    notas abertos: das quatro, a '#1' era a minimizada.
    """
    def chave(janela):
        try:
            minimizada = bool(ctypes.windll.user32.IsIconic(int(getattr(janela, "handle", 0) or 0)))
        except Exception:
            minimizada = False
        try:
            caixa = janela.rectangle()
            canto = (int(caixa.left), int(caixa.top))
        except Exception:
            canto = (1 << 30, 1 << 30)
        return (1 if minimizada else 0, canto[0], canto[1])
    return sorted(janelas, key=chave)


def _colado(texto):
    return "".join(letra for letra in texto.lower() if letra.isalnum())


def _janela(identificador, fresco=False):
    """(janela, erro): escolhida pelo hwnd, pelo processo ou por um trecho do titulo.

    Com varias janelas do MESMO titulo - tres clientes de um jogo, tres exploradores abertos -
    agir na primeira seria um palpite, e o palpite errado custa caro (o gesto cai na janela que
    nao era). O sufixo '#N' escolhe a N-esima contando da ESQUERDA para a direita, que e a ordem
    que o olho usa; sem ele, a ambiguidade RECUSA e lista as candidatas com o hwnd.
    """
    try:
        abertas = _janelas_abertas(fresco)
    except Exception as exc:
        return None, f"nao consegui enumerar as janelas do Windows ({type(exc).__name__}: {exc})"
    pedido = str(identificador or "").strip()
    if not pedido:
        return None, SEM_JANELA
    if pedido.isdigit():
        for janela in abertas:
            if str(janela.handle) == pedido:
                return janela, ""
        return _procurar_no_win32(pedido)
    if pedido.lower().startswith("pid:"):
        numero = pedido[4:].strip()
        if not numero.isdigit():
            return None, "o pid tem de ser um numero (ex: 'pid:12345')."
        do_pid = _por_posicao(
            [w for w in abertas if getattr(w.element_info, "process_id", None) == int(numero)]
        )
        return (do_pid[0], "") if do_pid else _procurar_no_win32(pedido)
    titulo, indice = _separar_indice(pedido)
    procurado = titulo.lower()
    exatas = [w for w in abertas if _texto(w).lower() == procurado]
    contem = [w for w in abertas if procurado in _texto(w).lower()]
    if not contem:
        colado = _colado(procurado)
        contem = [w for w in abertas if colado and colado in _colado(_texto(w))]
    casadas = _por_posicao(exatas or contem)
    if not casadas:
        return _procurar_no_win32(pedido)
    if indice > len(casadas):
        return None, (
            f"pedi a janela #{indice} de \"{titulo}\" mas so {len(casadas)} casam"
            f" ({', '.join(str(w.handle) for w in casadas[:4])})."
        )
    if len(casadas) > 1 and indice == 1 and not SUFIXO_DE_INDICE.search(pedido):
        return None, (
            f"{len(casadas)} janelas casam com \"{titulo}\" e nenhuma foi escolhida"
            " (agir na errada e pior do que parar):\n"
            + "\n".join(
                f"    'janela': '{titulo}#{pos}' ou '{w.handle}' -> {_texto(w)[:60]}"
                for pos, w in enumerate(casadas[:6], 1)
            )
            + f"\n  A ordem e da ESQUERDA para a direita no ecra."
        )
    return casadas[indice - 1], ""


def _caminho_do_programa(nome):
    """(caminho, erro): resolve pelo caminho escrito, pelo PATH, pelos locais conhecidos ou pelo registo."""
    pedido = str(nome or "").strip().strip('"')
    if not pedido:
        return "", "diga o programa em 'alvo', ex: 'notepad' ou o caminho completo."
    achado = executaveis.achar(pedido)
    if achado:
        return achado, ""
    return "", SEM_PROGRAMA.format(pedido)


def _repartir_alvo(alvo):
    """(caminho, argumentos, erro): aceita o caminho com espacos, com ou sem aspas.

    MEDIDO (2026-10-18): escrito sem aspas, 'C:\\Program Files\\App\\app.exe' era partido em dois
    tokens e a resolucao ia procurar 'C:\\Program' - a ferramenta exigia aspas e falhava a primeira
    tentativa. Quem escreve o caminho num campo nao tem de saber dessa regra, por isso junta-se o
    prefixo mais longo que existe mesmo no disco e o resto fica como argumentos.
    """
    pedido = str(alvo or "").strip()
    if not pedido:
        return "", [], "diga o programa em 'alvo', ex: 'notepad' ou o caminho completo."
    inteiro, erro = _caminho_do_programa(pedido)
    if inteiro:
        return inteiro, [], ""
    tokens = tokenizar_linha(pedido)
    for corte in range(len(tokens) - 1, 0, -1):
        candidato, _ = _caminho_do_programa(" ".join(tokens[:corte]))
        if candidato:
            return candidato, tokens[corte:], ""
    return "", [], erro


def _area(janela):
    try:
        caixa = janela.rectangle()
        return max(0, caixa.width()) * max(0, caixa.height())
    except Exception:
        return 0


def _janelas_do_pid(pid):
    """Janelas com titulo do processo, da maior para a menor."""
    encontradas = []
    try:
        for janela in _desktop().windows():
            if _texto(janela) and getattr(janela.element_info, "process_id", None) == pid:
                encontradas.append(janela)
    except Exception:
        return []
    return sorted(encontradas, key=_area, reverse=True)


AREA_MINIMA_DE_JANELA = 1600
LIMITE_JANELAS_AVULSAS = 12


_CENSO = {"quando": 0.0, "janelas": []}
_TRAVA_DO_CENSO = {"activa": False}


def _travar_censo(activa):
    """Enquanto um roteiro corre, o censo nao expira.

    As janelas nao mudam de um gesto para o outro, e reler o sistema a cada passo custa 2,4s -
    medido: um roteiro de cinco gestos levava 14,6s, dos quais 12 eram so enumeracao de janelas.
    """
    _TRAVA_DO_CENSO["activa"] = bool(activa)


def _esquecer_censo():
    """O proximo censo volta a ler o sistema - chamado por tudo o que abre, move ou fecha janelas."""
    _CENSO["quando"] = 0.0
    _CENSO["janelas"] = []


def _janelas_abertas(fresco=False):
    """Todas as janelas que valem um gesto: as que tem titulo e as sem titulo com area util.

    Enumerar so pelo titulo escondia janelas reais: uma janela de ferramenta (a do raciocinio,
    por exemplo) nao aparece na barra de tarefas e pode nao se declarar. O filtro que sobra e
    de TAMANHO, porque a arvore do Windows esta cheia de janelas de 0x0 que ninguem quer operar.

    MEDIDO: esta leitura custa 2,4s, porque pergunta ao UIA por cada janela do sistema - contra
    0,01s da varredura pelo Win32 puro. Num roteiro de oito gestos eram oito vezes 2,4s, e era
    isso, e nao os cliques, que fazia uma tarefa de dois minutos arrastar-se por vinte. O censo
    fica guardado por instantes: quem ABRE, MOVE ou FECHA uma janela esquece-o; quem PERGUNTA o
    que esta aberto (acao='janelas' e 'esperar') pede-o fresco.
    """
    agora = time.monotonic()
    if (
        not fresco
        and _CENSO["janelas"]
        and (_TRAVA_DO_CENSO["activa"] or agora - _CENSO["quando"] < VALIDADE_DO_CENSO)
    ):
        return list(_CENSO["janelas"])
    abertas = []
    for tentativa in (1, 2):
        try:
            abertas = [
                janela for janela in _desktop().windows()
                if _texto(janela) or (_visivel(janela) and _area(janela) >= AREA_MINIMA_DE_JANELA)
            ]
            break
        except Exception:
            abertas = []
            if tentativa == 2:
                raise
            time.sleep(0.5)
    vistas = {int(getattr(janela, "handle", 0) or 0) for janela in abertas}
    abertas.extend(_janelas_avulsas(vistas)[0])
    _CENSO["quando"] = time.monotonic()
    _CENSO["janelas"] = list(abertas)
    return abertas


def _esperar_janela(processo, antes, segundos=ESPERA_JANELA):
    """(janela, como, erro): a maior janela do processo, depois de ela dar sinal de estar pronta.

    Devolver a PRIMEIRA janela do pid entrega a splash de arranque das apps pesadas (medido no
    GIMP: 'GIMP Startup', sem controlos nenhuns, em vez da janela principal). Os dois sinais que
    distinguem a janela pronta sao universais: ser a maior do processo e ter filhos proprios -
    uma janela sem nenhum filho ainda esta a carregar ou e um aviso transitório.
    """
    inicio = time.time()
    limite = inicio + segundos
    ultima = None
    assinatura = None
    estavel_desde = None
    while time.time() < limite:
        candidatas = []
        novas = []
        for janela in _desktop().windows():
            if not _texto(janela):
                continue
            if getattr(janela.element_info, "process_id", None) == processo.pid:
                candidatas.append(janela)
            elif janela.handle not in antes:
                novas.append(janela)
        decorrido = time.time() - inicio
        do_pid = bool(candidatas)
        grupo = candidatas or (novas if novas and decorrido >= ESPERA_DELEGADA else [])
        if grupo:
            maior = max(grupo, key=_area)
            try:
                pronta = bool(maior.children())
            except Exception:
                pronta = True
            marca = (maior.handle, _area(maior), pronta, do_pid)
            if marca != assinatura:
                assinatura = marca
                estavel_desde = time.time()
            if pronta and estavel_desde and time.time() - estavel_desde >= PAUSA_ESTAVEL:
                como = "pelo pid do processo" if do_pid else "por uma janela que nao existia antes"
                return maior, como, ""
            ultima = maior
        elif processo.poll() is not None and decorrido >= ESPERA_DELEGADA:
            return None, "", (
                f"o processo terminou logo apos o arranque (codigo {processo.returncode}) e nenhuma"
                " janela nova apareceu em 6s - se ele abriu noutro processo, use acao='janelas'"
            )
        time.sleep(0.4)
    if ultima is not None:
        return ultima, "pelo pid do processo (a janela nao deu sinal de estar pronta a tempo)", ""
    return None, "", (
        f"o processo {processo.pid} corre, mas nao apareceu janela nova com titulo em"
        f" {segundos:.0f}s. Se o programa ja estava aberto, use acao='janelas'"
    )


def _janelas_do_win32():
    """(handle, titulo, pid, area) de cada janela de topo, pelo proprio Win32.

    A enumeracao do pywinauto nao devolve certas janelas reais: as de ferramenta, sem entrada
    na barra de tarefas (a janela do raciocinio e uma delas) existem para o Win32 e respondem a
    gestos, mas nunca aparecem na lista. Esta varredura e o caminho para as alcancar.
    """
    user32 = ctypes.windll.user32
    registos = []

    def recolher(handle, _):
        comprimento = user32.GetWindowTextLengthW(handle)
        titulo = ctypes.create_unicode_buffer(comprimento + 1)
        user32.GetWindowTextW(handle, titulo, comprimento + 1)
        caixa = wintypes.RECT()
        user32.GetWindowRect(handle, ctypes.byref(caixa))
        processo = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(processo))
        registos.append({
            "handle": int(handle),
            "titulo": titulo.value,
            "pid": processo.value,
            "visivel": bool(user32.IsWindowVisible(handle)),
            "area": max(0, caixa.right - caixa.left) * max(0, caixa.bottom - caixa.top),
        })
        return True

    retorno = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(retorno(recolher), 0)
    return registos


def _janela_avulsa(handle):
    """Wrapper UIA de uma janela que a enumeracao normal nao devolve, ou None."""
    try:
        from pywinauto import Application
        return Application(backend="uia").connect(handle=handle).window(handle=handle).wrapper_object()
    except Exception:
        return None


def _procurar_no_win32(pedido):
    """(janela, erro): a janela procurada como o Win32 a ve, para o que a arvore nao devolve."""
    try:
        registos = _janelas_do_win32()
    except Exception:
        return None, SEM_JANELA
    if pedido.isdigit():
        candidatos = [r for r in registos if str(r["handle"]) == pedido]
    elif pedido.lower().startswith("pid:"):
        numero = pedido[4:].strip()
        candidatos = [r for r in registos if r["pid"] == int(numero)] if numero.isdigit() else []
    else:
        procurado = pedido.lower()
        candidatos = [r for r in registos if r["titulo"] and procurado in r["titulo"].lower()]
    candidatos = [r for r in candidatos if r["titulo"] or r["area"] >= AREA_MINIMA_DE_JANELA]
    candidatos.sort(key=lambda r: r["area"], reverse=True)
    for registo in candidatos:
        janela = _janela_avulsa(registo["handle"])
        if janela is not None:
            return janela, ""
    return None, SEM_JANELA


def _janelas_avulsas(vistas):
    """(janelas, restantes): as que existem no Win32 e a enumeracao normal nao devolveu."""
    try:
        registos = _janelas_do_win32()
    except Exception:
        return [], 0
    candidatos = [
        r for r in registos
        if r["handle"] not in vistas and r["visivel"] and r["area"] >= AREA_MINIMA_DE_JANELA
    ]
    candidatos.sort(key=lambda r: r["area"], reverse=True)
    janelas = []
    for registo in candidatos[:LIMITE_JANELAS_AVULSAS]:
        janela = _janela_avulsa(registo["handle"])
        if janela is not None:
            janelas.append(janela)
    return janelas, max(0, len(candidatos) - LIMITE_JANELAS_AVULSAS)


def _focar(janela):
    """Traz a janela para a frente e CONFIRMA que ficou: o set_focus do pywinauto pode nao pegar (o Windows recusa o pedido de foco a quem nao o tem), e nesse caso o clique ia para a janela que esta em foco.

    Aceita o objeto da janela ou so o handle: quem chama com um numero (o print, que ja tem a janela resolvida) nao pode ficar sem foco em silencio.
    """
    so_handle = isinstance(janela, int)
    hwnd = janela if so_handle else getattr(janela, "handle", None)
    if not so_handle:
        try:
            janela.set_focus()
            time.sleep(0.3)
        except Exception:
            pass
    if hwnd and _a_frente(hwnd):
        return ""
    if hwnd:
        try:
            utilizador32 = ctypes.windll.user32
            utilizador32.ShowWindow(hwnd, 9)
            utilizador32.SetForegroundWindow(hwnd)
            time.sleep(0.3)
        except Exception as exc:
            return f"nao consegui trazer a janela para a frente ({type(exc).__name__}: {exc})"
        if _a_frente(hwnd):
            return ""
    return (
        "a janela nao ficou em primeiro plano e o gesto ia para a janela que esta em foco"
        " - traga-a para a frente e repita"
    )


def _arvore(janela, prazo=None):
    """Descendentes da janela, com a segunda leitura que o Chromium exige.

    Uma janela Electron devolve primeiro uma arvore truncada: o Chromium so a constroi
    quando percebe que ha um cliente de acessibilidade a ler. Nao e so a contagem baixa
    que o diz: uma janela grande com 20 a 40 elementos em que o conteudo chega como uma
    area de trabalho sem alvos la dentro (medido numa Tauri: 22 elementos e 93% da janela
    num Pane opaco, e 259 elementos na leitura seguinte) e a mesma arvore por construir.
    """
    elementos = janela.descendants()[:LIMITE_VARREDURA]
    if _prazo_esgotado(prazo):
        return elementos
    if len(elementos) >= 20 and not _arvore_por_construir(elementos, janela):
        return elementos
    time.sleep(0.6)
    outra = janela.descendants()[:LIMITE_VARREDURA]
    if len(outra) > len(elementos):
        return outra
    return elementos


def _arvore_por_construir(elementos, janela):
    """Janela grande cujo conteudo chegou como UMA area de trabalho: arvore por construir."""
    if len(elementos) >= ARVORE_POBRE:
        return False
    return bool(_superficies(elementos, janela))


def _alvos(elementos, prazo=None):
    """Elementos que respondem a um gesto: tipo interativo, a vista e com nome ou automacao."""
    escolhidos = []
    for elemento in elementos:
        if _prazo_esgotado(prazo):
            break
        tipo = _tipo(elemento)
        if tipo not in TIPOS_INTERATIVOS:
            continue
        if not _texto(elemento) and not _auto_id(elemento) and tipo not in TIPOS_SEM_NOME:
            continue
        if not _visivel(elemento):
            continue
        escolhidos.append(elemento)
    return escolhidos


def _superficies(elementos, janela, prazo=None):
    """Areas grandes que nao respondem a gesto: onde se desenha ou se le (canvas, folha, documento).

    O canvas fica fora dos alvos justamente por nao responder a gesto, e e dele que saem as
    coordenadas do desenho. Dedup por caixa, porque a mesma area chega repetida em Pane/Custom.
    """
    total = _area(janela)
    if total <= 0:
        return []
    vistas = {}
    for elemento in elementos:
        if _prazo_esgotado(prazo):
            break
        if not _visivel(elemento):
            continue
        try:
            caixa = elemento.rectangle()
            area = max(0, caixa.width()) * max(0, caixa.height())
        except Exception:
            continue
        if area * 5 < total:
            continue
        vistas.setdefault((caixa.left, caixa.top, caixa.width(), caixa.height()), (area, elemento))
    maiores = sorted(vistas.values(), key=lambda par: par[0], reverse=True)
    return [(area * 100 // total, elemento) for area, elemento in maiores[:LIMITE_SUPERFICIES]]


def _resolver(janela, alvo, elementos):
    """(elemento, erro, nota): '#AutoId', 'tipo:Button', 'n:3' ou um trecho do nome."""
    pedido = str(alvo or "").strip()
    if not pedido:
        return None, "diga 'alvo': '#AutoId', 'tipo:Button', 'n:3' (o numero do mapa) ou um trecho do nome", ""
    if pedido.lower().startswith("n:"):
        numero = pedido[2:].strip()
        if not numero.isdigit():
            return None, f"indice invalido em '{pedido}': use 'n:0', 'n:1'... conforme a numeracao do mapa", ""
        indice = int(numero)
        citados = _alvos(elementos)
        if indice >= len(citados):
            return None, f"o mapa tem {len(citados)} alvos e o indice {indice} esta fora", ""
        return citados[indice], "", "por indice do mapa"
    if pedido.startswith("#"):
        procurado = pedido[1:].strip().lower()
        candidatos = [e for e in elementos if _auto_id(e).lower() == procurado]
        if candidatos:
            return candidatos[0], "", "por AutomationId"
        return None, f"nenhum elemento com AutomationId '{pedido[1:]}'", ""
    if pedido.lower().startswith("tipo:"):
        procurado = pedido[5:].strip().lower()
        for elemento in elementos:
            if _tipo(elemento).lower() != procurado or not _visivel(elemento):
                continue
            return elemento, "", f"primeiro elemento do tipo {procurado}"
        return None, f"nenhum elemento do tipo '{procurado}' nesta janela", ""
    procurado = pedido.lower()
    candidatos = [e for e in elementos if procurado in _texto(e).lower()]
    if not candidatos:
        candidatos = [e for e in elementos if _auto_id(e).lower() == procurado]
        if candidatos:
            return candidatos[0], "", f"por AutomationId '{pedido}' (escrito sem o #)"
        return None, f"nenhum elemento cujo nome contenha '{pedido}' nem AutomationId igual. Veja o mapa para os nomes exatos", ""
    ambiguidade = len(candidatos)
    com_padrao = [e for e in candidatos if _padroes(e)]
    if ambiguidade > 1 and com_padrao:
        candidatos = com_padrao
    if len(candidatos) > 1:
        citados = _alvos(elementos)
        indices = [str(citados.index(e)) for e in candidatos if e in citados]
        repetidos = sorted({_auto_id(e) or _texto(e) for e in candidatos})
        if len(repetidos) > 1:
            return None, (
                f"'{pedido}' casa com {len(candidatos)} elementos diferentes: "
                + "; ".join(f"n:{i}" for i in indices[:8])
                + ". Use um destes indices ou um '#AutomationId'"
            ), ""
    escolhido = candidatos[0]
    desempate = (
        f" (havia {ambiguidade} com esse nome; fico com o que responde a um padrao)"
        if ambiguidade > 1 and len(candidatos) == len(com_padrao)
        else ""
    )
    return escolhido, "", f"por nome ({_tipo(escolhido)}){desempate}"


def _tabela_alvos(elementos, prazo=None):
    citados = _alvos(elementos, prazo)
    linhas = []
    for indice, elemento in enumerate(citados[:LIMITE_MAPA]):
        padroes = ",".join(_padroes(elemento)) or "so gesto"
        rotulo = _texto(elemento)[:44] or "(sem nome)"
        linhas.append(
            f"[{indice:>3}] {_tipo(elemento):<12} {rotulo!r:<46} "
            f"{(_auto_id(elemento) or ''):<18} {_caixa(elemento):<22} {padroes}"
        )
    return citados, linhas


def _tabela_superficies(elementos, janela, prazo=None):
    """Linhas do mapa para as superficies de trabalho, marcadas [sup]: nao sao clicaveis por nome."""
    caixas_dos_alvos = {_caixa(elemento) for elemento in _alvos(elementos, prazo)}
    linhas = []
    for parte, elemento in _superficies(elementos, janela, prazo):
        if _caixa(elemento) in caixas_dos_alvos:
            continue
        rotulo = _texto(elemento)[:44] or "(sem nome)"
        linhas.append(
            f"[sup] {_tipo(elemento):<12} {rotulo!r:<46} "
            f"{(_auto_id(elemento) or ''):<18} {_caixa(elemento):<22} "
            f"{parte}% da janela - superficie de trabalho (use 'ponto' para clicar dentro)"
        )
    return linhas


def _novos_no_clique(antes, depois):
    """Alvos que so apareceram depois do clique: o menu que abriu, ja pronto a apontar.

    Sem isto, abrir um submenu custa sempre uma leitura extra da arvore so para o mapear.
    """
    conhecidos = {_chave(elemento) for elemento in antes}
    chaves = [_chave(elemento) for elemento in depois]
    indice_por_chave = {}
    for numero, chave in enumerate(chaves):
        indice_por_chave.setdefault(chave, numero)
    linhas = []
    for numero, elemento in enumerate(depois):
        chave = chaves[numero]
        if chave in conhecidos:
            continue
        rotulo = _texto(elemento)[:44] or "(sem nome)"
        linhas.append(
            f"[n:{indice_por_chave[chave]}] {_tipo(elemento):<12} {rotulo!r:<46} "
            f"{(_auto_id(elemento) or ''):<18} {_caixa(elemento)}"
        )
        if len(linhas) >= LIMITE_MAPA:
            break
    if not linhas:
        return ""
    return (
        "\nO clique revelou estes alvos novos (ja entram na numeracao do mapa - aponte-os"
        " por 'n:<indice>'):\n" + "\n".join(linhas)
    )


def _excesso(citados):
    return "" if len(citados) <= LIMITE_MAPA else f" (mostro os primeiros {LIMITE_MAPA})"


def _acao_mapa(janela, elementos=None, prazo=None):
    if prazo is None:
        prazo = time.monotonic() + ORCAMENTO_MAPA
    if elementos is None:
        elementos = _arvore(janela, prazo)
    citados, linhas = _tabela_alvos(elementos, prazo)
    superficies = _tabela_superficies(elementos, janela, prazo)
    parte = f", {len(superficies)} superficie(s) de trabalho" if superficies else ""
    dica = (
        " Uma superficie de trabalho nao expoe controlos para ler: veja-a com 'print' (com"
        " 'grelha' para acertar as coordenadas na imagem) e aja com 'ponto' em 'janela:x,y',"
        " contado do canto dela."
        if superficies else ""
    )
    cortado = (
        " A janela tem mais elementos do que o orcamento de leitura permite varrer: a lista"
        f" abaixo parou aos {ORCAMENTO_MAPA:.0f}s de leitura e pode estar incompleta - va direto"
        " com 'ponto' ou com uma sub-janela ('janelas' lista as que existem)."
        if _prazo_esgotado(prazo) else ""
    )
    cabecalho = (
        f'Janela "{_texto(janela)}" (hwnd {janela.handle}, {_tipo(janela)}): '
        f"{len(elementos)} elementos na arvore, {len(citados)} respondem a um gesto"
        f"{_excesso(citados)}{parte}. O canto dela no ecra e {_caixa(janela)} - e desse canto que"
        f" se contam os 'janela:x,y' do clique e a 'regiao' do print.{dica}{cortado}"
    )
    if not linhas:
        return cabecalho + _aviso_sem_alvos(janela)
    if len(citados) <= 4:
        cabecalho += (
            f" Poucos alvos ({len(citados)}): pode ser so a moldura da janela - o 'print' mostra"
            " o que o mapa esta a ver. Nesse caso o caminho e o script proprio do programa."
        )
    como_usar = (
        " Colunas: [indice] tipo nome AutomationId caixa padroes-disponiveis."
        " Para apontar use 'n:<indice>', '#AutomationId' ou um trecho do nome."
        " Os padroes (invoke/value/toggle...) NAO injetam input; 'so gesto' significa que"
        " o clique injeta input e exige o desktop desbloqueado com a janela a frente."
    )
    return cabecalho + como_usar + "\n" + "\n".join(linhas + superficies)


def _contagem_msaa(hwnd):
    """Quantos controlos a via antiga (MSAA, backend win32) ve na mesma janela; -1 se ela nem responde.

    Separa duas causas de um mapa vazio que se confundem a olho: a ferramenta nao conseguiu ler,
    ou a app nao declara controlos a ninguem. Com as duas vias em zero, e a app.
    """
    try:
        from pywinauto import Desktop
        return len(Desktop(backend="win32").window(handle=hwnd).descendants())
    except Exception:
        return -1


def _aviso_sem_alvos(janela):
    """Explicacao do mapa vazio, com a segunda via MEDIDA em vez de suposta."""
    antiga = _contagem_msaa(janela.handle)
    medida = f"a via antiga (MSAA) ve {antiga}" if antiga >= 0 else "a via antiga (MSAA) nao respondeu"
    return (
        f" Nenhum alvo com nome, e {medida} - nao e falha da leitura, e a app a nao declarar"
        " controlos. O que resta, por ordem: (1) a linguagem propria do programa (um script ou"
        " batch do proprio programa, ex: o -b do GIMP, o --background do Blender); (2) clique por"
        " 'ponto', que so serve em tela plana. Use 'print' para localizar a caixa da janela."
    )


def _acao_elemento(janela, alvo, elementos):
    elemento, erro, nota = _resolver(janela, alvo, elementos)
    if erro:
        return "ERRO: " + erro
    return (
        f"{_tipo(elemento)} {_texto(elemento)!r} em {_caixa(elemento)}"
        f" | AutomationId: {_auto_id(elemento) or '(vazio)'}"
        f" | classe: {elemento.element_info.class_name or '(vazia)'}"
        f" | ativo: {elemento.is_enabled()} | vista: {elemento.is_visible()}"
        f" | padroes: {', '.join(_padroes(elemento)) or 'nenhum (so gesto)'}"
        f" | {nota}"
    )


def _capturar_janela(janela):
    """(imagem, metodo, erro): a janela a desenhar-se a si propria primeiro, o ecra como ultimo recurso.

    O print pela composicao do sistema nao serve todas as janelas: nas apps WinUI e nas
    que desenham por DirectComposition o PrintWindow por baixo devolve nada, em silencio - e
    numa janela tapada por outra (um cliente de jogo sob a janela do Axio) a composicao
    entrega o que esta POR CIMA, ou seja a imagem de outra janela qualquer.
    """
    imagem = _por_printwindow(janela)
    if _tem_area(imagem):
        return imagem, "a propria janela a desenhar-se (le-a mesmo tapada, e a conta e a da moldura)", ""
    try:
        imagem = janela.capture_as_image()
    except Exception:
        imagem = None
    if _tem_area(imagem):
        return imagem, "composicao do sistema", ""
    retangulo = janela.rectangle()
    if retangulo.right <= retangulo.left or retangulo.bottom <= retangulo.top:
        return None, "", _motivo_de_vazio(janela)
    try:
        imagem = ImageGrab.grab(bbox=(retangulo.left, retangulo.top, retangulo.right, retangulo.bottom))
    except Exception as exc:
        return None, "", f"{type(exc).__name__}: {exc}"
    if not _tem_area(imagem):
        return None, "", _motivo_de_vazio(janela)
    return imagem, "ecra (a janela tem de estar a vista e nao pode estar tapada)", ""


def _tem_area(imagem):
    return imagem is not None and min(imagem.size) > 0


def _grelha_de_coordenadas(imagem, passo=0, origem=(0, 0)):
    """A imagem com linhas de coordenadas e o valor de cada uma, na conta que o 'janela:x,y' usa.

    Com um recorte, 'origem' e o canto do recorte na janela: os rotulos ficam nas coordenadas do
    clique, nunca nas da imagem cortada - senao o numero que se le na imagem nao serve para clicar.
    """
    passo = int(passo or 0)
    if passo <= 0 or not _tem_area(imagem):
        return imagem
    if imagem.mode not in ("RGB", "RGBA"):
        imagem = imagem.convert("RGB")
    desenho = ImageDraw.Draw(imagem)
    cor = (255, 0, 128)
    largura, altura = imagem.size
    for x in range(0, largura, passo):
        desenho.line([(x, 0), (x, altura - 1)], fill=cor, width=1)
        desenho.text((x + 2, 1), str(origem[0] + x), fill=cor)
    for y in range(0, altura, passo):
        desenho.line([(0, y), (largura - 1, y)], fill=cor, width=1)
        desenho.text((2, y + 1), str(origem[1] + y), fill=cor)
    return imagem


def _ampliada(imagem, fator=1):
    """A imagem em ponto grande por pixels intactos: e o que deixa ler um slot ou uma cota pequena."""
    fator = max(1, int(fator or 1))
    if fator <= 1 or not _tem_area(imagem):
        return imagem
    return imagem.resize((imagem.width * fator, imagem.height * fator), Image.Resampling.NEAREST)


class _CabecalhoDeBitmap(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


def _por_printwindow(janela):
    """A janela desenha-se a si propria (PrintWindow): o unico caminho que devolve o conteudo REAL de uma janela tapada por outra.

    Medido num cliente de jogo sob a janela do Axio: a composicao do sistema entregou o Axio (a janela
    de cima) e a imagem so serviu para enganar; este caminho devolveu o jogo. Sai nas coordenadas da
    moldura - as mesmas que 'janela:x,y' usa no clique - o que dispensa somar deslocamentos a mao.
    Devolve None a qualquer tropeco: quem chama cai no caminho antigo.
    """
    hwnd = getattr(janela, "handle", None)
    if not hwnd:
        return None
    try:
        retangulo = janela.rectangle()
    except Exception:
        return None
    largura, altura = retangulo.width(), retangulo.height()
    if min(largura, altura) <= 1:
        return None
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    hdc = memoria = bitmap = None
    try:
        hdc = user32.GetDC(hwnd)
        memoria = gdi32.CreateCompatibleDC(hdc)
        bitmap = gdi32.CreateCompatibleBitmap(hdc, largura, altura)
        gdi32.SelectObject(memoria, bitmap)
        if not user32.PrintWindow(hwnd, memoria, 2):
            return None
        cabecalho = _CabecalhoDeBitmap()
        cabecalho.biSize = ctypes.sizeof(_CabecalhoDeBitmap)
        cabecalho.biWidth = largura
        cabecalho.biHeight = -altura
        cabecalho.biPlanes = 1
        cabecalho.biBitCount = 32
        tampao = ctypes.create_string_buffer(largura * altura * 4)
        if not gdi32.GetDIBits(memoria, bitmap, 0, altura, tampao, ctypes.byref(cabecalho), 0):
            return None
        return Image.frombuffer("RGBA", (largura, altura), tampao, "raw", "BGRA", 0, 1).convert("RGB")
    except Exception:
        return None
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memoria:
            gdi32.DeleteDC(memoria)
        if hdc:
            user32.ReleaseDC(hwnd, hdc)


def _motivo_de_vazio(janela):
    try:
        if janela.is_minimized():
            return "a janela esta MINIMIZADA: restaure-a e traga-a para a frente"
    except Exception:
        pass
    return "a janela nao tem area visivel (minimizada, escondida ou a fechar): restaure-a e traga-a para a frente"


def _a_frente(hwnd):
    """A janela e mesmo a que esta em primeiro plano? Sem confirmar, um gesto injectado vai para outra em silencio. O restype tem de sair largos: sem ele o ctypes trunca o handle a 32 bits e a comparacao mente."""
    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        return int(user32.GetForegroundWindow()) == int(hwnd)
    except Exception:
        return False


def _aviso_de_nao_estar_a_frente(janela):
    if _a_frente(janela.handle):
        return ""
    return (
        " ATENCAO: esta janela NAO estava a frente - o print por composicao de uma janela WebView2"
        " ja entregou o que estava POR CIMA dela. Se a imagem nao bater com esta janela,"
        " traga-a para a frente (clique nela) e repita antes de concluir."
    )


def _regiao_do_alvo(janela, alvo):
    """(regiao, nota, erro): a caixa do elemento em coordenadas da janela - as mesmas que o 'print' mostra."""
    try:
        elementos = _arvore(janela, time.monotonic() + ORCAMENTO_MAPA)
    except Exception as exc:
        return "", "", f"nao consegui ler a arvore da janela para achar '{alvo}' ({type(exc).__name__}: {exc})"
    elemento, erro, nota = _resolver(janela, alvo, elementos)
    if erro:
        return "", "", erro
    canto = _canto_da_janela(janela)
    if canto is None:
        return "", "", "nao consegui medir o canto da janela"
    try:
        caixa = elemento.rectangle()
    except Exception as exc:
        return "", "", f"nao consegui medir a caixa de '{alvo}' ({type(exc).__name__}: {exc})"
    margem = 4
    esquerda = max(0, int(caixa.left) - canto[0] - margem)
    topo = max(0, int(caixa.top) - canto[1] - margem)
    largura = int(caixa.width()) + margem * 2
    altura = int(caixa.height()) + margem * 2
    return (
        f"{esquerda},{topo},{largura},{altura}",
        f" Recortei a caixa do alvo ({nota}), {largura}x{altura} px contados do canto da janela.",
        "",
    )


def _acao_print(janela, regiao, alvo="", grelha=0, ampliar=1):
    recado_do_alvo = ""
    limpa = _pedido_relativo(regiao) or str(regiao or "").strip()
    if limpa and not retangulo_da_regiao(limpa):
        return (
            f"ERRO: a regiao {regiao!r} nao e 'x,y,largura,altura' (numeros inteiros, contados do"
            " canto superior esquerdo que a imagem mostra; o prefixo 'janela:' tambem serve)."
            " Sem recorte valido a imagem sairia inteira e o pedido passava por engano."
        )
    if not retangulo_da_regiao(limpa) and str(alvo or "").strip():
        regiao, recado_do_alvo, erro = _regiao_do_alvo(janela, alvo)
        if erro:
            return "ERRO: " + erro
        limpa = _pedido_relativo(regiao) or str(regiao or "").strip()
    _, recado_frente = _trazer_para_a_frente(janela)
    imagem, metodo, erro = _capturar_janela(janela)
    if imagem is None:
        return f"ERRO: nao consegui capturar a janela ({erro})."
    recorte = retangulo_da_regiao(limpa)
    if recorte:
        try:
            cortada = imagem.crop(recorte)
        except Exception:
            cortada = None
        if not _tem_area(cortada):
            return (
                f"ERRO: a regiao {regiao!r} cai toda fora da janela, que tem"
                f" {imagem.size[0]}x{imagem.size[1]} px: confira as coordenadas"
                " (x,y,largura,altura, a partir do canto superior esquerdo dela) ou capture sem 'regiao'."
            )
        imagem = cortada
    imagem = _grelha_de_coordenadas(imagem, grelha, recorte[:2] if recorte else (0, 0))
    imagem = _ampliada(imagem, ampliar)
    buffer = io.BytesIO()
    try:
        imagem.save(buffer, format="PNG")
    except (ValueError, OSError) as exc:
        return f"ERRO: a imagem da janela saiu com {imagem.size[0]}x{imagem.size[1]} px e nao a consegui codificar ({exc})."
    base64_img, mime, _ = codificar_para_envio(buffer.getvalue())
    largura, altura = imagem.size
    recado_grelha = (
        f" A cada {int(grelha)} px vai uma linha com o valor da coordenada 'janela:x,y' daquele"
        " ponto: leia a posicao na imagem e passe-a ao gesto tal e qual, sem somar deslocamentos."
        if int(grelha or 0) > 0 else ""
    )
    recado_zoom = f" Ampliada {int(ampliar)}x, pixels intactos." if int(ampliar or 1) > 1 else ""
    return {
        "texto": (
            f'Print da janela "{_texto(janela)}": {largura}x{altura} px, por {metodo}.{recado_do_alvo}{recado_frente}'
            f"{_aviso_de_nao_estar_a_frente(janela)}{recado_grelha}{recado_zoom}"
            " A imagem segue com esta resposta - olhe para ela antes de concluir."
            " ATENCAO: numa janela TRANSPARENTE (Electron/app com o fundo ainda por pintar, canvas a carregar) "
            "a composicao do sistema mostra o que esta ATRAS dela - se a imagem nao bater com o que se esperava "
            "dessa janela, e disso: traga-a para a frente, de tempo ao desenho e repita."
            " Para agir sobre o que a imagem mostra, de as coordenadas como 'janela:x,y' (contadas do canto"
            " superior esquerdo dela): o clique e o arrasto aceitam essa conta, sem somar deslocamentos a mao."
        ),
        "imagem": {"base64": base64_img, "mime": mime, "rotulo": f"[Janela nativa: hwnd {janela.handle}]"},
    }


def _trazer_para_a_frente(janela):
    """Uma janela tapada nao pinta: a composicao entrega o que esta por cima. Poe a alvo a frente antes de a fotografar."""
    if _a_frente(janela.handle):
        return True, ""
    _focar(janela.handle)
    if _a_frente(janela.handle):
        return True, " (trouxe-a para a frente para a fotografar)"
    return False, (
        " ATENCAO: esta janela nao esta a frente e nao a consegui trazer - a imagem pode ser a da janela"
        " que a tapa (tipicamente um fundo escuro). Traga-a a frente (clique nela) e repita."
    )


def _acao_abrir(alvo):
    caminho, argumentos, erro = _repartir_alvo(alvo)
    if erro:
        return "ERRO: " + erro
    try:
        antes = {janela.handle for janela in _desktop().windows() if _texto(janela)}
    except Exception as exc:
        return f"ERRO: nao consegui enumerar as janelas do Windows ({type(exc).__name__}: {exc})"
    antes_avisos = {aviso["hwnd"] for aviso in _dialogos_a_espera()}
    try:
        processo = subprocess.Popen(
            [caminho, *argumentos],
            cwd=os.path.dirname(caminho) or None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return f"ERRO: nao consegui lancar {caminho} ({type(exc).__name__}: {exc})"
    janela, como, erro = _esperar_janela(processo, antes)
    _esquecer_censo()
    if erro:
        return f"ERRO: {os.path.basename(caminho)} foi lancado (pid {processo.pid}), mas {erro}."
    resumo = "nao consegui ler a arvore dela"
    prazo = time.monotonic() + ORCAMENTO_MAPA
    try:
        elementos = _arvore(janela, prazo)
        resumo = f"{len(elementos)} elementos na arvore, {len(_alvos(elementos, prazo))} respondem a um gesto"
    except Exception:
        pass
    outras = [j for j in _janelas_do_pid(processo.pid) if j.handle != janela.handle]
    nota_irmas = (
        " Outras janelas do mesmo processo, da maior para a menor (use o hwnd em 'janela'): "
        + "; ".join(f'hwnd={j.handle} "{_texto(j)[:40]}" {_area(j)}px' for j in outras[:4])
        if outras else ""
    )
    pedidos = [
        aviso for aviso in _dialogos_a_espera() if aviso["hwnd"] not in antes_avisos
    ]
    nota_pedidos = (
        " ATENCAO: apareceu uma janela a pedir resposta e ela NAO pertence a este programa"
        " (tipicamente o pedido de autorizacao do Windows, que corre a parte): "
        + "; ".join(
            f'"{a["titulo"]}" (hwnd {a["hwnd"]}, {a["de_quem"]})'
            + (" [pedido do Windows: responde-se permitindo, nao se fecha]" if a["do_sistema"] else "")
            for a in pedidos[:3]
        )
        + ". Responde-lhe ou fecha-a agora (acao='fechar' com esse hwnd): deixada aberta, fica a"
        " espera do utilizador depois de a rodada acabar."
        if pedidos else ""
    )
    return (
        f'Abri "{os.path.basename(caminho)}" (pid {processo.pid}): janela "{_texto(janela)}"'
        f" hwnd {janela.handle}, encontrada {como}. {resumo}."
        " Use acao='mapa' com este hwnd para ver o indice dos alvos."
        + nota_irmas
        + nota_pedidos
    )


def _palavras(texto):
    """As palavras de um rotulo, sem acentos e sem maiusculas, para comparar palavra a palavra.

    Comparar por pedaco de texto dava falsos positivos, e nao teoricos: "Adicionar Nova Guia"
    contem "no" dentro de "nova" e "Pequeno Aumento Vertical" contem "no" dentro de "pequeno",
    e os dois passavam por botoes de resposta a um aviso - o 'situacao' apontava duas respostas
    que nao eram resposta nenhuma, com o Bloco de notas aberto. Palavra inteira resolve os dois.
    """
    simples = unicodedata.normalize("NFKD", (texto or "").lower())
    simples = "".join(caractere for caractere in simples if not unicodedata.combining(caractere))
    simples = simples.replace("'", "")
    return {palavra for palavra in re.split(r"[^a-z0-9]+", simples) if palavra}


def _familia_da_resposta(nome):
    """A familia de resposta a que o rotulo do botao pertence, ou None se ele nao responde a nada.

    A ordem E a da seguranca: fechar uma janela nunca justifica gravar em nome do utilizador, logo
    "Nao salvar" vem primeiro, depois "Nao", e so depois "Cancelar" - um "Salvar" sozinho nao
    pertence a familia nenhuma e nunca e carregado. Responder "Nao" a um aviso que nao era de
    gravacao deixa a janela aberta, e isso e reportado como esta: nunca se escreve por engano.
    """
    palavras = _palavras(nome)
    if not palavras:
        return None
    for posicao, familia in enumerate(RESPOSTAS_DE_AVISO):
        for frase in familia:
            if set(frase) <= palavras:
                return posicao
    return None


def _botao_do_aviso(janela, prazo=None):
    """O botao pelo qual se responde ao aviso a vista nesta superficie, ou None.

    Devolve sempre o da familia mais segura que existir. Le a arvore com prazo: um aviso e pequeno,
    mas uma janela que nem responde ao fecho nao pode custar uma varredura inteira a cada tentativa.
    """
    candidatos = []
    for elemento in _arvore(janela, prazo):
        if _prazo_esgotado(prazo):
            break
        if _tipo(elemento) != "Button" or not _visivel(elemento):
            continue
        familia = _familia_da_resposta(_texto(elemento))
        if familia is None:
            continue
        try:
            if not elemento.is_enabled():
                continue
        except Exception:
            pass
        candidatos.append((familia, elemento))
    if not candidatos:
        return None
    candidatos.sort(key=lambda par: par[0])
    return candidatos[0][1]


MARCAS_DE_PEDIDO_DO_SISTEMA = (
    "seguran",
    "security",
    "firewall",
    "controlo de conta",
    "user account control",
    "conta de utilizador",
)


def _pedido_do_sistema(titulo):
    """True quando o aviso e um pedido do proprio Windows e nao de um programa.

    O caso que isto apanha e' o dialogo do firewall ("Alerta de Seguranca do Windows"), que
    pertence a um servico do sistema: a resposta segura de um aviso qualquer (nunca gravar)
    nao serve ali, onde so ha permitir ou recusar.
    """
    texto = (titulo or "").lower()
    return any(marca in texto for marca in MARCAS_DE_PEDIDO_DO_SISTEMA)


def _dialogos_a_espera(pid=None):
    """Os avisos a vista que pedem resposta, do ecra todo ou so de um processo.

    Um aviso e uma janela de topo COM DONO (GW_OWNER) ou da classe #32770 - a classificacao do
    proprio Windows, que serve tanto para um message box como para um "Salvar como" ou para o
    dialogo de uma app desenhada a mao. Sem isto, um aviso deixado a espera e invisivel para a
    ferramenta: ela via a janela principal e mais nada.
    """
    user32 = ctypes.windll.user32
    achados = []
    for registo in _janelas_do_win32():
        if not registo["visivel"] or (pid is not None and registo["pid"] != pid):
            continue
        dono = int(user32.GetWindow(registo["handle"], 4) or 0)
        if not dono and _classe_do_hwnd(registo["handle"]) != "#32770":
            continue
        de_quem = _titulo_do_hwnd(dono) if dono else f"pid {registo['pid']}"
        achados.append({
            "hwnd": registo["handle"],
            "titulo": registo["titulo"] or "(sem titulo)",
            "de_quem": de_quem,
            "do_sistema": _pedido_do_sistema(registo["titulo"]),
        })
    return achados


def _pendentes_de_um_processo(pid, excepto=()):
    """(avisos, janelas) daquele programa, ja sem as que se fecharam.

    Os dois casos ficam SEPARADOS de proposito: um aviso a espera de resposta e trabalho por
    decidir; uma janela que continua aberta pode ser so o programa a correr - e um Bloco de
    notas partilhado, por exemplo, mostra as janelas todas do mesmo processo. Misturados, o
    segundo fazia parecer que tinha ficado lixo meu quando nao tinha.
    """
    if not pid:
        return [], []
    avisos = [
        f'"{aviso["titulo"]}" (hwnd {aviso["hwnd"]})'
        for aviso in _dialogos_a_espera(pid)
        if aviso["hwnd"] not in excepto
    ]
    janelas = [
        f'"{registo["titulo"]}" (hwnd {registo["handle"]})'
        for registo in _janelas_do_win32()
        if registo["pid"] == pid
        and registo["visivel"]
        and registo["handle"] not in excepto
        and registo["titulo"]
        and registo["area"] >= AREA_MINIMA_DE_JANELA
    ]
    return avisos, janelas


def _responde(hwnd, prazo_ms=400):
    """True se a janela ainda atende mensagens - o teste de "janela pendurada" do Windows.

    Ler a arvore de uma janela que esta a morrer levanta uma excecao COM (0x80040155,
    "interface nao registada") que o pywinauto apanha e o faulthandler despeja no terminal
    com a lista de threads inteira - medido a 2026-10-03. Perguntar primeiro se ela responde
    evita o despejo e nao muda o resultado: uma janela que nao responde nao mostra aviso
    nenhum para responder.
    """
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    resposta = ctypes.c_size_t()
    try:
        user32.SendMessageTimeoutW.restype = ctypes.c_size_t
        user32.SendMessageTimeoutW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
            ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t),
        ]
        atendida = user32.SendMessageTimeoutW(
            ctypes.c_void_p(hwnd), 0, 0, 0, 0x0002, prazo_ms, ctypes.byref(resposta)
        )
    except Exception:
        return False
    return bool(atendida)


def _acao_fechar(janela, segundos=0):
    """Fecha a janela E confirma o fecho, respondendo ao aviso que ela abrir pelo caminho.

    Pedir o fecho e sair era o defeito: a janela que abre um "guardar?" ficava a espera de resposta
    depois de a rodada acabar, e o utilizador encontrava um dialogo pendente no ecra. Aqui o fecho e
    CONFIRMADO (a janela tem de desaparecer) e o aviso e respondido pela opcao mais segura que
    existir - nunca "Salvar". No fim, diz o que ficou de pe daquele programa.
    """
    titulo = _texto(janela)
    hwnd = int(getattr(janela, "handle", 0) or 0)
    pid = int(getattr(janela.element_info, "process_id", 0) or 0)
    try:
        janela.close()
    except Exception as exc:
        return f'ERRO: nao consegui fechar "{titulo}" ({type(exc).__name__}: {exc}).'
    _esquecer_censo()
    limite = time.monotonic() + (segundos or ESPERA_FECHO)
    respondidos = []
    tentativas = 0
    while time.monotonic() < limite and tentativas < LIMITE_LEITURAS_DE_AVISO:
        time.sleep(PAUSA_ATE_O_AVISO)
        if not _viva(hwnd):
            break
        tentativas += 1
        if not _responde(hwnd):
            continue
        botao = _botao_do_aviso(janela, time.monotonic() + ORCAMENTO_AVISO)
        if botao is None:
            continue
        nome = _texto(botao)
        metodo, erro = _clicar(botao)
        if erro:
            return (
                f'ERRO: a janela "{titulo}" abriu um aviso e nao consegui responder-lhe ({metodo}).'
                " O aviso continua a espera: olhe para ele com acao='print' e responda com"
                " acao='clicar' no alvo certo."
            )
        respondidos.append(f"{nome!r} ({metodo})")
        time.sleep(PAUSA_DEPOIS_DO_AVISO)
    fechou = not _viva(hwnd)
    resposta = f" Ao aviso que ela abriu respondi {', '.join(respondidos)}." if respondidos else ""
    if fechou:
        avisos, janelas = _pendentes_de_um_processo(pid, excepto=(hwnd,))
        sobra = ""
        if avisos:
            sobra = " ATENCAO: ficou um aviso a espera de resposta: " + "; ".join(avisos[:4]) + "."
        if janelas:
            sobra += " O mesmo programa tem outras janelas abertas: " + "; ".join(janelas[:4]) + "."
        if not sobra:
            sobra = " Nao ficou nada aberto desse programa."
        return f'Fechei a janela "{titulo}" (hwnd {hwnd}) e confirmei que desapareceu.{resposta}{sobra}'
    return (
        f'A janela "{titulo}" (hwnd {hwnd}) CONTINUA aberta.{resposta} Ela recusou o pedido de'
        " fecho e nao deixou nenhum aviso por decidir: feche-a pelo caminho da propria app"
        " (acao='teclas' com a tecla de fecho) ou pela API dela. Se for um programa que so sai"
        " a forca, isso e decisao do utilizador - diga-lo, nao o matar por conta propria."
    )


def _acao_situacao(identificador=""):
    """O que ficou pendente: avisos a espera de resposta e janelas ainda abertas.

    Sem 'janela', varre o ecra pelo Win32 a procura dos avisos a espera - a pergunta "sobrou
    alguma coisa a pedir resposta?". Com 'janela' ou 'pid:<n>', olha so para esse programa E
    tambem para DENTRO das janelas dele, onde vivem os avisos que muitas apps modernas desenham
    sem abrir dialogo nenhum (o Bloco de notas novo pede para guardar dentro da propria janela).
    """
    pedido = str(identificador or "").strip()
    pid = None
    if pedido:
        janela, erro = _janela(pedido, fresco=True)
        if erro:
            return "ERRO: " + erro
        pid = int(getattr(janela.element_info, "process_id", 0) or 0)
    linhas = []
    for aviso in _dialogos_a_espera(pid):
        wrapper = _janela_avulsa(aviso["hwnd"])
        botao = _botao_do_aviso(wrapper, time.monotonic() + ORCAMENTO_AVISO) if wrapper else None
        resposta = (
            f" -> respondo com {_texto(botao)!r}" if botao is not None
            else " -> sem botao de resposta reconhecido, sera preciso olhar para ele"
        )
        linhas.append(f'  AVISO "{aviso["titulo"]}" (hwnd {aviso["hwnd"]}), de {aviso["de_quem"]}{resposta}')
    if pid:
        for registo in _janelas_do_win32():
            if registo["pid"] != pid or not registo["visivel"]:
                continue
            if not registo["titulo"] or registo["area"] < AREA_MINIMA_DE_JANELA:
                continue
            marca = " [minimizada]" if ctypes.windll.user32.IsIconic(registo["handle"]) else ""
            linhas.append(f'  JANELA "{registo["titulo"]}" (hwnd {registo["handle"]}){marca}')
            wrapper = _janela_avulsa(registo["handle"])
            if wrapper is None:
                continue
            botao = _botao_do_aviso(wrapper, time.monotonic() + ORCAMENTO_AVISO)
            if botao is not None:
                linhas.append(
                    f'      botao de resposta a vista dentro dela: {_texto(botao)!r}'
                    " (acao='fechar' responde e fecha)"
                )
    alvo = f" no programa {pid}" if pid else " no ecra"
    if not linhas:
        return f"Nada pendente{alvo}: nenhum aviso a espera de resposta."
    return f"Pendente{alvo}:\n" + "\n".join(linhas)


def _caixa_do_hwnd(hwnd):
    """(left, top, largura, altura) pelo Win32 - funciona com qualquer janela, mesmo a que o UIA mal ve."""
    caixa = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(caixa)):
        return None
    return (caixa.left, caixa.top, caixa.right - caixa.left, caixa.bottom - caixa.top)


def _viva(hwnd):
    """A janela existe - o teste mais barato que ha, e o unico que nao depende da arvore do UIA."""
    return bool(hwnd) and bool(ctypes.windll.user32.IsWindow(int(hwnd)))


def _classe_do_hwnd(hwnd):
    """A classe da janela, pelo Win32: '#32770' e o dialogo do Windows, seja de que app for."""
    buffer = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(int(hwnd), buffer, 256)
    return buffer.value


def _titulo_do_hwnd(hwnd):
    comprimento = ctypes.windll.user32.GetWindowTextLengthW(int(hwnd))
    if comprimento <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(comprimento + 1)
    ctypes.windll.user32.GetWindowTextW(int(hwnd), buffer, comprimento + 1)
    return buffer.value


def _acao_mover(janela, pedido):
    """Poe a janela em 'x,y,largura,altura' - o caminho para arrumar varias janelas lado a lado.

    O movimento vai pelo Win32, e nao pelo wrapper: o UIAWrapper do pywinauto nao tem
    move_window (so o do backend win32 tem), e o MoveWindow trabalha pelo hwnd, que existe
    para qualquer janela. A posicao final e LIDA de volta, nunca dada como certa.
    """
    numeros = [int(n) for n in re.findall(r"-?\d+", str(pedido or ""))]
    if len(numeros) != 4:
        return "ERRO: acao='mover' precisa de 'regiao' com 'x,y,largura,altura'."
    x, y, largura, altura = numeros
    if largura <= 0 or altura <= 0:
        return "ERRO: a largura e a altura tem de ser maiores que zero."
    hwnd = int(getattr(janela, "handle", 0) or 0)
    if not hwnd:
        return "ERRO: nao consegui o hwnd da janela para a mover."
    antes = _caixa_do_hwnd(hwnd)
    if not ctypes.windll.user32.MoveWindow(hwnd, x, y, largura, altura, True):
        return f"ERRO: o Windows recusou mover a janela {hwnd}."
    time.sleep(0.3)
    depois = _caixa_do_hwnd(hwnd)
    _esquecer_censo()
    de_onde = "%s,%s %sx%s" % antes if antes else "?"
    para_onde = "%s,%s %sx%s" % depois if depois else "?"
    aviso = ""
    if depois and tuple(depois) != (x, y, largura, altura):
        aviso = (
            " ATENCAO: o Windows ajustou o pedido - a janela tem minimo proprio ou nao ha"
            " esse espaco no ecra."
        )
    return (
        f'Movi a janela "{_texto(janela)}" (hwnd {hwnd}) de {de_onde} para {para_onde}.'
        " A posicao foi lida de volta do Windows, nao da conta pedida." + aviso
    )


def _acao_esperar(identificador, segundos):
    """Espera a janela existir e devolve o hwnd - a resposta a 'lancei o programa, quando e que posso agir nele?'.

    A espera polla pelo Win32 (0,007s por leitura, sem excecao nenhuma) e nao pelo censo do UIA:
    cada censo fresco custa 2,25s e levanta uma excecao COM que o pywinauto apanha e o faulthandler
    do Python despeja no terminal com a lista de threads inteira. Medido a 2026-10-03: esperar 10s
    por uma janela eram 25 varreduras completas do UIA, 56s de CPU e 25 despejos no terminal.
    """
    pedido = str(identificador or "").strip()
    if not pedido:
        return "ERRO: acao='esperar' precisa de 'janela' (o hwnd, 'pid:<numero>' ou um trecho do titulo)."
    limite = segundos or ESPERA_JANELA_PADRAO
    fim = time.monotonic() + limite
    ultimo = ""
    while time.monotonic() < fim:
        janela, erro = _procurar_no_win32(pedido)
        if janela is not None:
            try:
                caixa = janela.rectangle()
                onde = f"canto ({caixa.left},{caixa.top}), {caixa.width()}x{caixa.height()}"
            except Exception:
                onde = "caixa ilegivel"
            return (
                f'A janela "{_texto(janela)}" esta aberta: hwnd {janela.handle}, {onde}.'
                " Use este hwnd em 'janela' nas proximas chamadas."
            )
        ultimo = erro
        time.sleep(0.4)
    return f'ERRO: "{pedido}" nao apareceu em {limite:.0f}s. {ultimo}'


def _clicar(elemento):
    """(metodo, erro): padroes UIA primeiro, gesto so em ultimo recurso."""
    for nome, metodo in (
        ("invoke", "Invoke"),
        ("toggle", "Toggle"),
        ("selection_item", "Select"),
        ("expand_collapse", "Expand"),
    ):
        interface = _interface(elemento, nome)
        if interface is None:
            continue
        try:
            getattr(interface, metodo)()
            return f"padrao UIA {nome}.{metodo} (nao injeta input)", ""
        except Exception:
            continue
    try:
        elemento.set_focus()
        elemento.click_input()
        return "gesto click_input (injeta input: rato do utilizador e rede de seguranca)", ""
    except Exception as exc:
        return "", f"nao consegui acionar o elemento ({type(exc).__name__}: {exc})"


def _literal(texto):
    """O texto pronto para o teclado: os caracteres que o pywinauto le como TECLA vao entre chaves.

    Medido no Bloco de notas: sem isto, 'a^b(c)+d{2}~x' chega a janela feito lixo - o '^' pressiona
    Ctrl, o '(' agrupa, o '{' abre uma tecla com nome - e uma senha com parenteses entra errada em
    silencio. Os oito caracteres saem do parse_keys do proprio pywinauto, nao de suposicao.
    """
    return "".join("{" + c + "}" if c in CARACTERES_DE_TECLA else c for c in str(texto))


def _escrever(elemento, texto):
    interface = _interface(elemento, "value")
    if interface is not None:
        try:
            interface.SetValue(texto)
            return "padrao UIA value.SetValue (nao injeta input)", ""
        except Exception:
            pass
    try:
        elemento.set_focus()
        _teclado().send_keys(
            _literal(texto), with_spaces=True, with_tabs=True, with_newlines=True
        )
        return "gesto de teclado, com os caracteres de tecla escapados (injeta input)", ""
    except Exception as exc:
        return "", f"nao consegui escrever no elemento ({type(exc).__name__}: {exc})"


MODIFICADORES_TECLA = {"ctrl": "^", "control": "^", "alt": "%", "shift": "+"}
TECLAS_WIN = {"win", "windows", "super", "meta", "lwin"}

NOMES_TECLA = {
    "enter": "ENTER", "return": "ENTER", "tab": "TAB", "esc": "ESC", "escape": "ESC",
    "space": "SPACE", "backspace": "BACKSPACE", "delete": "DELETE", "del": "DELETE",
    "insert": "INSERT", "home": "HOME", "end": "END", "pageup": "PGUP", "pagedown": "PGDN",
    "up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT",
}


def _normalizar_teclas(tecla):
    """Traduz 'ctrl+shift+r' para a sintaxe que o pywinauto injecta ('^+r') e 'win+r'
    para '{VK_LWIN down}r{VK_LWIN up}'.

    Sem isto o que vai para o ecra e a STRING 'ctrl+shift+r' escrita no campo: o atalho
    nunca dispara e o campo fica com lixo la dentro. O Win nao tem prefixo de um
    caractere como o Ctrl/Alt/Shift - tem de ser pressionado e largado em volta da tecla,
    senao o que chega ao ecra e so a ultima letra. A sintaxe de chaves ('{ENTER}', '^a')
    passa intacta, como sempre passou.
    """
    bruto = str(tecla or "").strip()
    if not bruto or "{" in bruto:
        return bruto
    tokens = [t.strip() for t in bruto.split("+")]
    modificadores = ""
    com_win = False
    while len(tokens) > 1:
        baixo = tokens[0].lower()
        if baixo in MODIFICADORES_TECLA:
            modificadores += MODIFICADORES_TECLA[baixo]
        elif baixo in TECLAS_WIN:
            com_win = True
        else:
            break
        tokens.pop(0)
    if not tokens:
        return bruto
    resto = tokens[-1]
    nome = NOMES_TECLA.get(resto.lower())
    if nome:
        corpo = modificadores + "{" + nome + "}"
    elif len(resto) == 1:
        corpo = modificadores + resto
    elif len(tokens) == 1 and not modificadores:
        corpo = bruto
    else:
        corpo = modificadores + "{" + resto.upper() + "}"
    if com_win:
        return "{VK_LWIN down}" + corpo + "{VK_LWIN up}"
    return corpo


def _teclas_viraram_texto(antes, depois, tecla):
    """Palavras da tecla que ficaram escritas no campo: prova de que nao foram accionadas."""
    if depois == antes:
        return []
    ganho = depois[len(antes):] if depois.startswith(antes) else depois
    palavras = [p for p in re.split(r"[^0-9A-Za-z]+", str(tecla or "")) if len(p) > 2]
    return [p for p in palavras if p.lower() in ganho.lower() and p.lower() not in antes.lower()]


def _pontos(pedido, minimo=4):
    """[(x, y), ...] de 'x,y' ou de varios pares seguidos ('x1,y1 x2,y2 ...'), em coordenadas do ecra."""
    numeros = [int(n) for n in re.findall(r"-?\d+", str(pedido or ""))]
    if len(numeros) < minimo or len(numeros) % 2:
        return []
    return list(zip(numeros[::2], numeros[1::2]))


def _pedido_relativo(pedido):
    """O pedido sem o prefixo 'janela:', quando ele o traz; None quando as coordenadas ja sao do ecra."""
    texto = str(pedido or "").strip()
    for prefixo in ("janela:", "window:"):
        if texto.lower().startswith(prefixo):
            return texto[len(prefixo):].strip()
    return None


def _canto_da_janela(janela):
    """(x, y) do canto que o 'print' mostra como 0,0 - o canto superior esquerdo da janela, no ecra."""
    try:
        caixa = janela.rectangle()
    except Exception:
        return None
    return int(caixa.left), int(caixa.top)


def _pontos_do_pedido(janela, pedido, minimo=2):
    """(pontos, erro): pontos em coordenadas do ecra. Com 'janela:x,y' a conta parte do canto do 'print'."""
    relativo = _pedido_relativo(pedido)
    pontos = _pontos(relativo if relativo is not None else pedido, minimo=minimo)
    if not pontos:
        return [], (
            "escreva 'x,y' em coordenadas do ecra ou 'janela:x,y' contadas a partir do canto"
            " superior esquerdo que o 'print' dessa janela mostra"
        )
    if relativo is None:
        return pontos, ""
    canto = _canto_da_janela(janela)
    if canto is None:
        return [], "nao consegui medir o canto da janela para contar as coordenadas a partir dele"
    return [(canto[0] + x, canto[1] + y) for x, y in pontos], ""


def _interpolar(origem, destino, passos=8):
    return [
        (
            round(origem[0] + (destino[0] - origem[0]) * passo / passos),
            round(origem[1] + (destino[1] - origem[1]) * passo / passos),
        )
        for passo in range(1, passos + 1)
    ]


def _arrastar(pontos):
    """(metodo, erro): um press/move/release por segmento, com pausa entre os eventos - as apps que desenham a reta entre o press e o release ignoram os movimentos do meio, e as ferramentas de forma so pegam no arrasto se ele durar."""
    rato = _mouse()
    try:
        for origem, destino in zip(pontos, pontos[1:]):
            rato.move(coords=origem)
            time.sleep(PAUSA_TRACO)
            rato.press(button="left", coords=origem)
            time.sleep(PAUSA_TRACO)
            for ponto in _interpolar(origem, destino):
                rato.move(coords=ponto)
                time.sleep(PAUSA_TRACO)
            time.sleep(PAUSA_TRACO)
            rato.release(button="left", coords=destino)
            time.sleep(PAUSA_TRACO)
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"
    return f"gesto com {len(pontos) - 1} tracos (um press/move/release por segmento)", ""


def _acao_clique_ponto(janela, pedido, botao=""):
    pontos, erro = _pontos_do_pedido(janela, pedido, minimo=2)
    if erro:
        return "ERRO: em acao='clicar' com 'ponto', " + erro + "."
    erro = _focar(janela)
    if erro:
        return "ERRO: " + erro
    nome = _botao_do_clique(botao)
    try:
        _mouse().click(button=nome, coords=pontos[0])
    except Exception as exc:
        return (
            f"ERRO: nao consegui clicar em {pontos[0]} ({type(exc).__name__}: {exc})."
            " O gesto exige o desktop desbloqueado e a janela em primeiro plano."
        )
    regresso = {"right": " (botao direito)", "middle": " (botao do meio)"}.get(nome, "")
    return (
        f'Cliquei em {pontos[0]}{regresso} (coordenadas do ecra) na janela'
        f' "{_texto(janela)}", por gesto.'
    )


def _botao_do_clique(botao):
    """O nome do botao do rato na lingua do pywinauto - o que o pedido nao disser e o esquerdo."""
    return {"direito": "right", "meio": "middle", "esquerdo": "left"}.get(
        str(botao or "").strip().lower(), "left"
    )


def _acao_escrever_ponto(janela, pedido, texto):
    """(texto, erro): clica no ponto e escreve a seguir - a via para as apps que nao declaram controlos nenhuns (jogo, ipchanger, app desenhada a mao), onde nao ha 'alvo' para apontar."""
    pontos, erro = _pontos_do_pedido(janela, pedido, minimo=2)
    if erro:
        return "ERRO: em acao='escrever' com 'ponto', " + erro + "."
    erro = _focar(janela)
    if erro:
        return "ERRO: " + erro
    try:
        _mouse().click(button="left", coords=pontos[0])
        time.sleep(PAUSA_TRACO * 8)
        _teclado().send_keys(
            _literal(texto), with_spaces=True, with_tabs=True, with_newlines=True
        )
    except Exception as exc:
        return (
            f"ERRO: nao consegui escrever em {pontos[0]} ({type(exc).__name__}: {exc})."
            " O gesto exige o desktop desbloqueado e a janela em primeiro plano."
        )
    return (
        f"Escrevi {texto!r} em {pontos[0]} (coordenadas do ecra), na janela \"{_texto(janela)}\","
        " por gesto: clique no ponto e o texto a seguir (os caracteres de tecla vao escapados)."
    )


def _acao_escrever_em_foco(janela, texto):
    """Escreve sem alvo nem ponto: as teclas vao para a janela que ja tem o foco."""
    erro = _focar(janela)
    if erro:
        return "ERRO: " + erro
    do_cofre = cofre.tem_placeholders(texto)
    texto, erro_cofre = cofre.resolver_ou_erro(texto)
    if erro_cofre:
        return f"ERRO: {erro_cofre}."
    try:
        _teclado().send_keys(
            _literal(texto), with_spaces=True, with_tabs=True, with_newlines=True
        )
    except Exception as exc:
        return (
            f"ERRO: nao consegui escrever na janela ({type(exc).__name__}: {exc})."
            " Escrever injecta input: a janela tem de estar desbloqueada e em primeiro plano."
        )
    mostrado = "(valor do cofre, nao mostrado)" if do_cofre else repr(texto)
    return f'Escrevi {mostrado} na janela "{_texto(janela)}", sem alvo (input de teclado).'


def _acao_arrastar(janela, pedido):
    pontos, erro = _pontos_do_pedido(janela, pedido, minimo=4)
    if erro:
        return "ERRO: acao='arrastar' precisa de 'ponto' com pelo menos dois pares de coordenadas; " + erro + "."
    if len(pontos) > LIMITE_TRACO:
        return f"ERRO: o traco tem {len(pontos)} pontos e o limite e {LIMITE_TRACO}."
    erro = _focar(janela)
    if erro:
        return "ERRO: " + erro
    metodo, erro = _arrastar(pontos)
    if erro:
        return (
            f"ERRO: {erro}. O gesto exige o desktop desbloqueado e a janela em primeiro plano."
        )
    return (
        f'Arrastei na janela "{_texto(janela)}" por {metodo},'
        f" de {pontos[0]} a {pontos[-1]} (coordenadas do ecra)."
    )


def _teclas_a_janela(janela, tecla, alvo_teclas):
    """Teclas para a JANELA (sem alvo): vao pelo teclado do sistema, com a janela trazida a frente.

    A via do elemento - set_focus e type_keys no wrapper da janela - NAO serve: medida a
    2026-10-02 num Bloco de notas, rebenta com ElementNotEnabled. E e justamente o caminho de que
    um jogo ou uma app desenhada a mao precisa, onde nao ha controlo nenhum para focar.
    """
    hwnd = int(getattr(janela, "handle", 0) or 0)
    if hwnd:
        try:
            user32 = ctypes.windll.user32
            if user32.GetForegroundWindow() != hwnd:
                user32.SetForegroundWindow(hwnd)
                time.sleep(0.3)
        except Exception:
            pass
    try:
        _teclado().send_keys(alvo_teclas)
    except Exception as exc:
        return (
            f"ERRO: nao consegui enviar as teclas ({type(exc).__name__}: {exc})."
            " As teclas injectam input: o desktop tem de estar desbloqueado."
        )
    return (
        f'Enviei {tecla!r} (injectado como {alvo_teclas!r}) para a janela "{_texto(janela)}"'
        " (a propria janela, sem alvo), pelo teclado do sistema. ATENCAO: um atalho nao deixa"
        " marca no texto, por isso isto NAO prova que o alvo reagiu - confirme o efeito"
        " (acao='print' na janela, ou o estado que devia mudar) antes de concluir."
    )


def _por_na_area_de_transferencia(caminho):
    """Deixa um FICHEIRO na area de transferencia do Windows (CF_HDROP) - o unico caminho para
    o levar a outra sessao (Windows Sandbox, maquina virtual, RDP), onde um Ctrl+V o deposita
    na pasta que a janela estiver a mostrar. A area de transferencia e partilhada entre as
    sessoes; um caminho escrito como texto nao serve, porque a outra sessao nao o alcanca."""
    win32clipboard, win32con = _area_de_transferencia()
    lista = caminho + "\0\0"
    cabecalho = struct.pack("<IiiII", 20, 0, 0, 0, 1)
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_HDROP, cabecalho + lista.encode("utf-16-le"))
    finally:
        win32clipboard.CloseClipboard()


def _acao_colar_ficheiro(janela, ficheiro):
    caminho = os.path.abspath(str(ficheiro or "").strip())
    if not os.path.isfile(caminho):
        return f"ERRO: nao encontrei o ficheiro {ficheiro!r} no disco."
    _trazer_para_a_frente(janela)
    time.sleep(0.3)
    try:
        _por_na_area_de_transferencia(caminho)
    except Exception as exc:
        return (
            f"ERRO: nao consegui por o ficheiro na area de transferencia"
            f" ({type(exc).__name__}: {exc})."
        )
    time.sleep(0.3)
    _teclado().send_keys("^v")
    time.sleep(1.2)
    return (
        f"Pus {os.path.basename(caminho)} na area de transferencia e colei-o com Ctrl+V na"
        f" janela \"{_texto(janela)}\". A copia demora um instante (o ficheiro e grande) e cai"
        " na pasta que essa janela estiver a mostrar - confirme com acao='print' que ele"
        " apareceu, antes de contar com ele. Isto so vale entre sessoes que partilhem a area"
        " de transferencia (no Windows Sandbox partilham por omissao)."
    )


def _texto_da_area_de_transferencia():
    """Devolve, em TEXTO, o que esta copiado na area de transferencia do Windows."""
    win32clipboard, win32con = _area_de_transferencia()
    win32clipboard.OpenClipboard()
    try:
        if not win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            return (
                "A area de transferencia nao tem texto nenhum - so ficheiros, ou vazia."
                " Copie o texto na janela de origem (Ctrl+C) e repita."
            )
        texto = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()
    if not str(texto).strip():
        return "A area de transferencia tem texto vazio."
    return f"Texto copiado ({len(texto)} caracteres):\n{texto}"


def _passos_do_roteiro(passos):
    """Lista de gestos validada - cada passo e o mesmo que uma chamada isolada.

    Valida tudo ANTES de tocar em nada: um roteiro com o passo 4 mal escrito nao pode disparar os
    tres primeiros e so depois descobrir o erro, com a janela ja a meio de um login.
    """
    if isinstance(passos, (list, tuple)):
        bruto = list(passos)
    else:
        escrito = str(passos or "").strip()
        if not escrito:
            return None, (
                "indique 'passos' com a lista JSON dos gestos, por exemplo: "
                '[{"acao":"clicar","ponto":"janela:129,271"},'
                '{"acao":"escrever","ponto":"janela:367,213","texto":"conta"},'
                '{"acao":"teclas","tecla":"{TAB}"}]'
            )
        try:
            bruto = json.loads(escrito)
        except Exception as exc:
            return None, (
                f"'passos' nao e JSON valido ({exc}); cada gesto e um objeto com 'acao' e os seus"
                " argumentos, dentro de uma lista, por exemplo: "
                '[{"acao":"clicar","ponto":"janela:129,271"},{"acao":"teclas","tecla":"{TAB}"}]'
            )
    if not isinstance(bruto, list) or not bruto:
        return None, "'passos' tem de ser uma lista com pelo menos um gesto"
    if len(bruto) > LIMITE_PASSOS_ROTEIRO:
        return None, (
            f"'passos' tem {len(bruto)} gestos e o maximo por roteiro e {LIMITE_PASSOS_ROTEIRO};"
            " divida em dois roteiros"
        )
    limpos = []
    for indice, passo in enumerate(bruto, 1):
        if not isinstance(passo, dict):
            return None, f"o passo {indice} nao e um objeto com 'acao' e os seus argumentos"
        acao = str(passo.get("acao") or "").strip().lower()
        if acao not in ACOES_NO_ROTEIRO:
            return None, (
                f"o passo {indice} tem acao '{passo.get('acao')}'; use uma de: "
                + ", ".join(sorted(ACOES_NO_ROTEIRO))
            )
        try:
            espera = max(0, min(ESPERA_MAX_PASSO, int(passo.get("espera") or 0)))
        except (TypeError, ValueError):
            return None, (
                f"o passo {indice} tem espera '{passo.get('espera')}'; use milissegundos inteiros"
                f" (0 a {ESPERA_MAX_PASSO})"
            )
        limpos.append(dict(passo, acao=acao, espera=espera))
    return limpos, ""


def _alvo_do_passo(passo):
    """O que identifica o passo no relatorio: o alvo, o ponto, a tecla ou o que foi escrito."""
    for chave in ("alvo", "ponto", "tecla", "regiao"):
        valor = str(passo.get(chave) or "").strip()
        if valor:
            return valor
    escrito = str(passo.get("texto") or "").strip()
    return f"texto {escrito!r}" if escrito else ""


def _correr_roteiro(passos, janela=""):
    """Corre os gestos em serie pela mesma ferramenta de um gesto isolado.

    Nao ha caminho alternativo: cada passo entra por tool_operar_janela, logo leva o mesmo guard e
    o mesmo relato de efeito. Parar no primeiro erro e o que impede a cascata - um passo falhado
    deixaria os seguintes a agir sobre uma janela que ja nao esta no estado previsto.
    """
    linhas = []
    _travar_censo(True)
    try:
        linhas = _passos_em_serie(passos, janela)
    finally:
        _travar_censo(False)
    pendentes = _dialogos_a_espera()
    if pendentes:
        linhas.append(
            f"Nota: ha {len(pendentes)} aviso(s) a espera de resposta no ecra: "
            + "; ".join(f'"{a["titulo"]}" (de {a["de_quem"]})' for a in pendentes[:4])
            + ". Confirme se algum e seu antes de responder."
        )
    return "\n".join(linhas)


def _passos_em_serie(passos, janela):
    """Cada passo entra pela mesma ferramenta de um gesto isolado - o mesmo guard, o mesmo relato."""
    linhas = []
    for indice, passo in enumerate(passos, 1):
        if passo.get("espera"):
            time.sleep(passo["espera"] / 1000.0)
        resultado = tool_operar_janela(
            acao=passo["acao"],
            janela=str(passo.get("janela") or janela or ""),
            alvo=str(passo.get("alvo") or ""),
            texto=str(passo.get("texto") or ""),
            tecla=str(passo.get("tecla") or ""),
            regiao=str(passo.get("regiao") or ""),
            ponto=str(passo.get("ponto") or ""),
            segundos=int(passo.get("segundos") or 0),
            botao=str(passo.get("botao") or ""),
        )
        if isinstance(resultado, dict):
            resultado = (
                "capturou uma imagem, mas um roteiro NAO entrega imagens - a imagem nao cabe no"
                " relato em serie e vinha despejada em base64. Chame acao='print' SOZINHO, fora de"
                " 'passos', para a imagem chegar."
            )
        marca = " ".join(parte for parte in (passo["acao"], _alvo_do_passo(passo)) if parte)
        linhas.append(f"[{indice}] {marca}\n    {resultado}")
        if str(resultado).startswith("ERRO:"):
            restantes = len(passos) - indice
            if restantes:
                linhas.append(
                    f"PARADO no passo {indice} do roteiro: os {restantes} gesto(s) seguintes nao"
                    " correram, para nao agirem no sitio errado."
                )
            else:
                linhas.append(f"PARADO no passo {indice} do roteiro (era o ultimo).")
            break
    return linhas


@register(
    "tool_operar_janela",
    "Ve e opera QUALQUER programa nativo do Windows pela interface (UI Automation) - o mesmo "
    "que tool_operar_preview faz do outro lado, mas em vez do DOM le a arvore de controlos que "
    "a propria app declara. Nao e preciso embutir a janela em lado nenhum: fala-se com ela pelo "
    "hwnd, onde ela estiver, mesmo tapada por outra. acao='janelas' lista o que esta aberto; "
    "'mapa' devolve o indice dos elementos que respondem a um gesto (COMECE POR AQUI, em vez de "
    "perguntar elemento a elemento); 'elemento' detalha um; 'clicar', 'escrever' e 'teclas' "
    "agem; 'abrir' lanca um programa e devolve a janela dele; 'arrastar' desenha um traco por "
    "coordenadas do ecra; 'fechar' fecha a janela, responde ao aviso que ela abrir (nunca a "
    "gravar nada) e confirma que desapareceu; 'situacao' diz o que ficou pendente; "
    "'print' entrega uma imagem dela; "
    "'mover' poe a janela no sitio e no tamanho pedidos; 'esperar' aguarda que uma janela "
    "exista e devolve o hwnd; e 'roteiro' corre VARIOS gestos numa so chamada (um login "
    "inteiro, um formulario todo) pela mesma via de um gesto isolado. "
    "ALVO: '#AutomationId' (o mais estavel), "
    "'n:<indice>' (o numero do mapa, util quando os nomes se repetem), 'tipo:Button' (o primeiro "
    "de um tipo) ou um trecho do nome. PREFIRA SEMPRE OS PADROES: 'invoke', 'value' e 'toggle' "
    "operam por padrao UIA, funcionam com o ecra trancado e nao roubam o rato ao utilizador. O "
    "clique e as teclas injetam input no sistema: exigem desktop desbloqueado com a janela em "
    "primeiro plano, e falham de forma explicita quando nao e o caso - o retorno diz sempre qual "
    "dos dois caminhos foi usado. ONDE A ARVORE ACABA: num canvas de CAD, num viewport 3D, num "
    "jogo ou em qualquer controlo desenhado a mao, o UI Automation devolve um retangulo opaco "
    "sem controlos la dentro - para esses nao ha alvo por nome, e a via e o codigo proprio do "
    "programa (o passo 5 do plano do Axio). A distincao que decide o gesto: numa TELA PLANA "
    "(Paint, Photoshop) o pixel do ecra e o pixel do desenho, logo a caixa do canvas basta e "
    "'arrastar' desenha la dentro; num VIEWPORT COM CAMARA (CAD, 3D) o mesmo pixel vale "
    "distancias diferentes conforme o zoom, e nesses o caminho e a API propria do programa, "
    "nunca a adivinhacao do pixel. NOTA: ao abrir uma janela "
    "Electron (Chromium) a primeira leitura pode vir truncada, porque a arvore so e construida "
    "quando o Chromium percebe que ha um cliente de acessibilidade - a ferramenta ja faz a "
    "segunda leitura sozinha, mas numa janela que ainda esteja a arrancar vale repetir o mapa.",
    {
        "acao": {
            "tipo": "STRING", "obrig": True,
            "enum": ["janelas", "abrir", "mapa", "elemento", "clicar", "escrever", "teclas", "arrastar", "fechar", "situacao", "print", "mover", "esperar", "roteiro", "colar_ficheiro", "texto_copiado"],
            "desc": "'janelas' lista o que esta aberto (comece por aqui se nao souber o titulo); 'abrir' lanca um programa (o 'alvo' leva o nome ou o caminho) e devolve a janela dele; 'mapa' e o indice dos elementos operaveis da janela e das superficies de trabalho, marcadas [sup] (o canvas onde se desenha nao responde a gesto e por isso nunca entraria na lista de alvos - as [sup] dao a caixa dele, que e o que o 'arrastar' precisa); 'elemento' detalha um alvo; 'clicar', 'escrever' e 'teclas' agem sobre um alvo, e 'arrastar' desenha um traco por coordenadas do ecra (canvas, tela de desenho); 'fechar' fecha a janela, responde ao aviso que ela abrir (nunca a gravar nada) e confirma que desapareceu; 'situacao' diz o que ficou pendente - os avisos a espera de resposta e as janelas ainda abertas, no ecra todo ou num programa; 'print' entrega uma imagem dela (funciona com ela tapada por outra, porque le a superficie composta pelo sistema e nao o ecra); 'colar_ficheiro' leva um ficheiro do disco a outra sessao (Windows Sandbox, maquina virtual, RDP): poe-no na area de transferencia e cola-o com Ctrl+V na janela indicada - essa janela tem de estar a MOSTRAR a pasta onde o ficheiro deve cair; 'texto_copiado' devolve em TEXTO o que esta copiado na area de transferencia, e e o caminho para LER o interior de outra sessao (Windows Sandbox, maquina virtual, RDP) sem depender de olhar para uma imagem - la dentro selecione tudo e copie (Ctrl+A, Ctrl+C) e o conteudo volta aqui em texto limpo.",
        },
        "janela": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Qual janela: o numero do hwnd (visto em acao='janelas'), 'pid:<numero>' (escolhe pelo processo - e o caminho para uma janela SEM titulo) ou um trecho do titulo, ex: 'Bloco de notas'. Com VARIAS janelas do mesmo titulo (tres clientes de um jogo, tres exploradores) acrescente '#N' para escolher a N-esima contando da ESQUERDA para a direita do ecra - ex: 'Tibia - 127.0.0.1:7171#2'. Sem o '#N' e com mais que uma candidata, a ferramenta RECUSA e lista as opcoes com o hwnd, em vez de agir num palpite. Obrigatorio em todas as acoes menos 'janelas', 'abrir', 'roteiro' e 'texto_copiado'.",
        },
        "alvo": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "O elemento dentro da janela: '#AutomationId' (o mais estavel, sobrevive a mudancas de layout e de idioma), 'n:<indice>' (o numero que o mapa mostra - use quando varios elementos tem o mesmo nome), 'tipo:Button' (o primeiro elemento desse tipo) ou um trecho do nome visivel (ex: 'Salvar'). Em acao='abrir' o 'alvo' e o programa a lancar: o nome do executavel (ex: 'notepad') ou o caminho completo.",
        },
        "texto": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "O que escrever, em acao='escrever'. Substitui o conteudo do campo.",
        },
        "tecla": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Teclas em acao='teclas': '{ENTER}', '{TAB}', '{ESC}', 'ctrl+s', 'alt+f4' ou 'win+r' (o Win e escrito por nome, nao como prefixo). Injeta input: a janela tem de estar em primeiro plano.",
        },
        "regiao": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Em acao='print': 'x,y,largura,altura' para recortar (contadas do canto superior esquerdo que a propria imagem mostra; o prefixo 'janela:' tambem serve, para a conta ficar igual a do 'ponto'). Um recorte que nao seja quatro numeros agora da ERRO em vez de devolver a janela inteira por engano. Vazio captura a janela inteira; com 'alvo' indicado e sem 'regiao', recorta so a caixa desse elemento - e o caminho para ler um campo, um painel ou um trecho de ecra sem andar a adivinhar coordenadas. Quanto menor a regiao, mais nitida chega ao modelo. Em acao='mover': o destino da janela na mesma forma 'x,y,largura,altura' - e assim que se poem varias janelas em fila, lado a lado.",
        },
        "segundos": {
            "tipo": "INTEGER", "obrig": False, "padrao": 0,
            "desc": "So em acao='esperar': quantos segundos esperar que a janela apareca (0 usa o padrao de 15). Serve para o passo seguinte a lancar um programa - 'lancei, quando e que posso agir nele?' - sem dormir um tempo adivinhado. Em acao='fechar': quanto esperar pelo fecho e pela resposta ao aviso que a janela abrir (0 usa o padrao de 6).",
        },
        "passos": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "So em acao='roteiro': a lista JSON dos gestos, na ordem, cada um com 'acao' e os seus argumentos. Ex: [{\"acao\":\"clicar\",\"ponto\":\"janela:129,271\"},{\"acao\":\"escrever\",\"ponto\":\"janela:367,213\",\"texto\":\"conta\"},{\"acao\":\"teclas\",\"tecla\":\"{TAB}\"},{\"acao\":\"escrever\",\"texto\":\"senha\"},{\"acao\":\"teclas\",\"tecla\":\"{ENTER}\"}] - um login inteiro numa so chamada. Cada passo aceita ainda 'espera' (milissegundos a dormir ANTES de o executar, para dar tempo a janela de reagir), 'janela' (para trocar de janela a meio - util para repetir a mesma sequencia em varios clientes, apontando cada passo ao seu '#N') e 'botao' (em 'clicar': 'direito' ou 'meio'). O roteiro para no PRIMEIRO erro e diz em que passo ficou. O 'janela' do topo serve de omissao para os passos que nao tragam o seu.",
        },
        "ponto": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Coordenadas do ecra (as mesmas que a coluna 'caixa' do mapa mostra); 'janela:x,y' conta do canto da janela. Em acao='arrastar' leva os pontos do traco: 'x1,y1 x2,y2 ...', do inicio ao fim, ate 64 pontos. Em acao='clicar' com 'alvo' vazio leva um ponto so ('x,y') e clica ali. Em acao='escrever' com 'alvo' vazio leva tambem um ponto so: clica ali e escreve 'texto' a seguir - e o caminho para uma janela que NAO declara controlos nenhuns (jogo, ipchanger, app desenhada a mao), onde nao ha alvo para apontar. Com 'alvo' E 'ponto' vazios, acao='escrever' manda as teclas para a janela que ja tem o foco, sem clicar em nada. Injeta input: exige o desktop desbloqueado e a janela em primeiro plano.",
        },
        "botao": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Qual botao do rato em acao='clicar' com 'ponto': 'esquerdo' (omissao), 'direito' ou 'meio'. E o que faltava para o gesto de dois tempos de um jogo ou de uma app desenhada a mao: armar com o botao DIREITO num item (ex: uma runa) e completar com o ESQUERDO no alvo. Vale tambem dentro dos passos de 'roteiro', com a chave 'botao' no passo.",
        },
        "grelha": {
            "tipo": "INTEGER", "obrig": False, "padrao": 0,
            "desc": "Em acao='print': desenha linhas de coordenadas a cada N px, cada uma rotulada com o valor daquele ponto na conta que o 'ponto' usa ('janela:x,y'). E o que deixa LER uma posicao na imagem e passa-la ao gesto tal e qual - escolha a medida que interessa (32 num jogo de tiles, 50 ou 100 num painel). 0 nao desenha nada.",
        },
        "ficheiro": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "So em acao='colar_ficheiro': o caminho, no disco desta maquina, do ficheiro a levar para a outra sessao.",
        },
        "ampliar": {
            "tipo": "INTEGER", "obrig": False, "padrao": 1,
            "desc": "Em acao='print': amplia a imagem N vezes por pixels intactos (sem inventar detalhe), para ler de perto um recorte pequeno - um slot de inventario, uma cota, um icone. Rende com 'regiao' pequena; ampliar a janela toda gasta o mesmo e nao acrescenta nada.",
        },
    },
)
def tool_operar_janela(acao, janela="", alvo="", texto="", tecla="", regiao="", ponto="", passos="", segundos=0, botao="", grelha=0, ampliar=1, ficheiro=""):
    emit_event("executing", function=f"Janelas nativas: {acao}")
    try:
        _desktop()
    except ImportError:
        return "ERRO: " + SEM_BIBLIOTECA

    if acao == "abrir":
        return _acao_abrir(alvo)

    if acao == "roteiro":
        lista, falha = _passos_do_roteiro(passos)
        if falha:
            return "ERRO: " + falha
        return _correr_roteiro(lista, str(janela or ""))

    if acao == "esperar":
        return _acao_esperar(janela, segundos)

    if acao == "situacao":
        return _acao_situacao(janela)

    if acao == "janelas":
        try:
            abertas = _janelas_abertas(fresco=True)
        except Exception as exc:
            return f"ERRO: nao consegui enumerar as janelas do Windows ({type(exc).__name__}: {exc})"
        vistas = {int(getattr(w, "handle", 0) or 0) for w in abertas}
        avulsas, restantes = _janelas_avulsas(vistas)
        abertas.extend(avulsas)
        if not abertas:
            return "Nenhuma janela aberta."
        linhas = [
            f"  hwnd={w.handle:<12} {_tipo(w):<8} pid={getattr(w.element_info, 'process_id', 0):<7} {_texto(w)[:70] or '(sem titulo)'}"
            for w in abertas
        ]
        falta = f" (+{restantes} ocultas)" if restantes else ""
        return (
            f"{len(abertas)} janelas abertas{falta} (use o hwnd, 'pid:<numero>' ou um trecho do titulo em 'janela'):\n"
            + "\n".join(linhas)
        )

    janela_escolhida, erro = _janela(janela)
    if erro:
        return "ERRO: " + erro

    if acao == "arrastar":
        return _acao_arrastar(janela_escolhida, ponto)
    if acao == "escrever" and not alvo and not ponto:
        if not texto:
            return "ERRO: acao='escrever' precisa de 'texto'."
        return _acao_escrever_em_foco(janela_escolhida, texto)
    if acao == "escrever" and ponto and not alvo:
        if not texto:
            return "ERRO: acao='escrever' precisa de 'texto'."
        return _acao_escrever_ponto(janela_escolhida, ponto, texto)
    if acao == "clicar" and ponto and not alvo:
        return _acao_clique_ponto(janela_escolhida, ponto, botao)
    if acao == "fechar":
        return _acao_fechar(janela_escolhida)
    if acao == "print":
        return _acao_print(janela_escolhida, regiao, alvo, grelha, ampliar)
    if acao == "mover":
        return _acao_mover(janela_escolhida, regiao)

    if acao == "colar_ficheiro":
        return _acao_colar_ficheiro(janela_escolhida, ficheiro)

    if acao == "texto_copiado":
        return _texto_da_area_de_transferencia()

    if acao == "teclas" and not str(alvo or "").strip():
        if not tecla:
            return "ERRO: acao='teclas' precisa de 'tecla' (ex: 'ctrl+shift+r', 'enter' ou '{ENTER}')."
        return _teclas_a_janela(janela_escolhida, tecla, _normalizar_teclas(tecla))

    prazo = time.monotonic() + ORCAMENTO_MAPA
    try:
        elementos = _arvore(janela_escolhida, prazo)
    except Exception as exc:
        return (
            f"ERRO: nao consegui ler a arvore da janela \"{_texto(janela_escolhida)}\""
            f" ({type(exc).__name__}: {exc}). Se ela estiver a arrancar, tente de novo."
        )

    if acao == "mapa":
        return _acao_mapa(janela_escolhida, elementos, prazo)
    if acao == "elemento":
        return _acao_elemento(janela_escolhida, alvo, elementos)

    elemento, erro, nota = _resolver(janela_escolhida, alvo, elementos)
    if erro:
        return "ERRO: " + erro

    if acao == "clicar":
        metodo, erro = _clicar(elemento)
        if erro:
            return f"ERRO: {metodo}."
        time.sleep(0.4)
        antes = _alvos(elementos)
        depois = _alvos(_arvore(janela_escolhida))
        return (
            f"Cliquei em {_tipo(elemento)} {_texto(elemento)!r} ({nota}) por {metodo}."
            f" A janela tem agora {len(depois)} alvos operaveis (antes {len(antes)})."
            + _novos_no_clique(antes, depois)
        )

    if acao == "escrever":
        if not texto:
            return "ERRO: acao='escrever' precisa de 'texto'."
        do_cofre = cofre.tem_placeholders(texto)
        texto, erro_cofre = cofre.resolver_ou_erro(texto)
        if erro_cofre:
            return f"ERRO: {erro_cofre}."
        metodo, erro = _escrever(elemento, texto)
        if erro:
            return f"ERRO: {metodo}."
        mostrado = "(valor do cofre, nao mostrado)" if do_cofre else repr(texto)
        return f"Escrevi {mostrado} em {_tipo(elemento)} {_texto(elemento)!r} ({nota}) por {metodo}."

    if acao == "teclas":
        if not tecla:
            return "ERRO: acao='teclas' precisa de 'tecla' (ex: 'ctrl+shift+r', 'enter' ou '{ENTER}')."
        alvo_teclas = _normalizar_teclas(tecla)
        antes = _valor(elemento)
        try:
            elemento.set_focus()
            elemento.type_keys(alvo_teclas, with_spaces=True)
        except Exception as exc:
            return (
                f"ERRO: nao consegui enviar as teclas ({type(exc).__name__}: {exc})."
                " As teclas injectam input: a janela tem de estar desbloqueada e em primeiro plano."
            )
        time.sleep(0.3)
        depois = _valor(elemento)
        virou_texto = _teclas_viraram_texto(antes, depois, tecla)
        if virou_texto:
            return (
                f"ERRO: {_tipo(elemento)} {_texto(elemento)!r} ({nota}) NAO aceita teclas reais:"
                f" o que enviei entrou como TEXTO no campo (ficou {depois[:60]!r}). Este alvo"
                " opera pelo padrao UIA de valor, nao por input de teclado - para lhe passar"
                " texto use acao='escrever', e para um atalho mande as teclas a JANELA (sem"
                " 'alvo'), que e quem as recebe."
            )
        if antes != depois:
            return (
                f"Enviei {tecla!r} (injectado como {alvo_teclas!r}) para {_tipo(elemento)}"
                f" {_texto(elemento)!r} ({nota}); o campo passou de {antes[:60]!r} para"
                f" {depois[:60]!r}."
            )
        return (
            f"Enviei {tecla!r} (injectado como {alvo_teclas!r}) para {_tipo(elemento)}"
            f" {_texto(elemento)!r} ({nota}) sem deixar lixo no campo. ATENCAO: um atalho nao"
            " deixa marca no texto, por isso isto NAO prova que o alvo reagiu - confirme o"
            " efeito (acao='print' na janela, ou o estado que devia mudar) antes de concluir."
        )

    return f"ERRO: acao desconhecida: {acao!r}"
