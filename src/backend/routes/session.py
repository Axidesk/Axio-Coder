import os
import re
import time
import json
import threading

from flask import Blueprint, request, jsonify
from src.backend.state import estado
from src.backend.services.session import (
    pasta_session_logs,
    migrar_session_logs_antigos,
    ts_de_arquivo_log,
    ler_log_sessao,
    ler_cabecalho_log_sessao,
    gravar_log_sessao,
    prune_session_logs,
    summary_de_logs,
    snapshot_sessao_anterior,
    snapshot_recomposto,
    reconciliar_snapshot_com_disco,
    marcar_delecoes_manuais,
    capturar_arvore,
    carregar_snapshot_restauracao,
    criados_depois_de,
    rastreados_fora_do_snapshot,
    varredura_dos_logs,
    caminho_checkpoint_state,
)
from src.backend.services.file_service import (
    capturar_snapshot,
    registrar_edicao,
    mover_para_lixeira,
)
from src.backend.memory.vector import limpar_drawers_de_sources
from src.backend.services.session_index import (
    atualizar_indice_de_payload,
    indice_de_log,
    rodada_completa_de_log,
)
from src.backend.tools.js_contrato import quebras_introduzidas

session_bp = Blueprint("session", __name__)

_RELS_SEGREDOS = {".env"}

def _registrar_segredos(snapshot, pasta_raiz):
    """Acrescenta ao snapshot os ficheiros de segredos que ainda nao tem registo.

    Preenche APENAS o que falta: sobrescrever um registo existente faria a
    gravacao seguinte a um restauro destruir a unica copia da versao viva - que e
    exactamente o que aqui se quer preservar.
    """
    for rel in sorted(_RELS_SEGREDOS):
        if rel in snapshot:
            continue
        conteudo = _ler_conteudo_atual(os.path.join(pasta_raiz, rel.replace("/", os.sep)))
        if conteudo is not None:
            snapshot[rel] = {"conteudo": conteudo}

def _preservar_segredos_no_checkpoint_atual(pasta_logs, pasta_raiz):
    """Grava a versao VIVA dos segredos no checkpoint da sessao atual.

    Corre antes de aplicar um restauro. Sem isto, repor o `.env` da era antiga
    deixaria a versao viva apenas na lixeira e voltar ao card de agora nao a
    devolveria: o checkpoint atual carrega o mesmo registo antigo que a heranca
    alcanca (medido em 13/09/2026: 1031 chars de 17/08 contra 1239 no disco).
    Gravada aqui, a versao viva faz do card de agora um ponto de retorno que
    devolve mesmo as chaves de agora.
    """
    sid = estado.get("session_id_atual") or ""
    if not sid:
        return
    caminho = os.path.join(pasta_logs, f"sessionlog_{sid}.json")
    if not os.path.exists(caminho):
        return
    vivos = {}
    for rel in sorted(_RELS_SEGREDOS):
        conteudo = _ler_conteudo_atual(os.path.join(pasta_raiz, rel.replace("/", os.sep)))
        if conteudo is not None:
            vivos[rel] = {"conteudo": conteudo}
    if not vivos:
        return
    try:
        payload = ler_log_sessao(caminho)
    except Exception:
        return
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict):
        snapshot.update(vivos)
    for grupo in payload.get("logs", []):
        do_grupo = grupo.get("snapshot")
        if isinstance(do_grupo, dict):
            do_grupo.update(vivos)
    _gravar_payload(caminho, payload)


def _commits_ja_gravados(pay_dia):
    """Hash que o log ja tem por turno, para uma regravacao nao perder o ponto ja atribuido."""
    mapa = {}
    for grupo in (pay_dia or {}).get("logs") or []:
        chave = str((grupo or {}).get("id") or "")
        if chave and grupo.get("commit"):
            mapa[chave] = grupo["commit"]
    return mapa


