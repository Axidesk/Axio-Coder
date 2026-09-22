"""Janelas nativas do Windows: ver e operar qualquer app por UI Automation."""

import ctypes
import io
import os
import re
import shutil
import subprocess
import time
import winreg

from ctypes import wintypes
from PIL import ImageGrab

from src.backend.services import cofre
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
LIMITE_TRACO = 64
PAUSA_TRACO = 0.02
CHAVE_APP_PATHS = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\"
SEM_PROGRAMA = (
    "nao encontrei '{0}'. Use o nome do executavel (ex: 'notepad', 'mspaint') ou o caminho"
    " completo entre aspas (ex: \"C:\\Program Files\\App\\app.exe\")."
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
CHAVE_UNINSTALL = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
CHAVE_UNINSTALL_WOW = "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
PASTAS_IGNORADAS = frozenset({
    "$recycle.bin", "$windows.~bt", "$windows.~ws", ".git", ".venv", "__pycache__",
    "appdata", "cache", "config.msi", "installer", "logs", "node_modules",
    "system volume information", "temp", "tmp", "windows", "winsxs",
})
PROFUNDIDADE_BUSCA = 3
ORCAMENTO_BUSCA = 8.0
ORCAMENTO_MAPA = 10.0
PAUSA_ESTAVEL = 1.5
ESPERA_JANELA = 30.0
ESPERA_DELEGADA = 6.0
LIMITE_SUPERFICIES = 4


_MODULO = None
_RATO = None


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


def _janela(identificador):
    """(janela, erro): escolhida pelo hwnd, pelo processo ou por um trecho do titulo."""
    try:
        abertas = _janelas_abertas()
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
        for janela in abertas:
            if getattr(janela.element_info, "process_id", None) == int(numero):
                return janela, ""
        return _procurar_no_win32(pedido)
    procurado = pedido.lower()
    exatas = [w for w in abertas if _texto(w).lower() == procurado]
    parciais = [w for w in abertas if procurado in _texto(w).lower()]
    escolhidas = exatas or parciais
    if not escolhidas:
        return _procurar_no_win32(pedido)
    return escolhidas[0], ""


def _caminho_do_programa(nome):
    """(caminho, erro): resolve pelo PATH, pelos App Paths do registo ou pelo caminho escrito."""
    pedido = str(nome or "").strip().strip('"')
    if not pedido:
        return "", "diga o programa em 'alvo', ex: 'notepad' ou o caminho completo."
    if os.path.isfile(pedido):
        return pedido, ""
    encontrado = shutil.which(pedido)
    if encontrado:
        return encontrado, ""
    if os.name != "nt":
        return "", SEM_PROGRAMA.format(pedido)
    exe = pedido if pedido.lower().endswith(".exe") else pedido + ".exe"
    for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(raiz, CHAVE_APP_PATHS + exe) as chave:
                valor, _ = winreg.QueryValueEx(chave, "")
        except OSError:
            continue
        caminho = str(valor or "").strip().strip('"')
        if caminho and os.path.isfile(caminho):
            return caminho, ""
    do_registo = _caminho_no_registo(pedido)
    if do_registo:
        if do_registo.lower().endswith(".exe"):
            return do_registo, ""
        achado = _procurar_executavel(exe, [do_registo], orcamento=3.0)
        if achado:
            return achado, ""
    achado = _procurar_executavel(exe, _raizes_de_programas())
    if achado:
        return achado, ""
    return "", SEM_PROGRAMA.format(pedido)


def _raizes_de_programas():
    """Pastas de programas a varrer, da mais provavel para a menos (o PATH e os App Paths ja falharam)."""
    raizes = []
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA") or "", "Programs"),
                 os.environ.get("ProgramData")):
        if base and os.path.isdir(base):
            raizes.append(os.path.abspath(base))
    vistos = {raiz.lower() for raiz in raizes}
    for letra in "CDEFGHIJK":
        raiz = letra + ":\\"
        if os.path.isdir(raiz) and os.path.abspath(raiz).lower() not in vistos:
            raizes.append(raiz)
    return raizes


