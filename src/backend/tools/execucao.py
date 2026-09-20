"""O que esta a correr contra o codigo que esta no disco.

Cada familia de ficheiros entra em cena por um caminho diferente, e por isso a
mesma edicao exige acoes diferentes:

  * interface (Electron): src/main.js, src/preview-cdp.js e os *_preload.js sao
    lidos no ARRANQUE da janela -> so entram fechando e reabrindo o Axio;
  * servidor (Python): app.py e src/backend/**/*.py sao importados no ARRANQUE
    do Flask -> entram com Ctrl+Shift+B;
  * frontend (HTML/CSS/JS): servido do disco A CADA PEDIDO -> basta recarregar a
    janela ignorando a cache.

O instante de arranque e lido do SISTEMA (CreateToolhelp32Snapshot +
GetProcessTimes, por ctypes, sem dependencia nova). A data dos ficheiros diz
quando o codigo foi escrito, nunca o que esta em memoria: foi confundir as duas
que me fez dizer "estas a testar a versao nova" com um processo uma hora velho.
"""

import ctypes
import os
import time

from src.backend.config import APP_ROOT
from src.backend.state import ARRANQUE, emit_event
from src.backend.tools.registry import register

_EPOCA_DO_FILETIME = 116444736000000000
_INTERVALOS_POR_SEGUNDO = 10000000
_SNAPSHOT_DE_PROCESSOS = 0x00000002
_CONSULTA_LIMITADA = 0x1000
_HANDLE_INVALIDO = ctypes.c_void_p(-1).value

_NOMES_DA_INTERFACE = ("electron.exe",)
_NOMES_DO_SERVIDOR = ("python.exe", "pythonw.exe")

_ARQUIVOS_SOLTOS_DA_INTERFACE = ("src/main.js", "src/preview-cdp.js")


class _Filetime(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]


class _EntradaDeProcesso(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("cntUsage", ctypes.c_ulong),
        ("th32ProcessID", ctypes.c_ulong),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", ctypes.c_ulong),
        ("cntThreads", ctypes.c_ulong),
        ("th32ParentProcessID", ctypes.c_ulong),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", ctypes.c_ulong),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


def _configurar(api):
    api.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    api.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
    api.Process32FirstW.restype = ctypes.c_int
    api.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_EntradaDeProcesso)]
    api.Process32NextW.restype = ctypes.c_int
    api.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_EntradaDeProcesso)]
    api.OpenProcess.restype = ctypes.c_void_p
    api.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    api.GetProcessTimes.restype = ctypes.c_int
    api.GetProcessTimes.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_Filetime),
        ctypes.POINTER(_Filetime),
        ctypes.POINTER(_Filetime),
        ctypes.POINTER(_Filetime),
    ]
    api.CloseHandle.restype = ctypes.c_int
    api.CloseHandle.argtypes = [ctypes.c_void_p]


try:
    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _configurar(_KERNEL32)
except (AttributeError, OSError):
    _KERNEL32 = None


def _instante_do_filetime(contador):
    intervalos = (contador.dwHighDateTime << 32) | contador.dwLowDateTime
    return (intervalos - _EPOCA_DO_FILETIME) / _INTERVALOS_POR_SEGUNDO


def _inicio_do_processo(pid):
    """Instante de arranque (epoch UTC). 0.0 quando o sistema nao deixa ler."""
    if _KERNEL32 is None:
        return 0.0
    processo = _KERNEL32.OpenProcess(_CONSULTA_LIMITADA, False, int(pid))
    if not processo:
        return 0.0
    try:
        criacao, saida, nucleo, utilizador = _Filetime(), _Filetime(), _Filetime(), _Filetime()
        ok = _KERNEL32.GetProcessTimes(
            processo,
            ctypes.byref(criacao),
            ctypes.byref(saida),
            ctypes.byref(nucleo),
            ctypes.byref(utilizador),
        )
        return _instante_do_filetime(criacao) if ok else 0.0
    finally:
        _KERNEL32.CloseHandle(processo)


def _processos_vivos():
    """{pid: {pid, pai, nome, inicio}} de todos os processos, lidos do sistema."""
    if _KERNEL32 is None:
        return {}
    instantaneo = _KERNEL32.CreateToolhelp32Snapshot(_SNAPSHOT_DE_PROCESSOS, 0)
    if not instantaneo or instantaneo == _HANDLE_INVALIDO:
        return {}
    vivos = {}
    entrada = _EntradaDeProcesso()
    entrada.dwSize = ctypes.sizeof(_EntradaDeProcesso)
    try:
        if not _KERNEL32.Process32FirstW(instantaneo, ctypes.byref(entrada)):
            return {}
        while True:
            pid = int(entrada.th32ProcessID)
            if pid:
                vivos[pid] = {
                    "pid": pid,
                    "pai": int(entrada.th32ParentProcessID),
                    "nome": entrada.szExeFile,
                    "inicio": _inicio_do_processo(pid),
                }
            if not _KERNEL32.Process32NextW(instantaneo, ctypes.byref(entrada)):
                break
    finally:
        _KERNEL32.CloseHandle(instantaneo)
    return vivos