def _marcar_commit_do_agente(logs):
    """Da ao turno que fecha a rodada o commit que o AGENTE publicou nela.

    O commit feito no painel marca o proprio turno; o que o agente faz com
    tool_publicar_git nao tem como saber o turno, por isso deixa o hash aqui e a
    gravacao do log consome-o. E de uso unico: consumido ou nao, sai do estado,
    para um rastro velho nunca dar ponto a um turno de outra rodada."""
    pendente = estado.pop("commit_do_agente", None)
    if not pendente or not logs:
        return False
    grupo = logs[-1]
    if grupo.get("commit"):
        return False
    achado = re.search(r"(\d+)$", str(grupo.get("id") or ""))
    if not achado or int(achado.group(1)) > int(pendente.get("quando") or 0):
        return False
    grupo["commit"] = pendente.get("hash") or ""
    grupo["commit_nome"] = (pendente.get("mensagem") or "").strip()
    return True


@session_bp.route('/api/session_log/save', methods=['POST'])
def session_log_save():
    pasta_raiz = estado.get("pasta_raiz", "")
    if not pasta_raiz:
        return jsonify({"status": "error", "message": "Nenhuma pasta selecionada"}), 400

    data = request.json or {}
    logs = data.get("logs") or []
    if not logs:
        return jsonify({"status": "empty"})

    migrar_session_logs_antigos()
    pasta_logs = pasta_session_logs()
    try:
        os.makedirs(pasta_logs, exist_ok=True)
    except OSError as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    session_id = estado.get("session_id_atual") or ""
    if not session_id:
        session_id = str(int(time.time() * 1000))
        estado["session_id_atual"] = session_id

    caminho = os.path.join(pasta_logs, f"sessionlog_{session_id}.json")

    payload = None
    if os.path.exists(caminho):
        try:
            payload = ler_log_sessao(caminho)
        except Exception:
            payload = None

    hoje = time.strftime("%d/%m/%Y")

    def _dia_do_grupo(grupo):
        try:
            m = re.search(r"(\d+)$", str((grupo or {}).get("id") or ""))
            if m:
                return time.strftime("%d/%m/%Y", time.localtime(int(m.group(1)) / 1000))
        except Exception:
            pass
        return hoje

    _marcar_commit_do_agente(logs)

    grupos_por_dia = {}
    for grupo in logs:
        grupos_por_dia.setdefault(_dia_do_grupo(grupo), []).append(grupo)

    snapshot_anterior = {}
    if payload is not None and payload.get("logs"):
        snapshot_anterior = payload.get("snapshot") or {}
    else:
        snapshot_anterior = snapshot_recomposto(pasta_logs, caminho) or snapshot_sessao_anterior(pasta_logs, session_id)
        snapshot_anterior = reconciliar_snapshot_com_disco(snapshot_anterior)

    snapshot_anterior = marcar_delecoes_manuais(snapshot_anterior)
    snapshot_cumulativo = {
        **snapshot_anterior,
        **capturar_arvore(pasta_raiz, snapshot_anterior),
        **capturar_snapshot(),
    }
    _registrar_segredos(snapshot_cumulativo, pasta_raiz)

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

        ja_gravados = _commits_ja_gravados(pay_dia)
        for grupo in grupos_dia:
            if not grupo.get("commit"):
                anterior = ja_gravados.get(str(grupo.get("id") or ""))
                if anterior:
                    grupo["commit"] = anterior
            grupo["snapshot"] = snapshot_cumulativo
        pay_dia["logs"].extend(grupos_dia)
        pay_dia["summary"] = summary_de_logs(pay_dia["logs"]) or (data.get("summary") or "").strip()[:160]
        pay_dia["snapshot"] = snapshot_cumulativo

        caminho_dia = os.path.join(pasta_logs, f"sessionlog_{sid}.json")
        erro = _gravar_payload(caminho_dia, pay_dia)
        if erro:
            return erro
        filenames.append(f"sessionlog_{sid}.json")

    descartados = prune_session_logs(pasta_logs, manter_dias=3)
    if descartados:
        threading.Thread(target=limpar_drawers_de_sources, args=(descartados,), daemon=True).start()
    return jsonify({
        "status": "ok",
        "filename": filenames[-1] if filenames else "",
    })

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

    recentes = arquivos

    session_id_atual = estado.get("session_id_atual") or ""
    arquivo_atual = f"sessionlog_{session_id_atual}.json" if session_id_atual else ""

    sessoes = []
    for arq in recentes:
        ts = ts_de_arquivo_log(arq)
        cabecalho = ler_cabecalho_log_sessao(os.path.join(pasta_logs, arq))
        ts = cabecalho.get("timestamp", ts)
        data_hora = cabecalho.get("datetime", "")
        preview = cabecalho.get("summary", "")
        if not data_hora and ts:
            data_hora = time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(ts / 1000))

        sessoes.append({
            "filename": arq,
            "timestamp": ts,
            "datetime": data_hora,
            "preview": preview,
            "current": arq == arquivo_atual
        })

    return jsonify({"sessions": sessoes})

