import os
import re
import time
import json

from flask import Blueprint, request, jsonify
from src.backend.state import estado, caminho_estado_projeto
from src.backend.services.session import (
    pasta_session_logs,
    ts_de_arquivo_log,
    ler_log_sessao,
    prune_session_logs,
    summary_de_logs,
    snapshot_sessao_anterior,
    reconciliar_snapshot_com_disco,
    marcar_delecoes_manuais,
    carregar_snapshot_restauracao,
    criados_depois_de,
    caminho_checkpoint_state,
)
from src.backend.services.file_service import (
    capturar_snapshot,
    registrar_edicao,
    mover_para_lixeira,
)

session_bp = Blueprint("session", __name__)
@session_bp.route('/api/session_log/save', methods=['POST'])
def session_log_save():
    pasta_raiz = estado.get("pasta_raiz", "")
    if not pasta_raiz:
        return jsonify({"status": "error", "message": "Nenhuma pasta selecionada"}), 400

    data = request.json or {}
    logs = data.get("logs") or []
    if not logs:
        return jsonify({"status": "empty"})

    pasta_logs = caminho_estado_projeto("chats", "session_logs")
    try:
        os.makedirs(pasta_logs, exist_ok=True)
    except OSError as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    # Sessão atual: um único id por execução do programa + pasta selecionada.
    # Diferente de antes, NÃO criamos um arquivo novo por turno — acumulamos tudo aqui.
    session_id = estado.get("session_id_atual") or ""
    if not session_id:
        session_id = str(int(time.time() * 1000))
        estado["session_id_atual"] = session_id

    caminho = os.path.join(pasta_logs, f"sessionlog_{session_id}.json")

    # Se a sessão já existe (edições anteriores do mesmo projeto em aberto), faz merge.
    payload = None
    if os.path.exists(caminho):
        try:
            payload = ler_log_sessao(caminho)
        except Exception:
            payload = None

    # Rotação por dia: cada card é atribuído à sessão do dia em que o turno
    # realmente começou (data derivada do id epoch do card). Cards de um mesmo
    # save são agrupados por dia, então um turno que cruze a meia-noite grava
    # cada parte na sua própria sessão do histórico — sem arrastar turnos do
    # dia seguinte para o dia anterior (nem o contrário).
    hoje = time.strftime("%d/%m/%Y")

    def _dia_do_grupo(grupo):
        try:
            m = re.search(r"(\d+)$", str((grupo or {}).get("id") or ""))
            if m:
                return time.strftime("%d/%m/%Y", time.localtime(int(m.group(1)) / 1000))
        except Exception:
            pass
        return hoje

    grupos_por_dia = {}
    for grupo in logs:
        grupos_por_dia.setdefault(_dia_do_grupo(grupo), []).append(grupo)

    # Snapshot cumulativo: herda o checkpoint da sessão mais recente (mesma pasta)
    # e sobrescreve com os arquivos tocados nesta sessão. Assim, restaurar uma
    # tarefa antiga também restaura arquivos que ela não editou, mas que já existiam
    # naquele ponto — evita deixar arquivos "no futuro" de forma inconsistente.
    snapshot_anterior = {}
    if payload is not None and payload.get("logs"):
        snapshot_anterior = payload.get("snapshot") or {}
    else:
        snapshot_anterior = snapshot_sessao_anterior(pasta_logs, session_id)
        snapshot_anterior = reconciliar_snapshot_com_disco(snapshot_anterior)

    snapshot_anterior = marcar_delecoes_manuais(snapshot_anterior)
    snapshot_cumulativo = {**snapshot_anterior, **capturar_snapshot()}

    filenames = []
    for dia, grupos_dia in grupos_por_dia.items():
        sid = estado.get("session_id_atual") or ""
        caminho_dia = os.path.join(pasta_logs, f"sessionlog_{sid}.json") if sid else ""
        pay_dia = None
        if sid and os.path.exists(caminho_dia):
            try:
                pay_dia = ler_log_sessao(caminho_dia)
            except Exception:
                pay_dia = None
            data_sessao = (pay_dia.get("datetime") or "").split(" ")[0] if pay_dia else ""
            if data_sessao and data_sessao != dia:
                sid = ""
                pay_dia = None

        if not sid:
            sid = str(int(time.time() * 1000))
            estado["session_id_atual"] = sid
            pay_dia = None

        if pay_dia is None:
            ts_criacao = int(sid)
            pay_dia = {
                "timestamp": ts_criacao,
                "datetime": time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(ts_criacao / 1000)),
                "summary": "",
                "logs": [],
            }

        for grupo in grupos_dia:
            grupo["snapshot"] = snapshot_cumulativo
        pay_dia["logs"].extend(grupos_dia)
        pay_dia["summary"] = summary_de_logs(pay_dia["logs"]) or (data.get("summary") or "").strip()[:160]
        pay_dia["snapshot"] = snapshot_cumulativo

        caminho_dia = os.path.join(pasta_logs, f"sessionlog_{sid}.json")
        try:
            with open(caminho_dia, "w", encoding="utf-8") as f:
                json.dump(pay_dia, f, ensure_ascii=False, indent=2)
        except OSError as e:
            return jsonify({"status": "error", "message": str(e)}), 500
        filenames.append(f"sessionlog_{sid}.json")

    # Mantém apenas os logs dos últimos 3 dias distintos (substitui os mais antigos).
    prune_session_logs(pasta_logs, manter_dias=3)
    return jsonify({"status": "ok", "filename": filenames[-1] if filenames else ""})

