"""Achar um programa pelo nome quando ele nao esta no PATH."""

import glob
import os
import shutil
import time

try:
    import winreg  # import-local: modulo que so existe no Windows
except ImportError:
    winreg = None

CHAVE_APP_PATHS = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\"
CHAVE_UNINSTALL = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
CHAVE_UNINSTALL_WOW = "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
PASTAS_IGNORADAS = frozenset({
    "$recycle.bin", "$windows.~bt", "$windows.~ws", ".git", ".venv", "__pycache__",
    "appdata", "cache", "config.msi", "installer", "logs", "node_modules",
    "system volume information", "temp", "tmp", "windows", "winsxs",
})
UNIDADES = "CDEFGHIJK"
PROFUNDIDADE_BUSCA = 3
ORCAMENTO_BUSCA = 8.0
ORCAMENTO_NO_REGISTO = 3.0
LOCAIS_CONHECIDOS = {
    "php": ("php/php.exe", "*/php/php.exe", "*/bin/php/*/php.exe",
            "*/bin/php/*/*/php.exe", "*/*/php/php.exe"),
}

_encontrados = {}


def achar(nome):
    """Caminho do executavel, ou '' - tenta PATH, locais conhecidos, registo e varredura."""
    pedido = str(nome or "").strip().strip('"')
    if not pedido:
        return ""
    if pedido not in _encontrados:
        achado = _pela_escada(pedido)
        if achado:
            _encontrados[pedido] = achado
    return _encontrados.get(pedido, "")


def php():
    """Caminho do php.exe: a variavel PHP_EXE manda sobre a busca."""
    return os.environ.get("PHP_EXE", "").strip() or achar("php")

def _pela_escada(pedido):
    if os.path.isfile(pedido):
        return pedido
    achado = shutil.which(pedido)
    if achado:
        return achado
    achado = _por_padroes(pedido)
    if achado:
        return achado
    exe = pedido if pedido.lower().endswith(".exe") else pedido + ".exe"
    do_registo = _no_registo(pedido, exe)
    if do_registo:
        if os.path.isfile(do_registo):
            return do_registo
        achado = _varrer(exe, [do_registo], orcamento=ORCAMENTO_NO_REGISTO)
        if achado:
            return achado
    return _varrer(exe)


def _por_padroes(nome):
    padroes = LOCAIS_CONHECIDOS.get(os.path.splitext(str(nome).strip().lower())[0])
    if not padroes:
        return ""
    for padrao in padroes:
        for letra in UNIDADES:
            base = letra + ":\\"
            if not os.path.isdir(base):
                continue
            for alvo in sorted(glob.glob(os.path.join(base, *padrao.split("/")))):
                if os.path.isfile(alvo):
                    return alvo
    return ""


def _no_registo(pedido, exe):
    if winreg is None:
        return ""
    for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(raiz, CHAVE_APP_PATHS + exe) as chave:
                valor, _ = winreg.QueryValueEx(chave, "")
        except OSError:
            continue
        caminho = str(valor or "").strip().strip('"')
        if caminho and os.path.isfile(caminho):
            return caminho
    return _da_desinstalacao(os.path.splitext(str(pedido).strip().lower())[0])


def _da_desinstalacao(alvo):
    if not alvo or winreg is None:
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


def _varrer(nome, raizes=None, orcamento=ORCAMENTO_BUSCA):
    """Varre as pastas ate achar um .exe do nome pedido; entre candidatos fica o de nome mais curto."""
    alvo = os.path.splitext(str(nome).strip().lower())[0]
    if not alvo:
        return ""
    limite = time.time() + orcamento
    for raiz in (raizes if raizes is not None else _pastas_de_programas()):
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


def _pastas_de_programas():
    raizes = []
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA") or "", "Programs"),
                 os.environ.get("ProgramData")):
        if base and os.path.isdir(base):
            raizes.append(os.path.abspath(base))
    vistos = {raiz.lower() for raiz in raizes}
    for letra in UNIDADES:
        raiz = letra + ":\\"
        if os.path.isdir(raiz) and os.path.abspath(raiz).lower() not in vistos:
            raizes.append(raiz)
    return raizes