@session_bp.route('/api/sessions_index', methods=['GET'])
def sessions_index():
    """Indice leve de todas as sessoes: alimenta a pilha do historico e a busca."""
    pasta_logs = pasta_session_logs()
    if not pasta_logs or not os.path.exists(pasta_logs):
        return jsonify({"sessions": []})

    try:
        arquivos = [f for f in os.listdir(pasta_logs) if f.startswith("sessionlog_") and f.endswith(".json")]
    except OSError:
        return jsonify({"sessions": []})

    arquivos.sort(key=ts_de_arquivo_log, reverse=True)
    sessoes = []
    for arq in arquivos:
        indice = indice_de_log(os.path.join(pasta_logs, arq))
        sessoes.append({"filename": arq, "rounds": (indice or {}).get("rounds", [])})
    return jsonify({"sessions": sessoes})

@session_bp.route('/api/session_round', methods=['GET'])
def session_round():
    """Traz arquivos, diff e snapshot de UMA rodada, pedida ao abrir a tarefa na pilha."""
    filename = os.path.basename(request.args.get("file", ""))
    turn_id = request.args.get("id", "")
    pasta_logs = pasta_session_logs()
    if not pasta_logs or not filename or not turn_id:
        return jsonify({"error": "parâmetro inválido"}), 400

    caminho = os.path.join(pasta_logs, filename)
    if not os.path.exists(caminho):
        return jsonify({"error": "sessão não encontrada"}), 404

    try:
        rodada = rodada_completa_de_log(pasta_logs, filename, turn_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if rodada is None:
        return jsonify({"error": "tarefa não encontrada"}), 404
    return jsonify(rodada)

def _gravar_payload(caminho, payload):
    """Grava o payload JSON de um log de sessao.

    Devolve uma resposta 500 pronta em caso de OSError; None em caso de sucesso.
    """
    try:
        gravar_log_sessao(caminho, payload)
    except OSError as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    atualizar_indice_de_payload(caminho, payload)
    return None

def _ts_do_ponto(data):
    """Epoch (ms) do ponto a restaurar: o do `round_id`, com recuo para o timestamp.

    O `round_id` carrega o epoch do turno (`session-<ms>`) e e o instante exato do
    ponto; o `timestamp` do log e o do inicio da sessao e pode ser bem anterior
    (uma sessao longa guarda o turno das 04:01 num log aberto as 03:10).
    """
    rid = str((data or {}).get("round_id") or "")
    if "-" in rid:
        try:
            return int(rid.rsplit("-", 1)[1])
        except ValueError:
            pass
    try:
        return int((data or {}).get("timestamp") or 0)
    except (TypeError, ValueError):
        return 0

def _tocado_desde_ponto(pasta_raiz, rel, ts_ponto):
    """True quando o arquivo do disco foi modificado DEPOIS do ponto restaurado.

    O registo de um ficheiro pode estar a dias do ponto: uma edicao que nao passou
    por uma gravacao de checkpoint deixa o snapshot desatualizado, e a heranca
    alcanca uma versao anterior ao ponto. Repo-la seria uma regressao silenciosa --
    o ficheiro nunca foi tocado desde o ponto e devia ficar exatamente como esta. O
    mtime do disco e o sinal que separa os dois casos: posterior ao ponto -> o
    ficheiro mudou depois dele e volta atras; anterior -> ninguem lhe tocou.

    Medido em 13/09/2026 no checkpoint da tarefa 23: sem este corte apareciam 18
    ficheiros a restaurar (.env de 03/09, gemini.py e package.json de 05/09,
    findbar.js e highlight.js de 10/09, web.py de 11/09...), porque as edicoes
    recentes desses ficheiros nao estavam em snapshot nenhum; com ele sobram os
    que a sessao atual tocou.

    Arquivo ausente do disco conta como tocado: foi apagado depois do ponto e pode
    ter de ser recriado. Sem `ts_ponto` nao se corta nada.
    """
    if not ts_ponto:
        return True
    alvo = os.path.abspath(os.path.join(pasta_raiz, rel.replace("/", os.sep)))
    if not os.path.exists(alvo):
        return True
    try:
        return int(os.path.getmtime(alvo) * 1000) > ts_ponto
    except OSError:
        return False

def _snapshot_do_ponto(pasta_raiz, snapshot, ts_ponto):
    """Snapshot reduzido ao que foi mesmo tocado desde o ponto.

    O resto nao entra em lista nenhuma porque nao vai ser tocado: fica com o
    conteudo do disco, indistinguivel de um inalterado (ver `_tocado_desde_ponto`).
    """
    return {
        rel: meta for rel, meta in snapshot.items()
        if _tocado_desde_ponto(pasta_raiz, rel, ts_ponto)
    }

def _preparar_restauracao():
    """Valida pasta/filename e carrega o snapshot para as rotas de restauracao.

    Devolve (pasta_raiz, data, pasta_logs, snapshot, varredura, erro_response).
    Quando erro_response nao e None, o chamador deve devolve-lo imediatamente.

    `varredura` e a passagem pelos logs feita UMA vez para as duas leituras da
    restauracao: a heranca completa do snapshot (a ultima versao de cada ficheiro
    antes do ponto) e a classificacao dos rastreados (a primeira aparicao de cada
    um). E o mesmo trabalho, por isso sai daqui para nao ser feito duas vezes.
    """
    pasta_raiz = estado.get("pasta_raiz", "")
    if not pasta_raiz:
        return None, None, None, None, None, (jsonify({"status": "error", "message": "Nenhuma pasta selecionada"}), 400)

    data = request.json or {}
    filename = os.path.basename(data.get("filename") or "")
    if not filename:
        return None, None, None, None, None, (jsonify({"status": "error", "message": "filename obrigatório"}), 400)

    pasta_logs = pasta_session_logs()
    varredura = varredura_dos_logs(pasta_logs, filename)
    _, snapshot, erro = carregar_snapshot_restauracao(
        pasta_logs, filename, data.get("round_id") or "", varredura
    )
    if erro:
        codigo = 404 if erro == "Sessão não encontrada" else 500
        return None, None, None, None, None, (jsonify({"status": "error", "message": erro}), codigo)
    snapshot = _snapshot_do_ponto(pasta_raiz, snapshot, _ts_do_ponto(data))
    return pasta_raiz, data, pasta_logs, snapshot, varredura, None

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

def _quebras_da_restauracao(pasta_raiz, criados_depois, snapshot):
    """Quebras de contrato ESM que a restauracao introduziria (lista, talvez vazia).

    A restauracao repoe apenas os ficheiros que constam do checkpoint e remove os
    criados depois dele, o que pode deixar um modulo a importar de outro que ja
    nao lhe responde (ex.: um history.js de uma era a importar de um layout.js de
    outra). Em ES modules um import que nao resolve derruba o modulo inteiro e a
    interface fica muda, sem um erro no ecra. A medicao e por diferenca: so conta
    a quebra que a restauracao INTRODUZ (ver tools/js_imports.quebras_introduzidas).
    """
    projetado = {rel: conteudo for rel, conteudo, _alvo, _atual in _iter_itens_snapshot(pasta_raiz, snapshot)}
    for rel in sorted(criados_depois):
        projetado[rel] = None
    return quebras_introduzidas(pasta_raiz, projetado)

_LIMITE_AJUSTE_QUEBRAS = 60

def _preparar_snapshot_restauro(pasta_raiz, criados_depois, snapshot):
    """Ajusta o snapshot ao que pode mesmo ser reposto.

    Regra unica: ficheiro cuja versao registada esta incompativel com os modulos
    que ficam -- tipicamente uma versao anterior a migracao para ESM, sem os
    simbolos que os consumidores de agora importam -- fica com o conteudo do
    disco. A restauracao segue com os outros ficheiros em vez de ser recusada por
    inteiro por causa de um. Medido em 13/09/2026: o `highlight.js` e o
    `findbar.js` alcancados pela heranca cheia vinham de 10/09 (3273 e 13269
    chars, sem um unico `export`) e as 7 quebras que introduziam bloqueavam
    qualquer restauro, em qualquer tarefa do dia; devolvidos esses dois ao disco,
    as quebras vao a zero.

    O ajuste e SILENCIOSO: o ficheiro que sai do snapshot fica com o conteudo do
    disco e nao entra em lista nenhuma do modal. Nao e uma categoria nova -- para
    quem olha para o projeto, o ficheiro simplesmente nao foi tocado, como um
    inalterado. Se a projecao continuar quebrada mesmo depois do ajuste, devolve-se
    o que ha e o recuo final (recusar) fica com quem chamou.
    """
    ajustado = dict(snapshot)
    for _ in range(_LIMITE_AJUSTE_QUEBRAS):
        quebras = _quebras_da_restauracao(pasta_raiz, criados_depois, ajustado)
        if not quebras:
            return ajustado
        culpados = {q["modulo"] for q in quebras if q["modulo"] in ajustado}
        if not culpados:
            culpados = {q["arquivo"] for q in quebras if q["arquivo"] in ajustado}
        if not culpados:
            return ajustado
        for rel in sorted(culpados):
            ajustado.pop(rel, None)
    return ajustado

@session_bp.route('/api/session_restore_preview', methods=['POST'])
def session_restore_preview():
    """Prévia da restauração (sem aplicar): lista os arquivos do checkpoint e os
    órfãos (criados após o ponto) que seriam removidos, para o modal de confirmação."""
    pasta_raiz, dados, pasta_logs, snapshot, varredura, erro = _preparar_restauracao()
    if erro:
        return erro

    criados_depois = []
    if snapshot:
        ts_ponto = _ts_do_ponto(dados)
        criados_depois, fora = rastreados_fora_do_snapshot(
            pasta_logs, snapshot, dados.get("timestamp") or 0, varredura[0]
        )
        criados_depois = [r for r in criados_depois if _tocado_desde_ponto(pasta_raiz, r, ts_ponto)]
        fora = [r for r in fora if _tocado_desde_ponto(pasta_raiz, r, ts_ponto)]
        snapshot = _preparar_snapshot_restauro(pasta_raiz, criados_depois, snapshot)
    else:
        fora = []

    restored = []
    kept = []
    for rel, conteudo, _alvo, atual in _iter_itens_snapshot(pasta_raiz, snapshot):
        if conteudo is None:
            if atual is not None:
                restored.append({"caminho": rel, "acao": "removido"})
        else:
            if atual != conteudo:
                acao = "restaurado" if atual is not None else "recriado"
                restored.append({"caminho": rel, "acao": acao})
            else:
                kept.append(rel)

    orphans = []
    fora_do_alcance = []
    for rel in criados_depois:
        alvo = os.path.abspath(os.path.join(pasta_raiz, rel.replace("/", os.sep)))
        if os.path.exists(alvo):
            orphans.append(rel)
    for rel in fora:
        alvo = os.path.abspath(os.path.join(pasta_raiz, rel.replace("/", os.sep)))
        if os.path.exists(alvo):
            fora_do_alcance.append(rel)

    quebras = _quebras_da_restauracao(pasta_raiz, criados_depois, snapshot) if snapshot else []

    return jsonify({
        "status": "ok",
        "empty": not snapshot,
        "restored": restored,
        "kept": kept,
        "orphans": orphans,
        "fora_do_alcance": fora_do_alcance,
        "quebras": quebras
    })

@session_bp.route('/api/checkpoint_state', methods=['GET'])
def checkpoint_state_get():
    """Le o checkpoint restaurado atual (persistido por projeto) e o historico de
    restauros (`restores`: ts + checkpoint alvo), de onde o frontend deriva quais
    turnos tem o estado aplicado ao disco."""
    caminho = caminho_checkpoint_state()
    if not caminho or not os.path.exists(caminho):
        return jsonify({"checkpoint_id": None, "checkpoint_restored_at": 0, "restores": []})
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return jsonify({
            "checkpoint_id": dados.get("checkpoint_id") or None,
            "checkpoint_restored_at": dados.get("checkpoint_restored_at") or 0,
            "restores": dados.get("restores") or [],
        })
    except Exception:
        return jsonify({"checkpoint_id": None, "checkpoint_restored_at": 0, "restores": []})

def _normalizar_restauros(bruto):
    """Sanitiza o historico de restauros ({ts, checkpoint_id}).

    Cada restauro e um ramo do historico, e a linhagem do estado aplicado sai
    dele: uma entrada sem ts ou sem checkpoint tornaria o calculo indefinido no
    frontend, por isso entradas incompletas nao sao gravadas.
    """
    limpos = []
    for ev in bruto or []:
        if not isinstance(ev, dict):
            continue
        try:
            ts = int(ev.get("ts") or 0)
        except (TypeError, ValueError):
            continue
        alvo = str(ev.get("checkpoint_id") or "")
        if ts > 0 and alvo:
            limpos.append({"ts": ts, "checkpoint_id": alvo})
    return limpos

@session_bp.route('/api/checkpoint_state', methods=['POST'])
def checkpoint_state_set():
    """Persiste o id do checkpoint restaurado atual (ou null para limpar)."""
    caminho = caminho_checkpoint_state()
    if not caminho:
        return jsonify({"status": "error", "message": "Nenhuma pasta selecionada"}), 400
    data = request.json or {}
    checkpoint_id = data.get("checkpoint_id") or None
    checkpoint_restored_at = data.get("checkpoint_restored_at") or 0
    restores = _normalizar_restauros(data.get("restores"))
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump({
                "checkpoint_id": checkpoint_id,
                "checkpoint_restored_at": checkpoint_restored_at,
                "restores": restores,
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
    pasta_raiz, data, pasta_logs, snapshot, varredura, erro = _preparar_restauracao()
    if erro:
        return erro

    if not snapshot:
        return jsonify({"status": "empty", "message": "Esta tarefa/sessão não possui checkpoint de código para restaurar."})

    ts_ponto = _ts_do_ponto(data)
    criados_depois = criados_depois_de(pasta_logs, snapshot, data.get("timestamp") or 0, varredura[0])
    criados_depois = [r for r in criados_depois if _tocado_desde_ponto(pasta_raiz, r, ts_ponto)]

    snapshot = _preparar_snapshot_restauro(pasta_raiz, criados_depois, snapshot)

    quebras = _quebras_da_restauracao(pasta_raiz, criados_depois, snapshot)
    if quebras:
        return jsonify({
            "status": "blocked",
            "message": "Restauração cancelada: nada foi alterado.",
            "quebras": quebras[:40],
        }), 409

    _preservar_segredos_no_checkpoint_atual(pasta_logs, pasta_raiz)

    alterados = []
    for rel, conteudo, alvo, atual in _iter_itens_snapshot(pasta_raiz, snapshot):
        if conteudo is None:
            if atual is not None:
                registrar_edicao(alvo, atual, None)
                try:
                    mover_para_lixeira(alvo)
                except OSError as e:
                    return jsonify({"status": "error", "message": str(e)}), 500
                alterados.append({"nome": rel, "acao": "removido"})
        else:
            if atual != conteudo:
                registrar_edicao(alvo, atual, conteudo)
                if atual is not None and os.path.basename(rel) in _RELS_SEGREDOS:
                    try:
                        mover_para_lixeira(alvo)
                    except OSError as e:
                        return jsonify({"status": "error", "message": str(e)}), 500
                diretorio = os.path.dirname(alvo)
                if diretorio:
                    os.makedirs(diretorio, exist_ok=True)
                with open(alvo, "w", encoding="utf-8") as f:
                    f.write(conteudo)
                alterados.append({"nome": rel, "acao": "restaurado" if atual is not None else "recriado"})

    for rel in sorted(criados_depois):
        alvo = os.path.abspath(os.path.join(pasta_raiz, rel.replace("/", os.sep)))
        atual = _ler_conteudo_atual(alvo)
        if atual is None:
            continue
        registrar_edicao(alvo, atual, None)
        try:
            mover_para_lixeira(alvo)
        except OSError as e:
            return jsonify({"status": "error", "message": str(e)}), 500
        alterados.append({"nome": rel, "acao": "removido (criado após o ponto)"})

    return jsonify({"status": "ok", "altered": alterados, "count": len(alterados)})