@session_bp.route('/api/session_history', methods=['GET'])
def session_history():
    pasta_logs = pasta_session_logs()
    if not pasta_logs or not os.path.exists(pasta_logs):
        return jsonify({"sessions": []})

    try:
        arquivos = [f for f in os.listdir(pasta_logs) if f.startswith("sessionlog_") and f.endswith(".json")]
    except OSError:
        return jsonify({"sessions": []})

    arquivos.sort(key=ts_de_arquivo_log, reverse=True)

    # Mostra TODAS as sessões (incluindo a em andamento). O prune já limita os
    # arquivos em disco aos últimos 3 dias, então devolvemos todos sem cortar
    # (assim um dia com várias sessões não esconde um dia mais antigo).
    recentes = arquivos

    session_id_atual = estado.get("session_id_atual") or ""
    arquivo_atual = f"sessionlog_{session_id_atual}.json" if session_id_atual else ""

    sessoes = []
    for arq in recentes:
        caminho = os.path.join(pasta_logs, arq)
        ts = ts_de_arquivo_log(arq)
        data_hora = ""
        preview = ""
        try:
            dados = ler_log_sessao(caminho)
            ts = dados.get("timestamp", ts)
            data_hora = dados.get("datetime", "")
            preview = dados.get("summary", "")
            if not data_hora and ts:
                data_hora = time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(ts / 1000))
        except Exception as e:
            print(f"Erro ao ler log de sessão {arq}: {e}")
            if ts:
                data_hora = time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(ts / 1000))

        sessoes.append({
            "filename": arq,
            "timestamp": ts,
            "datetime": data_hora,
            "preview": preview,
            "current": arq == arquivo_atual
        })

    return jsonify({"sessions": sessoes})

@session_bp.route('/api/session_detail', methods=['GET'])
def session_detail():
    filename = request.args.get("file", "")
    pasta_logs = pasta_session_logs()
    if not pasta_logs or not filename:
        return jsonify({"error": "parâmetro inválido"}), 400

    filename = os.path.basename(filename)
    caminho = os.path.join(pasta_logs, filename)
    if not os.path.exists(caminho):
        return jsonify({"error": "sessão não encontrada"}), 404

    try:
        dados = ler_log_sessao(caminho)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    snapshot = dados.get("snapshot") or {}
    snapshot_files = []
    for rel, info in snapshot.items():
        removido = isinstance(info, dict) and info.get("conteudo") is None
        snapshot_files.append({"caminho": rel, "removido": removido})

    logs = dados.get("logs", [])
    # Compatibilidade: sessões salvas antes da Fase 2 não têm snapshot por tarefa.
    # Usa o snapshot final da sessão como fallback para que a restauração por tarefa
    # continue funcionando nesses casos.
    for grupo in logs:
        if "snapshot" not in grupo or not grupo.get("snapshot"):
            grupo["snapshot"] = snapshot

    return jsonify({
        "filename": filename,
        "datetime": dados.get("datetime", ""),
        "summary": dados.get("summary", ""),
        "logs": logs,
        "snapshot_files": snapshot_files
    })

def _gravar_payload(caminho, payload):
    """Grava o payload JSON de um log de sessao.

    Devolve uma resposta 500 pronta em caso de OSError; None em caso de sucesso.
    """
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    return None

