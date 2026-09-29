from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

def _tolerar_fecho_do_websocket():
    """Fechar um websocket cujo par ja desapareceu deixa de ser erro.

    Ao sair do Axio o Electron mata o processo do servidor (/T /F) e o cliente
    desaparece antes de o engineio fechar o socket: o close() do simple_websocket
    escreve no socket morto e levanta ConnectionAbortedError (WinError 10053)
    dentro da thread leitora do engineio, onde ninguem o apanha - sai um traceback
    no terminal a cada saida. Nao ha nada a recuperar: o par ja nao esta la, e o
    fecho passa a ser no-op.
    """
    try:
        from simple_websocket.ws import Server
    except Exception:
        return
    if getattr(Server, "_axio_fecho_tolerante", False):
        return

    original = Server.close

    def close(self, *args, **kwargs):
        try:
            return original(self, *args, **kwargs)
        except OSError:
            return None

    Server.close = close
    Server._axio_fecho_tolerante = True

_tolerar_fecho_do_websocket()

app = Flask(__name__, static_folder=None, template_folder=None)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
