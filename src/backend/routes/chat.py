import os
import time
import threading
import queue

from flask import Blueprint, request, jsonify, Response

from src.backend.state import estado, emit_event, caminho_estado_projeto, registrar_subscriber, remover_subscriber, limpar_eventos
from src.backend.services.process_manager import pty_lock, pty_kill_locked
from src.backend.tools.process import parar_processo_reg
from src.backend.services.session import criar_sessao_vazia, migrar_session_logs_antigos
from src.backend.services.session_index import preaquecer_indices_de_sessao
from src.backend.ai.context import medir_contexto, truncar_mensagem_historico
from src.backend.ai.loop import loop_raciocinio_ia
from src.backend.services.file_watcher import iniciar_watcher
from src.backend.services.settings import atualizar_settings, load_settings

chat_bp = Blueprint("chat", __name__)
@chat_bp.route('/api/stream')
def stream():
    def event_stream():
        fila = registrar_subscriber()
        try:
            medir_contexto()
            while True:
                try:
                    yield fila.get(timeout=1)
                except queue.Empty:
                    yield ":\n\n"
        except (GeneratorExit, ConnectionError, BrokenPipeError, OSError):
            return
        finally:
            remover_subscriber(fila)
    return Response(event_stream(), mimetype="text/event-stream")

@chat_bp.route('/api/set_folder', methods=['POST'])
def set_folder():
    from google.genai import types
    from src.backend.tools.projeto_info import preaquecer_info_projeto
    data = request.json
    pasta = data.get("folder")
    if pasta:
        pasta_anterior = estado.get("pasta_raiz", "")
        atualizar_settings({"projeto": {"ultima_pasta": pasta}})
        if pasta == pasta_anterior:
            preaquecer_info_projeto(pasta)
            return jsonify({"folder": pasta, "status": "ready"})
        estado["pasta_raiz"] = pasta
        migrar_session_logs_antigos()
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
        parados = 0
        arvore_morta = 0
        sobreviventes = []
        for pid, reg in list(estado.get("processos", {}).items()):
            try:
                resultado = parar_processo_reg(pid, reg)
            except Exception:
                continue
            alvos = [item for item in resultado.get("alvos", []) if item.get("existe")]
            if alvos:
                parados += 1
                arvore_morta += len(alvos)
            sobreviventes.extend(resultado.get("sobraram", []))
        estado["processos"] = {}
        estado["session_id_atual"] = str(int(time.time() * 1000))
        criar_sessao_vazia(pasta, estado["session_id_atual"])
        
        pasta_chats = caminho_estado_projeto("chats")
        if os.path.exists(pasta_chats):
            arquivos_chat = [f for f in os.listdir(pasta_chats) if f.startswith("sessao_") and f.endswith(".txt")]
            if arquivos_chat:
                arquivos_chat.sort()
                arquivos_recentes = arquivos_chat[-5:]
                for arq in arquivos_recentes:
                    arquivo_path = os.path.join(pasta_chats, arq)
                    try:
                        with open(arquivo_path, "r", encoding="utf-8") as f:
                            conteudo = f.read()
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

        limpar_eventos()
        preaquecer_info_projeto(pasta)
        preaquecer_indices_de_sessao()
        return jsonify({"folder": pasta, "status": "ready", "processos_parados": parados,
                        "arvore_morta": arvore_morta, "sobreviventes": sobreviventes})
    return jsonify({"error": "Nenhuma pasta fornecida"}), 400

def _correr_loop(mensagem, modo, imagens_b64, use_deepseek, turn_id, ai_model="gemini"):
    """Corre o loop do turno com a marca de ocupacao, limpa em QUALQUER saida.

    O loop tem varios returns antecipados (cancelamento) e pode estourar excecao:
    marcar o fim dentro dele exigiria tocar em todos esses caminhos. Envolver a
    chamada aqui garante que a marca cai sempre, sem mexer no motor da IA.
    """
    estado["turno_ocupado"] = True
    try:
        loop_raciocinio_ia(mensagem, modo, imagens_b64, use_deepseek, turn_id, ai_model)
    finally:
        estado["turno_ocupado"] = False


@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    mensagem = data.get("message", "")
    modo = data.get("mode", "auto")
    use_deepseek = data.get("use_deepseek", False)
    ai_model = data.get("ai_model", "gemini")
    imagens_b64 = data.get("images", [])
    turn_id = data.get("turn_id") or str(int(time.time() * 1000))
    if not estado.get("pasta_raiz"):
        emit_event("status", message="Erro: Selecione uma pasta no rodapé primeiro.")
        return jsonify({"error": "Pasta não configurada"}), 400

    if estado.get("etiquetando"):
        return jsonify({"error": "Aguarde a conclusao da etiquetagem do projeto."}), 409

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

    threading.Thread(target=_correr_loop, args=(mensagem, modo, imagens_b64, use_deepseek, turn_id, ai_model), daemon=True).start()
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