def _papel_do_processo(nome):
    baixo = (nome or "").lower()
    if baixo in _NOMES_DA_INTERFACE:
        return "interface"
    if baixo in _NOMES_DO_SERVIDOR:
        return "servidor"
    return "outro"


def _cadeia_acima(vivos, pid):
    """Processos de que este descende, do mais proximo ao mais distante."""
    cadeia, vistos = [], set()
    while pid and pid not in vistos and pid in vivos:
        vistos.add(pid)
        cadeia.append(vivos[pid])
        pid = vivos[pid]["pai"]
    return cadeia


def _elo_de_arranque(vivos):
    """(interface, servidor) da cadeia de pais do processo atual.

    O servidor e o Python mais EXTERNO da cadeia, e nao necessariamente este
    processo: uma sonda que corre num processo novo e filha dele e, a responder
    por si propria, mentiria sobre o arranque do Flask.
    """
    interface = servidor = None
    for processo in reversed(_cadeia_acima(vivos, os.getpid())):
        papel = _papel_do_processo(processo["nome"])
        if papel == "interface" and interface is None:
            interface = processo
        elif papel == "servidor" and servidor is None:
            servidor = processo
    return interface, servidor


def _membros(vivos, raiz):
    """O processo raiz e todos os seus descendentes, por pid."""
    if not raiz:
        return {}
    membros = {raiz["pid"]: raiz}
    filhos = {}
    for processo in vivos.values():
        filhos.setdefault(processo["pai"], []).append(processo)
    pendentes = [raiz["pid"]]
    while pendentes:
        for filho in filhos.get(pendentes.pop(), []):
            if filho["pid"] not in membros:
                membros[filho["pid"]] = filho
                pendentes.append(filho["pid"])
    return membros


def _hora(quando):
    return time.strftime("%d/%m %H:%M:%S", time.localtime(quando))


def _idade(inicio, agora):
    segundos = max(0, int(agora - inicio))
    horas, resto = divmod(segundos, 3600)
    minutos, sobra = divmod(resto, 60)
    if horas:
        return f"ha {horas}h{minutos:02d}m"
    if minutos:
        return f"ha {minutos}m{sobra:02d}s"
    return f"ha {sobra}s"


def _codigo(caminhos, extensoes):
    encontrados = []
    for caminho in caminhos:
        if not os.path.isdir(caminho):
            continue
        for raiz, subpastas, arquivos in os.walk(caminho):
            subpastas[:] = [s for s in subpastas if s != "__pycache__"]
            encontrados.extend(os.path.join(raiz, a) for a in arquivos if a.endswith(extensoes))
    return encontrados


def _codigo_da_interface():
    """Ficheiros que o Electron le no arranque (janela principal e preloads)."""
    caminhos = [os.path.join(APP_ROOT, p) for p in _ARQUIVOS_SOLTOS_DA_INTERFACE]
    pasta_js = os.path.join(APP_ROOT, "src", "frontend", "js")
    for raiz, subpastas, arquivos in os.walk(pasta_js):
        subpastas[:] = [s for s in subpastas if s != "vendor"]
        caminhos.extend(os.path.join(raiz, a) for a in arquivos if a.endswith("_preload.js"))
    return [c for c in caminhos if os.path.isfile(c)]


def _codigo_do_servidor():
    caminhos = [os.path.join(APP_ROOT, "app.py")]
    caminhos.extend(_codigo([os.path.join(APP_ROOT, "src", "backend")], (".py",)))
    return caminhos


def _codigo_do_frontend():
    return _codigo([os.path.join(APP_ROOT, "src", "frontend")], (".js", ".css", ".html"))


def _mais_novos(caminhos, quando):
    recentes = []
    for caminho in caminhos:
        try:
            escrito = os.path.getmtime(caminho)
        except OSError:
            continue
        if quando and escrito > quando:
            recentes.append((escrito, os.path.relpath(caminho, APP_ROOT).replace("\\", "/")))
    recentes.sort(reverse=True)
    return recentes


def _bloco_do_grupo(titulo, processo, caminhos, agora):
    linhas = [titulo]
    if processo is None:
        linhas.append("  processo nao identificado nesta maquina - nao consigo dizer o que lhe falta")
        return linhas, 0
    inicio = processo.get("inicio") or 0.0
    linhas.append(
        f"  {processo['nome']} pid {processo['pid']} arrancou "
        + (f"{_hora(inicio)} ({_idade(inicio, agora)})" if inicio else "(arranque desconhecido)")
    )
    if not inicio:
        linhas.append("  sem o instante de arranque nao ha como comparar com o disco")
        return linhas, 0
    recentes = _mais_novos(caminhos, inicio)
    if not recentes:
        linhas.append("  nada: este processo ja tem todo o codigo do disco")
        return linhas, 0
    linhas.append(f"  {len(recentes)} ficheiro(s) editado(s) DEPOIS do arranque:")
    for escrito, relativo in recentes[:8]:
        linhas.append(f"    {relativo}  ({_hora(escrito)})")
    if len(recentes) > 8:
        linhas.append(f"    ... e mais {len(recentes) - 8}")
    return linhas, len(recentes)


