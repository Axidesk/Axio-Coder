"""Le a arvore de processos do Windows pelo instantaneo Toolhelp32.

O sistema nao guarda a relacao pai-filho num sitio consultavel: a unica fonte e um
instantaneo, que da por processo o pid do pai - e dele a arvore reconstroi-se. O
instantaneo e lido no momento do pedido, nunca guardado, porque envelhece em segundos.
"""

import ctypes
import os
from ctypes import wintypes

TH32CS_SNAPPROCESS = 0x00000002
MAX_PATH = 260
TETO_ARVORE = 200


class _Entrada(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("pid", wintypes.DWORD),
        ("heap", ctypes.c_size_t),
        ("modulo", wintypes.DWORD),
        ("threads", wintypes.DWORD),
        ("pai", wintypes.DWORD),
        ("prioridade", wintypes.LONG),
        ("flags", wintypes.DWORD),
        ("nome", ctypes.c_wchar * MAX_PATH),
    ]


def _api():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Entrada)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Entrada)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    return kernel32


def instantaneo():
    """Todos os processos por pid, com nome e pid do pai (vazio fora do Windows)."""
    if os.name != "nt":
        return {}
    kernel32 = _api()
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == wintypes.HANDLE(-1).value:
        return {}
    processos = {}
    try:
        entrada = _Entrada()
        entrada.dwSize = ctypes.sizeof(_Entrada)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entrada))
        while ok:
            processos[int(entrada.pid)] = {
                "pid": int(entrada.pid),
                "pai": int(entrada.pai),
                "nome": str(entrada.nome),
            }
            ok = kernel32.Process32NextW(snap, ctypes.byref(entrada))
    finally:
        kernel32.CloseHandle(snap)
    return processos


def arvore(pid):
    """O processo indicado e todos os descendentes, em largura, com o nivel de cada um."""
    raiz = int(pid or 0)
    if not raiz:
        return []
    processos = instantaneo()
    if not processos:
        return []
    filhos = {}
    for item in processos.values():
        filhos.setdefault(item["pai"], []).append(item["pid"])
    resultado = []
    fila = [(raiz, 0)]
    vistos = set()
    while fila and len(resultado) < TETO_ARVORE:
        atual, nivel = fila.pop(0)
        if atual in vistos:
            continue
        vistos.add(atual)
        item = processos.get(atual)
        resultado.append({
            "pid": atual,
            "nivel": nivel,
            "nome": (item or {}).get("nome", ""),
            "existe": item is not None,
        })
        for filho in filhos.get(atual, []):
            fila.append((filho, nivel + 1))
    return resultado


def vivos(pids):
    """Os pids da lista que ainda existem agora, com o nome - a prova de quem sobreviveu."""
    processos = instantaneo()
    resultado = []
    for bruto in pids or []:
        pid = int(bruto or 0)
        if pid in processos:
            resultado.append({"pid": pid, "nome": processos[pid]["nome"]})
    return resultado
