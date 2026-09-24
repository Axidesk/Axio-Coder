import threading
import time
from datetime import date

from src.backend.services import git_repo
from src.backend.services.settings import git_automatico
from src.backend.state import estado

_INTERVALO = 60
_trava = threading.Lock()
_ultimo_dia = None


def enviar_pendentes():
    """Empurra o que estiver por subir, so com o modo automatico ligado. Devolve o resultado ou None."""
    if not git_automatico():
        return None
    pasta = estado.get("pasta_raiz", "") or ""
    if not pasta:
        return None
    if not git_repo.por_subir(pasta).get("count"):
        return None
    with _trava:
        return git_repo.empurrar(pasta)


def agendar_envio():
    """Envia em segundo plano, sem travar quem chamou (a abertura de uma pasta de projeto)."""
    threading.Thread(target=enviar_pendentes, daemon=True, name="envio-git-abertura").start()


def _vigia_da_virada_do_dia():
    global _ultimo_dia
    while True:
        time.sleep(_INTERVALO)
        hoje = date.today().isoformat()
        if _ultimo_dia is None or hoje == _ultimo_dia:
            _ultimo_dia = hoje
            continue
        _ultimo_dia = hoje
        try:
            enviar_pendentes()
        except Exception:
            continue


def iniciar_vigia_do_envio():
    """Arranca a vigia que envia na virada do dia, uma so vez por processo."""
    global _ultimo_dia
    if _ultimo_dia is not None:
        return False
    _ultimo_dia = date.today().isoformat()
    threading.Thread(target=_vigia_da_virada_do_dia, daemon=True, name="envio-git-virada").start()
    return True