def _bloco_do_frontend():
    recentes = _mais_novos(_codigo_do_frontend(), ARRANQUE)
    linhas = ["FRONTEND (HTML/CSS/JS) - servido do disco a cada pedido: basta recarregar a janela"]
    if not recentes:
        linhas.append("  nada editado desde o arranque desta sessao")
        return linhas
    linhas.append(f"  {len(recentes)} ficheiro(s) editado(s) desde o arranque - nao exige reiniciar:")
    for escrito, relativo in recentes[:5]:
        linhas.append(f"    {relativo}  ({_hora(escrito)})")
    if len(recentes) > 5:
        linhas.append(f"    ... e mais {len(recentes) - 5}")
    linhas.append(
        "  excecao: src/frontend/css/tailwind.entrada.css (ou markup com classes do Tailwind) "
        "pede 'npm run build:css', e src/frontend/vendor/ pede 'npm run build:viewer'"
    )
    return linhas


def _processos_principais(vivos, interface, servidor, agora):
    linhas = []
    for processo, papel in ((servidor, "servidor"), (interface, "interface")):
        if processo is None:
            linhas.append(f"  {papel}: nao identificado")
            continue
        inicio = processo.get("inicio") or 0.0
        quando = f"{_hora(inicio)} ({_idade(inicio, agora)})" if inicio else "arranque desconhecido"
        linhas.append(f"  {processo['nome']} pid {processo['pid']} - {papel} - arrancou {quando}")
    if interface:
        outros = _membros(vivos, interface)
        outros.pop(interface["pid"], None)
        if outros:
            nomes = {}
            for processo in outros.values():
                nomes[processo["nome"]] = nomes.get(processo["nome"], 0) + 1
            resumo = ", ".join(f"{quantos} {nome}" for nome, quantos in sorted(nomes.items()))
            linhas.append(f"  e mais {len(outros)} processo(s) filho(s) do interface: {resumo}")
    return linhas


@register(
    "tool_diagnosticar_execucao",
    "Diz o que esta a correr e que codigo do disco esses processos NAO tem: le o instante de arranque REAL de cada processo do Axio (interface Electron e servidor Python) e compara-o com a data dos ficheiros, dizendo o que falta em cada um e o que fazer para o codigo entrar (fechar e reabrir o Axio, Ctrl+Shift+B, ou so recarregar a janela). Use ANTES de dizer ao utilizador 'reinicia e testa' e sempre que a duvida for 'o que eu editei ja esta vivo?'.",
    {
    },
    disponivel="edicao",
)
def tool_diagnosticar_execucao():
    emit_event("executing", function="Medindo o que esta a correr contra o codigo do disco")
    vivos = _processos_vivos()
    if not vivos:
        return "ERRO: nao consegui ler os processos do sistema (kernel32 indisponivel por ctypes)."
    interface, servidor = _elo_de_arranque(vivos)
    agora = time.time()
    linhas = [f"AGORA {_hora(agora)}", "", "A CORRER (arranque lido do sistema, nao da data dos ficheiros)"]
    linhas.extend(_processos_principais(vivos, interface, servidor, agora))
    linhas.append("")
    linhas.append("CODIGO DO DISCO QUE ESTES PROCESSOS NAO TEM")
    linhas_da_interface, faltam_interface = _bloco_do_grupo(
        "INTERFACE (Electron) - lido no arranque: fechar e reabrir o Axio",
        interface,
        _codigo_da_interface(),
        agora,
    )
    linhas.extend(linhas_da_interface)
    linhas.append("")
    linhas_da_servidor, faltam_servidor = _bloco_do_grupo(
        "SERVIDOR (Python) - importado no arranque: Ctrl+Shift+B",
        servidor,
        _codigo_do_servidor(),
        agora,
    )
    linhas.extend(linhas_da_servidor)
    linhas.append("")
    linhas.extend(_bloco_do_frontend())
    linhas.append("")
    if faltam_interface:
        linhas.append("VEREDITO: fechar e reabrir o Axio - o Ctrl+Shift+B NAO leva la este codigo")
    elif faltam_servidor:
        linhas.append("VEREDITO: Ctrl+Shift+B para o servidor entrar em cena")
    else:
        linhas.append("VEREDITO: o que esta a correr ja tem o codigo do disco (so o frontend pede recarregar)")
    return "\n".join(linhas)
