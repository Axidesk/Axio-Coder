"""Marca no disco cada arranque do Axio, para o agente saber dos reinicios sozinho.

O agente vive DENTRO do processo: um reinicio, um Ctrl+C no console ou o PC a
desligar-se nao passam por ele, e ele ficava dependente de lhe contarem. Cada
arranque escreve aqui a sua marca e cada fecho ordenado deixa a despedida; quem
arranca a seguir compara as duas e sabe que houve reinicio, quando, e se o
anterior morreu a forca. A marca de um pid que ainda esta vivo nao e reinicio:
sao duas instancias a correr ao mesmo tempo.
"""

import atexit
import json
import os
import signal
import time

from src.backend.config import APP_ROOT
from src.backend.services.arvore_processos import instantaneo
from src.backend.state import ARRANQUE

_NOME_DO_ARQUIVO = "arranque.json"

_registo = None
_vigiado = False
_antigos = {}
_motivos = {}


def _caminho():
    return os.environ.get("AXIO_ARRANQUE_ARQUIVO") or os.path.join(APP_ROOT, ".axio", _NOME_DO_ARQUIVO)


def _texto(epoch=None):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ARRANQUE if epoch is None else epoch))


def _ler():
    try:
        with open(_caminho(), "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _gravar(dados):
    caminho = _caminho()
    pasta = os.path.dirname(caminho)
    try:
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except OSError:
        return False
    return True


def _marcar_fecho(motivo):
    """Despedida da marca DESTE processo. Nunca mexe na marca de outro nem repete a propria."""
    dados = _ler()
    if not dados or int(dados.get("pid") or 0) != os.getpid() or dados.get("encerrado_em"):
        return False
    dados["encerrado_em"] = _texto()
    dados["motivo_do_fecho"] = motivo
    return _gravar(dados)


def _ao_receber_sinal(numero, quadro):
    _marcar_fecho(_motivos.get(numero, "sinal"))
    antigo = _antigos.get(numero)
    if callable(antigo):
        antigo(numero, quadro)
        return
    if numero == getattr(signal, "SIGINT", None):
        raise KeyboardInterrupt
    raise SystemExit(0)


def _vigiar_o_fecho():
    """Deixa a despedida escrita num fecho ordenado, seja qual for o caminho que o provoca."""
    global _vigiado
    if _vigiado:
        return False
    atexit.register(_marcar_fecho, "normal")
    for nome, motivo in (("SIGINT", "ctrl+c"), ("SIGBREAK", "ctrl+break"), ("SIGTERM", "terminado")):
        numero = getattr(signal, nome, None)
        if numero is None:
            continue
        try:
            _antigos[numero] = signal.signal(numero, _ao_receber_sinal)
            _motivos[numero] = motivo
        except (ValueError, OSError):
            _antigos.pop(numero, None)
            _motivos.pop(numero, None)
    _vigiado = True
    return True


def _veredicto(anterior):
    if not anterior:
        return {"tipo": "primeiro"}
    pid = int(anterior.get("pid") or 0)
    vivos = instantaneo()
    if vivos and pid and pid != os.getpid() and pid in vivos:
        return {"tipo": "paralelo", "pid": pid}
    if anterior.get("encerrado_em"):
        return {
            "tipo": "limpo",
            "iniciado_em": anterior.get("iniciado_em") or "?",
            "encerrado_em": anterior.get("encerrado_em"),
            "motivo": anterior.get("motivo_do_fecho") or "",
        }
    return {
        "tipo": "brusco",
        "iniciado_em": anterior.get("iniciado_em") or "?",
        "pid": pid,
    }


def registar_arranque():
    """Marca este arranque no disco e diz como terminou o anterior. Uma vez por processo.

    Idempotente de proposito: tanto serve o arranque a serio (app.py, na thread
    principal) como a primeira rodada, que garante que a marca existe mesmo
    quando o servidor subiu por outro caminho. Fora da thread principal os
    handlers de sinal nao podem ser instalados - o registo fica sem despedida e
    o arranque seguinte le-o como fecho brusco, que e a verdade.
    """
    global _registo
    if _registo is not None:
        return _registo
    anterior = _ler()
    _registo = {
        "pid": os.getpid(),
        "iniciado_epoch": ARRANQUE,
        "iniciado_em": _texto(),
        "veredicto": _veredicto(anterior),
        "anterior": anterior,
    }
    _gravar({
        "pid": _registo["pid"],
        "iniciado_epoch": ARRANQUE,
        "iniciado_em": _registo["iniciado_em"],
        "encerrado_em": "",
        "motivo_do_fecho": "",
    })
    _vigiar_o_fecho()
    return _registo
