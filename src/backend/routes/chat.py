import os
import time
import threading
import queue

from flask import Blueprint, request, jsonify, Response

from src.backend.state import estado, emit_event, caminho_estado_projeto
from src.backend.services.process_manager import pty_lock, pty_kill_locked
from src.backend.tools.process import matar_arvore
from src.backend.services.session import criar_sessao_vazia
from src.backend.ai.context import medir_contexto, truncar_mensagem_historico
from src.backend.ai.loop import loop_raciocinio_ia
from src.backend.services.file_watcher import iniciar_watcher
from src.backend.services.settings import load_settings

chat_bp = Blueprint("chat", __name__)
@chat_bp.route('/api/stream')
def stream():
    def event_stream():
        # Emite o estado atual do contexto assim que o frontend conecta, para que
        # o tooltip do spinner nunca apareça vazio (mesmo com 0 tokens usados).
        medir_contexto()
        while True:
            try:
                msg = estado["event_queue"].get(timeout=1)
                yield msg
            except queue.Empty:
                yield ":\n\n"
    return Response(event_stream(), mimetype="text/event-stream")

@chat_bp.route('/api/set_folder', methods=['POST'])
def set_folder():
    from google.genai import types
    data = request.json
    pasta = data.get("folder")
    if pasta:
        pasta_anterior = estado.get("pasta_raiz", "")
        # Re-selecionar a MESMA pasta mantém o histórico em RAM intacto.
        if pasta == pasta_anterior:
            emit_event("status", message=f"Diretório já carregado: {pasta}")
            return jsonify({"folder": pasta, "status": "ready"})
        estado["pasta_raiz"] = pasta
        estado["cwd_terminal"] = ""
        estado["projeto_planejado"] = False
        iniciar_watcher()
        with pty_lock:
            pty_kill_locked()
        estado["historico_chat"] = []
        estado["file_history"] = {}
        estado["arquivos_tocados"] = set()
        estado["edicoes_rodada"] = []
        estado["compactacoes_contexto"] = 0
        # Trocar de pasta (ou reiniciar o programa) inicia outra sessão.
        for pid, reg in list(estado.get("processos", {}).items()):
            popen = reg.get("popen")
            if popen is not None:
                try:
                    if popen.poll() is None:
                        matar_arvore(popen)
                except Exception:
                    pass
                reg["status"] = "parado"
                emit_event("process_finished", pid=pid, exit_code=None, status="parado")
        estado["processos"] = {}
        estado["session_id_atual"] = str(int(time.time() * 1000))
        # Cria já o arquivo vazio da sessão para o card "em andamento" surgir
        # no histórico imediatamente, e a sessão anterior virar "anteriores".
        criar_sessao_vazia(pasta, estado["session_id_atual"])
        
        # Tentar carregar o histórico da sessão mais recente
        pasta_chats = caminho_estado_projeto("chats")
        if os.path.exists(pasta_chats):
            arquivos_chat = [f for f in os.listdir(pasta_chats) if f.startswith("sessao_") and f.endswith(".txt")]
            if arquivos_chat:
                arquivos_chat.sort() # Ordem cronológica (mais antigo primeiro)
                arquivos_recentes = arquivos_chat[-5:] # Pega os últimos 5
                for arq in arquivos_recentes:
                    arquivo_path = os.path.join(pasta_chats, arq)
                    try:
                        with open(arquivo_path, "r", encoding="utf-8") as f:
                            conteudo = f.read()
                            # Parsear o conteúdo (formato: Humano: ... \nIA: ...)
                            partes = conteudo.split("Humano: ")
                            for parte in partes:
                                if not parte.strip(): continue
                                if "\nIA: " in parte:
                                    msg_humano, msg_ia = parte.split("\nIA: ", 1)
                                    msg_humano = truncar_mensagem_historico(msg_humano.strip())
                                    msg_ia = truncar_mensagem_historico(msg_ia.strip())
                                    estado["historico_chat"].append(types.Content(role="user", parts=[types.Part.from_text(text=msg_humano)]))
                                    estado["historico_chat"].append(types.Content(role="model", parts=[types.Part.from_text(text=msg_ia)]))
                    except Exception as e:
                        print(f"Erro ao carregar histórico {arq}: {e}")

        while not estado["event_queue"].empty():
            try: estado["event_queue"].get_nowait()
            except queue.Empty: break
        emit_event("status", message=f"Diretório carregado: {pasta}")
        return jsonify({"folder": pasta, "status": "ready"})
    return jsonify({"error": "Nenhuma pasta fornecida"}), 400

@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    mensagem = data.get("message", "")
    modo = data.get("mode", "auto")
    use_deepseek = data.get("use_deepseek", False)
    imagens_b64 = data.get("images", [])
    turn_id = data.get("turn_id") or str(int(time.time() * 1000))
    if not estado.get("pasta_raiz"):
        emit_event("status", message="Erro: Selecione uma pasta no rodapé primeiro.")
        return jsonify({"error": "Pasta não configurada"}), 400

    s = load_settings()
    if use_deepseek:
        if not (s.get("deepseek") or {}).get("api_key", "").strip():
            return jsonify({"error": "Defina a chave do modelo nas Configurações."}), 400
    else:
        gemini = s.get("gemini") or {}
        tem_studio = bool((gemini.get("studio_api_key") or "").strip())
        tem_vertex = gemini.get("mode") == "vertex" and bool(gemini.get("vertex_json"))
        if not tem_studio and not tem_vertex:
            return jsonify({"error": "Defina a chave do modelo nas Configurações."}), 400

    threading.Thread(target=loop_raciocinio_ia, args=(mensagem, modo, imagens_b64, use_deepseek, turn_id), daemon=True).start()
    return jsonify({"status": "processing", "turn_id": turn_id})

@chat_bp.route('/api/cancel', methods=['POST'])
def cancel():
    estado["cancel_requested"] = True
    return jsonify({"status": "cancelled"})

@chat_bp.route('/api/clear_context', methods=['POST'])
def clear_context():
    estado["historico_chat"] = []
    estado["compactacoes_contexto"] = 0
    medir_contexto()
    return jsonify({"status": "ok"})
