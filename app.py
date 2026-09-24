
import os
from src.backend.config import APP_ROOT, DATA_DIR, carregar_env

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")

carregar_env()

from src.backend.services.aceleracao import preparar as _registar_runtime_cuda

_registar_runtime_cuda()

import sys
import logging

from flask import cli

from src.backend.memory.vector import preaquecer_mempalace
from src.backend.services.persistencia import limpar_temporarios_orfaos
from src.backend.services.envio_automatico import iniciar_vigia_do_envio
from src.backend.services.session import pasta_session_logs_em
from src.backend.services.settings import migrar_automatico_padrao
from src.backend.routes.static import static_bp
from src.backend.routes.chat import chat_bp
from src.backend.routes.terminal import terminal_bp
from src.backend.routes.editor import editor_bp
from src.backend.routes.files import files_bp
from src.backend.routes.session import session_bp
from src.backend.routes.git_panel import git_bp
from src.backend.routes.settings import settings_bp
from src.backend.routes.cofre import cofre_bp
from src.backend.routes.projeto import projeto_bp
from src.backend.routes.viewer import viewer_bp

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

from src.backend.extensions import app, socketio

app.register_blueprint(static_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(terminal_bp)
app.register_blueprint(editor_bp)
app.register_blueprint(files_bp)
app.register_blueprint(session_bp)
app.register_blueprint(git_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(cofre_bp)
app.register_blueprint(projeto_bp)
app.register_blueprint(viewer_bp)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
cli.show_server_banner = lambda *args: None

if __name__ == '__main__':
    recolhidos = limpar_temporarios_orfaos([DATA_DIR, pasta_session_logs_em(APP_ROOT)])
    if recolhidos:
        print(f"[limpeza] {recolhidos} temporario(s) orfao(s) de escrita recolhido(s)")
    migrar_automatico_padrao()
    preaquecer_mempalace()
    iniciar_vigia_do_envio()
    socketio.run(app, port=5000, debug=False, allow_unsafe_werkzeug=True)