@session_bp.route('/api/session_log/toggle_save', methods=['POST'])
def session_log_toggle_save():
    """Marca/desmarca uma tarefa (round) como salva, de forma persistente.

    Tarefas salvas não são removidas pela rotação dos 3 dias e aparecem no
    card "Salvo" do histórico.
    """
    pasta_logs = pasta_session_logs()
    if not pasta_logs or not os.path.exists(pasta_logs):
        return jsonify({"status": "error", "message": "Nenhum log encontrado"}), 400

    data = request.json or {}
    filename = os.path.basename(data.get("filename", ""))
    round_id = str(data.get("round_id", ""))
    if not filename or not round_id:
        return jsonify({"status": "error", "message": "parâmetro inválido"}), 400

    caminho = os.path.join(pasta_logs, filename)
    if not os.path.exists(caminho):
        return jsonify({"status": "error", "message": "sessão não encontrada"}), 404

    try:
        payload = ler_log_sessao(caminho)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    novo_valor = None
    for grupo in payload.get("logs", []):
        if str(grupo.get("id", "")) == round_id:
            grupo["salvo"] = not bool(grupo.get("salvo"))
            novo_valor = grupo["salvo"]
            break

    if novo_valor is None:
        return jsonify({"status": "error", "message": "tarefa não encontrada"}), 404

    erro = _gravar_payload(caminho, payload)
    if erro:
        return erro
    return jsonify({"status": "ok", "salvo": novo_valor})

@session_bp.route('/api/session_log/delete', methods=['POST'])
def session_log_delete():
    """Exclui logs de sessão (arquivos inteiros do histórico) e/ou cards (turnos)
    individuais, da sessão atual ou de sessões do histórico, conforme recebido do frontend."""
    pasta_logs = pasta_session_logs()
    if not pasta_logs or not os.path.exists(pasta_logs):
        return jsonify({"status": "error", "message": "Nenhum log para excluir"}), 400

    data = request.json or {}
    files = data.get("files") or []
    turn_ids = [str(x) for x in (data.get("turn_ids") or [])]
    turns = data.get("turns") or []  # [{"filename": "...", "turn_id": "..."}]

    deletados = 0

    def _remover_turnos_de_arquivo(nome_arquivo, ids):
        nonlocal deletados
        nome = os.path.basename(nome_arquivo)
        if not (nome.startswith("sessionlog_") and nome.endswith(".json")):
            return
        caminho = os.path.join(pasta_logs, nome)
        if not os.path.exists(caminho):
            return
        try:
            payload = ler_log_sessao(caminho)
            logs = payload.get("logs", [])
            antes = len(logs)
            ids_set = set(ids)
            payload["logs"] = [g for g in logs if str(g.get("id")) not in ids_set]
            payload["summary"] = summary_de_logs(payload["logs"])
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            deletados += antes - len(payload["logs"])
        except Exception as e:
            print(f"Erro ao excluir turnos de {nome}: {e}")

    # 1) Exclui sessões inteiras (histórico).
    for nome in files:
        nome = os.path.basename(nome)
        if not (nome.startswith("sessionlog_") and nome.endswith(".json")):
            continue
        caminho = os.path.join(pasta_logs, nome)
        try:
            if os.path.exists(caminho):
                os.remove(caminho)
                deletados += 1
                # Se apagou a sessão em andamento, recomeça uma sessão nova no próximo turno.
                if nome == f"sessionlog_{estado.get('session_id_atual', '')}.json":
                    estado["session_id_atual"] = ""
        except OSError as e:
            print(f"Erro ao excluir sessão {nome}: {e}")

    # 2) Exclui cards (turnos) individuais da sessão atual (compatibilidade).
    if turn_ids:
        session_id = estado.get("session_id_atual") or ""
        if session_id:
            _remover_turnos_de_arquivo(f"sessionlog_{session_id}.json", turn_ids)

    # 3) Exclui cards (turnos) individuais de sessões do histórico.
    for t in turns:
        if not isinstance(t, dict):
            continue
        filename = str(t.get("filename") or "")
        turn_id = str(t.get("turn_id") or "")
        if filename and turn_id:
            _remover_turnos_de_arquivo(filename, [turn_id])

    return jsonify({"status": "ok", "deleted": deletados})