def _procurar_executavel(nome, raizes, orcamento=ORCAMENTO_BUSCA):
    """Caminho de um executavel cujo nome-base comece pelo pedido, varrendo as pastas dadas.

    Existe porque um programa pode nao estar no PATH nem nos App Paths, e o registo pode estar
    orfao (medido com o GIMP: o Uninstall apontava para uma pasta que o utilizador ja tinha movido).
    O teto de tempo evita que uma pasta gigante prenda a chamada; entre dois candidatos da mesma
    pasta fica o de nome mais curto, o que prefere 'gimp-2.10.exe' a 'gimp-console-2.10.exe'.
    """
    alvo = os.path.splitext(str(nome).strip().lower())[0]
    if not alvo:
        return ""
    limite = time.time() + orcamento
    for raiz in raizes:
        melhor = ""
        pilha = [(raiz, 0)]
        while pilha:
            if time.time() > limite:
                return melhor
            atual, nivel = pilha.pop()
            try:
                entradas = list(os.scandir(atual))
            except OSError:
                continue
            for entrada in entradas:
                try:
                    if entrada.is_dir(follow_symlinks=False):
                        if nivel < PROFUNDIDADE_BUSCA and entrada.name.lower() not in PASTAS_IGNORADAS:
                            pilha.append((entrada.path, nivel + 1))
                        continue
                    if not entrada.name.lower().endswith(".exe"):
                        continue
                except OSError:
                    continue
                base = os.path.splitext(entrada.name.lower())[0]
                if base == alvo:
                    return entrada.path
                if base.startswith(alvo) and (not melhor or len(entrada.name) < len(os.path.basename(melhor))):
                    melhor = entrada.path
        if melhor:
            return melhor
    return ""


def _caminho_no_registo(pedido):
    """Exe ou pasta do registo Uninstall cujo DisplayName contenha o pedido, confirmado no disco.

    O registo fica ORFAO quando a pasta muda de sitio, por isso o que sai daqui so vale depois de
    confirmado - o que devolve existe agora, ou nao devolve nada.
    """
    alvo = os.path.splitext(str(pedido).strip().lower())[0]
    if not alvo:
        return ""
    for raiz, sub in ((winreg.HKEY_LOCAL_MACHINE, CHAVE_UNINSTALL),
                      (winreg.HKEY_LOCAL_MACHINE, CHAVE_UNINSTALL_WOW),
                      (winreg.HKEY_CURRENT_USER, CHAVE_UNINSTALL)):
        try:
            with winreg.OpenKey(raiz, sub) as lista:
                total = winreg.QueryInfoKey(lista)[0]
                for indice in range(total):
                    try:
                        with winreg.OpenKey(lista, winreg.EnumKey(lista, indice)) as app:
                            nome = str(winreg.QueryValueEx(app, "DisplayName")[0] or "").lower()
                            if alvo not in nome:
                                continue
                            for campo in ("InstallLocation", "DisplayIcon"):
                                try:
                                    bruto = str(winreg.QueryValueEx(app, campo)[0] or "")
                                except OSError:
                                    continue
                                limpo = bruto.strip().strip('"').split('"')[0].strip()
                                if limpo.lower().endswith(".exe") and os.path.isfile(limpo):
                                    return limpo
                                if os.path.isdir(limpo):
                                    return limpo
                    except OSError:
                        continue
        except OSError:
            continue
    return ""


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


def _janelas_abertas():
    """Todas as janelas que valem um gesto: as que tem titulo e as sem titulo com area util.

    Enumerar so pelo titulo escondia janelas reais: uma janela de ferramenta (a do raciocinio,
    por exemplo) nao aparece na barra de tarefas e pode nao se declarar. O filtro que sobra e
    de TAMANHO, porque a arvore do Windows esta cheia de janelas de 0x0 que ninguem quer operar.
    """
    abertas = []
    for janela in _desktop().windows():
        if _texto(janela) or (_visivel(janela) and _area(janela) >= AREA_MINIMA_DE_JANELA):
            abertas.append(janela)
    vistas = {int(getattr(janela, "handle", 0) or 0) for janela in abertas}
    abertas.extend(_janelas_avulsas(vistas)[0])
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
    try:
        janela.set_focus()
        time.sleep(0.3)
    except Exception as exc:
        return f"nao consegui trazer a janela para a frente ({type(exc).__name__}: {exc})"
    return ""


