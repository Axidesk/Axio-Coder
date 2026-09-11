#cd coder
#npm start

import os
from src.backend.config import carregar_env

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")

carregar_env()

import json
import time
import threading
import queue
import ast
import re
import subprocess
import socket
import shlex
import shutil
import sys
import logging
import base64
import locale
import unicodedata
import webbrowser
from flask import Flask, request, jsonify, Response, cli, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
import difflib

from src.backend.state import estado, emit_event, notificar_mudanca_arquivos, MAX_UNDO, memoria_lock, mineracao_em_andamento
from src.backend.services.file_service import dirs_leitura_extra, venv_projeto, resolver_caminho, resolver_caminho_arquivo, versao_pacote, entradas_diretorio, normalizar_unicode, aplicar_snapshot, registrar_edicao, capturar_snapshot, raiz_abs, raiz_lixeira, listar_lixeira, limpar_dirs_vazios, mover_para_lixeira, enviar_para_lixeira_sistema
from src.backend.services.diff import gerar_diff
from src.backend.tools.filesystem import tool_listar_pasta, tool_ler_arquivo, tool_ler_trecho_arquivo, tool_substituir_texto, tool_salvar_arquivo, tool_deletar_arquivo, tool_pesquisar_no_projeto, tool_ler_assinaturas, tool_analisar_simbolo, tool_substituir_tudo, tool_mapear_codigo, tool_planejar_arquitetura, tool_iniciar_plano, tool_atualizar_plano, tool_adicionar_etapa_plano
from src.backend.tools.refactor import tool_mover_funcao_verbatim, tool_verificar_integridade_refatoracao, tool_mover_bloco_verbatim, tool_mover_arquivo_binario
from src.backend.tools.process import tool_executar_comando, tool_executar_processo, tool_parar_processo, id_processo, matar_arvore, ler_saida_stream, montar_env_processo
from src.backend.tools.environment import tool_info_ambiente
from src.backend.tools.bootstrap import tool_gerenciar_bootstrap
from src.backend.tools.web import tool_buscar_web
from src.backend.tools.memory_tools import tool_gerenciar_memoria, tool_gerenciar_banco_vetorial
from src.backend.tools.audit import tool_corrigir_imports_js
from src.backend.memory.store import carregar_indice_knowledge
from src.backend.services.session import carregar_checkpoint, salvar_checkpoint, formatar_checkpoint, pasta_session_logs, caminho_checkpoint_state, ts_de_arquivo_log, ler_log_sessao, prune_session_logs, criar_sessao_vazia, summary_de_logs, reconciliar_snapshot_com_disco, marcar_delecoes_manuais, snapshot_sessao_anterior, primeira_aparicao_por_arquivo, criados_depois_de, propagar_rename_logs, marcar_deletado_logs, carregar_snapshot_restauracao
from src.backend.services.process_manager import pty_lock, pty_kill_locked, cwd_atual, detectar_shell, shell_caminho, comando_inicia_axio
from src.backend.memory.vector import garantir_patch_mempalace, wing_da_pasta, preaquecer_mempalace, espelhar_notas_existentes, minerar_em_segundo_plano, buscar_memorias_com_timeout
from src.backend.ai.context import ErroContextoExcedido, eh_erro_contexto_limite, eh_erro_transitorio, truncar_cabeca_cauda, compactar_historico, texto_de_content, texto_completo_de_content, tokens_historico, obter_encoder_tokens, contar_tokens, resumir_com_llm, podar_historico_global, texto_de_ferramentas, medir_contexto, LIMITE_TOKENS_HISTORICO_GLOBAL, MANTER_RECENTES_GLOBAL, token_encoder
from src.backend.ai.base import chamar_api_com_retry, converter_schema_google_para_openai
from src.backend.ai.loop import loop_raciocinio_ia
from src.backend.routes.static import static_bp
from src.backend.routes.chat import chat_bp
from src.backend.routes.terminal import terminal_bp
from src.backend.routes.editor import editor_bp
from src.backend.routes.files import files_bp
from src.backend.routes.session import session_bp
from src.backend.routes.settings import settings_bp

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
app.register_blueprint(settings_bp)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
cli.show_server_banner = lambda *args: None

USAR_DEEPSEEK = os.getenv("USAR_DEEPSEEK", "False").lower() == "true"

if __name__ == '__main__':
    preaquecer_mempalace()
    socketio.run(app, port=5000, debug=False, allow_unsafe_werkzeug=True)