@session_bp.route('/api/session_log/rename', methods=['POST'])
def session_log_rename():
    """Renomeia uma rodada (card de log) pelo id, persistindo o nome personalizado."""
    pasta_logs = pasta_session_logs()
    if not pasta_logs or not os.path.exists(pasta_logs):
        return jsonify({"status": "error", "message": "Nenhum log para renomear"}), 400

    data = request.json or {}
    round_id = str(data.get("round_id") or "")
    name = (data.get("name") or "").strip()
    if not round_id or not name:
        return jsonify({"status": "error", "message": "round_id e name são obrigatórios"}), 400

    try:
        arquivos = [f for f in os.listdir(pasta_logs) if f.startswith("sessionlog_") and f.endswith(".json")]
    except OSError as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    for arq in arquivos:
        caminho = os.path.join(pasta_logs, arq)
        try:
            payload = ler_log_sessao(caminho)
        except Exception:
            continue

        logs = payload.get("logs", [])
        alterado = False
        for grupo in logs:
            if str(grupo.get("id")) == round_id:
                grupo["name"] = name
                alterado = True

        if alterado:
            erro = _gravar_payload(caminho, payload)
            if erro:
                return erro
            return jsonify({"status": "ok", "name": name})

    return jsonify({"status": "error", "message": "Tarefa não encontrada"}), 404

def _preparar_restauracao():
    """Valida pasta/filename e carrega o snapshot para as rotas de restauracao.

    Devolve (pasta_raiz, data, pasta_logs, snapshot, erro_response). Quando
    erro_response nao e None, o chamador deve devolve-lo imediatamente.
    """
    pasta_raiz = estado.get("pasta_raiz", "")
    if not pasta_raiz:
        return None, None, None, None, (jsonify({"status": "error", "message": "Nenhuma pasta selecionada"}), 400)

    data = request.json or {}
    filename = os.path.basename(data.get("filename") or "")
    if not filename:
        return None, None, None, None, (jsonify({"status": "error", "message": "filename obrigatório"}), 400)

    pasta_logs = pasta_session_logs()
    dados, snapshot, erro = carregar_snapshot_restauracao(
        pasta_logs, filename, data.get("round_id") or ""
    )
    if erro:
        codigo = 404 if erro == "Sessão não encontrada" else 500
        return None, None, None, None, (jsonify({"status": "error", "message": erro}), codigo)
    return pasta_raiz, data, pasta_logs, snapshot, None