def _arvore(janela, prazo=None):
    """Descendentes da janela, com a segunda leitura que o Chromium exige.

    Uma janela Electron devolve primeiro uma arvore truncada: o Chromium so a constroi
    quando percebe que ha um cliente de acessibilidade a ler.
    """
    elementos = janela.descendants()[:LIMITE_VARREDURA]
    if len(elementos) < 20 and not _prazo_esgotado(prazo):
        time.sleep(0.6)
        outra = janela.descendants()[:LIMITE_VARREDURA]
        if len(outra) > len(elementos):
            return outra
    return elementos


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
        return None, f"nenhum elemento cujo nome contenha '{pedido}'. Veja o mapa para os nomes exatos", ""
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
    cortado = (
        " A janela tem mais elementos do que o orcamento de leitura permite varrer: a lista"
        f" abaixo parou aos {ORCAMENTO_MAPA:.0f}s de leitura e pode estar incompleta - va direto"
        " com 'ponto' ou com uma sub-janela ('janelas' lista as que existem)."
        if _prazo_esgotado(prazo) else ""
    )
    cabecalho = (
        f'Janela "{_texto(janela)}" (hwnd {janela.handle}, {_tipo(janela)}): '
        f"{len(elementos)} elementos na arvore, {len(citados)} respondem a um gesto"
        f"{_excesso(citados)}{parte}.{cortado}"
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
    """(imagem, metodo, erro): a composicao do sistema primeiro, o ecra como ultimo recurso.

    O print pela composicao do sistema nao serve todas as janelas: nas apps WinUI e nas
    que desenham por DirectComposition o PrintWindow por baixo devolve nada, em silencio.
    """
    try:
        imagem = janela.capture_as_image()
    except Exception:
        imagem = None
    if imagem is not None:
        return imagem, "composicao do sistema (le a janela mesmo tapada)", ""
    retangulo = janela.rectangle()
    try:
        imagem = ImageGrab.grab(bbox=(retangulo.left, retangulo.top, retangulo.right, retangulo.bottom))
    except Exception as exc:
        return None, "", f"{type(exc).__name__}: {exc}"
    return imagem, "ecra (a janela tem de estar a vista e nao pode estar tapada)", ""


def _acao_print(janela, regiao):
    imagem, metodo, erro = _capturar_janela(janela)
    if imagem is None:
        return (
            f"ERRO: nao consegui capturar a janela ({erro}). Restaure-a e traga-a para a frente."
        )
    recorte = retangulo_da_regiao(regiao)
    if recorte:
        try:
            imagem = imagem.crop(recorte)
        except Exception:
            pass
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    base64_img, mime, _ = codificar_para_envio(buffer.getvalue())
    largura, altura = imagem.size
    return {
        "texto": (
            f'Print da janela "{_texto(janela)}": {largura}x{altura} px, por {metodo}.'
            " A imagem segue com esta resposta - olhe para ela antes de concluir."
        ),
        "imagem": {"base64": base64_img, "mime": mime, "rotulo": f"[Janela nativa: hwnd {janela.handle}]"},
    }


def _acao_abrir(alvo):
    tokens = tokenizar_linha(alvo)
    caminho, erro = _caminho_do_programa(tokens[0] if tokens else "")
    if erro:
        return "ERRO: " + erro
    try:
        antes = {janela.handle for janela in _desktop().windows() if _texto(janela)}
    except Exception as exc:
        return f"ERRO: nao consegui enumerar as janelas do Windows ({type(exc).__name__}: {exc})"
    try:
        processo = subprocess.Popen(
            [caminho, *tokens[1:]],
            cwd=os.path.dirname(caminho) or None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return f"ERRO: nao consegui lancar {caminho} ({type(exc).__name__}: {exc})"
    janela, como, erro = _esperar_janela(processo, antes)
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
    return (
        f'Abri "{os.path.basename(caminho)}" (pid {processo.pid}): janela "{_texto(janela)}"'
        f" hwnd {janela.handle}, encontrada {como}. {resumo}."
        " Use acao='mapa' com este hwnd para ver o indice dos alvos."
        + nota_irmas
    )


def _acao_fechar(janela):
    titulo = _texto(janela)
    try:
        janela.close()
    except Exception as exc:
        return f'ERRO: nao consegui fechar "{titulo}" ({type(exc).__name__}: {exc}).'
    return (
        f'Pedi o fecho da janela "{titulo}" (hwnd {janela.handle}). Se ela abrir um dialogo a'
        " pedir para guardar, esse dialogo fica a espera de resposta."
    )


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
        elemento.type_keys(texto, with_spaces=True)
        return "gesto type_keys (injeta input)", ""
    except Exception as exc:
        return "", f"nao consegui escrever no elemento ({type(exc).__name__}: {exc})"


MODIFICADORES_TECLA = {"ctrl": "^", "control": "^", "alt": "%", "shift": "+"}

NOMES_TECLA = {
    "enter": "ENTER", "return": "ENTER", "tab": "TAB", "esc": "ESC", "escape": "ESC",
    "space": "SPACE", "backspace": "BACKSPACE", "delete": "DELETE", "del": "DELETE",
    "insert": "INSERT", "home": "HOME", "end": "END", "pageup": "PGUP", "pagedown": "PGDN",
    "up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT",
}


def _normalizar_teclas(tecla):
    """Traduz 'ctrl+shift+r' para a sintaxe que o pywinauto injecta ('^+r').

    Sem isto o que vai para o ecra e a STRING 'ctrl+shift+r' escrita no campo: o atalho
    nunca dispara e o campo fica com lixo la dentro. A sintaxe de chaves ('{ENTER}', '^a')
    passa intacta, como sempre passou.
    """
    bruto = str(tecla or "").strip()
    if not bruto or "{" in bruto:
        return bruto
    tokens = [t.strip() for t in bruto.split("+")]
    modificadores = ""
    while len(tokens) > 1 and tokens[0].lower() in MODIFICADORES_TECLA:
        modificadores += MODIFICADORES_TECLA[tokens.pop(0).lower()]
    if not tokens:
        return bruto
    resto = tokens[-1]
    nome = NOMES_TECLA.get(resto.lower())
    if nome:
        return modificadores + "{" + nome + "}"
    if len(resto) == 1:
        return modificadores + resto
    if len(tokens) == 1 and not modificadores:
        return bruto
    return modificadores + "{" + resto.upper() + "}"


def _teclas_viraram_texto(antes, depois, tecla):
    """Palavras da tecla que ficaram escritas no campo: prova de que nao foram accionadas."""
    if depois == antes:
        return []
    ganho = depois[len(antes):] if depois.startswith(antes) else depois
    palavras = [p for p in re.split(r"[^0-9A-Za-z]+", str(tecla or "")) if len(p) > 2]
    return [p for p in palavras if p.lower() in ganho.lower() and p.lower() not in antes.lower()]


def _pontos(pedido):
    """[(x, y), ...] de 'x,y' ou de varios pares seguidos ('x1,y1 x2,y2 ...'), em coordenadas do ecra."""
    numeros = [int(n) for n in re.findall(r"-?\d+", str(pedido or ""))]
    if len(numeros) < 4 or len(numeros) % 2:
        return []
    return list(zip(numeros[::2], numeros[1::2]))


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


def _acao_clique_ponto(janela, pedido):
    pontos = _pontos(pedido)
    if not pontos:
        return "ERRO: em acao='clicar' com 'ponto', escreva 'x,y' em coordenadas do ecra."
    erro = _focar(janela)
    if erro:
        return "ERRO: " + erro
    try:
        _mouse().click(button="left", coords=pontos[0])
    except Exception as exc:
        return (
            f"ERRO: nao consegui clicar em {pontos[0]} ({type(exc).__name__}: {exc})."
            " O gesto exige o desktop desbloqueado e a janela em primeiro plano."
        )
    return f'Cliquei em {pontos[0]} (coordenadas do ecra) na janela "{_texto(janela)}", por gesto.'


def _acao_arrastar(janela, pedido):
    pontos = _pontos(pedido)
    if not pontos:
        return (
            "ERRO: acao='arrastar' precisa de 'ponto' com pelo menos dois pares de coordenadas"
            " do ecra, ex: 'x1,y1 x2,y2'."
        )
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


@register(
    "tool_operar_janela",
    "Ve e opera QUALQUER programa nativo do Windows pela interface (UI Automation) - o mesmo "
    "que tool_operar_preview faz do outro lado, mas em vez do DOM le a arvore de controlos que "
    "a propria app declara. Nao e preciso embutir a janela em lado nenhum: fala-se com ela pelo "
    "hwnd, onde ela estiver, mesmo tapada por outra. acao='janelas' lista o que esta aberto; "
    "'mapa' devolve o indice dos elementos que respondem a um gesto (COMECE POR AQUI, em vez de "
    "perguntar elemento a elemento); 'elemento' detalha um; 'clicar', 'escrever' e 'teclas' "
    "agem; 'abrir' lanca um programa e devolve a janela dele; 'arrastar' desenha um traco por "
    "coordenadas do ecra e 'fechar' pede o fecho da janela; 'print' entrega uma imagem dela. "
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
            "enum": ["janelas", "abrir", "mapa", "elemento", "clicar", "escrever", "teclas", "arrastar", "fechar", "print"],
            "desc": "'janelas' lista o que esta aberto (comece por aqui se nao souber o titulo); 'abrir' lanca um programa (o 'alvo' leva o nome ou o caminho) e devolve a janela dele; 'mapa' e o indice dos elementos operaveis da janela e das superficies de trabalho, marcadas [sup] (o canvas onde se desenha nao responde a gesto e por isso nunca entraria na lista de alvos - as [sup] dao a caixa dele, que e o que o 'arrastar' precisa); 'elemento' detalha um alvo; 'clicar', 'escrever' e 'teclas' agem sobre um alvo, e 'arrastar' desenha um traco por coordenadas do ecra (canvas, tela de desenho); 'fechar' pede o fecho da janela; 'print' entrega uma imagem dela (funciona com ela tapada por outra, porque le a superficie composta pelo sistema e nao o ecra).",
        },
        "janela": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Qual janela: o numero do hwnd (visto em acao='janelas'), 'pid:<numero>' (escolhe pelo processo - e o caminho para uma janela SEM titulo) ou um trecho do titulo, ex: 'Bloco de notas'. Obrigatorio em todas as acoes menos 'janelas'.",
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
            "desc": "Teclas em acao='teclas', na sintaxe do pywinauto: '{ENTER}', '{TAB}', '{ESC}', '^s' (Ctrl+S), '%f' (Alt+F). Injeta input: a janela tem de estar em primeiro plano.",
        },
        "regiao": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "So em acao='print': 'x,y,largura,altura' para recortar. Vazio captura a janela inteira. Quanto menor a regiao, mais nitida chega ao modelo.",
        },
        "ponto": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Coordenadas do ecra (as mesmas que a coluna 'caixa' do mapa mostra). Em acao='arrastar' leva os pontos do traco: 'x1,y1 x2,y2 ...', do inicio ao fim, ate 64 pontos. Em acao='clicar' com 'alvo' vazio leva um ponto so ('x,y') e clica ali - e o caminho para dentro de um canvas que nao declara controlos. Injeta input: exige o desktop desbloqueado e a janela em primeiro plano.",
        },
    },
)
def tool_operar_janela(acao, janela="", alvo="", texto="", tecla="", regiao="", ponto=""):
    emit_event("executing", function=f"Janelas nativas: {acao}")
    try:
        _desktop()
    except ImportError:
        return "ERRO: " + SEM_BIBLIOTECA

    if acao == "abrir":
        return _acao_abrir(alvo)

    if acao == "janelas":
        try:
            abertas = _janelas_abertas()
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
    if acao == "clicar" and ponto and not alvo:
        return _acao_clique_ponto(janela_escolhida, ponto)
    if acao == "fechar":
        return _acao_fechar(janela_escolhida)
    if acao == "print":
        return _acao_print(janela_escolhida, regiao)

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