def _ler_conteudo_atual(alvo):
    if not os.path.exists(alvo):
        return None
    try:
        with open(alvo, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None

def _iter_itens_snapshot(pasta_raiz, snapshot):
    """Itera (rel, conteudo, alvo, atual) dos arquivos de um snapshot de restauracao.

    `conteudo` e None quando o arquivo nao existia no checkpoint; `atual` e o
    conteudo atual no disco (ou None se ausente/ilegivel).
    """
    for rel, info in snapshot.items():
        conteudo = info.get("conteudo") if isinstance(info, dict) else None
        alvo = os.path.abspath(os.path.join(pasta_raiz, rel.replace("/", os.sep)))
        yield rel, conteudo, alvo, _ler_conteudo_atual(alvo)

@session_bp.route('/api/session_restore_preview', methods=['POST'])
def session_restore_preview():
    """Prévia da restauração (sem aplicar): lista os arquivos do checkpoint e os
    órfãos (criados após o ponto) que seriam removidos, para o modal de confirmação."""
    pasta_raiz, dados, pasta_logs, snapshot, erro = _preparar_restauracao()
    if erro:
        return erro

    restored = []
    kept = []
    for rel, conteudo, _alvo, atual in _iter_itens_snapshot(pasta_raiz, snapshot):
        if conteudo is None:
            if atual is not None:
                restored.append({"caminho": rel, "acao": "removido"})
            # Arquivo já apagado no disco e marcado como inexistente no
            # checkpoint: nada a fazer. Não o listamos em "Mantidos" para não
            # confundir (ele não existe mais e não seria recriado na restauração).
        else:
            if atual != conteudo:
                acao = "restaurado" if atual is not None else "recriado"
                restored.append({"caminho": rel, "acao": acao})
            else:
                kept.append(rel)

    orphans = []
    if snapshot:
        ts_alvo = dados.get("timestamp") or 0
        criados_depois = criados_depois_de(pasta_logs, snapshot, ts_alvo)
        for rel in sorted(criados_depois):
            alvo = os.path.abspath(os.path.join(pasta_raiz, rel.replace("/", os.sep)))
            if os.path.exists(alvo):
                orphans.append(rel)

    return jsonify({
        "status": "ok",
        "empty": not snapshot,
        "restored": restored,
        "kept": kept,
        "orphans": orphans
    })

@session_bp.route('/api/checkpoint_state', methods=['GET'])
def checkpoint_state_get():
    """Lê o id do checkpoint restaurado atual (persistido por projeto)."""
    caminho = caminho_checkpoint_state()
    if not caminho or not os.path.exists(caminho):
        return jsonify({"checkpoint_id": None, "checkpoint_restored_at": 0, "discarded_rounds": []})
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return jsonify({
            "checkpoint_id": dados.get("checkpoint_id") or None,
            "checkpoint_restored_at": dados.get("checkpoint_restored_at") or 0,
            "discarded_rounds": dados.get("discarded_rounds") or [],
        })
    except Exception:
        return jsonify({"checkpoint_id": None, "checkpoint_restored_at": 0, "discarded_rounds": []})

@session_bp.route('/api/checkpoint_state', methods=['POST'])
def checkpoint_state_set():
    """Persiste o id do checkpoint restaurado atual (ou null para limpar)."""
    caminho = caminho_checkpoint_state()
    if not caminho:
        return jsonify({"status": "error", "message": "Nenhuma pasta selecionada"}), 400
    data = request.json or {}
    checkpoint_id = data.get("checkpoint_id") or None
    checkpoint_restored_at = data.get("checkpoint_restored_at") or 0
    discarded_rounds = data.get("discarded_rounds") or []
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump({
                "checkpoint_id": checkpoint_id,
                "checkpoint_restored_at": checkpoint_restored_at,
                "discarded_rounds": discarded_rounds,
            }, f, ensure_ascii=False, indent=2)
        return jsonify({"status": "ok"})
    except OSError as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@session_bp.route('/api/session_restore', methods=['POST'])
def session_restore():
    """Restaura o código dos arquivos tocados para o estado do checkpoint salvo
    na sessão de log informada. Antes de sobrescrever, registra o estado atual no
    histórico de undo para que a restauração possa ser desfeita (porto seguro).
    """
    pasta_raiz, data, pasta_logs, snapshot, erro = _preparar_restauracao()
    if erro:
        return erro

    if not snapshot:
        return jsonify({"status": "empty", "message": "Esta tarefa/sessão não possui checkpoint de código para restaurar."})

    alterados = []
    for rel, conteudo, alvo, atual in _iter_itens_snapshot(pasta_raiz, snapshot):
        if conteudo is None:
            # No checkpoint o arquivo não existia -> remove o arquivo atual.
            if atual is not None:
                registrar_edicao(alvo, atual, None)
                try:
                    mover_para_lixeira(alvo)
                except OSError as e:
                    return jsonify({"status": "error", "message": str(e)}), 500
                alterados.append({"nome": rel, "acao": "removido"})
        else:
            if atual != conteudo:
                # Porto seguro: registra o estado atual antes de sobrescrever.
                registrar_edicao(alvo, atual, conteudo)
                diretorio = os.path.dirname(alvo)
                if diretorio:
                    os.makedirs(diretorio, exist_ok=True)
                with open(alvo, "w", encoding="utf-8") as f:
                    f.write(conteudo)
                alterados.append({"nome": rel, "acao": "restaurado" if atual is not None else "recriado"})

    # Fecha a Fase 2: remove arquivos criados após o ponto restaurado para evitar
    # "arquivos órfãos" (ex.: um import que passou a apontar para um módulo criado
    # depois do checkpoint). Só tocamos arquivos que o sistema já conhece (rastreados),
    # nunca arquivos alheios ao controle de versão.
    criados_depois = criados_depois_de(pasta_logs, snapshot, data.get("timestamp") or 0)
    for rel in sorted(criados_depois):
        alvo = os.path.abspath(os.path.join(pasta_raiz, rel.replace("/", os.sep)))
        atual = _ler_conteudo_atual(alvo)
        if atual is None:
            continue  # Ausente, ilegível ou binário; nada a remover.
        registrar_edicao(alvo, atual, None)
        try:
            mover_para_lixeira(alvo)
        except OSError as e:
            return jsonify({"status": "error", "message": str(e)}), 500
        alterados.append({"nome": rel, "acao": "removido (criado após o ponto)"})

    return jsonify({"status": "ok", "altered": alterados, "count": len(alterados)})
